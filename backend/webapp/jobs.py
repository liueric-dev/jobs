"""
The read surface: a ranked list, one job in full, and where interactions land.

TENANCY. Every query here is scoped to `user.profile`, taken from the SESSION
and never from a request parameter. That is the whole model. A `?profile=`
parameter would turn one forgotten check into a cross-user data leak, and there
is no reason for a client to name a profile it does not choose.

THE JOIN IS ALREADY WRITTEN. Reads go through the `jobs_app` view in
../schema.py, which joins jobs + job_facts + job_matches + job_scores and drops
rows with no company, title, url or description. Its docstring explains why
that filter lives at the read edge rather than as a NOT NULL: builtin-nyc.py
legitimately writes a listing row first and fills description_text days later,
so partial rows exist on purpose and nothing downstream should see one. Do not
reimplement the join here.
"""

import base64
import json
import logging
from datetime import datetime, timedelta, timezone

import config  # noqa: F401  (must come first -- performs the sys.path insert)

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from auth import User, require_user
from db import db
from lib.timeparse import utc_now_str

log = logging.getLogger("webapp.jobs")

router = APIRouter()

DEFAULT_LIMIT = 25
MAX_LIMIT = 100

#: The closed set of interaction types. job_events.event is free TEXT, so this
#: allowlist is the only thing keeping the table analysable a year from now,
#: when the learned ranker in docs/SCORING.md wants to read it. A typo'd event
#: name is worse than a rejected one: it is silently unusable training data.
EVENT_NAMES = ("impression", "open", "save", "unsave", "dismiss", "applied")

#: How long before the same profile's impression of the same job counts again.
#: A list re-render is not new information; without this the table's most
#: common row is also its least meaningful one.
IMPRESSION_DEDUP_HOURS = 24

#: Columns returned by the list endpoint. description_text is deliberately
#: absent -- it is the largest column in the database and the list has
#: `summary` from job_facts for exactly this purpose. Names match the view's
#: own column names; the frontend does not exist yet to have an opinion, and a
#: translation layer between two things that agree is pure maintenance.
LIST_COLUMNS = (
    "id", "platform", "company_name", "title", "job_url", "location_raw",
    "location_is_nyc", "location_is_remote", "department", "seniority_guess",
    "posted_at_ts", "first_seen", "last_seen", "salary", "comp_min", "comp_max",
    "comp_currency", "seniority_level", "years_experience_min", "role_archetype",
    "tech_stack", "ai_involvement", "remote_policy", "employment_type",
    "visa_sponsorship", "gap_friendly_language", "summary", "match_score",
    "match_reasons", "fit_score", "primary_track", "gap_bridging_angle",
    "risk_factors", "key_technologies",
)

DETAIL_COLUMNS = LIST_COLUMNS + ("description_text",)

#: coalesce to -infinity rather than ORDER BY ... NULLS LAST, because it makes
#: the keyset comparison below a plain row comparison instead of three-branch
#: NULL logic. -infinity sorts last under DESC, which is the same thing NULLS
#: LAST means here.
#:
#: posted_at_ts, never posted_at: the latter is TEXT and holds three
#: incompatible formats including Built In's relative English ("Reposted 8
#: Hours Ago"), which no database can order. See ../schema.py.
_SORT_TS = "coalesce(v.posted_at_ts, '-infinity'::timestamptz)"
ORDER_BY = f"v.match_score DESC, {_SORT_TS} DESC, v.id ASC"


# --------------------------------------------------------------------------
# Cursor
# --------------------------------------------------------------------------

def encode_cursor(match_score, posted_at_ts, job_id):
    """Opaque keyset cursor: the sort tuple, base64'd.

    Keyset rather than OFFSET because the list is re-ranked nightly -- match.py
    rebuilds job_matches whenever facts or criteria move. An offset taken
    before that and used after silently skips or repeats rows; a sort-tuple
    cursor stays correct across a re-rank.
    """
    payload = [match_score,
               posted_at_ts.isoformat() if posted_at_ts else None,
               job_id]
    return base64.urlsafe_b64encode(json.dumps(payload).encode()).decode().rstrip("=")


def decode_cursor(raw):
    try:
        padded = raw + "=" * (-len(raw) % 4)
        score, ts, job_id = json.loads(base64.urlsafe_b64decode(padded))
        return int(score), ts, str(job_id)
    except Exception:
        raise HTTPException(status_code=400, detail="malformed cursor")


def _like(term):
    """Escape a user substring for LIKE. Without this a search for '100%'
    matches everything and a search for '_' matches every single character."""
    return "%" + term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"


#: This profile's interaction state for each row. The lookup is by
#: (profile, job_id), which is what idx_job_events_profile_job in ../schema.py
#: exists for -- the older (profile, occurred_at DESC) index answers "recent
#: activity" and cannot answer this, so without it every page render is a
#: sequential scan over a table that only grows.
#:
#: save/unsave are resolved by recency rather than by a flag, because the table
#: is append-only: an unsave is a row, not a deletion. occurred_at is TEXT in a
#: fixed-width ISO form, so string comparison IS chronological comparison.
_EVENT_STATE_JOIN = """
        LEFT JOIN LATERAL (
            SELECT bool_or(e.event IN ('impression', 'open')) AS seen,
                   bool_or(e.event = 'dismiss') AS dismissed,
                   bool_or(e.event = 'applied') AS applied,
                   max(e.occurred_at) FILTER (WHERE e.event = 'save') AS last_save,
                   max(e.occurred_at) FILTER (WHERE e.event = 'unsave') AS last_unsave
            FROM job_events e
            WHERE e.profile = v.profile AND e.job_id = v.id
        ) ev ON TRUE
"""


# --------------------------------------------------------------------------
# List
# --------------------------------------------------------------------------

@router.get("/v1/jobs")
def list_jobs(
    user: User = Depends(require_user),
    limit: int = Query(DEFAULT_LIMIT, ge=1, le=MAX_LIMIT),
    cursor: str | None = None,
    q: str | None = None,
    remote: bool | None = None,
    nyc: bool | None = None,
    min_score: int | None = None,
    since: str | None = Query(None, description="ISO date; posted_at_ts >= this"),
    exclude_dismissed: bool = False,
):
    where = ["v.profile = %s"]
    params = [user.profile]

    if cursor:
        score, ts, job_id = decode_cursor(cursor)
        # Both leading keys sort DESC, so "strictly after the cursor" is a
        # plain row comparison; id breaks the tie ascending.
        where.append(
            f"(((v.match_score, {_SORT_TS}) < (%s, coalesce(%s::timestamptz, "
            f"'-infinity'::timestamptz))) OR (v.match_score = %s AND {_SORT_TS} = "
            f"coalesce(%s::timestamptz, '-infinity'::timestamptz) AND v.id > %s))")
        params += [score, ts, score, ts, job_id]
    if q:
        where.append("(v.title ILIKE %s OR v.company_name ILIKE %s)")
        params += [_like(q), _like(q)]
    if remote is not None:
        where.append("coalesce(v.location_is_remote, FALSE) = %s")
        params.append(remote)
    if nyc is not None:
        where.append("coalesce(v.location_is_nyc, FALSE) = %s")
        params.append(nyc)
    if min_score is not None:
        where.append("v.match_score >= %s")
        params.append(min_score)
    if since:
        where.append("v.posted_at_ts >= %s::timestamptz")
        params.append(since)
    if exclude_dismissed:
        where.append("NOT coalesce(ev.dismissed, FALSE)")

    columns = ", ".join(f"v.{c}" for c in LIST_COLUMNS)
    sql = f"""
        SELECT {columns},
               coalesce(ev.seen, FALSE) AS seen,
               coalesce(ev.dismissed, FALSE) AS dismissed,
               coalesce(ev.applied, FALSE) AS applied,
               (ev.last_save IS NOT NULL
                AND (ev.last_unsave IS NULL OR ev.last_save > ev.last_unsave)) AS saved
        FROM jobs_app v
        {_EVENT_STATE_JOIN}
        WHERE {' AND '.join(where)}
        ORDER BY {ORDER_BY}
        LIMIT %s
    """
    params.append(limit + 1)   # one extra row: is there a next page?

    with db() as conn:
        rows = conn.execute(sql, params).fetchall()

    has_more = len(rows) > limit
    rows = rows[:limit]
    names = list(LIST_COLUMNS) + ["seen", "dismissed", "applied", "saved"]
    items = [dict(zip(names, r)) for r in rows]

    next_cursor = None
    if has_more and items:
        last = items[-1]
        next_cursor = encode_cursor(last["match_score"], last["posted_at_ts"], last["id"])

    return {"jobs": items, "next_cursor": next_cursor, "profile": user.profile}


# --------------------------------------------------------------------------
# Detail
# --------------------------------------------------------------------------

@router.get("/v1/jobs/{job_id}")
def get_job(job_id: str, user: User = Depends(require_user)):
    columns = ", ".join(f"v.{c}" for c in DETAIL_COLUMNS)
    with db() as conn:
        row = conn.execute(
            f"""
            SELECT {columns},
                   coalesce(ev.seen, FALSE) AS seen,
                   coalesce(ev.dismissed, FALSE) AS dismissed,
                   coalesce(ev.applied, FALSE) AS applied,
                   (ev.last_save IS NOT NULL
                    AND (ev.last_unsave IS NULL OR ev.last_save > ev.last_unsave)) AS saved
            FROM jobs_app v
            {_EVENT_STATE_JOIN}
            WHERE v.profile = %s AND v.id = %s
            """,
            (user.profile, job_id),
        ).fetchone()

    if row is None:
        # 404, not 403: "exists but isn't yours" and "doesn't exist" should be
        # indistinguishable to anyone enumerating ids.
        raise HTTPException(status_code=404, detail="no such job for this profile")
    names = list(DETAIL_COLUMNS) + ["seen", "dismissed", "applied", "saved"]
    return dict(zip(names, row))


# --------------------------------------------------------------------------
# Events
# --------------------------------------------------------------------------

class Event(BaseModel):
    job_id: str
    event: str


class EventBatch(BaseModel):
    # A list, so a page of impressions is one request rather than twenty.
    events: list[Event] = Field(default_factory=list, max_length=200)


@router.post("/v1/events")
def record_events(batch: EventBatch, user: User = Depends(require_user)):
    """Record interactions.

    match_score and fit_score are looked up SERVER-SIDE and never accepted from
    the client. docs/SCORING.md makes this the load-bearing property of the
    whole table: "Recording match_score and fit_score AS OF the impression is
    the load-bearing part -- without them you cannot reconstruct what the user
    was reacting to once weights change." A client-supplied score would be
    unverifiable training data, which is worse than none. It is the same rule
    api/ applies to postings, arrived at independently.
    """
    bad = sorted({e.event for e in batch.events} - set(EVENT_NAMES))
    if bad:
        raise HTTPException(
            status_code=400,
            detail=f"unknown event(s) {bad}; expected one of {list(EVENT_NAMES)}")

    if not batch.events:
        return {"recorded": 0, "deduped": 0, "skipped": 0}

    now = utc_now_str()
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=IMPRESSION_DEDUP_HOURS)
              ).strftime("%Y-%m-%dT%H:%M:%S")

    recorded = deduped = 0
    with db() as conn:
        # One query for the whole batch: which of these jobs are actually in
        # this profile's matches. Doing it up front is what lets a zero-row
        # insert below be reported as "deduped" rather than lumped in with
        # "unknown job" -- a client bug should be visible, not silent.
        known = {r[0] for r in conn.execute(
            "SELECT job_id FROM job_matches WHERE profile = %s AND job_id = ANY(%s)",
            (user.profile, [e.job_id for e in batch.events]),
        ).fetchall()}

        for e in batch.events:
            if e.job_id not in known:
                continue
            row = conn.execute(
                """
                INSERT INTO job_events (profile, job_id, event, match_score,
                                        fit_score, occurred_at)
                SELECT m.profile, m.job_id, %s, m.match_score,
                       (SELECT s.fit_score FROM job_scores s
                         WHERE s.job_id = m.job_id AND s.profile = m.profile),
                       %s
                FROM job_matches m
                WHERE m.profile = %s AND m.job_id = %s
                  AND (%s <> 'impression' OR NOT EXISTS (
                        SELECT 1 FROM job_events prior
                         WHERE prior.profile = m.profile AND prior.job_id = m.job_id
                           AND prior.event = 'impression' AND prior.occurred_at >= %s))
                RETURNING id
                """,
                (e.event, now, user.profile, e.job_id, e.event, cutoff),
            ).fetchone()
            if row:
                recorded += 1
            else:
                deduped += 1
        conn.commit()

    skipped = len(batch.events) - recorded - deduped
    if skipped:
        log.info("dropped %d event(s) for jobs not in profile %s", skipped, user.profile)
    return {"recorded": recorded, "deduped": deduped, "skipped": skipped}

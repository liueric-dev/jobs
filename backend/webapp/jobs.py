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
import uuid
from datetime import datetime, timedelta, timezone

import config  # noqa: F401  (must come first -- performs the sys.path insert)

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from auth import User, require_user
from db import db
from lib.timeparse import utc_now_str

log = logging.getLogger("webapp.jobs")

router = APIRouter()

DEFAULT_LIMIT = 25
MAX_LIMIT = 100

#: The closed set of interaction types a CLIENT may send. job_events.event is
#: free TEXT, so this allowlist is the only thing keeping the table analysable a
#: year from now, when the learned ranker in docs/SCORING.md wants to read it. A
#: typo'd event name is worse than a rejected one: it is silently unusable
#: training data.
CLIENT_EVENT_NAMES = ("impression", "open", "save", "unsave", "dismiss", "applied")

#: Written by the server, never accepted from a client. A `skip` is DERIVED --
#: see derive_skips() -- and a client that sends one is asserting something it
#: cannot know, because the derivation's whole input is the render state the
#: server issued. Kept as a separate tuple rather than a flag on the one above
#: so that "may a client send this" and "may this be stored" cannot drift apart:
#: the validator reads the first, the schema check reads the union.
SERVER_EVENT_NAMES = ("skip",)

#: Everything that may appear in job_events.event, from either writer.
EVENT_NAMES = CLIENT_EVENT_NAMES + SERVER_EVENT_NAMES

#: The dismiss vocabulary (tranche_five/27). A closed enum rather than free
#: text, and the values map onto existing features deliberately: a `wrong_level`
#: dismiss is evidence about the seniority weight, not about one posting, which
#: is what task 31 consumes. Free text would be unreadable at cohort scale and
#: un-joinable to any feature.
DISMISS_REASONS = ("wrong_level", "wrong_role", "wrong_location",
                   "bad_company", "stale_posting", "other")

#: Who may see an event, set server-side by event type and NEVER by the client.
#: Only a save is cohort-visible. An application is private on purpose: in a
#: cohort competing for the same entry-level roles, seeing who else applied is
#: discouraging at best. Task 25's watcher model must keep the same answer --
#: two different answers to "what is shared" is how a privacy promise gets
#: broken by accident.
VISIBILITY_PRIVATE = "private"
VISIBILITY_COHORT = "cohort_anon"
COHORT_VISIBLE_EVENTS = ("save",)

#: The events whose meaning IS a position, and which are therefore rejected
#: without a rank. Deliberately narrower than API-CONTRACT-v1.md's "reject a
#: batch missing request_id or any rank", and the deviation is the contract's
#: own doing: it says a detail-page request "is not an impression", so a `save`
#: or `applied` raised from GET /v1/jobs/{id} has no position in any render.
#: Requiring a rank there would force a client to invent one, which is the
#: sentinel this task refused in the schema wearing different clothes. rank is
#: still stored whenever it is supplied.
RANK_REQUIRED_EVENTS = ("impression", "open")

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
# Errors
# --------------------------------------------------------------------------

class ContractError(HTTPException):
    """A 400 in API-CONTRACT-v1.md's envelope: {"error": {code, message, ...}}.

    A subclass rather than a bare HTTPException because FastAPI's default
    handler wraps every detail in {"detail": ...}, which is one level deeper
    than the contract's shape. app.py registers contract_error_handler for this
    type alone, so auth.py's and label.py's existing 4xx bodies do not move.

    `code` is the machine-readable half and is what a client branches on;
    `message` is for a person reading a log. The contract's own examples use
    snake_case codes ("missing_rank").
    """

    def __init__(self, code, message, request_id=None):
        super().__init__(status_code=400, detail=message)
        self.code = code
        self.message = message
        self.request_id = request_id


async def contract_error_handler(request, exc):
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": {"code": exc.code,
                           "message": exc.message,
                           "request_id": exc.request_id}},
    )


# --------------------------------------------------------------------------
# Render identity
# --------------------------------------------------------------------------

def new_request_id():
    """Identify one rendered list, so events can be attributed back to it.

    Minted server-side and returned with the list. A client cannot be trusted
    to generate it -- not because it would lie, but because two clients would
    eventually collide and the collision would look like one enormous render
    with duplicate ranks, which is indistinguishable from correct data after
    the fact.

    uuid4 rather than the contract's ULID-shaped example: this is a stdlib-only
    service (see ../.claude/CLAUDE.md on dependencies) and nothing sorts or
    range-scans on this column -- idx_job_events_request leads with profile.
    The `req_` prefix is kept because it is what makes the value legible in a
    log line, which is the only place a person ever reads one.
    """
    return "req_" + uuid.uuid4().hex


# --------------------------------------------------------------------------
# Cursor
# --------------------------------------------------------------------------

#: Bumped when the cursor payload's shape changes. A cursor is opaque, but it
#: is also the one value a client holds across a deploy, so a stale one must
#: fail loudly rather than be reinterpreted -- silence is this system's default
#: failure mode and a misread cursor would silently skip or repeat rows.
CURSOR_VERSION = 2


def encode_cursor(match_score, posted_at_ts, job_id, request_id, next_rank):
    """Opaque keyset cursor: the sort tuple, the render, and the next rank.

    Keyset rather than OFFSET because the list is re-ranked nightly -- match.py
    rebuilds job_matches whenever facts or criteria move. An offset taken
    before that and used after silently skips or repeats rows; a sort-tuple
    cursor stays correct across a re-rank.

    THE RENDER SPANS PAGES, WHICH IS WHY request_id AND next_rank RIDE HERE.
    API-CONTRACT-v1.md requires `rank` to be "global across the render, not
    per-track", and a paginated list is still one render: the ordering the user
    actually saw runs 1..N across every page they scrolled. Carrying the pair in
    the cursor keeps that true with NO server-side render state -- the
    alternative is a table of open renders, which is a session store with a
    different name and an expiry policy nobody would maintain.
    """
    payload = {"v": CURSOR_VERSION,
               "s": match_score,
               "t": posted_at_ts.isoformat() if posted_at_ts else None,
               "i": job_id,
               "r": request_id,
               "k": next_rank}
    return base64.urlsafe_b64encode(json.dumps(payload).encode()).decode().rstrip("=")


def decode_cursor(raw):
    """(score, ts, job_id, request_id, next_rank), or 400.

    A v1 cursor -- the three-element list this issued before ranks existed --
    is rejected rather than upgraded. It has no request_id and no rank origin,
    so continuing it would either invent a second request_id mid-render or
    restart ranks at 1 on page two, and both produce log rows that look valid
    and are not. A 400 costs the client one un-cursored refetch.
    """
    try:
        padded = raw + "=" * (-len(raw) % 4)
        payload = json.loads(base64.urlsafe_b64decode(padded))
        if payload.get("v") != CURSOR_VERSION:
            raise ValueError("cursor version")
        return (int(payload["s"]), payload["t"], str(payload["i"]),
                str(payload["r"]), int(payload["k"]))
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

    # A call without a cursor STARTS a render; a call with one continues the
    # render the cursor names. That is the whole rule, and it is what makes
    # `rank` global across pages rather than restarting at 1 on page two.
    request_id = new_request_id()
    first_rank = 1

    if cursor:
        score, ts, job_id, request_id, first_rank = decode_cursor(cursor)
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

    # 1-based and continuing across pages. This is the position the user saw,
    # and it is the only field in the response that cannot be recomputed later:
    # ORDER_BY reads match_score and posted_at_ts, both of which the nightly run
    # is free to change before anyone asks the question.
    for offset, item in enumerate(items):
        item["rank"] = first_rank + offset

    next_cursor = None
    if has_more and items:
        last = items[-1]
        next_cursor = encode_cursor(last["match_score"], last["posted_at_ts"],
                                    last["id"], request_id, first_rank + len(items))

    return {"request_id": request_id, "jobs": items,
            "next_cursor": next_cursor, "profile": user.profile}


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
    # All three optional at the model layer and validated in the handler, so
    # that a contract violation comes back as the contract's own 400 envelope
    # rather than FastAPI's 422. Which fields are required depends on `event`,
    # which pydantic would express as a discriminated union of six models --
    # more machinery than the rule deserves, and it would still produce the
    # wrong error shape.
    rank: int | None = Field(default=None, ge=1)
    dwell_ms: int | None = Field(default=None, ge=0)
    reason: str | None = None


class EventBatch(BaseModel):
    # A list, so a page of impressions is one request rather than twenty.
    events: list[Event] = Field(default_factory=list, max_length=200)
    # Required by the contract, optional here for the reason above.
    request_id: str | None = None


def visibility_for(event):
    """Who may see this event. Server-side, by type, never from the client."""
    return VISIBILITY_COHORT if event in COHORT_VISIBLE_EVENTS else VISIBILITY_PRIVATE


def validate_batch(batch):
    """Raise ContractError on anything that would produce unusable rows.

    Everything here fails the whole batch rather than dropping the offending
    event. That is deliberate and it is the contract's instruction -- "fail
    loudly; silence is this system's default failure mode and the API should
    not add to it". A partially-accepted impression batch is the worst outcome
    available: the render's rank sequence acquires holes that are
    indistinguishable from items the user never scrolled to.
    """
    bad = sorted({e.event for e in batch.events} - set(CLIENT_EVENT_NAMES))
    if bad:
        # A server-only name gets its own message, because "unknown event
        # 'skip'" would send a client author looking for a typo when the real
        # answer is that the server derives it.
        server_sent = sorted(set(bad) & set(SERVER_EVENT_NAMES))
        if server_sent:
            raise ContractError(
                "server_derived_event",
                f"event(s) {server_sent} are derived server-side and may not be sent",
                batch.request_id)
        raise ContractError(
            "unknown_event",
            f"unknown event(s) {bad}; expected one of {list(CLIENT_EVENT_NAMES)}",
            batch.request_id)

    if not batch.request_id:
        raise ContractError(
            "missing_request_id",
            "request_id is required; echo the one GET /v1/jobs returned", None)

    for e in batch.events:
        if e.event in RANK_REQUIRED_EVENTS and e.rank is None:
            raise ContractError(
                "missing_rank",
                f"event '{e.event}' for job {e.job_id} requires rank; an "
                f"impression without a position is un-debiasable",
                batch.request_id)
        if e.reason is not None:
            if e.event != "dismiss":
                raise ContractError(
                    "reason_not_allowed",
                    f"reason is only meaningful on dismiss, not '{e.event}'",
                    batch.request_id)
            if e.reason not in DISMISS_REASONS:
                raise ContractError(
                    "unknown_reason",
                    f"unknown reason '{e.reason}'; expected one of "
                    f"{list(DISMISS_REASONS)}",
                    batch.request_id)
        if e.dwell_ms is not None and e.event != "open":
            raise ContractError(
                "dwell_not_allowed",
                f"dwell_ms is only meaningful on open, not '{e.event}'",
                batch.request_id)


def derive_skips(conn, profile, request_id, rank, now):
    """An open at rank k means every un-actioned item above it was passed over.

    The strongest free negative signal available, and derivable ONLY because
    request_id and rank exist -- which is the argument for task 27 in one
    function. "Un-actioned" is expressed as the absence of any non-impression
    event on that job in this render, which covers both "the user already did
    something with it" and "it was already skipped by an earlier open". That
    second reading is what makes this idempotent: a second open, further down
    the same render, skips only what the first one did not.

    Returns the number of skip rows written.

    ONE LIMIT WORTH KNOWING, and it is an interaction rather than a bug. The
    24-hour impression dedup above is keyed (profile, job_id) and NOT
    (profile, job_id, request_id), so a second render of the same list within
    the window writes no impression rows -- and this derivation, which reads
    impressions, therefore finds nothing to skip in it. Skips are consequently
    a first-render-per-day signal. Narrowing the dedup key would change an
    existing documented behaviour ("a list re-render is not new information")
    for a different task's benefit, so it is recorded here and in
    docs/ingest/engagement-events.md rather than changed in passing.
    """
    rows = conn.execute(
        """
        INSERT INTO job_events (profile, job_id, event, request_id, rank,
                                visibility, match_score, fit_score,
                                criteria_version, occurred_at)
        SELECT imp.profile, imp.job_id, 'skip', imp.request_id, imp.rank,
               %s, imp.match_score, imp.fit_score, imp.criteria_version, %s
        FROM job_events imp
        WHERE imp.profile = %s
          AND imp.request_id = %s
          AND imp.event = 'impression'
          AND imp.rank IS NOT NULL
          AND imp.rank < %s
          AND NOT EXISTS (
                SELECT 1 FROM job_events other
                 WHERE other.profile = imp.profile
                   AND other.request_id = imp.request_id
                   AND other.job_id = imp.job_id
                   AND other.event <> 'impression')
        RETURNING id
        """,
        (VISIBILITY_PRIVATE, now, profile, request_id, rank),
    ).fetchall()
    return len(rows)


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

    criteria_version and visibility join them on the same principle, for two
    different reasons. criteria_version is read from job_matches beside
    match_score because it names the weight generation that produced the order
    the user reacted to -- ../schema.py's job_scores block already states this
    as the reason that column exists there. visibility is set by event type
    because it is a privacy control, and a privacy control a client can set is
    not one.
    """
    validate_batch(batch)

    if not batch.events:
        return {"recorded": 0, "deduped": 0, "skipped": 0, "derived_skips": 0}

    now = utc_now_str()
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=IMPRESSION_DEDUP_HOURS)
              ).strftime("%Y-%m-%dT%H:%M:%S")

    recorded = deduped = derived = 0
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
                INSERT INTO job_events (profile, job_id, event, request_id, rank,
                                        dwell_ms, reason, visibility, match_score,
                                        fit_score, criteria_version, occurred_at)
                SELECT m.profile, m.job_id, %s, %s, %s, %s, %s, %s, m.match_score,
                       (SELECT s.fit_score FROM job_scores s
                         WHERE s.job_id = m.job_id AND s.profile = m.profile),
                       m.criteria_version, %s
                FROM job_matches m
                WHERE m.profile = %s AND m.job_id = %s
                  AND (%s <> 'impression' OR NOT EXISTS (
                        SELECT 1 FROM job_events prior
                         WHERE prior.profile = m.profile AND prior.job_id = m.job_id
                           AND prior.event = 'impression' AND prior.occurred_at >= %s))
                RETURNING id
                """,
                (e.event, batch.request_id, e.rank, e.dwell_ms, e.reason,
                 visibility_for(e.event), now, user.profile, e.job_id, e.event,
                 cutoff),
            ).fetchone()
            if row:
                recorded += 1
                # AFTER the open's own row, never before: the derivation
                # excludes any job with a non-impression event in this render,
                # and the job just opened must be one of them.
                if e.event == "open":
                    derived += derive_skips(conn, user.profile, batch.request_id,
                                            e.rank, now)
            else:
                deduped += 1
        # One transaction for the batch, so an open and the skips it implies
        # are never separately visible. A reader that saw the open alone would
        # measure a render in which nothing above it was passed over.
        conn.commit()

    skipped = len(batch.events) - recorded - deduped
    if skipped:
        log.info("dropped %d event(s) for jobs not in profile %s", skipped, user.profile)
    return {"recorded": recorded, "deduped": deduped, "skipped": skipped,
            "derived_skips": derived}

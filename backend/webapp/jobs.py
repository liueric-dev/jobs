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
from schema_web import DISMISS_REASONS
from lib.timeparse import utc_now_str

log = logging.getLogger("webapp.jobs")

router = APIRouter()

DEFAULT_LIMIT = 25
MAX_LIMIT = 100

#: The closed set of interaction types a CLIENT may send. job_events.event is
#: free TEXT, so this allowlist is the only thing keeping the table analysable a
#: year from now, when the learned ranker in ../docs/SCORING.md wants to read it. A
#: typo'd event name is worse than a rejected one: it is silently unusable
#: training data.
#:
#: `undismiss` is the undo (tranche_six/31). It is a row rather than a deletion
#: of the dismiss it reverses, for the reason that task gives: "the fact that
#: someone reversed a dismissal is itself signal, and deletion loses it". It is
#: shaped on `unsave`, which had already answered the same question.
CLIENT_EVENT_NAMES = ("impression", "open", "save", "unsave", "dismiss",
                      "undismiss", "applied")

#: Written by the server, never accepted from a client. A `skip` is DERIVED --
#: see derive_skips() -- and a client that sends one is asserting something it
#: cannot know, because the derivation's whole input is the render state the
#: server issued. Kept as a separate tuple rather than a flag on the one above
#: so that "may a client send this" and "may this be stored" cannot drift apart:
#: the validator reads the first, the schema check reads the union.
SERVER_EVENT_NAMES = ("skip",)

#: Everything that may appear in job_events.event, from either writer.
EVENT_NAMES = CLIENT_EVENT_NAMES + SERVER_EVENT_NAMES

#: The dismiss vocabulary (tranche_five/27), consumed by task 31's aggregation,
#: is IMPORTED from schema_web above and is not defined here any more -- so that
#: the CHECK on builder_job_state.dismiss_reason and this request validator read
#: one tuple. `jobs.DISMISS_REASONS` still resolves, which is what every
#: existing citation names (tests/test_events.py, and the defect register at
#: refactor-freeze-2026-08-02).

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

#: How long before the same Builder's impression of the same job counts again.
#: A list re-render is not new information; without this the table's most
#: common row is also its least meaningful one.
#:
#: OQ-2, decided 2026-08-03: keyed on (app_user_id, job_id), not (profile,
#: job_id). Thirty Builders share the `pursuit` profile, so the old key let
#: the first Builder to load the list suppress every other Builder's
#: impression of those postings for the window -- and derive_skips reads
#: impressions, so skips inherited the same suppression. See
#: docs/STATE-OF-THE-SYSTEM.md § 4 and DEV_TASKS.md's closed OQ-2 for the
#: full argument the owner weighed before picking this key.
IMPRESSION_DEDUP_HOURS = 24

#: Columns returned by the list endpoint. description_text is deliberately
#: absent -- it is the largest column in the database and the list has
#: `summary` from job_facts for exactly this purpose. Names match the view's
#: own column names; the frontend does not exist yet to have an opinion, and a
#: translation layer between two things that agree is pure maintenance.
#:
#: ORDER IS PART OF THE CONTRACT, not a style choice. frontend/verify_fixtures.py
#: parses this tuple out of this file with `ast` and asserts the exact key set
#: AND key order of every job object in frontend/fixtures/shipped/. So appending
#: here means hand-editing five fixture files in the same commit -- there is no
#: generator, and the backend suite is red in between. role_track is last for
#: the separate reason recorded beside it in schema._APP_VIEW_SQL: the view can
#: only append, and a reorder there costs the view its GRANTs.
LIST_COLUMNS = (
    "id", "platform", "company_name", "title", "job_url", "location_raw",
    "location_is_nyc", "location_is_remote", "department", "seniority_guess",
    "posted_at_ts", "first_seen", "last_seen", "salary", "comp_min", "comp_max",
    "comp_currency", "seniority_level", "years_experience_min", "role_archetype",
    "tech_stack", "ai_involvement", "remote_policy", "employment_type",
    "visa_sponsorship", "gap_friendly_language", "summary", "match_score",
    "match_reasons", "fit_score", "primary_track", "gap_bridging_angle",
    "risk_factors", "key_technologies", "role_track",
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


#: THIS Builder's event-derived state for each row -- `seen` and `applied`,
#: the half of the state that cannot live in builder_job_state because it is
#: derived from the append-only log rather than written as a current answer.
#:
#: IT USED TO READ `e.profile = v.profile`, AND THAT WAS DEFECTS D66 AND D67
#: (defect register, deleted 2026-08-02:
#: `git show refactor-freeze-2026-08-02:docs/ingest/DEFECTS.md`). Thirty
#: Builders share the `pursuit` profile, so one Builder's impression marked
#: the row `seen` for all thirty and one
#: Builder's application marked it `applied` for all thirty. D67 was the
#: sharper one: visibility_for("applied") correctly stores an application as
#: `private` and API-CONTRACT-v1.md calls it private, and the response body
#: then leaked the same fact anyway -- the control enforced in the column and
#: defeated in the join. It was invisible at one Builder (every value of
#: e.profile belonged to one person, so the join was accidentally correct) and
#: wrong at two, with no error on the day it turned. Both are closed by
#: job_events.app_user_id (../schema.py, add_missing_columns on EVENTS_TABLE).
#:
#: THE PROFILE IS DELIBERATELY GONE FROM THE PREDICATE, not merely joined by
#: an extra column. A user id already names exactly one Builder; re-adding
#: `e.profile = v.profile` would silently drop that Builder's own events from
#: before a profile change (manage_app_users.py:136, cmd_set_profile -- the
#: only supported way to move a user), which is a second wrong answer reached
#: from the same wrong idea that the profile identifies a person.
#:
#: The lookup is by (app_user_id, job_id), which is what idx_job_events_user_job
#: in ../schema.py exists for -- the older (profile, job_id) index cannot answer
#: this question and (profile, occurred_at DESC) answers "recent activity", so
#: without it every page render is a sequential scan over a table that only
#: grows.
#:
#: PRE-COLUMN ROWS HAVE app_user_id NULL AND RESOLVE TO FALSE, for everyone.
#: That is the intended direction: the equality never matches NULL, so an event
#: nobody can be shown to have generated is attributed to nobody, rather than
#: to whoever happens to be asking. ../schema.py says why they are not
#: backfilled.
#:
#: IT TAKES A PARAMETER AND IT COMES FIRST -- before _BUILDER_STATE_JOIN's,
#: which is spliced in after it, and before anything the WHERE contributes.
#: Both are user.id, so these two cannot be swapped against each other into a
#: wrong answer; the WHERE's params still can. See _BUILDER_STATE_JOIN.
#:
#: dismissed and saved USED to be resolved here too, by event recency. They are
#: not any more -- see _BUILDER_STATE_JOIN.
_EVENT_STATE_JOIN = """
        LEFT JOIN LATERAL (
            SELECT bool_or(e.event IN ('impression', 'open')) AS seen,
                   bool_or(e.event = 'applied') AS applied
            FROM job_events e
            WHERE e.app_user_id = %s AND e.job_id = v.id
        ) ev ON TRUE
"""

#: THIS Builder's state for each row, and the whole of task 31 in four lines.
#:
#: job_matches is keyed (job_id, profile) and thirty Builders share the cohort
#: profile, so anything per-person has to live beside it rather than in it.
#: Ranking stays cohort-level and cheap -- one match row per posting, not
#: thirty -- and the personal part is a read-time join. That is the same
#: fixed-effect/random-effect split as task 26's config inheritance and the
#: ranker's eventual shape, kept deliberately consistent.
#:
#: IT TAKES A PARAMETER, AND THE PARAMETER COMES BEFORE THE WHERE'S. Both this
#: fragment and _EVENT_STATE_JOIN are spliced in ahead of the WHERE clause, so
#: the params list LEADS with their two -- _EVENT_STATE_JOIN's user.id, then
#: this one's -- before anything the WHERE contributes. Getting that backwards
#: does not raise: it compares a user id against a profile name, finds nothing,
#: and silently reports every Builder as having no state. The two leading
#: values are both user.id and so are interchangeable with each other; it is
#: the boundary against the WHERE that matters. tests/test_event_replay.py
#: TestListState is what fails if it is ever reordered.
_BUILDER_STATE_JOIN = """
        LEFT JOIN builder_job_state bs
               ON bs.app_user_id = %s AND bs.job_id = v.id
"""

#: The four state fields in the response, in one place so the list and the
#: detail endpoint cannot answer the same question differently.
_STATE_COLUMNS = """
               coalesce(ev.seen, FALSE) AS seen,
               coalesce(ev.applied, FALSE) AS applied,
               (bs.dismissed_at IS NOT NULL) AS dismissed,
               (bs.saved_at IS NOT NULL) AS saved,
               bs.dismiss_reason
"""

#: Their names, in the order _STATE_COLUMNS selects them.
STATE_FIELDS = ("seen", "applied", "dismissed", "saved", "dismiss_reason")

#: The cohort badge (tranche_five/28), read from the MATERIALISED table and
#: never from job_events. That is the whole point of the table: the suppression
#: rule lives in exactly one place -- ../cohort.py's nightly fold -- so no
#: future endpoint can forget it by writing its own count. Nothing in this
#: package may query job_events for a save count; if it does, the rule now has
#: two implementations and only one of them was reviewed.
#:
#: IT NEEDS NO PARAMETER, and that is deliberate rather than lucky. Both other
#: joins here take a %s and the file's comments are emphatic about what
#: reordering them silently does. `cs.cohort_profile = v.profile` gets the same
#: answer from a column the view already carries and the WHERE has already
#: pinned to user.profile, so this fragment cannot be spliced in at the wrong
#: position because it has no position to get wrong.
#:
#: A MISS IS THE COMMON CASE AND IS NOT AN ERROR. Postings below the threshold
#: have no row at all -- see ../schema.py, which explains why absence rather
#: than a NULL bucket is what suppression has to look like -- so the LEFT JOIN
#: misses for almost every posting and renders as null.
_COHORT_SIGNAL_JOIN = """
        LEFT JOIN cohort_signal cs
               ON cs.job_id = v.id AND cs.cohort_profile = v.profile
"""

#: save_bucket ALONE. cohort_signal.computed_at is not selected and must not be:
#: it is a per-posting timestamp that moves when the underlying set moves, which
#: hands a client the recency channel the bucketing exists to close.
_COHORT_COLUMNS = """
               cs.save_bucket
"""

#: The raw column's name in the zip, popped before the response is built.
_COHORT_RAW_FIELD = "save_bucket"

#: The response key. A tuple so that anything reading this module's constants
#: -- ../../frontend/verify_fixtures.py parses them out with `ast` -- sees the
#: field the same way it sees LIST_COLUMNS and STATE_FIELDS.
COHORT_FIELDS = ("cohort_signal",)


def cohort_signal(save_bucket):
    """{"save_bucket": '3-5'|'6-10'|'10+'} for a posting with a badge, else None.

    NESTED RATHER THAN FLAT because that is the shape
    ../../frontend/fixtures/contract/GET_v1_jobs.json already declares, down to
    the key name, and task 32 nests the rest of the payload around it. A flat
    string here would have to be renamed later for no gain now.

    null is the answer for BOTH "nobody saved this" and "one or two Builders
    saved this", and the endpoint cannot tell them apart either -- the row does
    not exist in the first place. That is the requirement, not a limitation:
    absence of a badge must not be readable as "exactly one or two".
    """
    return None if save_bucket is None else {"save_bucket": save_bucket}


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
    include_dismissed: bool = Query(
        False, description="debugging only; dismissed postings are hidden by default"),
):
    """The ranked list for this Builder's profile.

    THE `cohort_signal` SUPPRESSION THRESHOLD IS A PRIVACY CONTROL, NOT A
    DISPLAY PREFERENCE. A posting fewer than schema.COHORT_MIN_SAVERS Builders
    have currently saved carries no badge at all -- not "1 Builder", not a
    greyed-out zero -- and absence must stay unreadable as "exactly one or
    two". The reason is arithmetic rather than caution: in a thirty-person
    cohort who see each other in a classroom, "1 Builder saved this" plus
    knowing who was on their laptop plus a posting for a role somebody
    mentioned out loud is an identification. Aggregates are not automatically
    anonymous at this scale.

    So: whoever is looking at this later because the badge never appears --
    the live cohort is two Builders, three is the floor, and an empty badge is
    the CORRECT rendering of a two-person cohort. Lowering the threshold to
    see output is the one change this docstring exists to stop. The buckets
    ('3-5' / '6-10' / '10+') are part of the same control, not formatting: an
    exact count that increments visibly lets an observer infer WHEN somebody
    saved something. tranche_five/28-cohort-aggregation.md § The small-N
    problem is the full argument; the rule itself is in ../schema.py.
    """
    # THE JOINS' PARAMETERS LEAD. _EVENT_STATE_JOIN and _BUILDER_STATE_JOIN are
    # both spliced in ahead of the WHERE clause, in that order, so their two %s
    # bind before any of the WHERE's -- see the comment on _BUILDER_STATE_JOIN
    # for what a reordering silently does.
    params = [user.id, user.id]

    where = ["v.profile = %s"]
    params.append(user.profile)

    # A dismissal is permanent for that Builder and is the DEFAULT, not a flag
    # the client has to remember to set. This replaces the old
    # `exclude_dismissed` parameter, which defaulted to showing dismissed rows
    # and so made the dismissal mean nothing unless a client opted in.
    # `include_dismissed` exists for reading the state back by hand; it is not
    # part of the client contract.
    if not include_dismissed:
        where.append("bs.dismissed_at IS NULL")

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

    columns = ", ".join(f"v.{c}" for c in LIST_COLUMNS)
    sql = f"""
        SELECT {columns},
        {_STATE_COLUMNS},
        {_COHORT_COLUMNS}
        FROM jobs_app v
        {_EVENT_STATE_JOIN}
        {_BUILDER_STATE_JOIN}
        {_COHORT_SIGNAL_JOIN}
        WHERE {' AND '.join(where)}
        ORDER BY {ORDER_BY}
        LIMIT %s
    """
    params.append(limit + 1)   # one extra row: is there a next page?

    with db() as conn:
        rows = conn.execute(sql, params).fetchall()

    has_more = len(rows) > limit
    rows = rows[:limit]
    names = list(LIST_COLUMNS) + list(STATE_FIELDS) + [_COHORT_RAW_FIELD]
    items = [dict(zip(names, r)) for r in rows]

    # BEFORE `rank` is assigned, so cohort_signal lands ahead of it and the
    # response key order stays LIST_COLUMNS, STATE_FIELDS, cohort_signal, rank
    # -- the order ../../frontend/verify_fixtures.py checks exactly.
    for item in items:
        item[COHORT_FIELDS[0]] = cohort_signal(item.pop(_COHORT_RAW_FIELD))

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
    """One posting in full, INCLUDING one this Builder has dismissed.

    The list hides a dismissal; this does not, and the difference is
    deliberate. Undo has to be reachable, and a client that has just written a
    `dismiss` still needs to render the row it acted on. Filtering here would
    make the undo in tranche_six/31 unimplementable from a detail page.

    `cohort_signal` IS THE SAME MATERIALISED ROW THE LIST SERVES, joined the
    same way and suppressed by the same rule -- the threshold is a privacy
    control and not a display preference, and list_jobs' docstring carries the
    argument. A detail page is where a per-posting count would be most
    tempting to compute live and is exactly where it must not be: this endpoint
    never touches job_events for it.
    """
    columns = ", ".join(f"v.{c}" for c in DETAIL_COLUMNS)
    with db() as conn:
        row = conn.execute(
            f"""
            SELECT {columns},
            {_STATE_COLUMNS},
            {_COHORT_COLUMNS}
            FROM jobs_app v
            {_EVENT_STATE_JOIN}
            {_BUILDER_STATE_JOIN}
            {_COHORT_SIGNAL_JOIN}
            WHERE v.profile = %s AND v.id = %s
            """,
            # user.id leads TWICE: both joins bind before the WHERE, in the
            # order they are spliced. _COHORT_SIGNAL_JOIN adds no third value
            # -- it matches on v.profile, which is already pinned below.
            (user.id, user.id, user.profile, job_id),
        ).fetchone()

    if row is None:
        # 404, not 403: "exists but isn't yours" and "doesn't exist" should be
        # indistinguishable to anyone enumerating ids.
        raise HTTPException(status_code=404, detail="no such job for this profile")
    names = list(DETAIL_COLUMNS) + list(STATE_FIELDS) + [_COHORT_RAW_FIELD]
    item = dict(zip(names, row))
    item[COHORT_FIELDS[0]] = cohort_signal(item.pop(_COHORT_RAW_FIELD))
    return item


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


#: How each event moves builder_job_state, as (SET clause, params-from-`now`).
#: Everything not named here -- impression, open, applied -- leaves the row
#: alone and writes nothing, which is why a Builder who has only ever scrolled
#: has no state row at all rather than an empty one.
#:
#: unsave and undismiss set their column back to NULL rather than deleting the
#: row: the OTHER column may be carrying a live state, and a delete would take
#: it with it. An undismiss also clears dismiss_reason, because a reason
#: outstanding on an undismissed row is a fact about a decision that was
#: reversed, and builder_job_state_reason_needs_dismissal refuses it.
_STATE_WRITES = {
    "dismiss":   ("dismissed_at = %s, dismiss_reason = %s", ("now", "reason")),
    "undismiss": ("dismissed_at = NULL, dismiss_reason = NULL", ()),
    "save":      ("saved_at = %s", ("now",)),
    "unsave":    ("saved_at = NULL", ()),
}


def write_builder_state(conn, app_user_id, job_id, event, reason, now):
    """Move THIS Builder's state for one posting. Returns True if it wrote.

    Called only after the job_events insert returned a row, which is what keeps
    the current state and the evidence behind it from ever disagreeing: an
    event for a job outside this profile's match set records neither, and a
    deduplicated impression is not an event this function has an opinion about.

    The state row is derived from job_events and is not a second source of
    truth -- job_events keeps every dismiss and every undo, and this table
    keeps the current answer. Both are written inside record_events' single
    transaction.
    """
    write = _STATE_WRITES.get(event)
    if write is None:
        return False
    set_clause, wanted = write
    values = {"now": now, "reason": reason}
    set_params = [values[name] for name in wanted]

    # The INSERT names every column the SET could touch, because ON CONFLICT
    # runs only when the row already exists -- a first dismiss has to land its
    # reason on the way in.
    conn.execute(
        f"""
        INSERT INTO builder_job_state (app_user_id, job_id, dismissed_at,
                                       dismiss_reason, saved_at, updated_at)
        VALUES (%s, %s, %s, %s, %s, %s)
        ON CONFLICT (app_user_id, job_id) DO UPDATE
           SET {set_clause}, updated_at = %s
        """,
        (app_user_id, job_id,
         now if event == "dismiss" else None,
         reason if event == "dismiss" else None,
         now if event == "save" else None,
         now,
         *set_params, now),
    )
    return True


def derive_skips(conn, profile, app_user_id, request_id, rank, now):
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
    24-hour impression dedup above is keyed (app_user_id, job_id) -- OQ-2,
    decided 2026-08-03, was narrower than that: the axis it settled was WHO,
    not WHETHER request_id joins the key -- and it is still NOT (app_user_id,
    job_id, request_id), so a second render of the same list BY THE SAME
    BUILDER within the window writes no impression rows -- and this
    derivation, which reads impressions, therefore finds nothing to skip in
    it. Skips are consequently a first-render-per-day signal, per Builder.
    Narrowing the dedup key further would change an existing documented
    behaviour ("a list re-render is not new information") for a different
    task's benefit, so it is recorded here and in
    docs/ingest/engagement-events.md (deleted 2026-08-02; behind
    refactor-freeze-2026-08-02) rather than changed in passing.

    THE DERIVATION IS CONFINED TO ONE BUILDER AT BOTH ENDS -- it reads only the
    caller's own impressions (`imp.app_user_id = %s`, bound to user.id) and only
    the caller's own actions veto them (`other.app_user_id = imp.app_user_id`).
    Both are defect D68 (register deleted 2026-08-02:
    `git show refactor-freeze-2026-08-02:docs/ingest/DEFECTS.md`), which has two
    halves, and this is the paragraph that says why neither is redundant with
    the request_id
    beside them.

    request_id DOES NOT ESTABLISH WHOSE RENDER THIS IS. new_request_id() mints
    one per render and its own docstring says a client cannot be trusted to
    generate it -- but nothing here enforces that. EventBatch.request_id is a
    free-form client string (`request_id: str | None`), validate_batch checks
    only that it is non-empty, and NOTHING RECORDS WHICH USER A MINTED ID WAS
    ISSUED TO: it goes out in the list response, rides the cursor across pages,
    and comes back in the batch unverified. Before this conjunct the only other
    predicate was `imp.profile = %s`, and thirty Builders share `pursuit`.

    Measured before the fix, not reasoned: A reports 7 impressions under
    "req_A"; B posts one `open` echoing "req_A"; the batch returned
    derived_skips=6 and job_events held ('skip', A's app_user_id, 6) -- six
    fabricated negatives for postings B never saw, stored under A's name. The
    cross-Builder READ predates app_user_id; what the column added was a wrong
    NAME on the result, which is what made it worth fixing rather than noting.

    THE SECOND HALF WAS FOUND BY THE FIX FOR THE FIRST, and is the mirror
    image: the NOT EXISTS asks "was there a non-impression event on this job in
    this render", and without an owner predicate it asked it across all thirty
    Builders. So B, echoing A's request_id and posting a `save`, could VETO a
    skip A's own open should have derived. Suppression rather than fabrication
    -- a lost negative rather than a false one -- and invisible in exactly the
    same way, since a skip that is never written looks identical to an item
    nobody passed over. Closing the read half and leaving the veto half would
    have been a half-answer to one question.

    THE OWNER MATCH IS NOT A REMOVAL. A job THIS Builder acted on in THIS
    render must still be excluded -- counting a save as a skip would feed the
    ranker a negative for its best outcome -- and the derived skip rows
    themselves carry the caller's app_user_id, which is what keeps a second
    open further down the same render idempotent.

    THE NULL CASE RESOLVES CLEANLY AND IS THE HONEST ANSWER, not a workaround.
    The outer conjunct already forces imp.app_user_id non-NULL, so the only
    NULL that can reach `other.app_user_id = imp.app_user_id` is a legacy
    row's; NULL = 'u_123' is NULL rather than TRUE, the row fails the EXISTS,
    and a pre-column action event simply stops suppressing. That is correct on
    the merits: an event nobody can be shown to have generated should not veto
    somebody else's negative. Asserted rather than reasoned to, by
    tests/test_event_replay.py
    TestEventStateIsPerBuilder.test_a_pre_column_action_event_does_not_suppress.

    IT NEVER REACHED seen OR applied, and that boundary is part of the finding.
    _EVENT_STATE_JOIN matches event IN ('impression','open') and
    event = 'applied'; 'skip' is in neither, so none of this was ever visible in
    a response body. The damage was confined to L2 training data -- which is
    this table's entire purpose, so it is not a mitigation.

    app_user_id IS STILL COPIED FROM THE IMPRESSION RATHER THAN STAMPED FROM
    THE CALLER, and the conjunct is what makes those two agree. Copying keeps a
    skip's owner a fact already on the row instead of one re-asserted from the
    caller, and it is what makes the NULL case above behave.

    WHAT THIS STILL DOES NOT COVER, stated so it is not read as total:

      * A render whose impressions predate app_user_id derives NOTHING, because
        NULL cannot satisfy the outer equality. Accepted deliberately: those
        rows are historical and already unattributable, and job_events is
        append-only, so every day the hole stayed open wrote permanently
        unremovable wrong rows.
      * request_id IS STILL UNVERIFIED. Nothing here rejects a batch echoing
        another Builder's render id -- the two conjuncts make it harmless to
        THIS derivation rather than impossible to send. A batch carrying a
        borrowed request_id still writes ITS OWN events (the open, the save)
        under that request_id and the sender's app_user_id, so one render id
        can end up spanning two Builders' rows. Nothing reads it that way
        today: grepped 2026-08-01, this function is the ONLY consumer of
        job_events.request_id in the tree -- score.py, match.py and tools/ do
        not reference the column at all. It is a constraint on the L2 analysis
        not yet written: GROUP BY request_id alone is not a render, and
        (app_user_id, request_id) is.
      * The 24-hour dedup above is now keyed (app_user_id, job_id) rather than
        (profile, job_id) -- OQ-2, decided 2026-08-03. A legacy impression
        row with a NULL app_user_id (predating the column) does not satisfy
        `prior.app_user_id = %s` either, for the same reason the bullet above
        gives, so it no longer suppresses a fresh impression from anyone --
        one more historical row this fix cannot retroactively attribute.
    """
    rows = conn.execute(
        """
        INSERT INTO job_events (profile, app_user_id, job_id, event, request_id,
                                rank,
                                visibility, match_score, fit_score,
                                criteria_version, occurred_at)
        SELECT imp.profile, imp.app_user_id, imp.job_id, 'skip', imp.request_id,
               imp.rank,
               %s, imp.match_score, imp.fit_score, imp.criteria_version, %s
        FROM job_events imp
        WHERE imp.profile = %s
          AND imp.app_user_id = %s
          AND imp.request_id = %s
          AND imp.event = 'impression'
          AND imp.rank IS NOT NULL
          AND imp.rank < %s
          AND NOT EXISTS (
                SELECT 1 FROM job_events other
                 WHERE other.profile = imp.profile
                   AND other.app_user_id = imp.app_user_id
                   AND other.request_id = imp.request_id
                   AND other.job_id = imp.job_id
                   AND other.event <> 'impression')
        RETURNING id
        """,
        (VISIBILITY_PRIVATE, now, profile, app_user_id, request_id, rank),
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

    A save, unsave, dismiss or undismiss ALSO moves builder_job_state, in this
    same transaction -- the append-only log keeps what happened, that table
    keeps the current answer, and they are written together so no reader can
    catch them disagreeing. It is keyed on user.id and not on the profile: see
    write_builder_state.

    criteria_version and visibility join them on the same principle, for two
    different reasons. criteria_version is read from job_matches beside
    match_score because it names the weight generation that produced the order
    the user reacted to -- ../schema.py's job_scores block already states this
    as the reason that column exists there. visibility is set by event type
    because it is a privacy control, and a privacy control a client can set is
    not one.

    app_user_id is written from user.id, on the same principle again and for a
    third reason: it is WHO, and the read side needs it. Without it `seen` and
    `applied` were resolved by profile and were therefore cohort-wide -- D66
    and D67, closed by this line and by _EVENT_STATE_JOIN together. The column
    is nullable and unbackfilled (../schema.py), so every row written from here
    onward has it and no earlier row acquires a guess.

    THE 24-HOUR IMPRESSION DEDUP IS NOW KEYED (app_user_id, job_id), NOT
    (profile, job_id). That gap was not an oversight left over from adding the
    column: it was an OPEN DECISION belonging to the repo owner, recorded in
    tranche_five/27-event-schema.md, API-CONTRACT-v1.md and
    docs/ingest/engagement-events.md, all deleted 2026-08-02 --
    `git show refactor-freeze-2026-08-02:docs/ingest/engagement-events.md` --
    and carried forward in docs/STATE-OF-THE-SYSTEM.md § 4. Its consequence was
    real: one Builder's render suppressed another Builder's impression of the
    same job for the rest of the window, and skips inherited it because
    derive_skips reads impressions. OQ-2, decided 2026-08-03: narrow to
    app_user_id. One Builder's render no longer speaks for another's. Existing
    job_events rows written under the old key are NOT backfilled -- a guessed
    attribution is worse than a missing one -- so only rows written from here
    onward observe the new key. derive_skips' docstring documents the second
    half of the same interaction.
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
                INSERT INTO job_events (profile, app_user_id, job_id, event,
                                        request_id, rank,
                                        dwell_ms, reason, visibility, match_score,
                                        fit_score, criteria_version, occurred_at)
                SELECT m.profile, %s, m.job_id, %s, %s, %s, %s, %s, %s, m.match_score,
                       (SELECT s.fit_score FROM job_scores s
                         WHERE s.job_id = m.job_id AND s.profile = m.profile),
                       m.criteria_version, %s
                FROM job_matches m
                WHERE m.profile = %s AND m.job_id = %s
                  AND (%s <> 'impression' OR NOT EXISTS (
                        SELECT 1 FROM job_events prior
                         WHERE prior.app_user_id = %s AND prior.job_id = m.job_id
                           AND prior.event = 'impression' AND prior.occurred_at >= %s))
                RETURNING id
                """,
                (user.id, e.event, batch.request_id, e.rank, e.dwell_ms, e.reason,
                 visibility_for(e.event), now, user.profile, e.job_id, e.event,
                 user.id, cutoff),
            ).fetchone()
            if row:
                recorded += 1
                # The current per-Builder answer, beside the evidence for it
                # and in the same transaction. Keyed on user.id, NOT on the
                # profile: thirty Builders share one profile, so a dismissal
                # written per-profile would suppress the posting for all of
                # them. tranche_six/31.
                write_builder_state(conn, user.id, e.job_id, e.event,
                                    e.reason, now)
                # AFTER the open's own row, never before: the derivation
                # excludes any job with a non-impression event in this render,
                # and the job just opened must be one of them.
                if e.event == "open":
                    # user.id as well as user.profile: the derivation reads
                    # impressions back out of the table, and request_id alone
                    # does not establish whose render they came from. D68.
                    derived += derive_skips(conn, user.profile, user.id,
                                            batch.request_id, e.rank, now)
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

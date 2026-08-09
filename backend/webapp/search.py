"""Searches: submit one, watch one, read what it found.

TENANCY, exactly as jobs.py states it. `user.profile` is the cohort and comes
from the SESSION; `user.id` is the Builder and comes from the same place.
Neither is ever taken from a request parameter.

WHAT THIS SERVICE MAY WRITE, AND WHY IT IS SO NARROW. The four tables behind
this router are declared in ../schema.py and owned by the pipeline. This
service holds INSERT on `search_queries` (register a query) and INSERT/UPDATE
on `search_query_watchers` (watch, unwatch) and NOTHING ELSE. In particular it
holds no privilege at all on `search_query_signal`, which carries the exposed
watcher bucket. That is the rule schema_web.py states for tranche_five/28's
cohort_signal in its own words -- the suppression rule lives in the pipeline's
nightly fold and this service must not be able to write a bucket it did not
compute -- and it is enforced by GRANT rather than by this docstring.

THE PRIVACY CONTRACT, which is the whole reason the shape is what it is:

  * `search_query_watchers` NEVER reaches a response. Not the rows, not the
    identities, not a count derived from them at request time. The only thing
    this service reads out of it is whether the CALLER watches a query, which
    is the caller's own fact.
  * The exposed count is `search_query_signal.watcher_bucket`, computed by the
    nightly fold, suppressed below schema.SEARCH_MIN_WATCHERS and bucketed above
    it. A LEFT JOIN, so a suppressed query yields `watcher_bucket: null` --
    which is what 0, 1, 2 and 3 watchers all yield, indistinguishably. A client
    must render null as no badge and never as a zero.
  * `first_requested_at` is NOT in the response, and its absence is deliberate
    rather than an oversight. It is the timestamp at which one identifiable
    person typed something, and timing is the strongest deanonymiser available
    in a cohort who sit in a room together (tranche_five/28). `last_run_at` IS
    exposed, because that is the pipeline's clock and no person's action.
  * Applications stay private entirely. Nothing here touches job_events, and
    the answer to "what is shared" is the same one jobs.py:72-80 gives: only a
    save is cohort-visible. Two different answers to that question is how a
    privacy promise gets broken by accident.

RESULTS ROUTE THROUGH THE FULL GATE, STRUCTURALLY. /results joins `jobs_app`,
never `jobs` and never `search_query_results` alone. jobs_app requires a
job_matches row, and match.py writes one only for postings that pass
relevance.union_sql -- so a relister posting a provider returned is suppressed
here exactly as it would be via ingest, without this module containing one line
of relevance logic. `.claude/CLAUDE.md`: do not reimplement relevance matching
in Python; one implementation, two callers.
"""

import json

import config  # noqa: F401  (must come first -- performs the sys.path insert)

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

#: NOT UNUSED, AND DO NOT REMOVE IT AS DEAD. Nothing in this module references
#: `schema.` -- the reference is from outside: tests/test_search_signal.py
#: asserts `search.schema is schema`, pinning that this route and the nightly
#: fold in ../searchqueries.py read ONE SEARCH_MIN_WATCHERS rather than two
#: copies that can drift. A watcher floor that disagrees across the process
#: boundary suppresses a badge on one side and shows it on the other.
import schema
import searchnorm
from auth import User, require_user
from db import db
from jobs import (COHORT_FIELDS, DEFAULT_LIMIT, LIST_COLUMNS, MAX_LIMIT,
                  ORDER_BY, ContractError, _BUILDER_STATE_JOIN,
                  _COHORT_COLUMNS, _COHORT_RAW_FIELD, _COHORT_SIGNAL_JOIN,
                  _EVENT_STATE_JOIN, _STATE_COLUMNS, STATE_FIELDS,
                  cohort_signal, decode_cursor, encode_cursor, new_request_id)
from lib.timeparse import utc_now_str
#: The plan figures behind the watch cap, read from config/serp-quota.json.
#: A FILE READ AND NEVER A VENDOR CALL on a request path -- quota.load_config()
#: parses JSON, where quota.Ledger.account() would open a socket to SerpApi.
#: The pipeline's rule that no LLM call may sit between a user and an ordering
#: (.claude/CLAUDE.md) is the same rule: a Builder pressing "search" must not
#: wait on a third party to be told how many keywords they may save, and a
#: vendor that is down must not turn saving a keyword into an error.
from serp import quota

router = APIRouter()

#: Columns of `search_queries` that may be rendered. A allowlist rather than
#: `SELECT *`, because the table grows columns the pipeline needs and a Builder
#: must not see: first_requested_at is the one that exists today (see the
#: module docstring) and a `SELECT *` would have shipped it the day it landed.
QUERY_COLUMNS = ("id", "display_text", "display_location", "chips", "source",
                 "role_track", "last_run_at", "run_count",
                 "result_count_last_run", "retired_at")

#: Their names in the response. `display_text` is `text` to a client -- the
#: column name records that it is the raw spelling rather than the key, which
#: is a storage concern, and the API contract's noun is just "text".
RESPONSE_NAMES = ("id", "text", "location", "chips", "source", "role_track",
                  "last_run_at", "run_count", "result_count_last_run",
                  "retired_at")

#: The bucket and the caller's own watch state, appended to every query row.
#:
#: TWO JOINS AND NOT ONE AGGREGATE. The obvious implementation is
#: `count(*) FROM search_query_watchers` at request time, and it is the exact
#: mistake this design exists to prevent: a live count is an unsuppressed count,
#: and the suppression would then live in whichever renderer remembered it.
#: `sig` is the pipeline's answer, already suppressed and already bucketed --
#: the same rule jobs._COHORT_SIGNAL_JOIN states for tranche_five/28, and
#: nothing in this package may query search_query_watchers for a count.
#: `mine` is a single-row lookup of the CALLER's own watch, which leaks nothing
#: about anyone else.
#:
#: IT TAKES TWO PARAMETERS, WHERE _COHORT_SIGNAL_JOIN TAKES NONE, and the
#: difference is not carelessness. That fragment can write
#: `cs.cohort_profile = v.profile` because jobs_app carries a profile column;
#: `search_queries` deliberately carries NO identity at all, cohort included, so
#: the cohort has to be bound. Both parameters therefore LEAD the params list --
#: this fragment is spliced in ahead of the WHERE -- which is the ordering
#: hazard jobs._BUILDER_STATE_JOIN is emphatic about. _select_queries() is the
#: single place that binds them, so there is one site to get right rather than
#: five, and TestSignalJoinBindsInOrder pins it.
#:
#: watcher_bucket ALONE. search_query_signal.computed_at is not selected and
#: must not be: it is a per-query timestamp that moves when the underlying set
#: moves, which hands a client the recency channel the bucketing exists to
#: close. jobs._COHORT_COLUMNS refuses the same column for the same reason.
_SIGNAL_JOIN = """
    LEFT JOIN search_query_signal sig
           ON sig.query_id = q.id AND sig.cohort_profile = %s
    LEFT JOIN search_query_watchers mine
           ON mine.query_id = q.id AND mine.app_user_id = %s
          AND mine.removed_at IS NULL
"""
_SIGNAL_COLUMNS = "sig.watcher_bucket, (mine.query_id IS NOT NULL) AS watching"
_SIGNAL_FIELDS = ("watcher_bucket", "watching")


def _row_to_query(row):
    item = dict(zip(list(RESPONSE_NAMES) + list(_SIGNAL_FIELDS), row))
    item["chips"] = json.loads(item["chips"]) if item["chips"] else None
    return item


#: Whose plan the cap is read from. A literal, because there is exactly one
#: account that runs watched queries today: `apify` is the other entry in
#: config/serp-quota.json and it bills per RESULT out of a dollar balance, so
#: its `allowance` is null and dividing it by days would be a unit error rather
#: than a smaller number.
#:
#: THIS IS THE PIPELINE'S ACCOUNT, NOT THE BUILDER'S, AND docs/adr/0007 WANTS
#: THE BUILDER'S. Decision 4 paces "from the contributor's own plan data", and
#: `T-35` is the row that stores a contributor's reported quota server-side --
#: until it lands there is no per-Builder plan to read, and the shared account
#: is not a placeholder for one but the account that actually dispatches every
#: watched query today. When `T-35` lands, the change is the argument passed to
#: searchnorm.watch_cap(), not the function and not the warning.
CAP_PROVIDER = "serpapi"


def plan_cap():
    """The derived cap, or None when the plan is not known. Advisory.

    NOT CACHED, DELIBERATELY. config/serp-quota.json is a small file in the
    page cache and this runs twice on the two routes that write a watch, so the
    read costs less than the invalidation would: a cached cap would go on
    quoting the old plan after an operator edited the file, and the symptom --
    a warning naming a number that is no longer anywhere in the repo -- is the
    silent kind this project's CLAUDE.md names as its failure mode.
    """
    entry = (quota.load_config().get(CAP_PROVIDER) or {})
    return searchnorm.watch_cap(entry.get("allowance"), utc_now_str(),
                                entry.get("cycle_reset_day", 1),
                                entry.get("reserve") or 0)


def _cap_warning(watched, already):
    """The soft warning for a Builder whose list has outgrown the plan, or None.

    A WARNING AND NEVER A REFUSAL -- this is what `T-33` changed, and the two
    routes below used to raise a `too_many_searches` ContractError here.
    (Spelled that way round on purpose: frontend/check_client.mjs derives the
    client's refusal copy by scanning this file for the call form, so writing
    the dead code as one would resurrect a refusal in the checker's eyes.)
    docs/adr/0007 decision 5: a watch row is a Builder's saved keyword and the
    list is a discovery surface, which filters and pins the existing corpus
    whether or not anything dispatches it. Refusing to save one because a
    SerpApi plan is small couples a UI affordance to a vendor invoice, and the
    save it refused would not have spent a credit.

    So the shape of the answer matters: callers ATTACH this, they do not branch
    on it. A caller that turned a non-None return into a 4xx would have
    reimplemented the block this row removed.

    `already` suppresses it for the same reason the old cap did: re-submitting
    or re-watching something a Builder already watches adds no query to the
    night, so warning about the list length would be a warning they cannot act
    on by not doing what they just did.
    """
    cap = plan_cap()
    if cap is None or already or watched < cap:
        return None
    return {
        "code": "watching_past_plan",
        "message": (f"you are watching {watched} searches and this plan "
                    f"refreshes about {cap} a night, so they will not all run "
                    f"every night"),
    }


def _select_queries(conn, user, where, params, limit):
    columns = ", ".join(f"q.{c}" for c in QUERY_COLUMNS)
    sql = f"""
        SELECT {columns}, {_SIGNAL_COLUMNS}
        FROM search_queries q
        {_SIGNAL_JOIN}
        WHERE {' AND '.join(where)}
        ORDER BY q.id
        LIMIT %s
    """  # noqa: S608 -- where built from fixed literals only, values always bound via params
    # The JOIN's parameters lead, because _SIGNAL_JOIN is spliced in ahead of
    # the WHERE -- the same ordering hazard jobs.py:323-325 annotates for
    # _BUILDER_STATE_JOIN, and the same fix: bind them first, here, once.
    rows = conn.execute(sql, [user.profile, user.id, *params, limit]).fetchall()
    return [_row_to_query(r) for r in rows]


class SearchRequest(BaseModel):
    text: str
    location: str | None = None
    # A free-form filter-chip object passed through to the provider. Validated
    # only as "is it an object": Google Jobs' chip vocabulary is the provider's,
    # it changes without notice, and a whitelist here would be a second place
    # to update every time it moved. Stored as TEXT, never interpolated.
    chips: dict | None = Field(default=None)


@router.post("/v1/searches")
def create_search(body: SearchRequest, user: User = Depends(require_user)):
    """Submit a search. Returns the query -- created or already existing.

    ASYNCHRONOUS, AND THE RESPONSE SAYS SO. No provider is called on this
    request. The query is registered, the caller becomes a watcher, and results
    appear when the nightly cycle (or a short-interval worker) runs it. Three
    reasons, in the task file's order of importance: the contributor API is
    inherently deferred, batching across users is what makes the cache work,
    and a Builder waiting twenty seconds on a scrape is a worse experience than
    one who submits and finds results next time they open the app.

    IDEMPOTENT ON THE NORMALISED KEY. Two Builders submitting "AI Operations"
    and "ai  operations!" get the SAME row id back and become two watchers of
    it -- which is the entire cost argument in tranche_four/25: one row, two
    watchers, one provider call. The find-or-create is one statement
    (searchnorm.REGISTER_QUERY_SQL) so that two simultaneous submissions cannot
    race into a unique violation that reads to a Builder as a failed search.

    `warning` IS ALWAYS IN THE RESPONSE AND IS USUALLY NULL. It is the one key
    here that is not a column of `search_queries` -- see _cap_warning() for why
    the plan cap advises rather than refuses. Always present rather than only
    when it fires, because a key that appears only on the bad day is a key
    every renderer forgets, and the Builder it was written for is exactly the
    one who would then be told nothing.
    """
    try:
        normalized_text, normalized_location = searchnorm.validate(
            body.text, body.location)
    except searchnorm.InvalidQuery as bad:
        raise ContractError(bad.code, str(bad))
    location = body.location or searchnorm.DEFAULT_LOCATION
    now = utc_now_str()

    with db() as conn:
        # Counted BEFORE the insert, so the warning describes the list the
        # Builder had when they asked rather than the one they are about to
        # have. That is a real choice and this is the softer of the two: on the
        # submission that crosses the cap, `watched` is the cap and the
        # comparison below is `>=`, so the warning arrives ON the crossing
        # rather than one search after it.
        watched = conn.execute(searchnorm.COUNT_WATCHED_SQL, (user.id,)).fetchone()[0]
        already = conn.execute(
            """
            SELECT 1 FROM search_query_watchers w
            JOIN search_queries q ON q.id = w.query_id
            WHERE w.app_user_id = %s AND w.removed_at IS NULL
              AND q.normalized_text = %s AND q.normalized_location = %s
            """,
            (user.id, normalized_text, normalized_location)).fetchone()
        warning = _cap_warning(watched, already)

        query_id = conn.execute(
            searchnorm.REGISTER_QUERY_SQL,
            (normalized_text, normalized_location, body.text, location,
             json.dumps(body.chips) if body.chips else None,
             "builder", None, now)).fetchone()[0]
        conn.execute(searchnorm.REGISTER_WATCHER_SQL,
                     (query_id, user.id, user.profile, now))
        items = _select_queries(conn, user, ["q.id = %s"], [query_id], 1)

    return {**items[0], "warning": warning}


@router.get("/v1/searches")
def list_searches(
    user: User = Depends(require_user),
    scope: str = Query("mine", pattern="^(mine|suggested)$"),
    limit: int = Query(DEFAULT_LIMIT, ge=1, le=MAX_LIMIT),
):
    """The caller's watched searches, or the seeded catalogue.

    TWO SCOPES AND NO THIRD. There is deliberately no "everything anyone has
    ever searched for" listing: `search_queries` carries no identity, but the
    TEXT of a builder-created query is often self-identifying in a
    thirty-person cohort ("bilingual healthcare operations Brooklyn"), and a
    browsable list of them would hand an observer the whole population to plant
    against. `mine` is the caller's own; `suggested` is the catalogue seeded
    from extract.ROLE_TRACK, which nobody typed.
    """
    if scope == "suggested":
        where = ["q.source IN ('seeded', 'track')", "q.retired_at IS NULL"]
        params = []
    else:
        where = ["mine.query_id IS NOT NULL"]
        params = []
    with db() as conn:
        items = _select_queries(conn, user, where, params, limit)
    return {"searches": items, "scope": scope}


@router.get("/v1/searches/{query_id}")
def get_search(query_id: int, user: User = Depends(require_user)):
    with db() as conn:
        items = _select_queries(conn, user, ["q.id = %s"], [query_id], 1)
    if not items:
        # 404 rather than 403, matching jobs.py:438-441: "exists but isn't
        # yours" and "doesn't exist" must be indistinguishable to anyone
        # enumerating ids -- and here the id space is a small integer sequence,
        # so enumeration is trivial and the rule matters more, not less.
        raise HTTPException(status_code=404, detail="no such search")
    return items[0]


@router.post("/v1/searches/{query_id}/watch")
def watch_search(query_id: int, user: User = Depends(require_user)):
    """Watch an existing search -- typically one from the suggested catalogue.

    Carries the same `warning` key as create_search, and must: watching a
    query somebody else typed puts exactly the same query into the night as
    typing it, which is why the count behind the cap is over WATCHES. A cap
    that only noticed the submit route would be advice a Builder could walk
    straight past by picking from the catalogue instead.
    """
    now = utc_now_str()
    with db() as conn:
        exists = conn.execute("SELECT 1 FROM search_queries WHERE id = %s",
                              (query_id,)).fetchone()
        if not exists:
            raise HTTPException(status_code=404, detail="no such search")
        watched = conn.execute(searchnorm.COUNT_WATCHED_SQL, (user.id,)).fetchone()[0]
        already = conn.execute(
            "SELECT 1 FROM search_query_watchers WHERE query_id = %s "
            "AND app_user_id = %s AND removed_at IS NULL",
            (query_id, user.id)).fetchone()
        warning = _cap_warning(watched, already)
        conn.execute(searchnorm.REGISTER_WATCHER_SQL,
                     (query_id, user.id, user.profile, now))
        items = _select_queries(conn, user, ["q.id = %s"], [query_id], 1)
    return {**items[0], "warning": warning}


@router.post("/v1/searches/{query_id}/unwatch")
def unwatch_search(query_id: int, user: User = Depends(require_user)):
    """Stop watching. A POST and not a DELETE, and that is not a style choice:
    app.py's CORS middleware allows GET, POST and OPTIONS only, so a DELETE
    from the browser client would be refused at the preflight with no error
    anyone would see -- the silent-failure mode this repo alerts on.

    An UPDATE setting `removed_at`, never a delete. Same treatment as
    builder_job_state (schema_web.py:52-57) and for the same reason
    tranche_six/31 gives about undismiss: the fact that someone reversed
    something is itself signal, and deletion loses it. The row is also what
    makes re-watching idempotent rather than a second INSERT.
    """
    now = utc_now_str()
    with db() as conn:
        exists = conn.execute("SELECT 1 FROM search_queries WHERE id = %s",
                              (query_id,)).fetchone()
        if not exists:
            raise HTTPException(status_code=404, detail="no such search")
        conn.execute(searchnorm.UNWATCH_SQL, (now, query_id, user.id))
        items = _select_queries(conn, user, ["q.id = %s"], [query_id], 1)
    return items[0]


@router.get("/v1/searches/{query_id}/results")
def search_results(
    query_id: int,
    user: User = Depends(require_user),
    limit: int = Query(DEFAULT_LIMIT, ge=1, le=MAX_LIMIT),
    cursor: str | None = None,
    include_dismissed: bool = Query(False),
):
    """What this search has surfaced, through the same gate as everything else.

    THE JOIN IS THE GATE. `FROM jobs_app v JOIN search_query_results r` -- so
    a posting only appears if the pipeline wrote a job_matches row for it,
    which match.py does only for postings passing relevance.union_sql, and if
    it satisfies jobs_app's four completeness predicates. Google Jobs is
    precisely where the relister junk originates and config/relevance.json
    already carries six excluded relist sites and a `description_exclude` for
    the 'reputed company' placeholder BECAUSE this source fed them in. A search
    route that read `jobs` directly would surface the exact postings the
    curated pipeline was built to suppress, to people with no industry
    pattern-matching to catch it.

    The response shape is /v1/jobs' shape, field for field, including
    `request_id`, `rank` and `cohort_signal`. Deliberately: a search result
    list is a rendered list, position bias applies to it identically, and
    tranche_five/27's instrumentation is unusable if half the renders in the
    product report positions in a different vocabulary. Every column, join and
    field name here is IMPORTED from jobs.py rather than restated, so the two
    lists cannot drift into two shapes -- a client rendering both would then
    need two renderers for one kind of thing.
    """
    # BOTH state joins bind first, and both take user.id -- _EVENT_STATE_JOIN
    # as well as _BUILDER_STATE_JOIN, since job_events gained app_user_id.
    # jobs.list_jobs opens with the identical `[user.id, user.id]` and the
    # duplication is the point: these fragments are spliced in ahead of the
    # WHERE, so their parameters lead. _COHORT_SIGNAL_JOIN takes none.
    params = [user.id, user.id]
    where = ["v.profile = %s", "r.query_id = %s"]
    params += [user.profile, query_id]
    if not include_dismissed:
        where.append("bs.dismissed_at IS NULL")

    request_id = new_request_id()
    first_rank = 1
    if cursor:
        score, ts, job_id, request_id, first_rank = decode_cursor(cursor)
        where.append(
            "(((v.match_score, coalesce(v.posted_at_ts, '-infinity'::timestamptz)) "
            "< (%s, coalesce(%s::timestamptz, '-infinity'::timestamptz))) OR "
            "(v.match_score = %s AND coalesce(v.posted_at_ts, "
            "'-infinity'::timestamptz) = coalesce(%s::timestamptz, "
            "'-infinity'::timestamptz) AND v.id > %s))")
        params += [score, ts, score, ts, job_id]

    columns = ", ".join(f"v.{c}" for c in LIST_COLUMNS)
    sql = f"""
        SELECT {columns},
        {_STATE_COLUMNS},
        {_COHORT_COLUMNS}
        FROM jobs_app v
        JOIN search_query_results r ON r.job_id = v.id
        {_EVENT_STATE_JOIN}
        {_BUILDER_STATE_JOIN}
        {_COHORT_SIGNAL_JOIN}
        WHERE {' AND '.join(where)}
        ORDER BY {ORDER_BY}
        LIMIT %s
    """  # noqa: S608 -- where built from fixed literals only, values always bound via params
    params.append(limit + 1)   # one extra row: is there a next page?
    with db() as conn:
        rows = conn.execute(sql, params).fetchall()

    has_more = len(rows) > limit
    rows = rows[:limit]
    names = list(LIST_COLUMNS) + list(STATE_FIELDS) + [_COHORT_RAW_FIELD]
    items = [dict(zip(names, r)) for r in rows]
    # BEFORE `rank`, so the key order is LIST_COLUMNS, STATE_FIELDS,
    # cohort_signal, rank -- byte for byte what /v1/jobs produces and what
    # ../../frontend/verify_fixtures.py checks there.
    for item in items:
        item[COHORT_FIELDS[0]] = cohort_signal(item.pop(_COHORT_RAW_FIELD))
    for offset, item in enumerate(items):
        item["rank"] = first_rank + offset

    next_cursor = None
    if has_more and items:
        last = items[-1]
        next_cursor = encode_cursor(last["match_score"], last["posted_at_ts"],
                                    last["id"], request_id, first_rank + len(items))
    return {"request_id": request_id, "query_id": query_id, "jobs": items,
            "next_cursor": next_cursor, "profile": user.profile}

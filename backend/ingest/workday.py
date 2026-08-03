#!/usr/bin/env python3
"""
Workday CXS ingest -- the large non-tech NYC employers, with the relevance
gate moved UPSTREAM into ingest.

Task 18 (`git show refactor-freeze-2026-08-02:docs/tasks/refactor/tranche_three/18-ingest-workday-cxs.md`). Reads
tenant/data-centre/site out of `company_ats` (task 16), walks each tenant's
public CXS list endpoint, and fetches a detail page ONLY for the postings that
survive an upstream filter. Writes `platform='workday'` rows to `jobs`.

WHY THE GATE MOVED UPSTREAM, AND WHY THAT IS THE WHOLE DESIGN
    A hospital system runs 2,000 open requisitions. One detail request per
    posting is 2,000 requests per tenant per night; across the tenants this
    plan expects, the detail fetches dominate the entire nightly window
    (`git show refactor-freeze-2026-08-02:docs/tasks/refactor/tranche_three/18-ingest-workday-cxs.md`:63-73).
    Every other source in this pipeline ingests whole and
    filters afterwards, because whole boards are cheap there. Here they are
    not.

    So the list response -- which carries title and location and nothing else
    -- decides who gets a detail request. `upstream_survivors()` is that
    decision and `RATIO_ALARM` is what tells you when it has stopped working.

    ONE IMPLEMENTATION, TWO CALLERS. CLAUDE.md forbids reimplementing
    relevance matching in Python, and `relevance.py` compiles config to
    POSTGRES regexes. Those are not Python regexes: `\\y` is a word boundary in
    Postgres and an error in Python's `re`, and `\\b` is a word boundary in
    Python and BACKSPACE in Postgres -- so a Python evaluator of
    `config/relevance.json` would not merely duplicate the matcher, it would
    disagree with it, silently, on the exact patterns CLAUDE.md names a
    landmine. This module therefore evaluates `relevance.tier_sql` in Postgres
    against the list rows, before they are a table (`_tiers()`). No second
    copy of the matching logic exists, in any language.

    `git show refactor-freeze-2026-08-02:docs/tasks/refactor/tranche_three/18-ingest-workday-cxs.md`:77-79
    asks instead for "a function that evaluates a
    title/location pair in Python against the same config". That would be the
    second copy, in the wrong dialect, and `relevance.py` is owned elsewhere
    this session in any case. The deviation is deliberate and is recorded in
    `git show refactor-freeze-2026-08-02:docs/ingest/workday.md`.

WHY THE UPSTREAM FILTER IS DELIBERATELY LOOSE
    `git show refactor-freeze-2026-08-02:docs/tasks/refactor/tranche_three/18-ingest-workday-cxs.md`:80-85:
    task 10's gate is description-first and at list time there
    is no description, so filtering tightly here "would discard exactly the
    postings this refactor exists to find, since their titles are the
    uninformative part". "Operations Coordinator" at a hospital is the target
    population; `title_include` will never match it.

    So the upstream filter drops a posting only on evidence that survives
    having no description:

      * an EXCLUSION fired -- `title_exclude`, `company_exclude`. Those lists
        are "narrow and specific on purpose" and "unambiguous"
        (`config/relevance.json` _title_exclude_note), which is exactly what
        makes them safe to apply to a bare title.
      * the location is KNOWN and is not one this deployment accepts.

    It never requires `title_include` to match. `_loose_cfg()` is how that is
    expressed without editing `relevance.py`: substitute a title pattern that
    matches everything, so `tier_sql` compiles the exclusion half of its
    `row_ok` predicate on its own. Tier 3 then means "excluded", tier 1 means
    "kept, location accepted", tier 2 means "kept, location not accepted" --
    and tier 2 survives only when the LIST RESPONSE could not say where the
    job is (see `location_flags()`), which is
    `git show refactor-freeze-2026-08-02:docs/tasks/refactor/tranche_three/18-ingest-workday-cxs.md`:83's
    "neither-but-unknown".

ONLY DETAIL-FETCHED POSTINGS ARE STORED
    `git show refactor-freeze-2026-08-02:docs/tasks/refactor/tranche_three/18-ingest-workday-cxs.md`:110-113 settles this: "a posting you never detail-fetched is
    still a posting you *saw*, so track seen-set membership from the list
    response, not from what you stored." Closure detection therefore feeds
    `close_missing()` the FULL seen set while the upsert carries only the
    survivors.

    The alternative -- store every listing row and fill descriptions later --
    was rejected for a concrete reason, not a stylistic one: a listing-only
    record has `description_text=None` and `posted_at=None`, and re-writing it
    over a row that was detail-fetched on an earlier night would blank both.
    Both are in `HASH_FIELDS_ATS` (`schema.py:131`), so the row would also
    churn between the two shapes forever.

THE FOUR SILENT FAILURES, AND WHERE EACH IS HANDLED
    Every one of these returns success and loses data (`git show refactor-freeze-2026-08-02:docs/tasks/refactor/tranche_three/18-ingest-workday-cxs.md`:39-59). Each
    has a fixture in `evals/workday_fixtures.py` and a test in
    `tests/test_workday_fixtures.py` that drives THIS module through it.

    1. `limit` cannot exceed 20. Ask for 100 and Workday returns an empty
       `jobPostings` with HTTP 200 and no error field -- byte-identical to "no
       more results". `_check_page_limit()` raises, and it is called from
       `list_body()` so every request path goes through it rather than only
       the ones a future editor remembers. `PAGE_LIMIT` is not a default
       argument anybody can override upward.

    2. A throttled page reads as the end of the list. `lib/http.py:75-81`
       retries 429 and 5xx with backoff, so the cheap half of the fix is
       simply using it. The other half is `collect_postings()` reconciling
       what it collected against the `total` the API returned and raising
       `Shortfall` -- `git show refactor-freeze-2026-08-02:docs/tasks/refactor/tranche_three/18-ingest-workday-cxs.md`:52, "a mismatch is an error, not a shrug". One
       published account lost 1,960 of NVIDIA's 2,000 jobs to this.

    3. The data-centre prefix varies -- wd1, wd5, wd108, wd501. It is read
       from `company_ats.workday_dc` and there is NO default anywhere in this
       file; `load_workday_tenants()` skips a row that lacks one rather than
       guessing. A wrong prefix answers 404/422 and reads as one more
       unreachable tenant in a fifty-tenant loop.

    4. The 10,000-result cap. A single query cannot enumerate past it however
       long the loop runs, so reconciliation DETECTS it and cannot fix it.
       `collect_tenant()` slices by `appliedFacets` using the facet values the
       response itself advertises, and merges. If no facet partitions the
       board finely enough, it raises rather than returning a short list.

A FIFTH, WHICH THE TASK FILE DOES NOT LIST AND WHICH BIT THIS CODE FIRST
    Found by running the loop above against the four live tenants in
    `company_ats` on 2026-07-28, not by reading anything. Two halves:

      * `total` IS REPORTED ON THE FIRST PAGE ONLY. Every later page answers
        `total: 0`. msk.wd108 returns total=88 at offset 0 and total=0 at
        offsets 20, 40, 60 and 80. So `total = payload.get("total", total)` --
        the obvious spelling, and the first one written here -- reconciles a
        complete walk against zero. All four tenants failed with "collected 40
        of 0" before this was understood. Both the constructed fixtures and
        NVIDIA's real recorded page repeat `total` on every page, so nothing
        in the test suite could have caught it.

      * AN OFFSET PAST THE END WRAPS. It does not return an empty array; it
        returns the FIRST page again. offset=100 against msk's 88 postings
        answers with postings 1-20 and total=88. So the textbook "loop until a
        page comes back empty" never terminates against a live tenant.

    Both are handled in `collect_postings` and both have tests. The first is
    the more dangerous: it turns a correct walk into a Shortfall, and a
    Shortfall is a tenant this script deliberately declines to write.

TWO MORE THINGS ONLY A LIVE RUN COULD SAY, AND THEY BOTH CHANGED THE DESIGN
    * `locationsText` IS NOT ALWAYS A LOCATION. NewYork-Presbyterian's is a
      facility hierarchy -- "NYP/Weill Cornell Medical Center",
      "NYP/Columbia University Irving Medical Center". Two of its three
      commonest values name New York hospitals without naming New York, so
      `text.classify_location` answers (False, False) and the first version of
      the upstream gate dropped most of a New York hospital system's board on
      the strength of its own internal naming convention -- silently, and
      exactly the mistake
      `git show refactor-freeze-2026-08-02:docs/tasks/refactor/tranche_three/18-ingest-workday-cxs.md`:80-85
      warns against. `location_flags()` now
      answers "unknown" for anything that is not recognisably a place; see
      `_PLACE_SHAPED`.

    * A BOARD MOVES WHILE IT IS BEING WALKED. Nordstrom answered total=867 and
      yielded 865 distinct postings across the 100 seconds that followed. Under
      a strict equality that is a Shortfall, and a Shortfall means the tenant
      is not written at all -- so the largest boards would lose whole nights at
      random for doing nothing wrong. The reconciliation threshold is one PAGE,
      which is the unit of the failure it exists to catch; smaller
      disagreements are reported as `drift` and never suppressed.

SILENCE IS THE FAILURE MODE, SO THE SUMMARY IS UNCONDITIONAL
    CLAUDE.md: "blocked scrapers and changed endpoints all return zero rows
    rather than raising. Alert on volume, not errors." Unlike ats.py this
    script prints its summary on EVERY run, including a quiet one, and prints
    a `workday-ingest: ALERT` line for a valid tenant that returned zero
    postings, for a detail-fetch ratio approaching 1.0, and for any tenant
    refused at the front door. A run where every tenant failed exits 1.

POLITENESS
    `git show refactor-freeze-2026-08-02:docs/tasks/refactor/tranche_three/18-ingest-workday-cxs.md`:90-98. Plain HTTP from this host's own IP, sequential, one
    request per `REQUEST_DELAY_SECONDS`. No scraping service. Tenants that
    answer 401/403/451 are counted as blocked and NOT retried -- retrying into
    a refusal is how a probe becomes an incident, the same rule
    `git show refactor-freeze-2026-08-02:docs/ats-token-discovery.md` "Politeness" adopted for the discovery pass.

CONFIG
    DATABASE_URL                    postgres connection string
    WORKDAY_REQUEST_DELAY           seconds between requests (default 1.5)
    WORKDAY_MAX_DETAIL_PER_TENANT   hard ceiling on detail fetches (default 400)
    WORKDAY_MAX_TENANTS             stop after N tenants (default: all)
    DEBUG_PRINT_KEYS=1              per-tenant tracing on stderr

SCHEDULE: not scheduled directly. See run-daily.py, which is the single cron
entry point and calls this script as a subprocess. This script is NOT yet in
its STEPS list -- see
`git show refactor-freeze-2026-08-02:docs/ingest/workday.md` for the line to
add and where.
"""

import json
import os
import re
import sys
import time
import urllib.error
from urllib.parse import quote

# ingest/ and tools/ sit one level below the pipeline modules they import
# (schema, relevance, llm, ...). Same insert as ingest/ats.py:129.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import profiles  # noqa: E402
import relevance  # noqa: E402
import schema  # noqa: E402
from lib import dbconn, http, state, text  # noqa: E402
from lib.timeparse import utc_now_str  # noqa: E402
from lib.upsert import (UpsertErrorRate, UpsertResult, check_error_rate,  # noqa: E402
                        upsert_checked)

PLATFORM = "workday"

#: THE LANDMINE. CLAUDE.md, `git show refactor-freeze-2026-08-02:docs/tasks/refactor/tranche_three/18-ingest-workday-cxs.md`:44, and `ats_discovery.py:280-283` all say
#: the same thing: Workday's CXS endpoint accepts `limit` up to 20 and answers
#: anything larger with an empty `jobPostings` array, HTTP 200, no error field.
#: That response is byte-identical to "no more results", so a single wrong
#: constant here ingests nothing and looks like a quiet night.
#:
#: This is a ceiling, not a suggestion: `_check_page_limit()` raises, and it is
#: called from `list_body()`, which every request in this file goes through.
MAX_PAGE_LIMIT = 20
PAGE_LIMIT = MAX_PAGE_LIMIT

#: A single Workday query cannot enumerate past this, whatever `total` says.
#: `git show refactor-freeze-2026-08-02:docs/tasks/refactor/tranche_three/18-ingest-workday-cxs.md`:56-59. Detected by reconciliation, fixed only by slicing.
RESULT_CAP = 10000

#: Seconds between outward requests. `git show refactor-freeze-2026-08-02:docs/tasks/refactor/tranche_three/18-ingest-workday-cxs.md`:97 -- "Start plain: 1-2s between
#: requests, ~50 tenants, sequential."
REQUEST_DELAY_SECONDS = float(os.environ.get("WORKDAY_REQUEST_DELAY", "1.5"))

#: Ceiling on detail fetches per tenant. Not a filter -- a fuse. If the
#: upstream gate breaks, the failure is a nightly window that never closes, and
#: 400 * REQUEST_DELAY is already ten minutes for one tenant. Hitting it is
#: reported as an ALERT, never as a normal night.
MAX_DETAIL_PER_TENANT = int(os.environ.get("WORKDAY_MAX_DETAIL_PER_TENANT", "400"))

#: `git show refactor-freeze-2026-08-02:docs/tasks/refactor/tranche_three/18-ingest-workday-cxs.md`:86-88: "If detail-fetched/seen creeps toward 1.0, the upstream
#: filter has stopped working and the window is about to blow."
RATIO_ALARM = 0.80

#: Fraction of a tenant's detail fetches that may fail before it is an alert.
#: A few 404s are ordinary -- a requisition filled between the list call and
#: the detail call -- and a fifth of them is a block starting.
DETAIL_ERROR_ALARM = 0.20

#: Statuses that mean "this host refused us", not "this tenant is empty".
#: Counted separately and never retried -- see POLITENESS above.
BLOCKED_STATUSES = (401, 403, 406, 429, 451)

#: raw_json ceiling. Workday detail bodies carry the full description HTML,
#: which is routinely 30-60 KB; text.bounded_json shrinks the long field rather
#: than slicing the serialization into an unparseable stump (lib/text.py:65-94).
RAW_JSON_LIMIT = 20000

PRUNE_CLOSED_AFTER_DAYS = 30
DEBUG_PRINT_KEYS = os.environ.get("DEBUG_PRINT_KEYS", "") == "1"

#: Workday writes this instead of a place when a requisition spans several.
#: It is the "neither-but-unknown" case at
#: `git show refactor-freeze-2026-08-02:docs/tasks/refactor/tranche_three/18-ingest-workday-cxs.md`:83,
#: and it is why
#: location_flags() returns None rather than False: FALSE would read as "known
#: not to be in New York" and the upstream filter would drop it.
MULTI_LOCATION = re.compile(r"^\s*\d+\s+locations?\s*$", re.I)

#: A location string is evidence about WHERE only if it is recognisably a
#: place. Measured 2026-07-28: NewYork-Presbyterian's `locationsText` is
#: "NYP/Weill Cornell Medical Center", "NYP/Columbia University Irving Medical
#: Center", "NYP/Brooklyn Methodist Hospital" -- a FACILITY hierarchy, not a
#: geography. `text.classify_location` returns (False, False) for the first two
#: because they contain no city token, and reading that as "known not to be in
#: New York" would drop most of a New York hospital system's board on the
#: strength of its internal naming convention. That is precisely the failure
#: `git show refactor-freeze-2026-08-02:docs/tasks/refactor/tranche_three/18-ingest-workday-cxs.md`:80-85 says this filter must not commit.
#:
#: The comma is the discriminator, and it is the shape every real place in this
#: data has: "New York, NY", "Boise, ID", "US, CA, Santa Clara", "Israel,
#: Yokneam". Anything with no comma and no NYC/remote match is UNKNOWN, not
#: elsewhere. A bare "Seattle" is therefore kept and costs one detail fetch --
#: the safe direction for a filter whose whole job is to be loose.
_PLACE_SHAPED = re.compile(r",\s*\S")

_REMOTE_TYPE = re.compile(r"remote", re.I)


class LimitTooLarge(ValueError):
    """A page size Workday answers with a silent empty array. See MAX_PAGE_LIMIT."""


class Shortfall(RuntimeError):
    """Collected fewer postings than the API's own `total` said existed.

    `git show refactor-freeze-2026-08-02:docs/tasks/refactor/tranche_three/18-ingest-workday-cxs.md`:52: "a mismatch is an error, not a shrug." Raised rather than
    returned, because every caller that could ignore a return value has, at
    least once, in a published account that cost 1,960 postings.
    """


class ResultCapUnsliceable(RuntimeError):
    """`total` exceeds the 10,000-result cap and no facet slices it finely enough."""


class TenantBlocked(RuntimeError):
    """The host refused us. Distinct from an empty board, and never retried."""


# ---------------------------------------------------------------------------
# the endpoint
# ---------------------------------------------------------------------------

def _check_page_limit(limit):
    """Raise unless `limit` is one Workday will actually honour.

    Deliberately not `min(limit, 20)`. Silently correcting the caller would
    preserve the bug in the caller's head and produce a run that quietly
    disagrees with the code that asked for it; the landmine is worth an
    exception at the request site.
    """
    if not isinstance(limit, int) or limit < 1 or limit > MAX_PAGE_LIMIT:
        raise LimitTooLarge(
            f"Workday CXS `limit` must be 1..{MAX_PAGE_LIMIT}, got {limit!r}. "
            f"Above {MAX_PAGE_LIMIT} the endpoint returns an EMPTY jobPostings "
            f"array with HTTP 200 and no error -- byte-identical to 'no more "
            f"results', so the run would report success and ingest nothing. "
            f"See CLAUDE.md's Landmines and `git show refactor-freeze-2026-08-02:docs/tasks/refactor/tranche_three/18-ingest-workday-cxs.md`:44.")
    return limit


def host(tenant, dc):
    return f"https://{tenant}.{dc}.myworkdayjobs.com"


def jobs_url(tenant, dc, site):
    """The list endpoint. `git show refactor-freeze-2026-08-02:docs/tasks/refactor/tranche_three/18-ingest-workday-cxs.md`:21."""
    return f"{host(tenant, dc)}/wday/cxs/{tenant}/{site}/jobs"


def detail_url(tenant, dc, site, external_path):
    """The detail endpoint. `git show refactor-freeze-2026-08-02:docs/tasks/refactor/tranche_three/18-ingest-workday-cxs.md`:34.

    `externalPath` arrives already url-shaped ("/job/New-York-NY/Foo_98479")
    and is quoted with `/` safe so a title containing a space or a `#` does not
    truncate the path -- Workday builds these from job titles, which contain
    both.
    """
    return (f"{host(tenant, dc)}/wday/cxs/{tenant}/{site}"
            f"{quote(external_path or '', safe='/')}")


def public_url(tenant, dc, site, external_path):
    """The human-facing url, per `git show refactor-freeze-2026-08-02:docs/tasks/refactor/tranche_three/18-ingest-workday-cxs.md`:37.

    Used only as a fallback: a detail response carries `externalUrl`, which is
    Workday's own canonical spelling and omits the `/en-US/` locale segment
    this constructs. Preferring theirs avoids storing a URL we invented into a
    hashed column (`schema.py:131`).
    """
    return f"{host(tenant, dc)}/en-US/{site}{external_path or ''}"


def list_body(offset, limit=PAGE_LIMIT, facets=None, search=""):
    """The POST body, as documented at `git show refactor-freeze-2026-08-02:docs/tasks/refactor/tranche_three/18-ingest-workday-cxs.md`:24.

    `sort_keys=True` because `evals/cassettes.py:374` keys a POST interaction
    on the sha256 of its body: two callers spelling the same request with
    different key order would be two different requests, and a cassette
    recorded by one would be a miss for the other.
    """
    _check_page_limit(limit)
    return json.dumps({"appliedFacets": facets or {},
                       "limit": limit, "offset": offset,
                       "searchText": search}, sort_keys=True).encode()


def fetch_list_page(tenant, dc, site, offset, *, limit=PAGE_LIMIT, facets=None,
                    timeout=30):
    """One page of the list endpoint, via lib/http so 429 backs off.

    Nothing here catches HTTPError. A page that never succeeds must reach
    `collect_postings`, which turns it into a Shortfall -- the failure this
    whole module is shaped around is a failed page being read as the end of a
    list.
    """
    return json.loads(http.get_text(
        jobs_url(tenant, dc, site),
        data=list_body(offset, limit, facets),
        headers={"Content-Type": "application/json"},
        method="POST", timeout=timeout,
        label=f"workday {tenant}@{dc}"))


def fetch_detail(tenant, dc, site, external_path, *, timeout=30):
    """The detail document for one posting. `git show refactor-freeze-2026-08-02:docs/tasks/refactor/tranche_three/18-ingest-workday-cxs.md`:31-35."""
    return json.loads(http.get_text(
        detail_url(tenant, dc, site, external_path),
        headers={"Accept": "application/json"},
        label=f"workday {tenant} detail"))


# ---------------------------------------------------------------------------
# pagination, reconciliation, and the cap
# ---------------------------------------------------------------------------

def _fetch_or_classify(tenant, dc, site, offset, *, limit=PAGE_LIMIT,
                       facets=None, collected=0, total=None):
    """One page, with every failure turned into the right loud exception.

    Shared by `collect_postings` and `collect_tenant` because the front page is
    fetched by the latter to read `total` and the facet list off it, and a
    refusal on the front page has to be the same `TenantBlocked` a refusal on
    page seven is. Classifying it in one place is what stops a 403 on page one
    reading as an unexplained "failed" while a 403 on page seven reads as
    "blocked".
    """
    try:
        return fetch_list_page(tenant, dc, site, offset, limit=limit,
                               facets=facets)
    except urllib.error.HTTPError as e:
        if e.code in BLOCKED_STATUSES:
            raise TenantBlocked(
                f"{tenant}@{dc}: HTTP {e.code} at offset {offset}") from e
        raise Shortfall(
            f"{tenant}@{dc}: page at offset {offset} never succeeded "
            f"(HTTP {e.code}) -- collected {collected} of "
            f"{total if total is not None else '?'}; a failed page is NOT "
            f"the end of the list") from e
    except (urllib.error.URLError, TimeoutError, OSError,
            json.JSONDecodeError) as e:
        raise Shortfall(
            f"{tenant}@{dc}: page at offset {offset} never succeeded "
            f"({e}) -- collected {collected} of "
            f"{total if total is not None else '?'}") from e


def collect_postings(tenant, dc, site, *, facets=None, limit=PAGE_LIMIT,
                     delay=REQUEST_DELAY_SECONDS, max_pages=None,
                     sleep=time.sleep, first_page=None):
    """(postings, total) for one query, reconciled against the API's `total`.

    THE TWO THINGS THIS DOES THAT A NAIVE LOOP DOES NOT

    1. It does not treat a failed page as the end of the list. `lib/http.py`
       has already retried 429/5xx five times with backoff by the time an
       exception reaches here, and what reaches here is re-raised as a
       Shortfall rather than becoming a `break`.

    2. It compares `len(collected)` against `total` and raises if they differ.
       That single check is also what catches failure 1 (limit>20 returns an
       empty page whose `total` is unchanged) and failure 4 (the 10,000 cap),
       neither of which produces an error of any kind.

    An empty page ends the walk, which is correct ONLY because of the
    reconciliation that follows it: on its own, "no postings" is the exact
    shape of every one of the silent failures.
    """
    _check_page_limit(limit)
    collected, seen_paths, total, offset = [], set(), None, 0
    # A page is `limit` postings, so the walk is bounded by total/limit; the
    # +2 leaves room for the terminating empty page. Bounded at all because an
    # endpoint that ignores `offset` would otherwise loop forever.
    pages = 0
    while True:
        if max_pages is not None and pages >= max_pages:
            break
        if first_page is not None and offset == 0:
            # collect_tenant already paid for page 0 to read `total` and the
            # facet list off it. Re-requesting it would double this source's
            # request count against every tenant's front page.
            payload, first_page = first_page, None
        else:
            payload = _fetch_or_classify(tenant, dc, site, offset, limit=limit,
                                         facets=facets,
                                         collected=len(collected), total=total)

        pages += 1
        if total is None:
            # THE FIFTH SILENT FAILURE, and it is not in the task file.
            # `total` is reported on the offset=0 page ONLY: every later page
            # answers `total: 0`. Measured 2026-07-28 against all four live
            # tenants in company_ats -- msk.wd108 returns total=88 at offset 0
            # and total=0 at offsets 20, 40, 60 and 80.
            #
            # Taking the latest value, which is the obvious way to write this
            # line, reconciles a complete 88-posting walk against 0 and calls
            # it a shortfall; worse, `offset >= total` then ends the walk at
            # page two and the reconciliation agrees with itself. First page
            # wins, permanently.
            total = payload.get("total")
        postings = payload.get("jobPostings") or []
        fresh = 0
        for p in postings:
            # Workday repeats postings across page boundaries when the board
            # changes mid-walk, and see the wrap below. Dedup by externalPath
            # so the reconciliation compares DISTINCT postings against `total`
            # rather than being satisfied by a duplicate.
            path = p.get("externalPath")
            if path and path in seen_paths:
                continue
            if path:
                seen_paths.add(path)
            collected.append(p)
            fresh += 1
        if not postings or fresh == 0:
            # `fresh == 0` is the WRAP guard, and it is the other half of the
            # fifth failure. An offset past the end of the board does NOT
            # return an empty array -- it returns the FIRST page again
            # (offset=100 against msk's 88 postings returns postings 1-20 and
            # total=88). A loop that waits for an empty page never terminates
            # against a live tenant; it cycles, forever, at one request per
            # REQUEST_DELAY.
            break
        offset += limit
        if len(postings) < limit:
            # A short page is the end of the list. Safe to trust ONLY because
            # the reconciliation below still runs: if a short page was in fact
            # a truncated one, this raises rather than returning quietly.
            break
        if max_pages is None and total is not None and offset >= total:
            break
        if delay:
            sleep(delay)

    # RECONCILIATION, AND THE ONE PLACE IT CANNOT BE AN EQUALITY.
    #
    # The failure this check exists to catch is a lost PAGE -- 1,960 of 2,000,
    # not 2 of 867. And a board changes while it is being walked: Nordstrom
    # answered total=867 on the front page and yielded 865 distinct postings
    # over the 100 seconds that followed, on 2026-07-28, because two
    # requisitions closed mid-walk. Equality turns that into a shortfall, and a
    # shortfall means this script declines to write the tenant at all -- so a
    # strict check would cost the largest boards whole nights, at random, for
    # doing nothing wrong.
    #
    # The threshold is therefore one page. A deficit smaller than `limit`
    # cannot be a lost page by definition; a deficit of a page or more cannot
    # be ordinary churn. Anything nonzero is still returned to the caller as
    # drift and reported -- see TenantOutcome.drift -- so this tolerates the
    # churn without ever going quiet about it.
    #
    # An EXCESS is never fatal: postings added mid-walk are not data loss.
    deficit = (total - len(collected)) if total is not None else 0
    if deficit >= limit:
        raise Shortfall(
            f"{tenant}@{dc}: collected {len(collected)} of {total} postings"
            f"{f' (facets {facets})' if facets else ''} -- {deficit} missing, "
            f"a page or more. Do not treat this as a smaller board.")
    return collected, total


def facet_slices(page, cap=RESULT_CAP):
    """`appliedFacets` bodies that partition a board too large to enumerate.

    The list response advertises its own facets -- `facetParameter`, and
    `values` each with an `id` and a `count` (verified against the recorded
    NVIDIA response in `evals/fixtures/cassettes/ats-validation.json`). So the
    slicing `git show refactor-freeze-2026-08-02:docs/tasks/refactor/tranche_three/18-ingest-workday-cxs.md`:57-59 prescribes needs no hardcoded facet name and no
    per-tenant configuration: pick the parameter whose value counts add up to
    `total` (i.e. it partitions the board) and whose largest value is under the
    cap.

    Returns [] when no parameter qualifies. The caller raises on that rather
    than proceeding, because a board that cannot be enumerated is a board this
    source silently under-reports.
    """
    total = page.get("total")
    best = []
    for facet in page.get("facets") or []:
        param = facet.get("facetParameter")
        values = [v for v in (facet.get("values") or [])
                  if v.get("id") and isinstance(v.get("count"), int)]
        if not param or not values:
            continue
        counts = [v["count"] for v in values]
        if max(counts) >= cap:
            continue
        if total is not None and sum(counts) < total:
            # Does not cover the board: merging these slices would be short by
            # construction, which is the failure being avoided.
            continue
        candidate = [{param: [v["id"]]} for v in values]
        if not best or len(candidate) < len(best):
            best = candidate            # fewest requests among those that work
    return best


def collect_tenant(tenant, dc, site, *, delay=REQUEST_DELAY_SECONDS,
                   sleep=time.sleep, cap=RESULT_CAP):
    """Every posting for one tenant, slicing by facet if the board is capped.

    Returns (postings, total). Raises Shortfall, ResultCapUnsliceable or
    TenantBlocked -- never a short list.
    """
    first = _fetch_or_classify(tenant, dc, site, 0)
    total = first.get("total")
    if delay:
        sleep(delay)

    if total is None or total <= cap:
        return collect_postings(tenant, dc, site, delay=delay, sleep=sleep,
                                first_page=first)

    slices = facet_slices(first, cap=cap)
    if not slices:
        raise ResultCapUnsliceable(
            f"{tenant}@{dc}: total={total} exceeds the {cap}-result cap and no "
            f"advertised facet partitions it below the cap. "
            f"{total - cap} postings are unreachable by any single query; "
            f"`git show refactor-freeze-2026-08-02:docs/tasks/refactor/tranche_three/18-ingest-workday-cxs.md`:56-59. Refusing to return a short list.")

    merged, by_path = [], set()
    for facets in slices:
        postings, _ = collect_postings(tenant, dc, site, facets=facets,
                                       delay=delay, sleep=sleep)
        for p in postings:
            path = p.get("externalPath")
            if path in by_path:
                continue
            by_path.add(path)
            merged.append(p)
    if len(merged) < total:
        raise Shortfall(
            f"{tenant}@{dc}: sliced into {len(slices)} facet queries and "
            f"merged {len(merged)} of {total} -- the slices do not cover the "
            f"board")
    return merged, total


# ---------------------------------------------------------------------------
# normalization
# ---------------------------------------------------------------------------

def location_flags(locations_text, remote_type=None):
    """(is_nyc, is_remote), where is_nyc may be None for "cannot say".

    `text.classify_location` is the same function ats.py:201, :233 and :270
    use, so location tagging is not re-invented here. What is added is the
    third answer it has no way to give. It returns two booleans, and a False
    from it means "this string contains no New York token" -- which the caller
    then reads as "the job is elsewhere". For Workday that inference is wrong
    twice over:

      * "2 Locations" is the placeholder Workday writes when a requisition
        spans several, and an absent `locationsText` happens too.
      * `locationsText` is frequently not a geography at all. See _PLACE_SHAPED
        above: NewYork-Presbyterian's is a facility hierarchy, and two of its
        three commonest values name New York hospitals without naming New York.

    So a False survives only when the string is recognisably a place. Otherwise
    the answer is None, and the upstream gate keeps the posting.
    """
    remote = bool(remote_type and _REMOTE_TYPE.search(remote_type))
    if not locations_text or MULTI_LOCATION.match(locations_text):
        return (None, True) if remote else (None, None)
    is_nyc, is_remote = text.classify_location(locations_text)
    is_remote = bool(is_remote or remote)
    if not is_nyc and not is_remote and not _PLACE_SHAPED.search(locations_text):
        return None, is_remote
    return is_nyc, is_remote


def normalize_listing(employer, posting):
    """A `schema.COLUMNS` record from a LIST entry alone.

    Every key in schema.COLUMNS is present (schema.py:118-120), because upsert
    binds them as named parameters. `description_text` and `posted_at` are None
    here and are filled by `apply_detail()`; a record that never gets there is
    never written -- see ONLY DETAIL-FETCHED POSTINGS ARE STORED.

    `source_id` is `externalPath` and NOT `bulletFields[0]`. bulletFields holds
    the requisition id, which is not unique: the recorded NVIDIA page carries
    `.../System-Speed-and-Reliability-Co-Design-Engineer_JR2018911-1` with
    bulletFields `JR2018911`, i.e. a second posting of one req. Keying on it
    would collapse the two onto one row via `schema.make_job_id`.
    """
    title = posting.get("title")
    locations_text = posting.get("locationsText")
    is_nyc, is_remote = location_flags(locations_text, posting.get("remoteType"))
    return {
        "platform": PLATFORM,
        "company_token": employer["token"],
        "company_name": employer["employer_name"],
        "source_id": posting.get("externalPath"),
        "title": title,
        "location_raw": locations_text,
        "department": None,
        "job_url": public_url(employer["token"], employer["dc"],
                              employer["site"], posting.get("externalPath")),
        # The list gives only "Posted Yesterday" -- a RELATIVE string, which is
        # why it is not stored in the hashed `posted_at` column. See
        # apply_detail() for where the absolute date comes from, and
        # schema.py:188-214 for why the derived timestamp is safe to recompute
        # while the hashed one is not.
        "posted_at": None,
        "posted_at_ts": text.parse_relative_posted_at(posting.get("postedOn")),
        "salary_text": None,
        "seniority_guess": text.guess_seniority(title),
        "location_is_nyc": is_nyc,
        "location_is_remote": is_remote,
        # company_ats records employers, not their HQs or their industry. A
        # guess here would be a guess in a hashed column.
        "company_is_nyc_hq": False,
        "company_is_ai_focused": False,
        "description_text": None,
        "raw_json": text.bounded_json(posting, RAW_JSON_LIMIT),
    }


def apply_detail(rec, detail, listing=None):
    """Fill in what only the detail document carries. Returns a new record.

    `git show refactor-freeze-2026-08-02:docs/tasks/refactor/tranche_three/18-ingest-workday-cxs.md`:27-30 states that the LIST response carries `startDate` and
    `jobRequisitionLocation`. It does not -- measured against msk.wd108 and
    against the recorded NVIDIA page, the list carries only title,
    externalPath, locationsText, postedOn, remoteType and bulletFields, and
    `startDate` / `jobRequisitionLocation` / `location` live on the DETAIL
    document. That is the difference between an absolute date and "Posted
    Yesterday", so it is not cosmetic; see
    `git show refactor-freeze-2026-08-02:docs/ingest/workday.md`.
    """
    info = (detail or {}).get("jobPostingInfo") or {}
    out = dict(rec)
    description = text.strip_html(info.get("jobDescription"))
    if description:
        out["description_text"] = description
    start = info.get("startDate")
    if start:
        out["posted_at"] = start
        out["posted_at_ts"] = text.posted_at_timestamp(start)
    # LOCATION: THE LIST WINS, AND THAT IS NOT THE OBVIOUS CHOICE.
    #
    # The detail document's `location` is not always a place. Measured on the
    # first live run, 2026-07-28: NewYork-Presbyterian answers
    # `"location": "NYP/Brooklyn Methodist Hospital"` -- a facility name --
    # while the list said "New York, NY". Preferring the detail there replaces
    # a location with an org chart, and any facility whose name happens to
    # carry no city token would flip `location_is_nyc` from true to FALSE and
    # demote a real NYC posting to tier 2 in every downstream query.
    #
    # So the list's `locationsText` wins whenever it is a real place, and the
    # detail is consulted only for the placeholder case ("2 Locations"), which
    # is exactly where the list has nothing to say. raw_json keeps both.
    detail_location = info.get("location")
    listing_is_placeholder = rec.get("location_is_nyc") is None
    location = (detail_location if listing_is_placeholder and detail_location
                else rec.get("location_raw") or detail_location)
    if location:
        out["location_raw"] = location
        is_nyc, is_remote = location_flags(location, info.get("remoteType"))
        # Knowledge may only be ADDED: true beats false beats unknown, whichever
        # document supplied it.
        answers = (rec.get("location_is_nyc"), is_nyc)
        out["location_is_nyc"] = (
            True if any(a is True for a in answers)
            else False if any(a is False for a in answers) else None)
        out["location_is_remote"] = bool(out.get("location_is_remote") or is_remote)
    if info.get("externalUrl"):
        out["job_url"] = info["externalUrl"]
    out["raw_json"] = text.bounded_json(
        {"listing": listing or {}, "jobPostingInfo": info},
        RAW_JSON_LIMIT, long_field="jobDescription")
    return out


# ---------------------------------------------------------------------------
# the upstream gate -- relevance.py's compiler, run in Postgres, before `jobs`
# ---------------------------------------------------------------------------

#: A Postgres regex matching any non-empty title. Substituted for
#: `title_include` so `relevance.tier_sql` compiles the EXCLUSION half of its
#: row_ok predicate on its own: at relevance.py:210-215 the exclusion is nested
#: inside `if include:`, so simply emptying the include list would drop
#: title_exclude with it.
ANY_TITLE = "."

#: Columns the gate rows carry besides the configured location columns -- every
#: non-location column `tier_sql` can reference: `title` (relevance.py:216, :233),
#: `description_text` (:220, :276), `company_name` (:268) and `platform` (:271).
#:
#: THIS LIST IS A CONTRACT WITH relevance.py, AND IT HAS BEEN BROKEN ONCE.
#: `platform_exclude` landed in 7d94bb1 and `tier_sql` began emitting
#: `c.platform` for any profile that set it; this tuple was not updated, and the
#: nightly run died on `UndefinedColumn: column c.platform does not exist` for
#: three nights. Nothing caught it because the gate is the ONLY caller that does
#: not run against the `jobs` table, where all four columns exist for free --
#: every other caller of `tier_sql` was fine. `tests/test_workday_ingest.py`
#: pins this against relevance.py so the next added column fails in the suite.
_GATE_TEXT_COLUMNS = ("title", "company_name", "description_text", "platform")


def _loose_cfg(cfg):
    """`cfg` with its title requirement removed and its exclusions kept.

    See WHY THE UPSTREAM FILTER IS DELIBERATELY LOOSE in the module docstring.
    """
    return {**cfg, "title_include": [ANY_TITLE]}


def _tiers(conn, cfgs, records, *, loose):
    """One relevance tier per (record, cfg), computed by Postgres.

    The rows do not exist in any table yet -- they are a `unnest(...) WITH
    ORDINALITY` derived table aliased `c`, which `tier_sql`'s `table_alias`
    parameter (relevance.py:189) exists to point at. That is the whole trick:
    the shared implementation is a SQL COMPILER, so reusing it before the rows
    are stored costs one query and no second matcher.

    `unnest` of typed arrays rather than `VALUES`: a VALUES list of literals
    types an all-NULL boolean column as `text` and the predicate fails to
    parse, and `description_text` is NULL for every row here by construction.
    """
    if not records or not cfgs:
        return [() for _ in records]

    params, exprs = {}, []
    for i, cfg in enumerate(cfgs):
        use = _loose_cfg(cfg) if loose else cfg
        # tier_sql validates location_columns as plain identifiers
        # (relevance.py:253-257); calling it BEFORE the column list below is
        # built is what makes that validation cover the interpolation here too.
        expr, p = relevance.tier_sql(use, table_alias="c",
                                     param_prefix=f"rel{i}")
        params.update(p)
        exprs.append(f"({expr})")

    loc_cols = sorted({c for cfg in cfgs
                       for c in (cfg.get("location_columns") or [])})
    arrays = []
    for col in _GATE_TEXT_COLUMNS:
        params[f"c_{col}"] = [r.get(col) for r in records]
        arrays.append(f"%(c_{col})s::text[]")
    for col in loc_cols:
        params[f"c_{col}"] = [r.get(col) for r in records]
        arrays.append(f"%(c_{col})s::boolean[]")

    cols = ", ".join((*_GATE_TEXT_COLUMNS, *loc_cols))
    sql = (f"SELECT {', '.join(exprs)} "  # noqa: S608 -- splices _GATE_TEXT_COLUMNS (module constant) and loc_cols, validated as plain identifiers by relevance.tier_sql -- see the comment above
           f"FROM unnest({', '.join(arrays)}) "
           f"WITH ORDINALITY AS c({cols}, n) ORDER BY c.n")
    return [tuple(row) for row in conn.execute(sql, params).fetchall()]


def upstream_survivors(conn, cfgs, records):
    """(survivors, tiers) -- which listing rows earn a detail request.

    A record survives if ANY active profile would keep it, which is
    `relevance.union_sql`'s reasoning (relevance.py:276-292): extraction is
    shared, so a posting one profile would never look at still deserves the
    work if a second profile would. The same argument applies a step earlier to
    a detail fetch, which is likewise shared.

    Per profile, under the loose config:
        tier 3  an exclusion fired                     -> drop
        tier 1  kept, and the location is accepted     -> keep
        tier 2  kept, location not accepted            -> keep ONLY if the list
                                                          response could not say
                                                          where the job is
    """
    tiers = _tiers(conn, cfgs, records, loose=True)
    survivors = []
    for rec, row in zip(records, tiers):
        unknown_location = rec.get("location_is_nyc") is None
        for tier in row:
            if tier == 1 or (tier == 2 and unknown_location):
                survivors.append(rec)
                break
    return survivors, tiers


def full_gate_count(conn, cfgs, records):
    """How many records clear the REAL gate -- the third ratio number.

    `git show refactor-freeze-2026-08-02:docs/tasks/refactor/tranche_three/18-ingest-workday-cxs.md`:86-88 asks for "postings seen, postings detail-fetched, postings
    surviving the full gate". This is the last of the three, and it is the
    unmodified config: `title_include` back in force, descriptions present,
    `tier <= max_tier_to_score` exactly as `relevance.union_sql` would ask it
    once the rows are in the table.
    """
    if not records or not cfgs:
        return 0
    tiers = _tiers(conn, cfgs, records, loose=False)
    maxima = [relevance.max_tier(cfg) for cfg in cfgs]
    return sum(1 for row in tiers
               if any(t <= m for t, m in zip(row, maxima)))


# ---------------------------------------------------------------------------
# tenants
# ---------------------------------------------------------------------------

def load_workday_tenants(conn, limit=None):
    """Valid Workday rows from `company_ats`, as tenant/dc/site triples.

    NEVER ASSUME, NEVER DEFAULT (`git show refactor-freeze-2026-08-02:docs/tasks/refactor/tranche_three/18-ingest-workday-cxs.md`:52-55). A row missing `workday_dc` or
    `workday_site` is skipped and reported, not filled in with `wd1`: the four
    tenants task 16 found use wd1, wd108 and wd501, and a wrong prefix answers
    404 or 422 -- indistinguishable from a tenant with no open roles.

    `status='valid'` only. `git show refactor-freeze-2026-08-02:docs/ats-token-discovery.md` is emphatic that the
    other six statuses are not booleans and not settled: `never_found` means
    "no ATS URL in the bytes we were served" and its positive control failed
    4 of 4, while `unvalidated` means the token was never checked. None of them
    carries a tenant/dc/site triple this endpoint could be called with anyway,
    which is why the filter is on the presence of the triple as much as on the
    status.
    """
    rows = conn.execute(
        """
        SELECT employer_name, token, workday_site, workday_dc,
               open_jobs_at_validation
          FROM company_ats
         WHERE ats = %s AND status = %s
         ORDER BY employer_name
        """,
        (PLATFORM, "valid"),
    ).fetchall()
    tenants, incomplete = [], []
    for employer_name, token, site, dc, open_jobs in rows:
        if not (token and site and dc):
            incomplete.append(employer_name)
            continue
        tenants.append({"employer_name": employer_name, "token": token,
                        "site": site, "dc": dc,
                        "open_jobs_at_validation": open_jobs})
    if limit is not None:
        tenants = tenants[:limit]
    return tenants, incomplete


def active_relevance_cfgs(conn):
    """The relevance configs the upstream gate answers to.

    Mirrors extract.py:800-806 -- `profiles.load_active` then
    `relevance.for_profile` -- with one deliberate divergence. `union_sql`
    returns FALSE for an empty profile list, on the argument that "no active
    profiles means nobody is waiting for this work" and an LLM call on their
    behalf is the expensive way to be wrong (relevance.py:288-292). That is
    right for extraction and wrong here: ingest spends HTTP, and a night this
    source does not pull is a night whose postings are gone from the board
    before anyone asks for them. So with no active profiles this falls back to
    the shared config and says so.
    """
    active = profiles.load_active(conn)
    cfgs = [relevance.for_profile(p) for p in active]
    if cfgs:
        return cfgs, [p.profile for p in active]
    print("workday-ingest: no active profiles; gating on the shared "
          "config/relevance.json instead of ingesting nothing", file=sys.stderr)
    return [relevance.load()], ["<shared>"]


# ---------------------------------------------------------------------------
# one tenant, end to end
# ---------------------------------------------------------------------------

class TenantOutcome:
    """What one tenant did, in the terms the summary line reports.

    A class rather than a tuple because the summary distinguishes six
    outcomes and a positional tuple of six is how one of them gets read as
    another at 03:00.
    """

    def __init__(self, employer, **kw):
        self.employer = employer
        self.seen = 0
        self.fetched = 0
        #: Survivors of the upstream gate BEFORE MAX_DETAIL_PER_TENANT, so
        #: `capped` can say how many the fuse cost.
        self.fetched_wanted = 0
        self.surviving = 0
        self.total = None
        self.seconds = 0.0
        self.status = "ok"           # ok | blocked | shortfall | failed | empty
        self.detail_errors = 0
        self.drift = 0
        self.capped = False
        self.error = None
        self.result = UpsertResult()
        self.closed = 0
        self.__dict__.update(kw)

    @property
    def ratio(self):
        return (self.fetched / self.seen) if self.seen else 0.0

    def line(self):
        return (f"{self.employer['employer_name']} "
                f"({PLATFORM}:{self.employer['token']}@{self.employer['dc']}): "
                f"{self.status}, seen {self.seen}"
                f"{f'/{self.total}' if self.total is not None else ''}, "
                f"detail-fetched {self.fetched} ({self.ratio:.0%}), "
                f"gate-surviving {self.surviving}, "
                f"drift {self.drift:+d}, "
                f"{self.result.new} new, {self.result.updated} updated, "
                f"{self.closed} closed, {self.detail_errors} detail error(s), "
                f"{self.seconds:.1f}s")


def ingest_tenant(conn, employer, cfgs, run_started_at, *,
                  delay=REQUEST_DELAY_SECONDS, sleep=time.sleep,
                  max_detail=MAX_DETAIL_PER_TENANT, write=True):
    """Walk one tenant, gate, detail-fetch the survivors, upsert, close.

    Returns a TenantOutcome. Never raises for anything tenant-specific: one
    unreachable employer is background noise across fifty, and ats.py:104-111
    is the template. A failure that is NOT tenant-specific (a DB error) is
    left to propagate.
    """
    out = TenantOutcome(employer)
    tenant, dc, site = employer["token"], employer["dc"], employer["site"]
    started = time.monotonic()
    try:
        postings, total = collect_tenant(tenant, dc, site, delay=delay,
                                         sleep=sleep)
    except TenantBlocked as e:
        out.status, out.error, out.seconds = "blocked", str(e), time.monotonic() - started
        return out
    except ResultCapUnsliceable as e:
        out.status, out.error, out.capped = "shortfall", str(e), True
        out.seconds = time.monotonic() - started
        return out
    except Shortfall as e:
        # Deliberately no partial write. A partial list plus close_missing()
        # would mark every posting on the missing pages as closed, turning a
        # lost page into hundreds of wrong closures -- the same safety valve
        # ats.py:91-95 describes for an empty fetch.
        out.status, out.error = "shortfall", str(e)
        out.seconds = time.monotonic() - started
        return out
    except Exception as e:                          # noqa: BLE001 -- per-tenant
        out.status, out.error = "failed", str(e)
        out.seconds = time.monotonic() - started
        return out

    out.total, out.seen = total, len(postings)
    #: Sub-page disagreement between `total` and what was collected. Tolerated
    #: by collect_postings (see the reconciliation note there) and reported
    #: here, so "the board moved under us" is visible without being fatal.
    out.drift = (total - len(postings)) if total is not None else 0
    listings = [normalize_listing(employer, p) for p in postings]
    # The SEEN set, not the stored set. `git show refactor-freeze-2026-08-02:docs/tasks/refactor/tranche_three/18-ingest-workday-cxs.md`:110-113: a posting that was
    # gated out was still observed, and closing it because we chose not to
    # fetch its description would be a lie about the employer's board.
    seen_ids = [r["source_id"] for r in listings if r["source_id"]]

    survivors, _ = upstream_survivors(conn, cfgs, listings)
    out.fetched_wanted = len(survivors)
    if len(survivors) > max_detail:
        out.capped = True
        survivors = survivors[:max_detail]

    detailed = _fetch_details(employer, survivors, postings, out,
                              delay=delay, sleep=sleep)

    out.surviving = full_gate_count(conn, cfgs, detailed)

    if write and detailed:
        try:
            out.result = upsert_checked(conn, schema.spec(schema.HASH_FIELDS_ATS),
                                        detailed, schema.make_job_id,
                                        debug=DEBUG_PRINT_KEYS)
        except UpsertErrorRate as e:
            out.result = e.result
            out.status = "failed"
            out.error = str(e)
    if write and seen_ids:
        out.closed = schema.close_missing(conn, PLATFORM, tenant, seen_ids,
                                          run_started_at)
        state.set_watermark(conn, f"{PLATFORM}:{tenant}", run_started_at,
                            table=schema.WATERMARK_TABLE)

    if out.status == "ok" and out.seen == 0:
        # A tenant company_ats validated as live returning nothing is the shape
        # of a changed endpoint, not of a quiet week. CLAUDE.md: alert on
        # volume, not errors.
        out.status = "empty"
    out.seconds = time.monotonic() - started
    return out


def _fetch_details(employer, survivors, postings, out, *, delay, sleep):
    """Detail-fetch each survivor, tolerating individual failures.

    One posting whose detail page 404s (it was filled between the list and the
    fetch, which happens) must not lose the other 149. Counted, never silent.
    """
    by_path = {p.get("externalPath"): p for p in postings}
    tenant, dc, site = employer["token"], employer["dc"], employer["site"]
    detailed = []
    for rec in survivors:
        if delay:
            sleep(delay)
        try:
            detail = fetch_detail(tenant, dc, site, rec["source_id"])
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError,
                OSError, json.JSONDecodeError) as e:
            out.detail_errors += 1
            if DEBUG_PRINT_KEYS:
                print(f"[debug] detail failed for {rec['source_id']}: {e}",
                      file=sys.stderr)
            continue
        detailed.append(apply_detail(rec, detail, by_path.get(rec["source_id"])))
    out.fetched = len(detailed)
    return detailed


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

def main():
    conn = dbconn.connect_or_exit("workday ingest", schema=schema.SCHEMA)
    schema.ensure_schema(conn)

    max_tenants = os.environ.get("WORKDAY_MAX_TENANTS")
    tenants, incomplete = load_workday_tenants(
        conn, limit=int(max_tenants) if max_tenants else None)
    cfgs, profile_names = active_relevance_cfgs(conn)

    if not tenants:
        # Not an error and not a success. company_ats having no valid Workday
        # row is a fact about task 16's coverage, and saying "0 new" without
        # saying why would read as an empty market.
        print(f"workday-ingest: ALERT no valid workday rows in company_ats "
              f"({len(incomplete)} row(s) missing dc/site). Nothing to ingest; "
              f"run tools/ats-discover.py.")
        conn.close()
        sys.exit(0)

    run_started_at = utc_now_str()
    started = time.monotonic()
    outcomes = []
    for employer in tenants:
        outcome = ingest_tenant(conn, employer, cfgs, run_started_at)
        outcomes.append(outcome)
        if DEBUG_PRINT_KEYS:
            print(f"[debug] {outcome.line()}", file=sys.stderr)

    pruned = schema.prune_old_closed(conn, PRUNE_CLOSED_AFTER_DAYS)
    conn.close()
    elapsed = time.monotonic() - started

    totals = UpsertResult()
    for o in outcomes:
        totals += o.result
    seen = sum(o.seen for o in outcomes)
    fetched = sum(o.fetched for o in outcomes)
    surviving = sum(o.surviving for o in outcomes)
    ok = [o for o in outcomes if o.status in ("ok", "empty")]
    blocked = [o for o in outcomes if o.status == "blocked"]
    shortfalls = [o for o in outcomes if o.status == "shortfall"]
    failed = [o for o in outcomes if o.status == "failed"]

    # UNCONDITIONAL. Every other ingest here stays quiet on a clean night;
    # this one does not, because for this source a clean night and a blocked
    # night produce the same zero. See SILENCE IS THE FAILURE MODE above.
    ratio = f"{fetched / seen:.0%} of seen" if seen else "no postings seen"
    print(f"workday-ingest: {len(ok)}/{len(outcomes)} tenants ok "
          f"({len(blocked)} blocked, {len(shortfalls)} shortfall, "
          f"{len(failed)} failed), seen {seen}, detail-fetched {fetched} "
          f"({ratio})")
    print(f"workday-ingest: gate-surviving {surviving}, "
          f"{totals.new} new, {totals.updated} updated, "
          f"{totals.unchanged} unchanged, "
          f"{sum(o.closed for o in outcomes)} closed, {pruned} old-closed "
          f"pruned, {len(totals.errors)} record(s) dropped, {elapsed:.1f}s "
          f"wall-clock, profiles={','.join(profile_names)}")
    for o in outcomes:
        print(f"workday-ingest:   {o.line()}")

    # -- the alerts, each of which is a silent failure somewhere else --------
    alerts = []
    for o in outcomes:
        if o.status == "empty":
            alerts.append(f"{o.employer['employer_name']}: 0 postings from a "
                          f"tenant company_ats validated as live -- changed "
                          f"endpoint or a block, not a quiet week")
        if o.status in ("blocked", "shortfall", "failed"):
            alerts.append(f"{o.employer['employer_name']}: {o.status} -- {o.error}")
        if o.capped and o.status != "shortfall":
            alerts.append(f"{o.employer['employer_name']}: detail fetches "
                          f"capped at {MAX_DETAIL_PER_TENANT} of "
                          f"{o.fetched_wanted} the gate wanted -- the fuse "
                          f"blew, which means the gate did")
        attempted = o.fetched + o.detail_errors
        if attempted and o.detail_errors / attempted > DETAIL_ERROR_ALARM:
            # A few 404s are normal -- a requisition filled between the list
            # and the fetch. A fifth of them failing is a block starting.
            alerts.append(f"{o.employer['employer_name']}: "
                          f"{o.detail_errors}/{attempted} detail fetches "
                          f"failed")
        if o.drift:
            alerts.append(f"{o.employer['employer_name']}: `total` said "
                          f"{o.total} and {o.seen} distinct postings were "
                          f"collected ({o.drift:+d}) -- under one page, so the "
                          f"board moved mid-walk rather than a page being lost")
        if o.seen and o.ratio >= RATIO_ALARM:
            alerts.append(f"{o.employer['employer_name']}: detail-fetched "
                          f"{o.ratio:.0%} of what it saw -- the upstream gate "
                          f"has stopped filtering (`git show refactor-freeze-2026-08-02:docs/tasks/refactor/tranche_three/18-ingest-workday-cxs.md`:86-88)")
    if incomplete:
        alerts.append(f"{len(incomplete)} company_ats workday row(s) have no "
                      f"dc/site and were skipped rather than guessed: "
                      f"{incomplete[:5]}")
    for a in alerts:
        print(f"workday-ingest: ALERT {a}")

    if failed or blocked or shortfalls:
        print(f"workday-ingest: block-rate this run "
              f"{len(blocked)}/{len(outcomes)} blocked, "
              f"{len(shortfalls)}/{len(outcomes)} shortfall. One run is not a "
              f"rate; `git show refactor-freeze-2026-08-02:docs/tasks/refactor/tranche_three/18-ingest-workday-cxs.md`:128 requires a week before any "
              f"escalation to a scraping service.")

    if len(ok) == 0:
        print(f"workday ingest FAILED: all {len(outcomes)} tenants failed. "
              f"Sample: {[o.error for o in outcomes][:3]}")
        sys.exit(1)

    try:
        check_error_rate(totals, label=schema.TABLE)
    except UpsertErrorRate as e:
        print(f"workday ingest FAILED: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()

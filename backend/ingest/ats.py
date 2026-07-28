#!/usr/bin/env python3
"""
ATS job-board ingestion -- Postgres edition.

Pulls current open job postings directly from each employer's public ATS
job-board API, normalizes into a common schema, and upserts into Postgres.
Six platforms: Greenhouse, Lever, Ashby, Workable, Recruitee, SmartRecruiters.

WHERE THE COMPANY LIST COMES FROM -- NOT A CONFIG FILE ANY MORE
    The roster is the `company_ats` table (task 16). See ingest/ats_sources.py
    for which statuses admit a token and why `valid` is not the only one.
    `config/companies.json` is retired as a runtime input and survives only as
    the one-time seed corpus behind `--seed-from-json`; adding an employer is
    an INSERT, never a deploy.

    This script pulls an employer's ENTIRE board, deliberately. It is why
    `config/relevance.json:_why` records that "~87% of the table is roles this
    persona will never apply to" -- and that property is the point now rather
    than a cost: pulling a hospital system's whole board is exactly how the
    AI-operations coordinator buried in it gets found. Filtering by profile
    happens at the relevance gate, never by removing rows here.

WHY DIRECT ATS APIS INSTEAD OF SCRAPING LINKEDIN/INDEED
    Every platform here exposes a public, unauthenticated JSON endpoint per
    company -- the same one that company's own /careers page calls to render
    its listings. Querying it isn't scraping in the adversarial sense (no
    login wall, no bot detection), it is the intended public embed mechanism.
    LinkedIn/Indeed have no such API and scraping them violates their ToS with
    real ban risk -- deliberately out of scope, and forbidden by CLAUDE.md.

CLOSURE IS FREE HERE, AND IT IS NOT FREE ANYWHERE ELSE
    Every endpoint below returns the COMPLETE current set of open postings for
    a company. So a posting present yesterday and absent today is closed: no
    re-crawl, no `validThrough` parsing, no inference. `close_missing()` in
    schema.py is the single implementation and every platform reaches closure
    through it -- there is no per-platform copy of this logic, on purpose.

    This does NOT hold for the sources in tasks 19-21 (JSON-LD, Firecrawl,
    aggregators), which see a *page* of a result set rather than an
    employer's whole board. When someone is deciding which source to trust
    for a staleness signal, that is the difference.

    Two guards stand in front of it:

      1. An empty fetch never closes anything. schema.close_missing() raises
         on an empty seen_ids rather than closing every open row for the
         company, and the loop below skips the call entirely. A genuine
         zero-postings company is rare and not urgent; silently closing an
         employer's whole board because of a transient empty response is a
         much worse failure than missing it for a day.

      2. An INCOMPLETE fetch never closes anything either. See RECONCILING
         AGAINST THE API'S OWN TOTAL below. A throttled or truncated page is
         not the end of a list, and treating it as one is how a published
         account lost 1,960 of 2,000 jobs.

RECONCILING AGAINST THE API'S OWN TOTAL -- per platform, measured 2026-07-28
    "A throttled page is not the end of a list" (CLAUDE.md). Where a platform
    reports how many postings it thinks there are, `Fetched.reported_total`
    carries it and `Fetched.complete` refuses closure when the collected count
    falls short.

    | platform        | pagination        | server-side total          |
    |-----------------|-------------------|----------------------------|
    | greenhouse      | none, one call    | YES -- `meta.total`        |
    | lever           | `limit` + `skip`  | no                         |
    | ashby           | none, one call    | no                         |
    | workable        | none (widget)     | YES -- v3 `total`          |
    | recruitee       | none, one call    | no                         |
    | smartrecruiters | `limit`+`offset`  | YES -- `totalFound`        |

    Four of six offer no total. For those, a short page is still read as the
    end of the list -- which is what this script has always done and what the
    endpoints' own semantics support (they return the whole board in one
    response). Lever is the exception that needs a rule of its own; see
    LEVER_SKIP_CEILING.

DELTA SYNC -- what the platforms actually support, measured 2026-07-28
    `17-retarget-ats-ingest.md:46` says "Both Greenhouse and Lever expose
    update timestamps. Poll with `updated_at` filtering rather than full
    re-pulls." Probed against the live APIs, that is not true of either:

      greenhouse   `?updated_after=2030-01-01T00:00:00Z` on the job-board API
                   returns the SAME 5 postings as no filter at all (probed
                   against `kickstarter`). The parameter is accepted and
                   silently ignored -- CLAUDE.md's silence landmine in its
                   purest form. `updated_after` belongs to the authenticated
                   Harvest API, not to this public board API. Each posting
                   does carry an `updated_at` FIELD, which is a different
                   thing and is already hashed into `posted_at`.
      lever        no update timestamp exists at all. A posting carries
                   `createdAt` and nothing else -- there is no `updatedAt`
                   key in the payload to filter on, server-side or client-side.
      ashby        no.
      workable     no.
      recruitee    postings carry `updated_at`, but the endpoint takes no
                   filter for it.
      smartrecruiters
                   YES, one: `releasedAfter=<ISO8601>`. Probed: with
                   `releasedAfter=2030-01-01T00:00:00Z`, `totalFound` drops
                   from 4,755 to 0, so the filter is real and server-side. It
                   filters on `releasedDate` -- PUBLICATION, not last update
                   -- so it will not surface an edit to an older posting.

    So `--delta` exists, applies to SmartRecruiters only, and DISABLES CLOSURE
    for the platforms it applies to. That is not a limitation to work around,
    it is arithmetic: closure here is derived from absence from the complete
    set, and a delta response is by construction not the complete set. A
    nightly run must be a full pull. `--delta` is for an intra-day catch-up.

REQUEST COUNT
    Every outward call goes through _get_json/_post_json, which count per
    platform, and an `ats-requests:` line is printed to stderr on EVERY run --
    including a quiet one, for the same reason lib/upsert.py:311-314 gives for
    `errors=0`: a number that only appears when it is interesting is a number
    nobody notices has stopped appearing. Task 04's nightly budget can be
    checked against this rather than against an estimate.

    It counts requests THIS SCRIPT ISSUES. lib/http.py retries a 429 or a 5xx
    underneath (up to lib.http.DEFAULT_MAX_RETRIES) and those retries are not
    visible here; the number is a floor on wire traffic and an exact count of
    intended calls.

DEPENDENCY (the one exception to "stdlib only" -- there's no reasonable
stdlib Postgres client):
    pip install "psycopg[binary]"
    (add --break-system-packages if your system Python is externally managed)

DATABASE:
    The `jobs` database, in its `public` schema. See ../schema.py's
    "DATABASE, NOT SCHEMA".

CONFIG:
    DATABASE_URL              -- postgres connection string
    JOB_SOURCES_FILE          -- path to the RETIRED seed file, read only by
                                 --seed-from-json (default: alongside this
                                 script, config/companies.json)
    ATS_SR_DETAIL_BUDGET      -- max SmartRecruiters detail requests per
                                 company per run (default 200); see
                                 SMARTRECRUITERS_DETAIL_BUDGET

SCHEDULE: not scheduled directly -- see run-daily.py, which is the single
cron entry point and calls this script as a subprocess.

TEST BEFORE SCHEDULING:
    python3 ingest/ats.py
    python3 ingest/ats.py --seed-from-json     # one-time, idempotent
    DEBUG_PRINT_KEYS=1 python3 ingest/ats.py
    systemctl --user start jobs-ingest.service   # the whole nightly run

HEURISTICS -- both are best-effort tags stored alongside each row, not hard
filters. Query them (WHERE seniority_guess != 'senior' etc.) rather than
trusting the ingest to have already dropped the wrong rows -- keyword
matching on a job title is inherently approximate.

    seniority_guess: 'senior' | 'entry' | 'mid_or_unspecified' | 'unknown'
        Titles matching senior-signal words (senior, staff, principal,
        director, lead, manager, ...) are tagged 'senior'. Titles matching
        entry-signal words (junior, associate, new grad, intern, ...) are
        tagged 'entry'. Everything else defaults to 'mid_or_unspecified'
        rather than guessing -- an unqualified "Software Engineer" could be
        either, and mislabeling it 'entry' would be worse than leaving it
        ambiguous for a human to skim.

    location_is_nyc / location_is_remote: regex match against the posting's
        own location text (NOT the employer's HQ).

    company_is_nyc_hq / company_is_ai_focused: now always None. They came
        from `config/companies.json`, `company_ats` has no column for them,
        and adding one is a schema change out of scope here. Nothing reads
        them -- verified 2026-07-28: the only references anywhere in the repo
        are the writes in the six ingest scripts and the DDL at
        schema.py:295-296. Four of the six other sources already hardcode
        None (`builtin-nyc.py:364-365`, `hn-hiring.py:322-323`,
        `weworkremotely.py:178-179`, `google_jobs.py:116-117`), so this makes
        the column uniformly "unknown from this source" rather than
        half-populated from one. They are NOT in HASH_FIELDS_ATS
        (schema.py:131-132), so no existing row's content hash moves.

INCREMENTAL BEHAVIOR -- see DELTA SYNC above: no platform but SmartRecruiters
offers a server-side "changed since" filter, and using it forfeits closure.
job_ingest_state still records last_success_at per company, purely for
observability, not to shrink the fetch. Change detection is client-side:

    1. content_hash per job -- a row's last_seen is bumped without a write
       if nothing about it actually changed.
    2. Jobs that disappear from a company's feed are marked status='closed'
       rather than deleted. Rows closed for more than PRUNE_CLOSED_AFTER_DAYS
       are hard-deleted each run so the table doesn't grow unbounded.

CONCURRENCY -- this script is not scheduled directly. run-daily.py is the
actual cron entry point and runs the ingest scripts sequentially via
subprocess, so they never run concurrently on the same machine.

ERROR HANDLING -- deliberately different from ingest/builtin-nyc.py. This
script hits dozens of independent company APIs per run; one flaky/renamed/down
company endpoint is expected background noise, not a signal anything is
broken. So: per-company fetch failures are logged and skipped, other companies
still run, and the run only exits non-zero if EVERY company failed (which
points at something systemic -- DB down, network outage -- worth paging on).
That is volume-based alerting, which is what CLAUDE.md asks for: "Alert on
volume, not errors."

POLITENESS -- these are real employers' boards. REQUEST_DELAY_SECONDS between
outward calls, an honest User-Agent from lib/http.py, and no endpoint is
called more than its own pagination requires.
"""

import argparse
import collections
import html
import json
import os
import sys
import time
import urllib.error
import urllib.parse
from datetime import datetime, timezone

# ingest/ and tools/ sit one level below the pipeline modules they import
# (schema, relevance, llm, ...). Python puts THIS file's directory on sys.path,
# not its parent, so the parent is added by hand. That same insert is what
# reaches lib/ -- there is nothing to install.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
# ...and this file's OWN directory, so `import ats_sources` resolves when this
# module is loaded by path rather than run as a script -- which is exactly what
# evals/ingest_modules.py:40-55 does for every cassette test.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import ats_sources  # noqa: E402
import schema  # noqa: E402
from lib import dbconn, http, state, text  # noqa: E402
from lib.timeparse import utc_now_str  # noqa: E402
from lib.upsert import (UpsertErrorRate, UpsertResult, check_error_rate,  # noqa: E402
                        upsert_checked)

JOB_SOURCES_FILE = os.environ.get(
    "JOB_SOURCES_FILE",
    os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "config", "companies.json"),
)
DEBUG_PRINT_KEYS = os.environ.get("DEBUG_PRINT_KEYS", "") == "1"
PRUNE_CLOSED_AFTER_DAYS = 30

#: Seconds between outward calls. Only relevant to the paginating platforms
#: and to SmartRecruiters' per-posting detail fetches; a one-request board
#: never waits.
REQUEST_DELAY_SECONDS = 0.5

#: Prefix of the per-run request-count line. Stable format -- anything parsing
#: it (task 04's budget check) reads `total=` and the per-platform keys.
REQUEST_SUMMARY_PREFIX = "ats-requests:"

#: platform -> outward calls issued this run. Module-level so a cassette test
#: can assert the request SHAPE, not only the response: "SmartRecruiters was
#: asked for limit=100" is a claim about what we sent.
REQUESTS = collections.Counter()


def reset_requests():
    REQUESTS.clear()


def _get_json(platform, url, **kwargs):
    REQUESTS[platform] += 1
    return http.get_json(url, **kwargs)


def _post_json(platform, url, payload, **kwargs):
    REQUESTS[platform] += 1
    return http.post_json(url, payload, **kwargs)


def request_summary_line(companies=0):
    total = sum(REQUESTS.values())
    per = " ".join(f"{p}={REQUESTS[p]}" for p in sorted(REQUESTS))
    return (f"{REQUEST_SUMMARY_PREFIX} total={total} companies={companies}"
            + (f" {per}" if per else ""))


# ---------------------------------------------------------------------------
# what a fetch returns
# ---------------------------------------------------------------------------

class Fetched(list):
    """The postings a board returned, plus what the API said about the set.

    A `list` subclass rather than a wrapper, so every existing caller keeps
    working unchanged -- `for j in fetch_greenhouse(t)`, `len(...)`, a list
    comprehension over it. The extra attributes are provenance about the
    fetch, which a bare list has nowhere to put and which closure needs:

        reported_total  what the API said the set size is, or None if it does
                        not say. See RECONCILING AGAINST THE API'S OWN TOTAL.
        requests        outward calls this fetch cost.
        truncated       we stopped for a reason of our own (a page cap, a
                        documented API ceiling) rather than because the list
                        ended. Always fatal to closure.
    """

    def __init__(self, jobs, *, reported_total=None, requests=1,
                 truncated=False):
        super().__init__(jobs)
        self.reported_total = reported_total
        self.requests = requests
        self.truncated = truncated

    @property
    def complete(self):
        """Whether this fetch may be trusted to close absent postings.

        `reported_total is None` resolves to True, which is a deliberate and
        slightly uncomfortable choice: four of the six platforms publish no
        total at all, and refusing closure for them would silently retire a
        working feature for two thirds of the roster. Their endpoints return
        the whole board in one response, so a short answer is the answer.
        Where a total IS published, it wins.
        """
        if self.truncated:
            return False
        if self.reported_total is None:
            return True
        return len(self) >= self.reported_total

    def shortfall(self):
        """(collected, reported) when the fetch came up short, else None."""
        if self.reported_total is None or len(self) >= self.reported_total:
            return None
        return (len(self), self.reported_total)


# ---------------------------------------------------------------------------
# fetchers
# ---------------------------------------------------------------------------

def fetch_greenhouse(token):
    """One call. `content=true` is what returns descriptions.

    Without that parameter every posting arrives with no `content` key at all
    and every description silently becomes NULL while the run reports success
    -- the shape the `ats-greenhouse-no-content` cassette holds.

    `meta.total` is the reconciliation anchor (verified 2026-07-28:
    `{"meta": {"total": 5}}` beside 5 postings for `kickstarter`).
    """
    data = _get_json(
        "greenhouse",
        f"https://api.greenhouse.io/v1/boards/{token}/jobs?content=true")
    jobs = data.get("jobs", [])
    meta = data.get("meta") or {}
    total = meta.get("total") if isinstance(meta.get("total"), int) else None
    return Fetched(jobs, reported_total=total, requests=1)


#: Lever pages with `limit`+`skip`. 100 per page, verified working
#: (limit=3/skip=3 returns a disjoint set of ids).
LEVER_PAGE_LIMIT = 100

#: 17-retarget-ats-ingest.md:41-42: "pagination truncates at 250, so a company
#: with more roles needs slicing by team or location". This script does not
#: slice -- it records that it could not see the whole board and declines to
#: close anything for that company. Past 250 a short page is indistinguishable
#: from the API's own truncation, and "absent therefore closed" needs the
#: absence to be real.
LEVER_SKIP_CEILING = 250

#: Hard stop, so a misbehaving endpoint cannot page forever.
LEVER_MAX_PAGES = 10


def fetch_lever(token):
    """Paged. No total, no update timestamp -- see DELTA SYNC.

    `mode=json` is what makes the response JSON rather than the HTML board.
    """
    out, requests = [], 0
    truncated = False
    for page in range(LEVER_MAX_PAGES):
        data = _get_json(
            "lever",
            f"https://api.lever.co/v0/postings/{token}?mode=json"
            f"&limit={LEVER_PAGE_LIMIT}&skip={page * LEVER_PAGE_LIMIT}")
        requests += 1
        batch = data if isinstance(data, list) else []
        out.extend(batch)
        if len(batch) < LEVER_PAGE_LIMIT:
            break
        _pause()
    else:
        truncated = True
    if len(out) >= LEVER_SKIP_CEILING:
        truncated = True
    return Fetched(out, requests=requests, truncated=truncated)


def fetch_ashby(token):
    """One call. `includeCompensation=true` is what fills salary_text.

    17-retarget-ats-ingest.md:31 -- "cleanest salary support of any public
    feed", and it is: the field is a rendered range string the employer chose
    to publish, not a number this pipeline has to infer from prose. It costs
    nothing extra, and boards that do not publish compensation return the key
    with empty tiers rather than omitting it (verified against `runway`).
    """
    data = _get_json(
        "ashby",
        f"https://api.ashbyhq.com/posting-api/job-board/{token}"
        f"?includeCompensation=true")
    return Fetched(data.get("jobs", []), requests=1)


#: Workable is TWO endpoints, and the reason is worth stating.
#:
#: `17-retarget-ats-ingest.md:33` names `/api/v3/accounts/{slug}/jobs`. That
#: endpoint is authoritative about the SET -- it reports `total` and pages by
#: an opaque `nextPage` token -- and it carries no descriptions at all. It
#: also pages ten at a time, so reading a whole board through it costs
#: ceil(n/10) requests for postings that `extract.py` could not use anyway.
#:
#: The v1 widget with `details=true` returns every posting WITH its full
#: description in ONE request. What it does not return is a total, and it
#: EXPANDS ONE POSTING PER LOCATION: measured 2026-07-28 against `braven`,
#: 66 entries for 20 distinct `shortcode`s. Ingested naively that is a 3.3x
#: over-count of one employer's board, with 46 rows whose primary keys
#: collide (schema.make_job_id hashes the job_url, which is per-shortcode) so
#: they would silently overwrite each other.
#:
#: So: one v3 call for the truth about the size, one widget call for the
#: content, dedupe by shortcode, and reconcile the two. Two requests per
#: account regardless of board size, and the over-count cannot survive.
WORKABLE_WIDGET_URL = ("https://apply.workable.com/api/v1/widget/accounts/"
                       "{token}?details=true")
WORKABLE_V3_URL = "https://apply.workable.com/api/v3/accounts/{token}/jobs"


def fetch_workable(token):
    """Two calls: v3 for `total`, the v1 widget for descriptions."""
    # v3 FIRST, deliberately. If it fails, the whole company fetch fails and
    # lands in the per-company error list -- which means no records, which
    # means no closure. Swallowing it and carrying on would leave us closing
    # postings on the strength of an unreconciled list.
    page = _post_json("workable", WORKABLE_V3_URL.format(token=token), {})
    total = page.get("total") if isinstance(page.get("total"), int) else None
    _pause()
    data = _get_json("workable", WORKABLE_WIDGET_URL.format(token=token))

    jobs, seen = [], set()
    for job in (data.get("jobs") or []):
        code = job.get("shortcode")
        if code in seen:
            continue
        seen.add(code)
        jobs.append(job)
    return Fetched(jobs, reported_total=total, requests=2)


def fetch_recruitee(token):
    """One call, whole board, descriptions and salary included.

    No total and no pagination -- `{"offers": [...]}` and nothing else
    (verified 2026-07-28). Postings carry `updated_at`, but see DELTA SYNC:
    the endpoint accepts no filter for it.
    """
    data = _get_json("recruitee",
                     f"https://{token}.recruitee.com/api/offers/")
    return Fetched(data.get("offers") or [], requests=1)


SMARTRECRUITERS_BASE = "https://api.smartrecruiters.com/v1/companies"

#: SmartRecruiters clamps `limit` to 100 AND REPORTS THE CLAMP BACK -- asked
#: for 200 it answers `"limit":100` with 100 items (verified 2026-07-28
#: against `BoschGroup`, totalFound 4,755). That is the honest behaviour
#: Workday does not have: CLAUDE.md's landmine is that Workday answers
#: limit>20 with an EMPTY array and no error, indistinguishable from the end
#: of the list. Both were probed rather than assumed, because the trap
#: generalises even where this particular vendor avoids it.
SMARTRECRUITERS_PAGE_LIMIT = 100

#: 100 pages = 10,000 postings. Larger than any plausible single employer.
SMARTRECRUITERS_MAX_PAGES = 100

#: SmartRecruiters' list endpoint carries NO description -- the job ad lives
#: behind one GET per posting (`/postings/{id}`), and there is no bulk or
#: `expand=` form (probed: `?expand=jobAd` is ignored). A 4,755-posting board
#: is therefore 4,755 requests to describe fully, which is not a nightly
#: budget.
#:
#: So descriptions are backfilled: each run spends at most this many detail
#: calls per company, on postings that do NOT already have a stored
#: description. In steady state that is the day's new postings and nothing
#: else. A board bigger than the budget fills in over successive nights, and
#: the shortfall is printed rather than left to be inferred from a column
#: that is quietly NULL.
SMARTRECRUITERS_DETAIL_BUDGET = int(
    os.environ.get("ATS_SR_DETAIL_BUDGET", "200"))


def fetch_smartrecruiters(token, released_after=None):
    """Paged list. `totalFound` is the reconciliation anchor.

    `released_after` is the ONE server-side delta filter available anywhere in
    this script (see DELTA SYNC). It filters on publication date, and a run
    that uses it must not close anything.
    """
    out, requests, offset = [], 0, 0
    total = None
    truncated = False
    for _ in range(SMARTRECRUITERS_MAX_PAGES):
        url = (f"{SMARTRECRUITERS_BASE}/{token}/postings"
               f"?limit={SMARTRECRUITERS_PAGE_LIMIT}&offset={offset}")
        if released_after:
            url += "&releasedAfter=" + urllib.parse.quote(released_after)
        data = _get_json("smartrecruiters", url)
        requests += 1
        if isinstance(data.get("totalFound"), int):
            total = data["totalFound"]
        content = data.get("content") or []
        out.extend(content)
        offset += len(content)
        if not content or (total is not None and len(out) >= total):
            break
        _pause()
    else:
        truncated = True
    return Fetched(out, reported_total=total, requests=requests,
                   truncated=truncated)


def fetch_smartrecruiters_detail(token, posting_id):
    """One posting, with its `jobAd`. The only way to get a description."""
    return _get_json(
        "smartrecruiters",
        f"{SMARTRECRUITERS_BASE}/{token}/postings/{posting_id}")


FETCHERS = {
    "greenhouse": fetch_greenhouse,
    "lever": fetch_lever,
    "ashby": fetch_ashby,
    "workable": fetch_workable,
    "recruitee": fetch_recruitee,
    "smartrecruiters": fetch_smartrecruiters,
}

#: Platforms whose fetcher takes a `released_after` keyword. See DELTA SYNC --
#: this is a one-element set and stating it as data keeps `--delta` from
#: quietly becoming a no-op nobody notices.
DELTA_CAPABLE = ("smartrecruiters",)


def _pause():
    time.sleep(REQUEST_DELAY_SECONDS)


# ---------------------------------------------------------------------------
# descriptions
# ---------------------------------------------------------------------------

def greenhouse_description(content):
    """Plain text from Greenhouse's `content`, which arrives HTML-ESCAPED.

    Greenhouse does not serve HTML in this field -- it serves HTML that has
    been escaped once, so the tags themselves are entities:

        &lt;div class=&quot;content-intro&quot;&gt;&lt;h2&gt;About Us:&amp;nbsp;

    That is one level deeper than every other source here, and it is why a
    single unescape is not enough. Unescaping once turns `&lt;div&gt;` into a
    real `<div>` (strippable) but only turns `&amp;nbsp;` into `&nbsp;`, which
    then survives tag-stripping and lands in the database as literal text.

    Measured over 400 sampled postings:
        strip_html(c, unescape=False)  -- 300/300 rows held literal entities
        strip_html(c)                  -- 277/300 still did
        strip_html(html.unescape(c))   --   0/300   <- this

    So: unescape once here, and let strip_html's own unescape handle the
    second level before it strips tags. Do not "simplify" this into a single
    call -- 7,182 rows reading `&lt;div class=&quot;...` is what that looks
    like in production.
    """
    if not content:
        return None
    return text.strip_html(html.unescape(content))


#: The order SmartRecruiters' own careers page renders them in. `videos` is
#: skipped: it holds embed markup, not prose.
SMARTRECRUITERS_SECTIONS = ("companyDescription", "jobDescription",
                            "qualifications", "additionalInformation")


def smartrecruiters_description(job):
    """Plain text from a merged posting's `jobAd.sections`, or None.

    Returns None -- not "" -- when the posting has no jobAd, so a row whose
    detail call has not been spent yet is distinguishable from a posting whose
    ad is genuinely empty. `extract.py`'s selector keys on that difference.
    """
    sections = ((job.get("jobAd") or {}).get("sections") or {})
    parts = []
    for name in SMARTRECRUITERS_SECTIONS:
        raw = (sections.get(name) or {}).get("text")
        if raw:
            parts.append(text.strip_html(raw))
    if not parts:
        return None
    return "\n\n".join(p for p in parts if p) or None


def recruitee_description(job):
    """`description` and `requirements`, both real HTML, joined."""
    parts = [text.strip_html(job.get(field))
             for field in ("description", "requirements")
             if job.get(field)]
    parts = [p for p in parts if p]
    return "\n\n".join(parts) if parts else None


def recruitee_salary(job):
    """Recruitee's structured salary as one line, or None.

    The only structured salary in this script besides Ashby's. Rendered
    rather than stored as JSON because `jobs.salary_text` is TEXT and every
    other source writes prose into it.
    """
    salary = job.get("salary")
    if not isinstance(salary, dict):
        return None
    low, high = salary.get("min"), salary.get("max")
    if not (low or high):
        return None
    currency = (salary.get("currency") or "").strip()
    period = (salary.get("period") or "").strip()
    span = f"{low}-{high}" if low and high else (low or high)
    out = " ".join(p for p in (currency, span) if p)
    return f"{out} / {period}" if period else out


def ashby_salary(job):
    """Ashby's rendered compensation summary, or None.

    `compensationTierSummary` is the string the employer's own board shows
    ("$213K - $251K • Offers Equity • ..."). `scrapeableCompensation-
    SalarySummary` is Ashby's machine-readable sibling and is the fallback.
    Boards that do not publish compensation return the `compensation` key
    with empty tiers and both summaries null, which is why this returns None
    rather than "" -- salary_text is nullable and "unknown" is not "none".
    """
    comp = job.get("compensation")
    if not isinstance(comp, dict):
        return None
    for key in ("compensationTierSummary", "scrapeableCompensationSalarySummary"):
        value = comp.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


# ---------------------------------------------------------------------------
# normalizers
# ---------------------------------------------------------------------------
#
# Every normalize_* must supply every key in schema.COLUMNS: upsert binds them
# as named parameters, so a missing one fails that record (isolated by its
# SAVEPOINT) rather than the batch. schema.py:118-120.
#
# `company` is a roster dict from ats_sources.load_companies() -- platform,
# token, name, status. `.get()` is used for the two retired company-level
# flags so that a caller still passing them (the cassette tests do) keeps
# working, while the roster's absence of them reads as None rather than False.


def _company_flags(company):
    """(is_nyc_hq, is_ai_focused) -- None when the roster does not say.

    `bool(company.get(...))` was wrong: it turned "this roster has no opinion"
    into a confident False on every row. Unknown is None. See the note on
    these two columns in the module docstring.
    """
    def flag(key):
        value = company.get(key)
        return None if value is None else bool(value)
    return flag("is_nyc_hq"), flag("is_ai_focused")


def normalize_greenhouse(company, job):
    title = job.get("title")
    location = (job.get("location") or {}).get("name")
    is_nyc, is_remote = text.classify_location(location)
    departments = job.get("departments") or []
    department = departments[0].get("name") if departments else None
    nyc_hq, ai_focused = _company_flags(company)
    return {
        "platform": "greenhouse",
        "company_token": company["token"],
        "company_name": company["name"],
        "source_id": str(job.get("id")),
        "title": title,
        "location_raw": location,
        "department": department,
        "job_url": job.get("absolute_url"),
        "posted_at": job.get("updated_at") or job.get("first_published"),
        # posted_at (hashed, frozen format) keeps updated_at first for
        # compatibility. posted_at_ts is what an app sorts on, so it prefers
        # first_published: "posted" should mean posted. Greenhouse bumps
        # updated_at for edits, which is why 6,096 rows looked July-fresh.
        "posted_at_ts": text.posted_at_timestamp(
            job.get("first_published") or job.get("updated_at")),
        "salary_text": None,
        "seniority_guess": text.guess_seniority(title),
        "location_is_nyc": is_nyc,
        "location_is_remote": is_remote,
        "company_is_nyc_hq": nyc_hq,
        "company_is_ai_focused": ai_focused,
        "description_text": greenhouse_description(job.get("content")),
        "raw_json": json.dumps(job),
    }


def normalize_lever(company, job):
    title = job.get("text")
    cats = job.get("categories") or {}
    location = cats.get("location") or ", ".join(cats.get("allLocations") or [])
    is_nyc, is_remote = text.classify_location(location)
    posted_at = None
    created = job.get("createdAt")
    if created:
        try:
            posted_at = datetime.fromtimestamp(created / 1000, tz=timezone.utc).isoformat()
        except (ValueError, OSError, OverflowError):
            posted_at = None
    nyc_hq, ai_focused = _company_flags(company)
    return {
        "platform": "lever",
        "company_token": company["token"],
        "company_name": company["name"],
        "source_id": str(job.get("id")),
        "title": title,
        "location_raw": location,
        "department": cats.get("department"),
        "job_url": job.get("hostedUrl"),
        "posted_at": posted_at,
        "posted_at_ts": text.posted_at_timestamp(posted_at),
        "salary_text": None,
        "seniority_guess": text.guess_seniority(title),
        "location_is_nyc": is_nyc,
        "location_is_remote": is_remote,
        "company_is_nyc_hq": nyc_hq,
        "company_is_ai_focused": ai_focused,
        # Lever serves real HTML (verified: `<p><strong>About Finix</strong>`),
        # so one unescape -- strip_html's default -- is correct here. Passing
        # unescape=False was leaving `&amp;` in the stored text.
        "description_text": text.strip_html(job.get("description") or job.get("descriptionBody")),
        "raw_json": json.dumps(job),
    }


def normalize_ashby(company, job):
    title = job.get("title")
    location = job.get("location")
    is_nyc, is_remote = text.classify_location(location)
    if job.get("isRemote"):
        is_remote = True
    nyc_hq, ai_focused = _company_flags(company)
    return {
        "platform": "ashby",
        "company_token": company["token"],
        "company_name": company["name"],
        "source_id": str(job.get("id")),
        "title": title,
        "location_raw": location,
        "department": job.get("department"),
        "job_url": job.get("jobUrl"),
        "posted_at": job.get("publishedAt"),
        "posted_at_ts": text.posted_at_timestamp(job.get("publishedAt")),
        "salary_text": ashby_salary(job),
        "seniority_guess": text.guess_seniority(title),
        "location_is_nyc": is_nyc,
        "location_is_remote": is_remote,
        "company_is_nyc_hq": nyc_hq,
        "company_is_ai_focused": ai_focused,
        # Ashby also serves real HTML (`<h1>Who We Are</h1>`) -- same reasoning
        # as Lever. This was leaving `&amp;` in 1,521 of 2,561 rows.
        "description_text": text.strip_html(job.get("descriptionHtml") or job.get("descriptionPlain")),
        "raw_json": json.dumps(job),
    }


def _workable_location(job):
    """"City, Region, Country" from whichever spelling the widget used."""
    parts = [job.get("city"), job.get("state"), job.get("country")]
    joined = ", ".join(p for p in parts if p)
    if joined:
        return joined
    first = (job.get("locations") or [{}])[0]
    parts = [first.get("city"), first.get("region"), first.get("country")]
    return ", ".join(p for p in parts if p) or None


def normalize_workable(company, job):
    """A v1-widget posting. `shortcode` is the id, not `id`.

    The widget carries no numeric id at all; `shortcode` is what appears in
    the public URL and is what the v3 endpoint agrees with, so it is the
    stable source_id.
    """
    title = job.get("title")
    location = _workable_location(job)
    is_nyc, is_remote = text.classify_location(location)
    if job.get("telecommuting"):
        is_remote = True
    posted = job.get("published_on") or job.get("created_at")
    nyc_hq, ai_focused = _company_flags(company)
    return {
        "platform": "workable",
        "company_token": company["token"],
        "company_name": company["name"],
        "source_id": str(job.get("shortcode")),
        "title": title,
        "location_raw": location,
        "department": job.get("department"),
        "job_url": job.get("url") or job.get("shortlink"),
        "posted_at": posted,
        "posted_at_ts": text.posted_at_timestamp(posted),
        "salary_text": None,
        "seniority_guess": text.guess_seniority(title),
        "location_is_nyc": is_nyc,
        "location_is_remote": is_remote,
        "company_is_nyc_hq": nyc_hq,
        "company_is_ai_focused": ai_focused,
        # Real HTML, one unescape -- same as Lever and Ashby, verified against
        # `braven`: `<p><strong>Job Title</strong>: ...`.
        "description_text": text.strip_html(job.get("description")),
        "raw_json": json.dumps(job),
    }


def normalize_recruitee(company, job):
    title = job.get("title")
    location = job.get("location")
    is_nyc, is_remote = text.classify_location(location)
    if job.get("remote"):
        is_remote = True
    posted = job.get("published_at") or job.get("created_at")
    nyc_hq, ai_focused = _company_flags(company)
    return {
        "platform": "recruitee",
        "company_token": company["token"],
        "company_name": company["name"],
        "source_id": str(job.get("id")),
        "title": title,
        "location_raw": location,
        "department": job.get("department"),
        "job_url": job.get("careers_url"),
        "posted_at": posted,
        "posted_at_ts": text.posted_at_timestamp(posted),
        "salary_text": recruitee_salary(job),
        "seniority_guess": text.guess_seniority(title),
        "location_is_nyc": is_nyc,
        "location_is_remote": is_remote,
        "company_is_nyc_hq": nyc_hq,
        "company_is_ai_focused": ai_focused,
        "description_text": recruitee_description(job),
        "raw_json": json.dumps(job),
    }


def _smartrecruiters_location(job):
    loc = job.get("location") or {}
    if loc.get("fullLocation"):
        return loc["fullLocation"]
    parts = [loc.get("city"), loc.get("region"),
             (loc.get("country") or "").upper() or None]
    return ", ".join(p for p in parts if p) or None


def normalize_smartrecruiters(company, job):
    """A posting, optionally merged with its detail response.

    `description_text` is None until a detail call has been spent on this
    posting -- see SMARTRECRUITERS_DETAIL_BUDGET. That is a real, reported
    state, not a parse failure.
    """
    title = job.get("name")
    location = _smartrecruiters_location(job)
    is_nyc, is_remote = text.classify_location(location)
    loc = job.get("location") or {}
    if loc.get("remote"):
        is_remote = True
    department = (job.get("department") or {}).get("label")
    posted = job.get("releasedDate")
    token = company["token"]
    nyc_hq, ai_focused = _company_flags(company)
    return {
        "platform": "smartrecruiters",
        "company_token": token,
        "company_name": company["name"],
        "source_id": str(job.get("id")),
        "title": title,
        "location_raw": location,
        "department": department,
        # postingUrl only exists on the detail response; the list carries
        # `ref`, which is the API URL and is not something a human can open.
        "job_url": (job.get("postingUrl")
                    or f"https://jobs.smartrecruiters.com/{token}/{job.get('id')}"),
        "posted_at": posted,
        "posted_at_ts": text.posted_at_timestamp(posted),
        "salary_text": None,
        "seniority_guess": text.guess_seniority(title),
        "location_is_nyc": is_nyc,
        "location_is_remote": is_remote,
        "company_is_nyc_hq": nyc_hq,
        "company_is_ai_focused": ai_focused,
        "description_text": smartrecruiters_description(job),
        "raw_json": json.dumps(job),
    }


NORMALIZERS = {
    "greenhouse": normalize_greenhouse,
    "lever": normalize_lever,
    "ashby": normalize_ashby,
    "workable": normalize_workable,
    "recruitee": normalize_recruitee,
    "smartrecruiters": normalize_smartrecruiters,
}


# ---------------------------------------------------------------------------
# SmartRecruiters description backfill
# ---------------------------------------------------------------------------

def already_described(conn, platform, token, source_ids):
    """Which of `source_ids` already have a stored description.

    Read-only. Spending a detail request on a posting whose description is
    already in the table is the whole cost this budget exists to avoid.
    """
    if not source_ids:
        return set()
    rows = conn.execute(
        """
        SELECT source_id FROM jobs
         WHERE platform = %s AND company_token = %s
           AND source_id = ANY(%s) AND description_text IS NOT NULL
        """,
        (platform, token, list(source_ids)),
    ).fetchall()
    return {r[0] for r in rows}


def merge_smartrecruiters_details(conn, token, postings, budget):
    """Fetch job ads for undescribed postings, newest first. Returns (postings, spent, still_missing).

    Newest first because a posting released today is the one a user is about
    to see; a two-year-old req that has gone undescribed for a week is not
    urgent. `releasedDate` sorts lexically as ISO 8601.
    """
    ids = [str(p.get("id")) for p in postings if p.get("id")]
    have = already_described(conn, "smartrecruiters", token, ids)
    todo = [p for p in postings if str(p.get("id")) not in have]
    todo.sort(key=lambda p: p.get("releasedDate") or "", reverse=True)

    by_id, spent = {}, 0
    for posting in todo[:budget]:
        try:
            by_id[str(posting["id"])] = fetch_smartrecruiters_detail(
                token, posting["id"])
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError,
                json.JSONDecodeError, OSError) as e:
            # One unreachable posting is not a reason to abandon the rest of
            # the board; it simply keeps its NULL description and is retried
            # tomorrow.
            if DEBUG_PRINT_KEYS:
                print(f"[debug] smartrecruiters detail {posting['id']} "
                      f"failed: {e}", file=sys.stderr)
        spent += 1
        _pause()

    merged = [{**p, **by_id.get(str(p.get("id")), {})} for p in postings]
    return merged, spent, max(0, len(todo) - budget)


# ---------------------------------------------------------------------------
# the run
# ---------------------------------------------------------------------------

def fetch_company(conn, company, delta_since=None):
    """(records, fetched, notes). Everything platform-specific ends here.

    Splitting this out is what keeps main()'s loop -- and therefore closure,
    upsert and the watermark -- identical for all six platforms. The task's
    "share the closure logic rather than copy-pasting it per platform" is a
    property of this shape, not of a helper: there is exactly one call to
    schema.close_missing() in this file and it is not inside a per-platform
    branch.
    """
    platform, token = company["platform"], company["token"]
    fetch, normalize = FETCHERS[platform], NORMALIZERS[platform]
    notes = []

    if delta_since and platform in DELTA_CAPABLE:
        fetched = fetch(token, released_after=delta_since)
        notes.append(f"delta since {delta_since}")
    else:
        fetched = fetch(token)

    raw = list(fetched)
    if platform == "smartrecruiters":
        raw, spent, missing = merge_smartrecruiters_details(
            conn, token, raw, SMARTRECRUITERS_DETAIL_BUDGET)
        if spent:
            notes.append(f"{spent} detail request(s)")
        if missing:
            notes.append(f"{missing} posting(s) still undescribed "
                         f"(budget {SMARTRECRUITERS_DETAIL_BUDGET})")

    records = [normalize(company, job) for job in raw]
    return records, fetched, notes


def main(argv=None):
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--seed-from-json", action="store_true",
                    help=f"one-time, idempotent: insert the tokens in "
                         f"{JOB_SOURCES_FILE} into company_ats and exit. "
                         f"Never overwrites a row tools/ats-discover.py wrote.")
    ap.add_argument("--delta", metavar="ISO8601",
                    help="only postings released after this timestamp, on the "
                         "platforms that support it (smartrecruiters). "
                         "DISABLES CLOSURE -- a delta response is not the "
                         "complete set, so absence proves nothing. Not for "
                         "the nightly run.")
    args = ap.parse_args(argv)

    conn = dbconn.connect_or_exit("jobs ingest", schema=schema.SCHEMA)
    schema.ensure_schema(conn)

    if args.seed_from_json:
        try:
            result, skipped = ats_sources.seed_from_companies_json(
                conn, JOB_SOURCES_FILE, debug=DEBUG_PRINT_KEYS)
        except (OSError, ValueError, KeyError, json.JSONDecodeError) as e:
            print(f"jobs ingest FAILED: could not seed from "
                  f"{JOB_SOURCES_FILE}: {e}")
            conn.close()
            sys.exit(1)
        print(f"ats-seed: {result.new} inserted, {skipped} already present, "
              f"{len(result.errors)} failed, from {JOB_SOURCES_FILE}")
        conn.close()
        return

    # One spec per source family: ats/wwr hash `department`, the Google and
    # HN sources do not. The tuples are stored digests -- see schema.py.
    ats_spec = schema.spec(schema.HASH_FIELDS_ATS)

    try:
        sources = ats_sources.load_companies(conn)
    except Exception as e:
        print(f"jobs ingest FAILED: could not read company_ats: {e}")
        conn.close()
        sys.exit(1)

    if not sources:
        # Silence is this system's failure mode. An empty roster is not a
        # quiet night, it is a broken one -- and it exits non-zero rather than
        # reporting a clean run over nothing.
        print(f"jobs ingest FAILED: company_ats holds no rows for "
              f"{list(ats_sources.HANDLED_PLATFORMS)} with status in "
              f"{list(ats_sources.ADMITTING_STATUSES)}. Seed it with "
              f"`python3 ingest/ats.py --seed-from-json` or run "
              f"`python3 tools/ats-discover.py --apply`.")
        conn.close()
        sys.exit(1)

    reset_requests()
    run_started_at = utc_now_str()
    total_closed = 0
    #: Accumulated across companies so the failure-rate check is per RUN, not
    #: per company: one 3-record source failing entirely is not a reason to
    #: abandon the other forty-nine, but the same failures spread across the
    #: whole run are. UpsertResult.__add__ sums the error lists too.
    totals = UpsertResult()
    company_errors = []
    company_successes = 0
    unreconciled = []
    unvalidated_used = sum(
        1 for c in sources if c["status"] != ats_sources.STATUS_VALID)

    for company in sources:
        platform = company["platform"]
        token = company["token"]

        try:
            records, fetched, notes = fetch_company(
                conn, company, delta_since=args.delta)
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError,
                json.JSONDecodeError, OSError) as e:
            company_errors.append(f"{company['name']} ({platform}:{token}): {e}")
            if DEBUG_PRINT_KEYS:
                print(f"[debug] fetch failed for {token}: {e}", file=sys.stderr)
            continue

        try:
            result = upsert_checked(conn, ats_spec, records, schema.make_job_id,
                                    debug=DEBUG_PRINT_KEYS)
        except UpsertErrorRate as e:
            # Same reasoning as the fetch failure above: one source writing
            # badly isn't a reason to skip the rest. But it IS now counted --
            # it lands in company_errors, in the stdout summary, and in the
            # run-level rate check after the loop.
            result = e.result
            company_errors.append(f"{company['name']} ({platform}:{token}): {e}")
        else:
            company_successes += 1
        totals += result
        n, u, unc = result.new, result.updated, result.unchanged

        # THE ONLY CLOSURE CALL IN THIS FILE. Three conditions, each of which
        # has its own failure story in the module docstring: a non-empty
        # fetch, a complete one, and a full pull rather than a delta.
        closing = bool(records) and fetched.complete and not (
            args.delta and platform in DELTA_CAPABLE)
        if closing:
            total_closed += schema.close_missing(conn, platform, token,
                                                 [r["source_id"] for r in records],
                                                 run_started_at)
        elif records and not fetched.complete:
            short = fetched.shortfall()
            why = (f"collected {short[0]} of {short[1]} the API reported"
                   if short else "fetch stopped at a page cap")
            unreconciled.append(f"{platform}:{token} ({why})")

        state.set_watermark(conn, f"{platform}:{token}", run_started_at,
                            table=schema.WATERMARK_TABLE)

        if DEBUG_PRINT_KEYS:
            extra = ("; " + "; ".join(notes)) if notes else ""
            print(f"[debug] {company['name']} ({platform}): fetched "
                  f"{len(fetched)} -> {n} new, {u} updated, {unc} unchanged"
                  f"{extra}", file=sys.stderr)

    pruned = schema.prune_old_closed(conn, PRUNE_CLOSED_AFTER_DAYS)
    conn.close()

    # ALWAYS, including on a clean run. See REQUEST COUNT in the docstring.
    print(request_summary_line(companies=len(sources)), file=sys.stderr)

    if unreconciled:
        # Never silent: a company whose board could not be reconciled kept its
        # rows open, which is the safe choice, but it also means the closure
        # signal for that employer is stale and somebody should know.
        print(f"jobs-ingest: {len(unreconciled)} board(s) not reconciled "
              f"against the API's own total -- closure SKIPPED for them: "
              f"{unreconciled[:5]}", file=sys.stderr)

    if company_errors and company_successes == 0:
        print(f"jobs ingest FAILED: all {len(company_errors)} sources failed. "
              f"Sample: {company_errors[:3]}")
        sys.exit(1)

    if company_errors and DEBUG_PRINT_KEYS:
        print(f"[debug] {len(company_errors)}/{len(sources)} sources failed (continuing): "
              f"{company_errors[:5]}", file=sys.stderr)

    # Stay silent on quiet days -- that's the point of no-agent watchdog mode.
    # Dropped records are never a quiet day, so totals.errors joins the
    # conditions that break the silence.
    if (totals.new or totals.updated or total_closed or pruned
            or company_errors or totals.errors or unreconciled):
        print(f"jobs-ingest: {totals.new} new, {totals.updated} updated, "
              f"{totals.unchanged} unchanged, "
              f"{total_closed} closed, {pruned} old-closed pruned, "
              f"{len(totals.errors)} record(s) dropped, "
              f"across {company_successes}/{len(sources)} sources "
              f"({len(company_errors)} failed, {unvalidated_used} unvalidated, "
              f"{len(unreconciled)} unreconciled), "
              f"{sum(REQUESTS.values())} request(s).")

    # Last, so the summary above is on stdout either way: the run-level rate,
    # across every company rather than within one.
    try:
        check_error_rate(totals, label=schema.TABLE)
    except UpsertErrorRate as e:
        print(f"jobs ingest FAILED: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()

"""The four Workday CXS silent failures, as replayable fixtures.

Task 18 (`docs/tasks/refactor/tranche_three/18-ingest-workday-cxs.md:40-59`)
lists four ways the Workday CXS endpoint loses data while returning success,
and requires that each have "a cassette fixture from task 09 that reproduces
it, and a test that fails loudly". This module is those four fixtures. Task
18 writes the ingest script; these exist first so it is written against them.

    from evals import cassettes, workday_fixtures as wf
    with cassettes.replay(cassette=wf.limit_over_20()) as player:
        ...                       # drive the real ingest script here

CONSTRUCTED, NOT RECORDED -- SAY SO PLAINLY
    Every other cassette in `evals/fixtures/cassettes/` holds bytes a real
    server sent. These do not, and could not yet: `company_ats` has no
    Workday rows until task 16 runs, so there is no tenant/dc/site triple to
    record against, and three of the four failures cannot be provoked on
    demand anyway -- you cannot ask a stranger's Akamai to throttle you.

    What they encode is the request/response SHAPE documented at
    18-ingest-workday-cxs.md:20-37, with the failure injected. That makes
    them a specification of the trap rather than evidence of it. The moment
    task 16 produces a real tenant, `record_cassettes.py` should gain a
    recipe that records the happy path, and `page()` below should be checked
    against it -- there is a test asserting the shape stays as documented so
    that check is a diff rather than a re-read.

WHY A BUILDER MODULE AND NOT COMMITTED JSON
    Failure 4 is the 10,000-result cap. Reproducing it honestly needs 500
    pages; committing 500 recorded pages to make one assertion is not a
    fixture anybody will read, and shrinking the cap to make the file small
    would test a cap that does not exist. So the shape is written literally
    here, once, and the pages are generated. The other three are small, and
    are built the same way for one mechanism rather than two.
"""

import hashlib
import json

from evals.cassettes import Cassette, Interaction

#: The documented tenant shape. `wd5` is deliberately not `wd1` -- see
#: prefix_assumed() for why a default is the third failure.
TENANT = "acmehospital"
SITE = "External"
DC = "wd5"
WRONG_DC = "wd1"

#: 18-ingest-workday-cxs.md:46: "Hardcode 20 and assert it."
PAGE_LIMIT = 20

#: NVIDIA's numbers, from the published account at
#: 18-ingest-workday-cxs.md:50 -- 1,960 of 2,000 jobs lost to a throttled
#: page read as the end of the list.
TOTAL = 2000
THROTTLE_AT_OFFSET = 40

#: A single Workday query cannot enumerate past this, whatever `total` says.
RESULT_CAP = 10000
CAPPED_TOTAL = 12431

#: The faceted slice task 18 prescribes for a tenant over the cap.
FACET = {"locations": ["nyc"]}
FACETED_TOTAL = 480


def host(dc=DC):
    return f"https://{TENANT}.{dc}.myworkdayjobs.com"


def jobs_url(dc=DC):
    return f"{host(dc)}/wday/cxs/{TENANT}/{SITE}/jobs"


def job_url(external_path):
    """The PUBLIC url, per 18-ingest-workday-cxs.md:37."""
    return f"{host()}/en-US/{SITE}{external_path}"


def body(offset=0, limit=PAGE_LIMIT, facets=None, search=""):
    """The request body, exactly as documented at 18-...md:24.

    Key order is fixed because the cassette matches a POST on the sha256 of
    its body: two callers spelling the same request with different key order
    would be two different requests. json.dumps with sort_keys is what the
    ingest script should send, and what this hashes.
    """
    return json.dumps({"appliedFacets": facets or {},
                       "limit": limit, "offset": offset,
                       "searchText": search}, sort_keys=True).encode()


def posting(n):
    """One jobPostings entry. Fields per 18-...md:27-30."""
    return {
        "title": f"Registered Nurse {n}" if n % 3 else f"Data Analyst {n}",
        "locationsText": "New York, NY" if n % 2 else "Brooklyn, NY",
        "externalPath": f"/job/New-York/Posting-{n}_R-{100000 + n}",
        "startDate": "2026-07-14",
        "bulletFields": [f"R-{100000 + n}"],
        "jobRequisitionLocation": {"country": {"descriptor": "United States"},
                                   "descriptor": "New York, NY"},
    }


def page(offset, total=TOTAL, limit=PAGE_LIMIT):
    """A successful list response: `total` plus up to `limit` postings."""
    remaining = max(0, min(limit, total - offset))
    return {"total": total,
            "jobPostings": [posting(offset + i) for i in range(remaining)]}


def _post(offset, payload, *, dc=DC, limit=PAGE_LIMIT, facets=None,
          status=200, headers=None, reason=""):
    return Interaction(
        method="POST", url=jobs_url(dc), status=status,
        headers=headers or {"Content-Type": "application/json"},
        body=json.dumps(payload),
        request_body_sha256=hashlib.sha256(
            body(offset, limit, facets)).hexdigest(),
        reason=reason)


def _cassette(name, note, interactions):
    return Cassette(name=name, source=f"{TENANT}.{DC}.myworkdayjobs.com "
                                      f"(CONSTRUCTED, not recorded)",
                    note=note, recorded_at=None,
                    recorded_by="evals/workday_fixtures.py (task 09)",
                    interactions=interactions)


# ---------------------------------------------------------------------------
# 1. `limit` cannot exceed 20
# ---------------------------------------------------------------------------

def limit_over_20():
    """limit=100 -> HTTP 200, `jobPostings: []`, no error field.

    18-ingest-workday-cxs.md:44: "byte-identical to 'no more results'". The
    fixture holds BOTH bodies against the SAME url, so a test can show that
    the only difference between "everything" and "nothing" is the request --
    which is the whole reason this one is invisible. `total` is still 2000
    in the empty response, which is what makes the reconciliation check in
    failure 2 catch this one too.
    """
    return _cassette(
        "workday-limit-over-20",
        "Same URL, two request bodies: limit=20 returns a full page, "
        "limit=100 returns an empty jobPostings with HTTP 200 and no error. "
        "The count that gives it away is `total`, which stays 2000.",
        [_post(0, page(0), limit=PAGE_LIMIT),
         _post(0, {"total": TOTAL, "jobPostings": []}, limit=100)])


# ---------------------------------------------------------------------------
# 2. A throttled page reads as the end of the list
# ---------------------------------------------------------------------------

def throttled_page():
    """Pages at offset 0 and 20, HTTP 429 at 40, pages again after.

    A loop that treats a failed page as termination stops with 40 of 2000 --
    the published NVIDIA failure, 1,960 lost, exit status zero. A loop that
    retries and then reconciles collected against `total` gets all 2000. The
    429 carries Retry-After, so lib/http.py:78 backs off on it rather than
    raising, which is what makes "just use lib/http" the cheap half of the
    fix.

    Every offset from 60 to the end is present, so a correct loop can
    actually finish; that is 100 pages, built lazily.
    """
    interactions = []
    for offset in range(0, TOTAL, PAGE_LIMIT):
        if offset == THROTTLE_AT_OFFSET:
            interactions.append(_post(
                offset, {"error": "Too Many Requests"}, status=429,
                headers={"Content-Type": "application/json", "Retry-After": "1"},
                reason="Too Many Requests"))
        interactions.append(_post(offset, page(offset)))
    # The terminating empty page. Every fixture that a loop walks to the end
    # needs one, or the loop's last request is a cassette miss and the test
    # measures the harness instead of the failure.
    interactions.append(_post(TOTAL, {"total": TOTAL, "jobPostings": []}))
    return _cassette(
        "workday-throttled-page",
        f"HTTP 429 at offset {THROTTLE_AT_OFFSET} of {TOTAL}, then the same "
        f"page succeeds on retry. A loop that terminates on a failed page "
        f"collects {THROTTLE_AT_OFFSET} and reports success.",
        interactions)


# ---------------------------------------------------------------------------
# 3. The data-centre prefix varies
# ---------------------------------------------------------------------------

def prefix_assumed():
    """wd1 (assumed) -> 404 HTML; wd5 (stored) -> the real list.

    18-ingest-workday-cxs.md:54: read `wd{N}` from `company_ats`, "never
    assume, never default". The fixture makes the cost concrete: the wrong
    host answers with an HTML error page, so a caller that json-decodes it
    gets a JSONDecodeError, which every ingest script in this repo catches
    and counts as one unreachable source among fifty -- indistinguishable
    from a tenant that is genuinely down, and therefore silent at the only
    scale that matters.
    """
    return _cassette(
        "workday-wrong-dc-prefix",
        f"{WRONG_DC} (a default) 404s with an HTML body; {DC} (the value "
        f"stored by task 16) returns the list. A wrong prefix is one more "
        f"failed tenant in a fifty-tenant loop, not an alert.",
        [_post(0, {}, dc=WRONG_DC, status=404, reason="Not Found",
               headers={"Content-Type": "text/html"}),
         _post(0, page(0))])


# ---------------------------------------------------------------------------
# 4. The 10,000-result cap
# ---------------------------------------------------------------------------

def result_cap():
    """total=12431, pages up to offset 10000, then empty forever.

    18-ingest-workday-cxs.md:57: a single query cannot enumerate past the
    cap. Reconciling against `total` DETECTS this one but cannot fix it --
    the fix is slicing by `appliedFacets` and merging, so the fixture also
    holds the faceted query, whose own `total` is under the cap and which
    therefore enumerates completely.
    """
    interactions = []
    for offset in range(0, RESULT_CAP + PAGE_LIMIT, PAGE_LIMIT):
        if offset >= RESULT_CAP:
            interactions.append(_post(
                offset, {"total": CAPPED_TOTAL, "jobPostings": []}))
        else:
            interactions.append(_post(offset, page(offset, total=CAPPED_TOTAL)))
    for offset in range(0, FACETED_TOTAL, PAGE_LIMIT):
        interactions.append(_post(
            offset, page(offset, total=FACETED_TOTAL), facets=FACET))
    interactions.append(_post(FACETED_TOTAL,
                              {"total": FACETED_TOTAL, "jobPostings": []},
                              facets=FACET))
    return _cassette(
        "workday-result-cap",
        f"Unfaceted: total={CAPPED_TOTAL}, enumerable to {RESULT_CAP}, empty "
        f"after -- {CAPPED_TOTAL - RESULT_CAP} postings unreachable however "
        f"long the loop runs. Faceted by {FACET}: total={FACETED_TOTAL}, "
        f"fully enumerable.",
        interactions)


#: Every failure, by the number task 18 gives it.
FIXTURES = {
    1: limit_over_20,
    2: throttled_page,
    3: prefix_assumed,
    4: result_cap,
}

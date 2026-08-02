"""SerpApi's `google_jobs` engine. 250 searches/month on the free tier.

LIFTED FROM ingest/google-serpapi.py:311-343 (serpapi_search), NOT REWRITTEN.
Three things in it were learned the expensive way and are kept verbatim with
their reasons, because a rewrite that dropped any of them would look correct:

  hl=en & gl=us          Without them Google intermittently answers with
                         non-English relative timestamps ("ha 2 dias"), which
                         text.parse_relative_posted_at()'s English-only regex
                         fails on SILENTLY -- posted_at is simply lost.
  lib.http, not urlopen  D31, 2026-08-02. A 429 backs off and honours
                         Retry-After instead of losing the query for the run,
                         and the key cannot reach the logs: it travels in the
                         query string and lib/http.py:72 tags retries with
                         url.split("?")[0]. tests/test_ingest_retry.py asserts
                         that over a real retry.
  errors arrive as 200   SerpApi reports a bad key, an exhausted plan and an
                         empty result set all as HTTP 200 with an `error` key,
                         so no status code sees them. They are NOT handed to
                         lib.http's body_is_transient: most are permanent and
                         retrying them burns wall-clock on a metered account.

WHAT IS NEW HERE, AND IT IS THE REASON THIS IS NOT A PURE MOVE
    That `error` key was one RuntimeError for every case. Three of them are
    genuinely different and the caller can only act on them if they arrive
    differently -- see serp/__init__.py's three failure classes. "Google
    hasn't returned any results" in particular is a SUCCESSFUL search that
    found nothing: raising on it made a quiet query indistinguishable from a
    broken one, and both spend the credit.
"""

import json
import os
import sys
import urllib.error

sys.path.insert(0, os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.abspath(__file__)))))

from lib import http  # noqa: E402

NAME = "serpapi"

#: One call, one search, whatever the result count. Contrast apify.py, whose
#: allowance is denominated in results -- the reason SerpResult carries the
#: unit rather than a bare number.
UNIT = "searches"

ENDPOINT = "https://serpapi.com/search.json"
ACCOUNT_ENDPOINT = "https://serpapi.com/account"

#: This ingest's own agent string, unchanged from ingest/google-serpapi.py so
#: that anything SerpApi-side keyed on it keeps working.
USER_AGENT = "hermes-jobs-ingest/1.0"

#: A 200 whose `error` is about the ACCOUNT, not the query. Matched as
#: lowercase substrings because the wording is the vendor's and has changed
#: before; the check is deliberately loose in the direction of raising, since
#: the cost of stopping a night that could have run is one night and the cost
#: of continuing against a dead key is every query in the bank reporting zero.
ACCOUNT_ERROR_MARKERS = (
    "invalid api key",
    "run out of searches",
    "ran out of searches",
    "no searches left",
    "account is not active",
    "exceeded your",
)

#: A 200 whose `error` means "this search found nothing", which is an ANSWER.
#: SerpApi has used both spellings; both are the empty case and neither is a
#: failure.
EMPTY_ERROR_MARKERS = (
    "hasn't returned any results",
    "has not returned any results",
    "no results found",
)

#: What lib.http re-raises once its backoff is exhausted, plus what never
#: reached it. Named here so serp/__init__.py's Deferred class has one
#: definition of "the endpoint did not answer" per provider rather than a
#: tuple copied into every caller -- the shape ingest/google-serpapi.py:385
#: had to spell out inline.
DEFERRING_EXCEPTIONS = (urllib.error.URLError, TimeoutError, ConnectionError,
                        http.TransientBody, json.JSONDecodeError)


class AccountRefused(Exception):
    """Bad key or exhausted plan -- serp/__init__.py maps this to ProviderRefused."""


def build_url(query, location, *, date_chip=None, api_key=None):
    """The request URL. Separate from fetch() so a test can read it without
    a network, and so the key's presence in the query string is visible in one
    place rather than assumed."""
    params = {
        "engine": "google_jobs",
        "q": query,
        "location": location,
        "hl": "en",   # locale pinned -- see the module docstring; without these
        "gl": "us",   # posted_at is silently lost on non-English answers
        "api_key": api_key,
    }
    if date_chip:
        params["chips"] = f"date_posted:{date_chip}"
    return ENDPOINT + "?" + http.urlencode(params)


def fetch(query, location, creds, *, date_chip=None):
    """One search. Returns SerpApi's `jobs_results` list, untouched.

    `creds` is the API key. Passed in rather than read from the environment
    here so that tests/test_secrets_rotation.py's property stays mechanical --
    no credential is read from anywhere but the process environment, and this
    module is not where that read happens.
    """
    if not creds:
        raise AccountRefused("SERPAPI_API_KEY is not set")
    data = http.get_json(build_url(query, location, date_chip=date_chip,
                                   api_key=creds),
                         headers={"User-Agent": USER_AGENT})
    error = data.get("error")
    if error:
        low = str(error).lower()
        if any(m in low for m in EMPTY_ERROR_MARKERS):
            return []                       # a search that found nothing
        if any(m in low for m in ACCOUNT_ERROR_MARKERS):
            raise AccountRefused(str(error))
        raise RuntimeError(str(error))      # spent, and unusable for this query
    return data.get("jobs_results", [])


def credits_for(raw):
    """One search per call, regardless of how many results came back."""
    return 1


def account(creds):
    """SerpApi's OWN counter. The instrument serp/quota.reconcile() reads.

    Returns the fields this repo needs, named as this repo names them, because
    the vendor's own key names are its to change:

        used       searches consumed this billing period
        left       searches remaining
        allowance  the plan's total, when it can be derived

    WHY THIS EXISTS AT ALL. DECISIONS.md, "EXP -- The repo's own SerpApi ledger
    undercounts real spend by 3.3x": google_jobs_query_stats implied 41 searches
    used and the account itself read 137. A ledger that counts rows this
    pipeline remembered to write is not a ledger, it is a memory of intentions,
    and its first symptom is a month that goes dark early with no error
    anywhere.
    """
    if not creds:
        raise AccountRefused("SERPAPI_API_KEY is not set")
    data = http.get_json(f"{ACCOUNT_ENDPOINT}?api_key=" + creds,
                         headers={"User-Agent": USER_AGENT})
    used = data.get("this_month_usage")
    left = data.get("total_searches_left")
    if left is None:
        left = data.get("plan_searches_left")
    allowance = data.get("searches_per_month")
    if allowance is None and used is not None and left is not None:
        allowance = used + left
    return {"used": used, "left": left, "allowance": allowance, "raw": data}

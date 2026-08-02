"""Apify's google-jobs-scraper actor. Billed per RESULT, out of a dollar balance.

LIFTED FROM ingest/google-apify.py:165-200 (run_actor_query), including D17's
fix and the comment that explains it: `run` must be bound before the poll loop,
because a run that comes back SUCCEEDED immediately never enters the loop -- the
actor is billed, the dataset exists, and the caller used to get an
UnboundLocalError instead of the rows. That was "the cheapest confirmed bug in
the repo" and it had been waiting on two lines.

THE TWO WAYS THIS ADAPTER IS NOT SERPAPI, AND BOTH ARE RECORDED RATHER THAN
SMOOTHED OVER:

  IT CANNOT TAKE A DATE CHIP. The actor's input schema has query, location,
  country, num_results and max_pagination, and no equivalent of Google's
  `chips=date_posted:X`. So the whole DATE FILTER design in
  ingest/google-serpapi.py -- narrow each run to the window since that query
  last ran -- does not apply here, and an Apify run re-fetches the same
  top-ranked results a relevance-ranked page returns every time.
  SUPPORTS_DATE_CHIP says so as data, because an adapter that accepted the
  argument and dropped it would be indistinguishable from one that used it,
  and this repo's failure mode is silence.

  ITS UNIT IS RESULTS AND ITS ACCOUNT IS DOLLARS. serp/quota.py can therefore
  count what this adapter spends but cannot reconcile it against the vendor
  the way it reconciles SerpApi -- the conversion needs a per-result price that
  is a property of the actor and of the plan. RECONCILABLE = False states that,
  and it is the same gap D37 records from the other end ("no reconciliation
  against Apify's own billing exists").
"""

import json
import os
import sys
import time
import urllib.error

sys.path.insert(0, os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.abspath(__file__)))))

from lib import http  # noqa: E402

NAME = "apify"

#: Pay-per-result: ten results cost ten times one. This is why ORDER puts it
#: second and why APIFY_RESULTS_PER_QUERY is explicit on every call -- the
#: COST DISCIPLINE section of ingest/google-apify.py records that omitting
#: num_results/max_pagination is how an unbounded run happens.
UNIT = "results"

ACTOR_ID = "johnvc~google-jobs-scraper---pay-per-result"
RESULTS_PER_QUERY = 10
RUN_TIMEOUT_SECS = 150
POLL_INTERVAL_SECS = 5

#: See the module docstring. Read by anything that wants to know whether a
#: query's date window survived the routing.
SUPPORTS_DATE_CHIP = False

#: serp/quota.py checks this before promising a reconciliation it cannot do.
RECONCILABLE = False

DEFERRING_EXCEPTIONS = (urllib.error.URLError, TimeoutError, ConnectionError,
                        http.TransientBody, json.JSONDecodeError)


class AccountRefused(Exception):
    """No token, or Apify refused the account -- mapped to ProviderRefused."""


def fetch(query, location, creds, *, date_chip=None):
    """Start an actor run, poll it, return the dataset items untouched.

    `date_chip` is accepted and NOT used -- see SUPPORTS_DATE_CHIP and the
    module docstring. It is in the signature because serp.call() has one
    calling convention for every adapter; dropping it from the signature would
    move the discrepancy to a place where nobody reads it.
    """
    if not creds:
        raise AccountRefused("APIFY_API_TOKEN is not set")
    start = http.post_json(
        f"https://api.apify.com/v2/acts/{ACTOR_ID}/runs?token={creds}",
        {
            "query": query,
            "location": location,
            "country": "us",
            "num_results": RESULTS_PER_QUERY,
            "max_pagination": max(1, RESULTS_PER_QUERY // 10),
        },
    )
    run_id = start["data"]["id"]

    # D17. `run` is bound HERE, not in the loop: an already-SUCCEEDED run never
    # enters the loop, and the start response carries the same `data` shape,
    # defaultDatasetId included, so it is the answer rather than a placeholder.
    run = start
    elapsed = 0
    status = start["data"]["status"]
    while status in ("READY", "RUNNING") and elapsed < RUN_TIMEOUT_SECS:
        time.sleep(POLL_INTERVAL_SECS)
        elapsed += POLL_INTERVAL_SECS
        run = http.get_json(
            f"https://api.apify.com/v2/actor-runs/{run_id}?token={creds}")
        status = run["data"]["status"]

    if status != "SUCCEEDED":
        # D37: the actor keeps running and keeps billing, and the run id lives
        # only in this message. Won't-fix on the stakes (<=$0.15/query), and
        # the id is in the string so an operator can find it.
        raise RuntimeError(
            f"actor run {run_id} ended with status={status} after {elapsed}s")

    dataset_id = run["data"]["defaultDatasetId"]
    return http.get_json(
        f"https://api.apify.com/v2/datasets/{dataset_id}/items?token={creds}")


def credits_for(raw):
    """Pay-per-result: what this call cost is how many results it returned."""
    return len(raw)


def account(creds):
    """Apify's own usage counter, in DOLLARS -- deliberately not converted.

    Returned in this repo's field names with `used`/`left`/`allowance` all in
    USD and the unit stated, so a caller cannot mistake it for the `results`
    this adapter spends. serp/quota.py refuses to reconcile against it for that
    reason rather than inventing a per-result price.
    """
    if not creds:
        raise AccountRefused("APIFY_API_TOKEN is not set")
    data = http.get_json(f"https://api.apify.com/v2/users/me/limits?token={creds}")
    payload = data.get("data") or {}
    current = payload.get("current") or {}
    limits = payload.get("limits") or {}
    used = current.get("monthlyUsageUsd")
    allowance = limits.get("maxMonthlyUsageUsd")
    left = None
    if used is not None and allowance is not None:
        left = allowance - used
    return {"used": used, "left": left, "allowance": allowance,
            "unit": "usd", "raw": data}

#!/usr/bin/env python3
"""Does `chips=date_posted:` still filter anything? Costs ~3 SerpApi credits.

WHY THIS EXISTS: ingest/google-serpapi.py's entire catch-up mechanism rests on
choose_date_chip() -- a query that hasn't run in 5 days asks for
`chips=date_posted:week` and trusts Google to return only that window. But
SerpApi's own Google Jobs docs now mark BOTH `chips` and `ltype` as
"deprecated by Google", with `uds` as the successor. If `chips` has quietly
become a no-op, every "catch-up" run is paying a credit to re-fetch the same
relevance-ranked page it already has, and the widening today->3days->week->month
ladder is decoration.

That is not a question to answer by reading docs -- SerpApi's own blog still
documents the chips values as current while the API reference calls them
deprecated. Three credits settles it.

WHAT IT DOES: runs one query three ways -- unfiltered, `date_posted:today`,
`date_posted:month` -- and compares the returned posting sets.

  * no_cache=true on every call. SerpApi serves identical searches from a 1h
    cache for free, and a cached response would make two different requests
    look identical for reasons that have nothing to do with filtering. Paying
    for three fresh fetches is the entire point of the test.

  * Comparison is on `htidocid` (decoded out of the job_id blob), NOT on the
    raw job_id. The raw blob embeds a volatile per-search `fc` token that
    rotates on every fresh fetch, so raw ids NEVER match across calls and
    every set would look disjoint. This is the same bug the ingest pipeline
    has been storing rows under; see pipelib.ids.decode_google_job_id.

THE VERDICT IS READ OFF posted_at, NOT OFF SET OVERLAP. The first version of
this script asked whether today ⊆ month ⊆ unfiltered and reported
"INCONCLUSIVE" when they didn't nest -- but a page is 10 results out of a pool
of thousands, ranked by relevance, so three calls sample three different
slices and the sets never nest even when the filter works perfectly. The
question that actually has a clean answer is "how old is the OLDEST posting
each variant returned":

    today  -> nothing older than ~24h   |  month -> nothing older than ~31d
        the filter works. Keep choose_date_chip() as is.
    every variant spans the same wide age range
        -> the filter is dead. choose_date_chip() is burning credits for
           nothing and must move to `uds`, read from the `filters` array of an
           unfiltered response rather than hardcoded. Note serpapi/public-roadmap#2280:
           `uds` is dropped when combined with next_page_token, so paginated
           pages are always unfiltered.

RESULT ON 2026-07-25: chips WORKS. date_posted:today returned 10/10 postings
under 24h (8h-23h) while the unfiltered top-10 for the same query contained
17-day-old listings; date_posted:month capped at 28 days. Deprecated in the
docs, still functional in practice.

USAGE:
    SERPAPI_API_KEY=... python3 jobs/tools/verify-date-filter.py
    python3 jobs/tools/verify-date-filter.py --query "LLM engineer" --location "New York, NY"
    python3 jobs/tools/verify-date-filter.py --dry-run    # print the plan, spend nothing
"""

import argparse
import base64
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter

SERPAPI_API_KEY = os.environ.get("SERPAPI_API_KEY")
ENDPOINT = "https://serpapi.com/search.json"
TIMEOUT = 30


def decode_job_id(job_id):
    """The base64 JSON blob Google hands back as `job_id`, as a dict.

    Padding is restored explicitly: Google strips '=' padding, and
    b64decode raises binascii.Error on unpadded input rather than coping.
    """
    if not job_id:
        return None
    try:
        padded = job_id + "=" * (-len(job_id) % 4)
        return json.loads(base64.b64decode(padded))
    except Exception:
        return None


def stable_key(job):
    """htidocid if the blob yields one, else a readable fallback label."""
    decoded = decode_job_id(job.get("job_id"))
    if decoded and decoded.get("htidocid"):
        return decoded["htidocid"]
    return f"?{job.get('company_name')}|{job.get('title')}"


def search(query, location, date_chip=None, api_key=None):
    params = {
        "engine": "google_jobs",
        "q": query,
        "location": location,
        "hl": "en",
        "gl": "us",
        # The whole test is "do two DIFFERENT requests return the same thing".
        # A cached hit would answer that question with "yes" for the wrong
        # reason. Also makes each call actually cost a credit, as intended.
        "no_cache": "true",
        "api_key": api_key,
    }
    if date_chip:
        params["chips"] = f"date_posted:{date_chip}"
    url = f"{ENDPOINT}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url, headers={"User-Agent": "hermes-jobs-verify/1.0"})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
        data = json.loads(resp.read().decode())
    if "error" in data:
        raise RuntimeError(data["error"])
    return data


#: "9 hours ago" -> 9, "4 days ago" -> 96. None for anything without an exact
#: anchor ("30+ days ago"), which must not be counted as an age.
_UNIT_HOURS = {"minute": 1 / 60, "hour": 1, "day": 24, "week": 168, "month": 720}


def age_hours(posted_at):
    if not posted_at:
        return None
    parts = posted_at.split()
    if len(parts) < 2 or not parts[0].isdigit():
        return None
    for unit, mult in _UNIT_HOURS.items():
        if parts[1].rstrip("s") == unit:
            return int(parts[0]) * mult
    return None


def summarize(label, data):
    jobs = data.get("jobs_results", [])
    keys = [stable_key(j) for j in jobs]
    raw = [(j.get("detected_extensions") or {}).get("posted_at") or "(none)"
           for j in jobs]
    ages = [h for h in (age_hours(p) for p in raw) if h is not None]
    echoed = data.get("search_parameters", {})
    print(f"\n--- {label}")
    print(f"    results: {len(jobs)}   distinct htidocid: {len(set(keys))}")
    print(f"    chips echoed back by SerpApi: {echoed.get('chips', '(absent)')}")
    print(f"    posted_at: {dict(Counter(raw))}")
    if ages:
        print(f"    age range: {min(ages):.0f}h .. {max(ages):.0f}h "
              f"({max(ages) / 24:.1f} days), {len(ages)}/{len(jobs)} parseable")
    return set(keys), ages


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--query", default="backend engineer")
    ap.add_argument("--location", default="New York, NY")
    ap.add_argument("--dry-run", action="store_true",
                    help="print what would be requested, spend no credits")
    args = ap.parse_args()

    variants = [("unfiltered", None), ("date_posted:today", "today"),
                ("date_posted:month", "month")]

    if args.dry_run:
        print(f"would run {len(variants)} searches (~{len(variants)} credits), "
              f"q={args.query!r} location={args.location!r}, no_cache=true:")
        for label, chip in variants:
            print(f"  - {label}")
        return 0

    if not SERPAPI_API_KEY:
        print("FAILED: SERPAPI_API_KEY not set (it lives in ~/.hermes/.env).",
              file=sys.stderr)
        return 1

    print(f"query={args.query!r} location={args.location!r}  "
          f"({len(variants)} fresh searches, no_cache=true)")

    sets, ages = {}, {}
    for label, chip in variants:
        try:
            data = search(args.query, args.location, chip, SERPAPI_API_KEY)
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError,
                json.JSONDecodeError, RuntimeError, OSError) as e:
            print(f"\nFAILED on {label}: {e}", file=sys.stderr)
            return 1
        sets[label], ages[label] = summarize(label, data)

    print("\n=== verdict")
    # Set overlap is reported but NOT used to decide -- see the module
    # docstring. Three 10-result samples of a large relevance-ranked pool do
    # not nest even when the filter is working.
    print(f"  (fyi) distinct postings across all three variants: "
          f"{len(set().union(*sets.values()))} of "
          f"{sum(len(s) for s in sets.values())} returned")

    # A chip that filters imposes a ceiling on age. That ceiling is the signal.
    # Slack on the bounds: Google rounds ("1 day ago" for a 25h posting) and
    # 'month' is a calendar-ish month rather than exactly 720h.
    today_ok = bool(ages["date_posted:today"]) and max(ages["date_posted:today"]) <= 26
    month_ok = bool(ages["date_posted:month"]) and max(ages["date_posted:month"]) <= 745
    unfiltered_max = max(ages["unfiltered"]) if ages["unfiltered"] else 0

    for label in ("unfiltered", "date_posted:today", "date_posted:month"):
        a = ages[label]
        oldest = f"{max(a) / 24:6.1f} days" if a else "  (none parseable)"
        print(f"  oldest returned by {label:20} {oldest}")

    if today_ok and month_ok and unfiltered_max > 26:
        print("\n  chips still FILTERS -- 'today' returned nothing older than "
              "a day while the unfiltered\n  page for the same query did. "
              "Keep choose_date_chip() as is.")
    elif not today_ok and unfiltered_max > 26:
        print("\n  chips appears to be a NO-OP: 'date_posted:today' returned "
              "postings older than a day.\n  choose_date_chip() is spending "
              "credits to re-fetch the same page.\n  -> move to `uds`, sourced "
              "from the `filters` array of an unfiltered response.")
    else:
        print("\n  INCONCLUSIVE -- the unfiltered page happened to contain only "
              "recent postings, so there\n  was no age ceiling to detect. "
              "Re-run against a broader query (--query 'software engineer').")
    return 0


if __name__ == "__main__":
    sys.exit(main())

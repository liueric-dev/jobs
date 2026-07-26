#!/usr/bin/env python3
"""
Contributor worker -- the script you run on YOUR machine to help collect job
postings.

WHAT IT DOES: asks the coordinating server which searches still need running,
runs them against Google Jobs using YOUR OWN SerpApi account, and sends the
raw results back. You never get or need database access; the server does all
the storing.

WHAT IT COSTS YOU: one SerpApi search credit per query it runs. SerpApi's free
tier is 250 searches/month. The server won't hand you more than your
configured per-run maximum, and it won't hand out a query that someone else
already ran recently, so credits don't get spent re-fetching the same thing.

DEPENDENCIES: none -- Python 3 standard library only. No database driver, no
pip install. That's deliberate, so this runs on any machine with Python.

SETUP:
    export JOBS_API_BASE_URL=https://<the server's address>
    export JOBS_API_KEY=<the key you were given>
    export SERPAPI_API_KEY=<your own SerpApi key from serpapi.com>

RUN:
    python3 google-serpapi-worker.py
    MAX_QUERIES=3 python3 google-serpapi-worker.py     # take more per run
    DEBUG=1 python3 google-serpapi-worker.py           # verbose

SCHEDULE (optional) -- once a day is plenty:
    crontab -e
    0 9 * * * cd /path/to/this/dir && /usr/bin/python3 google-serpapi-worker.py

IF A SEARCH FAILS: the script tells the server to release that query so
somebody else can pick it up right away, rather than leaving it locked. That
also means a failed run costs you nothing but the credit SerpApi already
charged.
"""

import os
import sys
import json
import urllib.parse
import urllib.request
import urllib.error

JOBS_API_BASE_URL = os.environ.get("JOBS_API_BASE_URL", "").rstrip("/")
JOBS_API_KEY = os.environ.get("JOBS_API_KEY", "")
SERPAPI_API_KEY = os.environ.get("SERPAPI_API_KEY", "")
MAX_QUERIES = int(os.environ.get("MAX_QUERIES", "1"))
HTTP_TIMEOUT = int(os.environ.get("HTTP_TIMEOUT", "45"))
DEBUG = os.environ.get("DEBUG", "") == "1"


def log(msg):
    if DEBUG:
        print(f"[debug] {msg}", file=sys.stderr)


def api_post(path, body):
    data = json.dumps(body).encode()
    req = urllib.request.Request(
        f"{JOBS_API_BASE_URL}{path}",
        data=data,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {JOBS_API_KEY}",
            "User-Agent": "jobs-contributor-worker/1.0",
        },
    )
    with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT) as resp:
        return json.loads(resp.read().decode())


def serpapi_search(query, location, date_chip):
    """Call SerpApi with the contributor's own key.

    hl=en&gl=us are pinned because without them Google intermittently returns
    non-English relative timestamps ("há 2 dias"), which the server's parser
    reads as "no date" and silently drops.
    """
    params = {
        "engine": "google_jobs",
        "q": query,
        "location": location,
        "hl": "en",
        "gl": "us",
        "api_key": SERPAPI_API_KEY,
    }
    if date_chip:
        params["chips"] = f"date_posted:{date_chip}"
    url = "https://serpapi.com/search.json?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"User-Agent": "jobs-contributor-worker/1.0"})
    with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT) as resp:
        data = json.loads(resp.read().decode())
    if "error" in data:
        raise RuntimeError(data["error"])
    return data.get("jobs_results", [])


def main():
    missing = [n for n, v in (
        ("JOBS_API_BASE_URL", JOBS_API_BASE_URL),
        ("JOBS_API_KEY", JOBS_API_KEY),
        ("SERPAPI_API_KEY", SERPAPI_API_KEY),
    ) if not v]
    if missing:
        print(f"worker FAILED: set {', '.join(missing)} (see this file's header)")
        sys.exit(1)

    try:
        claimed = api_post("/v1/queries/claim", {"max": MAX_QUERIES})
    except urllib.error.HTTPError as e:
        detail = e.read().decode()[:300]
        print(f"worker FAILED: could not claim queries (HTTP {e.code}): {detail}")
        sys.exit(1)
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError) as e:
        print(f"worker FAILED: could not reach {JOBS_API_BASE_URL}: {e}")
        sys.exit(1)

    queries = claimed.get("queries", [])
    if not queries:
        # Not an error: it means everything is already up to date. Exiting 0
        # keeps cron quiet on the (common) days there's nothing to do.
        print("worker: nothing to do -- no stale queries available right now.")
        return

    submitted = failed = 0
    for q in queries:
        dataset = q["dataset"]
        log(f"claimed {dataset} ({q['query']!r} @ {q['location']}, chip={q.get('date_chip')})")
        try:
            results = serpapi_search(q["query"], q["location"], q.get("date_chip"))
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError,
                json.JSONDecodeError, RuntimeError, OSError) as e:
            print(f"worker: search failed for {q['slug']}: {e}", file=sys.stderr)
            try:
                api_post(f"/v1/queries/{urllib.parse.quote(dataset)}/release",
                         {"reason": str(e)[:200]})
                log(f"released {dataset}")
            except Exception as release_err:
                # The claim will expire on its own; not worth failing over.
                log(f"could not release {dataset}: {release_err}")
            failed += 1
            continue

        try:
            resp = api_post(f"/v1/queries/{urllib.parse.quote(dataset)}/submit",
                            {"jobs": results})
            submitted += 1
            log(f"submitted {len(results)} results for {q['slug']}: {resp}")
        except urllib.error.HTTPError as e:
            print(f"worker: submit failed for {q['slug']} (HTTP {e.code}): "
                  f"{e.read().decode()[:200]}", file=sys.stderr)
            failed += 1
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError) as e:
            print(f"worker: submit failed for {q['slug']}: {e}", file=sys.stderr)
            failed += 1

    print(f"worker: {submitted} submitted, {failed} failed, {len(queries)} claimed.")
    if failed and not submitted:
        sys.exit(1)


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
Google Jobs ingest via Apify (johnvc/google-jobs-scraper---pay-per-result)
-- Postgres edition. Supplements ingest/google-serpapi.py, drawing
from the SAME query bank and the SAME least-recently-run scheduler state,
so the two scripts never redo each other's work on the same day (see that
script's module docstring for the full scheduling rationale).

BUCKET SCOPE -- NARROWER THAN THE SERPAPI SCRIPT, DELIBERATELY: this actor
has no date-filter parameter (confirmed by inspecting its full input
schema 2026-07-24 -- no date_posted/recency field exists), so unlike
SerpApi's script it can't narrow to "what's new since last run". Given
that limitation AND that Apify is by far the scarcer/more expensive
resource (APIFY_DAILY_QUERY_BUDGET=1 vs SerpApi's 8), its single daily
slot is drawn ONLY from the ai_integration and bridge_solutions buckets in
config/google-queries.json -- the two highest-priority buckets for this
candidate's actual positioning -- rather than the full bank. core_swe and
reentry_growth get zero Apify coverage; they're already served adequately
by SerpApi's own per-bucket budget.

WHY THIS SPECIFIC ACTOR, NOT A CHEAPER ONE: verified live (2026-07-24) --
the obvious cheap choice (khadinakbar/google-jobs-scraper, $0.003/result,
Playwright-driven browser automation) got CAPTCHA-blocked by Google twice
in a row in real testing (google.com/sorry/index, zero results delivered,
real spend charged anyway). johnvc's actor uses a different scraping
approach and returned clean, correct results in the same test session --
literally identical job_id values to SerpApi's own output for the same
posting, meaning it's hitting equivalent underlying data through a path
that isn't (yet) blocked. It costs 5x more per result ($0.015 vs $0.003 on
the free tier) but a working expensive result beats a free one that
doesn't exist.

COST DISCIPLINE -- LEARNED THE HARD WAY: this actor's `num_results`
defaults to 100 and `max_pagination` defaults to 0 (unlimited) if left
unset. A single test call without explicit limits cost $1.50 -- 30% of
Apify's entire $5/month free-tier credit in one shot. Every call this
script makes sets num_results and max_pagination EXPLICITLY (see
APIFY_RESULTS_PER_QUERY below) -- never rely on this actor's defaults.

BUDGET: at $0.015/result (free-tier pricing) and APIFY_RESULTS_PER_QUERY=10,
one query/day costs ~$0.15/day (~$4.50/month), fitting inside the $5/month
free credit with a small buffer -- hence APIFY_DAILY_QUERY_BUDGET=1. This
is intentionally conservative given free-tier pricing is the worst tier;
if the Apify plan is ever upgraded, raise APIFY_DAILY_QUERY_BUDGET and/or
APIFY_RESULTS_PER_QUERY directly -- no other code change needed.

DEPENDENCY: psycopg (same as ingest/ats.py). No Apify SDK -- plain HTTPS
via the Apify REST API (start run, poll status, fetch dataset items).

INSTALL: lives in ~/.hermes/scripts/jobs/ alongside config/google-queries.json

DATABASE: same Postgres instance/schema as ingest/ats.py (jobs.jobs table
+ job_ingest_state). Creates schema defensively, works standalone.

CONFIG:
    DATABASE_URL              -- postgres connection string
    APIFY_API_TOKEN            -- required, no fallback default (billing-
                                  linked secret, stored in ~/.hermes/.env)
    GOOGLE_JOBS_QUERIES_FILE   -- path to config/google-queries.json

SCHEDULE: not scheduled directly -- see run-daily.py. Runs AFTER
ingest/google-serpapi.py so its least-recently-run picks are already
disjoint from whatever SerpApi covered today.

TEST BEFORE SCHEDULING:
    python3 ingest/google-apify.py
    DEBUG_PRINT_KEYS=1 python3 ingest/google-apify.py

CLOSE SEMANTICS: staleness-based (not exact-diff), same reasoning as
ingest/google-serpapi.py and ingest/builtin-nyc.py.
"""

import os
import sys
import re
import json
import time
import html as html_module
import urllib.request
import urllib.error
from datetime import datetime, timedelta, timezone


_d = os.path.dirname(os.path.abspath(__file__))
while _d != os.path.dirname(_d) and not os.path.isdir(os.path.join(_d, "pipelib")):
    _d = os.path.dirname(_d)
sys.path.insert(0, _d)
sys.path.insert(0, os.path.join(_d, "jobs"))

import schema  # noqa: E402  (jobs/schema.py)
from pipelib import dbconn, http, ids, state, text  # noqa: E402
from pipelib.timeparse import utc_now_str  # noqa: E402
from pipelib.upsert import upsert  # noqa: E402

APIFY_API_TOKEN = os.environ.get("APIFY_API_TOKEN")
GOOGLE_JOBS_QUERIES_FILE = os.environ.get(
    "GOOGLE_JOBS_QUERIES_FILE",
    os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "config", "google-queries.json"),
)
DEBUG_PRINT_KEYS = os.environ.get("DEBUG_PRINT_KEYS", "") == "1"

ACTOR_ID = "johnvc~google-jobs-scraper---pay-per-result"
APIFY_DAILY_QUERY_BUDGET = 1     # see BUDGET note above -- free-tier pricing is conservative
APIFY_RESULTS_PER_QUERY = 10     # explicit -- NEVER omit num_results/max_pagination (see COST DISCIPLINE)
APIFY_RUN_TIMEOUT_SECS = 150
APIFY_POLL_INTERVAL_SECS = 5
GOOGLE_JOBS_STALE_AFTER_DAYS = 30
# Same guard as ingest/google-serpapi.py (see the comment there): don't
# re-claim a query that already succeeded within this window, so multiple
# machines running run-daily.py on the same day don't burn paid Apify
# results re-fetching what the first run already covered.
MIN_HOURS_BETWEEN_RUNS = float(os.environ.get("GOOGLE_JOBS_MIN_HOURS_BETWEEN_RUNS", "20"))


def log_query_stats(conn, slug, new_count, total_fetched, days_since_last_run):
    conn.execute(
        """
        INSERT INTO google_jobs_query_stats (slug, run_at, new_count, total_fetched, days_since_last_run)
        VALUES (%s, %s, %s, %s, %s)
        """,
        (slug, utc_now_str(), new_count, total_fetched, days_since_last_run),
    )
    conn.commit()


PRIORITY_BUCKETS = ("ai_integration", "bridge_solutions")  # see BUCKET SCOPE in module docstring


def load_priority_queries():
    with open(GOOGLE_JOBS_QUERIES_FILE) as f:
        buckets = json.load(f)["buckets"]
    queries = []
    for name in PRIORITY_BUCKETS:
        queries.extend(buckets[name]["queries"])
    return queries


def pick_stale_queries(conn, all_queries, n):
    """Least-recently-run scheduling over PRIORITY_BUCKETS only (see module
    docstring), claim-safe against both other Apify runs AND any SerpApi
    machines (same shared job_ingest_state table/dataset keys, same claim
    scheme -- see ingest/google-serpapi.py's module docstring)."""
    now_dt = datetime.now(timezone.utc)
    too_recent_cutoff = (now_dt - timedelta(hours=MIN_HOURS_BETWEEN_RUNS)).strftime("%Y-%m-%dT%H:%M:%S")
    slugs = [q["slug"] for q in all_queries]
    rows = conn.execute(
        "SELECT dataset, last_success_at FROM job_ingest_state WHERE dataset = ANY(%s)",
        ([f"google_jobs:query:{s}" for s in slugs],),
    ).fetchall()
    watermarks = {d.replace("google_jobs:query:", ""): ts for d, ts in rows}
    ordered = sorted(all_queries, key=lambda q: watermarks.get(q["slug"], ""))

    picked = []
    for q in ordered:
        if len(picked) >= n:
            break
        if watermarks.get(q["slug"], "") > too_recent_cutoff:
            break  # stalest-first: everything remaining ran even more recently
        dataset = f"google_jobs:query:{q['slug']}"
        if state.try_claim(conn, dataset, table=schema.WATERMARK_TABLE):
            picked.append((q, watermarks.get(q["slug"])))
    return picked


def run_actor_query(query, location):
    """Start an actor run, poll to completion, fetch dataset items. Explicit
    num_results/max_pagination on every call -- see COST DISCIPLINE above."""
    start = http.post_json(
        f"https://api.apify.com/v2/acts/{ACTOR_ID}/runs?token={APIFY_API_TOKEN}",
        {
            "query": query,
            "location": location,
            "country": "us",
            "num_results": APIFY_RESULTS_PER_QUERY,
            "max_pagination": max(1, APIFY_RESULTS_PER_QUERY // 10),
        },
    )
    run_id = start["data"]["id"]

    elapsed = 0
    status = start["data"]["status"]
    while status in ("READY", "RUNNING") and elapsed < APIFY_RUN_TIMEOUT_SECS:
        time.sleep(APIFY_POLL_INTERVAL_SECS)
        elapsed += APIFY_POLL_INTERVAL_SECS
        run = http.get_json(f"https://api.apify.com/v2/actor-runs/{run_id}?token={APIFY_API_TOKEN}")
        status = run["data"]["status"]

    if status != "SUCCEEDED":
        raise RuntimeError(f"actor run {run_id} ended with status={status} after {elapsed}s")

    dataset_id = run["data"]["defaultDatasetId"]
    return http.get_json(f"https://api.apify.com/v2/datasets/{dataset_id}/items?token={APIFY_API_TOKEN}")


def normalize_job(job, mode):
    """Identical record shape to ingest/google-serpapi.py -- this
    actor's output schema matches SerpApi's field-for-field (confirmed live,
    same job_id for the same posting via both paths).

    That last point is why this file MUST use the same ids.google_source_id()
    the SerpApi script does: the two sources returning the same posting is
    supposed to be one row, and it only stays one row while both derive the
    key the same way. See the Google Jobs section of pipelib/ids.py.
    """
    title = job.get("title")
    company_name = job.get("company_name") or "Unknown"
    location = job.get("location")
    detected = job.get("detected_extensions") or {}
    apply_options = job.get("apply_options") or []
    company_token = text.slugify(company_name)

    is_nyc = bool(text.NYC_PATTERN.search(location or ""))
    is_remote = bool(text.REMOTE_PATTERN.search(location or "")) or mode == "remote"

    return {
        "platform": "google_jobs",
        "company_token": company_token,
        "company_name": company_name,
        "source_id": ids.google_source_id(job, company_token),
        "title": title,
        "location_raw": location,
        "department": detected.get("schedule_type"),
        "job_url": (apply_options[0].get("link") if apply_options else None) or job.get("share_link"),
        "posted_at": text.parse_relative_posted_at(detected.get("posted_at")),
        "seniority_guess": text.guess_seniority(title),
        "location_is_nyc": is_nyc,
        "location_is_remote": is_remote,
        "company_is_nyc_hq": None,
        "company_is_ai_focused": None,
        "description_text": text.strip_html(job.get("description")),
        "raw_json": json.dumps(job)[:20000],
    }


def main():
    if not APIFY_API_TOKEN:
        print("google-jobs-apify ingest FAILED: APIFY_API_TOKEN not set.")
        sys.exit(1)

    conn = dbconn.connect_or_exit("google-jobs-apify ingest", schema=schema.SCHEMA)

    schema.ensure_schema(conn)
    state.ensure_state_schema(conn, schema.WATERMARK_TABLE,
                              with_claims=True)
    job_spec = schema.spec(schema.HASH_FIELDS_SHORT)

    try:
        all_queries = load_priority_queries()
    except (OSError, json.JSONDecodeError, KeyError) as e:
        print(f"google-jobs-apify ingest FAILED: could not load {GOOGLE_JOBS_QUERIES_FILE}: {e}")
        conn.close()
        sys.exit(1)

    picked = pick_stale_queries(conn, all_queries, APIFY_DAILY_QUERY_BUDGET)

    total_new = total_updated = total_unchanged = 0
    query_errors = []
    queries_run = 0

    for q, last_run_str in picked:
        dataset = f"google_jobs:query:{q['slug']}"
        try:
            jobs = run_actor_query(q["query"], q["location"])
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError,
                json.JSONDecodeError, RuntimeError, OSError) as e:
            query_errors.append(f"{q['slug']}: {e}")
            state.release_claim(conn, dataset, table=schema.WATERMARK_TABLE)
            if DEBUG_PRINT_KEYS:
                print(f"[debug] Apify run failed for {q['slug']}: {e}", file=sys.stderr)
            continue

        records = [normalize_job(j, q["mode"]) for j in jobs]
        n, u, unc = upsert(conn, job_spec, records, schema.make_job_id, debug=DEBUG_PRINT_KEYS)
        total_new += n
        total_updated += u
        total_unchanged += unc
        queries_run += 1

        state.mark_success(conn, dataset, utc_now_str(),
                           table=schema.WATERMARK_TABLE)
        log_query_stats(conn, q["slug"], n, len(jobs), text.days_since(last_run_str))

        if DEBUG_PRINT_KEYS:
            print(f"[debug] {q['slug']} ({q['query']!r} @ {q['location']}): "
                  f"{len(jobs)} results -> {n} new, {u} updated, {unc} unchanged", file=sys.stderr)

    closed_count = schema.close_stale(conn, 'google_jobs', GOOGLE_JOBS_STALE_AFTER_DAYS)
    conn.close()

    if query_errors and queries_run == 0:
        print(f"google-jobs-apify ingest FAILED: all {len(query_errors)} queries failed. "
              f"Sample: {query_errors[:3]}")
        sys.exit(1)

    if query_errors and DEBUG_PRINT_KEYS:
        print(f"[debug] {len(query_errors)}/{len(picked)} queries failed: {query_errors}", file=sys.stderr)

    if total_new or total_updated or closed_count or query_errors:
        print(f"google-jobs-apify-ingest: {total_new} new, {total_updated} updated, "
              f"{total_unchanged} unchanged, {closed_count} closed (stale), "
              f"{queries_run}/{len(picked)} queries succeeded ({len(query_errors)} failed).")


if __name__ == "__main__":
    main()

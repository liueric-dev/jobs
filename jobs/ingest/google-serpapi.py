#!/usr/bin/env python3
"""
Google Jobs ingest via SerpApi -- Postgres edition.

Pulls Google Jobs results for a rotating subset of queries (see
config/google-queries.json) through SerpApi's `google_jobs` engine and
upserts into the same `jobs` table the other ingest scripts write to,
tagged platform='google_jobs'.

WHY SERPAPI, NOT DIY BROWSER AUTOMATION: verified directly (2026-07-24) --
Google's own anti-scraping tech ("SearchGuard", shipped Jan 2025; Google is
actively suing SerpApi over circumvention as of Dec 2025) blocks
unsophisticated automated access. A live test against an Apify actor doing
Playwright-driven browser automation against Google Jobs got CAPTCHA-walled
twice in a row (google.com/sorry/index), burning real spend for zero
results. SerpApi's own infrastructure is the thing Google is suing over
specifically because it works well enough to be worth suing -- that's the
paid value being bought here, not a convenience fee.

WHY A ROTATING, BUCKETED QUERY BANK, NOT A FIXED DAILY QUERY SET: SerpApi's
free tier is 250 searches/month (~8/day) -- nowhere near enough to run a
broad query set exhaustively every day, and re-running the SAME query
daily mostly re-fetches the same top-ranked results without a date filter
(Google's default ranking is relevance-based, not chronological). So:
config/google-queries.json holds ~32 queries split into 4 strategic buckets
(core_swe, ai_integration, bridge_solutions, reentry_growth -- weighted to
Eric's actual positioning: 5 YOE full-stack SWE, 2.5yr career break,
currently 5mo into a prompt/agent engineering program). Each bucket has
its own daily_budget (summing to 8 on the free tier), and
pick_stale_queries_by_bucket() picks that many least-recently-run queries
FROM EACH BUCKET SEPARATELY -- not globally -- so ai_integration and
bridge_solutions (the highest-priority, best-fit buckets) get
proportionally more daily coverage than reentry_growth, regardless of how
many total queries live in each bucket. This is a deliberate change from
the original flat-list design: a global least-recently-run pick would
naturally equalize coverage across all queries over time, which doesn't
respect the fact that some buckets matter more than others for this
specific candidate.

Queries still use job_ingest_state for watermarks -- the SAME
table/dataset-key scheme ingest/google-apify.py uses, keyed
`google_jobs:query:<slug>`. Since run-daily.py runs this script
before the Apify one, the Apify script naturally picks different (still-
stale) queries without any direct coordination between the two -- they
just both read/write the same watermark rows. Adding/removing queries
from a bucket needs no migration: a new query has no watermark row yet,
so it's automatically top priority within its bucket.

DATE FILTER: each query call sets `chips=date_posted:X`, where X is chosen
by choose_date_chip() based on how long it's actually been since THAT
query last ran (today/3days/week/month) -- not always "today". A query
that's never run before gets NO filter at all, which is a deliberate
backfill: the first time a query runs, grab whatever Google currently
shows (as deep as page 1 goes); every subsequent run only asks for what's
new since the last time that specific query ran. Verified live
(2026-07-24) against a competing plan that instead appended the literal
phrase "posted last 3 days" into the query TEXT rather than using this
structured `chips` parameter -- that approach partly worked by accident
(Google's relevance engine treating it as keywords) but isn't a documented,
dependable mechanism the way `chips` is.

LOCALE: hl=en&gl=us are set on every call. Found the hard way: without
them, Google intermittently returns non-English relative timestamps (e.g.
"há 2 dias" instead of "2 days ago"), which text.parse_relative_posted_at()'s
English-only regex silently fails to parse, losing posted_at for no
visible reason.

QUERY STATS: every run logs (slug, new_count, days_since_last_run) into
google_jobs_query_stats -- not yet acted on, but this is exactly the
history needed to later compute each query's natural "new postings per
day" rate and adjust its effective revisit cadence (Eric's idea: if a
query only fills a full page every ~4 days, it doesn't need daily
attention). Logging it now means that adaptive logic can be built on top
of real history later instead of starting cold.

BUDGET: each bucket's daily_budget in config/google-queries.json is a plain
constant, not derived from any API introspection -- bump these directly
if the SerpApi plan is upgraded (e.g. Developer tier, 5,000/mo, supports
~166/day total) or reduce if hitting quota errors. No other code change
is needed for a plan upgrade.

MULTI-MACHINE SAFE BY DESIGN: this script is meant to be copyable to
multiple machines, each with its OWN SerpApi account/API key (per-machine
quota multiplies the effective total budget), all pointed at the SAME
shared Postgres instance. This is safe -- not just "usually fine" -- because
picking a query and claiming it are the same atomic operation:
try_claim_query() does a single INSERT ... ON CONFLICT ... DO UPDATE ...
WHERE claimed_at IS NULL OR claimed_at < ttl_cutoff RETURNING dataset,
which only succeeds for ONE caller if two machines race on the same query
at the same instant (Postgres's row-level locking makes this a real
guarantee, not a best-effort one). A machine that loses a claim race just
moves on to the next-stalest candidate in that bucket instead of blocking
-- this is what gives automatic load-balancing across machines for free,
with no static per-machine query assignment needed.

CLAIM_TTL_MINUTES bounds how long a claim blocks other machines if the
claiming machine dies mid-fetch without ever calling mark_success() or
release_claim() -- after that window, the claim expires and the query
becomes claimable again. On an actual fetch failure (as opposed to a
crash), release_claim() clears the claim immediately rather than making
other machines wait out the full TTL -- a failure on one account (e.g.
quota exhausted) shouldn't block a different machine with its own account
from retrying right away.

NOTE ON GOOGLE-FACING RISK: none of this changes the Apify-vs-SerpApi
analysis from earlier -- running from multiple machines only changes how
many machines call SerpApi's own REST API with their own API keys. SerpApi
itself is what talks to Google, using SerpApi's infrastructure, not the
calling machine's IP/identity -- there is no "detection" surface here
analogous to the Apify browser-automation case; the client IP making the
API call to SerpApi is irrelevant to Google's bot defenses since Google
never sees it.

DEPENDENCY: psycopg (same as ingest/ats.py). No SerpApi SDK -- it's a
plain HTTPS GET returning JSON, stdlib urllib is enough.

INSTALL: lives in ~/.hermes/scripts/jobs/ alongside config/google-queries.json

DATABASE: same Postgres instance/schema as ingest/ats.py (jobs.jobs table
+ job_ingest_state). Creates schema defensively, works standalone.

CONFIG:
    DATABASE_URL              -- postgres connection string
    SERPAPI_API_KEY            -- required, no fallback default (unlike
                                  DATABASE_URL's localhost-only default --
                                  this is a billing-linked secret, stored in
                                  ~/.hermes/.env, never hardcoded here)
    GOOGLE_JOBS_QUERIES_FILE   -- path to config/google-queries.json (default:
                                  alongside this script)

SCHEDULE: not scheduled directly -- see run-daily.py.

TEST BEFORE SCHEDULING:
    python3 ingest/google-serpapi.py
    DEBUG_PRINT_KEYS=1 python3 ingest/google-serpapi.py

CLOSE SEMANTICS: staleness-based (not exact-diff), same reasoning as
ingest/builtin-nyc.py -- each query only returns Google's current top
results for that query, not an exhaustive "all open postings" list.
"""

import os
import sys
import re
import json
import html as html_module
import hashlib
import urllib.request
import urllib.parse
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

SERPAPI_API_KEY = os.environ.get("SERPAPI_API_KEY")
GOOGLE_JOBS_QUERIES_FILE = os.environ.get(
    "GOOGLE_JOBS_QUERIES_FILE",
    os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "config", "google-queries.json"),
)
DEBUG_PRINT_KEYS = os.environ.get("DEBUG_PRINT_KEYS", "") == "1"

GOOGLE_JOBS_STALE_AFTER_DAYS = 30
# Don't re-run a query that succeeded this recently. With multiple machines
# each launching run-daily.py on their own schedule, the second machine of
# the day would otherwise re-claim queries the first already ran (claims
# clear on success), re-fetching a chip=today window that's nearly all
# overlap. 20h (not 24) so a fixed daily cron time drifting a few minutes
# never skips a legitimate next-day run.
MIN_HOURS_BETWEEN_RUNS = float(os.environ.get("GOOGLE_JOBS_MIN_HOURS_BETWEEN_RUNS", "20"))


def log_query_stats(conn, slug, new_count, total_fetched, days_since_last_run):
    """Not yet acted on -- see QUERY STATS in the module docstring. Just
    building the history now so an adaptive per-query cadence can be built
    on real data later instead of starting cold."""
    conn.execute(
        """
        INSERT INTO google_jobs_query_stats (slug, run_at, new_count, total_fetched, days_since_last_run)
        VALUES (%s, %s, %s, %s, %s)
        """,
        (slug, utc_now_str(), new_count, total_fetched, days_since_last_run),
    )
    conn.commit()


def load_query_buckets():
    with open(GOOGLE_JOBS_QUERIES_FILE) as f:
        return json.load(f)["buckets"]


def pick_stale_queries_by_bucket(conn, buckets):
    """Least-recently-run scheduling, scoped PER BUCKET rather than
    globally (see module docstring for why), AND claim-safe across
    multiple machines: candidates are walked in stalest-first order,
    attempting an atomic claim on each one via try_claim_query(). A
    candidate that's already claimed by another machine (mid-fetch, right
    now) is simply skipped in favor of the next-stalest one -- this is what
    gives automatic load-balancing across machines with no static
    per-machine query assignment. Returns (query_dict, last_run_str) tuples
    -- the watermark is needed by the caller to choose a date_posted chip."""
    picked = []
    now_dt = datetime.now(timezone.utc)
    too_recent_cutoff = (now_dt - timedelta(hours=MIN_HOURS_BETWEEN_RUNS)).strftime("%Y-%m-%dT%H:%M:%S")
    for bucket in buckets.values():
        queries = bucket["queries"]
        budget = bucket["daily_budget"]
        slugs = [q["slug"] for q in queries]
        rows = conn.execute(
            "SELECT dataset, last_success_at FROM job_ingest_state WHERE dataset = ANY(%s)",
            ([f"google_jobs:query:{s}" for s in slugs],),
        ).fetchall()
        watermarks = {d.replace("google_jobs:query:", ""): ts for d, ts in rows}
        ordered = sorted(queries, key=lambda q: watermarks.get(q["slug"], ""))

        claimed_in_bucket = 0
        for q in ordered:
            if claimed_in_bucket >= budget:
                break
            if watermarks.get(q["slug"], "") > too_recent_cutoff:
                # Stalest-first order means every remaining candidate in this
                # bucket ran even more recently -- the bucket's real work for
                # this interval is already done (by us or another machine).
                # Spending the rest of the budget here would just re-fetch a
                # window another run already covered.
                break
            dataset = f"google_jobs:query:{q['slug']}"
            if state.try_claim(conn, dataset, table=schema.WATERMARK_TABLE):
                picked.append((q, watermarks.get(q["slug"])))
                claimed_in_bucket += 1
            # else: another machine already holds this claim -- try the next-stalest candidate
    return picked


def choose_date_chip(last_run_str):
    """None (query has never run before) -> no chip at all -- this is the
    deliberate backfill case, grab whatever Google currently shows. Every
    subsequent run narrows to the chip bucket that covers the actual gap
    since that query's last run, not always "today" -- see DATE FILTER in
    the module docstring."""
    if not last_run_str:
        return None
    try:
        last_run = datetime.strptime(last_run_str, "%Y-%m-%dT%H:%M:%S").replace(tzinfo=timezone.utc)
    except ValueError:
        return None
    elapsed = datetime.now(timezone.utc) - last_run
    if elapsed <= timedelta(days=1):
        return "today"
    if elapsed <= timedelta(days=3):
        return "3days"
    if elapsed <= timedelta(days=7):
        return "week"
    return "month"


def serpapi_search(query, location, date_chip=None):
    params = {
        "engine": "google_jobs",
        "q": query,
        "location": location,
        "hl": "en",  # locale pinned -- without this Google intermittently returns
        "gl": "us",  # non-English relative timestamps, e.g. "há 2 dias" instead of
                     # "2 days ago", which text.parse_relative_posted_at()'s English-only
                     # regex silently fails to parse (found via plan review 2026-07-24)
        "api_key": SERPAPI_API_KEY,
    }
    if date_chip:
        params["chips"] = f"date_posted:{date_chip}"
    url = "https://serpapi.com/search.json?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"User-Agent": "hermes-jobs-ingest/1.0"})
    with urllib.request.urlopen(req, timeout=http.DEFAULT_TIMEOUT) as resp:
        data = json.loads(resp.read().decode())
    if "error" in data:
        raise RuntimeError(data["error"])
    return data.get("jobs_results", [])


def normalize_job(job, mode):
    """Shared record shape for both Google Jobs sources (SerpApi and the
    Apify actor return identical schema -- confirmed live, same job_id for
    the same posting via both paths)."""
    title = job.get("title")
    company_name = job.get("company_name") or "Unknown"
    location = job.get("location")
    detected = job.get("detected_extensions") or {}
    apply_options = job.get("apply_options") or []

    is_nyc = bool(text.NYC_PATTERN.search(location or ""))
    is_remote = bool(text.REMOTE_PATTERN.search(location or "")) or mode == "remote"

    return {
        "platform": "google_jobs",
        "company_token": text.slugify(company_name),
        "company_name": company_name,
        "source_id": job.get("job_id") or hashlib.sha256(
            f"{title}|{company_name}|{location}".encode()
        ).hexdigest()[:16],
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
    if not SERPAPI_API_KEY:
        print("google-jobs-serpapi ingest FAILED: SERPAPI_API_KEY not set.")
        sys.exit(1)

    conn = dbconn.connect_or_exit("google-jobs-serpapi ingest", schema=schema.SCHEMA)

    schema.ensure_schema(conn)
    state.ensure_state_schema(conn, schema.WATERMARK_TABLE,
                              with_claims=True)
    job_spec = schema.spec(schema.HASH_FIELDS_SHORT)

    try:
        buckets = load_query_buckets()
    except (OSError, json.JSONDecodeError, KeyError) as e:
        print(f"google-jobs-serpapi ingest FAILED: could not load {GOOGLE_JOBS_QUERIES_FILE}: {e}")
        conn.close()
        sys.exit(1)

    picked = pick_stale_queries_by_bucket(conn, buckets)

    total_new = total_updated = total_unchanged = 0
    query_errors = []
    queries_run = 0

    for q, last_run_str in picked:
        dataset = f"google_jobs:query:{q['slug']}"
        date_chip = choose_date_chip(last_run_str)
        try:
            jobs = serpapi_search(q["query"], q["location"], date_chip)
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError,
                json.JSONDecodeError, RuntimeError, OSError) as e:
            query_errors.append(f"{q['slug']}: {e}")
            state.release_claim(conn, dataset, table=schema.WATERMARK_TABLE)  # let another machine retry right away
            if DEBUG_PRINT_KEYS:
                print(f"[debug] SerpApi fetch failed for {q['slug']}: {e}", file=sys.stderr)
            continue

        records = [normalize_job(j, q["mode"]) for j in jobs]
        n, u, unc = upsert(conn, job_spec, records, schema.make_job_id, debug=DEBUG_PRINT_KEYS)
        total_new += n
        total_updated += u
        total_unchanged += unc
        queries_run += 1

        # Success -- releases the claim as part of the same write (see mark_success).
        state.mark_success(conn, dataset, utc_now_str(),
                           table=schema.WATERMARK_TABLE)
        log_query_stats(conn, q["slug"], n, len(jobs), text.days_since(last_run_str))

        if DEBUG_PRINT_KEYS:
            print(f"[debug] {q['slug']} ({q['query']!r} @ {q['location']}, "
                  f"chip={date_chip}): {len(jobs)} results -> {n} new, {u} updated, "
                  f"{unc} unchanged", file=sys.stderr)

    closed_count = schema.close_stale(conn, 'google_jobs', GOOGLE_JOBS_STALE_AFTER_DAYS)
    conn.close()

    if query_errors and queries_run == 0:
        print(f"google-jobs-serpapi ingest FAILED: all {len(query_errors)} queries failed. "
              f"Sample: {query_errors[:3]}")
        sys.exit(1)

    if query_errors and DEBUG_PRINT_KEYS:
        print(f"[debug] {len(query_errors)}/{len(picked)} queries failed: {query_errors}", file=sys.stderr)

    if total_new or total_updated or closed_count or query_errors:
        print(f"google-jobs-serpapi-ingest: {total_new} new, {total_updated} updated, "
              f"{total_unchanged} unchanged, {closed_count} closed (stale), "
              f"{queries_run}/{len(picked)} queries succeeded ({len(query_errors)} failed).")


if __name__ == "__main__":
    main()

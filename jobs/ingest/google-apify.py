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
import hashlib
import urllib.request
import urllib.error
from datetime import datetime, timedelta, timezone

import psycopg

DATABASE_URL = os.environ.get(
    "DATABASE_URL", "postgresql://nyc_events@localhost:5432/nyc_events"
)
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
HTTP_TIMEOUT = 30
GOOGLE_JOBS_STALE_AFTER_DAYS = 30
# Same guard as ingest/google-serpapi.py (see the comment there): don't
# re-claim a query that already succeeded within this window, so multiple
# machines running run-daily.py on the same day don't burn paid Apify
# results re-fetching what the first run already covered.
MIN_HOURS_BETWEEN_RUNS = float(os.environ.get("GOOGLE_JOBS_MIN_HOURS_BETWEEN_RUNS", "20"))

SENIOR_PATTERN = re.compile(
    r"\b(senior|sr\.?|staff|principal|director|vp\b|vice president|"
    r"head of|lead\b|chief|executive|manager)\b",
    re.IGNORECASE,
)
ENTRY_PATTERN = re.compile(
    r"\b(entry.?level|junior|jr\.?|new grad|graduate|intern(ship)?|"
    r"apprentice|associate|coordinator)\b",
    re.IGNORECASE,
)
NYC_PATTERN = re.compile(r"\b(new york|nyc|manhattan|brooklyn|queens|bronx|staten island)\b", re.IGNORECASE)
REMOTE_PATTERN = re.compile(r"\bremote\b", re.IGNORECASE)
RELATIVE_TIME_PATTERN = re.compile(r"(\d+)\+?\s*(hour|day|week|month)s?\s*ago", re.IGNORECASE)


def utc_now_str():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")


def ensure_schema(conn):
    """Defensive duplicate of ingest/ats.py's ensure_schema -- works standalone."""
    conn.execute("CREATE SCHEMA IF NOT EXISTS jobs")
    conn.execute("SET search_path TO jobs, public")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS jobs (
            id TEXT PRIMARY KEY,
            platform TEXT NOT NULL,
            company_token TEXT NOT NULL,
            company_name TEXT NOT NULL,
            source_id TEXT NOT NULL,
            title TEXT,
            location_raw TEXT,
            department TEXT,
            job_url TEXT,
            posted_at TEXT,
            seniority_guess TEXT,
            location_is_nyc BOOLEAN,
            location_is_remote BOOLEAN,
            company_is_nyc_hq BOOLEAN,
            company_is_ai_focused BOOLEAN,
            status TEXT NOT NULL DEFAULT 'open',
            description_text TEXT,
            raw_json TEXT,
            content_hash TEXT,
            first_seen TEXT NOT NULL,
            last_seen TEXT NOT NULL,
            closed_at TEXT
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_jobs_company ON jobs(company_token)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_jobs_seniority ON jobs(seniority_guess)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_jobs_nyc ON jobs(location_is_nyc)")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS job_ingest_state (
            dataset TEXT PRIMARY KEY,
            last_success_at TEXT NOT NULL
        )
    """)
    conn.execute("ALTER TABLE job_ingest_state ADD COLUMN IF NOT EXISTS claimed_at TEXT")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS google_jobs_query_stats (
            slug TEXT NOT NULL,
            run_at TEXT NOT NULL,
            new_count INTEGER NOT NULL,
            total_fetched INTEGER NOT NULL,
            days_since_last_run REAL,
            PRIMARY KEY (slug, run_at)
        )
    """)
    conn.commit()


CLAIM_TTL_MINUTES = 15  # same claim scheme as ingest/google-serpapi.py -- shared table


def try_claim_query(conn, dataset, now_dt):
    """Atomic claim -- see ingest/google-serpapi.py's module docstring
    (MULTI-MACHINE SAFE BY DESIGN) for the full reasoning. Shared table
    means this also coordinates against any SerpApi machines claiming the
    same dataset key, not just other Apify runs."""
    now_str = now_dt.strftime("%Y-%m-%dT%H:%M:%S")
    ttl_cutoff_str = (now_dt - timedelta(minutes=CLAIM_TTL_MINUTES)).strftime("%Y-%m-%dT%H:%M:%S")
    cur = conn.execute(
        """
        INSERT INTO job_ingest_state (dataset, last_success_at, claimed_at)
        VALUES (%(dataset)s, '', %(now)s)
        ON CONFLICT (dataset) DO UPDATE
            SET claimed_at = %(now)s
            WHERE job_ingest_state.claimed_at IS NULL OR job_ingest_state.claimed_at < %(ttl_cutoff)s
        RETURNING dataset
        """,
        {"dataset": dataset, "now": now_str, "ttl_cutoff": ttl_cutoff_str},
    )
    won = cur.fetchone() is not None
    conn.commit()
    return won


def mark_success(conn, dataset, ts):
    conn.execute(
        """
        INSERT INTO job_ingest_state (dataset, last_success_at, claimed_at)
        VALUES (%s, %s, NULL)
        ON CONFLICT (dataset) DO UPDATE SET last_success_at = EXCLUDED.last_success_at, claimed_at = NULL
        """,
        (dataset, ts),
    )
    conn.commit()


def release_claim(conn, dataset):
    conn.execute("UPDATE job_ingest_state SET claimed_at = NULL WHERE dataset = %s", (dataset,))
    conn.commit()


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
        if try_claim_query(conn, dataset, now_dt):
            picked.append((q, watermarks.get(q["slug"])))
    return picked


def days_since(last_run_str):
    if not last_run_str:
        return None
    try:
        last_run = datetime.strptime(last_run_str, "%Y-%m-%dT%H:%M:%S").replace(tzinfo=timezone.utc)
    except ValueError:
        return None
    return (datetime.now(timezone.utc) - last_run).total_seconds() / 86400


def http_json(url, method="GET", body=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(
        url, data=data, method=method,
        headers={"Content-Type": "application/json", "User-Agent": "hermes-jobs-ingest/1.0"},
    )
    with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT) as resp:
        return json.loads(resp.read().decode())


def run_actor_query(query, location):
    """Start an actor run, poll to completion, fetch dataset items. Explicit
    num_results/max_pagination on every call -- see COST DISCIPLINE above."""
    start = http_json(
        f"https://api.apify.com/v2/acts/{ACTOR_ID}/runs?token={APIFY_API_TOKEN}",
        method="POST",
        body={
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
        run = http_json(f"https://api.apify.com/v2/actor-runs/{run_id}?token={APIFY_API_TOKEN}")
        status = run["data"]["status"]

    if status != "SUCCEEDED":
        raise RuntimeError(f"actor run {run_id} ended with status={status} after {elapsed}s")

    dataset_id = run["data"]["defaultDatasetId"]
    return http_json(f"https://api.apify.com/v2/datasets/{dataset_id}/items?token={APIFY_API_TOKEN}")


def strip_html(text):
    if not text:
        return None
    text = html_module.unescape(text)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text[:5000] if text else None


def guess_seniority(title):
    if not title:
        return "unknown"
    if SENIOR_PATTERN.search(title):
        return "senior"
    if ENTRY_PATTERN.search(title):
        return "entry"
    return "mid_or_unspecified"


def slugify(text):
    text = re.sub(r"[^a-z0-9]+", "-", (text or "").lower()).strip("-")
    return text or "unknown"


def parse_relative_posted_at(text):
    if not text:
        return None
    m = RELATIVE_TIME_PATTERN.search(text)
    if not m:
        return None
    n, unit = int(m.group(1)), m.group(2).lower()
    delta = {
        "hour": timedelta(hours=n), "day": timedelta(days=n),
        "week": timedelta(weeks=n), "month": timedelta(days=n * 30),
    }[unit]
    return (datetime.now(timezone.utc) - delta).isoformat()


def normalize_job(job, mode):
    """Identical record shape to ingest/google-serpapi.py -- this
    actor's output schema matches SerpApi's field-for-field (confirmed live,
    same job_id for the same posting via both paths)."""
    title = job.get("title")
    company_name = job.get("company_name") or "Unknown"
    location = job.get("location")
    detected = job.get("detected_extensions") or {}
    apply_options = job.get("apply_options") or []

    is_nyc = bool(NYC_PATTERN.search(location or ""))
    is_remote = bool(REMOTE_PATTERN.search(location or "")) or mode == "remote"

    return {
        "platform": "google_jobs",
        "company_token": slugify(company_name),
        "company_name": company_name,
        "source_id": job.get("job_id") or hashlib.sha256(
            f"{title}|{company_name}|{location}".encode()
        ).hexdigest()[:16],
        "title": title,
        "location_raw": location,
        "department": detected.get("schedule_type"),
        "job_url": (apply_options[0].get("link") if apply_options else None) or job.get("share_link"),
        "posted_at": parse_relative_posted_at(detected.get("posted_at")),
        "seniority_guess": guess_seniority(title),
        "location_is_nyc": is_nyc,
        "location_is_remote": is_remote,
        "company_is_nyc_hq": None,
        "company_is_ai_focused": None,
        "description_text": strip_html(job.get("description")),
        "raw_json": json.dumps(job)[:20000],
    }


def content_hash(rec):
    fields = (
        rec["title"], rec["location_raw"], rec["job_url"],
        rec["posted_at"], rec.get("description_text") or "",
    )
    return hashlib.sha256("|".join(str(f) for f in fields).encode()).hexdigest()


def make_id(platform, token, source_id):
    return hashlib.sha256(f"{platform}:{token}:{source_id}".encode()).hexdigest()[:24]


def upsert(conn, records):
    now = utc_now_str()
    new_count = updated_count = unchanged_count = 0

    for rec in records:
        rec_id = make_id(rec["platform"], rec["company_token"], rec["source_id"])
        new_hash = content_hash(rec)
        existing = conn.execute(
            "SELECT content_hash, status FROM jobs WHERE id = %s", (rec_id,)
        ).fetchone()

        if existing is None:
            conn.execute(
                """
                INSERT INTO jobs (id, platform, company_token, company_name, source_id, title,
                    location_raw, department, job_url, posted_at, seniority_guess,
                    location_is_nyc, location_is_remote, company_is_nyc_hq, company_is_ai_focused,
                    status, description_text, raw_json, content_hash, first_seen, last_seen, closed_at)
                VALUES (%(id)s, %(platform)s, %(company_token)s, %(company_name)s, %(source_id)s,
                    %(title)s, %(location_raw)s, %(department)s, %(job_url)s, %(posted_at)s,
                    %(seniority_guess)s, %(location_is_nyc)s, %(location_is_remote)s,
                    %(company_is_nyc_hq)s, %(company_is_ai_focused)s, 'open', %(description_text)s,
                    %(raw_json)s, %(content_hash)s, %(first_seen)s, %(last_seen)s, NULL)
                """,
                {**rec, "id": rec_id, "content_hash": new_hash, "first_seen": now, "last_seen": now},
            )
            new_count += 1
        elif existing[0] != new_hash or existing[1] != "open":
            conn.execute(
                """
                UPDATE jobs SET title=%(title)s, location_raw=%(location_raw)s,
                    department=%(department)s, job_url=%(job_url)s, posted_at=%(posted_at)s,
                    seniority_guess=%(seniority_guess)s, location_is_nyc=%(location_is_nyc)s,
                    location_is_remote=%(location_is_remote)s, status='open',
                    description_text=%(description_text)s, raw_json=%(raw_json)s,
                    content_hash=%(content_hash)s, last_seen=%(last_seen)s, closed_at=NULL
                WHERE id=%(id)s
                """,
                {**rec, "id": rec_id, "content_hash": new_hash, "last_seen": now},
            )
            updated_count += 1
        else:
            conn.execute("UPDATE jobs SET last_seen = %s WHERE id = %s", (now, rec_id))
            unchanged_count += 1

    conn.commit()
    return new_count, updated_count, unchanged_count


def close_stale(conn, stale_days):
    cutoff = (datetime.now(timezone.utc) - timedelta(days=stale_days)).strftime("%Y-%m-%dT%H:%M:%S")
    now = utc_now_str()
    cur = conn.execute(
        """
        UPDATE jobs SET status = 'closed', closed_at = %s
        WHERE platform = 'google_jobs' AND status = 'open' AND last_seen < %s
        """,
        (now, cutoff),
    )
    conn.commit()
    return cur.rowcount


def main():
    if not APIFY_API_TOKEN:
        print("google-jobs-apify ingest FAILED: APIFY_API_TOKEN not set.")
        sys.exit(1)

    try:
        conn = psycopg.connect(DATABASE_URL)
    except psycopg.OperationalError as e:
        safe_target = DATABASE_URL.split("@")[-1]
        print(f"google-jobs-apify ingest FAILED: could not connect to Postgres ({safe_target}): {e}")
        sys.exit(1)

    ensure_schema(conn)

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
            release_claim(conn, dataset)
            if DEBUG_PRINT_KEYS:
                print(f"[debug] Apify run failed for {q['slug']}: {e}", file=sys.stderr)
            continue

        records = [normalize_job(j, q["mode"]) for j in jobs]
        n, u, unc = upsert(conn, records)
        total_new += n
        total_updated += u
        total_unchanged += unc
        queries_run += 1

        mark_success(conn, dataset, utc_now_str())
        log_query_stats(conn, q["slug"], n, len(jobs), days_since(last_run_str))

        if DEBUG_PRINT_KEYS:
            print(f"[debug] {q['slug']} ({q['query']!r} @ {q['location']}): "
                  f"{len(jobs)} results -> {n} new, {u} updated, {unc} unchanged", file=sys.stderr)

    closed_count = close_stale(conn, GOOGLE_JOBS_STALE_AFTER_DAYS)
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

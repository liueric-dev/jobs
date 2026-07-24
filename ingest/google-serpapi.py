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
"há 2 dias" instead of "2 days ago"), which parse_relative_posted_at()'s
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

import psycopg

DATABASE_URL = os.environ.get(
    "DATABASE_URL", "postgresql://nyc_events@localhost:5432/nyc_events"
)
SERPAPI_API_KEY = os.environ.get("SERPAPI_API_KEY")
GOOGLE_JOBS_QUERIES_FILE = os.environ.get(
    "GOOGLE_JOBS_QUERIES_FILE",
    os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "config", "google-queries.json"),
)
DEBUG_PRINT_KEYS = os.environ.get("DEBUG_PRINT_KEYS", "") == "1"

HTTP_TIMEOUT = 30
GOOGLE_JOBS_STALE_AFTER_DAYS = 30
# Don't re-run a query that succeeded this recently. With multiple machines
# each launching run-daily.py on their own schedule, the second machine of
# the day would otherwise re-claim queries the first already ran (claims
# clear on success), re-fetching a chip=today window that's nearly all
# overlap. 20h (not 24) so a fixed daily cron time drifting a few minutes
# never skips a legitimate next-day run.
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
RELATIVE_TIME_PATTERN = re.compile(
    r"(\d+)\+?\s*(hour|day|week|month)s?\s*ago", re.IGNORECASE
)


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


CLAIM_TTL_MINUTES = 15  # see MULTI-MACHINE SAFE BY DESIGN in the module docstring


def try_claim_query(conn, dataset, now_dt):
    """Atomic claim -- succeeds only if nobody else holds an unexpired
    claim on this dataset. The empty-string last_success_at on first
    INSERT matches the existing "never run" sentinel used elsewhere
    (watermarks.get(slug, "") sorts first), not NULL, since the column is
    NOT NULL. Returns True if this call won the claim."""
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
    """Called after a query's fetch actually succeeds -- updates
    last_success_at (the real signal used for staleness/date-chip
    ordering) and releases the claim immediately rather than waiting out
    CLAIM_TTL_MINUTES, since there's no reason to make anyone wait once
    we know the result."""
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
    """Called after a fetch FAILS -- clears the claim immediately so
    another machine (with its own SerpApi account/quota) can retry right
    away instead of waiting out CLAIM_TTL_MINUTES for no reason."""
    conn.execute("UPDATE job_ingest_state SET claimed_at = NULL WHERE dataset = %s", (dataset,))
    conn.commit()


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
            if try_claim_query(conn, dataset, now_dt):
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


def days_since(last_run_str):
    if not last_run_str:
        return None
    try:
        last_run = datetime.strptime(last_run_str, "%Y-%m-%dT%H:%M:%S").replace(tzinfo=timezone.utc)
    except ValueError:
        return None
    return (datetime.now(timezone.utc) - last_run).total_seconds() / 86400


def serpapi_search(query, location, date_chip=None):
    params = {
        "engine": "google_jobs",
        "q": query,
        "location": location,
        "hl": "en",  # locale pinned -- without this Google intermittently returns
        "gl": "us",  # non-English relative timestamps, e.g. "há 2 dias" instead of
                     # "2 days ago", which parse_relative_posted_at()'s English-only
                     # regex silently fails to parse (found via plan review 2026-07-24)
        "api_key": SERPAPI_API_KEY,
    }
    if date_chip:
        params["chips"] = f"date_posted:{date_chip}"
    url = "https://serpapi.com/search.json?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"User-Agent": "hermes-jobs-ingest/1.0"})
    with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT) as resp:
        data = json.loads(resp.read().decode())
    if "error" in data:
        raise RuntimeError(data["error"])
    return data.get("jobs_results", [])


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
    """SerpApi/Apify both return Google's own relative phrasing ("3 days
    ago") rather than an absolute timestamp -- convert what we can, leave
    the rest None rather than guess (e.g. "30+ days ago" has no exact
    anchor)."""
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
    """Shared record shape for both Google Jobs sources (SerpApi and the
    Apify actor return identical schema -- confirmed live, same job_id for
    the same posting via both paths)."""
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
    if not SERPAPI_API_KEY:
        print("google-jobs-serpapi ingest FAILED: SERPAPI_API_KEY not set.")
        sys.exit(1)

    try:
        conn = psycopg.connect(DATABASE_URL)
    except psycopg.OperationalError as e:
        safe_target = DATABASE_URL.split("@")[-1]
        print(f"google-jobs-serpapi ingest FAILED: could not connect to Postgres ({safe_target}): {e}")
        sys.exit(1)

    ensure_schema(conn)

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
            release_claim(conn, dataset)  # let another machine retry right away
            if DEBUG_PRINT_KEYS:
                print(f"[debug] SerpApi fetch failed for {q['slug']}: {e}", file=sys.stderr)
            continue

        records = [normalize_job(j, q["mode"]) for j in jobs]
        n, u, unc = upsert(conn, records)
        total_new += n
        total_updated += u
        total_unchanged += unc
        queries_run += 1

        # Success -- releases the claim as part of the same write (see mark_success).
        mark_success(conn, dataset, utc_now_str())
        log_query_stats(conn, q["slug"], n, len(jobs), days_since(last_run_str))

        if DEBUG_PRINT_KEYS:
            print(f"[debug] {q['slug']} ({q['query']!r} @ {q['location']}, "
                  f"chip={date_chip}): {len(jobs)} results -> {n} new, {u} updated, "
                  f"{unc} unchanged", file=sys.stderr)

    closed_count = close_stale(conn, GOOGLE_JOBS_STALE_AFTER_DAYS)
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

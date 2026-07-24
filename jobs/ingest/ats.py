#!/usr/bin/env python3
"""
Tech/AI jobs daily ingestion script -- Postgres edition.

Pulls current open job postings directly from each company's public ATS
job-board API (Greenhouse, Lever, or Ashby -- see config/companies.json for the
verified company list), normalizes into a common schema, and upserts into
Postgres. Designed to run as a Hermes no-agent cron job, same pattern as
nyc-events-ingest.py.

WHY DIRECT ATS APIS INSTEAD OF SCRAPING LINKEDIN/INDEED:
    Greenhouse, Lever, and Ashby all expose a public, unauthenticated JSON
    endpoint per company -- the same one each company's own /careers page
    uses to render its listings. Querying it isn't scraping in the
    adversarial sense (no login wall, no bot detection), it's the intended
    public embed mechanism. LinkedIn/Indeed have no such public API and
    scraping them violates their ToS with real ban risk -- deliberately
    out of scope here. See config/companies.json's "checked_but_not_found" list
    for companies that didn't resolve to one of these three platforms
    (likely Workday/iCIMS/custom ATS -- would need a different approach).

    LIMITATION: this only covers companies you already know to look for.
    It's a monitoring tool, not a discovery tool -- growing config/companies.json
    over time (more companies, resolved via each company's real /careers
    page rather than guessed slugs) is the main lever for broader coverage.

DEPENDENCY (the one exception to "stdlib only" -- there's no reasonable
stdlib Postgres client):
    pip install "psycopg[binary]"
    (add --break-system-packages if your system Python is externally managed)

INSTALL:
    Lives in ~/.hermes/scripts/jobs/ alongside config/companies.json and the
    rest of the jobs pipeline (cron scripts must live somewhere under
    ~/.hermes/scripts/ -- a subdirectory is fine, confirmed by pointing an
    existing cron job's --script at "jobs/run-daily.py" and
    running it successfully).

DATABASE:
    Reuses the same Postgres instance/database as nyc-events-ingest.py
    (docker compose up -d in this directory) -- but NOT the same schema.
    Tables live in a dedicated `jobs` schema (jobs.jobs, jobs.job_ingest_state)
    rather than `public`, which is where the events pipeline's tables live.
    Same server, same database, same negligible resource cost as one schema
    -- this is purely so two unrelated projects sharing one Postgres
    instance don't end up with same-named or commingled tables in `public`
    as more of these ingest scripts get added over time. Ordinary SQL can
    still join across schemas within the same database if that's ever
    useful (SELECT ... FROM jobs.jobs JOIN public.events ...) -- the
    separation is organizational, not a hard boundary like a separate
    database would be.

CONFIG:
    DATABASE_URL       -- postgres connection string
    JOB_SOURCES_FILE    -- path to config/companies.json (default: alongside this script)

SCHEDULE: not scheduled directly -- see run-daily.py, which is the
single cron entry point and calls this script as a subprocess.

TEST BEFORE SCHEDULING:
    python3 ingest/ats.py
    DEBUG_PRINT_KEYS=1 python3 ingest/ats.py
    hermes cron run jobs-ingest

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
        own location text (NOT the company's HQ). A company being
        is_nyc_hq=true in config/companies.json says nothing about where any
        individual req is based -- these two boards-wide flags and the
        per-job location tags are independent and both worth checking.

INCREMENTAL BEHAVIOR -- these ATS APIs return the full current list of open
jobs on every call (no server-side "changed since" filter like Socrata has),
so there's no watermark-based request narrowing here. job_ingest_state still
records last_success_at per company, purely for observability (last run
time), not to shrink the fetch. Change detection instead happens client-side:

    1. content_hash per job -- a row's last_seen is bumped without a write
       if nothing about it actually changed.
    2. Jobs that disappear from a company's feed (filled/pulled reqs) are
       marked status='closed' rather than deleted, so you can see what
       recently closed. Rows closed for more than PRUNE_CLOSED_AFTER_DAYS
       are hard-deleted each run so the table doesn't grow unbounded.
    3. SAFETY VALVE: if a company's fetch returns zero jobs, the
       close-missing step is skipped entirely for that company on that run.
       A genuine zero-postings company is rare and not urgent to detect;
       silently closing every open row for a company because of a transient
       empty/malformed response would be a much worse failure mode.

CONCURRENCY -- this script is not scheduled directly. run-daily.py
is the actual cron entry point and runs this and ingest/builtin-nyc.py
sequentially via subprocess, so they never run concurrently on the same
machine. Run this file directly (as in TEST BEFORE SCHEDULING above) and
it just runs standalone -- no lock, no coordination needed, because there's
only one path (the wrapper) that ever triggers both automatically.

ERROR HANDLING -- deliberately different from nyc-events-ingest.py. That
script treats any dataset failure as a whole-run failure (2 datasets total,
so any failure is notable). This script hits 60+ independent company APIs
per run; one flaky/renamed/down company endpoint is expected background
noise, not a signal anything is actually broken. So: per-company fetch
failures are logged and skipped, other companies still run, and the run
only exits non-zero if EVERY company failed (which points at something
systemic -- DB down, network outage -- worth actually paging on).
"""

import os
import sys
import json
import re
import hashlib
import urllib.request
import urllib.error
from datetime import datetime, timedelta, timezone

import psycopg

DATABASE_URL = os.environ.get(
    "DATABASE_URL", "postgresql://nyc_events@localhost:5432/nyc_events"
)
JOB_SOURCES_FILE = os.environ.get(
    "JOB_SOURCES_FILE",
    os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "config", "companies.json"),
)
DEBUG_PRINT_KEYS = os.environ.get("DEBUG_PRINT_KEYS", "") == "1"
PRUNE_CLOSED_AFTER_DAYS = 30
HTTP_TIMEOUT = 20

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
NYC_PATTERN = re.compile(
    r"\b(new york|nyc|manhattan|brooklyn|queens|bronx|staten island)\b",
    re.IGNORECASE,
)
REMOTE_PATTERN = re.compile(r"\bremote\b", re.IGNORECASE)


def utc_now_str():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")


def ensure_schema(conn):
    """CREATE TABLE IF NOT EXISTS is a no-op on a table that already exists --
    it does NOT add new columns, so schema changes across revisions of this
    script need an explicit ALTER TABLE (see nyc-events-ingest.py for
    precedent; no ALTERs needed yet here since this is the first version).

    Tables live in a `jobs` Postgres schema, not `public` -- see DATABASE
    section of the module docstring. search_path is set on this connection
    so every unqualified table name below (and in every other function that
    takes a conn) resolves inside jobs.* without rewriting every query."""
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
    conn.commit()


def set_watermark(conn, dataset, ts):
    conn.execute(
        """
        INSERT INTO job_ingest_state (dataset, last_success_at) VALUES (%s, %s)
        ON CONFLICT (dataset) DO UPDATE SET last_success_at = EXCLUDED.last_success_at
        """,
        (dataset, ts),
    )
    conn.commit()


def load_sources():
    with open(JOB_SOURCES_FILE) as f:
        data = json.load(f)
    return data["companies"]


def http_get_json(url):
    req = urllib.request.Request(url, headers={"User-Agent": "hermes-jobs-ingest/1.0"})
    with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT) as resp:
        return json.loads(resp.read().decode())


def fetch_greenhouse(token):
    data = http_get_json(f"https://api.greenhouse.io/v1/boards/{token}/jobs?content=true")
    return data.get("jobs", [])


def fetch_lever(token):
    data = http_get_json(f"https://api.lever.co/v0/postings/{token}?mode=json")
    return data if isinstance(data, list) else []


def fetch_ashby(token):
    data = http_get_json(f"https://api.ashbyhq.com/posting-api/job-board/{token}")
    return data.get("jobs", [])


FETCHERS = {"greenhouse": fetch_greenhouse, "lever": fetch_lever, "ashby": fetch_ashby}


def strip_html(html):
    """Rough tag-stripper -- good enough for keyword heuristics and display,
    not meant to be a correct HTML parser. Truncated because raw_json below
    already preserves the untouched original for anything that needs it."""
    if not html:
        return None
    text = re.sub(r"<[^>]+>", " ", html)
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


def classify_location(text):
    text = text or ""
    return bool(NYC_PATTERN.search(text)), bool(REMOTE_PATTERN.search(text))


def normalize_greenhouse(company, job):
    title = job.get("title")
    location = (job.get("location") or {}).get("name")
    is_nyc, is_remote = classify_location(location)
    departments = job.get("departments") or []
    department = departments[0].get("name") if departments else None
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
        "seniority_guess": guess_seniority(title),
        "location_is_nyc": is_nyc,
        "location_is_remote": is_remote,
        "company_is_nyc_hq": bool(company.get("is_nyc_hq")),
        "company_is_ai_focused": bool(company.get("is_ai_focused")),
        "description_text": strip_html(job.get("content")),
        "raw_json": json.dumps(job),
    }


def normalize_lever(company, job):
    title = job.get("text")
    cats = job.get("categories") or {}
    location = cats.get("location") or ", ".join(cats.get("allLocations") or [])
    is_nyc, is_remote = classify_location(location)
    posted_at = None
    created = job.get("createdAt")
    if created:
        try:
            posted_at = datetime.fromtimestamp(created / 1000, tz=timezone.utc).isoformat()
        except (ValueError, OSError, OverflowError):
            posted_at = None
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
        "seniority_guess": guess_seniority(title),
        "location_is_nyc": is_nyc,
        "location_is_remote": is_remote,
        "company_is_nyc_hq": bool(company.get("is_nyc_hq")),
        "company_is_ai_focused": bool(company.get("is_ai_focused")),
        "description_text": strip_html(job.get("description") or job.get("descriptionBody")),
        "raw_json": json.dumps(job),
    }


def normalize_ashby(company, job):
    title = job.get("title")
    location = job.get("location")
    is_nyc, is_remote = classify_location(location)
    if job.get("isRemote"):
        is_remote = True
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
        "seniority_guess": guess_seniority(title),
        "location_is_nyc": is_nyc,
        "location_is_remote": is_remote,
        "company_is_nyc_hq": bool(company.get("is_nyc_hq")),
        "company_is_ai_focused": bool(company.get("is_ai_focused")),
        "description_text": strip_html(job.get("descriptionHtml") or job.get("descriptionPlain")),
        "raw_json": json.dumps(job),
    }


NORMALIZERS = {"greenhouse": normalize_greenhouse, "lever": normalize_lever, "ashby": normalize_ashby}


def make_id(platform, token, source_id):
    return hashlib.sha256(f"{platform}:{token}:{source_id}".encode()).hexdigest()[:24]


def content_hash(rec):
    """Fields that represent the posting's actual content -- excludes
    bookkeeping (raw_json, timestamps, status) so unrelated churn doesn't
    register as a change. Status transitions are handled separately by
    close_missing(), not through this hash."""
    fields = (
        rec["title"], rec["location_raw"], rec["department"], rec["job_url"],
        rec["posted_at"], rec.get("description_text") or "",
    )
    return hashlib.sha256("|".join(str(f) for f in fields).encode()).hexdigest()


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
            # Second condition catches a job that was previously marked
            # closed (disappeared from a prior fetch) but has now reappeared
            # -- treat that as a reopen, not just a content edit.
            conn.execute(
                """
                UPDATE jobs SET title=%(title)s, location_raw=%(location_raw)s,
                    department=%(department)s, job_url=%(job_url)s, posted_at=%(posted_at)s,
                    seniority_guess=%(seniority_guess)s, location_is_nyc=%(location_is_nyc)s,
                    location_is_remote=%(location_is_remote)s, company_is_nyc_hq=%(company_is_nyc_hq)s,
                    company_is_ai_focused=%(company_is_ai_focused)s, status='open',
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


def close_missing(conn, platform, token, seen_ids, now):
    """Mark jobs 'closed' if they were open before but didn't show up in
    this run's fetch for this company. Caller is responsible for only
    invoking this when seen_ids is non-empty (see module docstring's
    SAFETY VALVE note) -- an empty seen_ids here would close every open
    job for the company, which is correct only if the fetch is trustworthy."""
    cur = conn.execute(
        """
        UPDATE jobs SET status = 'closed', closed_at = %s, last_seen = %s
        WHERE platform = %s AND company_token = %s AND status = 'open'
          AND NOT (source_id = ANY(%s))
        """,
        (now, now, platform, token, seen_ids),
    )
    conn.commit()
    return cur.rowcount


def prune_old_closed(conn, days):
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%S")
    cur = conn.execute(
        "DELETE FROM jobs WHERE status = 'closed' AND closed_at IS NOT NULL AND closed_at < %s",
        (cutoff,),
    )
    conn.commit()
    return cur.rowcount


def main():
    try:
        conn = psycopg.connect(DATABASE_URL)
    except psycopg.OperationalError as e:
        safe_target = DATABASE_URL.split("@")[-1]  # don't log credentials
        print(f"jobs ingest FAILED: could not connect to Postgres ({safe_target}): {e}")
        sys.exit(1)

    ensure_schema(conn)

    try:
        sources = load_sources()
    except (OSError, json.JSONDecodeError) as e:
        print(f"jobs ingest FAILED: could not load {JOB_SOURCES_FILE}: {e}")
        conn.close()
        sys.exit(1)

    run_started_at = utc_now_str()
    total_new = total_updated = total_unchanged = total_closed = 0
    company_errors = []
    company_successes = 0

    for company in sources:
        platform = company["platform"]
        token = company["token"]
        fetch = FETCHERS[platform]
        normalize = NORMALIZERS[platform]

        try:
            raw_jobs = fetch(token)
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError,
                json.JSONDecodeError, OSError) as e:
            company_errors.append(f"{company['name']} ({platform}:{token}): {e}")
            if DEBUG_PRINT_KEYS:
                print(f"[debug] fetch failed for {token}: {e}", file=sys.stderr)
            continue

        records = [normalize(company, j) for j in raw_jobs]
        n, u, unc = upsert(conn, records)
        total_new += n
        total_updated += u
        total_unchanged += unc
        company_successes += 1

        if records:
            seen_ids = [r["source_id"] for r in records]
            total_closed += close_missing(conn, platform, token, seen_ids, run_started_at)

        set_watermark(conn, f"{platform}:{token}", run_started_at)

        if DEBUG_PRINT_KEYS:
            print(f"[debug] {company['name']} ({platform}): fetched {len(raw_jobs)} -> "
                  f"{n} new, {u} updated, {unc} unchanged", file=sys.stderr)

    pruned = prune_old_closed(conn, PRUNE_CLOSED_AFTER_DAYS)
    conn.close()

    if company_errors and company_successes == 0:
        print(f"jobs ingest FAILED: all {len(company_errors)} sources failed. "
              f"Sample: {company_errors[:3]}")
        sys.exit(1)

    if company_errors and DEBUG_PRINT_KEYS:
        print(f"[debug] {len(company_errors)}/{len(sources)} sources failed (continuing): "
              f"{company_errors[:5]}", file=sys.stderr)

    # Stay silent on quiet days -- that's the point of no-agent watchdog mode.
    if total_new or total_updated or total_closed or pruned or company_errors:
        print(f"jobs-ingest: {total_new} new, {total_updated} updated, {total_unchanged} unchanged, "
              f"{total_closed} closed, {pruned} old-closed pruned, "
              f"across {company_successes}/{len(sources)} sources "
              f"({len(company_errors)} failed).")


if __name__ == "__main__":
    main()

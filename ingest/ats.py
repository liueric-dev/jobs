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
    Lives in ~/apps/jobs/ingest alongside the other five sources, one level
    below config/companies.json and the rest of the jobs pipeline. Scheduled
    by run-daily.py under the jobs-ingest systemd user timer, not by
    `hermes cron`, which refuses to run anything outside its own directory.

DATABASE:
    The `jobs` database, in its `public` schema. Shares a Postgres instance
    with the events pipeline and nothing else -- separate databases, separate
    roles, no cross-database query. This used to be a `jobs` schema inside the
    events database, on the argument that the separation only needed to be
    organizational; slice E made it a boundary Postgres enforces, because a
    convention that fails silently when forgotten is not a boundary.
    See ../schema.py's "DATABASE, NOT SCHEMA".

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
import html
import json
import re
import hashlib
import urllib.request
import urllib.error
from datetime import datetime, timedelta, timezone


# ingest/ and tools/ sit one level below the pipeline modules they import
# (schema, relevance, llm, ...). Python puts THIS file's directory on sys.path,
# not its parent, so the parent is added by hand. pipelib needs nothing -- it is
# an installed package (pip install --user -e ~/apps/pipelib).
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import schema  # noqa: E402  (schema.py)
from pipelib import dbconn, http, ids, state, text  # noqa: E402
from pipelib.timeparse import utc_now_str  # noqa: E402
from pipelib.upsert import upsert  # noqa: E402

JOB_SOURCES_FILE = os.environ.get(
    "JOB_SOURCES_FILE",
    os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "config", "companies.json"),
)
DEBUG_PRINT_KEYS = os.environ.get("DEBUG_PRINT_KEYS", "") == "1"
PRUNE_CLOSED_AFTER_DAYS = 30


def load_sources():
    with open(JOB_SOURCES_FILE) as f:
        data = json.load(f)
    return data["companies"]


def fetch_greenhouse(token):
    data = http.get_json(f"https://api.greenhouse.io/v1/boards/{token}/jobs?content=true")
    return data.get("jobs", [])


def fetch_lever(token):
    data = http.get_json(f"https://api.lever.co/v0/postings/{token}?mode=json")
    return data if isinstance(data, list) else []


def fetch_ashby(token):
    data = http.get_json(f"https://api.ashbyhq.com/posting-api/job-board/{token}")
    return data.get("jobs", [])


FETCHERS = {"greenhouse": fetch_greenhouse, "lever": fetch_lever, "ashby": fetch_ashby}


def greenhouse_description(content):
    """Plain text from Greenhouse's `content`, which arrives HTML-ESCAPED.

    Greenhouse does not serve HTML in this field -- it serves HTML that has
    been escaped once, so the tags themselves are entities:

        &lt;div class=&quot;content-intro&quot;&gt;&lt;h2&gt;About Us:&amp;nbsp;

    That is one level deeper than every other source here, and it is why a
    single unescape is not enough. Unescaping once turns `&lt;div&gt;` into a
    real `<div>` (strippable) but only turns `&amp;nbsp;` into `&nbsp;`, which
    then survives tag-stripping and lands in the database as literal text.

    Measured over 400 sampled postings:
        strip_html(c, unescape=False)  -- 300/300 rows held literal entities
        strip_html(c)                  -- 277/300 still did
        strip_html(html.unescape(c))   --   0/300   <- this

    So: unescape once here, and let strip_html's own unescape handle the
    second level before it strips tags. Do not "simplify" this into a single
    call -- 7,182 rows reading `&lt;div class=&quot;...` is what that looks
    like in production.
    """
    if not content:
        return None
    return text.strip_html(html.unescape(content))


def normalize_greenhouse(company, job):
    title = job.get("title")
    location = (job.get("location") or {}).get("name")
    is_nyc, is_remote = text.classify_location(location)
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
        # posted_at (hashed, frozen format) keeps updated_at first for
        # compatibility. posted_at_ts is what an app sorts on, so it prefers
        # first_published: "posted" should mean posted. Greenhouse bumps
        # updated_at for edits, which is why 6,096 rows looked July-fresh.
        "posted_at_ts": text.posted_at_timestamp(
            job.get("first_published") or job.get("updated_at")),
        "salary_text": None,
        "seniority_guess": text.guess_seniority(title),
        "location_is_nyc": is_nyc,
        "location_is_remote": is_remote,
        "company_is_nyc_hq": bool(company.get("is_nyc_hq")),
        "company_is_ai_focused": bool(company.get("is_ai_focused")),
        "description_text": greenhouse_description(job.get("content")),
        "raw_json": json.dumps(job),
    }


def normalize_lever(company, job):
    title = job.get("text")
    cats = job.get("categories") or {}
    location = cats.get("location") or ", ".join(cats.get("allLocations") or [])
    is_nyc, is_remote = text.classify_location(location)
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
        "posted_at_ts": text.posted_at_timestamp(posted_at),
        "salary_text": None,
        "seniority_guess": text.guess_seniority(title),
        "location_is_nyc": is_nyc,
        "location_is_remote": is_remote,
        "company_is_nyc_hq": bool(company.get("is_nyc_hq")),
        "company_is_ai_focused": bool(company.get("is_ai_focused")),
        # Lever serves real HTML (verified: `<p><strong>About Finix</strong>`),
        # so one unescape -- strip_html's default -- is correct here. Passing
        # unescape=False was leaving `&amp;` in the stored text.
        "description_text": text.strip_html(job.get("description") or job.get("descriptionBody")),
        "raw_json": json.dumps(job),
    }


def normalize_ashby(company, job):
    title = job.get("title")
    location = job.get("location")
    is_nyc, is_remote = text.classify_location(location)
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
        "posted_at_ts": text.posted_at_timestamp(job.get("publishedAt")),
        "salary_text": None,
        "seniority_guess": text.guess_seniority(title),
        "location_is_nyc": is_nyc,
        "location_is_remote": is_remote,
        "company_is_nyc_hq": bool(company.get("is_nyc_hq")),
        "company_is_ai_focused": bool(company.get("is_ai_focused")),
        # Ashby also serves real HTML (`<h1>Who We Are</h1>`) -- same reasoning
        # as Lever. This was leaving `&amp;` in 1,521 of 2,561 rows.
        "description_text": text.strip_html(job.get("descriptionHtml") or job.get("descriptionPlain")),
        "raw_json": json.dumps(job),
    }


NORMALIZERS = {"greenhouse": normalize_greenhouse, "lever": normalize_lever, "ashby": normalize_ashby}


def main():
    conn = dbconn.connect_or_exit("jobs ingest", schema=schema.SCHEMA)
    schema.ensure_schema(conn)

    # One spec per source family: ats/wwr hash `department`, the Google and
    # HN sources do not. The tuples are stored digests -- see schema.py.
    ats_spec = schema.spec(schema.HASH_FIELDS_ATS)

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
        result = upsert(conn, ats_spec, records, schema.make_job_id,
                        debug=DEBUG_PRINT_KEYS)
        n, u, unc = result
        total_new += n
        total_updated += u
        total_unchanged += unc
        company_successes += 1

        if records:
            seen_ids = [r["source_id"] for r in records]
            total_closed += schema.close_missing(conn, platform, token,
                                                 seen_ids, run_started_at)

        state.set_watermark(conn, f"{platform}:{token}", run_started_at,
                            table=schema.WATERMARK_TABLE)

        if DEBUG_PRINT_KEYS:
            print(f"[debug] {company['name']} ({platform}): fetched {len(raw_jobs)} -> "
                  f"{n} new, {u} updated, {unc} unchanged", file=sys.stderr)

    pruned = schema.prune_old_closed(conn, PRUNE_CLOSED_AFTER_DAYS)
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

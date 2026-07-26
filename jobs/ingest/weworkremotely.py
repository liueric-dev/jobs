#!/usr/bin/env python3
"""
We Work Remotely daily job listings ingest -- Postgres edition.

Pulls four category RSS feeds from weworkremotely.com and upserts into the
same `jobs` table ingest/ats.py writes to, tagged platform='weworkremotely'.

WHY RSS, NOT SCRAPING: WWR publishes genuine per-category RSS feeds (RSS
2.0, confirmed live) as its own public syndication mechanism -- this is the
intended machine-readable path, not an adversarial scrape.

WHICH CATEGORIES, AND WHY ONLY THESE FOUR: WWR's current site nav
(confirmed by parsing weworkremotely.com's homepage) exposes these
job categories: back-end-programming, front-end-programming,
full-stack-programming, devops-sysadmin, design, product, customer-support,
sales-and-marketing, management-and-finance, all-other-remote. Only the
first four are tech/AI-relevant for this pipeline's purpose; the rest are
deliberately excluded. (A legacy/umbrella "remote-programming-jobs.rss"
feed still resolves and returns content, but it isn't linked from current
site nav and appears to be a deprecated superset of the three specific
programming categories -- skipped in favor of the maintained, specific
ones. WWR also has no dedicated "data science" category as of this
writing; those roles surface under full-stack/back-end instead.)

NOISE WARNING -- VERIFIED, NOT HYPOTHETICAL: category tagging on WWR is
self-selected by the posting company, not enforced by WWR. Confirmed by
inspecting live feed output: the remote-back-end-programming-jobs.rss feed's
top items were "(Native Finnish) Customer Support Consultant" postings
tagged under "Full-Stack Programming". NON_TECH_EXCLUDE_PATTERN below
filters obviously-mistagged non-tech roles (customer support, sales,
recruiting, etc.) out of every category feed by title keyword -- this is a
blocklist applied on top of already-tech-leaning categories, not a
substitute for them, and it's necessarily imperfect (see ingest/ats.py's
own seniority-guess disclaimer re: keyword heuristics being approximate).

LIMITATION -- SAMPLED FEED, STALENESS-BASED CLOSE (same reasoning as
ingest/builtin-nyc.py): each RSS feed returns whatever WWR currently
publishes for that category (observed volumes: ~14-160 items depending on
category), not a stable exhaustive "all open postings" list with a
close-when-missing signal. A job absent from today's feed may have simply
scrolled off, not closed. So: weworkremotely-sourced rows close by
STALENESS (not re-seen in WWR_STALE_AFTER_DAYS days), not exact-diff.

REMOTE BY DEFINITION: every posting on We Work Remotely is remote --
location_is_remote is hardcoded True rather than regex-guessed from the
region text (which is often phrased as "Anywhere in the World", "US
Timezones Only", etc. and wouldn't reliably match a literal "remote"
keyword match). location_is_nyc still runs the normal regex against the
region text, since some remote-with-preference postings do call out NYC.

DEPENDENCY: none beyond psycopg (same as ingest/ats.py) -- stdlib
xml.etree.ElementTree parses the RSS, stdlib re/html handle field cleanup.

INSTALL: lives in ~/.hermes/scripts/jobs/ alongside the rest of the jobs pipeline

DATABASE: same Postgres instance/schema as ingest/ats.py (jobs.jobs table).
This script creates the schema defensively too, so it works standalone.

CONFIG:
    DATABASE_URL -- postgres connection string (same default as ingest/ats.py)

SCHEDULE: not scheduled directly -- see run-daily.py, which is the
single cron entry point and calls this script as a subprocess.

TEST BEFORE SCHEDULING:
    python3 ingest/weworkremotely.py
    DEBUG_PRINT_KEYS=1 python3 ingest/weworkremotely.py

CONCURRENCY: this script is not scheduled directly -- run-daily.py
runs all ingest scripts sequentially so they never run concurrently.
"""

import os
import sys
import re
import html as html_module
import hashlib
import time
import urllib.request
import urllib.error
import xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime
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

DEBUG_PRINT_KEYS = os.environ.get("DEBUG_PRINT_KEYS", "") == "1"

CATEGORIES = [
    "remote-back-end-programming-jobs",
    "remote-front-end-programming-jobs",
    "remote-full-stack-programming-jobs",
    "remote-devops-sysadmin-jobs",
]
FEED_URL_TEMPLATE = "https://weworkremotely.com/categories/{category}.rss"
REQUEST_DELAY_SECONDS = 2.0
WWR_STALE_AFTER_DAYS = 21
USER_AGENT = "Mozilla/5.0 (compatible; hermes-jobs-ingest/1.0; personal job-search automation)"

NON_TECH_EXCLUDE_PATTERN = re.compile(
    r"\b(customer support|customer success|sales rep|account executive|"
    r"account manager|business development|recruiter|talent acquisition|"
    r"hr generalist|human resources|bookkeeper|virtual assistant|"
    r"community manager|content writer|copywriter|social media|"
    r"marketing manager|marketing specialist|content marketing|"
    r"affiliate marketing)\b",
    re.IGNORECASE,
)


def fetch_feed(category):
    url = FEED_URL_TEMPLATE.format(category=category)
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=http.DEFAULT_TIMEOUT) as resp:
        return resp.read()


def parse_posted_at(pub_date_text):
    if not pub_date_text:
        return None
    try:
        return parsedate_to_datetime(pub_date_text).astimezone(timezone.utc).isoformat()
    except (TypeError, ValueError):
        return None


def parse_feed(xml_bytes, category):
    root = ET.fromstring(xml_bytes)
    records = []
    for item in root.iter("item"):
        raw_title = (item.findtext("title") or "").strip()
        if ":" in raw_title:
            company_name, title = raw_title.split(":", 1)
            company_name, title = company_name.strip(), title.strip()
        else:
            company_name, title = None, raw_title.strip()

        if not company_name or not title:
            continue  # can't build a usable row without both
        if NON_TECH_EXCLUDE_PATTERN.search(title):
            continue

        link = (item.findtext("link") or item.findtext("guid") or "").strip()
        region = (item.findtext("region") or "").strip()
        rss_category = (item.findtext("category") or category).strip()
        pub_date = item.findtext("pubDate")
        description = text.strip_html(item.findtext("description"))

        source_id = link.rsplit("/", 1)[-1] if link else None
        if not source_id:
            continue

        records.append({
            "platform": "weworkremotely",
            "company_token": text.slugify(company_name),
            "company_name": company_name,
            "source_id": source_id,
            "title": title,
            "location_raw": region or None,
            "department": rss_category or None,
            "job_url": link or None,
            "posted_at": parse_posted_at(pub_date),
            "posted_at_ts": text.posted_at_timestamp(parse_posted_at(pub_date)),
            "salary_text": None,
            "seniority_guess": text.guess_seniority(title),
            "location_is_nyc": bool(text.NYC_PATTERN.search(region)),
            "location_is_remote": True,
            "company_is_nyc_hq": None,
            "company_is_ai_focused": None,
            "description_text": description,
            "raw_json": None,
        })
    return records


def main():
    conn = dbconn.connect_or_exit("weworkremotely ingest", schema=schema.SCHEMA)

    schema.ensure_schema(conn)
    job_spec = schema.spec(schema.HASH_FIELDS_WWR)

    category_errors = []
    all_records = []
    seen_ids = set()
    for i, category in enumerate(CATEGORIES):
        try:
            xml_bytes = fetch_feed(category)
            records = parse_feed(xml_bytes, category)
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError,
                OSError, ET.ParseError) as e:
            category_errors.append(f"{category}: {e}")
            if DEBUG_PRINT_KEYS:
                print(f"[debug] fetch/parse failed for {category}: {e}", file=sys.stderr)
            continue

        for rec in records:
            key = (rec["company_token"], rec["source_id"])
            if key in seen_ids:
                continue  # same posting cross-listed under >1 category
            seen_ids.add(key)
            all_records.append(rec)

        if DEBUG_PRINT_KEYS:
            print(f"[debug] {category}: parsed {len(records)} items", file=sys.stderr)

        if i < len(CATEGORIES) - 1:
            time.sleep(REQUEST_DELAY_SECONDS)

    if not all_records and category_errors:
        print(f"weworkremotely ingest FAILED: no items parsed across {len(CATEGORIES)} "
              f"categories. Errors: {category_errors}")
        conn.close()
        sys.exit(1)

    new_count, updated_count, unchanged_count = upsert(conn, job_spec, all_records, schema.make_job_id, debug=DEBUG_PRINT_KEYS)
    closed_count = schema.close_stale(conn, 'weworkremotely', WWR_STALE_AFTER_DAYS)
    state.set_watermark(conn, "weworkremotely", utc_now_str(),
                        table=schema.WATERMARK_TABLE)
    conn.close()

    if category_errors and DEBUG_PRINT_KEYS:
        print(f"[debug] {len(category_errors)} categor(y/ies) failed: {category_errors}", file=sys.stderr)

    if new_count or updated_count or closed_count or category_errors:
        print(f"weworkremotely: {new_count} new, {updated_count} updated, "
              f"{unchanged_count} unchanged, {closed_count} closed (stale), "
              f"{len(all_records)} parsed across {len(CATEGORIES) - len(category_errors)}/{len(CATEGORIES)} "
              f"categories ({len(category_errors)} failures).")


if __name__ == "__main__":
    main()

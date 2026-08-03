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

INSTALL: lives in ~/apps/jobs/backend alongside the rest of the jobs pipeline

DATABASE: same database and table as ingest/ats.py (the `jobs` table).
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
import time
import urllib.error   # D31: the fetch moved to lib.http; the except tuple stayed
import xml.etree.ElementTree as ET
from collections import Counter
from email.utils import parsedate_to_datetime
from datetime import timezone


# ingest/ and tools/ sit one level below the pipeline modules they import
# (schema, relevance, llm, ...). Python puts THIS file's directory on sys.path,
# not its parent, so the parent is added by hand. That same insert is what
# reaches lib/ -- there is nothing to install.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import schema  # noqa: E402  (schema.py)
from lib import dbconn, http, state, text  # noqa: E402
from lib.timeparse import utc_now_str  # noqa: E402
from lib.upsert import UpsertErrorRate, upsert_checked  # noqa: E402

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
    """One category's RSS feed, as bytes.

    D31. This went through `lib.http` on 2026-08-02; before that it built its
    own Request and called `urllib.request.urlopen`, so a single transient 503
    from one feed lost that category for the run -- which is the exact
    scenario `lib/http.py:3-5` names as the reason that module was written.

    Bytes, not text, and `http.get_bytes` exists for this: the feed opens with
    `<?xml version="1.0" encoding="UTF-8"?>`, and `ET.fromstring` refuses a
    str that carries an encoding declaration.
    """
    url = FEED_URL_TEMPLATE.format(category=category)
    # The browser-ish USER_AGENT above, not lib/http.py's default -- WWR is a
    # scraped RSS feed, and this is the header the recorded cassettes were
    # taken with.
    return http.get_bytes(url, headers={"User-Agent": USER_AGENT})


def parse_posted_at(pub_date_text):
    if not pub_date_text:
        return None
    try:
        return parsedate_to_datetime(pub_date_text).astimezone(timezone.utc).isoformat()
    except (TypeError, ValueError):
        return None


#: D05. Every way an item can leave this script without becoming a row, in
#: report order. Named rather than counted anonymously, because the summary
#: line's whole job is to tell an exclude-pattern change that started eating
#: real engineering titles apart from a quiet week -- and one total cannot.
#: `git show refactor-freeze-2026-08-02:docs/ingest/weworkremotely.md:309-312` states the consequence of not having these:
#: such a change "would produce no signal at all".
#:
#: DROPS ARE NOT DEDUPES. `cross_listed` is counted here too but reported
#: separately below, because it is a CORRECT outcome and the other three are
#: losses. It is also normally nonzero -- WWR cross-lists heavily by design
#: (parse the same posting under back-end and full-stack) -- so folding it
#: into a "dropped" total would give that total a large, noisy floor for a
#: regression to hide inside, which is the exact failure this counter exists
#: to expose.
DROP_REASONS = ("no_company_or_title", "non_tech_excluded", "no_source_id")


def parse_feed(xml_bytes, category, stats=None):
    """Records from one category feed. `stats` accumulates DROP_REASONS.

    `stats` is an optional Counter so that the existing callers -- and every
    cassette test -- keep working unchanged, and so counts accumulate across
    all four feeds in one object rather than being summed by the caller.
    """
    stats = Counter() if stats is None else stats
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
            # No colon in <title>, or a colon with nothing on one side of it.
            # The register recorded this as "no colon"; the condition is
            # broader than that and the counter is named for the condition.
            stats["no_company_or_title"] += 1
            continue  # can't build a usable row without both
        if NON_TECH_EXCLUDE_PATTERN.search(title):
            stats["non_tech_excluded"] += 1
            continue

        link = (item.findtext("link") or item.findtext("guid") or "").strip()
        region = (item.findtext("region") or "").strip()
        rss_category = (item.findtext("category") or category).strip()
        pub_date = item.findtext("pubDate")
        description = text.strip_html(item.findtext("description"))

        source_id = link.rsplit("/", 1)[-1] if link else None
        if not source_id:
            stats["no_source_id"] += 1
            continue

        # D29. Parsed once and reused. It was called twice on the same string,
        # which was merely wasteful here -- but `posted_at` feeds
        # HASH_FIELDS_SHORT via posted_at_timestamp, so two calls are two
        # chances for one row to carry a value its own timestamp disagrees
        # with if the parse ever stops being pure.
        posted_at = parse_posted_at(pub_date)

        records.append({
            "platform": "weworkremotely",
            "company_token": text.slugify(company_name),
            "company_name": company_name,
            "source_id": source_id,
            "title": title,
            "location_raw": region or None,
            "department": rss_category or None,
            "job_url": link or None,
            "posted_at": posted_at,
            "posted_at_ts": text.posted_at_timestamp(posted_at),
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
    stats = Counter()
    for i, category in enumerate(CATEGORIES):
        try:
            xml_bytes = fetch_feed(category)
            records = parse_feed(xml_bytes, category, stats)
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError,
                OSError, ET.ParseError) as e:
            category_errors.append(f"{category}: {e}")
            if DEBUG_PRINT_KEYS:
                print(f"[debug] fetch/parse failed for {category}: {e}", file=sys.stderr)
            continue

        for rec in records:
            key = (rec["company_token"], rec["source_id"])
            if key in seen_ids:
                stats["cross_listed"] += 1
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

    # One batch, so upsert_checked's own threshold IS the per-run rate. The
    # raise is deferred to the bottom of main() so the summary still prints.
    upsert_failure = None
    try:
        result = upsert_checked(conn, job_spec, all_records, schema.make_job_id,
                                debug=DEBUG_PRINT_KEYS)
    except UpsertErrorRate as e:
        result, upsert_failure = e.result, e
    new_count, updated_count, unchanged_count = (result.new, result.updated,
                                                 result.unchanged)
    closed_count = schema.close_stale(conn, 'weworkremotely', WWR_STALE_AFTER_DAYS)
    state.set_watermark(conn, "weworkremotely", utc_now_str(),
                        table=schema.WATERMARK_TABLE)
    conn.close()

    if category_errors and DEBUG_PRINT_KEYS:
        print(f"[debug] {len(category_errors)} categor(y/ies) failed: {category_errors}", file=sys.stderr)

    # D05. Reported at every verbosity, not behind DEBUG_PRINT_KEYS: a drop
    # count that only appears when someone thinks to ask for it is the same
    # silence in a different shape.
    dropped = sum(stats[r] for r in DROP_REASONS)
    breakdown = ", ".join(f"{r}={stats[r]}" for r in DROP_REASONS)
    if (new_count or updated_count or closed_count or category_errors
            or result.errors or dropped or stats["cross_listed"]):
        print(f"weworkremotely: {new_count} new, {updated_count} updated, "
              f"{unchanged_count} unchanged, {closed_count} closed (stale), "
              f"{len(result.errors)} record(s) dropped, "
              f"{dropped} item(s) filtered out before upsert ({breakdown}), "
              f"{stats['cross_listed']} cross-listed duplicate(s), "
              f"{len(all_records)} parsed across {len(CATEGORIES) - len(category_errors)}/{len(CATEGORIES)} "
              f"categories ({len(category_errors)} failures).")

    if upsert_failure:
        print(f"weworkremotely ingest FAILED: {upsert_failure}")
        sys.exit(1)


if __name__ == "__main__":
    main()

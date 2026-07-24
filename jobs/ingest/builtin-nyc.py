#!/usr/bin/env python3
"""
Built In NYC daily job listings scraper -- Postgres edition.

Scrapes https://www.builtinnyc.com/jobs (server-rendered HTML, no
JS/headless browser needed) and upserts into the same `jobs` table
ingest/ats.py writes to, tagged platform='builtin'. This is a genuine
Tier-3 scraping source, not a public API -- see EXTRACTION METHOD below
for what was actually verified before writing this.

EXTRACTION METHOD -- confirmed by loading the page in a real browser and
checking DevTools network traffic: ZERO XHR/fetch calls fire to load job
listings. Despite being a React-driven page, Built In renders the full
job list server-side into the initial HTML response -- title, company,
location, salary (when disclosed), and Built In's own seniority
classification are all present in one plain GET, extractable with regex
against consistent `data-id="..."` attributes. No API, no JSON-LD, no
headless browser required. (An earlier pass at this wrongly concluded it
needed JS rendering -- that was a wrong regex for the job-detail URL
pattern, not an actual site limitation.)

ROBOTS.TXT / POLITENESS: builtinnyc.com's robots.txt explicitly Allows
crawling of /jobs?page=1, ?page=2, and ?page=3, then Disallows deeper
pagination generally. Pages 4+ were confirmed to still return valid data
when requested directly (nothing technically enforces the cutoff), but
that Allow/Disallow split is the site owner's stated crawl preference, so
MAX_PAGES defaults to 3 (~60 listings/run) rather than paging further.
REQUEST_DELAY_SECONDS adds a pause between page fetches -- this is a
scrape against real page loads, not a purpose-built API, so it doesn't
get hit back-to-back the way ingest/ats.py's ATS calls do.

LIMITATION -- this is a bounded sample (most-recent ~60 NYC listings
across ALL companies per run), not an exhaustive list the way Tier 1's
per-company ATS pulls are. Two consequences:
    1. No cross-source dedup: a company already covered by
       ingest/ats.py's ATS pull (e.g. Datadog via Greenhouse) may also
       appear here under platform='builtin' with a different company_token
       (derived from Built In's own /company/{slug} URL, not the ATS
       token). These are NOT merged -- querying across both sources means
       accepting some duplication, or de-duplicating at query time
       (e.g. DISTINCT ON company_name, title). Merging robustly would need
       fuzzy company-name matching that doesn't exist yet.
    2. NO close-missing logic (unlike ingest/ats.py). A job absent from
       this run's ~60-listing sample doesn't mean it closed -- it may have
       simply been pushed past page 3 by newer postings. Applying an
       exact-diff close would falsely close jobs that are still open.
       Instead, builtin-sourced rows are closed by STALENESS: not re-seen
       in BUILTIN_STALE_AFTER_DAYS days. That's a proxy, not a certainty,
       but it's the honest signal actually available from a sampled feed.

DEPENDENCY: none beyond psycopg (same as ingest/ats.py) -- stdlib `re`
handles the HTML parsing, no BeautifulSoup needed; the markup is regular
enough that regex against the site's `data-id` attributes is reliable
(verified against 4 separate live pages before writing this).

INSTALL: lives in ~/.hermes/scripts/jobs/ alongside the rest of the jobs pipeline

DATABASE: same Postgres instance/database/schema as ingest/ats.py
(jobs.jobs table) -- see that script's docstring for the schema-vs-database
reasoning. This script creates the schema defensively too, so it works
even if run before ingest/ats.py ever has.

CONFIG:
    DATABASE_URL -- postgres connection string (same default as ingest/ats.py)

SCHEDULE: not scheduled directly -- see run-daily.py, which is the
single cron entry point and calls this script as a subprocess.

TEST BEFORE SCHEDULING:
    python3 ingest/builtin-nyc.py
    DEBUG_PRINT_KEYS=1 python3 ingest/builtin-nyc.py

CONCURRENCY: this script is not scheduled directly -- see
run-daily.py, which runs this and ingest/ats.py sequentially via
subprocess so they never run at the same time on this machine.

SENIORITY MAPPING: Built In supplies its own classification per posting
("Junior", "Mid level", "Senior level", "Entry level", "Expert/Leader")
rather than requiring the title-keyword guess ingest/ats.py has to make.
Mapped onto the same seniority_guess vocabulary used there (entry / senior /
mid_or_unspecified) so both sources are queryable together consistently:
    Entry level, Junior  -> entry
    Mid level             -> mid_or_unspecified
    Senior level, Expert/Leader -> senior
    (missing/unrecognized) -> unknown
"""

import os
import sys
import re
import html as html_module
import hashlib
import time
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

DEBUG_PRINT_KEYS = os.environ.get("DEBUG_PRINT_KEYS", "") == "1"

BASE_URL = "https://www.builtinnyc.com/jobs"
MAX_PAGES = 3
REQUEST_DELAY_SECONDS = 2.5
BUILTIN_STALE_AFTER_DAYS = 14
USER_AGENT = "Mozilla/5.0 (compatible; hermes-jobs-ingest/1.0; personal job-search automation)"

TITLE_PATTERN = re.compile(r'data-id="job-card-title"[^>]*data-alias="([^"]+)"[^>]*>([^<]+)<')
COMPANY_PATTERN = re.compile(r'<a href="([^"]+)"[^>]*data-id="company-title"[^>]*><span>([^<]+)</span>')
WORK_TYPE_PATTERN = re.compile(r'fa-house-building[^>]*></i></div>\s*<span[^>]*>([^<]+)</span>', re.DOTALL)
GEO_PATTERN = re.compile(r'fa-location-dot[^>]*></i></div>\s*<div><span[^>]*>([^<]+)</span>', re.DOTALL)
SALARY_PATTERN = re.compile(r'([0-9]{1,3}K-[0-9]{1,3}K[^<]*)')
SENIORITY_PATTERN = re.compile(r'(Junior|Mid level|Senior level|Entry level|Expert/Leader)')
POSTED_PATTERN = re.compile(r'fa-clock[^>]*></i>([^<]+)<', re.DOTALL)

SENIORITY_MAP = {
    "entry level": "entry",
    "junior": "entry",
    "mid level": "mid_or_unspecified",
    "senior level": "senior",
    "expert/leader": "senior",
}


def fetch_page(page_num):
    url = f"{BASE_URL}?page={page_num}"
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=http.DEFAULT_TIMEOUT) as resp:
        return resp.read().decode("utf-8", errors="replace")


def extract_field(text, pattern):
    m = pattern.search(text)
    return html_module.unescape(m.group(1).strip()) if m else None


def parse_page(page_html):
    titles = list(TITLE_PATTERN.finditer(page_html))
    companies = list(COMPANY_PATTERN.finditer(page_html))

    records = []
    for i, tm in enumerate(titles):
        window_end = titles[i + 1].start() if i + 1 < len(titles) else tm.end() + 3000
        card = page_html[tm.start():window_end]

        alias = tm.group(1)
        title = html_module.unescape(tm.group(2))
        job_id = alias.rsplit("/", 1)[-1]

        company_href, company_name = (None, None)
        if i < len(companies):
            company_href = companies[i].group(1)
            company_name = html_module.unescape(companies[i].group(2))
        if not company_name:
            continue  # can't build a usable row without a company

        company_token = company_href.rsplit("/", 1)[-1] if company_href else "unknown"
        work_type = extract_field(card, WORK_TYPE_PATTERN)
        geo_location = extract_field(card, GEO_PATTERN)
        salary = extract_field(card, SALARY_PATTERN)
        seniority_raw = extract_field(card, SENIORITY_PATTERN)
        posted = extract_field(card, POSTED_PATTERN)

        location_combined = ", ".join(x for x in [geo_location, work_type] if x)
        is_nyc, is_remote = text.classify_location(location_combined)

        records.append({
            "platform": "builtin",
            "company_token": company_token,
            "company_name": company_name,
            "source_id": job_id,
            "title": title,
            "location_raw": location_combined or None,
            "department": None,
            "job_url": f"https://www.builtinnyc.com{alias}",
            "posted_at": posted,
            "seniority_guess": SENIORITY_MAP.get((seniority_raw or "").lower(), "unknown"),
            "location_is_nyc": is_nyc,
            "location_is_remote": is_remote,
            "company_is_nyc_hq": None,   # unknown from this source -- not the same signal ingest/ats.py has
            "company_is_ai_focused": None,
            "description_text": None,    # not present on the listing page; would need a per-job detail fetch
            "raw_json": None,
            "salary_text": salary,
        })
    return records


def main():
    conn = dbconn.connect_or_exit("builtin-nyc ingest", schema=schema.SCHEMA)

    schema.ensure_schema(conn)
    job_spec = schema.spec(schema.HASH_FIELDS_BUILTIN, blank_if_falsy=("salary_text",))

    page_errors = []
    all_records = []
    for page_num in range(1, MAX_PAGES + 1):
        try:
            page_html = fetch_page(page_num)
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError) as e:
            page_errors.append(f"page {page_num}: {e}")
            if DEBUG_PRINT_KEYS:
                print(f"[debug] fetch failed for page {page_num}: {e}", file=sys.stderr)
            continue

        records = parse_page(page_html)
        all_records.extend(records)
        if DEBUG_PRINT_KEYS:
            print(f"[debug] page {page_num}: parsed {len(records)} job cards", file=sys.stderr)

        if page_num < MAX_PAGES:
            time.sleep(REQUEST_DELAY_SECONDS)

    if not all_records:
        print(f"builtin-nyc ingest FAILED: no job cards parsed across {MAX_PAGES} pages. "
              f"Errors: {page_errors}")
        conn.close()
        sys.exit(1)

    new_count, updated_count, unchanged_count = upsert(conn, job_spec, all_records, schema.make_job_id, debug=DEBUG_PRINT_KEYS)
    closed_count = schema.close_stale(conn, 'builtin', BUILTIN_STALE_AFTER_DAYS)
    state.set_watermark(conn, "builtin:nyc", utc_now_str(),
                        table=schema.WATERMARK_TABLE)
    conn.close()

    if page_errors and DEBUG_PRINT_KEYS:
        print(f"[debug] {len(page_errors)} page(s) failed: {page_errors}", file=sys.stderr)

    if new_count or updated_count or closed_count or page_errors:
        print(f"builtin-nyc: {new_count} new, {updated_count} updated, "
              f"{unchanged_count} unchanged, {closed_count} closed (stale), "
              f"{len(all_records)} parsed across {MAX_PAGES - len(page_errors)}/{MAX_PAGES} pages "
              f"({len(page_errors)} page failures).")


if __name__ == "__main__":
    main()

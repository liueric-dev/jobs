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

DESCRIPTIONS -- the listing page carries no description, so each posting
needs one extra GET of its /job/... detail page. Those pages embed
schema.org JobPosting JSON, which is where the text comes from.

Worth knowing, because it cost 187 unusable rows: the detail pages write
the MIME type HTML-escaped, `type="application/ld&#x2B;json"`. A selector
written for a literal "ld+json" therefore matches nothing, finds no
description, and reports no error -- the rows just arrive empty.
Every builtin row in the database had description_text = '' while every
other source averaged ~4,900 chars, and because scoring orders tier 1 by
first_seen DESC these newest-first rows sorted straight to the top and
consumed scoring calls on title alone. LD_JSON_PATTERN accepts both
spellings.

Detail fetches are bounded (BUILTIN_DETAIL_LIMIT, default 60/run), paced
(BUILTIN_DETAIL_DELAY, default 2.0s) and skipped for rows that already
have a description, so the backfill spreads across runs instead of
becoming one long crawl.

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

INSTALL: lives in ~/apps/jobs alongside the rest of the jobs pipeline

DATABASE: same Postgres instance/database/schema as ingest/ats.py
(the `jobs` table) -- see that script's docstring for the database
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
import json
import html as html_module
import hashlib
import time
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

DEBUG_PRINT_KEYS = os.environ.get("DEBUG_PRINT_KEYS", "") == "1"

BASE_URL = "https://www.builtinnyc.com/jobs"
MAX_PAGES = 3
REQUEST_DELAY_SECONDS = 2.5
BUILTIN_STALE_AFTER_DAYS = 14
USER_AGENT = "Mozilla/5.0 (compatible; hermes-jobs-ingest/1.0; personal job-search automation)"

#: Detail pages are one extra GET per posting, so a run is bounded and rows
#: already holding a description are never re-fetched. Raise this to backfill
#: faster; the work is resumable, so several small runs get there too.
DETAIL_FETCH_LIMIT = int(os.environ.get("BUILTIN_DETAIL_LIMIT", "60"))
DETAIL_DELAY_SECONDS = float(os.environ.get("BUILTIN_DETAIL_DELAY", "2.0"))

TITLE_PATTERN = re.compile(r'data-id="job-card-title"[^>]*data-alias="([^"]+)"[^>]*>([^<]+)<')
COMPANY_PATTERN = re.compile(r'<a href="([^"]+)"[^>]*data-id="company-title"[^>]*><span>([^<]+)</span>')
WORK_TYPE_PATTERN = re.compile(r'fa-house-building[^>]*></i></div>\s*<span[^>]*>([^<]+)</span>', re.DOTALL)
GEO_PATTERN = re.compile(r'fa-location-dot[^>]*></i></div>\s*<div><span[^>]*>([^<]+)</span>', re.DOTALL)
SALARY_PATTERN = re.compile(r'([0-9]{1,3}K-[0-9]{1,3}K[^<]*)')
SENIORITY_PATTERN = re.compile(r'(Junior|Mid level|Senior level|Entry level|Expert/Leader)')
POSTED_PATTERN = re.compile(r'fa-clock[^>]*></i>([^<]+)<', re.DOTALL)

#: The `+` in the MIME type is HTML-escaped on these pages
#: (type="application/ld&#x2B;json"), so the conventional `ld\+json` selector
#: matches nothing at all. That is exactly how the description went missing:
#: silently, with no error. Both spellings are accepted here.
LD_JSON_PATTERN = re.compile(
    r'<script[^>]*type="application/ld(?:\+|&#x2B;)json"[^>]*>(.*?)</script>',
    re.DOTALL | re.IGNORECASE)

TAG_PATTERN = re.compile(r"<[^>]+>")
WHITESPACE_PATTERN = re.compile(r"\s+")

#: Tags become spaces so list items and block elements don't run together
#: ("<li>One</li><li>Two</li>" must not read "OneTwo"), but that leaves a
#: space before punctuation whenever a tag closes mid-sentence -- "Build
#: <b>things</b>." would come out "Build things .". This puts it back.
SPACE_BEFORE_PUNCT = re.compile(r"\s+([,.;:!?%)\]])")
SPACE_AFTER_OPEN = re.compile(r"([(\[])\s+")

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


def extract_description(page_html):
    """Plain-text JobPosting description from a detail page, or None.

    Built In embeds schema.org JobPosting inside an "@graph" array rather
    than as a bare top-level object, so both shapes are handled. The
    description itself is HTML, which is unescaped and stripped to text --
    the scorer reads prose, and markup is just tokens it pays for.
    """
    for block in LD_JSON_PATTERN.findall(page_html):
        try:
            data = json.loads(block)
        except ValueError:
            continue    # one malformed block must not hide a later good one
        nodes = data.get("@graph", data) if isinstance(data, dict) else data
        for node in (nodes if isinstance(nodes, list) else [nodes]):
            if not isinstance(node, dict) or node.get("@type") != "JobPosting":
                continue
            raw = node.get("description") or ""
            if not raw:
                continue
            plain = WHITESPACE_PATTERN.sub(
                " ", TAG_PATTERN.sub(" ", html_module.unescape(raw))).strip()
            plain = SPACE_AFTER_OPEN.sub(r"\1", SPACE_BEFORE_PUNCT.sub(r"\1", plain))
            if plain:
                return plain
    return None


class RateLimited(RuntimeError):
    """The site asked us to stop. Distinct from a per-posting failure.

    Collapsing this into "no description, try the next one" is what turns a
    polite scraper into a rude one: the whole remaining budget gets spent
    hammering a host that already said no, every request fails, and nothing
    is written. Callers must abandon the pass, not continue it.
    """


def fetch_description(job_url):
    """One detail-page GET. None when this posting has no usable description.

    A posting whose detail page 404s or times out must not fail the whole
    ingest: the listing row is still worth having, and the description is
    additive. Returning None leaves the row eligible for a retry next run,
    which is the same deferral logic scoring uses for transient errors.

    429 is the exception -- see RateLimited.
    """
    req = urllib.request.Request(job_url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=http.DEFAULT_TIMEOUT) as resp:
            return extract_description(resp.read().decode("utf-8", errors="replace"))
    except urllib.error.HTTPError as e:
        if e.code == 429:
            raise RateLimited(f"HTTP 429 from {job_url}")
        if DEBUG_PRINT_KEYS:
            print(f"[debug] detail fetch failed for {job_url}: {e}", file=sys.stderr)
        return None
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        if DEBUG_PRINT_KEYS:
            print(f"[debug] detail fetch failed for {job_url}: {e}", file=sys.stderr)
        return None


def fill_descriptions(conn, budget):
    """Fetch and store descriptions for open rows that lack one.

    Runs AFTER the upsert, against the table rather than the parsed records,
    and writes with a direct UPDATE. Both of those are deliberate.

    Routing descriptions through upsert() does not work: it writes a row only
    when content_hash changes, and description_text is deliberately absent
    from HASH_FIELDS_BUILTIN (schema.py freezes those tuples). A fetched
    description therefore leaves the hash identical, the row reads as
    "unchanged", and the text is silently dropped -- which is exactly what
    happened the first time this was written. Only brand-new rows kept their
    description, because an INSERT writes every column regardless of hash.

    Working off the table also reaches postings the current listing pages no
    longer show. attach-to-records only ever covered pages 1-3 (~65 cards),
    so anything pushed deeper kept an empty description forever -- that is
    how 187 empty rows accumulated in the first place. Oldest gap first, so
    the backlog drains in a predictable order.
    """
    if budget <= 0:
        return 0, 0

    rows = conn.execute(
        f"""SELECT id, job_url FROM {schema.SCHEMA}.jobs
            WHERE platform = 'builtin' AND status = 'open'
              AND coalesce(description_text, '') = ''
              AND coalesce(job_url, '') <> ''
            ORDER BY first_seen ASC
            LIMIT %(limit)s""",
        {"limit": budget},
    ).fetchall()

    fetched = failed = 0
    limited = False
    for n, (job_id, job_url) in enumerate(rows):
        try:
            desc = fetch_description(job_url)
        except RateLimited as e:
            # Stop the pass entirely. Each row is committed as it lands, so
            # the work already done survives and the next run resumes from
            # the same "oldest gap first" position.
            limited = True
            print(f"builtin-nyc: rate limited after {fetched} descriptions "
                  f"({e}) -- stopping this pass, {len(rows) - n} still empty. "
                  f"Raise BUILTIN_DETAIL_DELAY or lower BUILTIN_DETAIL_LIMIT.")
            break
        if desc:
            conn.execute(
                f"UPDATE {schema.SCHEMA}.jobs SET description_text = %(d)s "
                f"WHERE id = %(id)s", {"d": desc, "id": job_id})
            conn.commit()
            fetched += 1
        else:
            failed += 1
        if n + 1 < len(rows):
            time.sleep(DETAIL_DELAY_SECONDS)
    return fetched, failed


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
            # posted_at stays the raw relative string Built In prints
            # ("Reposted 8 Hours Ago"): it is in HASH_FIELDS_BUILTIN, so
            # rewriting it re-hashes every row and buys nothing -- a recomputed
            # absolute time drifts between runs exactly as the phrase does.
            # posted_at_ts is unhashed, which is what makes it safe to derive.
            "posted_at_ts": text.posted_at_timestamp(posted),
            "seniority_guess": SENIORITY_MAP.get((seniority_raw or "").lower(), "unknown"),
            "location_is_nyc": is_nyc,
            "location_is_remote": is_remote,
            "company_is_nyc_hq": None,   # unknown from this source -- not the same signal ingest/ats.py has
            "company_is_ai_focused": None,
            "description_text": None,    # filled by fill_descriptions() after the upsert
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

    # After the upsert: new rows are in the table by now, so one pass covers
    # both this run's postings and the older backlog. See fill_descriptions().
    desc_fetched, desc_failed = fill_descriptions(conn, DETAIL_FETCH_LIMIT)
    closed_count = schema.close_stale(conn, 'builtin', BUILTIN_STALE_AFTER_DAYS)
    state.set_watermark(conn, "builtin:nyc", utc_now_str(),
                        table=schema.WATERMARK_TABLE)
    conn.close()

    if page_errors and DEBUG_PRINT_KEYS:
        print(f"[debug] {len(page_errors)} page(s) failed: {page_errors}", file=sys.stderr)

    if new_count or updated_count or closed_count or page_errors:
        print(f"builtin-nyc: {new_count} new, {updated_count} updated, "
              f"{unchanged_count} unchanged, {closed_count} closed (stale), "
              f"{desc_fetched} descriptions fetched ({desc_failed} failed), "
              f"{len(all_records)} parsed across {MAX_PAGES - len(page_errors)}/{MAX_PAGES} pages "
              f"({len(page_errors)} page failures).")


if __name__ == "__main__":
    main()

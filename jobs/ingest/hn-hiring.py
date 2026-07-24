#!/usr/bin/env python3
"""
Hacker News "Who is hiring?" monthly thread ingest -- Postgres edition.

Finds the current month's "Ask HN: Who is hiring?" thread (posted by the
`whoishiring` account on the 1st of each month) via the official HN Firebase
API, pulls its top-level comments, regex-parses each into a job-shaped
record, and upserts into the same `jobs` table the other ingest scripts
write to, tagged platform='hn_whoishiring'.

WHY THE FIREBASE API: https://github.com/HackerNews/API is HN's own public,
unauthenticated, official API -- no scraping, no ToS risk. Verified live:
GET /v0/user/whoishiring.json returns a `submitted` array of item ids, newest
first; the current month's hiring thread is the highest-id story whose title
starts with "Ask HN: Who is hiring?" (the account also posts companion
"Who wants to be hired?" and "Freelancer? Seeking freelancer?" threads the
same day -- both are skipped by the title check).

PARSING -- VERIFIED AGAINST LIVE THREAD DATA, NOT ASSUMED: most top-level
comments open with a single-line, pipe-delimited header before the first
HTML paragraph break, e.g.:
    "St. Jude Children's Research Hospital | Sr. Staff or Principal Software
     Engineer, Rust Genomics Infrastructure | Memphis, TN | ONSITE (2x/week)
     or REMOTE | $125,840 - $238,160 | https://www.stjude.org/"
parse_comment() splits that header on "|" into company / title / (remaining
fields treated as location text). This is a real-world convention, not an
enforced schema -- comments that don't follow it (no "|" at all, or fewer
than 2 fields) are skipped rather than guessed at, same philosophy as
ingest/ats.py's seniority tagging: don't fabricate a company/title from
freeform prose. Expect a meaningful fraction (~20-30%, per manual sampling)
of a thread's comments to be skipped this way -- that's an accepted
precision-over-recall tradeoff, not a bug.

INCREMENTAL FETCH: fetching the full comment body for every kid every day
would be ~300-900 HTTP requests/day for content that essentially never
changes after the first day or two of the month. So: the story's `kids`
list (one request) is compared against ids already present in the jobs
table for this thread's dataset key, and only *new* comment ids get their
full item body fetched. Once a thread has been fully ingested, subsequent
daily runs cost just the one `kids`-list request until next month's thread
replaces it.

CLOSE SEMANTICS -- STALENESS, NOT EXACT-DIFF, SAME REASONING AS
ingest/builtin-nyc.py: an HN hiring post has no "filled/pulled" signal --
comments aren't edited or deleted when a role closes. The only honest
signal is that next month's thread supersedes this one, so
HN_STALE_AFTER_DAYS defaults to 40 (comfortably longer than one month) --
once a thread stops being the current one long enough, its rows close.

DEPENDENCY: none beyond psycopg (same as ingest/ats.py) -- stdlib
urllib/json/re/html handle everything else.

INSTALL: lives in ~/.hermes/scripts/jobs/ alongside the rest of the jobs pipeline

DATABASE: same Postgres instance/schema as ingest/ats.py (jobs.jobs table).
This script creates the schema defensively too, so it works standalone.

CONFIG:
    DATABASE_URL -- postgres connection string (same default as ingest/ats.py)

SCHEDULE: not scheduled directly -- see run-daily.py, which is the
single cron entry point and calls this script as a subprocess.

TEST BEFORE SCHEDULING:
    python3 ingest/hn-hiring.py
    DEBUG_PRINT_KEYS=1 python3 ingest/hn-hiring.py

CONCURRENCY: this script is not scheduled directly -- run-daily.py
runs all ingest scripts sequentially so they never run concurrently.
"""

import os
import sys
import re
import html as html_module
import hashlib
import json
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

HN_API_BASE = "https://hacker-news.firebaseio.com/v0"
HIRING_TITLE_PREFIX = "ask hn: who is hiring?"
HN_STALE_AFTER_DAYS = 40
USER_AGENT = "Mozilla/5.0 (compatible; hermes-jobs-ingest/1.0; personal job-search automation)"

URL_PATTERN = re.compile(r'https?://[^\s<>"]+')


def find_latest_hiring_thread():
    """whoishiring's `submitted` list is newest-first but mixes three
    monthly threads together ("Who is hiring?", "Who wants to be hired?",
    "Freelancer? Seeking freelancer?") -- scan until the title match is
    found rather than assuming a fixed offset."""
    user = http.get_json(f"{HN_API_BASE}/user/whoishiring.json")
    for item_id in user.get("submitted", [])[:15]:
        item = http.get_json(f"{HN_API_BASE}/item/{item_id}.json")
        if item and item.get("type") == "story" and \
                (item.get("title") or "").strip().lower().startswith(HIRING_TITLE_PREFIX):
            return item
    return None


def strip_html_keep_text(text):
    if not text:
        return None
    text = html_module.unescape(text)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text or None


def parse_comment(comment, thread_id):
    if comment.get("dead") or comment.get("deleted") or comment.get("type") != "comment":
        return None

    raw_text = comment.get("text") or ""
    if not raw_text:
        return None

    header_html = re.split(r"<p>", raw_text, maxsplit=1)[0]
    header = strip_html_keep_text(header_html)
    if not header:
        return None

    parts = [p.strip() for p in header.split("|")]
    if len(parts) < 2 or not parts[0] or not parts[1]:
        return None  # doesn't follow the pipe-delimited convention -- skip, don't guess

    company_name = parts[0]
    title = parts[1]
    location_raw = " | ".join(p for p in parts[2:] if p) or None

    full_text = strip_html_keep_text(raw_text)
    is_nyc = bool(text.NYC_PATTERN.search(location_raw or "")) or bool(text.NYC_PATTERN.search(title))
    is_remote = bool(text.REMOTE_PATTERN.search(location_raw or "")) or bool(text.REMOTE_PATTERN.search(title))

    url_match = URL_PATTERN.search(raw_text.replace("&#x2F;", "/"))
    job_url = url_match.group(0) if url_match else f"https://news.ycombinator.com/item?id={comment['id']}"

    posted_at = None
    if comment.get("time"):
        posted_at = datetime.fromtimestamp(comment["time"], tz=timezone.utc).isoformat()

    return {
        "platform": "hn_whoishiring",
        "company_token": text.slugify(company_name),
        "company_name": company_name,
        "source_id": str(comment["id"]),
        "title": title,
        "location_raw": location_raw,
        "department": None,
        "job_url": job_url,
        "posted_at": posted_at,
        "seniority_guess": text.guess_seniority(title),
        "location_is_nyc": is_nyc,
        "location_is_remote": is_remote,
        "company_is_nyc_hq": None,
        "company_is_ai_focused": None,
        "description_text": (full_text or "")[:5000] or None,
        "raw_json": None,
        "thread_id": thread_id,
    }


def touch_seen(conn, platform, source_ids):
    """For kid ids already ingested in a prior run, just bump last_seen
    without re-fetching the comment body (see INCREMENTAL FETCH docstring)."""
    if not source_ids:
        return
    now = utc_now_str()
    conn.execute(
        "UPDATE jobs SET last_seen = %s WHERE platform = %s AND source_id = ANY(%s)",
        (now, platform, [str(s) for s in source_ids]),
    )
    conn.commit()


def main():
    conn = dbconn.connect_or_exit("hn-hiring ingest", schema=schema.SCHEMA)

    schema.ensure_schema(conn)
    job_spec = schema.spec(schema.HASH_FIELDS_SHORT)

    try:
        thread = find_latest_hiring_thread()
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError,
            json.JSONDecodeError, OSError) as e:
        print(f"hn-hiring ingest FAILED: could not reach HN API: {e}")
        conn.close()
        sys.exit(1)

    if thread is None:
        print("hn-hiring ingest FAILED: no 'Ask HN: Who is hiring?' thread found "
              "in whoishiring's 15 most recent submissions.")
        conn.close()
        sys.exit(1)

    # hn_seen_comments (not the jobs table) is the source of truth for "already
    # processed" -- it covers BOTH successfully-parsed comments (which also got
    # a jobs row) and unparseable ones (which never did). Without it,
    # unparseable comments would get re-fetched every single day forever,
    # defeating the "one request/day once fully ingested" point of the
    # incremental design (see module docstring).
    kid_ids = thread.get("kids", [])
    seen_rows = conn.execute(
        "SELECT comment_id FROM hn_seen_comments WHERE comment_id = ANY(%s)",
        ([str(k) for k in kid_ids],),
    ).fetchall()
    already_seen_ids = {r[0] for r in seen_rows}
    new_kid_ids = [k for k in kid_ids if str(k) not in already_seen_ids]

    touch_seen(conn, "hn_whoishiring", already_seen_ids)

    records = []
    fetch_errors = 0
    now = utc_now_str()
    for kid_id in new_kid_ids:
        try:
            comment = http.get_json(f"{HN_API_BASE}/item/{kid_id}.json")
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError,
                json.JSONDecodeError, OSError) as e:
            fetch_errors += 1
            if DEBUG_PRINT_KEYS:
                print(f"[debug] fetch failed for comment {kid_id}: {e}", file=sys.stderr)
            continue  # transient failure -- don't mark seen, retry next run
        if not comment:
            continue

        conn.execute(
            "INSERT INTO hn_seen_comments (comment_id, fetched_at) VALUES (%s, %s) "
            "ON CONFLICT (comment_id) DO NOTHING",
            (str(kid_id), now),
        )
        rec = parse_comment(comment, thread["id"])
        if rec:
            records.append(rec)
    conn.commit()

    # This source is insert-only -- a comment is never edited in place, so
    # only the new count is meaningful here.
    new_count = upsert(conn, job_spec, records, schema.make_job_id,
                       debug=DEBUG_PRINT_KEYS).new
    closed_count = schema.close_stale(conn, 'hn_whoishiring', HN_STALE_AFTER_DAYS)
    state.set_watermark(conn, "hn_whoishiring", utc_now_str(),
                        table=schema.WATERMARK_TABLE)
    conn.close()

    skipped = len(new_kid_ids) - len(records) - fetch_errors
    if DEBUG_PRINT_KEYS:
        print(f"[debug] thread {thread['id']} ({thread.get('title')}): "
              f"{len(kid_ids)} total kids, {len(already_seen_ids)} already processed, "
              f"{len(new_kid_ids)} new, {skipped} unparseable, {fetch_errors} fetch errors",
              file=sys.stderr)

    if new_count or closed_count or fetch_errors:
        print(f"hn-hiring: thread '{thread.get('title')}' -- {new_count} new, "
              f"{skipped} skipped (unparseable), {closed_count} closed (stale), "
              f"{fetch_errors} fetch errors.")


if __name__ == "__main__":
    main()

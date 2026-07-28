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

INSTALL: lives in ~/apps/jobs/backend alongside the rest of the jobs pipeline

DATABASE: same database and table as ingest/ats.py (the `jobs` table).
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

import argparse
import os
import sys
import re
import html as html_module
import hashlib
import json
import urllib.request
import urllib.error
from datetime import datetime, timedelta, timezone


# ingest/ and tools/ sit one level below the pipeline modules they import
# (schema, relevance, llm, ...). Python puts THIS file's directory on sys.path,
# not its parent, so the parent is added by hand. That same insert is what
# reaches lib/ -- there is nothing to install.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import relevance  # noqa: E402  (relevance.py -- for the role vocabulary)
import schema  # noqa: E402  (schema.py)
from lib import dbconn, http, ids, state, text  # noqa: E402
from lib.timeparse import utc_now_str  # noqa: E402
from lib.upsert import UpsertErrorRate, upsert_checked  # noqa: E402

DEBUG_PRINT_KEYS = os.environ.get("DEBUG_PRINT_KEYS", "") == "1"

HN_API_BASE = "https://hacker-news.firebaseio.com/v0"
HIRING_TITLE_PREFIX = "ask hn: who is hiring?"
HN_STALE_AFTER_DAYS = 40
USER_AGENT = "Mozilla/5.0 (compatible; hermes-jobs-ingest/1.0; personal job-search automation)"

URL_PATTERN = re.compile(r'https?://[^\s<>"]+')

#: Segments that are plainly not a job title. Used to score header fields --
#: see pick_title_segment().
COMP_PATTERN = re.compile(
    r"([$€£]|\d+\s*k\b|\bk\s*\+|\bequity\b|\bsalary\b|\bcompensation\b|"
    r"\bbonus\b|\bbenefits\b|\bper hour\b|\bhourly\b|\bcommission\b)",
    re.IGNORECASE)
EMPLOYMENT_PATTERN = re.compile(
    r"\b(full[- ]?time|part[- ]?time|contract(or)?|freelance|intern(ship)?|"
    r"permanent|temporary|c2c|w2|\d+\+?\s*(yoe|years))\b", re.IGNORECASE)
#: Keyword half of "this field describes a place or a work mode". IGNORECASE is
#: load-bearing: without it \bonsite\b misses the "ONSITE" that HN posters
#: actually write, and the field scores as neutral and can win the title slot.
PLACE_PATTERN = re.compile(
    r"(\bonsite\b|\bon[- ]site\b|\bhybrid\b|\banywhere\b|\bin[- ]person\b|"
    r"\bvisa\b|\btime\s?zone\b|\bgmt\b|\bcet\b|\butc\b|\bany country\b|"
    r"\bflexible\b|\blocation:)", re.IGNORECASE)
#: "Brooklyn, NY" / "San Francisco, CA". Case-SENSITIVE on purpose -- the
#: trailing two-letter uppercase token is the whole signal, and lowercasing it
#: would match any "word, wo" pair.
CITY_STATE_PATTERN = re.compile(r"[A-Z][a-zA-Z.\- ]+,\s*[A-Z]{2}\b")
#: A bare domain ("spruceid.com"), which URL_PATTERN misses because it has no
#: scheme. Without this, a header whose only neutral-looking field is the
#: company's website gets that website stored as the job title.
BARE_DOMAIN_PATTERN = re.compile(
    r"\b[\w-]+\.(com|io|ai|org|net|co|dev|tech|app|xyz|so|sh|com?\.[a-z]{2})\b",
    re.IGNORECASE)
#: Longest plausible job title. Measured against the longest correctly-parsed
#: title in the current thread ("Senior/Staff Software Engineer - AI / Agentic
#: apps", 50 chars); 100 leaves generous headroom while still excluding a field
#: that has swallowed the comment body.
MAX_TITLE_CHARS = 100


def _python_role_pattern():
    """"Does this text look like a job title?", from config/relevance.json.

    Reuses title_include so the role vocabulary lives in ONE place -- the same
    file relevance.py tiers on -- rather than being duplicated here. That is
    what keeps this script domain-neutral: pointing the pipeline at nursing
    roles means editing that config, not this parser.

    The patterns are POSTGRES regexes, where a word boundary is \\y. Python's re
    rejects \\y outright ("bad escape"), so it is translated to \\b, which means
    the same thing in Python's dialect. Translating is safe in this direction
    and only in this direction: every other construct in that file (`back.?end`,
    `full.?stack`) is already common to both dialects.
    """
    patterns = relevance.load().get("title_include") or []
    if not patterns:
        return None
    try:
        return re.compile("|".join(p.replace("\\y", "\\b") for p in patterns),
                          re.IGNORECASE)
    except re.error:
        # A pattern only Postgres can parse must not take the ingest down; the
        # positional fallback in pick_title_segment() is still correct.
        return None


ROLE_PATTERN = _python_role_pattern()


def _segment_score(segment):
    """Higher means "more likely to be the role", for one header field.

    The positive signal is only a tie-breaker, not a requirement. title_include
    is this persona's relevance vocabulary, not a general definition of "job
    title", so real titles it does not list -- "Chief Technology Officer",
    "Senior Technical Program Manager", "Founding GTM Lead", "Technical
    Co-Founder" -- score a neutral 0 and must stay eligible. The work is done
    by the NEGATIVE signals: a field is rejected for looking like a place, a
    salary, an employment type or a URL, not for failing to look like a role.
    """
    score = 0
    if ROLE_PATTERN and ROLE_PATTERN.search(segment):
        score += 3
    if text.REMOTE_PATTERN.search(segment) or text.NYC_PATTERN.search(segment):
        score -= 2
    if PLACE_PATTERN.search(segment) or CITY_STATE_PATTERN.search(segment):
        score -= 2
    if COMP_PATTERN.search(segment):
        score -= 3
    if EMPLOYMENT_PATTERN.search(segment):
        score -= 2
    if URL_PATTERN.search(segment) or BARE_DOMAIN_PATTERN.search(segment):
        score -= 4
    # A field this long is not a job title -- it is the comment body. The
    # header is split on the first "<p>", so a poster who writes no paragraph
    # break leaves the whole comment in the last pipe field, and rows like
    # "Full Time LiveKit is building the infrastructure layer for the voi..."
    # get stored as titles. Length is the only signal that separates those from
    # a genuinely long title, and real ones do not run past ~100 characters.
    if len(segment) > MAX_TITLE_CHARS:
        score -= 3
    return score


def pick_title_segment(parts):
    """(title, location_text) from the pipe-delimited fields after the company.

    THE CONVENTION IS NOT A SCHEMA
        HN's informal header is "Company | Role | Location | Type | URL", and
        the previous implementation took parts[1] as the title unconditionally.
        Posters do not agree on the order, so 52 of 247 stored rows held
        something else entirely in `title`:

            SmarterDx        -> "150-250k+ + equity + benefits"
            Rail Europe      -> "Hiring in Paris and REMOTE"  (location "Senior SWE")
            SpruceID (YC W21)-> "REMOTE (US-Based Preferred)"

        Those are unusable in a listing and they poison guess_seniority() and
        the relevance title filter downstream.

    So: score every field after the company and take the best one, keeping the
    rest as location text in its original order. Ties go to the earliest field,
    so a header whose fields are indistinguishable is read exactly as before.

    RETURNS (None, None) WHEN EVERY FIELD LOOKS LIKE SOMETHING ELSE
        Some headers genuinely contain no title: "Junior | Remote | Any Time
        Zone" is a company, a work mode and a timezone. "SpruceID (YC W21) |
        REMOTE (US-Based Preferred) | Full-Time | spruceid.com" never says the
        role. Those are skipped rather than having "Any Time Zone" stored as a
        job title -- the same precision-over-recall trade this module's
        docstring already makes for comments with no pipes at all.

        The bar is score >= 0, i.e. "nothing marks this as a place, a salary, an
        employment type or a URL" -- NOT "matches title_include". Requiring a
        positive score was measured against all 247 stored rows and skipped 72
        of them, including real titles like "Chief Technology Officer"; this bar
        skips 30 and fixes 24, with no row made worse.
    """
    candidates = [p for p in parts[1:] if p]
    if not candidates:
        return None, None
    best_i, best_score = 0, _segment_score(candidates[0])
    for i, seg in enumerate(candidates[1:], start=1):
        s = _segment_score(seg)
        if s > best_score:
            best_i, best_score = i, s
    if best_score < 0:
        return None, None
    title = candidates[best_i]
    rest = [seg for i, seg in enumerate(candidates) if i != best_i]
    return title, (" | ".join(rest) or None)


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
    title, location_raw = pick_title_segment(parts)
    if not title:
        return None

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
        "posted_at_ts": text.posted_at_timestamp(posted_at),
        "salary_text": None,
        "seniority_guess": text.guess_seniority(title),
        "location_is_nyc": is_nyc,
        "location_is_remote": is_remote,
        "company_is_nyc_hq": None,
        "company_is_ai_focused": None,
        "description_text": (full_text or "")[:text.MAX_DESCRIPTION_CHARS] or None,
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
    ap = argparse.ArgumentParser(description="HN 'Who is hiring?' ingest.")
    ap.add_argument(
        "--reparse", action="store_true",
        help="re-fetch and re-parse comments already in hn_seen_comments. "
             "Needed after a parser change: the ledger is what makes the daily "
             "run cheap, and it also makes a fix invisible to existing rows.")
    args = ap.parse_args()

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
    if args.reparse:
        # Deliberately re-fetches every comment in the current thread: a parser
        # change is exactly the case the ledger's cheapness hides, because a
        # fixed title is invisible to a row that is never re-read. Costs one
        # request per comment, once, against HN's own API.
        new_kid_ids = list(kid_ids)
        print(f"hn-hiring: --reparse, re-reading all {len(kid_ids)} comments "
              f"({len(already_seen_ids)} were already in the ledger)")
    else:
        new_kid_ids = [k for k in kid_ids if str(k) not in already_seen_ids]

    touch_seen(conn, "hn_whoishiring", already_seen_ids)

    records = []
    declined = []          # comment ids re-read but yielding no usable record
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
        else:
            declined.append(str(kid_id))
    conn.commit()

    # This source is insert-only -- a comment is never edited in place, so
    # only the new count is meaningful here. The ERROR count is meaningful
    # everywhere, though, which is why `.new` alone was not enough: a comment
    # whose row failed to write is already marked seen in hn_seen_comments
    # above, so it is never retried and is lost for the life of the thread.
    upsert_failure = None
    try:
        result = upsert_checked(conn, job_spec, records, schema.make_job_id,
                                debug=DEBUG_PRINT_KEYS)
    except UpsertErrorRate as e:
        result, upsert_failure = e.result, e
    new_count = result.new

    # A --reparse that now DECLINES a comment must retire the row it wrote
    # under the old parser, because a skipped comment produces no record and
    # upsert therefore never touches the stale row. Without this, fixing the
    # parser leaves exactly the rows it was meant to fix -- 19 titles reading
    # "REMOTE (US)" or a swallowed comment body -- sitting there open forever.
    #
    # Closed, not deleted: that is this pipeline's convention everywhere
    # (close_stale, close_missing), it keeps the row inspectable, it excludes
    # it from extract/match/the app, and prune_old_closed eventually collects
    # it. Scoped to comments actually re-read on this run, so a fetch failure
    # can never close anything.
    retired_count = 0
    if args.reparse and declined:
        retired_count = conn.execute(
            f"UPDATE {schema.TABLE} SET status = %s, closed_at = %s "
            f"WHERE platform = 'hn_whoishiring' AND status = %s "
            f"  AND source_id = ANY(%s)",
            (schema.STATUS_CLOSED, now, schema.STATUS_OPEN, declined),
        ).rowcount
        conn.commit()
        print(f"hn-hiring: retired {retired_count} row(s) whose comment no "
              f"longer yields a usable title ({len(declined)} declined).")

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

    if new_count or closed_count or fetch_errors or result.errors:
        print(f"hn-hiring: thread '{thread.get('title')}' -- {new_count} new, "
              f"{skipped} skipped (unparseable), {closed_count} closed (stale), "
              f"{len(result.errors)} record(s) dropped, "
              f"{fetch_errors} fetch errors.")

    if upsert_failure:
        print(f"hn-hiring ingest FAILED: {upsert_failure}")
        sys.exit(1)


if __name__ == "__main__":
    main()

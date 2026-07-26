"""
Claim/staleness/normalization logic for the crowdsourced jobs API.

RELATIONSHIP TO ~/.hermes/scripts/jobs/: this is a deliberate, self-contained
REIMPLEMENTATION of the claim algorithm proven in that pipeline's
ingest/google-serpapi.py -- NOT an import of it. There is intentionally zero
code dependency between this repo and ~/.hermes (which is the private Hermes
harness directory, holding cron scripts, not servers). That pipeline already
uses this same convention internally: ingest/builtin-nyc.py keeps its own
defensive copy of ensure_schema() so it works standalone rather than importing
from a sibling.

WHY DUPLICATION IS SAFE HERE: correctness does NOT live in shared application
code -- it lives in a single Postgres row. Both this service and the existing
local scripts serialize through the same job_ingest_state row (keyed
'google_jobs:query:<slug>') using the same atomic
INSERT ... ON CONFLICT ... WHERE claimed_at IS NULL OR expired. Postgres
row-level locking makes the "two claimants never get the same query"
guarantee hold across two entirely separate codebases automatically. If you
change the claim SQL here, it stays compatible as long as it keeps operating
on that same row with that same conditional-update shape.

SCHEMA OWNERSHIP: this module only ADDs (CREATE TABLE IF NOT EXISTS /
ALTER TABLE ADD COLUMN IF NOT EXISTS). It never drops or rewrites columns the
~/.hermes pipeline owns. The two columns added beyond what that pipeline knows
about are job_ingest_state.claimed_by and .claim_granted_at -- the existing
scripts never populate either, which is fine: lock correctness keys on
claimed_at alone, and these two exist only so /submit can verify a contributor
still owns the claim they're submitting against. See holds_claim() for the
concrete takeover race they defend against (found by testing this service
against that pipeline's real SQL, not theorized).
"""

import os
import re
import json
import base64
import html as html_module
import hashlib
import urllib.parse
from datetime import datetime, timedelta, timezone

DATABASE_URL = os.environ.get(
    "DATABASE_URL", "postgresql://nyc_events@localhost:5432/nyc_events"
)

#: Every table this service touches, and the exact privileges it needs on each.
#: The role in DATABASE_URL is granted these and nothing else -- no DELETE
#: anywhere, no DDL, and no access to the ten pipeline-owned tables in the same
#: schema or to public.events. app.py verifies this at startup instead of
#: creating anything, because a service that faces untrusted input should not
#: hold schema-modification rights.
#:
#: google_jobs_query_stats needs SELECT despite being write-only from this
#: service's point of view: log_query_stats() uses
#: `INSERT ... ON CONFLICT (slug, run_at) DO NOTHING`, and Postgres requires
#: SELECT on the conflict target to evaluate the arbiter index. Granting INSERT
#: alone fails at runtime with "permission denied", not at deploy time -- which
#: is exactly why verify_schema() checks privileges and not just existence.
REQUIRED_TABLES = {
    "jobs": ("SELECT", "INSERT", "UPDATE"),
    "job_ingest_state": ("SELECT", "INSERT", "UPDATE"),
    "google_jobs_query_stats": ("SELECT", "INSERT"),
    "contributors": ("SELECT", "INSERT"),
    "api_keys": ("SELECT", "INSERT", "UPDATE"),
    "submission_log": ("SELECT", "INSERT"),
}
GOOGLE_QUERIES_FILE = os.environ.get(
    "GOOGLE_QUERIES_FILE",
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "config", "google-queries.json"),
)

# Mirrors ~/.hermes/scripts/jobs/ingest/google-serpapi.py's values -- keep in
# sync conceptually; they're independent constants, not shared state.
CLAIM_TTL_MINUTES = int(os.environ.get("CLAIM_TTL_MINUTES", "15"))
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


# --------------------------------------------------------------------------
# Schema
# --------------------------------------------------------------------------

def ensure_schema(conn):
    """Additive only -- safe to run against a database the ~/.hermes pipeline
    already created and actively uses. Creates the jobs.* tables if this
    service happens to run first, and adds the api/contributor tables that
    are unique to this service."""
    conn.execute("CREATE SCHEMA IF NOT EXISTS jobs")
    conn.execute("SET search_path TO jobs, public")

    # Identical definition to the ~/.hermes pipeline's -- a no-op there, and
    # makes this service standalone-runnable against a fresh database.
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
    conn.execute("""
        CREATE TABLE IF NOT EXISTS job_ingest_state (
            dataset TEXT PRIMARY KEY,
            last_success_at TEXT NOT NULL
        )
    """)
    conn.execute("ALTER TABLE job_ingest_state ADD COLUMN IF NOT EXISTS claimed_at TEXT")
    # New vs the ~/.hermes pipeline: records WHO holds a claim, so /submit can
    # reject a contributor submitting against someone else's claim.
    conn.execute("ALTER TABLE job_ingest_state ADD COLUMN IF NOT EXISTS claimed_by TEXT")
    # Snapshot of claimed_at at the moment THIS service granted the claim.
    # See holds_claim() for why comparing it against the live claimed_at is
    # what makes ownership safe against the ~/.hermes pipeline taking over.
    conn.execute("ALTER TABLE job_ingest_state ADD COLUMN IF NOT EXISTS claim_granted_at TEXT")
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

    # Tables owned solely by this service.
    conn.execute("""
        CREATE TABLE IF NOT EXISTS contributors (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            created_at TEXT NOT NULL,
            notes TEXT
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS api_keys (
            key_hash TEXT PRIMARY KEY,
            contributor_id TEXT NOT NULL REFERENCES contributors(id),
            label TEXT,
            created_at TEXT NOT NULL,
            revoked_at TEXT
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_api_keys_contributor ON api_keys(contributor_id)")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS submission_log (
            id BIGSERIAL PRIMARY KEY,
            contributor_id TEXT NOT NULL,
            dataset TEXT NOT NULL,
            submitted_at TEXT NOT NULL,
            fetched_count INTEGER NOT NULL,
            accepted_count INTEGER NOT NULL,
            rejected_count INTEGER NOT NULL,
            reason TEXT
        )
    """)
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_submission_log_contrib_time "
        "ON submission_log(contributor_id, submitted_at)"
    )
    conn.commit()


# --------------------------------------------------------------------------
# Claiming
# --------------------------------------------------------------------------

def try_claim_query(conn, dataset, now_dt, claimed_by):
    """Atomic claim -- succeeds only if nobody holds an unexpired claim.

    Byte-for-byte the same conditional-update shape the ~/.hermes pipeline
    uses (see module docstring), with claimed_by added. The empty-string
    last_success_at on first INSERT matches that pipeline's "never run"
    sentinel -- it must stay '' and not NULL, both because the column is
    NOT NULL and because stalest-first ordering relies on '' sorting first.
    """
    now_str = now_dt.strftime("%Y-%m-%dT%H:%M:%S")
    ttl_cutoff_str = (now_dt - timedelta(minutes=CLAIM_TTL_MINUTES)).strftime("%Y-%m-%dT%H:%M:%S")
    cur = conn.execute(
        """
        INSERT INTO job_ingest_state (dataset, last_success_at, claimed_at, claimed_by, claim_granted_at)
        VALUES (%(dataset)s, '', %(now)s, %(by)s, %(now)s)
        ON CONFLICT (dataset) DO UPDATE
            SET claimed_at = %(now)s, claimed_by = %(by)s, claim_granted_at = %(now)s
            WHERE job_ingest_state.claimed_at IS NULL OR job_ingest_state.claimed_at < %(ttl_cutoff)s
        RETURNING dataset
        """,
        {"dataset": dataset, "now": now_str, "ttl_cutoff": ttl_cutoff_str, "by": claimed_by},
    )
    won = cur.fetchone() is not None
    conn.commit()
    return won


def holds_claim(conn, dataset, contributor_id, now_dt):
    """True only if this contributor holds a live, unexpired claim that nobody
    has taken over since it was granted.

    THE TAKEOVER PROBLEM (found by testing against the real ~/.hermes SQL, not
    theorized): that pipeline's claim statement sets claimed_at but has no
    knowledge of claimed_by, so it never clears it. Sequence that breaks a
    naive `claimed_by == caller` check:

        1. This API grants query X to contributor C   (claimed_by='C')
        2. C stalls; the claim expires after CLAIM_TTL_MINUTES
        3. Eric's local pipeline legitimately claims X -- it updates
           claimed_at to now, leaving claimed_by='C' STALE
        4. C finally submits. A naive check sees claimed_by=='C' and a fresh
           claimed_at, and lets C write results and call mark_success() --
           clobbering the watermark while the local pipeline is mid-fetch.

    THE FIX: claim_granted_at records what claimed_at was when THIS service
    granted the claim. Any takeover by anyone necessarily rewrites claimed_at
    (both systems set it to their own `now`), so the two stop matching. They
    can only still be equal if nothing has re-claimed since -- and a genuine
    takeover requires the claim to have expired first, meaning at least
    CLAIM_TTL_MINUTES separates the two timestamps. There is no same-instant
    edge case to worry about.

    This is why no changes to ~/.hermes are needed: the guard lives entirely
    on this side, and treats any unexpected mutation of claimed_at as a lost
    claim.
    """
    ttl_cutoff_str = (now_dt - timedelta(minutes=CLAIM_TTL_MINUTES)).strftime("%Y-%m-%dT%H:%M:%S")
    row = conn.execute(
        "SELECT claimed_by, claimed_at, claim_granted_at FROM job_ingest_state WHERE dataset = %s",
        (dataset,),
    ).fetchone()
    if row is None:
        return False
    claimed_by, claimed_at, claim_granted_at = row
    if claimed_by != contributor_id or not claimed_at:
        return False
    if claim_granted_at != claimed_at:
        return False  # somebody re-claimed this after it was granted
    return claimed_at >= ttl_cutoff_str


def mark_success(conn, dataset, ts):
    """Advances last_success_at and releases the claim in one write.

    CRITICAL: this is the ONLY thing that may advance last_success_at, and it
    must run only after results are actually stored. That invariant is what
    makes the whole pipeline resume correctly after failures -- a failed run
    leaves the watermark untouched, so the next run's date-chip widens to
    cover the true gap instead of silently skipping it."""
    conn.execute(
        """
        INSERT INTO job_ingest_state (dataset, last_success_at, claimed_at, claimed_by, claim_granted_at)
        VALUES (%s, %s, NULL, NULL, NULL)
        ON CONFLICT (dataset) DO UPDATE
            SET last_success_at = EXCLUDED.last_success_at, claimed_at = NULL,
                claimed_by = NULL, claim_granted_at = NULL
        """,
        (dataset, ts),
    )
    conn.commit()


def release_claim(conn, dataset):
    """Called when a contributor's fetch FAILS -- frees the query immediately
    so another contributor (with a different SerpApi account, which may not
    share the same transient error/quota exhaustion) can retry right away
    instead of waiting out CLAIM_TTL_MINUTES."""
    conn.execute(
        "UPDATE job_ingest_state SET claimed_at = NULL, claimed_by = NULL, claim_granted_at = NULL WHERE dataset = %s",
        (dataset,),
    )
    conn.commit()


def log_query_stats(conn, slug, new_count, total_fetched, days_since_last_run):
    conn.execute(
        """
        INSERT INTO google_jobs_query_stats (slug, run_at, new_count, total_fetched, days_since_last_run)
        VALUES (%s, %s, %s, %s, %s)
        ON CONFLICT (slug, run_at) DO NOTHING
        """,
        (slug, utc_now_str(), new_count, total_fetched, days_since_last_run),
    )
    conn.commit()


def load_query_buckets():
    with open(GOOGLE_QUERIES_FILE) as f:
        return json.load(f)["buckets"]


def pick_stale_queries_by_bucket(conn, buckets, claimed_by, max_queries=None):
    """Per-bucket least-recently-run selection with atomic claiming.

    Same algorithm as the ~/.hermes pipeline: within each bucket, walk
    candidates stalest-first and attempt a claim on each until the bucket's
    daily_budget is met. A candidate already claimed by someone else is
    skipped in favor of the next-stalest -- that's what load-balances across
    contributors with no static per-contributor assignment.

    The MIN_HOURS_BETWEEN_RUNS guard breaks out of a bucket entirely on the
    first too-recent candidate: because ordering is stalest-first, everything
    after it is even fresher, so the bucket's work for this interval is
    already done and spending more of the budget would just re-fetch a window
    someone else already covered.

    max_queries caps the total returned to one caller (the per-request 'max'),
    independently of the per-bucket budgets.
    """
    picked = []
    now_dt = datetime.now(timezone.utc)
    too_recent_cutoff = (now_dt - timedelta(hours=MIN_HOURS_BETWEEN_RUNS)).strftime("%Y-%m-%dT%H:%M:%S")

    for bucket in buckets.values():
        if max_queries is not None and len(picked) >= max_queries:
            break
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
            if max_queries is not None and len(picked) >= max_queries:
                break
            if watermarks.get(q["slug"], "") > too_recent_cutoff:
                break  # stalest-first: everything remaining ran even more recently
            dataset = f"google_jobs:query:{q['slug']}"
            if try_claim_query(conn, dataset, now_dt, claimed_by):
                picked.append((q, watermarks.get(q["slug"])))
                claimed_in_bucket += 1
    return picked


def choose_date_chip(last_run_str):
    """None (never run) -> no chip at all, the deliberate backfill case.
    Otherwise narrow to the bucket covering the actual gap since that query's
    last SUCCESS -- not always 'today', which is what makes failure recovery
    self-healing."""
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


# --------------------------------------------------------------------------
# Normalization -- ALWAYS run server-side, never trusted from the client
# --------------------------------------------------------------------------

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


# -- Google Jobs posting identity --------------------------------------------
#
# THE ONE PLACE THIS SERVICE AND ~/.hermes MUST AGREE, despite sharing no code.
# The module docstring above explains why duplication is normally safe here:
# correctness lives in a Postgres row, not in shared application code. This is
# the exception. source_id feeds make_id(), which IS the dedup key -- if this
# file derives it differently from
# ~/.hermes/scripts/pipelib/ids.py:google_source_id(), the same posting
# submitted by a contributor and ingested locally becomes two rows, silently.
# Any change here is a change there, in the same commit.
#
# WHY NOT THE RAW job_id: it is a base64 JSON blob carrying the search context
# that produced it, including an `fc` token that rotates on every fresh fetch
# from Google and `hl`/`gl` keys that come and go. Hashing it minted a new
# primary key for an already-stored posting on every run -- measured at 32%
# duplicate rows (837 rows holding 632 real postings) on the live table before
# this was fixed. `htidocid`, inside the same blob, is the stable part.

_TRACKING_PARAMS = re.compile(r"^(utm_|gclid|fbclid|ref|source$)", re.I)


def decode_google_job_id(job_id):
    """Google's base64 job_id blob as a dict, or None if it isn't one."""
    if not job_id:
        return None
    try:
        padded = job_id + "=" * (-len(job_id) % 4)
        decoded = json.loads(base64.b64decode(padded))
    except Exception:
        return None
    return decoded if isinstance(decoded, dict) else None


def normalize_apply_url(url):
    """Drop tracking params and the fragment, so one posting has one URL."""
    if not url:
        return ""
    try:
        parts = urllib.parse.urlsplit(url)
    except ValueError:
        return url
    kept = [(k, v) for k, v in urllib.parse.parse_qsl(parts.query)
            if not _TRACKING_PARAMS.match(k)]
    return urllib.parse.urlunsplit(
        (parts.scheme, parts.netloc, parts.path.rstrip("/"),
         urllib.parse.urlencode(sorted(kept)), ""))


def google_source_id(job, company_token, length=16):
    """htidocid, else a fingerprint over (company, title, apply URL).

    Location is deliberately excluded: Google reports the same remote posting
    as "United States" on one search and "Anywhere" on another.
    """
    decoded = decode_google_job_id(job.get("job_id"))
    if decoded and decoded.get("htidocid"):
        return decoded["htidocid"]

    apply_options = job.get("apply_options") or []
    url = (apply_options[0].get("link") if apply_options else None) or job.get("share_link")
    key = "|".join((
        str(company_token or ""),
        " ".join(str(job.get("title") or "").lower().split()),
        normalize_apply_url(url),
    ))
    return "fp:" + hashlib.sha256(key.encode()).hexdigest()[:length]


def normalize_job(job, mode):
    """Derives every stored field from the RAW posting payload.

    SECURITY-RELEVANT: the API must call this on what a contributor uploads
    rather than accepting client-computed fields. platform/company_token/
    source_id feed make_id(), which is the cross-source dedup key -- letting a
    client set those directly would let a hostile contributor overwrite
    arbitrary existing rows (e.g. claiming a Greenhouse posting's id and
    replacing its URL). Recomputing here means the worst a bad payload can do
    is insert junk under its own derived id, never clobber another source's.

    That guarantee now rests on google_source_id() above rather than on the
    raw job_id -- note this makes the derivation depend on a field a
    contributor controls (the apply URL) only in the fallback branch, which is
    still client-derived-but-recomputed, never client-supplied.
    """
    title = job.get("title")
    company_name = job.get("company_name") or "Unknown"
    location = job.get("location")
    detected = job.get("detected_extensions") or {}
    apply_options = job.get("apply_options") or []
    company_token = slugify(company_name)

    is_nyc = bool(NYC_PATTERN.search(location or ""))
    is_remote = bool(REMOTE_PATTERN.search(location or "")) or mode == "remote"

    return {
        "platform": "google_jobs",
        "company_token": company_token,
        "company_name": company_name,
        "source_id": google_source_id(job, company_token),
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
    """Identical upsert semantics to the ~/.hermes pipeline, so rows written
    via this API are indistinguishable from locally-ingested ones (same id
    derivation, same content_hash change detection, same reopen-on-resee)."""
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

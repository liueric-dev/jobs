"""
Claim/staleness/normalization logic for the crowdsourced jobs API.

RELATIONSHIP TO THE PIPELINE -- REWRITTEN IN SLICE D, AND THE OLD VERSION OF
THIS PARAGRAPH IS WORTH KNOWING ABOUT. It used to say this file was a
deliberate, self-contained REIMPLEMENTATION with "intentionally zero code
dependency", on the argument that correctness lives in a Postgres row rather
than in shared application code.

That argument was right about the *claim*, and wrong about everything else.
Row-level locking really does make "two claimants never get the same query"
hold across two codebases, and try_claim_query() below is still deliberately
its own SQL for that reason. But the rest of what this file had copied was not
protected by any row: nine functions and the DDL for three tables, which had
drifted six ways by the time slice D measured them --

    strip_html truncated at 5000 where pipelib uses 20000
    parse_relative_posted_at knew neither minutes, "an hour ago", nor
        "yesterday", and returned None where the pipeline returned a timestamp
    raw_json sliced serialized JSON mid-string instead of bounded_json
    posted_at_ts and salary_text were missing from normalize_job, from the
        CREATE TABLE, and from the upsert column lists
    upsert had no per-record SAVEPOINT, so one bad row lost a whole batch
    the job_ingest_state migration took an unnecessary exclusive lock

The first two change content_hash, which is row identity for ~23,500 stored
digests: the same posting written by the pipeline and then through this API
produced two different digests, so each write counted the other's row as
"updated" and rewrote it. That was latent only because this service has never
been deployed. So the two are now co-located in one repo and this file imports
what it used to copy.

WHAT IS STILL DELIBERATELY SEPARATE: the claim SQL (try_claim_query,
holds_claim, mark_success, release_claim). It is a superset of pipelib.state's
-- it adds claimed_by and claim_granted_at -- because this service must answer
"does this contributor still own the claim they are submitting against?", a
question the pipeline never asks. Keep it operating on the same row with the
same conditional-update shape and it stays compatible.

SCHEMA OWNERSHIP: ../schema.py owns the jobs table, the watermark table and
google_jobs_query_stats; ensure_schema() below calls it rather than restating
it. This module declares only the three contributor tables and the two extra
claim columns, and never drops or rewrites anything the pipeline owns.
"""

import os
import sys
from datetime import datetime, timedelta, timezone

# api/ sits one level below the pipeline modules it shares code with. Python
# puts THIS file's directory on sys.path, not its parent. pipelib needs nothing
# here either -- but note this venv has include-system-site-packages = false,
# so it needs its own `pip install -e ~/apps/pipelib`; the user-site copy the
# pipeline uses is invisible in here.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import schema  # noqa: E402  (../schema.py -- the pipeline owns the jobs DDL)
from google_jobs import normalize_job  # noqa: E402,F401  (re-exported; app.py calls it)
from pipelib import dbconn  # noqa: E402
from pipelib.timeparse import utc_now_str  # noqa: E402
from pipelib.upsert import upsert as _pipelib_upsert  # noqa: E402

#: The same spec ingest/google-serpapi.py builds, so both write identical rows.
#: HASH_FIELDS_SHORT is the Google-source hash field set; using a different one
#: here would give the same posting two identities.
_JOB_SPEC = schema.spec(schema.HASH_FIELDS_SHORT)

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

#: submission_log.id is BIGSERIAL, so INSERT on the table is not enough on its
#: own -- the nextval() needs USAGE on the sequence. README's privilege table
#: has always listed this; until slice D nothing verified it, which made it the
#: one documented grant whose absence surfaced as a 500 on a contributor's
#: first submit rather than as a startup error.
REQUIRED_SEQUENCES = {
    "submission_log_id_seq": ("USAGE", "SELECT"),
}
#: One level up, because the query bank is shared with the pipeline's
#: ingest/google-serpapi.py. Until slice D this file had its own byte-identical
#: copy -- two files that had to agree and nothing making them.
GOOGLE_QUERIES_FILE = os.environ.get(
    "GOOGLE_QUERIES_FILE",
    os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                 "config", "google-queries.json"),
)

# Mirrors ingest/google-serpapi.py's values -- independent constants, not
# shared state, because a contributor's client and the local pipeline may
# legitimately want different pacing.
CLAIM_TTL_MINUTES = int(os.environ.get("CLAIM_TTL_MINUTES", "15"))
MIN_HOURS_BETWEEN_RUNS = float(os.environ.get("GOOGLE_JOBS_MIN_HOURS_BETWEEN_RUNS", "20"))

# --------------------------------------------------------------------------
# Schema
# --------------------------------------------------------------------------

def ensure_schema(conn):
    """Create what this service needs, delegating everything it does not own.

    Only `manage_users.py init-schema` reaches here, on the admin credential.
    The service itself holds no DDL rights at all and verifies at startup
    instead -- see app.verify_schema().

    WHO OWNS WHAT. The `jobs` table, the watermark table and
    google_jobs_query_stats belong to the pipeline, so ../schema.py declares
    them and this calls it. Until slice D this file re-declared all three from
    its own copy of the DDL, and they had already drifted: this copy was
    missing posted_at_ts and salary_text, so a fresh database created by
    init-schema produced a `jobs` table the pipeline then had to ALTER, and
    every row written through the API sorted last forever under the app view's
    `ORDER BY posted_at_ts DESC NULLS LAST`.

    The three contributor tables below are genuinely this service's own -- the
    pipeline has no concept of them -- as are two of the claim columns.
    """
    conn.execute("SET search_path TO jobs, public")

    # The pipeline's DDL, from the pipeline. Idempotent, and a no-op against a
    # database it already created. This also brings the app view and the
    # foreign-key cascade repair, which is fine: init-schema is an admin
    # command run deliberately, not something the request path touches.
    schema.ensure_schema(conn)

    # Beyond what the pipeline knows about: WHO holds a claim, so /submit can
    # reject a contributor submitting against someone else's, and a snapshot of
    # claimed_at at the moment this service granted it. See holds_claim() for
    # the takeover race those two defend against. state.ensure_state_schema()
    # supplies claimed_at itself, via with_claims=True.
    #
    # add_missing_columns rather than ALTER ... ADD COLUMN IF NOT EXISTS: the
    # IF NOT EXISTS form still takes an ACCESS EXCLUSIVE lock when it is a
    # no-op, and a pending exclusive lock queues ahead of readers, so a
    # long-lived transaction elsewhere turns a no-op migration into an outage.
    dbconn.add_missing_columns(conn, schema.WATERMARK_TABLE, [
        ("claimed_by", "TEXT"),
        ("claim_granted_at", "TEXT"),
    ])

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

    Byte-for-byte the same conditional-update shape the pipeline
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

    THE TAKEOVER PROBLEM (found by testing against the pipeline's real SQL, not
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

    This is why no changes to the pipeline are needed: the guard lives entirely
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

    Same algorithm as the pipeline: within each bucket, walk
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


# --------------------------------------------------------------------------
# Normalization -- ALWAYS run server-side, never trusted from the client
# --------------------------------------------------------------------------
#
# normalize_job is imported from ../google_jobs.py, which the pipeline's two
# Google ingest scripts also import. This used to be ~130 lines of copies here:
# strip_html, slugify, guess_seniority, parse_relative_posted_at,
# decode_google_job_id, normalize_apply_url, google_source_id, content_hash,
# make_id and normalize_job itself.
#
# The comment those copies carried was right about the stakes and wrong about
# the remedy. It said source_id feeds make_id(), which IS the dedup key, so
# deriving it differently from pipelib.ids.google_source_id() silently turns
# one posting into two rows -- and concluded "any change here is a change
# there, in the same commit". That is a rule a person has to remember. One
# import is a rule the interpreter enforces.

def upsert(conn, records):
    """Write postings exactly the way the pipeline's ingest scripts do.

    This is now literally the same code path -- pipelib.upsert with the same
    TableSpec (schema.HASH_FIELDS_SHORT) and the same id function -- rather
    than a reimplementation of it. Rows written through this API are therefore
    indistinguishable from locally-ingested ones by construction, not by two
    files agreeing.

    What that buys beyond tidiness: pipelib.upsert opens a SAVEPOINT per
    record. The hand-rolled version this replaces did not, and on Postgres a
    single failed statement aborts the whole transaction -- so one malformed
    posting in a contributor's batch of 50 took the other 49 with it, returned
    a 500, wrote no submission_log row, never called mark_success, and spent
    the contributor's SerpApi credit for nothing.

    Returns (new, updated, unchanged); pipelib's UpsertResult unpacks to that
    triple, and also carries .errors, which the caller may report.
    """
    result = _pipelib_upsert(conn, _JOB_SPEC, records, schema.make_job_id)
    conn.commit()
    return result

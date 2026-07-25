"""The `jobs.jobs` table -- DDL, column specs, and lifecycle helpers.

Owned by the jobs pipeline, deliberately not by pipelib: pipelib provides
mechanism (upsert, retry, hashing, checkpoints, claims) and knows nothing
about what a job listing is. This module is the single definition the six
ingest scripts and score.py share, replacing six separately-drifting copies
of ensure_schema() -- one of which (ingest/google-serpapi.py) described
itself in a comment as a "Defensive duplicate of ingest/ats.py's".

SCHEMA, NOT DATABASE
    These tables live in a Postgres schema called `jobs`, inside the same
    database as `public.events`. search_path is per-connection, so every
    connection must set it -- pipelib.dbconn.connect(schema="jobs") does,
    including the per-thread connections score.py opens. Getting this wrong
    does not error; it silently reads and writes `public`.

HASH FIELDS ARE PER SOURCE, DELIBERATELY
    The six scripts did NOT hash the same fields, and that is correct rather
    than drift: ats and weworkremotely include `department`; builtin-nyc
    includes `seniority_guess` and `salary_text` but no description; the
    Google and HN sources hash a shorter set. Each tuple below is the one
    its source has always used. These are stored digests -- unifying them
    would mark every row in the table as changed on the next run.

    `blank_if_falsy` preserves the other half of that compatibility: the
    originals hashed `rec.get("description_text") or ""` while hashing every
    other field bare, so a missing description contributed "" and not the
    string "None". Verified against 3,000 live rows.

    Note `salary_text` is a record-only field. It feeds builtin-nyc's hash
    but is not a column on the table, which is why it appears in
    HASH_FIELDS_BUILTIN and not in COLUMNS.

TIMESTAMPS STAY TEXT HERE
    Unlike events, this pipeline keeps bookkeeping timestamps as TEXT in
    'YYYY-MM-DDTHH:MM:SS' form. String comparison is load-bearing --
    `WHERE last_seen < %s`, `watermark > cutoff` -- and "" is the "never
    run" sentinel that must sort before every real timestamp. Converting
    these to timestamptz would silently break the self-healing gap logic in
    google-serpapi's choose_date_chip(). pipelib.timeparse.utc_now_str()
    produces exactly this format and is the only thing that should.
"""

from pipelib import dbconn, ids, state
from pipelib.upsert import TableSpec

SCHEMA = "jobs"
TABLE = "jobs"
WATERMARK_TABLE = "job_ingest_state"

STATUS_OPEN = "open"
STATUS_CLOSED = "closed"

#: Columns written from a normalized record.
COLUMNS = (
    "platform", "company_token", "company_name", "source_id",
    "title", "location_raw", "department", "job_url", "posted_at",
    "seniority_guess", "location_is_nyc", "location_is_remote",
    "company_is_nyc_hq", "company_is_ai_focused",
    "description_text", "raw_json",
)

#: Per-source hash field tuples. FROZEN -- see the module docstring.
HASH_FIELDS_ATS = ("title", "location_raw", "department", "job_url",
                   "posted_at", "description_text")
HASH_FIELDS_WWR = HASH_FIELDS_ATS
HASH_FIELDS_SHORT = ("title", "location_raw", "job_url", "posted_at",
                     "description_text")
HASH_FIELDS_BUILTIN = ("title", "location_raw", "job_url", "posted_at",
                       "seniority_guess", "salary_text")

#: Scoring columns, added by score.py rather than present in the base DDL.
SCORING_COLUMNS = (
    ("fit_score", "INTEGER"), ("primary_track", "TEXT"),
    ("gap_friendly_signal", "BOOLEAN"), ("key_technologies", "TEXT"),
    ("gap_bridging_angle", "TEXT"), ("risk_factors", "TEXT"),
    ("scored_at", "TEXT"), ("scoring_model", "TEXT"),
)


def spec(hash_fields, blank_if_falsy=("description_text",)):
    """A TableSpec for one source's hash field set.

    `computed` reopens a listing that reappears upstream: status back to
    'open' and closed_at cleared, on INSERT and UPDATE alike. Paired with
    revive_column, a row previously marked closed counts as an update rather
    than as unchanged, so a reappearance is never silently ignored.
    """
    return TableSpec(
        table=TABLE,
        columns=COLUMNS,
        hash_fields=hash_fields,
        blank_if_falsy=blank_if_falsy,
        computed={"status": f"'{STATUS_OPEN}'", "closed_at": "NULL"},
        revive_column="status",
        revive_value=STATUS_OPEN,
    )


def make_job_id(rec):
    """Primary key: sha256("platform:token:source_id")[:24].

    Identical to the expression all six scripts used, so existing keys are
    preserved -- verified against 3,000 live rows. Deduplicates within a
    source only: the same posting arriving via both Greenhouse and Google
    Jobs is two rows, which ingest/builtin-nyc.py already acknowledged.
    Cross-source dedup is a separate problem and not solved here.
    """
    return ids.make_id(rec["platform"], rec["company_token"], rec["source_id"])


def ensure_schema(conn):
    """Create the jobs schema and tables. Idempotent."""
    conn.execute(f"CREATE SCHEMA IF NOT EXISTS {SCHEMA}")
    conn.execute(f"SET search_path TO {SCHEMA}, public")
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
    conn.commit()
    # Catalog-checked rather than a bare ADD COLUMN IF NOT EXISTS: the latter
    # takes an ACCESS EXCLUSIVE lock even when it changes nothing, and a
    # pending exclusive lock queues ahead of readers -- one blocked ALTER
    # made ingest_state unreadable for everything behind it. See
    # pipelib.dbconn.add_missing_columns.
    dbconn.add_missing_columns(conn, TABLE, list(SCORING_COLUMNS))
    for name, col in (("idx_jobs_company", "company_token"),
                      ("idx_jobs_status", "status"),
                      ("idx_jobs_seniority", "seniority_guess"),
                      ("idx_jobs_nyc", "location_is_nyc")):
        conn.execute(f"CREATE INDEX IF NOT EXISTS {name} ON jobs({col})")
    conn.commit()
    # The watermark table lives in this schema too, and every ingest script
    # writes it before writing a single row. Each of the six used to create
    # it inline; centralising ensure_schema() moved that responsibility here.
    # with_claims because this pipeline leases datasets -- see state.try_claim.
    state.ensure_state_schema(conn, watermark_table=WATERMARK_TABLE,
                              with_claims=True)

    # Two source-specific side tables. They are not part of the jobs row, but
    # they are part of this schema, and the scripts that write them do so
    # before their first upsert -- so they have to exist by the time
    # ensure_schema() returns, exactly like the watermark table.
    #
    # hn_seen_comments is hn-hiring.py's dedup ledger and is load-bearing for
    # correctness: it, not jobs.jobs, is the source of truth for "this HN
    # comment was already parsed."  google_jobs_query_stats is append-only
    # history for the not-yet-built adaptive-cadence feature (see
    # DEVELOPER.md); nothing reads it yet, but both Google scripts write it
    # on every run and previously carried identical copies of this DDL.
    conn.execute("""
        CREATE TABLE IF NOT EXISTS hn_seen_comments (
            comment_id TEXT PRIMARY KEY,
            fetched_at TEXT NOT NULL
        )
    """)
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
    conn.commit()


# -- lifecycle ---------------------------------------------------------------

def close_missing(conn, platform, token, seen_ids, now=None):
    """Close listings that were open but absent from this run's fetch.

    Only valid for sources returning a company's COMPLETE listing set -- the
    ATS boards. SAFETY VALVE: an empty seen_ids would close every open job
    for the company, which is correct only if the fetch is trustworthy, so
    it raises instead. The original relied on the caller remembering.
    """
    from pipelib.timeparse import utc_now_str
    if not seen_ids:
        raise ValueError(
            "close_missing requires a non-empty seen_ids -- an empty fetch "
            "would close every open job for this company")
    now = now or utc_now_str()
    cur = conn.execute(
        """
        UPDATE jobs SET status = 'closed', closed_at = %s, last_seen = %s
        WHERE platform = %s AND company_token = %s AND status = 'open'
          AND NOT (source_id = ANY(%s))
        """,
        (now, now, platform, token, list(seen_ids)),
    )
    conn.commit()
    return cur.rowcount


def close_stale(conn, platform, stale_days, now=None):
    """Close listings not seen for `stale_days`.

    For sources returning a sampled slice rather than a full listing set,
    where absence from any single fetch means nothing.
    """
    from datetime import timedelta
    from pipelib.timeparse import utc_now, utc_now_str
    now = now or utc_now_str()
    cutoff = (utc_now() - timedelta(days=stale_days)).strftime("%Y-%m-%dT%H:%M:%S")
    cur = conn.execute(
        """
        UPDATE jobs SET status = 'closed', closed_at = %s
        WHERE platform = %s AND status = 'open' AND last_seen < %s
        """,
        (now, platform, cutoff),
    )
    conn.commit()
    return cur.rowcount


def prune_old_closed(conn, days):
    from datetime import timedelta
    from pipelib.timeparse import utc_now
    cutoff = (utc_now() - timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%S")
    cur = conn.execute(
        "DELETE FROM jobs WHERE status = 'closed' AND closed_at IS NOT NULL "
        "AND closed_at < %s", (cutoff,))
    conn.commit()
    return cur.rowcount

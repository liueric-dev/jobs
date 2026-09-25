"""Storage contract for normalized job postings and ingest checkpoints.

Only ingestion-owned tables are created here. Existing downstream tables in an
older database are left untouched; deleting stored data is not part of this
codebase reset.
"""

from collections.abc import Iterable
from typing import Any

import psycopg

from lib import dbconn, ids, state
from lib.upsert import TableSpec

SCHEMA = "public"
TABLE = "jobs"
WATERMARK_TABLE = "job_ingest_state"
STATUS_OPEN = "open"
STATUS_CLOSED = "closed"

# Stored record shape and source-specific hashes are preserved so a reset does
# not rewrite the identity or content_hash of existing postings.
COLUMNS = (
    "platform", "company_token", "company_name", "source_id",
    "title", "location_raw", "department", "job_url", "posted_at",
    "posted_at_ts", "salary_text", "seniority_guess", "location_is_nyc",
    "location_is_remote", "company_is_nyc_hq", "company_is_ai_focused",
    "description_text", "raw_json",
)
HASH_FIELDS_ATS = ("title", "location_raw", "department", "job_url",
                   "posted_at", "description_text")
HASH_FIELDS_WWR = HASH_FIELDS_ATS
HASH_FIELDS_SHORT = ("title", "location_raw", "job_url", "posted_at",
                     "description_text")
HASH_FIELDS_BUILTIN = ("title", "location_raw", "job_url", "posted_at",
                       "seniority_guess", "salary_text")


def spec(hash_fields: tuple[str, ...], blank_if_falsy: tuple[str, ...] = ("description_text",),
         sticky: tuple[str, ...] = ()) -> TableSpec:
    """Source-specific upsert contract; reappearing postings reopen."""
    return TableSpec(
        table=TABLE,
        columns=COLUMNS,
        hash_fields=hash_fields,
        blank_if_falsy=blank_if_falsy,
        computed={"status": f"'{STATUS_OPEN}'", "closed_at": "NULL"},
        revive_column="status",
        revive_value=STATUS_OPEN,
        sticky=sticky,
    )


def make_job_id(rec: dict[str, Any]) -> str:
    """Stable per-source ID: sha256(platform:company_token:source_id)[:24]."""
    return ids.make_id(rec["platform"], rec["company_token"], rec["source_id"])


def ensure_schema(conn: psycopg.Connection) -> None:
    """Create ingestion tables, without changing or removing legacy data."""
    events = conn.execute("SELECT to_regclass('public.events')").fetchone()
    if events is not None and events[0] is not None:
        raise RuntimeError(
            "refusing to run: DATABASE_URL points at the events database "
            "(public.events exists here); check this application's .env"
        )
    conn.execute(f"CREATE SCHEMA IF NOT EXISTS {SCHEMA}")
    conn.execute(f"SET search_path TO {SCHEMA}")
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
            posted_at_ts TIMESTAMPTZ,
            salary_text TEXT,
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
    # Older databases predate these two ingest columns. Check the catalog
    # before ALTER so normal runs do not take a needless table lock.
    dbconn.add_missing_columns(conn, TABLE, [
        ("posted_at_ts", "TIMESTAMPTZ"),
        ("salary_text", "TEXT"),
    ])
    for name, column in (("idx_jobs_company", "company_token"),
                         ("idx_jobs_status", "status"),
                         ("idx_jobs_seniority", "seniority_guess"),
                         ("idx_jobs_nyc", "location_is_nyc")):
        conn.execute(f"CREATE INDEX IF NOT EXISTS {name} ON jobs({column})")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_jobs_posted_at_ts "
                 "ON jobs(posted_at_ts DESC NULLS LAST)")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS hn_seen_comments (
            comment_id TEXT PRIMARY KEY,
            fetched_at TEXT NOT NULL
        )
    """)
    conn.commit()
    state.ensure_state_schema(conn, watermark_table=WATERMARK_TABLE,
                              with_claims=True)


def close_missing(conn: psycopg.Connection, platform: str, token: str,
                  seen_ids: Iterable[str], now: str | None = None) -> int:
    """Close jobs absent from a complete ATS board response."""
    from lib.timeparse import utc_now_str

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


def close_stale(conn: psycopg.Connection, platform: str, stale_days: int,
                now: str | None = None) -> int:
    """Close jobs not seen recently by a sampled source."""
    from datetime import timedelta
    from lib.timeparse import utc_now, utc_now_str

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


def prune_old_closed(conn: psycopg.Connection, days: int) -> int:
    """Prune closed rows after the configured retention period."""
    from datetime import timedelta
    from lib.timeparse import utc_now

    cutoff = (utc_now() - timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%S")
    cur = conn.execute(
        "DELETE FROM jobs WHERE status = 'closed' AND closed_at IS NOT NULL "
        "AND closed_at < %s", (cutoff,))
    conn.commit()
    return cur.rowcount

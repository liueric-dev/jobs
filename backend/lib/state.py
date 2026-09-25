"""Ingestion watermarks and optional TTL claims stored in job_ingest_state.

Watermarks record a source's last successful run. Claims are an atomic lease
mechanism for coordinating overlapping workers; current scheduled ingestion
uses the watermarks.
"""

from datetime import timedelta

import psycopg

from . import dbconn
from .timeparse import utc_now, utc_now_str

def ensure_state_schema(conn: psycopg.Connection, watermark_table: str = "ingest_state",
                         with_claims: bool = False) -> None:
    """Create the watermark table if absent.

    `with_claims` adds the `claimed_at` column try_claim() needs. It stays a
    parameter rather than becoming unconditional because ALTER TABLE takes an
    ACCESS EXCLUSIVE lock, and a *pending* exclusive lock queues ahead of new
    readers -- one blocked ALTER makes the whole table unreadable for
    everyone behind it. The ingestion schema requests it explicitly, but issuing
    DDL should stay something a caller asks for rather than something this
    function does on its own. See dbconn.add_missing_columns for the
    idle-transaction incident that lesson comes from.

    """
    conn.execute(f"""
        CREATE TABLE IF NOT EXISTS {watermark_table} (
            dataset TEXT PRIMARY KEY,
            last_success_at TEXT NOT NULL
        )
    """)
    conn.commit()
    if with_claims:
        dbconn.add_missing_columns(conn, watermark_table, [("claimed_at", "TEXT")])


# -- watermarks --------------------------------------------------------------

def get_watermark(conn: psycopg.Connection, dataset: str,
                   table: str = "ingest_state") -> str | None:
    row = conn.execute(
        f"SELECT last_success_at FROM {table} WHERE dataset = %s", (dataset,)  # noqa: S608 -- splices `table`, defaulted to the module's own constant "ingest_state"
    ).fetchone()
    return row[0] if row else None


def set_watermark(conn: psycopg.Connection, dataset: str, ts: str | None = None,
                   table: str = "ingest_state") -> None:
    """Record a successful run.

    Only call this when the fetch was *complete*. nyc-events-ingest used to
    advance the watermark even when fetch_socrata hit its max_pages safety
    cap, so the rows past the cap were skipped and then never requested
    again -- the next run's `:updated_at > watermark` filter excluded them
    permanently.
    """
    conn.execute(
        f"""
        INSERT INTO {table} (dataset, last_success_at) VALUES (%s, %s)
        ON CONFLICT (dataset) DO UPDATE
            SET last_success_at = EXCLUDED.last_success_at
        """,  # noqa: S608 -- splices `table`, defaulted to the module's own constant "ingest_state"
        (dataset, ts or utc_now_str()),
    )
    conn.commit()


# -- TTL claims --------------------------------------------------------------

DEFAULT_CLAIM_TTL_MINUTES = 15


def try_claim(conn: psycopg.Connection, dataset: str,
              ttl_minutes: int = DEFAULT_CLAIM_TTL_MINUTES,
              table: str = "ingest_state") -> bool:
    """Take a lease on `dataset`, or return False if someone else holds one.

    A stale claim (older than ttl_minutes) is stealable, so a crashed run
    can't block the dataset forever. Guards metered API budgets against two
    overlapping runs spending the same quota twice.
    """
    dbconn.add_missing_columns(conn, table, [("claimed_at", "TEXT")])
    cutoff = (utc_now() - timedelta(minutes=ttl_minutes)).strftime(
        "%Y-%m-%dT%H:%M:%S")
    now = utc_now_str()
    # RETURNING rather than rowcount: an ON CONFLICT DO UPDATE whose WHERE
    # fails reports zero affected rows, but "did anyone hand me a row back"
    # is the unambiguous signal, and it is what the original implementation
    # relied on. The '' last_success_at on first INSERT is deliberate -- it
    # is the "never run" sentinel that sorts before every real timestamp,
    # and the column is NOT NULL so it cannot be NULL instead.
    cur = conn.execute(
        f"""
        INSERT INTO {table} (dataset, last_success_at, claimed_at)
        VALUES (%(dataset)s, '', %(now)s)
        ON CONFLICT (dataset) DO UPDATE SET claimed_at = %(now)s
        WHERE {table}.claimed_at IS NULL OR {table}.claimed_at < %(cutoff)s
        RETURNING dataset
        """,  # noqa: S608 -- splices `table`, defaulted to the module's own constant "ingest_state"
        {"dataset": dataset, "now": now, "cutoff": cutoff},
    )
    won = cur.fetchone() is not None
    conn.commit()
    return won


def release_claim(conn: psycopg.Connection, dataset: str, table: str = "ingest_state") -> None:
    conn.execute(f"UPDATE {table} SET claimed_at = NULL WHERE dataset = %s",  # noqa: S608 -- splices `table`, defaulted to the module's own constant "ingest_state"
                 (dataset,))
    conn.commit()


def mark_success(conn: psycopg.Connection, dataset: str, ts: str | None = None,
                  table: str = "ingest_state") -> None:
    """Advance the watermark and drop the claim in one step.

    Called once a fetch actually succeeds. Releasing the claim here rather
    than letting it expire means nobody waits out the TTL for a result that
    is already known.
    """
    conn.execute(
        f"""
        INSERT INTO {table} (dataset, last_success_at, claimed_at)
        VALUES (%s, %s, NULL)
        ON CONFLICT (dataset) DO UPDATE
            SET last_success_at = EXCLUDED.last_success_at, claimed_at = NULL
        """,  # noqa: S608 -- splices `table`, defaulted to the module's own constant "ingest_state"
        (dataset, ts or utc_now_str()),
    )
    conn.commit()

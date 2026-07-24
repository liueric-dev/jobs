"""Run state: watermarks, resumable progress, and TTL claims.

Three mechanisms had grown up independently across the two pipelines, all
answering "what do I not need to fetch again?".

  * Watermarks (`ingest_state` / `job_ingest_state`) -- "dataset X last
    succeeded at T". Identical DDL and identical upsert in both pipelines,
    differing only in table name.

  * Resumable progress. nyc-library-events tracked a next-page cursor per
    borough in `library_ingest_progress`; ticketmaster-seatgeek tracked a
    per-date-slice page plus status and completion time in `fetch_progress`.
    The first is the degenerate case of the second, so they are unified here
    into one `ingest_progress` table. The two differed by an off-by-one --
    one stored the next page, the other the last completed page -- which is
    exactly the kind of drift worth deleting. `next_page` (the page to fetch
    next) is the surviving convention.

  * TTL claims (`google-serpapi.py`) -- a lease so two overlapping runs don't
    spend the same metered API budget twice. Nothing about it was Google- or
    jobs-specific; it is fully generic and lives here.

WHY RESUME MATTERS
    Neither library source offers a cheap "only what changed" filter, so a
    full run walks every page of every source. Committing each page's upserts
    and advancing the cursor immediately means a run killed on page 40 --
    by an OOM, a reboot, or QPL's WAF -- resumes at page 40 next time instead
    of re-walking 1..39. On clean completion the cursor resets to the start
    page, so "finished" doesn't read as "resume at the end and stop".
"""

from datetime import timedelta

from . import dbconn
from .timeparse import utc_now, utc_now_str

STATUS_IN_PROGRESS = "in_progress"
STATUS_COMPLETE = "complete"
STATUS_FAILED = "failed"


def ensure_state_schema(conn, watermark_table="ingest_state", with_claims=False):
    """Create the watermark and progress tables if absent.

    `with_claims` adds the `claimed_at` column used by try_claim(). It is
    opt-in because only the jobs pipeline leases datasets (to protect a
    metered API budget); the events pipeline never calls try_claim, so it
    has no reason to request the column.

    That distinction is not cosmetic. ALTER TABLE needs an ACCESS EXCLUSIVE
    lock, and a *pending* exclusive lock queues ahead of new readers -- so
    one blocked ALTER makes the whole table unreadable for everyone behind
    it. Asking for DDL a pipeline doesn't need turns any long-lived
    transaction elsewhere into an outage. See dbconn.add_missing_columns.
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
    conn.execute("""
        CREATE TABLE IF NOT EXISTS ingest_progress (
            run_key TEXT PRIMARY KEY,
            source TEXT NOT NULL,
            next_page INTEGER NOT NULL DEFAULT 0,
            status TEXT NOT NULL DEFAULT 'in_progress',
            window_start TEXT,
            window_end TEXT,
            completed_at TEXT,
            updated_at TEXT NOT NULL
        )
    """)
    conn.commit()


# -- watermarks --------------------------------------------------------------

def get_watermark(conn, dataset, table="ingest_state"):
    row = conn.execute(
        f"SELECT last_success_at FROM {table} WHERE dataset = %s", (dataset,)
    ).fetchone()
    return row[0] if row else None


def set_watermark(conn, dataset, ts=None, table="ingest_state"):
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
        """,
        (dataset, ts or utc_now_str()),
    )
    conn.commit()


# -- resumable progress ------------------------------------------------------

def get_progress(conn, run_key):
    """(next_page, status, completed_at) or None."""
    return conn.execute(
        "SELECT next_page, status, completed_at FROM ingest_progress "
        "WHERE run_key = %s", (run_key,)
    ).fetchone()


def resume_page(conn, run_key, start_page=0):
    row = get_progress(conn, run_key)
    return row[0] if row else start_page


def save_progress(conn, run_key, source, next_page, status=STATUS_IN_PROGRESS,
                  window_start=None, window_end=None):
    now = utc_now_str()
    conn.execute(
        """
        INSERT INTO ingest_progress
            (run_key, source, next_page, status, window_start, window_end,
             completed_at, updated_at)
        VALUES (%(run_key)s, %(source)s, %(next_page)s, %(status)s,
                %(window_start)s, %(window_end)s, %(completed_at)s, %(updated_at)s)
        ON CONFLICT (run_key) DO UPDATE SET
            next_page = EXCLUDED.next_page,
            status = EXCLUDED.status,
            window_start = COALESCE(EXCLUDED.window_start, ingest_progress.window_start),
            window_end = COALESCE(EXCLUDED.window_end, ingest_progress.window_end),
            completed_at = CASE WHEN EXCLUDED.status = 'complete'
                                THEN EXCLUDED.completed_at
                                ELSE ingest_progress.completed_at END,
            updated_at = EXCLUDED.updated_at
        """,
        {"run_key": run_key, "source": source, "next_page": next_page,
         "status": status, "window_start": window_start,
         "window_end": window_end,
         "completed_at": now if status == STATUS_COMPLETE else None,
         "updated_at": now},
    )
    conn.commit()


def complete_progress(conn, run_key, source, start_page=0, **kw):
    """Mark done and rewind, so the next run starts from the beginning."""
    save_progress(conn, run_key, source, start_page, STATUS_COMPLETE, **kw)


def is_fresh(conn, run_key, freshness_hours):
    """True only for a slice that is complete AND recently so.

    Both conditions matter: a 'failed' or 'in_progress' slice is never fresh,
    so it is always picked back up on the next run. A fresh slice is skipped
    *before* any API call -- the point is not fetching, not deduping after.
    """
    row = get_progress(conn, run_key)
    if not row or row[1] != STATUS_COMPLETE or not row[2]:
        return False
    from datetime import datetime, timezone
    completed = datetime.strptime(row[2], "%Y-%m-%dT%H:%M:%S").replace(
        tzinfo=timezone.utc)
    return (utc_now() - completed) < timedelta(hours=freshness_hours)


# -- TTL claims --------------------------------------------------------------

DEFAULT_CLAIM_TTL_MINUTES = 15


def try_claim(conn, dataset, ttl_minutes=DEFAULT_CLAIM_TTL_MINUTES,
              table="ingest_state"):
    """Take a lease on `dataset`, or return False if someone else holds one.

    A stale claim (older than ttl_minutes) is stealable, so a crashed run
    can't block the dataset forever. Guards metered API budgets against two
    overlapping runs spending the same quota twice.
    """
    dbconn.add_missing_columns(conn, table, [("claimed_at", "TEXT")])
    cutoff = (utc_now() - timedelta(minutes=ttl_minutes)).strftime(
        "%Y-%m-%dT%H:%M:%S")
    now = utc_now_str()
    cur = conn.execute(
        f"""
        INSERT INTO {table} (dataset, last_success_at, claimed_at)
        VALUES (%(dataset)s, '', %(now)s)
        ON CONFLICT (dataset) DO UPDATE SET claimed_at = %(now)s
        WHERE {table}.claimed_at IS NULL OR {table}.claimed_at < %(cutoff)s
        """,
        {"dataset": dataset, "now": now, "cutoff": cutoff},
    )
    conn.commit()
    return cur.rowcount > 0


def release_claim(conn, dataset, table="ingest_state"):
    conn.execute(f"UPDATE {table} SET claimed_at = NULL WHERE dataset = %s",
                 (dataset,))
    conn.commit()


def mark_success(conn, dataset, table="ingest_state"):
    """Advance the watermark and drop the claim in one step."""
    conn.execute(
        f"""
        INSERT INTO {table} (dataset, last_success_at, claimed_at)
        VALUES (%s, %s, NULL)
        ON CONFLICT (dataset) DO UPDATE
            SET last_success_at = EXCLUDED.last_success_at, claimed_at = NULL
        """,
        (dataset, utc_now_str()),
    )
    conn.commit()

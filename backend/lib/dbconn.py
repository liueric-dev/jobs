"""PostgreSQL connection helpers for the ingestion pipeline.

DATABASE_URL is required and has no fallback. The jobs database shares a
cluster with an unrelated application, so guessing a URL risks writing to the
wrong database. schema.ensure_schema() rejects the unrelated events database.
Connections may set search_path but never create schema as a side effect.
"""

import os
from collections.abc import Iterable

import psycopg

#: DATABASE_URL has no default because this cluster hosts an unrelated database.


def database_url() -> str:
    """The connection string, or a hard failure.

    Deliberately raises rather than guessing -- see the note above. Callers
    that want the standard failure message use connect_or_exit().
    """
    url = os.environ.get("DATABASE_URL")
    if not url:
        raise RuntimeError(
            "DATABASE_URL is not set. Set it in backend/.env or the process "
            "environment. There is deliberately no built-in default because "
            "this cluster also hosts an unrelated database.")
    return url


def scrub_url(url: str | None = None) -> str:
    """Everything after the '@' -- host/db, never the password.

    Must not raise: this is what failure paths print. Since database_url()
    now raises on an unset DATABASE_URL, an unset value is reported as such
    rather than propagating out of an error handler and replacing the real
    diagnostic with a RuntimeError from the logging code.
    """
    if not url:
        url = os.environ.get("DATABASE_URL")
    return url.split("@")[-1] if url else "<DATABASE_URL not set>"


def connect(schema: str | None = None, url: str | None = None,
            autocommit: bool = False) -> psycopg.Connection:
    """Open a connection, optionally scoped to a Postgres schema.

    `schema="public"` issues `SET search_path TO public`. Search path is
    per-connection, so callers cannot rely on an earlier connection's setting.

    This creates no schema. Passing `schema=` asserts where to look, it does
    not ask for DDL rights; schema.py's
    ensure_schema() is the one place that creates.

    `autocommit=True` exists for callers whose writes must survive
    independently of whatever transaction is running around them, such as a
    cache that should persist even if the enclosing batch rolls back. Nothing
    in this pipeline currently passes it.
    """
    conn = psycopg.connect(url or database_url())
    if autocommit:
        conn.autocommit = True
    if schema:
        conn.execute(f"SET search_path TO {schema}")
        if not autocommit:
            conn.commit()
    return conn


def existing_columns(conn: psycopg.Connection, table: str) -> set[str]:
    """Columns of `table` in the connection's current schema.

    Scoped to current_schema() deliberately. information_schema.columns spans
    every schema the role can see, so an unscoped lookup answers about whatever
    same-named table it finds first -- events runs in a database that also
    holds `topology`, `tiger` and `tiger_data`, and the only thing that has
    kept this honest is that no tiger table happens to be called `events`.
    """
    return {row[0] for row in conn.execute(
        "SELECT column_name FROM information_schema.columns "
        "WHERE table_name = %s AND table_schema = current_schema()",
        (table,)).fetchall()}


def add_missing_columns(conn: psycopg.Connection, table: str,
                         columns: Iterable[tuple[str, str]]) -> list[str]:
    """ALTER TABLE ADD COLUMN, but only for columns that are actually absent.

    `ADD COLUMN IF NOT EXISTS` looks idempotent and free. It is not: Postgres
    still acquires an ACCESS EXCLUSIVE lock to evaluate it, even when the
    column already exists and nothing changes. Issuing it on every run makes
    each invocation contend for an exclusive lock on a table every other
    query reads.

    That is not theoretical here. A run blocked for minutes behind a
    connection the previous generation of these scripts had left "idle in
    transaction" for thirty hours: the zombie held a harmless ACCESS SHARE
    from an old SELECT, which conflicts with ACCESS EXCLUSIVE and nothing
    else. Checking the catalog first means the steady-state path issues no
    DDL at all, so ordinary readers can never block a run.

    Returns the list of columns actually added.
    """
    present = existing_columns(conn, table)
    added = []
    for name, coltype in columns:
        if name not in present:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS {name} {coltype}")
            added.append(name)
    if added:
        conn.commit()
    return added


def connect_or_exit(label: str, schema: str | None = None, url: str | None = None,
                     autocommit: bool = False) -> psycopg.Connection:
    """connect(), or print the standard failure line and exit 1.

    Matches the message every script already printed, so cron output and any
    alerting that greps for it keep working.

    RuntimeError is caught alongside OperationalError because database_url()
    now raises it when DATABASE_URL is unset. Without that, the one failure
    this module most wants to report clearly would arrive as an uncaught
    traceback and skip the standard `<label> FAILED:` line the failure
    notifiers grep for.
    """
    import sys

    try:
        return connect(schema=schema, url=url, autocommit=autocommit)
    except (psycopg.OperationalError, RuntimeError) as e:
        print(f"{label} FAILED: could not connect to Postgres "
              f"({scrub_url(url)}): {e}")
        if not os.environ.get("DATABASE_URL"):
            print("  Set DATABASE_URL in backend/.env or the process "
                  "environment. No built-in fallback is used because the "
                  "cluster also hosts an unrelated database.")
        sys.exit(1)

"""Postgres connections, with the two footguns both pipelines hit.

FOOTGUN 1 -- the DATABASE_URL default had drifted.
    Eight scripts hardcoded a fallback pointing at the nyc_events database
    and ticketmaster-seatgeek-ingest.py hardcoded
        postgresql://nycevents:nycevents@localhost:5432/nycevents
    which matches no database that has ever existed here -- docker-compose.yml
    creates the first. That script could not connect even once, which is why
    its `fetch_progress` table was still missing. One default, defined here.

    The default carries NO password: the real connection string lives in
    ~/.hermes/.env alongside the other secrets, which is also where the jobs
    pipeline reads its API keys from. A credential baked into a source file
    goes stale the moment the password is rotated, and then reports itself
    as an authentication error rather than as a configuration one.

FOOTGUN 2 -- search_path is per-connection, not per-database.
    jobs/ lives in the `jobs` Postgres schema and relies on
    `SET search_path TO jobs, public` so its unqualified table names resolve.
    That setting attaches to a *connection*, so every new connection needs it
    again -- jobs/score.py:382 rediscovered this the hard way and re-issues it
    inside each ThreadPoolExecutor worker. connect() therefore takes the
    schema explicitly and applies it to every connection it returns, which
    makes the threaded case correct by construction instead of by remembering.

Credentials never reach a log: scrub_url() reduces a connection string to
its host/database tail, which is what the existing scripts print on failure.
"""

import os

import psycopg

DEFAULT_DATABASE_URL = (
    "postgresql://nyc_events@localhost:5432/nyc_events"
)


def database_url():
    return os.environ.get("DATABASE_URL", DEFAULT_DATABASE_URL)


def scrub_url(url=None):
    """Everything after the '@' -- host/db, never the password."""
    return (url or database_url()).split("@")[-1]


def connect(schema=None, url=None, autocommit=False):
    """Open a connection, optionally scoped to a Postgres schema.

    `schema="jobs"` issues `SET search_path TO jobs, public`. Pass it on
    EVERY connection into that schema, including per-thread ones.

    `autocommit=True` is required for the geocode cache, whose writes must
    survive independently of whatever transaction the caller is running --
    see ~/apps/events/geocode.py.
    """
    conn = psycopg.connect(url or database_url())
    if autocommit:
        conn.autocommit = True
    if schema:
        conn.execute(f"CREATE SCHEMA IF NOT EXISTS {schema}")
        conn.execute(f"SET search_path TO {schema}, public")
        if not autocommit:
            conn.commit()
    return conn


def existing_columns(conn, table):
    return {row[0] for row in conn.execute(
        "SELECT column_name FROM information_schema.columns WHERE table_name = %s",
        (table,)).fetchall()}


def add_missing_columns(conn, table, columns):
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


def connect_or_exit(label, schema=None, url=None, autocommit=False):
    """connect(), or print the standard failure line and exit 1.

    Matches the message every script already printed, so cron output and any
    alerting that greps for it keep working.
    """
    import sys

    try:
        return connect(schema=schema, url=url, autocommit=autocommit)
    except psycopg.OperationalError as e:
        print(f"{label} FAILED: could not connect to Postgres "
              f"({scrub_url(url)}): {e}")
        if not os.environ.get("DATABASE_URL"):
            print("  DATABASE_URL is not set -- it belongs in ~/.hermes/.env; "
                  "the built-in default carries no password by design.")
        sys.exit(1)

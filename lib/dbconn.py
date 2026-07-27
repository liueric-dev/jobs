"""Postgres connections, with the two footguns both pipelines hit.

FOOTGUN 1 -- the DATABASE_URL default had drifted.
    Eight scripts hardcoded a fallback pointing at the nyc_events database
    and ticketmaster-seatgeek-ingest.py hardcoded
        postgresql://nycevents:nycevents@localhost:5432/nycevents
    which matches no database that has ever existed here -- docker-compose.yml
    creates the first. That script could not connect even once, which is why
    its `fetch_progress` table was still missing. One default, defined here.

    The default carries NO password. The real connection strings live in each
    application's own .env -- ~/apps/events/.env and ~/apps/jobs/.env, plus
    ~/apps/jobs/api/.env for the service -- which is also where each reads its
    API keys from. A credential baked into a source file goes stale the moment
    the password is rotated, and then reports itself as an authentication
    error rather than as a configuration one.

FOOTGUN 2 -- the wrong DATABASE_URL is silent, and is now destructive.
    This used to say something else. Until the database split, jobs/ lived in a
    `jobs` schema inside the events database and depended on
    `SET search_path TO jobs, public`; a connection that forgot it read and
    wrote `public` without erroring. That footgun is gone -- jobs owns the
    `jobs` database and its tables sit in that database's `public`.

    What replaced it is sharper. The two applications are now told apart ONLY
    by the database named in DATABASE_URL, and both use unqualified table
    names in `public`. Point the jobs pipeline at the events database and it
    will not error: it will create its 13 tables alongside `public.events`.
    So jobs/schema.py's ensure_schema() refuses to run when `public.events`
    exists, and no non-superuser role can connect to nyc_events at all.

    search_path is still per-connection, which is why connect() applies it to
    every connection it returns rather than trusting a role default --
    jobs/score.py:417 re-issues it inside each ThreadPoolExecutor worker, and
    doing it here makes the threaded case correct by construction instead of
    by remembering. connect() does NOT create the schema: that is DDL, it
    would demand CREATE on the database from every connection including
    read-only ones, and Postgres checks that privilege before `IF NOT EXISTS`
    can short-circuit. Schema creation belongs to ensure_schema().

Credentials never reach a log: scrub_url() reduces a connection string to
its host/database tail, which is what the existing scripts print on failure.
"""

import os

import psycopg

#: THERE IS NO DEFAULT HERE, AND THAT IS THIS COPY'S ONE DELIBERATE
#: DIVERGENCE FROM ~/apps/events/lib/dbconn.py.
#:
#: The shared library carried one default, and it named the EVENTS database:
#:
#:     postgresql://nyc_events@localhost:5432/nyc_events
#:
#: which was correct for the pipeline that owned it and actively dangerous
#: here. Read FOOTGUN 2 above: the two applications are told apart only by the
#: database named in DATABASE_URL, and both use unqualified names in `public`.
#: A jobs process that fell back to that default would not error -- it would
#: connect to the events database and start creating its 13 tables alongside
#: `public.events`.
#:
#: Vendoring is what makes deleting it possible: while one file served both
#: pipelines, the default had to be right for events and jobs had to remember
#: never to rely on it. Now jobs simply cannot. An unset DATABASE_URL fails
#: loudly at the point of the mistake instead of connecting to something
#: plausible.
#:
#: Everything that runs here sets it explicitly: the systemd unit via
#: EnvironmentFile=~/apps/jobs/.env, run-daily.py via lib.envfile, and api/
#: from its own .env. api/query_claims.py additionally keeps a jobs-shaped
#: literal for manage_users.py's admin path, where being wrong is caught by
#: the role having no rights on the other database.


def database_url():
    """The connection string, or a hard failure.

    Deliberately raises rather than guessing -- see the note above. Callers
    that want the standard failure message use connect_or_exit().
    """
    url = os.environ.get("DATABASE_URL")
    if not url:
        raise RuntimeError(
            "DATABASE_URL is not set. It belongs in this application's own "
            ".env (~/apps/jobs/.env for the pipeline, ~/apps/jobs/api/.env "
            "for the service). There is deliberately no built-in default: "
            "the only one that ever existed named the events database, and "
            "falling back to it would create the jobs tables there.")
    return url


def scrub_url(url=None):
    """Everything after the '@' -- host/db, never the password.

    Must not raise: this is what failure paths print. Since database_url()
    now raises on an unset DATABASE_URL, an unset value is reported as such
    rather than propagating out of an error handler and replacing the real
    diagnostic with a RuntimeError from the logging code.
    """
    if not url:
        url = os.environ.get("DATABASE_URL")
    return url.split("@")[-1] if url else "<DATABASE_URL not set>"


def connect(schema=None, url=None, autocommit=False):
    """Open a connection, optionally scoped to a Postgres schema.

    `schema="public"` issues `SET search_path TO public`. Pass it on EVERY
    connection, including per-thread ones -- search_path is per-connection, so
    setting it here is what makes the threaded case in jobs/score.py correct
    without each worker having to remember.

    This creates no schema. Passing `schema=` asserts where to look, it does
    not ask for DDL rights; see FOOTGUN 2 above. jobs/schema.py's
    ensure_schema() is the one place that creates.

    `autocommit=True` is required for the geocode cache, whose writes must
    survive independently of whatever transaction the caller is running --
    see ~/apps/events/geocode.py.
    """
    conn = psycopg.connect(url or database_url())
    if autocommit:
        conn.autocommit = True
    if schema:
        conn.execute(f"SET search_path TO {schema}")
        if not autocommit:
            conn.commit()
    return conn


def existing_columns(conn, table):
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
            print("  DATABASE_URL is not set -- it belongs in this "
                  "application's own .env (~/apps/jobs/.env or "
                  "~/apps/jobs/api/.env). This copy of dbconn has no "
                  "built-in default on purpose: the only one that ever "
                  "existed named the events database.")
        sys.exit(1)

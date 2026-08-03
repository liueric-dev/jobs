"""A throwaway copy of the real schema, created by the real schema code.

WHY A SCRATCH DATABASE AT ALL
    `docs/ingestion_tests/05-fetcher-harness.md:42` splits the audit's seven
    fetcher defects in two: items 1, 4, 5 and 7 are cassette tests, items 2
    and 3 need a database. The reason is specific rather than general. Both
    are claims about POSTGRES TRANSACTION BEHAVIOUR:

      * `lib/upsert.py:191-197` says a plain try/except is not enough,
        because a failed statement aborts the whole transaction and every
        later record in the batch dies with "current transaction is
        aborted". Its fix is a per-record SAVEPOINT. A fake connection
        cannot falsify that -- `tests/test_upsert_checked.py`'s _FakeConn
        happily continues after a raise, so the test passes whether or not
        the SAVEPOINT is there. Only a real server can tell you.

      * "no per-record isolation" is a pipeline-wide property, not a
        `match.py` quirk -- three of nine scripts have it. Testing it needs
        somewhere to write.

    Neither can run against production: there is no staging instance, and
    `docs/ingestion_tests/README.md:118` is explicit that nothing here may
    drive an ingest against the live table.

A SCHEMA, NOT A DATABASE, AND THAT IS FORCED
    The task says "database". The pipeline role cannot create one:

        SELECT rolcreatedb FROM pg_roles WHERE rolname = current_user  -> f

    `jobs_pipeline` has no CREATEDB and no superuser, so `CREATE DATABASE`
    is not available to the process that would need it, and provisioning a
    second database by hand would put a manual step in front of every test
    run. What it does have is CREATE on the `jobs` database, so each run
    gets its own `scratch_<8 hex>` schema, `search_path` scoped to it, and a
    DROP SCHEMA CASCADE at the end. Set JOBS_SCRATCH_DATABASE_URL to point
    somewhere else and it is used instead -- the isolation improves, nothing
    else changes.

    The blast radius is the reason for the naming rule below: this module
    will only ever drop a schema matching `^scratch_[0-9a-f]{8}$`, checked
    immediately before the DROP rather than trusted from where the name came
    from.

SCHEMA CREATION SHARES THE REAL PATH
    `09-fetcher-harness.md:55` requires this and it is worth restating why:
    a hand-maintained DDL copy tests a schema that no longer exists, and
    this pipeline has already paid for that once -- `schema.py:5-8` exists
    because six ingest scripts each carried their own drifting
    ensure_schema(). So `create()` calls `schema.ensure_schema()`, the same
    function `manage_users.py init-schema` reaches (33469fe), with
    `schema.SCHEMA` temporarily pointed at the scratch schema. Phase 2 and 5
    migrations land in it for free; nothing here lists a table by name.

THE public.events REFUSAL IS KEPT, DELIBERATELY
    `lib/dbconn.py:19` FOOTGUN 2: ensure_schema() refuses to run where
    `public.events` exists, because the two applications are told apart only
    by the database in DATABASE_URL. Nothing here suppresses that -- a
    scratch schema pointed at the events database must fail exactly as loudly
    as a production run would, and `tests/test_scratchdb.py` pins it.
"""

import os
import re
import sys
import uuid
from contextlib import contextmanager

import psycopg

#: A scratch schema name and nothing else. Enforced at the DROP.
SCRATCH_NAME = re.compile(r"^scratch_[0-9a-f]{8}$")


def scratch_url():
    """Where scratch schemas are created.

    JOBS_SCRATCH_DATABASE_URL first, so a machine that does have a spare
    database can use it without any other change. DATABASE_URL otherwise --
    the scratch schema is a sibling of `public`, never `public` itself.
    """
    return (os.environ.get("JOBS_SCRATCH_DATABASE_URL")
            or os.environ.get("DATABASE_URL"))


def available():
    """Whether a scratch schema could actually be created right now.

    Used by `skipUnless`: a developer without Postgres running still gets a
    green suite, and the DB-backed tests announce themselves as skipped
    rather than passing vacuously.

    Distinguishes two different failures. Every connection-level problem --
    refused, timed out, wrong host, wrong credentials, wrong database --
    surfaces from psycopg as some form of `psycopg.OperationalError`: even
    "connection refused" and "password authentication failed" carry no more
    specific SQLSTATE and arrive as the bare class (confirmed against
    psycopg 3.3). That is the ROUTINE case -- a laptop with no Postgres --
    and stays silent exactly as it does today. Anything else is not that,
    and silence there is the exact defect docs/STATE-OF-THE-SYSTEM.md § 2
    names: a genuine driver bug reads as the identical skip to every module
    that gates on this. That gets one loud stderr line before the same
    `False`, so the skipUnless contract every caller depends on is unchanged.
    """
    url = scratch_url()
    if not url:
        return False
    try:
        with psycopg.connect(url, connect_timeout=5) as conn:
            conn.execute("SELECT 1")
        return True
    except psycopg.OperationalError:
        return False
    except Exception as e:
        print(f"scratchdb.available(): {type(e).__name__}: {e} -- this is "
              f"not 'Postgres isn't running', something is broken",
              file=sys.stderr)
        return False


def _new_name():
    return f"scratch_{uuid.uuid4().hex[:8]}"


def drop(conn, name):
    """DROP SCHEMA CASCADE, for a name this module could have created.

    The guard is not paranoia about a caller: `public` reaches this function
    the moment someone passes `schema.SCHEMA` by habit, and DROP SCHEMA
    public CASCADE against DATABASE_URL is the whole jobs table.
    """
    if not SCRATCH_NAME.match(name or ""):
        raise ValueError(
            f"refusing to drop schema {name!r}: this module only ever "
            f"creates and drops names matching {SCRATCH_NAME.pattern}")
    conn.execute(f"DROP SCHEMA IF EXISTS {name} CASCADE")
    conn.commit()


@contextmanager
def scratch_schema(url=None, keep=False):
    """Yield (conn, name) against a fresh, fully-migrated scratch schema.

    `keep=True` leaves it behind, for the case where a failing test is worth
    inspecting by hand. It prints the name, because a scratch schema nobody
    can name is a scratch schema nobody can drop.
    """
    import schema as jobs_schema        # imported here: sys.path is a caller
                                        # concern and this module is imported
                                        # by evals/ code that has already set it

    target = url or scratch_url()
    if not target:
        raise RuntimeError(
            "no scratch database: set JOBS_SCRATCH_DATABASE_URL, or "
            "DATABASE_URL for a scratch schema beside `public`.")

    name = _new_name()
    conn = psycopg.connect(target)
    original = jobs_schema.SCHEMA
    try:
        jobs_schema.SCHEMA = name
        # The real path, not a copy -- see SCHEMA CREATION SHARES THE REAL
        # PATH. ensure_schema() issues the CREATE SCHEMA and the SET
        # search_path itself (schema.py:266-267), so there is nothing to do
        # here but point it and call it.
        jobs_schema.ensure_schema(conn)
        yield conn, name
    finally:
        jobs_schema.SCHEMA = original
        try:
            if keep:
                print(f"[scratchdb] keeping schema {name}")
            else:
                conn.rollback()
                drop(conn, name)
        finally:
            conn.close()


@contextmanager
def second_connection(name, url=None):
    """A second, independent session scoped to the same scratch schema.

    Concurrency is the one property a single connection structurally cannot
    test, and `lib/state.try_claim` is the one place in this pipeline whose
    correctness only exists under it -- it is what stops two overlapping runs
    spending the same metered SerpApi/Apify budget twice
    (`lib/state.py:96-99`). See tests/test_scratchdb.py for the argument
    about which concurrency tests are worth having and which are not.
    """
    conn = psycopg.connect(url or scratch_url())
    try:
        conn.execute(f"SET search_path TO {name}")
        conn.commit()
        yield conn
    finally:
        conn.close()

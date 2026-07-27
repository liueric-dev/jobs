"""
The three tables this service owns, and the startup gate that proves it can
use them.

SCHEMA OWNERSHIP. ../schema.py owns `jobs`, `job_facts`, `job_matches`,
`job_scores`, `profiles`, `job_events` and the `jobs_app` view. This module
declares ONLY app_users, app_sessions and oauth_logins, and never drops,
alters or restates anything on the other side of that line. api/query_claims.py
makes the same split and its docstring records what happens when it is not
made: nine functions and three tables' DDL were duplicated there and had
drifted six ways by the time anyone measured, two of the drifts changing row
identity. One definition per table, in the module that owns it.

TIMESTAMPS ARE TEXT, in the pipeline's '%Y-%m-%dT%H:%M:%S' UTC form via
lib.timeparse.utc_now_str(). Not because TEXT is the better type -- because
every other table in this database does it, and one table with TIMESTAMPTZ
would make every join and every hand-written diagnostic query a special case.

WHY THE GRANT CHECK IS PART OF THIS FILE: REQUIRED_TABLES is the single source
of truth for three things -- the startup check below, the GRANT statements in
README.md, and tests/test_grants.py. A route that starts querying a new table
without adding it here yields a service that starts cleanly and 500s on that
one request, in production, on someone else's first click.
"""

import config  # noqa: F401  (must come first -- it performs the sys.path insert)

import schema
from lib import dbconn
from lib.timeparse import utc_now_str

#: Tables this service touches, and the privileges each use needs. Read tables
#: belong to the pipeline; the last three are ours.
#:
#: `jobs` is listed with SELECT even though every query goes through the
#: `jobs_app` view. A plain view runs with the CALLER's privileges -- it is not
#: a security barrier -- so granting on the view alone fails at the first
#: request, not at deploy time.
REQUIRED_TABLES = {
    "jobs_app": ("SELECT",),
    "jobs": ("SELECT",),
    "job_matches": ("SELECT",),
    "job_scores": ("SELECT",),
    "job_facts": ("SELECT",),
    "profiles": ("SELECT",),
    # Append-only: engagement is evidence, and a 'dismiss' is a row rather than
    # a deletion. No DELETE, no UPDATE.
    "job_events": ("SELECT", "INSERT"),
    "app_users": ("SELECT", "INSERT", "UPDATE"),
    "app_sessions": ("SELECT", "INSERT", "UPDATE", "DELETE"),
    "oauth_logins": ("SELECT", "INSERT", "DELETE"),
}

#: job_events.id is BIGSERIAL, so INSERT on the table is not enough on its own
#: -- nextval() needs USAGE on the sequence. api/ learned this the expensive
#: way: the equivalent grant was documented in its README and verified by
#: nothing, which made it the one requirement whose absence surfaced as a 500 on
#: a contributor's first submit rather than as a refusal to start.
REQUIRED_SEQUENCES = {
    "job_events_id_seq": ("USAGE", "SELECT"),
}

#: Every table any SQL in this package names. tests/test_grants.py asserts this
#: equals the key set above; it is separate only so the test reads as an
#: independent statement rather than a tautology.
TABLES_TOUCHED = frozenset(REQUIRED_TABLES)


def ensure_schema(conn):
    """Create this service's tables. Idempotent, DDL, admin credential only.

    Deliberately a separate, explicitly-invoked step rather than something the
    service does at startup: the long-running, browser-facing process holds no
    CREATE rights at all, so a missing table here is a deployment error to
    report (see verify_schema) rather than damage to silently repair.

    schema.ensure_schema() is called first, for two reasons. It creates the
    pipeline tables this service reads if a fresh database has none, and it
    carries the guard that refuses to run against the events database -- a
    wrong DATABASE_URL would otherwise create these tables in `public` beside
    somebody else's data and nothing downstream would report it.
    """
    schema.ensure_schema(conn)
    schema.ensure_app_view(conn)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS app_users (
            id TEXT PRIMARY KEY,
            email TEXT NOT NULL UNIQUE,
            google_sub TEXT UNIQUE,
            display_name TEXT,
            profile TEXT NOT NULL,
            is_admin BOOLEAN NOT NULL DEFAULT FALSE,
            active BOOLEAN NOT NULL DEFAULT TRUE,
            created_at TEXT NOT NULL,
            last_login_at TEXT
        )
    """)
    # profile is bare TEXT with NO foreign key to profiles(profile), matching
    # job_scores.profile and job_matches.profile in ../schema.py. A real FK
    # would make this service's DDL depend on a table it must not own, which is
    # the coupling the ownership rule above exists to prevent.
    # manage_app_users.py validates the profile with profiles.load_one()
    # instead -- the right place for it, since that function deliberately
    # returns paused profiles too.

    conn.execute("""
        CREATE TABLE IF NOT EXISTS app_sessions (
            token_hash TEXT PRIMARY KEY,
            user_id TEXT NOT NULL REFERENCES app_users(id) ON DELETE CASCADE,
            created_at TEXT NOT NULL,
            expires_at TEXT NOT NULL,
            last_seen_at TEXT,
            revoked_at TEXT,
            user_agent TEXT,
            ip TEXT
        )
    """)
    # token_hash is the primary key and the cookie value is never stored, so a
    # database dump yields no working credential -- the same property, and the
    # same three lines, as api_keys in api/manage_users.py.

    conn.execute("""
        CREATE TABLE IF NOT EXISTS oauth_logins (
            state TEXT PRIMARY KEY,
            code_verifier TEXT NOT NULL,
            nonce TEXT NOT NULL,
            next_path TEXT,
            created_at TEXT NOT NULL,
            expires_at TEXT NOT NULL
        )
    """)
    # PKCE state lives here rather than in a signed cookie. Rows are single-use
    # -- redeemed with one DELETE ... RETURNING -- so replay protection falls
    # out of the primary key instead of out of code someone has to keep
    # correct, and there is no signing secret to generate, store or rotate.

    conn.execute("CREATE INDEX IF NOT EXISTS idx_app_sessions_user "
                 "ON app_sessions(user_id)")
    conn.commit()


def verify_schema(conn):
    """Fail fast, and loudly, if the database is not ready for this service.

    Ported from api/app.py, including the reasoning:

    This process deliberately holds no DDL rights. So a missing table is a
    deployment error to report, not damage to repair -- refusing to start is
    the point, because a half-initialised database otherwise surfaces later as
    a confusing 500 on a real user's first click.

    Privileges are checked, not just existence. A table can exist and still be
    unusable if a GRANT was missed, and that failure mode is real: INSERT
    without SELECT on a table looks fine until the first ON CONFLICT runs.
    has_table_privilege() turns that into a startup error naming the missing
    grant. The sequence is checked for the same reason -- job_events.id is
    BIGSERIAL, so INSERT on the table needs USAGE on job_events_id_seq too.

    Raises RuntimeError listing everything that is wrong, not just the first
    thing: fixing grants one restart at a time is miserable.
    """
    problems = []
    for table, privileges in REQUIRED_TABLES.items():
        qualified = f"public.{table}"
        if conn.execute("SELECT to_regclass(%s)", (qualified,)).fetchone()[0] is None:
            problems.append(f"{qualified}: missing")
            continue
        lacking = [
            p for p in privileges
            if not conn.execute(
                "SELECT has_table_privilege(current_user, %s, %s)", (qualified, p)
            ).fetchone()[0]
        ]
        if lacking:
            problems.append(f"{qualified}: no {', '.join(lacking)}")

    for sequence, privileges in REQUIRED_SEQUENCES.items():
        qualified = f"public.{sequence}"
        if conn.execute("SELECT to_regclass(%s)", (qualified,)).fetchone()[0] is None:
            problems.append(f"{qualified}: missing")
            continue
        lacking = [
            p for p in privileges
            if not conn.execute(
                "SELECT has_sequence_privilege(current_user, %s, %s)", (qualified, p)
            ).fetchone()[0]
        ]
        if lacking:
            problems.append(f"{qualified}: no {', '.join(lacking)}")

    if problems:
        raise RuntimeError(
            f"database is not ready for this service ({dbconn.scrub_url()}) -- "
            + "; ".join(problems)
            + ". Run `python3 manage_app_users.py init-schema` with an admin "
              "credential (JOBS_ADMIN_DATABASE_URL), and check the GRANTs in "
              "README 'Database privileges'."
        )


def prune_expired_logins(conn):
    """Delete abandoned oauth_logins rows.

    Called from the callback rather than a timer: this table is only ever
    touched by logins, so a login is exactly when it is worth a cheap DELETE.
    An abandoned row is harmless -- it is single-use and expiry-checked -- but
    without this it stays forever.
    """
    conn.execute("DELETE FROM oauth_logins WHERE expires_at < %s", (utc_now_str(),))

"""
The four tables this service owns, and the startup gate that proves it can
use them.

SCHEMA OWNERSHIP. ../schema.py owns `jobs`, `job_facts`, `job_matches`,
`job_scores`, `profiles`, `job_events` and the `jobs_app` view. This module
declares ONLY app_users, app_sessions, oauth_logins and builder_job_state, and
never drops, alters or restates anything on the other side of that line. api/query_claims.py
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
#: belong to the pipeline; the last four are ours.
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
    # Current per-Builder state, upserted -- so INSERT and UPDATE, and no
    # DELETE. An undo is a column going back to NULL plus an `undismiss` row in
    # job_events, never a deletion: tranche_six/31 asks for the reversal itself
    # to be kept, because "the fact that someone reversed a dismissal is itself
    # signal, and deletion loses it".
    "builder_job_state": ("SELECT", "INSERT", "UPDATE"),
}

#: The golden-set tables, owned by ../evals/labels.py and merged in here.
#:
#: MERGED, NOT RESTATED. The ownership rule at the top of this file cuts both
#: ways: labels.py declares those three tables and this module must not carry
#: a second copy of their privileges that can drift out of agreement with the
#: DDL. Reading labels.WEB_PRIVILEGES keeps one definition and still lets the
#: startup check, the README grant table and tests/test_grants.py all see them.
#:
#: The privileges are SELECT on the two set tables and SELECT+INSERT on
#: eval_labels: no UPDATE and no DELETE anywhere. A label is evidence, and a
#: revised judgement is a second round rather than an overwrite -- exactly the
#: treatment job_events gets above, and for the same reason. It also means a
#: bug in label.py cannot destroy the ceiling measurement.
from evals import labels as _labels  # noqa: E402  (needs config's sys.path)

REQUIRED_TABLES.update(_labels.WEB_PRIVILEGES)

#: job_events.id is BIGSERIAL, so INSERT on the table is not enough on its own
#: -- nextval() needs USAGE on the sequence. api/ learned this the expensive
#: way: the equivalent grant was documented in its README and verified by
#: nothing, which made it the one requirement whose absence surfaced as a 500 on
#: a contributor's first submit rather than as a refusal to start.
REQUIRED_SEQUENCES = {
    "job_events_id_seq": ("USAGE", "SELECT"),
}

#: Columns this service WRITES that were added after the table shipped, and
#: which therefore exist only where ../schema.py's ensure_schema() has run.
#:
#: WHY A COLUMN CHECK AT ALL, when the table check above already passes. The
#: two processes migrate on different schedules: ensure_schema() is called by
#: the pipeline (extract.py, match.py, score.py), and this service holds no DDL
#: rights by design. So a deploy that ships webapp/ ahead of a nightly run finds
#: a job_events that exists, is granted correctly, and is missing six columns
#: the INSERT names -- which is a 500 on a real user's first click, the exact
#: failure verify_schema()'s docstring exists to convert into a startup error.
#: It is the same argument the sequence grant above is annotated with, and api/
#: is cited there as having learned it the expensive way.
#:
#: Only WRITTEN columns are listed. Reads go through the jobs_app view, whose
#: shape is that view's problem.
REQUIRED_COLUMNS = {
    "job_events": ("request_id", "rank", "dwell_ms", "reason", "visibility",
                   "criteria_version"),
}

#: eval_labels.id is BIGSERIAL for the same reason and needs the same grant.
REQUIRED_SEQUENCES.update(_labels.WEB_SEQUENCES)

#: Every table any SQL in this package names. tests/test_grants.py asserts this
#: equals the key set above; it is separate only so the test reads as an
#: independent statement rather than a tautology.
TABLES_TOUCHED = frozenset(REQUIRED_TABLES)

#: app_users.prior_domain -- the industry a Builder is changing career FROM.
#:
#: WHAT IT IS FOR, AND IT IS NOT SCORING. It exists so that Axis B disagreement
#: between two labellers can be decomposed within and across background instead
#: of being read as noise. `labels.AXIS_B_FIELD` is "would_apply", and on a
#: bridge role a Builder with prior commercial experience and one without give
#: OPPOSITE answers that are both correct. `labels.inter_annotator()` reads that
#: as disagreement and depresses the Axis B ceiling -- which makes every model
#: score denominated in it read as BETTER than it is. eval_labels.labeller_id is
#: app_users.id (label.py, submit_label), so the decomposition is a plain join
#: and neither labels.py function needs to change. Axis A is unaffected: its
#: rows carry no profile at all, enforced by eval_labels_axis_shape.
#:
#: DERIVED, NOT INVENTED. The first eight are the industry list in
#: config/pursuit-persona.json's `background_summary`, verbatim and in its
#: order: "healthcare, education, retail, hospitality, logistics,
#: administration, the trades, the military".
#:
#: `other` is a real domain this list does not name, priced as no-information
#: the way config/pursuit-criteria.json's `_archetypes_other_comment` prices the
#: archetype of the same name -- "no information, no verdict", never a penalty.
#:
#: `none` IS NOT NULL AND THE DISTINCTION IS THE POINT. background_summary says
#: the cohort is "early-career AND career-changing adults", so a Builder with no
#: prior domain is a real answer about a real person. NULL means NOBODY ASKED.
#: Collapsing the two would score an unasked labeller as a labeller with no
#: background, which is the same conflation `_seniority_unknown_comment` refuses
#: for seniority and that labels.py refuses for the "I cannot tell" abstention.
PRIOR_DOMAINS = (
    "healthcare", "education", "retail", "hospitality",
    "logistics", "administration", "trades", "military",
    "other", "none",
)

#: The CHECK is generated from PRIOR_DOMAINS rather than typed out beside it, so
#: the vocabulary cannot be widened in Python while the database keeps refusing
#: the new value -- a failure that would surface as a 500 on one operator's
#: command and nowhere else.
_PRIOR_DOMAIN_CHECK = (
    "prior_domain IS NULL OR prior_domain IN ("
    + ", ".join(f"'{v}'" for v in PRIOR_DOMAINS) + ")"
)

#: Why a Builder dismissed a posting (tranche_five/27, consumed by
#: tranche_six/31). A closed enum rather than free text, and the values map onto
#: existing features deliberately: a `wrong_level` dismiss is evidence about the
#: seniority weight, not about one posting. Free text would be unreadable at
#: cohort scale and un-joinable to any feature.
#:
#: IT LIVES HERE RATHER THAN IN jobs.py, WHERE IT WAS, for the reason
#: PRIOR_DOMAINS lives here: the CHECK below is generated from this tuple, so
#: the vocabulary cannot be widened in Python while the database keeps refusing
#: the new value -- a failure that would surface as a 500 on one Builder's
#: dismiss and nowhere else. jobs.py imports it back and the request validator
#: still reads `jobs.DISMISS_REASONS`; nothing here imports jobs.
DISMISS_REASONS = ("wrong_level", "wrong_role", "wrong_location",
                   "bad_company", "stale_posting", "other")

_DISMISS_REASON_CHECK = (
    "dismiss_reason IS NULL OR dismiss_reason IN ("
    + ", ".join(f"'{v}'" for v in DISMISS_REASONS) + ")"
)


def _ensure_prior_domain(conn):
    """Add prior_domain and its CHECK to an app_users that predates them.

    CREATE TABLE IF NOT EXISTS is a no-op on a table that already exists, so it
    carries a new column to fresh databases only. This one already has a row --
    the repo owner's, and it is the labeller behind every row in eval_labels --
    so without this the column would exist in the DDL and nowhere the labels
    are.

    Routed through dbconn.add_missing_columns rather than a bare ADD COLUMN IF
    NOT EXISTS for the reason that function documents at length: the IF NOT
    EXISTS form still takes an ACCESS EXCLUSIVE lock when the column is already
    there, so issuing it every run makes every run contend with ordinary
    readers. The catalog check means the steady state issues no DDL at all.

    The constraint is guarded the same way and for the same reason. Adding it
    scans the table, which is free at one row and is not a habit worth forming.
    """
    added = dbconn.add_missing_columns(conn, "app_users",
                                       [("prior_domain", "TEXT")])
    present = conn.execute(
        "SELECT 1 FROM pg_constraint WHERE conname = 'app_users_prior_domain'"
    ).fetchone()
    if not present:
        conn.execute("ALTER TABLE app_users ADD CONSTRAINT "
                     f"app_users_prior_domain CHECK ({_PRIOR_DOMAIN_CHECK})")
        conn.commit()
    return added


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

    conn.execute(f"""
        CREATE TABLE IF NOT EXISTS app_users (
            id TEXT PRIMARY KEY,
            email TEXT NOT NULL UNIQUE,
            google_sub TEXT UNIQUE,
            display_name TEXT,
            profile TEXT NOT NULL,
            prior_domain TEXT,
            is_admin BOOLEAN NOT NULL DEFAULT FALSE,
            active BOOLEAN NOT NULL DEFAULT TRUE,
            created_at TEXT NOT NULL,
            last_login_at TEXT,
            CONSTRAINT app_users_prior_domain CHECK ({_PRIOR_DOMAIN_CHECK})
        )
    """)
    _ensure_prior_domain(conn)
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

    conn.execute(f"""
        CREATE TABLE IF NOT EXISTS builder_job_state (
            app_user_id TEXT NOT NULL REFERENCES app_users(id) ON DELETE CASCADE,
            job_id TEXT NOT NULL,
            dismissed_at TEXT,
            dismiss_reason TEXT,
            saved_at TEXT,
            updated_at TEXT NOT NULL,
            PRIMARY KEY (app_user_id, job_id),
            CONSTRAINT builder_job_state_reason CHECK ({_DISMISS_REASON_CHECK}),
            -- A reason without a dismissal is a row that survived a bad undo.
            -- Cheap to forbid, and it makes the aggregation in
            -- tools/dismiss-reasons.py able to trust its own WHERE clause.
            CONSTRAINT builder_job_state_reason_needs_dismissal
                CHECK (dismiss_reason IS NULL OR dismissed_at IS NOT NULL)
        )
    """)
    # WHY THIS TABLE EXISTS: job_matches is keyed (job_id, profile) and thirty
    # Builders share one cohort profile, so a demotion written into match_score
    # would suppress a posting for all thirty. Per-Builder state goes here and
    # applies as a read-time join instead; ranking stays cohort-level and cheap,
    # which is the flat-cost property in ../.claude/CLAUDE.md. tranche_six/31.
    #
    # job_id IS BARE TEXT WITH NO FOREIGN KEY to jobs(id), for the same reason
    # app_users.profile carries none: a real FK would make this service's DDL
    # depend on a table it must not own. The exposure that creates is a jobs.id
    # rewrite (../schema.py's _ensure_fk_update_cascade exists because ids do
    # get rewritten) stranding a state row -- and the consequence is nil,
    # because a state row is only ever read joined to jobs_app. A stranded row
    # is invisible, not harmful.
    #
    # NOT AN EVENT LOG. job_events is the append-only evidence and keeps every
    # dismiss and every undo; this is the current answer, and it is derived from
    # those rows rather than a second source of truth. The two are written in
    # one transaction (jobs.record_events) so they cannot disagree.

    conn.execute("CREATE INDEX IF NOT EXISTS idx_app_sessions_user "
                 "ON app_sessions(user_id)")
    # The list's hot path: "which of this Builder's states apply to the page I
    # am rendering". The primary key already leads with app_user_id, so this
    # index is the covering half of it -- one partial index over the rows that
    # actually filter anything, since the overwhelming majority of state rows
    # are saves with dismissed_at NULL.
    conn.execute("CREATE INDEX IF NOT EXISTS idx_builder_job_state_dismissed "
                 "ON builder_job_state(app_user_id, job_id) "
                 "WHERE dismissed_at IS NOT NULL")
    conn.commit()

    # The golden-set tables, created by their own module's DDL. One definition
    # per table: `python3 -m evals label init-schema` reaches the same
    # function, so the operator can create them from either side and the two
    # cannot drift. Nothing is inserted -- the tables ship empty and stay that
    # way until people label.
    _labels.ensure_schema(conn)


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

    for table, columns in REQUIRED_COLUMNS.items():
        if conn.execute("SELECT to_regclass(%s)", (f"public.{table}",)
                        ).fetchone()[0] is None:
            continue        # already reported as missing above
        present = {r[0] for r in conn.execute(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_schema = 'public' AND table_name = %s", (table,)).fetchall()}
        absent = [c for c in columns if c not in present]
        if absent:
            problems.append(
                f"public.{table}: missing column(s) {', '.join(absent)} -- run the "
                f"pipeline's schema migration")

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

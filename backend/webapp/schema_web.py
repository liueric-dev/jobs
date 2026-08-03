"""
The five tables this service owns, and the startup gate that proves it can
use them.

SCHEMA OWNERSHIP. ../schema.py owns `jobs`, `job_facts`, `job_matches`,
`job_scores`, `profiles`, `job_events` and the `jobs_app` view. This module
declares ONLY app_users, app_sessions, oauth_logins, builder_job_state and
builder_profiles, and never drops, alters or restates anything on the other
side of that line. api/query_claims.py
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
    # Read-only, and read-only is the whole point: the suppression rule lives
    # in the pipeline's nightly fold and this service must not be able to write
    # a bucket it did not compute. Pipeline-owned, so SELECT-only for the same
    # reason jobs/job_matches/job_scores are.
    #
    # AND WHEN IT WAS ADDED, NOTHING WAS WATCHING FOR IT -- which is why this
    # entry has a paragraph and its neighbours have a line. test_grants' scanner
    # USED TO keep only string literals containing SELECT|INSERT|UPDATE|DELETE,
    # and jobs.py names this table solely in a bare `LEFT JOIN cohort_signal cs
    # ON ...` fragment, which contains none of those words -- so the string was
    # dropped before table names were looked for. The suite was green with no
    # entry here and no grant, and the first GET /v1/jobs would have been
    # `permission denied for table cohort_signal` on a Builder's first click.
    #
    # THAT HOLE IS CLOSED: D69, fixed in tests/test_grants.py, which now keeps a
    # string that is a statement OR a join clause (`_JOIN_CLAUSE`), so
    # tables_named_in('jobs.py') finds this table and a missing entry fails.
    # Kept in the past tense rather than deleted, because "nothing was watching"
    # is the actual reason this line exists.
    #
    # AND IT IS STILL THE ONLY ENTRY IN THIS DICT THAT DEPENDS ON THAT FIX.
    # Measured across every module in SERVICE_MODULES, not assumed: every other
    # table named in this package's SQL appears in a string that also carries a
    # statement keyword, so `_STATEMENT` alone would find it. This one appears
    # ONLY in the join fragment. Narrow the scanner back and it re-hides
    # immediately -- which is why the paragraph above is worth its length.
    # (No count is typed here on purpose: SERVICE_MODULES has grown twice since
    # this line was written, and a number here would have been wrong both times.)
    #
    # THAT IS NOT THE SAME AS "everything else is checked". Entries below are
    # justified in ways NO version of this scanner can derive -- the view
    # expansion above all. test_grants.sql_strings_in()'s docstring owns that
    # list; it is not restated here, because a second copy of it is exactly the
    # drift the ownership rule at the top of this file exists to prevent.
    # tranche_five/28, D69.
    "cohort_signal": ("SELECT",),
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
    # The per-Builder override row (tranche_five/26). Upserted by
    # POST /v1/onboarding and re-read on every resolution, so SELECT, INSERT
    # and UPDATE. No DELETE: clearing an override is a column going back to
    # NULL, exactly as it is on builder_job_state, and for the same reason --
    # the OTHER columns may be carrying live answers.
    "builder_profiles": ("SELECT", "INSERT", "UPDATE"),
    # -- the search-query tables (tranche_four/25) --------------------------
    #
    # PIPELINE-OWNED, ALL FOUR. ../schema.py declares them, because the pipeline
    # is what runs these queries, updates their run statistics, folds their
    # watcher counts and decays them. Ownership follows who COMPUTES, not who is
    # nearest the user. Listed here for the same reason `jobs` is: the startup
    # check has to prove this role can reach them before a Builder's first click
    # finds out.
    #
    # INSERT BUT NO UPDATE on search_queries. Registering a query is this
    # service's job; run_count, last_run_at, result_count_last_run and
    # retired_at are the pipeline's, and an UPDATE grant would let a
    # session-hijacking bug rewrite the schedule. The find-or-create still
    # works without it: searchnorm.REGISTER_QUERY_SQL's ON CONFLICT branch
    # assigns a column to itself, so the "update" changes nothing and needs
    # nothing.
    "search_queries": ("SELECT", "INSERT"),
    # Watch and unwatch. UPDATE rather than DELETE, matching builder_job_state
    # above: unwatching sets removed_at. A DELETE grant on the one table that
    # records who is looking for what is the grant this design least wants to
    # issue.
    "search_query_watchers": ("SELECT", "INSERT", "UPDATE"),
    # SELECT ONLY, AND THIS ENTRY IS THE POINT OF THE WHOLE ARRANGEMENT. This
    # table carries the exposed watcher bucket. The suppression rule lives in
    # the pipeline's nightly fold (../searchqueries.py, fold_signal) and this
    # service must not be able to write a bucket it did not compute -- which is
    # why the count is a separate table rather than a column on search_queries,
    # a table this service can INSERT into.
    "search_query_signal": ("SELECT",),
    # SELECT ONLY. Attaching a posting to a search is a pipeline act. A service
    # that could write here could put a posting in front of a Builder without it
    # ever having passed relevance.py -- the "no shortcut to display" rule in
    # tranche_four/25, made a privilege rather than a convention.
    #
    # THE SAME SHAPE AS cohort_signal ABOVE, DELIBERATELY. That entry states the
    # rule this one is built on -- the suppression rule lives in the pipeline's
    # nightly fold and this service must not be able to write a bucket it did
    # not compute -- and two different answers to "who may write an aggregate"
    # is how a privacy promise gets broken by accident.
    "search_query_results": ("SELECT",),
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
    # search_queries.id is BIGSERIAL and this service INSERTs into it, so the
    # same argument applies unchanged: without USAGE on the sequence, INSERT on
    # the table is a permission error at nextval() -- a 500 on the first search
    # anyone submits rather than a refusal to start.
    "search_queries_id_seq": ("USAGE", "SELECT"),
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
    # Added to eval_labels 2026-08-02, and the migration that creates them is
    # `evals label init` -- run by hand by an operator, not by the nightly
    # pipeline. So the window this entry closes is WIDER than job_events':
    # there, a nightly run repairs the drift within a day; here, nothing
    # repairs it until someone remembers. labels.record() names both columns
    # unconditionally.
    "eval_labels": ("facts_version", "facts_version_known"),
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


def _enum_check(column, vocabulary):
    """`col IS NULL OR col IN (...)`, generated from a Python tuple.

    The three vocabularies below were each about to be a fourth copy of the six
    lines PRIOR_DOMAINS and DISMISS_REASONS write out. Those two are left
    written out deliberately -- tests/test_prior_domain.py asserts on
    _PRIOR_DOMAIN_CHECK's text and moving it would be a change to a landed
    thing for a cosmetic reason -- but nothing new should add a fifth.

    NULL IS ADMITTED BY EVERY ONE OF THEM, and it is not laziness. It is the
    same distinction PRIOR_DOMAINS draws at length: NULL means NOBODY ASKED,
    which is the honest value for every Builder who existed before onboarding
    did. A vocabulary that cannot say "unasked" forces a wrong answer into the
    column on the day it ships.
    """
    return (f"{column} IS NULL OR {column} IN ("
            + ", ".join(f"'{v}'" for v in vocabulary) + ")")


def _subset_check(column, vocabulary):
    """`col IS NULL OR col <@ ARRAY[...]` for a TEXT[] column.

    Array containment rather than an IN list, because the column holds a SET of
    answers rather than one. `<@` is true for the empty array, which is
    deliberate and is the distinction above wearing different clothes: `{}` is
    "asked, and there are none", NULL is "nobody asked". A Builder with no
    schedule constraints is a real Builder.
    """
    return (f"{column} IS NULL OR {column} <@ ARRAY["
            + ", ".join(f"'{v}'" for v in vocabulary) + "]::text[]")


#: A Builder's current employment state, collected by POST /v1/onboarding.
#:
#: WHAT IT IS FOR: it is the one onboarding field that is about urgency rather
#: than about matching. Nothing scores on it and nothing filters on it today.
#: It exists so that "this Builder has been out of work for four months" is
#: answerable at all when somebody asks why the list is not converting, which
#: is a question about the cohort that no job column can answer.
#:
#: DERIVED, NOT INVENTED, and the derivation is thinner than PRIOR_DOMAINS'.
#: `employed_seeking` is verbatim from the frozen contract fixture
#: (frontend/fixtures/contract/ASPIRATIONAL_POST_v1_onboarding.request.json,
#: itself verbatim from API-CONTRACT-v1.md § POST /v1/onboarding, deleted
#: 2026-08-02 -- `git show
#: refactor-freeze-2026-08-02:docs/tasks/refactor/API-CONTRACT-v1.md`)
#: and is the only value attested anywhere in the repo.
#: `in_program` is config/pursuit-persona.json's background_summary in its own
#: words -- the cohort is "completing an intensive, hands-off program".
#: `unemployed_seeking` is the negation the attested value implies: a
#: vocabulary offering "employed and looking" and no way to say "not employed
#: and looking" forces every unemployed Builder onto `other`, which is the
#: conflation PRIOR_DOMAINS refuses between `none` and NULL.
#:
#: `other` is priced as no-information, the way PRIOR_DOMAINS' `other` is and
#: the way config/pursuit-criteria.json's `_archetypes_other_comment` prices
#: the archetype of the same name: no information, no verdict, never a penalty.
#:
#: THIS VOCABULARY IS UNVALIDATED AGAINST REAL BUILDERS, and PRIOR_DOMAINS is
#: the warning: it was derived just as carefully and HANDOFF.md records that it
#: already fails on the one real user in the table. Widening either is a
#: decision -- it moves a CHECK constraint generated from it -- and not a
#: tidy-up. Do not do it in passing.
SITUATIONS = ("employed_seeking", "unemployed_seeking", "in_program", "other")

_SITUATION_CHECK = _enum_check("situation", SITUATIONS)

#: Where a Builder will work. THREE VALUES BECAUSE THE READ PATH HAS TWO
#: BOOLEANS: jobs_app exposes `location_is_nyc` and `location_is_remote`
#: (../schema.py; jobs.py LIST_COLUMNS), and GET /v1/jobs already filters on
#: exactly those two (jobs.py, the `nyc` and `remote` query parameters). A
#: preference vocabulary richer than the columns that would have to satisfy it
#: is a promise the list cannot keep, so this is deliberately the coarsest
#: thing that maps onto a WHERE clause that exists.
#:
#: `either` is the permissive answer and is the shared default -- see
#: onboarding.DEFAULTS. A preference nobody expressed must not silently filter,
#: which is the same argument relevance.DISABLED makes for a missing config.
LOCATION_PREFS = ("nyc", "remote", "either")

_LOCATION_PREF_CHECK = _enum_check("location_pref", LOCATION_PREFS)

#: The least-flexible arrangement a Builder will accept, as a threshold over
#: ../extract.py's REMOTE_POLICY ("onsite", "hybrid", "remote_local",
#: "remote_anywhere", "unknown") rather than a second vocabulary beside it.
#: `hybrid_ok` is the contract fixture's value; the other two are its ends.
#:
#: A THRESHOLD, NOT A SET, because the underlying enum is ordered by how much
#: presence it demands and every real preference is "this or better". Storing a
#: set would let a Builder express "hybrid but not remote", which nobody wants
#: and which would then have to be honoured forever.
#:
#: `unknown` IS NEVER FILTERED OUT BY ANY OF THESE, at any threshold. It is
#: extract.py's abstention, not an arrangement, and dropping a posting because
#: the extractor could not tell would be silence deciding an outcome -- the
#: failure mode ../.claude/CLAUDE.md names as this system's default one.
REMOTE_PREFS = ("onsite_ok", "hybrid_ok", "remote_only")

_REMOTE_PREF_CHECK = _enum_check("remote_pref", REMOTE_PREFS)

#: Hard scheduling limits, as a set. ONE VALUE, AND THAT IS THE HONEST SIZE OF
#: IT: `no_overnight` is the only schedule constraint attested anywhere in this
#: repo -- it is the contract fixture's, and the contract's. Every obvious
#: sibling (`no_weekends`, `daytime_only`, `no_travel`) is an invention, and
#: inventing a vocabulary for a population nobody has asked yet is exactly what
#: config/pursuit-persona.json's `_population_not_person_comment` calls
#: "anything narrower is invented".
#:
#: So this ships with what is attested and refuses the rest, and widening it is
#: a decision taken with a real Builder's answer in hand. That is the same
#: treatment PRIOR_DOMAINS gets, and the same reason.
SCHEDULE_CONSTRAINTS = ("no_overnight",)

_SCHEDULE_CONSTRAINTS_CHECK = _subset_check("schedule_constraints",
                                            SCHEDULE_CONSTRAINTS)


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


def _ensure_app_users_profile_key(conn):
    """Add UNIQUE (id, profile) to an app_users that predates builder_profiles.

    A REDUNDANT-LOOKING KEY THAT IS DOING REAL WORK. `id` is already the
    primary key, so (id, profile) is unique for free and this index can never
    reject a row. It exists because Postgres will only accept a FOREIGN KEY
    whose referenced column list is covered by a unique constraint, and
    builder_profiles wants a composite one -- see the block beside that table
    for what it buys and why the alternative was not available.

    Same guard as _ensure_prior_domain and for the reason dbconn's
    add_missing_columns documents: ADD CONSTRAINT scans the table and takes a
    heavy lock, which is free at three rows and is not a habit worth forming.
    Checking the catalog first means the steady state issues no DDL at all.
    """
    present = conn.execute(
        "SELECT 1 FROM pg_constraint WHERE conname = 'app_users_id_profile'"
    ).fetchone()
    if not present:
        conn.execute("ALTER TABLE app_users ADD CONSTRAINT app_users_id_profile "
                     "UNIQUE (id, profile)")
        conn.commit()


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
            CONSTRAINT app_users_prior_domain CHECK ({_PRIOR_DOMAIN_CHECK}),
            -- Redundant against the primary key and referenced by
            -- builder_profiles. See _ensure_app_users_profile_key.
            CONSTRAINT app_users_id_profile UNIQUE (id, profile)
        )
    """)
    _ensure_prior_domain(conn)
    _ensure_app_users_profile_key(conn)
    # profile is bare TEXT with NO foreign key to profiles(profile), matching
    # job_scores.profile and job_matches.profile in ../schema.py. A real FK
    # would make this service's DDL depend on a table it must not own, which is
    # the coupling the ownership rule above exists to prevent.
    # manage_app_users.py validates the profile with profiles.load_one()
    # instead -- the right place for it, since that function deliberately
    # returns paused profiles too.
    #
    # tranche_five/26 ASKED FOR THAT DECISION TO BE REPLACED, calling it "a
    # design to replace rather than an unknown to discover". It is not
    # replaced, and this is the reasoning, because the next person will ask.
    #
    # THE OBSTACLE IS NOT THE REFERENCED SIDE. profiles.profile is TEXT PRIMARY
    # KEY (../schema.py), so it is referencable; and ensure_schema() below
    # already calls schema.ensure_schema() first, on this same connection and
    # this same admin credential, so the table is guaranteed to exist before
    # this DDL runs. Neither shape nor ordering nor privilege forbids it.
    #
    # WHAT FORBIDS IT IS THAT A FOREIGN KEY IS DDL ON BOTH TABLES. Postgres
    # implements referential integrity with system triggers, and the ON
    # DELETE / ON UPDATE half of them is installed on the REFERENCED table --
    # so `REFERENCES profiles(profile)` puts pg_trigger rows on a
    # pipeline-owned table, takes a lock on it that blocks the pipeline's own
    # writes for the duration of the migration, and thereafter makes every
    # DELETE from profiles this service's business. "Never alters anything on
    # the other side of that line" is the rule at the top of this file, and a
    # constraint that adds triggers to profiles alters profiles.
    #
    # AND IT WOULD BE ENFORCED IN THE WRONG DIRECTION ANYWAY. The failure worth
    # catching is a Builder pointed at a profile that does not exist. An FK
    # catches that at INSERT time on app_users -- which manage_app_users.py
    # already does, with a better error -- and spends the rest of its life
    # refusing the pipeline's DELETEs, which is not a thing anyone wanted.
    #
    # SO IT IS ENFORCED THREE OTHER PLACES, none of them a constraint:
    #   write time   manage_app_users.py's profiles.load_one() check, on `add`
    #                and on `set-profile` -- the two writers of the column.
    #   deploy time  verify_schema() below now re-checks the WHOLE table, so a
    #                row written by a hand-typed UPDATE (which README tells
    #                operators not to do, and which skips the check above) is a
    #                refusal to start rather than a 500 on that Builder's next
    #                click. That is the same argument the grant and column
    #                checks in that function are already made from.
    #   request time onboarding.py refuses to write a builder_profiles row for
    #                a caller whose profile has no profiles row.
    #
    # WHAT *IS* A REAL FOREIGN KEY IS THE HALF THAT CAN BE ONE: builder_profiles
    # references app_users(id, profile) compositely, so the two places a
    # Builder's profile name is stored cannot disagree. See that table.

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

    conn.execute(f"""
        CREATE TABLE IF NOT EXISTS builder_profiles (
            app_user_id TEXT NOT NULL,
            parent_profile TEXT NOT NULL,
            location_pref TEXT,
            remote_pref TEXT,
            comp_floor INTEGER,
            tracks TEXT[],
            prior_years INTEGER,
            situation TEXT,
            schedule_constraints TEXT[],
            onboarded_at TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            PRIMARY KEY (app_user_id),
            CONSTRAINT builder_profiles_parent
                FOREIGN KEY (app_user_id, parent_profile)
                REFERENCES app_users(id, profile)
                ON DELETE CASCADE ON UPDATE CASCADE,
            CONSTRAINT builder_profiles_location_pref
                CHECK ({_LOCATION_PREF_CHECK}),
            CONSTRAINT builder_profiles_remote_pref
                CHECK ({_REMOTE_PREF_CHECK}),
            CONSTRAINT builder_profiles_situation
                CHECK ({_SITUATION_CHECK}),
            CONSTRAINT builder_profiles_schedule_constraints
                CHECK ({_SCHEDULE_CONSTRAINTS_CHECK}),
            -- A negative floor is not a preference and a negative year count is
            -- not a career. Both are cheap to forbid and both would otherwise
            -- reach the resolution merge, where a comp_floor of -1 quietly
            -- means "no floor" and reads as though somebody chose it.
            CONSTRAINT builder_profiles_comp_floor
                CHECK (comp_floor IS NULL OR comp_floor >= 0),
            CONSTRAINT builder_profiles_prior_years
                CHECK (prior_years IS NULL OR prior_years >= 0)
        )
    """)
    # WHY THIS TABLE EXISTS: tranche_five/26's "inheritance, not authoring".
    # Nobody is hand-authoring thirty criteria_json files, so a Builder does NOT
    # get a `profiles` row. The cohort profile carries persona_json,
    # criteria_json and relevance_json for all thirty, and this table carries
    # only what genuinely varies per person. Resolution is Builder override,
    # else cohort, else shared default -- onboarding.resolve(), which follows
    # relevance.load()'s merge rather than inventing a second one.
    #
    # It is the same fixed-effect/random-effect split as builder_job_state
    # above and as the ranker's eventual global-plus-residual shape, kept
    # deliberately consistent so the per-Builder residual has an obvious place
    # to live later.
    #
    # THE FOREIGN KEY IS COMPOSITE, AND THAT IS THE WHOLE POINT OF IT. The task
    # sketched `parent_profile REFERENCES profiles(profile)`, which cannot be
    # written here -- see the app_users block above for why an FK onto a
    # pipeline-owned table is DDL on the other side of the ownership line. What
    # CAN be written is a reference to app_users(id, profile), which is on this
    # service's own side, and it is strictly the more useful constraint:
    #
    #   * A Builder's profile is now stored in two places -- app_users.profile,
    #     which auth.require_user() puts in the session and which every query in
    #     jobs.py scopes by, and parent_profile, which decides which cohort's
    #     criteria resolve. THEY CANNOT DISAGREE, by constraint. Two answers to
    #     "which cohort is this Builder in" is how D66/D67 happened one level
    #     down, and a Builder ranked by one cohort's weights while being served
    #     another cohort's list would be the same bug wearing a bigger coat.
    #   * ON UPDATE CASCADE IS THE COHORT LIFECYCLE, implemented rather than
    #     left implicit. Classes are rolling: a new cohort gets a new cohort
    #     profile seeded from the previous one's criteria_json
    #     (migrations/migrate_profiles.py --seed-from), and Builders move onto
    #     it with manage_app_users.py set-profile, which is one UPDATE of
    #     app_users.profile. The cascade carries every override row with it. A
    #     graduated Builder who is NOT moved keeps their old cohort profile and
    #     keeps working, which is what the task asks for -- their row is never
    #     touched.
    #   * ON DELETE CASCADE for the reason builder_job_state has one: an
    #     override for a user who no longer exists is unreachable, not evidence.
    #
    # NOTHING HERE IS A CACHE KEY AND NOTHING HERE IS VERSIONED. Every column is
    # an answer a person gave about themselves, so there is no upstream whose
    # version could make a row stale -- which is why this table carries none of
    # the four version columns job_scores does (../.claude/CLAUDE.md, "Versions
    # are cache keys"). onboarded_at is a timestamp, not a version.
    #
    # `tracks` IS THE ONE COLUMN WITH NO CHECK, deliberately. It is DERIVED
    # server-side from job_scores.primary_track rather than sent by a client
    # (onboarding.derive_tracks), so the argument that makes DISMISS_REASONS and
    # the four vocabularies above closed sets -- a typo'd client value is
    # silently unusable data -- does not apply: the only writer is a SELECT off
    # a column the pipeline populated. And the track vocabulary is genuinely
    # undecided: score.TRACKS is the AUTHOR'S five names, config/
    # pursuit-persona.json's `_no_buckets_comment` records that they "do not
    # describe this population", and choosing the cohort's is task 30's. A CHECK
    # generated from a vocabulary nobody has decided would constrain the
    # decision rather than the data.
    #
    # NULL vs {} ON THE TWO ARRAY COLUMNS. NULL is "nobody asked"; {} is "asked,
    # and the answer is none". That is PRIOR_DOMAINS' `none`-is-not-NULL
    # distinction applied to a set, and it matters in opposite directions on the
    # two columns: a Builder with no schedule constraints is a real Builder and
    # writes {}, whereas derive_tracks leaves `tracks` NULL rather than writing
    # {} when it finds nothing, because "subscribed to no tracks" is not an
    # answer anybody gave and would be indistinguishable from one.

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

    ONE DATA CHECK LIVES HERE AND THE REST ARE STRUCTURE. app_users.profile has
    no foreign key to profiles(profile) and cannot be given one -- the reasoning
    is beside that column in ensure_schema(). Checking the whole table here is
    what stands in for it at deploy time: manage_app_users.py validates on the
    two supported writes, and this catches everything that went round them,
    which is the hand-typed UPDATE README tells operators not to do. It is the
    same trade the checks above already make -- a deployment error named at
    startup instead of a 500 on one Builder's first click -- applied to a row
    rather than to a grant.

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

    problems.extend(profile_mapping_problems(conn))

    if problems:
        raise RuntimeError(
            f"database is not ready for this service ({dbconn.scrub_url()}) -- "
            + "; ".join(problems)
            + ". Run `python3 manage_app_users.py init-schema` with an admin "
              "credential (JOBS_ADMIN_DATABASE_URL), and check the GRANTs in "
              "README 'Database privileges'."
        )


def profile_mapping_problems(conn):
    """Every app_users.profile with no `profiles` row. The absent foreign key.

    A list of strings rather than a raise, so verify_schema() can report it
    beside the grant and column problems instead of ahead of them -- an operator
    fixing a deployment wants all of it at once.

    SEPARATE FROM verify_schema() BECAUSE IT ASKS A DIFFERENT KIND OF QUESTION.
    Everything else in that function is about structure and privilege and is
    true or false about an empty database; this is about rows. Splitting it out
    keeps that honest and makes it callable on its own -- manage_app_users.py
    could reasonably run it after a bulk import, and a test can assert on it
    without standing up the startup path.

    RETURNS EMPTY WHEN EITHER TABLE IS MISSING, on purpose. A missing table is
    already reported by the caller, and a second complaint derived from the
    first would bury it.

    THE SQL BELOW RUNS AS THE SERVICE ROLE AND IS NOW WATCHED BY
    tests/test_grants.py -- D69 residue part 3, closed 2026-08-02. It used to be
    the one place in the package where a service-role query's tables were
    declared by hand and checked by nothing: this file was excluded from
    SERVICE_MODULES deliberately, because it also holds the admin-only DDL above
    and every CREATE was assumed to read as a table the service needs granted.

    THAT ASSUMPTION WAS WRONG, which is why the exclusion could go. The scanner
    keys on FROM/JOIN/INTO/UPDATE, and `CREATE TABLE IF NOT EXISTS <name>`
    matches none of them, so the DDL contributes no table name at all. What the
    exclusion actually cost was this query. Both its tables, `app_users` and
    `profiles`, were already in REQUIRED_TABLES with SELECT for other reasons, so
    nothing was missing when it was found -- but a query added here naming a
    THIRD table would have needed its own entry and would have gone red nowhere.
    Now it goes red here. Kept in the past tense rather than deleted, because
    "checked by nothing" is the reason this paragraph exists.
    """
    for table in ("app_users", "profiles"):
        if conn.execute("SELECT to_regclass(%s)", (f"public.{table}",)
                        ).fetchone()[0] is None:
            return []
    orphans = conn.execute(
        """
        SELECT u.profile, count(*)
        FROM app_users u
        WHERE NOT EXISTS (SELECT 1 FROM profiles p WHERE p.profile = u.profile)
        GROUP BY u.profile ORDER BY u.profile
        """
    ).fetchall()
    return [
        f"public.app_users: {count} user(s) point at profile {profile!r}, which "
        f"has no row in public.profiles -- create it with "
        f"`python3 migrations/migrate_profiles.py --apply --new-cohort "
        f"--profile {profile}`, or move them with `manage_app_users.py "
        f"set-profile`"
        for profile, count in orphans
    ]


def prune_expired_logins(conn):
    """Delete abandoned oauth_logins rows.

    Called from the callback rather than a timer: this table is only ever
    touched by logins, so a login is exactly when it is worth a cheap DELETE.
    An abandoned row is harmless -- it is single-use and expiry-checked -- but
    without this it stays forever.
    """
    conn.execute("DELETE FROM oauth_logins WHERE expires_at < %s", (utc_now_str(),))

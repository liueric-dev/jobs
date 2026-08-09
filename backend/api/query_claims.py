"""
Claim/staleness/normalization logic for the crowdsourced jobs API.

RELATIONSHIP TO THE PIPELINE -- REWRITTEN IN SLICE D, AND THE OLD VERSION OF
THIS PARAGRAPH IS WORTH KNOWING ABOUT. It used to say this file was a
deliberate, self-contained REIMPLEMENTATION with "intentionally zero code
dependency", on the argument that correctness lives in a Postgres row rather
than in shared application code.

That argument was right about the *claim*, and wrong about everything else.
Row-level locking really does make "two claimants never get the same query"
hold across two codebases, and try_claim_query() below is still deliberately
its own SQL for that reason. But the rest of what this file had copied was not
protected by any row: nine functions and the DDL for three tables, which had
drifted six ways by the time slice D measured them --

    strip_html truncated at 5000 where lib/text.py uses 20000
    parse_relative_posted_at knew neither minutes, "an hour ago", nor
        "yesterday", and returned None where the pipeline returned a timestamp
    raw_json sliced serialized JSON mid-string instead of bounded_json
    posted_at_ts and salary_text were missing from normalize_job, from the
        CREATE TABLE, and from the upsert column lists
    upsert had no per-record SAVEPOINT, so one bad row lost a whole batch
    the job_ingest_state migration took an unnecessary exclusive lock

The first two change content_hash, which is row identity for ~23,500 stored
digests: the same posting written by the pipeline and then through this API
produced two different digests, so each write counted the other's row as
"updated" and rewrote it. That was latent only because this service has never
been deployed. So the two are now co-located in one repo and this file imports
what it used to copy.

WHAT IS STILL DELIBERATELY SEPARATE: the claim SQL (try_claim_query,
holds_claim, mark_success, release_claim). It is a superset of lib.state's
-- it adds claimed_by and claim_granted_at -- because this service must answer
"does this contributor still own the claim they are submitting against?", a
question the pipeline never asks. Keep it operating on the same row with the
same conditional-update shape and it stays compatible.

THERE ARE TWO CLAIM MODES, over two different tables. The four functions above
lease a DATASET STRING in job_ingest_state; try_claim_search_query,
holds_search_query_claim and release_search_query_claim lease one
`search_queries` ROW, which is what docs/adr/0007 dispatches per query. Same two
protections, mirrored rather than re-derived -- the section above those three
says what differs and why, and it is one thing, not several.

SCHEMA OWNERSHIP: ../schema.py owns the jobs table, the watermark table,
google_jobs_query_stats and search_queries; ensure_schema() below calls it
rather than restating it. This module declares only the three contributor
tables and the two extra claim columns on job_ingest_state, and never drops or
rewrites anything the pipeline owns -- search_queries' claim columns are
declared in ../schema.py with the rest of that table, so the one command that
stands a database up from nothing creates them (see TASKS.md's T-26).
"""

import hashlib
import json
import os
import secrets
import sys
from datetime import datetime, timedelta, timezone
from typing import NamedTuple

# api/ sits one level below the pipeline modules it shares code with. Python
# puts THIS file's directory on sys.path, not its parent, so the parent is
# added by hand. That one insert reaches BOTH ../schema.py and ../lib/, which
# is why there is nothing to install: this venv sets
# include-system-site-packages = false, and before lib/ was vendored that meant
# the shared library needed a second editable install in here, whose only
# symptom when forgotten was an ImportError under uvicorn and nowhere else.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import schema  # noqa: E402  (../schema.py -- the pipeline owns the jobs DDL)
import searchqueries  # noqa: E402  (../searchqueries.py -- owns the run statistics)
from google_jobs import normalize_job  # noqa: E402,F401  (re-exported; app.py calls it)
from lib import dbconn  # noqa: E402
from lib.timeparse import utc_now_str  # noqa: E402
from lib.upsert import UpsertErrorRate  # noqa: E402
from lib.upsert import upsert_checked as _lib_upsert_checked  # noqa: E402

#: The same spec both Google ingest scripts build, so all three write
#: identical rows -- including the sticky posted_at that keeps a re-submitted
#: posting's publication date from sliding. One function, three callers.
_JOB_SPEC = schema.google_spec()

#: The `jobs` database, never the events one. This fallback is also what
#: manage_users.py's ADMIN_DATABASE_URL falls back to, so pointing it at
#: nyc_events would run ensure_schema() there as a superuser -- which is how a
#: default nobody reads becomes the destructive path. It carries no password,
#: so an unset DATABASE_URL fails to authenticate rather than connecting to
#: something plausible.
DATABASE_URL = os.environ.get(
    "DATABASE_URL", "postgresql://jobs_api@localhost:5432/jobs"
)

#: Every table this service touches, and the exact privileges it needs on each.
#: The role in DATABASE_URL is granted these and nothing else -- no DELETE
#: anywhere, no DDL, and nothing on the seven pipeline-owned tables or the
#: jobs_app view in the same database. Events data is not merely ungranted but
#: unreachable: it lives in another database this role cannot connect to.
#: app.py verifies all of this at startup instead of creating anything, because
#: a service that faces untrusted input should not hold schema-modification
#: rights.
#:
#: google_jobs_query_stats needs SELECT despite being write-only from this
#: service's point of view: log_query_stats() uses
#: `INSERT ... ON CONFLICT (slug, run_at) DO NOTHING`, and Postgres requires
#: SELECT on the conflict target to evaluate the arbiter index. Granting INSERT
#: alone fails at runtime with "permission denied", not at deploy time -- which
#: is exactly why verify_schema() checks privileges and not just existence.
#:
#: contributor_status is the eighth, added by T-35, and it is the reason
#: `contributors` still reads SELECT/INSERT one line above. The four facts that
#: row reports -- last check-in, worker version, remaining quota, last error --
#: are written by the REQUEST PATH, on every poll, and `contributors` now holds
#: the operator's policy over that same machine. Putting them on `contributors`
#: would therefore have meant granting this role UPDATE on the row that says
#: whether it may grant anything at all: either table-wide, which T-34 refused
#: outright, or column-wise like search_queries below -- and
#: has_table_privilege() answers TRUE on both, so verify_schema() could not tell
#: a narrow grant from a wide one and the safety property would rest on a GRANT
#: nothing checks. A separate table needs no UPDATE on `contributors` at all,
#: which is a property a startup check CAN hold.
REQUIRED_TABLES = {
    "jobs": ("SELECT", "INSERT", "UPDATE"),
    "job_ingest_state": ("SELECT", "INSERT", "UPDATE"),
    "google_jobs_query_stats": ("SELECT", "INSERT"),
    "contributors": ("SELECT", "INSERT"),
    "contributor_status": ("SELECT", "INSERT", "UPDATE"),
    "api_keys": ("SELECT", "INSERT", "UPDATE"),
    "submission_log": ("SELECT", "INSERT"),
    "search_queries": ("SELECT", "UPDATE"),
}

#: search_queries is the seventh table and the only PIPELINE-owned one this
#: service may WRITE, so the grant that backs it is narrower than the line above
#: can express and must be issued column-wise:
#:
#:     GRANT SELECT ON search_queries TO jobs_api;
#:     GRANT UPDATE (claimed_at, claimed_by, claim_granted_at)
#:         ON search_queries TO jobs_api;
#:
#: NOT a table-wide UPDATE. last_run_at, run_count, provider_last_used,
#: result_count_last_run and last_result_at are ../searchqueries.py's, whose
#: record_run() is their only writer by design -- a table-wide grant would let a
#: contributor's submit forge a run history and silence a query for everyone by
#: writing a future last_run_at.
#:
#: THAT IS NOW A DECISION AND NOT ONLY A DEFAULT (docs/adr/0009). The narrowness
#: was written here before anything needed the wider grant; T-38 asked for the
#: run statistics to be advanced after a contributor's submit, which is the
#: first thing that did, and the answer is that they are advanced on the OTHER
#: side of this line rather than by widening it. A "narrow writer in api/ that
#: only sets them from server-side values" was considered and refused: it needs
#: this identical GRANT, so it buys the same exposure and pays for it with a
#: convention rather than a privilege -- and the sentence above says outright
#: that the split is enforced by GRANT and not by comment.
#:
#: NO INSERT either: registering a query is the
#: webapp's act (../schema.py:993), and a service that could insert one could
#: dispatch a Builder's SerpApi credit at a keyword nobody asked for.
#:
#: has_table_privilege(current_user, 'search_queries', 'UPDATE') answers TRUE on
#: a column-level grant, so verify_schema() accepts the narrow form -- what it
#: cannot do is tell the two apart, which is why the columns are written out
#: here and in README rather than left to the reader.
#:
#: THIS IS A NEW STARTUP REQUIREMENT ON AN ALREADY-DEPLOYED SERVICE. Until the
#: two statements above have run, verify_schema() refuses to start and names the
#: missing grant. That is the designed behaviour and the reason this map exists
#: -- the alternative is a service that starts cleanly and 500s on the first
#: claim -- but it is an action on a deployed database, so it is DEV_TASKS.md's
#: `OQ-29` rather than something a session can close.

#: submission_log.id is BIGSERIAL, so INSERT on the table is not enough on its
#: own -- the nextval() needs USAGE on the sequence. README's privilege table
#: has always listed this; until slice D nothing verified it, which made it the
#: one documented grant whose absence surfaced as a 500 on a contributor's
#: first submit rather than as a startup error.
REQUIRED_SEQUENCES = {
    "submission_log_id_seq": ("USAGE", "SELECT"),
}

#: docs/adr/0007 decision 3's desired state: the three settings the server holds
#: per contributor, with the DDL that creates them. ONE LITERAL, read by
#: ensure_schema() (which adds exactly these columns) and by REQUIRED_COLUMNS
#: below (which declares exactly these names) -- the shape
#: MIN_POLL_INTERVAL_SECONDS is annotated with one file over, where a number the
#: code enforces and a number the code schedules on are one edit rather than two
#: that can drift.
#:
#: WHY THEY LIVE ON `contributors` AND NOT ON A TABLE OF THEIR OWN. They are 1:1
#: with a contributor, they are three scalars, and they have no history to keep
#: -- a settings table would be a second place a contributor can be said to
#: exist, would need its own grant and its own "no row yet" branch, and every
#: read of it would be a LEFT JOIN resolving to the same defaults
#: contributor_settings() resolves to from NULL. The cost, stated: `contributors`
#: was identity-only and never updated after INSERT, and this makes it identity
#: AND policy, so the row an audit trail's foreign key points at is now a row
#: that changes. That is accepted rather than unnoticed -- what is lost is the
#: ability to say WHEN a contributor was paused and by whom, which no reader
#: needs today and which TASKS.md's T-55 is filed against.
CONTRIBUTOR_SETTING_COLUMNS = (
    ("paused", "BOOLEAN"),
    ("daily_cap", "INTEGER"),
    ("reserve_floor", "INTEGER"),
)
CONTRIBUTOR_SETTINGS = tuple(name for name, _ in CONTRIBUTOR_SETTING_COLUMNS)

#: TASKS.md's T-35: the four facts that tell a stalled worker from an idle one,
#: in the order contributor_status declares them. One literal, read by the
#: report's SELECT and by the tests that check the DDL spells the same names.
#:
#: EACH REPORTED FACT CARRIES ITS OWN TIMESTAMP, AND THAT IS NOT SYMMETRY FOR
#: ITS OWN SAKE. `last_check_in_at` moves on every poll; a quota and an error do
#: not, because a worker reports them only when it has one to report. Reading
#: the check-in time as the time a balance was reported would make every stale
#: balance look freshly confirmed once an hour, which is precisely the reading
#: T-54 is filed to build a floor on top of.
CONTRIBUTOR_STATUS_COLUMNS = ("last_check_in_at", "worker_version",
                              "quota_remaining", "quota_reported_at",
                              "last_error", "last_error_at")

#: Columns this service WRITES that were not in submission_log's original
#: CREATE TABLE, and which therefore exist only where `manage_users.py
#: init-schema` has run since they were added.
#:
#: WHY A COLUMN CHECK, when the table check above already passes. This service
#: holds no DDL rights: init-schema is a separate, deliberately-invoked admin
#: command, so a deploy that ships app.py ahead of it finds a submission_log
#: that exists, is granted correctly, and is missing the column every INSERT
#: names -- a 500 on a contributor's first claim, which is precisely the shape
#: of failure verify_schema() exists to convert into a refusal to start. It is
#: the same argument REQUIRED_SEQUENCES above is annotated with, one level down.
#: backend/webapp/schema_web.py carries the identical map for the same reason.
#:
#: T-45 WIDENED THIS FROM ONE COLUMN TO SEVEN, and the count is the finding. The
#: row that filed it named the two `ensure_schema()` adds to the watermark table
#: (claimed_by, claim_granted_at). But the contract this map states is the
#: columns this service WRITES, not the ones it creates, and reading every
#: statement that touches a claim gives six across two tables:
#:
#:   * job_ingest_state -- claimed_at as well. It is added by
#:     lib/state.ensure_state_schema(with_claims=True) rather than here, so it
#:     was easy to miss by looking only at this file's DDL; holds_claim() reads
#:     it and all three write sites set it. Whoever creates it is irrelevant to
#:     whether an INSERT naming it can fail.
#:   * search_queries -- all three, created by ../schema.py's
#:     ensure_search_query_schema. try_claim_search_query() writes them and
#:     holds_search_query_claim() reads them, so this service depends on them
#:     exactly as it does on the watermark table's.
#:
#: EVERY ONE OF THE SIX IS ADDED BY dbconn.add_missing_columns TO A TABLE THAT
#: ALREADY EXISTS (lib/state.py:59, ../schema.py:1092-1096, and ensure_schema()
#: below), which is the precise shape this check exists to catch: the table
#: passes to_regclass, passes its privilege check, and is missing the column the
#: statement names. A column in a CREATE TABLE could not go missing on its own;
#: these six can, and one of them going missing is a 500 on a contributor's
#: first claim rather than a refusal to start.
#:
#: NOT LISTED, deliberately: dataset and last_success_at. Both are written by
#: the claim SQL and both are in job_ingest_state's CREATE TABLE, so they exist
#: if the table does and REQUIRED_TABLES already covers that case.
#:
#: T-34 ADDED THE FIRST THREE THIS SERVICE ONLY READS, and that is a widening of
#: the contract the two paragraphs above state, made deliberately. Every entry
#: before them was written by a statement here; contributors' three settings are
#: read by `claim` and written only by manage_users.py on the admin credential.
#: The criterion that decides it is the one the paragraph above states -- can
#: this column go missing on its own? -- and not the direction of the access:
#: all three arrive by add_missing_columns onto a table that already exists, so
#: a deploy that ships app.py ahead of `init-schema` finds a contributors table
#: that passes to_regclass, passes its privilege check, and is missing the
#: column `claim`'s SELECT names. That is a 500 on EVERY claim, from a service
#: that started cleanly -- the identical failure, and a read rather than a write
#: does not soften it. verify_schema()'s docstring said "only columns this
#: service WRITES" and was corrected here rather than left to disagree.
REQUIRED_COLUMNS = {
    "submission_log": ("action",),
    "job_ingest_state": ("claimed_at", "claimed_by", "claim_granted_at"),
    "search_queries": ("claimed_at", "claimed_by", "claim_granted_at"),
    "contributors": CONTRIBUTOR_SETTINGS,
}

#: The closed vocabulary of submission_log.action. Free TEXT with a closed set
#: in code, the same shape webapp/jobs.py uses for job_events.event, because the
#: alternative -- a CHECK constraint -- would need DDL rights this service does
#: not have and a migration to widen.
#:
#: `claim` is the one that matters: claims_today() counts rows with that action
#: and nothing else, so the daily cap means "queries claimed today" rather than
#: "log rows written today". Counting every row would meter a submit and a
#: release against a cap whose name says claims, and would have made the cap
#: tighten as an honest worker did more work (defect D41).
#:
#: THE FOURTH IS NOT A LITERAL HERE, DELIBERATELY. `run` is read by
#: ../searchqueries.py's reconcile_contributor_runs(), which is what turns a row
#: with that action into an advance of the five run statistics this service may
#: not write (docs/adr/0009). Spelling it out on both sides would be two
#: constants that agree until the day they do not, with nothing to report the
#: divergence -- the failure T-31 built clamp_poll_interval to avoid, one table
#: over. backend/api/tests/test_run_statistics_boundary.py asserts this tuple's
#: fourth entry comes from that module and is not a second spelling of the word.
SUBMISSION_ACTIONS = ("claim", "submit", "release",
                      searchqueries.CONTRIBUTOR_RUN_ACTION)

#: The submission_log.dataset form naming one `search_queries` row, re-exported
#: from its owner exactly as normalize_job is above. The dispatch endpoint
#: docs/adr/0007 still owes calls this; nothing in app.py does yet, and the
#: reconciler on the other side is written against this same function rather
#: than against a string it hopes matches.
dataset_for_query = searchqueries.dataset_for_query

#: One level up, because the query bank is shared with the pipeline's
#: ingest/google-serpapi.py. Until slice D this file had its own byte-identical
#: copy -- two files that had to agree and nothing making them.
GOOGLE_QUERIES_FILE = os.environ.get(
    "GOOGLE_QUERIES_FILE",
    os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                 "config", "google-queries.json"),
)

# Mirrors ingest/google-serpapi.py's values -- independent constants, not
# shared state, because a contributor's client and the local pipeline may
# legitimately want different pacing.
CLAIM_TTL_MINUTES = int(os.environ.get("CLAIM_TTL_MINUTES", "15"))
MIN_HOURS_BETWEEN_RUNS = float(os.environ.get("GOOGLE_JOBS_MIN_HOURS_BETWEEN_RUNS", "20"))

# --------------------------------------------------------------------------
# Schema
# --------------------------------------------------------------------------

def ensure_schema(conn):
    """Create what this service needs, delegating everything it does not own.

    Only `manage_users.py init-schema` reaches here, on the admin credential.
    The service itself holds no DDL rights at all and verifies at startup
    instead -- see app.verify_schema().

    WHO OWNS WHAT. The `jobs` table, the watermark table and
    google_jobs_query_stats belong to the pipeline, so ../schema.py declares
    them and this calls it. Until slice D this file re-declared all three from
    its own copy of the DDL, and they had already drifted: this copy was
    missing posted_at_ts and salary_text, so a fresh database created by
    init-schema produced a `jobs` table the pipeline then had to ALTER, and
    every row written through the API sorted last forever under the app view's
    `ORDER BY posted_at_ts DESC NULLS LAST`.

    The three contributor tables below are genuinely this service's own -- the
    pipeline has no concept of them -- as are two of the claim columns.
    """
    conn.execute("SET search_path TO public")

    # The pipeline's DDL, from the pipeline. Idempotent, and a no-op against a
    # database it already created. This also brings the app view and the
    # foreign-key cascade repair, which is fine: init-schema is an admin
    # command run deliberately, not something the request path touches.
    schema.ensure_schema(conn)

    # Beyond what the pipeline knows about: WHO holds a claim, so /submit can
    # reject a contributor submitting against someone else's, and a snapshot of
    # claimed_at at the moment this service granted it. See holds_claim() for
    # the takeover race those two defend against. state.ensure_state_schema()
    # supplies claimed_at itself, via with_claims=True.
    #
    # add_missing_columns rather than ALTER ... ADD COLUMN IF NOT EXISTS: the
    # IF NOT EXISTS form still takes an ACCESS EXCLUSIVE lock when it is a
    # no-op, and a pending exclusive lock queues ahead of readers, so a
    # long-lived transaction elsewhere turns a no-op migration into an outage.
    dbconn.add_missing_columns(conn, schema.WATERMARK_TABLE, [
        ("claimed_by", "TEXT"),
        ("claim_granted_at", "TEXT"),
    ])

    # Tables owned solely by this service.
    conn.execute("""
        CREATE TABLE IF NOT EXISTS contributors (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            created_at TEXT NOT NULL,
            notes TEXT
        )
    """)
    # docs/adr/0007 decision 3's desired state, added after this table's first
    # CREATE and therefore by add_missing_columns, exactly as `action` is below
    # and for the same lock reason. See CONTRIBUTOR_SETTINGS for what each one
    # means and why they live on this table rather than on one of their own.
    #
    # ALL THREE ARE NULLABLE WITH NO DEFAULT, DELIBERATELY. A contributor minted
    # before this column existed and one minted after it with nothing configured
    # are the same contributor, and NULL says "the operator has expressed no
    # policy for this one" in both cases. contributor_settings() resolves NULL
    # to the service-wide default at read time, so a DEFAULT here would be a
    # second place that number lives -- and backfilling it onto every existing
    # row would turn "unset" into "set to today's default", which is a different
    # fact and the one an operator would later be unable to distinguish.
    dbconn.add_missing_columns(conn, "contributors",
                               CONTRIBUTOR_SETTING_COLUMNS)
    # T-35's four facts. A SEPARATE TABLE, and every column in the CREATE rather
    # than added afterwards -- which is what keeps it out of REQUIRED_COLUMNS:
    # the criterion that map states is "can the column go missing on its own",
    # and a column of a table this statement creates cannot. REQUIRED_TABLES
    # covers the table, which is the whole of what can be absent here.
    #
    # THE FOREIGN KEY IS THE DIFFERENCE FROM submission_log, and it is
    # deliberate. That table's contributor_id is plain TEXT precisely so a log
    # row whose contributor row is missing is still representable -- it is
    # evidence, and the rows most worth seeing are the anomalous ones. This is
    # not evidence; it is one row of current state per contributor, written only
    # after authenticate() resolved an api_keys row whose own foreign key
    # already reached `contributors`. A status row for a contributor that does
    # not exist would be a fact about nobody.
    conn.execute("""
        CREATE TABLE IF NOT EXISTS contributor_status (
            contributor_id TEXT PRIMARY KEY REFERENCES contributors(id),
            last_check_in_at TEXT NOT NULL,
            worker_version TEXT,
            quota_remaining INTEGER,
            quota_reported_at TEXT,
            last_error TEXT,
            last_error_at TEXT
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS api_keys (
            key_hash TEXT PRIMARY KEY,
            contributor_id TEXT NOT NULL REFERENCES contributors(id),
            label TEXT,
            created_at TEXT NOT NULL,
            revoked_at TEXT
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_api_keys_contributor ON api_keys(contributor_id)")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS submission_log (
            id BIGSERIAL PRIMARY KEY,
            contributor_id TEXT NOT NULL,
            dataset TEXT NOT NULL,
            submitted_at TEXT NOT NULL,
            fetched_count INTEGER NOT NULL,
            accepted_count INTEGER NOT NULL,
            rejected_count INTEGER NOT NULL,
            reason TEXT,
            action TEXT
        )
    """)
    # `action` was added after this table's first CREATE. add_missing_columns
    # rather than ADD COLUMN IF NOT EXISTS, for the reason given above the
    # job_ingest_state call: the IF NOT EXISTS form still takes an ACCESS
    # EXCLUSIVE lock when it is a no-op. Nullable and with no default because
    # this service has never been deployed, so there is no existing row whose
    # action anyone could infer -- a NULL action is honestly "written before
    # this column existed", and claims_today() counts `action = 'claim'`, which
    # NULL never satisfies.
    dbconn.add_missing_columns(conn, "submission_log", [("action", "TEXT")])
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_submission_log_contrib_time "
        "ON submission_log(contributor_id, submitted_at)"
    )
    conn.commit()


def verify_schema(conn):
    """Is `conn`'s database ready for this service? Raise listing what is not.

    LIVED IN app.py UNTIL T-39, AND THE MOVE IS THE POINT. app.verify_schema()
    is still the startup check and still the only caller that matters at
    runtime -- but it opened its own connection on this service's own
    credential, so the check was reachable only from inside a process that had
    already loaded FastAPI. ../tools/provision-database.py is the second
    caller, and it has neither: it runs on the pipeline's interpreter, as the
    owner role, against a database that may have nothing in it yet. Taking a
    conn rather than making one is what lets both use the same list. Same shape
    as ../webapp/schema_web.verify_schema(), which that tool already calls for
    exactly this reason.

    Everything below is unchanged from app.py's version, including the
    reasoning:

    This process deliberately holds no DDL rights: it connects as a role
    granted SELECT/INSERT/UPDATE on exactly the tables in REQUIRED_TABLES, and
    nothing else. Creating the schema there -- which is what it used to do --
    would mean an internet-facing service permanently holding CREATE on the
    same schema the ingest pipeline owns.

    So a missing table is a deployment error to report, not damage to silently
    repair. Refusing to start is the point: a half-initialised database would
    otherwise surface later as a confusing 500 on a contributor's submit.

    Privileges are checked, not just existence. A table can exist and still be
    unusable if a GRANT was missed, and that failure mode is real -- INSERT
    without SELECT on google_jobs_query_stats looks fine until the first
    ON CONFLICT runs. has_table_privilege() turns that into a startup error
    naming the missing grant. It also answers TRUE by ownership, which is why
    provision-database.py gets existence checking out of this and no more --
    see that file's 'WHAT IT DOES NOT DO: GRANTS'.

    The sequence is checked too. submission_log.id is BIGSERIAL, so an INSERT
    needs USAGE on submission_log_id_seq as well as INSERT on the table. That
    grant was in README's privilege table and in nothing that ran, which made
    it the one documented requirement a startup check could not catch -- it
    would have surfaced as a 500 on a contributor's first submit instead.

    And the columns, for the third instance of the same argument. A table can
    exist, be granted, and still be missing a column every INSERT names --
    init-schema is a separate admin command, so shipping this code ahead of it
    is one `git pull` away.

    THIS PARAGRAPH USED TO END "REQUIRED_COLUMNS lists only columns this service
    WRITES; reads that lose a column fail visibly at the query", and T-34
    falsified the second clause rather than working around it. `contributors`'
    three settings columns are read by `claim` and written only by
    manage_users.py on the admin credential, and losing one of them fails at the
    query on EVERY claim -- visibly, from a service that started cleanly, which
    is the same 500 the write case gives and not a milder one. What the map
    lists is columns that can go missing on their own: added by
    add_missing_columns to a table that already exists, rather than present in a
    CREATE TABLE. See REQUIRED_COLUMNS itself for the full argument.
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
        qualified = f"public.{table}"
        if conn.execute("SELECT to_regclass(%s)", (qualified,)).fetchone()[0] is None:
            continue        # already reported as missing above
        present = {r[0] for r in conn.execute(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_schema = 'public' AND table_name = %s", (table,)
        ).fetchall()}
        absent = [c for c in columns if c not in present]
        if absent:
            problems.append(
                f"{qualified}: missing column(s) {', '.join(absent)}")

    if problems:
        raise RuntimeError(
            "database is not ready for this service -- "
            + "; ".join(problems)
            + ". Run `python3 manage_users.py init-schema` with an admin "
              "credential (JOBS_ADMIN_DATABASE_URL), and check the GRANTs in "
              "README 'Deployment'."
        )


# --------------------------------------------------------------------------
# Minting a credential
# --------------------------------------------------------------------------

#: Server-to-server secret for the mint route in app.py. Unset by default, and
#: an unset value DISABLES the route rather than defaulting to something --
#: `oauth_configured()` in ../webapp/config.py is the same shape, and for the
#: same reason: a credential-issuing endpoint that a missing env var leaves
#: open is the one default nobody would notice until it had been used.
#:
#: WHY THIS EXISTS AT ALL. ../webapp/ authenticates the Builder and this
#: service owns `api_keys`; they hold different Postgres roles and 0006's
#: consequences reject granting `jobs_web` INSERT here. So webapp asks this
#: service to mint, over one authenticated route, in one direction. See
#: docs/adr/0006, and the "Minting" section of README.md.
MINT_SHARED_SECRET = os.environ.get("JOBS_MINT_SHARED_SECRET", "")


def mint_credential(conn, name, label=None, contributor_id=None, notes=None):
    """Create (or re-key) a contributor and return the ONE copy of the raw key.

    THE ONLY MINT IN THIS REPO. `manage_users.py create` and app.py's mint
    route are both callers -- there is deliberately no second place that
    generates a key, because the property that makes a leaked database dump
    worthless is "only sha256 is stored", and that property is only as good as
    its least careful copy.

    RE-KEYING REVOKES, IT DOES NOT ADD. Passing an existing contributor_id
    revokes every live key that contributor holds and issues one new one, so a
    Builder who opts in twice ends with exactly one working credential. The
    revoked rows are KEPT, matching revoke's behaviour and for the reason
    app.py's authenticate() gives: a revoked key must never be silently
    re-minted into validity.

    The caller commits. This function issues no transaction of its own so that
    the webapp-facing route can fail after it and leave nothing behind.
    """
    now = utc_now_str()
    if contributor_id is None:
        contributor_id = f"c_{secrets.token_hex(6)}"
        conn.execute(
            "INSERT INTO contributors (id, name, created_at, notes) VALUES (%s, %s, %s, %s)",
            (contributor_id, name, now, notes),
        )
    else:
        conn.execute(
            "UPDATE api_keys SET revoked_at = %s "
            "WHERE contributor_id = %s AND revoked_at IS NULL",
            (now, contributor_id),
        )

    # token_urlsafe(32) -> ~43 chars, 256 bits of entropy. Long enough that
    # online guessing is hopeless, and the server only ever compares hashes.
    raw_key = secrets.token_urlsafe(32)
    key_hash = hashlib.sha256(raw_key.encode()).hexdigest()
    conn.execute(
        """
        INSERT INTO api_keys (key_hash, contributor_id, label, created_at, revoked_at)
        VALUES (%s, %s, %s, %s, NULL)
        """,
        (key_hash, contributor_id, label, now),
    )
    return contributor_id, raw_key, key_hash, now


# --------------------------------------------------------------------------
# Contributor settings -- docs/adr/0007 decision 3, "the server holds desired
# state"
# --------------------------------------------------------------------------

#: What a contributor with nothing configured gets. `daily_cap` is deliberately
#: absent: its default is app.MAX_CLAIMS_PER_CONTRIBUTOR_PER_DAY, which is
#: env-configurable and belongs to the service rather than to this module, and
#: is passed into claim_allowance() rather than duplicated here.
DEFAULT_RESERVE_FLOOR = 0


class ContributorSettings(NamedTuple):
    """One contributor's desired state, with NULLs already resolved.

    `daily_cap` stays None when unset, because "unset" and "set to the
    service-wide default" are different facts and only the caller knows what
    that default currently is. The other two resolve here: an absent pause is
    not paused and an absent floor reserves nothing, and neither has a second
    candidate value anywhere.
    """
    paused: bool
    daily_cap: int | None
    reserve_floor: int


def contributor_settings(conn, contributor_id):
    """Read one contributor's settings. Missing row -> the defaults.

    A MISSING ROW IS NOT AN ERROR HERE, and that is not defensiveness. The only
    caller reaches this after authenticate() has already resolved a live
    api_keys row to this id, and api_keys.contributor_id is a foreign key onto
    contributors -- so the row exists, and the empty case is unreachable rather
    than tolerated. Returning defaults instead of raising keeps the unreachable
    case behaving like the ordinary one: an operator who has expressed no policy
    gets no policy, which is what an absent row also means.
    """
    row = conn.execute(
        "SELECT paused, daily_cap, reserve_floor FROM contributors WHERE id = %s",
        (contributor_id,),
    ).fetchone()
    if row is None:
        return ContributorSettings(False, None, DEFAULT_RESERVE_FLOOR)
    paused, daily_cap, reserve_floor = row
    return ContributorSettings(
        bool(paused),
        daily_cap,
        DEFAULT_RESERVE_FLOOR if reserve_floor is None else reserve_floor,
    )


def claim_allowance(settings, default_cap):
    """How many queries this contributor may be granted today, in total.

    Pure arithmetic over a settings tuple and a number, so the boundary the row
    that built this is specified on can be tested without a database, a request
    or a query bank -- the same reason ../score.py's score_job() takes no I/O.

    TWO NUMBERS, ONE SUBTRACTION, AND THE SECOND IS NOT REDUNDANT. `cap - floor`
    collapses arithmetically into a single smaller cap, and if the two had one
    owner it should be one column. They do not. The cap is the OPERATOR's: how
    much of a contributor's day this service is willing to schedule. The floor
    is the BUILDER's: how many of their own SerpApi credits they keep back. Held
    as one number, an operator raising a cap from 8 to 12 silently spends a
    reserve they cannot see and did not set, and the Builder's only way to
    restate it is to notice and ask. Two columns means each party edits their
    own number without knowing the other's, which is the property worth a
    column.

    THE FLOOR IS DENOMINATED IN A DAY'S CREDITS, not in a balance. `0007`
    decision 4's pacing divides credits remaining by days left, and a floor
    against a REPORTED remaining balance would be the more natural reading of
    the word -- but the balance is contributor-reported and nothing reports it
    yet: T-35 owns "remaining quota", and building a floor against a number that
    does not arrive would be a setting that silently never binds. See TASKS.md's
    T-54, filed against this line, for the version that reads a balance.

    NEVER BELOW ZERO. A floor larger than the cap is an operator and a Builder
    who disagree, and the resolution is that nothing is scheduled -- not a
    negative allowance, which `used >= allowance` would read as "already over"
    correctly but `min(req.max, allowance - used)` would read as a negative
    max_queries and hand to a query bank that has no opinion about one.
    """
    cap = default_cap if settings.daily_cap is None else settings.daily_cap
    return max(0, cap - settings.reserve_floor)


# --------------------------------------------------------------------------
# Contributor status -- TASKS.md's T-35, "tell a stalled worker from an idle
# one"
# --------------------------------------------------------------------------

#: How much of a reported string is kept. Both are bounds on text a contributor's
#: machine composed, so both are bounds on something this service does not
#: control: a version is a token and 100 characters is room for a long one, and
#: 500 matches what `release` already keeps of a reason, which is the same kind
#: of string from the same worker.
MAX_WORKER_VERSION_CHARS = 100
MAX_REPORTED_ERROR_CHARS = 500


def _reported_text(value, limit):
    """A string a contributor's machine sent, made safe to store and to print.

    TWO THINGS HAPPEN HERE AND NEITHER IS A REFUSAL. The check-in must never be
    able to fail the poll it rides on -- a worker whose error message was too
    long, or whose traceback carried a newline, would otherwise be refused the
    queries it called for, and status reporting would have broken the work it
    exists to report on. So an unusable string is trimmed rather than rejected.

    NON-PRINTABLE CHARACTERS BECOME SPACES, which is not tidiness. The one
    consumer of these strings is contribution_report.py, printing a fixed-width
    table on an operator's terminal, and an ANSI escape sequence in a
    contributor-supplied field is a field that can move the cursor, repaint the
    row above it, or hide itself. It is the same argument app._validation_detail
    makes one file over about the response body: make the output independent of
    the input by construction rather than by trusting the reader.

    A string that is empty once cleaned reports nothing, and None is what
    "nothing reported" means everywhere below -- so a worker sending `""` and a
    worker sending no field at all are one case, not two.
    """
    if value is None:
        return None
    cleaned = "".join(ch if ch.isprintable() else " " for ch in str(value))
    return cleaned.strip()[:limit].strip() or None


def record_check_in(conn, contributor_id, worker_version=None,
                    quota_remaining=None, last_error=None):
    """Move this contributor's check-in forward, and store what it reported.

    WHY THIS IS NOT A submission_log ROW, which is the cheaper-looking answer
    and the one T-55 reaches for on the settings side. That table is an
    append-only record of WORK, and claims_today() meters a daily cap off it. A
    heartbeat is neither: thirty machines polling hourly write seven hundred
    rows a day that record nothing anybody wants a history of, every one of them
    landing in the report's `other` bucket unless the vocabulary grows a fifth
    entry -- and the totals line under a report about contribution would then be
    dominated by machines saying nothing happened. Last-check-in is CURRENT
    STATE: only the latest value is ever read, so it is one row per contributor,
    updated in place.

    IT COMMITS, AND THE COMMIT IS THE POINT. `claim` refuses a contributor over
    their daily cap by raising, and `db()`'s `with conn:` rolls back on the way
    out -- so a check-in left to the caller's transaction would be erased for
    exactly the contributors an operator most needs to see polling. The fact
    that a machine called home is true whatever this service decides to do next,
    including refusing it, so it is committed before anything that can raise.

    UNREPORTED IS UNTOUCHED, WHICH IS WHAT THE COALESCEs ARE FOR. A worker sends
    a quota or an error only when it has one; a poll that carries neither must
    leave the last known values AND their timestamps exactly as they were,
    because overwriting them with NULL would erase the error an operator is
    reading and re-stamping them with `now` would make a week-old balance look
    freshly confirmed. That distinction is why each fact has a timestamp of its
    own rather than sharing the check-in's.

    ONE CLOCK. Every timestamp this writes is the same `now`, so a row can never
    say it was checked in before the value it was checked in with was reported.
    """
    now = utc_now_str()
    version = _reported_text(worker_version, MAX_WORKER_VERSION_CHARS)
    error = _reported_text(last_error, MAX_REPORTED_ERROR_CHARS)
    #: Stored as reported, INCLUDING a number that makes no sense. The row that
    #: asked for this says the quota is contributor-reported and never
    #: authoritative, and a negative balance on an operator's screen is a
    #: finding about that worker -- dropping it silently would hide the one
    #: thing it was evidence of.
    quota = None if quota_remaining is None else int(quota_remaining)
    conn.execute(
        """
        INSERT INTO contributor_status (contributor_id, last_check_in_at,
            worker_version, quota_remaining, quota_reported_at, last_error,
            last_error_at)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (contributor_id) DO UPDATE SET
            last_check_in_at  = EXCLUDED.last_check_in_at,
            worker_version    = COALESCE(EXCLUDED.worker_version,
                                         contributor_status.worker_version),
            quota_remaining   = COALESCE(EXCLUDED.quota_remaining,
                                         contributor_status.quota_remaining),
            quota_reported_at = COALESCE(EXCLUDED.quota_reported_at,
                                         contributor_status.quota_reported_at),
            last_error        = COALESCE(EXCLUDED.last_error,
                                         contributor_status.last_error),
            last_error_at     = COALESCE(EXCLUDED.last_error_at,
                                         contributor_status.last_error_at)
        """,
        (contributor_id, now, version, quota,
         None if quota is None else now, error, None if error is None else now),
    )
    conn.commit()


# --------------------------------------------------------------------------
# Claiming
# --------------------------------------------------------------------------

def try_claim_query(conn, dataset, now_dt, claimed_by):
    """Atomic claim -- succeeds only if nobody holds an unexpired claim.

    Byte-for-byte the same conditional-update shape the pipeline
    uses (see module docstring), with claimed_by added. The empty-string
    last_success_at on first INSERT matches that pipeline's "never run"
    sentinel -- it must stay '' and not NULL, both because the column is
    NOT NULL and because stalest-first ordering relies on '' sorting first.
    """
    now_str = now_dt.strftime("%Y-%m-%dT%H:%M:%S")
    ttl_cutoff_str = (now_dt - timedelta(minutes=CLAIM_TTL_MINUTES)).strftime("%Y-%m-%dT%H:%M:%S")
    cur = conn.execute(
        """
        INSERT INTO job_ingest_state (dataset, last_success_at, claimed_at, claimed_by, claim_granted_at)
        VALUES (%(dataset)s, '', %(now)s, %(by)s, %(now)s)
        ON CONFLICT (dataset) DO UPDATE
            SET claimed_at = %(now)s, claimed_by = %(by)s, claim_granted_at = %(now)s
            WHERE job_ingest_state.claimed_at IS NULL OR job_ingest_state.claimed_at < %(ttl_cutoff)s
        RETURNING dataset
        """,
        {"dataset": dataset, "now": now_str, "ttl_cutoff": ttl_cutoff_str, "by": claimed_by},
    )
    won = cur.fetchone() is not None
    conn.commit()
    return won


def holds_claim(conn, dataset, contributor_id, now_dt):
    """True only if this contributor holds a live, unexpired claim that nobody
    has taken over since it was granted.

    THE TAKEOVER PROBLEM (found by testing against the pipeline's real SQL, not
    theorized): that pipeline's claim statement sets claimed_at but has no
    knowledge of claimed_by, so it never clears it. Sequence that breaks a
    naive `claimed_by == caller` check:

        1. This API grants query X to contributor C   (claimed_by='C')
        2. C stalls; the claim expires after CLAIM_TTL_MINUTES
        3. Eric's local pipeline legitimately claims X -- it updates
           claimed_at to now, leaving claimed_by='C' STALE
        4. C finally submits. A naive check sees claimed_by=='C' and a fresh
           claimed_at, and lets C write results and call mark_success() --
           clobbering the watermark while the local pipeline is mid-fetch.

    THE FIX: claim_granted_at records what claimed_at was when THIS service
    granted the claim. Any takeover by anyone necessarily rewrites claimed_at
    (both systems set it to their own `now`), so the two stop matching. They
    can only still be equal if nothing has re-claimed since -- and a genuine
    takeover requires the claim to have expired first, meaning at least
    CLAIM_TTL_MINUTES separates the two timestamps. There is no same-instant
    edge case to worry about.

    This is why no changes to the pipeline are needed: the guard lives entirely
    on this side, and treats any unexpected mutation of claimed_at as a lost
    claim.
    """
    ttl_cutoff_str = (now_dt - timedelta(minutes=CLAIM_TTL_MINUTES)).strftime("%Y-%m-%dT%H:%M:%S")
    row = conn.execute(
        "SELECT claimed_by, claimed_at, claim_granted_at FROM job_ingest_state WHERE dataset = %s",
        (dataset,),
    ).fetchone()
    if row is None:
        return False
    claimed_by, claimed_at, claim_granted_at = row
    if claimed_by != contributor_id or not claimed_at:
        return False
    if claim_granted_at != claimed_at:
        return False  # somebody re-claimed this after it was granted
    return claimed_at >= ttl_cutoff_str


def mark_success(conn, dataset, ts):
    """Advances last_success_at and releases the claim in one write.

    CRITICAL: this is the ONLY thing that may advance last_success_at, and it
    must run only after results are actually stored. That invariant is what
    makes the whole pipeline resume correctly after failures -- a failed run
    leaves the watermark untouched, so the next run's date-chip widens to
    cover the true gap instead of silently skipping it."""
    conn.execute(
        """
        INSERT INTO job_ingest_state (dataset, last_success_at, claimed_at, claimed_by, claim_granted_at)
        VALUES (%s, %s, NULL, NULL, NULL)
        ON CONFLICT (dataset) DO UPDATE
            SET last_success_at = EXCLUDED.last_success_at, claimed_at = NULL,
                claimed_by = NULL, claim_granted_at = NULL
        """,
        (dataset, ts),
    )
    conn.commit()


def release_claim(conn, dataset):
    """Called when a contributor's fetch FAILS -- frees the query immediately
    so another contributor (with a different SerpApi account, which may not
    share the same transient error/quota exhaustion) can retry right away
    instead of waiting out CLAIM_TTL_MINUTES."""
    conn.execute(
        "UPDATE job_ingest_state SET claimed_at = NULL, claimed_by = NULL, claim_granted_at = NULL WHERE dataset = %s",
        (dataset,),
    )
    conn.commit()


# --------------------------------------------------------------------------
# Claiming, second mode: one `search_queries` row
# --------------------------------------------------------------------------
#
# WHY THERE ARE TWO MODES AND NOT ONE. The three functions above lease a
# DATASET STRING in job_ingest_state -- "google_jobs:query:<slug>", one row per
# entry in config/google-queries.json, a bank the pipeline and this service both
# read from a file. docs/adr/0007 dispatches something else: a `search_queries`
# row, which is a Builder's own saved keyword, registered at runtime by the
# webapp and carrying its own run statistics. There is no slug and no file, so
# there is nothing to name a dataset string after.
#
# The two protections are not re-derived, they are mirrored. The conditional
# UPDATE below has the same `claimed_at IS NULL OR claimed_at < ttl_cutoff`
# shape try_claim_query uses, and holds_search_query_claim checks the same three
# conditions holds_claim does, for the same reason and against the same failure
# -- see that docstring, which is where the whole sequence is written out.
#
# THE ONE STRUCTURAL DIFFERENCE, and it is deliberate: this is a plain UPDATE,
# not an upsert. try_claim_query INSERTs because a dataset that has never run
# has no job_ingest_state row and the claim is what creates it. A search_queries
# row is never created by claiming it -- id is BIGSERIAL and the row exists
# because a Builder saved the keyword or the seeder wrote it, so a claim against
# an id that is not there must fail rather than conjure a query nobody asked
# for. `RETURNING id` reports both outcomes the same way: no row back means the
# claim was not granted, whether because someone else holds it or because there
# was nothing to claim.

def try_claim_search_query(conn, query_id, now_dt, claimed_by):
    """Atomic claim on one search_queries row. False if it is already held.

    Same conditional-update shape as try_claim_query -- the WHERE is evaluated
    by the server against the stored row, which is what makes "two claimants
    never get the same query" true across two processes rather than true by
    convention.

    The parentheses around the OR are load-bearing: without them the `id = ...`
    binds to the first arm only and an expired-claim row of ANY id satisfies the
    statement, which is a claim on somebody else's query reported as a win.
    """
    now_str = now_dt.strftime("%Y-%m-%dT%H:%M:%S")
    ttl_cutoff_str = (now_dt - timedelta(minutes=CLAIM_TTL_MINUTES)).strftime("%Y-%m-%dT%H:%M:%S")
    cur = conn.execute(
        """
        UPDATE search_queries
           SET claimed_at = %(now)s, claimed_by = %(by)s, claim_granted_at = %(now)s
         WHERE id = %(id)s
           AND (claimed_at IS NULL OR claimed_at < %(ttl_cutoff)s)
        RETURNING id
        """,
        {"id": query_id, "now": now_str, "ttl_cutoff": ttl_cutoff_str, "by": claimed_by},
    )
    won = cur.fetchone() is not None
    conn.commit()
    return won


def holds_search_query_claim(conn, query_id, contributor_id, now_dt):
    """True only if this contributor still holds a live claim on this query.

    THE GUARD IS holds_claim's, UNCHANGED -- read that docstring for the
    takeover sequence it defends against; it is not restated here because one
    copy that drifts is worse than a pointer.

    WHAT IS DIFFERENT ON THIS TABLE, and it is worth knowing before deciding
    the third condition is dead weight: `search_queries` has no claimed_at
    writer in this tree today. The pipeline runs these rows through
    ../searchqueries.py's due_queries() and record_run(), neither of which
    leases anything, so the takeover route that made claim_granted_at
    necessary on job_ingest_state -- lib.state.try_claim rewriting claimed_at
    while knowing nothing of claimed_by -- has no caller here YET.

    That is an argument for building the guard now, not for leaving it out.
    0007 puts the local pipeline and N contributors on the same rows, so the
    first writer that leases one without knowing about claimed_by makes this
    live, and a guard added after the writer is a guard added after the
    corruption. tests/test_search_query_claims.py exercises the sequence
    against a writer of exactly that shape and says so.
    """
    ttl_cutoff_str = (now_dt - timedelta(minutes=CLAIM_TTL_MINUTES)).strftime("%Y-%m-%dT%H:%M:%S")
    row = conn.execute(
        "SELECT claimed_by, claimed_at, claim_granted_at "
        "FROM search_queries WHERE id = %s",
        (query_id,),
    ).fetchone()
    if row is None:
        return False
    claimed_by, claimed_at, claim_granted_at = row
    if claimed_by != contributor_id or not claimed_at:
        return False
    if claim_granted_at != claimed_at:
        return False  # somebody re-claimed this after it was granted
    return claimed_at >= ttl_cutoff_str


def release_search_query_claim(conn, query_id):
    """Free the query. The only way a claim on this table is given back early.

    Called on a failed fetch, for release_claim's reason -- another contributor
    with a different SerpApi account may not share the transient error -- and
    also after a successful submit, which is where this mode differs from the
    first one and the difference is not an oversight.

    THERE IS NO mark_success TWIN HERE, AND THERE IS NOT GOING TO BE. On
    job_ingest_state the watermark and the claim are columns of one row, so one
    statement advances the first and clears the second. This table's watermark
    half is last_run_at, run_count, provider_last_used, result_count_last_run
    and last_result_at -- and ../searchqueries.py's record_run() says in its own
    docstring that it is THE ONLY WRITER of those. It is also the only one that
    can be: this service's role holds no UPDATE on them (../schema.py:993),
    which is the grant that stops a submitted result from forging a run history.

    WHAT ADVANCES THEM, since docs/adr/0009 settled it: the pipeline does,
    asynchronously, from a submission_log row this service writes with
    action=`run` on the same branch mark_success sits on in the other mode.
    ../searchqueries.py's reconcile_contributor_runs() reads those rows on the
    next nightly cycle and calls record_run() for each. So the fact crosses the
    boundary as data rather than as a privilege, no grant moves in either
    direction, and record_run stays the one writer.

    THE COST IS A LAG, AND IT IS REAL: between the submit and the next cycle the
    row is released with last_run_at untouched, so a second contributor can
    claim it and spend a credit on a search that already happened. That was
    weighed against handing this service UPDATE on the five columns and taken
    deliberately -- one duplicated search inside one cycle, against a grant that
    would let any bug on this side silence a query for every Builder by writing
    a future last_run_at. 0009 records the argument and the two rejected shapes.

    Releasing is still enough to consume a claim: it clears all three columns,
    so a second submit against the same claim finds nothing held, which is the
    double-advance mark_success prevents on the other table.
    """
    conn.execute(
        "UPDATE search_queries SET claimed_at = NULL, claimed_by = NULL, "
        "claim_granted_at = NULL WHERE id = %s",
        (query_id,),
    )
    conn.commit()


def log_submission(conn, action, contributor_id, dataset, fetched_count=0,
                   accepted_count=0, rejected_count=0, reason=None):
    """The one writer of submission_log, for all four call sites in app.py.

    ONE FUNCTION BECAUSE THE COLUMN LIST IS LOAD-BEARING. This table is the
    audit trail AND the quota counter -- claims_today() reads it -- so a call
    site that forgot `action` would not fail, it would write a row the daily cap
    silently ignores. That is the same class of defect D41 was: a cap that reads
    a table nothing writes. Four hand-written INSERTs that must agree on a
    column list is a rule a person has to remember; one function is a rule the
    interpreter enforces.

    Does NOT commit. Callers are inside `db()`'s `with conn:` and several of
    them raise an HTTPException immediately afterwards; committing here would
    decide for them whether the surrounding work is kept.
    """
    if action not in SUBMISSION_ACTIONS:
        raise ValueError(f"unknown submission action {action!r}")
    conn.execute(
        """
        INSERT INTO submission_log (contributor_id, dataset, submitted_at,
            fetched_count, accepted_count, rejected_count, reason, action)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        """,
        (contributor_id, dataset, utc_now_str(), fetched_count, accepted_count,
         rejected_count, reason, action),
    )


def log_query_stats(conn, slug, new_count, total_fetched, days_since_last_run):
    conn.execute(
        """
        INSERT INTO google_jobs_query_stats (slug, run_at, new_count, total_fetched, days_since_last_run)
        VALUES (%s, %s, %s, %s, %s)
        ON CONFLICT (slug, run_at) DO NOTHING
        """,
        (slug, utc_now_str(), new_count, total_fetched, days_since_last_run),
    )
    conn.commit()


def load_query_buckets():
    with open(GOOGLE_QUERIES_FILE) as f:
        return json.load(f)["buckets"]


def pick_stale_queries_by_bucket(conn, buckets, claimed_by, max_queries=None):
    """Per-bucket least-recently-run selection with atomic claiming.

    Same algorithm as the pipeline: within each bucket, walk
    candidates stalest-first and attempt a claim on each until the bucket's
    daily_budget is met. A candidate already claimed by someone else is
    skipped in favor of the next-stalest -- that's what load-balances across
    contributors with no static per-contributor assignment.

    The MIN_HOURS_BETWEEN_RUNS guard breaks out of a bucket entirely on the
    first too-recent candidate: because ordering is stalest-first, everything
    after it is even fresher, so the bucket's work for this interval is
    already done and spending more of the budget would just re-fetch a window
    someone else already covered.

    max_queries caps the total returned to one caller (the per-request 'max'),
    independently of the per-bucket budgets.
    """
    picked = []
    now_dt = datetime.now(timezone.utc)
    too_recent_cutoff = (now_dt - timedelta(hours=MIN_HOURS_BETWEEN_RUNS)).strftime("%Y-%m-%dT%H:%M:%S")

    for bucket in buckets.values():
        if max_queries is not None and len(picked) >= max_queries:
            break
        queries = bucket["queries"]
        budget = bucket["daily_budget"]
        slugs = [q["slug"] for q in queries]
        rows = conn.execute(
            "SELECT dataset, last_success_at FROM job_ingest_state WHERE dataset = ANY(%s)",
            ([f"google_jobs:query:{s}" for s in slugs],),
        ).fetchall()
        watermarks = {d.replace("google_jobs:query:", ""): ts for d, ts in rows}
        ordered = sorted(queries, key=lambda q: watermarks.get(q["slug"], ""))

        claimed_in_bucket = 0
        for q in ordered:
            if claimed_in_bucket >= budget:
                break
            if max_queries is not None and len(picked) >= max_queries:
                break
            if watermarks.get(q["slug"], "") > too_recent_cutoff:
                break  # stalest-first: everything remaining ran even more recently
            dataset = f"google_jobs:query:{q['slug']}"
            if try_claim_query(conn, dataset, now_dt, claimed_by):
                picked.append((q, watermarks.get(q["slug"])))
                claimed_in_bucket += 1
    return picked


def choose_date_chip(last_run_str):
    """None (never run) -> no chip at all, the deliberate backfill case.
    Otherwise narrow to the bucket covering the actual gap since that query's
    last SUCCESS -- not always 'today', which is what makes failure recovery
    self-healing."""
    if not last_run_str:
        return None
    try:
        last_run = datetime.strptime(last_run_str, "%Y-%m-%dT%H:%M:%S").replace(tzinfo=timezone.utc)
    except ValueError:
        return None
    elapsed = datetime.now(timezone.utc) - last_run
    if elapsed <= timedelta(days=1):
        return "today"
    if elapsed <= timedelta(days=3):
        return "3days"
    if elapsed <= timedelta(days=7):
        return "week"
    return "month"


# --------------------------------------------------------------------------
# Normalization -- ALWAYS run server-side, never trusted from the client
# --------------------------------------------------------------------------
#
# normalize_job is imported from ../google_jobs.py, which the pipeline's two
# Google ingest scripts also import. This used to be ~130 lines of copies here:
# strip_html, slugify, guess_seniority, parse_relative_posted_at,
# decode_google_job_id, normalize_apply_url, google_source_id, content_hash,
# make_id and normalize_job itself.
#
# The comment those copies carried was right about the stakes and wrong about
# the remedy. It said source_id feeds make_id(), which IS the dedup key, so
# deriving it differently from lib.ids.google_source_id() silently turns
# one posting into two rows -- and concluded "any change here is a change
# there, in the same commit". That is a rule a person has to remember. One
# import is a rule the interpreter enforces.

def upsert(conn, records):
    """Write postings exactly the way the pipeline's ingest scripts do.

    This is now literally the same code path -- lib.upsert with the same
    TableSpec (schema.HASH_FIELDS_SHORT) and the same id function -- rather
    than a reimplementation of it. Rows written through this API are therefore
    indistinguishable from locally-ingested ones by construction, not by two
    files agreeing.

    What that buys beyond tidiness: lib.upsert opens a SAVEPOINT per
    record. The hand-rolled version this replaces did not, and on Postgres a
    single failed statement aborts the whole transaction -- so one malformed
    posting in a contributor's batch of 50 took the other 49 with it, returned
    a 500, wrote no submission_log row, never called mark_success, and spent
    the contributor's SerpApi credit for nothing.

    Returns the full UpsertResult. It still unpacks to (new, updated,
    unchanged), but callers must read `.errors` -- that is the whole point of
    upsert_checked, and this call site used to pass `debug=` too, so a
    per-record failure here had no stderr fallback either.

    WHY THIS DOES NOT PROPAGATE UpsertErrorRate. lib.upsert commits before
    the rate is checked, so by the time it raises, the records that succeeded
    are already in the table. Letting it out of here would 500 the request
    AFTER the write, skipping mark_success and the submission_log row -- the
    contributor would have spent their SerpApi credit, had their rows stored,
    and be told the submission failed with nothing recorded. So the batch is
    reported rather than rejected: the count reaches the response body, the
    submission_log reason, and the server log, which is three channels more
    than the zero it had before.
    """
    try:
        result = _lib_upsert_checked(conn, _JOB_SPEC, records,
                                     schema.make_job_id, debug=True)
    except UpsertErrorRate as e:
        result = e.result
    conn.commit()
    return result

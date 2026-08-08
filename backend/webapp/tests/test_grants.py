"""Every table this service's SQL names must be in REQUIRED_TABLES.

WHY THIS TEST EXISTS. REQUIRED_TABLES drives three things: the startup
privilege check, the GRANT statements in README.md, and the operator's mental
model. A route that starts querying a new table without being added there
produces a service that starts cleanly and 500s on that one request -- in
production, on someone else's first click, with a permission error nobody was
looking for.

api/ closed the identical gap by adding REQUIRED_SEQUENCES: a grant that was
documented in its README and verified by nothing, which made it the one
requirement whose absence surfaced as a 500 on a contributor's first submit
rather than as a refusal to start. This test is that lesson made automatic.
"""

import ast
import os
import re
import sys
import unittest

WEBAPP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, WEBAPP_DIR)

import schema_web  # noqa: E402

#: Modules whose SQL runs as the restricted service role. manage_app_users.py
#: is excluded on purpose: init-schema runs as the admin role, and its CREATE
#: statements would otherwise read as tables the service needs granted.
#:
#: schema_web.py IS SCANNED, and that is D69 residue part 3. It holds admin-only
#: DDL, which is why it was left out originally -- but the exclusion also hid a
#: real service-role query: `WHERE NOT EXISTS (SELECT 1 FROM profiles p ...)`,
#: which runs as the service role at startup. The DDL turns out not to be the
#: hazard it was assumed to be: `_FROM_JOIN` keys on FROM/JOIN/INTO/UPDATE, and
#: `CREATE TABLE IF NOT EXISTS <name>` matches none of them, so a CREATE
#: contributes no table name at all. Measured rather than argued -- scanning
#: this file adds exactly `profiles` (already declared), `information_schema`
#: and `pg_constraint` (catalog, excluded below) and `cascade` (SQL grammar,
#: in _KEYWORDS below). No CREATE'd table name among them.
#:
#: contribute.py IS SCANNED, and the reason is the whole point of this file: it
#: is the newest route module and it SELECTs and UPDATEs app_users. A module
#: missing from this tuple is a module whose SQL nothing checks, which is the
#: identical hole one level up from the one the scan closes -- so the tuple
#: itself is asserted against the directory listing in
#: TestEveryRouteModuleIsScanned below rather than left to be remembered.
SERVICE_MODULES = ("auth.py", "contribute.py", "jobs.py", "db.py", "app.py",
                   "label.py", "onboarding.py", "search.py", "schema_web.py")

#: Aliases bound inside the SQL itself -- subquery, lateral and correlation
#: names. They follow FROM/JOIN syntactically but are not tables to grant.
_ALIASES = {"m", "s", "e", "v", "u", "ev", "bs", "prior", "public", "lateral"}

#: Keywords that follow one of the words below syntactically and are not names
#: of anything. `set` is here because an upsert reads `ON CONFLICT ... DO UPDATE
#: SET`, and the pattern below cannot tell that UPDATE from the statement kind.
#: `cascade` is EXACTLY the same case one clause over -- a foreign key reads
#: `ON DELETE CASCADE ON UPDATE CASCADE`, so `_FROM_JOIN` reads the second
#: CASCADE as a table name following UPDATE. Both are SQL grammar that happens
#: to follow UPDATE, not English words admitted to quiet a finding; that
#: distinction is the one that keeps this set honest, and a future addition
#: that is not SQL grammar is the signal to narrow the pattern instead.
#: Kept separate from _ALIASES on purpose: an alias is something the SQL bound
#: and a keyword is something it did not, and collapsing the two would let a
#: real missing GRANT hide behind a plausible-looking word.
_KEYWORDS = {"set", "cascade"}

#: The system catalogs. Readable by every role by default, granted to nobody
#: explicitly, and therefore never entries in REQUIRED_TABLES. Unlike the
#: English words that ruled out the naive `_FROM_JOIN` widening, this namespace
#: is CLOSED and well-defined -- `pg_*` plus `information_schema` is the whole
#: of it -- which is what makes excluding it a rule rather than a quieting.
#: Reached by schema_web.py's introspection: `FROM pg_constraint WHERE conname
#: = ...` and `FROM information_schema.columns WHERE table_schema = ...`.
def _is_catalog(name):
    return name == "information_schema" or name.startswith("pg_")

_STATEMENT = re.compile(r"\b(SELECT|INSERT|UPDATE|DELETE)\b", re.I)
_FROM_JOIN = re.compile(r"\b(?:FROM|JOIN|INTO|UPDATE)\s+([a-z_][a-z0-9_]*)", re.I)

#: A join CLAUSE with no statement keyword in it -- `LEFT JOIN <table> <alias>
#: ON ...`. The second way a string can be SQL, and the one that used to be
#: invisible: see sql_strings_in()'s docstring for the defect and for why this
#: is narrower than it could be.
_JOIN_CLAUSE = re.compile(r"\bJOIN\s+[a-z_][a-z0-9_]*\b.*?\bON\b", re.I | re.S)


def sql_strings_in(path):
    """Every string literal in the module that is actually SQL.

    Parsed out of the AST rather than grepped out of the source, and with
    docstrings excluded, because neither filter alone is enough here: a grep
    cannot tell a table name from prose, and the prose in this package is full
    of sentences like "reachable from JavaScript" and "revocation is one
    UPDATE" that satisfy both patterns above. Docstrings are the only place
    that happens.

    A STRING IS SQL IF IT IS A STATEMENT **OR** A JOIN CLAUSE, and the second
    half is D69. `_STATEMENT` alone silently dropped every string with no
    statement keyword in it -- which is exactly what a hoisted join fragment
    is. jobs.py's `_COHORT_SIGNAL_JOIN` is `LEFT JOIN cohort_signal cs ON ...`
    and nothing else, so `cohort_signal` was never offered to `_FROM_JOIN`, was
    never reported undeclared, and this suite stayed green over a missing GRANT
    -- the precise failure this module's own docstring says it exists to turn
    into a refusal to start. `_BUILDER_STATE_JOIN` is invisible the same way
    and was declared only by luck, because write_builder_state's real INSERT
    names that table elsewhere in the file. The check worked whenever a table
    was WRITTEN and skipped tables that are only ever JOINED, which is to say
    it was blind to read-only tables specifically.

    WHY `_JOIN_CLAUSE` AND NOT SIMPLY `_FROM_JOIN`, which is the obvious
    widening and is wrong. Ordinary English contains "from <word>" constantly.
    Measured on this package rather than guessed: keeping every string that
    `_FROM_JOIN` matches admits label.py's user-facing HTML and onboarding.py's
    error messages, and yields the "tables" `memory`, `the`, `this`, `what`,
    `you` and `a` -- from "Answer it again from the posting, not from memory"
    and "a Builder inherits from a cohort profile". None of those is an alias
    or a keyword, so the only way to quiet them is to list English words in
    _ALIASES, which is how a real missing GRANT eventually hides behind a
    plausible-looking word. Requiring the JOIN ... ON shape instead admits
    exactly two more strings across the whole package -- jobs.py's two join
    fragments -- and adds exactly one name, `cohort_signal`, which is a real
    missing grant. No new alias or keyword was needed for this change, and
    needing one would have been the signal to narrow the pattern further.

    THIS CLOSES THE JOIN-FRAGMENT CASE, NOT THE GENERAL ONE. A SQL fragment
    hoisted into a constant with neither a statement keyword nor a JOIN ... ON
    -- a bare `FROM <table>` tail, a WHERE clause naming a table, a CTE body --
    is still dropped. That residue is deliberate: every narrowing here is a
    trade against the prose above, and the general form of "is this string SQL"
    is not a regex. Anything hoisted that way needs a test naming it directly.

    AND A TABLE REACHED THROUGH A VIEW IS INVISIBLE TO ANY VERSION OF THIS,
    which is a different limit and a permanent one. Measured, not assumed:
    `job_facts` appears in NO SQL string anywhere in this package -- only in
    prose and in the declaration itself -- and is nonetheless correctly granted,
    because `jobs_app` expands to jobs + job_facts + job_matches + job_scores
    and a plain view runs with the CALLER's privileges. That is the same reason
    REQUIRED_TABLES lists `jobs`, stated at the top of ../schema_web.py. No
    scanner over this package's own strings can derive those entries; they come
    from the view's definition, which lives in another process's file.

    `profiles` USED TO BE A THIRD SHAPE -- named in real SQL, but in
    ../schema_web.py, which was not in SERVICE_MODULES. That is D69 residue part
    3 and it is CLOSED: that file is scanned as of 2026-08-02, the query is seen,
    and TestSchemaWebIsScanned pins all six names it yields one assertion each.
    Re-measured at that commit rather than inherited from the note that proposed
    it, because widening a scanner can only ADD findings and the deliverable is
    the list of what it adds. Zero undeclared.

    So a declared table can be justified two ways this test cannot check -- the
    view expansion above, and a fragment that is neither a statement nor a
    JOIN ... ON. TestTheScannerSeesJoinOnlyFragments and TestSchemaWebIsScanned
    pin what it CAN check; the rest is why REQUIRED_TABLES stays hand-written
    rather than derived.

    An f-string is REASSEMBLED from its literal segments before being tested,
    not tested segment by segment. jobs.py interpolates its column list, so
    `SELECT {columns}` and `FROM jobs_app` land in different segments -- and
    checking each on its own silently drops the half with the table name in it,
    which is exactly the table this test exists to notice.
    """
    with open(path) as f:
        tree = ast.parse(f.read(), filename=path)

    # Docstrings, and the literal segments of f-strings (handled whole below).
    consumed = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef,
                             ast.ClassDef)):
            first = node.body[0] if node.body else None
            if (isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant)
                    and isinstance(first.value.value, str)):
                consumed.add(id(first.value))
        elif isinstance(node, ast.JoinedStr):
            consumed.update(id(part) for part in node.values)

    texts = []
    for node in ast.walk(tree):
        if isinstance(node, ast.JoinedStr):
            # Join on a space so "FROM {table}" cannot read as FROM followed by
            # whatever literal happens to come after the placeholder.
            texts.append(" ".join(
                part.value for part in node.values
                if isinstance(part, ast.Constant) and isinstance(part.value, str)))
        elif (isinstance(node, ast.Constant) and isinstance(node.value, str)
                and id(node) not in consumed):
            texts.append(node.value)

    return [t for t in texts
            if _STATEMENT.search(t) or _JOIN_CLAUSE.search(t)]


def tables_named_in(path):
    found = set()
    for sql in sql_strings_in(path):
        for match in _FROM_JOIN.finditer(sql):
            name = match.group(1).lower()
            if name not in _ALIASES and name not in _KEYWORDS and not _is_catalog(name):
                found.add(name)
    return found


class TestTheScannerSeesJoinOnlyFragments(unittest.TestCase):
    """D69. The scanner kept only strings containing a statement keyword, so a
    hoisted `LEFT JOIN <table> <alias> ON ...` constant was dropped before
    _FROM_JOIN ever ran -- and a table this service only ever JOINs, never
    writes, could go undeclared with the suite green. These tests are what
    stops a narrowing back to _STATEMENT alone from silently reopening it."""

    def test_a_join_fragment_with_no_statement_keyword_is_sql(self):
        fragment = ("LEFT JOIN cohort_signal cs\n"
                    "       ON cs.job_id = v.id AND cs.cohort_profile = v.profile")
        self.assertIsNone(_STATEMENT.search(fragment),
                          "the premise: this string has no statement keyword")
        self.assertIsNotNone(_JOIN_CLAUSE.search(fragment))

    def test_the_real_fragments_in_jobs_py_are_picked_up(self):
        named = tables_named_in(os.path.join(WEBAPP_DIR, "jobs.py"))
        # Both of jobs.py's hoisted joins. builder_job_state was declared only
        # by luck -- write_builder_state's INSERT names it elsewhere -- and
        # cohort_signal had no such luck, which is how the defect surfaced.
        self.assertIn("cohort_signal", named)
        self.assertIn("builder_job_state", named)

    def test_prose_that_merely_says_from_is_not_sql(self):
        # WHY THE PATTERN IS `JOIN ... ON` AND NOT SIMPLY `FROM|JOIN <name>`.
        # These six are real strings from label.py's HTML and onboarding.py's
        # error messages, and the loose widening reports them as the tables
        # `the`, `memory`, `what`, `you`, `this` and `a`. Quieting those means
        # listing English words as aliases, which is how a real missing GRANT
        # ends up hiding behind a plausible-looking word.
        for prose in (
            "Answer it again from the posting, not from memory",
            "Answer from what the posting says, not from what you think",
            "I can't tell from this posting",
            "a Builder inherits from a cohort profile and this one does not exist",
            "reachable from JavaScript",
            "Nothing else is needed from you",
        ):
            self.assertIsNone(_JOIN_CLAUSE.search(prose), prose)
            self.assertIsNone(_STATEMENT.search(prose), prose)

    def test_the_widening_needed_no_new_alias_or_keyword(self):
        # The check on the check. Widening a scanner can only ADD findings, so
        # the honest deliverable is the list of what it adds -- and every
        # addition must be a real missing grant, a real alias, or a real
        # keyword. The _JOIN_CLAUSE widening added exactly `cohort_signal`, a
        # real missing grant, and needed neither set touched.
        #
        # _KEYWORDS GREW BY ONE WITH THE schema_web.py WIDENING, and the bar it
        # had to clear is stated in the comment on that set: an addition must be
        # SQL GRAMMAR following UPDATE, not an English word admitted to quiet a
        # finding. `cascade` is `ON DELETE CASCADE ON UPDATE CASCADE`, which is
        # `set`'s case exactly. If a future widening needs a word that is not
        # SQL grammar in either set, narrow the pattern instead.
        self.assertNotIn("cs", _ALIASES, "the alias is never captured; only the table is")
        self.assertEqual(_KEYWORDS, {"set", "cascade"})
        for keyword in _KEYWORDS:
            self.assertIsNotNone(
                _FROM_JOIN.search(f"ON CONFLICT DO UPDATE {keyword}"),
                f"{keyword} is in _KEYWORDS but _FROM_JOIN never captures it, so "
                f"the entry is dead and hides nothing")


class TestEveryRouteModuleIsScanned(unittest.TestCase):
    """The hole one level up from the one this file closes.

    SERVICE_MODULES is a hand-maintained tuple, so a new route module is
    invisible to every test above until somebody remembers to add it -- and the
    failure looks exactly like the one the scan exists to prevent: a service
    that starts cleanly and 500s on that route with a permission error. T-27
    added contribute.py and hit this; the tuple is now checked against the
    directory rather than against memory.

    THE TWO EXCLUSIONS ARE NAMED, NOT INFERRED. Anything else new in this
    package is a failure here, which is the point: adding a module should
    require a decision about whether its SQL runs as the service role, not a
    silent default of "no".
    """

    #: Runs as the ADMIN role, deliberately, and its CREATE statements would
    #: read as tables the service needs granted. Same exclusion the tuple's own
    #: comment has always carried.
    _ADMIN_ONLY = frozenset({"manage_app_users.py"})

    #: Holds no SQL at all -- it is the env-var module. Listed rather than
    #: filtered by "does it contain SELECT", because that filter would also
    #: exclude a route module that had its SQL deleted in a refactor.
    _NO_SQL = frozenset({"config.py"})

    def test_the_tuple_matches_the_directory(self):
        on_disk = {
            name for name in os.listdir(WEBAPP_DIR)
            if name.endswith(".py") and not name.startswith("_")
        }
        expected = on_disk - self._ADMIN_ONLY - self._NO_SQL
        self.assertEqual(
            set(SERVICE_MODULES), expected,
            "SERVICE_MODULES has drifted from the modules in this package. A "
            "module missing here has SQL that nothing checks against "
            "REQUIRED_TABLES; if it genuinely runs as the admin role or holds "
            "no SQL, add it to _ADMIN_ONLY or _NO_SQL above with the reason.")

    def test_config_really_holds_no_sql(self):
        # The exclusion above is a claim about the file, so it is checked
        # rather than asserted. If config.py ever grows a query, this goes red
        # and the exclusion has to be removed rather than quietly outgrown.
        self.assertEqual(
            sql_strings_in(os.path.join(WEBAPP_DIR, "config.py")), [])


class TestContributeIsScanned(unittest.TestCase):
    """T-27. The route that mints a contributor credential.

    WHAT IT MUST NOT NAME is the interesting half. contribute.py reaches
    ../api/ over HTTP precisely so that `jobs_web` needs no grant on
    `contributors` or `api_keys` -- docs/adr/0006's consequences reject that
    grant outright. If either name ever appears in this module's SQL, the
    design has been reversed by accident and this goes red.
    """

    def _named(self):
        return tables_named_in(os.path.join(WEBAPP_DIR, "contribute.py"))

    def test_it_names_only_app_users(self):
        self.assertEqual(self._named(), {"app_users"})

    def test_app_users_is_declared_and_writable(self):
        self.assertEqual(schema_web.REQUIRED_TABLES["app_users"],
                         ("SELECT", "INSERT", "UPDATE"))

    def test_no_grant_crosses_into_the_contributor_api(self):
        named = self._named()
        for table in ("api_keys", "contributors"):
            self.assertNotIn(
                table, named,
                f"contribute.py names {table}. That table belongs to ../api/ "
                f"and jobs_web is granted nothing on it -- docs/adr/0006 "
                f"rejects DEC-84 option 1 outright. The credential is minted "
                f"by asking that service, not by writing its tables.")
            self.assertNotIn(table, schema_web.REQUIRED_TABLES)

    def test_the_new_columns_are_verified_at_startup(self):
        # Same argument as job_events and eval_labels below: a deploy that
        # ships this module ahead of `init-schema` finds an app_users without
        # the columns the UPDATE names.
        self.assertEqual(set(schema_web.REQUIRED_COLUMNS["app_users"]),
                         {"contributor_id", "contributor_opted_in_at"})

    def test_the_declared_columns_are_the_ones_the_writer_names(self):
        # Read from the UPDATE itself, so this is a statement about the writer
        # rather than a restatement of the declaration above.
        import re
        with open(os.path.join(WEBAPP_DIR, "contribute.py"), encoding="utf-8") as fh:
            source = fh.read()
        statements = re.findall(r"UPDATE app_users SET ([^\"]*)", source)
        self.assertEqual(len(statements), 1,
                         "opt_in is meant to be the only writer of these columns")
        for column in schema_web.REQUIRED_COLUMNS["app_users"]:
            self.assertIn(column, statements[0],
                          f"{column} is declared required but no writer names it")


class TestSchemaWebIsScanned(unittest.TestCase):
    """D69 residue part 3. schema_web.py was outside SERVICE_MODULES, so the one
    service-role query in it -- `SELECT 1 FROM profiles p` inside a NOT EXISTS,
    running at startup -- was declared by hand and checked by nothing.

    THE DELIVERABLE OF A WIDENING IS THE LIST OF WHAT IT ADDS, each confirmed
    individually, because widening a scanner can only ever ADD findings and a
    green run proves nothing about them. Re-measured at HEAD rather than
    inherited from the 2026-08-02 note: the file yields six names, and these
    tests are one assertion per name so that a future addition cannot slip in
    under a count."""

    def _named(self):
        return tables_named_in(os.path.join(WEBAPP_DIR, "schema_web.py"))

    def test_the_service_role_query_in_schema_web_is_now_seen(self):
        # The reason the exclusion mattered. This is real SQL, run as the
        # service role, and `profiles` was declared only because someone
        # remembered to.
        self.assertIn("profiles", self._named())
        self.assertIn("profiles", schema_web.REQUIRED_TABLES)

    def test_the_other_two_real_names_are_already_declared(self):
        named = self._named()
        for table in ("app_users", "oauth_logins"):
            self.assertIn(table, named)
            self.assertIn(table, schema_web.REQUIRED_TABLES)

    def test_the_catalog_names_are_excluded_not_declared(self):
        # `FROM pg_constraint` and `FROM information_schema.columns` are
        # introspection, readable by every role and granted to nobody. They must
        # not reach REQUIRED_TABLES and must not be reported undeclared either.
        for name in ("pg_constraint", "information_schema"):
            self.assertTrue(_is_catalog(name))
            self.assertNotIn(name, self._named())
            self.assertNotIn(name, schema_web.REQUIRED_TABLES)

    def test_cascade_is_excluded_as_grammar_not_as_a_table(self):
        # Task 26's builder_profiles FK is what put `ON UPDATE CASCADE` in this
        # file; it carried none before. Confirmed as grammar, not a name: the
        # capture comes from the FK clause and nothing declares a table by it.
        self.assertIn("cascade", _KEYWORDS)
        self.assertNotIn("cascade", self._named())
        self.assertIsNotNone(
            _FROM_JOIN.search("ON DELETE CASCADE ON UPDATE CASCADE"),
            "the premise: this is why cascade needs an entry at all")

    def test_the_catalog_predicate_does_not_swallow_a_real_table(self):
        # The risk of any namespace exclusion: a real table whose name starts
        # the same way. `pg_` is a reserved prefix in Postgres, so this cannot
        # collide with an application table -- but the assertion is cheap and
        # the failure would be silent.
        for table in schema_web.REQUIRED_TABLES:
            self.assertFalse(_is_catalog(table),
                             f"{table} is declared AND reads as a catalog name")

    def test_no_ddl_table_name_leaks_in_from_the_admin_half(self):
        # The original reason for the exclusion, tested rather than assumed.
        # _FROM_JOIN keys on FROM/JOIN/INTO/UPDATE, and `CREATE TABLE IF NOT
        # EXISTS <name>` matches none of them, so the DDL contributes no names.
        # If that ever changes, this file's CREATEs would start reading as
        # tables the service needs granted and the exclusion should come back.
        self.assertIsNone(
            _FROM_JOIN.search("CREATE TABLE IF NOT EXISTS builder_profiles ("))
        self.assertNotIn("builder_profiles_parent", self._named())


class TestGrantsCoverTheSQL(unittest.TestCase):

    def test_every_queried_table_is_declared(self):
        declared = set(schema_web.REQUIRED_TABLES)
        for module in SERVICE_MODULES:
            path = os.path.join(WEBAPP_DIR, module)
            undeclared = tables_named_in(path) - declared
            self.assertEqual(
                undeclared, set(),
                f"{module} queries {sorted(undeclared)}, which is not in "
                f"schema_web.REQUIRED_TABLES. Add it there (with the privileges "
                f"it needs) and to the grant table in README.md, or the service "
                f"will start cleanly and fail on that one request.")

    def test_required_tables_matches_tables_touched(self):
        self.assertEqual(set(schema_web.REQUIRED_TABLES), set(schema_web.TABLES_TOUCHED))

    def test_no_write_grant_on_a_pipeline_table(self):
        # The boundary this service is built around: it can read the corpus and
        # append engagement, and it can rewrite nothing. A session-hijacking bug
        # or an injection here must cost reads and event rows, not the corpus.
        #
        # cohort_signal (tranche_five/28) is here for a sharper version of the
        # same reason. It is pipeline-owned like the rest -- ../schema.py
        # declares it and ../cohort.py's nightly fold is its only writer -- but
        # what a write grant would cost is not corpus damage: it is the
        # suppression rule. The threshold below which a posting gets no badge is
        # a privacy control, and it is enforced in exactly one place. A service
        # that could INSERT a bucket could publish one it never computed, from a
        # count nobody applied a floor to.
        #
        # IT IS ALSO THE ONE ENTRY test_every_queried_table_is_declared ABOVE
        # CANNOT SEE. That scan keeps only string literals matching
        # SELECT|INSERT|UPDATE|DELETE, and jobs.py names cohort_signal solely in
        # _COHORT_SIGNAL_JOIN -- a bare `LEFT JOIN cohort_signal cs ON ...`
        # fragment, which contains none of those words. _BUILDER_STATE_JOIN is
        # invisible for the same reason and is declared only by luck, because
        # write_builder_state's real INSERT names that table elsewhere in the
        # file. So for cohort_signal this line is not a companion assertion, it
        # is the only automated thing standing between a missing GRANT and a
        # permission-denied 500 on a Builder's first list render.
        pipeline_read_only = ("jobs_app", "jobs", "job_matches", "job_scores",
                              "job_facts", "profiles", "cohort_signal",
                              # task 25, and the same argument as cohort_signal
                              # one line up: search_query_signal is the exposed,
                              # suppressed, bucketed watcher count and
                              # search_query_results is what a search surfaced.
                              # The pipeline computes both; this service must not
                              # be able to write either. search_query_signal is
                              # also named ONLY in search._SIGNAL_JOIN, a bare
                              # join clause -- so it is visible to the scan above
                              # only because D69 widened it, exactly as
                              # cohort_signal is.
                              "search_query_signal", "search_query_results")
        for table in pipeline_read_only:
            # Membership first, so an undeclared table fails with an
            # instruction rather than with a bare KeyError from the line below
            # -- the reader of this failure is whoever has to add the entry.
            self.assertIn(
                table, schema_web.REQUIRED_TABLES,
                f"{table} is pipeline-owned and queried by this service, but "
                f"schema_web.REQUIRED_TABLES has no entry, so verify_schema() "
                f"never checks it: the service starts cleanly and 500s with "
                f"permission denied on the first request that touches it. Add "
                f'"{table}": ("SELECT",) there and to README.md\'s grant table.')
            self.assertEqual(
                schema_web.REQUIRED_TABLES[table], ("SELECT",),
                f"{table} is pipeline-owned and must stay SELECT-only here")
        self.assertEqual(schema_web.REQUIRED_TABLES["job_events"],
                         ("SELECT", "INSERT"),
                         "job_events is append-only: a dismiss is a row, not a delete")
        # INSERT to register a query, and NOT update: the run statistics and the
        # decay flag are the pipeline's. searchnorm.REGISTER_QUERY_SQL's
        # conflict branch is what makes find-or-create work without one.
        self.assertEqual(schema_web.REQUIRED_TABLES["search_queries"],
                         ("SELECT", "INSERT"),
                         "search_queries: registering is ours, scheduling is not")
        self.assertNotIn("DELETE",
                         schema_web.REQUIRED_TABLES["search_query_watchers"],
                         "unwatching sets removed_at; who watched what is never "
                         "deleted, and never deletable from here")

    def test_the_label_tables_are_declared_and_append_only(self):
        # label.py's own SQL names eval_label_items; the rest of the golden-set
        # SQL lives in ../evals/labels.py, whose table names arrive here
        # through labels.WEB_PRIVILEGES rather than through the AST scan above
        # -- that scan cannot see a table name that is a module constant, and
        # tests/test_labels.py in the pipeline suite is where those three are
        # checked against the DDL that creates them.
        from evals import labels
        for table in labels.TABLES:
            self.assertIn(table, schema_web.REQUIRED_TABLES,
                          f"{table} is written by /v1/label and must be granted")
        self.assertNotIn("UPDATE", schema_web.REQUIRED_TABLES["eval_labels"])
        self.assertNotIn("DELETE", schema_web.REQUIRED_TABLES["eval_labels"])
        self.assertIn("eval_labels_id_seq", schema_web.REQUIRED_SEQUENCES)

    def test_the_bigserial_sequence_is_declared(self):
        # job_events.id is BIGSERIAL, so INSERT on the table is not enough --
        # nextval() needs USAGE on the sequence, and its absence is a runtime
        # 500 rather than a startup error unless it is checked.
        self.assertIn("job_events_id_seq", schema_web.REQUIRED_SEQUENCES)

    def test_every_written_column_added_after_ship_is_verified_at_startup(self):
        # The two processes migrate on different schedules: ensure_schema() is
        # the pipeline's, and this service holds no DDL rights. A deploy that
        # ships webapp/ ahead of a nightly run finds a job_events that exists,
        # is granted correctly, and is missing the columns the INSERT names --
        # a 500 on a real user's first click, which is precisely what
        # verify_schema() exists to convert into a refusal to start.
        self.assertEqual(
            set(schema_web.REQUIRED_COLUMNS["job_events"]),
            {"request_id", "rank", "dwell_ms", "reason", "visibility",
             "criteria_version"})

    def test_the_label_provenance_columns_are_verified_at_startup(self):
        # Same failure, WIDER WINDOW. job_events' migration is the nightly
        # pipeline's, so drift there repairs itself within a day; eval_labels'
        # is `evals label init`, run by hand, so nothing repairs it until
        # someone remembers. The symptom either way is a 500 on a volunteer's
        # submit, and this is what converts it into a refusal to start.
        self.assertEqual(
            set(schema_web.REQUIRED_COLUMNS["eval_labels"]),
            {"facts_version", "facts_version_known"})

    def test_the_declared_label_columns_are_the_ones_record_names(self):
        # Read from labels.record()'s own INSERT rather than from
        # PROVENANCE_COLUMNS, so this is an independent statement about the
        # writer rather than a restatement of the declaration.
        import inspect
        import re

        from evals import labels

        statements = re.findall(r"INSERT INTO eval_labels\s*\(([^)]*)\)",
                                inspect.getsource(labels.record))
        self.assertEqual(len(statements), 1,
                         "record() is the only writer -- a second INSERT here "
                         "is a second place to forget a column")
        named = {c.strip() for c in statements[0].split(",")}
        for column in schema_web.REQUIRED_COLUMNS["eval_labels"]:
            self.assertIn(column, named,
                          f"{column} is declared required but record() does "
                          f"not name it")

    def test_the_declared_columns_are_the_ones_the_writers_name(self):
        # The drift this guards: adding a column to an INSERT and forgetting the
        # declaration re-opens the hole the test above closed, and nothing would
        # go red until a deploy raced a migration.
        #
        # THE UNION OF ALL WRITERS, NOT ONE OF THEM. jobs.py has two -- the
        # client path in record_events and the derived path in derive_skips --
        # and their column lists differ legitimately: a skip has no dwell_ms and
        # no reason, because nobody dwelt on it and nobody gave a reason. An
        # earlier version of this test read only the first statement it found
        # and failed on exactly that difference, which is the test doing its job
        # about itself.
        import re

        import jobs
        with open(jobs.__file__, encoding="utf-8") as fh:
            source = fh.read()
        statements = re.findall(r"INSERT INTO job_events\s*\(([^)]*)\)", source)
        self.assertEqual(len(statements), 2,
                         "expected exactly two writers: the client path and the "
                         "skip derivation")
        named = {c.strip() for s in statements for c in s.split(",")}
        for column in schema_web.REQUIRED_COLUMNS["job_events"]:
            self.assertIn(column, named,
                          f"{column} is declared required but no writer names it")

    def test_the_event_grant_is_table_level_and_covers_new_columns(self):
        # WHY THIS IS WORTH A TEST rather than an assumption. Postgres supports
        # COLUMN-level grants, and under one of those, adding a column silently
        # produces a column the grantee cannot write -- an INSERT naming it
        # fails at runtime, on a user's click, long after the migration looked
        # like it worked. Task 27 added six columns to job_events on that
        # assumption, so the assumption is pinned: the declaration here is a
        # bare privilege list with no column list anywhere in it, which is what
        # makes a table-level GRANT the thing schema_web emits and checks.
        privileges = schema_web.REQUIRED_TABLES["job_events"]
        self.assertEqual(privileges, ("SELECT", "INSERT"))
        for privilege in privileges:
            self.assertNotIn("(", privilege,
                             "a column-list grant would not cover a new column")


if __name__ == "__main__":
    unittest.main()

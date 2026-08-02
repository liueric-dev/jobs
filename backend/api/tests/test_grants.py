"""Every table this service's SQL names must be in REQUIRED_TABLES.

WHY THIS TEST EXISTS. REQUIRED_TABLES, REQUIRED_SEQUENCES and REQUIRED_COLUMNS
drive three things: `verify_schema()`'s startup check, the GRANT table in
README.md, and the operator's mental model. A route that starts querying a new
table without being added there produces a service that starts cleanly and 500s
on that one request -- in production, on a contributor's first submit, with a
permission error nobody was looking for.

This service has already paid for that lesson twice, which is the reason to
automate it rather than remember it:

  - `submission_log_id_seq` was in README's privilege table and in nothing that
    ran, so its absence surfaced as a 500 on a contributor's first submit.
    REQUIRED_SEQUENCES closed it (`query_claims.py`).
  - `submission_log.action` is new in this tranche and every INSERT names it,
    while `init-schema` is a separate admin command -- so shipping app.py ahead
    of it is one `git pull` away from the identical failure. REQUIRED_COLUMNS
    closes that one.

`backend/webapp/tests/test_grants.py` is this file's sibling and cites api/ as
where the argument came from. The AST scan below is that file's, kept
deliberately similar so a fix to one reads as a fix to the other.
"""

import ast
import os
import re
import sys
import unittest

API_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, API_DIR)

import query_claims as qc  # noqa: E402

#: Modules whose SQL runs as the restricted `jobs_api` role.
#:
#: manage_users.py IS included, unlike webapp's equivalent exclusion of
#: manage_app_users.py, and the difference is not an oversight: its DDL lives in
#: qc.ensure_schema() rather than in its own body, so what remains here --
#: create, list, revoke -- runs on the same restricted DATABASE_URL the service
#: uses and touches only contributors and api_keys. Its own docstring says so.
#:
#: contribution_report.py is included on the same reasoning: it connects on
#: qc.DATABASE_URL, reads submission_log and contributors, and needs no grant
#: beyond the SELECTs this role already holds -- which is precisely the claim
#: this scan checks rather than assumes, and the reason the report lives in this
#: package instead of backend/tools/ (which runs as jobs_pipeline and holds
#: nothing on submission_log).
SERVICE_MODULES = ("app.py", "query_claims.py", "manage_users.py",
                   "contribution_report.py")

#: Aliases bound inside the SQL itself. They follow FROM/JOIN syntactically and
#: are not tables to grant.
_ALIASES = {"c", "k"}

#: Keywords that follow one of the words below syntactically and are not names
#: of anything. `set` is here because an upsert reads `ON CONFLICT ... DO UPDATE
#: SET`, and the pattern below cannot tell that UPDATE from the statement kind.
_KEYWORDS = {"set"}

#: System catalogs. Readable by every role by construction, grantable by nobody,
#: and therefore not a GRANT anyone could add. verify_schema() reads
#: information_schema.columns to check REQUIRED_COLUMNS -- the one place this
#: service queries something it does not own and must not declare.
_CATALOGS = {"information_schema", "pg_catalog"}

_STATEMENT = re.compile(r"\b(SELECT|INSERT|UPDATE|DELETE)\b", re.I)
_FROM_JOIN = re.compile(r"\b(?:FROM|JOIN|INTO|UPDATE)\s+([a-z_][a-z0-9_]*)", re.I)


def sql_strings_in(path):
    """Every string literal in the module that is actually SQL.

    Parsed out of the AST rather than grepped, and with docstrings excluded,
    because neither filter alone is enough: a grep cannot tell a table name from
    prose, and the prose in this package is thick with sentences like "one
    documented requirement a startup check could not catch" and "INSERT without
    SELECT on google_jobs_query_stats" that satisfy both patterns below.

    An f-string is REASSEMBLED from its literal segments before being tested, so
    a `FROM {table}` cannot read as FROM followed by whatever literal happens to
    come after the placeholder.
    """
    with open(path) as f:
        tree = ast.parse(f.read(), filename=path)

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
            texts.append(" ".join(
                part.value for part in node.values
                if isinstance(part, ast.Constant) and isinstance(part.value, str)))
        elif (isinstance(node, ast.Constant) and isinstance(node.value, str)
                and id(node) not in consumed):
            texts.append(node.value)

    return [t for t in texts if _STATEMENT.search(t)]


def tables_named_in(path):
    found = set()
    for sql in sql_strings_in(path):
        for match in _FROM_JOIN.finditer(sql):
            name = match.group(1).lower()
            if name not in _ALIASES and name not in _KEYWORDS and name not in _CATALOGS:
                found.add(name)
    return found


class TestGrantsCoverTheSQL(unittest.TestCase):

    def test_every_queried_table_is_declared(self):
        declared = set(qc.REQUIRED_TABLES)
        for module in SERVICE_MODULES:
            path = os.path.join(API_DIR, module)
            undeclared = tables_named_in(path) - declared
            self.assertEqual(
                undeclared, set(),
                f"{module} queries {sorted(undeclared)}, which is not in "
                f"query_claims.REQUIRED_TABLES. Add it there (with the "
                f"privileges it needs) and to the grant table in README.md, or "
                f"the service will start cleanly and fail on that one request.")

    def test_the_scan_actually_finds_something(self):
        # A regex that silently stopped matching would make the test above pass
        # for every possible codebase. Pin the floor: these three are the tables
        # the request path cannot function without.
        found = set()
        for module in SERVICE_MODULES:
            found |= tables_named_in(os.path.join(API_DIR, module))
        for table in ("api_keys", "submission_log", "job_ingest_state"):
            self.assertIn(table, found)

    def test_no_declared_table_is_unused(self):
        # The other direction. A granted table nothing queries is a privilege
        # held for no reason, and this service's whole security posture is that
        # its role can do exactly six things.
        found = set()
        for module in SERVICE_MODULES:
            found |= tables_named_in(os.path.join(API_DIR, module))
        # `jobs` is reached through lib.upsert rather than by SQL written here,
        # so it cannot appear in the scan and is asserted separately.
        self.assertEqual(set(qc.REQUIRED_TABLES) - found - {"jobs"}, set())

    def test_the_write_grants_are_the_ones_the_sql_needs(self):
        # No DELETE anywhere: the code issues none, and this is the assertion
        # that keeps it that way through a future edit.
        for table, privileges in qc.REQUIRED_TABLES.items():
            self.assertNotIn("DELETE", privileges,
                             f"{table}: this service never deletes")
            self.assertIn("SELECT", privileges,
                          f"{table}: ON CONFLICT needs SELECT on the arbiter")

    def test_nothing_pipeline_owned_is_granted(self):
        # The boundary the README's three privilege sections exist to defend:
        # `jobs_api` faces untrusted callers, so it holds nothing on the
        # pipeline's derived tables or on the app view.
        for table in ("job_scores", "job_facts", "job_matches", "profiles",
                      "hn_seen_comments", "ingest_progress", "job_events",
                      "jobs_app", "app_users"):
            self.assertNotIn(table, qc.REQUIRED_TABLES)


class TestBigserialSequences(unittest.TestCase):

    def test_the_bigserial_sequence_is_declared(self):
        # submission_log.id is BIGSERIAL, so INSERT on the table is not enough
        # -- nextval() needs USAGE on the sequence, and its absence is a runtime
        # 500 rather than a startup error unless it is checked.
        self.assertIn("submission_log_id_seq", qc.REQUIRED_SEQUENCES)
        self.assertEqual(qc.REQUIRED_SEQUENCES["submission_log_id_seq"],
                         ("USAGE", "SELECT"))

    def test_every_bigserial_this_service_creates_has_a_sequence_grant(self):
        # Derived from the DDL rather than listed, so adding a fourth table with
        # a BIGSERIAL id and forgetting the grant is red here rather than 500 on
        # first use. That is the exact history REQUIRED_SEQUENCES came from.
        with open(os.path.join(API_DIR, "query_claims.py")) as fh:
            source = fh.read()
        for table in re.findall(
                r"CREATE TABLE IF NOT EXISTS (\w+) \((?:[^)]*?)BIGSERIAL", source):
            self.assertIn(f"{table}_id_seq", qc.REQUIRED_SEQUENCES,
                          f"{table}.id is BIGSERIAL and needs a sequence grant")


class TestRequiredColumns(unittest.TestCase):
    """The third instance of the same argument, added with `action`.

    A table can exist, be granted correctly, and still be missing a column every
    INSERT names, because `init-schema` is a deliberately separate admin command
    this service holds no rights to run. That is a 500 on a contributor's first
    claim; verify_schema() turns it into a refusal to start.
    """

    def test_action_is_declared(self):
        self.assertIn("action", qc.REQUIRED_COLUMNS["submission_log"])

    def test_every_declared_column_is_created_by_ensure_schema(self):
        # A declaration with no DDL behind it would refuse to start forever.
        with open(os.path.join(API_DIR, "query_claims.py")) as fh:
            source = fh.read()
        for table, columns in qc.REQUIRED_COLUMNS.items():
            for column in columns:
                self.assertIn(f'("{column}", "TEXT")', source,
                              f"{table}.{column} is required at startup but "
                              f"ensure_schema never adds it")

    def test_every_declared_column_is_named_by_a_writer(self):
        # The drift this guards: declaring a column and never writing it makes
        # the startup check stricter than the code needs, which is how a
        # deployment gets blocked by a requirement nobody can justify.
        with open(os.path.join(API_DIR, "query_claims.py")) as fh:
            source = fh.read()
        statements = re.findall(r"INSERT INTO submission_log\s*\(([^)]*)\)", source)
        self.assertEqual(len(statements), 1,
                         "log_submission is meant to be the only writer")
        named = {c.strip() for s in statements for c in s.split(",")}
        for column in qc.REQUIRED_COLUMNS["submission_log"]:
            self.assertIn(column, named,
                          f"{column} is declared required but no writer names it")

    def test_verify_schema_checks_all_three_maps(self):
        # The maps are only worth maintaining if the startup path reads them.
        import app
        with open(app.__file__, encoding="utf-8") as fh:
            body = fh.read().split("def verify_schema")[1].split("\ndef ")[0]
        for name in ("REQUIRED_TABLES", "REQUIRED_SEQUENCES", "REQUIRED_COLUMNS"):
            self.assertIn(f"qc.{name}", body)


if __name__ == "__main__":
    unittest.main()

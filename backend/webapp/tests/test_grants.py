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
SERVICE_MODULES = ("auth.py", "jobs.py", "db.py", "app.py", "label.py")

#: Aliases bound inside the SQL itself -- subquery, lateral and correlation
#: names. They follow FROM/JOIN syntactically but are not tables to grant.
_ALIASES = {"m", "s", "e", "v", "u", "ev", "prior", "public", "lateral"}

_STATEMENT = re.compile(r"\b(SELECT|INSERT|UPDATE|DELETE)\b", re.I)
_FROM_JOIN = re.compile(r"\b(?:FROM|JOIN|INTO|UPDATE)\s+([a-z_][a-z0-9_]*)", re.I)


def sql_strings_in(path):
    """Every string literal in the module that is actually SQL.

    Parsed out of the AST rather than grepped out of the source, and with
    docstrings excluded, because neither filter alone is enough here: a grep
    cannot tell a table name from prose, and the prose in this package is full
    of sentences like "reachable from JavaScript" and "revocation is one
    UPDATE" that satisfy both patterns below. Docstrings are the only place
    that happens, so dropping them is the whole fix.

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

    return [t for t in texts if _STATEMENT.search(t)]


def tables_named_in(path):
    found = set()
    for sql in sql_strings_in(path):
        for match in _FROM_JOIN.finditer(sql):
            name = match.group(1).lower()
            if name not in _ALIASES:
                found.add(name)
    return found


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
        pipeline_read_only = ("jobs_app", "jobs", "job_matches", "job_scores",
                              "job_facts", "profiles")
        for table in pipeline_read_only:
            self.assertEqual(
                schema_web.REQUIRED_TABLES[table], ("SELECT",),
                f"{table} is pipeline-owned and must stay SELECT-only here")
        self.assertEqual(schema_web.REQUIRED_TABLES["job_events"],
                         ("SELECT", "INSERT"),
                         "job_events is append-only: a dismiss is a row, not a delete")

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


if __name__ == "__main__":
    unittest.main()

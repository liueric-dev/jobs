"""T-38 / docs/adr/0009: this service never writes a `search_queries` run statistic.

WHAT THIS PINS, AND WHY A TEST RATHER THAN THE GRANT ALONE
    The privilege is the real enforcement -- `GRANT UPDATE (claimed_at,
    claimed_by, claim_granted_at)` and no more, spelled out above
    REQUIRED_TABLES in ../query_claims.py. But a GRANT lives on a database, and
    the two statements that issue it were `OQ-29` in ../../../DEV_TASKS.md
    (closed 2026-08-09, both run on the deployed database): an action on a
    machine, not something this repo runs. So between a commit that widens a
    statement here and the day somebody notices the 500, there is nothing that
    reports it. This file is that report, and it runs in CI where no database
    exists.

    THE STARTUP CHECK STILL DOES NOT REPORT A GRANT THAT IS TOO WIDE, which is
    why "the privilege is the real enforcement" is not the whole story and this
    file is not redundant. verify_schema() reads
    REQUIRED_COLUMN_PRIVILEGES with has_column_privilege() as of OQ-29's
    closure, so it now SEES the column-scoped grant it previously could not --
    but every check it makes asks whether a privilege is present, never whether
    it is broader than declared. Making it ask the second question is `T-58`.

    It is also the only check that survives the wrong fix. 0009 refused a
    "narrow writer in api/ that only sets the columns from server-side values"
    on the grounds that it needs the identical GRANT -- which means the day
    somebody issues the wider grant by hand to make such a writer work, every
    privilege check in this tree goes on passing. What would still be true is
    that a statement in this service names a column that is not ours, and that
    is what these tests read.

NO DATABASE, DELIBERATELY, AND NOTHING IMPORTED FOR THE SCAN
    ../app.py is read off disk and parsed rather than imported: importing it
    pulls in FastAPI and builds the app, and what is under test is the source
    text of its SQL, which `ast` gives without either. The one import is
    ../query_claims.py, for the constants -- asserting a tuple's shape by
    reading the file that defines it would only test this file's own regex.

THE GUARD CANNOT COVER NOTHING
    T-39's lesson, and it applies twice here. A scanner that found no SQL at
    all would pass every assertion below, so one test feeds it a statement that
    IS a violation and requires it to be caught, and another parses
    record_run's own UPDATE and fails if `RUN_STATISTICS` and that SET clause
    ever stop naming the same five columns.
"""

import ast
import os
import re
import sys
import unittest

API_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BACKEND_DIR = os.path.dirname(API_DIR)
sys.path.insert(0, API_DIR)
sys.path.insert(0, BACKEND_DIR)

import query_claims as qc  # noqa: E402

import searchqueries  # noqa: E402

#: Every file that runs SQL as the `jobs_api` role. manage_users.py is here
#: because it holds this service's DDL-adjacent admin commands and is exactly
#: the kind of place a "just this once" UPDATE would be written.
SERVICE_SOURCES = (
    os.path.join(API_DIR, "query_claims.py"),
    os.path.join(API_DIR, "app.py"),
    os.path.join(API_DIR, "manage_users.py"),
)

#: The three this service may write, from the map that declares them. Read
#: rather than restated so that widening REQUIRED_COLUMNS cannot quietly widen
#: what this file considers acceptable.
CLAIM_COLUMNS = qc.REQUIRED_COLUMNS["search_queries"]


def write_statements(source):
    """Every string constant in `source` that writes to `search_queries`.

    A STRING CONSTANT AND NOT A LINE, because this repo's SQL is written as
    triple-quoted literals spanning ten lines, and a line-based scan would see
    `SET claimed_at = %(now)s` without the `UPDATE search_queries` three lines
    above it and have no idea which table it was about.

    Returns the statements themselves so a failure can print the offender.
    """
    found = []
    for node in ast.walk(ast.parse(source)):
        if not isinstance(node, ast.Constant) or not isinstance(node.value, str):
            continue
        text = node.value
        upper = text.upper()
        if "SEARCH_QUERIES" not in upper:
            continue
        if "UPDATE" not in upper and "INSERT" not in upper:
            continue
        found.append(text)
    return found


def columns_written(statement):
    """The column names `statement` assigns, as a set.

    Both shapes this tree writes: everything assigned between `SET` and
    `WHERE`, and an INSERT's parenthesised column list.

    EVERY ASSIGNMENT IN THE SET CLAUSE, NOT THE FIRST ON EACH LINE. This was
    written the lazy way first -- one regex per line, anchored at the start --
    and TestTheGuardBites caught it: release_search_query_claim writes all
    three claim columns on ONE line, so a per-line scan read a third of the
    statements in this service and passed everything anyway. That is the exact
    failure mode this whole file exists to prevent, found in the file itself.
    """
    cols = set()
    parts = re.split(r"\bSET\b", statement, maxsplit=1, flags=re.IGNORECASE)
    if len(parts) == 2:
        set_block = re.split(r"\bWHERE\b|\bRETURNING\b", parts[1],
                             maxsplit=1, flags=re.IGNORECASE)[0]
        for m in re.finditer(r"([a-z_][a-z0-9_]*)\s*=(?!=)", set_block,
                             re.IGNORECASE):
            cols.add(m.group(1).lower())
    m = re.search(r"INSERT\s+INTO\s+\w+\s*\(([^)]*)\)", statement, re.IGNORECASE)
    if m:
        for part in m.group(1).split(","):
            cols.add(part.strip().lower())
    return cols


class TestNoServiceStatementWritesARunStatistic(unittest.TestCase):
    """The boundary itself: docs/adr/0009's whole content, as an assertion."""

    def test_no_run_statistic_is_named_by_any_write_in_this_service(self):
        offenders = []
        for path in SERVICE_SOURCES:
            with open(path) as fh:
                for statement in write_statements(fh.read()):
                    bad = columns_written(statement) & set(searchqueries.RUN_STATISTICS)
                    if bad:
                        offenders.append((os.path.basename(path), sorted(bad),
                                          statement.strip()[:200]))
        self.assertEqual(
            offenders, [],
            "A statement in this service writes a search_queries run "
            "statistic. Those five columns are ../../searchqueries.py's; "
            "record_run() is their only writer and docs/adr/0009 is the "
            "decision that keeps it so. If a contributor's run needs to "
            "advance them, write a submission_log row with action="
            f"{searchqueries.CONTRIBUTOR_RUN_ACTION!r} and let "
            "reconcile_contributor_runs() do it.\n"
            f"{offenders}")

    def test_the_only_search_queries_columns_written_here_are_the_claim_three(self):
        """Stronger than the above, and the one that catches a NEW column.

        The test above forbids five names. This one permits only three, so a
        column added to `search_queries` tomorrow and written from here is a
        failure without anybody having to remember to add it to a list.
        """
        for path in SERVICE_SOURCES:
            with open(path) as fh:
                for statement in write_statements(fh.read()):
                    written = columns_written(statement)
                    extra = written - set(CLAIM_COLUMNS) - {"id"}
                    self.assertEqual(
                        extra, set(),
                        f"{os.path.basename(path)} writes {sorted(extra)} on "
                        f"search_queries; this service's grant covers "
                        f"{list(CLAIM_COLUMNS)} and nothing else.")

    def test_required_columns_does_not_declare_a_run_statistic(self):
        """The map is what verify_schema() checks at startup, so a run
        statistic appearing here would make the service refuse to start until
        somebody issued the very grant 0009 refuses."""
        self.assertEqual(
            set(CLAIM_COLUMNS) & set(searchqueries.RUN_STATISTICS), set())

    def test_the_documented_grant_names_exactly_the_three_claim_columns(self):
        """The comment above REQUIRED_TABLES is what an operator copies into
        psql (OQ-29), so it is the real grant on every deployed machine. A
        drifted comment here is a wider privilege in production."""
        with open(os.path.join(API_DIR, "query_claims.py")) as fh:
            source = fh.read()
        m = re.search(r"GRANT UPDATE \(([^)]*)\)", source)
        self.assertIsNotNone(
            m, "the GRANT UPDATE line above REQUIRED_TABLES is gone; it is "
               "what OQ-29 asks an operator to run")
        named = tuple(c.strip() for c in m.group(1).split(","))
        self.assertEqual(named, tuple(CLAIM_COLUMNS))


class TestTheGuardBites(unittest.TestCase):
    """A scanner that found nothing would pass all of the above."""

    def test_the_scan_finds_the_statements_that_are_actually_there(self):
        """Non-vacuity, stated as a floor rather than an exact count so that
        adding a claim statement does not turn this red for the wrong reason."""
        with open(os.path.join(API_DIR, "query_claims.py")) as fh:
            found = write_statements(fh.read())
        self.assertGreaterEqual(
            len(found), 1,
            "the scan found no search_queries write in query_claims.py, which "
            "contains try_claim_search_query and release_search_query_claim -- "
            "the scanner is broken, not the code")

    def test_a_widened_statement_is_caught(self):
        """The shape 0009 refuses, fed to the scanner directly."""
        offending = '''
            UPDATE search_queries
               SET claimed_at = NULL, last_run_at = %(now)s
             WHERE id = %(id)s
        '''
        stmts = write_statements(f"x = {offending!r}")
        self.assertEqual(len(stmts), 1)
        self.assertIn("last_run_at",
                      columns_written(stmts[0]) & set(searchqueries.RUN_STATISTICS))

    def test_a_run_statistic_written_from_an_insert_is_caught(self):
        """The other write shape, because forbidding only `SET` would leave the
        column list of an upsert unread -- and try_claim_query on the OTHER
        table is an upsert, so that shape is one copy-paste away."""
        offending = ("INSERT INTO search_queries (id, last_run_at, run_count) "
                     "VALUES (%s, %s, %s)")
        stmts = write_statements(f"x = {offending!r}")
        self.assertEqual(
            columns_written(stmts[0]) & set(searchqueries.RUN_STATISTICS),
            {"last_run_at", "run_count"})


class TestTheGuardCoversWhatRecordRunActuallyWrites(unittest.TestCase):
    """RUN_STATISTICS is the guard's whole vocabulary. If it and record_run's
    UPDATE drift apart, every test above goes on passing while covering less
    than it claims -- which is precisely T-39's failure mode."""

    def _record_run_update(self):
        with open(os.path.join(BACKEND_DIR, "searchqueries.py")) as fh:
            tree = ast.parse(fh.read())
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name == "record_run":
                for sub in ast.walk(node):
                    if (isinstance(sub, ast.Constant)
                            and isinstance(sub.value, str)
                            and "UPDATE search_queries" in sub.value):
                        return sub.value
        raise AssertionError("record_run's UPDATE statement was not found")

    def test_run_statistics_names_exactly_the_columns_record_run_sets(self):
        statement = self._record_run_update()
        set_block = statement.split("SET", 1)[1].split("WHERE", 1)[0]
        assigned = {m.group(1).lower() for m in
                    re.finditer(r"^\s*([a-z_][a-z0-9_]*)\s*=", set_block,
                                re.IGNORECASE | re.MULTILINE)}
        self.assertEqual(assigned, set(searchqueries.RUN_STATISTICS))


class TestTheRunActionIsOneConstantAndNotTwo(unittest.TestCase):
    """T-31's rule, one table over: two spellings that agree today are two
    spellings, and nothing reports the day they stop agreeing. Here the cost of
    divergence is silent -- api/ would write rows the reconciler never selects,
    so contributors' runs would go unrecorded with every counter reading zero
    and no error anywhere."""

    def test_submission_actions_takes_the_run_action_from_its_owner(self):
        with open(os.path.join(API_DIR, "query_claims.py")) as fh:
            tree = ast.parse(fh.read())
        assigned = None
        for node in ast.walk(tree):
            if (isinstance(node, ast.Assign)
                    and any(getattr(t, "id", None) == "SUBMISSION_ACTIONS"
                            for t in node.targets)):
                assigned = node.value
        self.assertIsNotNone(assigned, "SUBMISSION_ACTIONS is not assigned")
        last = assigned.elts[-1]
        self.assertIsInstance(
            last, ast.Attribute,
            "the run action is spelled out as a literal here. It must be read "
            "from searchqueries.CONTRIBUTOR_RUN_ACTION, which is what "
            "reconcile_contributor_runs() selects on -- two literals that "
            "agree today would diverge silently, and the symptom is "
            "contributors' runs never being reconciled with nothing logged.")
        self.assertEqual(last.attr, "CONTRIBUTOR_RUN_ACTION")
        self.assertEqual(last.value.id, "searchqueries")

    def test_the_value_reaches_the_tuple(self):
        """The AST test above says where it comes from; this says it arrived,
        because an import that resolved to a different module would satisfy the
        first and break the wire."""
        self.assertIn(searchqueries.CONTRIBUTOR_RUN_ACTION, qc.SUBMISSION_ACTIONS)

    def test_dataset_for_query_is_the_same_function_on_both_sides(self):
        """Not a copy: the endpoint 0007 still owes will call qc's name and the
        reconciler parses with searchqueries'. One function, so a change to the
        prefix cannot land on one side only."""
        self.assertIs(qc.dataset_for_query, searchqueries.dataset_for_query)


if __name__ == "__main__":
    unittest.main()

"""Unit tests for migrations/runner.py -- the schema_migrations table (T-10).

WHY THESE TESTS NEED A DATABASE (MOST OF THEM)
    ensure_migrations_table/applied/record are three lines of SQL each; the
    property worth pinning is what Postgres does with them (CREATE TABLE IF
    NOT EXISTS twice, ON CONFLICT DO UPDATE), not what a fake connection would
    be told to do. `evals.scratchdb.scratch_schema()` gives each test its own
    throwaway schema, same as tests/test_schema_ensure_app_view.py -- nothing
    here runs the ten real migration scripts or touches `public`.

WHAT apply_one() TESTS DO NOT DO
    They mock `subprocess.run` rather than actually invoking any of the ten
    scripts. `migrate_scores.py --apply` (used as the stand-in NAME below,
    picked arbitrarily -- these tests never let it run) writes real rows when
    it actually executes; the property under test is the runner's own
    call-it-once-then-remember bookkeeping, not that script's behavior.
"""

import os
import subprocess
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "migrations"))

import runner

from evals import scratchdb

requires_db = unittest.skipUnless(
    scratchdb.available(),
    "no scratch database: set DATABASE_URL (or JOBS_SCRATCH_DATABASE_URL)")


class TestRegistry(unittest.TestCase):
    """No database needed -- this is a claim about the filesystem."""

    def test_registry_names_match_the_scripts_on_disk(self):
        migrations_dir = os.path.dirname(os.path.abspath(runner.__file__))
        on_disk = {
            f[:-3] for f in os.listdir(migrations_dir)
            if f.startswith("migrate_") and f.endswith(".py")
        }
        self.assertEqual(runner.NAMES, on_disk)

    def test_registry_has_ten_entries(self):
        self.assertEqual(len(runner.REGISTRY), 10)


class TestMigrationsTable(unittest.TestCase):

    @requires_db
    def test_ensure_is_idempotent_and_starts_empty(self):
        with scratchdb.scratch_schema() as (conn, _name):
            runner.ensure_migrations_table(conn)
            runner.ensure_migrations_table(conn)  # second call: no error
            self.assertEqual(runner.applied(conn), {})

    @requires_db
    def test_record_and_applied_round_trip(self):
        with scratchdb.scratch_schema() as (conn, _name):
            runner.ensure_migrations_table(conn)
            runner.record(conn, "migrate_google_ids", "T-20 evidence")
            state = runner.applied(conn)
            self.assertIn("migrate_google_ids", state)
            _applied_at, note = state["migrate_google_ids"]
            self.assertEqual(note, "T-20 evidence")

    @requires_db
    def test_record_overwrites_on_conflict_rather_than_duplicating(self):
        with scratchdb.scratch_schema() as (conn, _name):
            runner.ensure_migrations_table(conn)
            runner.record(conn, "migrate_scores", "first note")
            runner.record(conn, "migrate_scores", "corrected note")
            state = runner.applied(conn)
            self.assertEqual(len(state), 1)
            self.assertEqual(state["migrate_scores"][1], "corrected note")

    @requires_db
    def test_status_lines_cover_every_registered_migration_exactly_once(self):
        with scratchdb.scratch_schema() as (conn, _name):
            runner.ensure_migrations_table(conn)
            runner.record(conn, "migrate_google_ids", "applied for this test")
            lines = runner.status_lines(conn)
            self.assertEqual(len(lines), len(runner.REGISTRY))
            applied_lines = [ln for ln in lines if ln.strip().startswith("[applied")]
            not_applied_lines = [ln for ln in lines
                                 if ln.strip().startswith("[NOT APPLIED")]
            self.assertEqual(len(applied_lines), 1)
            self.assertIn("migrate_google_ids", applied_lines[0])
            self.assertEqual(len(not_applied_lines), len(runner.REGISTRY) - 1)


class TestApplyOne(unittest.TestCase):

    @requires_db
    def test_first_apply_invokes_the_script_once_and_records_it(self):
        with scratchdb.scratch_schema() as (conn, _name):
            runner.ensure_migrations_table(conn)
            with mock.patch.object(runner.subprocess, "run") as run:
                run.return_value = mock.Mock(returncode=0)
                ok = runner.apply_one(conn, "migrate_scores", note="test run")
            self.assertTrue(ok)
            self.assertEqual(run.call_count, 1)
            self.assertIn("migrate_scores", runner.applied(conn))

    @requires_db
    def test_second_apply_of_the_same_name_does_not_invoke_the_script_again(self):
        with scratchdb.scratch_schema() as (conn, _name):
            runner.ensure_migrations_table(conn)
            with mock.patch.object(runner.subprocess, "run") as run:
                run.return_value = mock.Mock(returncode=0)
                first = runner.apply_one(conn, "migrate_scores", note="test run")
                second = runner.apply_one(conn, "migrate_scores", note="test run")
            self.assertTrue(first)
            self.assertTrue(second)
            self.assertEqual(run.call_count, 1,
                             "running --apply NAME twice must not re-invoke "
                             "NAME's script the second time")

    @requires_db
    def test_a_nonzero_exit_is_not_recorded_as_applied(self):
        with scratchdb.scratch_schema() as (conn, _name):
            runner.ensure_migrations_table(conn)
            with mock.patch.object(runner.subprocess, "run") as run:
                run.return_value = mock.Mock(returncode=1)
                ok = runner.apply_one(conn, "migrate_scores", note="test run")
            self.assertFalse(ok)
            self.assertNotIn("migrate_scores", runner.applied(conn))


_RUNNER_SCRIPT = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "migrations", "runner.py")


class TestCLIValidation(unittest.TestCase):
    """End-to-end against the real script, but only its argument validation
    -- an unregistered NAME is rejected before anything is invoked or
    recorded, so this never reaches subprocess.run or a real migration."""

    @requires_db
    def test_apply_of_an_unregistered_name_exits_nonzero_without_running_anything(self):
        result = subprocess.run(
            [sys.executable, _RUNNER_SCRIPT, "--apply", "not-a-real-migration"],
            capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("not one of the", result.stdout)

    @requires_db
    def test_mark_applied_without_note_is_refused(self):
        result = subprocess.run(
            [sys.executable, _RUNNER_SCRIPT, "--mark-applied", "migrate_scores"],
            capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("requires --note", result.stdout)


if __name__ == "__main__":
    unittest.main()

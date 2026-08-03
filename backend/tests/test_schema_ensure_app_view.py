"""schema.ensure_app_view's DROP fallback, and the GRANT it used to destroy.

T-13. DROP VIEW takes every GRANT with it and nothing in this repo re-granted
-- OQ-7 is the recorded day the webapp was down over it. This forces the
InvalidTableDefinition path against a real server (only Postgres raises it)
and asserts a grant issued beforehand survives the DROP + CREATE.
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import psycopg                                                  # noqa: E402
import schema                                                   # noqa: E402
from evals import scratchdb                                     # noqa: E402
from lib import envfile                                         # noqa: E402
from schema import _view_grants                                 # noqa: E402

envfile.load(os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), ".env"))

requires_db = unittest.skipUnless(
    scratchdb.available(),
    "no scratch database: set DATABASE_URL (or JOBS_SCRATCH_DATABASE_URL)")


class TestEnsureAppViewPreservesGrants(unittest.TestCase):

    @requires_db
    def test_a_grant_survives_the_forced_reorder_path(self):
        with scratchdb.scratch_schema() as (conn, _name):
            # A stand-in view, not schema.APP_VIEW's real SQL: this pins the
            # DROP-fallback behavior in isolation from jobs_app's real
            # column list, which is what forces InvalidTableDefinition here
            # without touching _APP_VIEW_SQL itself.
            conn.execute("CREATE TABLE t (a int, b int)")
            conn.execute("CREATE VIEW v AS SELECT a, b FROM t")
            conn.commit()
            conn.execute("GRANT SELECT ON v TO PUBLIC")
            conn.commit()

            try:
                # Reordering columns is exactly what raises
                # InvalidTableDefinition inside ensure_app_view's own
                # CREATE OR REPLACE VIEW attempt -- reproduced directly here
                # against `v` rather than by mutating _APP_VIEW_SQL.
                conn.execute("CREATE OR REPLACE VIEW v AS SELECT b, a FROM t")
                self.fail("premise: a column reorder must raise "
                          "InvalidTableDefinition, or this test proves "
                          "nothing")
            except psycopg.errors.InvalidTableDefinition:
                conn.rollback()

            grants = schema._view_grants(conn, "v")
            conn.execute("DROP VIEW IF EXISTS v")
            conn.execute("CREATE OR REPLACE VIEW v AS SELECT b, a FROM t")
            schema._regrant(conn, "v", grants)
            conn.commit()

            after = _view_grants(conn, "v")
        self.assertIn(("PUBLIC", "SELECT", False), after,
                      "the GRANT issued before the reorder did not survive "
                      "the DROP -- this is OQ-7 again")

    @requires_db
    def test_ensure_app_view_itself_preserves_a_grant_on_the_real_view(self):
        """The real path, not the stand-in: creates jobs_app for real inside
        a scratch schema, corrupts its column order (forcing the NEXT
        ensure_app_view() call to hit InvalidTableDefinition), grants it in
        that corrupted state, then asserts the grant survives the call that
        repairs it."""
        with scratchdb.scratch_schema() as (conn, name):
            schema.ensure_app_view(conn)
            conn.commit()

            # Reorder jobs_app's columns without knowing its underlying
            # FROM/JOIN structure: rename the real view out of the way, then
            # create the target name as a thin view over it with columns
            # reversed. This produces a view with the real one's name and
            # column set but an order _APP_VIEW_SQL's CREATE OR REPLACE
            # cannot reconcile -- and since the new jobs_app depends on the
            # renamed original (not the other way around), ensure_app_view's
            # own `DROP VIEW IF EXISTS jobs_app` can still succeed with no
            # CASCADE. table_schema must be pinned explicitly:
            # information_schema.columns is not scoped by search_path, so a
            # stray scratch schema left over from another run would
            # otherwise duplicate every row this query returns.
            cols = [r[0] for r in conn.execute(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_schema = %s AND table_name = %s "
                "ORDER BY ordinal_position",
                (name, schema.APP_VIEW)).fetchall()]
            conn.execute(f"ALTER VIEW {schema.APP_VIEW} RENAME TO jobs_app_orig")
            conn.execute(
                f"CREATE VIEW {schema.APP_VIEW} AS SELECT "
                + ", ".join(reversed(cols))
                + " FROM jobs_app_orig")
            conn.commit()

            # The grant goes on AFTER the corruption, so it is a grant on
            # the reordered view -- the one ensure_app_view is about to DROP.
            conn.execute(f"GRANT SELECT ON {schema.APP_VIEW} TO PUBLIC")
            conn.commit()

            schema.ensure_app_view(conn)

            after = _view_grants(conn, schema.APP_VIEW)
        self.assertIn(("PUBLIC", "SELECT", False), after)


if __name__ == "__main__":
    unittest.main()

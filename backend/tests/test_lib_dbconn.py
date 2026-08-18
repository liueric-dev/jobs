"""Tests for lib/dbconn.py -- schema handling and the DATABASE_URL rule.

Split out of the shared library's suite on 2026-07-26 when lib/ was vendored
into this repo (~/apps/REORG.md slice G).

stdlib unittest rather than pytest, which isn't installed here and isn't
worth adding as a dependency to a stdlib-plus-psycopg codebase.
"""

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import unittest  # noqa: E402
from unittest.mock import patch  # noqa: E402

from lib import dbconn  # noqa: E402


class _RecordingConn:
    """Just enough psycopg surface for connect(): execute/commit."""

    def __init__(self):
        self.statements = []
        self.commits = 0
        self.autocommit = False

    def execute(self, sql, params=None):
        self.statements.append(sql)
        return self

    def commit(self):
        self.commits += 1


class TestConnectSchemaHandling(unittest.TestCase):

    def _connect(self, **kw):
        rec = _RecordingConn()
        with patch.object(dbconn.psycopg, "connect", return_value=rec):
            dbconn.connect(url="postgresql://x@localhost/jobs", **kw)
        return rec

    def test_sets_search_path_to_the_named_schema(self):
        rec = self._connect(schema="public")
        self.assertIn("SET search_path TO public", rec.statements)

    def test_issues_no_ddl(self):
        """connect() must not demand CREATE on the database.

        Postgres checks the CREATE privilege *before* IF NOT EXISTS can
        short-circuit, so a `CREATE SCHEMA IF NOT EXISTS public` here fails for
        any role that does not own the database -- including jobs_api, which is
        the whole point of it holding no DDL rights. Verified live: it raises
        InsufficientPrivilege even though the schema already exists.
        """
        rec = self._connect(schema="public")
        joined = " ".join(rec.statements).upper()
        self.assertNotIn("CREATE SCHEMA", joined)
        self.assertNotIn("CREATE ", joined)

    def test_no_schema_leaves_search_path_alone(self):
        """Omitting schema= must be completely inert -- no statement, no
        commit. Callers that do not scope a connection must not silently
        acquire one."""
        rec = self._connect()
        self.assertEqual(rec.statements, [])
        self.assertEqual(rec.commits, 0)

    def test_autocommit_skips_the_explicit_commit(self):
        """For callers whose writes must survive independently of the
        enclosing transaction -- see connect()'s docstring."""
        rec = self._connect(schema="public", autocommit=True)
        self.assertIn("SET search_path TO public", rec.statements)
        self.assertEqual(rec.commits, 0)


class TestNoDatabaseUrlDefault(unittest.TestCase):
    """dbconn deliberately has NO DATABASE_URL default.

    The shared library this module came from carried one, and it named a
    DIFFERENT application's database. Applications on this Postgres instance
    are told apart only by the database in DATABASE_URL, and all of them use
    unqualified table names in `public`, so a process falling back to the
    wrong one would not error -- it would create its 14 tables inside
    somebody else's database.
    """

    def test_there_is_no_default_at_all(self):
        self.assertFalse(hasattr(dbconn, "DEFAULT_DATABASE_URL"),
                         "a default came back; see lib/dbconn.py's note")

    def test_unset_raises_instead_of_guessing(self):
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(RuntimeError) as ctx:
                dbconn.database_url()
        self.assertIn("DATABASE_URL is not set", str(ctx.exception))

    def test_the_error_never_names_a_database_to_fall_back_to(self):
        """The whole point is that no plausible-looking URL is offered."""
        with patch.dict(os.environ, {}, clear=True):
            try:
                dbconn.database_url()
            except RuntimeError as e:
                self.assertNotIn("postgresql://", str(e))

    def test_set_value_is_returned_unchanged(self):
        url = "postgresql://u:secret@localhost:5432/jobs"
        with patch.dict(os.environ, {"DATABASE_URL": url}):
            self.assertEqual(dbconn.database_url(), url)

    def test_scrub_url_does_not_raise_when_unset(self):
        """It is what failure paths print, so it must survive the failure."""
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(dbconn.scrub_url(), "<DATABASE_URL not set>")

    def test_scrub_url_drops_the_credential(self):
        scrubbed = dbconn.scrub_url("postgresql://u:secret@localhost:5432/jobs")
        self.assertEqual(scrubbed, "localhost:5432/jobs")
        self.assertNotIn("secret", scrubbed)


if __name__ == "__main__":
    unittest.main()

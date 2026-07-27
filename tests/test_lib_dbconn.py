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
        """Events passes no schema= and must be unaffected by any of this."""
        rec = self._connect()
        self.assertEqual(rec.statements, [])
        self.assertEqual(rec.commits, 0)

    def test_autocommit_skips_the_explicit_commit(self):
        """The geocode cache path -- see connect()'s docstring."""
        rec = self._connect(schema="public", autocommit=True)
        self.assertIn("SET search_path TO public", rec.statements)
        self.assertEqual(rec.commits, 0)


class TestDefaultDatabaseUrl(unittest.TestCase):

    def test_default_carries_no_password(self):
        """What makes falling back inert rather than dangerous."""
        self.assertNotIn(":", dbconn.DEFAULT_DATABASE_URL.split("//")[1].split("@")[0])

    def test_default_is_the_events_database(self):
        """Jobs must never reach its database by fallback, only explicitly."""
        self.assertTrue(dbconn.DEFAULT_DATABASE_URL.endswith("/nyc_events"))

    def test_scrub_url_drops_the_credential(self):
        scrubbed = dbconn.scrub_url("postgresql://u:secret@localhost:5432/jobs")
        self.assertEqual(scrubbed, "localhost:5432/jobs")
        self.assertNotIn("secret", scrubbed)


if __name__ == "__main__":
    unittest.main()

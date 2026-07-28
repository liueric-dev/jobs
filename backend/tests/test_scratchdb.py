"""evals/scratchdb.py, and the two things only a real Postgres can prove.

WHY THESE TESTS NEED A DATABASE AND THE OTHERS DO NOT

`tests/test_upsert_checked.py` covers the per-record error COUNT with a fake
connection, which is right: what varies across its eight call sites is the
TableSpec, not the server. What a fake connection structurally cannot check
is the claim `lib/upsert.py:191-197` makes about Postgres itself --

    "A plain try/except is NOT enough on Postgres: a failed statement aborts
     the whole transaction, so every subsequent record in the batch dies with
     'current transaction is aborted' and one bad row still loses the batch."

_FakeConn keeps going after a raise whether or not the SAVEPOINT exists, so
that suite passes either way. Delete `with conn.transaction():` from
upsert() and only `test_a_bad_row_does_not_take_the_rest_of_the_batch` below
notices. That is the whole argument for a scratch database, and it is audit
items 2 and 3 (`05-fetcher-harness.md:42-43`).

THE OPEN QUESTION, SETTLED

`05-fetcher-harness.md:77-84` asks whether to write concurrency tests for
`lib/upsert.py` and the Google claim SQL now that a scratch database makes
them possible. The answer taken here is **the claim SQL yes, upsert no**, and
the reason is that only one of them has a contract that exists only under
concurrency:

  * `state.try_claim` is *defined* by the concurrent case. Its docstring
    (`lib/state.py:96-99`) says it "guards metered API budgets against two
    overlapping runs spending the same quota twice", and both Google scripts
    lean on it in their scheduling comments. Single-process, it is trivially
    true and proves nothing. If it is wrong, the symptom is a double-spend of
    SerpApi/Apify quota that reports success -- silence, and money, which is
    this pipeline's characteristic failure. Nobody could assert it was right;
    now somebody can. Two tests, below.

  * `lib/upsert.py` has no cross-process contract to test. run-daily.py is
    the single cron entry point and runs the ingest scripts SEQUENTIALLY as
    subprocesses -- stated at `ingest/ats.py:97-102` and again in every other
    script's CONCURRENCY note -- so two upserts racing on one row is not a
    state this system reaches. A test would pin behaviour nothing depends on,
    would be slow and order-dependent, and would have to be maintained by
    people who would reasonably assume it was load-bearing. What actually
    motivated the question is transaction isolation, and that is testable
    without concurrency at all: see the SAVEPOINT tests.

SKIPPED, NOT SILENTLY PASSED, WITHOUT A DATABASE. `scratchdb.available()`
gates every DB test, so a developer with no Postgres sees skips rather than
green.
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import schema                                                 # noqa: E402
from evals import scratchdb                                   # noqa: E402
from lib import envfile, state, upsert                        # noqa: E402
from lib.upsert import upsert_checked                         # noqa: E402

#: The pipeline's own .env, the way run-daily.py loads it. Tests must not
#: depend on the caller having exported anything.
envfile.load(os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), ".env"))

requires_db = unittest.skipUnless(
    scratchdb.available(),
    "no scratch database: set DATABASE_URL (or JOBS_SCRATCH_DATABASE_URL)")


def _record(**overrides):
    """A record satisfying schema.COLUMNS -- same shape as
    tests/test_upsert_checked.py:100, which is the documented contract at
    schema.py:118-120."""
    rec = {c: "" for c in schema.COLUMNS}
    rec.update(platform="greenhouse", company_token="acme",
               company_name="Acme", source_id="1", title="Engineer",
               job_url="http://x", posted_at="2026-07-01",
               location_is_nyc=True, location_is_remote=False,
               company_is_nyc_hq=True, company_is_ai_focused=False,
               posted_at_ts=None)
    rec.update(overrides)
    return rec


class TestTheSchemaIsTheRealSchema(unittest.TestCase):

    @requires_db
    def test_every_table_the_pipeline_names_exists(self):
        """Asserted through schema.py's own constants, not a copied list.

        `09-fetcher-harness.md:55`: make schema creation share the real path
        "rather than a hand-maintained DDL copy, or the harness will silently
        test a schema that no longer exists." A literal list of table names
        here would be exactly that copy, one level up.
        """
        wanted = {schema.TABLE, schema.SCORES_TABLE, schema.FACTS_TABLE,
                  schema.MATCHES_TABLE, schema.EVENTS_TABLE,
                  schema.PROFILES_TABLE, schema.WATERMARK_TABLE,
                  "hn_seen_comments", "google_jobs_query_stats"}
        with scratchdb.scratch_schema() as (conn, name):
            present = {r[0] for r in conn.execute(
                "SELECT table_name FROM information_schema.tables "
                "WHERE table_schema = %s", (name,)).fetchall()}
        self.assertEqual(wanted - present, set())

    @requires_db
    def test_the_search_path_is_the_scratch_schema(self):
        with scratchdb.scratch_schema() as (conn, name):
            self.assertEqual(conn.execute("SHOW search_path").fetchone()[0],
                             name)
            self.assertEqual(
                conn.execute("SELECT count(*) FROM jobs").fetchone()[0], 0,
                "an unqualified query reached a table with rows in it -- the "
                "search_path is not scoped and this is production")

    @requires_db
    def test_the_schema_is_gone_afterwards(self):
        with scratchdb.scratch_schema() as (conn, name):
            pass
        with scratchdb.scratch_schema() as (conn, _other):
            left = conn.execute(
                "SELECT count(*) FROM information_schema.schemata "
                "WHERE schema_name = %s", (name,)).fetchone()[0]
        self.assertEqual(left, 0, f"{name} survived the context manager")

    @requires_db
    def test_two_scratch_schemas_do_not_collide(self):
        with scratchdb.scratch_schema() as (_c1, first):
            with scratchdb.scratch_schema() as (_c2, second):
                self.assertNotEqual(first, second)


class TestTheGuards(unittest.TestCase):
    """No database needed: these are about what this module refuses to do."""

    def test_drop_refuses_anything_not_named_scratch(self):
        for name in ("public", "jobs", "", None, "scratch_", "scratch_XYZ"):
            with self.subTest(schema=name):
                with self.assertRaises(ValueError):
                    scratchdb.drop(_ExplodingConn(), name)

    def test_drop_accepts_a_name_it_could_have_created(self):
        conn = _ExplodingConn(allow=True)
        scratchdb.drop(conn, "scratch_0123abcd")
        self.assertIn("DROP SCHEMA IF EXISTS scratch_0123abcd CASCADE",
                      conn.sql)

    def test_ensure_schema_still_refuses_the_events_database(self):
        """`lib/dbconn.py:19` FOOTGUN 2, kept rather than worked around.

        05-fetcher-harness.md:20-22 calls this refusal "a feature here; keep
        it". A scratch schema pointed at the events database must fail as
        loudly as a production run would, so this asserts the guard fires --
        with a stub connection, because provoking it for real would mean
        creating `public.events` in a live database.
        """
        with self.assertRaises(RuntimeError) as caught:
            schema.ensure_schema(_EventsDatabaseConn())
        self.assertIn("events database", str(caught.exception))


class _ExplodingConn:
    """Fails any statement, unless the test expects one."""

    def __init__(self, allow=False):
        self.allow, self.sql = allow, []

    def execute(self, sql, params=None):
        if not self.allow:
            raise AssertionError(f"should not have executed: {sql}")
        self.sql.append(sql)

    def commit(self):
        pass


class _EventsDatabaseConn:
    """A connection where `to_regclass('public.events')` answers."""

    def execute(self, sql, params=None):
        class _Cur:
            def fetchone(self_inner):
                return ("public.events",)
        return _Cur()


class TestPerRecordIsolationAgainstRealPostgres(unittest.TestCase):
    """Audit items 2 and 3, against a server that actually aborts."""

    @requires_db
    def test_a_bad_row_does_not_take_the_rest_of_the_batch(self):
        """The SAVEPOINT, proved.

        `company_name` is NOT NULL (schema.py:272), so a record carrying None
        fails inside Postgres rather than inside psycopg's parameter
        binding -- which is what makes it abort the surrounding transaction.
        Without upsert()'s per-record `conn.transaction()`, records 3 and 4
        below fail with "current transaction is aborted" and the batch is
        lost. That is the exact defect this pipeline had at eight call sites.
        """
        records = [_record(source_id="0"), _record(source_id="1"),
                   _record(source_id="2", company_name=None),
                   _record(source_id="3"), _record(source_id="4")]
        with scratchdb.scratch_schema() as (conn, _name):
            result = upsert_checked(conn, schema.spec(schema.HASH_FIELDS_ATS),
                                    records, schema.make_job_id,
                                    threshold=1.0, logger=lambda _: None)
            stored = conn.execute(
                "SELECT source_id FROM jobs ORDER BY source_id").fetchall()

        self.assertEqual(len(result.errors), 1, result.errors)
        self.assertEqual([r[0] for r in stored], ["0", "1", "3", "4"],
                         "records after the bad one were lost -- the "
                         "per-record SAVEPOINT is not doing its job")
        self.assertEqual(result.new, 4)

    @requires_db
    def test_the_summary_line_still_reports_the_real_counts(self):
        """Task 03's `upsert-summary:` line, over a real server rather than a
        fake connection -- run-daily.py parses this to tell "wrote nothing"
        apart from "dropped everything"."""
        logged = []
        with scratchdb.scratch_schema() as (conn, _name):
            upsert_checked(conn, schema.spec(schema.HASH_FIELDS_ATS),
                           [_record(source_id="0"),
                            _record(source_id="1", company_name=None)],
                           schema.make_job_id, threshold=1.0,
                           logger=logged.append)
        summary = next(ln for ln in logged
                       if ln.startswith(upsert.SUMMARY_PREFIX))
        self.assertIn("new=1", summary)
        self.assertIn("errors=1", summary)

    @requires_db
    def test_the_three_branches_are_new_then_unchanged_then_updated(self):
        """The whole point of the module, end to end on a real table. A fake
        connection can only answer whatever `existing` it was handed."""
        spec = schema.spec(schema.HASH_FIELDS_ATS)
        with scratchdb.scratch_schema() as (conn, _name):
            first = upsert_checked(conn, spec, [_record()], schema.make_job_id,
                                   logger=lambda _: None)
            again = upsert_checked(conn, spec, [_record()], schema.make_job_id,
                                   logger=lambda _: None)
            changed = upsert_checked(conn, spec, [_record(title="Engineer II")],
                                     schema.make_job_id, logger=lambda _: None)
        self.assertEqual((first.new, first.updated, first.unchanged), (1, 0, 0))
        self.assertEqual((again.new, again.updated, again.unchanged), (0, 0, 1))
        self.assertEqual((changed.new, changed.updated, changed.unchanged),
                         (0, 1, 0))


class TestTheClaimSQLUnderConcurrency(unittest.TestCase):
    """The half of the open question that IS worth testing. See the module
    docstring for why this one and not lib/upsert.py."""

    @requires_db
    def test_only_one_of_two_sessions_wins_a_claim(self):
        """Two overlapping runs must not both pay for the same query.

        `state.try_claim` is an INSERT ... ON CONFLICT DO UPDATE ... WHERE ...
        RETURNING (lib/state.py:111-120). The loser's DO UPDATE re-evaluates
        its WHERE against the row the winner just committed, finds a fresh
        `claimed_at`, updates nothing and returns nothing. That is the
        behaviour the SerpApi and Apify budgets rest on, and until now
        nothing asserted it.
        """
        dataset = "google_jobs:query:ai-engineer-nyc"
        with scratchdb.scratch_schema() as (conn, name):
            with scratchdb.second_connection(name) as other:
                first = state.try_claim(conn, dataset,
                                        table=schema.WATERMARK_TABLE)
                second = state.try_claim(other, dataset,
                                         table=schema.WATERMARK_TABLE)
        self.assertTrue(first)
        self.assertFalse(second, "both sessions took the same claim -- two "
                                 "runs would spend the metered quota twice")

    @requires_db
    def test_a_released_claim_is_takeable_by_the_other_session(self):
        """mark_success drops the claim so nobody waits out the TTL for a
        result that is already known (lib/state.py:133-137)."""
        dataset = "google_jobs:query:ai-engineer-nyc"
        with scratchdb.scratch_schema() as (conn, name):
            with scratchdb.second_connection(name) as other:
                self.assertTrue(state.try_claim(
                    conn, dataset, table=schema.WATERMARK_TABLE))
                self.assertFalse(state.try_claim(
                    other, dataset, table=schema.WATERMARK_TABLE))
                state.mark_success(conn, dataset, "2026-07-28T00:00:00",
                                   table=schema.WATERMARK_TABLE)
                self.assertTrue(state.try_claim(
                    other, dataset, table=schema.WATERMARK_TABLE))
                self.assertEqual(
                    state.get_watermark(other, dataset,
                                        table=schema.WATERMARK_TABLE),
                    "2026-07-28T00:00:00")


if __name__ == "__main__":
    unittest.main()

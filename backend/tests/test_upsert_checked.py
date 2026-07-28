"""upsert_checked: the per-record error count is never discarded again.

WHAT THIS PINS

`lib/upsert.py`'s UpsertResult.__iter__ yields (new, updated, unchanged) and
NOT .errors, so `n, u, unc = upsert(...)` reads naturally and silently threw
away every per-record failure. It did so at eight call sites -- all six ingest
scripts and both API write paths (`docs/ingest/DEFECTS.md` D01). A run that
dropped a hundred records reported success: no alert, no non-zero exit, no log
line, and a corpus quietly smaller than it should be, which looks exactly like
a slow hiring week.

So this file asserts, for the spec each of those eight paths actually writes
through, that a deliberately malformed record

  1. lands in `.errors` rather than vanishing,
  2. is logged even when the count is zero, and
  3. raises UpsertErrorRate once the rate passes the threshold.

WHY THE SPEC AND NOT THE SCRIPT. The scripts cannot be imported (five of six
have hyphens in their filenames) and importing them would buy nothing here:
what varies between the eight paths is the TableSpec and the record shape, and
those are what these tests parametrise over. The fetch and parse halves are
task 09's cassette harness, and these become cassette-backed there.

WHAT COUNTS AS MALFORMED. schema.py:118-120 states the contract these tests
break on purpose: "Every normalize_* function must supply every key here:
upsert binds them as named parameters, so a missing one fails that record". A
record missing a column is therefore not an invented failure -- it is the
documented one, and the one D19's normalization-outside-the-try defect
produces.

No network and no database: _FakeConn below is the same shape as
tests/test_lib_contract.py's _Conn, plus the transaction() and bound-parameter
checking that upsert() needs.
"""

import io
import re
import sys, os
import unittest
from contextlib import redirect_stderr

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import schema  # noqa: E402
from lib import upsert  # noqa: E402
from lib.upsert import (SUMMARY_PREFIX, UpsertErrorRate,  # noqa: E402
                        check_error_rate, upsert_checked)


_BIND = re.compile(r"%\((\w+)\)s")


class _FakeConn:
    """Records SQL, and fails a record whose binds are incomplete.

    Extends tests/test_lib_contract.py's _Conn with the two things upsert()
    needs: transaction(), which the real psycopg implements as a SAVEPOINT so
    one bad record rolls back alone, and a check that every %(name)s in the
    statement has a value. That check is the point -- psycopg raises on a
    missing bind, and reproducing that here is what makes a record with a
    missing column fail the way it fails in production rather than by a
    contrivance.
    """

    def __init__(self, existing=None):
        self.existing = existing
        self.sql = []
        self.params = []
        self.commits = 0

    def execute(self, sql, params=None):
        if isinstance(params, dict):
            for name in _BIND.findall(sql):
                if name not in params:
                    raise KeyError(f"missing bind parameter {name!r}")
        self.sql.append(sql)
        self.params.append(params)
        conn = self

        class _Cur:
            def fetchone(self_inner):
                return conn.existing if sql.startswith("SELECT") else None
        return _Cur()

    def transaction(self):
        class _Tx:
            def __enter__(self_inner):
                return self_inner

            def __exit__(self_inner, *exc):
                return False
        return _Tx()

    def commit(self):
        self.commits += 1


def _record(**overrides):
    """A record satisfying schema.COLUMNS -- the shape every normalize_*
    function is required to produce."""
    rec = {c: "" for c in schema.COLUMNS}
    rec.update(platform="greenhouse", company_token="acme", source_id="1",
               title="Engineer", job_url="http://x", posted_at="2026-07-01")
    rec.update(overrides)
    return rec


def _malformed(**overrides):
    """The documented failure: a record missing a column upsert must bind."""
    rec = _record(**overrides)
    del rec["salary_text"]
    return rec


#: (path, spec) for all eight call sites in D01. Four distinct specs; the
#: paths sharing one share it deliberately -- google_spec() exists precisely so
#: the two Google ingests and the contributor API cannot drift (schema.py:222).
PATHS = [
    ("ingest/ats.py", lambda: schema.spec(schema.HASH_FIELDS_ATS)),
    ("ingest/builtin-nyc.py",
     lambda: schema.spec(schema.HASH_FIELDS_BUILTIN,
                         blank_if_falsy=("salary_text",))),
    ("ingest/weworkremotely.py", lambda: schema.spec(schema.HASH_FIELDS_WWR)),
    ("ingest/hn-hiring.py", lambda: schema.spec(schema.HASH_FIELDS_SHORT)),
    ("ingest/google-serpapi.py", schema.google_spec),
    ("ingest/google-apify.py", schema.google_spec),
    ("api/app.py", schema.google_spec),
    ("api/query_claims.py", schema.google_spec),
]


class TestMalformedRecordPerIngestPath(unittest.TestCase):
    """One malformed record, once per write path, failing loudly."""

    def test_malformed_record_is_counted_not_swallowed(self):
        for path, make_spec in PATHS:
            with self.subTest(path=path):
                conn = _FakeConn()
                logged = []
                result = upsert_checked(
                    conn, make_spec(), [_record(), _malformed(source_id="2")],
                    schema.make_job_id, threshold=1.0, logger=logged.append)

                self.assertEqual(len(result.errors), 1,
                                 f"{path}: malformed record was not counted")
                self.assertEqual(result.new, 1,
                                 f"{path}: the good record was not written")

    def test_raises_once_the_failure_rate_passes_the_threshold(self):
        for path, make_spec in PATHS:
            with self.subTest(path=path):
                conn = _FakeConn()
                records = [_record(source_id=str(i)) for i in range(9)]
                records.append(_malformed(source_id="9"))   # 10% > 5% default

                with self.assertRaises(UpsertErrorRate) as caught:
                    upsert_checked(conn, make_spec(), records,
                                   schema.make_job_id, logger=lambda _: None)

                # The rows that DID write are still reachable: upsert commits
                # before the rate is checked, so a caller that catches this
                # can report and accumulate them.
                self.assertEqual(caught.exception.result.new, 9, path)
                self.assertEqual(len(caught.exception.result.errors), 1, path)

    def test_does_not_raise_below_the_threshold(self):
        """1 in 40 is 2.5%. Under the default it is logged, not fatal --
        otherwise one unusual posting takes down a whole night's ingest."""
        conn = _FakeConn()
        records = [_record(source_id=str(i)) for i in range(39)]
        records.append(_malformed(source_id="39"))
        logged = []

        result = upsert_checked(conn, schema.spec(schema.HASH_FIELDS_ATS),
                                records, schema.make_job_id,
                                logger=logged.append)

        self.assertEqual(len(result.errors), 1)
        self.assertTrue(any("2.5%" in line for line in logged),
                        f"the rate was not logged: {logged}")


class TestTheCountIsAlwaysLogged(unittest.TestCase):
    """The absence of the field must be the anomaly, not its value.

    A count that appears only when it is non-zero is a count nobody notices
    has stopped appearing -- which is how the original defect survived eight
    call sites and eleven audit documents.
    """

    def test_summary_is_logged_when_there_are_no_errors_at_all(self):
        conn = _FakeConn()
        logged = []
        upsert_checked(conn, schema.google_spec(), [_record()],
                       schema.make_job_id, logger=logged.append)

        summaries = [ln for ln in logged if ln.startswith(SUMMARY_PREFIX)]
        self.assertEqual(len(summaries), 1, f"expected one summary: {logged}")
        self.assertIn("errors=0", summaries[0])

    def test_summary_is_logged_for_an_empty_batch(self):
        """Zero records is the shape a blocked scraper produces, and it must
        still say so rather than logging nothing at all."""
        conn = _FakeConn()
        logged = []
        upsert_checked(conn, schema.google_spec(), [], schema.make_job_id,
                       logger=logged.append)

        self.assertTrue(any(ln.startswith(SUMMARY_PREFIX) for ln in logged))
        self.assertNotIn("ZeroDivision", "".join(logged))

    def test_default_logger_writes_to_stderr(self):
        """stdout is this pipeline's alert channel and is deliberately silent
        on a quiet day; the summary must not break that."""
        conn = _FakeConn()
        err = io.StringIO()
        with redirect_stderr(err):
            upsert_checked(conn, schema.google_spec(), [_record()],
                           schema.make_job_id)
        self.assertIn(SUMMARY_PREFIX, err.getvalue())

    def test_summary_line_carries_every_count(self):
        line = upsert.summary_line(
            upsert.UpsertResult(new=3, updated=2, unchanged=7, errors=["x"]),
            "jobs")
        self.assertEqual(
            line,
            f"{SUMMARY_PREFIX} table=jobs new=3 updated=2 unchanged=7 errors=1")


class TestRunLevelCheck(unittest.TestCase):
    """check_error_rate over an accumulated result.

    ats.py and the two Google scripts upsert inside a per-source loop, where
    one small source failing entirely is survivable -- it is recorded the way
    an unreachable source already is -- but the same failures spread across
    the whole run are not. That needs the rule applied at both scopes.
    """

    def test_batches_that_each_pass_can_fail_as_a_run(self):
        # Three batches of 1-in-10: each is 10%, and so is the total. The
        # point is that the total is checked at all -- before this, a loop
        # could drop a third of every source and exit zero.
        total = upsert.UpsertResult()
        for _ in range(3):
            total += upsert.UpsertResult(new=9, errors=["boom"])

        with self.assertRaises(UpsertErrorRate):
            check_error_rate(total, label="jobs", logger=lambda _: None)

    def test_clean_run_returns_the_result_unchanged(self):
        total = upsert.UpsertResult(new=5, updated=1, unchanged=2)
        self.assertIs(check_error_rate(total, logger=lambda _: None), total)

    def test_empty_result_does_not_divide_by_zero(self):
        empty = upsert.UpsertResult()
        self.assertIs(check_error_rate(empty, logger=lambda _: None), empty)


class TestRunDailySummaryParser(unittest.TestCase):
    """run-daily.py must distinguish "wrote nothing" from "dropped
    everything". Both used to print as a clean success."""

    def setUp(self):
        import importlib.util
        path = os.path.join(os.path.dirname(os.path.dirname(
            os.path.abspath(__file__))), "run-daily.py")
        spec = importlib.util.spec_from_file_location("run_daily", path)
        self.run_daily = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.run_daily)

    def test_wrote_nothing_and_dropped_everything_are_different(self):
        quiet = self.run_daily.parse_upsert_summaries(
            f"{SUMMARY_PREFIX} table=jobs new=0 updated=0 unchanged=400 errors=0")
        dropped = self.run_daily.parse_upsert_summaries(
            f"{SUMMARY_PREFIX} table=jobs new=0 updated=0 unchanged=0 errors=400")

        self.assertEqual(quiet, (0, 0))
        self.assertEqual(dropped, (0, 400))
        self.assertNotEqual(quiet, dropped)

    def test_counts_are_summed_across_a_per_source_loop(self):
        out = "\n".join([
            f"{SUMMARY_PREFIX} table=jobs new=3 updated=1 unchanged=9 errors=2",
            "[debug] something unrelated",
            f"{SUMMARY_PREFIX} table=jobs new=5 updated=0 unchanged=1 errors=0",
        ])
        self.assertEqual(self.run_daily.parse_upsert_summaries(out), (9, 2))

    def test_a_step_that_never_upserts_is_not_reported_as_zero(self):
        """extract/match/score write no rows through upsert. Reporting them as
        0/0 would be indistinguishable from an ingest step that wrote nothing,
        which is the exact confusion this summary exists to remove."""
        self.assertEqual(
            self.run_daily.parse_upsert_summaries("match: 412 rows scored"),
            (None, None))


if __name__ == "__main__":
    unittest.main()

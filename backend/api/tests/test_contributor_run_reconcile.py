"""T-38 / docs/adr/0009: a contributor's run stops the query being due again.

THE SEQUENCE THIS FILE IS ABOUT, END TO END
    claim a `search_queries` row -> the contributor spends a SerpApi credit ->
    submit -> release the claim -> the pipeline's next cycle reconciles ->
    due_queries() no longer returns it. Before 0009 the last step did not
    exist, so the release handed the row straight back to the pool with
    last_run_at untouched and the next cycle spent somebody else's credit on a
    search that had already happened.

WHY IT IS HERE AND NOT IN ../../tests/
    It spans the boundary: the claim and the log row are this service's,
    reconcile_contributor_runs() and due_queries() are the pipeline's. This
    side is the one that can reach both -- api/ already imports schema and
    google_jobs, while .claude/CLAUDE.md's layout rule forbids the reverse --
    and `submission_log` exists only where qc.ensure_schema() has run, which
    is what api_scratch_schema() below provides and a bare pipeline scratch
    schema does not.

AGAINST REAL SQL, FOR test_search_query_claims.py's REASON
    `tests/fakedb.py` dispatches on SQL text, so every assertion here would
    pass against it whether or not the statements do anything. What is under
    test is a watermark comparison, an UPDATE's arithmetic and a CASE
    expression -- all SQL semantics -- so this uses a scratch schema created on
    the PIPELINE's credential, exactly as that file does.

ONE CLOCK, NOT TWO
    Every timestamp below derives from NOW, including the ones written into
    submission_log and the one due_queries() is asked about. Two tests in this
    repo rotted by pairing a real-clock timestamp with a frozen one and passed
    only inside a window; nothing here reads the wall clock, so nothing here
    can. reconcile_contributor_runs() takes no `now` at all for the same
    reason -- it writes the log row's own submitted_at.

THE STEP THAT MAKES THE OTHERS MEAN SOMETHING
    test_the_row_is_still_due_after_a_release asserts the DEFECT, not the fix:
    it fails if a release alone somehow leaves the row not-due. Without it
    every "not due after reconcile" assertion below would also pass against a
    query that was never due in the first place.
"""

import contextlib
import os
import sys
import unittest
from datetime import UTC, datetime, timedelta

API_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BACKEND_DIR = os.path.dirname(API_DIR)
sys.path.insert(0, API_DIR)
sys.path.insert(0, BACKEND_DIR)

import query_claims as qc  # noqa: E402

import searchqueries  # noqa: E402
from evals import scratchdb  # noqa: E402
from lib import envfile  # noqa: E402

_BACKEND_ENV = os.path.join(BACKEND_DIR, ".env")


def _pipeline_url():
    try:
        with open(_BACKEND_ENV) as fh:
            return envfile.parse(fh.read()).get("DATABASE_URL")
    except OSError:
        return None


if "JOBS_SCRATCH_DATABASE_URL" not in os.environ:
    _url = _pipeline_url()
    if _url:
        os.environ["JOBS_SCRATCH_DATABASE_URL"] = _url

requires_db = unittest.skipUnless(
    scratchdb.available(),
    "no scratch database: set JOBS_SCRATCH_DATABASE_URL to a role with CREATE")

CONTRIBUTOR = "c_alpha"

#: The one moment everything here is measured from. See ONE CLOCK above.
NOW = datetime(2026, 8, 2, 12, 0, 0, tzinfo=UTC)


def stamp(dt):
    return dt.strftime("%Y-%m-%dT%H:%M:%S")


@contextlib.contextmanager
def api_scratch_schema():
    """A scratch schema with the pipeline's tables AND this service's.

    The same helper test_search_query_claims.py defines, and deliberately not
    imported from it for that file's stated reason: sibling modules under
    `unittest discover` are not a package, so importing one would depend on
    the discovery root rather than on sys.path.
    """
    with scratchdb.scratch_schema() as (conn, name):
        qc.ensure_schema(conn)
        yield conn, name


def register(conn, text, source="seeded", location="new york"):
    """One `search_queries` row, never run.

    SOURCE DEFAULTS TO `seeded`, NOT `builder`, AND THAT IS THE TEST WORKING.
    is_due() says an unwatched `builder` query that has already run is not due
    REGARDLESS of its run statistics (searchnorm.py:235), so a builder row
    would go not-due after the reconcile whether or not the reconcile wrote
    anything -- the assertion would pass for the wrong reason. `seeded` is in
    UNDECAYABLE_SOURCES, so the only thing that can make it not-due is the
    cadence, which is the thing under test.
    """
    return conn.execute(
        """
        INSERT INTO search_queries
            (normalized_text, normalized_location, display_text,
             display_location, source, first_requested_at)
        VALUES (%s, %s, %s, %s, %s, %s)
        RETURNING id
        """,
        (text, location, text, location, source, stamp(NOW - timedelta(days=1))),
    ).fetchone()[0]


def log_run(conn, query_id, submitted_at, accepted=3):
    """The submission_log row the dispatch endpoint docs/adr/0007 owes will
    write, on the branch mark_success sits on in the other claim mode.

    HAND-BUILT `submitted_at` RATHER THAN log_submission()'s OWN, and this is
    the one place that matters: log_submission stamps utc_now_str() itself, so
    routing through it would put a real-clock timestamp beside this module's
    frozen NOW -- the exact pairing that rotted two tests in this repo. The
    column list is otherwise log_submission's, and a test below asserts the
    two have not drifted apart.
    """
    conn.execute(
        """
        INSERT INTO submission_log (contributor_id, dataset, submitted_at,
            fetched_count, accepted_count, rejected_count, reason, action)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        """,
        (CONTRIBUTOR, searchqueries.dataset_for_query(query_id), submitted_at,
         accepted, accepted, 0, None, searchqueries.CONTRIBUTOR_RUN_ACTION),
    )
    conn.commit()


def stats(conn, query_id):
    cols = ", ".join(searchqueries.RUN_STATISTICS)
    row = conn.execute(
        f"SELECT {cols} FROM search_queries WHERE id = %s",
        (query_id,)).fetchone()
    # strict=True is an assertion, not decoration: it fails if the SELECT ever
    # returns a different number of columns than RUN_STATISTICS names, which is
    # how every lookup below would silently start reading the wrong column.
    return dict(zip(searchqueries.RUN_STATISTICS, row, strict=True))


def due_ids(conn, now=NOW):
    return [q["id"] for q in searchqueries.due_queries(conn, now=stamp(now))]


@requires_db
class TestTheDefectAndTheFix(unittest.TestCase):
    """The row's own "Done when", in order."""

    def test_the_row_is_still_due_after_a_release(self):
        """THE DEFECT, asserted rather than described.

        This is what T-38 reported and what every assertion below stands on.
        If a release ever starts leaving the row not-due on its own, this goes
        red and the rest of this file stops meaning anything -- which is the
        point of asserting it.
        """
        with api_scratch_schema() as (conn, _):
            qid = register(conn, "ai engineer")
            self.assertIn(qid, due_ids(conn))

            self.assertTrue(qc.try_claim_search_query(
                conn, qid, NOW - timedelta(minutes=5), CONTRIBUTOR))
            log_run(conn, qid, stamp(NOW - timedelta(hours=1)))
            qc.release_search_query_claim(conn, qid)

            self.assertIn(qid, due_ids(conn),
                          "a release alone must not make the row not-due -- "
                          "nothing has recorded that it ran")
            self.assertIsNone(stats(conn, qid)["last_run_at"])

    def test_reconciling_makes_it_not_due(self):
        """The fix, and the row's first Done-when clause verbatim."""
        with api_scratch_schema() as (conn, _):
            qid = register(conn, "ai engineer")
            qc.try_claim_search_query(
                conn, qid, NOW - timedelta(minutes=5), CONTRIBUTOR)
            log_run(conn, qid, stamp(NOW - timedelta(hours=1)))
            qc.release_search_query_claim(conn, qid)

            self.assertEqual(
                searchqueries.reconcile_contributor_runs(conn), (1, 0, True))
            self.assertNotIn(qid, due_ids(conn))

    def test_every_run_statistic_is_advanced_and_none_is_invented(self):
        """The second half of that clause: a test that fails if the run
        statistics are left untouched -- each of the five, by name."""
        with api_scratch_schema() as (conn, _):
            qid = register(conn, "ai engineer")
            submitted = stamp(NOW - timedelta(hours=1))
            log_run(conn, qid, submitted, accepted=7)
            searchqueries.reconcile_contributor_runs(conn)

            s = stats(conn, qid)
            self.assertEqual(s["last_run_at"], submitted,
                             "last_run_at must be the log row's own timestamp, "
                             "not this process's clock")
            self.assertEqual(s["run_count"], 1)
            self.assertEqual(s["provider_last_used"],
                             searchqueries.CONTRIBUTOR_PROVIDER)
            self.assertEqual(s["result_count_last_run"], 7)
            self.assertEqual(s["last_result_at"], submitted)

    def test_a_run_that_found_nothing_advances_the_cadence_and_not_the_decay(self):
        """record_run's rule, reached through the reconciler rather than
        restated by it -- which is the property that makes record_run still the
        only writer. If the reconciler ever grew its own UPDATE, this is the
        assertion that would notice the CASE expression had been dropped."""
        with api_scratch_schema() as (conn, _):
            qid = register(conn, "ai engineer")
            submitted = stamp(NOW - timedelta(hours=1))
            log_run(conn, qid, submitted, accepted=0)
            searchqueries.reconcile_contributor_runs(conn)

            s = stats(conn, qid)
            self.assertEqual(s["last_run_at"], submitted)
            self.assertEqual(s["result_count_last_run"], 0)
            self.assertIsNone(s["last_result_at"],
                              "an empty run must leave the decay clock ticking")


@requires_db
class TestItCannotDoubleCount(unittest.TestCase):
    """Idempotence with no watermark table: the whole argument for comparing
    against last_run_at rather than storing a cursor."""

    def test_a_second_reconcile_changes_nothing(self):
        with api_scratch_schema() as (conn, _):
            qid = register(conn, "ai engineer")
            log_run(conn, qid, stamp(NOW - timedelta(hours=1)))

            self.assertEqual(
                searchqueries.reconcile_contributor_runs(conn), (1, 0, True))
            self.assertEqual(
                searchqueries.reconcile_contributor_runs(conn), (0, 1, True))
            self.assertEqual(stats(conn, qid)["run_count"], 1)

    def test_two_runs_since_the_last_cycle_are_two_runs(self):
        """The opposite failure, and why the comparison is per-row rather than
        a single pre-loop predicate: a contributor who claimed the same query
        twice in a day did the work twice and spent two credits."""
        with api_scratch_schema() as (conn, _):
            qid = register(conn, "ai engineer")
            log_run(conn, qid, stamp(NOW - timedelta(hours=5)), accepted=2)
            log_run(conn, qid, stamp(NOW - timedelta(hours=1)), accepted=4)

            self.assertEqual(
                searchqueries.reconcile_contributor_runs(conn), (2, 0, True))
            s = stats(conn, qid)
            self.assertEqual(s["run_count"], 2)
            self.assertEqual(s["last_run_at"], stamp(NOW - timedelta(hours=1)),
                             "the LATEST run must win, whatever order the rows "
                             "came back in")
            self.assertEqual(s["result_count_last_run"], 4)

    def test_a_run_older_than_the_watermark_is_skipped(self):
        """The pipeline ran the query itself after the contributor submitted.
        Rewinding last_run_at would make it due again and spend a credit."""
        with api_scratch_schema() as (conn, _):
            qid = register(conn, "ai engineer")
            log_run(conn, qid, stamp(NOW - timedelta(hours=9)))
            searchqueries.record_run(conn, qid, "serpapi", 5,
                                     now=stamp(NOW - timedelta(hours=2)))

            self.assertEqual(
                searchqueries.reconcile_contributor_runs(conn), (0, 1, True))
            s = stats(conn, qid)
            self.assertEqual(s["last_run_at"], stamp(NOW - timedelta(hours=2)))
            self.assertEqual(s["run_count"], 1)
            self.assertEqual(s["provider_last_used"], "serpapi")


@requires_db
class TestWhatItRefusesToReconcile(unittest.TestCase):
    """Every other row in submission_log, which is a busy table."""

    def test_a_submit_row_is_not_a_run(self):
        """DEFECT D08, ONE TABLE OVER, AND THE REASON FOR A FOURTH ACTION.
        app.py writes a `submit` row on the success path and on both refusal
        paths. Treating one as a run would mark a query covered on the strength
        of a submission the endpoint rejected -- which is exactly what D08 was:
        an empty submission advancing a watermark.
        """
        with api_scratch_schema() as (conn, _):
            qid = register(conn, "ai engineer")
            qc.log_submission(conn, "submit", CONTRIBUTOR,
                              searchqueries.dataset_for_query(qid),
                              reason="empty submission")
            conn.commit()

            self.assertEqual(
                searchqueries.reconcile_contributor_runs(conn), (0, 0, True))
            self.assertIn(qid, due_ids(conn))

    def test_the_other_claim_modes_datasets_are_untouched(self):
        """job_ingest_state's rows carry `google_jobs:query:<slug>` in the same
        column. mark_success owns those; this must not read them."""
        with api_scratch_schema() as (conn, _):
            qid = register(conn, "ai engineer")
            conn.execute(
                """
                INSERT INTO submission_log (contributor_id, dataset,
                    submitted_at, fetched_count, accepted_count,
                    rejected_count, reason, action)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (CONTRIBUTOR, "google_jobs:query:ai-eng",
                 stamp(NOW - timedelta(hours=1)), 3, 3, 0, None,
                 searchqueries.CONTRIBUTOR_RUN_ACTION))
            conn.commit()

            self.assertEqual(
                searchqueries.reconcile_contributor_runs(conn), (0, 0, True))
            self.assertIsNone(stats(conn, qid)["last_run_at"])

    def test_a_run_row_naming_a_query_that_is_gone_is_skipped_not_raised(self):
        """submission_log is an audit trail and outlives what it names."""
        with api_scratch_schema() as (conn, _):
            log_run(conn, 999999, stamp(NOW - timedelta(hours=1)))
            self.assertEqual(
                searchqueries.reconcile_contributor_runs(conn), (0, 1, True))

    def test_an_unparseable_dataset_is_skipped_not_raised(self):
        with api_scratch_schema() as (conn, _):
            conn.execute(
                """
                INSERT INTO submission_log (contributor_id, dataset,
                    submitted_at, fetched_count, accepted_count,
                    rejected_count, reason, action)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (CONTRIBUTOR, "search_query:not-a-number",
                 stamp(NOW - timedelta(hours=1)), 0, 0, 0, None,
                 searchqueries.CONTRIBUTOR_RUN_ACTION))
            conn.commit()
            self.assertEqual(
                searchqueries.reconcile_contributor_runs(conn), (0, 1, True))


@requires_db
class TestTheMissingTableIsReportedAndNotSwallowed(unittest.TestCase):
    """A database provisioned before T-39 has no submission_log. The pipeline
    must still run, and must not report the same thing as a quiet night."""

    def test_absent_submission_log_reports_false_rather_than_raising(self):
        with scratchdb.scratch_schema() as (conn, _):
            # NOT api_scratch_schema: qc.ensure_schema is exactly what is
            # missing here, which is the state being reproduced.
            self.assertEqual(
                searchqueries.reconcile_contributor_runs(conn), (0, 0, False))


@requires_db
class TestTheTestsOwnWriterMatchesTheRealOne(unittest.TestCase):
    """log_run() hand-writes the INSERT so it can freeze the clock. That is a
    second column list, and a second column list is a thing that drifts."""

    def test_log_submission_writes_a_row_this_reconciler_would_read(self):
        """The real writer, with its own clock, reconciled for real. This is
        what says log_run()'s hand-built row is not a fiction: if
        log_submission's columns or its action check ever stopped matching,
        this fails while log_run() sailed on."""
        with api_scratch_schema() as (conn, _):
            qid = register(conn, "ai engineer")
            qc.log_submission(conn, searchqueries.CONTRIBUTOR_RUN_ACTION,
                              CONTRIBUTOR, searchqueries.dataset_for_query(qid),
                              fetched_count=4, accepted_count=4)
            conn.commit()

            reconciled, _, present = searchqueries.reconcile_contributor_runs(conn)
            self.assertTrue(present)
            self.assertEqual(reconciled, 1)
            s = stats(conn, qid)
            self.assertEqual(s["run_count"], 1)
            self.assertEqual(s["result_count_last_run"], 4)
            self.assertIsNotNone(s["last_run_at"])

    def test_the_run_action_passes_log_submissions_closed_vocabulary(self):
        """log_submission raises on an unknown action, so the fourth entry
        being absent from SUBMISSION_ACTIONS would break the writer rather than
        the reader -- a different failure, and a loud one."""
        self.assertIn(searchqueries.CONTRIBUTOR_RUN_ACTION,
                      qc.SUBMISSION_ACTIONS)


if __name__ == "__main__":
    unittest.main()

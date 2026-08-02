"""The submission_log report -- task 24's "empty-submission workers detectable".

TWO HALVES, AND THE SPLIT IS THE SAME ONE THE REST OF THIS SUITE DRAWS.
The bucket arithmetic, the findings and the formatting are pure functions over
dicts, so they are tested as such and run everywhere. The five COUNT(*) FILTER
expressions are SQL, and the claim that matters about them -- that they
PARTITION the table, so no row is silently dropped from somebody's totals -- is
a claim only a server can settle. Those run against a scratch schema and skip
where no database is available, exactly as tests/test_claim_protocol.py does
and for the same reason.

THE PROPERTY WORTH THE MOST HERE IS THE ONE ABOUT NULL. `submission_log.action`
is nullable with no default and query_claims.py says what a NULL means:
"written before this column existed". Every test below that touches it checks
the same thing from a different side -- that an unknown is carried as an
unknown, is never counted as a claim or a submit or a zero, and never earns a
contributor a finding. A report that guessed would be worse than no report:
"this worker submits nothing" about a worker whose rows simply predate the
column is a false accusation that reads exactly like a true one.
"""

import contextlib
import os
import sys
import unittest
from datetime import datetime, timezone

API_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BACKEND_DIR = os.path.dirname(API_DIR)
sys.path.insert(0, API_DIR)
sys.path.insert(0, BACKEND_DIR)

import contribution_report as report                  # noqa: E402
import query_claims as qc                             # noqa: E402
from evals import scratchdb                           # noqa: E402
from lib import envfile                               # noqa: E402

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

A = "c_alpha"
B = "c_beta"
D0 = "google_jobs:query:s0"
D1 = "google_jobs:query:s1"


def record(**overrides):
    """A summarized row with every bucket at zero, then whatever is asked for."""
    base = {"contributor_id": A, "name": "Alpha", "rows_total": 0, "claims": 0,
            "submits": 0, "empty_submits": 0, "releases": 0,
            "unknown_action": 0, "other_action": 0, "fetched": 0,
            "accepted": 0, "first_at": None, "last_at": None}
    base.update(overrides)
    base["rows_total"] = sum(base[bucket] for bucket in report.BUCKETS)
    return report.summarize(base)


class TestTheBucketsReconcile(unittest.TestCase):

    def test_a_row_in_no_bucket_is_a_loud_failure(self):
        # THE ASSERTION THIS REPORT IS BUILT AROUND. A future vocabulary entry
        # that gets a FILTER in the SQL and no entry in BUCKETS would otherwise
        # under-count somebody's work with nothing to notice it.
        broken = {"claims": 1, "submits": 0, "releases": 0, "unknown_action": 0,
                  "other_action": 0, "rows_total": 2}
        with self.assertRaises(ValueError) as caught:
            report.summarize(broken)
        self.assertIn("do not reconcile", str(caught.exception))

    def test_the_five_buckets_are_the_five_the_sql_computes(self):
        # BUCKETS drives the reconciliation, so a name that drifts from the SQL
        # would silently disable it by summing a KeyError-free subset.
        for bucket in report.BUCKETS:
            self.assertIn(f"AS {bucket}", report._BUCKET_SQL)

    def test_the_vocabulary_the_sql_excludes_is_the_one_in_code(self):
        # `other_action` is defined as "not NULL and not in the vocabulary",
        # and the vocabulary is passed as a parameter rather than written into
        # the SQL, so adding an action to qc.SUBMISSION_ACTIONS moves rows out
        # of `other` and into a named bucket without an edit here.
        self.assertIn("action = ANY(%s)", report._BUCKET_SQL)


class TestNullIsNeverCollapsed(unittest.TestCase):

    def test_a_null_row_counts_as_no_action_at_all(self):
        row = record(unknown_action=4)
        self.assertEqual(row["claims"], 0)
        self.assertEqual(row["submits"], 0)
        self.assertEqual(row["releases"], 0)
        self.assertEqual(row["unknown_action"], 4)

    def test_a_contributor_with_only_null_rows_earns_no_finding(self):
        # The false accusation this report must not make. Four rows of evidence
        # that cannot be classified is not evidence of a broken worker.
        rows = report.apply_findings([record(unknown_action=40)])
        self.assertEqual(rows[0]["finding"], "")

    def test_an_empty_rate_over_no_submits_is_none_not_zero(self):
        # None and 0.0 are different answers: one is "none of their submits
        # were empty", the other is "they have not submitted". Collapsing them
        # would rank a worker who has never run as healthier than one who has.
        self.assertIsNone(record(claims=3)["empty_rate"])
        self.assertEqual(record(submits=2, empty_submits=0)["empty_rate"], 0.0)

    def test_the_null_column_prints_a_word_not_a_blank(self):
        table = report.format_table([record(unknown_action=2)],
                                    "contributor_id", "contributor",
                                    (("name", "name"),))
        self.assertIn(report.NULL_LABEL, table)

    def test_an_absent_rate_prints_a_dash(self):
        table = report.format_table([record(claims=1)], "contributor_id",
                                    "contributor", (("name", "name"),))
        self.assertIn("-", table)
        self.assertNotIn("0%", table)

    def test_the_totals_line_names_the_null_rows_when_there_are_any(self):
        self.assertIn("NULL action",
                      report.totals_line([record(unknown_action=3)]))

    def test_the_totals_line_stays_quiet_when_there_are_none(self):
        # A caveat printed on every run is a caveat nobody reads.
        self.assertNotIn("NULL action",
                         report.totals_line([record(claims=1, submits=1)]))

    def test_an_out_of_vocabulary_action_is_called_out(self):
        # `action` is free TEXT because a CHECK would need DDL rights this
        # service does not hold, so a value outside the set is representable and
        # is its own finding about whatever wrote it.
        line = report.totals_line([record(other_action=2)])
        self.assertIn("outside", line)


class TestTheFindings(unittest.TestCase):

    def test_a_worker_whose_submits_are_mostly_empty_is_flagged(self):
        rows = report.apply_findings([record(claims=10, submits=8,
                                             empty_submits=7)])
        self.assertEqual(rows[0]["finding"], report.FINDING_EMPTY_SUBMITS)

    def test_a_worker_that_claims_and_never_submits_is_flagged_separately(self):
        # The half an empty-submit rate cannot see: this worker writes no
        # submit row of any kind, so its empty rate is undefined -- and each of
        # those claims held a query out of the pool for CLAIM_TTL_MINUTES.
        rows = report.apply_findings([record(claims=10)])
        self.assertEqual(rows[0]["finding"], report.FINDING_NO_SUBMITS)

    def test_a_healthy_worker_is_flagged_as_nothing(self):
        rows = report.apply_findings([record(claims=10, submits=10,
                                             empty_submits=1, fetched=93,
                                             accepted=90)])
        self.assertEqual(rows[0]["finding"], "")

    def test_one_empty_submit_out_of_one_is_not_a_finding(self):
        # 100% of a sample of one. The threshold exists so this is arguable
        # rather than asserted, which is why it is a flag.
        rows = report.apply_findings([record(claims=1, submits=1,
                                             empty_submits=1)])
        self.assertEqual(rows[0]["finding"], "")

    def test_the_thresholds_are_arguments_and_actually_move(self):
        # A lens, not a policy: nothing acts on these, and a reader who
        # disagrees changes what they are shown and nothing else.
        row = record(claims=2, submits=2, empty_submits=1)
        self.assertEqual(report.apply_findings([row])[0]["finding"], "")
        self.assertEqual(
            report.apply_findings([row], min_submits=2, empty_rate=0.5)[0]
            ["finding"], report.FINDING_EMPTY_SUBMITS)

    def test_findings_are_recomputed_not_accumulated(self):
        # apply_findings mutates in place and is called once per run, but a
        # second call with looser thresholds must be able to clear a label.
        row = record(claims=10, submits=10, empty_submits=10)
        report.apply_findings([row])
        self.assertEqual(row["finding"], report.FINDING_EMPTY_SUBMITS)
        report.apply_findings([row], empty_rate=1.5)
        self.assertEqual(row["finding"], "")


class TestTheSinceBound(unittest.TestCase):

    def test_a_date_and_a_timestamp_are_both_accepted(self):
        for value in ("2026-08-01", "2026-08-01T12:00:00"):
            clause, params = report._since_clause(value)
            self.assertIn("submitted_at >= %s", clause)
            self.assertEqual(params, [value])

    def test_no_bound_adds_no_clause(self):
        self.assertEqual(report._since_clause(None), ("", []))

    def test_a_mistyped_bound_is_refused_rather_than_matching_nothing(self):
        # submitted_at is TEXT, so `>= 'yesterday'` is a valid comparison that
        # matches every row, and `>= '08/01/2026'` one that matches none.
        # Either would report a number confidently and wrongly.
        for value in ("yesterday", "08/01/2026", "2026-8-1", "2026-08-01 12:00"):
            with self.subTest(value):
                with self.assertRaises(ValueError):
                    report._since_clause(value)


@contextlib.contextmanager
def report_scratch_schema():
    """The same fixture test_claim_protocol.py uses -- see its docstring."""
    with scratchdb.scratch_schema() as (conn, name):
        qc.ensure_schema(conn)
        yield conn, name


def log_raw(conn, contributor_id, dataset, action, submitted_at,
            fetched=0, accepted=0, rejected=0, reason=None):
    """A submission_log row written around log_submission's vocabulary check.

    Needed for exactly the two rows log_submission refuses to write and the
    database can nonetheless hold: a NULL action, and an action outside the
    vocabulary. Those are the rows the report exists to represent honestly, so
    a test that could not create them could not check the representation.
    """
    conn.execute(
        "INSERT INTO submission_log (contributor_id, dataset, submitted_at, "
        "fetched_count, accepted_count, rejected_count, reason, action) "
        "VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
        (contributor_id, dataset, submitted_at, fetched, accepted, rejected,
         reason, action))
    conn.commit()


def by_id(records):
    return {r["contributor_id"]: r for r in records}


@requires_db
class TestTheBucketsAgainstPostgres(unittest.TestCase):

    def test_each_action_lands_in_its_own_bucket(self):
        with report_scratch_schema() as (conn, _):
            qc.log_submission(conn, "claim", A, D0)
            qc.log_submission(conn, "submit", A, D0, fetched_count=9,
                              accepted_count=9)
            qc.log_submission(conn, "release", A, D1, reason="serpapi 429")
            conn.commit()
            row = by_id(report.fetch_contributors(conn))[A]
            self.assertEqual((row["claims"], row["submits"], row["releases"]),
                             (1, 1, 1))
            self.assertEqual(row["rows_total"], 3)

    def test_an_empty_submit_is_the_row_app_submit_actually_writes(self):
        # Not a hand-built row: this is exactly the call in app.submit's D08
        # short-circuit, with every count left at its default. The report keys
        # on fetched_count = 0 rather than on `reason`, and this is what makes
        # that keying checkable rather than asserted.
        with report_scratch_schema() as (conn, _):
            qc.log_submission(conn, "submit", A, D0,
                              reason="empty submission -- watermark not advanced")
            qc.log_submission(conn, "submit", A, D1, fetched_count=7,
                              accepted_count=7)
            conn.commit()
            row = by_id(report.fetch_contributors(conn))[A]
            self.assertEqual(row["submits"], 2)
            self.assertEqual(row["empty_submits"], 1)
            self.assertEqual(row["empty_rate"], 0.5)

    def test_a_null_action_row_lands_in_unknown_and_nowhere_else(self):
        with report_scratch_schema() as (conn, _):
            log_raw(conn, A, D0, None, "2026-08-02T09:00:00")
            row = by_id(report.fetch_contributors(conn))[A]
            self.assertEqual(row["unknown_action"], 1)
            self.assertEqual(row["claims"], 0)
            self.assertEqual(row["submits"], 0)
            self.assertEqual(row["releases"], 0)
            self.assertEqual(row["other_action"], 0)
            self.assertEqual(row["rows_total"], 1)

    def test_a_null_action_row_with_a_zero_count_is_not_an_empty_submit(self):
        # The collapse that would be easiest to write and hardest to see: a
        # pre-column row has fetched_count 0 like an empty submit does, and
        # keying on the count alone would turn every legacy row into evidence
        # of a broken worker.
        with report_scratch_schema() as (conn, _):
            log_raw(conn, A, D0, None, "2026-08-02T09:00:00", fetched=0)
            row = by_id(report.fetch_contributors(conn))[A]
            self.assertEqual(row["empty_submits"], 0)
            self.assertIsNone(row["empty_rate"])
            self.assertEqual(report.apply_findings([row])[0]["finding"], "")

    def test_an_action_outside_the_vocabulary_lands_in_other(self):
        with report_scratch_schema() as (conn, _):
            log_raw(conn, A, D0, "submitted", "2026-08-02T09:00:00")
            row = by_id(report.fetch_contributors(conn))[A]
            self.assertEqual(row["other_action"], 1)
            self.assertEqual(row["unknown_action"], 0)
            self.assertEqual(row["submits"], 0)

    def test_every_row_lands_in_exactly_one_bucket(self):
        # The partition, end to end, with all five kinds present at once.
        # summarize() raises if the five do not add to COUNT(*), so reaching
        # this assertion is most of the claim.
        with report_scratch_schema() as (conn, _):
            qc.log_submission(conn, "claim", A, D0)
            qc.log_submission(conn, "submit", A, D0, fetched_count=3)
            qc.log_submission(conn, "release", A, D1)
            conn.commit()
            log_raw(conn, A, D1, None, "2026-08-02T09:00:00")
            log_raw(conn, A, D1, "weird", "2026-08-02T09:01:00")
            row = by_id(report.fetch_contributors(conn))[A]
            self.assertEqual(row["rows_total"], 5)
            self.assertEqual(
                sum(row[bucket] for bucket in report.BUCKETS), 5)

    def test_the_totals_are_over_submits_only(self):
        # fetched and accepted are summed FILTERed on submit, so a claim row's
        # zeroes cannot dilute them and a release row's cannot either.
        with report_scratch_schema() as (conn, _):
            qc.log_submission(conn, "claim", A, D0)
            qc.log_submission(conn, "submit", A, D0, fetched_count=10,
                              accepted_count=8, rejected_count=2)
            conn.commit()
            row = by_id(report.fetch_contributors(conn))[A]
            self.assertEqual((row["fetched"], row["accepted"]), (10, 8))


@requires_db
class TestTheViews(unittest.TestCase):

    def test_the_since_bound_excludes_older_rows(self):
        with report_scratch_schema() as (conn, _):
            log_raw(conn, A, D0, "claim", "2026-07-31T23:59:59")
            log_raw(conn, A, D0, "claim", "2026-08-01T00:00:00")
            self.assertEqual(
                by_id(report.fetch_contributors(conn))[A]["claims"], 2)
            self.assertEqual(
                by_id(report.fetch_contributors(conn, "2026-08-01"))[A]["claims"],
                1)

    def test_a_contributor_with_no_row_in_contributors_still_reports(self):
        # contributor_id is plain TEXT with no foreign key, so this is
        # representable -- and it is the shape a leaked or hand-crafted key
        # would take, which makes it the last row that should be dropped.
        with report_scratch_schema() as (conn, _):
            log_raw(conn, "c_ghost", D0, "claim", "2026-08-02T09:00:00")
            row = by_id(report.fetch_contributors(conn))["c_ghost"]
            self.assertIsNone(row["name"])
            table = report.format_table([row], "contributor_id", "contributor",
                                        (("name", "name"),))
            self.assertIn("c_ghost", table)

    def test_the_name_is_joined_when_there_is_one(self):
        with report_scratch_schema() as (conn, _):
            conn.execute(
                "INSERT INTO contributors (id, name, created_at) "
                "VALUES (%s, %s, %s)", (A, "Alpha Builder", "2026-08-01T00:00:00"))
            log_raw(conn, A, D0, "claim", "2026-08-02T09:00:00")
            self.assertEqual(
                by_id(report.fetch_contributors(conn))[A]["name"],
                "Alpha Builder")

    def test_the_dataset_view_separates_a_dead_query_from_a_broken_worker(self):
        # THE CONTROL, and the reason --by-dataset exists. Two contributors
        # both submit empty on s0 and both submit real results on s1. Grouped
        # by contributor that is two suspicious workers; grouped by dataset it
        # is one dead query, which is the true reading.
        with report_scratch_schema() as (conn, _):
            for who in (A, B):
                qc.log_submission(conn, "submit", who, D0, reason="empty")
                qc.log_submission(conn, "submit", who, D1, fetched_count=8,
                                  accepted_count=8)
            conn.commit()
            datasets = {r["dataset"]: r for r in report.fetch_datasets(conn)}
            self.assertEqual(datasets[D0]["empty_submits"], 2)
            self.assertEqual(datasets[D0]["contributors"], 2)
            self.assertEqual(datasets[D1]["empty_submits"], 0)

    def test_a_broken_worker_is_visible_where_a_dead_query_is_not(self):
        # The other direction of the same table: one contributor empty across
        # both slugs while another succeeds on both.
        with report_scratch_schema() as (conn, _):
            for dataset in (D0, D1):
                qc.log_submission(conn, "claim", A, dataset)
                qc.log_submission(conn, "submit", A, dataset, reason="empty")
                qc.log_submission(conn, "claim", B, dataset)
                qc.log_submission(conn, "submit", B, dataset, fetched_count=6,
                                  accepted_count=6)
            conn.commit()
            rows = report.apply_findings(report.fetch_contributors(conn),
                                         min_submits=2)
            self.assertEqual(by_id(rows)[A]["finding"],
                             report.FINDING_EMPTY_SUBMITS)
            self.assertEqual(by_id(rows)[B]["finding"], "")

            datasets = {r["dataset"]: r for r in report.fetch_datasets(conn)}
            for dataset in (D0, D1):
                self.assertEqual(datasets[dataset]["empty_submits"], 1)
                self.assertEqual(datasets[dataset]["submits"], 2)

    def test_a_claim_only_worker_is_visible_as_such(self):
        # The D41 threat with a report behind it at last: claims held, nothing
        # submitted, and each claim locked a query for CLAIM_TTL_MINUTES.
        with report_scratch_schema() as (conn, _):
            for i in range(6):
                qc.log_submission(conn, "claim", A, f"google_jobs:query:s{i}")
            conn.commit()
            rows = report.apply_findings(report.fetch_contributors(conn))
            self.assertEqual(by_id(rows)[A]["finding"],
                             report.FINDING_NO_SUBMITS)

    def test_an_empty_table_reports_nothing_rather_than_failing(self):
        with report_scratch_schema() as (conn, _):
            self.assertEqual(report.fetch_contributors(conn), [])
            self.assertEqual(report.fetch_datasets(conn), [])
            self.assertIn("no submission_log rows", report.totals_line([]))

    def test_the_report_runs_on_this_services_own_grants(self):
        # It reads submission_log and contributors and nothing else. Asserted
        # here as well as in tests/test_grants.py because that scan reads the
        # SQL and this runs it: a table reached through a view or a function
        # would pass the scan and fail here.
        with report_scratch_schema() as (conn, _):
            log_raw(conn, A, D0, "claim", "2026-08-02T09:00:00")
            for table in ("submission_log", "contributors"):
                self.assertIn(table, qc.REQUIRED_TABLES)
            report.fetch_contributors(conn)
            report.fetch_datasets(conn)


if __name__ == "__main__":
    unittest.main()

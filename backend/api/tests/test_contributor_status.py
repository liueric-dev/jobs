"""T-35: four facts per contributor, so an idle worker and a stopped one differ.

THE DISTINCTION THIS WHOLE FILE IS ABOUT. `claim` writes no `submission_log`
row when it grants nothing, and granting nothing is the COMMON answer -- the
bank is fresh most days. So before this row, a contributor who installed the
worker, scheduled it, and polled faithfully every hour for a week was
indistinguishable, in every record this service kept, from a contributor who
opened the email and did nothing. Last check-in is not last submission, and
`0007`'s dormancy consequence ("pauses spending, not check-in") is unbuildable
until they are two facts instead of one.

WHAT IS PINNED HERE, IN THE ORDER IT MATTERS:

  1. EVERY authenticated poll checks in -- granted, granted-nothing, paused,
     and refused at the daily cap. The last is the one an implementation loses
     by accident: `claim` refuses by raising, `db()` rolls back on the way out,
     and a check-in inside that transaction would be erased for exactly the
     contributors an operator is looking for.
  2. And it is still not a claim. No `submission_log` row, nothing
     `claims_today()` counts, so an honest idle poll does not eat the allowance
     it exists to prove is unspent.
  3. The three reported fields are stored AS REPORTED and can never refuse the
     poll they ride on. A worker whose traceback had a newline in it must not
     be denied the queries it called for.

WHY A SEPARATE TABLE and not three more columns on `contributors`: see
qc.REQUIRED_TABLES. The short form is that this is written by the request path
and `contributors` holds the policy that governs the request path, so the two
must not share a grant.

ONE CLOCK. Every timestamp asserted below is compared against another timestamp
from the same write, or against a bound captured from the same run -- never
against a literal. Two tests in this repo rotted by mixing a real `now` with a
hardcoded one (TASKS.md, "Two rotting tests"), and a row with three timestamps
on it is exactly the invitation.
"""

import importlib.util
import os
import re
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fakedb import FakeConn, patch_db                # noqa: E402

import app                                          # noqa: E402
import contribution_report as report                # noqa: E402
import query_claims as qc                           # noqa: E402
from fastapi import HTTPException                   # noqa: E402

#: One scratch-schema fixture for this package, not three. Last in the block,
#: matching where test_claim_metering.py and test_contributor_settings.py put
#: their own cross-module imports.
from test_claim_protocol import api_scratch_schema, requires_db  # noqa: E402

API_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WORKER = os.path.join(API_DIR, "contributor-worker", "google-serpapi-worker.py")

A = "c_alpha"
B = "c_beta"
D0 = "google_jobs:query:s0"


def bank_of(n):
    """A bank of n slugs in one bucket with budget for all of them. Deliberately
    the same shape as the two other files that need one, and deliberately not
    shared with them: a helper joining three files that assert different things
    is a helper that has to change for all three at once."""
    return {
        "b": {
            "daily_budget": n,
            "queries": [{"slug": f"s{i}", "query": f"q{i}", "location": "New York",
                         "mode": "nyc"} for i in range(n)],
        }
    }


def run_claim(conn, max_queries=1, **reported):
    restore = patch_db(app, conn)
    try:
        return app.claim(app.ClaimRequest(max=max_queries, **reported),
                         authorization="Bearer key")
    finally:
        restore()


class _ClaimCase(unittest.TestCase):

    def setUp(self):
        self._real = qc.load_query_buckets
        self.addCleanup(lambda: setattr(qc, "load_query_buckets", self._real))
        qc.load_query_buckets = lambda: bank_of(3)


class TestEveryPollChecksIn(_ClaimCase):
    """The property, from each of the four directions a poll can end."""

    def test_a_poll_that_is_granted_queries_checks_in(self):
        conn = FakeConn()
        run_claim(conn, max_queries=3)
        self.assertEqual(len(conn.check_ins), 1)
        self.assertEqual(conn.check_ins[0]["contributor_id"], "c_test")

    def test_a_poll_that_is_granted_nothing_still_checks_in(self):
        # THE CASE THE ROW EXISTS FOR. claim_wins=False: every candidate is
        # already held, so this contributor gets nothing and writes no
        # submission_log row -- and is a perfectly healthy machine.
        conn = FakeConn(claim_wins=False)
        result = run_claim(conn, max_queries=3)
        self.assertEqual(result["queries"], [])
        self.assertEqual(conn.log, [])
        self.assertEqual(len(conn.check_ins), 1)

    def test_a_paused_poll_checks_in(self):
        # 0007's dormancy consequence, which is the whole reason pause is a 200:
        # pausing stops SPENDING and not REPORTING. A paused contributor whose
        # check-in stopped would look like one whose machine died.
        conn = FakeConn(settings=(True, None, None))
        result = run_claim(conn)
        self.assertTrue(result["paused"])
        self.assertEqual(len(conn.check_ins), 1)

    def test_a_poll_refused_at_the_daily_cap_checks_in(self):
        # THE ONE AN IMPLEMENTATION LOSES BY ACCIDENT. This path raises, and
        # `db()`'s `with conn:` rolls back on an exception -- so a check-in that
        # left its commit to the caller would be erased on exactly the polls
        # that prove a worker is alive and being told no.
        conn = FakeConn(claim_rows_today=app.MAX_CLAIMS_PER_CONTRIBUTOR_PER_DAY)
        with self.assertRaises(HTTPException) as caught:
            run_claim(conn)
        self.assertEqual(caught.exception.status_code, 429)
        self.assertEqual(len(conn.check_ins), 1)

    def test_the_check_in_is_committed_before_anything_can_refuse_the_poll(self):
        # The other half of the test above, and the half that survives someone
        # "tidying up" the commit: a rollback cannot undo what is already
        # committed, so the assertion is that a commit happened BEFORE the
        # refusal, not merely that the row was built.
        conn = FakeConn(claim_rows_today=app.MAX_CLAIMS_PER_CONTRIBUTOR_PER_DAY)
        with self.assertRaises(HTTPException):
            run_claim(conn)
        self.assertGreaterEqual(conn.commits, 1,
                                "the check-in was not committed, so the 429's "
                                "rollback takes it with it")

    def test_an_unauthenticated_poll_checks_nobody_in(self):
        # Ordering: authenticate() first. A check-in above it would be a row
        # this service writes on behalf of a caller it just refused to
        # recognise -- and there is no contributor_id to write it under.
        conn = FakeConn(revoked="2026-08-09T00:00:00")
        with self.assertRaises(HTTPException) as caught:
            run_claim(conn)
        self.assertEqual(caught.exception.status_code, 401)
        self.assertEqual(conn.check_ins, [])

    def test_one_poll_is_one_check_in_and_not_one_per_query(self):
        # `claim` writes one submission_log row PER QUERY (defect D41); the
        # check-in is per POLL. Copying the metering rule here would make a
        # busy machine look like three machines.
        conn = FakeConn()
        run_claim(conn, max_queries=3)
        self.assertEqual(len(conn.rows("claim")), 3)
        self.assertEqual(len(conn.check_ins), 1)


class TestTheCheckInIsNotAClaim(_ClaimCase):

    def test_it_writes_no_submission_log_row(self):
        conn = FakeConn(claim_wins=False)
        run_claim(conn)
        self.assertEqual(conn.log, [],
                         "a check-in must not be metered as work")

    def test_it_does_not_count_toward_the_daily_cap(self):
        # The failure this prevents, stated as the row states it: an honest
        # idle poll that consumed the allowance would exhaust a daily cron on
        # exactly the days there was nothing to do.
        conn = FakeConn(claim_wins=False)
        run_claim(conn)
        self.assertEqual(app.claims_today(conn, "c_test"), 0)

    def test_the_vocabulary_did_not_grow_a_fifth_action(self):
        # The cheaper-looking design this row rejected: a `check-in` row in
        # submission_log. Thirty machines polling hourly is ~700 rows a day of
        # something nobody wants a history of, in the table whose totals are
        # meant to report contribution.
        self.assertEqual(len(qc.SUBMISSION_ACTIONS), 4)
        self.assertNotIn("check-in", qc.SUBMISSION_ACTIONS)


class TestWhatAPollReports(_ClaimCase):

    def test_the_three_fields_are_stored_as_reported(self):
        conn = FakeConn()
        run_claim(conn, worker_version="jobs-contributor-worker/1.1",
                  quota_remaining=42, last_error="serpapi 401")
        row = conn.check_ins[0]
        self.assertEqual(row["worker_version"], "jobs-contributor-worker/1.1")
        self.assertEqual(row["quota_remaining"], 42)
        self.assertEqual(row["last_error"], "serpapi 401")

    def test_a_poll_reporting_nothing_reports_nothing(self):
        # An older worker, or a run with nothing to say. Every reported field
        # is NULL, which is what the COALESCEs read as "leave what you have".
        conn = FakeConn()
        run_claim(conn)
        row = conn.check_ins[0]
        for field in ("worker_version", "quota_remaining", "quota_reported_at",
                      "last_error", "last_error_at"):
            self.assertIsNone(row[field], field)
        self.assertIsNotNone(row["last_check_in_at"])

    def test_a_quota_gets_a_timestamp_and_an_absent_one_does_not(self):
        # WHY THE TIMESTAMP IS NOT last_check_in_at. If it were, a balance
        # reported once and never again would read as freshly confirmed every
        # hour -- and T-54 is filed to build a floor on top of exactly this
        # number's age.
        conn = FakeConn()
        run_claim(conn, quota_remaining=7)
        self.assertIsNotNone(conn.check_ins[0]["quota_reported_at"])
        self.assertIsNone(conn.check_ins[0]["last_error_at"])

    def test_an_error_gets_a_timestamp_and_an_absent_one_does_not(self):
        conn = FakeConn()
        run_claim(conn, last_error="boom")
        self.assertIsNotNone(conn.check_ins[0]["last_error_at"])
        self.assertIsNone(conn.check_ins[0]["quota_reported_at"])

    def test_every_timestamp_in_one_check_in_is_the_same_clock(self):
        # ONE CLOCK. Three utc_now_str() calls would differ across a second
        # boundary, and a row saying it was checked in before the value it was
        # checked in with was reported is a row that cannot be reasoned about.
        conn = FakeConn()
        run_claim(conn, quota_remaining=1, last_error="boom")
        row = conn.check_ins[0]
        self.assertEqual(row["last_check_in_at"], row["quota_reported_at"])
        self.assertEqual(row["last_check_in_at"], row["last_error_at"])

    def test_a_paused_poll_reports_its_facts_too(self):
        # Pausing stops spending, not reporting -- including the reporting a
        # Builder's own machine does about itself.
        conn = FakeConn(settings=(True, None, None))
        run_claim(conn, worker_version="w/9", quota_remaining=3)
        self.assertEqual(conn.check_ins[0]["worker_version"], "w/9")
        self.assertEqual(conn.check_ins[0]["quota_remaining"], 3)

    def test_a_zero_quota_is_a_report_and_not_an_absence(self):
        # 0 searches left is the single most actionable value this field can
        # hold -- a working install that will do no work. A falsiness check
        # would drop it and leave yesterday's number in place.
        conn = FakeConn()
        run_claim(conn, quota_remaining=0)
        self.assertEqual(conn.check_ins[0]["quota_remaining"], 0)
        self.assertIsNotNone(conn.check_ins[0]["quota_reported_at"])


class TestAReportCannotBreakThePoll(_ClaimCase):
    """The trade this row is specified on: status reporting must never be the
    thing that stops a machine collecting postings."""

    def test_an_enormous_error_string_is_trimmed_rather_than_refused(self):
        conn = FakeConn()
        result = run_claim(conn, last_error="x" * 100_000)
        self.assertEqual(len(result["queries"]), 1,
                         "the poll was refused over a status field")
        self.assertEqual(len(conn.check_ins[0]["last_error"]),
                         qc.MAX_REPORTED_ERROR_CHARS)

    def test_an_enormous_version_string_is_trimmed_too(self):
        conn = FakeConn()
        run_claim(conn, worker_version="v" * 5000)
        self.assertEqual(len(conn.check_ins[0]["worker_version"]),
                         qc.MAX_WORKER_VERSION_CHARS)

    def test_a_newline_in_a_traceback_does_not_refuse_the_poll(self):
        conn = FakeConn()
        run_claim(conn, last_error="Traceback:\n  File x\n  boom")
        self.assertNotIn("\n", conn.check_ins[0]["last_error"])
        self.assertIn("boom", conn.check_ins[0]["last_error"])

    def test_a_terminal_escape_sequence_never_reaches_the_stored_string(self):
        # The one consumer of this field prints a fixed-width table on an
        # operator's terminal. An ANSI escape in a contributor-supplied cell is
        # a cell that can repaint the row above it or hide itself -- the same
        # argument app._validation_detail makes about the response body.
        conn = FakeConn()
        run_claim(conn, last_error="\x1b[2Kfine\x07")
        stored = conn.check_ins[0]["last_error"]
        self.assertNotIn("\x1b", stored)
        self.assertNotIn("\x07", stored)
        self.assertIn("fine", stored)

    def test_a_wrong_type_is_still_a_422_and_that_is_deliberate(self):
        # The other side of the trade, stated so it is not read as an
        # oversight. A worker sending a string where a count belongs is broken
        # CODE, not a broken machine, and the most useful thing this end can do
        # is name the field.
        from pydantic import ValidationError
        with self.assertRaises(ValidationError):
            app.ClaimRequest(max=1, quota_remaining="lots")


class TestTheReportedTextRules(unittest.TestCase):
    """qc._reported_text alone -- no request, no database."""

    def test_none_stays_none(self):
        self.assertIsNone(qc._reported_text(None, 10))

    def test_a_string_of_only_whitespace_reports_nothing(self):
        # "" and "   " and "\n" are a worker with nothing to say, and None is
        # how "nothing to say" is spelled everywhere else in this path. Two
        # spellings would mean two branches at every reader.
        for value in ("", "   ", "\n\t"):
            with self.subTest(value=value):
                self.assertIsNone(qc._reported_text(value, 10))

    def test_it_truncates_rather_than_raising(self):
        self.assertEqual(qc._reported_text("abcdef", 3), "abc")

    def test_ordinary_text_is_untouched(self):
        self.assertEqual(qc._reported_text("serpapi 401: bad key", 100),
                         "serpapi 401: bad key")

    def test_non_ascii_text_survives(self):
        # isprintable() accepts unicode, and it should: a Builder's machine may
        # report an OS error in their own language, and mangling it would make
        # the message useless to the one person who could act on it.
        self.assertEqual(qc._reported_text("fichier introuvable — non", 100),
                         "fichier introuvable — non")


class TestTheColumnsAgree(unittest.TestCase):
    """One list of names; the DDL, the INSERT and the report's SELECT."""

    def _source(self, name):
        with open(os.path.join(API_DIR, name), encoding="utf-8") as fh:
            return fh.read()

    def test_the_ddl_declares_exactly_the_named_columns(self):
        create = re.search(
            r"CREATE TABLE IF NOT EXISTS contributor_status \((.*?)\n        \)",
            self._source("query_claims.py"), re.S)
        self.assertIsNotNone(create, "contributor_status' CREATE TABLE has moved")
        declared = tuple(
            line.strip().split()[0] for line in create.group(1).splitlines()
            if line.strip())
        self.assertEqual(declared,
                         ("contributor_id",) + qc.CONTRIBUTOR_STATUS_COLUMNS)

    def test_the_insert_names_every_column(self):
        source = self._source("query_claims.py")
        inserted = re.search(
            r"INSERT INTO contributor_status \((.*?)\)", source, re.S)
        self.assertIsNotNone(inserted, "record_check_in's INSERT has moved")
        named = {c.strip() for c in inserted.group(1).split(",")}
        for column in ("contributor_id",) + qc.CONTRIBUTOR_STATUS_COLUMNS:
            self.assertIn(column, named)

    def test_the_report_selects_every_column(self):
        source = self._source("contribution_report.py")
        for column in qc.CONTRIBUTOR_STATUS_COLUMNS:
            self.assertIn(f"s.{column}", source,
                          f"the report does not read {column}, so a fact this "
                          f"service stores reaches nobody")

    def test_the_columns_are_in_the_create_and_not_added_afterwards(self):
        # WHY THIS TABLE IS NOT IN REQUIRED_COLUMNS, asserted rather than
        # asserted-in-prose. That map's criterion is "can the column go missing
        # on its own", which is true of a column added by add_missing_columns to
        # a table that already exists and false of one in a CREATE TABLE.
        # REQUIRED_TABLES covers the only thing that can be absent here.
        source = self._source("query_claims.py")
        self.assertNotIn("contributor_status", str(qc.REQUIRED_COLUMNS))
        self.assertNotIn('add_missing_columns(conn, "contributor_status"', source)


class TestTheGrant(unittest.TestCase):

    def test_the_table_is_declared_with_the_privileges_it_needs(self):
        self.assertEqual(qc.REQUIRED_TABLES["contributor_status"],
                         ("SELECT", "INSERT", "UPDATE"))

    def test_contributors_still_holds_no_update(self):
        # THE REASON THIS IS A SECOND TABLE. `contributor_status` is written by
        # the request path; `contributors` carries the operator's policy over
        # that same machine. Had the four facts gone on `contributors`, this
        # role would need UPDATE there -- and a compromised app.py could
        # un-pause itself and raise its own cap. T-34 refused that outright and
        # this keeps the refusal checkable.
        self.assertNotIn("UPDATE", qc.REQUIRED_TABLES["contributors"])

    def test_the_new_table_has_no_bigserial_and_so_needs_no_sequence(self):
        # tests/test_grants.py derives sequence grants from the DDL; this says
        # the same thing from the other side, so a future edit that gives this
        # table a BIGSERIAL id is red in two places rather than 500ing on the
        # first check-in.
        self.assertNotIn("contributor_status_id_seq", qc.REQUIRED_SEQUENCES)


class TestTheReportShowsTheFourFacts(unittest.TestCase):
    """The formatter and the notes, over dicts -- no database."""

    def _record(self, **overrides):
        base = {"contributor_id": A, "name": "Alpha", "claims": 0, "submits": 0,
                "empty_submits": 0, "releases": 0, "unknown_action": 0,
                "other_action": 0, "fetched": 0, "accepted": 0,
                "first_at": None, "last_at": None}
        base.update(dict.fromkeys(report._STATUS_KEYS))
        base.update(overrides)
        base["rows_total"] = sum(base[b] for b in report.BUCKETS)
        return report.summarize(base)

    def _table(self, records):
        return report.format_table(
            records, "contributor_id", "contributor",
            (("name", "name"), ("check-in", "last_check_in"),
             ("worker", "worker_version"), ("quota", "quota_remaining")))

    def test_the_check_in_and_the_version_and_the_quota_are_columns(self):
        table = self._table([self._record(
            last_check_in="2026-08-09T10:00:00",
            worker_version="jobs-contributor-worker/1.1", quota_remaining=42)])
        for expected in ("check-in", "2026-08-09T10:00:00",
                         "jobs-contributor-worker/1.1", "42"):
            self.assertIn(expected, table)

    def test_a_contributor_that_has_never_checked_in_prints_a_dash(self):
        # The single most useful cell in this report: a Builder who opted in and
        # whose machine has never spoken to this service.
        table = self._table([self._record()])
        self.assertIn("-", table)
        self.assertNotIn("None", table)

    def test_the_error_is_a_note_and_not_a_column(self):
        # An error is a sentence. Truncated into a column it is unreadable;
        # untruncated it makes every other column unreachable.
        notes = report.status_notes([self._record(
            last_error="serpapi 401: this key is not recognised",
            last_error_at="2026-08-09T11:00:00")])
        self.assertIn("serpapi 401", notes)
        self.assertIn("2026-08-09T11:00:00", notes)

    def test_the_notes_say_the_facts_are_the_contributors_and_not_ours(self):
        # "never present it as authoritative", printed where the number is READ
        # rather than only where it is written.
        notes = report.status_notes([self._record(
            quota_remaining=9, quota_reported_at="2026-08-08T09:00:00")])
        self.assertIn("reported by the contributors' own machines", notes)
        self.assertIn("2026-08-08T09:00:00", notes)

    def test_a_quota_is_shown_with_the_time_it_was_reported_never_alone(self):
        # The caveat and the number cannot be separated: a balance without its
        # age is a balance a reader will assume is current.
        notes = report.status_notes([self._record(
            quota_remaining=9, quota_reported_at="2026-08-01T09:00:00")])
        self.assertIn("9", notes)
        self.assertIn("2026-08-01T09:00:00", notes)

    def test_nothing_reported_prints_no_note_at_all(self):
        # A heading that is always there is a heading nobody reads -- the same
        # rule totals_line() already applies to its NULL caveat.
        self.assertEqual(report.status_notes([self._record()]), "")

    def test_the_status_keys_do_not_disturb_the_bucket_reconciliation(self):
        # summarize() asserts the five buckets add to rows_total. Six more keys
        # on the same dict must not enter that sum.
        record = self._record(claims=2, last_check_in="2026-08-09T10:00:00")
        self.assertEqual(record["rows_total"], 2)


@requires_db
class TestAgainstARealDatabase(unittest.TestCase):
    """The claims a fake cannot make: the DDL runs, the upsert upserts, and
    COALESCE really does leave an unreported field alone.

    THE FIXTURE IS IMPORTED, NOT COPIED -- see test_contributor_settings.py's
    class of the same name for the one subtlety that makes it work. `requires_db`
    skips where no scratch database is reachable, so read `Ran N tests`.
    """

    schema = staticmethod(api_scratch_schema)

    def _row(self, conn, contributor_id):
        # The spliced names are a module-level constant tuple and never input,
        # which is .claude/rules/sql.md's rule. There is deliberately no S608
        # suppression comment the way a non-test site carries one: S608 is
        # per-file-ignored under tests/, so the directive would be inert and
        # would read as a rule being suppressed rather than as one being met.
        # (Spelling the directive out even inside prose makes ruff try to parse
        # it -- which is how this comment was first written, and it warned.)
        columns = ", ".join(qc.CONTRIBUTOR_STATUS_COLUMNS)
        return dict(zip(qc.CONTRIBUTOR_STATUS_COLUMNS, conn.execute(
            f"SELECT {columns} FROM contributor_status "
            f"WHERE contributor_id = %s", (contributor_id,)).fetchone()))

    def _contributor(self, conn, name="Dave"):
        cid, _key, _hash, _at = qc.mint_credential(conn, name)
        conn.commit()
        return cid

    def test_ensure_schema_creates_the_table(self):
        with self.schema() as (conn, _):
            present = {r[0] for r in conn.execute(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_name = 'contributor_status' "
                "AND table_schema = current_schema()").fetchall()}
            self.assertTrue(set(qc.CONTRIBUTOR_STATUS_COLUMNS) <= present)

    def test_running_ensure_schema_twice_raises_nothing(self):
        with self.schema() as (conn, _):
            qc.ensure_schema(conn)

    def test_a_first_check_in_inserts_and_a_second_updates_in_place(self):
        # ONE ROW PER CONTRIBUTOR, which is the difference between current state
        # and a log. Thirty machines polling hourly for a year must not be
        # 260,000 rows.
        with self.schema() as (conn, _):
            cid = self._contributor(conn)
            qc.record_check_in(conn, cid)
            first = self._row(conn, cid)["last_check_in_at"]
            qc.record_check_in(conn, cid)
            count = conn.execute(
                "SELECT COUNT(*) FROM contributor_status").fetchone()[0]
            self.assertEqual(count, 1)
            self.assertGreaterEqual(self._row(conn, cid)["last_check_in_at"],
                                    first)

    def test_an_unreported_field_keeps_its_value_and_its_timestamp(self):
        # THE COALESCE, AND BOTH HALVES OF IT. Keeping the value and re-stamping
        # the time would be worse than losing it: a balance nobody has confirmed
        # for a week would read as confirmed an hour ago, and T-54's staleness
        # fallback would never fire.
        with self.schema() as (conn, _):
            cid = self._contributor(conn)
            qc.record_check_in(conn, cid, quota_remaining=40,
                               last_error="serpapi 401")
            before = self._row(conn, cid)
            qc.record_check_in(conn, cid)
            after = self._row(conn, cid)
            self.assertEqual(after["quota_remaining"], 40)
            self.assertEqual(after["quota_reported_at"],
                             before["quota_reported_at"])
            self.assertEqual(after["last_error"], "serpapi 401")
            self.assertEqual(after["last_error_at"], before["last_error_at"])
            self.assertGreaterEqual(after["last_check_in_at"],
                                    before["last_check_in_at"])

    def test_a_reported_field_overwrites_both_the_value_and_its_time(self):
        with self.schema() as (conn, _):
            cid = self._contributor(conn)
            qc.record_check_in(conn, cid, quota_remaining=40)
            before = self._row(conn, cid)
            qc.record_check_in(conn, cid, quota_remaining=12)
            after = self._row(conn, cid)
            self.assertEqual(after["quota_remaining"], 12)
            self.assertGreaterEqual(after["quota_reported_at"],
                                    before["quota_reported_at"])

    def test_a_zero_quota_is_written_and_not_coalesced_away(self):
        # COALESCE(0, previous) is 0 in SQL as it is in Python, and this is the
        # test that says so rather than the reader having to remember it.
        with self.schema() as (conn, _):
            cid = self._contributor(conn)
            qc.record_check_in(conn, cid, quota_remaining=40)
            qc.record_check_in(conn, cid, quota_remaining=0)
            self.assertEqual(self._row(conn, cid)["quota_remaining"], 0)

    def test_the_types_are_the_ones_the_column_declares(self):
        # An INTEGER column and a TEXT one, round-tripped. A TEXT quota would
        # have passed every fake-based test above and sorted "9" after "40".
        with self.schema() as (conn, _):
            cid = self._contributor(conn)
            qc.record_check_in(conn, cid, quota_remaining=7,
                               worker_version="w/1.1")
            row = self._row(conn, cid)
            self.assertIsInstance(row["quota_remaining"], int)
            self.assertIsInstance(row["worker_version"], str)

    def test_a_status_row_for_an_unknown_contributor_is_refused(self):
        # The foreign key, which submission_log deliberately does NOT have. That
        # table is evidence and an orphan row is the most interesting kind; this
        # is one row of state per contributor, and a state row about nobody is
        # not a fact worth keeping.
        import psycopg
        with self.schema() as (conn, _):
            with self.assertRaises(psycopg.errors.ForeignKeyViolation):
                qc.record_check_in(conn, "c_nobody")
            conn.rollback()

    def test_a_contributor_who_has_only_ever_checked_in_appears_in_the_report(self):
        # THE HOLE THIS ROW CLOSES. Before T-35 the report grouped
        # submission_log, so a worker that polls faithfully and is granted
        # nothing -- the common case on a fresh bank -- was in no row of it.
        with self.schema() as (conn, _):
            cid = self._contributor(conn, "Faithful")
            qc.record_check_in(conn, cid, worker_version="w/1.1",
                               quota_remaining=200)
            rows = {r["contributor_id"]: r
                    for r in report.fetch_contributors(conn)}
            self.assertIn(cid, rows)
            self.assertEqual(rows[cid]["claims"], 0)
            self.assertEqual(rows[cid]["rows_total"], 0)
            self.assertEqual(rows[cid]["worker_version"], "w/1.1")
            self.assertEqual(rows[cid]["quota_remaining"], 200)
            self.assertIsNotNone(rows[cid]["last_check_in"])

    def test_a_contributor_who_has_never_checked_in_appears_with_no_status(self):
        with self.schema() as (conn, _):
            cid = self._contributor(conn, "Silent")
            rows = {r["contributor_id"]: r
                    for r in report.fetch_contributors(conn)}
            self.assertIn(cid, rows)
            for key in report._STATUS_KEYS:
                self.assertIsNone(rows[cid][key], key)

    def test_a_log_row_with_no_contributors_row_still_reports(self):
        # The other direction of the union, and the property the report had
        # before this row -- kept, because it is the shape a leaked or
        # hand-crafted key would take.
        with self.schema() as (conn, _):
            qc.log_submission(conn, "claim", "c_ghost", D0)
            conn.commit()
            rows = {r["contributor_id"]: r
                    for r in report.fetch_contributors(conn)}
            self.assertIn("c_ghost", rows)
            self.assertIsNone(rows["c_ghost"]["name"])
            self.assertIsNone(rows["c_ghost"]["last_check_in"])
            self.assertEqual(rows["c_ghost"]["claims"], 1)

    def test_a_contributor_appears_once_when_they_have_both(self):
        # The union is a union and not a concatenation: a contributor with a
        # status row AND log rows is one line, with the counts on it.
        with self.schema() as (conn, _):
            cid = self._contributor(conn, "Busy")
            qc.record_check_in(conn, cid)
            qc.log_submission(conn, "claim", cid, D0)
            conn.commit()
            rows = [r for r in report.fetch_contributors(conn)
                    if r["contributor_id"] == cid]
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["claims"], 1)
            self.assertIsNotNone(rows[0]["last_check_in"])

    def test_the_since_bound_filters_the_log_and_not_the_status(self):
        # A reader asking "who has done nothing since Monday" needs the
        # check-in that answers "because they stopped polling on Tuesday" --
        # filtering it out with the work would remove the answer.
        with self.schema() as (conn, _):
            cid = self._contributor(conn, "Quiet")
            qc.record_check_in(conn, cid)
            conn.execute(
                "INSERT INTO submission_log (contributor_id, dataset, "
                "submitted_at, fetched_count, accepted_count, rejected_count, "
                "action) VALUES (%s, %s, %s, 0, 0, 0, 'claim')",
                (cid, D0, "2026-07-01T00:00:00"))
            conn.commit()
            row = {r["contributor_id"]: r for r in
                   report.fetch_contributors(conn, "2026-08-01")}[cid]
            self.assertEqual(row["claims"], 0)
            self.assertIsNotNone(row["last_check_in"])

    def test_an_empty_database_still_reports_nothing(self):
        with self.schema() as (conn, _):
            self.assertEqual(report.fetch_contributors(conn), [])

    def test_the_report_reads_only_tables_this_role_is_granted(self):
        with self.schema() as (conn, _):
            for table in ("submission_log", "contributors",
                          "contributor_status"):
                self.assertIn(table, qc.REQUIRED_TABLES)
            report.fetch_contributors(conn)


def load_worker():
    """Import the worker under a name Python will accept -- the hyphens in the
    filename mean `import` cannot name it. Same loader, same reason, as
    test_worker_check.py's."""
    spec = importlib.util.spec_from_file_location("contributor_worker", WORKER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class TestTheWorkersOutbox(unittest.TestCase):
    """The file the worker keeps between runs, exercised for real.

    IT IS POINTED AT A TEMPORARY DIRECTORY IN setUp, and that is not
    boilerplate: STATE_PATH resolves from __file__, so a test that forgot would
    write into the shipped worker directory -- the same directory
    test_contributor_worker.py asserts holds no config.json, and for the same
    reason.
    """

    def setUp(self):
        import tempfile

        self.worker = load_worker()
        directory = tempfile.mkdtemp()
        self.addCleanup(__import__("shutil").rmtree, directory, True)
        self.worker.STATE_PATH = os.path.join(directory, "worker-state.json")

    def test_an_absent_outbox_is_empty_and_not_an_error(self):
        self.assertEqual(self.worker.read_outbox(), {})

    def test_what_a_run_remembers_is_what_the_next_poll_reads(self):
        self.worker.remember(last_error="boom")
        self.assertEqual(self.worker.read_outbox()["last_error"], "boom")

    def test_facts_are_merged_and_not_replaced(self):
        # A run can fail a search AND read its balance, at different moments.
        self.worker.remember(last_error="boom")
        self.worker.remember(quota_remaining=12)
        self.assertEqual(self.worker.read_outbox(),
                         {"last_error": "boom", "quota_remaining": 12})

    def test_the_newest_error_replaces_the_older_one(self):
        self.worker.remember(last_error="first")
        self.worker.remember(last_error="second")
        self.assertEqual(self.worker.read_outbox()["last_error"], "second")

    def test_clearing_it_leaves_nothing_to_report_twice(self):
        # WHY ANYTHING IS CLEARED AT ALL. A value re-sent every hour is a value
        # the server re-stamps every hour, and a week-old error would read as
        # an hour old forever.
        self.worker.remember(last_error="boom")
        self.worker.forget_outbox()
        self.assertEqual(self.worker.read_outbox(), {})

    def test_clearing_an_absent_outbox_is_not_an_error(self):
        self.worker.forget_outbox()

    def test_a_corrupt_outbox_reads_as_empty_rather_than_stopping_the_run(self):
        # This file is a convenience for the operator's report. A machine must
        # not stop collecting job postings because a JSON file it wrote itself
        # got truncated by a power cut.
        with open(self.worker.STATE_PATH, "w", encoding="utf-8") as fh:
            fh.write("{not json")
        self.assertEqual(self.worker.read_outbox(), {})

    def test_a_json_document_that_is_not_an_object_reads_as_empty(self):
        with open(self.worker.STATE_PATH, "w", encoding="utf-8") as fh:
            fh.write("[1, 2, 3]")
        self.assertEqual(self.worker.read_outbox(), {})

    def test_an_unwritable_location_does_not_raise(self):
        # A read-only directory is a machine that cannot report, not a machine
        # that cannot work.
        self.worker.STATE_PATH = os.path.join(
            self.worker.STATE_PATH, "nope", "worker-state.json")
        self.worker.remember(last_error="boom")
        self.assertEqual(self.worker.read_outbox(), {})


class TestTheWorkerReadsItsBalanceWithoutSpendingOne(unittest.TestCase):
    """remember_quota, with every answer scripted.

    NOTHING HERE REACHES THE NETWORK. The sender is injected, exactly as
    test_worker_check.py injects one -- and what is asserted about SerpApi is
    only what this suite itself scripted. That the account endpoint is really
    free and really reports `total_searches_left` is an account this repo does
    not have, and DEV_TASKS.md's OQ-25 is where a real install gets watched.
    """

    def setUp(self):
        import tempfile

        self.worker = load_worker()
        directory = tempfile.mkdtemp()
        self.addCleanup(__import__("shutil").rmtree, directory, True)
        self.worker.STATE_PATH = os.path.join(directory, "worker-state.json")
        self.worker.SERPAPI_API_KEY = "serp-test-key"
        self.sent = []

    def _sender(self, status, body):
        def send(request, timeout=None):
            self.sent.append(request)
            return status, body
        return send

    def test_it_remembers_the_remaining_count(self):
        self.worker.remember_quota(
            self._sender(200, '{"total_searches_left": 173, '
                              '"plan_name": "Free"}'))
        self.assertEqual(self.worker.read_outbox()["quota_remaining"], 173)

    def test_it_asks_the_account_endpoint_and_runs_no_search(self):
        # THE ROW'S CENTRAL PROMISE, one poll further along than --check made
        # it: this now runs on every scheduled run, so "it costs a credit"
        # would be a cost per hour rather than a cost per diagnosis.
        self.worker.remember_quota(self._sender(200, '{}'))
        self.assertEqual(len(self.sent), 1)
        self.assertTrue(self.sent[0].full_url.startswith(
            self.worker.SERPAPI_ACCOUNT_URL))
        self.assertNotIn("/search", self.sent[0].full_url)

    def test_a_rejected_key_is_reported_as_an_error_and_not_as_a_balance(self):
        # The most useful thing this can find: a SerpApi key that has stopped
        # working. It reaches the operator without anybody running --check.
        self.worker.remember_quota(self._sender(401, "bad key"))
        outbox = self.worker.read_outbox()
        self.assertNotIn("quota_remaining", outbox)
        self.assertIn("401", outbox["last_error"])

    def test_an_unreachable_serpapi_is_an_error_and_not_a_zero(self):
        import urllib.error

        def send(request, timeout=None):
            raise urllib.error.URLError("no route to host")

        self.worker.remember_quota(send)
        outbox = self.worker.read_outbox()
        self.assertNotIn("quota_remaining", outbox)
        self.assertIn("SerpApi account", outbox["last_error"])

    def test_an_answer_that_is_not_json_reports_no_balance(self):
        self.worker.remember_quota(self._sender(200, "<html>hello</html>"))
        self.assertNotIn("quota_remaining", self.worker.read_outbox())

    def test_a_plan_with_no_remaining_count_reports_no_balance(self):
        # AN OLD NUMBER THAT SAYS IT IS OLD BEATS A FRESH ZERO NOBODY MEASURED.
        # Reporting 0 here would tell an operator a Builder is out of credits.
        self.worker.remember_quota(self._sender(200, '{"plan_name": "Free"}'))
        self.assertEqual(self.worker.read_outbox(), {})

    def test_a_true_is_not_read_as_a_count(self):
        # bool is an int in Python, and `total_searches_left: true` would
        # otherwise be stored as a balance of 1.
        self.worker.remember_quota(
            self._sender(200, '{"total_searches_left": true}'))
        self.assertEqual(self.worker.read_outbox(), {})

    def test_no_serpapi_key_means_no_request_at_all(self):
        self.worker.SERPAPI_API_KEY = ""
        self.worker.remember_quota(self._sender(200, '{}'))
        self.assertEqual(self.sent, [])

    def test_the_key_never_reaches_the_remembered_error(self):
        # The URL carries the key as a query parameter, so an error quoting the
        # far end is a place it can come back out -- and this one is written to
        # a file and then posted to a server.
        self.worker.remember_quota(
            self._sender(500, f"upstream said {self.worker.SERPAPI_API_KEY}"))
        self.assertNotIn(self.worker.SERPAPI_API_KEY,
                         self.worker.read_outbox()["last_error"])


class TestTheWorkerSideOfTheContract(unittest.TestCase):
    """Read from the worker's source, because the two halves must agree on the
    field names and there is no other way to bind them from this side."""

    def _source(self):
        self.assertTrue(os.path.exists(WORKER),
                        f"{WORKER} is gone; this contract has no other side")
        with open(WORKER, encoding="utf-8") as fh:
            return fh.read()

    def test_the_poll_carries_the_three_fields_the_endpoint_accepts(self):
        source = self._source()
        for field in ("worker_version", "quota_remaining", "last_error"):
            self.assertIn(f'"{field}"', source,
                          f"the worker never sends {field}, so the column that "
                          f"stores it is one nothing can ever fill")
            self.assertIn(field, app.ClaimRequest.model_fields,
                          f"the worker sends {field} and the endpoint has no "
                          f"such field, so it is silently dropped")

    def test_there_is_one_version_string_and_not_two_spellings(self):
        # The User-Agent on the wire and the version the report prints are the
        # same constant, so a proxy's access log and an operator's terminal
        # cannot disagree about what a machine is running.
        source = self._source()
        self.assertIn('USER_AGENT = f"jobs-contributor-worker/{WORKER_VERSION}"',
                      source)
        self.assertNotIn('"jobs-contributor-worker/1.0"', source,
                         "a hardcoded User-Agent has come back; it will drift "
                         "from WORKER_VERSION the first time one is bumped")

    def _run_body(self):
        """main()'s body. Scoped, because forget_outbox is DEFINED above main
        and a whole-file search would find the definition rather than the call
        whose position is the claim being made."""
        source = self._source()
        halves = source.split("\ndef main():", 1)
        self.assertEqual(len(halves), 2, "main() has been renamed")
        return halves[1].split("\n# ---", 1)[0]

    def test_the_outbox_is_cleared_only_after_the_server_took_it(self):
        # If it were cleared before the request, a poll that never arrived would
        # drop the facts into a failed HTTP call and the next one would report
        # a machine with nothing wrong.
        claim = self._run_body().split('api_post("/v1/queries/claim"', 1)
        self.assertEqual(len(claim), 2, "the claim call has moved")
        self.assertNotIn("forget_outbox()", claim[0])
        self.assertIn("forget_outbox()", claim[1])

    def test_the_outbox_is_read_before_the_poll_that_carries_it(self):
        body = self._run_body()
        self.assertLess(body.index("read_outbox()"),
                        body.index('api_post("/v1/queries/claim"'))

    def test_every_failure_in_a_run_is_remembered(self):
        # Four places a run can go wrong -- claim, reach, search, submit -- and
        # each has to leave something for the next poll to carry, or the error
        # this row reports is only ever the last one that happened to be
        # convenient.
        source = self._source()
        self.assertGreaterEqual(source.count("remember(last_error="), 4)

    def test_the_balance_is_read_on_every_path_that_polled_successfully(self):
        # Paused, nothing-to-do, and a run that did work. A balance refreshed
        # only after real work would go stale on precisely the quiet machines
        # this report is for.
        self.assertEqual(self._source().count("remember_quota()"), 3)

    def test_the_worker_still_decides_nothing_from_what_it_reports(self):
        # T-34's property, extended to this row: the worker reports and does
        # not act. Nothing here is read back off the response, so a machine that
        # disagrees with the server about its own quota cannot exist.
        source = self._source()
        for reading in ('claimed.get("quota_remaining")',
                        'claimed.get("worker_version")',
                        'claimed.get("last_error")'):
            self.assertNotIn(reading, source)


if __name__ == "__main__":
    unittest.main()

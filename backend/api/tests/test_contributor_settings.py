"""T-34: the server holds desired state, and the worker holds none of it.

`docs/adr/0007` decision 3 gives this service three settings per contributor --
paused, a daily cap, a reserve floor -- and the reason they are here rather than
on the contributor's machine is that a machine's copy is a second source of
truth that a paused contributor's machine will disagree with. So every assertion
below is about what `claim` decides, not about what a worker does with the
answer.

THE THREE EDGES THIS FILE EXISTS FOR:

  1. PAUSE IS A 200. A paused contributor is granted nothing and is told so on
     an ordinary reply carrying an ordinary poll interval. Refusing the request
     instead would exit the worker non-zero (`google-serpapi-worker.py:407-412`
     exits 1 on any HTTPError from this route), which makes a deliberately quiet
     machine report itself broken -- and would leave T-35's check-in, which
     0007's dormancy consequence says must keep happening while spending stops,
     with nothing to record.

  2. THE FLOOR STOPS A CLAIM AT THE BOUNDARY, NOT ONE QUERY PAST IT. A cap of 5
     with a floor of 2 is an allowance of 3: the third claim of the day is
     granted and the fourth is refused. The off-by-one that `>` instead of `>=`
     would produce keeps 1 credit of a 2-credit reserve, which is the failure
     that looks most like working.

  3. THE FLOOR IS READ AGAINST A BALANCE, AND ONLY AGAINST ONE IT BELIEVES
     (T-54). A cap of 5 with a floor of 2 and a freshly reported balance of 10
     is an allowance of 5, not 3: the floor binds against the credits, so
     subtracting it from the cap as well would charge the Builder their reserve
     twice. The same contributor with a balance nothing has confirmed for days
     is back to 3 -- the fallback is T-34's reading and not zero, because a
     machine that has never finished a run has reported nothing, and stopping
     its work on the strength of a number that never came is the failure this
     edge is here to prevent.

WHY A FAKE AND NOT A DATABASE: see fakedb's own docstring. Every claim here is
about which branch the endpoint takes, and none is about SQL semantics -- except
the two in TestTheColumnsAgree, which check that the names in the SELECT, in the
DDL and in REQUIRED_COLUMNS are the same names, and those are checked as text
because that is the only thing that can go wrong between them.
"""

import contextlib
import io
import os
import re
import sys
import unittest
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fakedb import FakeConn, patch_db                # noqa: E402

import app                                          # noqa: E402
import query_claims as qc                           # noqa: E402
from fastapi import HTTPException                   # noqa: E402

#: One scratch-schema fixture for this package, not two. See
#: TestAgainstARealDatabase for why it is imported rather than copied; importing
#: it also inherits that module's JOBS_SCRATCH_DATABASE_URL fallback, which is
#: the thing that has to agree between them. Last in the block, matching the
#: place test_claim_metering.py puts its cross-module import.
from test_claim_protocol import api_scratch_schema, requires_db  # noqa: E402

API_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def bank_of(n):
    """A bank of n slugs in one bucket with budget for all of them, so the only
    thing that can limit a grant is the allowance under test. Deliberately the
    same shape as test_claim_metering's -- a shared helper would tie two files
    that assert different things to one bank."""
    return {
        "b": {
            "daily_budget": n,
            "queries": [{"slug": f"s{i}", "query": f"q{i}", "location": "New York",
                         "mode": "nyc"} for i in range(n)],
        }
    }


def run_claim(conn, max_queries=1, **reported):
    """One claim against `conn`. `**reported` is what the worker sent with it.

    Deliberately the same shape as test_contributor_status's, and for the same
    reason bank_of() is: two files that assert different things about one
    endpoint, each holding its own two-line helper, rather than one shared
    helper tying them together.
    """
    restore = patch_db(app, conn)
    try:
        return app.claim(app.ClaimRequest(max=max_queries, **reported),
                         authorization="Bearer key")
    finally:
        restore()


class _SettingsCase(unittest.TestCase):

    def setUp(self):
        self._real = qc.load_query_buckets
        self.addCleanup(lambda: setattr(qc, "load_query_buckets", self._real))
        qc.load_query_buckets = lambda: bank_of(10)


class TestPause(_SettingsCase):

    def test_a_paused_contributor_is_granted_no_queries(self):
        conn = FakeConn(settings=(True, None, None))
        result = run_claim(conn, max_queries=5)
        self.assertEqual(result["queries"], [])
        self.assertEqual(conn.claimed, [],
                         "a paused contributor must not lock a row either")

    def test_a_paused_poll_is_answered_rather_than_refused(self):
        # The whole reason pause is not a 4xx. If this becomes an exception the
        # worker exits 1 and a paused machine is indistinguishable from a broken
        # one -- and there is no reply for T-35's check-in to ride on.
        conn = FakeConn(settings=(True, None, None))
        result = run_claim(conn)
        self.assertTrue(result["paused"])
        self.assertEqual(result["poll_interval_seconds"],
                         app.POLL_INTERVAL_SECONDS)

    def test_a_paused_poll_still_carries_the_cadence_that_can_unpause_it(self):
        # Pausing must not slow or stop the polling, because the poll is the
        # only channel a resume can arrive on. Asserted separately from the
        # field above because this is the property, not the field.
        conn = FakeConn(settings=(True, None, None))
        self.assertIn("poll_interval_seconds", run_claim(conn))

    def test_a_paused_poll_writes_no_submission_log_row(self):
        # It was granted nothing, so there is nothing to meter -- the same rule
        # a granted-nothing claim already follows. Metering it would make a
        # pause spend the allowance it exists to stop spending.
        conn = FakeConn(settings=(True, None, None))
        run_claim(conn)
        self.assertEqual(conn.log, [])

    def test_a_paused_poll_does_not_consume_the_query_bank(self):
        # Reading the bank before answering would turn a bank that fails to load
        # into a 500 for a contributor who was being told "not now" anyway.
        def explode():
            raise AssertionError("the query bank was opened for a paused poll")

        qc.load_query_buckets = explode
        run_claim(FakeConn(settings=(True, None, None)))

    def test_pause_does_not_answer_for_an_unauthenticated_caller(self):
        # Ordering: authenticate() first, so a revoked key is still a 401 rather
        # than a friendly "you are paused" to someone holding a dead credential.
        conn = FakeConn(settings=(True, None, None), revoked="2026-08-09T00:00:00")
        with self.assertRaises(HTTPException) as caught:
            run_claim(conn)
        self.assertEqual(caught.exception.status_code, 401)

    def test_an_unpaused_contributor_is_told_so_explicitly(self):
        # False rather than absent: the worker's `.get("paused")` has to be able
        # to tell a pause from an ordinary empty day.
        conn = FakeConn(settings=(False, None, None))
        self.assertIs(run_claim(conn)["paused"], False)

    def test_a_null_pause_is_not_paused(self):
        conn = FakeConn(settings=(None, None, None))
        self.assertIs(run_claim(conn)["paused"], False)


class TestTheDailyCap(_SettingsCase):

    def test_an_unset_cap_is_the_service_default(self):
        conn = FakeConn(settings=(None, None, None),
                        claim_rows_today=app.MAX_CLAIMS_PER_CONTRIBUTOR_PER_DAY)
        with self.assertRaises(HTTPException) as caught:
            run_claim(conn)
        self.assertEqual(caught.exception.status_code, 429)

    def test_a_per_contributor_cap_overrides_the_service_default(self):
        # Read from the constant, not spelled out: T-53 warns that a test here
        # hardcoding a number passes today and misleads after the cap moves.
        conn = FakeConn(settings=(None, 3, None), claim_rows_today=3)
        with self.assertRaises(HTTPException) as caught:
            run_claim(conn)
        self.assertEqual(caught.exception.status_code, 429)
        self.assertLess(3, app.MAX_CLAIMS_PER_CONTRIBUTOR_PER_DAY,
                        "this case only tests an override if 3 is below the "
                        "service default it is overriding")

    def test_a_cap_larger_than_the_default_is_honoured_too(self):
        # The direction that is easy to lose to a min() somewhere: a
        # per-contributor cap REPLACES the default, it does not cap it.
        cap = app.MAX_CLAIMS_PER_CONTRIBUTOR_PER_DAY + 2
        conn = FakeConn(settings=(None, cap, None),
                        claim_rows_today=app.MAX_CLAIMS_PER_CONTRIBUTOR_PER_DAY)
        result = run_claim(conn, max_queries=2)
        self.assertEqual(len(result["queries"]), 2)

    def test_a_cap_of_zero_grants_nothing_and_is_not_read_as_unset(self):
        # 0 and NULL are different facts, and a falsiness check would collapse
        # them into "use the default" -- which is the opposite of what 0 says.
        conn = FakeConn(settings=(None, 0, None))
        with self.assertRaises(HTTPException) as caught:
            run_claim(conn)
        self.assertEqual(caught.exception.status_code, 429)


class TestTheReserveFloor(_SettingsCase):
    """THE BOUNDARY THIS ROW IS SPECIFIED ON.

    A cap of 5 and a floor of 2 is an allowance of 3. Every test here is one
    step either side of that number.
    """

    CAP, FLOOR, ALLOWANCE = 5, 2, 3

    def _conn(self, used):
        return FakeConn(settings=(None, self.CAP, self.FLOOR),
                        claim_rows_today=used)

    def test_the_last_query_inside_the_allowance_is_granted(self):
        result = run_claim(self._conn(self.ALLOWANCE - 1), max_queries=1)
        self.assertEqual(len(result["queries"]), 1)

    def test_the_first_query_that_would_touch_the_reserve_is_refused(self):
        # AT the boundary, not one past it. With `>` in place of `>=` this
        # contributor is handed a fourth query and keeps 1 of a 2-credit
        # reserve.
        with self.assertRaises(HTTPException) as caught:
            run_claim(self._conn(self.ALLOWANCE))
        self.assertEqual(caught.exception.status_code, 429)

    def test_one_request_cannot_walk_through_the_reserve(self):
        # The other half of the same edge: the cap check passing does not mean
        # the whole request may be granted. Asking for the full cap when the
        # floor is 2 must return the allowance, not the cap -- this is what
        # goes wrong if `remaining` is computed from the cap after the check
        # subtracted the floor.
        result = run_claim(self._conn(0), max_queries=self.CAP)
        self.assertEqual(len(result["queries"]), self.ALLOWANCE)

    def test_a_floor_at_the_cap_grants_nothing(self):
        conn = FakeConn(settings=(None, self.CAP, self.CAP))
        with self.assertRaises(HTTPException) as caught:
            run_claim(conn)
        self.assertEqual(caught.exception.status_code, 429)

    def test_a_floor_above_the_cap_grants_nothing_rather_than_a_negative(self):
        # An operator and a Builder who disagree. A negative allowance would
        # reach pick_stale_queries_by_bucket as a negative max_queries, which
        # has no opinion about one.
        conn = FakeConn(settings=(None, self.CAP, self.CAP + 4))
        with self.assertRaises(HTTPException) as caught:
            run_claim(conn)
        self.assertEqual(caught.exception.status_code, 429)

    def test_the_floor_applies_to_the_service_default_cap_too(self):
        # A floor set on a contributor whose cap is unset still binds; it is not
        # a modifier that only exists alongside an explicit cap.
        floor = 2
        used = app.MAX_CLAIMS_PER_CONTRIBUTOR_PER_DAY - floor
        conn = FakeConn(settings=(None, None, floor), claim_rows_today=used)
        with self.assertRaises(HTTPException) as caught:
            run_claim(conn)
        self.assertEqual(caught.exception.status_code, 429)

    def test_an_unset_floor_reserves_nothing(self):
        conn = FakeConn(settings=(None, self.CAP, None),
                        claim_rows_today=self.CAP - 1)
        self.assertEqual(len(run_claim(conn)["queries"]), 1)

    def test_a_refused_claim_is_not_logged(self):
        # A refusal locked no row and cost nothing; logging it would meter a
        # contributor for being told no, and claims_today() would then count it.
        conn = self._conn(self.ALLOWANCE)
        with self.assertRaises(HTTPException):
            run_claim(conn)
        self.assertEqual(conn.log, [])


class TestTheAllowanceArithmetic(unittest.TestCase):
    """claim_allowance() alone -- no request, no bank, no database.

    It is pure for the reason score_job() is: the boundary above is worth being
    able to sweep without standing anything up.
    """

    def test_the_cap_is_the_allowance_when_nothing_is_reserved(self):
        settings = qc.ContributorSettings(False, 8, 0)
        self.assertEqual(qc.claim_allowance(settings, 50), 8)

    def test_the_default_is_used_only_when_the_cap_is_none(self):
        self.assertEqual(
            qc.claim_allowance(qc.ContributorSettings(False, None, 0), 50), 50)
        self.assertEqual(
            qc.claim_allowance(qc.ContributorSettings(False, 0, 0), 50), 0)

    def test_the_floor_comes_off_the_cap(self):
        self.assertEqual(
            qc.claim_allowance(qc.ContributorSettings(False, 8, 3), 50), 5)

    def test_the_floor_comes_off_the_default_cap_as_well(self):
        self.assertEqual(
            qc.claim_allowance(qc.ContributorSettings(False, None, 3), 50), 47)

    def test_it_never_returns_a_negative(self):
        self.assertEqual(
            qc.claim_allowance(qc.ContributorSettings(False, 2, 9), 50), 0)


class TestTheAllowanceAgainstAReportedBalance(unittest.TestCase):
    """claim_allowance() once a balance is in play (T-54). Still no I/O.

    `headroom` is what quota_headroom() decided the floor leaves of the
    contributor's own credits; None means it decided nothing usable had been
    reported, which is the case every test in the class above is in.
    """

    def test_a_reported_balance_replaces_the_cap_as_the_binding_number(self):
        # 4 credits above the floor, a cap of 8: the balance is what runs out
        # first and the allowance says so.
        settings = qc.ContributorSettings(False, 8, 2)
        self.assertEqual(qc.claim_allowance(settings, 50, headroom=4), 4)

    def test_the_cap_still_binds_when_the_balance_is_the_larger_number(self):
        # The operator's ceiling does not go away because a Builder is rich.
        settings = qc.ContributorSettings(False, 8, 2)
        self.assertEqual(qc.claim_allowance(settings, 50, headroom=400), 8)

    def test_the_floor_does_not_come_off_the_cap_as_well(self):
        # THE HEADLINE OF THIS ROW. The same settings that read as an allowance
        # of 6 with no balance read as the full cap once the floor has credits
        # of its own to bind against -- subtracting it in both places is the
        # double charge T-54 exists to remove, and it is invisible in every
        # test that does not compare the two readings directly.
        settings = qc.ContributorSettings(False, 8, 2)
        self.assertEqual(qc.claim_allowance(settings, 50), 6)
        self.assertEqual(qc.claim_allowance(settings, 50, headroom=400), 8)

    def test_what_is_already_spent_is_added_back_because_the_answer_is_a_total(self):
        # A balance is a level as of the moment it was reported and is already
        # net of what was spent before it; the allowance is a day TOTAL that
        # app.py subtracts `used` from again. So the two have to be added here
        # for `allowance - used` to land back on the headroom -- and that
        # subtraction is asserted, not just the sum, because dropping `used`
        # from this line passes every test that leaves it at 0.
        settings = qc.ContributorSettings(False, 50, 2)
        allowance = qc.claim_allowance(settings, 50, used=7, headroom=4)
        self.assertEqual(allowance, 11)
        self.assertEqual(allowance - 7, 4)

    def test_a_headroom_of_zero_is_an_allowance_of_what_is_already_spent(self):
        # Which app.py reads as `used >= allowance` and refuses. Not a negative
        # and not the cap: the contributor is AT their floor, and the day-total
        # they are allowed is exactly what they have already had.
        settings = qc.ContributorSettings(False, 50, 2)
        self.assertEqual(qc.claim_allowance(settings, 50, used=3, headroom=0), 3)

    def test_a_headroom_of_none_is_not_a_headroom_of_zero(self):
        # The distinction the fallback rests on. Nothing reported must not read
        # as nothing left, or a contributor whose first run has not finished is
        # refused on evidence that never arrived.
        settings = qc.ContributorSettings(False, 8, 2)
        self.assertEqual(qc.claim_allowance(settings, 50, headroom=0), 0)
        self.assertEqual(qc.claim_allowance(settings, 50, headroom=None), 6)


class TestTheHeadroomAReportedBalanceLeaves(unittest.TestCase):
    """quota_headroom() alone: what the floor permits, and what it disbelieves.

    Pure, and that is what lets the staleness edge be tested at all -- a request
    path test cannot put a clock on a report it did not write.
    """

    #: One clock for every case in this class. Two `datetime.now()` calls a few
    #: microseconds apart would not fail these, which is exactly the problem:
    #: the bug that shape hides is the one where a cutoff and a report come from
    #: different instants, and a test that cannot express it cannot pin it.
    NOW = datetime(2026, 8, 9, 12, 0, 0, tzinfo=timezone.utc)
    INTERVAL = 3600

    def _fresh_since(self):
        return qc.quota_fresh_since(self.INTERVAL, self.NOW)

    def _reported(self, remaining, ago_seconds=0):
        at = (self.NOW - timedelta(seconds=ago_seconds)).strftime(
            "%Y-%m-%dT%H:%M:%S")
        return qc.ReportedQuota(remaining, at)

    def test_the_floor_comes_off_the_reported_balance(self):
        self.assertEqual(
            qc.quota_headroom(self._reported(10), 2, self._fresh_since()), 8)

    def test_a_balance_exactly_at_the_floor_leaves_nothing(self):
        # The boundary, and it is the reserve's whole point: the credit that
        # would take them below the floor is not granted, not granted-and-then
        # -refused.
        self.assertEqual(
            qc.quota_headroom(self._reported(2), 2, self._fresh_since()), 0)

    def test_a_balance_under_the_floor_is_zero_and_not_a_negative(self):
        # Reachable without anything being wrong: a floor raised after the
        # credits were already spent.
        self.assertEqual(
            qc.quota_headroom(self._reported(1), 2, self._fresh_since()), 0)

    def test_a_negative_balance_is_believed_and_bottoms_out_at_zero(self):
        # record_check_in stores a nonsensical number rather than dropping it,
        # on the argument that it is evidence about that worker. Here it simply
        # means there is nothing above the floor, which is the right reading of
        # it whether the worker is honest or broken.
        self.assertEqual(
            qc.quota_headroom(self._reported(-5), 2, self._fresh_since()), 0)

    def test_no_floor_leaves_the_whole_balance(self):
        self.assertEqual(
            qc.quota_headroom(self._reported(10), 0, self._fresh_since()), 10)

    def test_nothing_reported_is_none_and_not_zero(self):
        self.assertIsNone(
            qc.quota_headroom(qc.ReportedQuota(None, None), 2,
                              self._fresh_since()))

    def test_a_balance_with_no_timestamp_is_refused_rather_than_dated(self):
        # record_check_in binds the two together, so this pair is a row this
        # service did not write. The two candidate readings are both wrong:
        # the check-in's time is what the separate column exists to avoid, and
        # `now` would make an unknown age look like the freshest possible.
        self.assertIsNone(
            qc.quota_headroom(qc.ReportedQuota(10, None), 2,
                              self._fresh_since()))

    def test_a_timestamp_with_no_balance_reports_nothing(self):
        self.assertIsNone(
            qc.quota_headroom(qc.ReportedQuota(None, "2026-08-09T11:59:00"), 2,
                              self._fresh_since()))

    def test_a_balance_from_one_interval_ago_is_still_believed(self):
        # The ordinary case for a working machine: it reports on the poll after
        # a run finishes, so the freshest a balance is ever seen is one interval
        # old. A window that excluded this would never bind on anybody.
        self.assertEqual(
            qc.quota_headroom(self._reported(10, ago_seconds=self.INTERVAL), 2,
                              self._fresh_since()), 8)

    def test_a_balance_older_than_the_window_is_not_read_at_all(self):
        # A worker whose SerpApi key died reports an ERROR on every poll and a
        # balance never, so its check-in stays current while this number rots.
        # Reading it anyway is what makes a floor bind against a week-old level.
        self.assertIsNone(
            qc.quota_headroom(
                self._reported(10, ago_seconds=self.INTERVAL * 3), 2,
                self._fresh_since()))

    def test_the_window_is_more_than_a_single_interval(self):
        # Not the number, the property: at exactly one interval every cron's
        # ordinary jitter would put half the fleet on the stale side of the
        # line, and staleness would then be a report about scheduling noise.
        self.assertGreater(qc.QUOTA_STALE_AFTER_POLLS, 1)

    def test_the_cutoff_is_written_in_the_format_the_column_holds(self):
        # The comparison is `<` on TEXT. It is only meaningful if both sides
        # are the same fixed-width, offset-free shape -- a cutoff carrying
        # microseconds or a `+00:00` would sort against the stored value in
        # ways that have nothing to do with time.
        cutoff = qc.quota_fresh_since(self.INTERVAL, self.NOW)
        self.assertRegex(cutoff, r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}$")
        self.assertEqual(len(cutoff), len(qc.utc_now_str()))
        self.assertLess(cutoff, qc.utc_now_str())


class TestTheFloorAgainstAReportedBalance(_SettingsCase):
    """The whole path, through `claim`: settings, a stored report, one answer.

    THE FIXTURE IS CHOSEN SO THE TWO READINGS DIFFER. A cap of 5, a floor of 2
    and a balance of 10 is an allowance of 5 under the balance reading and 3
    under the fallback, so every test below can only pass under one of them --
    numbers where they coincide would let a wiring mistake through silently.
    """

    CAP, FLOOR, BALANCE = 5, 2, 10
    FALLBACK = 3

    def _conn(self, quota=(None, None), used=0):
        return FakeConn(settings=(None, self.CAP, self.FLOOR),
                        claim_rows_today=used, quota=quota)

    def _stored(self, remaining, ago_seconds=0):
        """A balance already in contributor_status, aged off THIS test's clock.

        Not a frozen literal: the request under test compares against
        `datetime.now()`, so a fixture with a hardcoded date would drift from
        fresh to stale as the calendar moved and would pass for years first.
        """
        at = (datetime.now(timezone.utc) - timedelta(seconds=ago_seconds)
              ).strftime("%Y-%m-%dT%H:%M:%S")
        return (remaining, at)

    def test_a_fresh_balance_leaves_the_cap_whole(self):
        result = run_claim(self._conn(self._stored(self.BALANCE)),
                           max_queries=self.CAP)
        self.assertEqual(len(result["queries"]), self.CAP)

    def test_the_same_contributor_falls_back_when_the_report_is_old(self):
        stale = self._stored(self.BALANCE,
                             ago_seconds=app.POLL_INTERVAL_SECONDS
                             * (qc.QUOTA_STALE_AFTER_POLLS + 1))
        result = run_claim(self._conn(stale), max_queries=self.CAP)
        self.assertEqual(len(result["queries"]), self.FALLBACK)

    def test_a_contributor_who_has_never_reported_falls_back(self):
        # The state every Builder is in between opting in and their first
        # completed run, and the one that must not be answered with a refusal.
        result = run_claim(self._conn(), max_queries=self.CAP)
        self.assertEqual(len(result["queries"]), self.FALLBACK)

    def test_a_missing_status_row_falls_back_rather_than_raising(self):
        # Unreachable through `claim`, which checks in first -- but reported_
        # quota() is what makes it unreachable-and-harmless rather than a 500.
        result = run_claim(self._conn(quota=None), max_queries=self.CAP)
        self.assertEqual(len(result["queries"]), self.FALLBACK)

    def test_a_balance_at_the_floor_is_refused(self):
        # STILL REFUSED, AND THE SHAPE OF THE REFUSAL MOVED IN T-57. This was a
        # 429 until a Builder at their floor became the ordinary case rather
        # than an operator/Builder disagreement -- `daily limit reached (0/0)`
        # named a cap nobody set, and a 4xx made the worker exit 1 hourly for a
        # state it was correctly in. The boundary this asserts is T-54's and is
        # unchanged: a balance AT the floor buys nothing.
        result = run_claim(self._conn(self._stored(self.FLOOR)))
        self.assertEqual(result["queries"], [])
        self.assertIs(result["reserve_reached"], True)
        self.assertIs(result["paused"], False)

    def test_the_last_credit_above_the_floor_is_granted(self):
        # One either side of the boundary, so a `<` for `<=` in the headroom
        # cannot pass both this and the case above.
        result = run_claim(self._conn(self._stored(self.FLOOR + 1)),
                           max_queries=self.CAP)
        self.assertEqual(len(result["queries"]), 1)

    def test_the_balance_reported_by_this_very_poll_is_the_one_that_binds(self):
        # The real sequence, and the reason record_check_in() commits before
        # anything reads it back: the worker reports its credits on the poll,
        # and the floor binds against THAT number rather than against whatever
        # was stored an hour ago. Here the stored balance would have granted
        # the full cap and the reported one grants nothing.
        conn = self._conn(self._stored(self.BALANCE))
        result = run_claim(conn, max_queries=self.CAP,
                           quota_remaining=self.FLOOR)
        self.assertEqual(result["queries"], [])
        self.assertIs(result["reserve_reached"], True)
        self.assertEqual(conn.check_ins[0]["quota_remaining"], self.FLOOR)

    def test_a_poll_reporting_no_balance_leaves_the_stored_one_binding(self):
        # The COALESCE half of the same sequence: a run that produced nothing
        # to report must not blank the balance the floor is reading.
        conn = self._conn(self._stored(self.BALANCE))
        result = run_claim(conn, max_queries=self.CAP, worker_version="w/1.1")
        self.assertEqual(len(result["queries"]), self.CAP)

    def test_what_is_already_spent_still_counts_against_the_cap(self):
        # A rich balance does not un-spend the day. Four of the cap of 5 are
        # gone, so one is left however many credits the Builder has.
        result = run_claim(
            self._conn(self._stored(self.BALANCE), used=self.CAP - 1),
            max_queries=self.CAP)
        self.assertEqual(len(result["queries"]), 1)

    def test_the_two_refusals_are_different_answers(self):
        # THE ROW ITSELF (T-57). One contributor is out of credits and one has
        # spent the operator's daily cap; before this they were the same 429
        # saying the same thing, and only one of them clears at midnight. Both
        # fixtures are refused -- the assertion is that they are refused
        # differently, so a Builder and an operator can tell which is which.
        credits = run_claim(self._conn(self._stored(self.FLOOR)))
        self.assertIs(credits["reserve_reached"], True)

        with self.assertRaises(HTTPException) as caught:
            run_claim(self._conn(self._stored(self.BALANCE), used=self.CAP))
        self.assertEqual(caught.exception.status_code, 429)
        self.assertIn("daily limit reached", caught.exception.detail)

    def test_a_contributor_who_never_reported_is_not_told_they_are_out(self):
        # The distinction quota_headroom() keeps and this branch inherits: None
        # is "nothing usable was reported", not "reported zero". A Builder
        # between opting in and their first completed run must never be told
        # they have spent credits they have not spent -- they fall back to the
        # cap reading, and are refused (if at all) as a cap.
        used = self.CAP  # spent out under the fallback, with no balance at all
        with self.assertRaises(HTTPException) as caught:
            run_claim(self._conn(used=used))
        self.assertEqual(caught.exception.status_code, 429)

    def test_the_flag_is_false_rather_than_absent_on_an_ordinary_reply(self):
        # The same argument `paused` is carried by: "at the reserve floor" and
        # "nothing stale right now" are both an empty list, so a key that
        # appeared only when true would leave a worker unable to tell them
        # apart -- and a granting reply is where that is cheapest to assert.
        result = run_claim(self._conn(self._stored(self.BALANCE)),
                           max_queries=1)
        self.assertIs(result["reserve_reached"], False)

    def test_a_refusal_on_the_floor_locks_nothing_and_logs_nothing(self):
        # THE PROPERTY THAT SURVIVED THE 200 (T-57), and the reason it is worth
        # re-asserting rather than deleting: a refusal that returns instead of
        # raising no longer gets `with conn:`'s rollback for free, so "granted
        # nothing" now has to be true because the branch is above the query bank
        # rather than because an exception undid it.
        conn = self._conn(self._stored(self.FLOOR))
        result = run_claim(conn)
        self.assertEqual(result["queries"], [])
        self.assertEqual(conn.log, [])
        self.assertEqual(conn.claimed, [])


class TestReadingTheSettings(unittest.TestCase):

    def test_all_null_is_the_default_for_every_setting(self):
        conn = FakeConn(settings=(None, None, None))
        self.assertEqual(qc.contributor_settings(conn, "c_test"),
                         qc.ContributorSettings(False, None,
                                                qc.DEFAULT_RESERVE_FLOOR))

    def test_a_missing_contributor_row_reads_as_the_defaults(self):
        # Unreachable behind authenticate()'s foreign key, and behaving like the
        # ordinary no-policy case rather than raising is what keeps it that way.
        conn = FakeConn(settings=None)
        self.assertEqual(qc.contributor_settings(conn, "c_ghost"),
                         qc.ContributorSettings(False, None,
                                                qc.DEFAULT_RESERVE_FLOOR))

    def test_values_come_back_in_the_order_the_columns_are_declared(self):
        # A transposition of daily_cap and reserve_floor is silent in every
        # other test in this file, because both are ints and both shrink an
        # allowance. Here the two differ.
        conn = FakeConn(settings=(True, 7, 1))
        self.assertEqual(qc.contributor_settings(conn, "c_test"),
                         qc.ContributorSettings(True, 7, 1))


class TestTheColumnsAgree(unittest.TestCase):
    """One list of names, four places that have to spell it identically.

    The DDL that creates the columns, the map that requires them at startup, the
    SELECT that reads them and the tuple that unpacks them. Three of the four
    are derived from CONTRIBUTOR_SETTING_COLUMNS; the SELECT is written out,
    because its column ORDER is what the NamedTuple unpacks positionally and a
    generated list would make that order invisible. So it is checked instead.
    """

    def _source(self):
        with open(os.path.join(API_DIR, "query_claims.py"), encoding="utf-8") as fh:
            return fh.read()

    def test_the_required_columns_are_the_declared_ones(self):
        self.assertEqual(qc.REQUIRED_COLUMNS["contributors"],
                         qc.CONTRIBUTOR_SETTINGS)

    def test_the_ddl_declares_exactly_the_three_settings(self):
        self.assertEqual(qc.CONTRIBUTOR_SETTINGS,
                         ("paused", "daily_cap", "reserve_floor"))

    def test_the_select_names_the_declared_columns_in_the_declared_order(self):
        selected = re.search(
            r"SELECT ([a-z_, ]+) FROM contributors WHERE id = %s", self._source())
        self.assertIsNotNone(
            selected, "contributor_settings()'s SELECT has moved or been "
                      "rewritten; this check is unanchored")
        self.assertEqual(tuple(c.strip() for c in selected.group(1).split(",")),
                         qc.CONTRIBUTOR_SETTINGS)

    def test_the_named_tuple_fields_match_the_columns(self):
        # The positional unpack in contributor_settings() means a field renamed
        # on one side and not the other silently returns the wrong value under
        # the right name.
        self.assertEqual(qc.ContributorSettings._fields, qc.CONTRIBUTOR_SETTINGS)

    def test_the_settings_columns_are_added_to_an_existing_table(self):
        # Not in contributors' CREATE TABLE, deliberately: they arrive by
        # add_missing_columns, which is what makes them able to go missing on
        # their own and therefore what puts them in REQUIRED_COLUMNS. If a
        # future edit folds them into the CREATE TABLE, the REQUIRED_COLUMNS
        # entry becomes the dead weight its own docstring rules out.
        source = self._source()
        create = re.search(r"CREATE TABLE IF NOT EXISTS contributors \((.*?)\)",
                           source, re.S)
        self.assertIsNotNone(create, "contributors' CREATE TABLE has moved")
        for column in qc.CONTRIBUTOR_SETTINGS:
            self.assertNotIn(column, create.group(1))
        self.assertIn("add_missing_columns(conn, \"contributors\"", source)


@contextlib.contextmanager
def quiet():
    """cmd_settings reports to a human on stdout/stderr; a suite is not one."""
    with contextlib.redirect_stdout(io.StringIO()), \
            contextlib.redirect_stderr(io.StringIO()):
        yield


class _FakeCursor:
    def __init__(self, rowcount=1, row=None):
        self.rowcount = rowcount
        self._row = row

    def fetchone(self):
        return self._row


class _FakeAdminConn:
    """manage_users.connect()'s result, reduced to what cmd_settings uses.

    Deliberately NOT fakedb.FakeConn: that one is documented as enough of a
    connection for one request against app.py, and it raises on SQL it does not
    recognise so that a new statement in a request path arrives as a test error.
    An admin command's UPDATE is not a request path, and widening that fake to
    accept one would blunt the property it exists to hold.
    """

    def __init__(self, row=(True, 8, 2), rowcount=1):
        self.statements = []
        self.params = []
        self.row = row
        self.rowcount = rowcount
        self.admin = None

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def execute(self, sql, params=()):
        self.statements.append(" ".join(sql.split()))
        self.params.append(params)
        if sql.strip().upper().startswith("SELECT"):
            return _FakeCursor(row=self.row)
        return _FakeCursor(rowcount=self.rowcount)

    def commit(self):
        pass


class _Args:
    def __init__(self, **kw):
        self.contributor = "c_test"
        self.paused = None
        self.daily_cap = None
        self.reserve_floor = None
        self.__dict__.update(kw)


class TestTheSettingsCommand(unittest.TestCase):
    """manage_users.py settings -- the only writer these three columns have.

    Settings nothing can set are not settings, so the command is part of this
    row rather than a follow-up. What is asserted here is the two decisions in
    it: which credential it opens, and which columns one invocation writes.

    NOT ASSERTED HERE, and stated rather than left as a gap: the UPDATE itself
    never runs against Postgres in this suite, because no test in this package
    has a database. The statement's shape is checked; its effect is not.
    """

    def _run(self, **kw):
        import manage_users

        conn = _FakeAdminConn()
        opened = []
        original = manage_users.connect
        manage_users.connect = lambda admin=False: (opened.append(admin), conn)[1]
        try:
            with quiet():
                manage_users.cmd_settings(_Args(**kw))
        finally:
            manage_users.connect = original
        return conn, opened

    def test_it_opens_the_admin_credential_and_not_the_service_one(self):
        # The reason these columns are not writable by `jobs_api`: the role that
        # faces contributors' machines must not be able to rewrite the policy
        # that governs them. If this flips to the restricted URL, a compromised
        # app.py can un-pause itself.
        _, opened = self._run(paused=True)
        self.assertTrue(all(opened), "cmd_settings opened a non-admin connection")

    def test_only_the_flags_that_were_passed_are_written(self):
        # Three settings on one row: the obvious implementation writes all three
        # every time, so `settings --paused` would silently reset a cap somebody
        # set last week.
        conn, _ = self._run(paused=True)
        update = next(s for s in conn.statements if s.startswith("UPDATE"))
        self.assertIn("paused = %s", update)
        self.assertNotIn("daily_cap", update)
        self.assertNotIn("reserve_floor", update)

    def test_several_flags_at_once_are_one_statement(self):
        conn, _ = self._run(paused=False, daily_cap="8", reserve_floor="2")
        updates = [s for s in conn.statements if s.startswith("UPDATE")]
        self.assertEqual(len(updates), 1)
        self.assertEqual(conn.params[0][:3], (False, 8, 2))

    def test_clear_writes_a_null_rather_than_a_zero(self):
        # 0 is a meaningful cap -- spend nothing -- so a sentinel of 0 for
        # "clear" would make it unreachable.
        conn, _ = self._run(daily_cap="clear")
        self.assertEqual(conn.params[0][0], None)

    def test_a_zero_is_kept_as_a_zero(self):
        conn, _ = self._run(daily_cap="0")
        self.assertEqual(conn.params[0][0], 0)

    def test_an_unknown_contributor_exits_nonzero(self):
        import manage_users

        conn = _FakeAdminConn(rowcount=0)
        original = manage_users.connect
        manage_users.connect = lambda admin=False: conn
        try:
            with self.assertRaises(SystemExit) as caught, quiet():
                manage_users.cmd_settings(_Args(paused=True))
        finally:
            manage_users.connect = original
        self.assertNotEqual(caught.exception.code, 0)

    def test_no_flags_at_all_exits_nonzero_and_writes_nothing(self):
        import manage_users

        conn = _FakeAdminConn()
        original = manage_users.connect
        manage_users.connect = lambda admin=False: conn
        try:
            with self.assertRaises(SystemExit), quiet():
                manage_users.cmd_settings(_Args())
        finally:
            manage_users.connect = original
        self.assertEqual(conn.statements, [])


@requires_db
class TestAgainstARealDatabase(unittest.TestCase):
    """The claims a fake cannot make: the DDL runs, the migration runs on a table
    that already exists, and verify_schema() sees a missing column.

    THE FIXTURE IS IMPORTED, NOT COPIED. `test_claim_protocol.api_scratch_schema`
    already knows the one subtlety that makes this work -- `qc.ensure_schema`
    opens with `SET search_path TO public` and is saved by `schema.ensure_schema`
    resetting it to the scratch name on the very next line -- and a second copy
    would be two fixtures that have to agree about that with nothing making them.
    Its `requires_db` skips where no scratch database is reachable, and so does
    this; read `Ran N tests`, because a skip here is not a pass.
    """

    schema = staticmethod(api_scratch_schema)

    def _columns(self, conn):
        return {r[0] for r in conn.execute(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name = 'contributors' "
            "AND table_schema = current_schema()").fetchall()}

    def test_ensure_schema_creates_the_three_settings_columns(self):
        with self.schema() as (conn, _):
            self.assertTrue(set(qc.CONTRIBUTOR_SETTINGS) <= self._columns(conn))

    def test_they_are_added_to_a_contributors_table_that_already_lacks_them(self):
        # THE MIGRATION, which is the case REQUIRED_COLUMNS exists for and the
        # one a fresh CREATE TABLE cannot exercise: an existing deployment has
        # the table without the columns, and add_missing_columns has to be what
        # closes that gap rather than the CREATE.
        with self.schema() as (conn, _):
            for column in qc.CONTRIBUTOR_SETTINGS:
                conn.execute(f"ALTER TABLE contributors DROP COLUMN {column}")
            conn.commit()
            self.assertFalse(set(qc.CONTRIBUTOR_SETTINGS) & self._columns(conn))
            qc.ensure_schema(conn)
            self.assertTrue(set(qc.CONTRIBUTOR_SETTINGS) <= self._columns(conn))

    def test_running_it_twice_adds_nothing_and_raises_nothing(self):
        with self.schema() as (conn, _):
            qc.ensure_schema(conn)
            self.assertTrue(set(qc.CONTRIBUTOR_SETTINGS) <= self._columns(conn))

    def test_a_freshly_minted_contributor_has_no_policy(self):
        with self.schema() as (conn, _):
            cid, _key, _hash, _at = qc.mint_credential(conn, "Dave")
            conn.commit()
            self.assertEqual(qc.contributor_settings(conn, cid),
                             qc.ContributorSettings(False, None,
                                                    qc.DEFAULT_RESERVE_FLOOR))

    def test_the_settings_command_s_update_actually_writes_them(self):
        # The statement cmd_settings builds, run for real. The fake upstairs
        # pins which columns it names; this pins that Postgres accepts it and
        # that contributor_settings() reads back what it wrote -- including the
        # BOOLEAN/INTEGER types, which a TEXT column would also have passed.
        with self.schema() as (conn, _):
            cid, _key, _hash, _at = qc.mint_credential(conn, "Dave")
            conn.execute(
                "UPDATE contributors SET paused = %s, daily_cap = %s, "
                "reserve_floor = %s WHERE id = %s", (True, 8, 2, cid))
            conn.commit()
            self.assertEqual(qc.contributor_settings(conn, cid),
                             qc.ContributorSettings(True, 8, 2))

    def test_a_contributor_who_has_never_polled_has_reported_no_balance(self):
        # The missing-row branch, against a real table rather than a fake that
        # was told to return nothing.
        with self.schema() as (conn, _):
            cid, _key, _hash, _at = qc.mint_credential(conn, "Dave")
            conn.commit()
            self.assertEqual(qc.reported_quota(conn, cid),
                             qc.ReportedQuota(None, None))

    def test_a_check_in_that_reported_nothing_leaves_the_balance_unreported(self):
        # A row EXISTS and its quota columns are NULL, which the fake upstairs
        # cannot distinguish from no row at all and Postgres can.
        with self.schema() as (conn, _):
            cid, _key, _hash, _at = qc.mint_credential(conn, "Dave")
            conn.commit()
            qc.record_check_in(conn, cid, worker_version="w/1.1")
            self.assertEqual(qc.reported_quota(conn, cid),
                             qc.ReportedQuota(None, None))

    def test_the_balance_reads_back_as_an_int_beside_its_own_timestamp(self):
        # What record_check_in() wrote, read by the function the floor calls.
        # The INTEGER round-trip is the part a TEXT column would also have
        # passed and quota_headroom()'s subtraction would then have failed on.
        with self.schema() as (conn, _):
            cid, _key, _hash, _at = qc.mint_credential(conn, "Dave")
            conn.commit()
            qc.record_check_in(conn, cid, quota_remaining=40)
            quota = qc.reported_quota(conn, cid)
            self.assertEqual(quota.remaining, 40)
            self.assertIsInstance(quota.remaining, int)
            self.assertEqual(qc.quota_headroom(quota, 2, "1970-01-01T00:00:00"),
                             38)

    def test_the_timestamp_read_back_is_comparable_to_the_cutoff(self):
        # THE CLAIM THE WHOLE STALENESS BRANCH RESTS ON, and the only one a
        # fake cannot make: what Postgres hands back for this column is a
        # string in utc_now_str()'s format, so `<` against quota_fresh_since()
        # is a comparison about time. A column that came back as a datetime, or
        # with an offset appended, would compare -- just not meaningfully.
        with self.schema() as (conn, _):
            cid, _key, _hash, _at = qc.mint_credential(conn, "Dave")
            conn.commit()
            qc.record_check_in(conn, cid, quota_remaining=40)
            reported_at = qc.reported_quota(conn, cid).reported_at
            self.assertIsInstance(reported_at, str)
            self.assertRegex(reported_at,
                             r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}$")
            now = datetime.now(timezone.utc)
            self.assertGreater(
                reported_at, qc.quota_fresh_since(3600, now),
                "a balance written moments ago must read as fresh")
            self.assertLess(
                reported_at,
                qc.quota_fresh_since(3600, now + timedelta(days=1)),
                "and as stale once the cutoff has moved past it")

    def test_a_later_report_is_what_the_floor_reads(self):
        # The UPSERT in place, from the floor's end: two runs, and the second
        # balance is the one the reserve binds against.
        with self.schema() as (conn, _):
            cid, _key, _hash, _at = qc.mint_credential(conn, "Dave")
            conn.commit()
            qc.record_check_in(conn, cid, quota_remaining=40)
            qc.record_check_in(conn, cid, quota_remaining=3)
            self.assertEqual(qc.reported_quota(conn, cid).remaining, 3)

    # NO verify_schema() TEST HERE, AND THE REASON IS NOT "IT IS AWKWARD".
    # Its column loop is hardcoded to `public` (query_claims.py:550, :555),
    # deliberately -- this service only ever runs there -- so under a scratch
    # schema it answers about `public.contributors` no matter which connection
    # it is handed. Both directions are therefore untestable from this fixture,
    # and the version of this test written first PASSED WITHOUT THE DROP,
    # reporting `public`'s state as if it were the scratch schema's. A test that
    # passes for the wrong reason is worse than the gap, so this is the gap,
    # named. What is checked instead is that REQUIRED_COLUMNS carries the three
    # (TestTheColumnsAgree) and that ensure_schema puts them there (above),
    # which are the two halves verify_schema joins.

class TestTheWorkerReportsThePauseAndDecidesNothing(unittest.TestCase):
    """The worker's side, read from its source.

    T-34's premise is that the worker holds no policy of its own beyond T-31's
    clamp. It is told `paused` so that a Builder can tell a paused machine from
    a broken one, and told neither number, because a number it could act on is a
    number it could disagree with the server about.
    """

    WORKER = os.path.join(API_DIR, "contributor-worker",
                          "google-serpapi-worker.py")

    def _source(self):
        self.assertTrue(os.path.exists(self.WORKER),
                        f"{self.WORKER} is gone; this contract has no other side")
        with open(self.WORKER, encoding="utf-8") as fh:
            return fh.read()

    def test_the_worker_reads_the_paused_flag(self):
        self.assertIn('claimed.get("paused")', self._source())

    def test_the_worker_never_reads_the_two_numbers(self):
        # The assertion that keeps decision 3 true. If the worker starts reading
        # a cap or a floor, the contributor's machine has an opinion about how
        # much to spend, and a paused contributor's machine will disagree with
        # the server -- which is the sentence T-34 exists to keep false.
        source = self._source()
        for setting in ("daily_cap", "reserve_floor"):
            self.assertNotIn(setting, source)


if __name__ == "__main__":
    unittest.main()

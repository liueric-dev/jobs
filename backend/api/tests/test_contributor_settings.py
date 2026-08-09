"""T-34: the server holds desired state, and the worker holds none of it.

`docs/adr/0007` decision 3 gives this service three settings per contributor --
paused, a daily cap, a reserve floor -- and the reason they are here rather than
on the contributor's machine is that a machine's copy is a second source of
truth that a paused contributor's machine will disagree with. So every assertion
below is about what `claim` decides, not about what a worker does with the
answer.

THE TWO EDGES THIS FILE EXISTS FOR:

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


def run_claim(conn, max_queries=1):
    restore = patch_db(app, conn)
    try:
        return app.claim(app.ClaimRequest(max=max_queries),
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

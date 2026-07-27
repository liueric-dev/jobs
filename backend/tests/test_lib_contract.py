"""Behavioural contract for the parts of lib/ that nothing else pins.

WHY THIS FILE EXISTS

`lib/` used to be a shared package and is now this repo's own code (see
lib/__init__.py). Code an application owns outright is code that can be
quietly rewritten, and the cost of that is not obvious from reading it.

For anything that feeds a stored digest, tests/test_row_identity.py handles
this by pinning literal outputs, so drift fails loudly. But `http.py`,
`state.py` and several functions in `dbconn.py` and `upsert.py` reach no
stored digest and had NO tests at all.

So this file is a specification. Every assertion below is about this code
alone: what these functions must do for this pipeline to be correct, stated
so that a rewrite, a "tidy-up", or a change that looked harmless has
something to fail against. Nothing here consults another repo or assumes one
exists.

WHAT IS DELIBERATELY NOT ASSERTED
    Exact log wording, backoff jitter values, and anything cosmetic. This
    pins behaviour that a caller depends on, not implementation detail --
    over-specifying is how a contract test becomes something people delete.
"""

import io
import sys, os
import unittest
import urllib.error
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lib import dbconn, http, state, timeparse, upsert  # noqa: E402


# --------------------------------------------------------------------------
# http.py -- the retry/permanent distinction
# --------------------------------------------------------------------------

def _http_error(code, retry_after=None):
    hdrs = {"Retry-After": retry_after} if retry_after else {}
    return urllib.error.HTTPError("http://x", code, "err", hdrs, None)


class _Resp(io.BytesIO):
    """Minimal context-manager response."""
    def __enter__(self): return self
    def __exit__(self, *a): return False


class TestHttpRetryPolicy(unittest.TestCase):
    """The one distinction this module exists to make.

    Transient failures (network error, 429, 5xx) back off and retry;
    permanent ones (401, 400, 404) raise immediately. Retrying a permanent
    failure burns wall-clock and, on a metered key, real API quota with no
    possibility of succeeding.
    """

    def _fetch(self, side_effect, **kw):
        with mock.patch("urllib.request.urlopen", side_effect=side_effect) as m, \
             mock.patch("time.sleep"):                      # no real waiting
            with mock.patch("sys.stderr", io.StringIO()):   # no retry noise
                try:
                    return http.get_text("http://x", **kw), m.call_count
                except Exception as e:
                    return e, m.call_count

    def test_permanent_status_is_not_retried(self):
        for code in (400, 401, 403, 404):
            result, calls = self._fetch(_http_error(code))
            self.assertIsInstance(result, urllib.error.HTTPError)
            self.assertEqual(calls, 1,
                             f"HTTP {code} was retried; permanent failures "
                             f"must surface immediately")

    def test_transient_status_is_retried_to_the_limit(self):
        for code in (429, 500, 503):
            result, calls = self._fetch(_http_error(code), max_retries=4)
            self.assertIsInstance(result, urllib.error.HTTPError)
            self.assertEqual(calls, 4, f"HTTP {code} should have been retried")

    def test_network_errors_are_transient(self):
        for exc in (urllib.error.URLError("boom"), TimeoutError(),
                    ConnectionResetError()):
            _, calls = self._fetch(exc, max_retries=3)
            self.assertEqual(calls, 3)

    def test_success_after_a_transient_failure_returns_the_body(self):
        result, calls = self._fetch([_http_error(503), _Resp(b"payload")])
        self.assertEqual(result, "payload")
        self.assertEqual(calls, 2)

    def test_body_is_transient_makes_a_200_retryable(self):
        """Some upstreams reject with HTTP 200 and an error page. Status
        codes alone cannot see that, so the predicate must be honoured."""
        result, calls = self._fetch(
            [_Resp(b"Request Rejected"), _Resp(b"Request Rejected"),
             _Resp(b"real data")],
            body_is_transient=lambda b: "Request Rejected" in b)
        self.assertEqual(result, "real data")
        self.assertEqual(calls, 3)

    def test_body_predicate_absent_means_200_is_final(self):
        result, calls = self._fetch([_Resp(b"Request Rejected")])
        self.assertEqual(result, "Request Rejected")
        self.assertEqual(calls, 1)


class TestHttpBackoff(unittest.TestCase):
    def test_grows_and_is_capped(self):
        self.assertLess(http._backoff(0), http._backoff(6))
        self.assertLessEqual(http._backoff(30), http.MAX_BACKOFF)

    def test_retry_after_raises_but_never_lowers_the_wait(self):
        """A server asking for longer is obeyed; one asking for shorter is
        not, or a 429 storm would be answered as fast as the server invites."""
        self.assertGreaterEqual(http._backoff(1, retry_after="45"), 45)
        self.assertGreaterEqual(http._backoff(5, retry_after="1"),
                                2 ** 5)

    def test_garbage_retry_after_is_ignored_not_fatal(self):
        self.assertGreater(http._backoff(1, retry_after="soon"), 0)


class TestHttpJsonHelpers(unittest.TestCase):
    def test_get_json_parses(self):
        with mock.patch("urllib.request.urlopen",
                        return_value=_Resp(b'{"a": 1}')):
            self.assertEqual(http.get_json("http://x"), {"a": 1})

    def test_post_json_sends_a_body_and_sets_the_method(self):
        captured = {}

        def fake(req, timeout=None):
            captured["method"] = req.method
            captured["data"] = req.data
            captured["ctype"] = req.headers.get("Content-type")
            return _Resp(b'{"ok": true}')

        with mock.patch("urllib.request.urlopen", side_effect=fake):
            self.assertEqual(http.post_json("http://x", {"q": 1}), {"ok": True})
        self.assertEqual(captured["method"], "POST")
        self.assertEqual(captured["data"], b'{"q": 1}')
        self.assertEqual(captured["ctype"], "application/json")


# --------------------------------------------------------------------------
# dbconn.py -- the lock-avoidance contract
# --------------------------------------------------------------------------

class _Conn:
    """Records SQL, answers the information_schema probe from `present`."""

    def __init__(self, present=()):
        self.present = set(present)
        self.sql = []
        self.params = []
        self.commits = 0

    def execute(self, sql, params=None):
        self.sql.append(sql)
        self.params.append(params)
        self._last = sql
        return self

    def fetchall(self):
        if "information_schema.columns" in self._last:
            return [(c,) for c in self.present]
        return []

    def fetchone(self):
        return None

    def commit(self):
        self.commits += 1


class TestAddMissingColumns(unittest.TestCase):
    """The steady-state path must issue NO DDL.

    `ADD COLUMN IF NOT EXISTS` looks idempotent and free. It is not: Postgres
    takes an ACCESS EXCLUSIVE lock to evaluate it even when nothing changes,
    and a *pending* exclusive lock queues ahead of new readers -- so issuing
    it every run means any long-lived transaction elsewhere can block the
    whole table. This is not theoretical; it happened, behind a connection
    left idle in transaction for thirty hours.
    """

    def test_no_ddl_when_every_column_exists(self):
        conn = _Conn(present=("a", "b"))
        added = dbconn.add_missing_columns(conn, "t", [("a", "TEXT"), ("b", "INT")])
        self.assertEqual(added, [])
        self.assertFalse([s for s in conn.sql if "ALTER TABLE" in s],
                         "issued DDL for columns that already exist")
        self.assertEqual(conn.commits, 0, "committed despite changing nothing")

    def test_only_the_absent_column_is_added(self):
        conn = _Conn(present=("a",))
        added = dbconn.add_missing_columns(conn, "t", [("a", "TEXT"), ("b", "INT")])
        self.assertEqual(added, ["b"])
        alters = [s for s in conn.sql if "ALTER TABLE" in s]
        self.assertEqual(len(alters), 1)
        self.assertIn("b", alters[0])
        self.assertNotIn(" a ", alters[0])

    def test_column_lookup_is_scoped_to_the_current_schema(self):
        """information_schema.columns spans every schema the role can see, so
        an unscoped lookup answers about whatever same-named table it finds
        first."""
        conn = _Conn(present=())
        dbconn.existing_columns(conn, "events")
        self.assertIn("current_schema()", conn.sql[0])


class TestConnectOrExit(unittest.TestCase):
    def test_exits_1_and_prints_the_greppable_line(self):
        """Failure notifiers grep for `<label> FAILED:`."""
        buf = io.StringIO()
        with mock.patch.object(dbconn, "connect",
                               side_effect=RuntimeError("no url")), \
             mock.patch("sys.stdout", buf):
            with self.assertRaises(SystemExit) as ctx:
                dbconn.connect_or_exit("jobs ingest")
        self.assertEqual(ctx.exception.code, 1)
        self.assertIn("jobs ingest FAILED:", buf.getvalue())

    def test_never_prints_a_password(self):
        buf = io.StringIO()
        url = "postgresql://u:hunter2@localhost:5432/jobs"
        with mock.patch.object(dbconn, "connect",
                               side_effect=RuntimeError("nope")), \
             mock.patch("sys.stdout", buf):
            with self.assertRaises(SystemExit):
                dbconn.connect_or_exit("jobs ingest", url=url)
        self.assertNotIn("hunter2", buf.getvalue())


# --------------------------------------------------------------------------
# state.py -- watermarks and the claim half
# --------------------------------------------------------------------------

class _StateConn(_Conn):
    """Adds a scripted fetchone() queue for the claim tests."""

    def __init__(self, present=(), returns=()):
        super().__init__(present)
        self.returns = list(returns)

    def fetchone(self):
        return self.returns.pop(0) if self.returns else None


class TestWatermarks(unittest.TestCase):
    def test_set_watermark_upserts_rather_than_inserting(self):
        """A second successful run must update, not fail on the primary key."""
        conn = _StateConn()
        state.set_watermark(conn, "greenhouse", ts="2026-07-26T00:00:00")
        sql = " ".join(conn.sql)
        self.assertIn("ON CONFLICT", sql)
        self.assertIn("DO UPDATE", sql)

    def test_watermark_table_is_parameterised(self):
        """jobs uses job_ingest_state; the table name must reach the SQL."""
        conn = _StateConn()
        state.get_watermark(conn, "ds", table="job_ingest_state")
        self.assertIn("job_ingest_state", conn.sql[0])


class TestClaims(unittest.TestCase):
    """The lease that stops two overlapping runs spending the same metered
    quota twice. This half is jobs-only."""

    def test_claim_is_won_when_a_row_comes_back(self):
        conn = _StateConn(returns=[("ds",)])
        self.assertTrue(state.try_claim(conn, "ds"))

    def test_claim_is_lost_when_no_row_comes_back(self):
        """RETURNING rather than rowcount: an ON CONFLICT DO UPDATE whose
        WHERE fails reports zero affected rows either way, so "was I handed a
        row" is the unambiguous signal."""
        conn = _StateConn(returns=[None])
        self.assertFalse(state.try_claim(conn, "ds"))

    def test_a_stale_claim_is_stealable(self):
        """Otherwise a crashed run blocks the dataset forever."""
        conn = _StateConn(returns=[("ds",)])
        state.try_claim(conn, "ds", ttl_minutes=15)
        sql = " ".join(conn.sql)
        self.assertIn("claimed_at IS NULL", sql)
        self.assertIn("claimed_at <", sql)

    def test_mark_success_advances_and_releases_together(self):
        """Releasing here rather than letting the TTL expire means nobody
        waits out the lease for a result already known."""
        conn = _StateConn()
        state.mark_success(conn, "ds", ts="2026-07-26T00:00:00")
        sql = " ".join(conn.sql)
        self.assertIn("last_success_at", sql)
        self.assertIn("claimed_at = NULL", sql)

    def test_release_clears_only_the_claim(self):
        conn = _StateConn()
        state.release_claim(conn, "ds")
        sql = " ".join(conn.sql)
        self.assertIn("claimed_at = NULL", sql)
        self.assertNotIn("last_success_at", sql)


class TestEnsureStateSchema(unittest.TestCase):
    def test_claim_column_only_on_request(self):
        """Issuing DDL must stay something a caller asks for -- see
        TestAddMissingColumns for why an unconditional ALTER is not free."""
        without = _StateConn()
        state.ensure_state_schema(without, "job_ingest_state")
        self.assertFalse([s for s in without.sql if "ALTER TABLE" in s])

        with_claims = _StateConn()
        state.ensure_state_schema(with_claims, "job_ingest_state",
                                  with_claims=True)
        self.assertTrue([s for s in with_claims.sql if "ALTER TABLE" in s])


# --------------------------------------------------------------------------
# upsert.py / timeparse.py -- small contracts with real callers
# --------------------------------------------------------------------------

class TestUpsertResult(unittest.TestCase):
    def test_unpacks_as_new_updated_unchanged(self):
        """api/query_claims.py returns this tuple straight to a caller."""
        r = upsert.UpsertResult()
        r.new, r.updated, r.unchanged = 1, 2, 3
        new, updated, unchanged = r
        self.assertEqual((new, updated, unchanged), (1, 2, 3))


class TestTimeparseFormats(unittest.TestCase):
    def test_utc_now_str_has_no_microseconds_or_offset(self):
        """first_seen/last_seen are TEXT and compared as strings; adding a
        suffix would break every range query silently."""
        s = timeparse.utc_now_str()
        self.assertRegex(s, r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}$")

    def test_utc_now_is_timezone_aware(self):
        self.assertIsNotNone(timeparse.utc_now().tzinfo)


if __name__ == "__main__":
    unittest.main()

"""T-31: the server dictates the poll interval, and the worker floors it.

THE ONE PROPERTY THIS ROW IS ABOUT IS A DIRECTION, so the direction is what is
pinned, in both directions, separately. A clamp written with min() instead of
max() passes any test that only checks "the interval is a number" and any test
that only offers it a below-floor value and reads the floor back. It takes a
second case, offering a value ABOVE the floor and requiring it back unchanged,
to tell a floor from a ceiling -- and a ceiling is the failure that matters
here: it would make "poll in six hours" unsayable, which is how an operator
waves thirty volunteers' machines off. Both cases are below, and neither is
sufficient alone.

WHY A REAL SOCKET IS AT THE BOTTOM OF THIS FILE. Every other case here calls
clamp_poll_interval() directly or app.claim() with a fake connection, which
proves the two halves and not the seam between them: that the server puts the
key on the wire, that the worker reads THAT key off it, and that the two spell
it the same way. A scripted stand-in cannot fail that way -- it is written from
the same assumption as the code it stands in for. So TestOverARealSocket stands
up an HTTP server on 127.0.0.1, answers one claim from it, and runs the worker
as a subprocess against it. It is offered no queries, so no SerpApi key is
needed and no search is ever attempted; the far end is a socket this test owns
and no packet leaves the machine.

NO CLOCK. An interval is a duration, not an instant: nothing here reads the
time, nothing expires, and there is no second clock to get out of step with the
first.
"""

import contextlib
import http.server
import importlib.util
import io
import json
import os
import subprocess
import sys
import threading
import unittest
from typing import ClassVar

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fakedb import FakeConn, patch_db                # noqa: E402

import app                                           # noqa: E402
import query_claims as qc                            # noqa: E402

WORKER_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "contributor-worker")
WORKER_NAME = "google-serpapi-worker.py"
WORKER = os.path.join(WORKER_DIR, WORKER_NAME)

#: Same list, same reason, as test_worker_check.py's and
#: test_worker_install.py's -- and spelled out again rather than imported from
#: either, because a test module that imports another test module fails in a
#: way that looks like the subject failing.
WORKER_VARS = ("JOBS_API_BASE_URL", "JOBS_API_KEY", "SERPAPI_API_KEY",
               "MAX_QUERIES", "HTTP_TIMEOUT", "DEBUG")


def load_worker():
    """Import the worker under a name Python will accept -- the hyphens in the
    filename mean `import` cannot name it."""
    spec = importlib.util.spec_from_file_location("contributor_worker", WORKER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


worker = load_worker()


def bank_of(n):
    """A query bank of exactly n slugs in one bucket with budget for all of
    them, so a test can ask for a known number of grants."""
    return {
        "b": {
            "daily_budget": n,
            "queries": [{"slug": f"s{i}", "query": f"q{i}", "location": "New York",
                         "mode": "nyc"} for i in range(n)],
        }
    }


class TestTheServerSendsAnInterval(unittest.TestCase):
    """The server's half: the reply carries the number."""

    def setUp(self):
        self._real = qc.load_query_buckets
        self.addCleanup(lambda: setattr(qc, "load_query_buckets", self._real))
        qc.load_query_buckets = lambda: bank_of(3)

    def claim(self, conn, max_queries=1):
        restore = patch_db(app, conn)
        try:
            return app.claim(app.ClaimRequest(max=max_queries),
                             authorization="Bearer key")
        finally:
            restore()

    def test_a_granted_claim_carries_the_interval(self):
        result = self.claim(FakeConn(), max_queries=3)
        self.assertEqual(result["poll_interval_seconds"],
                         app.POLL_INTERVAL_SECONDS)

    def test_a_claim_that_granted_nothing_carries_it_too(self):
        # THE CASE THAT MATTERS MOST, and the one an implementation that
        # attached the interval to the queries would get wrong. The bank is
        # fresh on most days, so this is the ordinary reply -- and a machine
        # with no work is precisely the machine an operator wants to be able to
        # slow down. Carried only alongside granted work, the cadence would
        # reach the quiet contributors never.
        conn = FakeConn(claim_wins=False)
        result = self.claim(conn, max_queries=3)
        self.assertEqual(result["queries"], [])
        self.assertEqual(result["poll_interval_seconds"],
                         app.POLL_INTERVAL_SECONDS)
        # And it is still not a metered event: an interval is not a grant.
        self.assertEqual(conn.log, [])

    def test_the_interval_is_not_nested_inside_a_query(self):
        # Reading it off a query would mean a worker granted nothing has
        # nowhere to read it from, which is the bug the case above forbids from
        # the other side.
        result = self.claim(FakeConn(), max_queries=3)
        for q in result["queries"]:
            self.assertNotIn("poll_interval_seconds", q)


class TestTheClampIsAFloor(unittest.TestCase):
    """The worker's half, and the row's central claim."""

    def test_a_below_floor_interval_is_raised(self):
        # THE ROW'S NAMED CASE. A server saying "poll in 10 seconds" -- changed,
        # compromised or typo'd -- must not be able to make thirty machines
        # hammer one endpoint.
        self.assertEqual(worker.clamp_poll_interval(10),
                         worker.MIN_POLL_INTERVAL_SECONDS)

    def test_an_above_floor_interval_is_honoured_unchanged(self):
        # THE DIRECTION THAT TELLS A FLOOR FROM A CEILING. Six hours, the row's
        # own example: slowing down costs the Builder nothing, and clamping it
        # back to an hour would leave an operator with no way to wave machines
        # off. Rewrite the clamp as min() and this is the case that goes red --
        # the one above stays green.
        self.assertEqual(worker.clamp_poll_interval(6 * 3600), 6 * 3600)

    def test_the_floor_itself_is_returned_unchanged(self):
        self.assertEqual(worker.clamp_poll_interval(worker.MIN_POLL_INTERVAL_SECONDS),
                         worker.MIN_POLL_INTERVAL_SECONDS)

    def test_one_second_above_the_floor_survives(self):
        # The boundary, from the side that a >= written as > would break.
        self.assertEqual(worker.clamp_poll_interval(worker.MIN_POLL_INTERVAL_SECONDS + 1),
                         worker.MIN_POLL_INTERVAL_SECONDS + 1)

    def test_the_floor_is_the_one_the_schedule_uses(self):
        # T-29 left this constant behind naming T-31 as its inheritor. Two
        # floors that drift apart is a worker polling on one number and
        # scheduled on another, which nothing would report -- so the clamp and
        # the plist are asserted to be the same constant, not two that agree.
        plist = worker.build_launch_agent(home="/nowhere")
        self.assertEqual(plist["StartInterval"], worker.MIN_POLL_INTERVAL_SECONDS)
        self.assertEqual(worker.clamp_poll_interval(1),
                         plist["StartInterval"])


class TestAnUnusableIntervalIsTheFloor(unittest.TestCase):
    """Absence and nonsense both land on the floor, and absence is silent."""

    def test_a_missing_key_is_the_floor(self):
        # A server that predates this row sends no interval. It must behave
        # exactly like the install that never heard of one -- that is what lets
        # the two ends deploy in either order.
        self.assertEqual(worker.clamp_poll_interval(None),
                         worker.MIN_POLL_INTERVAL_SECONDS)

    def test_a_string_is_not_read_as_a_number(self):
        self.assertEqual(worker.clamp_poll_interval("7200"),
                         worker.MIN_POLL_INTERVAL_SECONDS)

    def test_a_negative_interval_is_the_floor(self):
        self.assertEqual(worker.clamp_poll_interval(-1),
                         worker.MIN_POLL_INTERVAL_SECONDS)

    def test_true_is_not_a_cadence(self):
        # bool is an int in Python, so max(True, 3600) is 3600 by luck rather
        # than by intent -- and max(True, 1) would be 1. A flag arriving in this
        # field is a server bug either way, and it lands on the floor by a check
        # rather than by an accident of ordering.
        self.assertEqual(worker.clamp_poll_interval(True),
                         worker.MIN_POLL_INTERVAL_SECONDS)

    def test_not_a_number_is_the_floor(self):
        self.assertEqual(worker.clamp_poll_interval(float("nan")),
                         worker.MIN_POLL_INTERVAL_SECONDS)

    def test_infinity_is_the_floor(self):
        # Honouring it would mean int(inf), which raises -- an interval nobody
        # can schedule is not a slower cadence, it is a crash on the one run
        # nobody watches.
        self.assertEqual(worker.clamp_poll_interval(float("inf")),
                         worker.MIN_POLL_INTERVAL_SECONDS)

    def test_a_float_is_taken_at_its_whole_seconds(self):
        self.assertEqual(worker.clamp_poll_interval(7200.9), 7200)


class TestTheReportNamesTheSchedule(unittest.TestCase):
    """What a Builder sees, which is the reason the row asks for any output at
    all: a machine polling on a cadence the server did not ask for reads as
    broken unless something says otherwise."""

    def report(self, interval):
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            worker.report_poll_interval(interval)
        return buffer.getvalue()

    def test_the_ordinary_run_says_nothing(self):
        # The ask and the schedule agree on every machine nobody has changed
        # anything for. A line per run about a cadence that did not change is
        # noise in the one log a Builder is meant to read for failures.
        self.assertEqual(self.report(worker.MIN_POLL_INTERVAL_SECONDS), "")

    def test_a_changed_ask_is_reported_with_both_numbers(self):
        output = self.report(6 * 3600)
        self.assertIn("360", output)   # what the server asked for, in minutes
        self.assertIn("60", output)    # what this machine is actually on
        self.assertIn("--install", output)

    def test_it_is_not_reported_as_a_fault(self):
        # A Builder reading "FAILED" here would go looking for a broken
        # install, and would find a correct one.
        output = self.report(6 * 3600)
        self.assertNotIn("FAILED", output)
        self.assertNotIn("error", output.lower())


class ClaimStandIn(http.server.BaseHTTPRequestHandler):
    """One real HTTP endpoint: /v1/queries/claim, answering over a real socket.

    IT DOES NOT SPELL THE REPLY ITSELF. `payload` is whatever app.claim()
    returned when the test called it -- the server's own dict, serialised onto
    a real socket -- because a handler that wrote its own {"poll_interval_
    seconds": ...} would be asserting the worker agrees with THIS FILE rather
    than with the server. That version was written first and a rename on the
    server end sailed straight past it.

    It grants no queries, which is what keeps this test free: with an empty
    list the worker never reaches serpapi_search, so no SerpApi key is needed
    and no search is attempted against anyone's account.
    """

    payload: ClassVar[dict] = {}
    body = None

    def do_POST(self):
        length = int(self.headers.get("Content-Length") or 0)
        ClaimStandIn.body = self.rfile.read(length)
        payload = json.dumps(self.payload).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, *args):
        pass          # the suite's own output is not this server's access log


class TestOverARealSocket(unittest.TestCase):
    """The seam: the server's key name, on a wire, read by the worker's parser.

    Both halves of this row can be individually right and still not meet -- a
    key spelled `poll_interval` on one end and `poll_interval_seconds` on the
    other passes every scripted case in this file, because a stand-in is
    written from the same assumption as the code it stands in for. Nothing but
    a real request finds that.
    """

    def setUp(self):
        self._real_bank = qc.load_query_buckets
        self.addCleanup(lambda: setattr(qc, "load_query_buckets", self._real_bank))
        qc.load_query_buckets = lambda: bank_of(3)
        self._real_interval = app.POLL_INTERVAL_SECONDS
        self.addCleanup(lambda: setattr(app, "POLL_INTERVAL_SECONDS",
                                        self._real_interval))
        self.server = http.server.HTTPServer(("127.0.0.1", 0), ClaimStandIn)
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.server.shutdown)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.port = self.server.server_address[1]

    def server_reply(self, interval):
        """What this service really answers a claim with, at that setting.

        Built by calling the route, not by writing out its shape: the key name
        on the wire has to be the server's, or this test proves only that the
        worker agrees with the fixture beside it. claim_wins=False so nothing
        is granted and the worker has nothing to search.
        """
        app.POLL_INTERVAL_SECONDS = interval
        restore = patch_db(app, FakeConn(claim_wins=False))
        try:
            return app.claim(app.ClaimRequest(max=3), authorization="Bearer key")
        finally:
            restore()

    def run_worker(self, interval):
        ClaimStandIn.payload = self.server_reply(interval)
        environ = {k: v for k, v in os.environ.items() if k not in WORKER_VARS}
        environ.update({
            "JOBS_API_BASE_URL": f"http://127.0.0.1:{self.port}",
            "JOBS_API_KEY": "test-key",
            # Set because the worker refuses to start without it, and never
            # used: the stand-in grants no queries, so nothing is searched.
            "SERPAPI_API_KEY": "unused-no-search-is-run",
            "HTTP_TIMEOUT": "10",
        })
        return subprocess.run(  # noqa: S603 -- argv is sys.executable and a module-level constant path
            [sys.executable, WORKER],
            cwd=os.path.dirname(WORKER_DIR), env=environ,
            capture_output=True, text=True, timeout=60, check=False)

    def test_a_below_floor_interval_from_a_real_server_is_raised(self):
        result = self.run_worker(10)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        # 10 seconds was asked for and the floor is what is in force, so there
        # is no disagreement to report: the clamped ask IS the schedule.
        self.assertNotIn("the server asks", result.stdout)
        self.assertIn("nothing to do", result.stdout)

    def test_an_above_floor_interval_from_a_real_server_is_reported(self):
        # THE SEAM. The server wrote the key, the worker read it, and the
        # number that came out the far end is the one that went in -- which no
        # test in this file that scripts its own answer can establish.
        result = self.run_worker(6 * 3600)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("every 360 minutes", result.stdout)

    def test_the_worker_still_claims_the_way_it_always_did(self):
        # The request this row extends is the one T-30 left at the top of
        # main(); a reply that grew a key must not have changed what is sent.
        self.run_worker(10)
        self.assertEqual(json.loads(ClaimStandIn.body).get("max"),
                         worker.MAX_QUERIES)


if __name__ == "__main__":
    unittest.main()

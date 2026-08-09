"""T-30: `--check`, and the one server-side assumption it rests on.

WHAT THIS MACHINE CAN AND CANNOT CHECK, said before anything below is read.
Three checks are being made by this row -- a base URL that answers, a
credential the server accepts, a SerpApi key SerpApi accepts -- and two of the
three have a far end this suite cannot reach. So the line drawn here is:

  * WHAT WE SEND is asserted for real. Which URL, which method, which endpoint,
    how many requests, and -- the row's central promise -- that no request this
    command makes is a SerpApi SEARCH. That is a claim about our own code and
    it is checked exactly.
  * WHAT COMES BACK is scripted. Every answer below is one this suite wrote,
    so nothing here says SerpApi's account endpoint really is free, or really
    reports `total_searches_left`. That is an account we do not have; the
    row's own acceptance clause -- the reported remaining count, read before
    and after -- needs a real key, and DEV_TASKS.md's OQ-25 is where a real
    install gets watched.
  * WHETHER THE OUTPUT MEANS ANYTHING TO A READER is not checked and is not
    checkable. The row says so itself: plain language is a human judgement,
    and inventing an assertion for it would be inventing the finding.

THE SERVER-SIDE HALF IS NOT A FAKE OF THE SERVER, IT IS THE SERVER'S OWN CODE.
`check_credential` asks the api whether a credential works by offering to
release a claim nobody can hold, and reads the 409 as a pass. That is only
true while `release` authenticates BEFORE it checks claim ownership, which is
an ordering inside app.py that nothing else in this tree had a reason to keep.
TestTheServerSideOfTheProbe below calls the real route with a fake connection
and pins it. Reversed, `--check` would tell a Builder with a perfectly good
credential to go and ask for a new one.

NO CLOCK. Nothing in this row has an expiry, an interval or a timestamp; the
one place a clock could enter is `release`'s TTL comparison, and the probe
never reaches it because no claim row exists to compare.
"""

import contextlib
import importlib.util
import io
import os
import subprocess
import sys
import unittest
import urllib.error

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fakedb import FakeConn, patch_db                # noqa: E402

import app                                           # noqa: E402
import query_claims as qc                            # noqa: E402
from fastapi import HTTPException                    # noqa: E402

WORKER_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "contributor-worker")
WORKER = os.path.join(WORKER_DIR, "google-serpapi-worker.py")

#: Everything the worker reads out of the environment, cleared before every
#: subprocess run so the machine this suite is on cannot supply a setting the
#: test did not. Same list, same reason, as test_worker_install.py's -- and
#: spelled out here rather than imported from it, because a test module that
#: imports another test module fails in a way that looks like the subject
#: failing.
WORKER_VARS = ("JOBS_API_BASE_URL", "JOBS_API_KEY", "SERPAPI_API_KEY",
               "MAX_QUERIES", "HTTP_TIMEOUT", "DEBUG")


def load_worker():
    """Import the worker under a name Python will accept -- the hyphens in the
    filename mean `import` cannot name it. Same loader, same reason, as
    test_worker_install.py's."""
    spec = importlib.util.spec_from_file_location("contributor_worker", WORKER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


worker = load_worker()


class Answers:
    """Stands in for the worker's `probe`, recording what it was asked to send.

    It answers from a script, and an Exception in that script is raised rather
    than returned -- that is how the unreachable cases below are expressed,
    since `probe` itself only raises for a non-answer (DNS, refused, timeout).
    An empty script is a test error rather than a default answer: a check that
    sends a request this test did not expect must be visible.
    """

    def __init__(self, *answers):
        self.answers = list(answers)
        self.requests = []

    def __call__(self, request, timeout=None):
        self.requests.append(request)
        if not self.answers:
            raise AssertionError(f"unscripted request to {request.full_url}")
        answer = self.answers.pop(0)
        if isinstance(answer, Exception):
            raise answer
        return answer

    @property
    def urls(self):
        return [r.full_url for r in self.requests]


def report(answers):
    """run_checks, with its report captured rather than printed.

    Captured in every caller, including the ones that assert on the requests
    and not on the output: a suite that prints a Builder-facing report between
    its own dots is a suite somebody stops reading.
    """
    buffer = io.StringIO()
    with contextlib.redirect_stdout(buffer):
        code = worker.run_checks(answers)
    return code, buffer.getvalue()


class _CheckCase(unittest.TestCase):
    """Sets the three settings on the module, and puts them back.

    The worker resolves its settings once, at import, into module globals; the
    check functions read those globals at call time, which is what makes them
    settable here. Restoring is not politeness -- a leaked JOBS_API_KEY would
    make a later test that asserts on the unset case pass for the wrong
    reason.
    """

    BASE_URL = "https://jobs.example.test"
    API_KEY = "jobs-key-0123456789"
    SERPAPI_KEY = "serpapi-key-0123456789"

    def setUp(self):
        self._previous = (worker.JOBS_API_BASE_URL, worker.JOBS_API_KEY,
                          worker.SERPAPI_API_KEY)
        worker.JOBS_API_BASE_URL = self.BASE_URL
        worker.JOBS_API_KEY = self.API_KEY
        worker.SERPAPI_API_KEY = self.SERPAPI_KEY

    def tearDown(self):
        (worker.JOBS_API_BASE_URL, worker.JOBS_API_KEY,
         worker.SERPAPI_API_KEY) = self._previous


class TestNoSerpApiCreditIsSpent(_CheckCase):
    """The row's hard constraint, as far as it is checkable from here: what
    this command sends. Whether SerpApi charges for the account endpoint is
    SerpApi's business and OQ-25's evidence; whether we ever ask SerpApi for a
    SEARCH is ours, and it is asserted."""

    def test_the_serpapi_check_asks_the_account_endpoint(self):
        # The literal, not the constant. Asserting `startswith(the constant)`
        # would follow an edit to the constant anywhere it went, including to
        # /search.json -- which is the one edit this row forbids, so the test
        # that is supposed to catch it must not be written from it. (Found by
        # making exactly that edit: this case stayed green until the literal
        # was here.)
        self.assertEqual(worker.SERPAPI_ACCOUNT_URL,
                         "https://serpapi.com/account")
        answers = Answers((200, '{"total_searches_left": 212}'))
        worker.check_serpapi(answers)
        self.assertEqual(len(answers.urls), 1)
        self.assertTrue(answers.urls[0].startswith(worker.SERPAPI_ACCOUNT_URL),
                        f"asked {answers.urls[0]}")

    def test_no_check_ever_requests_a_serpapi_search(self):
        # The failure this forbids: a --check that proves the key works by
        # using one of the 250 searches the Builder is donating.
        answers = Answers((200, '{"ok": true}'), (409, "{}"),
                          (200, '{"total_searches_left": 212}'))
        report(answers)
        self.assertEqual(len(answers.urls), 3, answers.urls)
        for url in answers.urls:
            self.assertNotIn("/search", url)
            self.assertNotIn("engine=google_jobs", url)

    def test_the_credential_check_never_claims_a_query(self):
        # /v1/queries/claim locks rows out of the pool and meters the caller
        # against a daily cap, so a check that used it would spend the
        # allowance it is checking -- and lock real queries on a stale day.
        answers = Answers((409, "{}"))
        worker.check_credential(True, answers)
        self.assertEqual(len(answers.requests), 1)
        self.assertNotIn("/claim", answers.urls[0])
        self.assertTrue(answers.urls[0].endswith("/release"), answers.urls[0])
        self.assertEqual(answers.requests[0].method, "POST")

    def test_the_probe_dataset_is_one_the_query_bank_cannot_produce(self):
        # If a real slug could ever spell this, the probe would release a
        # query somebody was working on. The server builds every dataset name
        # as google_jobs:query:<slug> (app.py:509), so this is a claim about
        # the bank's slugs.
        buckets = qc.load_query_buckets()
        slugs = [q["slug"] for b in buckets.values() for q in b["queries"]]
        self.assertTrue(slugs, "the query bank is empty; this check is "
                               "unanchored")
        for slug in slugs:
            self.assertNotEqual(f"google_jobs:query:{slug}",
                                worker.CHECK_PROBE_DATASET)


class TestTheBaseUrlCheck(_CheckCase):

    def test_a_healthy_server_passes(self):
        ok, label, detail = worker.check_base_url(Answers((200, '{"ok": true}')))
        self.assertTrue(ok)
        self.assertEqual(label, "base URL")
        self.assertIn(self.BASE_URL, detail)

    def test_it_asks_v1_health_and_sends_no_credential(self):
        # No Authorization header, deliberately: that is what makes this check
        # able to fail differently from the credential check below.
        answers = Answers((200, '{"ok": true}'))
        worker.check_base_url(answers)
        self.assertTrue(answers.urls[0].endswith("/v1/health"), answers.urls[0])
        self.assertIsNone(answers.requests[0].get_header("Authorization"))

    def test_an_unreachable_server_fails_as_unreachable(self):
        ok, _, detail = worker.check_base_url(
            Answers(urllib.error.URLError("Name or service not known")))
        self.assertFalse(ok)
        self.assertIn("nothing answered", detail)

    def test_a_non_200_is_a_failure_naming_the_status(self):
        ok, _, detail = worker.check_base_url(Answers((502, "bad gateway")))
        self.assertFalse(ok)
        self.assertIn("502", detail)

    def test_a_200_that_is_not_this_service_fails(self):
        # A captive portal, a parked domain and a proxy error page all answer
        # 200, and a check that stopped at the status would call them healthy.
        ok, _, detail = worker.check_base_url(
            Answers((200, "<html>sign in to the hotel wifi</html>")))
        self.assertFalse(ok)
        self.assertIn("health response", detail)

    def test_an_unset_base_url_fails_without_sending_anything(self):
        worker.JOBS_API_BASE_URL = ""
        answers = Answers()
        ok, _, detail = worker.check_base_url(answers)
        self.assertFalse(ok)
        self.assertIn("JOBS_API_BASE_URL", detail)
        self.assertEqual(answers.requests, [])


class TestTheCredentialCheck(_CheckCase):

    def test_a_409_is_the_pass(self):
        # The server authenticated the caller and only then found no claim.
        ok, label, detail = worker.check_credential(
            True, Answers((409, '{"detail": "you do not hold a live claim on '
                                'this dataset"}')))
        self.assertTrue(ok, detail)
        self.assertEqual(label, "credential")

    def test_a_401_is_the_failure(self):
        ok, _, detail = worker.check_credential(
            True, Answers((401, '{"detail": "invalid api key"}')))
        self.assertFalse(ok)
        self.assertIn("JOBS_API_KEY", detail)

    def test_it_sends_the_key_as_a_bearer_token(self):
        answers = Answers((409, "{}"))
        worker.check_credential(True, answers)
        self.assertEqual(answers.requests[0].get_header("Authorization"),
                         f"Bearer {self.API_KEY}")

    def test_an_unreachable_base_url_makes_this_unchecked_not_failed(self):
        # The row's acceptance clause: a wrong credential must be
        # distinguishable from a base URL that never answered. This is the
        # half that would otherwise send a Builder to ask for a new key they
        # already have.
        answers = Answers()
        ok, _, detail = worker.check_credential(False, answers)
        self.assertFalse(ok)
        self.assertIn("not checked", detail)
        self.assertEqual(answers.requests, [], "a server that did not answer "
                                               "/v1/health will not answer "
                                               "this either")

    def test_the_two_failures_do_not_read_alike(self):
        bad_key = worker.check_credential(
            True, Answers((401, '{"detail": "invalid api key"}')))[2]
        no_server = worker.check_credential(False, Answers())[2]
        self.assertNotEqual(bad_key, no_server)

    def test_an_unset_key_fails_without_sending_anything(self):
        worker.JOBS_API_KEY = ""
        answers = Answers()
        ok, _, detail = worker.check_credential(True, answers)
        self.assertFalse(ok)
        self.assertIn("JOBS_API_KEY", detail)
        self.assertEqual(answers.requests, [])

    def test_an_unexpected_status_is_neither_a_pass_nor_a_verdict(self):
        ok, _, detail = worker.check_credential(True, Answers((500, "boom")))
        self.assertFalse(ok)
        self.assertIn("500", detail)
        self.assertIn("may be fine", detail)


class TestTheSerpApiCheck(_CheckCase):

    def test_an_accepted_key_reports_what_is_left(self):
        ok, label, detail = worker.check_serpapi(
            Answers((200, '{"plan_name": "Free", "total_searches_left": 212}')))
        self.assertTrue(ok)
        self.assertEqual(label, "SerpApi key")
        self.assertIn("212", detail)
        self.assertIn("Free", detail)

    def test_a_rejected_key_fails(self):
        ok, _, detail = worker.check_serpapi(
            Answers((401, '{"error": "Invalid API key"}')))
        self.assertFalse(ok)
        self.assertIn("rejected", detail)

    def test_a_long_answer_is_parsed_rather_than_truncated(self):
        # FOUND AGAINST THE REAL ENDPOINT, NOT HERE. `probe` used to cut every
        # body to 400 characters for printing, and SerpApi's account answer is
        # longer than that -- so a perfectly good key came back as "answered
        # 200 with something that is not JSON". Every scripted answer in this
        # file was short enough to hide it. This one is not: the padding is
        # what the real endpoint has and this suite did not.
        payload = ('{"plan_name": "Free Plan", "total_searches_left": 212, '
                   + ', '.join(f'"field_{i}": "value_{i}"' for i in range(40))
                   + '}')
        self.assertGreater(len(payload), 400, "this fixture no longer tests "
                                              "what it was written for")
        ok, _, detail = worker.check_serpapi(Answers((200, payload)))
        self.assertTrue(ok, detail)
        self.assertIn("212", detail)

    def test_an_accepted_key_with_no_count_still_passes(self):
        # The count is useful, not load-bearing: this check is about the key.
        ok, _, detail = worker.check_serpapi(Answers((200, '{"plan_name": "Free"}')))
        self.assertTrue(ok, detail)

    def test_an_unset_key_says_whose_key_it_is(self):
        # docs/adr/0006 decision 3: this one never reaches the server, so
        # "ask for a new one" would be the wrong instruction.
        worker.SERPAPI_API_KEY = ""
        answers = Answers()
        ok, _, detail = worker.check_serpapi(answers)
        self.assertFalse(ok)
        self.assertIn("serpapi.com", detail)
        self.assertEqual(answers.requests, [])


class TestNothingPrintsACredential(_CheckCase):
    """The check that makes a bad key visible must not make a good one
    public. Both keys are in flight here -- one in a header, one in a query
    string -- and a far end that quotes either back is the case that puts a
    credential in a scrollback."""

    def _output(self, answers):
        return report(answers)[1]

    def test_a_body_that_echoes_a_key_is_redacted(self):
        printed = self._output(Answers(
            (200, '{"ok": true}'),
            (401, '{"detail": "invalid api key: ' + self.API_KEY + '"}'),
            (400, '{"error": "unknown key ' + self.SERPAPI_KEY + '"}')))
        self.assertNotIn(self.API_KEY, printed)
        self.assertNotIn(self.SERPAPI_KEY, printed)
        self.assertIn("<redacted>", printed)

    def test_the_serpapi_url_is_never_printed(self):
        # The key is a query parameter there, so the URL is itself a
        # credential -- printing "could not reach <url>" would leak it.
        printed = self._output(Answers(
            (200, '{"ok": true}'), (409, "{}"),
            urllib.error.URLError("connection refused")))
        self.assertNotIn(self.SERPAPI_KEY, printed)
        self.assertIn("serpapi.com did not answer", printed)


class TestTheReport(_CheckCase):

    def _run(self, answers):
        return report(answers)

    def test_all_three_passing_exits_zero_with_a_line_each(self):
        code, printed = self._run(Answers(
            (200, '{"ok": true}'), (409, "{}"),
            (200, '{"total_searches_left": 212}')))
        self.assertEqual(code, 0)
        self.assertEqual(len([ln for ln in printed.splitlines()
                              if ln.startswith("  ok  ")]), 3, printed)
        self.assertNotIn("FAIL", printed)

    def test_any_failure_exits_non_zero(self):
        code, printed = self._run(Answers(
            (200, '{"ok": true}'), (401, "{}"),
            (200, '{"total_searches_left": 212}')))
        self.assertEqual(code, 1)
        self.assertIn("worker FAILED", printed)
        # The passes are still printed: a Builder needs to know which of the
        # three is wrong, not that something is.
        self.assertEqual(len([ln for ln in printed.splitlines()
                              if ln.startswith("  ok  ")]), 2, printed)

    def test_every_report_says_it_cost_nothing(self):
        for answers in (Answers((200, '{"ok": true}'), (409, "{}"),
                                (200, "{}")),
                        Answers((500, ""), (401, "{}"), (401, "{}"))):
            _, printed = self._run(answers)
            self.assertIn("no credit", printed)


class TestTheCommandLine(unittest.TestCase):
    """--check as a Builder types it. No network: with nothing set, every
    check fails before it sends anything, which is also the state a Builder
    who has not finished the setup is actually in."""

    def run_worker(self, *args):
        environ = {k: v for k, v in os.environ.items() if k not in WORKER_VARS}
        return subprocess.run(  # noqa: S603 -- argv is sys.executable, a module-level constant path, and flags this test spells out
            [sys.executable, WORKER, *args],
            cwd=os.path.dirname(WORKER_DIR), env=environ,
            capture_output=True, text=True, timeout=60, check=False)

    def test_check_is_accepted_now_and_reports_on_an_unset_machine(self):
        result = self.run_worker("--check")
        self.assertEqual(result.returncode, 1)
        self.assertIn("JOBS_API_BASE_URL", result.stdout)
        self.assertIn("JOBS_API_KEY", result.stdout)
        self.assertIn("SERPAPI_API_KEY", result.stdout)
        self.assertEqual(len([ln for ln in result.stdout.splitlines()
                              if ln.startswith("  FAIL")]), 3, result.stdout)

    def test_the_unset_report_is_not_the_bare_run_message(self):
        # A bare run says one sentence about the shell. --check is the command
        # for finding out WHICH of three things is wrong, so answering it with
        # that sentence would make the new flag pointless.
        result = self.run_worker("--check")
        self.assertNotIn("see this file's header)", result.stdout.splitlines()[0])

    def test_help_names_check_and_says_it_costs_nothing(self):
        result = self.run_worker("--help")
        self.assertEqual(result.returncode, 0)
        self.assertIn("--check", result.stdout)
        self.assertIn("costs you nothing", result.stdout)

    def test_check_is_not_in_the_scheduling_group(self):
        # It is not a third way to schedule, and the usage line must not offer
        # it as one. The group is [--install | --uninstall]; --check stands
        # outside it, which is also why it works on this non-Mac machine.
        result = self.run_worker("--help")
        usage = result.stdout.split("\n\n")[0]
        self.assertIn("--install | --uninstall", usage)
        self.assertNotIn("--install | --uninstall | --check", usage)

    def test_check_combined_with_a_scheduling_flag_is_refused(self):
        for flag in ("--install", "--uninstall"):
            result = self.run_worker("--check", flag)
            self.assertEqual(result.returncode, 1, flag)
            self.assertIn("one at a time", result.stdout)
            # Refused BEFORE anything ran: no check line, no plist.
            self.assertNotIn("  ok  ", result.stdout)
            self.assertNotIn("  FAIL", result.stdout)

    def test_a_bare_run_is_still_untouched(self):
        # Re-asserted from the row that could have moved it, as T-29 did from
        # its own. Two other suites pin this message; this one only has to not
        # break it.
        result = self.run_worker()
        self.assertEqual(
            result.stdout.strip(),
            "worker FAILED: set JOBS_API_BASE_URL, JOBS_API_KEY, "
            "SERPAPI_API_KEY (see this file's header)")
        self.assertEqual(result.returncode, 1)

    def test_an_unknown_flag_is_still_refused(self):
        result = self.run_worker("--frobnicate")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("unrecognized arguments", result.stderr)


class TestTheServerSideOfTheProbe(unittest.TestCase):
    """`check_credential` reads a 409 as "the credential is good". That is only
    true while `release` authenticates before it looks at claim ownership --
    an ordering inside app.py that nothing else had a reason to preserve, and
    the thing this class exists to make expensive to reverse.

    The real route, the real authentication, a fake connection. What is being
    asserted is a decision -- which check runs first, and what gets written --
    which is exactly what fakedb.py says a fake can falsify.
    """

    def release_probe(self, conn):
        """The worker's own probe, as the server sees it: the worker's
        constant, not a copy of it, so a rename on either side turns this
        red rather than leaving two files quietly disagreeing."""
        restore = patch_db(app, conn)
        try:
            return app.release(dataset=worker.CHECK_PROBE_DATASET,
                               req=app.ReleaseRequest(reason="--check"),
                               authorization="Bearer key")
        finally:
            restore()

    def test_a_good_credential_on_an_unheld_dataset_is_a_409(self):
        conn = FakeConn(claim_state=None)
        with self.assertRaises(HTTPException) as raised:
            self.release_probe(conn)
        self.assertEqual(raised.exception.status_code, 409)

    def test_that_409_writes_nothing_and_commits_nothing(self):
        # This is what makes the probe free to run as often as a Builder
        # likes: it takes no row out of the pool, meters nothing, and leaves
        # no audit-log entry for work that never happened.
        conn = FakeConn(claim_state=None)
        with self.assertRaises(HTTPException):
            self.release_probe(conn)
        self.assertEqual(conn.log, [])
        self.assertEqual(conn.released, [])
        self.assertEqual(conn.commits, 0)

    def test_authentication_comes_first_and_a_bad_key_is_a_401(self):
        # THE ORDERING THE WORKER'S CHECK RESTS ON. Same request, same absent
        # claim: the only difference is the credential, so a 401 here and a
        # 409 above is the whole signal --check reads.
        conn = FakeConn(contributor=None, claim_state=None)
        with self.assertRaises(HTTPException) as raised:
            self.release_probe(conn)
        self.assertEqual(raised.exception.status_code, 401)

    def test_a_revoked_key_is_a_401_too(self):
        conn = FakeConn(revoked="2026-08-01T00:00:00", claim_state=None)
        with self.assertRaises(HTTPException) as raised:
            self.release_probe(conn)
        self.assertEqual(raised.exception.status_code, 401)

    def test_the_two_answers_do_not_carry_the_same_detail(self):
        # The worker turns these into two different sentences for a Builder;
        # if the server ever collapsed them, that distinction would be a
        # fiction invented on this side.
        details = {}
        for name, conn in (("bad", FakeConn(contributor=None, claim_state=None)),
                           ("good", FakeConn(claim_state=None))):
            with self.assertRaises(HTTPException) as raised:
                self.release_probe(conn)
            details[name] = raised.exception.detail
        self.assertNotEqual(details["bad"], details["good"])


class TestTheProbeSafetyCitationsStillPointAtTheClaim(unittest.TestCase):
    """The probe is safe because no real slug can spell CHECK_PROBE_DATASET, and
    that rests on the server building every dataset name itself. Two comments say
    so and both carry an `app.py:NNN` -- T-46's subject, and T-40's fix shape:
    pin the one claim in the file that makes it rather than build a content
    checker. audit-citations.py resolves the number and cannot read the line;
    this reads the line.

    BOTH ENDS OF THE CLAIM, because either alone stays green under the drift it
    exists to catch. A number that merely lands somewhere in `claim` still looks
    right; what matters is that the line CONSTRUCTS the dataset string, which is
    what makes "no slug is spelled like this" a property of the server rather
    than of a comment.
    """

    #: (file that makes the claim, the text its citation follows). Parsed by
    #: hand rather than with `re`, deliberately: importing one more name here
    #: would shift every line below it, which is the exact defect T-46 is about.
    CITERS = (
        ("contributor-worker/google-serpapi-worker.py", "own query bank (api/app.py:"),
        ("tests/test_worker_check.py", "as google_jobs:query:<slug> (app.py:"),
    )

    @staticmethod
    def _cited_line_number(text, anchor):
        at = text.find(anchor)
        if at < 0:
            return None
        digits = ""
        for ch in text[at + len(anchor):]:
            if not ch.isdigit():
                break
            digits += ch
        return int(digits) if digits else None

    def _app_py_lines(self):
        path = os.path.join(os.path.dirname(os.path.dirname(
            os.path.abspath(__file__))), "app.py")
        with open(path, encoding="utf-8") as fh:
            return fh.read().split("\n")

    def test_each_citer_names_a_line_that_builds_the_dataset_name(self):
        api_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        lines = self._app_py_lines()
        for relpath, anchor in self.CITERS:
            with self.subTest(citer=relpath):
                with open(os.path.join(api_dir, relpath), encoding="utf-8") as fh:
                    cited = self._cited_line_number(fh.read(), anchor)
                self.assertIsNotNone(
                    cited, f"{relpath} no longer carries the citation this pins")
                self.assertLessEqual(cited, len(lines), f"{relpath}: line past EOF")
                self.assertIn(
                    'f"google_jobs:query:{q[', lines[cited - 1],
                    f"{relpath} cites app.py:{cited}, which does not build the "
                    f"dataset name: {lines[cited - 1].strip()!r}")

    def test_the_probe_dataset_is_not_something_the_server_could_build(self):
        # The other end of the same claim: whatever app.py builds, it is always
        # the prefix plus a bank slug, so a dataset with no slug after the
        # prefix cannot be produced however the bank is edited.
        self.assertTrue(
            worker.CHECK_PROBE_DATASET.startswith("google_jobs:query:"))
        self.assertNotIn(
            worker.CHECK_PROBE_DATASET[len("google_jobs:query:"):],
            [q["slug"] for b in qc.load_query_buckets().values()
             for q in b["queries"]])


if __name__ == "__main__":
    unittest.main()

"""Defect D41: `claim` must be metered by the cap that claims to meter it.

WHAT WAS WRONG, and it is worth stating as a shape rather than a line number:
`MAX_CLAIMS_PER_CONTRIBUTOR_PER_DAY` was enforced by `claims_today()`, which
counted `submission_log` rows -- and `claim`, the only endpoint that takes a
query OUT of the pool, wrote none. So the cap could only ever see contributors
who finished their work. A worker that claimed and never submitted was
unmetered, and each claim locks its row for `CLAIM_TTL_MINUTES`, so a claim-loop
could hold the whole query bank and starve the operator's own nightly pipeline.
`backend/api/README.md`'s "known gaps" section named this before the code
existed to check it; a gap that is documented and unenforced is still a gap.

TWO HALVES, AND EITHER ALONE IS WRONG.

  1. `claim` writes one submission_log row per query it grants. Per query, not
     per request: `claim` already computes `remaining = MAX - used` and passes
     it to `max_queries`, so the number has always been read as a count of
     queries and now is one.

  2. `claims_today` counts `action = 'claim'` and nothing else. Without the
     filter, an honest submit and an honest release would each burn a claim from
     a cap whose name is about claims -- doing the work would reduce how much
     work you were allowed, which is a worse bug than the one being fixed and
     would have looked like the fix working.

A REQUEST GRANTED NOTHING WRITES NOTHING. It locked no row and cost nothing, and
charging for it would exhaust an honest daily cron's allowance on exactly the
days the bank is fresh -- the worker prints "nothing to do" and exits 0 on those
(`contributor-worker/google-serpapi-worker.py:330-335`). Request volume with no
grant is a rate concern for whatever terminates TLS, not something a per-query
cap can express.

That line range is pinned by TestTheCitationInThisModulesDocstring at the foot
of this file, because it had been wrong since the day it was written and no
tool in this repo could say so (`T-40`).
"""

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

#: This module's own docstring, captured because inside a class body `__doc__`
#: means the class's and the test at the foot of this file wants this one. It
#: sits BELOW the imports deliberately: a plain assignment above them makes
#: ruff's E402 start firing on the four lines that already carry `# noqa: E402`,
#: which silently turns four RUF100 unused-noqa findings into zero and moves a
#: baseline this row has no business moving.
MODULE_DOCSTRING = __doc__


def run_claim(conn, max_queries=1):
    restore = patch_db(app, conn)
    try:
        return app.claim(app.ClaimRequest(max=max_queries),
                         authorization="Bearer key")
    finally:
        restore()


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


class _ClaimCase(unittest.TestCase):

    def setUp(self):
        self._real = qc.load_query_buckets
        self.addCleanup(lambda: setattr(qc, "load_query_buckets", self._real))
        qc.load_query_buckets = lambda: bank_of(3)


class TestClaimIsLogged(_ClaimCase):

    def test_a_granted_claim_writes_one_row_per_query(self):
        # THE DEFECT. Remove the log_submission loop from app.claim and this
        # goes red: the list is empty however many queries were handed out.
        conn = FakeConn()
        result = run_claim(conn, max_queries=3)
        self.assertEqual(len(result["queries"]), 3)
        rows = conn.rows("claim")
        self.assertEqual(len(rows), 3)

    def test_the_row_names_the_dataset_that_was_locked(self):
        # Counts alone would meter the cap and leave "which query is this
        # worker sitting on" unanswerable, which is the other half of what an
        # audit log is for.
        conn = FakeConn()
        result = run_claim(conn, max_queries=3)
        self.assertEqual({r["dataset"] for r in conn.rows("claim")},
                         {q["dataset"] for q in result["queries"]})

    def test_a_claim_that_granted_nothing_writes_nothing(self):
        # claim_wins=False: every candidate is already held by someone else.
        conn = FakeConn(claim_wins=False)
        result = run_claim(conn, max_queries=3)
        self.assertEqual(result["queries"], [])
        self.assertEqual(conn.log, [])


class TestTheCapCountsClaims(_ClaimCase):

    def test_claims_are_what_counts_toward_the_cap(self):
        conn = FakeConn()
        run_claim(conn, max_queries=3)
        self.assertEqual(app.claims_today(conn, "c_test"), 3)

    def test_a_submit_row_does_not_count_against_the_claim_cap(self):
        # The half-fix this guards against: making `claim` write rows while
        # claims_today still counted every row would charge a contributor twice
        # for one query and once more for giving it back.
        conn = FakeConn()
        qc.log_submission(conn, "submit", "c_test", "google_jobs:query:s0",
                          fetched_count=10, accepted_count=10)
        qc.log_submission(conn, "release", "c_test", "google_jobs:query:s1",
                          reason="serpapi 429")
        self.assertEqual(app.claims_today(conn, "c_test"), 0)

    def test_the_cap_refuses_a_contributor_at_the_limit(self):
        conn = FakeConn(claim_rows_today=app.MAX_CLAIMS_PER_CONTRIBUTOR_PER_DAY)
        with self.assertRaises(HTTPException) as caught:
            run_claim(conn)
        self.assertEqual(caught.exception.status_code, 429)
        self.assertEqual(conn.log, [], "a refused claim must not be logged")

    def test_a_contributor_near_the_limit_gets_only_what_is_left(self):
        # The pre-existing `remaining` arithmetic, now that `used` is a count of
        # queries rather than a count of unrelated log rows.
        conn = FakeConn(claim_rows_today=app.MAX_CLAIMS_PER_CONTRIBUTOR_PER_DAY - 2)
        result = run_claim(conn, max_queries=3)
        self.assertEqual(len(result["queries"]), 2)


class TestTheSubmissionLogVocabulary(unittest.TestCase):
    """`action` is free TEXT, so the closed set in code is the only thing
    keeping the column analysable -- the same argument webapp/jobs.py's
    EVENT_NAMES carries."""

    def test_the_closed_set(self):
        self.assertEqual(set(qc.SUBMISSION_ACTIONS),
                         {"claim", "submit", "release"})

    def test_an_unknown_action_is_refused_at_the_writer(self):
        conn = FakeConn()
        with self.assertRaises(ValueError):
            qc.log_submission(conn, "submitted", "c_test", "d")
        self.assertEqual(conn.log, [])

    def test_every_action_is_written_by_something(self):
        # A vocabulary entry nothing emits is either dead or a call site that
        # was renamed and left the constant behind.
        with open(app.__file__, encoding="utf-8") as fh:
            source = fh.read()
        for action in qc.SUBMISSION_ACTIONS:
            self.assertIn(f'log_submission(conn, "{action}"', source,
                          f"nothing in app.py writes action={action!r}")

    def test_there_is_exactly_one_writer_of_the_table(self):
        # Four hand-written INSERTs that must agree on a column list is how a
        # call site comes to omit `action` and write a row the cap cannot see --
        # which is the defect, not a hypothetical.
        for module in (app, qc):
            with open(module.__file__, encoding="utf-8") as fh:
                source = fh.read()
            code = "\n".join(line for line in source.splitlines()
                             if not line.strip().startswith("#"))
            expected = 1 if module is qc else 0
            self.assertEqual(code.count("INSERT INTO submission_log"), expected,
                             f"{os.path.basename(module.__file__)} should hold "
                             f"{expected} submission_log INSERT(s)")


class TestTheCitationInThisModulesDocstring(unittest.TestCase):
    """This file's docstring cites a line range in the worker. Nothing read it.

    `tools/audit-citations.py` reports that citation green and always will: it
    checks that the path resolves and that the line is inside the file, and its
    own docstring says outright that it cannot check whether the line still
    carries the claim. This one never did. It named the worker's settings block
    on the day it was written and `load_config()`'s JSON parsing by the time
    anyone looked, and the checker was green across all of it -- `T-40`.

    THE ROW THAT FILED IT WENT STALE TOO, WHICH IS THE ARGUMENT FOR A TEST
    RATHER THAN A THIRD CORRECT NUMBER. `T-40` prescribed `:247-252`; that was
    right at `9c5154d` and was moved to `:330-335` a day later by `T-31`
    inserting two functions above `main()`. A citation into this particular
    file has now been wrong twice in five days, and `T-41` has still to edit it.

    THIS PINS ONE CITATION AND IS NOT A CHECKER. `T-40` says not to generalise
    it into one, and it is right: the tool cannot be a content checker and a
    second hand-rolled auditor is the failure mode this repo deleted 137 files
    to end. What is cheap here is that this is one claim, in the file that
    makes it, asserting the one string the claim is about -- the same idiom
    `TestTheSubmissionLogVocabulary` above already uses on `app` and `qc`.
    """

    WORKER = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "contributor-worker", "google-serpapi-worker.py")

    def cited_lines(self):
        """The lines the docstring's citation names, read from the worker."""
        m = re.search(
            r"contributor-worker/google-serpapi-worker\.py:(\d+)-(\d+)",
            MODULE_DOCSTRING)
        self.assertIsNotNone(
            m, "this module's docstring no longer carries the citation this "
               "test exists to pin")
        start, end = int(m.group(1)), int(m.group(2))
        with open(self.WORKER, encoding="utf-8") as fh:
            lines = fh.read().splitlines()
        self.assertLessEqual(end, len(lines),
                             f"the citation names line {end} of a "
                             f"{len(lines)}-line file")
        return lines[start - 1:end]

    def test_the_cited_lines_are_the_granted_nothing_branch(self):
        # BOTH ENDS, not just the contents. A range that merely contains the
        # print still passes while sliding off one end of the block, which is
        # exactly how a one-line insertion above main() would go unnoticed --
        # so the first cited line is asserted to be the read of the grant,
        # which is what makes "granted nothing" legible at all.
        cited = self.cited_lines()
        self.assertEqual('queries = claimed.get("queries", [])',
                         cited[0].strip(),
                         "the cited range does not start where the grant is "
                         "read")
        body = "\n".join(cited)
        self.assertIn("if not queries:", body,
                      "the cited range is not the granted-nothing branch")
        self.assertIn('print("worker: nothing to do', body,
                      "the cited range does not print what this docstring "
                      "says it prints")

    def test_the_cited_lines_leave_by_a_bare_return(self):
        # "exits 0" is the other half of the claim and the half a nearby
        # sys.exit(1) would quietly falsify -- main() has three of those above
        # this branch. A bare return is what cli() turns into exit 0
        # (`contributor-worker/google-serpapi-worker.py:811-812`, reached from
        # `:816`), and this asserts the branch leaves that way and not another.
        cited = self.cited_lines()
        self.assertNotIn("sys.exit", "\n".join(cited))
        self.assertEqual("return", cited[-1].strip())


if __name__ == "__main__":
    unittest.main()

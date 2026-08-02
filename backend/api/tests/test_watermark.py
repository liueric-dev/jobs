"""Defect D08: an empty submission must not advance the query's watermark.

WHAT WAS WRONG. `submit` called `qc.mark_success` unconditionally
(`app.py`, the block above `log_query_stats`). `{"jobs": []}` therefore upserted
nothing and still marked the query covered for
GOOGLE_JOBS_MIN_HOURS_BETWEEN_RUNS, so every posting published in that window
was skipped by every path, permanently, while the response said success. That is
the register's "silent data loss" class in one statement.

WHY THE PIPELINE IS ALLOWED TO DO THE OPPOSITE, and why that is not an
inconsistency: `ingest/google-serpapi.py:335-351` advances the watermark on zero
results because it made the SerpApi call itself and knows the fetch succeeded.
This endpoint only ever sees an array, and an empty one is what an exhausted
key, a blocked worker, a wrong chip and a genuinely quiet query all look like
from here. The pipeline has evidence; the API has a caller it does not trust.

THE SHAPE OF THE FIX, pinned below because each part is load-bearing:
  - no mark_success, so the window is not consumed;
  - release_claim, so the query returns to the pool now rather than in
    CLAIM_TTL_MINUTES -- an empty result is weak evidence that THIS worker has a
    problem, and the next contributor has a different SerpApi account;
  - a submission_log row anyway, because "a contributor whose submissions are
    consistently empty is a broken worker, not a lazy person" and that is only
    discoverable if the empty ones are recorded;
  - `watermark_advanced` in the response, so a worker author can tell the two
    outcomes apart without reading this file.
"""

import asyncio
import os
import sys
import unittest

# BOTH directories, and neither is redundant. api/ is what `import app` needs
# and `-m unittest discover -s tests` does not add it; tests/ is what
# `import fakedb` needs when this module is loaded as `tests.test_watermark`
# (running one case by dotted name) rather than as a top-level module (what
# discover does). Absolute rather than relative imports for that same reason --
# webapp/tests draws the same line.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fakedb import FakeConn, FakeRequest, patch_db   # noqa: E402

import app                                          # noqa: E402
import query_claims as qc                           # noqa: E402

DATASET = "google_jobs:query:ai-engineer-nyc"
SLUG = "ai-engineer-nyc"
NOW = "2026-08-02T12:00:00"

#: A live claim held by the caller: claimed_by matches, claim_granted_at equals
#: claimed_at (nobody took it over), and claimed_at is inside the TTL. All three
#: are required by holds_claim; a test that got any of them wrong would get a
#: 409 and pass for the wrong reason, so every case below asserts on the write
#: it expected rather than merely on the absence of an exception.
def live_claim(contributor="c_test"):
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
    return (contributor, now, now)


def a_real_slug():
    """A slug that IS in the committed query bank.

    Not invented: _mode_for_slug now 409s on a slug the bank does not know
    (defect D09), so a made-up one would make every test here fail for the wrong
    reason.
    """
    buckets = qc.load_query_buckets()
    for bucket in buckets.values():
        return bucket["queries"][0]["slug"]
    raise AssertionError("the query bank is empty")


class _SubmitCase(unittest.TestCase):

    def submit(self, conn, jobs_json, slug=None):
        slug = slug or a_real_slug()
        dataset = f"google_jobs:query:{slug}"
        restore = patch_db(app, conn)
        try:
            return asyncio.run(app.submit(
                dataset=dataset,
                request=FakeRequest(jobs_json),
                authorization="Bearer key",
            )), dataset
        finally:
            restore()


class TestEmptySubmission(_SubmitCase):

    def setUp(self):
        self.conn = FakeConn(claim_state=live_claim())

    def test_an_empty_submission_does_not_advance_the_watermark(self):
        # THE DEFECT. Reverting the `if not payload.jobs` branch in app.submit
        # turns this line red: mark_success runs, conn.marked gains a row.
        result, _ = self.submit(self.conn, '{"jobs": []}')
        self.assertEqual(self.conn.marked, [],
                         "mark_success ran for a submission that stored nothing")
        self.assertFalse(result["watermark_advanced"])

    def test_an_empty_submission_releases_the_claim(self):
        # Otherwise the query is locked for CLAIM_TTL_MINUTES by a worker that
        # has just demonstrated it cannot fetch.
        _, dataset = self.submit(self.conn, '{"jobs": []}')
        self.assertEqual(self.conn.released, [dataset])

    def test_an_empty_submission_is_still_logged(self):
        self.submit(self.conn, '{"jobs": []}')
        rows = self.conn.rows("submit")
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["fetched_count"], 0)
        self.assertIn("empty", rows[0]["reason"])

    def test_an_empty_submission_does_not_write_query_stats(self):
        # log_query_stats is a record of a run that happened. Zero rows from a
        # fetch that may never have occurred is not a data point about the
        # query's yield, and google_jobs_query_stats is read as exactly that.
        self.submit(self.conn, '{"jobs": []}')
        self.assertEqual(self.conn.stats, [])

    def test_it_is_not_an_error_for_the_contributor(self):
        # A 4xx would leave the honest "my search genuinely returned nothing"
        # worker retrying forever and reporting failures to its owner. The
        # outcome is recorded, not punished.
        result, _ = self.submit(self.conn, '{"jobs": []}')
        self.assertEqual(result["accepted"], 0)
        self.assertEqual(result["new"], 0)


class TestNonEmptySubmissionStillAdvances(_SubmitCase):
    """The other half: the fix must not stop a real submission working."""

    def setUp(self):
        self.conn = FakeConn(claim_state=live_claim())
        self._real_upsert = qc.upsert

        class Result:
            new, updated, unchanged, errors = 1, 0, 0, []

        qc.upsert = lambda conn, records: Result()
        self.addCleanup(lambda: setattr(qc, "upsert", self._real_upsert))

    def test_a_submission_with_rows_advances_the_watermark(self):
        result, dataset = self.submit(
            self.conn,
            '{"jobs": [{"title": "AI Engineer", "company_name": "Acme"}]}')
        self.assertEqual(len(self.conn.marked), 1)
        self.assertEqual(self.conn.marked[0][0], dataset)
        self.assertTrue(result["watermark_advanced"])
        self.assertEqual(self.conn.released, [])

    def test_a_submission_with_rows_writes_stats_and_a_log_row(self):
        self.submit(self.conn,
                    '{"jobs": [{"title": "AI Engineer", "company_name": "Acme"}]}')
        self.assertEqual(len(self.conn.stats), 1)
        self.assertEqual(len(self.conn.rows("submit")), 1)


if __name__ == "__main__":
    unittest.main()

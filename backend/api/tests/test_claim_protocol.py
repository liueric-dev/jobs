"""Defect D72: the claim protocol, against a real Postgres schema.

WHY THIS FILE IS NOT PART OF THE REST OF THIS SUITE
    `tests/fakedb.py` says it in its own docstring: it dispatches on SQL text
    and cannot falsify a WHERE clause. Every other module here asserts on a
    DECISION -- did `claim` write a row the cap can see, did an empty submit
    call mark_success -- and a fake falsifies a decision exactly. The claim
    protocol is not a decision. `try_claim_query`'s conditional update and
    `holds_claim`'s three conditions ARE SQL semantics, and against a fake they
    pass whether or not the conditions are there. That is why the suite was
    green beside an untested core, which is the state defect D72 was filed in.

    `backend/webapp/tests/test_event_replay.py` is the worked pattern and this
    follows it: a scratch schema from `evals/scratchdb`, skipped where no
    database is available rather than passing vacuously.

THE CREDENTIAL INDIRECTION, AND WHY IT IS NOT OPTIONAL
    `scratchdb.create()` calls `schema.ensure_schema()`, which issues CREATE
    SCHEMA. This service's role is `jobs_api`, which by design holds no DDL at
    all -- that is the security property `verify_schema()` exists to preserve.
    So the scratch schema is created on the PIPELINE's credential, read out of
    `backend/.env` and published ONLY as JOBS_SCRATCH_DATABASE_URL, the escape
    hatch `scratchdb.scratch_url()` documents and prefers. It is deliberately
    not merged into the environment: quietly switching this service's own
    DATABASE_URL inside its own test suite is the kind of thing that gets
    debugged for an afternoon, and nothing in `api/` reads the scratch name.

WHAT THIS DOES AND DOES NOT EXERCISE
    query_claims.py's claim SQL, run by Postgres, on tables created by the same
    `ensure_schema()` an operator's `init-schema` reaches. Not exercised:
    FastAPI routing and authentication, which the other modules cover with a
    fake and which would need a live api_keys row to reach. Not exercised
    either: a genuine simultaneous race -- see TestTwoSessions for what is
    claimed instead and why.
"""

import contextlib
import os
import sys
import unittest
from datetime import datetime, timedelta, timezone

API_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BACKEND_DIR = os.path.dirname(API_DIR)
sys.path.insert(0, API_DIR)
sys.path.insert(0, BACKEND_DIR)

import query_claims as qc                             # noqa: E402
import schema                                         # noqa: E402
from evals import scratchdb                           # noqa: E402
from lib import envfile                               # noqa: E402
from lib import state as pipeline_state               # noqa: E402

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

DATASET = "google_jobs:query:ai-engineer-nyc"
A = "c_alpha"
B = "c_beta"

#: A moment to anchor every relative time to, so nothing here depends on how
#: long the test took to run. try_claim_query and holds_claim both take now_dt;
#: the pipeline's own try_claim does not, which is what TestTheTakeoverGuard
#: turns into the point rather than the obstacle.
NOW = datetime(2026, 8, 2, 12, 0, 0, tzinfo=timezone.utc)
TTL = timedelta(minutes=qc.CLAIM_TTL_MINUTES)


@contextlib.contextmanager
def api_scratch_schema():
    """A scratch schema with the pipeline's tables AND this service's.

    `scratchdb.scratch_schema()` calls `schema.ensure_schema()` and nothing
    else -- it belongs to the pipeline and knows nothing about contributors,
    api_keys, submission_log or the two extra claim columns. `qc.ensure_schema`
    is called INSIDE the body, where `schema.SCHEMA` is still pointed at the
    scratch name, so its unqualified CREATEs land there like everything else.

    ONE SUBTLETY WORTH NAMING because it looks like a bug on a fast read:
    `qc.ensure_schema` opens with `SET search_path TO public`, which would put
    the contributor tables in the wrong schema -- except that the very next
    thing it does is call `schema.ensure_schema()`, which issues its own
    `SET search_path TO {SCHEMA}` (../schema.py). The search_path is therefore
    back on the scratch schema before any DDL this service owns is issued.
    Reordering those two calls would silently create contributor tables in
    `public`, which is exactly the kind of thing a test that only ever ran
    against `public` could not tell you.
    """
    with scratchdb.scratch_schema() as (conn, name):
        qc.ensure_schema(conn)
        yield conn, name


def row(conn, dataset=DATASET):
    """(last_success_at, claimed_at, claimed_by, claim_granted_at), or None."""
    return conn.execute(
        "SELECT last_success_at, claimed_at, claimed_by, claim_granted_at "
        "FROM job_ingest_state WHERE dataset = %s", (dataset,)).fetchone()


def stamp(dt):
    return dt.strftime("%Y-%m-%dT%H:%M:%S")


@requires_db
class TestTryClaimQuery(unittest.TestCase):
    """The conditional update. Every assertion here is about a WHERE clause."""

    def test_a_first_claim_creates_the_row_with_the_never_run_sentinel(self):
        with api_scratch_schema() as (conn, _):
            self.assertTrue(qc.try_claim_query(conn, DATASET, NOW, A))
            last_success, claimed_at, claimed_by, granted = row(conn)
            # '' and not NULL: the column is NOT NULL, and stalest-first
            # ordering relies on '' sorting before every real timestamp.
            self.assertEqual(last_success, "")
            self.assertEqual(claimed_by, A)
            self.assertEqual(claimed_at, stamp(NOW))
            # The two must be equal at grant time. holds_claim's takeover guard
            # is nothing but "are these still equal".
            self.assertEqual(granted, claimed_at)

    def test_a_second_claimant_loses_and_changes_nothing(self):
        # THE PROPERTY THE WHOLE SERVICE RESTS ON. A fake connection returns
        # whatever it was told to; only a server evaluates the WHERE.
        with api_scratch_schema() as (conn, _):
            qc.try_claim_query(conn, DATASET, NOW, A)
            before = row(conn)
            self.assertFalse(
                qc.try_claim_query(conn, DATASET, NOW + timedelta(minutes=1), B))
            # Not merely "returned False": a losing claim must not have written
            # claimed_by=B and then reported failure.
            self.assertEqual(row(conn), before)

    def test_an_expired_claim_is_stealable(self):
        with api_scratch_schema() as (conn, _):
            qc.try_claim_query(conn, DATASET, NOW - TTL - timedelta(minutes=1), A)
            self.assertTrue(qc.try_claim_query(conn, DATASET, NOW, B))
            _, claimed_at, claimed_by, granted = row(conn)
            self.assertEqual(claimed_by, B)
            self.assertEqual(claimed_at, stamp(NOW))
            self.assertEqual(granted, stamp(NOW))

    def test_a_claim_exactly_at_the_ttl_is_not_stealable(self):
        # The comparison is `claimed_at < ttl_cutoff`, strictly. Pinned because
        # a boundary is where an off-by-one lives, and because loosening it to
        # <= would make a claim expire a whole TTL early under a clock that
        # rounds -- handing a live query to a second contributor.
        with api_scratch_schema() as (conn, _):
            qc.try_claim_query(conn, DATASET, NOW - TTL, A)
            self.assertFalse(qc.try_claim_query(conn, DATASET, NOW, B))
            self.assertEqual(row(conn)[2], A)

    def test_a_released_claim_is_claimable_immediately(self):
        # The `claimed_at IS NULL` half of the WHERE -- the reason release
        # exists at all, and the reason an empty submit releases rather than
        # holds (defect D08).
        with api_scratch_schema() as (conn, _):
            qc.try_claim_query(conn, DATASET, NOW, A)
            qc.release_claim(conn, DATASET)
            self.assertTrue(
                qc.try_claim_query(conn, DATASET, NOW + timedelta(seconds=1), B))
            self.assertEqual(row(conn)[2], B)

    def test_a_claim_does_not_disturb_the_watermark(self):
        # Claiming is a lease, not progress. If it touched last_success_at, a
        # worker that claimed and died would look like a successful run and the
        # window it never fetched would be skipped by every path.
        with api_scratch_schema() as (conn, _):
            qc.mark_success(conn, DATASET, "2026-08-01T00:00:00")
            qc.try_claim_query(conn, DATASET, NOW, A)
            self.assertEqual(row(conn)[0], "2026-08-01T00:00:00")


@requires_db
class TestHoldsClaim(unittest.TestCase):
    """The three conditions, each falsified on its own."""

    def test_the_claimant_holds_its_own_fresh_claim(self):
        with api_scratch_schema() as (conn, _):
            qc.try_claim_query(conn, DATASET, NOW, A)
            self.assertTrue(qc.holds_claim(conn, DATASET, A, NOW))

    def test_another_contributor_does_not(self):
        with api_scratch_schema() as (conn, _):
            qc.try_claim_query(conn, DATASET, NOW, A)
            self.assertFalse(qc.holds_claim(conn, DATASET, B, NOW))

    def test_an_expired_claim_is_not_held_even_by_its_owner(self):
        with api_scratch_schema() as (conn, _):
            qc.try_claim_query(conn, DATASET, NOW, A)
            self.assertFalse(
                qc.holds_claim(conn, DATASET, A, NOW + TTL + timedelta(minutes=1)))

    def test_a_claim_exactly_at_the_ttl_is_still_held(self):
        # `claimed_at >= ttl_cutoff`, and the other side of the boundary
        # test_a_claim_exactly_at_the_ttl_is_not_stealable pins. The two
        # comparisons are in different functions and must agree: a window where
        # the owner has lost the claim and nobody else can take it is a query
        # frozen for no reason.
        with api_scratch_schema() as (conn, _):
            qc.try_claim_query(conn, DATASET, NOW, A)
            self.assertTrue(qc.holds_claim(conn, DATASET, A, NOW + TTL))

    def test_a_dataset_with_no_row_is_held_by_nobody(self):
        with api_scratch_schema() as (conn, _):
            self.assertFalse(qc.holds_claim(conn, DATASET, A, NOW))

    def test_a_released_claim_is_not_held(self):
        with api_scratch_schema() as (conn, _):
            qc.try_claim_query(conn, DATASET, NOW, A)
            qc.release_claim(conn, DATASET)
            self.assertFalse(qc.holds_claim(conn, DATASET, A, NOW))

    def test_a_successful_submit_consumes_the_claim(self):
        # mark_success clears all three columns, so a worker cannot submit
        # twice against one claim and advance the watermark twice.
        with api_scratch_schema() as (conn, _):
            qc.try_claim_query(conn, DATASET, NOW, A)
            qc.mark_success(conn, DATASET, stamp(NOW))
            self.assertFalse(qc.holds_claim(conn, DATASET, A, NOW))


@requires_db
class TestTheTakeoverGuard(unittest.TestCase):
    """`claim_granted_at`, against the pipeline's REAL claim statement.

    query_claims.py's docstring says this was "found by testing against the
    pipeline's real SQL, not theorized", and the test is only worth anything if
    it keeps doing that -- so the takeover below is performed by
    `lib.state.try_claim`, the function `ingest/google-serpapi.py` actually
    calls, rather than by a hand-written UPDATE that agrees with this file's
    idea of what that function does. If the pipeline ever learns about
    `claimed_by`, these tests change behaviour and say so.
    """

    def take_over_as_the_pipeline(self, conn):
        """The pipeline claims the same row. Returns whether it won.

        It sets claimed_at and knows nothing of claimed_by -- which is the
        whole problem, and is asserted rather than assumed in
        test_the_pipeline_leaves_claimed_by_stale below.
        """
        return pipeline_state.try_claim(
            conn, DATASET, ttl_minutes=qc.CLAIM_TTL_MINUTES,
            table=schema.WATERMARK_TABLE)

    def test_the_pipeline_leaves_claimed_by_stale(self):
        # THE PREMISE, pinned separately from the guard that defends against
        # it. If this ever fails, the guard is defending against nothing and
        # somebody should be told rather than left to wonder why the code is
        # shaped this way.
        with api_scratch_schema() as (conn, _):
            qc.try_claim_query(conn, DATASET, NOW - TTL - timedelta(minutes=5), A)
            self.assertTrue(self.take_over_as_the_pipeline(conn))
            _, claimed_at, claimed_by, granted = row(conn)
            self.assertEqual(claimed_by, A, "the pipeline does not clear it")
            self.assertNotEqual(claimed_at, granted,
                                "the pipeline rewrote claimed_at")

    def test_a_naive_check_would_have_said_yes(self):
        # Why the guard is not paranoia. After the takeover BOTH conditions a
        # naive `claimed_by == caller and claimed_at is fresh` check would look
        # at are satisfied, and the claim is nonetheless gone.
        with api_scratch_schema() as (conn, _):
            qc.try_claim_query(conn, DATASET, NOW - TTL - timedelta(minutes=5), A)
            self.take_over_as_the_pipeline(conn)
            _, claimed_at, claimed_by, _ = row(conn)
            now = datetime.now(timezone.utc)
            cutoff = stamp(now - TTL)
            self.assertEqual(claimed_by, A)
            self.assertGreaterEqual(claimed_at, cutoff)

    def test_holds_claim_says_no_after_a_takeover(self):
        # THE DEFECT THE GUARD PREVENTS: A submits, is let through, writes
        # results and calls mark_success -- clobbering the watermark while the
        # local pipeline is mid-fetch. Delete the claim_granted_at comparison
        # from holds_claim and this is the test that goes red.
        with api_scratch_schema() as (conn, _):
            qc.try_claim_query(conn, DATASET, NOW - TTL - timedelta(minutes=5), A)
            self.take_over_as_the_pipeline(conn)
            self.assertFalse(
                qc.holds_claim(conn, DATASET, A, datetime.now(timezone.utc)))

    def test_a_re_grant_to_the_same_contributor_is_a_live_claim_again(self):
        # The guard must not be a one-way latch. A contributor whose claim
        # expired and who legitimately re-claims the same query holds it: the
        # re-grant writes claimed_at and claim_granted_at together, so they
        # match again.
        with api_scratch_schema() as (conn, _):
            qc.try_claim_query(conn, DATASET, NOW - TTL - timedelta(minutes=5), A)
            self.assertTrue(qc.try_claim_query(conn, DATASET, NOW, A))
            self.assertTrue(qc.holds_claim(conn, DATASET, A, NOW))

    def test_a_takeover_by_another_contributor_also_revokes_the_claim(self):
        # Same guard, the other route in: B's claim rewrites all three columns,
        # so A loses on claimed_by and would lose on claim_granted_at too.
        with api_scratch_schema() as (conn, _):
            qc.try_claim_query(conn, DATASET, NOW - TTL - timedelta(minutes=5), A)
            qc.try_claim_query(conn, DATASET, NOW, B)
            self.assertFalse(qc.holds_claim(conn, DATASET, A, NOW))
            self.assertTrue(qc.holds_claim(conn, DATASET, B, NOW))


@requires_db
class TestMarkSuccessAndRelease(unittest.TestCase):

    def test_mark_success_advances_the_watermark_and_drops_the_claim(self):
        with api_scratch_schema() as (conn, _):
            qc.try_claim_query(conn, DATASET, NOW, A)
            qc.mark_success(conn, DATASET, "2026-08-02T12:30:00")
            last_success, claimed_at, claimed_by, granted = row(conn)
            self.assertEqual(last_success, "2026-08-02T12:30:00")
            self.assertIsNone(claimed_at)
            self.assertIsNone(claimed_by)
            self.assertIsNone(granted)

    def test_mark_success_creates_the_row_when_there_is_none(self):
        # The INSERT half of the upsert. Reached by a submit against a dataset
        # whose row was somehow removed, and the case that would 500 silently
        # if this were an UPDATE.
        with api_scratch_schema() as (conn, _):
            qc.mark_success(conn, DATASET, "2026-08-02T12:30:00")
            self.assertEqual(row(conn)[0], "2026-08-02T12:30:00")

    def test_release_frees_the_claim_and_leaves_the_watermark_alone(self):
        # The distinction the whole D08 decision turns on: releasing says "this
        # attempt produced nothing", which must not be recorded as coverage.
        with api_scratch_schema() as (conn, _):
            qc.mark_success(conn, DATASET, "2026-08-01T00:00:00")
            qc.try_claim_query(conn, DATASET, NOW, A)
            qc.release_claim(conn, DATASET)
            last_success, claimed_at, claimed_by, granted = row(conn)
            self.assertEqual(last_success, "2026-08-01T00:00:00")
            self.assertIsNone(claimed_at)
            self.assertIsNone(claimed_by)
            self.assertIsNone(granted)

    def test_release_on_an_absent_dataset_is_a_no_op(self):
        with api_scratch_schema() as (conn, _):
            qc.release_claim(conn, DATASET)
            self.assertIsNone(row(conn))


@requires_db
class TestPickStaleQueries(unittest.TestCase):
    """Bucket selection, with the array read and the claims done for real.

    The fake returns every watermark it was given regardless of the
    `dataset = ANY(%s)` filter, so bucket membership, stalest-first ordering
    and the too-recent break are all unfalsifiable there.
    """

    @staticmethod
    def bank(slugs, budget):
        return {"b": {"daily_budget": budget,
                      "queries": [{"slug": s, "query": f"q {s}",
                                   "location": "New York", "mode": "nyc"}
                                  for s in slugs]}}

    def test_never_run_queries_are_claimed_first(self):
        with api_scratch_schema() as (conn, _):
            qc.mark_success(conn, "google_jobs:query:fresh",
                            stamp(datetime.now(timezone.utc)
                                  - timedelta(days=30)))
            picked = qc.pick_stale_queries_by_bucket(
                conn, self.bank(["fresh", "never"], budget=1), A)
            self.assertEqual([q["slug"] for q, _ in picked], ["never"])

    def test_a_query_someone_else_holds_is_skipped_for_the_next_stalest(self):
        # The load-balancing property, and the reason a lost claim does not
        # consume the bucket's budget: with budget 1 the walk must reach the
        # second candidate.
        with api_scratch_schema() as (conn, _):
            qc.try_claim_query(conn, "google_jobs:query:s0",
                               datetime.now(timezone.utc), B)
            picked = qc.pick_stale_queries_by_bucket(
                conn, self.bank(["s0", "s1"], budget=1), A)
            self.assertEqual([q["slug"] for q, _ in picked], ["s1"])
            self.assertEqual(row(conn, "google_jobs:query:s0")[2], B)

    def test_the_bucket_budget_caps_the_grants(self):
        with api_scratch_schema() as (conn, _):
            picked = qc.pick_stale_queries_by_bucket(
                conn, self.bank(["s0", "s1", "s2", "s3"], budget=2), A)
            self.assertEqual(len(picked), 2)

    def test_max_queries_caps_the_grants_independently_of_the_budget(self):
        with api_scratch_schema() as (conn, _):
            picked = qc.pick_stale_queries_by_bucket(
                conn, self.bank(["s0", "s1", "s2", "s3"], budget=4), A,
                max_queries=1)
            self.assertEqual(len(picked), 1)

    def test_a_bucket_whose_stalest_ran_recently_yields_nothing(self):
        # The MIN_HOURS_BETWEEN_RUNS break. Because ordering is stalest-first,
        # a too-recent head means every tail entry is fresher still, so the
        # bucket's work for this interval is already done -- spending more
        # budget would re-fetch a window somebody else covered.
        recent = stamp(datetime.now(timezone.utc) - timedelta(hours=1))
        with api_scratch_schema() as (conn, _):
            for slug in ("s0", "s1"):
                qc.mark_success(conn, f"google_jobs:query:{slug}", recent)
            picked = qc.pick_stale_queries_by_bucket(
                conn, self.bank(["s0", "s1"], budget=2), A)
            self.assertEqual(picked, [])

    def test_the_last_run_returned_beside_each_query_is_its_own_watermark(self):
        # app.claim passes this straight to choose_date_chip, so pairing a slug
        # with another slug's watermark would hand the contributor a date chip
        # covering the wrong window -- and the postings in the real gap would
        # never be fetched by anyone.
        old = stamp(datetime.now(timezone.utc) - timedelta(days=5))
        with api_scratch_schema() as (conn, _):
            qc.mark_success(conn, "google_jobs:query:s1", old)
            picked = qc.pick_stale_queries_by_bucket(
                conn, self.bank(["s0", "s1"], budget=2), A)
            by_slug = {q["slug"]: last for q, last in picked}
            self.assertEqual(by_slug["s1"], old)
            self.assertIsNone(by_slug["s0"])


@requires_db
class TestTwoSessions(unittest.TestCase):
    """Across connections, which is where "two claimants" actually lives.

    WHAT IS CLAIMED, precisely: a claim committed by one session is visible to
    and blocking for an independent one. WHAT IS NOT: a genuinely simultaneous
    race. Two overlapping uncommitted `INSERT ... ON CONFLICT DO UPDATE`
    statements on one key BLOCK on a row lock rather than interleaving, so a
    test of that would either deadlock the suite or need a second thread and a
    timeout -- and the property it would establish is Postgres's, not this
    file's. `evals/tests/test_scratchdb.py` makes the same argument about which
    concurrency tests are worth having.
    """

    def test_a_committed_claim_blocks_an_independent_session(self):
        with api_scratch_schema() as (conn, name):
            qc.try_claim_query(conn, DATASET, NOW, A)
            with scratchdb.second_connection(name) as other:
                self.assertFalse(qc.try_claim_query(other, DATASET, NOW, B))
                self.assertFalse(qc.holds_claim(other, DATASET, B, NOW))
                self.assertTrue(qc.holds_claim(other, DATASET, A, NOW))

    def test_a_release_in_one_session_frees_the_query_in_another(self):
        with api_scratch_schema() as (conn, name):
            qc.try_claim_query(conn, DATASET, NOW, A)
            qc.release_claim(conn, DATASET)
            with scratchdb.second_connection(name) as other:
                self.assertTrue(qc.try_claim_query(other, DATASET, NOW, B))


if __name__ == "__main__":
    unittest.main()

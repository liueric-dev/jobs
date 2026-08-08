"""T-26: the second claim mode, over `search_queries` rows, against real SQL.

WHY THIS FILE IS BESIDE test_claim_protocol.py AND NOT INSIDE THE FAKE SUITE
    `tests/fakedb.py` dispatches on SQL text and cannot falsify a WHERE clause,
    so every assertion here would pass against it whether or not the conditions
    exist -- which is the state defect D72 was filed in and the argument
    test_claim_protocol.py opens with. This mode's two protections ARE SQL
    semantics, so this follows that file exactly: a scratch schema from
    `evals/scratchdb`, created on the PIPELINE's credential (this service's role
    holds no DDL by design), skipped where no database is available rather than
    passing vacuously.

    `search_queries` needs no extra provisioning step to appear here:
    `schema.ensure_schema()` calls `ensure_search_query_schema()` itself
    (../../schema.py:962), so `scratchdb.scratch_schema()` already brings it.

ONE CLOCK, NOT TWO
    Every timestamp below is derived from NOW, including the takeover writer's
    -- which takes its `now_dt` as an argument for that reason and not for
    tidiness. Two tests in this repo rotted by pairing a real-clock timestamp
    with a hardcoded one and passed only inside a window (TASKS.md's note above
    T-26). Nothing here reads the wall clock at all, so nothing here can.
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

#: The one moment everything here is measured from. See ONE CLOCK above.
NOW = datetime(2026, 8, 2, 12, 0, 0, tzinfo=timezone.utc)
TTL = timedelta(minutes=qc.CLAIM_TTL_MINUTES)


def stamp(dt):
    return dt.strftime("%Y-%m-%dT%H:%M:%S")


@contextlib.contextmanager
def api_scratch_schema():
    """A scratch schema with the pipeline's tables AND this service's.

    Identical to test_claim_protocol.py's, and deliberately not imported from
    it: that module is a sibling under `unittest discover`, not a package, so
    importing it would depend on the discovery root rather than on sys.path.
    The subtlety it documents applies here unchanged -- `qc.ensure_schema`
    opens with `SET search_path TO public` and is saved by `schema.ensure_schema
    ()` immediately re-pointing it at the scratch name.
    """
    with scratchdb.scratch_schema() as (conn, name):
        qc.ensure_schema(conn)
        yield conn, name


def register(conn, text, location="new york"):
    """Insert one `search_queries` row the way the webapp's register does, and
    return its id.

    Written out rather than routed through `searchnorm.REGISTER_QUERY_SQL`
    because normalization is not what is under test here and that statement
    would drag its whole normalize/dedupe contract in with it. The columns are
    only the NOT NULL ones plus `source`, which carries a CHECK.
    """
    return conn.execute(
        """
        INSERT INTO search_queries
            (normalized_text, normalized_location, display_text,
             display_location, source, first_requested_at)
        VALUES (%s, %s, %s, %s, 'builder', %s)
        RETURNING id
        """,
        (text, location, text, location, stamp(NOW - timedelta(days=1))),
    ).fetchone()[0]


def row(conn, query_id):
    """(claimed_at, claimed_by, claim_granted_at) for one query."""
    return conn.execute(
        "SELECT claimed_at, claimed_by, claim_granted_at "
        "FROM search_queries WHERE id = %s",
        (query_id,),
    ).fetchone()


def take_over_knowing_only_claimed_at(conn, query_id, now_dt):
    """A claimant that leases the row and has never heard of `claimed_by`.

    THIS IS A HAND-WRITTEN STATEMENT, AND test_claim_protocol.py IS EMPHATIC
    THAT ITS EQUIVALENT MUST NOT BE. That file performs its takeover with
    `lib.state.try_claim` -- the function `ingest/google-serpapi.py` actually
    calls -- on the argument that a hand-written UPDATE only tests this file's
    idea of what the pipeline does. The argument is right and does not apply
    here, for a reason worth stating rather than working around: NOTHING IN
    THIS TREE LEASES A search_queries ROW TODAY. `lib.state.try_claim` is keyed
    on a `dataset` TEXT primary key in a watermark table (../../lib/state.py:98)
    and cannot address this table at all; ../../searchqueries.py's due_queries()
    and record_run() are the pipeline's only writers here and neither claims
    anything.

    So this is the shape rather than the caller: `lib.state.try_claim`'s
    statement with the key column swapped and nothing else changed -- one
    conditional UPDATE that sets claimed_at, reads no claimed_by and writes no
    claim_granted_at, because it does not know they exist. Every writer that
    0007 puts on these rows without knowing about this service is that shape,
    and the guard has to hold against it before the first one lands rather
    than after.
    """
    cutoff = stamp(now_dt - TTL)
    cur = conn.execute(
        """
        UPDATE search_queries
           SET claimed_at = %(now)s
         WHERE id = %(id)s
           AND (claimed_at IS NULL OR claimed_at < %(cutoff)s)
        RETURNING id
        """,
        {"id": query_id, "now": stamp(now_dt), "cutoff": cutoff},
    )
    won = cur.fetchone() is not None
    conn.commit()
    return won


@requires_db
class TestTryClaimSearchQuery(unittest.TestCase):
    """The conditional update. Every assertion here is about a WHERE clause."""

    def test_a_first_claim_records_all_three_columns(self):
        with api_scratch_schema() as (conn, _):
            qid = register(conn, "ai engineer")
            self.assertTrue(qc.try_claim_search_query(conn, qid, NOW, A))
            claimed_at, claimed_by, granted = row(conn, qid)
            self.assertEqual(claimed_by, A)
            self.assertEqual(claimed_at, stamp(NOW))
            # Equal at grant time. The takeover guard is nothing but "are these
            # still equal", so a mode that wrote them apart would be born
            # holding no claim at all.
            self.assertEqual(granted, claimed_at)

    def test_a_second_claimant_loses_and_changes_nothing(self):
        # THE PROPERTY THE WHOLE MODE RESTS ON. A fake connection returns
        # whatever it was told to; only a server evaluates the WHERE.
        with api_scratch_schema() as (conn, _):
            qid = register(conn, "ai engineer")
            qc.try_claim_search_query(conn, qid, NOW, A)
            before = row(conn, qid)
            self.assertFalse(
                qc.try_claim_search_query(conn, qid, NOW + timedelta(minutes=1), B))
            # Not merely "returned False": a losing claim must not have written
            # claimed_by=B and then reported failure.
            self.assertEqual(row(conn, qid), before)

    def test_an_expired_claim_is_stealable(self):
        with api_scratch_schema() as (conn, _):
            qid = register(conn, "ai engineer")
            qc.try_claim_search_query(conn, qid, NOW - TTL - timedelta(minutes=1), A)
            self.assertTrue(qc.try_claim_search_query(conn, qid, NOW, B))
            claimed_at, claimed_by, granted = row(conn, qid)
            self.assertEqual(claimed_by, B)
            self.assertEqual(claimed_at, stamp(NOW))
            self.assertEqual(granted, stamp(NOW))

    def test_a_claim_exactly_at_the_ttl_is_not_stealable(self):
        # `claimed_at < ttl_cutoff`, strictly, and the same boundary
        # test_claim_protocol.py pins on the other table. Loosening it to <=
        # expires a claim a whole TTL early under a clock that rounds, handing
        # a live query to a second contributor.
        with api_scratch_schema() as (conn, _):
            qid = register(conn, "ai engineer")
            qc.try_claim_search_query(conn, qid, NOW - TTL, A)
            self.assertFalse(qc.try_claim_search_query(conn, qid, NOW, B))
            self.assertEqual(row(conn, qid)[1], A)

    def test_a_released_claim_is_claimable_immediately(self):
        with api_scratch_schema() as (conn, _):
            qid = register(conn, "ai engineer")
            qc.try_claim_search_query(conn, qid, NOW, A)
            qc.release_search_query_claim(conn, qid)
            self.assertTrue(
                qc.try_claim_search_query(conn, qid, NOW + timedelta(seconds=1), B))
            self.assertEqual(row(conn, qid)[1], B)

    def test_a_claim_against_an_absent_id_creates_nothing(self):
        # The one structural difference from try_claim_query, which INSERTs.
        # A search_queries row exists because a Builder saved the keyword; a
        # claim must never be what conjures one.
        with api_scratch_schema() as (conn, _):
            self.assertFalse(qc.try_claim_search_query(conn, 424242, NOW, A))
            self.assertEqual(
                conn.execute(
                    "SELECT count(*) FROM search_queries"
                ).fetchone()[0], 0)

    def test_a_claim_touches_exactly_one_row(self):
        # THE PARENTHESES. Written as `id = %s AND claimed_at IS NULL OR
        # claimed_at < cutoff` the predicate groups as
        # `(id = %s AND claimed_at IS NULL) OR (claimed_at < cutoff)`, so every
        # expired claim in the table is taken over by a claim aimed at one row
        # -- reported as a win, with the other Builders' queries silently
        # reassigned. RETURNING still hands back a row, so only a second row
        # can catch it.
        with api_scratch_schema() as (conn, _):
            mine = register(conn, "ai engineer")
            theirs = register(conn, "data analyst")
            qc.try_claim_search_query(
                conn, theirs, NOW - TTL - timedelta(minutes=1), B)
            expired = row(conn, theirs)
            self.assertTrue(qc.try_claim_search_query(conn, mine, NOW, A))
            self.assertEqual(row(conn, theirs), expired)

    def test_a_claim_disturbs_no_run_statistics(self):
        # Claiming is a lease, not a run. If it moved last_run_at a worker that
        # claimed and died would look like a completed run, and the window it
        # never fetched would be skipped by due_queries() forever.
        with api_scratch_schema() as (conn, _):
            qid = register(conn, "ai engineer")
            conn.execute(
                "UPDATE search_queries SET last_run_at = %s WHERE id = %s",
                (stamp(NOW - timedelta(days=2)), qid))
            conn.commit()
            qc.try_claim_search_query(conn, qid, NOW, A)
            after = conn.execute(
                "SELECT last_run_at, run_count FROM search_queries "
                "WHERE id = %s", (qid,)).fetchone()
            self.assertEqual(after, (stamp(NOW - timedelta(days=2)), 0))


@requires_db
class TestHoldsSearchQueryClaim(unittest.TestCase):
    """The three conditions, each falsified on its own."""

    def test_the_claimant_holds_its_own_fresh_claim(self):
        with api_scratch_schema() as (conn, _):
            qid = register(conn, "ai engineer")
            qc.try_claim_search_query(conn, qid, NOW, A)
            self.assertTrue(qc.holds_search_query_claim(conn, qid, A, NOW))

    def test_another_contributor_does_not(self):
        with api_scratch_schema() as (conn, _):
            qid = register(conn, "ai engineer")
            qc.try_claim_search_query(conn, qid, NOW, A)
            self.assertFalse(qc.holds_search_query_claim(conn, qid, B, NOW))

    def test_an_expired_claim_is_not_held_even_by_its_owner(self):
        with api_scratch_schema() as (conn, _):
            qid = register(conn, "ai engineer")
            qc.try_claim_search_query(conn, qid, NOW, A)
            self.assertFalse(qc.holds_search_query_claim(
                conn, qid, A, NOW + TTL + timedelta(minutes=1)))

    def test_a_claim_exactly_at_the_ttl_is_still_held(self):
        # `claimed_at >= ttl_cutoff`, the other side of the boundary
        # test_a_claim_exactly_at_the_ttl_is_not_stealable pins. The two
        # comparisons live in different functions and must agree: a window
        # where the owner has lost the claim and nobody else can take it is a
        # query frozen for no reason.
        with api_scratch_schema() as (conn, _):
            qid = register(conn, "ai engineer")
            qc.try_claim_search_query(conn, qid, NOW, A)
            self.assertTrue(qc.holds_search_query_claim(conn, qid, A, NOW + TTL))

    def test_a_query_that_does_not_exist_is_held_by_nobody(self):
        with api_scratch_schema() as (conn, _):
            self.assertFalse(qc.holds_search_query_claim(conn, 424242, A, NOW))

    def test_an_unclaimed_query_is_held_by_nobody(self):
        with api_scratch_schema() as (conn, _):
            qid = register(conn, "ai engineer")
            self.assertFalse(qc.holds_search_query_claim(conn, qid, A, NOW))

    def test_a_released_claim_is_not_held(self):
        with api_scratch_schema() as (conn, _):
            qid = register(conn, "ai engineer")
            qc.try_claim_search_query(conn, qid, NOW, A)
            qc.release_search_query_claim(conn, qid)
            self.assertFalse(qc.holds_search_query_claim(conn, qid, A, NOW))

    def test_a_claim_on_one_query_is_not_a_claim_on_another(self):
        with api_scratch_schema() as (conn, _):
            mine = register(conn, "ai engineer")
            theirs = register(conn, "data analyst")
            qc.try_claim_search_query(conn, mine, NOW, A)
            self.assertFalse(qc.holds_search_query_claim(conn, theirs, A, NOW))


@requires_db
class TestTheTakeoverGuard(unittest.TestCase):
    """`claim_granted_at`, against a writer that knows only `claimed_at`.

    See `take_over_knowing_only_claimed_at` above for what that writer is, why
    it is hand-written here when test_claim_protocol.py's equivalent must not
    be, and what in `0007` makes it a real shape rather than a hypothetical.
    """

    def test_the_takeover_leaves_claimed_by_stale(self):
        # THE PREMISE, pinned separately from the guard that defends against
        # it. If a claimed_at-only writer ever did clear claimed_by, the guard
        # would be defending against nothing and somebody should be told rather
        # than left to wonder why the code is shaped this way.
        with api_scratch_schema() as (conn, _):
            qid = register(conn, "ai engineer")
            qc.try_claim_search_query(
                conn, qid, NOW - TTL - timedelta(minutes=5), A)
            self.assertTrue(take_over_knowing_only_claimed_at(conn, qid, NOW))
            claimed_at, claimed_by, granted = row(conn, qid)
            self.assertEqual(claimed_by, A, "the writer does not clear it")
            self.assertNotEqual(claimed_at, granted, "it rewrote claimed_at")

    def test_a_naive_check_would_have_said_yes(self):
        # Why the guard is not paranoia. After the takeover BOTH conditions a
        # naive `claimed_by == caller and claimed_at is fresh` check would look
        # at are satisfied, and the claim is nonetheless gone.
        with api_scratch_schema() as (conn, _):
            qid = register(conn, "ai engineer")
            qc.try_claim_search_query(
                conn, qid, NOW - TTL - timedelta(minutes=5), A)
            take_over_knowing_only_claimed_at(conn, qid, NOW)
            claimed_at, claimed_by, _ = row(conn, qid)
            self.assertEqual(claimed_by, A)
            self.assertGreaterEqual(claimed_at, stamp(NOW - TTL))

    def test_holds_says_no_after_a_takeover(self):
        # THE ROW'S OWN ACCEPTANCE CRITERION, AND THE ONE TEST THAT MEETS IT:
        # delete the `claim_granted_at != claimed_at` comparison from
        # holds_search_query_claim and this is the test that goes red. Verified
        # by doing exactly that, not by reading the predicate.
        #
        # The defect it prevents: A submits, is let through, writes results and
        # releases a claim it no longer holds, while the writer that took the
        # query over is mid-fetch on it.
        #
        # test_a_takeover_by_another_contributor_also_revokes_the_claim below
        # is NOT this test and must not be mistaken for it -- a second
        # contributor's claim rewrites claimed_by too, so it stays green with
        # the guard removed and would report a working guard that is gone.
        with api_scratch_schema() as (conn, _):
            qid = register(conn, "ai engineer")
            qc.try_claim_search_query(
                conn, qid, NOW - TTL - timedelta(minutes=5), A)
            take_over_knowing_only_claimed_at(conn, qid, NOW)
            self.assertFalse(qc.holds_search_query_claim(conn, qid, A, NOW))

    def test_a_re_grant_to_the_same_contributor_is_a_live_claim_again(self):
        # The guard must not be a one-way latch. A contributor whose claim
        # expired and who legitimately re-claims the same query holds it: the
        # re-grant writes claimed_at and claim_granted_at together.
        with api_scratch_schema() as (conn, _):
            qid = register(conn, "ai engineer")
            qc.try_claim_search_query(
                conn, qid, NOW - TTL - timedelta(minutes=5), A)
            self.assertTrue(qc.try_claim_search_query(conn, qid, NOW, A))
            self.assertTrue(qc.holds_search_query_claim(conn, qid, A, NOW))

    def test_a_re_grant_after_a_takeover_is_a_live_claim_again(self):
        # The same latch argument, entered through the takeover. Once the
        # claimed_at-only writer's own lease expires, A may claim the query
        # again and genuinely holds it -- the guard revokes a claim, it does
        # not blacklist a contributor from the row.
        with api_scratch_schema() as (conn, _):
            qid = register(conn, "ai engineer")
            qc.try_claim_search_query(
                conn, qid, NOW - TTL - timedelta(minutes=5), A)
            take_over_knowing_only_claimed_at(conn, qid, NOW)
            later = NOW + TTL + timedelta(minutes=1)
            self.assertTrue(qc.try_claim_search_query(conn, qid, later, A))
            self.assertTrue(qc.holds_search_query_claim(conn, qid, A, later))

    def test_a_takeover_by_another_contributor_also_revokes_the_claim(self):
        # Same guard, the other route in -- and green with the guard removed,
        # which is why it is not the criterion. B's claim rewrites all three
        # columns, so A loses on claimed_by first.
        with api_scratch_schema() as (conn, _):
            qid = register(conn, "ai engineer")
            qc.try_claim_search_query(
                conn, qid, NOW - TTL - timedelta(minutes=5), A)
            qc.try_claim_search_query(conn, qid, NOW, B)
            self.assertFalse(qc.holds_search_query_claim(conn, qid, A, NOW))
            self.assertTrue(qc.holds_search_query_claim(conn, qid, B, NOW))


@requires_db
class TestReleaseSearchQueryClaim(unittest.TestCase):

    def test_release_clears_all_three_columns(self):
        with api_scratch_schema() as (conn, _):
            qid = register(conn, "ai engineer")
            qc.try_claim_search_query(conn, qid, NOW, A)
            qc.release_search_query_claim(conn, qid)
            self.assertEqual(row(conn, qid), (None, None, None))

    def test_release_leaves_the_run_statistics_alone(self):
        # The distinction the D08 decision turns on, on this table's terms:
        # releasing says "this attempt produced nothing", which must not be
        # recorded as coverage. record_run() is the only writer of these.
        with api_scratch_schema() as (conn, _):
            qid = register(conn, "ai engineer")
            conn.execute(
                "UPDATE search_queries SET last_run_at = %s, run_count = 3 "
                "WHERE id = %s",
                (stamp(NOW - timedelta(days=2)), qid))
            conn.commit()
            qc.try_claim_search_query(conn, qid, NOW, A)
            qc.release_search_query_claim(conn, qid)
            self.assertEqual(
                conn.execute(
                    "SELECT last_run_at, run_count FROM search_queries "
                    "WHERE id = %s",
                    (qid,)).fetchone(),
                (stamp(NOW - timedelta(days=2)), 3))

    def test_release_on_an_absent_query_is_a_no_op(self):
        with api_scratch_schema() as (conn, _):
            qc.release_search_query_claim(conn, 424242)

    def test_release_frees_only_the_query_named(self):
        with api_scratch_schema() as (conn, _):
            mine = register(conn, "ai engineer")
            theirs = register(conn, "data analyst")
            qc.try_claim_search_query(conn, mine, NOW, A)
            qc.try_claim_search_query(conn, theirs, NOW, B)
            qc.release_search_query_claim(conn, mine)
            self.assertTrue(qc.holds_search_query_claim(conn, theirs, B, NOW))


@requires_db
class TestTwoSessions(unittest.TestCase):
    """Across connections, which is where "two claimants" actually lives.

    WHAT IS CLAIMED, precisely: a claim committed by one session is visible to
    and blocking for an independent one. WHAT IS NOT: a genuinely simultaneous
    race -- test_claim_protocol.py's TestTwoSessions makes that argument in
    full and it is unchanged by the key column.
    """

    def test_a_committed_claim_blocks_an_independent_session(self):
        with api_scratch_schema() as (conn, name):
            qid = register(conn, "ai engineer")
            conn.commit()
            qc.try_claim_search_query(conn, qid, NOW, A)
            with scratchdb.second_connection(name) as other:
                self.assertFalse(qc.try_claim_search_query(other, qid, NOW, B))
                self.assertFalse(qc.holds_search_query_claim(other, qid, B, NOW))
                self.assertTrue(qc.holds_search_query_claim(other, qid, A, NOW))

    def test_a_release_in_one_session_frees_the_query_in_another(self):
        with api_scratch_schema() as (conn, name):
            qid = register(conn, "ai engineer")
            conn.commit()
            qc.try_claim_search_query(conn, qid, NOW, A)
            qc.release_search_query_claim(conn, qid)
            with scratchdb.second_connection(name) as other:
                self.assertTrue(qc.try_claim_search_query(other, qid, NOW, B))


if __name__ == "__main__":
    unittest.main()

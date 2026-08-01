"""The skip derivation, against a real Postgres schema.

WHY THIS FILE IS NOT PART OF test_events.py
    That file promises no database -- it is the one someone runs on a laptop
    with nothing installed, and every assertion in it is about a constant or a
    pure function. The claims here are about a WHERE clause, and a fake
    connection cannot falsify a WHERE clause. `NOT EXISTS (... event <>
    'impression')` versus a naive "no open on this job" is the difference
    between an idempotent derivation and one that writes a second set of skip
    rows every time a user opens something further down the same list, and only
    a real server can show you which one you wrote.

    So these run against a scratch schema exactly as tests/test_score_versions.py
    and tests/test_extract.py do, and skip when there is no database rather than
    passing vacuously.

WHY IT REPLAYS RATHER THAN ASSERTS ON SQL
    tranche_five/27-event-schema.md asks for exactly this: "a script that posts
    a synthetic impression batch for a 20-row list, then an `open` at rank 7,
    and asserts six `skip` rows appear with correct ranks and a shared
    `request_id`." The reason it is a replay and not a unit test is in the same
    file: silent event-logging bugs are undetectable later, because there is
    nothing to compare the log against. The only moment this can be checked is
    before the rows matter.

WHAT IS AND IS NOT EXERCISED
    record_events() itself, with its real INSERT and its real derivation --
    jobs.db is redirected at the scratch connection and nothing else is faked.
    Not exercised: FastAPI's routing and require_user, which have their own
    tests and would need a live session row to reach.
"""

import contextlib
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config  # noqa: F401,E402  (must come first -- performs the sys.path insert)

import jobs                                            # noqa: E402
from auth import User                                  # noqa: E402
from evals import scratchdb                            # noqa: E402
from lib import envfile                                # noqa: E402

#: THE SCRATCH SCHEMA NEEDS THE PIPELINE ROLE, NOT THIS SERVICE'S.
#: config.py has already loaded webapp/.env by the time this runs, so
#: DATABASE_URL is `jobs_web` -- which by design holds SELECT/INSERT on seven
#: tables and CREATE on nothing. scratchdb.create() calls schema.ensure_schema(),
#: which issues CREATE SCHEMA, so under jobs_web every test here dies with
#: "permission denied for database jobs" rather than skipping.
#:
#: So: read backend/.env WITHOUT merging it (envfile.load would not override an
#: already-set DATABASE_URL anyway, and silently switching this service's
#: credential inside its own test suite is exactly the kind of thing that later
#: gets debugged for an afternoon), and publish it only as
#: JOBS_SCRATCH_DATABASE_URL -- the escape hatch scratchdb.scratch_url()
#: documents and prefers. Nothing in webapp/ reads that name.
_BACKEND_ENV = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    ".env")


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

PROFILE = "pursuit"
USER = User(id="u_replay", email="replay@example.test", display_name="Replay",
            profile=PROFILE, is_admin=False)

#: The render under test: twenty jobs at ranks 1..20.
N = 20
OPEN_RANK = 7


def seed(conn, n=N):
    """n jobs, all matched to PROFILE. Returns their ids in rank order.

    job_matches rather than only jobs, because record_events' INSERT selects
    FROM job_matches -- membership in the profile's match set is what makes an
    event recordable at all, and seeding jobs alone would exercise the
    "unknown job" path for every row.
    """
    ids = [f"replay_{i:03d}" for i in range(1, n + 1)]
    for i, job_id in enumerate(ids, start=1):
        conn.execute(
            """
            INSERT INTO jobs (id, platform, company_token, company_name,
                              source_id, title, first_seen, last_seen)
            VALUES (%s, 'greenhouse', 'acme', 'Acme', %s, %s,
                    '2026-08-01T00:00:00', '2026-08-01T00:00:00')
            """,
            (job_id, job_id, f"Role {i}"))
        conn.execute(
            """
            INSERT INTO job_matches (job_id, profile, match_score, match_reasons,
                                     facts_version, criteria_version, matched_at)
            VALUES (%s, %s, %s, '[]', 3, 7, '2026-08-01T00:00:00')
            """,
            (job_id, PROFILE, 100 - i))
    conn.commit()
    return ids


@contextlib.contextmanager
def redirect_db(conn):
    """Point jobs.db at the scratch connection for the duration.

    record_events commits; the scratch schema is dropped wholesale afterwards,
    so a commit here is free. The contextmanager must NOT close the connection
    -- scratch_schema owns it.
    """
    @contextlib.contextmanager
    def fake_db():
        yield conn

    original = jobs.db
    jobs.db = fake_db
    try:
        yield
    finally:
        jobs.db = original


def events_of(conn, event=None):
    """Rows as (job_id, event, rank, request_id, visibility, criteria_version)."""
    sql = ("SELECT job_id, event, rank, request_id, visibility, criteria_version "
           "FROM job_events")
    params = ()
    if event:
        sql += " WHERE event = %s"
        params = (event,)
    return conn.execute(sql + " ORDER BY rank, job_id", params).fetchall()


@requires_db
class TestSkipReplay(unittest.TestCase):
    """The Definition of done's replay, and the properties around it."""

    def render(self, conn, ids, request_id="req_replay"):
        """Post impressions for the whole list, ranks 1..N."""
        jobs.record_events(
            jobs.EventBatch(
                request_id=request_id,
                events=[{"job_id": job_id, "event": "impression", "rank": i}
                        for i, job_id in enumerate(ids, start=1)]),
            USER)
        return request_id

    def test_an_open_at_rank_seven_skips_the_six_above_it(self):
        with scratchdb.scratch_schema() as (conn, _):
            ids = seed(conn)
            with redirect_db(conn):
                request_id = self.render(conn, ids)
                result = jobs.record_events(
                    jobs.EventBatch(
                        request_id=request_id,
                        events=[{"job_id": ids[OPEN_RANK - 1], "event": "open",
                                 "rank": OPEN_RANK, "dwell_ms": 14200}]),
                    USER)

            self.assertEqual(result["derived_skips"], OPEN_RANK - 1)
            skips = events_of(conn, "skip")
            self.assertEqual(len(skips), 6)
            # Correct ranks: exactly 1..6, and the opened item is not among them.
            self.assertEqual([r[2] for r in skips], [1, 2, 3, 4, 5, 6])
            self.assertEqual([r[0] for r in skips], ids[:6])
            self.assertNotIn(ids[OPEN_RANK - 1], [r[0] for r in skips])
            # A shared request_id: the skips belong to the render that produced
            # them, which is the only thing that makes them interpretable.
            self.assertEqual({r[3] for r in skips}, {request_id})

    def test_skips_inherit_the_scores_and_version_of_their_impression(self):
        # A skip is evidence about a row the user saw at a moment; it has to
        # carry what that row looked like then, exactly as the impression does.
        with scratchdb.scratch_schema() as (conn, _):
            ids = seed(conn)
            with redirect_db(conn):
                request_id = self.render(conn, ids)
                jobs.record_events(
                    jobs.EventBatch(request_id=request_id,
                                    events=[{"job_id": ids[OPEN_RANK - 1],
                                             "event": "open", "rank": OPEN_RANK}]),
                    USER)
            rows = conn.execute(
                "SELECT job_id, match_score, criteria_version, visibility "
                "FROM job_events WHERE event = 'skip' ORDER BY rank").fetchall()
            for i, (job_id, match_score, criteria_version, visibility) in enumerate(rows):
                self.assertEqual(match_score, 100 - (i + 1))
                self.assertEqual(criteria_version, 7)
                self.assertEqual(visibility, jobs.VISIBILITY_PRIVATE)

    def test_a_second_open_lower_down_does_not_re_skip(self):
        # The idempotence property, and the reason the derivation excludes any
        # job with a non-impression event rather than only an opened one: after
        # the first open, ranks 1-6 carry skip rows, and a skip is itself a
        # non-impression event.
        with scratchdb.scratch_schema() as (conn, _):
            ids = seed(conn)
            with redirect_db(conn):
                request_id = self.render(conn, ids)
                jobs.record_events(
                    jobs.EventBatch(request_id=request_id,
                                    events=[{"job_id": ids[6], "event": "open",
                                             "rank": 7}]), USER)
                second = jobs.record_events(
                    jobs.EventBatch(request_id=request_id,
                                    events=[{"job_id": ids[11], "event": "open",
                                             "rank": 12}]), USER)

            # Ranks 8..11 only -- four, not eleven.
            self.assertEqual(second["derived_skips"], 4)
            skips = events_of(conn, "skip")
            self.assertEqual([r[2] for r in skips], [1, 2, 3, 4, 5, 6, 8, 9, 10, 11])

    def test_an_actioned_item_above_the_open_is_not_a_skip(self):
        # A save at rank 3 means the item was examined and WANTED. Counting it
        # as passed-over would feed the ranker a negative for its best outcome.
        with scratchdb.scratch_schema() as (conn, _):
            ids = seed(conn)
            with redirect_db(conn):
                request_id = self.render(conn, ids)
                jobs.record_events(
                    jobs.EventBatch(request_id=request_id,
                                    events=[{"job_id": ids[2], "event": "save",
                                             "rank": 3}]), USER)
                jobs.record_events(
                    jobs.EventBatch(request_id=request_id,
                                    events=[{"job_id": ids[6], "event": "open",
                                             "rank": 7}]), USER)

            skipped_ids = [r[0] for r in events_of(conn, "skip")]
            self.assertNotIn(ids[2], skipped_ids)
            self.assertEqual(len(skipped_ids), 5)

    def test_a_different_render_is_not_skipped(self):
        # request_id is a fence, not a label. An open in render B must say
        # nothing about what the user did or did not look at in render A.
        with scratchdb.scratch_schema() as (conn, _):
            ids = seed(conn)
            with redirect_db(conn):
                self.render(conn, ids, request_id="req_A")
                result = jobs.record_events(
                    jobs.EventBatch(request_id="req_B",
                                    events=[{"job_id": ids[6], "event": "open",
                                             "rank": 7}]), USER)
            self.assertEqual(result["derived_skips"], 0)

    def test_a_save_is_the_only_cohort_visible_row_written(self):
        with scratchdb.scratch_schema() as (conn, _):
            ids = seed(conn)
            with redirect_db(conn):
                request_id = self.render(conn, ids)
                jobs.record_events(
                    jobs.EventBatch(request_id=request_id, events=[
                        {"job_id": ids[0], "event": "save", "rank": 1},
                        {"job_id": ids[1], "event": "applied", "rank": 2},
                        {"job_id": ids[2], "event": "dismiss", "rank": 3,
                         "reason": "wrong_level"},
                    ]), USER)
            cohort = conn.execute(
                "SELECT event FROM job_events WHERE visibility = %s",
                (jobs.VISIBILITY_COHORT,)).fetchall()
            self.assertEqual([r[0] for r in cohort], ["save"])

    def test_the_dismiss_reason_lands_on_the_row(self):
        with scratchdb.scratch_schema() as (conn, _):
            ids = seed(conn)
            with redirect_db(conn):
                jobs.record_events(
                    jobs.EventBatch(request_id="req_r", events=[
                        {"job_id": ids[0], "event": "dismiss", "rank": 1,
                         "reason": "wrong_location"}]), USER)
            row = conn.execute(
                "SELECT reason FROM job_events WHERE event = 'dismiss'").fetchone()
            self.assertEqual(row[0], "wrong_location")

    def test_dwell_lands_only_where_it_was_sent(self):
        with scratchdb.scratch_schema() as (conn, _):
            ids = seed(conn)
            with redirect_db(conn):
                request_id = self.render(conn, ids)
                jobs.record_events(
                    jobs.EventBatch(request_id=request_id,
                                    events=[{"job_id": ids[6], "event": "open",
                                             "rank": 7, "dwell_ms": 14200}]), USER)
            self.assertEqual(
                conn.execute("SELECT dwell_ms FROM job_events WHERE event = 'open'"
                             ).fetchone()[0], 14200)
            # Derived rows are not opens and must not inherit a dwell.
            self.assertEqual(
                conn.execute("SELECT count(*) FROM job_events "
                             "WHERE event = 'skip' AND dwell_ms IS NOT NULL"
                             ).fetchone()[0], 0)


@requires_db
class TestSchemaShape(unittest.TestCase):
    """The columns exist, and the ones that must stay nullable are."""

    def test_the_new_columns_are_present(self):
        with scratchdb.scratch_schema() as (conn, name):
            cols = {r[0] for r in conn.execute(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_schema = %s AND table_name = 'job_events'",
                (name,)).fetchall()}
            for col in ("request_id", "rank", "dwell_ms", "reason", "visibility",
                        "criteria_version"):
                self.assertIn(col, cols)

    def test_rank_and_request_id_are_nullable(self):
        # CLAUDE.md: "Do not backfill `rank` on existing job_events rows. A
        # guessed rank is worse than a missing one." NOT NULL here would make
        # that instruction unsatisfiable without a sentinel, and a sentinel is
        # a guessed value wearing a different name. The writer enforces what
        # the schema deliberately does not -- see TestBatchValidation.
        with scratchdb.scratch_schema() as (conn, name):
            nullable = dict(conn.execute(
                "SELECT column_name, is_nullable FROM information_schema.columns "
                "WHERE table_schema = %s AND table_name = 'job_events'",
                (name,)).fetchall())
            self.assertEqual(nullable["rank"], "YES")
            self.assertEqual(nullable["request_id"], "YES")

    def test_visibility_defaults_to_private(self):
        # The one column whose value for a pre-instrumentation row is knowable
        # rather than guessed: every one of them was written under a system
        # that shared nothing.
        with scratchdb.scratch_schema() as (conn, name):
            default = conn.execute(
                "SELECT column_default FROM information_schema.columns "
                "WHERE table_schema = %s AND table_name = 'job_events' "
                "AND column_name = 'visibility'", (name,)).fetchone()[0]
            self.assertIn("private", default)


if __name__ == "__main__":
    unittest.main()

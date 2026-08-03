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
import schema_web                                      # noqa: E402
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

#: A SECOND BUILDER ON THE SAME PROFILE, and the whole reason task 31 exists.
#: job_matches is keyed (job_id, profile) and a cohort shares one profile, so
#: every per-person claim in this file is only falsifiable with two of these.
USER_B = User(id="u_replay_b", email="replay-b@example.test",
              display_name="Replay B", profile=PROFILE, is_admin=False)

#: The render under test: twenty jobs at ranks 1..20.
N = 20
OPEN_RANK = 7


@contextlib.contextmanager
def web_scratch_schema():
    """A scratch schema with BOTH sides' tables in it.

    scratchdb.scratch_schema() calls schema.ensure_schema() and nothing else --
    it belongs to the pipeline and knows nothing about this service. That was
    enough while every table these tests touched was a pipeline table. It is
    not any more: record_events writes builder_job_state, which schema_web owns
    and which references app_users.

    schema_web.ensure_schema() is called INSIDE the body, where schema.SCHEMA
    is still pointed at the scratch name and the connection's search_path is
    already set to it, so its unqualified CREATEs land in the scratch schema
    like everything else. It re-enters schema.ensure_schema() first; that is
    idempotent and is the same real path the operator's `init-schema` reaches.
    """
    with scratchdb.scratch_schema() as (conn, name):
        schema_web.ensure_schema(conn)
        yield conn, name


def seed_users(conn, *users):
    """app_users rows for the Builders a test acts as.

    builder_job_state.app_user_id is a real foreign key -- app_users is on this
    service's own side of the ownership line, so unlike job_id there was no
    reason to decline one. Which means a test that skips this gets a
    ForeignKeyViolation rather than a silent miss.
    """
    for user in users:
        conn.execute(
            """
            INSERT INTO app_users (id, email, display_name, profile, created_at)
            VALUES (%s, %s, %s, %s, '2026-08-01T00:00:00')
            ON CONFLICT (id) DO NOTHING
            """,
            (user.id, user.email, user.display_name, user.profile))
    conn.commit()


def seed(conn, n=N, users=(USER,)):
    """n jobs, all matched to PROFILE. Returns their ids in rank order.

    job_matches rather than only jobs, because record_events' INSERT selects
    FROM job_matches -- membership in the profile's match set is what makes an
    event recordable at all, and seeding jobs alone would exercise the
    "unknown job" path for every row.

    job_url AND description_text ARE NOT DECORATION. jobs_app drops any row
    missing company, title, url or description (../schema.py, _APP_VIEW_SQL) --
    that filter lives at the read edge rather than as a NOT NULL because
    builtin-nyc.py legitimately writes a listing row first. So a seed without
    them is invisible to every list and detail query, which is a 404 that looks
    like a bug in whatever is being tested. record_events never noticed,
    because it reads job_matches directly.
    """
    seed_users(conn, *users)
    ids = [f"replay_{i:03d}" for i in range(1, n + 1)]
    for i, job_id in enumerate(ids, start=1):
        conn.execute(
            """
            INSERT INTO jobs (id, platform, company_token, company_name,
                              source_id, title, job_url, description_text,
                              first_seen, last_seen)
            VALUES (%s, 'greenhouse', 'acme', 'Acme', %s, %s, %s, %s,
                    '2026-08-01T00:00:00', '2026-08-01T00:00:00')
            """,
            (job_id, job_id, f"Role {i}",
             f"https://example.test/{job_id}", f"Description of role {i}."))
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
        with web_scratch_schema() as (conn, _):
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
        with web_scratch_schema() as (conn, _):
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
        with web_scratch_schema() as (conn, _):
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
        with web_scratch_schema() as (conn, _):
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
        with web_scratch_schema() as (conn, _):
            ids = seed(conn)
            with redirect_db(conn):
                self.render(conn, ids, request_id="req_A")
                result = jobs.record_events(
                    jobs.EventBatch(request_id="req_B",
                                    events=[{"job_id": ids[6], "event": "open",
                                             "rank": 7}]), USER)
            self.assertEqual(result["derived_skips"], 0)

    def test_a_save_is_the_only_cohort_visible_row_written(self):
        with web_scratch_schema() as (conn, _):
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
        with web_scratch_schema() as (conn, _):
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
        with web_scratch_schema() as (conn, _):
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

    def test_a_second_builders_impression_is_not_deduped_by_the_first(self):
        # OQ-2, decided 2026-08-03: the 24h impression dedup is keyed
        # (app_user_id, job_id), not (profile, job_id). Before this, thirty
        # Builders sharing the `pursuit` profile meant the first Builder to
        # render a job suppressed every other Builder's impression of it for
        # the rest of the window -- this is the replay that would have caught
        # it, deduped=1 for an impression USER_B never had before.
        with web_scratch_schema() as (conn, _):
            ids = seed(conn, users=(USER, USER_B))
            with redirect_db(conn):
                self.render(conn, ids, request_id="req_a")
                result = jobs.record_events(
                    jobs.EventBatch(
                        request_id="req_b",
                        events=[{"job_id": ids[0], "event": "impression",
                                 "rank": 1}]),
                    USER_B)
            self.assertEqual(result["recorded"], 1)
            self.assertEqual(result["deduped"], 0)
            rows = conn.execute(
                "SELECT app_user_id FROM job_events "
                "WHERE job_id = %s AND event = 'impression'", (ids[0],)).fetchall()
            self.assertEqual({r[0] for r in rows}, {USER.id, USER_B.id})

    def test_the_same_builders_second_impression_is_still_deduped(self):
        # The other side of OQ-2's fix: narrowing the key to app_user_id must
        # not narrow it all the way to nothing. A re-render by the SAME
        # Builder within the window is still "not new information".
        with web_scratch_schema() as (conn, _):
            ids = seed(conn)
            with redirect_db(conn):
                self.render(conn, ids, request_id="req_a")
                result = jobs.record_events(
                    jobs.EventBatch(
                        request_id="req_b",
                        events=[{"job_id": ids[0], "event": "impression",
                                 "rank": 1}]),
                    USER)
            self.assertEqual(result["recorded"], 0)
            self.assertEqual(result["deduped"], 1)


def state_of(conn, user, job_id):
    """(dismissed_at, dismiss_reason, saved_at) for one Builder and one job."""
    return conn.execute(
        "SELECT dismissed_at, dismiss_reason, saved_at FROM builder_job_state "
        "WHERE app_user_id = %s AND job_id = %s", (user.id, job_id)).fetchone()


@requires_db
class TestBuilderState(unittest.TestCase):
    """The write half of tranche_six/31: the current answer, beside the evidence.

    job_events keeps what happened and builder_job_state keeps what is true
    now. Every test here asserts on both, because the failure mode worth
    guarding is not either table being wrong on its own -- it is the two
    disagreeing, which no reader could detect afterwards.
    """

    def post(self, events, user=USER, request_id="req_state"):
        return jobs.record_events(
            jobs.EventBatch(request_id=request_id, events=events), user)

    def test_a_dismiss_writes_state_and_evidence_together(self):
        with web_scratch_schema() as (conn, _):
            ids = seed(conn)
            with redirect_db(conn):
                self.post([{"job_id": ids[0], "event": "dismiss", "rank": 1,
                            "reason": "wrong_level"}])
            dismissed_at, reason, saved_at = state_of(conn, USER, ids[0])
            self.assertIsNotNone(dismissed_at)
            self.assertEqual(reason, "wrong_level")
            self.assertIsNone(saved_at)
            # And the event row it was derived from is still there.
            self.assertEqual(
                conn.execute("SELECT reason FROM job_events WHERE event = 'dismiss'"
                             ).fetchone()[0], "wrong_level")

    def test_an_undismiss_clears_the_state_and_keeps_the_history(self):
        # The task is explicit that the reversal is itself signal: "record the
        # undo as its own event rather than deleting the original ... deletion
        # loses it". So the state goes back and the log grows -- job_events is
        # granted SELECT and INSERT and nothing else, so this is enforced by
        # privilege rather than by care.
        with web_scratch_schema() as (conn, _):
            ids = seed(conn)
            with redirect_db(conn):
                self.post([{"job_id": ids[0], "event": "dismiss", "rank": 1,
                            "reason": "wrong_role"}])
                self.post([{"job_id": ids[0], "event": "undismiss"}])
            dismissed_at, reason, _ = state_of(conn, USER, ids[0])
            self.assertIsNone(dismissed_at)
            self.assertIsNone(reason)
            self.assertEqual(
                [r[0] for r in conn.execute(
                    "SELECT event FROM job_events ORDER BY id").fetchall()],
                ["dismiss", "undismiss"])

    def test_a_save_and_an_unsave_move_only_the_save_column(self):
        with web_scratch_schema() as (conn, _):
            ids = seed(conn)
            with redirect_db(conn):
                self.post([{"job_id": ids[0], "event": "dismiss", "rank": 1,
                            "reason": "other"},
                           {"job_id": ids[0], "event": "save", "rank": 1}])
                dismissed_before, _, saved = state_of(conn, USER, ids[0])
                self.assertIsNotNone(saved)
                self.post([{"job_id": ids[0], "event": "unsave"}])
            dismissed_after, reason, saved = state_of(conn, USER, ids[0])
            self.assertIsNone(saved)
            # The unsave is a column going NULL, NOT a deleted row -- the
            # dismissal on the same row has to survive it.
            self.assertEqual(dismissed_after, dismissed_before)
            self.assertEqual(reason, "other")

    def test_an_impression_writes_no_state_row_at_all(self):
        # A Builder who has only scrolled has no state, rather than an empty
        # state. The distinction matters to tools/dismiss-reasons.py, which
        # counts rows in this table.
        with web_scratch_schema() as (conn, _):
            ids = seed(conn)
            with redirect_db(conn):
                self.post([{"job_id": ids[0], "event": "impression", "rank": 1},
                           {"job_id": ids[1], "event": "open", "rank": 2},
                           {"job_id": ids[2], "event": "applied", "rank": 3}])
            self.assertEqual(
                conn.execute("SELECT count(*) FROM builder_job_state"
                             ).fetchone()[0], 0)

    def test_a_job_outside_the_match_set_writes_neither(self):
        # record_events drops events for jobs not in this profile's matches,
        # and the state write is conditioned on the event row having landed.
        # If it were not, a client could seed state for any id it could guess.
        with web_scratch_schema() as (conn, _):
            seed(conn)
            with redirect_db(conn):
                result = self.post([{"job_id": "not_a_job", "event": "dismiss",
                                     "rank": 1, "reason": "other"}])
            self.assertEqual(result["skipped"], 1)
            self.assertEqual(
                conn.execute("SELECT count(*) FROM builder_job_state"
                             ).fetchone()[0], 0)

    def test_two_builders_on_one_profile_have_separate_state(self):
        # THE POINT OF THE TABLE. Both users carry profile='pursuit' and share
        # every job_matches row; if the state were keyed on profile -- as the
        # event rows still are -- these two would be one.
        with web_scratch_schema() as (conn, _):
            ids = seed(conn, users=(USER, USER_B))
            with redirect_db(conn):
                self.post([{"job_id": ids[0], "event": "dismiss", "rank": 1,
                            "reason": "bad_company"}], user=USER)
                self.post([{"job_id": ids[0], "event": "save", "rank": 1}],
                          user=USER_B)
            a_dismissed, a_reason, a_saved = state_of(conn, USER, ids[0])
            b_dismissed, b_reason, b_saved = state_of(conn, USER_B, ids[0])
            self.assertIsNotNone(a_dismissed)
            self.assertIsNone(a_saved)
            self.assertIsNone(b_dismissed)
            self.assertIsNotNone(b_saved)
            self.assertEqual(a_reason, "bad_company")
            self.assertIsNone(b_reason)

    def test_the_reason_vocabulary_is_closed_in_the_database_too(self):
        # The validator refuses an unknown reason (tests/test_events.py) and so
        # does the column, generated from the same tuple. Two layers because
        # the writer is not the only thing that will ever write here.
        import psycopg
        with web_scratch_schema() as (conn, _):
            ids = seed(conn)
            with self.assertRaises(psycopg.errors.CheckViolation):
                conn.execute(
                    "INSERT INTO builder_job_state (app_user_id, job_id, "
                    "dismissed_at, dismiss_reason, updated_at) "
                    "VALUES (%s, %s, '2026-08-01T00:00:00', 'meh', "
                    "'2026-08-01T00:00:00')", (USER.id, ids[0]))
            conn.rollback()

    def test_a_reason_cannot_outlive_the_dismissal_it_explains(self):
        import psycopg
        with web_scratch_schema() as (conn, _):
            ids = seed(conn)
            with self.assertRaises(psycopg.errors.CheckViolation):
                conn.execute(
                    "INSERT INTO builder_job_state (app_user_id, job_id, "
                    "dismiss_reason, updated_at) VALUES (%s, %s, 'other', "
                    "'2026-08-01T00:00:00')", (USER.id, ids[0]))
            conn.rollback()


@requires_db
class TestListState(unittest.TestCase):
    """The read half, with two accounts -- task 31's Definition of done.

    "A dismissed posting never reappears in that Builder's list, and appears
    normally for everyone else -- verify with two accounts." That sentence is
    only checkable by running the list query, so this calls list_jobs directly
    under the same redirect_db the write tests use. It is also the test that
    catches _BUILDER_STATE_JOIN's parameter landing in the wrong position: bind
    user.id after the profile and every assertion about A's state below fails.
    """

    def list_for(self, user, **kwargs):
        """list_jobs with everything FastAPI would have supplied.

        EVERY parameter is passed, including the ones this file never varies.
        Calling the handler as a plain function bypasses the framework, so an
        unpassed argument keeps its `Query(...)` default OBJECT rather than
        that object's value -- and `Query(False)` is truthy, so a filter
        defaulting to off silently comes on. It surfaces as "cannot adapt type
        'Query'" if the value reaches a placeholder and as nothing at all if it
        only reaches an `if`.
        """
        call = dict(limit=jobs.MAX_LIMIT, cursor=None, q=None, remote=None,
                    nyc=None, min_score=None, since=None,
                    include_dismissed=False)
        call.update(kwargs)
        return jobs.list_jobs(user=user, **call)

    def test_a_dismissal_hides_the_row_for_one_builder_only(self):
        with web_scratch_schema() as (conn, _):
            ids = seed(conn, users=(USER, USER_B))
            with redirect_db(conn):
                jobs.record_events(
                    jobs.EventBatch(request_id="req_d", events=[
                        {"job_id": ids[2], "event": "dismiss", "rank": 3,
                         "reason": "wrong_location"}]), USER)
                mine = self.list_for(USER)
                theirs = self.list_for(USER_B)

            self.assertNotIn(ids[2], [j["id"] for j in mine["jobs"]])
            self.assertIn(ids[2], [j["id"] for j in theirs["jobs"]])
            # And it is not merely hidden from the other Builder's flags: the
            # row reads as untouched for them.
            row = next(j for j in theirs["jobs"] if j["id"] == ids[2])
            self.assertFalse(row["dismissed"])
            self.assertIsNone(row["dismiss_reason"])

    def test_ranks_close_over_the_dismissed_row(self):
        # The filter is in the WHERE, so rank is the position in what was
        # actually rendered -- 1..N with no hole where the dismissal was.
        # A hole would be indistinguishable from an item nobody scrolled to.
        with web_scratch_schema() as (conn, _):
            ids = seed(conn, users=(USER,))
            with redirect_db(conn):
                jobs.record_events(
                    jobs.EventBatch(request_id="req_d", events=[
                        {"job_id": ids[2], "event": "dismiss", "rank": 3,
                         "reason": "other"}]), USER)
                mine = self.list_for(USER)
            self.assertEqual([j["rank"] for j in mine["jobs"]],
                             list(range(1, N)))

    def test_a_save_is_not_visible_as_another_builders_save(self):
        with web_scratch_schema() as (conn, _):
            ids = seed(conn, users=(USER, USER_B))
            with redirect_db(conn):
                jobs.record_events(
                    jobs.EventBatch(request_id="req_s", events=[
                        {"job_id": ids[0], "event": "save", "rank": 1}]), USER_B)
                mine = self.list_for(USER)
                theirs = self.list_for(USER_B)
            self.assertFalse(
                next(j for j in mine["jobs"] if j["id"] == ids[0])["saved"])
            self.assertTrue(
                next(j for j in theirs["jobs"] if j["id"] == ids[0])["saved"])

    def test_include_dismissed_is_the_debugging_escape_hatch(self):
        with web_scratch_schema() as (conn, _):
            ids = seed(conn, users=(USER,))
            with redirect_db(conn):
                jobs.record_events(
                    jobs.EventBatch(request_id="req_d", events=[
                        {"job_id": ids[2], "event": "dismiss", "rank": 3,
                         "reason": "stale_posting"}]), USER)
                shown = self.list_for(USER, include_dismissed=True)
            row = next(j for j in shown["jobs"] if j["id"] == ids[2])
            self.assertTrue(row["dismissed"])
            self.assertEqual(row["dismiss_reason"], "stale_posting")

    def test_the_detail_endpoint_still_serves_a_dismissed_posting(self):
        # Otherwise undo is unreachable from a detail page: a client that has
        # just written a dismiss could not render the row it acted on.
        with web_scratch_schema() as (conn, _):
            ids = seed(conn, users=(USER,))
            with redirect_db(conn):
                jobs.record_events(
                    jobs.EventBatch(request_id="req_d", events=[
                        {"job_id": ids[2], "event": "dismiss", "rank": 3,
                         "reason": "wrong_role"}]), USER)
                row = jobs.get_job(ids[2], user=USER)
            self.assertTrue(row["dismissed"])
            self.assertEqual(row["dismiss_reason"], "wrong_role")

    def test_an_undismiss_brings_the_row_back(self):
        with web_scratch_schema() as (conn, _):
            ids = seed(conn, users=(USER,))
            with redirect_db(conn):
                jobs.record_events(
                    jobs.EventBatch(request_id="req_d", events=[
                        {"job_id": ids[2], "event": "dismiss", "rank": 3,
                         "reason": "other"}]), USER)
                self.assertNotIn(ids[2],
                                 [j["id"] for j in self.list_for(USER)["jobs"]])
                jobs.record_events(
                    jobs.EventBatch(request_id="req_u", events=[
                        {"job_id": ids[2], "event": "undismiss"}]), USER)
                back = self.list_for(USER)
            row = next(j for j in back["jobs"] if j["id"] == ids[2])
            self.assertFalse(row["dismissed"])
            self.assertIsNone(row["dismiss_reason"])


@requires_db
class TestEventStateIsPerBuilder(unittest.TestCase):
    """`seen` and `applied`, with two accounts -- defects D66 and D67.

    The other half of TestListState's question, and the half that could not be
    asked until job_events carried app_user_id. dismissed and saved live in
    builder_job_state and were made per-Builder by task 31; seen and applied
    derive from the append-only log and stayed cohort-wide, because a table
    keyed (profile, job_id) cannot answer "did THIS Builder see it" and thirty
    Builders share the `pursuit` profile.

    EVERY TEST HERE PASSES VACUOUSLY WITH ONE ACCOUNT. That is the defects'
    whole shape: with a single active Builder every value of e.profile belonged
    to one person and the old join was accidentally correct, so it was
    invisible at one Builder and wrong at two, with no error on the day it
    turned. USER_B is not decoration.
    """

    def list_for(self, user, **kwargs):
        # Same reason as TestListState.list_for: calling the handler as a plain
        # function leaves unpassed arguments as their Query(...) OBJECT, and
        # Query(False) is truthy.
        call = dict(limit=jobs.MAX_LIMIT, cursor=None, q=None, remote=None,
                    nyc=None, min_score=None, since=None,
                    include_dismissed=False)
        call.update(kwargs)
        return jobs.list_jobs(user=user, **call)

    def row_for(self, listing, job_id):
        return next(j for j in listing["jobs"] if j["id"] == job_id)

    def test_an_application_is_not_visible_as_another_builders_application(self):
        # D67, and the sharper of the two. visibility_for("applied") stores the
        # row `private` and API-CONTRACT-v1.md calls an application private;
        # resolving the flag by profile then leaked the same fact back out of
        # the response body -- the control enforced in the column and defeated
        # in the join. At N=30 in one classroom that is not a distinction task
        # 28 is willing to rely on.
        with web_scratch_schema() as (conn, _):
            ids = seed(conn, users=(USER, USER_B))
            with redirect_db(conn):
                jobs.record_events(
                    jobs.EventBatch(request_id="req_a", events=[
                        {"job_id": ids[0], "event": "applied"}]), USER)
                mine = self.list_for(USER)
                theirs = self.list_for(USER_B)
            self.assertTrue(self.row_for(mine, ids[0])["applied"])
            self.assertFalse(self.row_for(theirs, ids[0])["applied"])

    def test_an_impression_is_not_visible_as_another_builders_impression(self):
        # D66. `seen` is the one flag a Builder never sets deliberately, so a
        # cohort-wide answer here is also the one they are least likely to
        # notice is wrong.
        with web_scratch_schema() as (conn, _):
            ids = seed(conn, users=(USER, USER_B))
            with redirect_db(conn):
                jobs.record_events(
                    jobs.EventBatch(request_id="req_i", events=[
                        {"job_id": ids[1], "event": "impression", "rank": 2}]),
                    USER)
                mine = self.list_for(USER)
                theirs = self.list_for(USER_B)
            self.assertTrue(self.row_for(mine, ids[1])["seen"])
            self.assertFalse(self.row_for(theirs, ids[1])["seen"])

    def test_the_detail_endpoint_answers_the_same_way(self):
        # _STATE_COLUMNS exists so the list and the detail endpoint cannot
        # answer the same question differently, and it takes both joins'
        # parameters -- which the detail endpoint binds in its own tuple rather
        # than through list_jobs' params list. A fix applied to one and not the
        # other would be caught only here.
        with web_scratch_schema() as (conn, _):
            ids = seed(conn, users=(USER, USER_B))
            with redirect_db(conn):
                jobs.record_events(
                    jobs.EventBatch(request_id="req_a", events=[
                        {"job_id": ids[0], "event": "applied"},
                        {"job_id": ids[0], "event": "open", "rank": 1}]), USER)
                mine = jobs.get_job(ids[0], user=USER)
                theirs = jobs.get_job(ids[0], user=USER_B)
            self.assertTrue(mine["applied"])
            self.assertTrue(mine["seen"])
            self.assertFalse(theirs["applied"])
            self.assertFalse(theirs["seen"])

    def test_the_event_row_records_who_wrote_it(self):
        with web_scratch_schema() as (conn, _):
            ids = seed(conn, users=(USER, USER_B))
            with redirect_db(conn):
                jobs.record_events(
                    jobs.EventBatch(request_id="req_a", events=[
                        {"job_id": ids[0], "event": "applied"}]), USER)
                jobs.record_events(
                    jobs.EventBatch(request_id="req_b", events=[
                        {"job_id": ids[1], "event": "save", "rank": 2}]), USER_B)
            rows = dict(conn.execute(
                "SELECT job_id, app_user_id FROM job_events "
                "ORDER BY job_id").fetchall())
            self.assertEqual(rows[ids[0]], USER.id)
            self.assertEqual(rows[ids[1]], USER_B.id)

    def test_a_derived_skip_belongs_to_the_builder_whose_impression_it_came_from(self):
        # derive_skips copies imp.app_user_id rather than taking it from the
        # caller. A skip attributed to nobody is a lost negative; a skip
        # attributed to the wrong Builder is a wrong one, which is worse.
        with web_scratch_schema() as (conn, _):
            ids = seed(conn, users=(USER, USER_B))
            with redirect_db(conn):
                jobs.record_events(
                    jobs.EventBatch(request_id="req_r", events=[
                        {"job_id": job_id, "event": "impression", "rank": i}
                        for i, job_id in enumerate(ids[:OPEN_RANK], start=1)]),
                    USER)
                jobs.record_events(
                    jobs.EventBatch(request_id="req_r", events=[
                        {"job_id": ids[OPEN_RANK - 1], "event": "open",
                         "rank": OPEN_RANK}]), USER)
            owners = {r[0] for r in conn.execute(
                "SELECT app_user_id FROM job_events WHERE event = 'skip'"
            ).fetchall()}
            self.assertEqual(owners, {USER.id})

    def test_an_echoed_request_id_cannot_derive_another_builders_skips(self):
        """Defect D68. A `request_id` does not establish whose render it was.

        `EventBatch.request_id` is a free-form client string, `validate_batch`
        checks only that it is non-empty, and nothing records which user a
        minted id was issued to -- it goes out in the list response and comes
        back unverified. Before `imp.app_user_id = %s` the derivation's only
        other predicate was the profile, which thirty Builders share, so B
        echoing A's request_id on an `open` derived six skip rows FROM A's
        impressions and stored them UNDER A's app_user_id: fabricated negatives
        for postings B never saw.
        """
        with web_scratch_schema() as (conn, _):
            ids = seed(conn, users=(USER, USER_B))
            with redirect_db(conn):
                # A renders a list and reports impressions for ranks 1..7.
                jobs.record_events(
                    jobs.EventBatch(request_id="req_belongs_to_A", events=[
                        {"job_id": j, "event": "impression", "rank": i}
                        for i, j in enumerate(ids[:OPEN_RANK], start=1)]), USER)
                # B posts an open echoing A's request_id. Nothing issued it to
                # B; B simply put A's string in the batch.
                result = jobs.record_events(
                    jobs.EventBatch(request_id="req_belongs_to_A", events=[
                        {"job_id": ids[OPEN_RANK - 1], "event": "open",
                         "rank": OPEN_RANK}]), USER_B)

            # B's own open is recorded -- it is a real event by a real user on
            # a job in the profile's match set. What must not happen is the
            # derivation reading A's impressions.
            self.assertEqual(result["recorded"], 1)
            self.assertEqual(result["derived_skips"], 0)
            self.assertEqual(
                conn.execute("SELECT count(*) FROM job_events "
                             "WHERE event = 'skip'").fetchone()[0], 0)

    def test_a_builders_own_open_still_derives_its_skips(self):
        # The other half of D68, and the one that catches a conjunct bound to
        # the wrong value: narrowing the derivation must not disable it. Same
        # render, same ranks, one Builder throughout.
        with web_scratch_schema() as (conn, _):
            ids = seed(conn, users=(USER, USER_B))
            with redirect_db(conn):
                jobs.record_events(
                    jobs.EventBatch(request_id="req_mine", events=[
                        {"job_id": j, "event": "impression", "rank": i}
                        for i, j in enumerate(ids[:OPEN_RANK], start=1)]), USER)
                result = jobs.record_events(
                    jobs.EventBatch(request_id="req_mine", events=[
                        {"job_id": ids[OPEN_RANK - 1], "event": "open",
                         "rank": OPEN_RANK}]), USER)
            self.assertEqual(result["derived_skips"], OPEN_RANK - 1)
            owners = {r[0] for r in conn.execute(
                "SELECT app_user_id FROM job_events WHERE event = 'skip'"
            ).fetchall()}
            self.assertEqual(owners, {USER.id})

    def test_another_builders_action_cannot_suppress_my_skip(self):
        """D68's second half: suppression, found by the fix for the first.

        The NOT EXISTS asks "was there a non-impression event on this job in
        this render". Without an owner predicate it answered that question
        across all thirty Builders, so B -- echoing A's request_id and posting
        a `save` -- could veto a skip A's own open should have derived. A lost
        negative rather than a false one, and invisible the same way.
        """
        with web_scratch_schema() as (conn, _):
            ids = seed(conn, users=(USER, USER_B))
            with redirect_db(conn):
                jobs.record_events(
                    jobs.EventBatch(request_id="req_mine", events=[
                        {"job_id": j, "event": "impression", "rank": i}
                        for i, j in enumerate(ids[:OPEN_RANK], start=1)]), USER)
                # B saves a job A saw, under A's request_id. B's own state is
                # B's business; what it must not do is speak for A's render.
                jobs.record_events(
                    jobs.EventBatch(request_id="req_mine", events=[
                        {"job_id": ids[2], "event": "save", "rank": 3}]), USER_B)
                result = jobs.record_events(
                    jobs.EventBatch(request_id="req_mine", events=[
                        {"job_id": ids[OPEN_RANK - 1], "event": "open",
                         "rank": OPEN_RANK}]), USER)

            self.assertEqual(result["derived_skips"], OPEN_RANK - 1)
            skipped = {r[0] for r in conn.execute(
                "SELECT job_id FROM job_events WHERE event = 'skip'").fetchall()}
            self.assertIn(ids[2], skipped)

    def test_my_own_action_still_suppresses_my_skip(self):
        # The other side of the same predicate, and the reason it is an owner
        # match rather than a removal: a job THIS Builder acted on in THIS
        # render is not passed over. Counting a save as a skip would feed the
        # ranker a negative for its best outcome.
        with web_scratch_schema() as (conn, _):
            ids = seed(conn, users=(USER,))
            with redirect_db(conn):
                jobs.record_events(
                    jobs.EventBatch(request_id="req_mine", events=[
                        {"job_id": j, "event": "impression", "rank": i}
                        for i, j in enumerate(ids[:OPEN_RANK], start=1)]), USER)
                jobs.record_events(
                    jobs.EventBatch(request_id="req_mine", events=[
                        {"job_id": ids[2], "event": "save", "rank": 3}]), USER)
                result = jobs.record_events(
                    jobs.EventBatch(request_id="req_mine", events=[
                        {"job_id": ids[OPEN_RANK - 1], "event": "open",
                         "rank": OPEN_RANK}]), USER)

            self.assertEqual(result["derived_skips"], OPEN_RANK - 2)
            skipped = {r[0] for r in conn.execute(
                "SELECT job_id FROM job_events WHERE event = 'skip'").fetchall()}
            self.assertNotIn(ids[2], skipped)

    def test_a_pre_column_action_event_does_not_suppress(self):
        """The NULL case in the NOT EXISTS, asserted rather than reasoned to.

        `other.app_user_id = imp.app_user_id` against a legacy row's NULL is
        NULL, not TRUE, so the row does not satisfy the EXISTS and the skip is
        still derived. That is the intended answer and not a workaround: an
        event nobody can be shown to have generated should not veto somebody
        else's negative. The outer conjunct guarantees `imp.app_user_id` is
        non-NULL, so this is the only NULL that can reach the comparison.
        """
        with web_scratch_schema() as (conn, _):
            ids = seed(conn, users=(USER,))
            with redirect_db(conn):
                jobs.record_events(
                    jobs.EventBatch(request_id="req_mine", events=[
                        {"job_id": j, "event": "impression", "rank": i}
                        for i, j in enumerate(ids[:OPEN_RANK], start=1)]), USER)
            # A pre-column action event: same render, same job, no owner.
            conn.execute(
                """
                INSERT INTO job_events (profile, job_id, event, request_id,
                                        rank, occurred_at)
                VALUES (%s, %s, 'save', 'req_mine', 3, '2026-07-01T00:00:00')
                """, (PROFILE, ids[2]))
            conn.commit()
            with redirect_db(conn):
                result = jobs.record_events(
                    jobs.EventBatch(request_id="req_mine", events=[
                        {"job_id": ids[OPEN_RANK - 1], "event": "open",
                         "rank": OPEN_RANK}]), USER)

            self.assertEqual(result["derived_skips"], OPEN_RANK - 1)
            skipped = {r[0] for r in conn.execute(
                "SELECT job_id FROM job_events WHERE event = 'skip' "
                "AND app_user_id IS NOT NULL").fetchall()}
            self.assertIn(ids[2], skipped)

    def test_an_event_written_before_the_column_belongs_to_nobody(self):
        # The pre-existing rows carry NULL and are deliberately not backfilled
        # (../schema.py). This asserts the direction that failure takes: the
        # join's equality never matches NULL, so an unattributable impression
        # reads as unseen for everyone rather than as seen for everyone.
        with web_scratch_schema() as (conn, _):
            ids = seed(conn, users=(USER,))
            conn.execute(
                """
                INSERT INTO job_events (profile, job_id, event, occurred_at)
                VALUES (%s, %s, 'impression', '2026-07-01T00:00:00')
                """, (PROFILE, ids[3]))
            conn.commit()
            with redirect_db(conn):
                mine = self.list_for(USER)
            self.assertFalse(self.row_for(mine, ids[3])["seen"])


@requires_db
class TestSchemaShape(unittest.TestCase):
    """The columns exist, and the ones that must stay nullable are."""

    def test_the_new_columns_are_present(self):
        with web_scratch_schema() as (conn, name):
            cols = {r[0] for r in conn.execute(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_schema = %s AND table_name = 'job_events'",
                (name,)).fetchall()}
            for col in ("request_id", "rank", "dwell_ms", "reason", "visibility",
                        "criteria_version", "app_user_id"):
                self.assertIn(col, cols)

    def test_rank_and_request_id_are_nullable(self):
        # CLAUDE.md: "Do not backfill `rank` on existing job_events rows. A
        # guessed rank is worse than a missing one." NOT NULL here would make
        # that instruction unsatisfiable without a sentinel, and a sentinel is
        # a guessed value wearing a different name. The writer enforces what
        # the schema deliberately does not -- see TestBatchValidation.
        with web_scratch_schema() as (conn, name):
            nullable = dict(conn.execute(
                "SELECT column_name, is_nullable FROM information_schema.columns "
                "WHERE table_schema = %s AND table_name = 'job_events'",
                (name,)).fetchall())
            self.assertEqual(nullable["rank"], "YES")
            self.assertEqual(nullable["request_id"], "YES")

    def test_app_user_id_is_nullable_and_has_no_default(self):
        # Same argument as rank, one column later. NOT NULL is unsatisfiable
        # for the rows that predate the column, and every way of satisfying it
        # -- a DEFAULT, a sentinel, a backfill from the only account that
        # currently exists -- asserts an owner nobody recorded. A sentinel is
        # worse than NULL for a specific reason: a sentinel JOINs, so it would
        # hand every pre-existing impression to whichever Builder drew the
        # sentinel. NULL cannot match _EVENT_STATE_JOIN's equality at all.
        with web_scratch_schema() as (conn, name):
            row = conn.execute(
                "SELECT is_nullable, column_default FROM information_schema.columns "
                "WHERE table_schema = %s AND table_name = 'job_events' "
                "AND column_name = 'app_user_id'", (name,)).fetchone()
            self.assertEqual(row[0], "YES")
            self.assertIsNone(row[1])

    def test_visibility_defaults_to_private(self):
        # The one column whose value for a pre-instrumentation row is knowable
        # rather than guessed: every one of them was written under a system
        # that shared nothing.
        with web_scratch_schema() as (conn, name):
            default = conn.execute(
                "SELECT column_default FROM information_schema.columns "
                "WHERE table_schema = %s AND table_name = 'job_events' "
                "AND column_name = 'visibility'", (name,)).fetchone()[0]
            self.assertIn("private", default)


if __name__ == "__main__":
    unittest.main()

"""builder_profiles, POST /v1/onboarding, and the foreign key that could be.

WHY THIS FILE IS NOT PART OF test_onboarding.py
    That file promises no database and every assertion in it is about a constant
    or a pure function. The claims here are about constraints, and a fake
    connection cannot falsify a constraint. Whether ON UPDATE CASCADE actually
    carries a Builder onto a new cohort, and whether the composite key actually
    refuses a parent_profile that disagrees with app_users.profile, is the
    difference between a design and a comment about one -- and only a real
    server can show you which one you wrote.

    So these run against a scratch schema exactly as tests/test_event_replay.py
    does, and skip when there is no database rather than passing vacuously.

WHAT IS AND IS NOT EXERCISED
    onboarding.post_onboarding() itself, with its real upsert and the real
    jobs.record_events() it delegates the seed judgements to -- both onboarding.db
    and jobs.db are redirected at the scratch connection and nothing else is
    faked. Not exercised: FastAPI's routing and require_user, which have their
    own tests and would need a live session row to reach. Same boundary
    test_event_replay.py draws, for the same reason.
"""

import contextlib
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config  # noqa: F401,E402  (must come first -- performs the sys.path insert)

import jobs                                            # noqa: E402
import onboarding                                      # noqa: E402
import profiles                                        # noqa: E402
import schema_web                                      # noqa: E402
from auth import User                                  # noqa: E402
from evals import scratchdb                            # noqa: E402
from lib import envfile                                # noqa: E402

#: THE SCRATCH SCHEMA NEEDS THE PIPELINE ROLE, NOT THIS SERVICE'S -- the whole
#: argument is in tests/test_event_replay.py beside the identical block, and it
#: is not repeated here. Short version: config.py has already pointed
#: DATABASE_URL at `jobs_web`, which holds CREATE on nothing, so scratchdb would
#: die rather than skip; backend/.env is read WITHOUT merging and published only
#: as JOBS_SCRATCH_DATABASE_URL, which nothing in webapp/ reads.
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
NEXT_COHORT = "pursuit-2027-spring"

USER = User(id="u_onboard", email="onboard@example.test",
            display_name="Onboard", profile=PROFILE, is_admin=False)

#: A SECOND BUILDER ON THE SAME COHORT PROFILE. Thirty Builders share one
#: `profiles` row, so every per-person claim in this file is only falsifiable
#: with two of these -- the same reason test_event_replay.py carries USER_B.
USER_B = User(id="u_onboard_b", email="onboard-b@example.test",
              display_name="Onboard B", profile=PROFILE, is_admin=False)

#: The minimum a `profiles` row needs to survive profiles.validate() on the way
#: back out. Only criteria_json is read by anything here.
_PERSONA = {"background_summary": "x", "strengths": [], "honest_gaps": [],
            "scoring_instructions": "x"}


@contextlib.contextmanager
def web_scratch_schema():
    """A scratch schema with BOTH sides' tables in it. See
    tests/test_event_replay.py's copy for why schema_web.ensure_schema() is
    called inside the body rather than beside scratchdb's own DDL."""
    with scratchdb.scratch_schema() as (conn, name):
        schema_web.ensure_schema(conn)
        yield conn, name


def seed_profile(conn, profile=PROFILE, criteria=None):
    """A cohort `profiles` row. Without one, post_onboarding() correctly 400s."""
    profiles.upsert(conn, profile, _PERSONA, criteria or {"base": 50})


def seed_users(conn, *users):
    for user in users:
        conn.execute(
            """
            INSERT INTO app_users (id, email, display_name, profile, created_at)
            VALUES (%s, %s, %s, %s, '2026-08-02T00:00:00')
            ON CONFLICT (id) DO NOTHING
            """,
            (user.id, user.email, user.display_name, user.profile))
    conn.commit()


def seed_jobs(conn, n, profile=PROFILE, tracks=None):
    """n postings, matched to `profile`, optionally scored with a primary_track.

    job_matches is what record_events() checks a judgement against, so a seed
    judgement for a job that is not there is silently dropped -- which is a real
    behaviour this file asserts on rather than works around.
    """
    ids = []
    for i in range(n):
        job_id = f"j{i:03d}"
        ids.append(job_id)
        conn.execute(
            """
            INSERT INTO jobs (id, platform, company_token, company_name,
                              source_id, title, first_seen, last_seen)
            VALUES (%s, 'greenhouse', 'acme', 'Acme', %s, %s,
                    '2026-08-02T00:00:00', '2026-08-02T00:00:00')
            ON CONFLICT (id) DO NOTHING
            """, (job_id, job_id, f"Role {i}"))
        conn.execute(
            """
            INSERT INTO job_matches (job_id, profile, match_score, match_reasons,
                                     facts_version, criteria_version, matched_at)
            VALUES (%s, %s, %s, '[]', 3, 1, '2026-08-02T00:00:00')
            ON CONFLICT (job_id, profile) DO NOTHING
            """, (job_id, profile, 100 - i))
        if tracks:
            conn.execute(
                """
                INSERT INTO job_scores (job_id, profile, fit_score, primary_track,
                                        scored_at, scoring_model)
                VALUES (%s, %s, 70, %s, '2026-08-02T00:00:00', 'test')
                ON CONFLICT (job_id, profile) DO NOTHING
                """, (job_id, profile, tracks[i % len(tracks)]))
    conn.commit()
    return ids


@contextlib.contextmanager
def routed_at(conn):
    """Point both onboarding.db and jobs.db at the scratch connection.

    BOTH, and that is the point of the fixture rather than an implementation
    detail: post_onboarding() writes the profile row through its own db() and
    the seed judgements through jobs.record_events()'s, so a test that redirected
    one would exercise half the endpoint against a schema the other half cannot
    see. The two are separate transactions in production too -- see
    record_seed_judgements' docstring for why that is the price of not
    duplicating the write path.
    """
    @contextlib.contextmanager
    def fake_db():
        yield conn

    original = (onboarding.db, jobs.db)
    onboarding.db = fake_db
    jobs.db = fake_db
    try:
        yield
    finally:
        onboarding.db, jobs.db = original


def body(**kwargs):
    return onboarding.OnboardingRequest(**kwargs)


@requires_db
class TestTheTableExists(unittest.TestCase):

    def test_the_columns_are_the_ones_the_task_asked_for(self):
        with web_scratch_schema() as (conn, _name):
            present = {r[0] for r in conn.execute(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_name = 'builder_profiles'").fetchall()}
        # The task's § Schema block, plus the four onboarding fields that had
        # nowhere else to go and the provenance stamp.
        self.assertEqual(present, {
            "app_user_id", "parent_profile", "location_pref", "remote_pref",
            "comp_floor", "tracks", "prior_years", "situation",
            "schedule_constraints", "onboarded_at", "created_at", "updated_at"})

    def test_the_primary_key_is_the_builder(self):
        # One override row per Builder, per the task's PRIMARY KEY (app_user_id).
        with web_scratch_schema() as (conn, _name):
            row = conn.execute(
                "SELECT a.attname FROM pg_index i "
                "JOIN pg_attribute a ON a.attrelid = i.indrelid "
                "                   AND a.attnum = ANY(i.indkey) "
                "WHERE i.indrelid = 'builder_profiles'::regclass "
                "  AND i.indisprimary").fetchall()
        self.assertEqual([r[0] for r in row], ["app_user_id"])

    def test_it_is_declared_in_the_grant_set(self):
        # A table queried but not declared is a service that starts cleanly and
        # 500s on that one request. REQUIRED_TABLES is what prevents it.
        self.assertEqual(schema_web.REQUIRED_TABLES["builder_profiles"],
                         ("SELECT", "INSERT", "UPDATE"))
        self.assertNotIn("DELETE",
                         schema_web.REQUIRED_TABLES["builder_profiles"])


@requires_db
class TestTheConstraintsRefuseWhatThePythonRefuses(unittest.TestCase):
    """The CHECKs are generated from the vocabularies, and test_onboarding.py
    asserts the generation. These assert the database actually enforces the
    result, which is the half a source-level test cannot reach."""

    def _insert(self, conn, **columns):
        columns = {"app_user_id": USER.id, "parent_profile": PROFILE,
                   "created_at": "x", "updated_at": "x", **columns}
        names = ", ".join(columns)
        placeholders = ", ".join(["%s"] * len(columns))
        conn.execute(f"INSERT INTO builder_profiles ({names}) "
                     f"VALUES ({placeholders})", tuple(columns.values()))

    def test_every_vocabulary_value_is_actually_storable(self):
        # The one-sided failure the generated CHECK exists to prevent: a value
        # legal in Python and refused by the column, which surfaces as a 500 on
        # one Builder's submit and nowhere else.
        with web_scratch_schema() as (conn, _name):
            seed_users(conn, USER)
            for column, vocabulary in (
                    ("location_pref", schema_web.LOCATION_PREFS),
                    ("remote_pref", schema_web.REMOTE_PREFS),
                    ("situation", schema_web.SITUATIONS)):
                for value in vocabulary:
                    self._insert(conn, **{column: value})
                    conn.execute("DELETE FROM builder_profiles")
            self._insert(conn,
                         schedule_constraints=list(schema_web.SCHEDULE_CONSTRAINTS))
            conn.rollback()

    def test_a_value_outside_the_vocabulary_is_refused(self):
        import psycopg
        for column, value in (("location_pref", "boston"),
                              ("remote_pref", "maybe"),
                              ("situation", "retired")):
            with self.subTest(column=column):
                with web_scratch_schema() as (conn, _name):
                    seed_users(conn, USER)
                    with self.assertRaises(psycopg.errors.CheckViolation):
                        self._insert(conn, **{column: value})
                    conn.rollback()

    def test_an_unlisted_schedule_constraint_is_refused(self):
        import psycopg
        with web_scratch_schema() as (conn, _name):
            seed_users(conn, USER)
            with self.assertRaises(psycopg.errors.CheckViolation):
                self._insert(conn, schedule_constraints=["no_mondays"])
            conn.rollback()

    def test_an_empty_constraint_array_is_accepted(self):
        # `{}` is "asked, and there are none"; NULL is "nobody asked". Array
        # containment admits the empty array, which is what keeps them distinct.
        with web_scratch_schema() as (conn, _name):
            seed_users(conn, USER)
            self._insert(conn, schedule_constraints=[])
            stored = conn.execute(
                "SELECT schedule_constraints FROM builder_profiles").fetchone()[0]
            self.assertEqual(stored, [])
            self.assertIsNotNone(stored)
            conn.rollback()

    def test_negative_numbers_are_refused(self):
        import psycopg
        for column in ("comp_floor", "prior_years"):
            with self.subTest(column=column):
                with web_scratch_schema() as (conn, _name):
                    seed_users(conn, USER)
                    with self.assertRaises(psycopg.errors.CheckViolation):
                        self._insert(conn, **{column: -1})
                    conn.rollback()

    def test_tracks_takes_any_value_because_the_vocabulary_is_undecided(self):
        # Deliberate: it is server-derived, and score.TRACKS' names are recorded
        # in config/pursuit-persona.json as not describing this population. Task
        # 30 decides; a CHECK now would constrain the decision.
        with web_scratch_schema() as (conn, _name):
            seed_users(conn, USER)
            self._insert(conn, tracks=["AI Integration", "anything at all"])
            conn.rollback()


@requires_db
class TestTheForeignKeyThatCouldBeWritten(unittest.TestCase):
    """builder_profiles -> app_users(id, profile), composite.

    Task 26 sketched `parent_profile REFERENCES profiles(profile)`. That one
    cannot be written from this module -- a foreign key installs system triggers
    on the REFERENCED table, so it would be DDL on a pipeline-owned table, which
    is the line schema_web.py's docstring draws. This is what was written
    instead, and it is a stronger constraint on the thing that can actually go
    wrong."""

    def test_a_parent_profile_disagreeing_with_app_users_is_refused(self):
        # The whole reason it is composite. Two answers to "which cohort is this
        # Builder in" is D66/D67 one level up: ranked by one cohort's weights
        # while being served another cohort's list, silently.
        import psycopg
        with web_scratch_schema() as (conn, _name):
            seed_users(conn, USER)
            with self.assertRaises(psycopg.errors.ForeignKeyViolation):
                conn.execute(
                    "INSERT INTO builder_profiles (app_user_id, parent_profile, "
                    "created_at, updated_at) VALUES (%s, 'some-other-cohort', "
                    "'x', 'x')", (USER.id,))
            conn.rollback()

    def test_a_row_for_a_user_who_does_not_exist_is_refused(self):
        import psycopg
        with web_scratch_schema() as (conn, _name):
            with self.assertRaises(psycopg.errors.ForeignKeyViolation):
                conn.execute(
                    "INSERT INTO builder_profiles (app_user_id, parent_profile, "
                    "created_at, updated_at) VALUES ('u_ghost', %s, 'x', 'x')",
                    (PROFILE,))
            conn.rollback()

    def test_moving_a_builder_to_a_new_cohort_carries_their_overrides(self):
        """ON UPDATE CASCADE IS THE COHORT LIFECYCLE, implemented.

        Classes are rolling. `manage_app_users.py set-profile` is one UPDATE of
        app_users.profile -- its docstring calls itself "the command that makes
        app_users.profile correctable" and names itself one of only two writers
        -- and this is what happens to the Builder's overrides when it runs.
        """
        with web_scratch_schema() as (conn, _name):
            seed_users(conn, USER, USER_B)
            for user in (USER, USER_B):
                conn.execute(
                    "INSERT INTO builder_profiles (app_user_id, parent_profile, "
                    "comp_floor, created_at, updated_at) "
                    "VALUES (%s, %s, 55000, 'x', 'x')", (user.id, PROFILE))
            conn.commit()

            # Exactly what cmd_set_profile issues.
            conn.execute("UPDATE app_users SET profile = %s WHERE id = %s",
                         (NEXT_COHORT, USER.id))
            conn.commit()

            moved = dict(conn.execute(
                "SELECT app_user_id, parent_profile FROM builder_profiles"
            ).fetchall())
            self.assertEqual(moved[USER.id], NEXT_COHORT)
            # And ONLY that Builder. Thirty share the row; moving one must not
            # move the cohort.
            self.assertEqual(moved[USER_B.id], PROFILE)
            # The override itself survives the move -- "a graduated Builder
            # keeps access unless they ask otherwise".
            self.assertEqual(conn.execute(
                "SELECT comp_floor FROM builder_profiles WHERE app_user_id = %s",
                (USER.id,)).fetchone()[0], 55000)

    def test_deleting_a_user_takes_their_overrides_with_them(self):
        with web_scratch_schema() as (conn, _name):
            seed_users(conn, USER)
            conn.execute(
                "INSERT INTO builder_profiles (app_user_id, parent_profile, "
                "created_at, updated_at) VALUES (%s, %s, 'x', 'x')",
                (USER.id, PROFILE))
            conn.execute("DELETE FROM app_users WHERE id = %s", (USER.id,))
            self.assertEqual(conn.execute(
                "SELECT count(*) FROM builder_profiles").fetchone()[0], 0)
            conn.rollback()


@requires_db
class TestTheAbsentForeignKeyIsCheckedInstead(unittest.TestCase):
    """app_users.profile -> profiles.profile is enforced at write time by
    manage_app_users.py, at deploy time here, and at request time by
    post_onboarding(). None of the three is a constraint, and the reasoning for
    that is beside the column in schema_web.ensure_schema()."""

    def test_a_clean_database_reports_nothing(self):
        with web_scratch_schema() as (conn, _name):
            seed_profile(conn)
            seed_users(conn, USER)
            self.assertEqual(schema_web.profile_mapping_problems(conn), [])

    def test_a_builder_pointed_at_a_profile_that_does_not_exist_is_reported(self):
        # The hand-typed UPDATE README tells operators not to do, and which
        # skips manage_app_users.py's check -- the one hole a constraint would
        # have closed.
        with web_scratch_schema() as (conn, _name):
            seed_users(conn, USER, USER_B)
            problems = schema_web.profile_mapping_problems(conn)
            self.assertEqual(len(problems), 1, problems)
            self.assertIn(PROFILE, problems[0])
            self.assertIn("2 user(s)", problems[0])
            # The message says how to fix it. An operator reading a refusal to
            # start needs the next command, not a diagnosis.
            self.assertIn("migrate_profiles.py", problems[0])

    def test_verify_schema_reports_it_beside_the_grant_problems(self):
        with web_scratch_schema() as (conn, _name):
            seed_users(conn, USER)
            with self.assertRaises(RuntimeError) as caught:
                schema_web.verify_schema(conn)
            self.assertIn("no row in public.profiles", str(caught.exception))

    def test_onboarding_refuses_a_session_naming_a_profile_that_does_not_exist(self):
        with web_scratch_schema() as (conn, _name):
            seed_users(conn, USER)
            with routed_at(conn):
                with self.assertRaises(onboarding.ContractError) as caught:
                    onboarding.post_onboarding(body(), USER)
            self.assertEqual(caught.exception.code, "unknown_profile")


@requires_db
class TestResolutionAgainstTheCohort(unittest.TestCase):

    def test_a_builder_with_no_row_gets_the_cohorts_answers(self):
        with web_scratch_schema() as (conn, _name):
            seed_profile(conn, criteria={
                "base": 50,
                onboarding.COHORT_DEFAULTS_KEY: {"location_pref": "nyc",
                                                 "comp_floor": 50000}})
            seed_users(conn, USER)
            resolved = onboarding.resolved_for(conn, USER)
            self.assertEqual(resolved["location_pref"], "nyc")
            self.assertEqual(resolved["comp_floor"], 50000)

    def test_a_builders_own_answer_overrides_the_cohorts(self):
        with web_scratch_schema() as (conn, _name):
            seed_profile(conn, criteria={
                "base": 50,
                onboarding.COHORT_DEFAULTS_KEY: {"location_pref": "nyc",
                                                 "comp_floor": 50000}})
            seed_users(conn, USER, USER_B)
            with routed_at(conn):
                onboarding.post_onboarding(body(location_pref="remote"), USER)
            # The one who answered moves; the one who did not keeps the cohort's
            # answer. Thirty Builders share one profiles row, so this pair is
            # what makes the claim falsifiable.
            self.assertEqual(onboarding.resolved_for(conn, USER),
                             {"location_pref": "remote", "remote_pref": "onsite_ok",
                              "comp_floor": 50000, "tracks": None})
            self.assertEqual(onboarding.resolved_for(conn, USER_B)["location_pref"],
                             "nyc")

    def test_the_cohort_of_today_has_no_builder_defaults_and_that_is_fine(self):
        # `pursuit` carries no builder_defaults section, so this is the live
        # case: everything falls through to DEFAULTS and nothing raises.
        with web_scratch_schema() as (conn, _name):
            seed_profile(conn, criteria={"base": 50})
            seed_users(conn, USER)
            self.assertEqual(onboarding.resolved_for(conn, USER),
                             dict(onboarding.DEFAULTS))


@requires_db
class TestPostOnboarding(unittest.TestCase):

    def _setup(self, conn, n=5, tracks=None):
        seed_profile(conn)
        seed_users(conn, USER, USER_B)
        return seed_jobs(conn, n, tracks=tracks)

    def test_the_form_lands_and_the_response_matches_the_contract(self):
        with web_scratch_schema() as (conn, _name):
            self._setup(conn)
            with routed_at(conn):
                result = onboarding.post_onboarding(
                    body(prior_domain="hospitality", prior_years=6,
                         situation="employed_seeking", location_pref="nyc",
                         remote_pref="hybrid_ok", comp_floor=55000,
                         schedule_constraints=["no_overnight"]),
                    USER)
            self.assertEqual(set(result),
                             {"onboarding", "seed_judgements_recorded", "profile"})
            self.assertEqual(result["profile"], PROFILE)
            self.assertTrue(result["onboarding"]["completed"])
            self.assertEqual(result["onboarding"]["prior_domain"], "hospitality")
            self.assertEqual(result["onboarding"]["prior_years"], 6)
            self.assertIsNotNone(result["onboarding"]["completed_at"])

    def test_prior_domain_goes_to_app_users_and_the_rest_to_builder_profiles(self):
        # The split looks arbitrary and is not: prior_domain exists to decompose
        # Axis B inter-annotator disagreement by background, through
        # eval_labels.labeller_id = app_users.id. It is a fact about the
        # labeller, not an input to matching.
        with web_scratch_schema() as (conn, _name):
            self._setup(conn)
            with routed_at(conn):
                onboarding.post_onboarding(
                    body(prior_domain="logistics", situation="in_program"), USER)
            self.assertEqual(conn.execute(
                "SELECT prior_domain FROM app_users WHERE id = %s",
                (USER.id,)).fetchone()[0], "logistics")
            self.assertEqual(conn.execute(
                "SELECT situation FROM builder_profiles WHERE app_user_id = %s",
                (USER.id,)).fetchone()[0], "in_program")

    def test_the_parent_profile_comes_from_the_session(self):
        with web_scratch_schema() as (conn, _name):
            self._setup(conn)
            with routed_at(conn):
                onboarding.post_onboarding(body(), USER)
            self.assertEqual(conn.execute(
                "SELECT parent_profile FROM builder_profiles WHERE app_user_id = %s",
                (USER.id,)).fetchone()[0], PROFILE)

    def test_a_bad_vocabulary_value_is_a_400_and_writes_nothing(self):
        with web_scratch_schema() as (conn, _name):
            self._setup(conn)
            with routed_at(conn):
                with self.assertRaises(onboarding.ContractError) as caught:
                    onboarding.post_onboarding(body(situation="retired"), USER)
            self.assertEqual(caught.exception.code, "unknown_situation")
            self.assertEqual(conn.execute(
                "SELECT count(*) FROM builder_profiles").fetchone()[0], 0)

    def test_resubmitting_updates_the_same_row_and_preserves_what_it_omits(self):
        """ABSENT MEANS PRESERVE, migrations/migrate_profiles.py's rule.

        A caller that did not mention a field has no opinion about it and must
        not express one. That file records all three columns this rule was
        added for after each of them was a silent overwrite.
        """
        with web_scratch_schema() as (conn, _name):
            self._setup(conn)
            with routed_at(conn):
                onboarding.post_onboarding(
                    body(comp_floor=55000, location_pref="nyc"), USER)
                onboarding.post_onboarding(body(comp_floor=60000), USER)
            rows = conn.execute(
                "SELECT comp_floor, location_pref FROM builder_profiles").fetchall()
            self.assertEqual(rows, [(60000, "nyc")])

    def test_two_builders_get_two_rows(self):
        with web_scratch_schema() as (conn, _name):
            self._setup(conn)
            with routed_at(conn):
                onboarding.post_onboarding(body(comp_floor=55000), USER)
                onboarding.post_onboarding(body(comp_floor=70000), USER_B)
            self.assertEqual(
                dict(conn.execute("SELECT app_user_id, comp_floor "
                                  "FROM builder_profiles").fetchall()),
                {USER.id: 55000, USER_B.id: 70000})

    def test_get_onboarding_reads_the_state_back(self):
        with web_scratch_schema() as (conn, _name):
            self._setup(conn)
            with routed_at(conn):
                before = onboarding.get_onboarding(USER)
                self.assertFalse(before["onboarding"]["completed"])
                onboarding.post_onboarding(body(prior_years=6), USER)
                after = onboarding.get_onboarding(USER)
            self.assertTrue(after["onboarding"]["completed"])
            self.assertEqual(after["onboarding"]["prior_years"], 6)

    def test_a_builder_who_never_onboarded_reads_as_incomplete_not_missing(self):
        # A first-run client needs to tell "has not onboarded" from "no such
        # user", and a LEFT JOIN is what keeps the first from 404ing.
        with web_scratch_schema() as (conn, _name):
            self._setup(conn)
            with routed_at(conn):
                state = onboarding.get_onboarding(USER)["onboarding"]
            self.assertEqual(state, {"completed": False, "completed_at": None,
                                     "prior_domain": None, "prior_years": None})


@requires_db
class TestSeedJudgements(unittest.TestCase):
    """Task 26's step 2: "it produces the Builder's first job_events rows ON DAY
    ONE, it seeds their track subscriptions from behaviour rather than a
    checkbox, and it teaches"."""

    def _setup(self, conn, n=5, tracks=None):
        seed_profile(conn)
        seed_users(conn, USER, USER_B)
        return seed_jobs(conn, n, tracks=tracks)

    def test_they_become_real_job_events_with_server_set_visibility(self):
        with web_scratch_schema() as (conn, _name):
            ids = self._setup(conn)
            with routed_at(conn):
                result = onboarding.post_onboarding(body(seed_judgements=[
                    {"job_id": ids[0], "verdict": "interested"},
                    {"job_id": ids[1], "verdict": "interested"},
                    {"job_id": ids[2], "verdict": "not_interested"}]), USER)
            self.assertEqual(result["seed_judgements_recorded"], 3)
            rows = conn.execute(
                "SELECT job_id, event, visibility, app_user_id, request_id, "
                "       criteria_version, match_score "
                "FROM job_events ORDER BY job_id").fetchall()
            self.assertEqual([(r[0], r[1]) for r in rows],
                             [(ids[0], "save"), (ids[1], "save"),
                              (ids[2], "dismiss")])
            # visibility is set by event type, server-side. A privacy control a
            # client can set is not one.
            self.assertEqual([r[2] for r in rows],
                             [jobs.VISIBILITY_COHORT, jobs.VISIBILITY_COHORT,
                              jobs.VISIBILITY_PRIVATE])
            # app_user_id is WHO, and without it `seen` and `applied` resolve
            # cohort-wide -- D66 and D67.
            self.assertEqual({r[3] for r in rows}, {USER.id})
            # One request_id: a seed set IS a render, and these rows name it.
            self.assertEqual(len({r[4] for r in rows}), 1)
            self.assertTrue(next(iter({r[4] for r in rows})).startswith("req_"))
            # match_score and criteria_version are looked up server-side, as of
            # the judgement. Without them nothing can reconstruct what the
            # Builder was reacting to once weights change.
            self.assertEqual([r[5] for r in rows], [1, 1, 1])
            self.assertIsNotNone(rows[0][6])

    def test_they_move_builder_job_state_in_the_same_transaction(self):
        # The append-only log keeps what happened; builder_job_state keeps the
        # current answer. record_events writes both together, which is what this
        # inherits by calling it rather than inserting.
        with web_scratch_schema() as (conn, _name):
            ids = self._setup(conn)
            with routed_at(conn):
                onboarding.post_onboarding(body(seed_judgements=[
                    {"job_id": ids[0], "verdict": "interested"},
                    {"job_id": ids[1], "verdict": "not_interested"}]), USER)
            state = {r[0]: (r[1] is not None, r[2] is not None) for r in
                     conn.execute("SELECT job_id, saved_at, dismissed_at "
                                  "FROM builder_job_state").fetchall()}
            self.assertEqual(state, {ids[0]: (True, False),
                                     ids[1]: (False, True)})

    def test_no_dismiss_reason_is_invented(self):
        # DISMISS_REASONS is a closed vocabulary about WHY, and an onboarding
        # thumbs-down carries no why. An invented one would be unfalsifiable
        # evidence in the table task 31's aggregation reads.
        with web_scratch_schema() as (conn, _name):
            ids = self._setup(conn)
            with routed_at(conn):
                onboarding.post_onboarding(body(seed_judgements=[
                    {"job_id": ids[0], "verdict": "not_interested"}]), USER)
            self.assertIsNone(conn.execute(
                "SELECT dismiss_reason FROM builder_job_state").fetchone()[0])

    def test_one_builders_judgements_are_not_anothers(self):
        with web_scratch_schema() as (conn, _name):
            ids = self._setup(conn)
            with routed_at(conn):
                onboarding.post_onboarding(body(seed_judgements=[
                    {"job_id": ids[0], "verdict": "interested"}]), USER)
                onboarding.post_onboarding(body(seed_judgements=[
                    {"job_id": ids[1], "verdict": "interested"}]), USER_B)
            self.assertEqual(
                dict(conn.execute("SELECT app_user_id, job_id FROM job_events "
                                  "ORDER BY app_user_id").fetchall()),
                {USER.id: ids[0], USER_B.id: ids[1]})

    def test_a_judgement_for_a_job_outside_the_match_set_is_dropped_not_stored(self):
        # record_events' existing behaviour, inherited: an event for a job this
        # profile has no match row for records nothing. The count in the
        # response tells the client, which is why it is the recorded count and
        # not the submitted one.
        with web_scratch_schema() as (conn, _name):
            ids = self._setup(conn)
            with routed_at(conn):
                result = onboarding.post_onboarding(body(seed_judgements=[
                    {"job_id": ids[0], "verdict": "interested"},
                    {"job_id": "j_nonexistent", "verdict": "interested"}]), USER)
            self.assertEqual(result["seed_judgements_recorded"], 1)
            self.assertEqual(conn.execute(
                "SELECT count(*) FROM job_events").fetchone()[0], 1)

    def test_the_form_still_lands_when_no_judgement_does(self):
        # The order the handler writes in: the profile row first, so the
        # survivable failure is a Builder who onboarded with no judgements --
        # which a client can retry -- rather than judgements with no Builder.
        with web_scratch_schema() as (conn, _name):
            self._setup(conn)
            with routed_at(conn):
                result = onboarding.post_onboarding(body(
                    comp_floor=55000,
                    seed_judgements=[{"job_id": "j_nonexistent",
                                      "verdict": "interested"}]), USER)
            self.assertEqual(result["seed_judgements_recorded"], 0)
            self.assertTrue(result["onboarding"]["completed"])

    def test_no_judgements_at_all_writes_no_events_and_mints_no_render(self):
        with web_scratch_schema() as (conn, _name):
            self._setup(conn)
            with routed_at(conn):
                result = onboarding.post_onboarding(body(), USER)
            self.assertEqual(result["seed_judgements_recorded"], 0)
            self.assertEqual(conn.execute(
                "SELECT count(*) FROM job_events").fetchone()[0], 0)


@requires_db
class TestTrackSubscriptionsComeFromBehaviour(unittest.TestCase):

    def test_liking_postings_subscribes_to_their_tracks(self):
        with web_scratch_schema() as (conn, _name):
            seed_profile(conn)
            seed_users(conn, USER)
            ids = seed_jobs(conn, 4, tracks=["AI Integration", "Core SWE"])
            with routed_at(conn):
                onboarding.post_onboarding(body(seed_judgements=[
                    {"job_id": ids[0], "verdict": "interested"},
                    {"job_id": ids[1], "verdict": "interested"}]), USER)
            self.assertEqual(sorted(conn.execute(
                "SELECT tracks FROM builder_profiles").fetchone()[0]),
                ["AI Integration", "Core SWE"])

    def test_disliking_a_posting_does_not_subscribe_to_its_track(self):
        with web_scratch_schema() as (conn, _name):
            seed_profile(conn)
            seed_users(conn, USER)
            ids = seed_jobs(conn, 4, tracks=["AI Integration", "Core SWE"])
            with routed_at(conn):
                onboarding.post_onboarding(body(seed_judgements=[
                    {"job_id": ids[0], "verdict": "interested"},
                    {"job_id": ids[1], "verdict": "not_interested"}]), USER)
            self.assertEqual(conn.execute(
                "SELECT tracks FROM builder_profiles").fetchone()[0],
                ["AI Integration"])

    def test_poor_fit_is_never_subscribed_to(self):
        # A real score.TRACKS value and the scorer's way of saying the posting is
        # wrong for the cohort. Subscribing somebody to it because they liked one
        # posting the scorer misjudged turns a disagreement into a preference.
        with web_scratch_schema() as (conn, _name):
            seed_profile(conn)
            seed_users(conn, USER)
            ids = seed_jobs(conn, 2, tracks=["Poor Fit"])
            with routed_at(conn):
                onboarding.post_onboarding(body(seed_judgements=[
                    {"job_id": ids[0], "verdict": "interested"}]), USER)
            self.assertIsNone(conn.execute(
                "SELECT tracks FROM builder_profiles").fetchone()[0])

    def test_re_entry_and_growth_is_never_subscribed_to(self):
        # DEV_TASKS.md's OQ-22, closed 2026-08-05: the other score.TRACKS value
        # that is a fit judgment rather than a job family (score.py:283-298).
        # Excluded the same way 'Poor Fit' is, for the same reason.
        with web_scratch_schema() as (conn, _name):
            seed_profile(conn)
            seed_users(conn, USER)
            ids = seed_jobs(conn, 2, tracks=["Re-Entry & Growth"])
            with routed_at(conn):
                onboarding.post_onboarding(body(seed_judgements=[
                    {"job_id": ids[0], "verdict": "interested"}]), USER)
            self.assertIsNone(conn.execute(
                "SELECT tracks FROM builder_profiles").fetchone()[0])

    def test_an_unscored_cohort_derives_nothing_and_stores_null(self):
        """THE LIVE CASE AS OF 2026-08-02, and the code is still right.

        primary_track is written by score.py, and `pursuit` has
        daily_narrative_budget = 0 -- so score.py writes no rows for it and
        job_scores holds zero pursuit rows. Every seed judgement therefore
        derives an empty set, and NULL is stored rather than {}: "subscribed to
        no tracks" is not an answer anybody gave and must not look like one.
        """
        with web_scratch_schema() as (conn, _name):
            seed_profile(conn)
            seed_users(conn, USER)
            ids = seed_jobs(conn, 3)          # no job_scores rows at all
            with routed_at(conn):
                onboarding.post_onboarding(body(seed_judgements=[
                    {"job_id": ids[0], "verdict": "interested"}]), USER)
            self.assertIsNone(conn.execute(
                "SELECT tracks FROM builder_profiles").fetchone()[0])

    def test_a_later_submission_without_judgements_keeps_the_subscriptions(self):
        # tracks is derived from THIS request's judgements, so absent-means-
        # preserve matters most here: a Builder editing their comp floor must not
        # lose a subscription set built from twenty real answers.
        with web_scratch_schema() as (conn, _name):
            seed_profile(conn)
            seed_users(conn, USER)
            ids = seed_jobs(conn, 2, tracks=["AI Integration"])
            with routed_at(conn):
                onboarding.post_onboarding(body(seed_judgements=[
                    {"job_id": ids[0], "verdict": "interested"}]), USER)
                onboarding.post_onboarding(body(comp_floor=60000), USER)
            self.assertEqual(conn.execute(
                "SELECT tracks FROM builder_profiles").fetchone()[0],
                ["AI Integration"])


if __name__ == "__main__":
    unittest.main()

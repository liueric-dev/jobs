"""The cohort badge: the fold, the suppression, and what may not reach either.

WHY THESE ARE IN webapp/tests/ WHEN cohort.py IS PIPELINE CODE
    Two reasons, and the second is the stronger one.

    Every claim here is about a WHERE clause and a fold over an append-only
    log, so it needs a real Postgres for the same reason test_event_replay.py
    does -- a fake connection cannot falsify a DISTINCT ON, and "count the
    latest of {save, unsave}" versus "count the saves" differ only on data a
    real server has to hold. That file already built the scratch-schema
    machinery for both sides' tables, so this one reuses it rather than
    carrying a second copy that can drift.

    And this is the only interpreter that can import BOTH cohort.py and
    webapp/jobs.py. The event vocabulary is duplicated across the process
    boundary on purpose -- the pipeline must not import fastapi -- and
    TestVocabularyDoesNotDrift is the check that keeps the duplication honest.
    It cannot live anywhere else.

WHAT IS BEING PINNED, IN ONE SENTENCE EACH
    * Two Builders produce NO badge. Not a small one. The live cohort is two.
    * A retracted save does not count, and the tie-break that makes that true
      when both events share a timestamp.
    * A `private` event cannot reach the count, enforced by the query rather
      than by the event name happening to be 'save'.
    * A NULL app_user_id is excluded rather than folded into one phantom
      Builder, which would push postings OVER the threshold.
    * The endpoint reads the materialised table and gets null when that table
      is empty, even with three saves sitting in job_events.
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
#: This directory too, so `test_event_replay` below imports under BOTH
#: invocations. `unittest discover -s tests` makes tests/ the top level and
#: loads modules under bare names; `python -m unittest tests.test_cohort_signal`
#: from webapp/ loads them under `tests.`. A bare import plus this path entry is
#: the only spelling that works either way.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import config  # noqa: F401,E402  (must come first -- performs the sys.path insert)

import cohort                                          # noqa: E402
import jobs                                            # noqa: E402
import schema                                          # noqa: E402
from auth import User                                  # noqa: E402

#: The scratch-schema harness, imported rather than rebuilt. It also performs
#: the JOBS_SCRATCH_DATABASE_URL setup this file needs: config.py has already
#: pointed DATABASE_URL at `jobs_web`, which holds CREATE on nothing, so every
#: test here would die rather than skip without it. See that module's comment.
from test_event_replay import (                         # noqa: E402
    PROFILE, USER, USER_B, redirect_db, requires_db, seed, web_scratch_schema)

#: A third and a fourth Builder. Three is the threshold, so the smallest cohort
#: that can produce a badge at all has three people in it, and proving that the
#: fold subtracts requires a fourth.
USER_C = User(id="u_cohort_c", email="c@example.test", display_name="C",
              profile=PROFILE, is_admin=False)
USER_D = User(id="u_cohort_d", email="d@example.test", display_name="D",
              profile=PROFILE, is_admin=False)

ALL_USERS = (USER, USER_B, USER_C, USER_D)

#: Enough Builders to reach every bucket boundary without inventing named
#: constants for eleven people.
def builders(n):
    return [User(id=f"u_bulk_{i:02d}", email=f"bulk{i}@example.test",
                 display_name=f"Bulk {i}", profile=PROFILE, is_admin=False)
            for i in range(n)]


def raw_event(conn, job_id, event, *, app_user_id, visibility,
              occurred_at="2026-08-02T10:00:00", profile=PROFILE):
    """One job_events row written directly, bypassing record_events.

    NECESSARY RATHER THAN CONVENIENT. Three of the cases below cannot be
    produced through the endpoint at all: a `save` stored with visibility
    'private' (visibility_for refuses to write one), and a row with
    app_user_id NULL (record_events always stamps user.id). Both are exactly
    what the aggregation has to survive -- the first is the difference between
    enforcing the rule in the query and enforcing it by convention, and the
    second is every row this table held before 2026-08-01.
    """
    conn.execute(
        """
        INSERT INTO job_events (profile, app_user_id, job_id, event,
                                visibility, occurred_at)
        VALUES (%s, %s, %s, %s, %s, %s)
        """,
        (profile, app_user_id, job_id, event, visibility, occurred_at))
    conn.commit()


def save(conn, job_id, user, at="2026-08-02T10:00:00"):
    """A cohort-visible save, exactly as visibility_for() would store it."""
    raw_event(conn, job_id, cohort.SAVE_EVENT, app_user_id=user.id,
              visibility=jobs.visibility_for(cohort.SAVE_EVENT), occurred_at=at)


def unsave(conn, job_id, user, at="2026-08-02T11:00:00"):
    """An unsave, stored `private`, exactly as visibility_for() would store it."""
    raw_event(conn, job_id, cohort.UNSAVE_EVENT, app_user_id=user.id,
              visibility=jobs.visibility_for(cohort.UNSAVE_EVENT), occurred_at=at)


def bucket_of(conn, job_id, profile=PROFILE):
    row = conn.execute(
        "SELECT save_bucket FROM cohort_signal "
        "WHERE job_id = %s AND cohort_profile = %s", (job_id, profile)).fetchone()
    return row[0] if row else None


def rows_for(conn, profile=PROFILE):
    return conn.execute(
        "SELECT job_id, save_bucket FROM cohort_signal WHERE cohort_profile = %s "
        "ORDER BY job_id", (profile,)).fetchall()


# --------------------------------------------------------------------------
# The rule itself, with no database in sight
# --------------------------------------------------------------------------

class TestBucketArithmetic(unittest.TestCase):
    """schema.cohort_bucket is pure, so the privacy rule is testable without a
    server -- the same property score_job() is kept for, and for the same
    reason: this is the function whose boundaries someone will want to move."""

    def test_below_three_is_suppressed(self):
        for n in (0, 1, 2):
            self.assertIsNone(schema.cohort_bucket(n), n)

    def test_the_boundaries_are_where_the_labels_say(self):
        for n, expected in ((3, "3-5"), (4, "3-5"), (5, "3-5"),
                            (6, "6-10"), (9, "6-10"), (10, "6-10"),
                            (11, "10+"), (400, "10+")):
            self.assertEqual(schema.cohort_bucket(n), expected, n)

    def test_ten_is_in_the_six_to_ten_bucket_not_the_open_one(self):
        # The labels are ambiguous and the code is not. '10+' reads as "ten or
        # more" and means ELEVEN or more, because the first matching bound
        # wins. Pinned rather than corrected: the strings are the task file's
        # and frontend/fixtures/contract/ already ships them verbatim.
        self.assertEqual(schema.cohort_bucket(10), "6-10")

    def test_every_bucket_the_function_can_return_satisfies_the_constraint(self):
        # The CHECK on cohort_signal.save_bucket is generated from
        # COHORT_BUCKET_LABELS, so an added bucket that the DDL did not learn
        # about would be an INSERT failure on a nightly run rather than here.
        produced = {schema.cohort_bucket(n) for n in range(3, 60)}
        self.assertEqual(produced, set(schema.COHORT_BUCKET_LABELS))

    def test_the_floor_is_three(self):
        # Asserted on the constant, not just on behaviour. Lowering it is the
        # one change the whole design is written against, and it is one
        # character.
        self.assertEqual(schema.COHORT_MIN_SAVERS, 3)


class TestVocabularyDoesNotDrift(unittest.TestCase):
    """cohort.py mirrors three constants out of jobs.py rather than importing
    them -- the pipeline must not import fastapi. This is the only interpreter
    that can see both files, so it is the only place the copy can be checked.
    A silent drift here does not raise: it produces an aggregation that counts
    nothing, forever, which is this system's documented failure mode."""

    def test_the_save_event_is_the_cohort_visible_one(self):
        self.assertEqual(jobs.COHORT_VISIBLE_EVENTS, (cohort.SAVE_EVENT,))

    def test_the_unsave_event_is_the_one_that_clears_saved_at(self):
        self.assertIn(cohort.UNSAVE_EVENT, jobs._STATE_WRITES)
        self.assertEqual(jobs._STATE_WRITES[cohort.UNSAVE_EVENT][0],
                         "saved_at = NULL")

    def test_the_cohort_visibility_string_matches(self):
        self.assertEqual(cohort.VISIBILITY_COHORT, jobs.VISIBILITY_COHORT)
        self.assertEqual(jobs.visibility_for(cohort.SAVE_EVENT),
                         cohort.VISIBILITY_COHORT)

    def test_an_unsave_is_stored_private_and_that_is_why_the_fold_is_asymmetric(self):
        # THE FINDING, PINNED. The task file says "aggregate only cohort_anon
        # events, enforce it in the query" and also "take the latest of
        # {save, unsave}". Those two instructions conflict, because an unsave
        # is NOT cohort_anon: COHORT_VISIBLE_EVENTS names only `save`. A fold
        # filtered on visibility = 'cohort_anon' would drop every unsave and
        # silently restore the retracted-save overcount.
        #
        # cohort._SAVERS_SQL resolves it by putting the visibility predicate on
        # the counted row only. If someone later makes `unsave` cohort-visible,
        # this assertion is what says the asymmetry can be removed.
        self.assertEqual(jobs.visibility_for(cohort.UNSAVE_EVENT),
                         jobs.VISIBILITY_PRIVATE)


# --------------------------------------------------------------------------
# The fold
# --------------------------------------------------------------------------

@requires_db
class TestSuppression(unittest.TestCase):
    """The first thing the task file asks a test here to pin."""

    def test_two_builders_produce_no_badge_rather_than_a_small_one(self):
        # THE TEST THE TASK FILE NAMES. docs/labelling-report-2026-08-02.md
        # records two labellers on `pursuit`, so at a floor of three this table
        # is empty by construction today -- and an empty badge is the CORRECT
        # rendering of a two-person cohort. Anyone reaching for a lower
        # threshold to "see output" fails here first.
        with web_scratch_schema() as (conn, _):
            ids = seed(conn, n=1, users=ALL_USERS)
            save(conn, ids[0], USER)
            save(conn, ids[0], USER_B)

            cohort.refresh(conn, PROFILE)

            self.assertIsNone(bucket_of(conn, ids[0]))
            # Not "a row with a NULL bucket" either. The row's existence would
            # itself publish "somebody saved this and it is below three", to a
            # role that holds SELECT on the table. Absence is the answer.
            self.assertEqual(rows_for(conn), [])

    def test_one_builder_produces_no_badge(self):
        with web_scratch_schema() as (conn, _):
            ids = seed(conn, n=1, users=ALL_USERS)
            save(conn, ids[0], USER)
            cohort.refresh(conn, PROFILE)
            self.assertEqual(rows_for(conn), [])

    def test_a_posting_nobody_saved_and_one_two_builders_saved_are_indistinguishable(self):
        # "Absence of a badge must not be readable as 'exactly one or two'."
        # Stated as an equality between two query results rather than as two
        # separate assertions, because that is what the requirement IS.
        with web_scratch_schema() as (conn, _):
            ids = seed(conn, n=2, users=ALL_USERS)
            save(conn, ids[0], USER)
            save(conn, ids[0], USER_B)
            cohort.refresh(conn, PROFILE)

            self.assertEqual(bucket_of(conn, ids[0]), bucket_of(conn, ids[1]))
            self.assertEqual(rows_for(conn), [])

    def test_three_builders_produce_the_first_bucket(self):
        with web_scratch_schema() as (conn, _):
            ids = seed(conn, n=1, users=ALL_USERS)
            for user in (USER, USER_B, USER_C):
                save(conn, ids[0], user)

            cohort.refresh(conn, PROFILE)

            self.assertEqual(bucket_of(conn, ids[0]), "3-5")

    def test_the_bucket_boundaries_survive_the_round_trip(self):
        # The arithmetic is unit-tested above; this proves the SQL's count is
        # the number that arithmetic is applied to, at every boundary the
        # labels have.
        for n, expected in ((5, "3-5"), (6, "6-10"), (10, "6-10"), (11, "10+")):
            with self.subTest(savers=n):
                with web_scratch_schema() as (conn, _):
                    people = builders(n)
                    ids = seed(conn, n=1, users=people)
                    for user in people:
                        save(conn, ids[0], user)
                    cohort.refresh(conn, PROFILE)
                    self.assertEqual(bucket_of(conn, ids[0]), expected)

    def test_no_exact_count_is_stored_anywhere_in_the_table(self):
        # The table's whole column list, asserted. A count column added "just
        # for debugging" is the leak this design is built to prevent, and it
        # would be invisible until somebody selected it.
        with web_scratch_schema() as (conn, name):
            columns = {r[0] for r in conn.execute(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_schema = %s AND table_name = 'cohort_signal'",
                (name,)).fetchall()}
            self.assertEqual(
                columns, {"job_id", "cohort_profile", "save_bucket", "computed_at"})


@requires_db
class TestTheFoldIsNotAFilter(unittest.TestCase):
    """save and unsave are BOTH events and job_events is append-only, so the
    current answer is the latest of the two per (Builder, job) -- never a
    count of `save` rows."""

    def test_a_retracted_save_does_not_count(self):
        with web_scratch_schema() as (conn, _):
            ids = seed(conn, n=1, users=ALL_USERS)
            for user in (USER, USER_B, USER_C):
                save(conn, ids[0], user)
            # Three savers, then one leaves. A filter on event='save' still
            # sees three rows and would publish a badge; the fold sees two.
            unsave(conn, ids[0], USER_C)

            cohort.refresh(conn, PROFILE)

            self.assertEqual(rows_for(conn), [])

    def test_the_save_row_is_still_there_which_is_what_makes_this_a_real_test(self):
        # If the unsave deleted the save this would all be trivially correct.
        # It does not: job_events is append-only and webapp/schema_web.py grants
        # no DELETE on it.
        with web_scratch_schema() as (conn, _):
            ids = seed(conn, n=1, users=ALL_USERS)
            save(conn, ids[0], USER)
            unsave(conn, ids[0], USER)
            naive = conn.execute(
                "SELECT COUNT(DISTINCT app_user_id) FROM job_events "
                "WHERE job_id = %s AND event = 'save'", (ids[0],)).fetchone()[0]
            self.assertEqual(naive, 1)
            self.assertEqual(cohort.savers_by_job(conn, PROFILE, min_savers=1), [])

    def test_a_re_save_after_an_unsave_counts_again(self):
        with web_scratch_schema() as (conn, _):
            ids = seed(conn, n=1, users=ALL_USERS)
            for user in (USER, USER_B):
                save(conn, ids[0], user)
            save(conn, ids[0], USER_C, at="2026-08-02T10:00:00")
            unsave(conn, ids[0], USER_C, at="2026-08-02T11:00:00")
            save(conn, ids[0], USER_C, at="2026-08-02T12:00:00")

            cohort.refresh(conn, PROFILE)

            self.assertEqual(bucket_of(conn, ids[0]), "3-5")

    def test_id_breaks_a_same_second_tie_the_way_insertion_order_did(self):
        # occurred_at is TEXT to the second and record_events stamps one `now`
        # across a whole batch, so a save and an unsave of the same posting can
        # share a timestamp exactly. Without `id DESC` the winner is arbitrary
        # -- and arbitrary in the direction that publishes a badge half the
        # time, which is the suppression failing open nondeterministically.
        same = "2026-08-02T10:00:00"
        with web_scratch_schema() as (conn, _):
            ids = seed(conn, n=1, users=ALL_USERS)
            for user in (USER, USER_B):
                save(conn, ids[0], user)
            save(conn, ids[0], USER_C, at=same)
            unsave(conn, ids[0], USER_C, at=same)      # later id: wins
            cohort.refresh(conn, PROFILE)
            self.assertEqual(rows_for(conn), [])

    def test_the_same_tie_the_other_way_round_counts(self):
        same = "2026-08-02T10:00:00"
        with web_scratch_schema() as (conn, _):
            ids = seed(conn, n=1, users=ALL_USERS)
            for user in (USER, USER_B):
                save(conn, ids[0], user)
            unsave(conn, ids[0], USER_C, at=same)
            save(conn, ids[0], USER_C, at=same)        # later id: wins
            cohort.refresh(conn, PROFILE)
            self.assertEqual(bucket_of(conn, ids[0]), "3-5")

    def test_one_builder_saving_three_times_is_one_builder(self):
        # The question the table could not answer before app_user_id: three
        # save rows on a profile thirty people share used to be
        # indistinguishable from three people.
        with web_scratch_schema() as (conn, _):
            ids = seed(conn, n=1, users=ALL_USERS)
            for at in ("10:00:00", "11:00:00", "12:00:00"):
                save(conn, ids[0], USER, at=f"2026-08-02T{at}")
            cohort.refresh(conn, PROFILE)
            self.assertEqual(cohort.savers_by_job(conn, PROFILE, min_savers=1),
                             [(ids[0], 1)])

    def test_a_builder_who_unsaves_stops_counting_on_every_posting_separately(self):
        # The fold is per (Builder, job), not per Builder. Leaving one posting
        # must not remove that Builder from another.
        with web_scratch_schema() as (conn, _):
            ids = seed(conn, n=2, users=ALL_USERS)
            for job_id in ids:
                for user in (USER, USER_B, USER_C):
                    save(conn, job_id, user)
            unsave(conn, ids[0], USER_C)

            cohort.refresh(conn, PROFILE)

            self.assertIsNone(bucket_of(conn, ids[0]))
            self.assertEqual(bucket_of(conn, ids[1]), "3-5")


@requires_db
class TestPrivateEventsCannotReachTheCount(unittest.TestCase):
    """"Applications are private and must never reach this path -- enforce it
    in the query, not by convention." Both halves are tested, and the second
    is the one a convention-only implementation passes."""

    def test_applications_do_not_produce_a_badge(self):
        with web_scratch_schema() as (conn, _):
            ids = seed(conn, n=1, users=ALL_USERS)
            for user in (USER, USER_B, USER_C):
                raw_event(conn, ids[0], "applied", app_user_id=user.id,
                          visibility=jobs.VISIBILITY_PRIVATE)
            cohort.refresh(conn, PROFILE)
            self.assertEqual(rows_for(conn), [])

    def test_no_other_event_type_produces_a_badge_either(self):
        with web_scratch_schema() as (conn, _):
            ids = seed(conn, n=1, users=ALL_USERS)
            for event in jobs.EVENT_NAMES:
                if event in (cohort.SAVE_EVENT, cohort.UNSAVE_EVENT):
                    continue
                for user in (USER, USER_B, USER_C, USER_D):
                    raw_event(conn, ids[0], event, app_user_id=user.id,
                              visibility=jobs.visibility_for(event))
            cohort.refresh(conn, PROFILE)
            self.assertEqual(rows_for(conn), [])

    def test_a_save_row_stored_private_is_not_counted(self):
        # THE TEST THAT SEPARATES ENFORCEMENT FROM CONVENTION. Every case above
        # is also passed by an implementation that merely filters
        # event = 'save' and never looks at visibility, because the event names
        # and the visibility values happen to agree today. This one is not:
        # the event name says `save` and the stored visibility says `private`,
        # and only a query with the visibility predicate in it returns nothing.
        with web_scratch_schema() as (conn, _):
            ids = seed(conn, n=1, users=ALL_USERS)
            for user in (USER, USER_B, USER_C):
                raw_event(conn, ids[0], cohort.SAVE_EVENT, app_user_id=user.id,
                          visibility=jobs.VISIBILITY_PRIVATE)
            cohort.refresh(conn, PROFILE)
            self.assertEqual(rows_for(conn), [])

    def test_a_private_save_cannot_top_up_a_sub_threshold_count(self):
        # The sharper shape of the same claim: two legitimate savers plus one
        # private save is two, not three. An implementation missing the
        # predicate publishes a badge here.
        with web_scratch_schema() as (conn, _):
            ids = seed(conn, n=1, users=ALL_USERS)
            save(conn, ids[0], USER)
            save(conn, ids[0], USER_B)
            raw_event(conn, ids[0], cohort.SAVE_EVENT, app_user_id=USER_C.id,
                      visibility=jobs.VISIBILITY_PRIVATE)
            cohort.refresh(conn, PROFILE)
            self.assertEqual(rows_for(conn), [])


@requires_db
class TestNullAppUserIdIsExcluded(unittest.TestCase):
    """Pre-column rows carry NULL and are deliberately unbackfilled. Counting
    them collapses every pre-2026-08-01 saver into one phantom Builder, and a
    phantom Builder is a whole unit of evidence toward a threshold on the
    strength of a row that names nobody -- the privacy control failing open."""

    def test_pre_column_saves_alone_produce_no_badge(self):
        with web_scratch_schema() as (conn, _):
            ids = seed(conn, n=1, users=ALL_USERS)
            for at in ("10:00:00", "11:00:00", "12:00:00"):
                raw_event(conn, ids[0], cohort.SAVE_EVENT, app_user_id=None,
                          visibility=jobs.VISIBILITY_COHORT,
                          occurred_at=f"2026-07-20T{at}")
            cohort.refresh(conn, PROFILE)
            self.assertEqual(rows_for(conn), [])

    def test_pre_column_saves_cannot_top_up_a_real_count(self):
        # Two named Builders plus any number of anonymous rows is two. If the
        # NULLs folded into one group this would be three and would publish.
        with web_scratch_schema() as (conn, _):
            ids = seed(conn, n=1, users=ALL_USERS)
            save(conn, ids[0], USER)
            save(conn, ids[0], USER_B)
            for at in ("10:00:00", "11:00:00", "12:00:00", "13:00:00"):
                raw_event(conn, ids[0], cohort.SAVE_EVENT, app_user_id=None,
                          visibility=jobs.VISIBILITY_COHORT,
                          occurred_at=f"2026-07-20T{at}")
            cohort.refresh(conn, PROFILE)
            self.assertEqual(rows_for(conn), [])

    def test_a_pre_column_unsave_cannot_retract_somebody_elses_save(self):
        # The mirror image, and it resolves in the safe direction for free:
        # NULL never equals a real id, so an unattributable unsave folds
        # against nothing and removes nobody.
        with web_scratch_schema() as (conn, _):
            ids = seed(conn, n=1, users=ALL_USERS)
            for user in (USER, USER_B, USER_C):
                save(conn, ids[0], user)
            raw_event(conn, ids[0], cohort.UNSAVE_EVENT, app_user_id=None,
                      visibility=jobs.VISIBILITY_PRIVATE,
                      occurred_at="2026-08-02T23:00:00")
            cohort.refresh(conn, PROFILE)
            self.assertEqual(bucket_of(conn, ids[0]), "3-5")


@requires_db
class TestRefreshReplacesRatherThanAccumulates(unittest.TestCase):
    """The set can shrink. A posting that falls below the threshold must LOSE
    its row -- a stale bucket is a save the Builder retracted, still published."""

    def test_a_posting_that_drops_below_the_floor_loses_its_row(self):
        with web_scratch_schema() as (conn, _):
            ids = seed(conn, n=1, users=ALL_USERS)
            for user in (USER, USER_B, USER_C):
                save(conn, ids[0], user)
            cohort.refresh(conn, PROFILE)
            self.assertEqual(bucket_of(conn, ids[0]), "3-5")

            unsave(conn, ids[0], USER_C, at="2026-08-03T09:00:00")
            rows, removed = cohort.refresh(conn, PROFILE)

            self.assertEqual(rows, [])
            self.assertEqual(removed, 1)
            self.assertIsNone(bucket_of(conn, ids[0]))

    def test_a_second_refresh_with_no_new_events_is_a_no_op(self):
        with web_scratch_schema() as (conn, _):
            ids = seed(conn, n=1, users=ALL_USERS)
            for user in (USER, USER_B, USER_C):
                save(conn, ids[0], user)
            cohort.refresh(conn, PROFILE)
            rows, removed = cohort.refresh(conn, PROFILE)
            self.assertEqual([r[0] for r in rows], [ids[0]])
            self.assertEqual(removed, 0)
            self.assertEqual(rows_for(conn), [(ids[0], "3-5")])

    def test_a_dry_run_writes_nothing(self):
        with web_scratch_schema() as (conn, _):
            ids = seed(conn, n=1, users=ALL_USERS)
            for user in (USER, USER_B, USER_C):
                save(conn, ids[0], user)
            rows, removed = cohort.refresh(conn, PROFILE, dry_run=True)
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows_for(conn), [])

    def test_another_profiles_rows_are_not_touched(self):
        # cohort_signal is keyed (job_id, cohort_profile) and the refresh
        # DELETEs by profile. A rolling programme means several cohorts exist
        # at once, and "not across cohorts" is the task file's stated privacy
        # promise -- one cohort's nightly run must not clear another's.
        other = "other-cohort"
        with web_scratch_schema() as (conn, _):
            ids = seed(conn, n=1, users=ALL_USERS)
            conn.execute(
                "INSERT INTO cohort_signal (job_id, cohort_profile, save_bucket, "
                "computed_at) VALUES (%s, %s, '6-10', '2026-08-01T00:00:00')",
                (ids[0], other))
            conn.commit()

            cohort.refresh(conn, PROFILE)

            self.assertEqual(rows_for(conn, other), [(ids[0], "6-10")])

    def test_another_profiles_saves_do_not_count_toward_this_one(self):
        with web_scratch_schema() as (conn, _):
            ids = seed(conn, n=1, users=ALL_USERS)
            save(conn, ids[0], USER)
            save(conn, ids[0], USER_B)
            raw_event(conn, ids[0], cohort.SAVE_EVENT, app_user_id=USER_C.id,
                      visibility=jobs.VISIBILITY_COHORT, profile="other-cohort")
            cohort.refresh(conn, PROFILE)
            self.assertEqual(rows_for(conn), [])


class TestTheWebappIsGrantedOnTheTable(unittest.TestCase):
    """The read endpoint joins cohort_signal, so the service needs SELECT on it.

    RED UNTIL schema_web.REQUIRED_TABLES DECLARES IT, AND RED IS THE CORRECT
    STATE. That file belongs to another stream and a second writer inside the
    same dict would be a lost update, so this assertion is the pin rather than
    the fix -- the same disposition task 36 took, and the reason the doc-policy
    baseline is pruned and never grown: a known gap is carried as a visible
    failure, not as a silence.

    Without the entry, verify_schema() never checks the table, the service
    starts cleanly, and the first GET /v1/jobs is `permission denied for table
    cohort_signal` -- a 500 on a Builder's first list render.

    test_grants.py holds the same claim from the other side, and until D69 was
    fixed it could not: its scanner dropped every string with no statement
    keyword, and jobs.py names this table only in a join fragment.
    """

    def test_cohort_signal_is_declared_select_only(self):
        import schema_web
        self.assertEqual(
            schema_web.REQUIRED_TABLES.get("cohort_signal"), ("SELECT",),
            'webapp/jobs.py joins cohort_signal, so schema_web.REQUIRED_TABLES '
            'needs "cohort_signal": ("SELECT",) -- SELECT-only because the '
            'pipeline owns the table and cohort.py is its only writer. Until '
            'it lands, verify_schema() cannot check the grant and the first '
            'list render 500s. Owned by the profiles stream; this failure is '
            'the pin, not a regression in task 28.')


@requires_db
class TestTheSchemaEnforcesTheShape(unittest.TestCase):

    def test_save_bucket_is_not_nullable(self):
        # The DELIBERATE DEVIATION from the task file's DDL sketch, which lists
        # null as a fourth value. A NULL-bucket row would mean "somebody saved
        # this and it is below three" and would be readable by a role that
        # holds SELECT -- the suppression failing open one indirection along.
        with web_scratch_schema() as (conn, name):
            nullable = conn.execute(
                "SELECT is_nullable FROM information_schema.columns "
                "WHERE table_schema = %s AND table_name = 'cohort_signal' "
                "AND column_name = 'save_bucket'", (name,)).fetchone()[0]
            self.assertEqual(nullable, "NO")

    def test_an_invented_bucket_is_refused_by_the_database(self):
        with web_scratch_schema() as (conn, _):
            ids = seed(conn, n=1, users=ALL_USERS)
            with self.assertRaises(Exception):
                conn.execute(
                    "INSERT INTO cohort_signal (job_id, cohort_profile, "
                    "save_bucket, computed_at) VALUES (%s, %s, '1-2', %s)",
                    (ids[0], PROFILE, "2026-08-02T00:00:00"))
            conn.rollback()


# --------------------------------------------------------------------------
# The read edge
# --------------------------------------------------------------------------

@requires_db
class TestTheEndpointReadsTheMaterialisedTable(unittest.TestCase):
    """"The read endpoint joins the materialised table, never job_events."""

    def _list(self, conn, user=USER):
        # EVERY Query()-defaulted parameter is passed explicitly. Calling the
        # route function directly bypasses FastAPI's dependency resolution, so
        # an omitted one arrives as the Query object itself -- and `since`
        # reaches the WHERE clause, where psycopg refuses to adapt it. The
        # failure is loud, but only for the parameters that reach SQL.
        with redirect_db(conn):
            return jobs.list_jobs(user=user, limit=50, since=None,
                                  include_dismissed=False)

    def test_a_badged_posting_carries_the_bucket(self):
        with web_scratch_schema() as (conn, _):
            ids = seed(conn, n=2, users=ALL_USERS)
            for user in (USER, USER_B, USER_C):
                save(conn, ids[0], user)
            cohort.refresh(conn, PROFILE)

            items = {row["id"]: row for row in self._list(conn)["jobs"]}

            self.assertEqual(items[ids[0]]["cohort_signal"],
                             {"save_bucket": "3-5"})
            self.assertIsNone(items[ids[1]]["cohort_signal"])

    def test_the_detail_endpoint_answers_identically(self):
        with web_scratch_schema() as (conn, _):
            ids = seed(conn, n=1, users=ALL_USERS)
            for user in (USER, USER_B, USER_C):
                save(conn, ids[0], user)
            cohort.refresh(conn, PROFILE)

            with redirect_db(conn):
                row = jobs.get_job(ids[0], USER)

            self.assertEqual(row["cohort_signal"], {"save_bucket": "3-5"})

    def test_three_saves_in_job_events_and_an_empty_table_render_as_null(self):
        # THE PROOF THAT THE ENDPOINT DOES NOT COMPUTE LIVE, stated as
        # behaviour rather than as a grep over the SQL. Everything a live
        # implementation needs is present -- three cohort_anon saves by three
        # named Builders -- and the nightly fold has not run. A live count
        # returns '3-5' here; a join against an empty table returns null.
        with web_scratch_schema() as (conn, _):
            ids = seed(conn, n=1, users=ALL_USERS)
            for user in (USER, USER_B, USER_C):
                save(conn, ids[0], user)

            items = self._list(conn)["jobs"]

            self.assertEqual(len(items), 1)
            self.assertIsNone(items[0]["cohort_signal"])

    def test_the_badge_is_the_same_for_every_builder_in_the_cohort(self):
        # It is a COHORT signal, not a personal one: unlike `saved`, it does
        # not vary by who is asking. A Builder who saved nothing sees the same
        # badge as one of the three who did.
        with web_scratch_schema() as (conn, _):
            ids = seed(conn, n=1, users=ALL_USERS)
            for user in (USER, USER_B, USER_C):
                save(conn, ids[0], user)
            cohort.refresh(conn, PROFILE)

            mine = self._list(conn, USER)["jobs"][0]
            theirs = self._list(conn, USER_D)["jobs"][0]

            self.assertEqual(mine["cohort_signal"], {"save_bucket": "3-5"})
            self.assertEqual(theirs["cohort_signal"], mine["cohort_signal"])

    def test_no_recency_reaches_the_response(self):
        # computed_at exists on the table for an operator and must not be
        # served: it is a per-posting timestamp that moves when the underlying
        # set moves, which is the recency channel bucketing exists to close.
        with web_scratch_schema() as (conn, _):
            ids = seed(conn, n=1, users=ALL_USERS)
            for user in (USER, USER_B, USER_C):
                save(conn, ids[0], user)
            cohort.refresh(conn, PROFILE)

            row = self._list(conn)["jobs"][0]

            self.assertEqual(set(row["cohort_signal"]), {"save_bucket"})
            self.assertNotIn("computed_at", row)
            self.assertNotIn("save_bucket", row)

    def test_the_response_key_order_puts_cohort_signal_before_rank(self):
        # ../../frontend/verify_fixtures.py checks the exact key ORDER of every
        # job object, not just the key set. This is the order it must learn.
        with web_scratch_schema() as (conn, _):
            ids = seed(conn, n=1, users=ALL_USERS)
            row = self._list(conn)["jobs"][0]
            expected = (list(jobs.LIST_COLUMNS) + list(jobs.STATE_FIELDS)
                        + list(jobs.COHORT_FIELDS) + ["rank"])
            self.assertEqual(list(row), expected)

    def test_the_list_and_the_detail_agree_on_where_the_field_sits(self):
        with web_scratch_schema() as (conn, _):
            ids = seed(conn, n=1, users=ALL_USERS)
            with redirect_db(conn):
                row = jobs.get_job(ids[0], USER)
            expected = (list(jobs.DETAIL_COLUMNS) + list(jobs.STATE_FIELDS)
                        + list(jobs.COHORT_FIELDS))
            self.assertEqual(list(row), expected)


@requires_db
class TestTheVolumeInstrument(unittest.TestCase):
    """This step writes zero rows on a healthy run for as long as the cohort is
    smaller than the floor, and "silence is this system's failure mode". The
    builder count beside the posting count is what tells a quiet Tuesday from
    a broken fold."""

    def test_it_counts_builders_who_currently_have_something_saved(self):
        with web_scratch_schema() as (conn, _):
            ids = seed(conn, n=2, users=ALL_USERS)
            save(conn, ids[0], USER)
            save(conn, ids[1], USER)        # same Builder, second posting
            save(conn, ids[0], USER_B)
            self.assertEqual(cohort.active_savers(conn, PROFILE), 2)

    def test_a_builder_who_unsaved_everything_stops_being_counted(self):
        with web_scratch_schema() as (conn, _):
            ids = seed(conn, n=1, users=ALL_USERS)
            save(conn, ids[0], USER)
            save(conn, ids[0], USER_B)
            unsave(conn, ids[0], USER_B)
            self.assertEqual(cohort.active_savers(conn, PROFILE), 1)

    def test_the_summary_line_carries_no_per_posting_count(self):
        # It reports how many postings are in each BUCKET, never how many
        # savers any posting has. Printing "12 postings are below the
        # threshold" would be a per-posting sub-threshold fact in a log.
        line = cohort.summarise(PROFILE, 2, [("j1", PROFILE, "3-5", "t"),
                                             ("j2", PROFILE, "10+", "t")])
        self.assertIn("2 posting(s)", line)
        self.assertIn("3-5=1", line)
        self.assertIn("10+=1", line)
        self.assertIn("2 builder(s) saving", line)
        self.assertIn("floor=3", line)


class TestItIsWiredIntoTheNightlyRun(unittest.TestCase):
    """A compute nothing schedules is a compute that never runs, and the
    failure is silent: the endpoint keeps returning null and looks correct."""

    def _steps(self):
        import importlib.util
        # Loaded by path because the filename has a hyphen -- the mechanism
        # ../../tests/test_upsert_checked.py:270-276 already uses on this file.
        path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(
                os.path.abspath(__file__)))), "run-daily.py")
        spec = importlib.util.spec_from_file_location("run_daily", path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module.STEPS

    def test_cohort_py_is_a_nightly_step(self):
        names = [s if isinstance(s, str) else s[0] for s in self._steps()]
        self.assertIn("cohort.py", names)
        self.assertEqual(names.count("cohort.py"), 1)

    def test_it_runs_with_no_flags(self):
        # --dry-run in the schedule would leave the table empty forever while
        # every test here still passed.
        steps = [s for s in self._steps()
                 if (s if isinstance(s, str) else s[0]) == "cohort.py"]
        self.assertEqual(steps, ["cohort.py"])


if __name__ == "__main__":
    unittest.main()

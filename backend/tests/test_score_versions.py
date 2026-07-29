"""The narrative's cache keys: what makes a score stale, and what must not.

WHY THIS IS A SEPARATE FILE FROM test_score.py
    test_score.py:11-13 promises NO NETWORK, NO DATABASE, and it should keep
    that promise -- it is the file someone runs to check the coercion rules on
    a laptop with nothing installed. The claims here are about a WHERE clause,
    and a fake connection cannot falsify a WHERE clause: `IS DISTINCT FROM`
    versus `<> ... IS NOT NULL` is a difference only Postgres can show you,
    and it is precisely the difference between 0 stale rows and 1,293. So
    these run against a scratch schema, exactly as
    test_extract.py's SchemaAndSelectionTests do, and skip when there is no
    database rather than passing vacuously.

WHAT EVERY TEST HERE IS PROTECTING
    Money. A staleness predicate is a decision to spend one LLM call per row
    it matches, so the failure modes are asymmetric: selecting too few rows
    costs a stale narrative nobody notices, and selecting too many costs a
    four-figure call count on a corpus of 1,293 scores across three profiles.
    Every test below is a bound on the second.

    The spend-safety test is test_the_default_predicate_is_existence_only. If
    only one test in this file survives, it should be that one -- it is the
    assertion that no version column, moving for any reason, can put a single
    extra row in front of the model without an operator typing a flag.
"""

import hashlib
import io
import json
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import llm                                             # noqa: E402
import schema                                          # noqa: E402
import score                                           # noqa: E402
from evals import scratchdb                            # noqa: E402
from lib import dbconn, envfile                        # noqa: E402

#: The pipeline's own .env, the way run-daily.py loads it -- tests must not
#: depend on the caller having exported anything. Same line as
#: tests/test_extract.py:48-50.
envfile.load(os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), ".env"))

requires_db = unittest.skipUnless(
    scratchdb.available(),
    "no scratch database: set DATABASE_URL (or JOBS_SCRATCH_DATABASE_URL)")


#: The persona and the posting the prompt digest is pinned against. Frozen
#: literals rather than a fixture load: the digest below has to move only when
#: build_prompt's TEMPLATE moves, and a fixture file someone edits would make
#: it move for a reason that has nothing to do with the template.
FIXED_PERSONA = {
    "background_summary": "Five years of production Python.",
    "strengths": ["ships things", "reads code"],
    "honest_gaps": ["no kubernetes"],
    "buckets": {"core_swe": {"description": "backend work",
                             "fit_signal": "strong"}},
    "scoring_instructions": "Score honestly.",
}

FIXED_JOB = {
    "id": "pinned", "title": "Backend Engineer", "company_name": "Acme",
    "location_raw": "New York, NY", "platform": "greenhouse",
    "summary": "A backend role on the payments team.",
    "seniority_level": "mid", "years_experience_min": 3,
    "role_archetype": "backend", "tech_stack": '["python", "postgres"]',
    "remote_policy": "hybrid", "ai_involvement": "uses_ai_tools",
    "gap_friendly_language": False, "comp_min": None, "comp_max": None,
    "facts_version": 3,
}

#: sha256 of build_prompt(FIXED_PERSONA, FIXED_JOB), committed 2026-07-29
#: under schema.SCORE_PROMPT_VERSION = 1.
#:
#: EDITING THE TEMPLATE FAILS THIS TEST, AND THE ONLY FIX IS TO BUMP
#: schema.SCORE_PROMPT_VERSION AND THIS DIGEST IN THE SAME DIFF. That is the
#: whole mechanism schema.py:207-216 describes: whitespace counts, there are
#: no carve-outs for cosmetic edits, and arguing about which changes really
#: matter is how bumps get skipped. It is affordable only because a bump
#: spends nothing on its own -- see the re-scoring flags.
PROMPT_DIGEST = "bfbae5ca612aaf052f963b356cf95c52d07666d79c370c831e20e5cdc532ccfe"

RESPONSE = {
    "fit_score": 72, "primary_track": "AI Integration",
    "gap_friendly_signal": True, "key_technologies": ["Python"],
    "gap_bridging_angle": "Five years of production Python.",
    "risk_factors": ["Wants Kubernetes depth."],
}


def _ctx(profile="tech", persona=None, prompt_version=None,
         criteria_version=5, model_label="test-model@example"):
    persona = FIXED_PERSONA if persona is None else persona
    return score.ScoreContext(
        profile=profile, persona=persona, model_label=model_label,
        persona_sha=score.persona_sha(persona),
        prompt_version=(schema.SCORE_PROMPT_VERSION if prompt_version is None
                        else prompt_version),
        criteria_version=criteria_version)


class _Profile:
    """The profiles.Profile surface run_for_profile and context_for read."""

    def __init__(self, profile="tech", persona=None, budget=20,
                 criteria_version=5, active=True):
        self.profile = profile
        self.persona = FIXED_PERSONA if persona is None else persona
        self.daily_narrative_budget = budget
        self.criteria_version = criteria_version
        self.active = active


class _Seeded(unittest.TestCase):
    """A scratch schema with one profile's ranked, open, extracted postings."""

    PROFILE = "tech"

    def _job(self, conn, job_id, first_seen="2026-07-01T00:00:00",
             facts_version=None, match_score=90):
        conn.execute(
            "INSERT INTO jobs (id, platform, company_token, company_name, "
            "source_id, title, description_text, status, first_seen, "
            "last_seen) VALUES (%s, 'greenhouse', 'acme', 'Acme', %s, "
            "'Engineer', 'We are hiring an engineer.', %s, %s, %s)",
            (job_id, job_id, schema.STATUS_OPEN, first_seen, first_seen))
        conn.execute(
            "INSERT INTO job_facts (job_id, facts_version, summary, "
            "seniority_level, extracted_at) VALUES (%s, %s, 'A role.', "
            "'mid', '2026-07-01T00:00:00')",
            (job_id, schema.FACTS_VERSION if facts_version is None
             else facts_version))
        conn.execute(
            "INSERT INTO job_matches (job_id, profile, match_score, "
            "match_reasons, facts_version, criteria_version, matched_at) "
            "VALUES (%s, %s, %s, '[]', %s, 5, '2026-07-01T00:00:00')",
            (job_id, self.PROFILE, match_score, schema.FACTS_VERSION))
        conn.commit()

    def _score(self, conn, job_id, *, facts_version=None, persona_sha=None,
               prompt_version=None, criteria_version=5, model="m@h"):
        """A job_scores row with versions stated explicitly.

        Every argument defaulting to None writes NULL, which is the
        pre-migration shape -- so `unversioned` is what you get by omission,
        exactly as it is in production.
        """
        conn.execute(
            "INSERT INTO job_scores (job_id, profile, fit_score, "
            "primary_track, scored_at, scoring_model, facts_version, "
            "persona_sha, prompt_version, criteria_version) VALUES "
            "(%s, %s, 72, 'Core SWE', '2026-07-01T00:00:00', %s, %s, %s, "
            "%s, %s)",
            (job_id, self.PROFILE, model, facts_version, persona_sha,
             prompt_version, criteria_version))
        conn.commit()

    def _picked(self, conn, ctx, **flags):
        return [j["id"] for j in
                score.select_shortlist(conn, 10, self.PROFILE, versions=ctx,
                                       **flags)]


@requires_db
class SchemaTests(unittest.TestCase):
    def test_ensure_schema_creates_the_score_version_columns(self):
        """A FRESH database is the path that could silently lack them.

        job_scores is the first table to get add_missing_columns, and the
        migration only covers databases that already exist. A schema whose
        two creation paths disagree is the drift schema.py:5-8 exists to
        prevent -- and here it would be silent: every column is nullable, so
        the writers would keep working and every row would be unversioned.
        """
        with scratchdb.scratch_schema() as (conn, _name):
            cols = dbconn.existing_columns(conn, schema.SCORES_TABLE)
            for column in ("facts_version", "persona_sha", "prompt_version",
                           "criteria_version"):
                self.assertIn(column, cols)

    def test_the_version_columns_have_no_default(self):
        """A DEFAULT would fabricate a version for every pre-existing row.

        1,293 rows predate these columns and nothing about them is
        recoverable: build_prompt changed mid-history and the rows straddle
        it. A default would stamp them all current and permanently HIDE the
        stale ones -- the opposite of what a cache key is for."""
        with scratchdb.scratch_schema() as (conn, _name):
            rows = conn.execute(
                "SELECT column_name, column_default, is_nullable "
                "FROM information_schema.columns "
                "WHERE table_schema = current_schema() "
                "AND table_name = %s AND column_name = ANY(%s)",
                (schema.SCORES_TABLE,
                 ["facts_version", "persona_sha", "prompt_version",
                  "criteria_version"])).fetchall()
            self.assertEqual(len(rows), 4)
            for name, default, nullable in rows:
                self.assertIsNone(default, msg=name)
                self.assertEqual(nullable, "YES", msg=name)


@requires_db
class SelectionTests(_Seeded):
    """What --rescore-* selects, and -- far more important -- what it does not.

    Production has 0 stale and 835 unversioned rows on `tech` the day these
    columns land. Every assertion below is calibrated on keeping those two
    numbers apart.
    """

    def test_the_default_predicate_is_existence_only(self):
        """THE SPEND-SAFETY TEST.

        A row whose every recorded version differs from the current one, with
        no flag passed, must not be selected. This is the property that lets
        SCORE_PROMPT_VERSION's bump rule be absolute: invalidation is inert,
        so over-sensitivity costs nothing. If this test fails, editing a
        persona spends a call per posting on the next nightly run.
        """
        with scratchdb.scratch_schema() as (conn, _name):
            self._job(conn, "stale-everywhere")
            self._score(conn, "stale-everywhere", facts_version=1,
                        persona_sha="a-different-persona", prompt_version=99)
            ctx = _ctx()
            self.assertEqual(self._picked(conn, ctx), [])
            self.assertEqual(
                score.select_shortlist(conn, 10, self.PROFILE), [])
            # ... and it is genuinely stale, so the flag is the only
            # difference between these two lines.
            self.assertEqual(self._picked(conn, ctx, include_stale=True),
                             ["stale-everywhere"])

    def test_an_unversioned_row_is_never_stale(self):
        """The IS DISTINCT FROM trap, asserted rather than commented.

        IS DISTINCT FROM treats NULL as "differs", so it would have marked
        every pre-migration row stale the instant the column landed -- 835 on
        `tech` alone. NULL is not version 0; it is nobody recorded it.
        """
        with scratchdb.scratch_schema() as (conn, _name):
            self._job(conn, "old-row")
            self._score(conn, "old-row", criteria_version=None)
            ctx = _ctx()
            self.assertEqual(self._picked(conn, ctx, include_stale=True), [])
            self.assertEqual(
                self._picked(conn, ctx, include_unversioned=True),
                ["old-row"])
            census = score.stale_census(conn, self.PROFILE, ctx)
            self.assertEqual(census["unversioned"], 1)
            self.assertEqual(census["stale_persona"], 0)
            self.assertEqual(census["stale_prompt"], 0)
            self.assertEqual(census["stale_facts"], 0)

    def test_a_partially_versioned_row_is_judged_on_what_it_records(self):
        """Half a provenance is still a provenance for the half it has.

        A row that records a prompt_version and nothing else is not
        unversioned -- there is a recorded value to compare -- so it goes
        stale on that column alone, and stays invisible to the unversioned
        flag."""
        with scratchdb.scratch_schema() as (conn, _name):
            self._job(conn, "half")
            self._score(conn, "half", prompt_version=99)
            ctx = _ctx()
            self.assertEqual(self._picked(conn, ctx, include_stale=True),
                             ["half"])
            self.assertEqual(
                self._picked(conn, ctx, include_unversioned=True), [])

    def test_a_criteria_bump_alone_does_not_make_a_score_stale(self):
        """criteria_version is provenance, not a cache key.

        select_shortlist reads m.match_score and m.match_reasons; build_prompt
        and _facts_block read neither. Criteria decides WHICH jobs are asked
        about, never WHAT is asked, so a weight edit that reorders the
        shortlist changes no prompt and must invalidate no narrative. It is
        stored so L2 analysis of job_events knows which weight generation
        ordered the list a user saw."""
        with scratchdb.scratch_schema() as (conn, _name):
            self._job(conn, "j1")
            self._score(conn, "j1", facts_version=schema.FACTS_VERSION,
                        persona_sha=score.persona_sha(FIXED_PERSONA),
                        prompt_version=schema.SCORE_PROMPT_VERSION,
                        criteria_version=5)
            bumped = _ctx(criteria_version=6)
            self.assertEqual(self._picked(conn, bumped, include_stale=True),
                             [])
            self.assertEqual(
                score.stale_census(conn, self.PROFILE, bumped)["current"], 1)

    def test_facts_version_is_compared_to_the_joined_row_not_the_constant(self):
        """A score is stale when the facts IT READ changed, not when
        extraction is behind.

        The row below reads facts at v2 and records v2, while
        schema.FACTS_VERSION is 3. Comparing against the constant would mark
        it stale -- and would mark all 5,029 v2 rows in production stale --
        for a backlog that belongs to extract.py and that re-scoring cannot
        fix. Re-scoring against unchanged facts produces the same narrative
        at the price of one call each."""
        with scratchdb.scratch_schema() as (conn, _name):
            behind = schema.FACTS_VERSION - 1
            self._job(conn, "behind", facts_version=behind)
            self._score(conn, "behind", facts_version=behind,
                        persona_sha=score.persona_sha(FIXED_PERSONA),
                        prompt_version=schema.SCORE_PROMPT_VERSION)
            ctx = _ctx()
            self.assertEqual(self._picked(conn, ctx, include_stale=True), [])

            # ... and the other half of the same claim: when the facts row
            # moves ahead of what the score read, it IS stale.
            conn.execute("UPDATE job_facts SET facts_version = %s "
                         "WHERE job_id = 'behind'", (schema.FACTS_VERSION,))
            conn.commit()
            self.assertEqual(self._picked(conn, ctx, include_stale=True),
                             ["behind"])

    def test_a_persona_edit_makes_its_own_profiles_scores_stale(self):
        with scratchdb.scratch_schema() as (conn, _name):
            self._job(conn, "j1")
            self._score(conn, "j1", facts_version=schema.FACTS_VERSION,
                        persona_sha=score.persona_sha(FIXED_PERSONA),
                        prompt_version=schema.SCORE_PROMPT_VERSION)
            edited = dict(FIXED_PERSONA, honest_gaps=["something else"])
            ctx = _ctx(persona=edited)
            self.assertEqual(self._picked(conn, ctx, include_stale=True),
                             ["j1"])
            self.assertEqual(
                score.stale_census(conn, self.PROFILE, ctx)["stale_persona"],
                1)

    def test_never_scored_sorts_ahead_of_stale(self):
        """A backfill must not put tonight's postings behind a queue of
        re-scores. Same argument select_unextracted_jobs makes for
        never-extracted rows (extract.py) -- the rows nobody is waiting on
        must not displace the ones somebody is."""
        with scratchdb.scratch_schema() as (conn, _name):
            # The stale one outranks the new one on match_score, so ordering
            # by match_score alone would put it first.
            self._job(conn, "stale-high", match_score=99)
            self._score(conn, "stale-high", prompt_version=99,
                        facts_version=schema.FACTS_VERSION,
                        persona_sha=score.persona_sha(FIXED_PERSONA))
            self._job(conn, "never-low", match_score=41)
            self._job(conn, "never-high", match_score=95)
            picked = self._picked(conn, _ctx(), include_stale=True)
            self.assertEqual(picked, ["never-high", "never-low", "stale-high"])

    def test_the_flags_do_not_raise_the_cap(self):
        """Stale rows compete for the same --limit slots, behind the
        never-scored ones. A flag can change WHICH rows a budget is spent on;
        it can never change how many."""
        with scratchdb.scratch_schema() as (conn, _name):
            self._job(conn, "never", match_score=50)
            self._job(conn, "stale", match_score=99)
            self._score(conn, "stale", prompt_version=99)
            self._job(conn, "unversioned", match_score=98)
            self._score(conn, "unversioned")
            picked = score.select_shortlist(
                conn, 1, self.PROFILE, versions=_ctx(), include_stale=True,
                include_unversioned=True)
            self.assertEqual([j["id"] for j in picked], ["never"])

    def test_selecting_stale_rows_needs_something_to_compare_against(self):
        """A predicate with no ScoreContext would compare every recorded
        version against NULL, which is never true -- so the flag would
        silently select nothing and the operator would conclude there was no
        backlog."""
        with scratchdb.scratch_schema() as (conn, _name):
            with self.assertRaises(ValueError):
                score.select_shortlist(conn, 10, self.PROFILE,
                                       include_stale=True)
            with self.assertRaises(ValueError):
                score.select_shortlist(conn, 10, self.PROFILE,
                                       include_unversioned=True)

    def test_the_shortlist_carries_the_facts_version_it_read(self):
        with scratchdb.scratch_schema() as (conn, _name):
            self._job(conn, "j1", facts_version=schema.FACTS_VERSION - 1)
            row = score.select_shortlist(conn, 10, self.PROFILE)[0]
            self.assertEqual(row["facts_version"], schema.FACTS_VERSION - 1)


@requires_db
class TombstoneTests(_Seeded):
    """A scoring tombstone is evidence about the prompt that was sent.

    Symmetric with extract.mark_extract_failed, which stores at the current
    facts_version precisely so a bump gives every failed posting one more
    chance under the new prompt. It is a stronger argument here: 40 of the 57
    tombstones in production were written by FAILED:glm-4.5-flash@api.z.ai,
    which is not the production pin and was failing for a credential reason
    that says nothing whatever about the postings.
    """

    def _tombstone(self, conn, job_id, ctx, facts_version=None):
        score.mark_score_failed(
            conn, job_id, ctx,
            schema.FACTS_VERSION if facts_version is None else facts_version)

    def test_a_tombstone_is_not_retried_at_the_same_version(self):
        with scratchdb.scratch_schema() as (conn, _name):
            self._job(conn, "dead")
            ctx = _ctx()
            self._tombstone(conn, "dead", ctx)
            self.assertEqual(self._picked(conn, ctx), [])
            self.assertEqual(self._picked(conn, ctx, include_stale=True), [])
            self.assertEqual(
                self._picked(conn, ctx, include_unversioned=True), [])

    def test_a_tombstone_becomes_eligible_when_the_prompt_moves(self):
        with scratchdb.scratch_schema() as (conn, _name):
            self._job(conn, "dead")
            self._tombstone(conn, "dead", _ctx())
            moved = _ctx(prompt_version=schema.SCORE_PROMPT_VERSION + 1)
            self.assertEqual(self._picked(conn, moved), [])
            self.assertEqual(self._picked(conn, moved, include_stale=True),
                             ["dead"])

    def test_a_stale_tombstone_is_its_own_census_bucket(self):
        """So an operator can retry the cheap 57 without signing up for the
        other 1,018."""
        with scratchdb.scratch_schema() as (conn, _name):
            self._job(conn, "dead")
            self._job(conn, "scored")
            ctx = _ctx()
            self._tombstone(conn, "dead", ctx)
            score.update_job_score(conn, "scored", score.normalize(RESPONSE),
                                   ctx, schema.FACTS_VERSION)
            moved = _ctx(prompt_version=schema.SCORE_PROMPT_VERSION + 1)
            census = score.stale_census(conn, self.PROFILE, moved)
            self.assertEqual(census["stale_tombstone"], 1)
            self.assertEqual(census["stale_prompt"], 1)

    def test_a_tombstone_over_a_scored_row_does_not_inherit_its_versions(self):
        """D43's shape, one column family across: a row whose tombstone
        describes one attempt and whose provenance describes an earlier,
        different one."""
        with scratchdb.scratch_schema() as (conn, _name):
            self._job(conn, "j1")
            first = _ctx()
            score.update_job_score(conn, "j1", score.normalize(RESPONSE),
                                   first, 1)
            second = _ctx(prompt_version=7)
            self._tombstone(conn, "j1", second, facts_version=2)
            row = conn.execute(
                "SELECT fit_score, scoring_model, facts_version, "
                "prompt_version FROM job_scores WHERE job_id = 'j1'"
            ).fetchone()
            self.assertIsNone(row[0])
            self.assertTrue(row[1].startswith(llm.FAILED_PREFIX))
            self.assertEqual(row[2], 2)
            self.assertEqual(row[3], 7)


@requires_db
class WriterPredicateAgreementTests(_Seeded):
    """THE EXPENSIVE-FAILURE TEST.

    A version the predicate reads and the writer does not write is a row that
    is stale the moment it is written, forever, and gets re-scored on every
    run of the flag that noticed. There is no error message for it -- the only
    symptom is a backlog that never goes down and a bill that does.
    """

    def test_a_row_the_writer_just_wrote_is_never_stale(self):
        with scratchdb.scratch_schema() as (conn, _name):
            self._job(conn, "j1")
            ctx = _ctx()
            row = score.select_shortlist(conn, 10, self.PROFILE)[0]
            score.update_job_score(conn, "j1", score.normalize(RESPONSE),
                                   ctx, row["facts_version"])
            self.assertEqual(
                self._picked(conn, ctx, include_stale=True,
                             include_unversioned=True), [])
            self.assertEqual(
                score.stale_census(conn, self.PROFILE, ctx)["current"], 1)

    def test_a_tombstone_the_writer_just_wrote_is_never_stale(self):
        with scratchdb.scratch_schema() as (conn, _name):
            self._job(conn, "j1")
            ctx = _ctx()
            row = score.select_shortlist(conn, 10, self.PROFILE)[0]
            score.mark_score_failed(conn, "j1", ctx, row["facts_version"])
            self.assertEqual(
                self._picked(conn, ctx, include_stale=True,
                             include_unversioned=True), [])

    def test_the_columns_written_are_exactly_the_predicate_columns(self):
        """Stated as column names as well as behaviour, so a future column
        added to one side and not the other fails here rather than in a
        month's invoice."""
        predicate = set()
        for clause in (score._STALE_ANY, score._UNVERSIONED):
            predicate.update(part.split()[0] for part in
                             clause.replace("(", " ").replace(")", " ").split()
                             if part.startswith("s."))
        predicate = {c[2:] for c in predicate}
        self.assertEqual(predicate,
                         {"job_id", "facts_version", "persona_sha",
                          "prompt_version"})

        conn = _RecordingConn()
        ctx = _ctx()
        score.update_job_score(conn, "j1", score.normalize(RESPONSE), ctx, 3)
        score.mark_score_failed(conn, "j1", ctx, 3)
        for sql, _params in conn.statements:
            written = sql.split("(", 1)[1].split(")", 1)[0]
            written = {c.strip() for c in written.split(",")}
            self.assertTrue(predicate <= written,
                            msg=f"{predicate - written} in the predicate and "
                                f"not in {sql[:40]}")


class _RecordingConn:
    """Records statements; enough psycopg surface for the writers."""

    def __init__(self):
        self.statements = []

    def execute(self, sql, params=None):
        self.statements.append((" ".join(sql.split()), params))
        return self

    def commit(self):
        pass


@requires_db
class CensusTests(_Seeded):
    def test_the_buckets_are_disjoint_and_sum_to_the_population(self):
        """An operator adds these up to decide what a backfill costs. If they
        overlap, the same row is paid for twice in the estimate."""
        with scratchdb.scratch_schema() as (conn, _name):
            self._job(conn, "never")
            self._job(conn, "unversioned")
            self._score(conn, "unversioned")
            self._job(conn, "stale")
            self._score(conn, "stale", prompt_version=99,
                        facts_version=schema.FACTS_VERSION,
                        persona_sha=score.persona_sha(FIXED_PERSONA))
            self._job(conn, "current")
            self._score(conn, "current", prompt_version=1,
                        facts_version=schema.FACTS_VERSION,
                        persona_sha=score.persona_sha(FIXED_PERSONA))
            census = score.stale_census(conn, self.PROFILE, _ctx())
            self.assertEqual(sum(census.values()), 4)
            self.assertEqual(census, {"never_scored": 1, "unversioned": 1,
                                      "stale_tombstone": 0, "stale_facts": 0,
                                      "stale_persona": 0, "stale_prompt": 1,
                                      "current": 1})

    def test_the_census_counts_what_the_flags_would_select(self):
        """A report that promises rows selection would not return is worse
        than no report."""
        with scratchdb.scratch_schema() as (conn, _name):
            self._job(conn, "never")
            self._job(conn, "unversioned")
            self._score(conn, "unversioned")
            self._job(conn, "stale")
            self._score(conn, "stale", prompt_version=99)
            ctx = _ctx()
            census = score.stale_census(conn, self.PROFILE, ctx)
            stale_total = sum(census[b] for b in
                              ("stale_tombstone", "stale_facts",
                               "stale_persona", "stale_prompt"))
            self.assertEqual(
                len(self._picked(conn, ctx, include_stale=True)),
                census["never_scored"] + stale_total)
            self.assertEqual(
                len(self._picked(conn, ctx, include_unversioned=True)),
                census["never_scored"] + census["unversioned"])

    def test_a_closed_posting_is_in_no_bucket_at_all(self):
        """The census population is the shortlist population. A score for a
        posting nobody can apply to is not a backlog."""
        with scratchdb.scratch_schema() as (conn, _name):
            self._job(conn, "gone")
            self._score(conn, "gone")
            conn.execute("UPDATE jobs SET status = %s WHERE id = 'gone'",
                         (schema.STATUS_CLOSED,))
            conn.commit()
            census = score.stale_census(conn, self.PROFILE, _ctx())
            self.assertEqual(sum(census.values()), 0)

    def test_the_report_makes_no_call_and_no_write(self):
        """--stale-report is what an operator runs to decide whether to spend
        anything, so it must cost nothing and be runnable with no credential
        at all -- which is why main() handles it BEFORE the api_key check."""
        with scratchdb.scratch_schema() as (conn, name):
            self._job(conn, "never")
            self._job(conn, "unversioned")
            self._score(conn, "unversioned")
            conn.execute(
                "INSERT INTO profiles (profile, persona_json, criteria_json, "
                "criteria_version, daily_narrative_budget, active, "
                "created_at, updated_at) VALUES (%s, %s, '{}', 5, 20, TRUE, "
                "'2026-07-01T00:00:00', '2026-07-01T00:00:00')",
                (self.PROFILE, json.dumps(FIXED_PERSONA)))
            conn.commit()
            before = conn.execute("SELECT count(*) FROM job_scores"
                                  ).fetchone()[0]

            def must_not_be_called(prompt, **kw):
                self.fail("--stale-report spent an LLM call")

            out = io.StringIO()
            with mock.patch.object(llm, "call", must_not_be_called), \
                    mock.patch.object(llm, "api_key", lambda: ""), \
                    mock.patch.object(score.dbconn, "connect_or_exit",
                                      lambda *a, **kw: _NoClose(conn)), \
                    mock.patch.object(sys, "argv",
                                      ["score.py", "--stale-report"]), \
                    mock.patch.object(sys, "stdout", out):
                score.main()

            text = out.getvalue()
            self.assertIn("never_scored", text)
            self.assertIn("1 unversioned", text)
            self.assertEqual(conn.execute("SELECT count(*) FROM job_scores"
                                          ).fetchone()[0], before)

    def test_the_report_survives_a_profile_that_has_no_scores(self):
        with scratchdb.scratch_schema() as (conn, _name):
            census = score.stale_census(conn, "nobody", _ctx("nobody"))
            self.assertEqual(sum(census.values()), 0)
            self.assertEqual(set(census), set(score.CENSUS_BUCKETS))


class _NoClose:
    """A connection whose close() is a no-op.

    _print_stale_report closes what it opens, which is right in production and
    fatal here: the scratch schema's contextmanager still has to DROP it.
    """

    def __init__(self, conn):
        self._conn = conn

    def __getattr__(self, name):
        return getattr(self._conn, name)

    def close(self):
        pass


class BudgetTests(unittest.TestCase):
    """No database: these are about arithmetic that decides how many calls
    get made, which is worth testing where nothing can fail for another
    reason."""

    def test_limit_zero_scores_nothing(self):
        """`limit or budget` made --limit 0 mean "spend the default", and
        --limit 0 is exactly what someone types to mean "spend nothing".
        `0 or 20` is 20, and twenty calls is the wrong answer to "none"."""
        seen = {}

        def fake_select(conn, limit, profile, **kw):
            seen["limit"] = limit
            return []

        with mock.patch.object(score, "select_shortlist", fake_select):
            score.run_for_profile(None, _Profile(budget=20), limit=0)
        self.assertEqual(seen["limit"], 0)

    def test_no_limit_still_means_the_profiles_budget(self):
        seen = {}

        def fake_select(conn, limit, profile, **kw):
            seen["limit"] = limit
            return []

        with mock.patch.object(score, "select_shortlist", fake_select):
            score.run_for_profile(None, _Profile(budget=20))
        self.assertEqual(seen["limit"], 20)

    def test_a_zero_budget_profile_stays_at_zero(self):
        seen = {}

        def fake_select(conn, limit, profile, **kw):
            seen["limit"] = limit
            return []

        with mock.patch.object(score, "select_shortlist", fake_select):
            score.run_for_profile(None, _Profile(budget=0))
        self.assertEqual(seen["limit"], 0)

    def test_the_rescore_flags_require_an_explicit_limit(self):
        """argparse refuses rather than defaulting. daily_narrative_budget is
        a nightly warm-pass quantity; reusing it as a backfill quantity is how
        an operator signs up for 51 nights of re-scoring by typing one
        flag."""
        for flag in ("--rescore-stale", "--rescore-unversioned"):
            err = io.StringIO()
            with mock.patch.object(sys, "argv", ["score.py", flag]), \
                    mock.patch.object(sys, "stderr", err):
                with self.assertRaises(SystemExit) as raised:
                    score.main()
            self.assertEqual(raised.exception.code, 2)
            self.assertIn("--limit", err.getvalue())

    def test_the_flags_are_keyword_only(self):
        """tools/claude-bench.py calls select_shortlist(conn, n, profile)
        positionally. Keyword-only keys mean no caller can acquire staleness
        by adding an argument in the wrong place."""
        import inspect
        params = inspect.signature(score.select_shortlist).parameters
        for name in ("versions", "include_stale", "include_unversioned"):
            self.assertEqual(params[name].kind,
                             inspect.Parameter.KEYWORD_ONLY, msg=name)


class PromptVersionTests(unittest.TestCase):
    def test_prompt_version_pins_the_template(self):
        """schema.SCORE_PROMPT_VERSION's comment promises this test exists and
        that it fails on any change to build_prompt's output, whitespace
        included. If you are reading this because it failed: bump
        SCORE_PROMPT_VERSION and PROMPT_DIGEST in the same diff. Do not update
        the digest alone -- that is the bump getting skipped, and the stored
        narratives it silently keeps current are the reason the column
        exists."""
        digest = hashlib.sha256(
            score.build_prompt(FIXED_PERSONA, FIXED_JOB).encode("utf-8")
        ).hexdigest()
        self.assertEqual(digest, PROMPT_DIGEST)

    def test_the_digest_would_notice_a_whitespace_edit(self):
        """The rule is only absolute if the mechanism is that sensitive."""
        prompt = score.build_prompt(FIXED_PERSONA, FIXED_JOB)
        nudged = hashlib.sha256(
            (prompt + "\n").encode("utf-8")).hexdigest()
        self.assertNotEqual(nudged, PROMPT_DIGEST)

    def test_persona_sha_covers_exactly_the_keys_the_prompt_reads(self):
        """PERSONA_PROMPT_KEYS records build_prompt's field set; build_prompt
        defines it. A key the prompt starts reading and the digest does not
        cover is a persona edit that changes every narrative and marks
        nothing stale."""
        base = score.persona_sha(FIXED_PERSONA)
        for key, value in [("background_summary", "different"),
                           ("strengths", ["other"]),
                           ("honest_gaps", []),
                           ("buckets", {}),
                           ("scoring_instructions", "differently")]:
            self.assertNotEqual(
                score.persona_sha(dict(FIXED_PERSONA, **{key: value})), base,
                msg=key)
        self.assertEqual(set(score.PERSONA_PROMPT_KEYS),
                         {"background_summary", "strengths", "honest_gaps",
                          "buckets", "scoring_instructions"})

    def test_the_eval_harness_re_exports_the_same_function(self):
        """The pipeline must not import from evals/. Moving the function and
        re-exporting it keeps the dependency pointing the way it pointed --
        and keeps one answer to "is this narrative stale"."""
        from evals.tasks import score as score_task
        self.assertIs(score_task.persona_sha, score.persona_sha)


class NightlySpendTests(unittest.TestCase):
    """The one line of this repo that decides what a night costs.

    A test on a literal constant is unusual, and it is the point. Everything
    else in this file makes re-scoring possible; this is the only thing that
    keeps it OPT-IN. Every other guard here -- the inert predicate, the
    required --limit, the report that runs without a credential -- is
    defeated the moment a --rescore-* flag appears in run-daily.py's STEPS,
    and nothing about that edit looks expensive. It is one word in a list, it
    passes every other test in the suite, and the first evidence is an
    invoice.

    run-daily.py is loaded by path because the filename has a hyphen. Same
    mechanism tests/test_upsert_checked.py:270-276 already uses on the same
    file.
    """

    def setUp(self):
        import importlib.util
        path = os.path.join(os.path.dirname(os.path.dirname(
            os.path.abspath(__file__))), "run-daily.py")
        spec = importlib.util.spec_from_file_location("run_daily", path)
        self.run_daily = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.run_daily)

    def _score_step(self):
        steps = [s for s in self.run_daily.STEPS
                 if (s if isinstance(s, str) else s[0]) == "score.py"]
        self.assertEqual(len(steps), 1,
                         "score.py must appear exactly once in STEPS")
        return steps[0]

    def test_run_daily_score_step_passes_no_rescore_flag(self):
        """Asserted verbatim, which is what run-daily.py's comment promises.

        Not "contains no --rescore-stale" -- the whole entry, so that a flag
        added under any spelling, or a --limit that would let one through,
        fails here."""
        self.assertEqual(self._score_step(),
                         ["score.py", "--active-within-days", "7"])

    def test_no_scheduled_step_can_spend_on_a_backfill(self):
        """The same claim over the whole schedule rather than one entry, so
        moving the re-scoring into some other step does not slip past the
        assertion above."""
        for step in self.run_daily.STEPS:
            args = [] if isinstance(step, str) else list(step[1:])
            for flag in ("--rescore-stale", "--rescore-unversioned"):
                self.assertNotIn(flag, args, msg=str(step))

    def test_the_flags_the_step_omits_are_flags_score_py_really_has(self):
        """Otherwise the assertion above decays into a test that misspelled
        flag names are absent, which is true of every string."""
        err = io.StringIO()
        with mock.patch.object(sys, "argv", ["score.py", "--help"]), \
                mock.patch.object(sys, "stdout", err):
            with self.assertRaises(SystemExit):
                score.main()
        for flag in ("--rescore-stale", "--rescore-unversioned",
                     "--stale-report", "--limit", "--active-within-days"):
            self.assertIn(flag, err.getvalue(), msg=flag)


class BucketCommentTests(unittest.TestCase):
    """D16 with a different key.

    CLAUDE.md makes `_comment` load-bearing in every config JSON in this repo,
    so a persona whose buckets{} carries one is a persona someone followed the
    convention writing. Its string value hit `.get('description')`, raised
    AttributeError inside the thread pool, and score_one_job's blanket handler
    turned that into ERRORED -- for every job in the batch, because every job
    in a batch shares one persona.
    """

    def test_a_bucket_comment_does_not_end_the_batch(self):
        persona = dict(FIXED_PERSONA, buckets={
            "_comment": "why these buckets and what was rejected",
            "core_swe": {"description": "backend work",
                         "fit_signal": "strong"}})
        prompt = score.build_prompt(persona, FIXED_JOB)
        self.assertIn("- core_swe: backend work (strong)", prompt)
        self.assertNotIn("_comment", prompt)
        self.assertNotIn("what was rejected", prompt)

    def test_a_comment_only_buckets_dict_drops_the_section(self):
        persona = dict(FIXED_PERSONA, buckets={"_comment": "documentation"})
        self.assertNotIn("POSITIONING BUCKETS",
                         score.build_prompt(persona, FIXED_JOB))

    def test_a_malformed_bucket_costs_its_own_line_not_the_batch(self):
        """Tolerated the way None already was. One bad bucket must not cost a
        profile its whole night."""
        persona = dict(FIXED_PERSONA, buckets={"core_swe": "a bare string"})
        prompt = score.build_prompt(persona, FIXED_JOB)
        self.assertIn("POSITIONING BUCKETS", prompt)

    def test_the_digest_notices_a_comment_edit_it_cannot_see_in_the_prompt(self):
        """Known and accepted: buckets{} is digested whole, so editing a
        `_comment` inside it moves persona_sha without moving the prompt. It
        marks rows stale that are not -- inert until someone passes
        --rescore-stale, which is the trade the whole design is built on. The
        alternative is a digest that has to re-implement build_prompt's
        filtering, and a digest that can disagree with the prompt is worse
        than one that is merely over-sensitive."""
        with_comment = dict(FIXED_PERSONA,
                            buckets={"_comment": "a", **FIXED_PERSONA["buckets"]})
        other_comment = dict(FIXED_PERSONA,
                             buckets={"_comment": "b", **FIXED_PERSONA["buckets"]})
        self.assertEqual(score.build_prompt(with_comment, FIXED_JOB),
                         score.build_prompt(other_comment, FIXED_JOB))
        self.assertNotEqual(score.persona_sha(with_comment),
                            score.persona_sha(other_comment))


if __name__ == "__main__":
    unittest.main()

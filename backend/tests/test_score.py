"""Tests for the score stage: coercion, isolation, and ranking stability.

WHAT THESE PIN, AND WHAT THEY DELIBERATELY DO NOT
    Shape, not accuracy. There is no fact of the matter about whether 72 is
    the right fit_score for a posting, so nothing here asserts that a score is
    correct -- only that whatever the model said reaches job_scores in a form
    the column can hold, or does not reach it at all. The boundary is argued
    in docs/ingestion_tests/04-score-validation.md:8-37 and it is the whole
    scope of D15.

NO NETWORK, NO DATABASE, like the rest of the suite. llm.call is stubbed at
the score.py seam and dbconn.connect is replaced with a recording fake, which
is what lets the batch-isolation test assert on the SQL that a tombstone
actually emits.

THE MALFORMED RESPONSES ARE SYNTHESISED, AND THAT IS A DEPARTURE.
    04-score-validation.md:119-120 asks for normalize() to be validated
    "against real cached responses from task 02's cache". There are none: all
    entries in backend/evals/.cache are extract responses, because no score
    run had ever been made through the harness. Every response below is
    instead built from a shape the code path can actually produce -- and the
    two that matter most are not hypothetical at all: `frontend_core` and the
    fit_score-without-a-track row are both taken from production rows
    measured on 2026-07-28 (docs/score-validation.md).
"""

import io
import json
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import extract                                        # noqa: E402
import llm                                            # noqa: E402
import profiles                                       # noqa: E402
import score                                          # noqa: E402
from evals import metrics, report, runner, tasks      # noqa: E402
from evals.tasks import score as score_task           # noqa: E402


def _response(**overrides):
    """A well-formed model response, with fields overridable per test."""
    base = {
        "fit_score": 72,
        "primary_track": "AI Integration",
        "gap_friendly_signal": True,
        "key_technologies": ["Python", "PostgreSQL"],
        "gap_bridging_angle": "Five years of production Python.",
        "risk_factors": ["Wants Kubernetes depth."],
    }
    base.update(overrides)
    return base


def _persona(**overrides):
    base = {
        "background_summary": "A background.",
        "strengths": ["ships things"],
        "honest_gaps": ["no k8s"],
        "buckets": {"core_swe": {"description": "d", "fit_signal": "f"}},
        "scoring_instructions": "Score it.",
    }
    base.update(overrides)
    return base


def _job(job_id="j1"):
    return {"id": job_id, "title": "Engineer", "company_name": "Acme",
            "location_raw": "NYC", "platform": "greenhouse",
            "summary": "A role.", "seniority_level": "mid",
            "role_archetype": "backend", "tech_stack": '["python"]',
            "remote_policy": "hybrid", "ai_involvement": "uses_ai_tools",
            "gap_friendly_language": False, "years_experience_min": 3,
            "comp_min": None, "comp_max": None}


class _FakeConn:
    """Records every statement. Enough of psycopg's surface for score.py."""

    def __init__(self, rows=()):
        self.statements = []
        self.commits = 0
        self.closed = False
        self._rows = list(rows)

    def execute(self, sql, params=None):
        self.statements.append((" ".join(sql.split()), params))
        return self

    def fetchall(self):
        return self._rows

    def fetchone(self):
        return self._rows[0] if self._rows else None

    def commit(self):
        self.commits += 1

    def close(self):
        self.closed = True


# --------------------------------------------------------------------------
# The vocabulary. D15's specific trap is that extraction's coercion would
# silently rewrite every value in this column.
# --------------------------------------------------------------------------

class TestTrackVocabulary(unittest.TestCase):
    def test_every_track_round_trips_to_its_stored_form(self):
        for track in score.TRACKS:
            self.assertEqual(score._track(track), track)

    def test_prompt_and_vocabulary_name_the_same_five(self):
        """The prompt's schema line is where the model learns the vocabulary;
        TRACKS is where the database learns it. A track in one and not the
        other is a value that can be produced and cannot be stored."""
        prompt = score.build_prompt(_persona(), _job())
        line = [ln for ln in prompt.splitlines()
                if '"primary_track"' in ln][0]
        for track in score.TRACKS:
            self.assertIn(track, line)
        named = line.split("one of:")[1].rstrip('">,')
        self.assertEqual([t.strip() for t in named.split(",")],
                         list(score.TRACKS))

    def test_punctuation_and_case_are_tolerated(self):
        for raw, want in [
            ("core_swe", "Core SWE"),
            ("CoreSWE", "Core SWE"),
            ("  ai integration  ", "AI Integration"),
            ("AI-Integration", "AI Integration"),
            ("Bridge and Solutions", "Bridge & Solutions"),
            ("bridge & solutions", "Bridge & Solutions"),
            ("re_entry_growth", "Re-Entry & Growth"),
            ("POOR FIT", "Poor Fit"),
            ("Poor Fit - not enough backend depth", "Poor Fit"),
        ]:
            self.assertEqual(score._track(raw), want, msg=raw)

    def test_off_vocabulary_is_none_not_a_guess(self):
        # 'frontend_core' is not hypothetical: 3 production rows on the
        # `frontend` profile hold it, written by deepseek-v4-flash. It is the
        # profile's name in extraction's snake_case, and there is no honest
        # mapping from it onto the five.
        for raw in ("frontend_core", "Great Fit", "poor", "", "   ",
                    None, 42, ["Poor Fit"]):
            self.assertIsNone(score._track(raw), msg=repr(raw))

    def test_poor_fit_is_never_the_fallback(self):
        """A negative answer must not be manufactured out of a malformed one.

        Defaulting to 'Poor Fit' would turn every unparseable track into a
        recorded rejection of the posting, which is worse than a NULL: NULL
        says nothing, 'Poor Fit' says something false."""
        self.assertIsNone(score._track("banana"))

    def test_extract_enum_would_have_rewritten_every_value(self):
        """The trap D15 names, asserted rather than described.

        extract._enum() lowercases and replaces separators with underscores
        because extraction's vocabularies are snake_case. Reusing it here
        would map 'Core SWE' to 'core_swe' -- a silent rewrite of all 1,231
        model-written rows in job_scores."""
        snake = tuple(t.lower().replace(" ", "_").replace("&", "and")
                      for t in score.TRACKS)
        for track in score.TRACKS:
            coerced = extract._enum(track, snake)
            self.assertNotEqual(coerced, track, msg=track)
            self.assertEqual(score._track(track), track)


class TestFitScoreCoercion(unittest.TestCase):
    def test_accepts_integers_and_integral_strings(self):
        self.assertEqual(score._fit_score(0), 0)
        self.assertEqual(score._fit_score(100), 100)
        self.assertEqual(score._fit_score("85"), 85)

    def test_booleans_are_not_scores(self):
        # bool is an int subclass; True would otherwise store as 1.
        self.assertIsNone(score._fit_score(True))
        self.assertIsNone(score._fit_score(False))

    def test_out_of_range_is_none_not_clamped(self):
        # A clamp would invent a top-of-list annotation out of a typo.
        for raw in (850, 101, -1):
            self.assertIsNone(score._fit_score(raw), msg=repr(raw))

    def test_unparseable_is_none(self):
        for raw in ("high", "72.6", None, [72], {"v": 72}):
            self.assertIsNone(score._fit_score(raw), msg=repr(raw))


# --------------------------------------------------------------------------
# normalize()
# --------------------------------------------------------------------------

class TestNormalize(unittest.TestCase):
    def test_returns_exactly_the_stored_columns(self):
        values = score.normalize(_response())
        self.assertEqual(set(values), {
            "fit_score", "primary_track", "gap_friendly_signal",
            "key_technologies", "gap_bridging_angle", "risk_factors"})
        self.assertEqual(values["fit_score"], 72)
        self.assertEqual(values["primary_track"], "AI Integration")

    def test_missing_required_key_is_unusable(self):
        for field in score.REQUIRED_FIELDS:
            partial = _response()
            del partial[field]
            self.assertIsNone(score.normalize(partial), msg=field)

    def test_null_in_both_scored_columns_is_a_tombstone(self):
        """The exact shape of the three anomalous production rows.

        llm.has_fields() checks key PRESENCE, so {"fit_score": null,
        "primary_track": null, ...} passed the old gate and was written as a
        row that no query can tell from a real score without also reading
        scoring_model."""
        unusable = _response(fit_score=None, primary_track=None)
        self.assertTrue(llm.has_fields(unusable, score.REQUIRED_FIELDS))
        self.assertIsNone(score.normalize(unusable))

    def test_one_usable_column_survives_the_other_being_junk(self):
        values = score.normalize(_response(primary_track="frontend_core"))
        self.assertEqual(values["fit_score"], 72)
        self.assertIsNone(values["primary_track"])

        values = score.normalize(_response(fit_score="unknown"))
        self.assertIsNone(values["fit_score"])
        self.assertEqual(values["primary_track"], "AI Integration")

    def test_gap_friendly_signal_is_tristate(self):
        self.assertIs(score.normalize(
            _response(gap_friendly_signal=True))["gap_friendly_signal"], True)
        self.assertIs(score.normalize(
            _response(gap_friendly_signal=False))["gap_friendly_signal"], False)
        # "yes" is the extractor shrugging, not the posting saying so.
        for raw in ("yes", 1, None, "true"):
            self.assertIsNone(score.normalize(
                _response(gap_friendly_signal=raw))["gap_friendly_signal"],
                msg=repr(raw))

    def test_lists_are_cleaned_but_keep_display_case(self):
        values = score.normalize(_response(
            key_technologies=["  React ", "react", "", None, 7,
                              {"nested": 1}, "PostgreSQL"]))
        self.assertEqual(values["key_technologies"],
                         ["React", "7", "PostgreSQL"])

    def test_non_list_collections_become_empty(self):
        values = score.normalize(_response(key_technologies="Python, Go",
                                           risk_factors=None))
        self.assertEqual(values["key_technologies"], [])
        self.assertEqual(values["risk_factors"], [])

    def test_blank_prose_is_none(self):
        self.assertIsNone(
            score.normalize(_response(gap_bridging_angle="   "))
            ["gap_bridging_angle"])


class TestNormalizeTieStructure(unittest.TestCase):
    """08's requirement: a normalisation rule that collapses values makes the
    tie problem worse, so measure it rather than assuming.

    59 postings share fit_score 45 in production and 141 share 15; the scale
    has 32 distinct values over 1,294 rows. Any rounding or clamping here
    would push p_tie up."""

    RAW = ([{"fit_score": v} for v in
            [15, 15, 15, 25, 25, 45, 55, 72, 78, 88, 0, 100]]
           + [{"fit_score": v} for v in [850, -5, "high", None, True]])

    def _normalized(self):
        out = []
        for raw in self.RAW:
            values = score.normalize(_response(**raw))
            out.append(values["fit_score"] if values else None)
        return out

    def test_no_in_range_value_is_merged_with_another(self):
        before = metrics.tie_histogram([r["fit_score"] for r in self.RAW
                                        if isinstance(r["fit_score"], int)
                                        and not isinstance(r["fit_score"], bool)
                                        and 0 <= r["fit_score"] <= 100])
        after = metrics.tie_histogram(self._normalized())
        self.assertEqual(before["distinct"], after["distinct"])
        self.assertEqual(before["largest"], after["largest"])
        self.assertEqual(before["n"], after["n"])

    def test_p_tie_does_not_rise(self):
        before = metrics.tie_histogram(
            [r["fit_score"] for r in self.RAW
             if isinstance(r["fit_score"], int)
             and not isinstance(r["fit_score"], bool)
             and 0 <= r["fit_score"] <= 100])
        after = metrics.tie_histogram(self._normalized())
        self.assertLessEqual(after["p_tie"], before["p_tie"])

    def test_rejects_are_undefined_rather_than_folded_into_a_value(self):
        after = metrics.tie_histogram(self._normalized())
        self.assertEqual(after["undefined"], 5)
        self.assertNotIn(100, [v for v, _ in after["top"] if v == 100
                               and after["distinct"] == 0])


# --------------------------------------------------------------------------
# The writes
# --------------------------------------------------------------------------

class TestWrites(unittest.TestCase):
    def test_update_job_score_cannot_be_handed_a_raw_response(self):
        """The structural half of the D15 fix.

        Coercion that a caller can skip is coercion that a caller will skip.
        update_job_score() indexes the normalize() keys directly, so a raw
        model response cannot be written even by mistake."""
        conn = _FakeConn()
        with self.assertRaises(KeyError):
            score.update_job_score(conn, "j1", "tech", {"fit_score": 72},
                                   "m@h")
        self.assertEqual(conn.statements, [])

    def test_update_job_score_writes_the_normalized_values(self):
        conn = _FakeConn()
        values = score.normalize(_response(primary_track="core_swe"))
        score.update_job_score(conn, "j1", "tech", values, "m@h")
        sql, params = conn.statements[0]
        self.assertIn("INSERT INTO", sql)
        self.assertEqual(params[0:4], ("j1", "tech", 72, "Core SWE"))
        self.assertEqual(json.loads(params[5]), ["Python", "PostgreSQL"])
        self.assertEqual(conn.commits, 1)

    def test_tombstone_clears_the_narrative_columns(self):
        """score.py's docstring promises a tombstone leaves fit_score NULL.

        The ON CONFLICT clause used to update only scored_at and
        scoring_model, so a re-tombstoned row kept a stale score under a
        'FAILED:' label -- three such rows exist in production."""
        conn = _FakeConn()
        score.mark_score_failed(conn, "j1", "tech", "m@h")
        sql, params = conn.statements[0]
        for column in ("fit_score", "primary_track", "gap_friendly_signal",
                       "key_technologies", "gap_bridging_angle",
                       "risk_factors"):
            self.assertIn(f"{column}=NULL", sql, msg=column)
        self.assertTrue(params[3].startswith(llm.FAILED_PREFIX))


# --------------------------------------------------------------------------
# D16: the buckets KeyError, and per-job isolation
# --------------------------------------------------------------------------

class TestBuildPromptWithoutBuckets(unittest.TestCase):
    def test_a_persona_without_buckets_still_builds_a_prompt(self):
        persona = _persona()
        del persona["buckets"]
        prompt = score.build_prompt(persona, _job())
        self.assertNotIn("POSITIONING BUCKETS", prompt)
        self.assertIn("HONEST GAPS", prompt)
        self.assertIn("SCORING INSTRUCTIONS", prompt)
        self.assertIn("no k8s", prompt)

    def test_an_empty_buckets_dict_drops_the_section_too(self):
        prompt = score.build_prompt(_persona(buckets={}), _job())
        self.assertNotIn("POSITIONING BUCKETS", prompt)

    def test_the_section_is_unchanged_when_buckets_are_present(self):
        prompt = score.build_prompt(_persona(), _job())
        self.assertIn("POSITIONING BUCKETS:\n- core_swe: d (f)\n\nSCORING",
                      prompt)

    def test_malformed_bucket_entries_do_not_raise(self):
        for buckets in ({"a": {}}, {"a": None}):
            self.assertIn("POSITIONING BUCKETS",
                          score.build_prompt(_persona(buckets=buckets),
                                             _job()))

    def test_validate_still_accepts_a_persona_without_buckets(self):
        """Pinned deliberately, against the task file's own suggestion.

        04-score-validation.md:168-172 proposes adding `buckets` to
        validate()'s required keys. The active `pursuit` profile ships
        without one -- there is no single target role to bucket against under
        the Pursuit scope -- so requiring it would reject a profile that
        already exists. The fix went into build_prompt instead."""
        persona = _persona()
        del persona["buckets"]
        profiles.validate(persona, {"base": 0})


class TestPerJobIsolation(unittest.TestCase):
    """run_for_profile materialises pool.map through list(), so anything that
    escapes score_one_job ends the profile's whole batch -- and every job in a
    batch shares one persona, so the first job to fail is also the last."""

    def setUp(self):
        self.conns = []
        patcher = mock.patch.object(
            score.dbconn, "connect",
            side_effect=lambda **kw: self._new_conn())
        self.addCleanup(patcher.stop)
        patcher.start()
        self.stderr = io.StringIO()
        err = mock.patch.object(sys, "stderr", self.stderr)
        self.addCleanup(err.stop)
        err.start()

    def _new_conn(self):
        conn = _FakeConn()
        self.conns.append(conn)
        return conn

    def test_a_persona_missing_buckets_now_scores(self):
        persona = _persona()
        del persona["buckets"]
        with mock.patch.object(llm, "call",
                               return_value=json.dumps(_response())):
            outcome = score.score_one_job(_job(), persona, "pursuit", "m@h")
        self.assertEqual(outcome, score.SCORED)

    def test_an_unexpected_exception_costs_one_job_not_the_batch(self):
        # strengths as a number: validate() checks the key exists, not that it
        # is iterable, so this is a profile that saves cleanly.
        persona = _persona(strengths=5)
        jobs = [_job("j1"), _job("j2"), _job("j3")]
        with mock.patch.object(llm, "call",
                               return_value=json.dumps(_response())):
            outcomes = [score.score_one_job(j, persona, "tech", "m@h")
                        for j in jobs]
        self.assertEqual(outcomes, [score.ERRORED] * 3)
        self.assertEqual(self.stderr.getvalue().count("job-score ERROR"), 3)

    def test_an_errored_job_writes_nothing(self):
        """Not a tombstone: a bug here says nothing about the posting, and
        tombstoning would discard it permanently."""
        with mock.patch.object(llm, "call",
                               return_value=json.dumps(_response())):
            score.score_one_job(_job(), _persona(strengths=5), "tech", "m@h")
        self.assertEqual([s for c in self.conns for s in c.statements], [])

    def test_run_for_profile_completes_despite_a_broken_persona(self):
        rows = [tuple([f"j{i}", "Engineer", "Acme", "NYC", "greenhouse",
                       90, "[]", "A role.", "mid", 3, "backend", "[]",
                       "hybrid", "uses_ai_tools", False, None, None])
                for i in range(4)]
        outer = _FakeConn(rows)

        class _Profile:
            profile = "tech"
            persona = _persona(strengths=5)
            daily_narrative_budget = 4

        with mock.patch.object(llm, "call",
                               return_value=json.dumps(_response())):
            counts = score.run_for_profile(outer, _Profile())
        self.assertEqual(counts[score.ERRORED], 4)
        self.assertEqual(counts[score.SCORED], 0)

    def test_transient_error_defers_and_writes_nothing(self):
        with mock.patch.object(llm, "call",
                               side_effect=llm.TransientError("429")):
            outcome = score.score_one_job(_job(), _persona(), "tech", "m@h")
        self.assertEqual(outcome, score.DEFERRED)
        self.assertEqual([s for c in self.conns for s in c.statements], [])

    def test_an_unusable_answer_is_tombstoned(self):
        unusable = json.dumps(_response(fit_score=None, primary_track=None))
        with mock.patch.object(llm, "call", return_value=unusable):
            outcome = score.score_one_job(_job(), _persona(), "tech", "m@h")
        self.assertEqual(outcome, score.REJECTED)
        sql, _ = self.conns[0].statements[0]
        self.assertIn("fit_score=NULL", sql)

    def test_the_connection_is_closed_on_every_path(self):
        with mock.patch.object(llm, "call", side_effect=RuntimeError("400")):
            score.score_one_job(_job(), _persona(), "tech", "m@h")
        self.assertTrue(all(c.closed for c in self.conns))


# --------------------------------------------------------------------------
# Ranking metrics. New in metrics.py: there was no rank correlation, no
# tolerance band and no tie histogram anywhere in evals/ before this.
# --------------------------------------------------------------------------

class TestRankingMetrics(unittest.TestCase):
    def test_spearman_is_one_for_an_order_preserving_change(self):
        rho, n = metrics.spearman([10, 20, 30, 40], [11, 22, 33, 44])
        self.assertAlmostEqual(rho, 1.0)
        self.assertEqual(n, 4)

    def test_spearman_is_minus_one_when_reversed(self):
        rho, _ = metrics.spearman([10, 20, 30], [30, 20, 10])
        self.assertAlmostEqual(rho, -1.0)

    def test_a_constant_column_has_no_ordering_to_correlate(self):
        rho, n = metrics.spearman([50, 50, 50], [10, 20, 30])
        self.assertIsNone(rho)
        self.assertEqual(n, 3)

    def test_none_is_dropped_pairwise_not_treated_as_a_value(self):
        rho, n = metrics.spearman([10, None, 30], [10, 99, 30])
        self.assertAlmostEqual(rho, 1.0)
        self.assertEqual(n, 2)

    def test_ties_share_the_mean_rank(self):
        self.assertEqual(metrics._ranks([5, 5, 9]), [1.5, 1.5, 3.0])

    def test_within_never_counts_a_missing_answer_as_agreement(self):
        self.assertTrue(metrics.within(70, 72, 5))
        self.assertFalse(metrics.within(70, 80, 5))
        self.assertFalse(metrics.within(None, None, 100))
        self.assertFalse(metrics.within(70, None, 100))

    def test_tie_histogram_counts_absence_separately(self):
        hist = metrics.tie_histogram([15, 15, 15, 25, None])
        self.assertEqual(hist["n"], 4)
        self.assertEqual(hist["undefined"], 1)
        self.assertEqual(hist["distinct"], 2)
        self.assertEqual(hist["largest"], 3)
        self.assertAlmostEqual(hist["p_tie"], 6 / 12)
        self.assertEqual(hist["top"][0], (15, 3))

    def test_top_k_overlap_is_deterministic_under_ties(self):
        ids = ["a", "b", "c", "d"]
        xs = [50, 50, 50, 10]
        ys = [50, 50, 50, 10]
        overlap, n = metrics.top_k_overlap(ids, xs, ys, k=2)
        self.assertEqual(overlap, 1.0)
        self.assertEqual(n, 4)

    def test_ranking_reports_the_worst_pair_not_just_the_mean(self):
        per_record = [(10, 10, 90), (20, 20, 80), (30, 30, 70), (40, 40, 60)]
        ids = ["a", "b", "c", "d"]
        block = metrics.ranking(per_record, ids, k=2)
        self.assertAlmostEqual(block["spearman_mean"],
                               (1.0 - 1.0 - 1.0) / 3)
        self.assertAlmostEqual(block["spearman_min"], -1.0)
        self.assertEqual(block["bands"][0]["k"], 4)
        self.assertEqual(len(block["ties"]), 3)

    def test_bands_are_reported_at_every_tolerance(self):
        block = metrics.ranking([(70, 72), (10, 30)], ["a", "b"])
        self.assertEqual(block["bands"][0]["rate"], 0.0)
        self.assertEqual(block["bands"][5]["rate"], 0.5)
        self.assertEqual(block["bands"][10]["rate"], 0.5)
        self.assertEqual(block["mean_abs_diff"], 11.0)


class _FakeResult:
    def __init__(self, job_id, normalized):
        self.job_id = job_id
        self.status = runner.OK
        self.normalized = normalized


class _FakeRun:
    def __init__(self, results):
        self.results = results
        self.model_label = "m@h"
        self.task = "score"


class TestSelfcheckAndReport(unittest.TestCase):
    def _runs(self, first, second):
        return [
            _FakeRun([_FakeResult(f"j{i}", {"fit_score": v,
                                            "primary_track": "Poor Fit"})
                      for i, v in enumerate(col)])
            for col in (first, second)]

    def _records(self, n):
        return [{"platform": "greenhouse"} for _ in range(n)]

    def test_a_score_field_adds_a_ranking_block(self):
        # Pass 2 moves every posting a little and the last one a lot: the
        # ordering survives, exact agreement does not, and the +/-5 band
        # catches three of four. Three different readings of one run, which
        # is the argument for printing all of them.
        runs = self._runs([10, 20, 30, 40], [12, 22, 28, 50])
        stats = metrics.selfcheck(runs, self._records(4),
                                  score_task.FIELD_KINDS)
        self.assertIn("fit_score", stats["ranking"])
        block = stats["ranking"]["fit_score"]
        self.assertAlmostEqual(block["spearman_mean"], 1.0)
        self.assertEqual(stats["fields"]["fit_score"]["overall"]["agree2"], 0.0)
        self.assertEqual(block["bands"][0]["k"], 0)
        self.assertEqual(block["bands"][5]["k"], 3)
        self.assertEqual(block["bands"][10]["k"], 4)

    def test_an_extract_run_is_unchanged(self):
        """No field of kind `score`, so the block is empty and every existing
        selfcheck report renders exactly as before."""
        from evals.tasks import extract as extract_task
        runs = [
            _FakeRun([_FakeResult("j0", {"seniority_level": "mid"})]),
            _FakeRun([_FakeResult("j0", {"seniority_level": "mid"})]),
        ]
        stats = metrics.selfcheck(runs, self._records(1),
                                  extract_task.FIELD_KINDS)
        self.assertEqual(stats["ranking"], {})
        self.assertEqual(report.render_ranking(stats), [])

    def test_the_report_prints_rho_the_ties_and_the_bands(self):
        runs = self._runs([10, 20, 30, 40], [12, 22, 28, 44])
        stats = metrics.selfcheck(runs, self._records(4),
                                  score_task.FIELD_KINDS)
        text = report.render_selfcheck(stats, runs)
        self.assertIn("ranking stability", text)
        self.assertIn("spearman rho", text)
        self.assertIn("within +/-5", text)
        self.assertIn("p_tie", text)


# --------------------------------------------------------------------------
# The eval task adapter
# --------------------------------------------------------------------------

def _corpus_record(with_facts=True, job_id="c1"):
    record = {"id": job_id, "title": "Backend Engineer", "company_name": "Acme",
              "location_raw": "NYC", "platform": "greenhouse",
              "description_text": "UNIQUEDESCRIPTION build services.",
              "facts": None}
    if with_facts:
        record["facts"] = {
            "facts_version": 2, "summary": "UNIQUESUMMARY a backend role.",
            "seniority_level": "mid", "role_archetype": "backend",
            "tech_stack": '["python"]', "remote_policy": "hybrid",
            "ai_involvement": "uses_ai_tools", "gap_friendly_language": False,
            "years_experience_min": 3, "comp_min": None, "comp_max": None,
            "extraction_model": "deepseek-v4-flash@api.deepseek.com"}
    return record


class TestScoreEvalTask(unittest.TestCase):
    def setUp(self):
        self.task = score_task.ScoreTask(persona=_persona())

    def test_it_is_registered_under_its_name(self):
        self.assertIs(tasks.get("score"), score_task.TASK)
        self.assertEqual(tasks.get("score").name, "score")

    def test_an_unextracted_record_is_skipped_not_counted(self):
        """select_shortlist inner-joins job_facts, so the pipeline would never
        send this record and the model is not being asked."""
        self.assertFalse(self.task.eligible(_corpus_record(with_facts=False)))
        self.assertTrue(self.task.eligible(_corpus_record()))

    def test_the_prompt_carries_facts_not_the_description(self):
        prompt = self.task.build_prompt(_corpus_record())
        self.assertIn("UNIQUESUMMARY", prompt)
        self.assertNotIn("UNIQUEDESCRIPTION", prompt)
        self.assertIn("Backend Engineer", prompt)

    def test_parse_classifies_exactly_as_the_pipeline_does(self):
        values, reason = self.task.parse(json.dumps(_response()))
        self.assertEqual(values["primary_track"], "AI Integration")
        self.assertIsNone(reason)

        values, reason = self.task.parse("I cannot help with that.")
        self.assertIsNone(values)
        self.assertEqual(reason, "unparseable_json")

        values, reason = self.task.parse(json.dumps(
            _response(fit_score=None, primary_track=None)))
        self.assertIsNone(values)
        self.assertEqual(reason, "no_usable_fields")

    def test_parse_survives_a_fenced_response(self):
        fenced = f"Sure!\n```json\n{json.dumps(_response())}\n```\n"
        values, reason = self.task.parse(fenced)
        self.assertEqual(values["fit_score"], 72)
        self.assertIsNone(reason)

    def test_the_persona_digest_covers_the_five_prompt_keys(self):
        base = self.task.persona_sha
        self.assertEqual(base, score_task.persona_sha(_persona()))
        for field, value in [("background_summary", "different"),
                             ("strengths", ["other"]),
                             ("honest_gaps", []),
                             ("buckets", {}),
                             ("scoring_instructions", "differently")]:
            self.assertNotEqual(
                score_task.persona_sha(_persona(**{field: value})), base,
                msg=field)

    def test_the_digest_ignores_what_never_reaches_a_prompt(self):
        noise = _persona(_comment="a note", profile="tech",
                         display_name="Tech")
        self.assertEqual(score_task.persona_sha(noise), self.task.persona_sha)

    def test_field_kinds_cover_every_required_field(self):
        self.assertEqual(set(score_task.FIELD_KINDS),
                         set(score.REQUIRED_FIELDS))

    def test_prose_fields_are_never_compared(self):
        """gap_bridging_angle is two sentences of generated English. Scoring
        it as an enum would report a model as unstable for rewording."""
        for field in ("gap_bridging_angle", "risk_factors"):
            self.assertEqual(score_task.FIELD_KINDS[field], "prose")


if __name__ == "__main__":
    unittest.main()

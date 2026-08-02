"""Tests for the golden set: evals/labels.py and its report.

WHAT IS PINNED HERE
    The properties that are about honesty rather than arithmetic, matching
    tests/test_evals.py's stance:

      * a model-vs-human figure cannot be built without a floor and a ceiling
      * the two axes are keyed independently, enforced by Postgres and not by
        a convention anyone has to remember
      * a label can be attached to a posting with no job_scores row and no
        job_facts row -- which is what makes recall estimable at all
      * an abstention is never counted as agreement
      * nothing in this package can write a label without a person

THE DATABASE TESTS ARE REAL, AND THAT IS DELIBERATE
    The independence of the two axes is a claim about two PARTIAL UNIQUE
    INDEXES. A fake connection cannot falsify it -- it would accept every
    insert whether or not the indexes are there, which is the same argument
    evals/scratchdb.py:9 makes about SAVEPOINT and _FakeConn. They skip
    cleanly where no Postgres is reachable.
"""

import ast
import json
import os
import re
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from evals import labels, metrics, report, scratchdb  # noqa: E402
from evals.tasks import extract as extract_task       # noqa: E402
from lib import envfile                               # noqa: E402

#: The pipeline's own .env, the way run-daily.py and tests/test_scratchdb.py
#: load it. Tests must not depend on the caller having exported anything.
envfile.load(os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), ".env"))


def _label(job_id, field, value, who, *, axis=labels.AXIS_A, round_no=1,
           profile=None, platform=None):
    return {"axis": axis, "label_set": "s", "job_id": job_id, "field": field,
            "value": value, "profile": profile, "labeller_id": who,
            "round_no": round_no, "labelled_at": "2026-07-28T00:00:00",
            "note": None, "platform": platform}


def _cell(n, agree2, ci=(0.0, 1.0)):
    """A metrics.field_cell()-shaped stub, only as far as the reader reads it.

    `ci` defaults to the whole range because most assertions here do not care
    -- but the breakout's thin-cell marker is computed FROM the interval
    (labels.is_thin), so a fixture standing in for a real 98-record cell has
    to carry a real 98-record interval or it reads as thin.
    """
    return {"n": n, "agree2": agree2, "agree2_ci": ci}


KINDS = extract_task.FIELD_KINDS


# --------------------------------------------------------------------------
# The form
# --------------------------------------------------------------------------

class TestQuestions(unittest.TestCase):

    def test_vocabulary_is_extract_s_own_never_a_copy(self):
        # A human label recorded as "Mid-Level" cannot be compared against a
        # job_facts row holding "mid": it would score formatting. This is the
        # one property that makes the whole comparison meaningful, so it is
        # checked against extract.py directly rather than against a literal.
        import extract as extract_stage
        by_field = {q.field: q for q in labels.questions()}
        self.assertEqual(by_field["seniority_level"].choices,
                         tuple(extract_stage.SENIORITY))
        self.assertEqual(by_field["ai_involvement"].choices,
                         tuple(extract_stage.AI_INVOLVEMENT))
        self.assertEqual(by_field["remote_policy"].choices,
                         tuple(extract_stage.REMOTE_POLICY))

    def test_ai_involvement_and_seniority_are_asked_first(self):
        # Not cosmetic. Task 06 measured ai_involvement at 77.8% pairwise
        # self-agreement on hn_whoishiring, and it is how the Pursuit cohort's
        # opportunity space is identified at all. A volunteer who labels five
        # jobs and stops must have spent those five on the fields that matter.
        self.assertEqual(labels.AXIS_A_FIELDS[:2],
                         ("ai_involvement", "seniority_level"))

    def test_the_priority_fields_are_either_asked_or_recorded_as_unstable(self):
        # 03-metrics-and-golden-set.md:116 -- let the selfcheck narrow the set,
        # and record what it removed. A field silently missing from the form is
        # indistinguishable from one nobody thought of.
        for field in extract_task.PRIORITY_FIELDS:
            self.assertIn(field,
                          set(labels.AXIS_A_FIELDS) | set(labels.KNOWN_UNSTABLE),
                          f"{field} is scored by match.py but is neither on "
                          f"the form nor recorded as known-unstable")
        self.assertFalse(set(labels.AXIS_A_FIELDS) & set(labels.KNOWN_UNSTABLE))

    def test_every_axis_a_field_is_a_field_metrics_can_score(self):
        for field in labels.AXIS_A_FIELDS:
            self.assertIn(field, KINDS)
            self.assertNotEqual(KINDS[field], "prose")

    def test_off_vocabulary_answers_are_refused(self):
        with self.assertRaises(ValueError):
            labels.validate("A", "seniority_level", "Mid-Level")
        with self.assertRaises(ValueError):
            labels.validate("A", "not_a_field", "mid")
        with self.assertRaises(ValueError):
            labels.validate("Z", "seniority_level", "mid")

    def test_abstention_is_none_not_a_value(self):
        for raw in (None, "", "unsure"):
            self.assertIsNone(labels.validate("A", "seniority_level", raw))
        self.assertEqual(labels.validate("A", "seniority_level", "mid"), "mid")

    def test_axis_b_has_no_middle_option(self):
        would = [q for q in labels.questions() if q.axis == labels.AXIS_B][0]
        self.assertEqual(would.choices, ("yes", "no"))

    def test_role_tracks_vocabulary_is_the_pipelines_own_plus_one(self):
        import extract as extract_stage
        track = [q for q in labels.questions() if q.field == "role_track"][0]
        self.assertEqual(track.choices,
                         tuple(extract_stage.ROLE_TRACK) + (labels.NO_TRACK_FITS,))
        # The nine must be byte-identical to extract.py's, in its order. A copy
        # here would score formatting rather than the answer -- questions()'
        # docstring is the argument.
        self.assertEqual(track.choices[:-1], tuple(extract_stage.ROLE_TRACK))

    def test_no_track_fits_is_a_value_and_not_an_abstention(self):
        # THE DISTINCTION THIS PINS. extract.py:338 tells the model that null
        # means "no listed track describes this role" -- a verdict. The form's
        # "I can't tell from this posting" is an abstention. Both would be
        # stored as NULL without NO_TRACK_FITS, and model_vs_human would then
        # score a considered verdict and a shrug as the same answer.
        self.assertEqual(
            labels.validate("A", "role_track", labels.NO_TRACK_FITS),
            labels.NO_TRACK_FITS)
        for raw in (None, "", "unsure"):
            self.assertIsNone(labels.validate("A", "role_track", raw))

    def test_no_track_fits_reads_as_agreement_against_a_model_null(self):
        # The fold happens at comparison, never in storage -- see
        # as_model_domain(). Folding in validate() would make the two
        # indistinguishable in eval_labels forever.
        self.assertIsNone(
            labels.as_model_domain("role_track", labels.NO_TRACK_FITS))
        self.assertEqual(metrics.exact("enum", None, None), True)
        # Every other field is untouched, including a value that happens to
        # look similar.
        self.assertEqual(
            labels.as_model_domain("role_archetype", "other"), "other")
        self.assertEqual(
            labels.as_model_domain("role_track", "software_engineering"),
            "software_engineering")

    def test_role_track_is_on_the_form_without_a_self_consistency_floor(self):
        # Recorded rather than quietly true. The other four axis-A fields are
        # on the form because task 06 measured them unstable; role_track has no
        # task 06 figure at all -- it postdates that run -- and is here because
        # task 30 groups its precision figures by this vocabulary. If a
        # selfcheck ever does measure it, this test is the place that says the
        # justification changed.
        self.assertIn("role_track", labels.AXIS_A_FIELDS)
        self.assertNotIn("role_track", labels.KNOWN_UNSTABLE)
        self.assertEqual(KINDS["role_track"], "enum")


# --------------------------------------------------------------------------
# Sampling -- including the rows the pipeline threw away
# --------------------------------------------------------------------------

def _pool_rows():
    """A pool with all three strata and one row that is in none of them."""
    rows = []
    for i in range(12):
        rows.append({"job_id": f"surf{i:02d}", "platform": "greenhouse",
                     "tier": 1, "facts_version": 3, "match_score": 70})
    for i in range(12):
        rows.append({"job_id": f"low{i:02d}", "platform": "hn_whoishiring",
                     "tier": 2, "facts_version": 3, "match_score": None})
    for i in range(12):
        rows.append({"job_id": f"gate{i:02d}", "platform": "builtin",
                     "tier": 3, "facts_version": None, "match_score": None})
    # Inside the gate, never extracted: the nightly run has not reached it.
    # Not a stratum -- labelling it measures the schedule, not the model.
    rows.append({"job_id": "pending", "platform": "ashby", "tier": 1,
                 "facts_version": None, "match_score": None})
    for row in rows:
        row["stratum"] = labels.classify(row, max_tier=2)
        row["computed_score"] = None
    return rows


class TestStrata(unittest.TestCase):

    def test_classification(self):
        by_id = {r["job_id"]: r["stratum"] for r in _pool_rows()}
        self.assertEqual(by_id["surf00"], "surfaced")
        self.assertEqual(by_id["low00"], "below_floor")
        self.assertEqual(by_id["gate00"], "gate_rejected")
        self.assertIsNone(by_id["pending"])

    def test_the_tail_offset_is_stable_and_stays_in_range(self):
        # Pure, so it is testable with no database -- which is what
        # 03-metrics-and-golden-set.md's definition of done requires of this
        # package, and the reason the rotation is computed in Python rather
        # than with Postgres hashtext(). Integer arithmetic, so it is the same
        # number on every platform.
        for size in (1, 2, 7, 190):
            for rank in range(12):
                off = labels.tail_offset(rank, size)
                self.assertGreaterEqual(off, 0)
                self.assertLess(off, size)
                self.assertEqual(off, labels.tail_offset(rank, size))
        self.assertEqual(labels.tail_offset(3, 0), 0)

    def test_offsets_tile_the_tail_instead_of_colliding(self):
        # THE MEASUREMENT THAT CHOSE THIS FUNCTION, and the reason it takes a
        # rank rather than a labeller_id. The first version hashed the name:
        # stateless, stable, and it spreads people at RANDOM, which is the
        # birthday problem, not a partition. Against the drawn 200-row set
        # (190-row tail), ten labellers doing twenty postings each:
        #
        #     hashed offsets       84 distinct postings   -- misses the DoD
        #     rank-spaced         110 distinct postings   -- the ideal
        #
        # Same sitting, same set, 26 postings of difference.
        tail, overlap, budget = 190, 10, 20
        for n in (5, 10):
            seen = set(range(overlap))
            for rank in range(n):
                off = labels.tail_offset(rank, tail)
                seen.update(overlap + ((k + off) % tail)
                            for k in range(budget - overlap))
            self.assertEqual(len(seen), overlap + n * (budget - overlap),
                             f"{n} labellers must tile the tail, not collide")

    def test_a_gate_rejected_row_may_still_carry_facts(self):
        # The stratum's comment used to promise these rows have no job_facts.
        # They can: extraction is SHARED and its queue is the union over
        # ACTIVE profiles, so anything an earlier active profile pulled in
        # keeps its facts under a gate that now rejects it. 24 of the 50
        # gate-rejected rows in pursuit-v1 are like this. Rejection is what
        # defines the stratum; the facts are incidental.
        row = {"job_id": "g", "tier": 3, "facts_version": 3,
               "match_score": None}
        self.assertEqual(labels.classify(row, 2), "gate_rejected")

    def test_a_labeller_with_no_labels_yet_ranks_zero_not_crashes(self):
        # They are still inside the overlap block, which everyone walks in the
        # same order, so the offset cannot matter yet -- but next_item() must
        # not need a special case for their first request.
        self.assertEqual(labels.tail_offset(0, 190), 0)

    def test_the_set_contains_rows_the_pipeline_rejected(self):
        # THE POINT OF THE WHOLE STRATIFICATION. Everything measured before
        # this was something the pipeline already chose to surface, so only
        # precision was estimable. A set with no rejected rows cannot bound
        # recall at all, however large it is.
        picked = labels.sample([r for r in _pool_rows() if r["stratum"]], 20,
                               seed=1)
        strata = {r["stratum"] for r in picked}
        self.assertIn("below_floor", strata)
        self.assertIn("gate_rejected", strata)

        rejected = [r for r in picked if r["stratum"] != "surfaced"]
        self.assertTrue(rejected)
        for row in rejected:
            # No job_matches row, hence no job_scores row: match.py:291 stores
            # one only at or above MATCH_FLOOR.
            self.assertIsNone(row["match_score"])
        self.assertTrue(any(r["stratum"] == "gate_rejected" and
                            r["facts_version"] is None for r in picked),
                        "gate-rejected rows have no job_facts row either")

    def test_a_row_never_extracted_is_not_sampled(self):
        picked = labels.sample([r for r in _pool_rows() if r["stratum"]], 30,
                               seed=1)
        self.assertNotIn("pending", {r["job_id"] for r in picked})

    def test_sampling_is_deterministic_and_pinned_by_sorted_job_id(self):
        pool = [r for r in _pool_rows() if r["stratum"]]
        a = labels.sample(list(pool), 20, seed=7)
        b = labels.sample(list(pool), 20, seed=7)
        self.assertEqual([r["job_id"] for r in a], [r["job_id"] for r in b])
        self.assertEqual([r["job_id"] for r in a],
                         sorted(r["job_id"] for r in a))
        self.assertEqual(labels.digest(a), labels.digest(b))
        self.assertNotEqual(labels.digest(a),
                            labels.digest(labels.sample(list(pool), 20, seed=8)))

    def test_overlap_rows_come_first_in_every_queue(self):
        # The ceiling is the measurement most easily lost to attrition. A
        # volunteer who labels ten jobs and stops has contributed to it only
        # if the shared rows were at the front.
        picked = labels.sample([r for r in _pool_rows() if r["stratum"]], 24,
                               seed=3, overlap=6)
        flags = [r["overlap"] for r in picked]
        self.assertEqual(flags[:6], [True] * 6)
        self.assertNotIn(True, flags[6:])
        # Still canonically ordered within each half.
        for half in (picked[:6], picked[6:]):
            self.assertEqual([r["job_id"] for r in half],
                             sorted(r["job_id"] for r in half))

    def test_the_overlap_block_mirrors_the_set_it_is_drawn_from(self):
        # THE OVERLAP BLOCK IS THE WHOLE INTER-ANNOTATOR CEILING -- it is the
        # only part of the set more than one person sees. Taking the head of a
        # job_id sort has no stratification guarantee, and the first draw of
        # pursuit-v1 returned 6 gate_rejected / 3 surfaced / 1 below_floor
        # against a 25/50/25 set. Six of ten rows would have been postings the
        # pipeline threw away, on which every labeller answers Axis B "no" and
        # agreement is near-unanimous for free: a ceiling measured on the easy
        # cases, which is the failure this whole stratification exists to
        # avoid, one level in.
        pool = [r for r in _pool_rows() if r["stratum"]]
        picked = labels.sample(pool, 24, seed=3, overlap=8)
        shared = [r for r in picked if r["overlap"]]
        self.assertEqual(len(shared), 8)
        for stratum in labels.STRATA:
            in_set = sum(1 for r in picked if r["stratum"] == stratum)
            in_block = sum(1 for r in shared if r["stratum"] == stratum)
            expected = 8 * in_set / len(picked)
            self.assertLessEqual(
                abs(in_block - expected), 1,
                f"{stratum}: block has {in_block}, set implies {expected:.1f}")

    def test_an_overlap_larger_than_the_set_is_clamped(self):
        pool = [r for r in _pool_rows() if r["stratum"]]
        picked = labels.sample(pool, 6, seed=1, overlap=99)
        self.assertEqual(sum(1 for r in picked if r["overlap"]), len(picked))

    def test_the_gate_the_pool_classifies_against_is_the_profiles_own(self):
        # THE DEFECT. pool()/pool_query() defaulted to relevance.load(), the
        # shared config/relevance.json, while taking a PROFILE as the argument
        # that names the population. A cohort profile carrying its own
        # relevance_json was therefore classified against the repo author's
        # software-engineer gate.
        #
        # classify() tests tier BEFORE match_score, so the consequence is not
        # a near miss: a posting the pipeline is actively surfacing comes back
        # `gate_rejected` if the OTHER gate happens to call it tier 3. That is
        # the one stratum whose entire value is being identified correctly
        # (labels.py:438). Measured on the live corpus 2026-07-29: 59 rows
        # classified `surfaced` under the shared gate against 144 under
        # pursuit's own -- 85 misfiled.
        import relevance

        shared = {"title_include": ["engineer"], "max_tier_to_score": 2}
        cohort = {"title_include": ["analyst"], "max_tier_to_score": 2}
        self.assertNotEqual(relevance.load(cfg=shared),
                            relevance.load(cfg=cohort))

        # A row the cohort gate admits (tier 1) and the shared gate does not
        # (tier 3), carrying a match_score -- i.e. the pipeline surfaced it.
        surfaced_here = {"job_id": "j", "tier": 1, "facts_version": 3,
                         "match_score": 70}
        rejected_there = dict(surfaced_here, tier=3)
        self.assertEqual(labels.classify(surfaced_here, 2), "surfaced")
        self.assertEqual(labels.classify(rejected_there, 2), "gate_rejected")

    def test_pool_query_will_not_silently_answer_for_the_wrong_gate(self):
        # The fix is not "pass the right cfg at the one call site" -- it is
        # that there is no longer a default that can be wrong. A keyword with
        # a plausible fallback re-arms itself the first time someone adds a
        # second caller.
        import inspect
        sig = inspect.signature(labels.pool_query)
        self.assertIs(sig.parameters["cfg"].default,
                      inspect.Parameter.empty,
                      "pool_query must not default its gate")
        # Walk the BODY, not the source text: the docstring names the old
        # default in order to explain why it is gone, so a grep over the whole
        # function fails on its own explanation. Same AST idiom the suite uses
        # to check score_job()'s purity -- it does not rely on a promise.
        import ast, textwrap
        tree = ast.parse(textwrap.dedent(inspect.getsource(labels.pool_query)))
        fn = tree.body[0]
        calls = [ast.unparse(n) for n in ast.walk(ast.Module(fn.body[1:], []))
                 if isinstance(n, ast.Call)]
        self.assertNotIn("relevance.load()", calls)
        self.assertIn("relevance.tier_sql(cfg, 'j')", calls)

    def test_sample_has_no_second_knob_for_the_gate_boundary(self):
        # sample() carried max_tier=2 and never referenced it. A parameter
        # that reads as a gate control but controls nothing is worse than
        # absent: classification happens in classify(), which is the only
        # place that has a tier.
        import inspect
        self.assertNotIn("max_tier", inspect.signature(labels.sample).parameters)

    def test_confirm_scores_evicts_a_row_match_py_had_not_caught_up_with(self):
        # "No job_matches row" has two causes and SQL cannot tell them apart.
        # score_job() is pure, so the ambiguity can be removed rather than
        # documented -- a recall figure over a stratum contaminated with rows
        # the scheduler simply had not reached would measure the scheduler.
        import schema
        rows = [{"job_id": "x", "stratum": "below_floor"},
                {"job_id": "y", "stratum": "surfaced"}]
        kept, promoted = labels.confirm_scores(
            rows, criteria={"base": schema.MATCH_FLOOR + 10})
        self.assertEqual([r["job_id"] for r in promoted], ["x"])
        self.assertEqual([r["job_id"] for r in kept], ["y"])

        rows = [{"job_id": "x", "stratum": "below_floor"}]
        kept, promoted = labels.confirm_scores(rows, criteria={"base": 0})
        self.assertEqual(promoted, [])
        self.assertEqual(kept[0]["computed_score"], 0)


# --------------------------------------------------------------------------
# The ceiling, and the floor it is not
# --------------------------------------------------------------------------

class TestAgreement(unittest.TestCase):

    def test_inter_annotator_is_between_people(self):
        rows = [
            _label("j1", "ai_involvement", "uses_ai_tools", "alice"),
            _label("j1", "ai_involvement", "uses_ai_tools", "bob"),
            _label("j2", "ai_involvement", "none", "alice"),
            _label("j2", "ai_involvement", "uses_ai_tools", "bob"),
        ]
        out = labels.inter_annotator(rows, KINDS)
        cell = out["fields"]["ai_involvement"]
        self.assertEqual(cell["n"], 2)
        self.assertAlmostEqual(cell["agree2"], 0.5)
        self.assertEqual(out["labellers"], ["alice", "bob"])

    def test_one_labeller_yields_no_ceiling_and_says_so(self):
        rows = [_label("j1", "seniority_level", "mid", "alice")]
        out = labels.inter_annotator(rows, KINDS)
        self.assertNotIn("seniority_level", out["fields"])
        self.assertEqual(out["single_labeller_items"]["seniority_level"], 1)

    def test_abstentions_are_excluded_and_counted_never_folded_in(self):
        # Two people who both gave up have not agreed about anything.
        rows = [
            _label("j1", "seniority_level", None, "alice"),
            _label("j1", "seniority_level", None, "bob"),
            _label("j2", "seniority_level", "mid", "alice"),
            _label("j2", "seniority_level", "mid", "bob"),
        ]
        out = labels.inter_annotator(rows, KINDS)
        self.assertEqual(out["fields"]["seniority_level"]["n"], 1)
        self.assertEqual(out["fields"]["seniority_level"]["agree2"], 1.0)
        self.assertEqual(out["abstained"]["seniority_level"], 2)

    def test_intra_annotator_needs_two_rounds_from_the_same_person(self):
        rows = [
            _label("j1", "seniority_level", "mid", "alice", round_no=1),
            _label("j1", "seniority_level", "senior", "alice", round_no=2),
            _label("j1", "seniority_level", "mid", "bob", round_no=1),
        ]
        out = labels.intra_annotator(rows, KINDS)
        self.assertEqual(out["fields"]["seniority_level"]["n"], 1)
        self.assertEqual(out["fields"]["seniority_level"]["agree2"], 0.0)

    def test_the_two_ceilings_are_different_quantities(self):
        # Alice is perfectly self-consistent and disagrees with everyone. That
        # is a problem with the FORM, not with the labellers, and only having
        # both numbers tells the two cases apart.
        rows = []
        for job in ("j1", "j2", "j3"):
            rows += [
                _label(job, "role_archetype", "backend", "alice", round_no=1),
                _label(job, "role_archetype", "backend", "alice", round_no=2),
                _label(job, "role_archetype", "data", "bob", round_no=1),
            ]
        self.assertEqual(
            labels.intra_annotator(rows, KINDS)["fields"]["role_archetype"]["agree2"],
            1.0)
        self.assertEqual(
            labels.inter_annotator(rows, KINDS)["fields"]["role_archetype"]["agree2"],
            0.0)

    def test_a_tie_is_not_broken_into_a_consensus(self):
        rows = [
            _label("j1", "remote_policy", "hybrid", "alice"),
            _label("j1", "remote_policy", "onsite", "bob"),
            _label("j2", "remote_policy", "hybrid", "alice"),
            _label("j2", "remote_policy", "hybrid", "bob"),
            _label("j2", "remote_policy", "onsite", "carol"),
        ]
        agreed, tied = labels.consensus(rows)
        self.assertEqual(agreed, {("j2", "remote_policy"): "hybrid"})
        self.assertEqual(tied, [("j1", "remote_policy")])

    def test_model_vs_human_reports_the_ties_it_dropped(self):
        rows = [
            _label("j1", "remote_policy", "hybrid", "alice"),
            _label("j1", "remote_policy", "onsite", "bob"),
            _label("j2", "remote_policy", "hybrid", "alice"),
            _label("j2", "remote_policy", "hybrid", "bob"),
        ]
        out = labels.model_vs_human(
            rows, {"j1": {"remote_policy": "hybrid"},
                   "j2": {"remote_policy": "onsite"}}, KINDS)
        self.assertEqual(out["vs_consensus"]["remote_policy"]["n"], 1)
        self.assertEqual(out["vs_consensus"]["remote_policy"]["rate"], 0.0)
        self.assertEqual(out["no_consensus"], 1)
        # vs_each uses every labeller and needs no consensus rule, so the tied
        # item is still evidence there: 4 comparisons, one of them a match.
        self.assertEqual(out["vs_each"]["remote_policy"]["n"], 4)
        self.assertEqual(out["vs_each"]["remote_policy"]["k"], 1)

    def test_axis_b_has_no_model_to_be_compared_against(self):
        # CLAUDE.md: LLMs explain, never rank. "Would you apply" has no model
        # prediction and inventing one would put an LLM between a user and an
        # ordering.
        rows = [_label("j1", labels.AXIS_B_FIELD, "yes", "alice",
                       axis=labels.AXIS_B, profile="pursuit")]
        with self.assertRaises(ValueError):
            labels.model_vs_human(rows, {}, KINDS, axis=labels.AXIS_B)

    def test_axis_b_agreement_is_keyed_by_profile_not_pooled_across_them(self):
        rows = [
            _label("j1", "would_apply", "yes", "alice", axis=labels.AXIS_B,
                   profile="pursuit"),
            _label("j1", "would_apply", "no", "bob", axis=labels.AXIS_B,
                   profile="tech"),
        ]
        out = labels.inter_annotator(rows, {"would_apply": "enum"},
                                     axis=labels.AXIS_B)
        # Two different personas answering about the same posting is not a
        # disagreement. Pooling them would report one.
        self.assertNotIn("would_apply", out["fields"])
        self.assertEqual(out["single_labeller_items"]["would_apply"], 2)


# --------------------------------------------------------------------------
# Broken out by source platform -- 29:106, for the reason at 29:87-89
# --------------------------------------------------------------------------

def _agreeing(job, platform, *, agree=True, field="ai_involvement"):
    """One item two people labelled, agreeing or not."""
    other = "uses_ai_tools" if agree else "none"
    return [_label(job, field, "uses_ai_tools", "alice", platform=platform),
            _label(job, field, other, "bob", platform=platform)]


class TestThePerPlatformBreakout(unittest.TestCase):
    """Task 29:106 asks for the three quantities per field per platform.

    29:87-89 says why: task 06's reconciliation predicts extraction degrades
    on messy sources and Phase 3 just added several, so a blended number
    would hide exactly that effect.
    """

    def _rows(self):
        rows = []
        for i in range(4):
            rows += _agreeing(f"gh{i}", "greenhouse", agree=i < 3)
        for i in range(2):
            rows += _agreeing(f"hn{i}", "hn_whoishiring", agree=False)
        return rows

    def test_the_blended_number_is_still_the_headline(self):
        # The breakout is a diagnostic BESIDE the blended figure, never a
        # replacement -- 29:87-89 asks for the split, not for the average to
        # be dropped. `fields` must keep meaning what it meant.
        out = labels.inter_annotator(self._rows(), KINDS)
        cell = out["fields"]["ai_involvement"]
        self.assertEqual(cell["n"], 6)
        self.assertAlmostEqual(cell["agree2"], 3 / 6)

    def test_a_cell_is_metrics_field_cell_and_not_new_arithmetic(self):
        # labels.py's inter_annotator docstring: reusing field_cell() is what
        # makes agree2 mean the same thing here as it does in the
        # self-consistency table. A second implementation would make the
        # floor and the ceiling two statistics that merely look alike.
        out = labels.inter_annotator(self._rows(), KINDS)
        cell = out["by_platform"]["fields"]["ai_involvement"]["greenhouse"]
        expected = metrics.field_cell("enum", [
            ("uses_ai_tools", "uses_ai_tools")] * 3
            + [("none", "uses_ai_tools")])
        self.assertEqual(cell, expected)

    def test_every_breakout_cell_carries_its_n(self):
        # A bare percentage over n=3 reads exactly like one over n=300.
        # CLAUDE.md: "n=17 is not a result."
        out = labels.inter_annotator(self._rows(), KINDS)
        block = out["by_platform"]["fields"]["ai_involvement"]
        self.assertEqual(block["greenhouse"]["n"], 4)
        self.assertEqual(block["hn_whoishiring"]["n"], 2)
        self.assertEqual(out["by_platform"]["platform_counts"],
                         {"greenhouse": 4, "hn_whoishiring": 2})

    def test_a_thin_cell_is_distinguishable_from_a_thick_one(self):
        # The test is on the INTERVAL, not on n, and that is the point: 5/10
        # and 10/10 are the same n and only one of them says anything.
        self.assertTrue(labels.is_thin(metrics.field_cell(
            "enum", [("a", "a")] * 3)))
        self.assertFalse(labels.is_thin(metrics.field_cell(
            "enum", [("a", "a")] * 300)))
        self.assertTrue(labels.is_thin(metrics.field_cell(
            "enum", [("a", "a")] * 5 + [("a", "b")] * 5)))
        self.assertTrue(labels.is_thin({}), "an absent cell is not a rate")
        self.assertTrue(labels.is_thin({"n": 0, "agree2": None}))

    def test_the_clean_messy_axis_is_metrics_own_and_not_a_second_one(self):
        # metrics.CLEAN_PLATFORMS, reused. A second definition here would
        # make the floor's clean/messy columns and the ceiling's
        # non-comparable, which is the same failure reusing field_cell()
        # exists to prevent.
        out = labels.inter_annotator(self._rows(), KINDS)
        block = out["by_platform"]
        self.assertEqual(block["clean"]["ai_involvement"]["n"], 4)
        self.assertEqual(block["messy"]["ai_involvement"]["n"], 2)
        self.assertIn("greenhouse", metrics.CLEAN_PLATFORMS)
        self.assertNotIn("hn_whoishiring", metrics.CLEAN_PLATFORMS)

    def test_an_unrecorded_platform_is_unknown_and_pools_into_messy(self):
        # metrics.selfcheck() calls it `unknown` too (metrics.py:406), and it
        # counts as messy there. A posting whose source was not recorded is
        # not evidence of a clean one.
        rows = _agreeing("j1", None) + _agreeing("j2", None, agree=False)
        block = labels.inter_annotator(rows, KINDS)["by_platform"]
        self.assertEqual(
            set(block["fields"]["ai_involvement"]), {labels.UNKNOWN_PLATFORM})
        self.assertEqual(block["messy"]["ai_involvement"]["n"], 2)
        self.assertEqual(block["clean"]["ai_involvement"]["n"], 0)

    def test_the_platform_rides_on_the_row_and_a_map_overrides_it(self):
        # fetch() carries it (labels._FETCH_COLUMNS), so the normal path needs
        # no argument at all. `platforms` is for a caller holding a set file
        # rather than a database.
        rows = _agreeing("j1", "greenhouse")
        self.assertEqual(labels.platform_index(rows), {"j1": "greenhouse"})
        self.assertEqual(labels.platform_index(rows, {"j1": "lever"}),
                         {"j1": "lever"})
        block = labels.inter_annotator(
            rows, KINDS, platforms={"j1": "lever"})["by_platform"]
        self.assertEqual(list(block["fields"]["ai_involvement"]), ["lever"])

    def test_model_vs_human_breaks_out_the_consensus_column_only(self):
        # vs_each's pairs come from the same item and are not independent
        # (metrics.py:30), so it carries no interval even blended. Splitting a
        # number that cannot have an interval into single-digit cells would
        # produce the most quotable and least supportable figures here.
        rows = self._rows()
        out = labels.model_vs_human(
            rows, {r["job_id"]: {"ai_involvement": "uses_ai_tools"}
                   for r in rows}, KINDS)
        block = out["by_platform"]["fields"]["ai_involvement"]
        self.assertEqual(set(block), {"greenhouse"})
        self.assertEqual(block["greenhouse"]["n"], 3)
        self.assertEqual(block["greenhouse"]["rate"], 1.0)
        # hn_whoishiring's two items were both ties, and a tie is not broken.
        self.assertEqual(out["no_consensus"], 3)

    def test_a_measured_cell_keeps_the_measured_shape_not_field_cell_s(self):
        # A per-platform cell has to mean what the column it sits under
        # means. Building this one from field_cell() would silently swap
        # `rate` (model vs the majority human answer) for `agree2` (two
        # answers about the same item) and the table would still print.
        rows = _agreeing("gh0", "greenhouse")
        out = labels.model_vs_human(
            rows, {"gh0": {"ai_involvement": "none"}}, KINDS)
        cell = out["by_platform"]["fields"]["ai_involvement"]["greenhouse"]
        self.assertEqual(set(cell), {"kind", "n", "k", "rate", "ci"})
        self.assertEqual(cell, out["vs_consensus"]["ai_involvement"])

    def test_intra_annotator_computes_the_breakout_it_does_not_print(self):
        # The original design is 5-10 jobs labelled twice, so a per-platform
        # cell here is n=1. It is in the dict because a JSON consumer can
        # pool it across sessions; it is off the page because a table of
        # single-item cells is noise.
        rows = [
            _label("j1", "seniority_level", "mid", "alice", round_no=1,
                   platform="greenhouse"),
            _label("j1", "seniority_level", "mid", "alice", round_no=2,
                   platform="greenhouse"),
        ]
        out = labels.intra_annotator(rows, KINDS)
        self.assertEqual(
            out["by_platform"]["fields"]["seniority_level"]["greenhouse"]["n"],
            1)
        text = report.render_labels(
            [], inter={"labellers": [], "single_labeller_items": {},
                       "abstained": {}},
            intra=out,
            measured={"vs_consensus": {}, "vs_each": {}, "no_consensus": 0,
                      "no_model_output": []})
        self.assertNotIn("greenhouse", text)


class TestTheBreakoutIsRenderedBesideTheBlendedNumber(unittest.TestCase):

    #: Task 06's real figures, intervals included: 92.2% [85-96] on the clean
    #: ATS end against 77.8% [55-91] on everything else. That 14-point gap is
    #: the effect 29:87-89 predicts and the reason this breakout exists.
    FLOOR = {"ai_involvement": {
        "overall": _cell(115, 0.907, (0.84, 0.95)),
        "by_platform": {"greenhouse": _cell(98, 0.922, (0.85, 0.96))},
        "clean": _cell(98, 0.922, (0.85, 0.96)),
        "messy": _cell(17, 0.778, (0.55, 0.91))}}

    def _report(self):
        rows = []
        for i in range(4):
            rows += _agreeing(f"gh{i}", "greenhouse", agree=i < 3)
        rows += _agreeing("hn0", "hn_whoishiring")
        model = {r["job_id"]: {"ai_involvement": "uses_ai_tools"}
                 for r in rows}
        inter = labels.inter_annotator(rows, KINDS)
        measured = labels.model_vs_human(rows, model, KINDS)
        triples = labels.interpretable(floor=self.FLOOR,
                                       ceiling=inter["fields"],
                                       measured=measured["vs_consensus"])
        return report.render_labels(
            triples, inter=inter,
            intra=labels.intra_annotator(rows, KINDS), measured=measured)

    def test_the_floor_s_own_platform_cells_come_free_from_the_selfcheck(self):
        # metrics.selfcheck() already stores by_platform/clean/messy beside
        # `overall` (metrics.py:419-429), so the floor column of the breakout
        # cost interpretable() no new argument.
        triples = labels.interpretable(
            floor=self.FLOOR,
            ceiling={"ai_involvement": _cell(6, 0.5)},
            measured={"ai_involvement": {"n": 6, "k": 5, "rate": 0.83,
                                         "ci": (0.4, 0.97)}})
        self.assertEqual(triples[0].floor, _cell(115, 0.907, (0.84, 0.95)))
        self.assertEqual(triples[0].floor_by_platform["fields"],
                         {"greenhouse": _cell(98, 0.922, (0.85, 0.96))})
        self.assertEqual(triples[0].floor_by_platform["messy"],
                         _cell(17, 0.778, (0.55, 0.91)))

    def test_the_table_prints_a_row_per_platform_under_the_blended_row(self):
        text = self._report()
        self.assertIn("per platform", text)
        self.assertIn("greenhouse", text)
        self.assertIn("hn_whoishiring", text)
        # The blended row is still there and still first.
        self.assertLess(text.index("ceiling = two different people"),
                        text.index("per platform"))

    def test_a_small_cell_is_marked_and_a_large_one_is_not(self):
        # This is the property that stops n=2 being quoted as a rate. The
        # floor cell over 98 records prints bare; every cell over the handful
        # of labels this set holds prints with `~`.
        text = self._report()
        self.assertIn("~", text)
        self.assertIn("n=98", text)
        self.assertIn("n=1", text)
        for line in text.splitlines():
            if "n=98" in line:
                self.assertNotIn("~  92%", line)

    def test_a_platform_missing_a_floor_or_a_ceiling_is_flagged(self):
        # Not suppressed: the selfcheck corpus and the label set are
        # different samples and need not cover the same sources. A model
        # number with nothing to be read between is a diagnostic, and the
        # reader has to be able to see that it is.
        text = self._report()
        flagged = [ln for ln in text.splitlines()
                   if ln.strip().startswith("! hn_whoishiring")]
        self.assertEqual(len(flagged), 1, text)

    def test_the_pooled_clean_messy_row_is_the_one_with_any_n(self):
        text = self._report()
        self.assertIn("clean (gh+ashby)", text)
        self.assertIn("messy (all others)", text)

    def test_a_set_with_no_platforms_says_so_rather_than_printing_blanks(self):
        rows = _agreeing("j1", None) + _agreeing("j2", None, agree=False)
        model = {"j1": {"ai_involvement": "uses_ai_tools"},
                 "j2": {"ai_involvement": "uses_ai_tools"}}
        inter = labels.inter_annotator(rows, KINDS)
        measured = labels.model_vs_human(rows, model, KINDS)
        # Every item still has a platform -- `unknown` -- so the table prints
        # it rather than claiming nothing is there. What must never happen is
        # a silent empty block.
        text = report.render_labels(
            labels.interpretable(floor={"ai_involvement": {
                                     "overall": _cell(115, 0.907)}},
                                 ceiling=inter["fields"],
                                 measured=measured["vs_consensus"]),
            inter=inter, intra=labels.intra_annotator(rows, KINDS),
            measured=measured)
        self.assertIn(labels.UNKNOWN_PLATFORM, text)

    def test_the_breakout_opens_no_route_around_the_refusal(self):
        # Interpretable still requires all three blended quantities. A field
        # with a rich per-platform floor and no measured figure raises, so
        # nothing can reach the per-platform table that the gate rejected.
        with self.assertRaises(labels.Uninterpretable):
            labels.interpretable(floor=self.FLOOR,
                                 ceiling={"ai_involvement": _cell(6, 0.5)},
                                 measured={"ai_involvement": {"n": 0}})
        with self.assertRaises(labels.Uninterpretable):
            labels.interpretable(floor=self.FLOOR, ceiling={},
                                 measured={"ai_involvement": {
                                     "n": 6, "k": 5, "rate": 0.83,
                                     "ci": (0.4, 0.97)}})


# --------------------------------------------------------------------------
# The gate: three quantities or nothing
# --------------------------------------------------------------------------

class TestThreeQuantities(unittest.TestCase):

    FLOOR = {"ai_involvement": {"overall": _cell(115, 0.907)}}
    CEILING = {"ai_involvement": _cell(20, 0.85)}
    MEASURED = {"ai_involvement": {"n": 20, "k": 17, "rate": 0.85,
                                   "ci": (0.6, 0.96)}}

    def test_all_three_present_builds(self):
        out = labels.interpretable(floor=self.FLOOR, ceiling=self.CEILING,
                                   measured=self.MEASURED)
        self.assertEqual([t.field for t in out], ["ai_involvement"])

    def test_no_floor_refuses(self):
        with self.assertRaises(labels.Uninterpretable) as ctx:
            labels.interpretable(floor={}, ceiling=self.CEILING,
                                 measured=self.MEASURED)
        self.assertIn("floor", str(ctx.exception))
        self.assertIn("selfcheck", str(ctx.exception))

    def test_no_ceiling_refuses(self):
        with self.assertRaises(labels.Uninterpretable) as ctx:
            labels.interpretable(floor=self.FLOOR, ceiling={},
                                 measured=self.MEASURED)
        self.assertIn("ceiling", str(ctx.exception))
        self.assertIn("overlap", str(ctx.exception))

    def test_an_empty_cell_is_as_absent_as_a_missing_one(self):
        # A field measured on zero records is not a measurement, and a cell of
        # n=0 must not slip past the gate just because the key exists.
        with self.assertRaises(labels.Uninterpretable):
            labels.interpretable(floor=self.FLOOR,
                                 ceiling={"ai_involvement": _cell(0, None)},
                                 measured=self.MEASURED)

    def test_a_field_with_a_partial_triple_is_refused_not_dropped(self):
        # Silently omitting the row would be its own quiet lie about what was
        # measured.
        floor = dict(self.FLOOR)
        floor["seniority_level"] = {"overall": _cell(115, 0.852)}
        measured = dict(self.MEASURED)
        measured["seniority_level"] = {"n": 20, "k": 12, "rate": 0.6,
                                       "ci": (0.4, 0.8)}
        with self.assertRaises(labels.Uninterpretable) as ctx:
            labels.interpretable(floor=floor, ceiling=self.CEILING,
                                 measured=measured)
        self.assertIn("seniority_level", str(ctx.exception))

    def test_the_only_renderer_takes_the_triple(self):
        # There is deliberately no function that prints a model-vs-human rate
        # on its own. This is the enforcement, checked rather than asserted in
        # prose: render_labels is the only public name in report.py that
        # mentions labels at all.
        label_renderers = [n for n in dir(report)
                           if not n.startswith("_") and "label" in n.lower()]
        self.assertEqual(label_renderers, ["render_labels"])

    def test_the_table_names_the_floor_and_the_ceiling_beside_the_number(self):
        triples = labels.interpretable(floor=self.FLOOR, ceiling=self.CEILING,
                                       measured=self.MEASURED)
        text = report.render_labels(
            triples,
            inter={"labellers": ["alice", "bob"], "single_labeller_items": {},
                   "abstained": {"ai_involvement": 3}},
            intra={"fields": {}},
            measured={"vs_consensus": self.MEASURED,
                      "vs_each": {"ai_involvement": {"n": 40, "k": 34,
                                                     "rate": 0.85}},
                      "no_consensus": 2, "no_model_output": []})
        self.assertIn("floor", text)
        self.assertIn("ceiling", text)
        self.assertIn("91%", text)          # the floor, from task 06
        self.assertIn("abstentions", text)
        self.assertIn("no majority", text)


# --------------------------------------------------------------------------
# Nothing here can produce a label
# --------------------------------------------------------------------------

class TestNoLabelIsEverGenerated(unittest.TestCase):

    def test_no_module_in_the_package_calls_a_model_to_label(self):
        path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "evals", "labels.py")
        with open(path, encoding="utf-8") as fh:
            source = fh.read()
        for forbidden in ("llm.call", "call_detailed", "import llm"):
            self.assertNotIn(forbidden, source,
                             "labels.py must have no path from a model's "
                             "output into eval_labels -- that is exactly the "
                             "defect claude-bench.py:417 has")

    def test_record_refuses_to_mix_the_axes(self):
        class _Conn:
            def execute(self, *a, **k):
                raise AssertionError("must not reach the database")

        with self.assertRaises(ValueError):
            labels.record(_Conn(), axis=labels.AXIS_A, job_id="j",
                          field="seniority_level", value="mid",
                          labeller_id="alice", profile="pursuit")
        with self.assertRaises(ValueError):
            labels.record(_Conn(), axis=labels.AXIS_B, job_id="j",
                          field="would_apply", value="yes",
                          labeller_id="alice")
        with self.assertRaises(ValueError):
            labels.record(_Conn(), axis=labels.AXIS_A, job_id="j",
                          field="seniority_level", value="Mid-Level",
                          labeller_id="alice")


_BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _code_only(path):
    """A module's source with docstrings and comments removed.

    ast.unparse() never emits `#` comments -- they are not in the tree -- and
    dropping the leading string Expr of every module, class and function
    removes the docstrings. What is left is code, which is the only thing a
    "this module never queries X" assertion should be reading.

    Grepping the raw file would be wrong in both directions here:
    webapp/label.py's docstrings legitimately DISCUSS `job_facts` and
    `jobs_app` while querying neither, so a raw grep both fails on prose and
    would tempt the next person to reword a comment to make a test pass.
    """
    with open(path, encoding="utf-8") as fh:
        tree = ast.parse(fh.read())
    for node in ast.walk(tree):
        body = getattr(node, "body", None)
        if not isinstance(body, list) or not body:
            continue
        if not isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef,
                                 ast.AsyncFunctionDef)):
            continue
        first = body[0]
        if (isinstance(first, ast.Expr)
                and isinstance(first.value, ast.Constant)
                and isinstance(first.value.value, str)):
            body.pop(0)
    return ast.unparse(tree)


def _module_constant(path, name):
    """One module-level literal, without importing the module.

    webapp/ imports fastapi, which is not installed in this environment (five
    modules there have always failed to import). The property below is too
    load-bearing to be pinned only in a suite that cannot run, so it is read
    out of the AST instead -- the same device
    test_no_module_in_the_package_calls_a_model_to_label uses one class down.
    """
    with open(path, encoding="utf-8") as fh:
        tree = ast.parse(fh.read())
    for node in tree.body:
        targets = ([node.target] if isinstance(node, ast.AnnAssign)
                   else getattr(node, "targets", []))
        for target in targets:
            if isinstance(target, ast.Name) and target.id == name:
                return ast.literal_eval(node.value)
    raise AssertionError(f"{path} has no module-level {name}")


class TestTheLabellerIsBlindToTheModelsAnswer(unittest.TestCase):
    """29:105 -- "Labellers were blind to `fit_score`".

    29:72-73 calls seeing it "the single easiest way to invalidate the whole
    exercise", because a human shown the model's number first collapses their
    judgement onto it. The property holds by construction in webapp/label.py
    and, until this class, nothing asserted it.

    IT IS PINNED HERE AND NOT ONLY BESIDE THE MODULE IT GUARDS. There is a
    matching class in webapp/tests/test_label_form.py, which is the natural
    home -- but `fastapi` is not installed in this environment, so that suite
    cannot run at all and never has. A property this load-bearing needs an
    assertion that actually executes. These read the source rather than
    import it, which is what makes that possible.
    """

    PATH = os.path.join(_BACKEND, "webapp", "label.py")

    #: Everything that would leak the pipeline's own opinion of a posting: the
    #: score tables, their columns, and the schema constants that name them.
    #: `job_facts` is on the list too, and not only `job_scores`: showing a
    #: labeller the model's extracted `seniority_level` would anchor axis A
    #: exactly as showing fit_score anchors axis B, and axis A is the half of
    #: this exercise that outlives the cohort (29:29).
    FORBIDDEN = ("fit_score", "match_score", "job_scores", "job_matches",
                 "job_facts", "SCORES_TABLE", "MATCHES_TABLE", "FACTS_TABLE",
                 "jobs_app",
                 # `jobs` itself carries a machine verdict on question 2 of the
                 # form: `seniority_guess` is text.guess_seniority(title),
                 # written at ingest by four ingest modules, and the form asks
                 # "What seniority does the posting actually ask for?". It is
                 # not a "score" by name, so nothing else here excludes it, and
                 # `_DETAIL_COLUMNS` only bounds _job() -- a SECOND query
                 # against `jobs` could reach it. Named because the tables
                 # assertion below allows `jobs` and therefore cannot.
                 "seniority_guess")

    def test_the_form_reads_six_columns_of_jobs_and_none_is_a_score(self):
        # label.py:78. _job() (label.py:112-128) selects exactly these and
        # nothing else, so what the page can render is bounded by this tuple.
        columns = _module_constant(self.PATH, "_DETAIL_COLUMNS")
        self.assertEqual(columns, ("id", "title", "company_name",
                                   "location_raw", "platform",
                                   "description_text"))
        for column in columns:
            self.assertNotIn("score", column)

    def test_no_score_table_is_reachable_from_the_module_at_all(self):
        # Not "the form does not display it" -- the module never asks for it.
        # A future _job() that widened its SELECT would fail here before
        # anybody had to notice a number on the page.
        code = _code_only(self.PATH)
        for name in self.FORBIDDEN:
            self.assertNotIn(name, code,
                             f"webapp/label.py must not reach {name}. "
                             f"29:105 requires labellers blind to the "
                             f"model's answer, and 29:72-73 calls breaking "
                             f"that the single easiest way to invalidate "
                             f"the whole exercise")

    def test_the_only_tables_named_are_the_corpus_and_the_eval_set(self):
        # The positive half of the same claim, so the test above cannot be
        # satisfied by renaming things. `jobs` for the posting,
        # eval_label_items for set membership, and nothing else.
        code = _code_only(self.PATH)
        self.assertIn("FROM jobs WHERE id = %s", code)
        self.assertIn("FROM eval_label_items", code)
        # AMENDED 2026-07-30: this counted FROM clauses and expected 2. The
        # count was a PROXY for the real rule -- "the route reaches no table
        # that could show a labeller more" -- and the proxy broke when round 2
        # added two WRITE-SIDE preconditions: is this an overlap row, and which
        # fields did this person answer in round 1. Neither renders anything;
        # both gate what may be stored. So assert the rule instead of the
        # proxy, which is stricter in the direction that matters: FORBIDDEN is
        # checked against the whole module by the two tests above, and here we
        # pin the exact set of tables named.
        # WHAT THIS TRADE COSTS, STATED SO IT IS NOT DISCOVERED LATER. The
        # count fired on ANY new query; the set fires only on a new TABLE. So a
        # second query against a table already listed here no longer trips it.
        # Taken deliberately: a count that must be bumped by hand on every edit
        # teaches the next person to bump it without reading it, which is a
        # worse guard than one that fires only on the risky class. The risky
        # class is a new data source, and FORBIDDEN (checked against the whole
        # module by the two tests above) is what actually bounds it.
        # A JOIN adds no FROM token, so it would reach a table without ever
        # entering `found` -- scanned separately rather than claimed by the
        # consistency check below, which cannot see it. (The previous message
        # here said the check caught JOINs. It does not, and neither did the
        # FROM-count it replaced.)
        found = re.findall(r"FROM\s+(\w+)", code) + \
            re.findall(r"JOIN\s+(\w+)", code)
        self.assertEqual(len(found),
                         code.count("FROM") + code.count("JOIN"),
                         "every FROM and JOIN must yield a bare table name -- a "
                         "subquery or an interpolated table name yields none "
                         "and would slip past the set assertion below, so fail "
                         "loudly instead")
        # `eval_labels` is deliberately NOT here. The round-2 path needs to know
        # which fields this labeller already answered, and that query lives in
        # labels.round_one_answers() -- the module that owns the table -- rather
        # than as a second copy in the route. Same ownership rule labels.py's
        # TABLES comment states, and the reason it gives: three tables' DDL once
        # lived in two places and had drifted six ways by the time anyone
        # measured.
        self.assertEqual(set(found), {"jobs", "eval_label_items"},
                         "the route may read the corpus row it renders and the "
                         "eval set it belongs to. A third table is a change to "
                         "what a labeller can be shown -- and anything about "
                         "labels themselves belongs in labels.py.")

    def test_the_stratum_is_never_handed_to_the_renderer(self):
        # A stratum name is the pipeline's verdict in one word: "surfaced"
        # tells a labeller the ranker already liked this posting, and
        # "gate_rejected" tells them it never made it in. next_item() returns
        # it (labels.py:750) and the route deliberately does not pass it on.
        with open(self.PATH, encoding="utf-8") as fh:
            tree = ast.parse(fh.read())
        renderer = [n for n in ast.walk(tree)
                    if isinstance(n, ast.FunctionDef)
                    and n.name == "_render_form"]
        self.assertEqual(len(renderer), 1)
        args = [a.arg for a in renderer[0].args.args]
        self.assertNotIn("stratum", args)
        # `round_no` was added when the round-2 path landed and IS admissible
        # on this list, which is worth stating because the list is otherwise an
        # allowlist and a future reader will wonder. The rule the list encodes
        # is "nothing that tells the labeller what the PIPELINE thinks of this
        # posting". `overlap` says only that other people also see it;
        # `round_no` says only that this person saw it before; `blank` says only
        # that their last submit recorded nothing. None of the three carries a
        # verdict. `stratum` does, which is why it stays off.
        self.assertEqual(args, ["job", "question_list", "label_set", "done",
                                "total", "overlap", "round_no", "blank"])
        self.assertNotIn("stratum", _code_only(self.PATH))


class TestGrantsAreDeclaredOnce(unittest.TestCase):

    def test_web_privileges_cover_every_table_the_ddl_creates(self):
        self.assertEqual(set(labels.WEB_PRIVILEGES), set(labels.TABLES))

    def test_labels_are_append_only_to_the_service(self):
        # A revised judgement is round 2, never an overwrite. A bug in the web
        # route must not be able to destroy the ceiling measurement.
        self.assertEqual(labels.WEB_PRIVILEGES["eval_labels"],
                         ("SELECT", "INSERT"))
        for table in ("eval_label_sets", "eval_label_items"):
            self.assertEqual(labels.WEB_PRIVILEGES[table], ("SELECT",))

    def test_the_pipeline_table_record_reads_is_declared_and_read_only(self):
        # record() resolves facts_version from job_facts, so the labelling
        # surface reads a table it does not own. Declared separately from
        # WEB_PRIVILEGES so the invariant above stays a true statement about
        # this module's own tables -- and so schema_web's REQUIRED_TABLES.update
        # cannot silently overwrite the entry that file makes for itself.
        self.assertEqual(labels.WEB_READS, {"job_facts": ("SELECT",)})
        self.assertNotIn("job_facts", labels.WEB_PRIVILEGES)
        for needed in labels.WEB_READS.values():
            self.assertEqual(needed, ("SELECT",),
                             "a pipeline-owned table is read here and never "
                             "written -- job_facts belongs to extract.py")

    def test_verify_schema_checks_what_the_module_reads_not_only_what_it_owns(self):
        # The failure this closes: job_facts granted to jobs_web for the job
        # list but not thought about here, then a GRANT tightened, and the
        # first symptom is a 500 on a volunteer's submit rather than a service
        # that refuses to start. Asserted through the default argument because
        # that is what app.py's lifespan actually calls.
        seen = {}

        class _Conn:
            def execute(self, sql, params=None):
                if "to_regclass" in sql:
                    seen.setdefault(params[0], set())
                    return _Row(("public.x",))
                if "has_table_privilege" in sql:
                    seen[params[0]].add(params[1])
                    return _Row((True,))
                return _Row((True,))

        class _Row:
            def __init__(self, value):
                self._value = value

            def fetchone(self):
                return self._value

        labels.verify_schema(_Conn())
        self.assertIn("public.job_facts", seen)
        self.assertEqual(seen["public.job_facts"], {"SELECT"})


class TestProvenanceIsDeclaredInBothPlaces(unittest.TestCase):
    """The 41a shape: a column added on one side of a pair, the other side not
    following, and the failure arriving in production as UndefinedColumn.

    ensure_schema() writes the columns twice on purpose -- the CREATE TABLE
    serves a database that does not exist yet, add_missing_columns serves the
    one that does -- so nothing but a test keeps the two in agreement.
    """

    def _create_table_columns(self):
        """The column names in ensure_schema()'s CREATE TABLE eval_labels.

        Read from the source rather than from a shared constant: a constant
        feeding both sides would make the assertion below a tautology, which
        is the objection webapp/tests/test_grants.py records about its own
        equivalent.
        """
        import re

        with open(labels.__file__, encoding="utf-8") as fh:
            source = fh.read()
        block = re.search(
            r"CREATE TABLE IF NOT EXISTS eval_labels \((.*?)\n        \)",
            source, re.S)
        self.assertIsNotNone(block, "could not find the eval_labels DDL")
        names = []
        for line in block.group(1).splitlines():
            line = line.strip()
            if not line or line.startswith(("CONSTRAINT", "CHECK", "OR ")):
                continue
            names.append(line.split()[0])
        return names

    #: eval_labels as it shipped. Anything the DDL names beyond this list is a
    #: column added later, and every one of those has to be in
    #: PROVENANCE_COLUMNS or the live database never gets it.
    AS_SHIPPED = ("id", "axis", "label_set", "job_id", "field", "value",
                  "profile", "labeller_id", "round_no", "labelled_at", "note")

    def test_every_column_added_after_ship_is_also_in_the_migration(self):
        added = [c for c in self._create_table_columns()
                 if c not in self.AS_SHIPPED]
        self.assertEqual(added, [name for name, _type in
                                 labels.PROVENANCE_COLUMNS],
                         "a column in the CREATE TABLE and not in "
                         "PROVENANCE_COLUMNS reaches a fresh database and "
                         "never reaches the live one")

    def test_the_ddl_still_names_every_column_that_shipped(self):
        # The other direction, and the cheaper mistake: editing the DDL and
        # dropping a column that live rows already carry.
        for column in self.AS_SHIPPED:
            self.assertIn(column, self._create_table_columns())

    def test_the_absent_state_is_a_boolean_and_never_a_sentinel_version(self):
        # The whole argument for two columns. A sentinel 0 or -1 would make
        # "this posting had no extraction" indistinguishable from a real
        # version in exactly the query the column exists to answer, and it is
        # what task 11's normalize() stopped doing.
        types = dict(labels.PROVENANCE_COLUMNS)
        self.assertEqual(types["facts_version"], "INTEGER",
                         "no DEFAULT: a row whose posting has no facts must "
                         "be NULL, not a number")
        self.assertIn("NOT NULL DEFAULT FALSE", types["facts_version_known"],
                      "every pre-existing row must read FALSE without a "
                      "backfill -- that is what makes the migration honest")

    def test_record_names_both_columns(self):
        # The INSERT is the only writer. If it stops naming them, the default
        # takes over and every new row reads as unrecorded -- silently, which
        # is this system's failure mode.
        import inspect

        source = inspect.getsource(labels.record)
        for name, _type in labels.PROVENANCE_COLUMNS:
            self.assertIn(name, source)


# --------------------------------------------------------------------------
# Against a real Postgres: the constraints, which a fake connection cannot test
# --------------------------------------------------------------------------

@unittest.skipUnless(scratchdb.available(),
                     "no reachable Postgres for a scratch schema")
class TestSchemaAgainstPostgres(unittest.TestCase):
    """The two axes are two partial unique indexes and two CHECKs.

    Every assertion below is about behaviour only a server has: a fake
    connection accepts each of these inserts whether or not the constraint
    exists, so it would pass a schema with none of them.
    """

    def setUp(self):
        self._ctx = scratchdb.scratch_schema()
        self.conn, self.name = self._ctx.__enter__()
        labels.ensure_schema(self.conn)
        self.conn.execute(
            "INSERT INTO eval_label_sets (label_set, created_at, seed, n, "
            "profile, job_id_sha256) VALUES ('s', '2026-07-28T00:00:00', 0, "
            "1, 'pursuit', 'deadbeef')")
        self.conn.commit()

    def tearDown(self):
        self._ctx.__exit__(None, None, None)

    def _rollback(self):
        self.conn.rollback()

    def test_axis_a_may_not_carry_a_profile(self):
        import psycopg
        with self.assertRaises(psycopg.errors.CheckViolation):
            self.conn.execute(
                "INSERT INTO eval_labels (axis, job_id, field, value, profile,"
                " labeller_id, round_no, labelled_at) VALUES "
                "('A','j','seniority_level','mid','pursuit','alice',1,'t')")
        self._rollback()

    def test_axis_b_must_carry_a_profile(self):
        import psycopg
        with self.assertRaises(psycopg.errors.CheckViolation):
            self.conn.execute(
                "INSERT INTO eval_labels (axis, job_id, field, value, profile,"
                " labeller_id, round_no, labelled_at) VALUES "
                "('B','j','would_apply','yes',NULL,'alice',1,'t')")
        self._rollback()

    def test_axis_a_is_unique_without_a_profile_in_the_key(self):
        # The bug this pins: a single composite UNIQUE over a nullable profile
        # column enforces NOTHING on axis A, because Postgres treats NULLs as
        # distinct. The same person could answer the same question ten times
        # and no constraint would complain.
        labels.record(self.conn, axis="A", job_id="j", field="seniority_level",
                      value="mid", labeller_id="alice", label_set="s")
        wrote = labels.record(self.conn, axis="A", job_id="j",
                              field="seniority_level", value="senior",
                              labeller_id="alice", label_set="s")
        self.conn.commit()
        self.assertFalse(wrote, "a second answer for the same round must not "
                                "silently overwrite or duplicate round 1")
        rows = labels.fetch(self.conn, axis="A")
        self.assertEqual([r["value"] for r in rows], ["mid"])

    def test_a_revision_is_a_second_round_and_both_survive(self):
        labels.record(self.conn, axis="A", job_id="j", field="seniority_level",
                      value="mid", labeller_id="alice", label_set="s")
        labels.record(self.conn, axis="A", job_id="j", field="seniority_level",
                      value="senior", labeller_id="alice", label_set="s",
                      round_no=2)
        self.conn.commit()
        rows = labels.fetch(self.conn, axis="A")
        self.assertEqual([(r["round_no"], r["value"]) for r in rows],
                         [(1, "mid"), (2, "senior")])

    def test_two_people_may_answer_the_same_axis_a_question(self):
        for who in ("alice", "bob"):
            labels.record(self.conn, axis="A", job_id="j",
                          field="ai_involvement", value="uses_ai_tools",
                          labeller_id=who, label_set="s")
        self.conn.commit()
        self.assertEqual(len(labels.fetch(self.conn, axis="A")), 2)

    def test_axis_b_is_keyed_per_profile(self):
        for profile in ("pursuit", "tech"):
            labels.record(self.conn, axis="B", job_id="j", field="would_apply",
                          value="yes", labeller_id="alice", label_set="s",
                          profile=profile)
        self.conn.commit()
        self.assertEqual(len(labels.fetch(self.conn, axis="B")), 2)

    def test_dropping_the_cohort_leaves_axis_a_intact(self):
        # THE DURABILITY CLAIM, checked rather than asserted. Axis B dies when
        # the Pursuit cohort ends; axis A transfers to every future user and
        # every future vertical, and it must survive that DELETE untouched.
        labels.record(self.conn, axis="A", job_id="j", field="ai_involvement",
                      value="uses_ai_tools", labeller_id="alice",
                      label_set="s")
        labels.record(self.conn, axis="B", job_id="j", field="would_apply",
                      value="no", labeller_id="alice", label_set="s",
                      profile="pursuit")
        self.conn.execute("DELETE FROM eval_labels WHERE axis = 'B'")
        self.conn.commit()
        rows = labels.fetch(self.conn)
        self.assertEqual([(r["axis"], r["field"], r["value"]) for r in rows],
                         [("A", "ai_involvement", "uses_ai_tools")])

    def test_a_gate_rejected_row_can_be_labelled(self):
        # PROVEN, NOT ASSERTED. This job has no job_facts row and no
        # job_matches row -- the pipeline never extracted it and nothing
        # downstream can see it. If the label table could not hold it, recall
        # would remain unmeasurable and the whole stratification would be
        # decoration.
        import schema
        self.conn.execute(
            f"INSERT INTO {schema.TABLE} (id, platform, company_token, "
            f"source_id, title, company_name, content_hash, first_seen, "
            f"last_seen, status) VALUES ('gate1','builtin','acme','g1',"
            f"'Ops Lead','Acme','h','t','t','open')")
        self.conn.execute(
            "INSERT INTO eval_label_items (label_set, job_id, stratum, "
            "platform, overlap, position) VALUES "
            "('s','gate1','gate_rejected','builtin',TRUE,0)")
        self.conn.commit()

        for table in (schema.FACTS_TABLE, schema.MATCHES_TABLE,
                      schema.SCORES_TABLE):
            n = self.conn.execute(
                f"SELECT COUNT(*) FROM {table} WHERE job_id = 'gate1'"
            ).fetchone()[0]
            self.assertEqual(n, 0, f"{table} must have no row for this job")

        self.assertTrue(labels.record(
            self.conn, axis="A", job_id="gate1", field="ai_involvement",
            value="uses_ai_tools", labeller_id="alice", label_set="s"))
        self.assertTrue(labels.record(
            self.conn, axis="B", job_id="gate1", field="would_apply",
            value="yes", labeller_id="alice", label_set="s",
            profile="pursuit"))
        self.conn.commit()
        self.assertEqual(len(labels.fetch(self.conn)), 2)

    # ----------------------------------------------------------------------
    # Which extraction the label was formed against. DEC-95.
    # ----------------------------------------------------------------------

    def _posting(self, job_id, facts_version=None):
        """A jobs row, and a job_facts row only if a version is given."""
        import schema
        self.conn.execute(
            f"INSERT INTO {schema.TABLE} (id, platform, company_token, "
            f"source_id, title, company_name, content_hash, first_seen, "
            f"last_seen, status) VALUES (%s,'builtin','acme',%s,"
            f"'Ops Lead','Acme','h','t','t','open')", (job_id, job_id))
        if facts_version is not None:
            self.conn.execute(
                f"INSERT INTO {schema.FACTS_TABLE} (job_id, facts_version, "
                f"extracted_at) VALUES (%s, %s, 't')",
                (job_id, facts_version))
        self.conn.commit()

    def _provenance(self, job_id):
        return self.conn.execute(
            "SELECT facts_version, facts_version_known FROM eval_labels "
            "WHERE job_id = %s", (job_id,)).fetchone()

    def test_a_label_records_the_extraction_that_was_current(self):
        self._posting("pv1", facts_version=3)
        labels.record(self.conn, axis="A", job_id="pv1",
                      field="seniority_level", value="mid",
                      labeller_id="alice", label_set="s")
        self.conn.commit()
        self.assertEqual(self._provenance("pv1"), (3, True))

    def test_a_posting_with_no_extraction_records_that_it_had_none(self):
        # NOT a failure and not a gap: most of the gate_rejected and
        # below_floor strata are exactly this, and the fact is permanent --
        # those labels can never be compared against model output at any
        # version. `known` is what separates it from "nobody was recording".
        self._posting("pv2")
        labels.record(self.conn, axis="A", job_id="pv2",
                      field="seniority_level", value="mid",
                      labeller_id="alice", label_set="s")
        self.conn.commit()
        self.assertEqual(self._provenance("pv2"), (None, True))

    def test_a_label_on_a_posting_with_no_jobs_row_at_all_still_records(self):
        # eval_labels carries no foreign key to jobs on purpose, and the
        # subquery must not turn that into an error. It resolves to NULL.
        labels.record(self.conn, axis="A", job_id="ghost",
                      field="seniority_level", value="mid",
                      labeller_id="alice", label_set="s")
        self.conn.commit()
        self.assertEqual(self._provenance("ghost"), (None, True))

    def test_a_row_written_before_the_columns_existed_reads_as_unrecorded(self):
        # THE ONE THAT MATTERS FOR THE 271 ROWS ALREADY IN THE LIVE TABLE.
        # An INSERT that names neither column takes the defaults, and the
        # defaults must say "nobody was recording" -- distinguishable from
        # the row above, which says "there was nothing to record".
        self.conn.execute(
            "INSERT INTO eval_labels (axis, job_id, field, value, "
            "labeller_id, round_no, labelled_at) VALUES "
            "('A','legacy','seniority_level','mid','alice',1,'t')")
        self.conn.commit()
        self.assertEqual(self._provenance("legacy"), (None, False))

    def test_ensure_schema_never_backfills_an_existing_row(self):
        # A guessed value is worse than a missing one -- job_events.rank's
        # rule, and the reason this migration is additive and nothing more.
        # Re-running it must leave every existing row exactly as it was, even
        # though job_facts now holds a version for this very posting.
        self.conn.execute(
            "INSERT INTO eval_labels (axis, job_id, field, value, "
            "labeller_id, round_no, labelled_at) VALUES "
            "('A','legacy2','seniority_level','mid','alice',1,'t')")
        self._posting("legacy2", facts_version=3)
        labels.ensure_schema(self.conn)
        self.assertEqual(self._provenance("legacy2"), (None, False))

    def test_fetch_carries_the_provenance_to_every_consumer(self):
        # The export JSONL, corpus.load() and the agreement functions all take
        # label rows and nothing else, so a column fetch() drops is a column
        # that exists in the table and nowhere a reader can see it.
        self._posting("pv3", facts_version=3)
        labels.record(self.conn, axis="A", job_id="pv3",
                      field="seniority_level", value="mid",
                      labeller_id="alice", label_set="s")
        self.conn.commit()
        row, = [r for r in labels.fetch(self.conn) if r["job_id"] == "pv3"]
        self.assertEqual(row["facts_version"], 3)
        self.assertIs(row["facts_version_known"], True)

    def test_the_tables_ship_empty(self):
        self.assertEqual(labels.fetch(self.conn), [])
        for table in labels.TABLES:
            if table == "eval_label_sets":
                continue
            n = self.conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            self.assertEqual(n, 0)

    def test_next_item_serves_overlap_rows_first(self):
        for i, (job, overlap) in enumerate(
                [("a", False), ("b", True), ("c", False)]):
            self.conn.execute(
                "INSERT INTO eval_label_items (label_set, job_id, stratum, "
                "platform, overlap, position) VALUES ('s',%s,'surfaced',"
                "'greenhouse',%s,%s)", (job, overlap, i))
        self.conn.commit()
        self.assertEqual(
            labels.next_item(self.conn, "s", "alice")["job_id"], "b")
        labels.record(self.conn, axis="A", job_id="b",
                      field="ai_involvement", value="none",
                      labeller_id="alice", label_set="s")
        self.conn.commit()
        # After the shared row, the tail. WHICH tail row is now a function of
        # the labeller -- see test_two_labellers_do_not_walk_the_same_tail --
        # so this asserts only that it is one of them.
        self.assertIn(
            labels.next_item(self.conn, "s", "alice")["job_id"], {"a", "c"})
        # A different person still gets the shared row first: that is what
        # makes the two of them comparable at all.
        self.assertEqual(
            labels.next_item(self.conn, "s", "bob")["job_id"], "b")

    def test_two_labellers_do_not_walk_the_same_tail(self):
        # THE DEFECT THIS PINS. next_item() ordered every labeller's queue
        # `overlap DESC, position ASC` -- identically. Ten volunteers doing
        # twenty postings each answered THE SAME twenty, so
        #
        #     distinct = overlap + n_labellers * (budget - overlap)
        #
        # had a structurally zero second term and distinct coverage could
        # never exceed what one person completed. Task 29's ">=100 labelled
        # postings from >=5 labellers" was unreachable regardless of turnout,
        # and the suite was green because nothing asserted coverage.
        for i in range(20):
            self.conn.execute(
                "INSERT INTO eval_label_items (label_set, job_id, stratum, "
                "platform, overlap, position) VALUES ('s',%s,'surfaced',"
                "'greenhouse',%s,%s)", (f"j{i:02d}", i < 4, i))
        self.conn.commit()

        # Everyone clears the four shared rows first, then diverges.
        firsts = set()
        for who in ("alice", "bob", "carol", "dave", "erin"):
            for job in ("j00", "j01", "j02", "j03"):
                item = labels.next_item(self.conn, "s", who)
                self.assertTrue(item["overlap"],
                                "shared rows must still come first")
                labels.record(self.conn, axis="A", job_id=item["job_id"],
                              field="ai_involvement", value="none",
                              labeller_id=who, label_set="s")
            self.conn.commit()
            firsts.add(labels.next_item(self.conn, "s", who)["job_id"])

        self.assertGreater(len(firsts), 1,
                           "five labellers entering a 16-row tail must not "
                           "all be handed the same posting")

    def test_a_labeller_who_comes_back_resumes_the_same_walk(self):
        # Determinism is not decoration. A volunteer who closes the tab and
        # reopens it must not be re-seated somewhere else in the tail. This is
        # what makes the rank derivable rather than stored: labelled_at is
        # written at insert time, so nobody can acquire an earlier first label
        # than someone already ranked, and no rank can move once assigned.
        for i in range(12):
            self.conn.execute(
                "INSERT INTO eval_label_items (label_set, job_id, stratum, "
                "platform, overlap, position) VALUES ('s',%s,'surfaced',"
                "'ashby',FALSE,%s)", (f"k{i:02d}", i))
        self.conn.commit()
        first = labels.next_item(self.conn, "s", "alice")["job_id"]
        for _ in range(4):
            self.assertEqual(
                labels.next_item(self.conn, "s", "alice")["job_id"], first)

        # And a later arrival does not renumber an earlier one.
        labels.record(self.conn, axis="A", job_id=first,
                      field="ai_involvement", value="none",
                      labeller_id="alice", label_set="s")
        self.conn.commit()
        rank_before = labels.labeller_rank(self.conn, "s", "alice")
        labels.record(self.conn, axis="A", job_id="k05",
                      field="ai_involvement", value="none",
                      labeller_id="zara", label_set="s")
        self.conn.commit()
        self.assertEqual(labels.labeller_rank(self.conn, "s", "alice"),
                         rank_before)
        self.assertNotEqual(labels.labeller_rank(self.conn, "s", "zara"),
                            rank_before)

    def test_every_row_is_still_reachable_by_one_labeller(self):
        # Rotating the tail must not strand rows. A modular walk that skipped
        # one would cap the set below its own n and nothing else would notice.
        for i in range(9):
            self.conn.execute(
                "INSERT INTO eval_label_items (label_set, job_id, stratum, "
                "platform, overlap, position) VALUES ('s',%s,'surfaced',"
                "'builtin',%s,%s)", (f"m{i:02d}", i < 2, i))
        self.conn.commit()
        seen = []
        while True:
            item = labels.next_item(self.conn, "s", "zoe")
            if item is None:
                break
            seen.append(item["job_id"])
            labels.record(self.conn, axis="A", job_id=item["job_id"],
                          field="ai_involvement", value="none",
                          labeller_id="zoe", label_set="s")
            self.conn.commit()
        self.assertEqual(sorted(seen), [f"m{i:02d}" for i in range(9)])

    def _overlap_set(self, n_overlap=3, n_tail=5):
        for i in range(n_overlap + n_tail):
            self.conn.execute(
                "INSERT INTO eval_label_items (label_set, job_id, stratum, "
                "platform, overlap, position) VALUES ('s',%s,'surfaced',"
                "'greenhouse',%s,%s)",
                (f"r{i:02d}", i < n_overlap, i))
        self.conn.commit()

    #: Round-1 answers in these tests are dated well in the past by default, so
    #: that a test about the round-2 QUEUE is not also a test of
    #: ROUND_TWO_DELAY_DAYS. The tests that are about the delay pass `at` and
    #: `now` explicitly. Left at the default they would all be too fresh to
    #: re-ask, which is the delay working and would read as the queue broken.
    OLD = "2026-01-01T09:00:00"

    def _answer(self, job_id, who, *, round_no=1, value="none", at=OLD):
        labels.record(self.conn, axis="A", job_id=job_id,
                      field="ai_involvement", value=value, labeller_id=who,
                      label_set="s", round_no=round_no, now=at)
        self.conn.commit()

    def test_round_two_was_unreachable_and_that_is_what_this_pins(self):
        # THE DEFECT THIS PINS. next_item()'s round-1 predicate is "this
        # labeller has answered nothing about this job", with no round_no in
        # it, and webapp/label.py never passed round_no to record(). So
        # record()'s round_no parameter, both partial unique indexes and
        # intra_annotator() were all correct and jointly unreachable: no route
        # through the built surface could produce a round-2 row, and
        # docs/ingestion_tests/03-metrics-and-golden-set.md:25's "5-10 jobs
        # labelled twice, a week apart" was uncollectable at any turnout.
        self._overlap_set()
        self._answer("r00", "alice")
        # Round 1 will not serve it again -- that part was never wrong.
        served = []
        while (item := labels.next_item(self.conn, "s", "alice")) is not None:
            served.append(item["job_id"])
            self._answer(item["job_id"], "alice")
        self.assertNotIn("r00", served)
        # Round 2 does, and only because it asks a different question.
        self.assertEqual(
            labels.next_item(self.conn, "s", "alice", round_no=2)["job_id"],
            "r00")

    def test_round_two_serves_only_overlap_rows_already_answered(self):
        self._overlap_set()
        # One overlap row and one tail row answered in round 1.
        self._answer("r01", "alice")
        self._answer("r05", "alice")
        seen = []
        while (item := labels.next_item(self.conn, "s", "alice",
                                        round_no=2)) is not None:
            seen.append(item["job_id"])
            self._answer(item["job_id"], "alice", round_no=2)
        # r05 is answered but is not an overlap row; r00 and r02 are overlap
        # rows but were never answered in round 1. Neither belongs in a
        # self-agreement measurement.
        self.assertEqual(seen, ["r01"])

    def test_round_two_does_not_serve_the_same_row_twice(self):
        self._overlap_set()
        self._answer("r00", "alice")
        self._answer("r00", "alice", round_no=2, value="uses_ai_tools")
        self.assertIsNone(
            labels.next_item(self.conn, "s", "alice", round_no=2))

    def test_both_rounds_survive_and_intra_annotator_can_read_them(self):
        # The point of the whole path: a figure that has never been computable
        # from data. A disagreeing pair must come back as disagreement, not be
        # collapsed by ON CONFLICT.
        self._overlap_set()
        self._answer("r00", "alice", value="none")
        self._answer("r00", "alice", round_no=2, value="uses_ai_tools")
        self._answer("r01", "alice", value="none")
        self._answer("r01", "alice", round_no=2, value="none")
        rows = labels.fetch(self.conn, axis="A")
        self.assertEqual(
            sorted((r["job_id"], r["round_no"], r["value"]) for r in rows),
            [("r00", 1, "none"), ("r00", 2, "uses_ai_tools"),
             ("r01", 1, "none"), ("r01", 2, "none")])
        intra = labels.intra_annotator(rows, {"ai_involvement": "enum"})
        cell = intra["fields"]["ai_involvement"]
        # Two postings answered twice by one person; one pair agrees. It is a
        # metrics.field_cell(), so the count is `agree2_k` and it means the
        # same thing here as in the inter-annotator column -- one Bernoulli
        # trial per item. That is what makes the two ceilings comparable, and
        # comparing them is the reason round 2 exists.
        self.assertEqual(cell["n"], 2)
        self.assertEqual(cell["agree2_k"], 1)
        self.assertEqual(cell["agree2"], 0.5)

    def test_the_round_two_gate_names_a_date_rather_than_refusing_blankly(self):
        # ROUND_TWO_DELAY_DAYS is the measurement, not politeness: served an
        # hour later this measures memory. The refusal has to carry the date,
        # because "not yet" with no date is indistinguishable from "broken".
        self._overlap_set()
        self._answer("r00", "alice", at="2026-07-01T09:00:00")
        ready, n, when = labels.round_two_ready(
            self.conn, "s", "alice", now="2026-07-03T09:00:00")
        self.assertFalse(ready)
        self.assertEqual(n, 1)
        self.assertEqual(when[:10], "2026-07-08")
        ready, n, when = labels.round_two_ready(
            self.conn, "s", "alice", now="2026-07-09T09:00:00")
        self.assertTrue(ready)

    def test_the_delay_is_per_row_not_per_labeller(self):
        # The defect this pins. Gating on the labeller's EARLIEST round-1
        # answer would serve a row answered yesterday the moment their oldest
        # row matured -- re-asking a fresh posting, which measures memory and
        # is the one thing the delay exists to stop. Gating on their LATEST
        # would be sound and would block nine mature rows behind one fresh one.
        self._overlap_set(n_overlap=2)
        self._answer("r00", "alice", at="2026-07-01T09:00:00")   # old
        self._answer("r01", "alice", at="2026-07-20T09:00:00")   # fresh
        served = []
        while True:
            item = labels.next_item(self.conn, "s", "alice", round_no=2,
                                    now="2026-07-21T09:00:00")
            if item is None:
                break
            served.append(item["job_id"])
            self._answer(item["job_id"], "alice", round_no=2)
        self.assertEqual(served, ["r00"],
                         "only the matured row may be re-asked")
        # And the fresh one becomes available on its own schedule.
        self.assertEqual(
            labels.next_item(self.conn, "s", "alice", round_no=2,
                             now="2026-07-28T09:00:00")["job_id"], "r01")

    def test_round_two_re_asks_only_what_was_actually_answered(self):
        # THE BYPASS THIS PINS. An earlier fix re-filed a field blank in round 1
        # as a round-1 answer when it arrived at round-2 time. That created a
        # FRESH round-1 row which a round-2 row could then partner minutes
        # later: the posting stayed eligible on its OTHER fields' timestamps,
        # and intra_annotator() never reads labelled_at, so the close pair
        # landed in the ceiling unmarked. Round 2 now re-asks only fields that
        # were answered, not abstained, and matured.
        self._overlap_set(n_overlap=1)
        self._answer("r00", "alice", value="none")               # answered
        labels.record(self.conn, axis="A", job_id="r00",
                      field="seniority_level", value=None,
                      labeller_id="alice", label_set="s", now=self.OLD)
        self.conn.commit()                                        # abstained
        # role_track was never answered at all.
        due = labels.round_one_answers(self.conn, "s", "r00", "alice")
        self.assertEqual(due, {"ai_involvement"},
                         "an abstention and a blank are both excluded")

    def test_a_round_one_answer_too_fresh_to_re_ask_is_excluded_per_field(self):
        # Per field, not per posting -- the whole point. A posting can be
        # eligible on one field and not another.
        self._overlap_set(n_overlap=1)
        self._answer("r00", "alice", value="none", at="2026-07-01T09:00:00")
        labels.record(self.conn, axis="A", job_id="r00",
                      field="seniority_level", value="mid",
                      labeller_id="alice", label_set="s",
                      now="2026-07-20T09:00:00")
        self.conn.commit()
        due = labels.round_one_answers(self.conn, "s", "r00", "alice",
                                       now="2026-07-21T09:00:00")
        self.assertEqual(due, {"ai_involvement"},
                         "the fresh field is not due even though the posting "
                         "is")

    def test_a_posting_answered_only_by_abstention_is_not_re_served(self):
        # Otherwise round 2 serves a posting with nothing due on it, and the
        # POST has to reject the whole submission.
        self._overlap_set(n_overlap=1)
        labels.record(self.conn, axis="A", job_id="r00",
                      field="ai_involvement", value=None,
                      labeller_id="alice", label_set="s", now=self.OLD)
        self.conn.commit()
        self.assertIsNone(
            labels.next_item(self.conn, "s", "alice", round_no=2))

    def test_an_abstain_only_posting_is_not_counted_as_still_waiting(self):
        # THE PERMANENT "COME BACK LATER" THIS PINS. n_waiting once counted any
        # posting with round-1 rows, while next_item() requires a NON-NULL one.
        # So a posting a labeller abstained on across every question counted as
        # outstanding and could never be served: the caller's
        # `done < n_waiting` test stayed true forever and the "there is more to
        # do here later" page never retired. The original exhaustion defect
        # inverted -- told to come back to a queue that will never fill.
        self._overlap_set(n_overlap=2)
        self._answer("r00", "alice", value="none")              # real answer
        labels.record(self.conn, axis="A", job_id="r01",
                      field="ai_involvement", value=None,
                      labeller_id="alice", label_set="s", now=self.OLD)
        self.conn.commit()                                       # abstain only
        ready, n_waiting, when = labels.round_two_ready(self.conn, "s", "alice")
        self.assertTrue(ready)
        self.assertEqual(n_waiting, 1,
                         "the abstain-only posting is not re-askable, so it is "
                         "not outstanding either")
        # And the queue agrees, which is the invariant the two must share.
        served = []
        while (item := labels.next_item(self.conn, "s", "alice",
                                        round_no=2)) is not None:
            served.append(item["job_id"])
            self._answer(item["job_id"], "alice", round_no=2)
        self.assertEqual(served, ["r00"])
        done, _total = labels.progress(self.conn, "s", "alice", round_no=2)
        self.assertEqual(done, n_waiting,
                         "done must be able to reach n_waiting, or the caller "
                         "can never say 'finished'")

    def test_a_labeller_with_no_round_one_is_a_different_state_from_too_soon(self):
        self._overlap_set()
        ready, n, when = labels.round_two_ready(self.conn, "s", "nobody")
        self.assertFalse(ready)
        self.assertEqual(n, 0)
        self.assertIsNone(when)

    def test_round_two_progress_counts_against_the_overlap_block(self):
        # Not against the set. "3 of 200" on a ten-row queue reads as an
        # eight-hour evening, which is how a volunteer closes the tab.
        self._overlap_set(n_overlap=3, n_tail=5)
        self._answer("r00", "alice")
        self.assertEqual(labels.progress(self.conn, "s", "alice"), (1, 8))
        self._answer("r00", "alice", round_no=2)
        self.assertEqual(
            labels.progress(self.conn, "s", "alice", round_no=2), (1, 3))

    def test_round_one_progress_is_not_inflated_by_round_two_answers(self):
        self._overlap_set()
        self._answer("r00", "alice")
        self._answer("r00", "alice", round_no=2)
        # One posting done in round 1, not two.
        self.assertEqual(labels.progress(self.conn, "s", "alice")[0], 1)

    def test_fetch_carries_the_platform_the_breakout_needs(self):
        # 29:106 needs a per-platform split and eval_labels has no platform
        # column -- deliberately, because the platform is a property of the
        # posting and eval_label_items already records it once (labels.py:273).
        # fetch() joins it on, so the export, corpus.load() and all three
        # agreement functions get it without a second query or a second copy
        # that can disagree with the first.
        self.conn.execute(
            "INSERT INTO eval_label_items (label_set, job_id, stratum, "
            "platform, overlap, position) VALUES "
            "('s','j1','surfaced','hn_whoishiring',FALSE,0)")
        labels.record(self.conn, axis="A", job_id="j1",
                      field="ai_involvement", value="none",
                      labeller_id="alice", label_set="s")
        self.conn.commit()
        rows = labels.fetch(self.conn)
        self.assertEqual([r["platform"] for r in rows], ["hn_whoishiring"])

    def test_a_label_outside_any_set_still_comes_back(self):
        # LEFT JOIN, not INNER. record() allows a NULL label_set and axis A is
        # deliberately not owned by whichever set sampled the row
        # (ensure_schema's comment). An inner join would delete evidence in
        # order to add a column, which is the same defect pool_query() warns
        # about at labels.py:414.
        labels.record(self.conn, axis="A", job_id="orphan",
                      field="ai_involvement", value="none",
                      labeller_id="alice")
        self.conn.commit()
        rows = labels.fetch(self.conn)
        self.assertEqual([(r["job_id"], r["platform"]) for r in rows],
                         [("orphan", None)])
        # ... and it reports as `unknown`, not as absent.
        block = labels.inter_annotator(
            rows + [dict(rows[0], labeller_id="bob")], KINDS)["by_platform"]
        self.assertEqual(list(block["fields"]["ai_involvement"]),
                         [labels.UNKNOWN_PLATFORM])

    def test_one_label_cannot_be_fanned_out_by_the_join(self):
        # eval_label_items' primary key is (label_set, job_id), so at most one
        # item matches. Pinned because a join that duplicates rows would
        # double every n in the report and nothing else would notice.
        for label_set in ("s", "s2"):
            if label_set != "s":
                self.conn.execute(
                    "INSERT INTO eval_label_sets (label_set, created_at, seed,"
                    " n, profile, job_id_sha256) VALUES (%s, 't', 0, 1, "
                    "'pursuit', 'sha')", (label_set,))
            self.conn.execute(
                "INSERT INTO eval_label_items (label_set, job_id, stratum, "
                "platform, overlap, position) VALUES (%s,'j1','surfaced',"
                "'greenhouse',FALSE,0)", (label_set,))
        labels.record(self.conn, axis="A", job_id="j1",
                      field="ai_involvement", value="none",
                      labeller_id="alice", label_set="s")
        self.conn.commit()
        self.assertEqual(len(labels.fetch(self.conn)), 1)

    def test_verify_schema_names_a_missing_table(self):
        problems = labels.verify_schema(
            self.conn, privileges={"eval_labels_nope": ("SELECT",)},
            sequences={})
        self.assertEqual(len(problems), 1)
        self.assertIn("missing", problems[0])


# --------------------------------------------------------------------------
# The redraw window, which closes the first time anyone answers anything
# --------------------------------------------------------------------------

def _drawn(job_ids, *, overlap=()):
    """A drawn set in the shape register_set() consumes.

    Positions come from the order given, so a caller can hand the same job ids
    back in a different order and see that the digest -- which is over the
    SORTED ids -- does not move.
    """
    return [{"job_id": j, "stratum": "surfaced", "platform": "greenhouse",
             "overlap": j in overlap, "position": i}
            for i, j in enumerate(job_ids)]


@unittest.skipUnless(scratchdb.available(),
                     "no reachable Postgres for a scratch schema")
class TestASetCannotBeRedrawnOnceItIsDrawn(unittest.TestCase):
    """The window HANDOFF.md:275 calls closed, closed in code.

    THE DEFECT THIS PINS. register_set() inserts `ON CONFLICT DO NOTHING` on
    both tables, so re-running `evals label sample` with a different --seed or
    --n did not fail: the existing items kept their old `position` and
    `overlap`, newly drawn job_ids were APPENDED, and `eval_label_sets.n` and
    `job_id_sha256` went on describing the first draw. digest() existed and was
    never compared against the stored value anywhere. Three disagreeing records
    of one set -- database, committed fixture, published figures -- and nothing
    red.

    Against a real Postgres rather than a fake connection: the guard is a claim
    about what two TABLES hold, and one of them is `eval_labels`, which a fake
    connection reports empty forever -- so it would pass the unguarded code.
    """

    def setUp(self):
        self._ctx = scratchdb.scratch_schema()
        self.conn, self.name = self._ctx.__enter__()
        labels.ensure_schema(self.conn)
        self.rows = _drawn(("a1", "b2", "c3"))
        labels.register_set(self.conn, "pursuit-v1", self.rows, seed=0,
                            profile="pursuit")

    def tearDown(self):
        self._ctx.__exit__(None, None, None)

    def _stored(self):
        return self.conn.execute(
            "SELECT n, job_id_sha256 FROM eval_label_sets "
            "WHERE label_set = 'pursuit-v1'").fetchone()

    def _job_ids(self):
        return [r[0] for r in self.conn.execute(
            "SELECT job_id FROM eval_label_items WHERE label_set = "
            "'pursuit-v1' ORDER BY job_id").fetchall()]

    def test_re_registering_the_same_draw_is_a_no_op_and_does_not_raise(self):
        # THIS IS WHAT THE GUARD MUST NOT BREAK. A re-run of the same command
        # with the same seed is how an operator recovers from a crash between
        # register_set() and save_set(), and it is how pursuit-v1's own
        # defect-4 redraw was verified against the committed fixture. Handed
        # back in a different order, because the digest is over the SORTED ids
        # and a guard that keyed on insertion order would refuse this.
        stored = self._stored()
        labels.register_set(self.conn, "pursuit-v1", list(reversed(self.rows)),
                            seed=0, profile="pursuit")
        self.assertEqual(self._stored(), stored)
        self.assertEqual(self._job_ids(), ["a1", "b2", "c3"])

    def test_a_draw_with_different_job_ids_is_refused(self):
        other = _drawn(("a1", "b2", "c4"))
        with self.assertRaises(labels.SetAlreadyDrawn) as caught:
            labels.register_set(self.conn, "pursuit-v1", other, seed=1,
                                profile="pursuit")
        msg = str(caught.exception)
        # Both digests, the stored n and the label count, so the reader can
        # tell "I changed the seed" from "the corpus moved under me" without
        # going to the database to find out which.
        self.assertIn(labels.digest(self.rows), msg)
        self.assertIn(labels.digest(other), msg)
        self.assertIn("n=3", msg)
        self.assertIn("0 row(s)", msg)
        # And it refused BEFORE writing: `c4` was not appended, which is the
        # shape the unguarded version left behind.
        self.assertEqual(self._job_ids(), ["a1", "b2", "c3"])

    def test_one_label_refuses_even_a_redraw_at_the_same_digest(self):
        labels.record(self.conn, axis="A", job_id="a1",
                      field="ai_involvement", value="none",
                      labeller_id="alice", label_set="pursuit-v1")
        self.conn.commit()

        # SAME DIGEST, DIFFERENT SET. The job ids are the digest's only input,
        # so moving which rows are `overlap` -- exactly what pursuit-v1's
        # defect-4 redraw did -- hashes identically. Those flags decide which
        # postings every labeller is shown first and which rows the
        # inter-annotator ceiling is computed over, so re-registering under
        # alice silently changes what her answer was an answer to.
        moved = _drawn(("a1", "b2", "c3"), overlap=("c3",))
        self.assertEqual(labels.digest(moved), labels.digest(self.rows))
        with self.assertRaises(labels.SetAlreadyDrawn) as caught:
            labels.register_set(self.conn, "pursuit-v1", moved, seed=0,
                                profile="pursuit")
        self.assertIn("1 row(s)", str(caught.exception))
        self.assertIn("labelled", str(caught.exception))

    def test_a_different_name_is_always_free_to_draw(self):
        # The refusal is not a lock on the sampler. The remedy the message
        # names -- a new --label-set -- has to work with labels in the table,
        # or the guard would make the tool unusable exactly when it matters.
        labels.record(self.conn, axis="A", job_id="a1",
                      field="ai_involvement", value="none",
                      labeller_id="alice", label_set="pursuit-v1")
        self.conn.commit()
        labels.register_set(self.conn, "pursuit-v2", _drawn(("d4", "e5")),
                            seed=1, profile="pursuit")
        self.assertEqual(self._job_ids(), ["a1", "b2", "c3"])


class _NoCloseConn:
    """The scratch connection with close() removed.

    cmd_label_sample owns the connection _labels_conn() hands it and closes it
    in a finally. Handed the scratch schema's only session it would close that,
    and tearDown could no longer drop the schema.
    """

    def __init__(self, conn):
        self._conn = conn

    def __getattr__(self, name):
        return getattr(self._conn, name)

    def close(self):
        pass


@unittest.skipUnless(scratchdb.available(),
                     "no reachable Postgres for a scratch schema")
class TestARefusedSampleDoesNotRewriteTheFixture(unittest.TestCase):
    """`evals label sample` registers the set BEFORE it writes --out.

    Which is why the guard has to be asked there and not inside save_set(): the
    fixture is what report time reads, and a refusal discovered after the file
    had been rewritten would already have desynced it from the database that
    refused it -- leaving the operator with the one state nothing can tell
    apart from a good run.

    Exit 2, matching the `report` refusal (__main__.py's
    `except labels.Uninterpretable` handler) rather than 1, which in this CLI
    means "nothing to do".
    """

    def setUp(self):
        import tempfile
        self._ctx = scratchdb.scratch_schema()
        self.conn, self.name = self._ctx.__enter__()
        labels.ensure_schema(self.conn)
        labels.register_set(self.conn, "pursuit-v1", _drawn(("a1", "b2")),
                            seed=0, profile="pursuit")
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.out = os.path.join(tmp.name, "labelset-pursuit-v1.jsonl")
        with open(self.out, "w", encoding="utf-8") as fh:
            fh.write('{"job_id": "a1", "position": 0}\n')
            fh.write('{"job_id": "b2", "position": 1}\n')
        with open(self.out, "rb") as fh:
            self.before = fh.read()

    def tearDown(self):
        self._ctx.__exit__(None, None, None)

    def _run(self, **overrides):
        """Drive cmd_label_sample against the scratch schema.

        Everything patched here is upstream of the guard -- the corpus read and
        the profile row -- and nothing downstream of it is. register_set(),
        redraw_refusal(), save_set() and the command's own control flow are the
        real ones, which is the whole point: the claim under test is about the
        ORDER of two calls in that function.
        """
        import argparse
        import contextlib
        import io
        from unittest import mock

        import profiles
        import relevance
        from evals import __main__ as evals_main

        args = argparse.Namespace(
            n=6, out=self.out, label_set="pursuit-v1", profile="pursuit",
            seed=1, overlap=0, per_platform=10, note=None, dry_run=False)
        for k, v in overrides.items():
            setattr(args, k, v)

        class _Prof:
            criteria = {}

        err = io.StringIO()
        with mock.patch.object(evals_main, "_labels_conn",
                               return_value=_NoCloseConn(self.conn)), \
             mock.patch.object(profiles, "load_one", return_value=_Prof()), \
             mock.patch.object(relevance, "for_profile", return_value={}), \
             mock.patch.object(labels, "pool", return_value=_pool_rows()), \
             mock.patch.object(labels, "confirm_scores",
                               side_effect=lambda rows, criteria: (rows, [])), \
             contextlib.redirect_stderr(err), \
             contextlib.redirect_stdout(io.StringIO()):
            rc = evals_main.cmd_label_sample(args)
        self.stderr = err.getvalue()
        return rc

    def _unchanged(self):
        with open(self.out, "rb") as fh:
            self.assertEqual(fh.read(), self.before)

    def test_a_refused_sample_leaves_the_out_file_byte_identical(self):
        self.assertEqual(self._run(), 2)
        self._unchanged()
        self.assertIn("REFUSED", self.stderr)
        self.assertIn(self.out, self.stderr)
        # And the database is the state it was refused from, not a merge of
        # the two draws.
        self.assertEqual(
            self.conn.execute("SELECT COUNT(*) FROM eval_label_items "
                              "WHERE label_set = 'pursuit-v1'").fetchone()[0],
            2)

    def test_a_dry_run_reports_the_refusal_instead_of_would_write(self):
        # A dry run writes nothing, so it is never the run that does the
        # damage -- but it is the run an operator makes to find out whether the
        # real one will work, and "would write ..." is the wrong answer.
        self.assertEqual(self._run(dry_run=True), 2)
        self._unchanged()
        self.assertIn("REFUSED", self.stderr)


class TestAnAbsentFieldIsNotANullAnswer(unittest.TestCase):
    """`normalized.get(field)` cannot tell silence from a verdict.

    On `role_track` a present null is the model saying "no listed track
    describes this role" -- extract.py:338: "Use null if none of the listed
    tracks clearly describes the role. Do not force a value." An absent key is
    the model never having been asked. `.get()` returns None for both, and
    as_model_domain() folds a human NO_TRACK_FITS to None for comparison, so
    under `.get()` the two scored as AGREEMENT.
    """

    def _labels(self, job_ids, value=labels.NO_TRACK_FITS):
        return [_label(j, "role_track", value, "alice") for j in job_ids]

    def test_a_missing_field_is_excluded_and_counted_not_scored(self):
        rows = self._labels(["j1", "j2"])
        # The model record exists -- it is not `no_model_output` -- and simply
        # has no role_track key, which is the shape of every row in
        # pursuit-criteria-corpus.jsonl.
        model = {"j1": {"seniority_level": "mid"},
                 "j2": {"seniority_level": "mid"}}
        out = labels.model_vs_human(rows, model, KINDS)
        self.assertNotIn("role_track", out["vs_consensus"])
        self.assertEqual(out["no_model_field"]["role_track"], 2)
        # Not booked as a missing record: the record is right there.
        self.assertEqual(out["no_model_output"], [])
        # And it is not in the per-platform breakout either, which would carry
        # the same false disagreement into a thinner cell.
        self.assertNotIn("role_track", out["by_platform"]["fields"])

    def test_a_present_null_is_compared_and_agrees_with_no_track_fits(self):
        rows = self._labels(["j1"])
        model = {"j1": {"role_track": None}}
        out = labels.model_vs_human(rows, model, KINDS)
        cell = out["vs_consensus"]["role_track"]
        self.assertEqual((cell["n"], cell["k"], cell["rate"]), (1, 1, 1.0))
        # Both sides say no listed track fits. That is agreement, and it is
        # the reading as_model_domain() exists to produce.
        self.assertEqual(out["no_model_field"], {})

    def test_the_two_cases_differ_and_a_get_would_collapse_them(self):
        # THE ASSERTION THAT FAILS UNDER `.get()`. Same human answer, same
        # field, two model records that differ only in whether the key is
        # there. Under `.get()` both are None on the model side and both score
        # as agreement, so every number below would have been identical.
        rows = self._labels(["j1", "j2"])
        absent = labels.model_vs_human(
            rows, {"j1": {}, "j2": {}}, KINDS)
        present = labels.model_vs_human(
            rows, {"j1": {"role_track": None}, "j2": {"role_track": None}},
            KINDS)
        self.assertNotIn("role_track", absent["vs_consensus"])
        self.assertEqual(absent["no_model_field"]["role_track"], 2)
        self.assertEqual(present["vs_consensus"]["role_track"]["n"], 2)
        self.assertEqual(present["vs_consensus"]["role_track"]["rate"], 1.0)
        self.assertEqual(present["no_model_field"], {})

    def test_a_real_answer_against_a_missing_field_is_not_a_disagreement(self):
        # The direction that drove the field toward 0%: a human who confidently
        # named a track, against a corpus with no such key. Excluded, not
        # scored 0.
        rows = self._labels(["j1"], value="data_analytics")
        out = labels.model_vs_human(rows, {"j1": {}}, KINDS)
        self.assertNotIn("role_track", out["vs_consensus"])
        self.assertEqual(out["no_model_field"]["role_track"], 1)

    def test_a_wholly_absent_record_is_still_no_model_output(self):
        # Unchanged behaviour, and a different quantity: `no_model_output` is
        # the record that is not there at all, `no_model_field` is one field of
        # a record that is.
        rows = self._labels(["j1", "j2"])
        out = labels.model_vs_human(rows, {"j1": {"role_track": None}}, KINDS)
        self.assertEqual(out["no_model_output"], ["j2"])
        self.assertEqual(out["no_model_field"], {})
        self.assertEqual(out["vs_consensus"]["role_track"]["n"], 1)

    def test_the_two_columns_count_the_loss_in_their_own_denominators(self):
        # `vs_consensus` counts items and `vs_each` counts comparisons, so one
        # shared counter would belong to neither. Three labellers agreeing on
        # one item is one lost item and three lost comparisons.
        rows = [_label("j1", "role_track", "data_analytics", who)
                for who in ("alice", "bob", "carol")]
        out = labels.model_vs_human(rows, {"j1": {}}, KINDS)
        self.assertEqual(out["no_model_field"]["role_track"], 1)
        self.assertEqual(out["no_model_field_each"]["role_track"], 3)
        self.assertNotIn("role_track", out["vs_each"])

    def test_an_abstaining_labeller_is_not_also_counted_as_a_model_gap(self):
        # An abstention is already excluded for a human reason. Booking it
        # twice would inflate the model-gap count with rows the model was never
        # asked about.
        rows = [_label("j1", "role_track", None, "alice"),
                _label("j1", "role_track", "data_analytics", "bob")]
        out = labels.model_vs_human(rows, {"j1": {}}, KINDS)
        self.assertEqual(out["no_model_field_each"]["role_track"], 1)

    def test_the_other_four_fields_are_unaffected_by_the_membership_test(self):
        # They are present on all 859 rows of the frozen corpus, so nothing
        # about them changes -- including a genuine disagreement still scoring
        # as one.
        rows = [_label("j1", "seniority_level", "mid", "alice"),
                _label("j2", "seniority_level", "senior", "alice")]
        out = labels.model_vs_human(
            rows, {"j1": {"seniority_level": "mid"},
                   "j2": {"seniority_level": "mid"}}, KINDS)
        cell = out["vs_consensus"]["seniority_level"]
        self.assertEqual((cell["n"], cell["k"]), (2, 1))
        self.assertEqual(out["no_model_field"], {})


class TestTheFrozenCorpusCannotMeasureRoleTrack(unittest.TestCase):
    """The corpus is not the thing to fix, and the report has to say so.

    Writing `role_track` values into it would be inventing model answers in an
    eval corpus, in a file with no generator script (HANDOFF.md:1043-1047) whose
    rows also carry tests/test_match.py's pinned scores and ranks. It is not
    covered by tests/test_evals.py:454's sha256 pin either, so such an edit
    would be quiet rather than loud. Re-extracting it at a facts_version that
    carries the field is separate, deliberate work.
    """

    CORPUS = os.path.join(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))), "evals", "fixtures",
        "pursuit-criteria-corpus.jsonl")

    def setUp(self):
        from evals import corpus
        self.records = corpus.load(self.CORPUS)

    def test_role_track_is_absent_from_every_row_and_the_rest_are_present(self):
        self.assertEqual(len(self.records), 859)
        self.assertEqual(
            sum(1 for r in self.records if "role_track" in r), 0)
        for field in ("ai_involvement", "seniority_level", "role_archetype",
                      "remote_policy"):
            self.assertEqual(
                sum(1 for r in self.records if field in r), 859, field)
        # Flat dicts, no nested `facts` block -- which is why membership on the
        # record itself is the right test.
        self.assertEqual(sum(1 for r in self.records if "facts" in r), 0)

    def test_the_report_counts_the_shortfall_rather_than_scoring_it_zero(self):
        # One human label per corpus row, on the one field the corpus cannot
        # answer. Under `.get()` this produced a `role_track` cell with n=20
        # and a rate near 0; now it produces no cell and a count of 20.
        sample = [r["job_id"] for r in self.records[:20]]
        rows = [_label(j, "role_track", "data_analytics", "alice")
                for j in sample]
        model = {r["job_id"]: r for r in self.records}
        out = labels.model_vs_human(rows, model, KINDS)
        self.assertNotIn("role_track", out["vs_consensus"])
        self.assertEqual(out["no_model_field"]["role_track"], 20)
        self.assertEqual(out["no_model_output"], [])
        # So the three-quantity gate refuses the field, and the refusal names
        # the model-output cause rather than sending the reader after
        # volunteers who have already labelled it.
        with self.assertRaises(labels.Uninterpretable) as caught:
            labels.interpretable(
                floor={"role_track": {"overall": {"n": 5, "agree2": 1.0}}},
                ceiling={"role_track": {"n": 5, "agree2": 1.0}},
                measured=out["vs_consensus"], fields=["role_track"])
        self.assertIn("no_model_field", str(caught.exception))


# --------------------------------------------------------------------------
# Axis B against the ordering the product ships -- labels.ordering()
# --------------------------------------------------------------------------

def _item(job_id, stratum, *, match_score=None, computed_score=None,
          platform=None, position=0, overlap=False, tier=None):
    """One row of a label SET, in save_set()'s shape (labels.py:770-772).

    Distinct from _label() above, which makes a row of eval_labels. The two
    inputs to ordering() are different things and conflating them in a fixture
    factory would hide which of the two a figure came from: the set says what
    the population is and what score orders it, the labels say what a person
    said about it.
    """
    return {"job_id": job_id, "stratum": stratum, "platform": platform,
            "position": position, "overlap": overlap, "tier": tier,
            "match_score": match_score, "computed_score": computed_score}


def _b(job_id, value, who, *, profile="pursuit", round_no=1):
    """One axis-B answer. Carries a profile, because axis B always does."""
    return _label(job_id, labels.AXIS_B_FIELD, value, who,
                  axis=labels.AXIS_B, profile=profile, round_no=round_no)


#: The pinned set's identity. CLAUDE.md pins an eval set by sorted `job_id`,
#: and every figure ordering() produces is a figure ABOUT THIS SET -- so a
#: regenerated file would change the population under numbers already written
#: down. The same device tests/test_evals.py:454 puts on the frozen corpora.
PURSUIT_V1_SHA = ("afb2d58f5d369dfd03ad9237a8b16396"
                  "cea31b838a67343f51aceecf70cd1763")

PURSUIT_V1 = os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "evals", "fixtures",
    "labelset-pursuit-v1.jsonl")


class TestAxisBAgainstTheOrdering(unittest.TestCase):
    """Does `match_score` put the postings a Builder would apply to first?

    NO DATABASE AND NO REAL LABEL ANYWHERE IN HERE. `eval_labels` ships empty
    and stays empty until task 29's labelling night; the whole point of
    building this adapter first is that it must be trustworthy BEFORE the
    labels exist, and it is only trustworthy if it can be falsified on
    synthetic rows. Every fixture below is a _label()/_item() dict.
    """

    def test_a_perfect_ordering_scores_one(self):
        set_rows = [_item("j1", "surfaced", match_score=90),
                    _item("j2", "surfaced", match_score=80),
                    _item("j3", "surfaced", match_score=70),
                    _item("j4", "surfaced", match_score=60)]
        rows = [_b("j1", "yes", "alice"), _b("j2", "yes", "alice"),
                _b("j3", "no", "alice"), _b("j4", "no", "alice")]
        block = labels.ordering(rows, set_rows,
                                profile="pursuit", k=2)["strata"]["surfaced"]
        self.assertEqual(block["average_precision"], 1.0)
        self.assertEqual(block["precision_at_k"], 1.0)
        self.assertEqual(block["k"], 2)
        # AP's chance level IS the positive rate (metrics.py:396-399), so 1.0
        # against 0.5 is signal and 1.0 against 1.0 would be nothing at all.
        # The two are in the same dict so a report cannot print one alone.
        self.assertEqual(block["n_positive"], 2)
        self.assertEqual(block["positive_rate"], 0.5)

    def test_ordering_has_no_default_profile(self):
        # A default would silently pool two personas' answers about one posting
        # against one match_score, which is keyed (job_id, profile).
        with self.assertRaises(TypeError):
            labels.ordering([], [])

    def test_the_positive_class_is_the_consensus_and_a_tie_is_excluded(self):
        set_rows = [_item("j1", "surfaced", match_score=90),
                    _item("j2", "surfaced", match_score=80)]
        rows = [_b("j1", "yes", "alice"), _b("j1", "no", "bob"),
                _b("j2", "yes", "alice"), _b("j2", "yes", "bob"),
                _b("j2", "no", "carol")]
        out = labels.ordering(rows, set_rows, profile="pursuit")
        block = out["strata"]["surfaced"]
        self.assertEqual(block["labelled"], 1)
        self.assertEqual(block["label_coverage"], "1/2")
        self.assertEqual(block["n_positive"], 1)
        # consensus() refuses to invent a majority out of a disagreement, and
        # the count surfaces under the key name model_vs_human() already uses
        # (labels.py:1608) so the two tables' columns line up.
        self.assertEqual(block["no_consensus"], 1)
        self.assertEqual(out["no_consensus"], 1)
        # A human tie is not a missing score. Those are different failures.
        self.assertEqual(block["n_unscored"], 0)

    def test_an_all_abstain_item_is_counted_apart_from_an_unlabelled_one(self):
        # consensus() drops both into the same silence at labels.py:1481, which
        # is a real defect: "five Builders read this and none could tell" is
        # evidence about the POSTING, "nobody reached it" is evidence about the
        # NIGHT, and the module's own rule is that an abstention is a value and
        # is never folded away.
        set_rows = [_item("j1", "surfaced", match_score=90),
                    _item("j2", "surfaced", match_score=80),
                    _item("j3", "surfaced", match_score=70)]
        rows = [_b("j1", None, "alice"), _b("j1", None, "bob"),
                _b("j3", "yes", "alice")]
        out = labels.ordering(rows, set_rows, profile="pursuit")
        block = out["strata"]["surfaced"]
        self.assertEqual(block["all_abstained"], 1)
        self.assertEqual(block["unlabelled"], 1)
        self.assertEqual((out["all_abstained"], out["unlabelled"]), (1, 1))
        self.assertEqual(block["labelled"], 1)
        # And the function it is built on genuinely cannot tell them apart --
        # j1 is in neither return value, exactly like the row nobody opened.
        agreed, tied = labels.consensus(rows, axis=labels.AXIS_B)
        self.assertNotIn(("j1", labels.AXIS_B_FIELD, "pursuit"), agreed)
        self.assertEqual(tied, [])

    def test_an_unlabelled_member_is_not_a_score_drop(self):
        # Ranked.n_dropped means the RANKER produced no number (metrics.py:331)
        # and every drop there flatters the ranker. Booking a labelling
        # shortfall into it would be wrong in the flattering direction.
        set_rows = [_item("j1", "surfaced", match_score=90),
                    _item("j2", "surfaced", match_score=80)]
        block = labels.ordering([_b("j1", "yes", "alice")], set_rows,
                                profile="pursuit")["strata"]["surfaced"]
        self.assertEqual(block["n_unscored"], 0)
        self.assertTrue(block["complete"])
        # Two denominators, two keys, never one.
        self.assertEqual(block["coverage"], "1/1")        # the ranker's
        self.assertEqual(block["label_coverage"], "1/2")  # the night's
        self.assertEqual(block["unlabelled"], 1)

    def test_a_member_the_ranker_could_not_score_is_a_drop(self):
        # The other direction, and the reason the two numbers cannot be one:
        # here the label exists and the SCORE does not, which is what
        # n_unscored is for and is a pipeline finding rather than a turnout one.
        set_rows = [_item("j1", "surfaced", match_score=90),
                    _item("j2", "surfaced", match_score=None)]
        block = labels.ordering(
            [_b("j1", "yes", "alice"), _b("j2", "yes", "bob")], set_rows,
            profile="pursuit")["strata"]["surfaced"]
        self.assertEqual(block["n_unscored"], 1)
        self.assertEqual(block["n_unscored_positive"], 1)
        self.assertFalse(block["complete"])
        self.assertEqual(block["coverage"], "1/2")
        self.assertEqual(block["label_coverage"], "2/2")
        self.assertEqual(block["unlabelled"], 0)

    def test_score_ties_are_averaged_and_permuting_cannot_move_the_answer(self):
        # metrics.TIE_MODES: `expected` is the mean over every tie-break and is
        # the only one of the three that is a property of the RANKER rather
        # than of the sort. One positive somewhere inside a block of three
        # equal scores is the case where it matters.
        set_rows = [_item("j1", "surfaced", match_score=90),
                    _item("j2", "surfaced", match_score=90),
                    _item("j3", "surfaced", match_score=90),
                    _item("j4", "surfaced", match_score=50)]
        rows = [_b("j1", "yes", "alice"), _b("j2", "no", "alice"),
                _b("j3", "no", "alice"), _b("j4", "no", "alice")]
        block = labels.ordering(rows, set_rows,
                                profile="pursuit")["strata"]["surfaced"]
        self.assertAlmostEqual(block["average_precision"], 1 / 3 + 1 / 6 + 1 / 9)
        # The bounds are what a real sort could have produced; the point
        # estimate sits strictly between them, so the gap is visible.
        self.assertEqual(block["ap_optimistic"], 1.0)
        self.assertAlmostEqual(block["ap_pessimistic"], 1 / 3)
        self.assertEqual(block["ties"]["largest"], 3)
        self.assertAlmostEqual(block["ties"]["p_tie"], 0.5)
        # Permuting either input cannot move it. A job_id or position
        # tie-break would make both of these differ.
        for permuted in (list(reversed(rows)),
                         [rows[2], rows[0], rows[3], rows[1]]):
            other = labels.ordering(permuted, list(reversed(set_rows)),
                                    profile="pursuit")["strata"]["surfaced"]
            self.assertEqual(other["average_precision"],
                             block["average_precision"])
            self.assertEqual(other["precision_at_k"], block["precision_at_k"])

    def test_another_profile_s_answer_is_never_pooled_in(self):
        # match_score is keyed (job_id, profile) -- the property that makes
        # cost flat in users -- and _item_key() (labels.py:1329) puts the
        # profile in every axis-B key for the same reason. `tech` here answers
        # the exact inverse of `pursuit`; pooled, every item would be a tie and
        # there would be nothing left to rank.
        set_rows = [_item("j1", "surfaced", match_score=90),
                    _item("j2", "surfaced", match_score=50)]
        rows = [_b("j1", "no", "alice", profile="tech"),
                _b("j2", "yes", "alice", profile="tech"),
                _b("j1", "yes", "alice", profile="pursuit"),
                _b("j2", "no", "alice", profile="pursuit")]
        mine = labels.ordering(rows, set_rows,
                               profile="pursuit")["strata"]["surfaced"]
        theirs = labels.ordering(rows, set_rows,
                                 profile="tech")["strata"]["surfaced"]
        self.assertEqual(mine["labelled"], 2)
        self.assertEqual(mine["no_consensus"], 0)
        self.assertEqual(mine["average_precision"], 1.0)
        # Counted separately, against the same two scores, and not lost.
        self.assertEqual(theirs["labelled"], 2)
        self.assertEqual(theirs["average_precision"], 0.5)

    def test_a_round_two_answer_does_not_enter_a_round_one_figure(self):
        # Round 2 is the intra-annotator measurement -- the same postings a
        # week later (ROUND_TWO_DELAY_DAYS). Folding it in would count one
        # person twice and silently double the evidence under the figure.
        set_rows = [_item("j1", "surfaced", match_score=90),
                    _item("j2", "surfaced", match_score=50)]
        rows = [_b("j1", "no", "alice"), _b("j2", "yes", "alice"),
                _b("j1", "yes", "alice", round_no=2),
                _b("j2", "no", "alice", round_no=2)]
        one = labels.ordering(rows, set_rows, profile="pursuit")
        two = labels.ordering(rows, set_rows, profile="pursuit", round_no=2)
        self.assertEqual(one["strata"]["surfaced"]["average_precision"], 0.5)
        self.assertEqual(two["strata"]["surfaced"]["average_precision"], 1.0)
        # Two answers each, not four: neither figure borrowed the other's.
        self.assertEqual(one["strata"]["surfaced"]["labelled"], 2)
        self.assertEqual(two["strata"]["surfaced"]["labelled"], 2)
        # Which round a figure is over travels with it, so two dumps of these
        # blocks cannot be read as one.
        self.assertEqual((one["round"], two["round"]), (1, 2))

    def test_gate_rejected_is_refused_by_name_not_filtered_out(self):
        # Filtering would let a caller ask for "the whole set" and receive a
        # figure over three quarters of it -- a stratum measured against the
        # wrong population, trap 4.1 again.
        set_rows = [_item("g1", "gate_rejected"),
                    _item("j1", "surfaced", match_score=90)]
        with self.assertRaises(ValueError) as caught:
            labels.ordering([], set_rows, profile="pursuit",
                            strata=("surfaced", "gate_rejected"))
        message = str(caught.exception)
        self.assertIn("gate_rejected", message)
        self.assertIn("recall_bound", message)
        with self.assertRaises(ValueError):
            labels.score_index(set_rows, strata=("gate_rejected",))
        # An unknown stratum is refused too, rather than yielding an empty
        # block that reads as "nobody said yes".
        with self.assertRaises(ValueError):
            labels.ordering([], set_rows, profile="pursuit",
                            strata=("surfaced", "nonsense"))

    def test_below_floor_reads_computed_score_and_surfaced_match_score(self):
        # confirm_scores() recomputed `computed_score` with match.score_job(),
        # which is pure (match.py:73-84), so the two columns are one 0-100
        # construction under two names. Each row here carries a decoy in the
        # other column that would inverse the ordering if it were read.
        set_rows = [_item("j1", "surfaced", match_score=90, computed_score=1),
                    _item("j2", "surfaced", match_score=50, computed_score=99),
                    _item("j3", "below_floor", computed_score=30,
                          match_score=1),
                    _item("j4", "below_floor", computed_score=10,
                          match_score=99)]
        rows = [_b("j1", "yes", "alice"), _b("j2", "no", "alice"),
                _b("j3", "yes", "alice"), _b("j4", "no", "alice")]
        out = labels.ordering(rows, set_rows, profile="pursuit")
        self.assertEqual(out["strata"]["surfaced"]["score_column"],
                         "match_score")
        self.assertEqual(out["strata"]["below_floor"]["score_column"],
                         "computed_score")
        self.assertEqual(out["strata"]["surfaced"]["average_precision"], 1.0)
        self.assertEqual(out["strata"]["below_floor"]["average_precision"], 1.0)
        self.assertEqual(labels.score_index(set_rows),
                         {"j1": 90, "j2": 50, "j3": 30, "j4": 10})

    def test_an_explicit_score_map_wins_over_the_set_file(self):
        # platform_index()'s convention (labels.py:1269): a caller passing a
        # map is being specific on purpose -- a re-run of match.py, or a swept
        # weight table -- and must not be silently overridden by the file.
        set_rows = [_item("j1", "surfaced", match_score=90)]
        self.assertEqual(labels.score_index(set_rows, {"j1": 42}), {"j1": 42})
        # A None in the map is not an override to "unscored": absence of a
        # fresher number is not a claim that there is no number.
        self.assertEqual(labels.score_index(set_rows, {"j1": None}), {"j1": 90})

    def test_no_score_column_is_fit_score(self):
        # CLAUDE.md: `match_score` orders the list, `fit_score` only annotates
        # it, and LLMs explain, never rank. fit_score is also L1 -- the layer
        # tools/learned-ranker-probe.py already fits against -- so scoring an
        # L0 label against it would be evaluating on the trained layer.
        self.assertNotIn("fit_score", labels.SCORE_COLUMN.values())
        self.assertEqual(set(labels.SCORE_COLUMN), set(labels.SCORED_STRATA))
        self.assertNotIn("gate_rejected", labels.SCORED_STRATA)
        # Every scoreable stratum is a real stratum, and one is missing from
        # SCORED_STRATA on purpose.
        self.assertTrue(set(labels.SCORED_STRATA) < set(labels.STRATA))

    def test_the_two_strata_are_reported_apart_and_never_averaged(self):
        # The set is stratified 100/50/50 BY DESIGN, so neither prevalence is
        # the corpus's and their mean is a figure about no population at all.
        set_rows = [_item("j1", "surfaced", match_score=90),
                    _item("j2", "below_floor", computed_score=30)]
        rows = [_b("j1", "yes", "alice"), _b("j2", "yes", "alice")]
        out = labels.ordering(rows, set_rows, profile="pursuit")
        self.assertEqual(sorted(out["strata"]), ["below_floor", "surfaced"])
        for key in ("average_precision", "precision_at_k", "positive_rate",
                    "n_positive"):
            self.assertNotIn(key, out)

    def test_an_off_vocabulary_answer_is_refused_not_scored_as_a_no(self):
        # validate() confines the column to AXIS_B_VALUES, so a stray value
        # means a row reached eval_labels without going through record().
        # Scoring it 0 would move it into the negative class with no trace.
        set_rows = [_item("j1", "surfaced", match_score=90)]
        with self.assertRaises(ValueError):
            labels.ordering([_b("j1", "maybe", "alice")], set_rows,
                            profile="pursuit")

    def test_a_label_about_a_posting_outside_the_set_is_counted(self):
        # Silence is this system's failure mode. Labels collected against a
        # different set is the case where every figure is over the wrong rows.
        set_rows = [_item("j1", "surfaced", match_score=90)]
        out = labels.ordering(
            [_b("j1", "yes", "alice"), _b("stranger", "yes", "alice")],
            set_rows, profile="pursuit")
        self.assertEqual(out["labelled_not_in_set"], 1)
        self.assertEqual(out["strata"]["surfaced"]["labelled"], 1)


class TestTheRecallBound(unittest.TestCase):
    """The one statement `gate_rejected` can make, and it is not a rate."""

    def test_it_is_a_count_with_an_interval_and_not_a_rate(self):
        set_rows = [_item(f"g{i}", "gate_rejected") for i in range(1, 5)]
        rows = [_b("g1", "yes", "alice"), _b("g2", "no", "alice"),
                _b("g3", "no", "alice"), _b("g4", "no", "alice")]
        block = labels.recall_bound(rows, set_rows, profile="pursuit")
        self.assertEqual((block["k"], block["n"], block["members"]), (1, 4, 4))
        lo, hi = block["ci"]
        self.assertLess(lo, 0.25)
        self.assertGreater(hi, 0.25)
        # There is deliberately no key a report could print as precision.
        for forbidden in ("rate", "average_precision", "precision_at_k",
                          "positive_rate", "score_column"):
            self.assertNotIn(forbidden, block)
        self.assertIn("never a precision rate", block["statement"])

    def test_it_is_computed_always_and_merged_into_nothing(self):
        # A `yes` on a gate-rejected posting is not a precision miss: the
        # profile's users can never see it, so nothing was ranked wrongly.
        set_rows = [_item("g1", "gate_rejected"),
                    _item("j1", "surfaced", match_score=90)]
        rows = [_b("g1", "yes", "alice"), _b("j1", "no", "alice")]
        out = labels.ordering(rows, set_rows, profile="pursuit")
        self.assertEqual(out["recall_bound"]["k"], 1)
        self.assertNotIn("gate_rejected", out["strata"])
        # The surfaced figure is over its own 1 member, not over 2.
        self.assertEqual(out["strata"]["surfaced"]["members"], 1)
        self.assertEqual(out["strata"]["surfaced"]["n_positive"], 0)
        # ... and the gate-rejected yes did not become a surfaced positive.
        self.assertEqual(out["strata"]["surfaced"]["labelled"], 1)

    def test_its_denominator_is_what_was_answered_not_the_stratum_size(self):
        # The two are the same 50 when the night finishes the stratum. When it
        # does not, the shortfall belongs beside the interval, not inside it.
        set_rows = [_item(f"g{i}", "gate_rejected") for i in range(1, 5)]
        rows = [_b("g1", "yes", "alice"), _b("g2", None, "alice")]
        block = labels.recall_bound(rows, set_rows, profile="pursuit")
        self.assertEqual((block["k"], block["n"]), (1, 1))
        self.assertEqual(block["label_coverage"], "1/4")
        self.assertEqual(block["all_abstained"], 1)
        self.assertEqual(block["unlabelled"], 2)

    def test_another_profile_s_yes_is_not_this_profile_s_recall_miss(self):
        # A posting `tech` would apply to says nothing about what `pursuit`'s
        # gate is discarding from `pursuit`'s users.
        set_rows = [_item("g1", "gate_rejected")]
        rows = [_b("g1", "yes", "alice", profile="tech")]
        block = labels.recall_bound(rows, set_rows, profile="pursuit")
        self.assertEqual((block["k"], block["n"], block["unlabelled"]),
                         (0, 0, 1))


class TestThePinnedSetCarriesItsOwnScoreAxis(unittest.TestCase):
    """No database read is needed to join axis B to match_score.

    The set file records both score columns (save_set(), labels.py:770-772), so
    the join is a pure function over a fixture. That is what lets the adapter be
    built and tested before the labelling night, and it is also the only way the
    figure is reproducible: match.py re-ranks nightly, so a score read live
    would pair a sampling-time stratum with a report-time number.
    """

    def setUp(self):
        self.set_rows = labels.load_set(PURSUIT_V1)

    def test_the_set_is_pinned_by_its_sorted_job_ids(self):
        self.assertEqual(len(self.set_rows), 200)
        self.assertEqual(labels.digest(self.set_rows), PURSUIT_V1_SHA)

    def test_every_scoreable_row_has_its_own_column_and_no_other(self):
        by_stratum = {}
        for row in self.set_rows:
            by_stratum.setdefault(row["stratum"], []).append(row)
        self.assertEqual(
            {s: len(rs) for s, rs in sorted(by_stratum.items())},
            {"below_floor": 50, "gate_rejected": 50, "surfaced": 100})
        for stratum, column in labels.SCORE_COLUMN.items():
            rows = by_stratum[stratum]
            self.assertTrue(all(r[column] is not None for r in rows), stratum)
            other = ("computed_score" if column == "match_score"
                     else "match_score")
            self.assertTrue(all(r[other] is None for r in rows), stratum)
        # And gate_rejected has neither, on any scale, which is why it is
        # refused rather than filtered.
        for row in by_stratum["gate_rejected"]:
            self.assertIsNone(row["match_score"])
            self.assertIsNone(row["computed_score"])

    def test_score_index_covers_both_scoreable_strata_and_nothing_else(self):
        index = labels.score_index(self.set_rows)
        self.assertEqual(len(index), 150)
        gate = {str(r["job_id"]) for r in self.set_rows
                if r["stratum"] == "gate_rejected"}
        self.assertEqual(gate & set(index), set())
        # The two windows on one construction: 40-92 above the floor
        # (schema.MATCH_FLOOR is 40) and 0-34 below it.
        surfaced = [index[str(r["job_id"])] for r in self.set_rows
                    if r["stratum"] == "surfaced"]
        below = [index[str(r["job_id"])] for r in self.set_rows
                 if r["stratum"] == "below_floor"]
        self.assertEqual((min(surfaced), max(surfaced)), (40, 92))
        self.assertEqual((min(below), max(below)), (0, 34))

    def test_the_whole_join_runs_with_no_label_and_reports_zero_coverage(self):
        # The state on the morning of the labelling night: the adapter must
        # already run, and it must say the set is unlabelled rather than
        # producing a figure over nothing.
        out = labels.ordering([], self.set_rows, profile="pursuit")
        self.assertEqual(out["unlabelled"], 150)
        self.assertEqual(out["all_abstained"], 0)
        self.assertEqual(out["recall_bound"]["unlabelled"], 50)
        for stratum, block in out["strata"].items():
            self.assertIsNone(block["average_precision"], stratum)
            self.assertEqual(block["labelled"], 0, stratum)
            self.assertEqual(block["n_unscored"], 0, stratum)


if __name__ == "__main__":
    unittest.main()

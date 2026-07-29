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
        # than with Postgres hashtext().
        for size in (1, 2, 7, 190):
            for who in ("alice", "bob", "u_090b0ad12e99", ""):
                off = labels.tail_offset(who, size)
                self.assertGreaterEqual(off, 0)
                self.assertLess(off, size)
                self.assertEqual(off, labels.tail_offset(who, size))
        self.assertEqual(labels.tail_offset("alice", 0), 0)
        spread = {labels.tail_offset(f"builder{i:02d}", 190)
                  for i in range(10)}
        self.assertGreater(len(spread), 1)

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
                 "jobs_app")

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
        self.assertEqual(code.count("FROM"), 2,
                         "two queries: the posting, and its membership of the "
                         "eval set. A third is a change to what a labeller "
                         "can be shown.")

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
        self.assertEqual(args, ["job", "question_list", "label_set", "done",
                                "total", "overlap"])
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
        # reopens it must not be re-seated somewhere else in the tail, and the
        # set's coverage has to be reproducible from the labeller ids alone.
        # sha256, not hash(): PYTHONHASHSEED randomises str hashing per
        # process, so hash() would reshuffle the same person on every request.
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


if __name__ == "__main__":
    unittest.main()

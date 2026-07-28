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

import json
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from evals import labels, report, scratchdb           # noqa: E402
from evals.tasks import extract as extract_task       # noqa: E402
from lib import envfile                               # noqa: E402

#: The pipeline's own .env, the way run-daily.py and tests/test_scratchdb.py
#: load it. Tests must not depend on the caller having exported anything.
envfile.load(os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), ".env"))


def _label(job_id, field, value, who, *, axis=labels.AXIS_A, round_no=1,
           profile=None):
    return {"axis": axis, "label_set": "s", "job_id": job_id, "field": field,
            "value": value, "profile": profile, "labeller_id": who,
            "round_no": round_no, "labelled_at": "2026-07-28T00:00:00",
            "note": None}


def _cell(n, agree2):
    return {"n": n, "agree2": agree2, "agree2_ci": (0.0, 1.0)}


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
        self.assertEqual(
            labels.next_item(self.conn, "s", "alice")["job_id"], "a")
        # A different person still gets the shared row first: that is what
        # makes the two of them comparable at all.
        self.assertEqual(
            labels.next_item(self.conn, "s", "bob")["job_id"], "b")

    def test_verify_schema_names_a_missing_table(self):
        problems = labels.verify_schema(
            self.conn, privileges={"eval_labels_nope": ("SELECT",)},
            sequences={})
        self.assertEqual(len(problems), 1)
        self.assertIn("missing", problems[0])


if __name__ == "__main__":
    unittest.main()

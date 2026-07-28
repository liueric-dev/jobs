"""Unit tests for the rules matcher.

Run:  python3 tests/test_match.py

stdlib unittest -- pytest is not installed and is not
worth a dependency here.

WHY THESE TESTS AND NOT OTHERS
    score_job is pure, so it can be pinned exactly. The properties worth
    pinning are the ones whose violation would be silent in production:

      * a hard exclude must short-circuit to 0 no matter how many bonuses
        the posting would otherwise collect -- a research role that happens
        to name Python must not out-rank a genuine fit;
      * the reasons must sum to the score, because they are the only
        explanation anyone will ever get and a reason list that does not
        reconcile is worse than none;
      * the score must stay inside 0..100, since the surfacing layer and
        calibrate-match.py both assume that range.
"""

import json
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import match  # noqa: E402

CRITERIA = {
    "base": 35,
    "archetypes": {"forward_deployed": 28, "ai_integration": 22,
                   "fullstack": 15, "ml_research": -100},
    "seniority": {"target": ["mid"], "tolerate": {"senior": -8},
                  "hard_exclude": ["intern", "principal"],
                  "penalty_per_level": 12, "unknown_penalty": -4},
    "years_experience": {"max_required": 6, "over_penalty_per_year": 8,
                         "over_penalty_cap": 32},
    "tech": {"boost": {"python": 6, "typescript": 5, "rag": 6}, "cap": 12},
    "ai_involvement": {"builds_llm_features": 12, "core_ml_research": -60},
    "location": {"accept_nyc": True, "accept_remote": True,
                 "neither_penalty": -45, "onsite_elsewhere_penalty": -55},
    "flags": {"gap_friendly_language": 10, "customer_facing": 8,
              "advanced_degree_required": -45, "ml_research_required": -100},
}


#: CRITERIA with every missingness price set, and each one a DIFFERENT number
#: so an assertion cannot pass by hitting the wrong rule. The magnitudes are
#: not config/criteria.json's -- that file prices tech_stack and remote_policy
#: at 0 on purpose, which would leave those two code paths unexercised here.
#: "none" is added to the ai_involvement map because the default facts() carry
#: it and it would otherwise read as an unpriced value in every test below.
MISSING_PENALTIES = {
    "years_experience_min": -2,
    "role_archetype": -6,
    "ai_involvement": -4,
    "tech_stack": -3,
    "remote_policy": -1,
    "gap_friendly_language": -7,
    "customer_facing": -9,
    "advanced_degree_required": -6,
    "ml_research_required": -11,
}

MISS_CRITERIA = dict(
    CRITERIA,
    ai_involvement=dict(CRITERIA["ai_involvement"], none=0),
    unknown_penalty=MISSING_PENALTIES,
)

#: base 35 + fullstack 15, with every other rule silent.
ON_TARGET = 50


def facts(**over):
    base = {
        "seniority_level": "mid", "years_experience_min": 3,
        "role_archetype": "fullstack", "tech_stack": [],
        "ai_involvement": "none", "ml_research_required": False,
        "advanced_degree_required": False, "customer_facing": False,
        "remote_policy": "hybrid", "gap_friendly_language": False,
        "location_is_nyc": True, "location_is_remote": False,
    }
    base.update(over)
    return base


class TestHardExclude(unittest.TestCase):
    def test_seniority_exclusion_wins_over_every_bonus(self):
        score, reasons = match.score_job(
            facts(seniority_level="principal", role_archetype="forward_deployed",
                  tech_stack=["python", "typescript", "rag"],
                  ai_involvement="builds_llm_features",
                  gap_friendly_language=True, customer_facing=True),
            CRITERIA)
        self.assertEqual(score, 0)
        self.assertIn("seniority:principal:excluded",
                      [r["rule"] for r in reasons])

    def test_archetype_exclusion_short_circuits(self):
        score, _ = match.score_job(
            facts(role_archetype="ml_research", tech_stack=["python"]), CRITERIA)
        self.assertEqual(score, 0)

    def test_flag_exclusion_short_circuits(self):
        score, _ = match.score_job(
            facts(role_archetype="forward_deployed", ml_research_required=True),
            CRITERIA)
        self.assertEqual(score, 0)

    def test_a_hard_exclude_stops_later_rules_being_credited(self):
        """The short-circuit must not merely subtract 100 and continue --
        otherwise enough bonuses could climb back above the floor."""
        _, reasons = match.score_job(
            facts(role_archetype="ml_research", gap_friendly_language=True),
            CRITERIA)
        self.assertNotIn("flag:gap_friendly_language",
                         [r["rule"] for r in reasons])


class TestArithmetic(unittest.TestCase):
    def test_reasons_sum_to_score(self):
        for f in (facts(),
                  facts(seniority_level="senior", years_experience_min=9),
                  facts(role_archetype="forward_deployed", customer_facing=True,
                        tech_stack=["python", "rag"]),
                  facts(location_is_nyc=False, remote_policy="onsite"),
                  facts(seniority_level=None)):
            score, reasons = match.score_job(f, CRITERIA)
            self.assertEqual(score, match._clamp(sum(r["delta"] for r in reasons)),
                             f"reasons do not reconcile for {f}")

    def test_on_target_seniority_costs_nothing(self):
        score, _ = match.score_job(facts(seniority_level="mid"), CRITERIA)
        self.assertEqual(score, 35 + 15)  # base + fullstack

    def test_tolerated_seniority_uses_its_named_penalty(self):
        score, _ = match.score_job(facts(seniority_level="senior"), CRITERIA)
        self.assertEqual(score, 35 + 15 - 8)

    def test_unlisted_seniority_falls_back_to_distance(self):
        # staff is 2 levels above mid, and is neither targeted nor tolerated
        score, reasons = match.score_job(facts(seniority_level="staff"), CRITERIA)
        self.assertEqual(score, 35 + 15 - 24)
        self.assertIn("seniority:staff:2_levels_off",
                      [r["rule"] for r in reasons])

    def test_years_penalty_is_capped(self):
        score, _ = match.score_job(facts(years_experience_min=40), CRITERIA)
        # 34 years over * 8 would be 272; the cap is 32
        self.assertEqual(score, 35 + 15 - 32)

    def test_tech_boost_is_capped(self):
        score, _ = match.score_job(
            facts(tech_stack=["python", "typescript", "rag"]), CRITERIA)
        self.assertEqual(score, 35 + 15 + 12)  # 6+5+6=17, capped to 12

    def test_tech_matches_on_substring(self):
        score, _ = match.score_job(facts(tech_stack=["node.js", "python3"]),
                                   CRITERIA)
        self.assertEqual(score, 35 + 15 + 6)

    def test_score_is_clamped_to_range(self):
        generous = dict(CRITERIA, base=95)
        score, _ = match.score_job(
            facts(role_archetype="forward_deployed", customer_facing=True,
                  gap_friendly_language=True), generous)
        self.assertEqual(score, 100)

        harsh = dict(CRITERIA, base=0)
        score, _ = match.score_job(
            facts(location_is_nyc=False, remote_policy="onsite",
                  advanced_degree_required=True), harsh)
        self.assertEqual(score, 0)


class TestLocation(unittest.TestCase):
    def test_nyc_is_accepted_without_penalty(self):
        score, reasons = match.score_job(facts(location_is_nyc=True), CRITERIA)
        self.assertNotIn("location:unmatched", [r["rule"] for r in reasons])

    def test_remote_is_accepted_without_penalty(self):
        score, reasons = match.score_job(
            facts(location_is_nyc=False, location_is_remote=True), CRITERIA)
        self.assertNotIn("location:unmatched", [r["rule"] for r in reasons])

    def test_onsite_elsewhere_is_penalised_harder_than_unknown(self):
        elsewhere, _ = match.score_job(
            facts(location_is_nyc=False, remote_policy="onsite"), CRITERIA)
        unknown, _ = match.score_job(
            facts(location_is_nyc=False, remote_policy="unknown"), CRITERIA)
        self.assertLess(elsewhere, unknown)


class TestMissingness(unittest.TestCase):
    """Every nullable field must cost something and say so.

    The bug these pin: a field the extractor could not answer used to fall
    through with no delta and no reason, which scores identically to a field
    that genuinely matched -- so the ranking rewarded the postings extraction
    did worst on. Each test therefore asserts BOTH halves: the delta lands,
    and `missing` does not equal `on target`.
    """

    def rules(self, f, criteria=None):
        _, reasons = match.score_job(f, criteria or MISS_CRITERIA)
        return [r["rule"] for r in reasons]

    def test_baseline_is_what_the_deltas_are_measured_against(self):
        score, _ = match.score_job(facts(), MISS_CRITERIA)
        self.assertEqual(score, ON_TARGET)

    # -- one per nullable field --------------------------------------------

    def test_missing_years_experience(self):
        score, _ = match.score_job(facts(years_experience_min=None),
                                   MISS_CRITERIA)
        self.assertEqual(score, ON_TARGET - 2)
        self.assertIn("years:missing", self.rules(facts(years_experience_min=None)))
        # A stated, satisfiable requirement is free; not knowing is not.
        known, _ = match.score_job(facts(years_experience_min=3), MISS_CRITERIA)
        self.assertNotEqual(score, known)

    def test_missing_archetype(self):
        score, _ = match.score_job(facts(role_archetype=None), MISS_CRITERIA)
        self.assertEqual(score, 35 - 6)  # base, no archetype credit, minus the price
        self.assertIn("archetype:missing", self.rules(facts(role_archetype=None)))
        self.assertNotEqual(score, ON_TARGET)

    def test_unpriced_archetype_is_not_silently_free(self):
        """The superset in section 1 of task 11 adds values an un-bumped
        criteria_json will not name -- the same silent zero _staff_comment
        documents for seniority."""
        f = facts(role_archetype="ai_operations")
        score, _ = match.score_job(f, MISS_CRITERIA)
        self.assertEqual(score, 35 - 6)
        self.assertIn("archetype:ai_operations:unpriced", self.rules(f))

    def test_missing_ai_involvement(self):
        f = facts(ai_involvement=None)
        score, _ = match.score_job(f, MISS_CRITERIA)
        self.assertEqual(score, ON_TARGET - 4)
        self.assertIn("ai:missing", self.rules(f))
        on_target, _ = match.score_job(
            facts(ai_involvement="builds_llm_features"), MISS_CRITERIA)
        self.assertNotEqual(score, on_target)

    def test_unpriced_ai_involvement_is_not_silently_free(self):
        f = facts(ai_involvement="uses_ai_tools")  # absent from this map
        score, _ = match.score_job(f, MISS_CRITERIA)
        self.assertEqual(score, ON_TARGET - 4)
        self.assertIn("ai:uses_ai_tools:unpriced", self.rules(f))

    def test_missing_tech_stack_is_not_an_empty_tech_stack(self):
        """criteria.json:44 records that absence is never penalised for this
        persona. That decision is about [] -- the extractor answering 'no
        technologies named' -- and is preserved by pricing NULL at 0 there,
        not by refusing to tell the two states apart."""
        empty, _ = match.score_job(facts(tech_stack=[]), MISS_CRITERIA)
        null, _ = match.score_job(facts(tech_stack=None), MISS_CRITERIA)
        self.assertEqual(empty, ON_TARGET)
        self.assertEqual(null, ON_TARGET - 3)
        self.assertNotIn("tech:missing", self.rules(facts(tech_stack=[])))
        self.assertIn("tech:missing", self.rules(facts(tech_stack=None)))

    def test_missing_remote_policy_is_charged_only_where_it_was_consulted(self):
        """Not double-charged: location:unmatched already prices 'we could not
        classify this', so remote:missing rides alongside it and appears at
        all only where the location booleans failed to resolve the posting."""
        unresolved = facts(location_is_nyc=False, location_is_remote=False,
                           remote_policy=None)
        score, _ = match.score_job(unresolved, MISS_CRITERIA)
        self.assertEqual(score, ON_TARGET - 45 - 1)
        self.assertIn("remote:missing", self.rules(unresolved))
        # ... and is strictly worse than a policy we could read.
        hybrid, _ = match.score_job(dict(unresolved, remote_policy="hybrid"),
                                    MISS_CRITERIA)
        self.assertLess(score, hybrid)

    def test_missing_remote_policy_is_free_when_location_already_resolved(self):
        f = facts(location_is_nyc=True, remote_policy=None)
        score, _ = match.score_job(f, MISS_CRITERIA)
        self.assertEqual(score, ON_TARGET)
        self.assertNotIn("remote:missing", self.rules(f))

    def test_missing_gap_friendly_language(self):
        f = facts(gap_friendly_language=None)
        score, _ = match.score_job(f, MISS_CRITERIA)
        self.assertEqual(score, ON_TARGET - 7)
        self.assertIn("flag:gap_friendly_language:missing", self.rules(f))

    def test_missing_customer_facing(self):
        f = facts(customer_facing=None)
        score, _ = match.score_job(f, MISS_CRITERIA)
        self.assertEqual(score, ON_TARGET - 9)
        self.assertIn("flag:customer_facing:missing", self.rules(f))

    def test_missing_advanced_degree_required(self):
        f = facts(advanced_degree_required=None)
        score, _ = match.score_job(f, MISS_CRITERIA)
        self.assertEqual(score, ON_TARGET - 6)
        self.assertIn("flag:advanced_degree_required:missing", self.rules(f))

    def test_missing_ml_research_required(self):
        f = facts(ml_research_required=None)
        score, _ = match.score_job(f, MISS_CRITERIA)
        self.assertEqual(score, ON_TARGET - 11)
        self.assertIn("flag:ml_research_required:missing", self.rules(f))

    def test_a_boolean_flag_has_three_states_not_two(self):
        """None used to be indistinguishable from False -- so a posting whose
        disqualifying flags could not be read scored as though clear."""
        true_, _ = match.score_job(facts(gap_friendly_language=True),
                                   MISS_CRITERIA)
        false_, _ = match.score_job(facts(gap_friendly_language=False),
                                    MISS_CRITERIA)
        null, _ = match.score_job(facts(gap_friendly_language=None),
                                  MISS_CRITERIA)
        self.assertEqual(len({true_, false_, null}), 3)

    def test_missingness_never_hard_excludes(self):
        """ml_research_required is a -100. Not knowing it must not disqualify:
        an extraction failure would then delete the posting outright, which is
        a worse version of the bias this whole block removes."""
        excluded, _ = match.score_job(facts(ml_research_required=True),
                                      MISS_CRITERIA)
        unknown, _ = match.score_job(facts(ml_research_required=None),
                                     MISS_CRITERIA)
        self.assertEqual(excluded, 0)
        self.assertGreater(unknown, 0)

    def test_hard_exclude_short_circuit_is_unperturbed(self):
        """The seniority exclude returns before every other rule, so no
        missingness reason may appear beside it."""
        score, reasons = match.score_job(
            facts(seniority_level="principal", role_archetype=None,
                  years_experience_min=None, ai_involvement=None,
                  tech_stack=None, ml_research_required=None),
            MISS_CRITERIA)
        self.assertEqual(score, 0)
        self.assertEqual([r["rule"] for r in reasons],
                         ["base", "seniority:principal:excluded"])

    def test_seniority_reads_the_block_only_as_a_fallback(self):
        """Live profiles carry seniority's price inside its own block; the
        shared block must not quietly override it."""
        own = dict(MISS_CRITERIA,
                   unknown_penalty=dict(MISSING_PENALTIES, seniority_level=-30))
        score, _ = match.score_job(facts(seniority_level=None), own)
        self.assertEqual(score, ON_TARGET - 4)  # its own -4 wins

        no_own = dict(own, seniority={k: v
                                      for k, v in CRITERIA["seniority"].items()
                                      if k != "unknown_penalty"})
        score, reasons = match.score_job(facts(seniority_level=None), no_own)
        self.assertEqual(score, ON_TARGET - 30)
        self.assertIn("seniority:unknown", [r["rule"] for r in reasons])

    # -- the change is inert until criteria_version is bumped ---------------

    def test_criteria_without_unknown_penalties_is_unchanged(self):
        """CRITERIA carries no unknown_penalty block, exactly like every live
        profile until migrate_profiles.py --apply --bump runs. Every nullable
        field is NULL here and the reason list must still be the pre-change
        one -- no new entries, no new deltas."""
        _, reasons = match.score_job(
            {k: None for k in facts()} | {"seniority_level": None}, CRITERIA)
        self.assertEqual(reasons, [{"rule": "base", "delta": 35},
                                   {"rule": "seniority:unknown", "delta": -4},
                                   {"rule": "location:unmatched", "delta": -45}])

    def test_reasons_still_sum_to_score_with_missingness(self):
        for f in (facts(role_archetype=None),
                  facts(years_experience_min=None, ai_involvement=None),
                  facts(tech_stack=None, customer_facing=None),
                  facts(location_is_nyc=False, remote_policy=None),
                  {k: None for k in facts()}):
            score, reasons = match.score_job(f, MISS_CRITERIA)
            self.assertEqual(score, match._clamp(sum(r["delta"] for r in reasons)),
                             f"reasons do not reconcile for {f}")

    def test_missingness_reasons_are_json_serialisable(self):
        _, reasons = match.score_job({k: None for k in facts()}, MISS_CRITERIA)
        json.loads(json.dumps(reasons))


class TestDegenerateInputs(unittest.TestCase):
    def test_empty_criteria_does_not_crash(self):
        score, reasons = match.score_job(facts(), {})
        self.assertEqual(score, 0)
        self.assertEqual(reasons, [{"rule": "base", "delta": 0}])

    def test_all_null_facts_do_not_crash(self):
        empty = {k: None for k in facts()}
        empty["tech_stack"] = []
        score, _ = match.score_job(empty, CRITERIA)
        self.assertIsInstance(score, int)

    def test_reasons_are_json_serialisable(self):
        _, reasons = match.score_job(facts(seniority_level="staff"), CRITERIA)
        json.loads(json.dumps(reasons))


if __name__ == "__main__":
    unittest.main(verbosity=2)

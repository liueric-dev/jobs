"""Unit tests for the rules matcher.

Run:  python3 jobs/tests/test_match.py

stdlib unittest, same as pipelib/tests -- pytest is not installed and is not
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
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))))

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

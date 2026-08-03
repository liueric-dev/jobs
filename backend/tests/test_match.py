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

import collections
import contextlib
import importlib
import inspect
import io
import json
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import extract  # noqa: E402  (D13 -- the vocabulary match.py must cover)
import match  # noqa: E402
import schema  # noqa: E402
from evals import scratchdb  # noqa: E402
from lib import envfile  # noqa: E402

#: The pipeline's own .env, so the D11 database tests run in an ordinary
#: checkout rather than skipping. Same reason tests/test_nyc_open_data.py
#: does it: a test must not depend on the caller having exported anything.
envfile.load(os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), ".env"))

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


#: The cohort profile's weights and the two frozen eval sets that pin them.
#: Read from disk rather than duplicated here on purpose: config/pursuit-criteria.json
#: is what migrate_profiles.py imports, so a test that copied the numbers would
#: keep passing after someone edited the file the pipeline actually reads.
_BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PURSUIT_CRITERIA_FILE = os.path.join(_BACKEND, "config", "pursuit-criteria.json")
PURSUIT_GOLDENS_FILE = os.path.join(
    _BACKEND, "evals", "fixtures", "pursuit-criteria-goldens.json")
PURSUIT_CORPUS_FILE = os.path.join(
    _BACKEND, "evals", "fixtures", "pursuit-criteria-corpus.jsonl")


def _load_json(path):
    with open(path) as f:
        return json.load(f)


def _pursuit_criteria():
    """The file as match.py would see it, i.e. with the documentation stripped.

    Same transformation migrations/migrate_profiles.py:strip_comments applies
    before the config reaches the database, so the numbers under test are the
    ones that would actually rank.
    """
    return {k: v for k, v in _load_json(PURSUIT_CRITERIA_FILE).items()
            if not k.startswith("_")}


class TestPursuitCriteriaComments(unittest.TestCase):
    """Every weight block carries a `_comment`. Task 13's DoD line 126.

    CLAUDE.md calls these load-bearing documentation, and the failure mode is
    not that someone deletes one -- it is that someone ADDS a weight block and
    does not write one, at which point the file has a number nobody can trace.
    So the assertion walks the file's own top-level keys rather than a list
    written here, which would go stale the moment the config grew.
    """

    def setUp(self):
        self.cfg = _load_json(PURSUIT_CRITERIA_FILE)

    def test_every_weight_block_has_a_comment(self):
        blocks = [k for k in self.cfg if not k.startswith("_")]
        self.assertTrue(blocks, "the config has no weight blocks at all")
        for name in blocks:
            # Any _-prefixed sibling naming the block counts: several blocks
            # need more than one comment (_seniority_comment plus
            # _seniority_hard_exclude_comment), and requiring exactly
            # `_{name}_comment` would push the extra prose somewhere worse.
            siblings = [k for k in self.cfg
                        if k.startswith("_") and name in k]
            self.assertTrue(
                siblings,
                f"criteria block {name!r} has no _comment. Every weight gets "
                f"one -- see CLAUDE.md, Conventions.")

    def test_the_stale_self_agreement_figures_are_not_reimported(self):
        """DoD line 127. config/criteria.json's _hard_exclude_comment used to
        justify its penalty design with 95% / 90% self-agreement figures from
        tools/compare-extract.py. Task 06 measured neither: seniority_level is
        85.2% and role_archetype 84.3% at n=115. The correction landed in the
        author's file; the obligation here is not to copy the dead numbers
        into a new one."""
        prose = " ".join(v for k, v in self.cfg.items()
                         if k.startswith("_") and isinstance(v, str))
        for stale in ("95%", "90%"):
            self.assertNotIn(stale, prose,
                             f"{stale} self-agreement is superseded -- the live "
                             f"figure is 85.2% agree2 on seniority_level, from "
                             f"evals/fixtures/results/selfcheck-n120-2026-07-28.json")
        self.assertIn("85.2%", prose)

    def test_every_archetype_in_the_extractor_vocabulary_is_priced(self):
        """An omission is not a neutral zero: match.py:180-191 charges an
        unnamed value unknown_penalty.role_archetype down the
        `archetype:{v}:unpriced` path. Imported from extract rather than
        listed here so adding a value to the vocabulary fails this test."""
        import extract
        priced = set(self.cfg["archetypes"])
        self.assertEqual(set(extract.ARCHETYPE), priced,
                         "archetypes must price extract.ARCHETYPE exactly")


class TestPursuitGoldens(unittest.TestCase):
    """Task 13's DoD lines 122-124, against frozen fixtures.

    OFFLINE BY CONSTRUCTION. The corpus is the 859 job_facts rows the cohort
    gate admits as of 2026-07-28, frozen to JSONL, so these assertions do not
    read the database -- which matters because the repo owner's operating
    stance is that database contents are staging data. A test that scored the
    live table would fail on a re-extraction rather than on a weight change,
    and that is not hypothetical: task 35 (`303f7b9`) deleted four of this
    corpus's rows mid-task-13 for being browser-DOM markup rather than job
    postings. Freezing is what made that a deliberate re-pin instead of a
    mystery failure.

    THE LISTS WERE PICKED ON TITLE, COMPANY AND LOCATION, BEFORE ANY SCORE
    EXISTED. score_job() reads none of those three, so this is the one
    non-circular check available. The fixture's own _selection_method and
    _measured_2026_07_28 record the method and, more importantly, the two
    numbers that came in BELOW what the task file asks for.
    """

    @classmethod
    def setUpClass(cls):
        cls.criteria = _pursuit_criteria()
        cls.goldens = _load_json(PURSUIT_GOLDENS_FILE)
        with open(PURSUIT_CORPUS_FILE) as f:
            cls.corpus = [json.loads(line) for line in f if line.strip()]
        scored = sorted(
            ((match.score_job(facts_, cls.criteria)[0], facts_["job_id"])
             for facts_ in cls.corpus),
            key=lambda pair: (-pair[0], pair[1]))
        cls.score = {job_id: s for s, job_id in scored}
        cls.rank = {job_id: i + 1 for i, (_, job_id) in enumerate(scored)}
        cls.floor = cls.goldens["match_floor"]

    def test_the_fixture_matches_the_corpus_it_was_pinned_against(self):
        self.assertEqual(len(self.corpus), self.goldens["corpus_rows"])
        self.assertEqual(len({r["job_id"] for r in self.corpus}),
                         len(self.corpus), "duplicate job_id in the corpus")

    #: The four postings task 35 (`303f7b9`) removed for being browser-DOM
    #: markup rather than job postings. Named here, not counted, because a
    #: count cannot tell "regenerated from the live corpus" from "restored
    #: from the pre-remediation snapshot and coincidentally the same size".
    REMEDIATED = (
        "1074b7f0354bc3cceed49194", "53cbf3ae21a12bff1ff73476",
        "7bdfba1a4e254be44463737c", "ff9f9d9f9643e185af0f48ca",
    )

    def test_the_remediated_markup_rows_are_gone_and_stay_gone(self):
        """Their facts were derived from a scraped ChatGPT web UI and from a
        staffing firm's navigation menu. Regenerating this fixture from a
        stale snapshot would put them back, and they would score and rank
        like real postings -- one of them cleared the floor at rank 126."""
        present = set(self.score) & set(self.REMEDIATED)
        self.assertFalse(
            present,
            f"markup rows are back in the corpus: {sorted(present)}. "
            f"Regenerate from the live gate, not from an old snapshot.")

    def test_both_lists_are_pinned_by_sorted_job_id(self):
        """CLAUDE.md: pin eval sets by sorted job_id. Sorted order is what
        makes 'is this the same eval set' answerable by eye in a diff."""
        for key in ("target_roles", "senior_software_roles"):
            ids = [r["job_id"] for r in self.goldens[key]]
            self.assertEqual(ids, sorted(ids), f"{key} is not sorted")
            self.assertEqual(len(ids), len(set(ids)), f"{key} has duplicates")
            for job_id in ids:
                self.assertIn(job_id, self.score,
                              f"{job_id} is not in the frozen corpus")

    def test_ten_senior_software_roles_are_below_the_floor(self):
        """DoD line 124, and the only one of the three met in full."""
        rows = self.goldens["senior_software_roles"]
        self.assertEqual(len(rows), 10)
        for r in rows:
            self.assertLess(
                self.score[r["job_id"]], self.floor,
                f"{r['title']} ({r['company']}) scores "
                f"{self.score[r['job_id']]} >= floor {self.floor}")

    def test_target_roles_clear_the_floor_at_the_pinned_rate(self):
        """DoD line 122 asks for 20 of 20 and the measured answer is 16.

        Asserted as a floor rather than as 20 because the four misses were
        diagnosed and NOT tuned away -- three of them carry
        ai_involvement = 'none' and are arguably correct rejections of
        postings that read AI-adjacent only because the employer is an AI
        company. Raising a weight until this reads 20/20 would be fitting to
        a twenty-row eval, which CLAUDE.md forbids twice over. The number is
        here so a change that makes it WORSE is caught; task 29's labels are
        what should decide whether 16 is the right answer.
        """
        rows = self.goldens["target_roles"]
        self.assertEqual(len(rows), 20)
        above = [r for r in rows if self.score[r["job_id"]] >= self.floor]
        self.assertGreaterEqual(
            len(above), 16,
            "hand-picked target roles above MATCH_FLOOR fell below the "
            "pinned 16 of 20")

    def test_target_roles_in_the_top_twenty_at_the_pinned_rate(self):
        """DoD line 123, same shape as above: 10 of 20 measured against 20 of
        20 asked for. This one is precision@20 read from the other side -- of
        the ranking's top 20, half are on a list drawn up without seeing it.
        CLAUDE.md is explicit that a count of twenty cannot resolve the
        differences being decided on, so it is a regression floor and not a
        quality claim."""
        rows = self.goldens["target_roles"]
        in_top = [r for r in rows if self.rank[r["job_id"]] <= 20]
        self.assertGreaterEqual(
            len(in_top), 10,
            "hand-picked target roles inside the top 20 fell below the "
            "pinned 10 of 20")

    def test_pinned_scores_and_ranks_still_reproduce(self):
        """The change detector. A weight edit is SUPPOSED to break this; the
        point is that its effect on thirty known postings is printed rather
        than discovered later. Regenerate the fixture in the same commit."""
        for key in ("target_roles", "senior_software_roles"):
            for r in self.goldens[key]:
                job_id = r["job_id"]
                self.assertEqual(
                    (self.score[job_id], self.rank[job_id]),
                    (r["pinned_score"], r["pinned_rank"]),
                    f"{r['title']} ({r['company']}) moved: pinned "
                    f"{r['pinned_score']}@{r['pinned_rank']}, now "
                    f"{self.score[job_id]}@{self.rank[job_id]}")

    def test_the_corpus_wide_counts_the_weights_were_chosen_against(self):
        """The three numbers the repo owner selected this weight set on, over
        the whole frozen corpus rather than the thirty pinned rows. They are
        the only figures here big enough to mean anything, and they are what
        a later editor should re-run first.

        144 AND 145 ARE BOTH RIGHT, ABOUT DIFFERENT CORPORA. The weight set
        was selected against 863 rows and 145 cleared the floor. Task 35
        (`303f7b9`) then deleted four postings whose description_text was
        browser-DOM markup rather than a job posting, one of which was above
        the floor at rank 126, and this fixture was re-pinned to the
        surviving 859. So an older document saying 145 is not stale
        arithmetic -- it is the same weights over a corpus that still
        contained four things that were not jobs. The goldens file's
        _both_numbers block is the long version.

        The other two figures did not move at all: none of the four removed
        rows was entry-level x uses_ai_tools.
        """
        matched = [j for j, s in self.score.items() if s >= self.floor]
        self.assertEqual(len(matched), 144)

        entry = ("intern", "new_grad", "junior")
        by_id = {f["job_id"]: f for f in self.corpus}
        top20 = sorted(self.score, key=lambda j: (-self.score[j], j))[:20]
        self.assertEqual(
            sum(1 for j in top20
                if by_id[j]["seniority_level"] in entry
                and by_id[j]["ai_involvement"] == "uses_ai_tools"), 19)

        # The shared floor as a population: entry-level AND the cohort's
        # targeting mechanism. 13-cohort-criteria-profile.md:25-33.
        shared_floor = [f["job_id"] for f in self.corpus
                        if f["seniority_level"] in entry
                        and f["ai_involvement"] == "uses_ai_tools"]
        self.assertEqual(len(shared_floor), 55)
        self.assertEqual(
            sum(1 for j in shared_floor if self.score[j] >= self.floor), 51)


class TestCriteriaSectionsAreCheckedAtReadTime(unittest.TestCase):
    """D12: a misspelled criteria section disabled itself in silence.

    Every lookup in `score_job()` is a `.get()` with a default, so a profile
    whose `criteria_json` says "senority" scores every posting as though the
    seniority rule did not exist -- no error, no reason row, no clue. The
    check lives in the CALLER, because `score_job()` is pure and stays pure.
    """

    class _Profile:
        profile = "test"

        def __init__(self, criteria):
            self.criteria = criteria

    def test_the_shipped_criteria_files_have_no_unknown_sections(self):
        # If this fails, either a section was added to a config without being
        # taught to score_job(), or CRITERIA_SECTIONS has gone stale.
        for name in ("criteria.json", "pursuit-criteria.json"):
            path = os.path.join(os.path.dirname(os.path.dirname(
                os.path.abspath(__file__))), "config", name)
            with open(path) as fh:
                criteria = json.load(fh)
            with self.subTest(config=name):
                self.assertEqual(
                    match.check_criteria_sections(self._Profile(criteria)), [],
                    f"{name} has a section score_job() never reads")

    def test_a_typo_is_reported_rather_than_ignored(self):
        criteria = {"base": 50, "senority": {"target": ["junior"]}}
        self.assertEqual(
            match.check_criteria_sections(self._Profile(criteria)), ["senority"])

    def test_underscore_comment_keys_are_not_reported(self):
        # `_comment` fields are load-bearing documentation in this repo and
        # appear in every config; flagging them would make the check noise.
        criteria = {"base": 50, "_comment": "why 50", "_source": "task 13"}
        self.assertEqual(
            match.check_criteria_sections(self._Profile(criteria)), [])

    def test_every_section_score_job_reads_is_declared(self):
        # The frozenset is hand-maintained; this pins it against the source.
        import re as _re
        src = open(match.__file__).read()
        body = src[src.index("def score_job("):src.index("def existing_versions(")]
        read = set(_re.findall(r'criteria\.get\("([a-z_]+)"', body))
        self.assertEqual(read - match.CRITERIA_SECTIONS, set(),
                         "score_job() reads a section CRITERIA_SECTIONS omits")


class TestSeniorityVocabularyGuard(unittest.TestCase):
    """D13: the two vocabularies were coupled by nothing but habit.

    `extract.SENIORITY` decides what can land in `job_facts.seniority_level`;
    `match.SENIORITY_ORDER` is the scale the seniority penalty measures
    distance along. A level in the first and not the second falls through
    every branch of the seniority block and is scored as FREE -- not zero the
    way an on-target level is, but unpriced, silently, in the ranking that
    decides what a user sees. Nothing asserted the relation anywhere.
    """

    def test_the_shipped_constants_agree(self):
        self.assertEqual(match.check_seniority_vocabulary(),
                         match.SENIORITY_ORDER)

    def test_a_level_the_ranker_cannot_place_raises(self):
        with self.assertRaises(match.SeniorityVocabularyDrift) as caught:
            match.check_seniority_vocabulary(
                vocabulary=extract.SENIORITY + ("staff_plus",))
        self.assertIn("staff_plus", str(caught.exception))

    def test_the_message_names_every_missing_level_not_just_the_first(self):
        with self.assertRaises(match.SeniorityVocabularyDrift) as caught:
            match.check_seniority_vocabulary(
                vocabulary=("junior", "staff_plus", "fellow"))
        self.assertIn("staff_plus", str(caught.exception))
        self.assertIn("fellow", str(caught.exception))

    def test_extra_rungs_in_the_ranker_are_allowed(self):
        # A SUPERSET, not equality: SENIORITY_ORDER may carry rungs the
        # extractor never emits, and forbidding that would be a different
        # defect. Only the other direction loses information.
        match.check_seniority_vocabulary(
            order=match.SENIORITY_ORDER + ("emeritus",))

    def test_the_guard_fires_at_import_not_only_when_called(self):
        """The property that makes this a guard rather than a test.

        A check nobody calls is a comment. This adds a level to the
        extractor's vocabulary -- the real drift -- and asserts that merely
        importing match.py refuses to proceed.
        """
        original = extract.SENIORITY
        try:
            extract.SENIORITY = original + ("staff_plus",)
            # Caught as RuntimeError, not as match.SeniorityVocabularyDrift:
            # reload() rebinds the class before the raise, so the exception
            # raised is an instance of the NEW class object and the name held
            # here is the old one. The type name is asserted instead.
            with self.assertRaises(RuntimeError) as caught:
                importlib.reload(match)
        finally:
            extract.SENIORITY = original
            importlib.reload(match)
        self.assertEqual(type(caught.exception).__name__,
                         "SeniorityVocabularyDrift")
        self.assertIn("staff_plus", str(caught.exception))
        self.assertEqual(match.check_seniority_vocabulary(),
                         match.SENIORITY_ORDER)


class TestDeletedRowsAreRecoverable(unittest.TestCase):
    """D11: demoted and orphaned rows were deleted with only a count.

    A weight edit that demotes hundreds of rows printed a number, and the
    rows were already gone by the time anyone read it -- so "which ones"
    had no answer from anywhere. The id is the part still worth keeping:
    `job_id` is stable and derived, so it resolves against `jobs`,
    `job_facts` and `job_events` long after the match row is gone.
    """

    def _capture(self, debug, ids):
        original = match.DEBUG_PRINT_KEYS
        stream = io.StringIO()
        try:
            match.DEBUG_PRINT_KEYS = debug
            with contextlib.redirect_stderr(stream):
                match.log_deleted_ids("tech", "demoted", ids)
        finally:
            match.DEBUG_PRINT_KEYS = original
        return stream.getvalue()

    def test_the_ids_reach_the_log_at_debug_verbosity(self):
        out = self._capture(True, ["job-a", "job-b"])
        self.assertIn("job-a", out)
        self.assertIn("job-b", out)
        self.assertIn("2 demoted", out)
        self.assertIn("tech", out)

    def test_nothing_is_printed_by_default(self):
        # A new output surface on a stage that runs nightly. The flag is the
        # whole point: the summary line stays exactly as it was.
        self.assertEqual(self._capture(False, ["job-a", "job-b"]), "")

    def test_an_empty_deletion_says_nothing_even_at_debug_verbosity(self):
        self.assertEqual(self._capture(True, []), "")

    def test_match_py_reads_the_flag_at_all(self):
        """It read `DEBUG_PRINT_KEYS` NOWHERE before this -- which is why the
        ids were unrecoverable at every verbosity rather than merely off by
        default. `.claude/CLAUDE.md` documents the flag as the convention
        everywhere; this is the assertion that match.py is part of
        'everywhere'."""
        with open(match.__file__) as fh:
            src = fh.read()
        self.assertIn('os.environ.get("DEBUG_PRINT_KEYS"', src)
        self.assertIn("log_deleted_ids(profile.profile, \"orphaned\"", src)
        self.assertIn("log_deleted_ids(profile.profile, \"demoted\"", src)


@unittest.skipUnless(
    scratchdb.available(),
    "no scratch database: set DATABASE_URL (or JOBS_SCRATCH_DATABASE_URL)")
class TestPruneOrphansAgainstPostgres(unittest.TestCase):
    """D11's other half: the ids have to be the ones actually deleted.

    `prune_orphans` learns them from `DELETE ... RETURNING`, so this is the
    only place the claim can be checked -- a fake connection would return
    whatever it was told to.
    """

    class _Profile:
        profile = "tech"

    def _rows(self, conn, job_ids):
        for job_id in job_ids:
            # job_matches.job_id REFERENCES jobs(id), so the posting has to
            # exist before its match row can.
            conn.execute(
                f"INSERT INTO {schema.TABLE} "
                f"(id, platform, company_token, company_name, source_id, "
                f" title, first_seen, last_seen) "
                f"VALUES (%s, 'greenhouse', 'acme', 'Acme', %s, 'Engineer', "
                f"'2026-08-01T00:00:00', '2026-08-01T00:00:00')",
                (job_id, job_id))
            conn.execute(
                f"INSERT INTO {schema.MATCHES_TABLE} "
                f"(job_id, profile, match_score, match_reasons, facts_version,"
                f" criteria_version, matched_at) "
                f"VALUES (%s, 'tech', 50, '[]', 3, 1, '2026-08-01T00:00:00')",
                (job_id,))
        conn.commit()

    def test_the_logged_ids_are_exactly_the_deleted_rows(self):
        stream = io.StringIO()
        original = match.DEBUG_PRINT_KEYS
        with scratchdb.scratch_schema() as (conn, _name):
            self._rows(conn, ["keep-1", "orphan-1", "orphan-2"])
            try:
                match.DEBUG_PRINT_KEYS = True
                with contextlib.redirect_stderr(stream):
                    deleted = match.prune_orphans(
                        conn, self._Profile(), [{"job_id": "keep-1"}])
            finally:
                match.DEBUG_PRINT_KEYS = original
            survivors = [r[0] for r in conn.execute(
                f"SELECT job_id FROM {schema.MATCHES_TABLE}").fetchall()]
        self.assertEqual(deleted, 2)
        self.assertEqual(survivors, ["keep-1"])
        out = stream.getvalue()
        self.assertIn("orphan-1", out)
        self.assertIn("orphan-2", out)
        self.assertNotIn("keep-1", out)

    def test_the_count_still_matches_what_the_delete_removed(self):
        """RETURNING replaced `.rowcount`; the number callers print must not
        have changed with it."""
        with scratchdb.scratch_schema() as (conn, _name):
            self._rows(conn, ["a", "b", "c"])
            self.assertEqual(
                match.prune_orphans(conn, self._Profile(),
                                    [{"job_id": "a"}, {"job_id": "b"}]), 1)
            self.assertEqual(
                match.prune_orphans(conn, self._Profile(),
                                    [{"job_id": "a"}, {"job_id": "b"}]), 0)

    def test_a_dry_run_deletes_nothing_and_logs_nothing(self):
        stream = io.StringIO()
        original = match.DEBUG_PRINT_KEYS
        with scratchdb.scratch_schema() as (conn, _name):
            self._rows(conn, ["a", "b"])
            try:
                match.DEBUG_PRINT_KEYS = True
                with contextlib.redirect_stderr(stream):
                    n = match.prune_orphans(conn, self._Profile(),
                                            [{"job_id": "a"}], dry_run=True)
            finally:
                match.DEBUG_PRINT_KEYS = original
            remaining = conn.execute(
                f"SELECT count(*) FROM {schema.MATCHES_TABLE}").fetchone()[0]
        self.assertEqual((n, remaining), (1, 2))
        self.assertEqual(stream.getvalue(), "")


# ---------------------------------------------------------------------------
# D20 -- per-record isolation, the invariant this stage did not have
# ---------------------------------------------------------------------------

class _MatchProfile:
    """The three attributes match_profile() reads off a profile."""

    profile = "tech"
    criteria_version = 1

    def __init__(self, criteria=None):
        self.criteria = CRITERIA if criteria is None else criteria


class TestScoringFailuresAreIsolated(unittest.TestCase):
    """D20, the half that needs no database.

    `score_job` was called unguarded at `match.py:523` (the register said
    `:290`), so the uncaught `TypeError` from `total += delta` at `:152` (the
    register said `:92`) propagated out of `match_profile` and out of `main`'s
    per-profile loop, ending the run for every profile -- including ones
    already computed and not yet committed.

    Everything here is dry-run, so `score_job`'s purity is the only thing
    under test and no connection is touched.
    """

    def _facts(self, n):
        return [dict(facts(), job_id=f"job-{i}", facts_version=3)
                for i in range(n)]

    def test_one_unscorable_job_does_not_cost_the_others(self):
        """A facts row no rule anticipated. `tech_stack` is iterated, so a
        non-iterable there is a shape the extractor could really produce."""
        rows = self._facts(3)
        rows[1]["tech_stack"] = 7          # not iterable -- TypeError inside
        stats = collections.Counter()
        with contextlib.redirect_stderr(io.StringIO()) as err:
            written, deleted, skipped = match.match_profile(
                None, _MatchProfile(), rows, rebuild=True, dry_run=True,
                stats=stats)
        self.assertEqual(written, 2, "two jobs scored cleanly and must count")
        self.assertEqual(stats["score_failed"], 1)
        self.assertIn("job-1", err.getvalue(),
                      "the job that could not be scored must be named")

    def test_a_non_numeric_weight_fails_every_job_loudly(self):
        """The register's own example: a criteria weight that is not a number.

        It is not one bad row -- it is every row -- and the point of the
        isolation is that this is now REPORTED rather than raised. main()
        turns it into a non-zero exit; see the source assertion below.
        """
        broken = dict(CRITERIA, base="thirty-five")
        stats = collections.Counter()
        with contextlib.redirect_stderr(io.StringIO()):
            written, _deleted, _skipped = match.match_profile(
                None, _MatchProfile(broken), self._facts(4), rebuild=True,
                dry_run=True, stats=stats)
        self.assertEqual(written, 0)
        self.assertEqual(stats["score_failed"], 4)

    def test_only_the_first_few_failures_are_printed(self):
        """20,000 facts against a broken criteria file must not print 20,000
        lines. Loud is a signal; a flood is the same silence."""
        broken = dict(CRITERIA, base="thirty-five")
        with contextlib.redirect_stderr(io.StringIO()) as err:
            match.match_profile(None, _MatchProfile(broken), self._facts(50),
                                rebuild=True, dry_run=True)
        self.assertEqual(err.getvalue().count("could not score"), 3)

    def test_an_unscorable_job_is_never_demoted(self):
        """The dangerous fix, ruled out.

        Treating a scoring exception as "below the floor" would DELETE the
        existing match row -- so one bad weight would silently clear a
        profile's whole list. That is worse than the crash it replaces.
        """
        src = inspect.getsource(match.match_profile)
        guard = src[src.index("try:\n            score, reasons"):]
        self.assertNotIn("to_delete.append", guard.split("continue")[0])

    def test_main_exits_non_zero_when_a_profile_scores_nothing(self):
        src = inspect.getsource(match.main)
        self.assertIn("failed_profiles", src)
        self.assertIn("sys.exit(1)", src)


@unittest.skipUnless(
    scratchdb.available(),
    "no scratch database: set DATABASE_URL (or JOBS_SCRATCH_DATABASE_URL)")
class TestRejectedRowsDoNotLoseTheBatch(unittest.TestCase):
    """D20's other half: the `executemany` at `match.py:537-549` (the register
    said `:304-316`) is one statement with no per-row isolation.

    This needs a real server for the reason `evals/scratchdb.py`'s docstring
    gives: a failed statement aborts the whole Postgres transaction, and a
    fake connection cannot reproduce that. The trigger is not contrived --
    `job_matches.job_id REFERENCES jobs(id)` (`schema.py:574-575`), so a
    posting deleted between `load_facts()` and this write is a plain foreign
    key violation, and before the fix it took every other row with it.
    """

    def _jobs(self, conn, job_ids):
        for job_id in job_ids:
            conn.execute(
                f"INSERT INTO {schema.TABLE} "
                f"(id, platform, company_token, company_name, source_id, "
                f" title, first_seen, last_seen) "
                f"VALUES (%s, 'greenhouse', 'acme', 'Acme', %s, 'Engineer', "
                f"'2026-08-01T00:00:00', '2026-08-01T00:00:00')",
                (job_id, job_id))
        conn.commit()

    def _row(self, job_id):
        return (job_id, "tech", 50, "[]", 3, 1, "2026-08-01T00:00:00")

    def test_one_row_with_no_posting_does_not_lose_the_batch(self):
        with scratchdb.scratch_schema() as (conn, _name):
            self._jobs(conn, ["a", "c"])
            with contextlib.redirect_stderr(io.StringIO()) as err:
                failed = match.write_matches(
                    conn, [self._row("a"), self._row("b"), self._row("c")])
            conn.commit()
            landed = sorted(r[0] for r in conn.execute(
                f"SELECT job_id FROM {schema.MATCHES_TABLE}").fetchall())
        self.assertEqual(failed, 1)
        self.assertEqual(landed, ["a", "c"],
                         "'b' has no posting and cannot be written; 'a' and "
                         "'c' have one and must be")
        self.assertIn("job_id=b", err.getvalue())

    def test_a_clean_batch_stays_one_statement(self):
        """The fallback must be a fallback. If every batch degraded to
        row-by-row the nightly run would pay a round trip per posting."""
        with scratchdb.scratch_schema() as (conn, _name):
            self._jobs(conn, ["a", "b"])
            with contextlib.redirect_stderr(io.StringIO()) as err:
                failed = match.write_matches(
                    conn, [self._row("a"), self._row("b")])
            conn.commit()
            landed = conn.execute(
                f"SELECT count(*) FROM {schema.MATCHES_TABLE}").fetchone()[0]
        self.assertEqual((failed, landed), (0, 2))
        self.assertEqual(err.getvalue(), "",
                         "a batch that succeeded has nothing to report")

    def test_the_row_by_row_pass_writes_what_the_batch_would_have(self):
        """One SQL string, used by both paths -- so the fallback cannot
        quietly stop matching the statement it falls back from."""
        with scratchdb.scratch_schema() as (conn, _name):
            self._jobs(conn, ["a"])
            with contextlib.redirect_stderr(io.StringIO()):
                match.write_matches(conn, [self._row("a"), self._row("gone")])
            conn.commit()
            row = conn.execute(
                f"SELECT match_score, match_reasons, facts_version, "
                f"criteria_version, matched_at FROM {schema.MATCHES_TABLE} "
                f"WHERE job_id = 'a'").fetchone()
        self.assertEqual(row, (50, "[]", 3, 1, "2026-08-01T00:00:00"))

    def test_match_profile_reports_rejected_rows_as_unwritten(self):
        """`written` must be what the table holds, not what was attempted."""
        with scratchdb.scratch_schema() as (conn, _name):
            self._jobs(conn, ["a"])
            rows = [dict(facts(), job_id="a", facts_version=3),
                    dict(facts(), job_id="gone", facts_version=3)]
            stats = collections.Counter()
            with contextlib.redirect_stderr(io.StringIO()):
                written, _deleted, _skipped = match.match_profile(
                    conn, _MatchProfile(), rows, rebuild=True, stats=stats)
            landed = conn.execute(
                f"SELECT count(*) FROM {schema.MATCHES_TABLE}").fetchone()[0]
        self.assertEqual(stats["write_failed"], 1)
        self.assertEqual((written, landed), (1, 1))


if __name__ == "__main__":
    unittest.main(verbosity=2)

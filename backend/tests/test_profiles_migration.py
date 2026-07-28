"""Unit tests for migrations/migrate_profiles.py.

Run:  python3 tests/test_profiles_migration.py

stdlib unittest -- pytest is not installed and is not worth a dependency here.

WHY THIS FILE EXISTS AT ALL
    migrate_profiles.py had no tests of any kind before task 13, and it is the
    script that writes profiles.criteria_json, persona_json, relevance_json,
    daily_narrative_budget and active -- five columns that between them decide
    what the pipeline ranks, what it spends money on, and how many postings it
    sends to an LLM every night. It was also carrying three latent overwrites
    at once, all of the same shape: profiles.upsert writes all ten columns on
    every call, and this script fed it a default for the three it does not
    derive from a config file.

WHAT THE THREE OVERWRITES WOULD HAVE DONE, since that is what these tests pin
    relevance_json  upsert was called with no relevance_cfg, so the ON CONFLICT
                    branch wrote NULL. Running the script against `pursuit`
                    would have erased the description-first cohort gate task 10
                    measured over 876 rows and silently replaced it with the
                    shared software-title filter. Nothing downstream would
                    have raised -- the profile would just start matching a
                    different population.
    daily_narrative_budget
                    --budget defaulted to 20 and was passed unconditionally, so
                    a run whose purpose was to change WEIGHTS would also have
                    turned on paid narrative LLM calls for a profile
                    deliberately pinned at 0.
    active          upsert defaults active=True and the script never passed it,
                    so refreshing `tech` -- deactivated by task 12 precisely to
                    stop re-extracting its 5,317 eligible rows at every
                    FACTS_VERSION bump -- would have switched it back on.

    All three are now preserve-on-absent, and resolve_preserved() is factored
    out of main() so the property is testable without a database. These tests
    are about that function and about the config files it is pointed at; they
    do not connect to Postgres and must not start doing so.
"""

import json
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "migrations"))

import profiles  # noqa: E402
import migrate_profiles  # noqa: E402
import migrate_pursuit_profile  # noqa: E402

_BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PURSUIT_CRITERIA = os.path.join(_BACKEND, "config", "pursuit-criteria.json")
PURSUIT_PERSONA = os.path.join(_BACKEND, "config", "pursuit-persona.json")


def stored(profile="pursuit", *, relevance=None, budget=0, active=True):
    """A profiles.Profile as load_one() would return it.

    Frozen dataclass, so it is built rather than mutated -- which is the point:
    resolve_preserved() must read the stored row and never write to it.
    """
    return profiles.Profile(
        profile=profile, display_name=profile, persona={}, criteria={},
        relevance=relevance, criteria_version=1,
        daily_narrative_budget=budget, active=active)


class TestPreserveOnAbsent(unittest.TestCase):
    """Omitting a flag must preserve, not reset. One test per column, plus the
    combination, because the three defaults were independently wrong."""

    #: A stand-in for the cohort gate. Its CONTENTS do not matter here -- what
    #: matters is that the same object comes back out.
    GATE = {"title_include": [["ai"], ["junior"]], "max_tier_to_score": 2}

    def test_relevance_is_preserved_when_no_file_is_given(self):
        existing = stored(relevance=self.GATE)
        rel, _, _ = migrate_profiles.resolve_preserved(existing)
        self.assertEqual(rel, self.GATE)

    def test_relevance_is_replaced_when_a_file_is_given(self):
        existing = stored(relevance=self.GATE)
        other = {"title_include": [["something else"]]}
        rel, _, _ = migrate_profiles.resolve_preserved(
            existing, relevance_cfg=other)
        self.assertEqual(rel, other)

    def test_budget_is_preserved_when_the_flag_is_absent(self):
        """pursuit sits at 0 on purpose. The old default of 20 would have
        turned on paid scoring for every posting the profile matches."""
        _, budget, _ = migrate_profiles.resolve_preserved(stored(budget=0))
        self.assertEqual(budget, 0)

    def test_budget_zero_is_preserved_and_not_read_as_absent(self):
        """0 is falsy, and the whole class of bug this file is about is a
        falsy value being treated as 'not supplied'. Only None means absent."""
        _, budget, _ = migrate_profiles.resolve_preserved(
            stored(budget=20), budget=0)
        self.assertEqual(budget, 0)

    def test_active_is_preserved_when_the_flag_is_absent(self):
        """tech and frontend are inactive by task 12's decision. Reactivating
        either costs the 5,317-row extraction bill at the next bump."""
        _, _, active = migrate_profiles.resolve_preserved(
            stored("tech", active=False))
        self.assertFalse(active)

    def test_active_false_is_preserved_and_not_read_as_absent(self):
        _, _, active = migrate_profiles.resolve_preserved(
            stored(active=True), active=False)
        self.assertFalse(active)

    def test_a_run_that_mentions_nothing_changes_nothing(self):
        """The combination, which is the realistic case: refreshing a
        profile's weights must move only its weights."""
        existing = stored("tech", relevance=self.GATE, budget=7, active=False)
        self.assertEqual(
            migrate_profiles.resolve_preserved(existing),
            (self.GATE, 7, False))

    def test_a_new_profile_gets_the_documented_defaults(self):
        rel, budget, active = migrate_profiles.resolve_preserved(None)
        self.assertIsNone(rel)
        self.assertEqual(budget, migrate_profiles.NEW_PROFILE_BUDGET)
        self.assertTrue(active)

    def test_flags_still_win_over_the_new_profile_defaults(self):
        rel, budget, active = migrate_profiles.resolve_preserved(
            None, relevance_cfg=self.GATE, budget=0, active=False)
        self.assertEqual((rel, budget, active), (self.GATE, 0, False))


class TestStripComments(unittest.TestCase):
    """The _-prefixed keys are documentation and must not reach the database.

    They are also the deliverable -- CLAUDE.md calls them load-bearing -- so
    the property is exactly 'they live in the file and nowhere else'."""

    def test_underscore_keys_are_dropped(self):
        out = migrate_profiles.strip_comments(
            {"_comment": "why", "base": 50, "_base_comment": "how"})
        self.assertEqual(out, {"base": 50})

    def test_nested_underscore_keys_are_NOT_dropped(self):
        """Deliberate, and worth pinning: the function is shallow, matching
        relevance.load (relevance.py:88-97). Nothing in either config nests a
        comment, and a recursive strip would silently mangle an archetype or a
        tech term that legitimately began with an underscore."""
        out = migrate_profiles.strip_comments({"tech": {"_note": "x", "cap": 0}})
        self.assertEqual(out, {"tech": {"_note": "x", "cap": 0}})


class TestPursuitPlaceholderGuard(unittest.TestCase):
    """migrate_pursuit_profile.py must not silently revert task 13.

    It still owns the cohort RELEVANCE GATE, so it is the script someone
    reaches for to refresh that -- and until task 13 landed, re-running it was
    harmless. It is not any more: it would write its own stand-in criteria
    over the real ones WITHOUT bumping criteria_version, so match.py would
    consider every row current and job_matches would stay full while every
    score collapsed to `base`. That is the repo's stated failure mode, silence,
    with a full table as the disguise.
    """

    def profile_with(self, criteria):
        return profiles.Profile(
            profile="pursuit", display_name="p", persona={}, criteria=criteria,
            relevance={}, criteria_version=2, daily_narrative_budget=0,
            active=True)

    def test_the_stand_in_criteria_are_recognised(self):
        self.assertTrue(migrate_pursuit_profile.is_placeholder(
            self.profile_with(migrate_pursuit_profile.PLACEHOLDER_CRITERIA)))

    def test_the_real_cohort_criteria_are_not(self):
        with open(PURSUIT_CRITERIA) as f:
            real = migrate_profiles.strip_comments(json.load(f))
        self.assertFalse(
            migrate_pursuit_profile.is_placeholder(self.profile_with(real)))

    def test_the_test_is_the_archetype_map_and_not_a_marker_string(self):
        """A marker string is the kind of thing an editor tidies away, and
        `archetypes` empty is the property that actually makes the stand-in
        rank uniformly. Stripping every comment out of the stand-in must not
        make it look real."""
        stripped = migrate_profiles.strip_comments(
            migrate_pursuit_profile.PLACEHOLDER_CRITERIA)
        self.assertNotIn("_placeholder", stripped)
        self.assertTrue(
            migrate_pursuit_profile.is_placeholder(self.profile_with(stripped)))

    def test_a_missing_archetypes_key_reads_as_a_placeholder(self):
        """Fail safe: an absent map and an empty one both mean 'this profile
        cannot rank', so both must refuse rather than only the shape the
        stand-in happens to have."""
        self.assertTrue(
            migrate_pursuit_profile.is_placeholder(self.profile_with({"base": 50})))


class TestCohortConfigFilesAreImportable(unittest.TestCase):
    """The two files task 13 adds must survive the exact path a real run takes:
    parse, strip, validate. Failing at save time naming the field is the whole
    point of profiles.validate (profiles.py:123-136); these tests make sure the
    cohort files reach it rather than dying earlier on a typo."""

    def setUp(self):
        with open(PURSUIT_CRITERIA) as f:
            self.criteria = migrate_profiles.strip_comments(json.load(f))
        self.persona = profiles.load_persona_file(PURSUIT_PERSONA)

    def test_the_pair_validates(self):
        profiles.validate(self.persona, self.criteria)

    def test_the_persona_has_no_placeholders_left(self):
        """migrate_pursuit_profile.py:371-396 wrote four PLACEHOLDER strings to
        satisfy validate(). Task 13 replaces them, and 'the key exists' is not
        the property that matters -- 'it is not still the placeholder' is."""
        for key in ("background_summary", "strengths", "honest_gaps",
                    "scoring_instructions"):
            self.assertNotIn("PLACEHOLDER", json.dumps(self.persona[key]),
                             f"persona.{key} is still a placeholder")

    def test_the_persona_has_no_buckets_key(self):
        """Task 30's decision, not this one. D16 makes its absence safe rather
        than merely tolerated (score.py:334), so adding one here would
        pre-empt a vocabulary choice that is blocked on task 29's labels."""
        self.assertNotIn("buckets", self.persona)

    def test_the_criteria_carry_no_documentation_into_the_database(self):
        self.assertFalse([k for k in self.criteria if k.startswith("_")])

    def test_the_criteria_still_carry_documentation_in_the_file(self):
        with open(PURSUIT_CRITERIA) as f:
            raw = json.load(f)
        self.assertTrue([k for k in raw if k.startswith("_")])


if __name__ == "__main__":
    unittest.main(verbosity=2)

"""Unit tests for the relevance tiering SQL.

Run:  python3 tests/test_relevance.py

These assert on the generated SQL and params rather than against a database,
because the property that matters is structural: which predicates end up in the
tier-1/tier-2 arms, and whether an absent config key adds a predicate at all.

WHY THE "PERMISSIVE WHEN ABSENT" TESTS MATTER MOST
    This module fails silently in the direction that hurts. A filter that
    accidentally matches everything sends good postings to tier 3, where
    max_tier_to_score means nothing scores them and nobody looks. There is no
    error and no empty result -- just a ranking that quietly stops containing
    the jobs you wanted. So the defaults are pinned: a config without
    company_exclude must not emit a company predicate, and a NULL description
    must not be treated as matching an exclusion.
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import relevance  # noqa: E402


class TestDisabledDefaults(unittest.TestCase):
    def test_missing_config_keeps_everything_in_tier_1(self):
        sql, params = relevance.tier_sql(dict(relevance.DISABLED))
        self.assertEqual(params, {})
        self.assertIn("THEN 1", sql)
        for column in ("company_name", "description_text", "title"):
            self.assertNotIn(column, sql,
                             f"a disabled config must not filter on {column}")

    def test_new_keys_are_in_disabled(self):
        """load() merges over DISABLED, so a key absent from it would raise a
        KeyError for every caller using the shared config file."""
        self.assertIn("company_exclude", relevance.DISABLED)
        self.assertIn("description_exclude", relevance.DISABLED)
        self.assertIn("description_include", relevance.DISABLED)
        self.assertIn("platform_exclude", relevance.DISABLED)
        self.assertEqual(relevance.DISABLED["company_exclude"], [])
        self.assertEqual(relevance.DISABLED["description_include"], [])
        self.assertEqual(relevance.DISABLED["platform_exclude"], [])

    def test_profile_override_starts_from_disabled_not_the_file(self):
        """A profile specifying only title_include must get the permissive
        default for the keys it omitted, not the shared file's answers."""
        cfg = relevance.load(cfg={"title_include": ["engineer"]})
        self.assertEqual(cfg["company_exclude"], [])
        self.assertEqual(cfg["description_exclude"], [])


class TestCompanyExclude(unittest.TestCase):
    BASE = {**relevance.DISABLED, "title_include": ["engineer"]}

    def test_absent_emits_no_predicate(self):
        sql, params = relevance.tier_sql(self.BASE)
        self.assertNotIn("company_name", sql)
        self.assertNotIn("rel_coexcl", params)

    def test_present_forces_tier_3_for_matches(self):
        sql, params = relevance.tier_sql(
            {**self.BASE, "company_exclude": ["\\yremote zest\\y"]})
        self.assertIn("company_name !~*", sql)
        self.assertEqual(params["rel_coexcl"], "\\yremote zest\\y")
        # It must gate BOTH tier arms, or an excluded company would merely drop
        # from tier 1 to tier 2 and still be scored.
        self.assertEqual(sql.count("company_name !~*"), 2)

    def test_alternation_joins_patterns(self):
        _, params = relevance.tier_sql(
            {**self.BASE, "company_exclude": ["\\yfoo\\y", "\\ybar\\y"]})
        self.assertEqual(params["rel_coexcl"], "\\yfoo\\y|\\ybar\\y")


class TestDescriptionExclude(unittest.TestCase):
    BASE = {**relevance.DISABLED, "title_include": ["engineer"]}

    def test_absent_emits_no_predicate(self):
        sql, _ = relevance.tier_sql(self.BASE)
        self.assertNotIn("description_text", sql)

    def test_null_description_is_coalesced(self):
        """Without COALESCE, `NULL !~* pattern` is NULL, the CASE arm is not
        true, and every posting whose description has not been fetched yet
        silently lands in tier 3 -- which is 190 Built In rows today."""
        sql, _ = relevance.tier_sql(
            {**self.BASE, "description_exclude": ["reputed company"]})
        self.assertIn("COALESCE", sql)
        self.assertIn("description_text", sql)
        self.assertRegex(sql, r"COALESCE\(\s*j\.description_text,\s*''\s*\)")


class TestDescriptionIncludeIsInert(unittest.TestCase):
    """THE INVARIANT: adding description_include changed nothing for anyone
    who does not set it.

    The author's `frontend` and `tech` profiles both have relevance_json NULL,
    so they run on config/relevance.json, which has no description_include.
    Their tier assignments are unchanged iff tier_sql emits the same SQL and
    the same params for a config without the key. That is a property of the
    generated string, so it is checked as one -- byte equality, not
    "semantically similar". A tier count diff against the live table is the
    other half of the check and lives in docs/pursuit-description-gate.md;
    this is the half that runs in CI.

    THE GOLDEN STRING IS THE POINT
        Pinning the exact SQL is deliberately brittle. Anything that changes
        it changes which postings the pipeline extracts, and that should never
        happen as a side effect of an unrelated edit -- it should require
        someone to look at this string and decide.
    """

    PRODUCTION_SQL = (
        "CASE WHEN (j.title ~* %(rel_include)s"
        " AND j.title !~* %(rel_exclude)s"
        " AND j.company_name !~* %(rel_coexcl)s"
        " AND COALESCE(j.description_text, '') !~* %(rel_dexcl)s)"
        " AND (COALESCE(j.location_is_nyc, FALSE)"
        " OR COALESCE(j.location_is_remote, FALSE)) THEN 1 "
        "     WHEN (j.title ~* %(rel_include)s"
        " AND j.title !~* %(rel_exclude)s"
        " AND j.company_name !~* %(rel_coexcl)s"
        " AND COALESCE(j.description_text, '') !~* %(rel_dexcl)s) THEN 2 "
        "     ELSE 3 END"
    )

    #: Every shape the shared config and the two existing profiles can take.
    SHAPES = {
        "disabled": {},
        "include only": {"title_include": ["engineer"]},
        "include + title_exclude": {"title_include": ["engineer"],
                                    "title_exclude": ["\\ysdr\\y"]},
        "all excludes": {"title_include": ["engineer"],
                         "title_exclude": ["\\ysdr\\y"],
                         "company_exclude": ["\\yremote zest\\y"],
                         "description_exclude": ["reputed company"]},
        "no include, excludes only": {"company_exclude": ["\\yremote zest\\y"],
                                      "description_exclude": ["reputed company"]},
        "with locations": {"title_include": ["engineer"],
                           "location_columns": ["location_is_nyc",
                                                "location_is_remote"]},
    }

    def test_shared_config_sql_is_pinned(self):
        sql, params = relevance.tier_sql(relevance.load())
        self.assertEqual(sql, self.PRODUCTION_SQL)
        self.assertNotIn("rel_dincl", params)
        self.assertNotIn("rel_pfexcl", params)

    def test_absent_null_and_empty_are_all_identical(self):
        for name, base in self.SHAPES.items():
            cfg = {**relevance.DISABLED, **base}
            absent = relevance.tier_sql(cfg)
            for label, value in (("empty list", []), ("null", None),
                                 ("empty groups", [[]])):
                with self.subTest(shape=name, description_include=label):
                    got = relevance.tier_sql({**cfg, "description_include": value})
                    self.assertEqual(got, absent)

    def test_platform_exclude_is_inert_when_absent(self):
        for name, base in self.SHAPES.items():
            cfg = {**relevance.DISABLED, **base}
            with self.subTest(shape=name):
                sql, params = relevance.tier_sql(cfg)
                self.assertNotIn("platform", sql)
                self.assertNotIn("rel_pfexcl", params)

    def test_union_sql_is_unchanged_for_configs_without_the_key(self):
        """extract.py gates on union_sql across all active profiles. Both
        current profiles resolve to the shared config, so the union must be
        exactly the one-profile predicate it was before this key existed."""
        cfg = relevance.load()
        sql, params = relevance.union_sql([cfg, cfg])
        self.assertNotIn("description_text, '') ~*", sql)
        self.assertNotIn("rel0_dincl", params)
        self.assertNotIn("rel1_dincl", params)


class TestDescriptionInclude(unittest.TestCase):
    BASE = {**relevance.DISABLED, "title_include": ["engineer"],
            "title_exclude": ["\\yaccount executive\\y"]}

    def test_or_with_title_so_a_body_match_carries_the_row(self):
        sql, params = relevance.tier_sql(
            {**self.BASE, "description_include": ["chatgpt"]})
        self.assertIn("(j.title ~* %(rel_include)s OR "
                      "COALESCE(j.description_text, '') ~* %(rel_dincl)s)", sql)
        self.assertEqual(params["rel_dincl"], "chatgpt")

    def test_null_description_is_coalesced_on_the_include_path_too(self):
        """Without COALESCE, `NULL ~* pattern` is NULL and the OR degrades to
        NULL for every not-yet-described row -- which would silently demote
        the title path as well, because NULL OR TRUE is TRUE but
        NULL AND ... is not."""
        sql, _ = relevance.tier_sql(
            {**relevance.DISABLED, "description_include": ["chatgpt"]})
        self.assertRegex(sql, r"COALESCE\(j\.description_text, ''\) ~\*")

    def test_title_exclude_still_gates_the_description_path(self):
        """A posting whose body mentions ChatGPT and whose title is
        'Account Executive' is still an Account Executive posting."""
        sql, _ = relevance.tier_sql(
            {**self.BASE, "description_include": ["chatgpt"]})
        arm = sql.split("THEN 1")[0]
        self.assertIn("j.title !~* %(rel_exclude)s", arm)
        # Both tier arms, or an excluded title would merely drop to tier 2.
        self.assertEqual(sql.count("j.title !~* %(rel_exclude)s"), 2)

    def test_works_with_no_title_include_at_all(self):
        sql, params = relevance.tier_sql(
            {**relevance.DISABLED, "description_include": ["chatgpt"],
             "title_exclude": ["\\ysdr\\y"]})
        self.assertNotIn("j.title ~*", sql)
        self.assertIn("j.title !~* %(rel_exclude)s", sql)
        self.assertNotIn("rel_include", params)


class TestIncludeGroups(unittest.TestCase):
    """A list of lists means AND-of-ORs: one term from every group."""

    def test_flat_list_is_one_group(self):
        self.assertEqual(relevance._include_groups(["a", "b"]), [["a", "b"]])

    def test_nested_list_is_several_groups(self):
        self.assertEqual(relevance._include_groups([["a", "b"], ["c"]]),
                         [["a", "b"], ["c"]])

    def test_mixed_shapes_raise_rather_than_guess(self):
        with self.assertRaises(ValueError):
            relevance._include_groups(["a", ["b"]])

    def test_groups_are_anded_with_distinct_params(self):
        sql, params = relevance.tier_sql(
            {**relevance.DISABLED,
             "description_include": [["chatgpt", "claude"], ["\\yjunior\\y"]]})
        self.assertIn("(COALESCE(j.description_text, '') ~* %(rel_dincl)s AND "
                      "COALESCE(j.description_text, '') ~* %(rel_dincl2)s)", sql)
        self.assertEqual(params["rel_dincl"], "chatgpt|claude")
        self.assertEqual(params["rel_dincl2"], "\\yjunior\\y")

    def test_single_group_keeps_the_unsuffixed_param_name(self):
        """union_sql and every existing caller bind rel_include by name."""
        _, params = relevance.tier_sql(
            {**relevance.DISABLED, "title_include": [["engineer", "developer"]]})
        self.assertEqual(params, {"rel_include": "engineer|developer"})

    def test_empty_group_does_not_shift_the_numbering(self):
        _, params = relevance.tier_sql(
            {**relevance.DISABLED, "title_include": [[], ["a"], ["b"]]})
        self.assertEqual(params, {"rel_include": "a", "rel_include2": "b"})


class TestPlatformExclude(unittest.TestCase):
    BASE = {**relevance.DISABLED, "title_include": ["engineer"]}

    def test_present_gates_both_tier_arms(self):
        sql, params = relevance.tier_sql(
            {**self.BASE, "platform_exclude": ["^builtin$", "^weworkremotely$"]})
        self.assertEqual(sql.count("j.platform !~*"), 2)
        self.assertEqual(params["rel_pfexcl"], "^builtin$|^weworkremotely$")

    def test_prefixes_do_not_collide(self):
        _, params = relevance.union_sql([
            {**self.BASE, "platform_exclude": ["^a$"]},
            {**self.BASE, "platform_exclude": ["^b$"]},
        ])
        self.assertEqual(params["rel0_pfexcl"], "^a$")
        self.assertEqual(params["rel1_pfexcl"], "^b$")


class TestParamPrefixIsolation(unittest.TestCase):
    def test_prefixes_do_not_collide_across_profiles(self):
        """union_sql embeds one tier_sql per profile in a single statement. A
        shared param name would not error -- it would apply one profile's regex
        under another's name."""
        cfgs = [
            {**relevance.DISABLED, "title_include": ["engineer"],
             "company_exclude": ["\\yaaa\\y"]},
            {**relevance.DISABLED, "title_include": ["designer"],
             "company_exclude": ["\\ybbb\\y"]},
        ]
        _, params = relevance.union_sql(cfgs)
        self.assertEqual(params["rel0_coexcl"], "\\yaaa\\y")
        self.assertEqual(params["rel1_coexcl"], "\\ybbb\\y")

    def test_empty_profile_list_is_false_not_true(self):
        sql, params = relevance.union_sql([])
        self.assertEqual(sql, "FALSE")
        self.assertEqual(params, {})


class TestSharedConfigFile(unittest.TestCase):
    """The live config must stay loadable and must keep excluding the spam."""

    def setUp(self):
        self.cfg = relevance.load()

    def test_loads(self):
        self.assertTrue(self.cfg["title_include"])

    def test_still_excludes_the_measured_relist_sites(self):
        joined = "|".join(self.cfg["company_exclude"])
        for name in ("remote zest", "remote click", "mysmartpros"):
            self.assertIn(name, joined)

    def test_does_not_exclude_url_only_aggregators(self):
        """bebee/jobleads/lensa appear in job_url but company_name holds the
        real employer for those rows -- excluding them would discard genuine
        postings. See _company_exclude_scope_note in the config."""
        joined = "|".join(self.cfg["company_exclude"]).lower()
        for name in ("bebee", "jobleads", "lensa", "learn4good"):
            self.assertNotIn(name, joined)


if __name__ == "__main__":
    unittest.main(verbosity=2)

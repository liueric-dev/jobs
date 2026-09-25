"""Unit tests for the shared PostgreSQL-regex filter compiler.

The Workday ingestion gate uses this SQL to limit detail requests. Tests pin
which predicates enter each tier and ensure omitted settings stay permissive.
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

    def test_explicit_override_starts_from_disabled_not_the_file(self):
        """An explicit override gets permissive defaults for omitted keys."""
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
        # from tier 1 to tier 2 and still be fetched.
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
    """An absent description_include must leave generated SQL unchanged."""

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

    #: Representative shared and override configuration shapes.
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

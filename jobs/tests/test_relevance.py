"""Unit tests for the relevance tiering SQL.

Run:  python3 jobs/tests/test_relevance.py

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
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))))

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
        self.assertEqual(relevance.DISABLED["company_exclude"], [])

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

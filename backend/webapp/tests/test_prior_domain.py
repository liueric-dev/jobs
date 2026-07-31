"""`app_users.prior_domain`: the closed vocabulary, and the join it enables.

WHAT THIS COLUMN IS FOR, because nothing reads it yet and a later session will
reasonably ask whether it can be deleted.

`labels.AXIS_B_FIELD` is "would_apply", and Axis B rows are stamped with the
SESSION's profile -- which is the COHORT profile, identical for every Builder.
So two Builders answering a bridge role from opposite backgrounds, both
correctly, are recorded as two people disagreeing. `labels.inter_annotator()`
reads that as disagreement and depresses the Axis B ceiling, and every model
score denominated in that ceiling then reads as BETTER than it is.

This column is the smallest thing that turns that disagreement from noise into
something decomposable. It does not change the form, the pinned item set, or
either labels.py function -- see test_the_decomposition_is_a_join below for why
it does not have to.

NO DATABASE HERE, the line test_set_profile.py and test_label_form.py both
draw. What needs a database -- that the CHECK refuses a bad value -- is asserted
against the generated SQL instead, which is the thing that would be wrong.
"""

import os
import sys
import unittest

WEBAPP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, WEBAPP_DIR)

import config  # noqa: E402,F401  (must come first -- performs the sys.path insert)

import manage_app_users  # noqa: E402
import schema_web  # noqa: E402

from evals import labels  # noqa: E402


class TestTheVocabularyIsDerivedNotInvented(unittest.TestCase):

    def test_the_first_eight_are_the_personas_industry_list_in_its_own_order(self):
        # config/pursuit-persona.json background_summary: "healthcare,
        # education, retail, hospitality, logistics, administration, the
        # trades, the military". Pinned in order, so a reordering that looked
        # cosmetic could not quietly become a different derivation.
        self.assertEqual(
            schema_web.PRIOR_DOMAINS[:8],
            ("healthcare", "education", "retail", "hospitality",
             "logistics", "administration", "trades", "military"))

    def test_the_only_two_added_values_are_other_and_none(self):
        self.assertEqual(schema_web.PRIOR_DOMAINS[8:], ("other", "none"))

    def test_none_is_in_the_vocabulary_and_null_is_not(self):
        # The distinction the column exists to preserve: 'none' is a real
        # answer about a real person (background_summary: the cohort is
        # "early-career AND career-changing"), NULL means nobody asked.
        # Collapsing them scores an unasked labeller as one with no background.
        self.assertIn("none", schema_web.PRIOR_DOMAINS)
        self.assertNotIn(None, schema_web.PRIOR_DOMAINS)
        self.assertNotIn("", schema_web.PRIOR_DOMAINS)
        self.assertNotIn("unknown", schema_web.PRIOR_DOMAINS)

    def test_no_duplicates(self):
        self.assertEqual(len(set(schema_web.PRIOR_DOMAINS)),
                         len(schema_web.PRIOR_DOMAINS))


class TestTheCheckCannotDriftFromThePythonList(unittest.TestCase):
    """One definition. The CHECK is generated, never typed out beside it.

    The failure this prevents is quiet and one-sided: widening PRIOR_DOMAINS
    while the database keeps refusing the new value surfaces as a constraint
    violation on one operator's command and nowhere else.
    """

    def test_every_value_appears_in_the_generated_check(self):
        for value in schema_web.PRIOR_DOMAINS:
            self.assertIn(f"'{value}'", schema_web._PRIOR_DOMAIN_CHECK)

    def test_the_check_admits_null(self):
        self.assertIn("prior_domain IS NULL", schema_web._PRIOR_DOMAIN_CHECK)

    def test_the_check_names_nothing_the_vocabulary_does_not(self):
        import re
        quoted = set(re.findall(r"'([^']+)'", schema_web._PRIOR_DOMAIN_CHECK))
        self.assertEqual(quoted, set(schema_web.PRIOR_DOMAINS))

    def test_the_table_ddl_uses_the_generated_check(self):
        # Rather than a second literal list inside the CREATE TABLE, which is
        # exactly the drift api/query_claims.py's docstring records.
        import inspect
        source = inspect.getsource(schema_web.ensure_schema)
        self.assertIn("app_users_prior_domain CHECK ({_PRIOR_DOMAIN_CHECK})",
                      source)


class TestTheCommandLineAgreesWithTheDatabase(unittest.TestCase):

    def _parser_choices(self, subcommand):
        parser = manage_app_users.build_parser()
        action = next(
            a for a in parser._subparsers._group_actions[0]
            .choices[subcommand]._actions if a.dest == "prior_domain")
        return action

    def test_add_offers_exactly_the_schema_vocabulary(self):
        action = self._parser_choices("add")
        self.assertEqual(tuple(action.choices), schema_web.PRIOR_DOMAINS)

    def test_set_profile_offers_exactly_the_schema_vocabulary(self):
        action = self._parser_choices("set-profile")
        self.assertEqual(tuple(action.choices), schema_web.PRIOR_DOMAINS)

    def test_the_flag_is_optional_and_defaults_to_not_asked(self):
        # required=True would make NULL unreachable, and NULL is the honest
        # value for every row created before anybody was asked -- including the
        # one that already exists and owns every label collected so far.
        for sub in ("add", "set-profile"):
            action = self._parser_choices(sub)
            self.assertFalse(action.required)
            self.assertIsNone(action.default)


class TestWhyNeitherLabelsFunctionHasToChange(unittest.TestCase):

    def test_the_decomposition_is_a_join(self):
        """labeller_id is app_users.id, so prior_domain is one JOIN away.

        This is the whole reason the column can be added without touching
        labels.inter_annotator() or labels.interpretable(), both of which are
        correct for Axis A and must stay exactly as they are.
        """
        import inspect
        source = inspect.getsource(manage_app_users)
        self.assertIn("prior_domain", source)

        submit = inspect.getsource(__import__("label").submit_label)
        # The value passed as labeller_id is the app_users primary key, not the
        # email and not the google_sub -- so `eval_labels.labeller_id =
        # app_users.id` is a plain equijoin.
        self.assertIn("labeller_id=user.id", "".join(submit.split()))

    def test_axis_a_carries_no_profile_so_it_is_unaffected(self):
        # The Axis B ceiling caveat is specific to Axis B. Axis A rows are
        # profile-independent by constraint, not by convention, so no labeller
        # attribute can change how they are read.
        self.assertEqual(labels.AXIS_B_FIELD, "would_apply")
        self.assertNotIn(labels.AXIS_B_FIELD, labels.AXIS_A_FIELDS)

    def test_this_change_adds_no_new_table_to_the_grant_set(self):
        # A new COLUMN needs no new grant -- table-level privileges cover it --
        # and adding one to TABLES_TOUCHED without a matching GRANT is the
        # failure REQUIRED_TABLES exists to prevent.
        self.assertIn("app_users", schema_web.TABLES_TOUCHED)
        self.assertEqual(schema_web.TABLES_TOUCHED,
                         frozenset(schema_web.REQUIRED_TABLES))


if __name__ == "__main__":
    unittest.main()

"""Unit tests for HN "Who is hiring?" header parsing.

Run:  python3 tests/test_hn_header.py

Every header below is a real one from the live thread. The bug being pinned:
parse_comment() took parts[1] as the title unconditionally, and posters do not
agree on field order, so 52 of 247 stored rows held a location, a salary or the
comment body in `title`.

WHY THE SKIP CASES MATTER AS MUCH AS THE FIX CASES
    The selector must decline rather than guess. "Junior | Remote | Any Time
    Zone" contains no role at all, and storing "Any Time Zone" as a job title
    is worse than storing nothing -- it pollutes the listing, and it feeds
    guess_seniority() and the relevance title filter downstream.
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import importlib.util  # noqa: E402

_HN = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                   "ingest", "hn-hiring.py")
_spec = importlib.util.spec_from_file_location("hn_hiring", _HN)
hn = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(hn)


def pick(header):
    return hn.pick_title_segment([p.strip() for p in header.split("|")])


class TestPicksTheRole(unittest.TestCase):
    def test_conventional_order_is_unchanged(self):
        """Company | Role | Location -- must behave exactly as before."""
        title, loc = pick("Third Iron | Senior Quality Engineer | REMOTE (US)")
        self.assertEqual(title, "Senior Quality Engineer")
        self.assertEqual(loc, "REMOTE (US)")

    def test_role_after_location(self):
        """Real row: the role is in field 3, the location in field 2."""
        title, _ = pick("Rail Europe ( https://wwww.raileurope.com/ ) | "
                        "Hiring in Paris and REMOTE | Senior SWE | Full-time")
        self.assertEqual(title, "Senior SWE")

    def test_role_after_city_state(self):
        title, _ = pick("Cascade Space (YC P25) | San Francisco, CA - ONSITE | "
                        "Senior Mechanical Engineer | Full-time")
        self.assertEqual(title, "Senior Mechanical Engineer")

    def test_salary_field_never_wins(self):
        title, _ = pick("BREAKFAST Studio | Senior Technical Program Manager | "
                        "Brooklyn, NYC (ONSITE) | Full-time | $180k-$210k base")
        self.assertEqual(title, "Senior Technical Program Manager")

    def test_title_outside_the_relevance_vocabulary_is_still_chosen(self):
        """title_include is this persona's filter, not a definition of "job
        title". "Chief Technology Officer" matches none of it and must still
        beat a city and an employment type."""
        title, _ = pick("MassChallenge | Chief Technology Officer | Boston, MA | "
                        "HYBRID (2 days/week) | Full-time")
        self.assertEqual(title, "Chief Technology Officer")

    def test_bare_domain_never_wins(self):
        """"spruceid.com" has no scheme, so URL_PATTERN alone missed it and it
        was chosen as the title."""
        title, _ = pick("Acme Corp | Backend Engineer | acme.com | REMOTE")
        self.assertEqual(title, "Backend Engineer")

    def test_remaining_fields_become_location_in_order(self):
        title, loc = pick("Mitty | First Engineer | Honolulu, HI or REMOTE | "
                          "Full-time | Base + Founding equity")
        self.assertEqual(title, "First Engineer")
        self.assertEqual(loc, "Honolulu, HI or REMOTE | Full-time | "
                              "Base + Founding equity")

    def test_ties_prefer_the_earliest_field(self):
        """Reproduces the old positional behaviour when nothing distinguishes
        the candidates, so this change can only improve on it."""
        title, _ = pick("Acme | Widget Wrangler | Sprocket Herder")
        self.assertEqual(title, "Widget Wrangler")


class TestDeclinesWhenThereIsNoRole(unittest.TestCase):
    def test_only_location_and_employment_type(self):
        title, loc = pick("SpruceID (YC W21) | REMOTE (US-Based Preferred) | "
                          "Full-Time | spruceid.com")
        self.assertIsNone(title)
        self.assertIsNone(loc)

    def test_only_work_mode_and_timezone(self):
        self.assertIsNone(pick("Junior | Remote | Any Time Zone")[0])

    def test_only_salary_and_location(self):
        self.assertIsNone(pick("Marketron | REMOTE (US) | Full-time | "
                               "70k - 90k | 3+ YOE required")[0])

    def test_no_fields_after_company(self):
        self.assertEqual(pick("SomeCompany"), (None, None))


class TestCaseInsensitivity(unittest.TestCase):
    def test_uppercase_onsite_is_recognised(self):
        """PLACE_PATTERN was originally compiled without IGNORECASE, so the
        "ONSITE" that HN posters actually write scored as neutral text and
        could win the title slot."""
        self.assertLess(hn._segment_score("ONSITE"), 0)
        self.assertLess(hn._segment_score("On-Site"), 0)
        self.assertLess(hn._segment_score("HYBRID"), 0)


class TestBodyAbsorption(unittest.TestCase):
    def test_swallowed_comment_body_is_penalised(self):
        """When a poster writes no <p> break the whole comment lands in the
        last field. Length is the only signal separating that from a title."""
        body = ("Full Time LiveKit is building the infrastructure layer for "
                "the voice AI era and we are hiring across the stack in many "
                "different areas of the product and platform")
        self.assertGreater(len(body), hn.MAX_TITLE_CHARS)
        self.assertLess(hn._segment_score(body), 0)

    def test_short_real_title_is_not_penalised(self):
        self.assertGreaterEqual(hn._segment_score("Senior Software Engineer"), 0)


class TestRolePatternTranslation(unittest.TestCase):
    def test_postgres_word_boundary_was_translated(self):
        """config/relevance.json holds POSTGRES regexes (\\y). Python's re
        raises "bad escape \\y", so a failure to translate would silently
        disable the positive signal via the except branch."""
        self.assertIsNotNone(hn.ROLE_PATTERN,
                             "role vocabulary failed to compile -- \\y was "
                             "probably not translated to \\b")
        self.assertTrue(hn.ROLE_PATTERN.search("Senior SWE"))
        self.assertTrue(hn.ROLE_PATTERN.search("Backend Developer"))
        self.assertFalse(hn.ROLE_PATTERN.search("REMOTE (US)"))


if __name__ == "__main__":
    unittest.main(verbosity=2)

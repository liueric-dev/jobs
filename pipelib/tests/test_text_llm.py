"""Tests for the jobs-side helpers extracted into pipelib.

These consolidate functions that were duplicated 4-6 times across
jobs/ingest/*.py. The regexes were byte-identical before consolidation, so
these tests pin current behaviour rather than proposing new behaviour --
their job is to prove the extraction changed nothing.
"""

import unittest
from datetime import datetime, timezone

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))))

from pipelib import llm, text  # noqa: E402


class TestSeniority(unittest.TestCase):
    def test_senior_titles(self):
        for title in ("Senior Engineer", "Staff SWE", "Principal Scientist",
                      "VP of Data", "Head of Platform", "Engineering Manager",
                      "Tech Lead"):
            self.assertEqual(text.guess_seniority(title), "senior", title)

    def test_entry_titles(self):
        for title in ("Junior Developer", "New Grad Engineer",
                      "Software Engineering Intern", "Entry-Level Analyst",
                      "Associate Engineer"):
            self.assertEqual(text.guess_seniority(title), "entry", title)

    def test_unmarked_is_mid(self):
        self.assertEqual(text.guess_seniority("Software Engineer"),
                         "mid_or_unspecified")

    def test_missing_title(self):
        self.assertEqual(text.guess_seniority(None), "unknown")
        self.assertEqual(text.guess_seniority(""), "unknown")

    def test_senior_wins_over_entry(self):
        # Order matters: SENIOR_PATTERN is checked first, so a title
        # containing both reads as senior. Pinning the existing precedence.
        self.assertEqual(text.guess_seniority("Senior Associate"), "senior")


class TestLocation(unittest.TestCase):
    def test_nyc_variants(self):
        for loc in ("New York, NY", "NYC", "Brooklyn", "Manhattan",
                    "Queens, New York", "Bronx", "Staten Island"):
            self.assertTrue(text.classify_location(loc)[0], loc)

    def test_remote(self):
        self.assertEqual(text.classify_location("Remote (US)"), (False, True))
        self.assertEqual(text.classify_location("Brooklyn, NY - Remote"),
                         (True, True))

    def test_neither(self):
        self.assertEqual(text.classify_location("Austin, TX"), (False, False))
        self.assertEqual(text.classify_location(None), (False, False))

    def test_word_boundaries(self):
        """\\b anchors mean substrings must not match."""
        self.assertFalse(text.classify_location("Remotely operated")[1],
                         "'Remotely' must not count as remote")
        self.assertFalse(text.classify_location("Newark")[0],
                         "'Newark' must not count as New York")


class TestStripHtmlAndSlug(unittest.TestCase):
    def test_strips_tags_and_collapses_space(self):
        self.assertEqual(text.strip_html("<p>Hello   <b>world</b></p>"),
                         "Hello world")

    def test_empty_becomes_none(self):
        self.assertIsNone(text.strip_html(""))
        self.assertIsNone(text.strip_html(None))
        self.assertIsNone(text.strip_html("<br/>"))

    def test_truncated(self):
        self.assertEqual(len(text.strip_html("x" * 9000)),
                         text.MAX_DESCRIPTION_CHARS)

    def test_slugify(self):
        self.assertEqual(text.slugify("Flatiron Health, Inc."),
                         "flatiron-health-inc")
        self.assertEqual(text.slugify(""), "unknown")
        self.assertEqual(text.slugify(None), "unknown")


class TestRelativeTime(unittest.TestCase):
    NOW = datetime(2026, 7, 24, 12, 0, tzinfo=timezone.utc)

    def test_days_ago(self):
        got = text.parse_relative_posted_at("3 days ago", now=self.NOW)
        self.assertTrue(got.startswith("2026-07-21T12:00:00"))

    def test_hours_and_weeks(self):
        self.assertTrue(text.parse_relative_posted_at("2 hours ago", now=self.NOW)
                        .startswith("2026-07-24T10:00:00"))
        self.assertTrue(text.parse_relative_posted_at("1 week ago", now=self.NOW)
                        .startswith("2026-07-17T12:00:00"))

    def test_unanchored_returns_none(self):
        """"30+ days ago" has no exact anchor -- None beats a guess."""
        self.assertIsNotNone(text.parse_relative_posted_at("30+ days ago",
                                                           now=self.NOW))
        self.assertIsNone(text.parse_relative_posted_at("recently", now=self.NOW))
        self.assertIsNone(text.parse_relative_posted_at(None))

    def test_days_since(self):
        self.assertAlmostEqual(
            text.days_since("2026-07-22T12:00:00", now=self.NOW), 2.0, places=3)
        self.assertIsNone(text.days_since(""))
        self.assertIsNone(text.days_since("not-a-timestamp"))


class TestLlmParsing(unittest.TestCase):
    def test_plain_json(self):
        self.assertEqual(llm.parse_json('{"fit_score": 7}'), {"fit_score": 7})

    def test_fenced_json(self):
        self.assertEqual(llm.parse_json('```json\n{"a": 1}\n```'), {"a": 1})

    def test_surrounded_by_chatter(self):
        self.assertEqual(
            llm.parse_json('Sure! Here is the result:\n{"a": 1}\nHope that helps.'),
            {"a": 1})

    def test_unparseable_returns_none(self):
        for bad in ("no json here", "", "{ broken", "}{"):
            self.assertIsNone(llm.parse_json(bad), repr(bad))

    def test_has_fields(self):
        self.assertTrue(llm.has_fields({"a": 1, "b": 2}, ("a", "b")))
        self.assertFalse(llm.has_fields({"a": 1}, ("a", "b")))
        self.assertFalse(llm.has_fields(None, ("a",)))
        self.assertFalse(llm.has_fields("not a dict", ("a",)))

    def test_failed_label_is_prefixed(self):
        self.assertTrue(llm.failed_label("m").startswith(llm.FAILED_PREFIX))


if __name__ == "__main__":
    unittest.main()

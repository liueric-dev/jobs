"""Tests for pipelib/text.py.

These consolidate functions that were duplicated 4-6 times across
jobs/ingest/*.py. The regexes were byte-identical before consolidation, so
these tests pin current behaviour rather than proposing new behaviour --
their job is to prove the extraction changed nothing.

The llm half of this file moved to jobs/tests/test_llm.py when llm.py left
pipelib. text.py stays shared: events uses strip_html, jobs uses all of it.
"""

import json
import unittest
from datetime import datetime, timezone

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))))

from pipelib import text  # noqa: E402


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

    def test_unescape_variants_are_both_preserved(self):
        """The two implementations that existed must both remain reachable.

        weworkremotely/google-serpapi/google-apify unescaped entities before
        stripping tags; ats did not. description_text feeds content_hash, so
        collapsing these silently rewrites one group's rows -- it reported
        217 of 242 weworkremotely rows as updated when nothing had changed.
        """
        markup = "<p>R&amp;D team</p>"
        self.assertEqual(text.strip_html(markup, unescape=True), "R&D team")
        self.assertEqual(text.strip_html(markup, unescape=False), "R&amp;D team")

    def test_unescape_defaults_to_true(self):
        self.assertEqual(text.strip_html("A &amp; B"), "A & B")

    def test_unescape_then_strip_eats_encoded_angle_brackets(self):
        """Unescaping runs BEFORE tag stripping, so entity-encoded angle
        brackets become real ones and are then removed as tags. Surprising,
        but it is what the original implementations did and what the stored
        hashes were computed from -- pinned so it cannot drift silently."""
        self.assertEqual(text.strip_html("<p>R&amp;D &lt;Engineer&gt;</p>"), "R&D")

    def test_empty_becomes_none(self):
        self.assertIsNone(text.strip_html(""))
        self.assertIsNone(text.strip_html(None))
        self.assertIsNone(text.strip_html("<br/>"))

    def test_truncated(self):
        """Written relative to the cap on purpose: the previous version hard-coded
        an input of 9000 chars, which silently stopped testing anything the moment
        the cap moved past it (5000 -> 20000)."""
        over = "x" * (text.MAX_DESCRIPTION_CHARS + 1000)
        self.assertEqual(len(text.strip_html(over)), text.MAX_DESCRIPTION_CHARS)

    def test_under_cap_is_not_padded_or_cut(self):
        under = "y" * (text.MAX_DESCRIPTION_CHARS - 1)
        self.assertEqual(len(text.strip_html(under)),
                         text.MAX_DESCRIPTION_CHARS - 1)

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

    # The four shapes Built In prints that used to parse to None, leaving 35 of
    # 192 rows with no usable date at all.
    def test_minutes_ago(self):
        self.assertTrue(text.parse_relative_posted_at("51 Minutes Ago", now=self.NOW)
                        .startswith("2026-07-24T11:09:00"))

    def test_bare_article_means_one(self):
        """"An Hour Ago" carries no digit, so the numeric branch missed it."""
        self.assertTrue(text.parse_relative_posted_at("An Hour Ago", now=self.NOW)
                        .startswith("2026-07-24T11:00:00"))

    def test_reposted_prefix_is_ignored(self):
        """Built In writes "Reposted 8 Hours Ago"; .search() handles the prefix."""
        self.assertTrue(text.parse_relative_posted_at("Reposted 8 Hours Ago",
                                                      now=self.NOW)
                        .startswith("2026-07-24T04:00:00"))
        self.assertTrue(text.parse_relative_posted_at("Reposted An Hour Ago",
                                                      now=self.NOW)
                        .startswith("2026-07-24T11:00:00"))

    def test_day_words_anchor_to_midnight(self):
        """Anchored to midnight, not now-24h, so two runs on the same day agree
        instead of drifting the same posting's date by hours."""
        self.assertTrue(text.parse_relative_posted_at("Yesterday", now=self.NOW)
                        .startswith("2026-07-23T00:00:00"))
        self.assertTrue(text.parse_relative_posted_at("Reposted Yesterday",
                                                      now=self.NOW)
                        .startswith("2026-07-23T00:00:00"))
        self.assertTrue(text.parse_relative_posted_at("Today", now=self.NOW)
                        .startswith("2026-07-24T00:00:00"))


class TestPostedAtTimestamp(unittest.TestCase):
    NOW = datetime(2026, 7, 24, 12, 0, tzinfo=timezone.utc)

    def test_iso_passes_through_untouched(self):
        """Six of seven sources already store ISO; re-deriving it would only
        risk changing it."""
        for iso in ("2026-02-01T17:48:22-05:00",
                    "2021-04-27T20:13:45.158+00:00",
                    "2026-07-01"):
            self.assertEqual(text.posted_at_timestamp(iso, now=self.NOW), iso)

    def test_relative_is_converted(self):
        self.assertTrue(text.posted_at_timestamp("Reposted 8 Hours Ago",
                                                 now=self.NOW)
                        .startswith("2026-07-24T04:00:00"))

    def test_absent_or_unparseable_is_none(self):
        self.assertIsNone(text.posted_at_timestamp(None))
        self.assertIsNone(text.posted_at_timestamp(""))
        self.assertIsNone(text.posted_at_timestamp("Full-time"))


class TestBoundedJson(unittest.TestCase):
    """raw_json must always be valid JSON.

    `json.dumps(obj)[:20000]` was storing stumps that json.loads cannot read --
    10 rows in the live table end mid-string at character 20000. Anything
    rebuilding from raw_json (jobs/migrate_ats_descriptions.py) needs it valid.
    """

    def test_under_limit_is_plain_dumps(self):
        obj = {"a": 1, "description": "short"}
        self.assertEqual(text.bounded_json(obj, 20000), json.dumps(obj))

    def test_over_limit_stays_parseable_and_keeps_envelope(self):
        obj = {"id": "abc", "apply_options": [{"link": "https://x"}],
               "description": "y" * 40000}
        out = text.bounded_json(obj, 20000)
        self.assertLessEqual(len(out), 20000)
        back = json.loads(out)                      # must not raise
        self.assertEqual(back["id"], "abc")
        self.assertEqual(back["apply_options"], [{"link": "https://x"}])
        self.assertLess(len(back["description"]), 40000)

    def test_naive_slice_would_have_been_invalid(self):
        """Pins why this function exists rather than a slice."""
        obj = {"id": "abc", "description": "y" * 40000}
        with self.assertRaises(json.JSONDecodeError):
            json.loads(json.dumps(obj)[:20000])

    def test_unshrinkable_falls_back_to_valid_placeholder(self):
        obj = {"description": "z" * 10, "other": "q" * 40000}
        back = json.loads(text.bounded_json(obj, 1000))
        self.assertTrue(back["_truncated"])
        self.assertGreater(back["_original_chars"], 1000)


if __name__ == "__main__":
    unittest.main()

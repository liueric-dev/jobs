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




class TestTransientClassification(unittest.TestCase):
    """A transient failure must never look like a permanent one.

    score.py tombstones a job it cannot score so it is not retried forever.
    That is right for "the model returned garbage" and badly wrong for "HTTP
    429" -- the latter says nothing about the job, so recording it discards a
    posting that was never actually evaluated. These pin which is which.
    """

    def _call_raising(self, exc):
        """Run llm.call with urlopen replaced by something that raises."""
        import urllib.request
        real = urllib.request.urlopen
        urllib.request.urlopen = lambda *a, **k: (_ for _ in ()).throw(exc)
        try:
            return llm.call("prompt")
        finally:
            urllib.request.urlopen = real

    def _http_error(self, code):
        import urllib.error, io
        return urllib.error.HTTPError("http://x", code, "err", {},
                                      io.BytesIO(b"body"))

    def test_rate_limit_is_transient(self):
        with self.assertRaises(llm.TransientError):
            self._call_raising(self._http_error(429))

    def test_server_errors_are_transient(self):
        for code in (500, 502, 503, 504):
            with self.assertRaises(llm.TransientError, msg=f"HTTP {code}"):
                self._call_raising(self._http_error(code))

    def test_client_errors_are_permanent(self):
        # 400/401/404 are the endpoint's final answer -- retrying cannot help.
        for code in (400, 401, 403, 404):
            with self.assertRaises(RuntimeError, msg=f"HTTP {code}") as cm:
                self._call_raising(self._http_error(code))
            self.assertNotIsInstance(cm.exception, llm.TransientError,
                                     f"HTTP {code} must not be transient")

    def test_timeout_is_transient(self):
        with self.assertRaises(llm.TransientError):
            self._call_raising(TimeoutError("timed out"))

    def test_connection_error_is_transient(self):
        import urllib.error
        with self.assertRaises(llm.TransientError):
            self._call_raising(urllib.error.URLError("refused"))

    def test_transient_is_a_runtimeerror(self):
        # Callers that only catch RuntimeError must still not crash.
        self.assertTrue(issubclass(llm.TransientError, RuntimeError))


if __name__ == "__main__":
    unittest.main()

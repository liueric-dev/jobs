"""Tests for Built In detail-page description extraction.

These exist because the original failure was silent: the selector matched
nothing, no error was raised, and 187 rows were stored with an empty
description while every other source averaged ~4,900 chars. A regression here
would look exactly the same -- no exception, just empty text -- so the
escaped-MIME-type case is pinned explicitly.
"""

import importlib.util
import os
import unittest

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(os.path.dirname(_HERE))

# The module has a hyphen in its name, so it cannot be imported normally.
_spec = importlib.util.spec_from_file_location(
    "builtin_nyc", os.path.join(_ROOT, "jobs", "ingest", "builtin-nyc.py"))
builtin_nyc = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(builtin_nyc)

extract_description = builtin_nyc.extract_description


def page(script_type, body):
    return f'<html><head><script type="{script_type}">{body}</script></head></html>'


GRAPH = ('{"@context":"https://schema.org","@graph":[{"@type":"JobPosting",'
         '"title":"Engineer","description":"<p>Build <b>things</b>.</p>"}]}')


class TestExtractDescription(unittest.TestCase):
    def test_escaped_mime_type(self):
        """The actual site markup: the '+' is written &#x2B;.

        This is the case that broke -- if only the literal spelling is
        matched, this returns None and rows silently arrive empty.
        """
        self.assertEqual(
            extract_description(page("application/ld&#x2B;json", GRAPH)),
            "Build things.")

    def test_literal_mime_type(self):
        """The conventional spelling must keep working too."""
        self.assertEqual(
            extract_description(page("application/ld+json", GRAPH)),
            "Build things.")

    def test_bare_object_not_wrapped_in_graph(self):
        body = '{"@type":"JobPosting","description":"Plain text."}'
        self.assertEqual(
            extract_description(page("application/ld+json", body)), "Plain text.")

    def test_html_is_stripped_and_whitespace_collapsed(self):
        body = ('{"@type":"JobPosting","description":'
                '"<ul>\\n  <li>One</li>\\n  <li>Two</li>\\n</ul>"}')
        self.assertEqual(
            extract_description(page("application/ld+json", body)), "One Two")

    def test_entities_are_unescaped(self):
        body = ('{"@type":"JobPosting","description":'
                '"R&amp;D at Ben &amp; Jerry&#39;s"}')
        self.assertEqual(
            extract_description(page("application/ld+json", body)),
            "R&D at Ben & Jerry's")

    def test_non_jobposting_nodes_are_skipped(self):
        body = ('{"@graph":[{"@type":"Organization","description":"About us."},'
                '{"@type":"JobPosting","description":"The role."}]}')
        self.assertEqual(
            extract_description(page("application/ld+json", body)), "The role.")

    def test_malformed_block_does_not_hide_a_later_good_one(self):
        html = (page("application/ld+json", "{not json")
                + page("application/ld+json", GRAPH))
        self.assertEqual(extract_description(html), "Build things.")

    def test_missing_description_returns_none(self):
        body = '{"@type":"JobPosting","title":"Engineer"}'
        self.assertIsNone(extract_description(page("application/ld+json", body)))

    def test_empty_description_returns_none(self):
        """Must be None, not '' -- callers test truthiness to decide retry."""
        body = '{"@type":"JobPosting","description":""}'
        self.assertIsNone(extract_description(page("application/ld+json", body)))

    def test_markup_only_description_returns_none(self):
        body = '{"@type":"JobPosting","description":"<div></div>"}'
        self.assertIsNone(extract_description(page("application/ld+json", body)))

    def test_no_script_at_all(self):
        self.assertIsNone(extract_description("<html><body>nope</body></html>"))


if __name__ == "__main__":
    unittest.main()

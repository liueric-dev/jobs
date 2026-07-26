"""Unit tests for ATS description extraction.

Run:  python3 tests/test_ats_descriptions.py

stdlib unittest, same as tests/test_match.py and pipelib/tests.

WHY THESE TESTS EXIST
    Every one of these pins a bug that was live in the database, not a
    hypothetical. 7,182 Greenhouse rows -- 65% of the whole table -- stored
    their entire description as escaped markup (`&lt;div class=&quot;...`),
    and 1,521 Ashby rows stored `&amp;` where `&` belonged.

    The failure mode is what makes it worth a test: nothing errored. The
    ingest reported success, the row count was right, `description_text` was
    non-empty and passed every not-null check. It was simply unreadable, and
    it stayed that way through two ingest runs because no assertion ever
    looked at the *content* of the field.

    The Greenhouse case is also the one a future reader is most likely to
    "simplify" back into a bug, because a single unescape looks obviously
    sufficient and is measurably not (277 of 300 sampled rows still held
    literal entities after one pass). test_single_unescape_is_insufficient
    exists to fail loudly when someone tries.
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "ingest"))

import ats  # noqa: E402
from pipelib import text  # noqa: E402

COMPANY = {"token": "acme", "name": "Acme", "is_nyc_hq": True,
           "is_ai_focused": False}

#: A Greenhouse `content` value, in the shape the API actually returns it:
#: HTML that has been escaped once, so the tags are entities and any entity in
#: the source text is double-escaped.
GREENHOUSE_CONTENT = (
    "&lt;div class=&quot;content-intro&quot;&gt;"
    "&lt;h2&gt;&lt;strong&gt;About Acme:&amp;nbsp;&lt;/strong&gt;&lt;/h2&gt;\n"
    "&lt;p&gt;We build R&amp;amp;D tools.&lt;/p&gt;"
)


class TestGreenhouseDescription(unittest.TestCase):
    def test_produces_plain_text(self):
        self.assertEqual(ats.greenhouse_description(GREENHOUSE_CONTENT),
                         "About Acme: We build R&D tools.")

    def test_no_markup_survives(self):
        out = ats.greenhouse_description(GREENHOUSE_CONTENT)
        for fragment in ("&lt;", "&gt;", "&quot;", "&nbsp;", "&amp;",
                         "<div", "<h2", "<p>"):
            self.assertNotIn(fragment, out,
                             f"{fragment!r} leaked into description_text")

    def test_single_unescape_is_insufficient(self):
        """The regression guard. Greenhouse is escaped one level deeper than
        every other source, so strip_html's own single unescape leaves entities
        behind: `&amp;nbsp;` becomes `&nbsp;`, which then survives tag
        stripping. If this ever passes, greenhouse_description has been
        "simplified" into the bug it was written to fix."""
        naive = text.strip_html(GREENHOUSE_CONTENT)
        self.assertIn("&nbsp;", naive)
        self.assertNotIn("&nbsp;", ats.greenhouse_description(GREENHOUSE_CONTENT))

    def test_empty_and_none(self):
        self.assertIsNone(ats.greenhouse_description(None))
        self.assertIsNone(ats.greenhouse_description(""))

    def test_normalizer_uses_it(self):
        rec = ats.normalize_greenhouse(COMPANY, {
            "id": 1, "title": "Backend Engineer", "content": GREENHOUSE_CONTENT,
            "location": {"name": "New York, NY"}, "absolute_url": "https://x/1",
        })
        self.assertEqual(rec["description_text"], "About Acme: We build R&D tools.")


class TestRealHtmlSources(unittest.TestCase):
    """Ashby and Lever serve real HTML, so one unescape is correct for them.

    Verified against live payloads: Ashby returns `<h1>Who We Are</h1>` and
    Lever returns `<p><strong>About Finix</strong>`, not entity-escaped
    equivalents. They were passing unescape=False, which is what left `&amp;`
    in the stored text.
    """

    def test_ashby_unescapes_entities(self):
        rec = ats.normalize_ashby(COMPANY, {
            "id": "a1", "title": "SRE", "location": "Remote",
            "jobUrl": "https://x/a1",
            "descriptionHtml": "<h1>Who We Are</h1><p>R&amp;D and Q&amp;A</p>",
        })
        self.assertEqual(rec["description_text"], "Who We Are R&D and Q&A")
        self.assertNotIn("&amp;", rec["description_text"])

    def test_lever_unescapes_entities(self):
        rec = ats.normalize_lever(COMPANY, {
            "id": "l1", "text": "Data Engineer", "hostedUrl": "https://x/l1",
            "categories": {"location": "Remote", "department": "Eng"},
            "description": "<p><strong>About Finix</strong> R&amp;D</p>",
        })
        self.assertEqual(rec["description_text"], "About Finix R&D")
        self.assertNotIn("&amp;", rec["description_text"])


class TestDescriptionCap(unittest.TestCase):
    def test_storage_cap_is_display_sized_not_prompt_sized(self):
        """The cap governs what is STORED. extract.py and score.py each
        truncate to 3,000 before building a prompt, so this number must stay
        comfortably above a real posting (~6.3k chars average on Greenhouse)
        without anyone worrying about token spend."""
        self.assertGreaterEqual(text.MAX_DESCRIPTION_CHARS, 12000)

    def test_long_greenhouse_content_is_capped(self):
        huge = "&lt;p&gt;" + ("word " * 20000) + "&lt;/p&gt;"
        self.assertEqual(len(ats.greenhouse_description(huge)),
                         text.MAX_DESCRIPTION_CHARS)


if __name__ == "__main__":
    unittest.main(verbosity=2)

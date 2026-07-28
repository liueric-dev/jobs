"""The labelling form: what it renders, and what it refuses.

NO DATABASE HERE, DELIBERATELY, AND THE LINE IS DRAWN ON PURPOSE
    This package's suite covers what is logic rather than I/O (README,
    "Tests"). The claims below are all about rendering and request handling,
    and a fake connection proves every one of them.

    The claims a fake connection CANNOT prove -- that the two axes are keyed
    independently, that a gate-rejected row can be labelled at all -- are in
    ../../tests/test_labels.py against a real scratch schema, because those
    are properties of two partial unique indexes and a fake conn accepts the
    insert whether or not they exist.

WHY THE ESCAPING TEST IS HERE AND NOT AN AFTERTHOUGHT
    Postings are scraped HTML from seven sources and every one of them is
    attacker-influenced: a company controls its own job description. This page
    is the one URL ten volunteers are emailed and told to sign into with
    Google. An unescaped title is stored XSS against a session cookie.
"""

import os
import sys
import unittest

WEBAPP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, WEBAPP_DIR)

import config  # noqa: E402,F401  (must come first -- performs the sys.path insert)

import label   # noqa: E402
from evals import labels as labels_mod  # noqa: E402


_HOSTILE = "Ops Lead <script>alert(document.cookie)</script>"


def _job(**over):
    """The slice of a `jobs` row _render_form reads."""
    row = {"id": "g1", "title": _HOSTILE, "company_name": "Acme & Sons",
           "location_raw": "NYC", "platform": "builtin",
           "description_text": "Runs our AI tooling.\n<b>Entry level.</b>"}
    row.update(over)
    return row


def _render(**over):
    return label._render_form(_job(**over), labels_mod.questions(), "ls1",
                              0, 30, True).body.decode()


class TestFormRendering(unittest.TestCase):

    def test_a_hostile_title_is_escaped_not_executed(self):
        body = _render()
        self.assertNotIn("<script>", body)
        self.assertIn("&lt;script&gt;", body)

    def test_a_hostile_description_is_escaped(self):
        body = _render(description_text="<img src=x onerror=alert(1)>")
        self.assertNotIn("<img", body)
        self.assertIn("&lt;img", body)

    def test_the_metadata_separator_survives_but_the_data_does_not(self):
        # Escaped per field and joined afterwards. Escaping the joined string
        # would render the separator as literal "&middot;", and escaping
        # nothing would be the same hole as the title.
        body = _render()
        self.assertIn("&middot;", body)
        self.assertIn("Acme &amp; Sons", body)

    def test_every_question_is_on_the_form_with_its_vocabulary(self):
        body = _render()
        for question in labels_mod.questions():
            self.assertIn(f"name='{question.axis}:{question.field}'", body)
            for choice in question.choices:
                self.assertIn(f"value='{choice}'", body)

    def test_the_two_axes_are_labelled_differently_for_the_human(self):
        # A Builder has to know which questions are about the posting and
        # which are about them. If they answer axis A with a preference the
        # whole objective measurement is quietly contaminated.
        body = _render()
        self.assertIn("from what the posting says", body)
        self.assertIn("Your own view", body)

    def test_there_is_always_a_way_to_abstain(self):
        # A labeller with no way to say "I can't tell" guesses, and a guess
        # recorded as a label is exactly the poison the golden set exists to
        # avoid. One per question, and none of them preselected.
        body = _render()
        self.assertEqual(body.count("value='unsure'"),
                         len(labels_mod.questions()))
        self.assertNotIn("checked", body)

    def test_the_full_description_is_shown_not_a_summary(self):
        # 03-metrics-and-golden-set.md:127 -- the point is a human judgement on
        # the same input the model got. A `summary` would be showing them the
        # model's reading of the posting instead.
        self.assertNotIn("summary", label._DETAIL_COLUMNS)
        self.assertIn("description_text", label._DETAIL_COLUMNS)

    def test_progress_and_the_shared_marker_are_visible(self):
        self.assertIn("0 of 30 done", _render())
        self.assertIn("shared posting", _render())

    def test_no_javascript_and_no_external_asset(self):
        # A build step or a CDN is a way for this page to stop working for a
        # volunteer, months from now, for reasons nobody is watching for.
        body = _render()
        self.assertNotIn("<script", body)
        self.assertNotIn("http://", body)
        self.assertNotIn("https://", body)


class TestTheRouteCannotWriteAModelsAnswer(unittest.TestCase):

    def test_the_module_never_reaches_a_model(self):
        with open(os.path.join(WEBAPP_DIR, "label.py"), encoding="utf-8") as fh:
            source = fh.read()
        for forbidden in ("import llm", "call_detailed", "extract_one_job"):
            self.assertNotIn(forbidden, source)

    def test_an_unanswered_question_is_not_an_abstention(self):
        # Distinct states: "I looked and cannot tell" is data, "the form was
        # submitted without this field" is not. Recording the second as the
        # first invents a judgement nobody made.
        self.assertIsNone(labels_mod.validate("A", "seniority_level", "unsure"))
        with self.assertRaises(ValueError):
            labels_mod.validate("A", "seniority_level", "definitely mid")


if __name__ == "__main__":
    unittest.main()

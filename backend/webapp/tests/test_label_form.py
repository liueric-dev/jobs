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
        # `git show refactor-freeze-2026-08-02:docs/ingestion_tests/03-metrics-and-golden-set.md:127` -- the point is a human judgement on
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


class TestTheLabellerIsBlindToTheModelsAnswer(unittest.TestCase):
    """29:105 -- "Labellers were blind to `fit_score`".

    29:72-73 calls seeing it "the single easiest way to invalidate the whole
    exercise": a human shown the model's number first collapses their
    judgement onto it, and the resulting agreement measures the anchoring
    rather than the extraction.

    The property holds by construction -- _DETAIL_COLUMNS is six columns of
    `jobs` (label.py:78), _job() selects only those (label.py:112-128), and
    neither job_scores nor job_matches is queried anywhere in the module --
    and until this class nothing asserted it.

    THE SOURCE-LEVEL HALF OF THIS IS IN ../../tests/test_labels.py, because
    `fastapi` is not installed in this environment and this whole package's
    suite cannot run. What is here is what needs the module imported: the
    rendered page itself.
    """

    #: A row carrying everything a future, wider _job() might hand the
    #: renderer. _render_form reads named keys, so none of this can reach the
    #: page today -- which is exactly the property being pinned, against the
    #: day somebody adds `{job.get('fit_score')}` to the header for context.
    #:
    #: The values are sentinels rather than plausible ones, in both
    #: directions. A bare `87` for fit_score is indistinguishable from the
    #: stylesheet's `.87rem` and the assertion would fail for a reason that
    #: is not about labelling; `junior` and `builds_llm_features` are printed
    #: as radio choices, so asserting THOSE absent would be asserting the
    #: form is broken.
    LEAKY = {"fit_score": "FIT-SCORE-87", "match_score": "MATCH-SCORE-74",
             "stratum": "surfaced",
             "summary": "the model's own reading of this posting",
             "seniority_level": "SENIORITY-FROM-JOB-FACTS",
             "ai_involvement": "AI-INVOLVEMENT-FROM-JOB-FACTS"}

    def test_the_rendered_page_carries_no_model_output(self):
        body = _render(**self.LEAKY)
        for value in self.LEAKY.values():
            self.assertNotIn(str(value), body)
        # And the field names, for the four that are not themselves questions.
        # `ai_involvement` and `seniority_level` ARE asked, so their names
        # appear as form input names and their absence is not the property.
        for key in ("fit_score", "match_score", "stratum", "summary"):
            self.assertNotIn(key, body)

    def test_the_detail_columns_are_six_columns_of_jobs_and_no_score(self):
        # label.py:78. What the page can render is bounded by this tuple, so
        # this is the assertion that has to be maintained, not the one above.
        self.assertEqual(label._DETAIL_COLUMNS,
                         ("id", "title", "company_name", "location_raw",
                          "platform", "description_text"))

    def test_the_stratum_is_never_shown_to_the_labeller(self):
        # A stratum name is the pipeline's verdict in one word: "surfaced"
        # says the ranker already liked this posting and "gate_rejected" says
        # it never got in. next_item() returns it (labels.py:750) and
        # label_form deliberately passes only `overlap` to the renderer.
        import inspect
        self.assertNotIn(
            "stratum", inspect.signature(label._render_form).parameters)
        for shared in (True, False):
            body = label._render_form(_job(), labels_mod.questions(), "ls1",
                                      0, 30, shared).body.decode()
            for stratum in labels_mod.STRATA:
                self.assertNotIn(stratum, body)


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


class TestTheRoundTwoSurface(unittest.TestCase):
    """The web half of the round-2 path, which had no test at all.

    Every round-2 assertion in the repo was at the labels.py layer, so the
    route -- the ?round=2 branch, the hidden field, the POST allowlist, the
    round-preserving 303 and the two exhaustion messages -- was unasserted.
    That is how the defect below shipped: the queue was right and the PAGE was
    wrong, and no test looked at the page.
    """

    def test_the_hidden_round_travels_with_the_form(self):
        # Without this the POST cannot know which round it is answering, and
        # every answer lands as round 1 -- which is the original defect.
        self.assertIn("name=round_no value='1'", _render())
        second = label._render_form(_job(), labels_mod.questions(), "ls1",
                                    0, 10, True, round_no=2).body.decode()
        self.assertIn("name=round_no value='2'", second)

    def test_the_second_look_says_so_and_says_not_from_memory(self):
        second = label._render_form(_job(), labels_mod.questions(), "ls1",
                                    0, 10, True, round_no=2).body.decode()
        self.assertIn("second look", second)
        self.assertIn("not from memory", second)
        self.assertNotIn("not from memory", _render())

    def test_the_round_allowlist_admits_only_one_and_two(self):
        # A bogus round would write a THIRD round that no agreement function
        # reads -- a label that cost a volunteer's attention and is invisible
        # to every report. There is also no CHECK on the column, so this parse
        # is where the invariant lives.
        #
        # THIS CALLS THE PARSER. An earlier version re-implemented the
        # expression here, which passes whatever the route does and therefore
        # asserted nothing -- the tautology this repo names elsewhere. That is
        # why parse_round is module-level and public.
        for raw, expect in (("2", 2), (" 2 ", 2), ("1", 1), ("3", 1), ("", 1),
                            ("two", 1), ("2x", 1), ("02", 1), (None, 1)):
            self.assertEqual(label.parse_round(raw), expect,
                             f"{raw!r} must resolve to round {expect}")
        # And both entry points use it, so the query string and the form body
        # cannot disagree about what round means.
        code = open(label.__file__, encoding="utf-8").read()
        self.assertEqual(code.count("parse_round("), 3,
                         "one definition, one GET caller, one POST caller")

    def test_exhausted_for_now_is_not_all_done(self):
        # THE DEFECT THIS PINS. round_two_ready() opens the round off the
        # labeller's EARLIEST round-1 answer; next_item() admits rows one at a
        # time as each reaches ROUND_TWO_DELAY_DAYS. Someone who answered the
        # overlap block over two sittings therefore empties the queue with rows
        # still maturing, and the page used to tell them "You have labelled all
        # 10 postings in this set. Nothing else is needed from you." -- ending
        # their part in the one measurement that has no second sitting.
        more = label._MORE_LATER.format(done=1, waiting=10, days=7)
        self.assertIn("1 of your 10", more)
        self.assertIn("this is not the end of the second look", more)
        # And the two messages must not be confusable.
        done = label._ALL_DONE.format(total=10)
        self.assertIn("Nothing else is needed from you", done)
        self.assertNotIn("Nothing else is needed", more)

    def test_the_two_reasons_a_round_two_queue_is_empty_are_different_pages(self):
        # "You have no round-1 answers to re-check" and "come back when they
        # mature" and "you are finished" are three states. A volunteer who
        # cannot tell them apart either gives up or retries forever, and the
        # operator hears about neither.
        pages = {label._NO_ROUND_ONE, label._TOO_SOON, label._MORE_LATER,
                 label._ALL_DONE}
        self.assertEqual(len(pages), 4, "each state needs its own page")
        self.assertIn("{when}", label._TOO_SOON)
        self.assertIn("{waiting}", label._MORE_LATER)

    def test_the_too_soon_page_names_a_date(self):
        # Not "later". A refusal with no date is indistinguishable from a bug.
        soon = label._TOO_SOON.format(n=10, when="2026-08-06")
        self.assertIn("2026-08-06", soon)
        self.assertIn("remember", soon)


if __name__ == "__main__":
    unittest.main()

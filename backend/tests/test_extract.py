"""Unit tests for the extraction policy, the vote, and the drain loop.

Run:  python3 tests/test_extract.py

stdlib unittest -- pytest is not installed and is not worth a dependency here.

WHY THESE TESTS AND NOT OTHERS
    Three properties decide whether extract.py is doing what
    config/extraction-policy.json says it does, and all three fail SILENTLY:

      * one platform gets three calls and every other gets exactly one. A
        renamed platform string, or a policy file that failed to load, would
        quietly drop everything back to one pass -- and a one-pass row looks
        exactly like a three-pass unanimous one unless something counts the
        calls. So the calls are counted, with a fake `call` that spends
        nothing.
      * the vote is pure and its ties are pinned. A tie rule that drifts
        changes stored facts without changing any test that only checks the
        easy case, and the fallback ("the first pass's value") is precisely
        the behaviour this change must never be worse than.
      * a zero-progress batch stops the drain loop. DEFERRED rows stay
        eligible, so a down endpoint re-selects the same batch forever; a
        loop that did not break here would spin until its deadline against
        an endpoint already returning 429, which is strictly worse than the
        single batch it replaces. Nothing about that failure is visible in
        production until it has already happened.

Nothing here touches a database or an endpoint.
"""

import html
import json
import os
import re
import sys
import tempfile
import unittest
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import extract  # noqa: E402
import llm  # noqa: E402
import schema  # noqa: E402
from evals import cassettes, ingest_modules, scratchdb  # noqa: E402
from lib import dbconn, envfile, text as text_module  # noqa: E402

#: The pipeline's own .env, the way run-daily.py loads it -- see
#: tests/test_scratchdb.py, which does the same. Tests must not depend on the
#: caller having exported anything.
envfile.load(os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), ".env"))

requires_db = unittest.skipUnless(
    scratchdb.available(),
    "no scratch database: set DATABASE_URL (or JOBS_SCRATCH_DATABASE_URL)")


#: One complete normalize()-shaped result. Tests mutate copies of this, so
#: every field job_facts stores is present in every vote and a new column
#: cannot be forgotten by a test that only builds the fields it cares about.
BASE = {
    "seniority_level": "junior",
    "years_experience_min": 2,
    "years_experience_max": 4,
    "role_archetype": "backend",
    "role_track": "software_engineering",
    "tech_stack": '["python"]',
    "ai_involvement": "uses_ai_tools",
    "ml_research_required": False,
    "advanced_degree_required": False,
    "customer_facing": True,
    "remote_policy": "hybrid",
    "employment_type": "full_time",
    "comp_min": 100000,
    "comp_max": 140000,
    "comp_currency": "USD",
    "gap_friendly_language": False,
    "visa_sponsorship": "unknown",
    "summary": "A backend role. It uses Python.",
}


def result(**overrides):
    return {**BASE, **overrides}


def job(platform, job_id="j1"):
    return {"id": job_id, "title": "Engineer", "company_name": "Acme",
            "location_raw": "NYC", "platform": platform,
            "description_text": "We are hiring an engineer."}


#: Sentinel for payload(): "delete this key entirely", which is a different
#: response from "answer it with null" and a very different one from "answer
#: it false". Telling those three apart is the whole of the missingness work.
_OMIT = object()


def payload(**overrides):
    """A raw model response dict that normalize() will accept.

    Only the REQUIRED_FIELDS keys are present by default, so a test that
    wants to know what normalize() does with an unanswered field can simply
    not mention it.
    """
    p = {
        "seniority_level": "junior", "role_archetype": "backend",
        "remote_policy": "hybrid", "tech_stack": ["python"],
        "summary": "A backend role. It uses Python.",
    }
    p.update(overrides)
    return {k: v for k, v in p.items() if v is not _OMIT}


def response(**overrides):
    """The same thing as JSON, for the tests that go through a fake `call`."""
    return json.dumps(payload(**overrides))


class PolicyTests(unittest.TestCase):
    """The shipped config, read as extract.py reads it."""

    def setUp(self):
        self.policy = extract.load_policy()

    def test_only_hn_is_below_the_threshold(self):
        # The measured figures are task 06's, n=115, 2026-07-28. If a
        # re-measurement moves one, this is the test that says which
        # platforms changed cost.
        multi = {p for p in self.policy["measured_agreement"]
                 if extract.passes_for(p, self.policy) > 1}
        self.assertEqual(multi, {"hn_whoishiring"})

    def test_hn_gets_three_passes_and_everything_else_one(self):
        self.assertEqual(extract.passes_for("hn_whoishiring", self.policy), 3)
        for platform in ("greenhouse", "ashby", "google_jobs", "builtin",
                         "weworkremotely", "lever"):
            self.assertEqual(extract.passes_for(platform, self.policy), 1,
                             platform)

    def test_unmeasured_platform_gets_one_pass(self):
        # An unmeasured source is not a bad source. Tripling it would be
        # paying for a number nobody has -- and this is also what protects
        # the bill when a platform string is renamed.
        self.assertEqual(extract.passes_for("a_new_board", self.policy), 1)
        self.assertEqual(extract.passes_for(None, self.policy), 1)
        # "builtin", not "builtin-nyc" -- several task files write the latter.
        self.assertIn("builtin", self.policy["measured_agreement"])

    def test_missing_config_falls_back_to_one_pass_everywhere(self):
        with tempfile.TemporaryDirectory() as d:
            policy = extract.load_policy(os.path.join(d, "absent.json"))
        self.assertEqual(extract.passes_for("hn_whoishiring", policy), 1)

    def test_threshold_is_not_sitting_on_a_measured_value(self):
        # Documented in the config's _threshold_note: 0.90 has clear air
        # under it (0.778) and above it (0.911), so the decision does not
        # turn on a rounding difference.
        threshold = self.policy["agreement_threshold"]
        for platform, agreement in self.policy["measured_agreement"].items():
            self.assertNotAlmostEqual(agreement, threshold, places=3,
                                      msg=platform)


class CallCountTests(unittest.TestCase):
    """Decision A1's actual claim: how many calls each platform costs."""

    def _count_calls(self, platform):
        calls = []

        def fake_call(prompt):
            calls.append(prompt)
            return response()

        outcome, facts, passes, unanimity = extract.extract_facts(
            job(platform), call=fake_call)
        return calls, outcome, facts, passes, unanimity

    def test_hn_whoishiring_makes_three_calls_and_votes(self):
        calls, outcome, facts, passes, unanimity = self._count_calls(
            "hn_whoishiring")
        self.assertEqual(len(calls), 3)
        self.assertEqual(outcome, extract.EXTRACTED)
        self.assertEqual(passes, 3)
        # Three identical answers: unanimous on every voted field.
        self.assertEqual(unanimity, 1.0)
        # Same prompt every pass -- the cache prefix argument in the module
        # docstring depends on the instruction block being byte-identical.
        self.assertEqual(len(set(calls)), 1)

    def test_every_other_platform_makes_exactly_one_call(self):
        for platform in ("greenhouse", "ashby", "google_jobs", "builtin",
                         "weworkremotely", "lever", "some_future_source"):
            calls, outcome, facts, passes, unanimity = self._count_calls(platform)
            self.assertEqual(len(calls), 1, platform)
            self.assertEqual(passes, 1, platform)
            # NULL, not 1.0: one pass has no agreement to report.
            self.assertIsNone(unanimity, platform)

    def test_three_passes_actually_disagreeing_produce_the_majority(self):
        answers = iter([response(seniority_level="junior"),
                        response(seniority_level="mid"),
                        response(seniority_level="junior")])
        outcome, facts, passes, unanimity = extract.extract_facts(
            job("hn_whoishiring"), call=lambda p: next(answers))
        self.assertEqual(facts["seniority_level"], "junior")
        self.assertEqual(passes, 3)
        self.assertLess(unanimity, 1.0)

    def test_a_transient_pass_does_not_discard_the_usable_ones(self):
        answers = [response(), llm.TransientError("429"), llm.TransientError("429")]

        def flaky(prompt):
            item = answers.pop(0)
            if isinstance(item, Exception):
                raise item
            return item

        outcome, facts, passes, unanimity = extract.extract_facts(
            job("hn_whoishiring"), call=flaky)
        self.assertEqual(outcome, extract.EXTRACTED)
        # Records what the row GOT, not what the policy asked for.
        self.assertEqual(passes, 1)
        self.assertIsNone(unanimity)

    def test_all_passes_transient_defers_and_writes_nothing(self):
        def always_429(prompt):
            raise llm.TransientError("429")

        outcome, facts, passes, unanimity = extract.extract_facts(
            job("hn_whoishiring"), call=always_429)
        self.assertEqual(outcome, extract.DEFERRED)
        self.assertIsNone(facts)

    def test_all_passes_unusable_is_a_tombstone_not_a_defer(self):
        # Every pass answered; none of the answers were usable. That is
        # evidence about the posting, so it earns a tombstone -- the
        # distinction score.py's three-way split exists to preserve.
        outcome, facts, passes, unanimity = extract.extract_facts(
            job("hn_whoishiring"), call=lambda p: "not json at all")
        self.assertEqual(outcome, extract.REJECTED)
        self.assertIsNone(facts)


#: The one taboola posting whose greenhouse `content` is a pasted ChatGPT web
#: UI, and an ordinary posting from the same board on the same day. Real bytes:
#: python3 evals/record_cassettes.py ats-greenhouse-domsoup
DOMSOUP_CASSETTE = "ats-greenhouse-domsoup"
DOMSOUP_POISONED = ("https://boards-api.greenhouse.io/v1/boards/taboola/jobs/"
                    "8035268?content=true")
DOMSOUP_CLEAN = ("https://boards-api.greenhouse.io/v1/boards/taboola/jobs/"
                 "8087797?content=true")


@unittest.skipUnless(
    cassettes.available(DOMSOUP_CASSETTE),
    f"cassette {DOMSOUP_CASSETTE} not recorded; "
    f"python3 evals/record_cassettes.py {DOMSOUP_CASSETTE}")
class InputSanityCassetteTests(unittest.TestCase):
    """The stripper AND the gate, driven from the bytes greenhouse served.

    WHY A CASSETTE AND NOT A STRING IN THIS FILE. The contaminating token is
    `[&:has([data-writing-block])>*]:pointer-events-auto`, and what makes it
    dangerous is a detail nobody writing a fixture from a description would
    include: the ">" inside the class attribute ended lib/text.strip_html()'s
    old `<[^>]+>` early, so the remainder of the tag was emitted as prose. A
    hand-written "some markup" fixture tests the sentence "some markup", which
    is the trap HANDOFF.md:571-574 names -- all three failure modes task 18
    found live were invisible to its four constructed fixtures.

    It also runs the REAL ingest function (ats.greenhouse_description) rather
    than a copy, so the chain under test is the production one: greenhouse
    bytes -> the double unescape -> strip_html -> description_text -> the gate.

    WHAT CHANGED WHEN lib/text._TAG LANDED
        This class used to assert that the markup SURVIVED into
        description_text, and said in its own docstring that failing was the
        correct signal once the stripper was fixed. It was, and it did. The
        assertion is now its own inverse -- the same recorded bytes must come
        out as prose -- which turns a test that pinned the defect into one
        that pins the fix, against the same real bytes.

    TWO PROPERTIES, NOW INDEPENDENT. READ THIS BEFORE DELETING ANYTHING.
        Fixing the stripper did NOT make task 35's gate dead code, and the
        two facts must not be collapsed:

          1. THIS class: strip_html no longer PRODUCES this class of input
             from these bytes.
          2. InputSanityGateTests below: the gate still REJECTS this class of
             input if anything else ever produces it -- and things still can.
             `_TAG` handles double-quoted attribute values and deliberately
             not single-quoted ones (lib/text.py:139-155, measured), and no
             tag-stripper of any kind can remove markup that arrives with no
             tags in it at all.

        A reader who finds the gate with no reachable trigger through THIS
        path and concludes it is unreachable has read half the file.
        extract.is_unusable_input() (extract.py:517) is the last line of
        defence for any future ingest path that captures the wrong bytes, and
        the `unusable` counter on the run summary is the alarm that one has.
    """

    @classmethod
    def setUpClass(cls):
        cls.ats = ingest_modules.load("ats")
        from lib import http
        with cassettes.replay(DOMSOUP_CASSETTE):
            cls.poisoned = http.get_json(DOMSOUP_POISONED)
            cls.clean = http.get_json(DOMSOUP_CLEAN)

    def _job(self, body, platform="greenhouse"):
        return {"id": str(body["id"]), "title": body.get("title"),
                "company_name": "Taboola", "location_raw": "New York",
                "platform": platform,
                "description_text": self.ats.greenhouse_description(
                    body.get("content"))}

    def test_a_gt_inside_an_attribute_value_no_longer_leaks(self):
        """THE REGRESSION TEST for lib/text._TAG, on the bytes that caused it.

        Every token asserted absent here was present in the stored
        description_text of ff9f9d9f9643e185af0f48ca until the stripper was
        fixed, and every one of them is a fragment of a tag that a `<[^>]+>`
        pattern stopped short of: the class attribute holding
        `[&:has([data-writing-block])>*]` ends at its own ">", so `data-testid`
        and everything after it was prose as far as the stripper was concerned.
        """
        description = self._job(self.poisoned)["description_text"]
        for leaked in ("data-testid=", "pointer-events-auto", "data-turn-id=",
                       "var(--", "--thread-response-height"):
            self.assertNotIn(leaked, description,
                             f"{leaked!r} still leaks out of strip_html")
        # Not merely absent -- the prose it was displacing is present, and
        # first, which is what distinguishes a fix from an over-eager stripper
        # that ate the posting along with the soup.
        self.assertTrue(description.startswith("Realize your potential"),
                        description[:120])
        self.assertIn("Product Analytics team", description)

    def test_the_poisoned_posting_now_extracts_like_any_other(self):
        """It was REJECTED without a call; it is a real Taboola posting.

        The gate was always a mitigation. This is the measurement that says
        the underlying input is repaired rather than merely tolerated: the
        same cassette bytes now reach the model exactly once.
        """
        calls = []
        outcome, facts, passes, unanimity = extract.extract_facts(
            self._job(self.poisoned),
            call=lambda prompt: calls.append(prompt) or response())
        self.assertEqual(outcome, extract.EXTRACTED)
        self.assertEqual(len(calls), 1)
        self.assertEqual(extract.markup_ratio(calls[0]), 0.0)

    def test_an_ordinary_posting_from_the_same_board_is_untouched(self):
        """The control, and it is a real posting rather than a synthetic one.

        A gate measured only against the inputs it was built to reject cannot
        report a false-positive rate. This is one real greenhouse posting,
        fetched from the same board on the same day as the poisoned one, going
        all the way through to an extraction.

        It is also the byte-identity check on the stripper change: this
        posting's `content` carries no ">" inside any attribute value, so a
        change that altered it would be a change to 13,060 other rows too.
        """
        calls = []
        outcome, facts, passes, unanimity = extract.extract_facts(
            self._job(self.clean),
            call=lambda prompt: calls.append(prompt) or response())
        self.assertEqual(outcome, extract.EXTRACTED)
        self.assertEqual(len(calls), 1)
        self.assertEqual(extract.markup_ratio(calls[0]), 0.0)
        # And the posting itself reached the model, not just the instructions.
        self.assertIn("Taboola", calls[0])

    def test_neither_cassette_posting_carries_markup_any_more(self):
        """Both ratios in one assertion -- the numeric form of the test above.

        The CLIFF this used to assert between these two postings has moved to
        InputSanityGateTests, because there is no longer a gap through THIS
        path and that is the fix working, not the gate weakening. What the
        gate's threshold was measured against (extract.py:436-449) was a
        population the old stripper produced; the gate itself still needs a
        cliff under test, on input that is still poisoned today.
        """
        poisoned = extract.markup_ratio(
            extract.prompt_description(self._job(self.poisoned)))
        clean = extract.markup_ratio(
            extract.prompt_description(self._job(self.clean)))
        self.assertEqual((poisoned, clean), (0.0, 0.0))


#: The tag pattern lib/text.strip_html() used before lib/text._TAG landed.
#:
#: A COPY, DELIBERATELY, and the one place in this repo where that is right.
#: evals/cassettes.py's rule is ADAPTERS, NEVER COPIES, and it applies to code
#: that still exists -- an adapter cannot be pointed at behaviour that has been
#: deleted. What this reconstructs is not a current code path but the bytes
#: 14,003 described rows were written by, which is a fact about the DATABASE
#: and stays true until migrations/migrate_description_rehash.py is applied.
_PRE_FIX_TAG = re.compile(r"<[^>]+>")

#: Markup residue carrying no tags at all: rendered CSS pasted into a
#: description field as prose. Tokens lifted from e93ddca38b45bb929e6e46cd and
#: ff9f9d9f9643e185af0f48ca, the live rows, not invented.
#:
#: THE POINT OF ITS EXISTENCE: no tag-stripper of any design can remove this,
#: because there is no tag. It is the permanent floor under task 35's gate --
#: the class of input that stays reachable no matter what lib/text.py does.
TAGLESS_CSS_RESIDUE = (
    "About the role Perks and benefits --tw-ring-color: "
    "var(--color-blue-500); [&>*]:mt-2 !important"
)


@unittest.skipUnless(
    cassettes.available(DOMSOUP_CASSETTE),
    f"cassette {DOMSOUP_CASSETTE} not recorded; "
    f"python3 evals/record_cassettes.py {DOMSOUP_CASSETTE}")
class InputSanityGateTests(unittest.TestCase):
    """Task 35's gate, on input that is STILL POISONED after the stripper fix.

    WHY THIS CLASS EXISTS AND MUST NOT BE FOLDED BACK INTO THE ONE ABOVE
        Fixing lib/text.strip_html() cleaned the fixture the gate was tested
        against. It did not make the gate unnecessary: the gate guards a CLASS
        of input, not one cassette, and extract.is_unusable_input()
        (extract.py:517) is the last line of defence for any future ingest
        path that captures the wrong bytes. Retiring these assertions because
        one upstream producer stopped producing would retire a live alarm --
        the `unusable` counter on the run summary -- as a side effect of
        fixing something upstream of it.

    THE INPUTS ARE SYNTHETIC HERE, AND THAT IS THE CORRECT CHOICE
        The class above states the rule: a fixture written from a
        specification tests the specification. It applies to the STRIPPER,
        whose subject is what real employers really emit. The subject HERE is
        the gate, and the gate's contract is over the shape of its input, so
        constructing that shape is testing the thing itself.

        Neither input is invented from a description even so. Both are
        derived from bytes that were really served:

          1. THE SAME CASSETTE, RE-QUOTED. `_TAG` treats double-quoted
             attribute values as opaque and single-quoted ones deliberately
             not -- measured over 21,350 live markup strings, single-quote
             handling changed nothing and risks apostrophes in unquoted
             values (lib/text.py:139-155). So the identical recorded posting,
             with `&quot;` swapped for `&#39;` as any hand-written or
             non-Greenhouse source might emit it, still leaks. It reproduces
             the pre-fix length exactly, which is the assertion that says
             `_TAG` fell back to `<[^>]+>` here rather than doing something
             new.
          2. TAGLESS_CSS_RESIDUE above, for the case no stripper can ever
             reach.

    AND THE ROWS ALREADY IN THE TABLE. The last test covers the third
    population: description_text is in HASH_FIELDS_ATS and HASH_FIELDS_SHORT
    (schema.py:131-135), so lib/upsert.py takes the touch branch and never
    rewrites a row whose content hash still matches upstream. Until the
    migration is applied, the poisoned bytes are what extract.py reads.
    """

    @classmethod
    def setUpClass(cls):
        cls.ats = ingest_modules.load("ats")
        from lib import http
        with cassettes.replay(DOMSOUP_CASSETTE):
            cls.poisoned = http.get_json(DOMSOUP_POISONED)
            cls.clean = http.get_json(DOMSOUP_CLEAN)

    def _job(self, description):
        return {"id": "8035268", "title": "Product Analyst",
                "company_name": "Taboola", "location_raw": "New York",
                "platform": "greenhouse", "description_text": description}

    def _single_quoted(self, body):
        """The recorded posting as a source emitting single-quoted attributes.

        Greenhouse serves `content` escaped once, so an attribute quote is
        `&quot;` in the raw bytes. Swapping it for `&#39;` before the REAL
        ingest function runs means the whole production chain is exercised --
        the double unescape, strip_html, the cap -- on real markup that lands
        in `_TAG`'s documented blind spot.
        """
        content = (body.get("content") or "").replace("&quot;", "&#39;")
        return self.ats.greenhouse_description(content)

    def test_the_inputs_are_still_poisoned_after_the_stripper_fix(self):
        """Guard on the guards. If either stops leaking, these tests are
        asserting nothing and the fixture must be re-sourced, not deleted."""
        requoted = self._single_quoted(self.poisoned)
        self.assertIn("data-testid=", requoted)
        self.assertIn("pointer-events-auto", requoted)
        # `_TAG` fell back to the historical pattern for these tags rather
        # than inventing a third behaviour: same bytes out, to the character.
        self.assertEqual(len(requoted), 4838)
        # And the tagless case survives strip_html untouched, by construction.
        self.assertEqual(text_module.strip_html(TAGLESS_CSS_RESIDUE),
                         TAGLESS_CSS_RESIDUE)

    def test_a_pasted_browser_dom_is_rejected_without_an_llm_call(self):
        calls = []
        outcome, facts, passes, unanimity = extract.extract_facts(
            self._job(self._single_quoted(self.poisoned)),
            call=lambda prompt: calls.append(prompt) or response())
        self.assertEqual(outcome, extract.REJECTED)
        self.assertIsNone(facts)
        self.assertEqual(passes, 0)
        # THE POINT. score.py's REJECTED normally means "the model answered
        # and the answer was unusable"; here the model is never reached.
        self.assertEqual(calls, [])

    def test_markup_with_no_tags_at_all_is_rejected_too(self):
        """The case a stripper fix can never address, so the gate always must."""
        calls = []
        outcome, facts, passes, unanimity = extract.extract_facts(
            self._job(TAGLESS_CSS_RESIDUE),
            call=lambda prompt: calls.append(prompt) or response())
        self.assertEqual(outcome, extract.REJECTED)
        self.assertEqual(passes, 0)
        self.assertEqual(calls, [])

    def test_the_gate_is_a_cliff_not_a_slope_between_these_two(self):
        """Both ratios, printed as one assertion, so the margin is visible.

        The threshold's justification is the GAP it sits in, not the value
        itself. If a re-recording narrows that gap the number to change is
        extract.MARKUP_REJECT_RATIO, and this is where you find out.

        THE MARGIN IS NARROWER THAN IT WAS AND THE REASON IS NOT THE FIX.
        The stored row scored 0.1290; this re-quoted form of the same bytes
        scores 0.0613 -- still 6x the threshold, but half of what the same
        leak used to score. `_MARKUP_RESIDUE`'s attribute alternative
        (extract.py:425) is `[A-Za-z][A-Za-z0-9_-]*="`, which requires a
        DOUBLE quote, so `data-testid='x'` is leaked markup the predicate does
        not count. That is a real blind spot in the gate, recorded here
        because this is the test that surfaced it.
        """
        poisoned = extract.markup_ratio(
            extract.prompt_description(self._job(self._single_quoted(self.poisoned))))
        clean = extract.markup_ratio(
            extract.prompt_description(self._job(self._single_quoted(self.clean))))
        self.assertEqual(clean, 0.0)
        self.assertGreater(poisoned, extract.MARKUP_REJECT_RATIO * 5,
                           f"poisoned={poisoned}, clean={clean}")

    def test_the_rows_already_written_by_the_old_stripper_are_still_rejected(self):
        """The third population: what is in the table right now.

        Reconstructed from the same cassette through _PRE_FIX_TAG, because
        until migrate_description_rehash.py is applied these bytes -- not the
        clean ones -- are what extract.py will read for those six rows.
        """
        markup = html.unescape(html.unescape(self.poisoned.get("content") or ""))
        stripped = re.sub(r"\s+", " ", _PRE_FIX_TAG.sub(" ", markup)).strip()
        stored = stripped[:text_module.MAX_DESCRIPTION_CHARS]
        self.assertIn("data-testid=", stored)  # the reconstruction still leaks

        calls = []
        outcome, facts, passes, unanimity = extract.extract_facts(
            self._job(stored),
            call=lambda prompt: calls.append(prompt) or response())
        self.assertEqual(outcome, extract.REJECTED)
        self.assertEqual(passes, 0)
        self.assertEqual(calls, [])


class MarkupRatioTests(unittest.TestCase):
    """The predicate itself: what it counts, and what it deliberately does not.

    Every string here is either lifted verbatim from a row in the live table
    (the job_id is named) or is the shape a measured false positive took. None
    of them is invented -- see the cassette class above for why that matters.
    """

    def test_an_ordinary_posting_scores_zero(self):
        self.assertEqual(extract.markup_ratio(
            "We are hiring a senior backend engineer. You will own our "
            "Python services and work with Postgres and Kafka."), 0.0)

    def test_html_attribute_soup_is_counted(self):
        # ff9f9d9f9643e185af0f48ca, the reported row, at its first leak.
        ratio = extract.markup_ratio(
            '*]:pointer-events-auto R6Vx5W_threadScrollVars '
            'data-testid="conversation-turn-136" data-turn="assistant">')
        self.assertGreater(ratio, 0.5)

    def test_tailwind_class_residue_with_no_data_attribute_is_counted(self):
        # e93ddca38b45bb929e6e46cd (Databricks). A marker blocklist built from
        # `data-testid=` / `pointer-events-auto` -- the query HANDOFF.md:410
        # used -- scores this at zero and lets it through.
        self.assertGreater(extract.markup_ratio('p]:pt-0 [&>p]:mb-2 [&>p]:my-0">'),
                           0.5)

    def test_bracketed_prose_is_not_markup(self):
        """`[ONSITE]:` is Who's Hiring convention, not a Tailwind variant.

        415fcb871b101301330b9a67 is a real hn_whoishiring posting written this
        way, and it was a false positive until `\\]:` was tightened to
        `\\]:[a-z]`. It is the only false positive the sweep has ever produced,
        so it is the one worth a test.
        """
        self.assertEqual(extract.markup_ratio(
            "HPC Hardware & Infra Sysadmin [ONSITE]: We are looking for a "
            "system administrator to help run Sherlock."), 0.0)

    def test_an_empty_or_missing_description_is_not_markup(self):
        # Not the gate's problem: _eligible_sql already excludes empty
        # descriptions, and answering 1.0 here would make "" look poisoned.
        self.assertEqual(extract.markup_ratio(""), 0.0)
        self.assertEqual(extract.markup_ratio(None), 0.0)
        self.assertFalse(extract.is_unusable_input({}))
        self.assertFalse(extract.is_unusable_input({"description_text": None}))

    def test_the_gate_judges_the_prompt_window_not_the_stored_text(self):
        """Markup past MAX_DESCRIPTION_CHARS reaches no model, so it is not
        grounds for a tombstone. build_prompt and the gate read the same slice
        through prompt_description() so the two cannot drift."""
        clean = "We are hiring an engineer. " * 200
        self.assertGreater(len(clean), extract.MAX_DESCRIPTION_CHARS)
        soup = ' data-testid="x" [&>p]:mb-2 var(--y) ' * 40
        self.assertTrue(extract.is_unusable_input({"description_text": soup + clean}))
        self.assertFalse(extract.is_unusable_input({"description_text": clean + soup}))

    def test_a_light_nick_of_markup_does_not_tombstone_a_real_posting(self):
        """cc7d1b61574ffdac2d112a8d: eleven characters of stray Tailwind in an
        otherwise complete Fireblocks job description, ratio 0.0040. Rejecting
        a readable posting is the failure mode that matters more than missing
        this one, so the threshold is set above it deliberately."""
        prose = "What you'll own: the mobile product end-to-end. " * 60
        posting = f"You define what gets built and why. _*]:min-w-0 {prose}"
        ratio = extract.markup_ratio(posting)
        self.assertGreater(ratio, 0.0)
        self.assertLess(ratio, extract.MARKUP_REJECT_RATIO)
        self.assertFalse(extract.is_unusable_input({"description_text": posting}))

    def test_the_threshold_sits_in_the_measured_gap(self):
        """0.01 is sqrt(0.0040 * 0.0247), the geometric midpoint between the
        worst clean row and the mildest poisoned one in the 2026-07-28 sweep.
        A future edit that moves it out of that interval is moving it onto one
        of the two populations rather than between them."""
        self.assertGreater(extract.MARKUP_REJECT_RATIO, 0.0040)
        self.assertLess(extract.MARKUP_REJECT_RATIO, 0.0247)


class InputRejectionTombstoneTests(unittest.TestCase):
    """A gate that fires invisibly is the failure mode it was added to end."""

    def test_the_tombstone_says_it_was_the_input(self):
        label = f"{extract.INPUT_REJECT_LABEL}/deepseek-v4-flash@example.com"
        # Still a FAILED: tombstone: match.py:285 excludes these with
        # NOT LIKE 'FAILED:%' and evals/corpus.py:171 buckets them the same
        # way, so the reason rides along without moving either predicate.
        self.assertTrue(llm.failed_label(label).startswith(llm.FAILED_PREFIX))
        self.assertIn(extract.INPUT_REJECT_LABEL, llm.failed_label(label))

    def test_a_model_failure_is_not_labelled_as_an_input_failure(self):
        # The distinction is the whole value of the label: both outcomes are
        # REJECTED, but only one of them is evidence about the model.
        self.assertNotIn(extract.INPUT_REJECT_LABEL,
                         llm.failed_label("deepseek-v4-flash@example.com"))

    def test_rejection_counts_as_progress_for_the_drain_loop(self):
        """A batch of nothing but poisoned rows must not read as a down endpoint.

        drain_loop breaks on `EXTRACTED + REJECTED == 0`, so an input rejection
        has to land in REJECTED and not in DEFERRED. Getting that backwards
        would stop the night's drain on the first contaminated batch and leave
        every posting behind it unextracted -- and it would report itself as
        "no-progress", i.e. as a rate-limited endpoint, which is the wrong
        thing to go and investigate.
        """
        soup = {"id": "j1", "platform": "greenhouse", "title": "Analyst",
                "description_text": '*]:pointer-events-auto data-testid="x">'}
        batches = [[soup, soup], []]

        def run_batch(jobs):
            return Counter(extract.extract_facts(j)[0] for j in jobs)

        totals, ran, stopped = extract.drain_loop(
            lambda: batches.pop(0), run_batch, deadline_secs=60)
        self.assertEqual(totals[extract.REJECTED], 2)
        self.assertEqual(totals[extract.DEFERRED], 0)
        # DRAINED, not NO_PROGRESS: the batch learned something.
        self.assertEqual(stopped, extract.DRAINED)


#: The fourteen values docs/role-track-derivation.md added to the original
#: twelve. Listed here rather than sliced out of extract.ARCHETYPE so the test
#: fails if somebody removes one, which slicing would not catch.
NEW_ARCHETYPES = (
    "ai_operations", "implementation_analyst", "support_ops", "marketing_ops",
    "admin_ops", "hardware_embedded", "infrastructure_compute",
    "engineering_management", "qa_test", "program_management", "mobile",
    "business_systems", "it_internal", "developer_relations",
)


class VocabularyTests(unittest.TestCase):
    """The closed vocabularies, and the coercion that keeps them closed.

    match.py compares these strings exactly, so a value the model can say but
    _enum() cannot recognise scores as unknown for every profile forever --
    silently. That is the failure these tests exist for, and it is invisible
    in production.
    """

    def test_every_vocabulary_value_survives_a_round_trip(self):
        for vocab in (extract.ARCHETYPE, extract.ROLE_TRACK,
                      extract.SENIORITY, extract.AI_INVOLVEMENT,
                      extract.REMOTE_POLICY):
            for value in vocab:
                self.assertEqual(extract._enum(value, vocab), value)

    def test_the_fourteen_derived_archetypes_are_present(self):
        for value in NEW_ARCHETYPES:
            self.assertIn(value, extract.ARCHETYPE, value)
        self.assertEqual(len(extract.ARCHETYPE), 26)
        self.assertEqual(len(set(extract.ARCHETYPE)), 26)

    def test_the_two_dropped_candidates_are_absent(self):
        # Proposed by the task file, dropped on evidence: between them they
        # reclaim ONE row of 427 (automation_specialist has 5 cohort postings
        # and 1 `other` row; 8 of data_coordination's 9 hits are a single
        # employer's "Data Annotation Specialist"). See
        # docs/role-track-derivation.md, "Dropped". Adding them back needs new
        # evidence, not a re-reading of the task file.
        self.assertNotIn("automation_specialist", extract.ARCHETYPE)
        self.assertNotIn("data_coordination", extract.ARCHETYPE)

    def test_business_systems_is_deliberately_in_both_vocabularies(self):
        # Not a copy-paste slip: the archetype is the role, the track is the
        # browsable family it sits in. Pinned so it is not "tidied up".
        self.assertIn("business_systems", extract.ARCHETYPE)
        self.assertIn("business_systems", extract.ROLE_TRACK)

    def test_archetype_near_misses_coerce(self):
        for raw, expected in (
                ("AI Operations", "ai_operations"),
                ("QA/Test", "qa_test"),
                ("Support-Ops", "support_ops"),
                ("IT Internal", "it_internal"),
                ("ENGINEERING_MANAGEMENT", "engineering_management"),
                ("Hardware/Embedded", "hardware_embedded"),
                ("mobile engineer", "mobile"),            # prefix rule
                ("business_systems_analyst", "business_systems"),
        ):
            self.assertEqual(extract._enum(raw, extract.ARCHETYPE), expected,
                             raw)

    def test_role_track_near_misses_coerce(self):
        for raw, expected in (
                ("Software Engineering", "software_engineering"),
                ("revenue-operations", "revenue_operations"),
                ("SOLUTIONS_AND_IMPLEMENTATION", "solutions_and_implementation"),
                ("business operations coordinator", "business_operations"),
        ):
            self.assertEqual(extract._enum(raw, extract.ROLE_TRACK), expected,
                             raw)

    def test_a_slash_is_a_separator_like_a_dash(self):
        # The module docstring has always named "Senior/Mid" as a shape that
        # must not silently score as unknown; until now the slash survived
        # both replaces and matched nothing. A compound answer resolves to the
        # value named FIRST -- the same first-wins arbitration the prefix rule
        # already applies to "mid_level".
        self.assertEqual(extract._enum("Senior/Mid", extract.SENIORITY),
                         "senior")
        self.assertEqual(extract._enum("Mid/Senior", extract.SENIORITY), "mid")

    def test_an_unrecognised_answer_is_none_not_a_guess(self):
        self.assertIsNone(extract._enum("astronaut", extract.ARCHETYPE))
        self.assertIsNone(extract._enum("veterinary", extract.ROLE_TRACK))
        self.assertIsNone(extract._enum(None, extract.ARCHETYPE))
        self.assertIsNone(extract._enum(7, extract.ARCHETYPE))

    def test_the_prompt_offers_every_value_it_will_accept(self):
        # A value in the tuple but not in _INSTRUCTIONS is a value the model
        # is never told about; one in the prompt but not the tuple coerces to
        # NULL on the way back in. Both fail silently, so both are pinned.
        for value in extract.ARCHETYPE + extract.ROLE_TRACK:
            self.assertIn(value, extract._INSTRUCTIONS, value)
        # The prompt must PERMIT null rather than force a track: coverage is
        # 83.2% and the cluster tail is explicitly untrusted, so a model with
        # no good answer has to be allowed to say so.
        guidance = [line for line in extract._INSTRUCTIONS.splitlines()
                    if line.startswith("  role_track ")]
        self.assertEqual(len(guidance), 1)
        self.assertIn("null", guidance[0])

    def test_the_confusable_values_are_told_apart_in_the_prompt(self):
        # The list of values is generated from the tuples, so it cannot fall
        # out of date -- but the GUIDANCE is hand-written, and a vocabulary
        # that doubled in size without explaining its overlapping values just
        # moves the ambiguity from `other` into a wrong confident answer.
        # These four pairs are the ones docs/role-track-derivation.md flags.
        archetype = [line for line in extract._INSTRUCTIONS.splitlines()
                     if line.startswith("  role_archetype ")][0]
        for value in ("support_ops", "it_internal", "engineering_management",
                      "pm", "infrastructure_compute", "devops",
                      "ai_operations", "other"):
            self.assertIn(f'"{value}"', archetype, value)


class MissingnessTests(unittest.TestCase):
    """normalize() must not launder "could not tell" into a real value.

    Every enum here used to carry a default, so an unanswered field was
    stored as "other" / "none" / "unknown" / false and match.py scored it
    identically to a confident answer -- which rewards the postings
    extraction did WORST on. These assert `is None`, never falsiness:
    assertFalse(None) passes and would hide exactly the bug.
    """

    def test_absent_enums_are_none(self):
        facts = extract.normalize(payload(remote_policy=None))
        self.assertIsNone(facts["remote_policy"])
        self.assertIsNone(facts["ai_involvement"])   # key never sent at all
        self.assertIsNone(facts["role_track"])

    def test_unrecognised_enums_are_none_not_a_default(self):
        facts = extract.normalize(payload(
            role_archetype="quantum_alchemist", ai_involvement="a lot",
            remote_policy="wherever", role_track="misc"))
        self.assertIsNone(facts["role_archetype"])
        self.assertIsNone(facts["ai_involvement"])
        self.assertIsNone(facts["remote_policy"])
        self.assertIsNone(facts["role_track"])

    def test_booleans_are_tri_state(self):
        for field in ("ml_research_required", "advanced_degree_required",
                      "customer_facing", "gap_friendly_language"):
            absent = extract.normalize(payload())
            self.assertIsNone(absent[field], field)
            self.assertIs(extract.normalize(payload(**{field: False}))[field],
                          False, field)
            self.assertIs(extract.normalize(payload(**{field: True}))[field],
                          True, field)

    def test_a_non_boolean_answer_is_unknown_rather_than_true(self):
        # "yes" and 1 are the model failing to follow the schema, not the
        # posting stating a requirement. Reading them as True would penalise
        # a posting for something it never said.
        for value in ("yes", "true", 1, [], {}):
            facts = extract.normalize(payload(advanced_degree_required=value))
            self.assertIsNone(facts["advanced_degree_required"], repr(value))

    def test_employment_type_and_visa_keep_their_unknown(self):
        # Left alone deliberately: "unknown" is a real VALUE in both
        # vocabularies -- a posting genuinely says nothing about sponsorship
        # -- and nothing in match.py scores either field.
        facts = extract.normalize(payload())
        self.assertEqual(facts["employment_type"], "unknown")
        self.assertEqual(facts["visa_sponsorship"], "unknown")

    def test_a_null_required_field_still_passes_the_shape_gate(self):
        # llm.has_fields tests key PRESENCE, and that is still right now that
        # null is meaningful: requiring non-null would TOMBSTONE a posting
        # whose archetype the model honestly could not determine, permanently
        # discarding a row for giving the newly-correct answer.
        facts = extract.normalize(payload(role_archetype=None))
        self.assertIsNotNone(facts)
        self.assertIsNone(facts["role_archetype"])

    def test_a_missing_required_key_is_still_unusable(self):
        self.assertIsNone(extract.normalize(payload(summary=_OMIT)))


class TombstoneGuardTests(unittest.TestCase):
    """The guard at extract.py's normalize(): exactly what it caught before.

    It used to read `archetype == "other"`, using "other" as a proxy for "the
    model said nothing useful" -- correct only because "other" was also the
    default for an unrecognised answer. Now that the default is None, a naive
    read of that line stops firing and junk gets STORED instead of tombstoned,
    with nothing in production to notice.
    """

    def test_the_new_predicate_is_the_old_one(self):
        # The algebra, asserted rather than argued: _enum(x, ARCHETYPE,
        # "other") == "other" iff _enum(x, ARCHETYPE) is "other" or None, for
        # every shape of answer. That is what makes the rewrite equivalent.
        for raw in ("other", "Other", "OTHER", "backend", "ai_operations",
                    "astronaut", "", "   ", None, 7, [], {"a": 1}, True,
                    "other_thing", "otherwise"):
            old = extract._enum(raw, extract.ARCHETYPE, "other") == "other"
            new = extract._enum(raw, extract.ARCHETYPE) in (None, "other")
            self.assertEqual(old, new, repr(raw))

    def test_a_genuinely_empty_response_still_tombstones(self):
        self.assertIsNone(extract.normalize(payload(
            seniority_level=None, role_archetype=None, remote_policy=None,
            tech_stack=[], summary="")))

    def test_an_unrecognised_answer_to_everything_still_tombstones(self):
        # The case the old code caught via the "other" default. It must keep
        # tombstoning now that the default is gone.
        self.assertIsNone(extract.normalize(payload(
            seniority_level="whatever", role_archetype="astronaut",
            remote_policy="wherever", tech_stack="not a list", summary=42)))

    def test_an_explicit_other_is_an_answer_and_is_not_tombstoned(self):
        # "None of these archetypes fit" is a real, meaningful reply. It is
        # stored as "other" -- distinguishable from the NULL an unrecognised
        # answer now produces, which it was not before.
        facts = extract.normalize(payload(role_archetype="other"))
        self.assertIsNotNone(facts)
        self.assertEqual(facts["role_archetype"], "other")

    def test_an_explicit_other_and_nothing_else_still_tombstones(self):
        # Equivalence in the other direction: the guard needs all four
        # signals empty, and "other" alone was never enough to save a row.
        self.assertIsNone(extract.normalize(payload(
            seniority_level=None, role_archetype="other", remote_policy=None,
            tech_stack=[], summary="")))

    def test_any_one_usable_signal_saves_the_row(self):
        empty = {"seniority_level": None, "role_archetype": None,
                 "remote_policy": None, "tech_stack": [], "summary": ""}
        for saved in ({"seniority_level": "senior"},
                      {"role_archetype": "support_ops"},
                      {"tech_stack": ["python"]},
                      {"summary": "A role."}):
            self.assertIsNotNone(extract.normalize({**empty, **saved}), saved)

    def test_a_newly_recognised_archetype_is_no_longer_tombstone_bait(self):
        # Not a change to the guard but a consequence of the vocabulary: a
        # response naming ONLY "support_ops" used to coerce to "other" and,
        # with nothing else usable, was thrown away. It is now an answer.
        facts = extract.normalize({
            "seniority_level": None, "role_archetype": "support_ops",
            "remote_policy": None, "tech_stack": [], "summary": ""})
        self.assertEqual(facts["role_archetype"], "support_ops")


class VoteTests(unittest.TestCase):
    """vote_facts is pure: no database, no clock, no endpoint."""

    def test_every_stored_column_has_a_voting_rule(self):
        covered = (extract.VOTE_ENUM_FIELDS + extract.VOTE_BOOL_FIELDS
                   + extract.VOTE_INT_FIELDS + extract.VOTE_CARRIED_FIELDS)
        self.assertEqual(sorted(covered), sorted(extract._FACT_COLUMNS))
        self.assertEqual(len(covered), len(set(covered)))

    def test_single_pass_is_returned_unchanged_with_no_unanimity(self):
        facts, unanimity = extract.vote_facts([result()])
        self.assertEqual(facts, BASE)
        self.assertIsNone(unanimity)

    def test_single_pass_result_is_a_copy(self):
        original = result()
        facts, _ = extract.vote_facts([original])
        facts["seniority_level"] = "staff"
        self.assertEqual(original["seniority_level"], "junior")

    def test_enum_majority(self):
        facts, _ = extract.vote_facts([
            result(seniority_level="mid"),
            result(seniority_level="junior"),
            result(seniority_level="junior"),
        ])
        self.assertEqual(facts["seniority_level"], "junior")

    def test_enum_three_way_tie_falls_back_to_the_first_pass(self):
        # Pinned deliberately: with three different answers the vote has no
        # information, and the first pass's value is exactly what this script
        # stored before voting existed. The fallback is never worse than the
        # behaviour it replaces.
        facts, unanimity = extract.vote_facts([
            result(ai_involvement="none"),
            result(ai_involvement="uses_ai_tools"),
            result(ai_involvement="builds_llm_features"),
        ])
        self.assertEqual(facts["ai_involvement"], "none")
        self.assertLess(unanimity, 1.0)

    def test_enum_none_votes(self):
        # None means "the posting does not say", which is an answer.
        facts, _ = extract.vote_facts([
            result(seniority_level=None),
            result(seniority_level=None),
            result(seniority_level="senior"),
        ])
        self.assertIsNone(facts["seniority_level"])

    def test_bool_majority(self):
        facts, _ = extract.vote_facts([
            result(customer_facing=True),
            result(customer_facing=False),
            result(customer_facing=False),
        ])
        self.assertFalse(facts["customer_facing"])

    def test_bool_two_of_three_true(self):
        facts, _ = extract.vote_facts([
            result(gap_friendly_language=True),
            result(gap_friendly_language=True),
            result(gap_friendly_language=False),
        ])
        self.assertTrue(facts["gap_friendly_language"])

    def test_int_median_not_mode(self):
        # 3, 3, 4 has a mode; 3, 4, 5 does not, and a majority vote would
        # fall back to an arbitrary pass. The median is defined for both.
        facts, _ = extract.vote_facts([
            result(years_experience_min=3),
            result(years_experience_min=4),
            result(years_experience_min=5),
        ])
        self.assertEqual(facts["years_experience_min"], 4)

    def test_int_median_ignores_a_lone_none(self):
        facts, _ = extract.vote_facts([
            result(comp_min=None),
            result(comp_min=100000),
            result(comp_min=120000),
        ])
        self.assertEqual(facts["comp_min"], 100000)   # lower middle of two

    def test_int_majority_none_wins(self):
        facts, _ = extract.vote_facts([
            result(comp_max=None),
            result(comp_max=None),
            result(comp_max=200000),
        ])
        self.assertIsNone(facts["comp_max"])

    def test_int_all_none_stays_none(self):
        facts, _ = extract.vote_facts([
            result(years_experience_max=None),
            result(years_experience_max=None),
            result(years_experience_max=None),
        ])
        self.assertIsNone(facts["years_experience_max"])

    def test_int_median_never_invents_a_value(self):
        # The lower of the two middle values, not their mean: 3 and 5 must
        # not become a 4 that no pass produced and no posting contains.
        facts, _ = extract.vote_facts([
            result(years_experience_min=3),
            result(years_experience_min=5),
        ])
        self.assertIn(facts["years_experience_min"], (3, 5))
        self.assertEqual(facts["years_experience_min"], 3)

    def test_prose_is_carried_whole_from_the_pass_the_vote_endorsed(self):
        # Pass 2 and 3 agree on the enums, so the summary and tech_stack come
        # from pass 2 -- not merged, not from the outvoted pass 1.
        facts, _ = extract.vote_facts([
            result(seniority_level="staff", summary="Outvoted.",
                   tech_stack='["cobol"]'),
            result(seniority_level="junior", summary="Endorsed.",
                   tech_stack='["python"]'),
            result(seniority_level="junior", summary="Also endorsed.",
                   tech_stack='["python", "sql"]'),
        ])
        self.assertEqual(facts["seniority_level"], "junior")
        self.assertEqual(facts["summary"], "Endorsed.")
        self.assertEqual(facts["tech_stack"], '["python"]')

    def test_prose_tie_goes_to_the_earliest_matching_pass(self):
        facts, _ = extract.vote_facts([
            result(summary="First."),
            result(summary="Second."),
            result(summary="Third."),
        ])
        self.assertEqual(facts["summary"], "First.")

    def test_prose_is_never_merged(self):
        facts, _ = extract.vote_facts([
            result(tech_stack='["python"]'),
            result(tech_stack='["python", "go"]'),
            result(tech_stack='["rust"]'),
        ])
        # Whatever it picks, it is one pass's answer verbatim -- never a
        # union (which accumulates hallucinations) or an intersection (which
        # deletes what two passes named).
        self.assertIn(facts["tech_stack"],
                      ('["python"]', '["python", "go"]', '["rust"]'))

    def test_unanimity_is_the_fraction_of_voted_fields_agreeing(self):
        n_voted = (len(extract.VOTE_ENUM_FIELDS) + len(extract.VOTE_BOOL_FIELDS)
                   + len(extract.VOTE_INT_FIELDS))
        facts, unanimity = extract.vote_facts([
            result(seniority_level="mid"), result(), result()])
        self.assertAlmostEqual(unanimity, (n_voted - 1) / n_voted)

        # Prose is excluded from the count -- three different summaries of
        # the same posting are not a disagreement about the posting.
        facts, unanimity = extract.vote_facts([
            result(summary="One."), result(summary="Two."),
            result(summary="Three.")])
        self.assertEqual(unanimity, 1.0)

    def test_vote_needs_at_least_one_result(self):
        with self.assertRaises(ValueError):
            extract.vote_facts([])

    def test_role_track_votes_like_any_other_enum(self):
        facts, _ = extract.vote_facts([
            result(role_track="business_operations"),
            result(role_track="technical_support"),
            result(role_track="technical_support"),
        ])
        self.assertEqual(facts["role_track"], "technical_support")

    def test_role_track_three_way_tie_falls_back_to_the_first_pass(self):
        facts, unanimity = extract.vote_facts([
            result(role_track="data_and_analytics"),
            result(role_track="business_analysis"),
            result(role_track="revenue_operations"),
        ])
        self.assertEqual(facts["role_track"], "data_and_analytics")
        self.assertLess(unanimity, 1.0)

    def test_role_track_none_majority_wins(self):
        # None means "no listed track describes this", which is a real answer
        # on a nullable-by-design field: two passes saying it outrank one that
        # named a track.
        facts, _ = extract.vote_facts([
            result(role_track=None),
            result(role_track=None),
            result(role_track="product_and_marketing"),
        ])
        self.assertIsNone(facts["role_track"])

    def test_role_track_all_none_stays_none(self):
        facts, unanimity = extract.vote_facts(
            [result(role_track=None)] * 3)
        self.assertIsNone(facts["role_track"])
        self.assertEqual(unanimity, 1.0)   # agreeing on None is agreement

    def test_role_track_disagreement_moves_the_prose_pass(self):
        # role_track joins the agreement vector _majority_pass_index() scores,
        # so a pass outvoted on it alone no longer carries the summary. That
        # is the intended effect and not a side effect: the prose should
        # describe the reading of the posting the vote endorsed.
        facts, _ = extract.vote_facts([
            result(role_track="business_analysis", summary="Outvoted."),
            result(role_track="technical_support", summary="Endorsed."),
            result(role_track="technical_support", summary="Also endorsed."),
        ])
        self.assertEqual(facts["role_track"], "technical_support")
        self.assertEqual(facts["summary"], "Endorsed.")

    def test_a_null_role_track_never_tombstones_a_row(self):
        # End to end through extract_facts: the model omitting the field is
        # the expected case on 16.8% of postings and must cost nothing.
        outcome, facts, passes, _ = extract.extract_facts(
            job("greenhouse"), call=lambda p: response())
        self.assertEqual(outcome, extract.EXTRACTED)
        self.assertIsNone(facts["role_track"])

    def test_tri_state_booleans_vote_with_none(self):
        # normalize() no longer forces these through bool(), so None reaches
        # the vote and has to count as an answer here too.
        facts, _ = extract.vote_facts([
            result(customer_facing=None),
            result(customer_facing=None),
            result(customer_facing=True),
        ])
        self.assertIsNone(facts["customer_facing"])

    def test_vote_does_not_mutate_its_inputs(self):
        results = [result(seniority_level="mid"), result(), result()]
        snapshot = json.dumps(results, sort_keys=True)
        extract.vote_facts(results)
        self.assertEqual(json.dumps(results, sort_keys=True), snapshot)


class DrainLoopTests(unittest.TestCase):
    """The 40/day ceiling, and the ways draining it could go wrong."""

    def _loop(self, batches, deadline=1000, clock=None):
        """Run drain_loop over a scripted list of (jobs, outcomes) batches."""
        script = list(batches)
        seen = []

        def fetch():
            return script[len(seen)][0] if len(seen) < len(script) else []

        def run(jobs):
            seen.append(jobs)
            return Counter(script[len(seen) - 1][1])

        kwargs = {"clock": clock} if clock else {}
        return extract.drain_loop(fetch, run, deadline, **kwargs), seen

    def test_drains_until_the_backlog_is_empty(self):
        (totals, batches, stopped), seen = self._loop([
            (["a"] * 40, {extract.EXTRACTED: 40}),
            (["b"] * 40, {extract.EXTRACTED: 38, extract.REJECTED: 2}),
            (["c"] * 5, {extract.EXTRACTED: 5}),
        ])
        self.assertEqual(stopped, extract.DRAINED)
        self.assertEqual(batches, 3)
        self.assertEqual(totals[extract.EXTRACTED], 83)
        self.assertEqual(totals[extract.REJECTED], 2)

    def test_nothing_to_do_runs_no_batches(self):
        (totals, batches, stopped), seen = self._loop([])
        self.assertEqual(batches, 0)
        self.assertEqual(stopped, extract.DRAINED)
        self.assertEqual(seen, [])

    def test_zero_progress_batch_breaks_the_loop(self):
        # THE ONE THAT MATTERS. Every call deferred, so the same rows stay
        # eligible and the next fetch would return them again. Without this
        # break the loop spins against a rate-limited endpoint until the
        # deadline burns -- strictly worse than the single batch it replaces.
        (totals, batches, stopped), seen = self._loop([
            (["a"] * 40, {extract.EXTRACTED: 40}),
            (["b"] * 40, {extract.DEFERRED: 40}),
            (["b"] * 40, {extract.DEFERRED: 40}),
            (["b"] * 40, {extract.DEFERRED: 40}),
        ])
        self.assertEqual(stopped, extract.NO_PROGRESS)
        self.assertEqual(batches, 2)
        self.assertEqual(len(seen), 2)

    def test_one_rejection_still_counts_as_progress(self):
        # A batch where every call came back unusable is progress: those rows
        # were tombstoned and will not be selected again.
        (totals, batches, stopped), seen = self._loop([
            (["a"] * 40, {extract.REJECTED: 40}),
            (["b"] * 40, {extract.DEFERRED: 40}),
        ])
        self.assertEqual(stopped, extract.NO_PROGRESS)
        self.assertEqual(batches, 2)

    def test_deadline_stops_the_loop_between_batches(self):
        ticks = iter([0, 5, 10, 15, 20, 25])
        (totals, batches, stopped), seen = self._loop(
            [(["a"] * 40, {extract.EXTRACTED: 40})] * 10,
            deadline=10, clock=lambda: next(ticks))
        self.assertEqual(stopped, extract.DEADLINE_HIT)
        # start=0 so deadline=10; batch 1 runs unconditionally, the check
        # before batch 2 reads 5 (<10) and runs it, the check before batch 3
        # reads 10 and stops.
        self.assertEqual(batches, 2)

    def test_the_first_batch_always_runs_however_late_it_is(self):
        # One batch per invocation is the old behaviour and the floor this
        # must never fall below -- a deadline already in the past must not
        # turn the nightly run into a no-op.
        ticks = iter([0, 9999, 9999])
        (totals, batches, stopped), seen = self._loop(
            [(["a"] * 40, {extract.EXTRACTED: 40})] * 3,
            deadline=0, clock=lambda: next(ticks))
        self.assertEqual(batches, 1)
        self.assertEqual(stopped, extract.DEADLINE_HIT)

    def test_deadline_is_never_checked_mid_batch(self):
        # The clock is read once per iteration, not per job: a batch that
        # starts is always finished, so the overshoot is bounded by one batch
        # and no posting is left half-extracted.
        reads = []

        def clock():
            reads.append(len(reads))
            return len(reads) * 100

        self._loop([(["a"] * 40, {extract.EXTRACTED: 40})] * 3,
                   deadline=1000, clock=clock)
        self.assertLessEqual(len(reads), 4)   # one start + one per iteration


@requires_db
class SchemaAndSelectionTests(unittest.TestCase):
    """The parts a fake connection structurally cannot check.

    Two claims here are about Postgres rather than about Python: that
    ensure_schema() creates the stability columns on a FRESH database (the
    migration only covers databases that already exist, and a schema whose
    two paths disagree is the drift schema.py:5-8 exists to prevent), and
    that select_unextracted_jobs' ORDER BY does what its docstring says when
    stale and never-extracted rows are mixed. The second cannot be asserted
    against production because production currently has no stale rows.
    """

    def _insert_job(self, conn, job_id, first_seen):
        conn.execute(
            "INSERT INTO jobs (id, platform, company_token, company_name, "
            "source_id, title, description_text, status, first_seen, "
            "last_seen) VALUES (%s, 'greenhouse', 'acme', 'Acme', %s, "
            "'Engineer', 'We are hiring an engineer.', %s, %s, %s)",
            (job_id, job_id, schema.STATUS_OPEN, first_seen, first_seen))

    def test_ensure_schema_creates_the_stability_columns(self):
        with scratchdb.scratch_schema() as (conn, _name):
            cols = dbconn.existing_columns(conn, schema.FACTS_TABLE)
            self.assertIn("extraction_passes", cols)
            self.assertIn("vote_unanimity", cols)

    def test_ensure_schema_creates_role_track(self):
        # Added via add_missing_columns rather than the CREATE TABLE, so a
        # FRESH database is exactly the path that could silently lack it --
        # and update_job_facts INSERTs every name in _FACT_COLUMNS, so a
        # missing column is an error on every extraction rather than a
        # degraded one.
        with scratchdb.scratch_schema() as (conn, _name):
            self.assertIn("role_track",
                          dbconn.existing_columns(conn, schema.FACTS_TABLE))

    def test_update_job_facts_writes_role_track(self):
        with scratchdb.scratch_schema() as (conn, _name):
            self._insert_job(conn, "j1", "2026-07-01T00:00:00")
            conn.commit()
            extract.update_job_facts(
                conn, "j1", result(role_track="technical_support"),
                "test-model")
            self.assertEqual(conn.execute(
                "SELECT role_track FROM job_facts WHERE job_id = 'j1'"
            ).fetchone()[0], "technical_support")

    def test_a_null_role_track_round_trips_as_null(self):
        with scratchdb.scratch_schema() as (conn, _name):
            self._insert_job(conn, "j2", "2026-07-01T00:00:00")
            conn.commit()
            extract.update_job_facts(conn, "j2", result(role_track=None),
                                     "test-model")
            self.assertIsNone(conn.execute(
                "SELECT role_track FROM job_facts WHERE job_id = 'j2'"
            ).fetchone()[0])

    def test_update_job_facts_writes_the_stability_columns(self):
        with scratchdb.scratch_schema() as (conn, _name):
            self._insert_job(conn, "j1", "2026-07-01T00:00:00")
            conn.commit()
            facts, unanimity = extract.vote_facts(
                [result(), result(), result(seniority_level="mid")])
            extract.update_job_facts(conn, "j1", facts, "test-model",
                                     passes=3, unanimity=unanimity)
            row = conn.execute(
                "SELECT extraction_passes, vote_unanimity, seniority_level "
                "FROM job_facts WHERE job_id = 'j1'").fetchone()
            self.assertEqual(row[0], 3)
            self.assertAlmostEqual(row[1], unanimity, places=5)
            self.assertEqual(row[2], "junior")

    def test_selection_is_never_extracted_first_then_fifo(self):
        with scratchdb.scratch_schema() as (conn, _name):
            # Two never extracted (one old, one new) and two carrying a
            # STALE facts row -- the state a FACTS_VERSION bump produces.
            self._insert_job(conn, "new-never", "2026-07-20T00:00:00")
            self._insert_job(conn, "old-never", "2026-07-01T00:00:00")
            self._insert_job(conn, "new-stale", "2026-07-21T00:00:00")
            self._insert_job(conn, "old-stale", "2026-07-02T00:00:00")
            for job_id in ("new-stale", "old-stale"):
                conn.execute(
                    "INSERT INTO job_facts (job_id, facts_version, "
                    "extracted_at) VALUES (%s, %s, '2026-07-01T00:00:00')",
                    (job_id, schema.FACTS_VERSION - 1))
            # And one already current, which must not be selected at all.
            self._insert_job(conn, "current", "2026-07-22T00:00:00")
            conn.execute(
                "INSERT INTO job_facts (job_id, facts_version, extracted_at) "
                "VALUES ('current', %s, '2026-07-01T00:00:00')",
                (schema.FACTS_VERSION,))
            conn.commit()

            cfgs = [dict(extract.relevance.DISABLED)]
            picked = [j["id"] for j in
                      extract.select_unextracted_jobs(conn, 10, cfgs)]
            self.assertEqual(picked,
                             ["old-never", "new-never", "old-stale", "new-stale"])
            # remaining() must agree with what selection can see, or the
            # summary line reports a backlog no batch will ever burn down.
            self.assertEqual(extract.remaining(conn, cfgs), len(picked))

    def test_an_input_rejection_tombstones_and_counts_as_unusable(self):
        """extract_one_job end to end on a poisoned row: no call, a labelled
        tombstone, and a REJECTED that main() prints as `unusable`.

        The three claims are one claim. A gate whose rejection does not reach
        the summary line is invisible, and a gate whose rejection does not
        reach job_facts is re-run every night forever.
        """
        with scratchdb.scratch_schema() as (conn, _name):
            self._insert_job(conn, "soup", "2026-07-01T00:00:00")
            conn.execute(
                "UPDATE jobs SET description_text = %s WHERE id = 'soup'",
                ('*]:pointer-events-auto data-testid="conversation-turn-136" '
                 'data-turn="assistant"> We are hiring an engineer.',))
            conn.commit()

            job_row = extract.select_unextracted_jobs(
                conn, 10, [dict(extract.relevance.DISABLED)])[0]
            self.assertEqual(job_row["id"], "soup")

            def must_not_be_called(prompt):
                self.fail("the gate let a poisoned posting reach the model")

            outcome, facts, passes, _ = extract.extract_facts(
                job_row, call=must_not_be_called)
            self.assertEqual(outcome, extract.REJECTED)

            # This is what main() sums into the `unusable` field of its
            # summary line (extract.py's print at the end of main()).
            self.assertEqual(Counter([outcome])[extract.REJECTED], 1)

            extract.mark_extract_failed(
                conn, "soup",
                f"{extract.INPUT_REJECT_LABEL}/test-model")
            stored = conn.execute(
                "SELECT facts_version, extraction_model FROM job_facts "
                "WHERE job_id = 'soup'").fetchone()
            self.assertEqual(stored[0], schema.FACTS_VERSION)
            self.assertTrue(stored[1].startswith(llm.FAILED_PREFIX))
            self.assertIn(extract.INPUT_REJECT_LABEL, stored[1])

            # And it is out of the backlog, so it costs nothing tomorrow.
            cfgs = [dict(extract.relevance.DISABLED)]
            self.assertEqual(extract.remaining(conn, cfgs), 0)

    def test_a_tombstone_is_not_reselected(self):
        with scratchdb.scratch_schema() as (conn, _name):
            self._insert_job(conn, "dead", "2026-07-01T00:00:00")
            conn.commit()
            extract.mark_extract_failed(conn, "dead", "test-model")
            cfgs = [dict(extract.relevance.DISABLED)]
            self.assertEqual(extract.select_unextracted_jobs(conn, 10, cfgs), [])
            self.assertEqual(extract.remaining(conn, cfgs), 0)


if __name__ == "__main__":
    unittest.main()

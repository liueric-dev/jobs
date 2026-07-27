"""Frozen digests for every lib/ function that decides row identity.

THIS FILE IS THE REASON lib/ CAN BE OWNED BY THIS REPO. READ BEFORE EDITING lib/.

lib/ was a shared package until 2026-07-26 and is now this repo's own code
(see lib/__init__.py and ~/apps/REORG.md slice G). Code that one application
owns outright is code that can be quietly rewritten -- and this project has
already proved what that costs, when a private reimplementation of these
functions accumulated four divergences, two of which changed content_hash and
therefore row identity for tens of thousands of rows.

What made that dangerous was not the rewriting. It was that nothing detected
it: the code ran, it looked right, and the disagreement existed only in the
digests it wrote.

So the values below are LITERALS, not recomputations. They were generated
against the shared library on 2026-07-26, immediately before it was split,
and they encode what production was actually storing at that moment. A test
that recomputes an expected value with the function under test proves
nothing; these prove the function still returns what the database holds.

Every assertion is self-contained. Nothing here consults another repo, reads
another checkout, or assumes one exists.

If you change a value here you must have a migration reason -- every one of
these digests is stored on ~11,400 rows in this repo's database.
"""

import hashlib
import sys, os
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lib import ids, text  # noqa: E402

#: Fixed instant for every relative-time vector. parse_relative_posted_at is
#: `now - delta`, so without pinning `now` these assertions would drift daily.
NOW = __import__("datetime").datetime(
    2026, 7, 26, 12, 0, 0, tzinfo=__import__("datetime").timezone.utc)


class TestMakeId(unittest.TestCase):
    """`id` is the primary key of every stored row."""

    VECTORS = [
        (("nyc_parks_events", "guid-1", "2026-07-24T19:00:00.000"),
         "b1116fa3fb6397306bc35ae1"),
        (("nypl_events", "Story Time", "2026-07-24T19:00:00+00:00"),
         "4fbde4e1f7ddfe1daf6c495a"),
        (("seatgeek", 12345, ""), "feac5dd0d7e49b7aef7fff76"),
        (("nyc_permitted_events", "Fair", ""), "e3b22670ccc1f6652974638e"),
        (("greenhouse", "flatironhealth", "4567"), "66c6be62c043efe58d2e7852"),
        (("lever", "sailorhealth", "abc-def"), "4b9a303ddd1010ff6711e1c4"),
        (("ashby", "formationbio", 99), "908fadace1816a236669baea"),
        (("a", None), "7360ad2bfeeea4d382aa0a6d"),
        (("a", ""), "bfc622d4a6d410f26be3d72d"),
    ]

    def test_frozen(self):
        for parts, expected in self.VECTORS:
            self.assertEqual(ids.make_id(*parts), expected,
                             f"make_id drift for {parts!r}")

    def test_none_is_not_empty(self):
        """A None part renders as 'None', matching the f-strings this replaced.

        Normalising None to "" would silently re-key every row whose
        source_id was absent -- the last two vectors above differ only here.
        """
        self.assertNotEqual(ids.make_id("a", None), ids.make_id("a", ""))


class TestContentHash(unittest.TestCase):
    """`content_hash` decides whether a re-seen row counts as changed."""

    EVENTS_REC = {
        "title": "Yoga", "description": None, "start_datetime": "2026-07-24",
        "end_datetime": None, "venue_name": "Chelsea Park", "address": "x",
        "borough": "Manhattan", "categories": "Fitness", "is_free": True,
        "registration_url": None, "source_url": "http://e",
        "latitude": 40.7, "longitude": -74.0,
    }
    EVENTS_FIELDS = ("title", "description", "start_datetime", "end_datetime",
                     "venue_name", "address", "borough", "categories",
                     "is_free", "registration_url", "source_url",
                     "latitude", "longitude")
    JOBS_REC = {
        "title": "Backend Engineer", "company": "Acme",
        "location": "New York, NY", "description_text": None,
        "url": "https://ex.com/j/1", "salary_text": None,
        "posted_at": "2026-07-20", "employment_type": "Full-time",
    }
    JOBS_FIELDS = ("title", "company", "location", "description_text", "url",
                   "salary_text", "posted_at", "employment_type")

    def test_events_shape(self):
        self.assertEqual(
            ids.content_hash(self.EVENTS_REC, self.EVENTS_FIELDS),
            "ae465bf86f67932951bb5ae20be303742c05b406c5c3ea19fe202f6e3915db43")

    def test_jobs_shape_bare(self):
        self.assertEqual(
            ids.content_hash(self.JOBS_REC, self.JOBS_FIELDS),
            "f7b19da3c13650d0687cd9ab0f7fb3624ea5b0f4639ec3b5c91f9bbe50efab92")

    def test_blank_if_falsy_is_not_cosmetic(self):
        """A falsy field hashing as "" rather than "None" is a DIFFERENT row.

        The jobs scripts hashed `rec.get("description_text") or ""` while
        hashing every other field bare. Losing this parameter re-hashes every
        row with no description.
        """
        blanked = ids.content_hash(
            self.JOBS_REC, self.JOBS_FIELDS,
            blank_if_falsy=("description_text", "salary_text"))
        self.assertEqual(
            blanked,
            "8b686b29ae1d243758521fbee8555ffd9b42c484333a48abb0d9e479f9c74e7a")
        self.assertNotEqual(
            blanked, ids.content_hash(self.JOBS_REC, self.JOBS_FIELDS))


class TestGoogleIdentity(unittest.TestCase):
    """Google posting identity -- jobs-only, absent from the events copy."""

    JOB_ID_BLOB = ("eyJqb2JfdGl0bGUiOiAiU1dFIiwgImNvbXBhbnlfbmFtZSI6ICJBY21lIi"
                   "wgImh0aWRvY2lkIjogIjVwNjloeE16Rm1RcmxMcWlBQUFBQUE9PSIsICJm"
                   "YyI6ICJyb3RhdGVzIn0")

    NORMALIZE_VECTORS = [
        ("https://ex.com/apply/?utm_campaign=google_jobs_apply&id=7",
         "https://ex.com/apply?id=7"),
        ("https://ex.com/apply/?gclid=x&b=2&a=1", "https://ex.com/apply?a=1&b=2"),
        ("https://ex.com/apply#frag", "https://ex.com/apply"),
        ("", ""),
        (None, ""),
    ]

    def test_normalize_apply_url_frozen(self):
        for url, expected in self.NORMALIZE_VECTORS:
            self.assertEqual(ids.normalize_apply_url(url), expected,
                             f"normalize_apply_url drift for {url!r}")

    def test_htidocid_wins(self):
        job = {"job_id": self.JOB_ID_BLOB, "title": "SWE",
               "apply_options": [{"link": "https://ex.com/a?utm_source=g"}]}
        self.assertEqual(ids.google_source_id(job, "acme"),
                         "5p69hxMzFmQrlLqiAAAAAA==")

    def test_fingerprint_fallback_frozen(self):
        job = {"job_id": None, "title": "  Senior   Backend Engineer ",
               "apply_options": [{"link": "https://ex.com/a/?utm_source=g&x=1"}]}
        self.assertEqual(ids.google_source_id(job, "acme"), "fp:aa84fae9ae4d7563")


class TestStripHtml(unittest.TestCase):
    """strip_html feeds content_hash. This is the exact function the previous
    vendoring attempt got wrong, by truncating at 5000 instead of 20000."""

    def test_cap_is_20000_and_output_is_frozen(self):
        long_markup = "<p>" + ("word &amp; more " * 3000) + "</p>"
        stripped = text.strip_html(long_markup)
        self.assertEqual(len(stripped), 20000,
                         "the truncation cap moved -- this is the 5000/20000 bug")
        self.assertEqual(
            hashlib.sha256(stripped.encode()).hexdigest(),
            "822d85aa697beb7eb7cd4976122bbfe28691cd27a7b62bf3da98ad22e5e5d4f6")

    def test_unescape_variants_both_frozen(self):
        """Both behaviours must stay reachable: ats.py passes unescape=False
        to preserve its stored hashes, the other sources rely on the default.
        Collapsing them rewrote 217 of 242 weworkremotely rows once already."""
        markup = "<div>Hello &amp; <b>welcome</b>\n\n  to   NYC</div>"
        self.assertEqual(text.strip_html(markup), "Hello & welcome to NYC")
        self.assertEqual(text.strip_html(markup, unescape=False),
                         "Hello &amp; welcome to NYC")

    def test_empty_is_none_not_empty_string(self):
        self.assertIsNone(text.strip_html(""))
        self.assertIsNone(text.strip_html("<p></p>"))


class TestPostedAt(unittest.TestCase):
    """posted_at is in the Google and Built In hash tuples, so its parsing
    is row identity too."""

    VECTORS = [
        ("3 days ago", "2026-07-23T12:00:00+00:00"),
        ("30+ days ago", "2026-06-26T12:00:00+00:00"),
        ("An Hour Ago", "2026-07-26T11:00:00+00:00"),
        ("51 Minutes Ago", "2026-07-26T11:09:00+00:00"),
        ("yesterday", "2026-07-25T00:00:00+00:00"),
        ("Reposted Yesterday", "2026-07-25T00:00:00+00:00"),
        ("Today", "2026-07-26T00:00:00+00:00"),
        ("2 weeks ago", "2026-07-12T12:00:00+00:00"),
        ("1 month ago", "2026-06-26T12:00:00+00:00"),
        ("a day ago", "2026-07-25T12:00:00+00:00"),
        ("no date here", None),
        ("", None),
        (None, None),
    ]

    def test_frozen(self):
        for value, expected in self.VECTORS:
            self.assertEqual(text.posted_at_timestamp(value, now=NOW), expected,
                             f"posted_at drift for {value!r}")

    def test_iso_passes_through_untouched(self):
        """An absolute date must not be reformatted -- it is stored as-is."""
        self.assertEqual(
            text.posted_at_timestamp("2026-07-20T10:00:00", now=NOW),
            "2026-07-20T10:00:00")

    def test_thirty_plus_days_is_parsed_not_rejected(self):
        """DELIBERATELY PINNED, because the docstring disagrees with it.

        text.parse_relative_posted_at's docstring says anything without an
        exact anchor ("30+ days ago") returns None rather than a guess. It
        does not: RELATIVE_TIME_PATTERN's `(\\d+)\\+?` captures the 30 and the
        '+' is discarded, so the value resolves to exactly 30 days.

        Whichever is right, rows are already stored under the behaviour, so
        it is frozen here and the docstring is the thing that is wrong. Do
        not "fix" the code to match the prose without a migration.
        """
        self.assertEqual(text.posted_at_timestamp("30+ days ago", now=NOW),
                         text.posted_at_timestamp("30 days ago", now=NOW))


class TestBoundedJson(unittest.TestCase):
    """raw_json must stay VALID json -- the previous vendoring sliced it."""

    def test_oversized_stays_parseable(self):
        import json
        big = {"id": "x1", "url": "https://ex.com", "description": "z" * 30000}
        dumped = text.bounded_json(big, 20000)
        self.assertLessEqual(len(dumped), 20000)
        self.assertEqual(json.loads(dumped)["id"], "x1",
                         "bounded_json produced a stump json.loads cannot read")
        self.assertEqual(
            hashlib.sha256(dumped.encode()).hexdigest(),
            "17099daad9dd193a31fd5150c87149097642bdc488e4135d323912573c2615ce")


if __name__ == "__main__":
    unittest.main()

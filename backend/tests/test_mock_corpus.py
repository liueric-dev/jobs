"""Tests for evals/mock_corpus.py -- the 55 synthetic postings and their key.

WHAT IS PINNED HERE
    The properties whose violation would be silent, and each of them is about
    the measurement rather than the arithmetic:

      * a mapped record carries every schema.COLUMNS key, because a missing
        one fails that record inside its SAVEPOINT rather than raising
        (schema.py:118-120) -- a corpus that quietly ran 54 postings would
        still report a number;
      * `job_url` is empty, so a mock row cannot reach jobs_app even if one
        leaked into a real schema (schema.py:711);
      * every non-null quote in the real key file is a BYTE-EXACT substring of
        the field it names. This is the property that makes the key auditable
        rather than merely assertable: a quote that has been tidied cannot be
        checked back against the posting by anybody;
      * a null expected value is NOT MEASURABLE and never a mismatch, because
        counting the fixture's own silence as a model error manufactures
        precision out of nothing;
      * reconcile() prints both verdicts and never one merged one;
      * nothing can ever pull this into the nightly run.

THE REAL-KEY TESTS RUN UNCONDITIONALLY
    mock-postings-v3-answer-key.json is written by a separate hand. The tests
    that read it are NOT skipUnless'd on its existence: a skipped test is a
    test nobody runs, and the whole point of the quote-substring property is
    that it holds for the file that actually ships. Until the key lands these
    fail with `MockCorpusError: ...answer-key.json: not found`, which names
    the missing file and is a better prompt than a green run.
"""

import ast
import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import extract                                        # noqa: E402
import schema                                         # noqa: E402
from evals import mock_corpus as mc                   # noqa: E402
from lib import text                                  # noqa: E402

BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _posting(job_id="mock_900", **over):
    """A structurally valid posting. Every field the loader validates."""
    posting = {
        "job_id": job_id,
        "title": "Operations Associate",
        "company_name": "Northgate Mutual Aid",
        "location": "New York, NY",
        "remote_policy": "hybrid",
        "source": "mock",
        "generated_by": "human",
        "posted_at": "2026-07-20",
        "description_text": "We use an AI intake assistant daily. No prior "
                            "experience required.",
        "comp_min": 45000,
        "comp_max": 55000,
        "comp_currency": "USD",
        "comp_period": "yearly",
        "comp_is_estimated": False,
    }
    posting.update(over)
    return posting


def _entry(**over):
    entry = {
        "verdict": "good",
        "failure_modes": [],
        "key_source": "hand",
        "notes": "",
        "fields": {},
    }
    entry.update(over)
    return entry


def _key(postings, entries):
    return {
        "_comment": "test fixture",
        "_method": "hand",
        "_not_a_label": "specification fixture, never eval_labels",
        "_generated": "2026-07-29",
        "postings_file": "postings.json",
        "postings_sha256": "0" * 64,
        "n": len(entries),
        "entries": entries,
    }


class _Pair:
    """A temporary (postings, key) file pair, so the cross-file validations
    can be exercised without touching either shipped file."""

    def __init__(self, postings, entries):
        self.dir = tempfile.TemporaryDirectory()
        self.postings_path = os.path.join(self.dir.name, "postings.json")
        self.key_path = os.path.join(self.dir.name, "key.json")
        with open(self.postings_path, "w", encoding="utf-8") as fh:
            json.dump(postings, fh)
        with open(self.key_path, "w", encoding="utf-8") as fh:
            json.dump(_key(postings, entries), fh)

    def load(self):
        return mc.load_key(self.key_path,
                           postings=mc.load_postings(self.postings_path))

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.dir.cleanup()
        return False


# --------------------------------------------------------------------------
# The postings file
# --------------------------------------------------------------------------

class TestPostings(unittest.TestCase):

    def test_the_corpus_is_fifty_five_postings_with_distinct_ids(self):
        """mock_corpus.EXPECTED_N. Two postings sharing a job_id would share a
        source_id and collapse to one row under schema.make_job_id
        (schema.py:302), shrinking the corpus with nothing reporting it."""
        postings = mc.load_postings()
        self.assertEqual(len(postings), mc.EXPECTED_N)
        self.assertEqual(len(postings), 55)
        ids = [p["job_id"] for p in postings]
        self.assertEqual(len(set(ids)), 55)

    def test_file_order_is_preserved_because_it_is_the_narrative_order(self):
        """load_postings docstring: 001-040 are the first batch, 041-055 the
        second, which is how the addendum reads
        (mock-postings-v3-answer-key-addendum.md:3-4)."""
        ids = [p["job_id"] for p in mc.load_postings()]
        self.assertEqual(ids[0], "mock_001")
        self.assertEqual(ids[-1], "mock_055")
        self.assertEqual(ids, sorted(ids))

    def test_a_duplicate_job_id_is_an_error_and_not_a_dropped_posting(self):
        """load_postings raises rather than de-duplicating: silently keeping
        the last of two would make the corpus 54 and say nothing."""
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "p.json")
            with open(path, "w", encoding="utf-8") as fh:
                json.dump([_posting("mock_900"), _posting("mock_900")], fh)
            with self.assertRaises(mc.MockCorpusError) as cm:
                mc.load_postings(path)
        self.assertIn("duplicate job_id", str(cm.exception))

    def test_an_empty_description_is_rejected(self):
        """POSTING_REQUIRED_NONEMPTY. An empty description is not a hard case,
        it is a missing case, and extract.py's own selector would exclude it
        (evals/corpus.py:48-50) -- so it would silently leave the corpus."""
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "p.json")
            with open(path, "w", encoding="utf-8") as fh:
                json.dump([_posting(description_text="   ")], fh)
            with self.assertRaises(mc.MockCorpusError) as cm:
                mc.load_postings(path)
        self.assertIn("description_text is empty", str(cm.exception))

    def test_a_posting_missing_a_key_names_the_key(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "p.json")
            broken = _posting()
            del broken["comp_currency"]
            with open(path, "w", encoding="utf-8") as fh:
                json.dump([broken], fh)
            with self.assertRaises(mc.MockCorpusError) as cm:
                mc.load_postings(path)
        self.assertIn("comp_currency", str(cm.exception))

    def test_a_posting_claiming_a_real_source_is_rejected(self):
        """`source` must be "mock". A real posting inside a file that claims to
        be synthetic is the one input that would make the whole fixture's
        provenance claim false."""
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "p.json")
            with open(path, "w", encoding="utf-8") as fh:
                json.dump([_posting(source="greenhouse")], fh)
            with self.assertRaises(mc.MockCorpusError):
                mc.load_postings(path)


# --------------------------------------------------------------------------
# The mapping to `jobs` records
# --------------------------------------------------------------------------

class TestJobRecords(unittest.TestCase):

    def setUp(self):
        self.postings = mc.load_postings()
        self.records = mc.records(self.postings)

    def test_every_record_carries_exactly_the_eighteen_writable_columns(self):
        """schema.COLUMNS (schema.py:121-128). upsert binds these as named
        parameters, so a missing key fails THAT record inside its SAVEPOINT
        rather than the batch (schema.py:118-120) -- one line of a summary,
        which is exactly the kind of loss this corpus exists to not have."""
        self.assertEqual(len(schema.COLUMNS), 18)
        for record in self.records:
            self.assertEqual(set(record), set(schema.COLUMNS))

    def test_every_not_null_column_is_non_empty_on_every_record(self):
        """The `jobs` DDL at schema.py:333-338 declares platform,
        company_token, company_name and source_id NOT NULL. Every other
        writable column is nullable, so those four are the whole obligation."""
        not_null = ("platform", "company_token", "company_name", "source_id")
        for record in self.records:
            for column in not_null:
                self.assertTrue(str(record[column] or "").strip(),
                                f"{column} empty on {record['source_id']}")

    def test_platform_is_exactly_mock_and_no_whitelist_forbids_it(self):
        """`jobs.platform` is a bare TEXT NOT NULL (schema.py:335) -- there is
        no CHECK constraint and no enum. The only platform tuple in the
        codebase is ats_sources.HANDLED_PLATFORMS (ingest/ats_sources.py:76),
        which gates which ATS feeds are FETCHED and is never consulted on a
        write, so "mock" is admissible without changing anything."""
        self.assertEqual(mc.PLATFORM, "mock")
        for record in self.records:
            self.assertEqual(record["platform"], "mock")
        with open(os.path.join(BACKEND, "schema.py"), encoding="utf-8") as fh:
            ddl = fh.read()
        self.assertNotIn("platform TEXT NOT NULL CHECK", ddl)

    def test_job_url_is_empty_so_a_mock_row_can_never_reach_the_webapp(self):
        """jobs_app's WHERE requires `coalesce(j.job_url,'') <> ''`
        (schema.py:711). An empty job_url is therefore a containment
        guarantee: a mock row that leaked into a real schema still cannot
        surface to a user. Filling this in would remove that guarantee and
        nothing else would notice."""
        for record in self.records:
            self.assertEqual(record["job_url"], "")
        with open(os.path.join(BACKEND, "schema.py"), encoding="utf-8") as fh:
            self.assertIn("coalesce(j.job_url, '') <> ''", fh.read())

    def test_the_row_id_is_the_hash_and_never_the_raw_mock_id(self):
        """schema.make_job_id (schema.py:302) = sha256("mock:<token>:mock_001")
        truncated to 24. A caller that assumes `mock_001` is the key joins
        against nothing."""
        first = self.postings[0]
        job_id = mc.job_id_for(first)
        self.assertEqual(len(job_id), 24)
        self.assertNotEqual(job_id, first["job_id"])
        self.assertEqual(job_id, schema.make_job_id(mc.to_job_record(first)))

    def test_job_ids_are_deterministic_across_two_calls_and_all_distinct(self):
        """Determinism is what lets the scratch schema be rebuilt and the
        answer key still join. Distinctness matters because two of the 55
        share a company_name -- Upwork and Fiverr each appear twice -- so the
        source_id is the only thing separating those pairs."""
        first = [mc.job_id_for(p) for p in self.postings]
        second = [mc.job_id_for(p) for p in mc.load_postings()]
        self.assertEqual(first, second)
        self.assertEqual(len(set(first)), 55)
        tokens = [r["company_token"] for r in self.records]
        self.assertLess(len(set(tokens)), len(tokens),
                        "the duplicate-company case must stay in the corpus")

    def test_the_location_booleans_are_never_null(self):
        """relevance.py:291-295 wraps every location column in
        COALESCE(col, FALSE), so a NULL reads as "not acceptable" and drops
        the row from tier 1 to tier 2. Leaving them NULL would mean the
        tier-1 gate never runs against this corpus while a tier number is
        still reported for all 55."""
        for record in self.records:
            self.assertIsInstance(record["location_is_nyc"], bool)
            self.assertIsInstance(record["location_is_remote"], bool)

    def test_the_nyc_heuristics_own_misses_are_kept_rather_than_corrected(self):
        """lib.text.NYC_PATTERN (lib/text.py:25) lists seven names and no
        neighbourhoods, so Long Island City and Astoria classify as NOT NYC
        even though both are Queens. Pinned rather than fixed: lib/ is
        vendored byte-identical to another repo, and hand-correcting the flags
        here would report a gate that production does not have."""
        by_id = {p["job_id"]: mc.to_job_record(p) for p in self.postings}
        self.assertEqual(by_id["mock_022"]["location_raw"],
                         "Long Island City, NY")
        self.assertFalse(by_id["mock_022"]["location_is_nyc"])
        self.assertEqual(by_id["mock_028"]["location_raw"], "Astoria, NY")
        self.assertFalse(by_id["mock_028"]["location_is_nyc"])
        self.assertTrue(by_id["mock_001"]["location_is_nyc"])

    def test_a_stated_remote_policy_only_ever_adds_is_remote(self):
        """"hybrid" is not remote, and a "Remote" location string already sets
        the flag through classify_location -- so the policy is a supplement to
        the heuristic and never a contradiction of it."""
        record = mc.to_job_record(
            _posting(location="Wichita, KS", remote_policy="remote"))
        self.assertTrue(record["location_is_remote"])
        self.assertFalse(record["location_is_nyc"])
        hybrid = mc.to_job_record(
            _posting(location="Wichita, KS", remote_policy="hybrid"))
        self.assertFalse(hybrid["location_is_remote"])

    def test_the_mocks_own_facts_are_stripped_from_the_input_row(self):
        """`remote_policy` and the four comp_* keys are job_facts columns
        (schema.py:420-424) -- things extract.py is supposed to PRODUCE.
        upsert ignores non-column keys (tests/test_nyc_open_data.py:490-505),
        so carrying them would write fine and corrupt the measurement: any
        later reader would be taking the answer off the input row."""
        record = mc.to_job_record(self.postings[0])
        for leaked in ("remote_policy", "comp_min", "comp_max",
                       "comp_currency", "comp_period", "comp_is_estimated"):
            self.assertNotIn(leaked, record)

    def test_derived_fields_come_from_the_real_helpers(self):
        """seniority_guess and posted_at_ts are lib/text.py's, not
        reimplemented here -- one implementation, and the mock rows are
        derived the same way every real row is."""
        for posting, record in zip(self.postings, self.records):
            self.assertEqual(record["seniority_guess"],
                             text.guess_seniority(posting["title"]))
            self.assertEqual(record["posted_at_ts"],
                             text.posted_at_timestamp(posting["posted_at"]))
            self.assertEqual(record["company_token"],
                             text.slugify(posting["company_name"]))

    def test_the_spec_hashes_the_short_field_set(self):
        """HASH_FIELDS_SHORT (schema.py:134-135) rather than HASH_FIELDS_ATS:
        the mock postings carry no department, so hashing it would hash a
        constant None across all 55."""
        spec = mc.spec()
        self.assertEqual(spec.hash_fields, schema.HASH_FIELDS_SHORT)
        self.assertEqual(spec.table, schema.TABLE)
        self.assertEqual(spec.columns, schema.COLUMNS)


# --------------------------------------------------------------------------
# The answer key, against synthetic files
# --------------------------------------------------------------------------

class TestKeyValidation(unittest.TestCase):

    def test_an_entry_for_an_unknown_job_id_is_an_error(self):
        with _Pair([_posting("mock_900")],
                   {"mock_900": _entry(), "mock_999": _entry()}) as pair:
            with self.assertRaises(mc.MockCorpusError) as cm:
                pair.load()
        self.assertIn("mock_999", str(cm.exception))

    def test_a_posting_with_no_entry_is_an_error_and_not_a_skip(self):
        """A key covering part of the corpus computes precision over whichever
        part somebody got to -- the flattering denominator this fixture exists
        to avoid."""
        with _Pair([_posting("mock_900"), _posting("mock_901")],
                   {"mock_900": _entry()}) as pair:
            with self.assertRaises(mc.MockCorpusError) as cm:
                pair.load()
        self.assertIn("mock_901", str(cm.exception))
        self.assertIn("no entry", str(cm.exception))

    def test_a_value_outside_the_closed_vocabulary_is_rejected(self):
        """The vocabularies are extract.py's own tuples by reference
        (SENIORITY:220, ARCHETYPE:262, AI_INVOLVEMENT:310, REMOTE_POLICY:312),
        not copies -- ARCHETYPE went from 12 values to 26 at FACTS_VERSION 3
        and a stale duplicate here would reject 14 valid answers."""
        fields = {"seniority_level": {"value": "entry_level", "quote": None}}
        with _Pair([_posting("mock_900")],
                   {"mock_900": _entry(fields=fields)}) as pair:
            with self.assertRaises(mc.MockCorpusError) as cm:
                pair.load()
        self.assertIn("closed vocabulary", str(cm.exception))
        self.assertNotIn("entry_level", extract.SENIORITY)

    def test_a_good_value_in_every_closed_vocabulary_is_accepted(self):
        fields = {name: {"value": vocab[0], "quote": None}
                  for name, vocab in mc.CLOSED_VOCABULARIES.items()}
        with _Pair([_posting("mock_900")],
                   {"mock_900": _entry(fields=fields)}) as pair:
            key = pair.load()
        self.assertEqual(len(key["mock_900"]["fields"]),
                         len(mc.CLOSED_VOCABULARIES))

    def test_a_quote_that_is_not_a_literal_substring_is_rejected(self):
        """The property that makes the key auditable rather than merely
        assertable. A tidied quote cannot be checked back against the posting
        by anybody, so it stops being evidence and becomes an assertion."""
        posting = _posting("mock_900")
        fields = {"ai_involvement": {
            "value": "uses_ai_tools",
            "quote": "we use an AI intake assistant daily"}}   # lower-cased W
        with _Pair([posting], {"mock_900": _entry(fields=fields)}) as pair:
            with self.assertRaises(mc.MockCorpusError) as cm:
                pair.load()
        self.assertIn("literal substring", str(cm.exception))

    def test_a_byte_exact_quote_is_accepted_and_a_quote_may_name_its_field(self):
        posting = _posting("mock_900")
        fields = {
            "ai_involvement": {"value": "uses_ai_tools",
                               "quote": "We use an AI intake assistant"},
            "remote_policy": {"value": "hybrid", "quote": "New York, NY",
                              "quote_field": "location_raw"},
        }
        with _Pair([posting], {"mock_900": _entry(fields=fields)}) as pair:
            key = pair.load()
        self.assertEqual(
            mc.expected(key, "mock_900", "remote_policy"),
            ("hybrid", "New York, NY"))

    def test_a_quote_naming_a_field_the_posting_does_not_have_is_rejected(self):
        fields = {"summary": {"value": "x", "quote": "y",
                              "quote_field": "department"}}
        with _Pair([_posting("mock_900")],
                   {"mock_900": _entry(fields=fields)}) as pair:
            with self.assertRaises(mc.MockCorpusError) as cm:
                pair.load()
        self.assertIn("quote_field", str(cm.exception))

    def test_a_fields_name_that_is_not_a_job_facts_column_is_rejected(self):
        """Nothing extracts it, so nothing can ever be scored against it, and
        a key that carries one has an expectation no run can meet."""
        fields = {"vibe": {"value": "good", "quote": None}}
        with _Pair([_posting("mock_900")],
                   {"mock_900": _entry(fields=fields)}) as pair:
            with self.assertRaises(mc.MockCorpusError) as cm:
                pair.load()
        self.assertIn("job_facts column", str(cm.exception))

    def test_a_loader_field_inside_fields_is_still_rejected(self):
        """UNSOFTENED. match.py:275-288 selects j.location_is_nyc and
        j.location_is_remote from the `jobs` table alongside twelve job_facts
        columns, so they reach score_job looking exactly like extracted facts.
        No model produces them -- mock_corpus._location_flags() does -- so
        scoring one would compare this module's mapping to the key's reading of
        the same string and put the agreement in an extraction numerator."""
        fields = {"location_is_nyc": {"value": True, "quote": None}}
        with _Pair([_posting("mock_900")],
                   {"mock_900": _entry(fields=fields)}) as pair:
            with self.assertRaises(mc.MockCorpusError) as cm:
                pair.load()
        self.assertIn("`jobs` column", str(cm.exception))
        self.assertIn("loader_fields", str(cm.exception))

    def test_an_unknown_verdict_or_failure_mode_is_rejected(self):
        with _Pair([_posting("mock_900")],
                   {"mock_900": _entry(verdict="maybe")}) as pair:
            with self.assertRaises(mc.MockCorpusError):
                pair.load()
        with _Pair([_posting("mock_900")],
                   {"mock_900": _entry(verdict="bad",
                                       failure_modes=["vibes"])}) as pair:
            with self.assertRaises(mc.MockCorpusError) as cm:
                pair.load()
        self.assertIn("vibes", str(cm.exception))

    def test_a_declared_n_that_disagrees_with_the_entries_is_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            postings = [_posting("mock_900")]
            ppath = os.path.join(d, "p.json")
            kpath = os.path.join(d, "k.json")
            with open(ppath, "w", encoding="utf-8") as fh:
                json.dump(postings, fh)
            key = _key(postings, {"mock_900": _entry()})
            key["n"] = 55
            with open(kpath, "w", encoding="utf-8") as fh:
                json.dump(key, fh)
            with self.assertRaises(mc.MockCorpusError) as cm:
                mc.load_key(kpath, postings=mc.load_postings(ppath))
        self.assertIn("n=55", str(cm.exception))

    def test_a_missing_key_file_names_the_file_rather_than_returning_empty(self):
        with self.assertRaises(mc.MockCorpusError) as cm:
            mc.load_key(os.path.join(mc._MOCK_DIR, "no-such-key.json"))
        self.assertIn("not found", str(cm.exception))


# --------------------------------------------------------------------------
# Reading the key
# --------------------------------------------------------------------------

class TestNotMeasurable(unittest.TestCase):

    def test_a_null_value_is_not_measurable_and_is_never_a_mismatch(self):
        """A null value means "not determinable from the posting". Scoring a
        model wrong for it manufactures errors out of the fixture's own
        silence and shrinks nothing -- the denominator stays 55 while the
        numerator drops, which is a fabricated regression."""
        fields = {"comp_min": {"value": None, "quote": None,
                               "notes": "no comp stated"}}
        with _Pair([_posting("mock_900")],
                   {"mock_900": _entry(fields=fields)}) as pair:
            key = pair.load()
        self.assertEqual(mc.expected(key, "mock_900", "comp_min"),
                         (None, None))
        self.assertFalse(mc.is_measurable(key, "mock_900", "comp_min"))
        self.assertEqual(mc.measurable(key, "comp_min"), [])

    def test_absent_and_null_are_distinguishable_at_the_expected_call(self):
        """Three outcomes, and conflating the first two is how a denominator
        goes wrong: None means the key is silent, (None, quote) means the key
        says the posting does not determine it."""
        fields = {"comp_min": {"value": None, "quote": None}}
        with _Pair([_posting("mock_900")],
                   {"mock_900": _entry(fields=fields)}) as pair:
            key = pair.load()
        self.assertIsNone(mc.expected(key, "mock_900", "summary"))
        self.assertIsNotNone(mc.expected(key, "mock_900", "comp_min"))
        self.assertIsNone(mc.expected(key, "mock_999", "comp_min"))

    def test_a_falsy_but_real_answer_is_measurable(self):
        """False and 0 are perfectly good expected answers, which is why
        callers must branch on is_measurable() and not on truthiness."""
        fields = {"ml_research_required": {"value": False, "quote": None},
                  "years_experience_min": {"value": 0, "quote": None}}
        with _Pair([_posting("mock_900")],
                   {"mock_900": _entry(fields=fields)}) as pair:
            key = pair.load()
        self.assertTrue(mc.is_measurable(key, "mock_900",
                                         "ml_research_required"))
        self.assertTrue(mc.is_measurable(key, "mock_900",
                                         "years_experience_min"))
        self.assertEqual(mc.measurable(key, "years_experience_min"),
                         ["mock_900"])


class TestTheTwoBlocksStayDisjoint(unittest.TestCase):
    """`fields` holds what a model produces; `loader_fields` holds what
    to_job_record() produces. match.py:275-288 selects both kinds into one
    flat row -- twelve columns from job_facts and two from jobs -- so past
    that SELECT nothing distinguishes them, and an accuracy figure that summed
    them would credit the model with 110 agreements it was never asked for."""

    def test_the_two_vocabularies_share_no_name(self):
        """The structural precondition. If a name were in both tuples the
        two-directional check below would accept it in either block and the
        split would be decorative."""
        self.assertEqual(set(mc.FACT_FIELDS) & set(mc.LOADER_FIELDS), set())
        self.assertEqual(set(mc.LOADER_FIELDS), set(schema.COLUMNS))
        for name in ("location_is_nyc", "location_is_remote"):
            self.assertIn(name, mc.LOADER_FIELDS)
            self.assertNotIn(name, mc.FACT_FIELDS)

    def test_an_extraction_field_inside_loader_fields_is_rejected(self):
        """The other direction. In `loader_fields` a job_facts column would be
        quietly removed from the extraction denominator -- the numerator would
        not move and the percentage would, which is worse than an error."""
        loader = {"seniority_level": {"value": "junior", "quote": None}}
        with _Pair([_posting("mock_900")],
                   {"mock_900": _entry(loader_fields=loader)}) as pair:
            with self.assertRaises(mc.MockCorpusError) as cm:
                pair.load()
        self.assertIn("job_facts column", str(cm.exception))
        self.assertIn("`fields`", str(cm.exception))

    def test_a_name_in_neither_vocabulary_is_rejected_from_loader_fields(self):
        loader = {"vibe": {"value": True, "quote": None}}
        with _Pair([_posting("mock_900")],
                   {"mock_900": _entry(loader_fields=loader)}) as pair:
            with self.assertRaises(mc.MockCorpusError) as cm:
                pair.load()
        self.assertIn("schema.COLUMNS", str(cm.exception))

    def test_a_valid_loader_block_is_accepted_and_read_by_its_own_door(self):
        loader = {"location_is_nyc": {"value": True, "quote": "New York, NY",
                                      "quote_field": "location"}}
        with _Pair([_posting("mock_900")],
                   {"mock_900": _entry(loader_fields=loader)}) as pair:
            key = pair.load()
        self.assertEqual(mc.loader_expected(key, "mock_900",
                                            "location_is_nyc"),
                         (True, "New York, NY"))

    def test_expected_refuses_a_loader_field_rather_than_answering_none(self):
        """Returning None would let a caller compute location_is_nyc accuracy
        over a denominator of zero and print it beside the real figures. A
        raise is the only outcome that cannot be skipped past."""
        loader = {"location_is_nyc": {"value": True, "quote": None}}
        with _Pair([_posting("mock_900")],
                   {"mock_900": _entry(loader_fields=loader)}) as pair:
            key = pair.load()
        with self.assertRaises(mc.MockCorpusError) as cm:
            mc.expected(key, "mock_900", "location_is_nyc")
        self.assertIn("loader_expected", str(cm.exception))
        with self.assertRaises(mc.MockCorpusError):
            mc.measurable(key, "location_is_nyc")

    def test_the_two_accessors_return_disjoint_sets(self):
        """extraction_fields() and loader_fields() are what agent C's
        denominators are built from. A caller wanting one denominator has to
        take the union in its own source, where a reviewer can see it."""
        fields = {"seniority_level": {"value": "junior", "quote": None}}
        loader = {"location_is_nyc": {"value": True, "quote": None}}
        with _Pair([_posting("mock_900")],
                   {"mock_900": _entry(fields=fields,
                                       loader_fields=loader)}) as pair:
            key = pair.load()
        self.assertEqual(mc.extraction_fields(key), {"seniority_level"})
        self.assertEqual(mc.loader_fields(key), {"location_is_nyc"})
        self.assertEqual(mc.extraction_fields(key) & mc.loader_fields(key),
                         set())

    def test_a_loader_block_on_some_entries_but_not_all_is_rejected(self):
        """A partial block is a denominator chosen by whoever stopped editing
        -- the same defect as a half-written key, one level down."""
        loader = {"location_is_nyc": {"value": True, "quote": None}}
        with _Pair([_posting("mock_900"), _posting("mock_901")],
                   {"mock_900": _entry(loader_fields=loader),
                    "mock_901": _entry()}) as pair:
            with self.assertRaises(mc.MockCorpusError) as cm:
                pair.load()
        self.assertIn("mock_901", str(cm.exception))
        self.assertIn("loader_fields", str(cm.exception))

    def test_loader_disagreements_reports_both_readings_and_merges_neither(self):
        """The check runs backwards here: the key is a second reader and
        _location_flags() is the thing under test. Reported as a pair for the
        same reason reconcile() is -- a mapping bug and a key typo look
        identical from one merged value."""
        posting = _posting("mock_900", location="Wichita, KS")
        loader = {"location_is_nyc": {"value": True, "quote": None,
                                      "notes": "key says NYC"}}
        with _Pair([posting], {"mock_900": _entry(loader_fields=loader)}) as p:
            key = p.load()
            rows = mc.loader_disagreements(key,
                                           postings=mc.load_postings(
                                               p.postings_path))
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["field"], "location_is_nyc")
        self.assertFalse(rows[0]["derived"])
        self.assertTrue(rows[0]["key"])
        self.assertNotIn("value", rows[0])

    def test_a_null_loader_value_is_not_a_disagreement(self):
        loader = {"location_is_nyc": {"value": None, "quote": None}}
        with _Pair([_posting("mock_900")],
                   {"mock_900": _entry(loader_fields=loader)}) as p:
            key = p.load()
            rows = mc.loader_disagreements(key,
                                           postings=mc.load_postings(
                                               p.postings_path))
        self.assertEqual(rows, [])


class TestReconcile(unittest.TestCase):

    def test_reconcile_returns_both_verdicts_and_never_one_merged_one(self):
        """HANDOFF's rule is to make the tool print both rather than pick one.
        A disagreement resolved inside a loader is a real distinction buried
        where nobody will look for it -- and mock_042 is exactly such a case,
        "good - flag for your judgment"
        (mock-postings-v3-answer-key-addendum.md:37)."""
        entries = {"mock_900": _entry(verdict="bad",
                                      failure_modes=["seniority"],
                                      addendum_verdict="good",
                                      addendum_note="degree floor")}
        with _Pair([_posting("mock_900")], entries) as pair:
            rows = mc.reconcile(pair.load())
        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(row["derived"], "bad")
        self.assertEqual(row["addendum"], "good")
        self.assertFalse(row["agrees"])
        self.assertEqual(row["note"], "degree floor")
        self.assertNotIn("verdict", row,
                         "a single merged verdict is the thing this must "
                         "never produce")

    def test_reconcile_reports_agreement_rather_than_omitting_it(self):
        """An agreeing row is evidence the addendum was read, not noise: a
        list that only held disagreements would be indistinguishable from a
        reconciliation nobody ran."""
        entries = {"mock_900": _entry(addendum_verdict="good")}
        with _Pair([_posting("mock_900")], entries) as pair:
            rows = mc.reconcile(pair.load())
        self.assertEqual(len(rows), 1)
        self.assertTrue(rows[0]["agrees"])

    def test_an_entry_with_no_addendum_verdict_produces_no_row(self):
        with _Pair([_posting("mock_900")], {"mock_900": _entry()}) as pair:
            self.assertEqual(mc.reconcile(pair.load()), [])

    def test_verdicts_and_failure_modes_are_flat_lookups(self):
        entries = {"mock_900": _entry(verdict="bad",
                                      failure_modes=["branding_trap",
                                                     "out_of_scope_location"])}
        with _Pair([_posting("mock_900")], entries) as pair:
            key = pair.load()
        self.assertEqual(mc.verdicts(key), {"mock_900": "bad"})
        self.assertEqual(mc.failure_modes(key),
                         {"mock_900": ["branding_trap",
                                       "out_of_scope_location"]})

    def test_the_compound_failure_case_is_representable(self):
        """mock-postings-v3-answer-key-addendum.md:60-63 keeps at least one
        posting that fails for two independent reasons, since real postings do
        not usually fail for a single tidy one. failure_modes is a list for
        that reason and must not be narrowed to a single value."""
        self.assertIn("branding_trap", mc.FAILURE_MODES)
        self.assertIn("out_of_scope_location", mc.FAILURE_MODES)
        self.assertEqual(len(mc.FAILURE_MODES), 6)


# --------------------------------------------------------------------------
# The real answer key. These fail until it lands, deliberately.
# --------------------------------------------------------------------------

class TestTheShippedAnswerKey(unittest.TestCase):
    """No skipUnless. See this module's docstring: a skipped test is a test
    nobody runs, and the quote-substring property only matters for the file
    that actually ships."""

    def test_the_shipped_key_loads_and_covers_every_posting(self):
        key = mc.load_key()
        self.assertEqual(len(key), mc.EXPECTED_N)
        self.assertEqual(set(key),
                         {p["job_id"] for p in mc.load_postings()})

    def test_every_non_null_quote_in_the_shipped_key_is_byte_exact(self):
        """The property that makes the key auditable rather than merely
        assertable. Asserted here directly, and not only through load_key, so
        that the failure names the field and the posting."""
        postings = {p["job_id"]: p for p in mc.load_postings()}
        key = mc.load_key()
        checked = 0
        for job_id, entry in sorted(key.items()):
            for name, field in sorted(entry["fields"].items()):
                quote = field["quote"]
                if quote is None:
                    continue
                source_field = field.get("quote_field",
                                         mc.DEFAULT_QUOTE_FIELD)
                source = mc._quote_source(postings[job_id], source_field)
                self.assertIsNotNone(source, f"{job_id}.{name}")
                self.assertIn(quote, source, f"{job_id}.{name}")
                checked += 1
        self.assertGreater(checked, 0,
                           "a key with no quotes at all is unauditable")

    def test_every_shipped_value_is_in_the_closed_vocabulary(self):
        key = mc.load_key()
        for job_id, entry in sorted(key.items()):
            for name, field in sorted(entry["fields"].items()):
                vocab = mc.CLOSED_VOCABULARIES.get(name)
                if vocab is None or field["value"] is None:
                    continue
                self.assertIn(field["value"], vocab, f"{job_id}.{name}")

    def test_the_shipped_key_answers_the_addendum(self):
        """mock-postings-v3-answer-key-addendum.md:54-56 states 30 good and 25
        bad. Asserted against the derived verdicts so a key that drifted from
        the document it was written against says so out loud.

        `undecided` counts with `good`: mock_042 is the one posting the
        addendum flags for judgment (line 37) and it sits on the good side of
        its own count. A posting moving off the bad side is a substantive
        reclassification, and the right way to make this pass is to edit the
        addendum and this line together -- not to loosen the assertion."""
        counts = {}
        for verdict in mc.verdicts(mc.load_key()).values():
            counts[verdict] = counts.get(verdict, 0) + 1
        self.assertEqual(sum(counts.values()), 55)
        self.assertEqual(counts.get("good", 0) + counts.get("undecided", 0),
                         30, f"addendum:54-56 says 30 good; derived {counts}")
        self.assertEqual(counts.get("bad", 0), 25,
                         f"addendum:55 says 25 bad; derived {counts}")

    def test_the_shipped_key_records_the_postings_it_answers(self):
        """postings_sha256 is what makes "which corpus is this a key to" a
        check rather than a guess. Reported rather than enforced by load_key
        -- see postings_sha256()."""
        with open(mc.KEY_PATH, encoding="utf-8") as fh:
            raw = json.load(fh)
        self.assertEqual(raw["postings_sha256"], mc.postings_sha256())
        self.assertEqual(os.path.basename(raw["postings_file"]),
                         os.path.basename(mc.POSTINGS_PATH))

    def test_the_shipped_loader_block_agrees_with_this_modules_own_mapping(self):
        """THE REASON THE LOADER BLOCK IS WORTH KEEPING AT ALL.

        Every other test here treats the key as the expected answer. This one
        inverts it: agent A read the same location strings independently, so a
        mismatch means `_location_flags()` and a careful human disagree about
        what "Long Island City, NY" is.

        That matters beyond this fixture. `location_is_nyc` and
        `location_is_remote` reach score_job through match.py:275-288 and price
        config/criteria.json's `location` block on EVERY row in production.
        They are computed once at ingest and never re-derived, so a wrong
        mapping is permanent and silent -- there is no other check on them in
        this repo. Failures are printed as pairs, never merged.

        THREE DISAGREEMENTS ARE EXPECTED AND FROZEN HERE. Agent A recorded
        them deliberately, and they are the same three this file already pins
        from the other direction in
        test_the_nyc_heuristics_own_misses_are_kept_rather_than_corrected:
        NYC_PATTERN (lib/text.py:25-28) lists the five borough names and "new
        york" but no neighbourhoods, so Long Island City (mock_022, mock_030)
        and Astoria (mock_028) compute False while being in Queens.

        Two independent readers arriving at the same three is what makes this
        a finding rather than a typo, and it is NOT confined to the fixture:
        the same expression runs at ingest on every real posting, so any
        production row whose location names a neighbourhood instead of a
        borough is priced by config/criteria.json's `location` block as though
        it were out of area. Frozen rather than fixed -- lib/ is vendored
        byte-identical (`git show 87bbff5:tools/lib-parity.sh`, deleted when
        the other repo link was cut) and widening the pattern is a
        corpus-wide re-ranking, not a test fix."""
        known = {("mock_022", "location_is_nyc"),
                 ("mock_028", "location_is_nyc"),
                 ("mock_030", "location_is_nyc")}
        rows = mc.loader_disagreements(mc.load_key())
        seen = {(r["job_id"], r["field"]) for r in rows}
        self.assertEqual(
            seen - known, set(),
            "a disagreement nobody recorded: "
            + "; ".join(f"{r['job_id']}.{r['field']} derived={r['derived']!r} "
                        f"key={r['key']!r} note={r['note']!r}"
                        for r in rows if (r["job_id"], r["field"]) not in known))
        self.assertEqual(known - seen, set(),
                         "a recorded disagreement stopped happening -- if "
                         "NYC_PATTERN was widened, this test and the addendum "
                         "both need editing, not deleting")
        # Direction matters more than count. The loader UNDER-reports NYC and
        # never over-reports it: a False where the truth is True loses a
        # genuine cohort posting, which is recoverable by widening the pattern.
        # A True where the truth is False would surface an out-of-area job as
        # local, and nothing downstream would question it.
        for row in rows:
            self.assertFalse(row["derived"])
            self.assertTrue(row["key"])

    def test_the_shipped_key_carries_a_loader_block_on_every_entry(self):
        """Both location columns, on all 55. A block present on some entries
        and not others would make the backwards check above cover whichever
        subset somebody got to."""
        key = mc.load_key()
        self.assertEqual(mc.loader_fields(key),
                         {"location_is_nyc", "location_is_remote"})
        for job_id, entry in sorted(key.items()):
            self.assertEqual(set(entry["loader_fields"]),
                             {"location_is_nyc", "location_is_remote"},
                             job_id)

    def test_no_extraction_field_of_the_shipped_key_is_a_loader_field(self):
        """The disjointness that keeps agent C's denominators honest, asserted
        on the file that actually ships rather than only on fixtures."""
        key = mc.load_key()
        extraction = mc.extraction_fields(key)
        loader = mc.loader_fields(key)
        self.assertEqual(extraction & loader, set())
        self.assertTrue(extraction <= set(mc.FACT_FIELDS))
        self.assertTrue(loader <= set(mc.LOADER_FIELDS))

    def test_every_extraction_field_reports_its_own_denominator(self):
        """A per-field accuracy figure is uninterpretable without its n. The
        key answers `years_experience_min` null on most postings, so its
        denominator is a fraction of 55 and a percentage printed as though it
        were 55 would read a two-posting difference as four points."""
        counts = mc.measurable_counts(mc.load_key())
        self.assertEqual(set(counts), mc.extraction_fields(mc.load_key()))
        for field, n in sorted(counts.items()):
            self.assertLessEqual(n, 55, field)
            self.assertGreater(n, 0,
                               f"{field} is answered null on all 55 postings; "
                               f"it cannot be measured and should not be in "
                               f"the key")

    def test_the_addendum_this_module_cites_is_on_disk(self):
        self.assertTrue(os.path.exists(mc.ADDENDUM_PATH))
        self.assertTrue(os.path.exists(mc.POSTINGS_PATH))


# --------------------------------------------------------------------------
# Containment
# --------------------------------------------------------------------------

class TestNothingCanPullThisIntoProduction(unittest.TestCase):

    def _source(self):
        with open(mc.__file__.replace(".pyc", ".py"), encoding="utf-8") as fh:
            return fh.read()

    def test_the_module_calls_no_model(self):
        """The same grep tests/test_labels.py:423-429 runs against labels.py.
        This module lives in the same package and is a SPECIFICATION FIXTURE:
        a path from a model's output into this file would make the answer key
        a record of what a model said, which is the defect that test names."""
        source = self._source()
        for forbidden in ("llm.call", "call_detailed", "import llm"):
            self.assertNotIn(forbidden, source,
                             "mock_corpus.py must have no path from a model "
                             "into the answer key")

    def test_the_module_imports_nothing_that_opens_a_socket_or_a_database(self):
        """An AST scan of this module's own imports, not a substring search:
        the point is what it can reach at import time, and psycopg / urllib /
        requests are each one line away from turning an offline fixture into
        something that needs a network or a DATABASE_URL."""
        tree = ast.parse(self._source())
        imported = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(a.name.split(".")[0] for a in node.names)
            elif isinstance(node, ast.ImportFrom) and node.level == 0:
                imported.add((node.module or "").split(".")[0])
        for forbidden in ("llm", "socket", "psycopg", "urllib", "requests",
                          "http", "dbconn", "ssl"):
            self.assertNotIn(forbidden, imported)

    def test_the_module_opens_no_connection(self):
        """No .connect( and no .execute( anywhere in the source. schema is
        imported for COLUMNS and make_job_id; calling into its DDL helpers
        would make a pure loader a writer."""
        source = self._source()
        for forbidden in (".connect(", ".execute(", "ensure_schema"):
            self.assertNotIn(forbidden, source)

    def test_no_ingest_module_references_the_mock_corpus(self):
        """The containment guarantee. `ingest/` is what run-daily.py runs; a
        reference from there is the only way these 55 synthetic postings could
        reach the production `jobs` table."""
        ingest = os.path.join(BACKEND, "ingest")
        for name in sorted(os.listdir(ingest)):
            if not name.endswith(".py"):
                continue
            with open(os.path.join(ingest, name), encoding="utf-8") as fh:
                self.assertNotIn("mock_corpus", fh.read(), f"ingest/{name}")

    def test_no_step_in_the_nightly_run_references_the_mock_corpus(self):
        """run-daily.py:113 STEPS is the nightly schedule. Nothing named here
        may reach this module, and the check is against the source rather
        than an import because run-daily.py is a script, not a module."""
        with open(os.path.join(BACKEND, "run-daily.py"), encoding="utf-8") as fh:
            source = fh.read()
        self.assertNotIn("mock_corpus", source)
        self.assertNotIn("mock-postings", source)

    def test_the_module_says_plainly_that_it_is_not_a_label(self):
        """`git show 11f0fd0:docs/tasks/refactor/HANDOFF.md:805-808` -- fixtures written from a specification test
        the specification. The caveat has to travel with the module, because
        the number it produces will outlive the conversation that made it."""
        doc = mc.__doc__
        self.assertIn("SPECIFICATION FIXTURE", doc)
        self.assertIn("eval_labels", doc)
        self.assertIn("HANDOFF.md:805-808", doc)


if __name__ == "__main__":
    unittest.main()

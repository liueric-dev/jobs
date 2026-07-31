"""The six non-LLM fetchers, replayed against real recorded upstream bytes.

WHAT MAKES THIS DIFFERENT FROM THE TESTS ALREADY HERE

`tests/test_upsert_checked.py:20-24` says it plainly: the ingest scripts
"cannot be imported (five of six have hyphens in their filenames)", so it
tests the TableSpec each script writes through, and notes that "the fetch and
parse halves are task 09's cassette harness, and these become cassette-backed
there." This is that. `evals/ingest_modules.py` imports them by path, and
every assertion below runs the script's OWN fetch and normalize functions
over bytes the real endpoint really sent -- no hand-written sample payloads,
because the audit defects (`docs/ingest/DEFECTS.md`) live in shapes nobody
would think to write down.

THE CONTRACT EVERY SOURCE OWES. `schema.py:118-120`: "Every normalize_*
function must supply every key here: upsert binds them as named parameters,
so a missing one fails that record." That is asserted once, for all six, in
`assert_normalizes`. It is the cheapest possible regression net for the seven
new ingest scripts Phase 3 adds from these templates.

PROVENANCE IS PRINTED, NOT ASSUMED. Each cassette's recording date is printed
once per run. A fixture recorded in July is the specification in December
whether anyone meant it to be or not; the least this can do is say how old it
is out loud.

OFFLINE. Every test here replays. `cassettes.CassetteMiss` is fatal, so a
request this suite does not have recorded fails rather than silently going
back to the network.
"""

import json
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import schema                                                 # noqa: E402
from evals import cassettes                                   # noqa: E402
from evals.ingest_modules import load as load_ingest          # noqa: E402

_ANNOUNCED = set()


def announce(name):
    """Print a cassette's provenance once per process. See PROVENANCE."""
    if name not in _ANNOUNCED:
        _ANNOUNCED.add(name)
        print("  " + cassettes.Cassette.load(name).provenance_line())


def replaying(name):
    announce(name)
    return cassettes.replay(name)


def require(name):
    return unittest.skipUnless(
        cassettes.available(name),
        f"cassette {name} not recorded -- `python3 evals/record_cassettes.py "
        f"{name}`")


class NormalizerContract(unittest.TestCase):
    """Shared assertions. Every source's records must satisfy these."""

    def assert_normalizes(self, records, *, platform, minimum=1):
        self.assertGreaterEqual(len(records), minimum,
                                f"{platform}: cassette produced no records")
        for rec in records:
            missing = [c for c in schema.COLUMNS if c not in rec]
            self.assertEqual(missing, [],
                             f"{platform}: record is missing {missing}, which "
                             f"upsert binds by name (schema.py:118)")
            self.assertEqual(rec["platform"], platform)
            self.assertTrue(rec["title"], f"{platform}: untitled record")
            self.assertTrue(rec["source_id"], f"{platform}: no source_id")
            # make_job_id is the primary key and is a frozen expression
            # (schema.py:239). A normalizer that produced an unusable id
            # would fail per-record inside upsert, where it is one line of a
            # summary rather than a test failure.
            self.assertTrue(schema.make_job_id(rec))

    def assert_ids_unique(self, records, platform):
        ids = [schema.make_job_id(r) for r in records]
        self.assertEqual(len(ids), len(set(ids)),
                         f"{platform}: two records share a primary key, so "
                         f"one silently overwrites the other")


# ---------------------------------------------------------------------------
# ats.py -- three platforms, three cassettes
# ---------------------------------------------------------------------------

class TestATS(NormalizerContract):

    @classmethod
    def setUpClass(cls):
        cls.ats = load_ingest("ats")

    @require("ats-greenhouse")
    def test_greenhouse_fetch_and_normalize(self):
        company = {"token": "kickstarter", "name": "Kickstarter",
                   "is_nyc_hq": True, "is_ai_focused": False}
        with replaying("ats-greenhouse"):
            jobs = self.ats.fetch_greenhouse("kickstarter")
        records = [self.ats.normalize_greenhouse(company, j) for j in jobs]
        self.assert_normalizes(records, platform="greenhouse")
        self.assert_ids_unique(records, "greenhouse")

    @require("ats-greenhouse")
    def test_greenhouse_descriptions_are_unescaped_twice(self):
        """ats.py:169-194, against the bytes the measurement was made on.

        Greenhouse serves HTML that has been escaped once, so a single
        unescape leaves `&nbsp;` in the stored text -- 7,182 rows of it, in
        production. The docstring quotes 0/300 rows holding literal entities
        after the double unescape; this asserts the same property on a live
        recording, which is the part that can rot when Greenhouse changes
        its encoding.
        """
        with replaying("ats-greenhouse"):
            jobs = self.ats.fetch_greenhouse("kickstarter")
        described = 0
        for job in jobs:
            raw = job.get("content")
            if not raw:
                continue
            described += 1
            self.assertIn("&lt;", raw,
                          "the recording no longer shows escaped HTML -- "
                          "re-read ats.py:169-194 before trusting it")
            plain = self.ats.greenhouse_description(raw)
            for entity in ("&lt;", "&gt;", "&nbsp;", "&amp;", "&quot;"):
                self.assertNotIn(entity, plain,
                                 f"{entity} survived greenhouse_description()")
        self.assertGreater(described, 0, "no posting carried a description")

    @require("ats-greenhouse-no-content")
    def test_a_payload_with_no_content_field_loses_descriptions_silently(self):
        """The third awkward response from 05-fetcher-harness.md:73-76.

        Recorded from the same board with `?content=true` dropped, which is
        the real shape ats.py:152 would receive if that parameter were ever
        lost. Nothing raises: every record still normalizes, every column is
        still bound, and `description_text` is None on all of them. So the
        whole board's descriptions become NULL and the run reports success --
        which is why the fixture is worth having and why the assertion below
        is about the count of Nones rather than about an exception.

        The fetch is spelled out here rather than going through
        `fetch_greenhouse`, because fetch_greenhouse always appends
        `?content=true` and would therefore MISS this cassette -- correctly.
        The parser under test is `normalize_greenhouse`, and that is the real
        one.
        """
        from lib import http
        company = {"token": "kickstarter", "name": "Kickstarter",
                   "is_nyc_hq": True, "is_ai_focused": False}
        with replaying("ats-greenhouse-no-content"):
            jobs = http.get_json(
                "https://api.greenhouse.io/v1/boards/kickstarter/jobs"
            ).get("jobs", [])
        self.assertTrue(jobs)
        self.assertTrue(all("content" not in j for j in jobs),
                        "this cassette is supposed to be the no-content shape")
        records = [self.ats.normalize_greenhouse(company, j) for j in jobs]
        self.assert_normalizes(records, platform="greenhouse")
        self.assertTrue(all(r["description_text"] is None for r in records))

    @require("ats-lever")
    def test_lever_fetch_and_normalize(self):
        company = {"token": "finix", "name": "Finix",
                   "is_nyc_hq": False, "is_ai_focused": False}
        with replaying("ats-lever"):
            jobs = self.ats.fetch_lever("finix")
        records = [self.ats.normalize_lever(company, j) for j in jobs]
        self.assert_normalizes(records, platform="lever")
        self.assert_ids_unique(records, "lever")
        # ats.py:261: Lever serves real HTML, so ONE unescape is correct here
        # and passing unescape=False was leaving `&amp;` in the stored text.
        for rec in records:
            if rec["description_text"]:
                self.assertNotIn("&amp;", rec["description_text"])

    @require("ats-ashby")
    def test_ashby_fetch_and_normalize(self):
        company = {"token": "runway", "name": "Runway",
                   "is_nyc_hq": True, "is_ai_focused": True}
        with replaying("ats-ashby"):
            jobs = self.ats.fetch_ashby("runway")
        records = [self.ats.normalize_ashby(company, j) for j in jobs]
        self.assert_normalizes(records, platform="ashby")
        self.assert_ids_unique(records, "ashby")

    @require("ats-greenhouse")
    def test_a_fetch_this_cassette_does_not_hold_is_not_a_live_call(self):
        """The property the whole harness rests on."""
        with replaying("ats-greenhouse"):
            with self.assertRaises(cassettes.CassetteMiss):
                self.ats.fetch_greenhouse("some-other-company")


# ---------------------------------------------------------------------------
# hn-hiring.py
# ---------------------------------------------------------------------------

class TestHNHiring(NormalizerContract):

    @classmethod
    def setUpClass(cls):
        cls.hn = load_ingest("hn-hiring")

    @require("hn-hiring")
    def test_thread_discovery_walks_past_the_other_monthly_threads(self):
        """find_latest_hiring_thread scans `submitted` rather than assuming a
        fixed offset, because whoishiring posts three threads a month
        (hn-hiring.py:211-214). The cassette holds the real user object, so
        this asserts against the real interleaving."""
        with replaying("hn-hiring"):
            thread = self.hn.find_latest_hiring_thread()
        self.assertIsNotNone(thread)
        self.assertEqual(thread["type"], "story")
        self.assertTrue(thread["title"].lower().startswith(
            self.hn.HIRING_TITLE_PREFIX))
        self.assertTrue(thread.get("kids"))

    @require("hn-hiring")
    def test_comments_parse_into_complete_records(self):
        with replaying("hn-hiring") as player:
            thread = self.hn.find_latest_hiring_thread()
            comments = [self.hn.http.get_json(
                f"{self.hn.HN_API_BASE}/item/{kid}.json")
                for kid in thread["kids"][:10]]
        records = [r for r in
                   (self.hn.parse_comment(c, thread["id"]) for c in comments)
                   if r]
        self.assert_normalizes(records, platform="hn_whoishiring")
        self.assert_ids_unique(records, "hn_whoishiring")
        self.assertTrue(player.requests)

    @require("hn-hiring")
    def test_a_null_item_replays_as_None(self):
        """Audit item 5 / D23's neighbour: `if not comment: continue` at
        hn-hiring.py:409-412 returns BEFORE the ledger insert, so an id that
        answers `null` is re-fetched every run for the life of the thread.

        This pins the INPUT, which is the half that could not be written by
        hand: HN answers a nonexistent id with the four bytes `null`, which
        json-decodes to None and is indistinguishable from a fetch that
        returned nothing. The fix belongs to whoever closes the defect; the
        fixture is what lets them test it.
        """
        with replaying("hn-hiring"):
            item = self.hn.http.get_json(
                f"{self.hn.HN_API_BASE}/item/99999999999.json")
        self.assertIsNone(item)
        self.assertFalse(item, "the `if not comment` guard must fire on it")


# ---------------------------------------------------------------------------
# weworkremotely.py
# ---------------------------------------------------------------------------

class TestWeWorkRemotely(NormalizerContract):

    @classmethod
    def setUpClass(cls):
        cls.wwr = load_ingest("weworkremotely")

    @require("wwr-feeds")
    def test_feeds_parse_into_complete_records(self):
        with replaying("wwr-feeds"):
            records = []
            for cat in ("remote-back-end-programming-jobs",
                        "remote-full-stack-programming-jobs"):
                records.extend(self.wwr.parse_feed(self.wwr.fetch_feed(cat), cat))
        self.assert_normalizes(records, platform="weworkremotely")
        # Every WWR posting is remote by definition (weworkremotely.py:44-49).
        self.assertTrue(all(r["location_is_remote"] for r in records))

    @require("wwr-feeds")
    def test_cross_listed_postings_deduplicate(self):
        """weworkremotely.py:206-211 keys on (company_token, source_id)
        because the same posting appears under more than one category. Two
        feeds were recorded so this has something to prove."""
        with replaying("wwr-feeds"):
            per_feed = {cat: self.wwr.parse_feed(self.wwr.fetch_feed(cat), cat)
                        for cat in ("remote-back-end-programming-jobs",
                                    "remote-full-stack-programming-jobs")}
        seen, deduped = set(), []
        for records in per_feed.values():
            for rec in records:
                key = (rec["company_token"], rec["source_id"])
                if key not in seen:
                    seen.add(key)
                    deduped.append(rec)
        total = sum(len(r) for r in per_feed.values())
        self.assertEqual(len(deduped), len(seen))
        self.assertLessEqual(len(deduped), total)
        self.assert_ids_unique(deduped, "weworkremotely")

    @require("wwr-feeds")
    def test_the_non_tech_blocklist_actually_fires(self):
        """The NOISE WARNING at weworkremotely.py:25-34 is a claim about live
        data: category tags are self-selected, so customer-support postings
        show up under Full-Stack Programming. If the blocklist stops matching
        anything, either WWR cleaned up or the pattern rotted -- and either
        way somebody should look."""
        with replaying("wwr-feeds"):
            raw = self.wwr.fetch_feed("remote-back-end-programming-jobs")
        import xml.etree.ElementTree as ET
        titles = [(item.findtext("title") or "")
                  for item in ET.fromstring(raw).iter("item")]
        self.assertTrue(titles, "the feed recorded no items at all")
        blocked = [t for t in titles
                   if self.wwr.NON_TECH_EXCLUDE_PATTERN.search(t)]
        parsed = self.wwr.parse_feed(raw, "remote-back-end-programming-jobs")
        for rec in parsed:
            self.assertIsNone(
                self.wwr.NON_TECH_EXCLUDE_PATTERN.search(rec["title"]),
                f"blocked title survived parse_feed: {rec['title']!r}")
        if not blocked:
            self.skipTest("no mistagged titles in this recording -- the "
                          "blocklist is untested by these bytes")


# ---------------------------------------------------------------------------
# builtin-nyc.py
# ---------------------------------------------------------------------------

class TestBuiltInNYC(NormalizerContract):

    @classmethod
    def setUpClass(cls):
        cls.builtin = load_ingest("builtin-nyc")

    @require("builtin-nyc")
    def test_listing_page_parses_into_complete_records(self):
        with replaying("builtin-nyc"):
            page = self.builtin.fetch_page(1)
        records = self.builtin.parse_page(page)
        self.assert_normalizes(records, platform="builtin")
        self.assert_ids_unique(records, "builtin")

    @require("builtin-nyc")
    def test_titles_and_companies_line_up(self):
        """D02: `parse_page` zips independently-matched title and company
        lists, so one card missing a company anchor shifts every later row by
        one -- silently, with a plausible-looking wrong employer on each.

        Cheap invariant over real bytes: every parsed record has both, and
        the company count matches the title count on the recorded page. When
        D02 is fixed this test is where the misaligned fixture goes.
        """
        with replaying("builtin-nyc"):
            page = self.builtin.fetch_page(1)
        titles = self.builtin.TITLE_PATTERN.findall(page)
        companies = self.builtin.COMPANY_PATTERN.findall(page)
        self.assertEqual(
            len(titles), len(companies),
            "title and company counts diverge on the recorded page -- this is "
            "the exact condition D02 misattributes under")
        for rec in self.builtin.parse_page(page):
            self.assertTrue(rec["company_name"])
            self.assertTrue(rec["title"])

    @require("builtin-nyc")
    def test_salaries_are_shaped_like_salaries(self):
        """D03: SALARY_PATTERN is unscoped, so any `NNK-NNK` anywhere on the
        card can be captured. Asserted over real bytes rather than argued."""
        with replaying("builtin-nyc"):
            page = self.builtin.fetch_page(1)
        for rec in self.builtin.parse_page(page):
            salary = rec.get("salary_text")
            if salary:
                self.assertRegex(salary, r"^\d{1,3}K-\d{1,3}K")

    @require("builtin-nyc")
    def test_detail_page_yields_a_description(self):
        """builtin-nyc.py:153-156: the ld+json MIME type is HTML-escaped on
        these pages (`application/ld&#x2B;json`), so the conventional
        `ld\\+json` selector matches nothing -- "exactly how the description
        went missing: silently, with no error". The recorded detail page is
        the only way to keep that true."""
        with replaying("builtin-nyc"):
            page = self.builtin.fetch_page(1)
            first = self.builtin.parse_page(page)[0]
            description = self.builtin.fetch_description(first["job_url"])
        self.assertTrue(description,
                        "no description parsed out of the recorded detail page")
        self.assertNotIn("<", description, "markup survived into the text")


# ---------------------------------------------------------------------------
# google-serpapi.py
# ---------------------------------------------------------------------------

class TestGoogleSerpApi(NormalizerContract):

    @classmethod
    def setUpClass(cls):
        cls.serp = load_ingest("google-serpapi")

    @require("google-serpapi")
    def test_search_and_normalize(self):
        with replaying("google-serpapi"):
            results = self.serp.serpapi_search(
                "AI engineer", "New York, New York, United States",
                date_chip="week")
        from google_jobs import normalize_job
        records = [normalize_job(j, "nyc") for j in results]
        self.assert_normalizes(records, platform="google_jobs")
        self.assert_ids_unique(records, "google_jobs")

    @require("google-serpapi")
    def test_the_recording_replays_under_any_api_key(self):
        """The credential is not part of the cache key -- rotating it must
        not discard the corpus (`docs/ingestion_tests/README.md:86-87`)."""
        original = self.serp.SERPAPI_API_KEY
        try:
            self.serp.SERPAPI_API_KEY = "a-completely-different-key"
            with replaying("google-serpapi"):
                results = self.serp.serpapi_search(
                    "AI engineer", "New York, New York, United States",
                    date_chip="week")
            self.assertTrue(results)
        finally:
            self.serp.SERPAPI_API_KEY = original


# ---------------------------------------------------------------------------
# google-apify.py
# ---------------------------------------------------------------------------

def _immediate_success(cassette):
    """The recorded run, with a start POST that already says SUCCEEDED.

    DERIVED IN CODE, NOT COMMITTED AS A SECOND FILE. Apify's start endpoint
    and its run endpoint return the same `{"data": {...}}` run resource, so
    the awkward case -- a run that finished before the first poll -- is the
    recorded run object served as the start response. Committing that as its
    own cassette would be committing a copy that silently stops matching the
    recording it came from the first time either is re-recorded.

    This is `apify-immediate-success.json` from
    `05-fetcher-harness.md:68`, built rather than stored.
    """
    from evals.cassettes import Cassette, Interaction
    run = next(i for i in cassette.interactions if "/actor-runs/" in i.url)
    start = Interaction(
        method="POST",
        url="https://api.apify.com/v2/acts/"
            "johnvc~google-jobs-scraper---pay-per-result/runs?token=REDACTED",
        status=201, headers={"Content-Type": "application/json"},
        body=run.body)
    return Cassette(name=cassette.name + "+immediate-success",
                    source=cassette.source, recorded_at=cassette.recorded_at,
                    note="derived: the recorded SUCCEEDED run served as the "
                         "start response",
                    interactions=[start, *cassette.interactions])


class TestGoogleApify(NormalizerContract):

    @classmethod
    def setUpClass(cls):
        cls.apify = load_ingest("google-apify")

    @require("google-apify")
    def test_dataset_items_normalize(self):
        with replaying("google-apify") as player:
            run = self.apify.http.get_json(player.cassette.interactions[0].url)
            items = self.apify.http.get_json(
                f"https://api.apify.com/v2/datasets/"
                f"{run['data']['defaultDatasetId']}/items?token=x")
        from google_jobs import normalize_job
        records = [normalize_job(j, "nyc") for j in items]
        self.assert_normalizes(records, platform="google_jobs")
        self.assert_ids_unique(records, "google_jobs")

    @require("google-apify")
    def test_an_immediately_successful_run_returns_its_dataset(self):
        """Audit item 1 / D17 -- FIXED 2026-07-31, and this is the flip.

        `run_actor_query` used to bind `run` only inside the `while` body. A
        start response that is already SUCCEEDED skips the loop entirely,
        passes the `status != "SUCCEEDED"` check, and then read
        `run["data"]["defaultDatasetId"]` -- a name that was never assigned.
        The result was a paid actor run whose results are never collected,
        reported as one failed query among many.

        The previous version of this test asserted the UnboundLocalError on
        purpose, as the reproduction `DEFECTS.md` D17 said was blocked on this
        harness. `run = start` before the loop is the whole fix; this asserts
        the rows instead, which is what the assertion was left here to become.

        The cassette is unchanged -- `_immediate_success()` rewrites the start
        response's status, so the same recorded bytes drive both the old
        failure and the new success.
        """
        announce("google-apify")
        cassette = _immediate_success(cassettes.Cassette.load("google-apify"))
        with cassettes.replay(cassette=cassette):
            items = self.apify.run_actor_query("AI engineer", "New York")
        self.assertTrue(items, "an immediately-SUCCEEDED run returned no items")
        records = [self.apify.normalize_job(j, "nyc") for j in items]
        self.assert_normalizes(records, platform="google_jobs")


if __name__ == "__main__":
    unittest.main()

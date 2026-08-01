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
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import schema                                                 # noqa: E402
from evals import cassettes, scratchdb                        # noqa: E402
from evals.ingest_modules import load as load_ingest          # noqa: E402
from lib import envfile                                       # noqa: E402
from lib.upsert import upsert_checked                         # noqa: E402

#: The pipeline's own .env, the way run-daily.py loads it. Same reason
#: tests/test_nyc_open_data.py:52-55 does it: the DB-backed test below must
#: not depend on the caller having exported DATABASE_URL by hand.
envfile.load(os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), ".env"))

#: Fixtures that are not cassettes -- a shape a recording cannot express.
#: See evals/fixtures/builtin-nyc-desync.html's own header for why it exists
#: and why it is not a re-recording.
FIXTURE_DIR = os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "evals", "fixtures")

requires_db = unittest.skipUnless(
    scratchdb.available(),
    "no scratch database: set DATABASE_URL (or JOBS_SCRATCH_DATABASE_URL)")

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

    # -- D23: the ledger/upsert crash window ---------------------------------
    #
    # Both tests below drive the REAL read_comments() over the REAL recorded
    # bytes into a REAL Postgres schema, and differ only in whether the
    # transaction is committed or lost. A process that dies mid-run does not
    # get to run cleanup code -- the server rolls its open transaction back --
    # so `conn.rollback()` after read_comments() is exactly the crash, and
    # calling upsert_checked() is exactly the survival. Nothing is simulated
    # except the moment of death.

    def _recorded_kids(self, thread):
        """The comment ids this cassette actually holds, in thread order.

        The thread lists far more kids than were recorded, and a request the
        cassette does not hold is fatal by design (CassetteMiss), so the ids
        are intersected with the recording rather than truncated to a count
        that would break the day the cassette gains an interaction.
        """
        recorded = {i.url.rsplit("/", 1)[-1].removesuffix(".json")
                    for i in cassettes.Cassette.load("hn-hiring").interactions}
        return [k for k in thread["kids"] if str(k) in recorded]

    @require("hn-hiring")
    @requires_db
    def test_a_crash_before_the_upsert_leaves_no_comment_marked_seen(self):
        """D23. The ledger gates re-fetching, so a comment marked seen with no
        `jobs` row is stranded for the life of the thread -- `--reparse` is the
        only thing that recovers it, and nothing tells anyone to run it.

        read_comments() commits nothing; a crash between it and the upsert
        must therefore lose the ledger inserts too, so the next ordinary run
        re-fetches those comments and writes the rows.
        """
        with scratchdb.scratch_schema() as (conn, _name):
            with replaying("hn-hiring"):
                thread = self.hn.find_latest_hiring_thread()
                kids = self._recorded_kids(thread)
                records, _declined, _errs, _null = self.hn.read_comments(
                    conn, thread["id"], kids, "2026-08-01T00:00:00")
            self.assertTrue(records, "the recording parsed into no records")
            seen_before = conn.execute(
                "SELECT count(*) FROM hn_seen_comments").fetchone()[0]
            self.assertEqual(seen_before, len(kids),
                             "read_comments must mark every fetched comment "
                             "seen -- within its caller's transaction")

            conn.rollback()          # the crash

            self.assertEqual(
                conn.execute(
                    "SELECT count(*) FROM hn_seen_comments").fetchone()[0], 0,
                "comments are marked seen but hold no jobs row: the ledger "
                "gates re-fetching, so every one of them is stranded")
            self.assertEqual(
                conn.execute(f"SELECT count(*) FROM {schema.TABLE} "
                             f"WHERE platform = 'hn_whoishiring'").fetchone()[0],
                0)

    @require("hn-hiring")
    @requires_db
    def test_the_ledger_and_the_jobs_rows_land_in_one_commit(self):
        """The other half of D23: atomic means both, not neither.

        Deferring the ledger commit would be a bad fix if it also deferred the
        ledger -- the point is that the ordinary path still writes it, in the
        same transaction as the rows it is a ledger OF.
        """
        with scratchdb.scratch_schema() as (conn, _name):
            with replaying("hn-hiring"):
                thread = self.hn.find_latest_hiring_thread()
                kids = self._recorded_kids(thread)
                records, _declined, _errs, _null = self.hn.read_comments(
                    conn, thread["id"], kids, "2026-08-01T00:00:00")
            upsert_checked(conn, schema.spec(schema.HASH_FIELDS_SHORT),
                           records, schema.make_job_id, logger=lambda _l: None)
            conn.rollback()   # anything uncommitted at this point was lost

            self.assertEqual(
                conn.execute(
                    "SELECT count(*) FROM hn_seen_comments").fetchone()[0],
                len(kids))
            self.assertEqual(
                conn.execute(f"SELECT count(*) FROM {schema.TABLE} "
                             f"WHERE platform = 'hn_whoishiring'").fetchone()[0],
                len(records))


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

    # -- D05: every dropped item is counted ----------------------------------

    def _parse_both_feeds(self, stats):
        with replaying("wwr-feeds"):
            return [rec
                    for cat in ("remote-back-end-programming-jobs",
                                "remote-full-stack-programming-jobs")
                    for rec in self.wwr.parse_feed(
                        self.wwr.fetch_feed(cat), cat, stats)]

    @require("wwr-feeds")
    def test_every_item_the_feed_offered_is_either_a_record_or_a_counter(self):
        """D05. The conservation law, over the real recorded feeds.

        The summary used to print `len(all_records)` and nothing else, so an
        exclude-pattern edit that started eating real engineering titles
        "would produce no signal at all" (weworkremotely.md:309-312). The
        counters make the difference between items offered and rows produced
        add up -- which is the only thing that can turn that edit into a
        number somebody sees.
        """
        import xml.etree.ElementTree as ET
        stats = Counter()
        records = self._parse_both_feeds(stats)
        with replaying("wwr-feeds"):
            offered = sum(
                len(list(ET.fromstring(self.wwr.fetch_feed(cat)).iter("item")))
                for cat in ("remote-back-end-programming-jobs",
                            "remote-full-stack-programming-jobs"))
        dropped = sum(stats[r] for r in self.wwr.DROP_REASONS)
        self.assertGreater(dropped, 0,
                           "this recording drops nothing, so it cannot show "
                           "that drops are counted")
        self.assertEqual(len(records) + dropped, offered,
                         f"{offered} items in, {len(records)} records out, "
                         f"{dropped} accounted for -- the difference is the "
                         f"silence D05 is about")

    @require("wwr-feeds")
    def test_the_blocklist_drop_is_counted_under_its_own_name(self):
        """Named counters, not one total. An exclude-pattern regression shows
        up in `non_tech_excluded` and nowhere else; a feed that started
        omitting `<link>` shows up in `no_source_id`. One number could not
        tell those apart, and they need opposite responses."""
        stats = Counter()
        self._parse_both_feeds(stats)
        self.assertGreater(stats["non_tech_excluded"], 0)
        self.assertEqual(
            sorted(k for k in stats if stats[k]), ["non_tech_excluded"],
            f"this recording is supposed to exercise exactly one drop "
            f"reason; it now shows {dict(stats)}")

    @require("wwr-feeds")
    def test_a_cross_listed_duplicate_is_counted_apart_from_a_drop(self):
        """The fifth `continue`, and deliberately NOT a drop.

        Deduping a posting that WWR published under two categories is a
        correct outcome, and it is normally nonzero -- so adding it to the
        dropped total would give that total a large noisy floor for a real
        regression to hide inside. Counted, reported, kept separate.
        """
        stats = Counter()
        records = self._parse_both_feeds(stats)
        seen, kept = set(), []
        for rec in records:                     # main()'s dedup, same keying
            key = (rec["company_token"], rec["source_id"])
            if key in seen:
                stats["cross_listed"] += 1
                continue
            seen.add(key)
            kept.append(rec)
        self.assertGreater(stats["cross_listed"], 0,
                           "two feeds were recorded so this has something to "
                           "prove (weworkremotely.py:211-215)")
        self.assertNotIn("cross_listed", self.wwr.DROP_REASONS)
        self.assertEqual(len(kept) + stats["cross_listed"], len(records))


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
        """D02 -- FIXED, and this is the half the recorded page can prove.

        `parse_page` used to zip independently-matched title and company
        lists positionally. The recorded page holds 23 titles and 23 anchors
        interleaved one for one, so it cannot show the misattribution -- the
        desync fixture below is what does. What this page CAN show is that
        containment did not change the answer on well-formed markup, which is
        the regression the fix could plausibly have caused.
        """
        with replaying("builtin-nyc"):
            page = self.builtin.fetch_page(1)
        titles = self.builtin.TITLE_PATTERN.findall(page)
        companies = self.builtin.COMPANY_PATTERN.findall(page)
        self.assertEqual(
            len(titles), len(companies),
            "title and company counts diverge on the recorded page -- this is "
            "the exact condition D02 misattributed under")
        stats = Counter()
        records = self.builtin.parse_page(page, stats)
        self.assertEqual(len(records), len(titles))
        self.assertEqual(dict(stats), {})
        for rec in records:
            self.assertTrue(rec["company_name"])
            self.assertTrue(rec["title"])

    # -- D02: the desync fixture ---------------------------------------------

    def _desync_fixture(self):
        with open(os.path.join(FIXTURE_DIR, "builtin-nyc-desync.html"),
                  encoding="utf-8") as fh:
            return fh.read()

    @require("builtin-nyc")
    def test_the_desync_fixture_is_still_the_recorded_bytes(self):
        """The fixture is a slice of the cassette with one anchor deleted.

        A derived fixture that is allowed to drift from its source is a
        hand-written fixture wearing a provenance note (the failure mode
        `_immediate_success()` avoids by deriving in code). This is the same
        guarantee for a case that cannot be derived in code: everything after
        the deletion is asserted to still be a byte-for-byte substring of the
        recording, so re-recording the cassette breaks this test rather than
        silently leaving a stale copy behind.
        """
        with replaying("builtin-nyc"):
            page = self.builtin.fetch_page(1)
        body = self._desync_fixture().split("-->\n", 1)[1]
        self.assertIn(
            body, page,
            "the fixture is no longer a slice of the recording it documents")
        # The deletion is at the slice's leading edge, which is what makes the
        # remainder contiguous and checkable this cheaply: what the fixture
        # drops is exactly the anchor that ends where the fixture begins.
        self.assertTrue(
            page[:page.index(body)].endswith("<span>PwC</span>"),
            "the fixture no longer starts immediately after the anchor it is "
            "supposed to be missing")

    def test_a_card_with_no_company_anchor_drops_only_itself(self):
        """D02, stated as the property. No network, no cassette: the fixture
        IS the input.

        Under positional pairing this file produced `AI Engineer` at Narmi
        (it is PwC's), `Senior Sales Engineer` at NBCUniversal (it is
        Narmi's), and dropped the fourth card entirely when the shorter list
        ran out -- two employers wrong, one row lost, nothing counted. The
        wrong rows are the dangerous half: a title under a real employer's
        name for a job that employer is not hiring for is indistinguishable
        from a correct row at every point downstream.
        """
        stats = Counter()
        records = self.builtin.parse_page(self._desync_fixture(), stats)
        self.assertEqual(
            [(r["title"], r["company_name"]) for r in records],
            [("Senior Sales Engineer - Commercial Banking", "Narmi"),
             ("Cyber Communications Lead", "NBCUniversal"),
             ("Tech Lead Manager, AI/ML Engineering (East Coast)",
              "NBCUniversal")])
        self.assertEqual(stats["no_company_anchor"], 1,
                         "the card whose anchor is missing must be counted, "
                         "not merely skipped")

    def test_an_anchorless_card_is_dropped_rather_than_misattributed(self):
        """The same fixture, said as conservation: every title on the page is
        either a record or a counted drop, and no record inherits a position.
        """
        fixture = self._desync_fixture()
        stats = Counter()
        records = self.builtin.parse_page(fixture, stats)
        titles = self.builtin.TITLE_PATTERN.findall(fixture)
        self.assertEqual(len(records) + stats["no_company_anchor"],
                         len(titles))
        self.assertNotIn("PwC", [r["company_name"] for r in records],
                         "PwC's anchor was deleted from this fixture, so no "
                         "record may claim it")
        # The card that must go is the one whose anchor is gone, not whichever
        # card happens to be last when a shorter list runs out. Under
        # positional pairing it was the other way round: `AI Engineer`
        # survived under Narmi's name and the final card was dropped instead.
        self.assertNotIn("AI Engineer", [r["title"] for r in records])
        # The token is cut from the anchor's own href, so a record whose name
        # and token disagree took them from two different cards.
        for rec in records:
            self.assertEqual(rec["company_token"],
                             rec["company_name"].lower().replace(" ", "-"))

    # -- D03: the salary element ---------------------------------------------

    @require("builtin-nyc")
    def test_salaries_are_shaped_like_salaries(self):
        """D03. Asserted over real bytes rather than argued."""
        with replaying("builtin-nyc"):
            page = self.builtin.fetch_page(1)
        priced = 0
        for rec in self.builtin.parse_page(page):
            salary = rec.get("salary_text")
            if salary:
                priced += 1
                self.assertRegex(salary, r"^\d{1,3}K-\d{1,3}K")
        # Re-derived, and pinned: scoping the pattern to the salary element
        # must not lose a value the unscoped one found. 20 of 23 on this
        # recording, before and after.
        self.assertEqual(priced, 20)

    @require("builtin-nyc")
    def test_salary_comes_from_the_salary_element_not_from_the_title(self):
        """D03 -- the false positive the recording does not happen to contain.

        `SALARY_PATTERN` used to match `NNK-NNK` ANYWHERE in the card window,
        and the window opens at the title. Built In titles do carry comp
        ("Sales Engineer, 120K-260K OTE"), and a card like that stored the
        title's number as `salary_text` with nothing to say it had not come
        from the salary field -- which is precisely why the register could
        only call the 135 live values "unverified".

        DERIVED IN CODE FROM THE RECORDING, for the reason
        `_immediate_success()` gives: one edit to one card's title text, with
        the disclosed range left exactly where Built In renders it, so the
        two candidate substrings are both real and the test is about which
        one is read.
        """
        with replaying("builtin-nyc"):
            page = self.builtin.fetch_page(1)
        original = self.builtin.parse_page(page)[0]
        self.assertEqual(original["salary_text"], "130K-150K Annually")
        mutated = page.replace(">Executive Assistant to the COO<",
                               ">Sales Engineer, 120K-260K OTE<", 1)
        self.assertNotEqual(mutated, page, "the title text moved -- re-read "
                                           "the cassette before trusting this")
        rec = self.builtin.parse_page(mutated)[0]
        self.assertEqual(rec["title"], "Sales Engineer, 120K-260K OTE")
        self.assertEqual(
            rec["salary_text"], "130K-150K Annually",
            "the title's comp string was stored as the salary -- SALARY_PATTERN "
            "is reading the card, not the fa-sack-dollar element")

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

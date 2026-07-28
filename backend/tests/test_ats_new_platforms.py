"""ingest/ats.py after task 17: six platforms, one roster, one closure call.

WHAT THIS PINS, AND WHY EACH ONE

  * The roster is `company_ats`, and an empty roster is a FAILURE, not a
    quiet night. `ats.py` used to read a 68-entry JSON file that could not be
    empty; a table can be, and "silence is this system's failure mode"
    (CLAUDE.md) means the empty case has to exit non-zero rather than report
    a clean run over nothing.

  * `unvalidated` admits a token. Task 16's fourth status means "we found a
    token and could not check it" -- a 403 at validation time. Excluding it
    would mean a board blocked once is never pulled again, which is the same
    silence one layer up. The choice is data (ats_sources.ADMITTING_STATUSES)
    and is asserted here so it cannot drift into a bare `status = 'valid'`.

  * Workable's widget EXPANDS ONE POSTING PER LOCATION. Measured against the
    committed cassette: 66 entries, 20 distinct shortcodes. Ingested naively
    that is a 3.3x over-count whose extra rows collide on the primary key and
    silently overwrite each other. The dedupe is the only thing standing
    between those two numbers, and this is the test that fails if it goes.

  * A fetch that could not be reconciled never closes anything. Closure here
    is "present yesterday, absent today", which is only sound if today's
    answer is the complete set. `Fetched.complete` is the gate and there is
    exactly ONE call to schema.close_missing() in ats.py -- asserted
    structurally, because "shared rather than copy-pasted per platform" is a
    property of the file, not of any one function.

  * Every request URL is an assertion target, not only every response. That
    Ashby is asked for `includeCompensation=true`, that SmartRecruiters is
    asked for `limit=100`, and that Workable costs exactly two calls are
    claims about what this pipeline SENDS -- the same reason
    evals/cassettes.py exposes `Player.requests`.

No network. Every test replays a committed cassette or builds one in memory.
"""

import json
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import schema                                                 # noqa: E402
from evals import cassettes                                   # noqa: E402
from evals.cassettes import Cassette, Interaction             # noqa: E402
from evals.ingest_modules import load as load_ingest          # noqa: E402

ats = load_ingest("ats")
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "ingest"))
import ats_sources                                            # noqa: E402

INGEST_DIR = os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "ingest")


def require(name):
    return unittest.skipUnless(
        cassettes.available(name),
        f"cassette {name} not recorded -- `python3 evals/record_cassettes.py "
        f"{name}`")


def replaying(name):
    return cassettes.replay(name)


def _cassette(*interactions):
    return Cassette(name="unit", source="unit",
                    recorded_at="2026-07-28T00:00:00Z",
                    interactions=list(interactions))


def _ok(url, payload, *, method="GET"):
    return Interaction(method=method, url=url, status=200,
                       body=json.dumps(payload))


ROSTER = {"platform": "x", "token": "acme", "name": "Acme", "status": "valid"}


class NormalizedRecord(unittest.TestCase):
    """schema.py:118-120 -- every normalize_* must supply every COLUMN."""

    def assert_contract(self, records, platform, minimum=1):
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
            self.assertTrue(rec["job_url"], f"{platform}: no job_url")
            self.assertTrue(schema.make_job_id(rec))
        ids = [schema.make_job_id(r) for r in records]
        self.assertEqual(len(ids), len(set(ids)),
                         f"{platform}: two records share a primary key, so "
                         f"one silently overwrites the other")


# ---------------------------------------------------------------------------
# Workable
# ---------------------------------------------------------------------------

class TestWorkable(NormalizedRecord):

    @require("ats-workable")
    def test_fetch_and_normalize(self):
        with replaying("ats-workable"):
            jobs = ats.fetch_workable("braven")
        records = [ats.normalize_workable(ROSTER, j) for j in jobs]
        self.assert_contract(records, "workable")
        self.assertTrue(any(r["description_text"] for r in records),
                        "the v1 widget is fetched with ?details=true "
                        "precisely so descriptions arrive; none did")

    @require("ats-workable")
    def test_one_posting_per_location_is_deduplicated(self):
        """66 widget entries, 20 distinct shortcodes. Measured 2026-07-28.

        The widget repeats a posting once per location. Without the dedupe in
        fetch_workable() this board ingests as 66 records whose job_url --
        and therefore whose make_job_id -- repeats, so 46 of them overwrite a
        row that was already written in the same batch and the run reports
        them as `updated`.
        """
        cas = Cassette.load("ats-workable")
        widget = [i for i in cas.interactions if "widget" in i.url]
        self.assertEqual(len(widget), 1)
        raw = json.loads(widget[0].raw)["jobs"]
        self.assertGreater(len(raw), len({j["shortcode"] for j in raw}),
                           "this cassette no longer exhibits the "
                           "location-expansion trap it was recorded for; "
                           "re-record against a multi-location account or "
                           "the dedupe is no longer covered")

        with replaying("ats-workable"):
            jobs = ats.fetch_workable("braven")
        self.assertEqual(len(jobs), len({j["shortcode"] for j in raw}))
        self.assertLess(len(jobs), len(raw))

    @require("ats-workable")
    def test_reconciles_the_widget_against_v3s_total(self):
        with replaying("ats-workable") as player:
            jobs = ats.fetch_workable("braven")
        self.assertEqual(jobs.reported_total, len(jobs))
        self.assertTrue(jobs.complete)
        self.assertIsNone(jobs.shortfall())
        # Two endpoints, two requests, in that order: v3 first so that a
        # failure there fails the company before anything is closed on the
        # strength of an unreconciled list.
        self.assertEqual([m for m, _ in player.requests], ["POST", "GET"])
        self.assertIn("/api/v3/accounts/braven/jobs", player.requests[0][1])
        self.assertIn("details=true", player.requests[1][1])
        self.assertEqual(jobs.requests, 2)

    def test_a_widget_short_of_v3s_total_refuses_closure(self):
        """The half of the reconciliation no live board will demonstrate."""
        with cassettes.replay(cassette=_cassette(
                _ok(ats.WORKABLE_V3_URL.format(token="acme"),
                    {"total": 9, "results": []}, method="POST"),
                _ok(ats.WORKABLE_WIDGET_URL.format(token="acme"),
                    {"jobs": [{"shortcode": "A1", "title": "t"}]}))):
            jobs = ats.fetch_workable("acme")
        self.assertEqual(len(jobs), 1)
        self.assertEqual(jobs.reported_total, 9)
        self.assertFalse(jobs.complete)
        self.assertEqual(jobs.shortfall(), (1, 9))


# ---------------------------------------------------------------------------
# Recruitee
# ---------------------------------------------------------------------------

class TestRecruitee(NormalizedRecord):

    @require("ats-recruitee")
    def test_fetch_and_normalize(self):
        with replaying("ats-recruitee") as player:
            jobs = ats.fetch_recruitee("jobs")
        records = [ats.normalize_recruitee(ROSTER, j) for j in jobs]
        self.assert_contract(records, "recruitee")
        self.assertEqual(len(player.requests), 1,
                         "recruitee returns the whole board in one response; "
                         "a second request means someone added pagination "
                         "the endpoint does not have")
        self.assertTrue(any(r["description_text"] for r in records))
        self.assertTrue(any(r["salary_text"] for r in records),
                        "recruitee publishes a structured salary object and "
                        "recruitee_salary() renders it; none survived")

    def test_salary_renders_only_what_is_there(self):
        self.assertEqual(
            ats.recruitee_salary({"salary": {"min": "50000", "max": "65000",
                                             "currency": "EUR",
                                             "period": "year"}}),
            "EUR 50000-65000 / year")
        # A one-sided range is still a fact worth storing.
        self.assertEqual(
            ats.recruitee_salary({"salary": {"min": "50000", "max": None,
                                             "currency": "USD",
                                             "period": "year"}}),
            "USD 50000 / year")
        # Nothing published is None, never "" -- salary_text is nullable and
        # "unknown" is not "no salary".
        self.assertIsNone(ats.recruitee_salary({"salary": None}))
        self.assertIsNone(ats.recruitee_salary({"salary": {}}))
        self.assertIsNone(ats.recruitee_salary({}))


# ---------------------------------------------------------------------------
# SmartRecruiters
# ---------------------------------------------------------------------------

class TestSmartRecruiters(NormalizedRecord):

    @require("ats-smartrecruiters")
    def test_fetch_and_normalize_with_details(self):
        """The merge, and BOTH shapes a spent detail call can return.

        Visa's two postings are, as recorded, one ad with text only in
        `additionalInformation` and one whose four sections are all empty
        strings. That is not a defect in the cassette -- it is the reason the
        empty case has to be told apart from the not-yet-fetched case, and
        both are here in real bytes. The rich shape (all four sections full
        of HTML) was measured the same day against `BoschGroup`, whose board
        is 4,755 postings and not something to commit for one parser; it is
        exercised by test_description_joins_the_sections... below.
        """
        with replaying("ats-smartrecruiters") as player:
            postings = ats.fetch_smartrecruiters("Visa")
            merged = [{**p, **ats.fetch_smartrecruiters_detail("Visa", p["id"])}
                      for p in postings]
        records = [ats.normalize_smartrecruiters(ROSTER, j) for j in merged]
        self.assert_contract(records, "smartrecruiters")
        self.assertTrue(all("jobAd" in j for j in merged),
                        "the detail response is what carries jobAd; if it is "
                        "absent the merge did not happen")
        described = [r for r in records if r["description_text"]]
        self.assertTrue(described,
                        "no description survived the merge, so the section "
                        "extraction is not reaching the real bytes")
        # An ad whose sections are all empty is None, not "". extract.py's
        # selector keys on NULL, so "" would enqueue a prompt over nothing.
        for rec in records:
            self.assertIn(rec["description_text"], [None, *[
                r["description_text"] for r in described]])
        # The list URL is a claim about what we send: 100 is the maximum the
        # API honours and it reports the clamp back rather than, as Workday
        # does for limit>20, answering with an empty array and no error.
        self.assertIn(f"limit={ats.SMARTRECRUITERS_PAGE_LIMIT}",
                      player.requests[0][1])

    @require("ats-smartrecruiters")
    def test_the_list_alone_has_no_description(self):
        """Why the detail call exists at all, from the real bytes."""
        with replaying("ats-smartrecruiters"):
            postings = ats.fetch_smartrecruiters("Visa")
        records = [ats.normalize_smartrecruiters(ROSTER, p) for p in postings]
        self.assertTrue(all(r["description_text"] is None for r in records),
                        "SmartRecruiters' list endpoint carries no job ad; a "
                        "description appearing here means the merge happened "
                        "somewhere it should not have")

    @require("ats-smartrecruiters")
    def test_totalfound_is_carried_and_reconciled(self):
        with replaying("ats-smartrecruiters"):
            postings = ats.fetch_smartrecruiters("Visa")
        self.assertIsNotNone(postings.reported_total)
        self.assertEqual(len(postings), postings.reported_total)
        self.assertTrue(postings.complete)

    def test_pages_until_totalfound_is_satisfied(self):
        """Synthetic, because a board large enough to page is large to commit.

        Two pages, `totalFound` 3 on both. The property under test is that
        the second page is requested at the right offset and that collection
        stops when the API's own total is reached rather than when a page
        happens to look short.
        """
        base = (f"{ats.SMARTRECRUITERS_BASE}/acme/postings"
                f"?limit={ats.SMARTRECRUITERS_PAGE_LIMIT}&offset=")
        with cassettes.replay(cassette=_cassette(
                _ok(base + "0", {"totalFound": 3, "limit": 100, "offset": 0,
                                 "content": [{"id": "1"}, {"id": "2"}]}),
                _ok(base + "2", {"totalFound": 3, "limit": 100, "offset": 2,
                                 "content": [{"id": "3"}]}))):
            postings = ats.fetch_smartrecruiters("acme")
        self.assertEqual([p["id"] for p in postings], ["1", "2", "3"])
        self.assertEqual(postings.reported_total, 3)
        self.assertTrue(postings.complete)
        self.assertEqual(postings.requests, 2)

    def test_a_throttled_page_is_not_the_end_of_the_list(self):
        """CLAUDE.md's landmine, as arithmetic.

        The API says three; a page comes back empty after one. Reading that
        as "no more results" is how a published account lost 1,960 of 2,000
        jobs -- and here it would additionally CLOSE the two it never saw.
        """
        base = (f"{ats.SMARTRECRUITERS_BASE}/acme/postings"
                f"?limit={ats.SMARTRECRUITERS_PAGE_LIMIT}&offset=")
        with cassettes.replay(cassette=_cassette(
                _ok(base + "0", {"totalFound": 3, "content": [{"id": "1"}]}),
                _ok(base + "1", {"totalFound": 3, "content": []}))):
            postings = ats.fetch_smartrecruiters("acme")
        self.assertEqual(len(postings), 1)
        self.assertFalse(postings.complete)
        self.assertEqual(postings.shortfall(), (1, 3))

    def test_released_after_reaches_the_url(self):
        """The one server-side delta filter in this script.

        Probed 2026-07-28 against `BoschGroup`: with
        releasedAfter=2030-01-01T00:00:00Z, totalFound drops from 4,755 to 0,
        so the filter is real and server-side -- unlike greenhouse's
        `updated_after`, which is accepted and ignored.
        """
        since = "2026-07-01T00:00:00Z"
        url = (f"{ats.SMARTRECRUITERS_BASE}/acme/postings"
               f"?limit={ats.SMARTRECRUITERS_PAGE_LIMIT}&offset=0"
               f"&releasedAfter=2026-07-01T00%3A00%3A00Z")
        with cassettes.replay(cassette=_cassette(
                _ok(url, {"totalFound": 0, "content": []}))) as player:
            postings = ats.fetch_smartrecruiters("acme", released_after=since)
        self.assertEqual(len(postings), 0)
        self.assertIn("releasedAfter", player.requests[0][1])

    def test_a_delta_run_never_closes(self):
        """Arithmetic, not policy: a delta response is not the complete set.

        `main()` gates closure on `not (args.delta and platform in
        DELTA_CAPABLE)`. This pins the half that decides it -- that
        SmartRecruiters is in that set, so a `--delta` run reaches the
        exclusion rather than sliding past it.
        """
        self.assertIn("smartrecruiters", ats.DELTA_CAPABLE)

    def test_description_joins_the_sections_and_skips_the_video_embed(self):
        job = {"jobAd": {"sections": {
            "companyDescription": {"text": "<p>About Acme</p>"},
            "jobDescription": {"text": "<ul><li>Do the thing</li></ul>"},
            "qualifications": {"text": "<p>R&amp;D experience</p>"},
            "videos": {"urls": ["https://example.test/v"]},
        }}}
        out = ats.smartrecruiters_description(job)
        self.assertIn("About Acme", out)
        self.assertIn("Do the thing", out)
        self.assertIn("R&D experience", out)
        self.assertNotIn("example.test", out)
        self.assertNotIn("<", out)

    def test_no_job_ad_is_none_not_empty_string(self):
        self.assertIsNone(ats.smartrecruiters_description({"id": "1"}))
        self.assertIsNone(ats.smartrecruiters_description(
            {"jobAd": {"sections": {}}}))

    def test_job_url_is_a_page_a_human_can_open(self):
        """The list's `ref` is an API URL. It must never reach job_url."""
        listed = ats.normalize_smartrecruiters(
            ROSTER, {"id": "7", "name": "Analyst",
                     "ref": "https://api.smartrecruiters.com/v1/companies/"
                            "acme/postings/7"})
        self.assertNotIn("api.smartrecruiters.com", listed["job_url"])
        self.assertIn("jobs.smartrecruiters.com", listed["job_url"])
        detailed = ats.normalize_smartrecruiters(
            ROSTER, {"id": "7", "name": "Analyst",
                     "postingUrl": "https://jobs.smartrecruiters.com/acme/7-analyst"})
        self.assertEqual(detailed["job_url"],
                         "https://jobs.smartrecruiters.com/acme/7-analyst")


# ---------------------------------------------------------------------------
# Ashby compensation, Lever pagination, Greenhouse total
# ---------------------------------------------------------------------------

class TestAshbyCompensation(unittest.TestCase):

    @require("ats-ashby")
    def test_the_request_asks_for_compensation(self):
        with replaying("ats-ashby") as player:
            ats.fetch_ashby("runway")
        self.assertIn("includeCompensation=true", player.requests[0][1])

    @require("ats-ashby")
    def test_a_board_that_publishes_none_yields_none(self):
        """runway returns the `compensation` KEY with empty tiers.

        That is the common case and the one that must not turn into "" or
        into the literal string "None" in a TEXT column.
        """
        with replaying("ats-ashby"):
            jobs = ats.fetch_ashby("runway")
        self.assertTrue(jobs, "cassette produced no postings")
        for job in jobs:
            self.assertIn("compensation", job,
                          "includeCompensation=true is what puts this key "
                          "there; without it the parameter has stopped working")
            self.assertIsNone(ats.ashby_salary(job))

    def test_a_published_tier_summary_is_stored_verbatim(self):
        """The populated branch, from a real board.

        The string is copied verbatim from
        `api.ashbyhq.com/posting-api/job-board/vanta?includeCompensation=true`
        on 2026-07-28. It is not a cassette because the smallest Ashby board
        that publishes compensation is `writer` at 859 KB -- more bytes than
        one field is worth committing. If this shape ever changes, the
        cassette assertion above is what notices `compensation` moving.
        """
        summary = ("$213K - $251K • Offers Equity • This role is also "
                   "eligible for medical benefits, 401(k) plan, and other "
                   "company perk programs.")
        job = {"compensation": {"compensationTierSummary": summary,
                                "scrapeableCompensationSalarySummary": None,
                                "compensationTiers": [], "summaryComponents": []}}
        self.assertEqual(ats.ashby_salary(job), summary)
        self.assertEqual(
            ats.normalize_ashby(ROSTER, {"id": "1", "title": "Eng",
                                         "jobUrl": "https://x.test/1",
                                         **job})["salary_text"],
            summary)

    def test_the_scrapeable_summary_is_the_fallback(self):
        job = {"compensation": {"compensationTierSummary": None,
                                "scrapeableCompensationSalarySummary": "$90K - $110K"}}
        self.assertEqual(ats.ashby_salary(job), "$90K - $110K")

    def test_a_board_without_the_key_at_all_is_none(self):
        self.assertIsNone(ats.ashby_salary({"id": "1"}))


class TestLeverPagination(unittest.TestCase):

    @require("ats-lever")
    def test_the_request_carries_limit_and_skip(self):
        with replaying("ats-lever") as player:
            jobs = ats.fetch_lever("finix")
        url = player.requests[0][1]
        self.assertIn(f"limit={ats.LEVER_PAGE_LIMIT}", url)
        self.assertIn("skip=0", url)
        self.assertIn("mode=json", url)
        self.assertEqual(len(player.requests), 1,
                         "finix returns a short first page, which ends the "
                         "loop; a second request means the short-page exit "
                         "stopped working")
        self.assertTrue(jobs.complete)

    def test_a_full_page_is_followed(self):
        page = [{"id": str(i), "text": "t"} for i in range(ats.LEVER_PAGE_LIMIT)]
        base = "https://api.lever.co/v0/postings/acme?mode=json&limit="
        with cassettes.no_sleep(), cassettes.replay(cassette=_cassette(
                _ok(f"{base}{ats.LEVER_PAGE_LIMIT}&skip=0", page),
                _ok(f"{base}{ats.LEVER_PAGE_LIMIT}&skip={ats.LEVER_PAGE_LIMIT}",
                    [{"id": "x", "text": "t"}]))):
            jobs = ats.fetch_lever("acme")
        self.assertEqual(len(jobs), ats.LEVER_PAGE_LIMIT + 1)
        self.assertEqual(jobs.requests, 2)

    def test_past_the_documented_ceiling_the_board_is_not_closeable(self):
        """17-retarget-ats-ingest.md:41-42 -- Lever truncates at 250.

        Past that point "the next page was empty" and "the API stopped
        answering" are the same bytes, so absence stops being evidence and
        closure is declined for that company. Slicing by team or location is
        the fix and this script does not do it; recording that it could not
        see the whole board is strictly better than closing on a guess.
        """
        limit = ats.LEVER_PAGE_LIMIT
        base = "https://api.lever.co/v0/postings/acme?mode=json&limit="
        pages = []
        for page in range(3):
            body = [{"id": f"{page}-{i}", "text": "t"} for i in range(limit)]
            pages.append(_ok(f"{base}{limit}&skip={page * limit}", body))
        pages.append(_ok(f"{base}{limit}&skip={3 * limit}", []))
        with cassettes.no_sleep(), cassettes.replay(cassette=_cassette(*pages)):
            jobs = ats.fetch_lever("acme")
        self.assertGreaterEqual(len(jobs), ats.LEVER_SKIP_CEILING)
        self.assertTrue(jobs.truncated)
        self.assertFalse(jobs.complete)


class TestGreenhouseTotal(unittest.TestCase):

    @require("ats-greenhouse")
    def test_meta_total_is_carried(self):
        with replaying("ats-greenhouse"):
            jobs = ats.fetch_greenhouse("kickstarter")
        self.assertIsNotNone(jobs.reported_total,
                             "greenhouse reports meta.total and it is the "
                             "only reconciliation anchor this platform has")
        self.assertEqual(len(jobs), jobs.reported_total)
        self.assertTrue(jobs.complete)

    def test_a_board_short_of_its_own_meta_total_refuses_closure(self):
        with cassettes.replay(cassette=_cassette(
                _ok("https://api.greenhouse.io/v1/boards/acme/jobs?content=true",
                    {"meta": {"total": 40},
                     "jobs": [{"id": 1, "title": "t"}]}))):
            jobs = ats.fetch_greenhouse("acme")
        self.assertFalse(jobs.complete)
        self.assertEqual(jobs.shortfall(), (1, 40))


# ---------------------------------------------------------------------------
# the roster
# ---------------------------------------------------------------------------

class _StubConn:
    """Records the SQL it is handed and replays canned rows. No database."""

    def __init__(self, rows):
        self.rows = rows
        self.sql = []
        self.params = []

    def execute(self, sql, params=None):
        self.sql.append(" ".join(sql.split()))
        self.params.append(params)
        return self

    def fetchall(self):
        return self.rows


class TestRoster(unittest.TestCase):

    def test_it_queries_company_ats_for_the_handled_platforms_only(self):
        conn = _StubConn([])
        ats_sources.load_companies(conn)
        self.assertIn("FROM company_ats", conn.sql[0])
        platforms, statuses = conn.params[0]
        self.assertEqual(sorted(platforms),
                         sorted(ats_sources.HANDLED_PLATFORMS))
        # Task 18 owns workday and task 20 owns icims. Both have rows in this
        # table; neither is pulled here.
        self.assertNotIn("workday", platforms)
        self.assertNotIn("icims", platforms)

    def test_unvalidated_admits_a_token_and_dead_does_not(self):
        """The status decision, as data rather than as a literal in a query.

        `unvalidated` is task 16's fourth value: a token was found and the
        ATS did not answer (403/429/5xx/unparseable). Dropping those rows
        would mean a board blocked once at validation time is never pulled
        again, which is the failure this whole vocabulary exists to prevent.
        `dead` is a conclusive 404 or empty list from the vendor and stays
        out.
        """
        statuses = ats_sources.ADMITTING_STATUSES
        self.assertIn(ats_sources.STATUS_VALID, statuses)
        self.assertIn(ats_sources.STATUS_UNVALIDATED, statuses)
        import ats_discovery
        self.assertNotIn(ats_discovery.STATUS_DEAD, statuses)
        self.assertNotIn(ats_discovery.STATUS_NEVER_FOUND, statuses)

    def test_one_board_reached_twice_is_one_company(self):
        """A parent and its subsidiary can share a token.

        Pulled twice, the board costs double the requests and close_missing
        runs twice over the same rows.
        """
        conn = _StubConn([
            ("greenhouse", "acme", "Acme Health", "valid"),
            ("greenhouse", "ACME", "Acme Physicians Group", "valid"),
            ("lever", "acme", "Acme (lever board)", "valid"),
        ])
        rows = ats_sources.load_companies(conn)
        self.assertEqual([(r["platform"], r["token"]) for r in rows],
                         [("greenhouse", "acme"), ("lever", "acme")])

    def test_the_seed_never_overwrites_a_discovered_row(self):
        """migrations/migrate_company_ats.py:165-171's rule, restated here.

        tools/ats-discover.py owns every row it wrote. Re-running the seed
        must not replace a probe's `status` or `validation_note` with the
        file's stale opinion, so rows already present are filtered out BEFORE
        the upsert rather than left to its three branches.
        """
        rows = ats_sources.companies_json_rows(
            os.path.join(os.path.dirname(INGEST_DIR), "config",
                         "companies.json"))
        self.assertTrue(rows)
        import ats_discovery
        ids = [ats_discovery.make_row_id(r) for r in rows]
        self.assertEqual(len(ids), len(set(ids)),
                         "two seed rows share a primary key, so one would "
                         "silently overwrite the other in a single batch")
        for row in rows:
            self.assertIn(row["ats"], ats_sources.HANDLED_PLATFORMS)
            self.assertEqual(row["status"], ats_sources.STATUS_VALID)
            self.assertTrue(row["first_validated_at"])
            # Not NULL: docs/ats-token-discovery.md:344-350 -- a NULL here
            # disarms the 60-day stale-feed check for exactly these rows.
            self.assertTrue(row["open_jobs_changed_at"])

    def test_the_seed_date_is_when_the_check_happened(self):
        """Not "now". Stamping today's date on a check made on 2026-07-23 is
        how a staleness rule quietly stops being able to fire."""
        self.assertTrue(
            ats_sources.COMPANIES_JSON_VERIFIED_AT.startswith("2026-07-23"))


# ---------------------------------------------------------------------------
# structural properties of the file
# ---------------------------------------------------------------------------

class TestFileShape(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        with open(os.path.join(INGEST_DIR, "ats.py"), encoding="utf-8") as fh:
            cls.source = fh.read()

    def test_closure_is_called_exactly_once(self):
        """"Shared rather than copy-pasted per platform" is a property of the
        FILE, so it is asserted against the file.

        Six platforms and one closure call. A seventh platform that grew its
        own `close_missing` would also grow its own idea of when closing is
        safe, and the guards (empty fetch, incomplete fetch, delta run) would
        have to be remembered rather than inherited.

        Counted over the AST rather than by regex: this file mentions
        `close_missing()` several times in prose, and a test that counted
        those would fail for a documentation edit and pass for a second real
        call hidden in a string.
        """
        import ast
        calls = [n for n in ast.walk(ast.parse(self.source))
                 if isinstance(n, ast.Call)
                 and isinstance(n.func, ast.Attribute)
                 and n.func.attr == "close_missing"]
        self.assertEqual(len(calls), 1,
                         f"{len(calls)} calls to schema.close_missing() in "
                         f"ingest/ats.py; there must be exactly one")

    def test_no_hardcoded_token_list_remains(self):
        """The roster is company_ats, full stop.

        `config/companies.json` may appear only as the JOB_SOURCES_FILE
        default that --seed-from-json reads. Nothing may open it on a normal
        run, and there is no literal token list to fall back to.
        """
        self.assertNotIn("def load_sources", self.source)
        self.assertIn("ats_sources.load_companies", self.source)
        # The only file-open in this module is the seed path, which lives in
        # ats_sources.companies_json_rows -- not here.
        self.assertNotIn("json.load(", self.source)

    def test_every_upsert_goes_through_upsert_checked(self):
        """CLAUDE.md's landmine: `upsert()`'s three-tuple drops .errors."""
        for module in ("ats.py", "ats_sources.py"):
            with open(os.path.join(INGEST_DIR, module), encoding="utf-8") as fh:
                body = fh.read()
            with self.subTest(module=module):
                self.assertNotIn("upsert(conn", body)
                self.assertNotIn(" = upsert(", body)

    def test_delta_capable_is_not_silently_empty(self):
        """`--delta` exists for exactly one platform.

        Probed 2026-07-28: greenhouse's `updated_after` is ACCEPTED AND
        IGNORED on the job-board API (a 2030 timestamp returns the same
        postings), lever exposes no update timestamp at all, and only
        SmartRecruiters honours a date filter (`releasedAfter`). If this set
        empties, `--delta` has become a flag that does nothing.
        """
        self.assertEqual(ats.DELTA_CAPABLE, ("smartrecruiters",))
        for platform in ats.DELTA_CAPABLE:
            self.assertIn(platform, ats.FETCHERS)

    def test_every_handled_platform_has_a_fetcher_and_a_normalizer(self):
        self.assertEqual(sorted(ats.FETCHERS),
                         sorted(ats_sources.HANDLED_PLATFORMS))
        self.assertEqual(sorted(ats.NORMALIZERS),
                         sorted(ats_sources.HANDLED_PLATFORMS))


class TestRequestCount(unittest.TestCase):
    """Task 04's budget needs a measured number, not an estimate."""

    def setUp(self):
        ats.reset_requests()

    def tearDown(self):
        ats.reset_requests()

    @require("ats-workable")
    def test_requests_are_counted_per_platform(self):
        with replaying("ats-workable"):
            ats.fetch_workable("braven")
        self.assertEqual(ats.REQUESTS["workable"], 2)
        line = ats.request_summary_line(companies=1)
        self.assertTrue(line.startswith(ats.REQUEST_SUMMARY_PREFIX))
        self.assertIn("total=2", line)
        self.assertIn("workable=2", line)
        self.assertIn("companies=1", line)

    def test_the_line_is_printed_even_when_nothing_was_fetched(self):
        """`errors=0` on every run is what makes its absence the anomaly
        (lib/upsert.py:311-314). Same argument, same shape."""
        line = ats.request_summary_line(companies=0)
        self.assertIn("total=0", line)
        self.assertIn("companies=0", line)


if __name__ == "__main__":
    unittest.main()

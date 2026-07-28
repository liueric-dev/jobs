"""The part of task 18 that is not one of the four silent failures.

`tests/test_workday_fixtures.py` drives `ingest/workday.py` through the four
documented ways the CXS endpoint loses data. This file covers the rest of the
Definition of done (18-ingest-workday-cxs.md:114-131): the UPSTREAM GATE, which
is what makes this source affordable, plus normalization, tenant selection and
the seen/fetched/surviving accounting.

WHY THE GATE TESTS NEED A DATABASE

Because the gate IS a database. CLAUDE.md forbids reimplementing relevance
matching in Python, and `relevance.py` compiles `config/relevance.json` to
POSTGRES regexes -- a dialect in which `\\y` is a word boundary and `\\b` is
BACKSPACE, both the opposite of Python's `re`. So `ingest/workday.py` gates
list rows by running `relevance.tier_sql` against them in Postgres before they
are a table (`_tiers()`), and a test that evaluated the same config in Python
would be testing the second implementation this design exists to avoid.

`scratchdb.available()` gates those tests, so a developer with no Postgres sees
skips rather than green -- the same rule `tests/test_scratchdb.py:47` adopted.
The gate query touches no table (`FROM unnest(...) WITH ORDINALITY`), so the
scratch schema is used for a connection and nothing else.
"""

import json
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import relevance                                              # noqa: E402
import schema                                                 # noqa: E402
from evals import cassettes, scratchdb                        # noqa: E402
from evals import workday_fixtures as wf                      # noqa: E402
from evals.ingest_modules import load as load_ingest          # noqa: E402
from lib import envfile                                       # noqa: E402

envfile.load(os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), ".env"))

workday = load_ingest("workday")

requires_db = unittest.skipUnless(
    scratchdb.available(),
    "no scratch database: set DATABASE_URL (or JOBS_SCRATCH_DATABASE_URL)")

EMPLOYER = {"employer_name": "Acme Hospital", "token": wf.TENANT,
            "dc": wf.DC, "site": wf.SITE}

#: A relevance config in the shape config/relevance.json uses, small enough to
#: reason about. Postgres dialect: `\y`, never `\b` (CLAUDE.md's landmine).
CFG = relevance.load(cfg={
    "title_include": ["\\yengineer", "\\ydata scien"],
    "title_exclude": ["\\ynurse\\y", "\\yaccount executive\\y"],
    "company_exclude": ["\\yremote zest\\y"],
    "description_exclude": ["reputed company"],
    "location_columns": ["location_is_nyc", "location_is_remote"],
    "max_tier_to_score": 2,
})


def listing(title, locations_text="New York, NY", remote_type=None):
    return workday.normalize_listing(EMPLOYER, {
        "title": title, "locationsText": locations_text,
        "externalPath": f"/job/x/{title.replace(' ', '-')}_1",
        "postedOn": "Posted Yesterday", "remoteType": remote_type,
        "bulletFields": ["R-1"]})


class TestLocationFlags(unittest.TestCase):
    """The third answer text.classify_location cannot give: "cannot say"."""

    def test_a_real_place_is_classified_the_way_every_other_source_does(self):
        self.assertEqual(workday.location_flags("New York, NY"), (True, False))
        self.assertEqual(workday.location_flags("Boise, ID"), (False, False))

    def test_the_multi_location_placeholder_is_unknown_not_elsewhere(self):
        """Workday writes "2 Locations" instead of a place. (False, False)
        would state the job is known not to be in New York and the upstream
        filter would drop it on the strength of a placeholder."""
        for placeholder in ("2 Locations", "17 locations", " 3 Locations "):
            with self.subTest(placeholder=placeholder):
                self.assertEqual(workday.location_flags(placeholder),
                                 (None, None))
        self.assertEqual(workday.location_flags(None), (None, None))
        self.assertEqual(workday.location_flags(""), (None, None))

    def test_a_facility_name_is_unknown_not_elsewhere(self):
        """Measured 2026-07-28: NewYork-Presbyterian's `locationsText` is a
        FACILITY hierarchy, not a geography -- "NYP/Weill Cornell Medical
        Center", "NYP/Columbia University Irving Medical Center". Two of its
        three commonest values name New York hospitals without naming New York,
        so `text.classify_location` returns (False, False) and reading that as
        "known not to be in New York" drops most of a New York hospital
        system's board on its own internal naming convention."""
        for facility in ("NYP/Weill Cornell Medical Center",
                         "NYP/Columbia University Irving Medical Center",
                         "Sloan Kettering Institute"):
            with self.subTest(facility=facility):
                self.assertEqual(workday.location_flags(facility), (None, False))

    def test_a_real_elsewhere_is_still_elsewhere(self):
        """The comma is the discriminator, and it is the shape every real place
        in this data has. Losing that would make the location half of the
        upstream filter a no-op, and Nordstrom's 868 -> 27 is where it pays."""
        for place in ("Boise, ID", "Seattle, WA", "US, CA, Santa Clara",
                      "Israel, Yokneam"):
            with self.subTest(place=place):
                self.assertEqual(workday.location_flags(place), (False, False))

    def test_a_bare_out_of_town_city_errs_toward_keeping(self):
        """"Seattle" with no state is unknown, so it costs one detail fetch
        rather than a lost posting. That asymmetry is the point of a loose
        upstream filter and it is deliberate, not an oversight."""
        self.assertEqual(workday.location_flags("Seattle"), (None, False))

    def test_remote_type_is_read_even_when_the_place_is_unknown(self):
        self.assertEqual(workday.location_flags("4 Locations", "Remote"),
                         (None, True))
        self.assertEqual(workday.location_flags("Boise, ID", "Remote"),
                         (False, True))
        self.assertEqual(workday.location_flags("New York, NY", "Hybrid"),
                         (True, False))


class TestNormalization(unittest.TestCase):

    def test_a_listing_record_supplies_every_schema_column(self):
        rec = listing("Staff Engineer")
        for column in schema.COLUMNS:
            self.assertIn(column, rec)

    def test_the_hashed_posted_at_never_receives_a_relative_string(self):
        """`posted_at` is in HASH_FIELDS_ATS (schema.py:131) and the list gives
        only "Posted Yesterday". Storing that would re-derive to a different
        instant every run and churn the row forever; the sortable form goes to
        the unhashed posted_at_ts instead (schema.py:188-214)."""
        rec = listing("Staff Engineer")
        self.assertIsNone(rec["posted_at"])
        self.assertIsNotNone(rec["posted_at_ts"])

    def test_the_detail_document_supplies_the_absolute_date_and_description(self):
        detail = {"jobPostingInfo": {
            "jobDescription": "<p>Runs <b>ChatGPT</b> workflows.</p>",
            "startDate": "2026-07-27", "location": "New York, NY",
            "externalUrl": "https://acmehospital.wd5.myworkdayjobs.com/"
                           "External/job/x/Staff-Engineer_1"}}
        rec = workday.apply_detail(listing("Staff Engineer"), detail)
        self.assertEqual(rec["posted_at"], "2026-07-27")
        self.assertEqual(rec["posted_at_ts"], "2026-07-27")
        self.assertIn("ChatGPT", rec["description_text"])
        self.assertNotIn("<p>", rec["description_text"])
        self.assertEqual(rec["job_url"], detail["jobPostingInfo"]["externalUrl"],
                         "Workday's own canonical url beats one we built")

    def test_the_detail_location_may_only_add_knowledge(self):
        """A list saying "2 Locations" and a detail saying "New York, NY" must
        resolve to known-NYC, not stay unknown."""
        rec = listing("Staff Engineer", "2 Locations")
        self.assertIsNone(rec["location_is_nyc"])
        out = workday.apply_detail(rec, {"jobPostingInfo": {
            "location": "New York, NY", "jobDescription": "x"}})
        self.assertTrue(out["location_is_nyc"])
        self.assertEqual(out["location_raw"], "New York, NY")

    def test_a_facility_name_in_the_detail_cannot_un_new_york_a_posting(self):
        """Measured on the first live run: NewYork-Presbyterian's detail
        answers `location: "NYP/Weill Cornell Medical Center"` -- an org chart
        entry, not a place -- while the list said "New York, NY". Preferring
        the detail there flips location_is_nyc to FALSE and demotes a real NYC
        posting to tier 2 in every downstream query."""
        rec = listing("Patient Registrar", "New York, NY")
        self.assertTrue(rec["location_is_nyc"])
        out = workday.apply_detail(rec, {"jobPostingInfo": {
            "location": "NYP/Weill Cornell Medical Center",
            "jobDescription": "x"}})
        self.assertTrue(out["location_is_nyc"])
        self.assertEqual(out["location_raw"], "New York, NY",
                         "the list's place beats the detail's facility name")

    def test_raw_json_stays_valid_json_however_long_the_description(self):
        """lib/text.py:65-94 -- slicing serialized JSON produces a stump
        json.loads cannot read, and 10 live rows already are one."""
        detail = {"jobPostingInfo": {"jobDescription": "x" * 200000,
                                     "startDate": "2026-07-27"}}
        rec = workday.apply_detail(listing("Staff Engineer"), detail)
        self.assertLessEqual(len(rec["raw_json"]), workday.RAW_JSON_LIMIT)
        json.loads(rec["raw_json"])          # raises if it is a stump

    def test_source_id_is_the_external_path_not_the_requisition_id(self):
        """Two postings of one req share bulletFields and differ only in
        externalPath; keying on the req id would collapse them onto one row."""
        a = workday.normalize_listing(EMPLOYER, {
            "title": "Engineer", "externalPath": "/job/a/Engineer_JR1",
            "bulletFields": ["JR1"], "locationsText": "New York, NY"})
        b = workday.normalize_listing(EMPLOYER, {
            "title": "Engineer", "externalPath": "/job/b/Engineer_JR1-1",
            "bulletFields": ["JR1"], "locationsText": "Boise, ID"})
        self.assertNotEqual(schema.make_job_id(a), schema.make_job_id(b))

    def test_a_title_with_a_space_does_not_truncate_the_detail_url(self):
        url = workday.detail_url(wf.TENANT, wf.DC, wf.SITE,
                                 "/job/New York/Data Scientist_1")
        self.assertNotIn(" ", url)
        self.assertTrue(url.endswith("/job/New%20York/Data%20Scientist_1"))


@requires_db
class TestTheUpstreamGate(unittest.TestCase):
    """18-...md:61-88, the architectural half of this task."""

    @classmethod
    def setUpClass(cls):
        cls._ctx = scratchdb.scratch_schema()
        cls.conn, _ = cls._ctx.__enter__()

    @classmethod
    def tearDownClass(cls):
        cls._ctx.__exit__(None, None, None)

    def survivors(self, records, cfgs=(CFG,)):
        out, _ = workday.upstream_survivors(self.conn, list(cfgs), records)
        return [r["title"] for r in out]

    def test_an_uninformative_title_in_the_right_place_survives(self):
        """The whole reason the upstream filter is loose. "Operations
        Coordinator" at a hospital is the target population and no
        title_include regex will ever match it -- 18-...md:80-85."""
        self.assertEqual(
            self.survivors([listing("Operations Coordinator")]),
            ["Operations Coordinator"])

    def test_an_excluded_title_does_not(self):
        """title_exclude is "narrow and specific on purpose" and unambiguous
        (config/relevance.json _title_exclude_note), which is what makes it
        safe to apply to a bare title with no description behind it."""
        self.assertEqual(self.survivors([listing("Registered Nurse")]), [])
        self.assertEqual(self.survivors([listing("Account Executive")]), [])

    def test_a_known_elsewhere_location_does_not(self):
        self.assertEqual(
            self.survivors([listing("Operations Coordinator", "Boise, ID")]),
            [])

    def test_an_unknown_location_does(self):
        """18-...md:83's "neither-but-unknown". "2 Locations" is a placeholder
        and dropping on it would discard whatever the requisition really is."""
        self.assertEqual(
            self.survivors([listing("Operations Coordinator", "2 Locations")]),
            ["Operations Coordinator"])

    def test_a_remote_posting_anywhere_survives(self):
        self.assertEqual(
            self.survivors([listing("Operations Coordinator", "Boise, ID",
                                    "Remote")]),
            ["Operations Coordinator"])

    def test_an_excluded_company_drops_the_whole_tenant(self):
        cfg = relevance.load(cfg={**CFG, "company_exclude": ["\\yacme\\y"]})
        self.assertEqual(self.survivors([listing("Data Scientist")], (cfg,)), [])

    def test_the_gate_is_the_union_over_active_profiles(self):
        """relevance.py:276-292's argument, applied one step earlier: a detail
        fetch is shared, so a posting one profile would never look at still
        deserves the request if a second profile would."""
        picky = relevance.load(cfg={**CFG, "title_exclude": ["\\yengineer"]})
        records = [listing("Staff Engineer")]
        self.assertEqual(self.survivors(records, (picky,)), [])
        self.assertEqual(self.survivors(records, (CFG, picky)),
                         ["Staff Engineer"])

    def test_the_postgres_dialect_is_the_one_that_runs(self):
        r"""`\y` is a word boundary in Postgres and an error in Python's `re`;
        `\b` is a word boundary in Python and BACKSPACE in Postgres. A Python
        evaluator of this config would not merely duplicate the matcher, it
        would disagree with it -- which is why the gate is a query."""
        import re as _re
        self.assertRaises(_re.error, _re.compile, "\\ynurse\\y")
        self.assertEqual(self.survivors([listing("Registered Nurse")]), [],
                         "Postgres understood the pattern Python cannot parse")

    def test_no_active_profiles_falls_back_rather_than_ingesting_nothing(self):
        """union_sql returns FALSE for an empty profile list, which is right
        for extraction and wrong for ingest: a night this source does not pull
        is a night whose postings are gone before anyone asks. The divergence
        is deliberate and announced -- ingest/workday.py:active_relevance_cfgs."""
        cfgs, names = workday.active_relevance_cfgs(self.conn)
        self.assertEqual(len(cfgs), 1)
        self.assertEqual(names, ["<shared>"])

    def test_the_full_gate_count_uses_the_unmodified_config(self):
        """The third of the three ratio numbers. Same rows, real title_include
        back in force, so an uninformative title that SURVIVED the upstream
        filter is correctly not counted as gate-surviving."""
        detailed = [
            workday.apply_detail(listing("Data Scientist"),
                                 {"jobPostingInfo": {"jobDescription": "x",
                                                     "startDate": "2026-07-27"}}),
            workday.apply_detail(listing("Operations Coordinator"),
                                 {"jobPostingInfo": {"jobDescription": "x",
                                                     "startDate": "2026-07-27"}}),
        ]
        self.assertEqual(workday.full_gate_count(self.conn, [CFG], detailed), 1)

    def test_the_gate_survives_a_config_that_ignores_location(self):
        """location_columns=[] is the documented way to accept anywhere
        (config/relevance.json _location_note); the gate must not require a
        column that no profile named."""
        anywhere = relevance.load(cfg={**CFG, "location_columns": []})
        self.assertEqual(
            self.survivors([listing("Operations Coordinator", "Boise, ID")],
                           (anywhere,)),
            ["Operations Coordinator"])

    def test_a_location_column_that_is_not_an_identifier_is_refused(self):
        """relevance.py:253-257 validates these because they are interpolated
        into SQL. Calling tier_sql before building the column list is what
        makes that validation cover the interpolation here too."""
        evil = relevance.load(cfg={**CFG,
                                   "location_columns": ["x; DROP TABLE jobs"]})
        self.assertRaises(ValueError, self.survivors,
                          [listing("Engineer")], (evil,))

    def test_an_empty_record_list_costs_no_query(self):
        self.assertEqual(self.survivors([]), [])


@requires_db
class TestTenantSelection(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls._ctx = scratchdb.scratch_schema()
        cls.conn, _ = cls._ctx.__enter__()
        cls.conn.execute("""
            CREATE TABLE company_ats (
                id TEXT PRIMARY KEY, employer_name TEXT NOT NULL,
                careers_url TEXT, ats TEXT NOT NULL, token TEXT NOT NULL,
                workday_site TEXT, workday_dc TEXT,
                open_jobs_at_validation INTEGER, open_jobs_changed_at TEXT,
                first_validated_at TEXT, last_validated_at TEXT,
                status TEXT NOT NULL, validation_note TEXT,
                discovered_via TEXT, content_hash TEXT,
                first_seen TEXT NOT NULL, last_seen TEXT NOT NULL)
        """)
        rows = [
            ("1", "NewYork-Presbyterian", "workday", "nyp", "nypcareers",
             "wd1", "valid"),
            ("2", "Nordstrom", "workday", "nordstrom", "nordstrom_careers",
             "wd501", "valid"),
            ("3", "No Data Centre", "workday", "ghost", "Careers", None,
             "valid"),
            ("4", "Detected Only", "workday", "maybe", "Careers", "wd1",
             "unvalidated"),
            ("5", "Per Scholas", "greenhouse", "perscholashires", None, None,
             "valid"),
            ("6", "Nowhere", "", "", None, None, "never_found"),
        ]
        for rid, name, ats, token, site, dc, status in rows:
            cls.conn.execute(
                "INSERT INTO company_ats (id, employer_name, ats, token, "
                "workday_site, workday_dc, status, first_seen, last_seen) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s,'t','t')",
                (rid, name, ats, token, site, dc, status))
        cls.conn.commit()

    @classmethod
    def tearDownClass(cls):
        cls._ctx.__exit__(None, None, None)

    def test_only_valid_workday_rows_with_a_complete_triple_are_used(self):
        tenants, incomplete = workday.load_workday_tenants(self.conn)
        self.assertEqual([t["employer_name"] for t in tenants],
                         ["NewYork-Presbyterian", "Nordstrom"])
        self.assertEqual(incomplete, ["No Data Centre"])

    def test_a_missing_data_centre_is_reported_and_never_guessed(self):
        """18-...md:52-55, "never assume, never default". wd1/wd108/wd501 are
        all in use among the four tenants task 16 found; a wrong prefix answers
        404 or 422 and reads as a tenant with no open roles."""
        _, incomplete = workday.load_workday_tenants(self.conn)
        self.assertIn("No Data Centre", incomplete)

    def test_the_data_centre_is_carried_into_the_url(self):
        tenants, _ = workday.load_workday_tenants(self.conn)
        nordstrom = tenants[1]
        self.assertEqual(
            workday.jobs_url(nordstrom["token"], nordstrom["dc"],
                             nordstrom["site"]),
            "https://nordstrom.wd501.myworkdayjobs.com/wday/cxs/nordstrom/"
            "nordstrom_careers/jobs")

    def test_never_found_does_not_mean_no_ats(self):
        """docs/ats-token-discovery.md's headline result: the positive control
        found 0 of 4 known-good tokens, so `not_found`/`never_found` means "no
        ATS URL in the bytes we were served" and nothing stronger. This ingest
        must therefore filter on status='valid' PLUS the triple, never on the
        absence of a negative."""
        tenants, _ = workday.load_workday_tenants(self.conn)
        self.assertNotIn("Nowhere", [t["employer_name"] for t in tenants])
        self.assertNotIn("Detected Only", [t["employer_name"] for t in tenants])


@requires_db
class TestTheRatioIsAccounted(unittest.TestCase):
    """18-...md:86-88: "Log the ratio: postings seen, postings detail-fetched,
    postings surviving the full gate. If detail-fetched/seen creeps toward 1.0,
    the upstream filter has stopped working and the window is about to blow."
    """

    @classmethod
    def setUpClass(cls):
        # scratch_schema() has already run the real ensure_schema() against
        # the fresh schema (evals/scratchdb.py:145).
        cls._ctx = scratchdb.scratch_schema()
        cls.conn, _ = cls._ctx.__enter__()

    @classmethod
    def tearDownClass(cls):
        cls._ctx.__exit__(None, None, None)

    def test_a_tenant_run_reports_all_three_numbers(self):
        """Driven through the constructed throttled-page fixture -- 2,000
        postings, of which the fixture's own posting() makes one in three a
        "Data Analyst" and the rest "Registered Nurse", i.e. an excluded title.
        So the gate must cut roughly two thirds, and `write=False` keeps this
        out of the jobs table."""
        detail = json.dumps({"jobPostingInfo": {
            "jobDescription": "<p>Ordinary prose.</p>",
            "startDate": "2026-07-14", "location": "New York, NY"}})
        cas = wf.throttled_page()
        # Every detail GET this run makes, answered by one recorded body. The
        # loose lookup (cassettes.py:381-385) serves it for any detail url.
        for i in (0, 3):
            cas.interactions.append(cassettes.Interaction(
                method="GET",
                url=workday.detail_url(wf.TENANT, wf.DC, wf.SITE,
                                       wf.posting(i)["externalPath"]),
                status=200, body=detail))
        with cassettes.no_sleep(), cassettes.replay(cassette=cas):
            out = workday.ingest_tenant(
                self.conn, EMPLOYER, [CFG], "2026-07-28T00:00:00",
                delay=0, sleep=lambda _s: None, max_detail=2, write=False)
        self.assertEqual(out.status, "ok")
        self.assertEqual(out.seen, wf.TOTAL)
        self.assertEqual(out.total, wf.TOTAL)
        # posting(n) is "Data Analyst n" when n % 3 == 0 -- 667 of 2,000, and
        # every one of them is in a real place, so the gate keeps exactly them.
        self.assertEqual(out.fetched_wanted, 667)
        self.assertLess(out.ratio, workday.RATIO_ALARM,
                        "if the gate stopped filtering this is the number "
                        "that says so")
        self.assertTrue(out.capped, "max_detail=2 is a fuse and it blew")
        self.assertEqual(out.fetched, 2)

    def test_a_blocked_tenant_is_counted_not_retried(self):
        """18-...md:104-106: inaccessible tenants are skipped and counted.
        A 403 is a datum, not an obstacle to route around."""
        cas = wf.prefix_assumed()
        cas.interactions = [wf._post(0, {"error": "forbidden"}, status=403,
                                     reason="Forbidden")]
        with cassettes.no_sleep(), cassettes.replay(cassette=cas) as player:
            out = workday.ingest_tenant(
                self.conn, EMPLOYER, [CFG], "2026-07-28T00:00:00",
                delay=0, sleep=lambda _s: None, write=False)
        self.assertEqual(out.status, "blocked")
        self.assertEqual(len(player.requests), 1,
                         "a refusal must not be retried into an incident")

    def test_a_shortfall_writes_nothing_at_all(self):
        """The safety valve. A partial list plus close_missing() would mark
        every posting on the missing pages as closed -- a lost page becoming
        hundreds of wrong closures, which is worse than the lost page."""
        truncated = wf.throttled_page()
        truncated.interactions = [
            i for i in truncated.interactions if i.status == 200][:1] + [
            wf._post(20, {"total": wf.TOTAL, "jobPostings": []})]
        with cassettes.no_sleep(), cassettes.replay(cassette=truncated):
            out = workday.ingest_tenant(
                self.conn, EMPLOYER, [CFG], "2026-07-28T00:00:00",
                delay=0, sleep=lambda _s: None, write=True)
        self.assertEqual(out.status, "shortfall")
        self.assertEqual(out.closed, 0)
        self.assertEqual(out.result.new, 0)
        self.assertIn("of 2000", out.error)


class TestTheHouseRules(unittest.TestCase):
    """Two things CLAUDE.md names that a reviewer should not have to grep for."""

    def test_upsert_is_never_unpacked_as_a_bare_three_tuple(self):
        """UpsertResult.__iter__ yields three values and NOT .errors, which is
        the defect task 03 existed to remove. This module calls upsert_checked
        and never upsert()."""
        path = os.path.join(os.path.dirname(os.path.dirname(
            os.path.abspath(__file__))), "ingest", "workday.py")
        with open(path, encoding="utf-8") as fh:
            src = fh.read()
        self.assertIn("upsert_checked(", src)
        self.assertNotIn("= upsert(", src)
        self.assertNotIn("upsert.upsert(", src)

    def test_no_llm_module_is_imported(self):
        """Ingest is HTTP and arithmetic by design; extract and score are the
        two stages that cost calls (CLAUDE.md, Architecture invariants)."""
        self.assertNotIn("llm", dir(workday))


if __name__ == "__main__":
    unittest.main()

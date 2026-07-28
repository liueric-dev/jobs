"""ATS token discovery: the signature patterns, and the silence distinction.

WHAT THIS PINS

Task 16 exists because there is no public directory of ATS board tokens, and
its whole method rests on two properties that are easy to break silently:

  1. A regex that reads the WRONG token out of a careers page produces a row
     that validates as `dead` and is then indistinguishable from a company
     that migrated ATS. The Workday triple and Greenhouse's `embed` form are
     the two that get this wrong in practice, so both have tests here.

  2. "Found nothing" and "was not allowed to look" must never collapse into
     each other. CLAUDE.md names silence this pipeline's failure mode, and a
     discovery pass is the worst place for it: a blocked run writes an empty
     table that the next run reads as settled fact. So the tests assert that
     only a CONCLUSIVE outcome can produce a `never_found` row, and that a
     validation that could not be performed is `unvalidated` rather than
     either `valid` or `dead`.

No network and no database. The signature and classification halves of
discovery are pure by construction (ats_discovery.py holds no I/O), which is
what makes them testable here rather than only against live hosts -- the same
split score.score_job() has, and for the same reason.
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import ats_discovery as ad  # noqa: E402


class SignatureTests(unittest.TestCase):

    def find(self, text, platform=None):
        hits = ad.find_signatures(text)
        if platform:
            hits = [(p, f) for p, f in hits if p == platform]
        return hits

    def test_greenhouse_board_url(self):
        self.assertEqual(
            self.find('<a href="https://boards.greenhouse.io/mountsinai">'),
            [("greenhouse", {"token": "mountsinai"})])

    def test_greenhouse_new_host(self):
        self.assertEqual(
            self.find("https://job-boards.greenhouse.io/nyclibrary/jobs/412"),
            [("greenhouse", {"token": "nyclibrary"})])

    def test_greenhouse_embed_form_reads_the_query_string(self):
        """`embed` is a path segment, not a token.

        boards.greenhouse.io/embed/job_board?for=TOKEN puts the real token in
        the query string. A pattern that takes the first path segment records
        every employer using this form as token `embed`, which 404s on
        validation and lands as `dead` -- a false negative that reads exactly
        like a company that migrated ATS.
        """
        hits = self.find(
            '<script src="https://boards.greenhouse.io/embed/job_board/js'
            '?for=hshs"></script>', platform="greenhouse")
        self.assertEqual(hits, [("greenhouse", {"token": "hshs"})])

    def test_greenhouse_embed_with_escaped_ampersand(self):
        hits = self.find(
            "https://boards.greenhouse.io/embed/job_board?b=1&amp;for=cityhall",
            platform="greenhouse")
        self.assertEqual(hits, [("greenhouse", {"token": "cityhall"})])

    def test_workday_captures_tenant_dc_and_site(self):
        """All three, separately. 18-ingest-workday-cxs.md:54 forbids guessing
        the data centre, because wd1 vs wd5 is a 404 and a 404 there is
        indistinguishable from a tenant with no open roles."""
        hits = self.find(
            "https://mountsinai.wd5.myworkdayjobs.com/MSHSCareers")
        self.assertEqual(hits, [("workday", {
            "token": "mountsinai", "workday_dc": "wd5",
            "workday_site": "MSHSCareers"})])

    def test_workday_locale_segment_is_not_the_site(self):
        """The one that silently breaks task 18.

        Workday URLs are optionally /{locale}/{site}. Capturing the first path
        segment records `en-US` as the site for every employer that includes
        it, and the CXS POST to /wday/cxs/{tenant}/en-US/jobs then 404s.
        """
        hits = self.find(
            "https://nyp.wd1.myworkdayjobs.com/en-US/NYPCareers/job/x")
        self.assertEqual(hits[0][1]["workday_site"], "NYPCareers")
        self.assertEqual(hits[0][1]["workday_dc"], "wd1")
        self.assertEqual(hits[0][1]["token"], "nyp")

    def test_workday_data_centre_is_lowercased_not_invented(self):
        hits = self.find("https://acme.WD3.myworkdayjobs.com/en-US/Ext")
        self.assertEqual(hits[0][1]["workday_dc"], "wd3")

    def test_lever_ashby_workable_recruitee_smartrecruiters(self):
        page = ("jobs.lever.co/citymeals "
                "https://jobs.ashbyhq.com/pursuit "
                "https://apply.workable.com/bkstreet/ "
                "https://foodbank.recruitee.com/o/analyst "
                "https://careers.smartrecruiters.com/NorthwellHealth")
        got = dict(ad.find_signatures(page))
        self.assertEqual(got["lever"]["token"], "citymeals")
        self.assertEqual(got["ashby"]["token"], "pursuit")
        self.assertEqual(got["workable"]["token"], "bkstreet")
        self.assertEqual(got["recruitee"]["token"], "foodbank")
        self.assertEqual(got["smartrecruiters"]["token"], "NorthwellHealth")

    def test_icims_careers_prefix_is_stripped_exactly_once(self):
        """`-` is in the token character class, so a naive pair of patterns
        matches careers-montefiore.icims.com twice -- as `montefiore` and as
        `careers-montefiore`. The second validates against
        careers-careers-montefiore.icims.com, 404s, and is stored as a `dead`
        row beside the valid one, which reads like an employer mid-migration
        rather than like a regex bug."""
        self.assertEqual(
            self.find("https://careers-montefiore.icims.com/jobs/search"),
            [("icims", {"token": "montefiore"})])

    def test_icims_bare_and_jobs_prefixed_forms(self):
        self.assertEqual(self.find("https://acme.icims.com/jobs"),
                         [("icims", {"token": "acme"})])
        self.assertEqual(self.find("https://jobs-nyplib.icims.com/x"),
                         [("icims", {"token": "nyplib"})])

    def test_duplicate_links_yield_one_row(self):
        """Careers pages link the same board four times. Each duplicate would
        otherwise cost a validation request against a stranger's API."""
        page = " ".join(["https://boards.greenhouse.io/nypl"] * 6)
        self.assertEqual(len(self.find(page, platform="greenhouse")), 1)

    def test_non_token_path_segments_are_rejected(self):
        for junk in ("https://boards.greenhouse.io/js/app.js",
                     "https://jobs.lever.co/static/x",
                     "https://www.icims.com/about"):
            self.assertEqual(
                ad.find_signatures(junk), [],
                f"{junk} produced a token that would be validated")

    def test_a_page_with_no_ats_yields_nothing(self):
        self.assertEqual(
            ad.find_signatures(
                "<html><body>Careers at Acme. Email hr@acme.org.</body></html>"),
            [])

    def test_signature_found_inside_a_js_bundle(self):
        """Single-page careers apps keep the board URL in a JS chunk, not in
        an <a href>. Matching URLs wherever they appear is deliberate."""
        self.assertEqual(
            self.find('var C={board:"https://jobs.ashbyhq.com/vnshealth",n:3}'),
            [("ashby", {"token": "vnshealth"})])


class ValidationEndpointTests(unittest.TestCase):

    def test_workday_limit_is_twenty(self):
        """CLAUDE.md's landmine. Workday returns an empty jobPostings array
        with no error for limit>20 -- byte-identical to "no more results", so
        asking for 100 would validate every live tenant as dead."""
        method, url, body = ad.validation_request(
            "workday", "mountsinai", workday_site="MSHSCareers",
            workday_dc="wd5")
        self.assertEqual(method, "POST")
        self.assertEqual(body["limit"], 20)
        self.assertEqual(
            url,
            "https://mountsinai.wd5.myworkdayjobs.com/wday/cxs/mountsinai/"
            "MSHSCareers/jobs")

    def test_workday_without_a_data_centre_is_not_guessed(self):
        self.assertIsNone(
            ad.validation_request("workday", "acme", workday_site="Ext"))

    def test_unvalidatable_platform_has_no_request(self):
        self.assertIsNone(ad.validation_request("taleo", "acme"))

    def test_every_validatable_platform_builds_a_request(self):
        for platform in ad.VALIDATABLE:
            req = ad.validation_request(platform, "tok", workday_site="Site",
                                        workday_dc="wd5")
            self.assertIsNotNone(req, platform)
            self.assertTrue(req[1].startswith("https://"), platform)


class JobCountTests(unittest.TestCase):

    def test_counts_per_platform_shape(self):
        self.assertEqual(ad.open_job_count("greenhouse", '{"jobs":[1,2,3]}'), 3)
        self.assertEqual(ad.open_job_count("lever", "[{},{}]"), 2)
        self.assertEqual(ad.open_job_count("recruitee", '{"offers":[1]}'), 1)

    def test_server_side_total_beats_page_length(self):
        """SmartRecruiters and Workday page. Reconciling against the total the
        API reported is the habit that keeps a throttled page from reading as
        the end of a list."""
        self.assertEqual(
            ad.open_job_count("workday",
                              '{"total": 1960, "jobPostings":[1,2,3]}'), 1960)
        self.assertEqual(
            ad.open_job_count("smartrecruiters",
                              '{"totalFound": 812, "content":[1]}'), 812)

    def test_unparseable_body_is_none_not_zero(self):
        """None means "could not tell" and 0 means "the board is empty". They
        take opposite statuses, so collapsing them is the bug."""
        self.assertIsNone(ad.open_job_count("greenhouse", "<html>nope</html>"))
        self.assertIsNone(ad.open_job_count("greenhouse", None))
        self.assertEqual(ad.open_job_count("greenhouse", '{"jobs":[]}'), 0)


class ClassificationTests(unittest.TestCase):
    """The silence distinction, asserted directly."""

    def test_a_live_board_is_valid_with_its_count(self):
        status, jobs, note = ad.classify_validation(
            "greenhouse", 200, '{"jobs":[1,2,3,4]}')
        self.assertEqual((status, jobs), (ad.STATUS_VALID, 4))
        self.assertIsNone(note)

    def test_404_is_dead(self):
        self.assertEqual(
            ad.classify_validation("greenhouse", 404, "")[0], ad.STATUS_DEAD)

    def test_empty_board_is_dead_not_valid(self):
        status, jobs, _ = ad.classify_validation("lever", 200, "[]")
        self.assertEqual((status, jobs), (ad.STATUS_DEAD, 0))

    def test_no_response_is_unvalidated_never_dead(self):
        """A validation request that never completed says nothing about the
        token. Writing it `dead` deletes evidence; writing it `valid` ships a
        token that contributes zero rows forever and looks healthy."""
        status, jobs, note = ad.classify_validation("greenhouse", None, None)
        self.assertEqual(status, ad.STATUS_UNVALIDATED)
        self.assertIsNone(jobs)
        self.assertIn("network", note)

    def test_403_and_429_are_unvalidated_never_dead(self):
        for code in (403, 429):
            self.assertEqual(
                ad.classify_validation("greenhouse", code, "")[0],
                ad.STATUS_UNVALIDATED, code)

    def test_5xx_is_unvalidated_never_dead(self):
        self.assertEqual(
            ad.classify_validation("greenhouse", 503, "")[0],
            ad.STATUS_UNVALIDATED)

    def test_200_that_is_not_a_feed_is_unvalidated(self):
        """A captive portal or a login wall answering 200 with HTML must not
        be read as an empty board."""
        status, jobs, note = ad.classify_validation(
            "greenhouse", 200, "<html><body>Sign in</body></html>")
        self.assertEqual(status, ad.STATUS_UNVALIDATED)
        self.assertIsNone(jobs)

    def test_detected_but_unvalidatable_platform(self):
        status, jobs, note = ad.classify_validation("taleo", None, None)
        self.assertEqual(status, ad.STATUS_UNVALIDATED)
        self.assertIn("taleo", note)

    def test_outcome_vocabulary_is_partitioned(self):
        """CONCLUSIVE and INCONCLUSIVE must stay disjoint and complete: the
        summary line counts them separately and a value in neither bucket
        would vanish from the report entirely."""
        conclusive, inconclusive = set(ad.CONCLUSIVE), set(ad.INCONCLUSIVE)
        self.assertEqual(conclusive & inconclusive, set())
        all_outcomes = {ad.FOUND, ad.NOT_FOUND, ad.BLOCKED, ad.UNREACHABLE,
                        ad.MISSING_PAGE, ad.NO_URL, ad.SKIPPED}
        self.assertEqual(conclusive | inconclusive, all_outcomes)


class RowTests(unittest.TestCase):

    def test_never_found_rows_do_not_collide(self):
        """They have no token, so keying them like a token row would hash
        ("","","") for every employer and collapse hundreds of them onto one
        row -- silently, since upsert would report the rest as `unchanged`."""
        a = ad.never_found_row("Mount Sinai", "https://a/careers", "T")
        b = ad.never_found_row("Northwell Health", "https://b/careers", "T")
        self.assertNotEqual(ad.make_row_id(a), ad.make_row_id(b))

    def test_a_token_row_is_keyed_by_the_board_not_the_employer(self):
        """Two spellings of an employer reaching the same board are one board
        and must be one row."""
        base = {"ats": "greenhouse", "token": "nyulangone",
                "workday_site": None}
        self.assertEqual(
            ad.make_row_id({**base, "employer_name": "NYU Langone"}),
            ad.make_row_id({**base, "employer_name": "NYU Langone Health"}))

    def test_workday_site_is_part_of_identity(self):
        """One tenant commonly runs several sites (external, internal,
        physicians). They are different feeds and different rows."""
        a = {"ats": "workday", "token": "nyp", "workday_site": "NYPCareers",
             "employer_name": "x"}
        b = {**a, "workday_site": "NYPPhysicians"}
        self.assertNotEqual(ad.make_row_id(a), ad.make_row_id(b))

    def test_never_found_row_carries_every_column(self):
        """lib/upsert binds COMPANY_ATS_COLUMNS as named parameters, so a
        record missing one fails that record rather than the batch
        (schema.py:118-120) -- and would do it silently before task 03."""
        row = ad.never_found_row("Acme", "https://acme.org/careers", "T")
        self.assertEqual(set(ad.COMPANY_ATS_COLUMNS) - set(row), set())
        self.assertEqual(row["status"], ad.STATUS_NEVER_FOUND)

    def test_hash_fields_exclude_last_validated_at(self):
        """It moves on every run by definition. Including it would report the
        monthly re-probe as hundreds of updated rows and bury the handful that
        actually moved."""
        self.assertNotIn("last_validated_at", ad.HASH_FIELDS_COMPANY_ATS)
        self.assertIn("open_jobs_at_validation", ad.HASH_FIELDS_COMPANY_ATS)

    def test_sticky_column_is_a_real_column(self):
        """TableSpec.__post_init__ raises otherwise -- a sticky column absent
        from `columns` would be read back and then never written."""
        for name in ad.STICKY_COMPANY_ATS:
            self.assertIn(name, ad.COMPANY_ATS_COLUMNS)


class DedupeTests(unittest.TestCase):
    """tools/ats-discover.py's dedupe_by_id, imported the way the migration
    tests import their subject -- the script has a hyphen in its name, so it
    is loaded by path rather than by `import`."""

    @classmethod
    def setUpClass(cls):
        import importlib.util
        path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "tools", "ats-discover.py")
        spec = importlib.util.spec_from_file_location("ats_discover_cli", path)
        cls.cli = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.cli)

    def test_two_employers_on_one_board_collapse_to_one_row(self):
        """Staten Island University Hospital and Northwell Health share a
        careers host; a health system's subsidiaries share its Workday tenant.
        Left in, the duplicate is written twice in one batch and the SECOND
        write lands -- and since apply_change_tracking keys on the row id, the
        loser carries open_jobs_changed_at=None and would blank it, disarming
        the 60-day stale-feed check for exactly the largest employers."""
        rows = [
            {"employer_name": "Northwell Health", "ats": "icims",
             "token": "northwell", "workday_site": None,
             "open_jobs_changed_at": "2026-01-01"},
            {"employer_name": "Staten Island University Hospital",
             "ats": "icims", "token": "northwell", "workday_site": None,
             "open_jobs_changed_at": None},
        ]
        out = self.cli.dedupe_by_id(rows)
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0]["employer_name"], "Northwell Health")

    def test_distinct_boards_survive(self):
        rows = [{"employer_name": "A", "ats": "greenhouse", "token": "a",
                 "workday_site": None},
                {"employer_name": "B", "ats": "greenhouse", "token": "b",
                 "workday_site": None}]
        self.assertEqual(len(self.cli.dedupe_by_id(rows)), 2)

    def test_flush_of_nothing_writes_nothing(self):
        """A run that found no tokens must not touch the table at all -- an
        empty batch reaching upsert would still emit an upsert-summary line
        and make `written 0` indistinguishable from `nothing to write`."""
        result = self.cli.flush(conn=None, records=[], now="T")
        self.assertEqual((result.new, result.updated, result.errors),
                         (0, 0, []))

    def test_the_spec_is_constructible(self):
        """TableSpec.__post_init__ validates identifiers and checks that every
        sticky column is in `columns`; a mismatch raises at import time in
        production and here instead."""
        spec = self.cli.company_ats_spec()
        self.assertEqual(spec.table, "company_ats")
        self.assertIn("first_validated_at", spec.columns)
        self.assertEqual(spec.sticky, ad.STICKY_COMPANY_ATS)

    def test_waf_body_behind_a_200_is_a_block(self):
        """lib/http.py records the same shape: a WAF answering 200 with
        "Request Rejected". Counting that as "page read, no ATS found" would
        write a never_found row on the strength of a block."""
        for body in ("<h1>Request Rejected</h1>",
                     "Attention Required! | Cloudflare",
                     "Access Denied"):
            self.assertTrue(self.cli._WAF_BODY.search(body), body)
        self.assertIsNone(
            self.cli._WAF_BODY.search("Careers at Acme Health"))


class CareersUrlTests(unittest.TestCase):

    def test_seeded_url_is_tried_first(self):
        got = ad.careers_url_candidates("https://mountsinai.org/work-here")
        self.assertEqual(got[0], "https://mountsinai.org/work-here")

    def test_fallbacks_stay_on_the_same_origin(self):
        for url in ad.careers_url_candidates("https://acme.org/x"):
            self.assertTrue(url.startswith("https://acme.org/"), url)

    def test_candidates_are_capped(self):
        """Three guesses is where the value stops and the impoliteness
        starts."""
        self.assertLessEqual(
            len(ad.careers_url_candidates("https://acme.org/x")),
            ad.MAX_URL_CANDIDATES)

    def test_no_url_yields_no_candidates(self):
        for empty in (None, "", "   "):
            self.assertEqual(ad.careers_url_candidates(empty), [])

    def test_bare_domain_is_schemed(self):
        self.assertEqual(
            ad.careers_url_candidates("acme.org/careers")[0],
            "https://acme.org/careers")

    def test_host_of(self):
        self.assertEqual(ad.host_of("https://Jobs.ACME.org/x"), "jobs.acme.org")
        self.assertEqual(ad.host_of(""), "")


if __name__ == "__main__":
    unittest.main()

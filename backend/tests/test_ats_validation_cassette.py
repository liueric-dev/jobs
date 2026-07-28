"""The task-16 validator, replayed against real ATS vendor bytes.

WHY THIS EXISTS SEPARATELY FROM tests/test_ats_discovery.py

    That file unit-tests `classify_validation()` -- given a status code and a
    body, what status comes out. It is fast, it is pure, and it cannot catch
    the thing that actually breaks: that the URL we build is the URL the
    vendor answers, and that the vendor's real refusal looks like what the
    classifier was written to expect.

    The validator's whole job is to stop the pipeline trusting a regex match
    found in a stale footer link (`16-ats-token-discovery.md:51-54`). A
    validator exercised only against boards that resolve would pass every test
    while being unable to tell a live board from a dead one -- so the
    non-resolving probes in this cassette are the ones that make the rest of
    it mean anything.

    And it must not be exercised against the LIVE endpoints, for the reason
    task 09's harness exists: a test that reaches the network fails on the day
    a vendor changes something, weeks after the commit that actually caused
    the failure, and passes on a laptop with no network only by accident.

WHAT IS RECORDED
    `evals/record_cassettes.py record_ats_validation()` -- ten probes across
    the eight ATS platforms `ats_discovery.VALIDATABLE` lists, driven through
    tools/ats-discover.py's OWN validate(), so the recorded request is by
    construction the request the discovery tool makes. Re-record with:

        python3 evals/record_cassettes.py ats-validation

FOUR SHAPES WORTH THE DISK SPACE
    * a live board (greenhouse/lever/ashby/workday) -> valid, with a count
    * a 404 board                                   -> dead
    * a 200 carrying an EMPTY list (SmartRecruiters does not 404 an unknown
      company) -> dead, which a status-code-only check would call valid
    * a WRONG Workday data centre -> 422, not 404, so `unvalidated`
"""

import hashlib
import importlib.util
import json
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import ats_discovery as ad  # noqa: E402
from evals import cassettes  # noqa: E402

CASSETTE = "ats-validation"


def _load_cli():
    path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "tools", "ats-discover.py")
    spec = importlib.util.spec_from_file_location("ats_discover_cli", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@unittest.skipUnless(cassettes.available(CASSETTE),
                     f"cassette {CASSETTE} not recorded; "
                     f"python3 evals/record_cassettes.py {CASSETTE}")
class AtsValidationCassetteTests(unittest.TestCase):
    """Replay the recorded vendor responses through the real validator."""

    @classmethod
    def setUpClass(cls):
        cls.cli = _load_cli()
        cls.cassette = cassettes.Cassette.load(CASSETTE)
        # A fixture recorded in July silently becomes the specification in
        # December unless somebody is told how old it is.
        print("\n" + cls.cassette.provenance_line())

    def _validate(self, platform, token, **extra):
        """One probe, served from the cassette. delay=0: the politeness pacing
        is a property of the live probe, not of replay, and a suite that
        sleeps is a suite people stop running."""
        with cassettes.replay(CASSETTE):
            fetcher = self.cli.Fetcher(delay=0, host_delay=0, timeout=1)
            return self.cli.validate(fetcher, platform,
                                     {"token": token, **extra})

    # -- boards that resolve -------------------------------------------------

    def test_live_greenhouse_board_is_valid_with_a_count(self):
        status, jobs, note = self._validate("greenhouse", "kickstarter")
        self.assertEqual(status, ad.STATUS_VALID)
        self.assertGreater(jobs, 0)
        self.assertIsNone(note)

    def test_live_lever_board_is_valid(self):
        status, jobs, _ = self._validate("lever", "finix")
        self.assertEqual(status, ad.STATUS_VALID)
        self.assertGreater(jobs, 0)

    def test_live_ashby_board_is_valid(self):
        status, jobs, _ = self._validate("ashby", "runway")
        self.assertEqual(status, ad.STATUS_VALID)
        self.assertGreater(jobs, 0)

    def test_live_workday_tenant_reports_the_server_side_total(self):
        """NVIDIA is the tenant CLAUDE.md's throttling landmine is about --
        "one published account lost 1,960 of 2,000 jobs". The count recorded
        here is `total`, not the length of the returned page, which is the
        whole point: reconciling against the number the API reported is what
        keeps a truncated page from reading as the end of the list."""
        status, jobs, _ = self._validate(
            "workday", "nvidia", workday_dc="wd5",
            workday_site="NVIDIAExternalCareerSite")
        self.assertEqual(status, ad.STATUS_VALID)
        self.assertGreater(jobs, 100)

        page = None
        for i in self.cassette.interactions:
            if "wd5" in i.url and i.status == 200:
                page = json.loads(i.body)
        self.assertIsNotNone(page)
        self.assertEqual(jobs, page["total"])
        self.assertLess(len(page["jobPostings"]), jobs,
                        "one page should be smaller than the total, or this "
                        "fixture no longer exercises pagination at all")

    # -- the reason the cassette exists -------------------------------------

    def test_a_board_that_does_not_resolve_is_dead(self):
        status, jobs, note = self._validate("greenhouse", "no-such-board-xyzzy")
        self.assertEqual(status, ad.STATUS_DEAD)
        self.assertIsNone(jobs)
        self.assertIn("404", note)

    def test_dead_is_never_never_found(self):
        """`never_found` is a claim about an EMPLOYER's careers page, made
        only after reading it. A validation 404 is a claim about a token. A
        validator that conflated them would let one bad token erase what the
        probe learned about the employer."""
        for platform, token in (("greenhouse", "no-such-board-xyzzy"),
                                ("recruitee", "no-such-tenant-xyzzy"),
                                ("icims", "no-such-tenant-xyzzy"),
                                ("workable", "no-such-account-xyzzy")):
            status, _, _ = self._validate(platform, token)
            self.assertNotEqual(status, ad.STATUS_NEVER_FOUND, platform)
            self.assertNotEqual(status, ad.STATUS_VALID, platform)

    def test_smartrecruiters_200_with_an_empty_list_is_not_valid(self):
        """SmartRecruiters does NOT 404 an unknown company -- it answers 200
        with totalFound=0. A validator that checked only the status code would
        record this as a live board that then contributes zero rows forever,
        which is indistinguishable from a quiet employer."""
        status, jobs, note = self._validate("smartrecruiters", "Ubisoft")
        self.assertEqual(status, ad.STATUS_DEAD)
        self.assertEqual(jobs, 0)
        self.assertIn("empty", note)

    def test_wrong_workday_data_centre_is_unvalidated_not_dead(self):
        """18-ingest-workday-cxs.md:54 forbids guessing the data centre. The
        recorded refusal is 422, not the 404 one would assume -- and 422 lands
        as `unvalidated`, which is the safe side: a guessed dc must never be
        able to mark a real tenant `dead` and retire it."""
        status, jobs, note = self._validate(
            "workday", "nvidia", workday_dc="wd1",
            workday_site="NVIDIAExternalCareerSite")
        self.assertEqual(status, ad.STATUS_UNVALIDATED)
        self.assertIsNone(jobs)

    # -- claims about the REQUEST, not the response --------------------------

    def test_the_recorded_workday_request_asked_for_twenty(self):
        """CLAUDE.md's landmine, pinned at the byte level.

        Workday returns an empty jobPostings array with NO error for
        limit > 20 -- byte-identical to "no more results" -- so an edit
        raising the limit would validate every live tenant in New York as
        dead, silently. Asserting the classifier is not enough: the claim is
        about what was SENT. The cassette stores a sha256 of each request
        body, so the exact payload is checkable without the body itself ever
        being on disk.
        """
        expected = hashlib.sha256(json.dumps(
            {"appliedFacets": {}, "limit": 20, "offset": 0, "searchText": ""}
        ).encode()).hexdigest()
        workday = [i for i in self.cassette.interactions
                   if i.method == "POST" and "myworkdayjobs.com" in i.url]
        self.assertTrue(workday, "no Workday interaction in the cassette")
        for i in workday:
            self.assertEqual(i.request_body_sha256, expected, i.url)

    def test_every_validatable_platform_is_covered(self):
        """The bullet this cassette was added for: one probe per ATS. A
        platform added to VALIDATABLE without a probe here would ship a
        validator nothing has ever run."""
        covered = set()
        for i in self.cassette.interactions:
            for platform in ad.VALIDATABLE:
                probe = ad.validation_request(
                    platform, "X", workday_site="S", workday_dc="wd5")
                if probe and _same_endpoint(probe[1], i.url):
                    covered.add(platform)
        self.assertEqual(set(ad.VALIDATABLE) - covered, set(),
                         "ATS platforms with a validator but no recorded probe")

    def test_the_cassette_holds_a_non_resolving_token(self):
        self.assertTrue(
            any(i.status == 404 for i in self.cassette.interactions),
            "no 404 recorded -- the validator would only ever have been "
            "exercised against endpoints that resolve")


def _same_endpoint(built, recorded):
    """Do two URLs name the same vendor endpoint, ignoring the token?

    Compares host plus the path's fixed segments, since the token is exactly
    what differs between the built probe and the recorded one.
    """
    import urllib.parse
    a, b = urllib.parse.urlsplit(built), urllib.parse.urlsplit(recorded)
    if a.netloc == b.netloc:
        return True
    # Per-tenant subdomains (recruitee, icims, workday) differ by token.
    return a.netloc.split(".", 1)[-1] == b.netloc.split(".", 1)[-1]


if __name__ == "__main__":
    unittest.main()

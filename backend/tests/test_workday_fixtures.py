"""The four Workday CXS silent failures each reproduce, before task 18 exists.

`docs/tasks/refactor/tranche_three/18-ingest-workday-cxs.md:41` requires that
each of the four "needs a cassette fixture from task 09 that reproduces it,
and a test that fails loudly". Task 09 owes the fixture. This file proves the
fixtures actually reproduce what they claim to, which is the part that can
silently stop being true -- a fixture that no longer triggers its own failure
is worse than no fixture, because it reads like coverage.

WHY THERE IS A LOOP IN THIS FILE

`_collect_naively` and `_collect_reconciled` below are NOT the ingest script
and must not become it. They are the two-line difference the whole task is
about: one treats a failed page as the end of the list, the other retries and
then compares what it collected against the `total` the API returned. Writing
both here is what lets the fixture demonstrate a 1,960-row loss today, with
nothing to import yet. When task 18 lands, these get deleted and its real
loop is driven through the same four fixtures.

The postings themselves are constructed rather than recorded, and
`evals/workday_fixtures.py` says so at length: `company_ats` has no Workday
tenant until task 16 runs, and you cannot ask a stranger's Akamai to throttle
you on demand. The SHAPES are quoted from 18-...md:20-37.
"""

import json
import os
import sys
import unittest
import urllib.error
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from evals import cassettes                                   # noqa: E402
from evals import workday_fixtures as wf                      # noqa: E402


class Reconciliation(RuntimeError):
    """Collected fewer postings than `total` said existed.

    18-ingest-workday-cxs.md:52: "a mismatch is an error, not a shrug."
    """


def _post(offset, limit=wf.PAGE_LIMIT, facets=None, dc=wf.DC):
    req = urllib.request.Request(
        wf.jobs_url(dc), data=wf.body(offset, limit, facets),
        headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=5) as resp:
        return json.loads(resp.read())


def _collect_naively(limit=wf.PAGE_LIMIT, facets=None, dc=wf.DC, max_pages=600):
    """The defect: any failure, or any short page, ends the walk."""
    collected, total, offset = [], None, 0
    for _ in range(max_pages):
        try:
            payload = _post(offset, limit, facets, dc)
        except urllib.error.HTTPError:
            break                       # <- "a throttled page is not the end"
        total = payload.get("total")
        postings = payload.get("jobPostings") or []
        if not postings:
            break
        collected.extend(postings)
        offset += limit
    return collected, total


def _collect_reconciled(limit=wf.PAGE_LIMIT, facets=None, dc=wf.DC,
                        max_pages=600, retries=3):
    """The fix: retry a failed page, then reconcile against `total`."""
    collected, total, offset = [], None, 0
    for _ in range(max_pages):
        payload = None
        for _attempt in range(retries):
            try:
                payload = _post(offset, limit, facets, dc)
                break
            except urllib.error.HTTPError:
                continue
        if payload is None:
            raise Reconciliation(f"page at offset {offset} never succeeded")
        total = payload.get("total")
        postings = payload.get("jobPostings") or []
        if not postings:
            break
        collected.extend(postings)
        offset += limit
    if total is not None and len(collected) != total:
        raise Reconciliation(
            f"collected {len(collected)} of {total} postings -- a page was "
            f"lost silently")
    return collected, total


class TestFailure1LimitCannotExceed20(unittest.TestCase):

    def test_limit_100_returns_an_empty_array_with_no_error(self):
        with cassettes.replay(cassette=wf.limit_over_20()):
            good = _post(0, limit=wf.PAGE_LIMIT)
            bad = _post(0, limit=100)
        self.assertEqual(len(good["jobPostings"]), wf.PAGE_LIMIT)
        self.assertEqual(bad["jobPostings"], [])
        self.assertNotIn("error", bad,
                         "if the response carried an error this would not be "
                         "a SILENT failure and would need no fixture")

    def test_it_is_indistinguishable_from_end_of_list_except_by_total(self):
        """Which is why reconciliation is the only detector for this one."""
        with cassettes.replay(cassette=wf.limit_over_20()):
            bad = _post(0, limit=100)
        end_of_list = {"total": wf.TOTAL, "jobPostings": []}
        self.assertEqual(bad, end_of_list)
        self.assertEqual(bad["total"], wf.TOTAL,
                         "`total` is the one field that still tells the truth")

    def test_a_naive_walk_at_limit_100_collects_nothing_and_reports_success(self):
        with cassettes.replay(cassette=wf.limit_over_20()):
            collected, total = _collect_naively(limit=100)
        self.assertEqual(collected, [])
        self.assertEqual(total, wf.TOTAL)

    def test_reconciliation_catches_it(self):
        with cassettes.replay(cassette=wf.limit_over_20()):
            with self.assertRaises(Reconciliation) as caught:
                _collect_reconciled(limit=100)
        self.assertIn(f"0 of {wf.TOTAL}", str(caught.exception))


class TestFailure2AThrottledPageIsNotTheEnd(unittest.TestCase):

    def test_a_naive_walk_loses_1960_of_2000(self):
        """The published NVIDIA number, reproduced exactly."""
        with cassettes.no_sleep(), cassettes.replay(
                cassette=wf.throttled_page()):
            collected, total = _collect_naively()
        self.assertEqual(len(collected), wf.THROTTLE_AT_OFFSET)
        self.assertEqual(total, wf.TOTAL)
        self.assertEqual(total - len(collected), 1960)

    def test_retrying_and_reconciling_collects_all_2000(self):
        with cassettes.no_sleep(), cassettes.replay(
                cassette=wf.throttled_page()):
            collected, total = _collect_reconciled()
        self.assertEqual(len(collected), wf.TOTAL)
        self.assertEqual(total, wf.TOTAL)

    def test_the_throttled_response_carries_retry_after(self):
        """So lib/http.py:78 backs off on it rather than raising, which is
        the cheap half of the fix -- use lib/http, do not hand-roll urlopen
        the way four of the six existing scripts do."""
        from lib import http
        with cassettes.no_sleep(), cassettes.replay(
                cassette=wf.throttled_page()):
            payload = http.post_json(
                wf.jobs_url(),
                json.loads(wf.body(wf.THROTTLE_AT_OFFSET).decode()))
        self.assertEqual(len(payload["jobPostings"]), wf.PAGE_LIMIT)


class TestFailure3TheDataCentrePrefixVaries(unittest.TestCase):

    def test_the_assumed_prefix_404s_while_the_stored_one_works(self):
        with cassettes.replay(cassette=wf.prefix_assumed()):
            with self.assertRaises(urllib.error.HTTPError) as caught:
                _post(0, dc=wf.WRONG_DC)
            good = _post(0, dc=wf.DC)
        self.assertEqual(caught.exception.code, 404)
        self.assertEqual(len(good["jobPostings"]), wf.PAGE_LIMIT)

    def test_a_wrong_prefix_reads_as_one_more_unreachable_tenant(self):
        """Why this counts as silent. Every ingest script in this repo catches
        HTTPError per source and continues -- ats.py:333-338 is the template
        Phase 3 copies -- so a hardcoded `wd1` costs a whole tenant and
        produces one line in a fifty-line noise floor."""
        with cassettes.replay(cassette=wf.prefix_assumed()):
            collected, total = _collect_naively(dc=wf.WRONG_DC)
        self.assertEqual(collected, [])
        self.assertIsNone(total, "nothing was ever learned about this tenant")

    def test_the_prefix_is_not_guessable_from_the_tenant(self):
        """wd1/wd3/wd5 are data centres, not a function of the name. The
        fixture pins that the fixture itself does not use wd1, so a test
        written against it cannot accidentally pass by defaulting."""
        self.assertNotEqual(wf.DC, wf.WRONG_DC)
        self.assertIn(wf.WRONG_DC, wf.host(wf.WRONG_DC))


class TestFailure4TheTenThousandResultCap(unittest.TestCase):

    def test_an_unfaceted_walk_stops_at_the_cap_and_looks_finished(self):
        with cassettes.replay(cassette=wf.result_cap()):
            collected, total = _collect_naively()
        self.assertEqual(len(collected), wf.RESULT_CAP)
        self.assertEqual(total, wf.CAPPED_TOTAL)
        self.assertEqual(total - len(collected), wf.CAPPED_TOTAL - wf.RESULT_CAP)

    def test_reconciliation_detects_the_cap_but_cannot_fix_it(self):
        """The distinction that decides the design: for failures 1 and 2 the
        reconciliation check IS the fix. Here it only tells you to slice."""
        with cassettes.replay(cassette=wf.result_cap()):
            with self.assertRaises(Reconciliation):
                _collect_reconciled()

    def test_a_faceted_slice_enumerates_completely(self):
        with cassettes.replay(cassette=wf.result_cap()):
            collected, total = _collect_reconciled(facets=wf.FACET)
        self.assertEqual(len(collected), wf.FACETED_TOTAL)
        self.assertEqual(total, wf.FACETED_TOTAL)
        self.assertLess(total, wf.RESULT_CAP)


class TestTheFixturesMatchTheDocumentedShape(unittest.TestCase):
    """If Workday's contract changes, these fail here rather than in task 18.

    Everything asserted is quoted from 18-ingest-workday-cxs.md:20-37, so a
    reviewer can diff the doc against the code without reading either twice.
    """

    def test_the_request_is_the_documented_body(self):
        self.assertEqual(json.loads(wf.body(40).decode()),
                         {"appliedFacets": {}, "limit": 20, "offset": 40,
                          "searchText": ""})

    def test_the_url_is_the_documented_endpoint(self):
        self.assertEqual(
            wf.jobs_url(),
            f"https://{wf.TENANT}.{wf.DC}.myworkdayjobs.com"
            f"/wday/cxs/{wf.TENANT}/{wf.SITE}/jobs")

    def test_a_posting_carries_every_field_the_normalizer_will_want(self):
        p = wf.posting(7)
        for field in ("title", "locationsText", "externalPath", "startDate",
                      "jobRequisitionLocation"):
            self.assertIn(field, p)
        # startDate is native ISO -- 18-...md:29, "no 'posted 3 days ago'
        # parsing", which is why this source does not need
        # text.parse_relative_posted_at at all.
        self.assertRegex(p["startDate"], r"^\d{4}-\d{2}-\d{2}$")

    def test_the_public_job_url_is_built_the_documented_way(self):
        path = wf.posting(3)["externalPath"]
        self.assertEqual(wf.job_url(path),
                         f"{wf.host()}/en-US/{wf.SITE}{path}")

    def test_all_four_fixtures_are_registered_and_distinct(self):
        built = {n: f() for n, f in wf.FIXTURES.items()}
        self.assertEqual(sorted(built), [1, 2, 3, 4])
        self.assertEqual(len({c.name for c in built.values()}), 4)
        for number, cassette in built.items():
            with self.subTest(failure=number):
                self.assertTrue(cassette.interactions)
                self.assertIn("CONSTRUCTED", cassette.source,
                              "a constructed fixture must say so")
                self.assertTrue(cassette.note)


if __name__ == "__main__":
    unittest.main()

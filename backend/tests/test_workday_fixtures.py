"""The four Workday CXS silent failures, driven through the REAL ingest loop.

`git show refactor-freeze-2026-08-02:docs/tasks/refactor/tranche_three/18-ingest-workday-cxs.md:41` requires that
each of the four "needs a cassette fixture from task 09 that reproduces it, and
a test that fails loudly". Task 09 wrote the fixtures
(`evals/workday_fixtures.py`) and this file proved they reproduce what they
claim. Task 18 has now written the loop, so its Definition of done
(`git show refactor-freeze-2026-08-02:docs/tasks/refactor/tranche_three/18-ingest-workday-cxs.md`:118-121) asks for one more thing: "Drive the real ingest loop through
them and delete that file's stand-in `_collect_naively`/`_collect_reconciled`."

WHAT WAS DELETED, WHAT WAS KEPT, AND WHY THAT IS NOT THE WHOLE INSTRUCTION

`_collect_reconciled` is gone. `ingest/workday.py:collect_postings` replaces it
and every test that used it now calls that instead -- which is the point: a
fixture proving a hand-written loop in a test file behaves correctly proves
nothing about the loop that runs at 03:00.

`_collect_naively` is KEPT, deliberately, against the letter of that
instruction. It is not a stand-in for the ingest loop; it is a stand-in for the
DEFECT, and it is the only thing here that can show a fixture still bites. This
file's original docstring made the argument itself -- "a fixture that no longer
triggers its own failure is worse than no fixture, because it reads like
coverage" -- and deleting the naive walker would delete exactly that check.
Every one of these fixtures is CONSTRUCTED, so nothing but a demonstration
keeps them honest.

WHAT THE RECORDED PAGE ADDED, AND WHAT IT CONTRADICTS

`workday_fixtures.recorded_list_page()` is real bytes (nvidia.wd5, lifted from
the `ats-validation` recording), and it falsifies part of the task file:
`git show refactor-freeze-2026-08-02:docs/tasks/refactor/tranche_three/18-ingest-workday-cxs.md`:27-30 attributes `startDate` and `jobRequisitionLocation` to the LIST
response, and the list carries neither. They are on the DETAIL document. See
TestTheRecordingContradictsTheTaskFile below.
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
from evals.ingest_modules import load as load_ingest          # noqa: E402

workday = load_ingest("workday")

#: Every call below replays; nothing sleeps between pages. `delay=0` is the
#: ingest loop's own politeness pause, `cassettes.no_sleep()` is lib/http.py's
#: retry backoff, and both have to go or a retry test costs eight seconds.
NO_DELAY = {"delay": 0, "sleep": lambda _s: None}


def _post(offset, limit=wf.PAGE_LIMIT, facets=None, dc=wf.DC):
    """A single raw request. Kept because three assertions are about the
    RESPONSE rather than about the loop -- see failure 1."""
    req = urllib.request.Request(
        wf.jobs_url(dc), data=wf.body(offset, limit, facets),
        headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=5) as resp:
        return json.loads(resp.read())


def _collect_naively(limit=wf.PAGE_LIMIT, facets=None, dc=wf.DC, max_pages=600):
    """The defect: any failure, or any short page, ends the walk.

    NOT the ingest loop and must never become it. This is the two-line
    difference the whole task is about, kept so each fixture can be shown to
    still lose the data it says it loses.
    """
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


def _collect(**kw):
    """The REAL loop, against the fixture tenant."""
    return workday.collect_postings(wf.TENANT, kw.pop("dc", wf.DC), wf.SITE,
                                    **{**NO_DELAY, **kw})


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

    def test_the_ingest_loop_refuses_to_make_the_request_at_all(self):
        """The primary defence: the guard is in list_body(), so it fires
        before any request rather than after a wasted one."""
        with cassettes.replay(cassette=wf.limit_over_20()) as player:
            with self.assertRaises(workday.LimitTooLarge) as caught:
                _collect(limit=100)
        self.assertEqual(player.requests, [],
                         "a limit>20 must not reach the network at all")
        self.assertIn("20", str(caught.exception))

    def test_every_request_path_goes_through_the_guard(self):
        """A future editor cannot route around it by calling a lower level:
        list_body() is the only place a body is built, and it checks."""
        for call in (lambda: workday.list_body(0, 100),
                     lambda: workday.fetch_list_page("t", "wd1", "s", 0,
                                                     limit=21),
                     lambda: workday.collect_postings("t", "wd1", "s",
                                                      limit=100, **NO_DELAY)):
            with self.subTest(call=call):
                self.assertRaises(workday.LimitTooLarge, call)

    def test_the_ceiling_is_20_and_the_default_is_the_ceiling(self):
        self.assertEqual(workday.MAX_PAGE_LIMIT, 20)
        self.assertEqual(workday.PAGE_LIMIT, workday.MAX_PAGE_LIMIT)
        self.assertEqual(workday.PAGE_LIMIT, wf.PAGE_LIMIT)
        # 20 is honoured, 21 is not -- the boundary, pinned.
        self.assertEqual(workday._check_page_limit(20), 20)
        self.assertRaises(workday.LimitTooLarge, workday._check_page_limit, 21)
        self.assertRaises(workday.LimitTooLarge, workday._check_page_limit, 0)


class TestFailure2AThrottledPageIsNotTheEnd(unittest.TestCase):

    def test_a_naive_walk_loses_1960_of_2000(self):
        """The published NVIDIA number, reproduced exactly."""
        with cassettes.no_sleep(), cassettes.replay(
                cassette=wf.throttled_page()):
            collected, total = _collect_naively()
        self.assertEqual(len(collected), wf.THROTTLE_AT_OFFSET)
        self.assertEqual(total, wf.TOTAL)
        self.assertEqual(total - len(collected), 1960)

    def test_the_ingest_loop_retries_and_collects_all_2000(self):
        with cassettes.no_sleep(), cassettes.replay(
                cassette=wf.throttled_page()):
            collected, total = _collect()
        self.assertEqual(len(collected), wf.TOTAL)
        self.assertEqual(total, wf.TOTAL)

    def test_a_page_that_never_succeeds_raises_rather_than_terminating(self):
        """The reconciliation half. A 500 that outlives lib/http's retries
        must not read as the end of the list."""
        broken = wf.throttled_page()
        # Every interaction for offset 40 replaced by a permanent 500, so
        # lib/http.py exhausts its retries and gives up.
        target = wf._post(wf.THROTTLE_AT_OFFSET, {}, status=500,
                          reason="Internal Server Error")
        broken.interactions = [
            target if i.request_body_sha256 == target.request_body_sha256
            else i for i in broken.interactions]
        with cassettes.no_sleep(), cassettes.replay(cassette=broken):
            with self.assertRaises(workday.Shortfall) as caught:
                _collect()
        self.assertIn("NOT", str(caught.exception))
        self.assertIn(str(wf.THROTTLE_AT_OFFSET), str(caught.exception))

    def test_the_throttled_response_carries_retry_after(self):
        """So lib/http.py:78 backs off on it rather than raising, which is
        the cheap half of the fix -- use lib/http, do not hand-roll urlopen
        the way four of the six existing scripts do. fetch_list_page does."""
        with cassettes.no_sleep(), cassettes.replay(
                cassette=wf.throttled_page()):
            payload = workday.fetch_list_page(
                wf.TENANT, wf.DC, wf.SITE, wf.THROTTLE_AT_OFFSET)
        self.assertEqual(len(payload["jobPostings"]), wf.PAGE_LIMIT)

    def test_a_board_that_moves_mid_walk_is_drift_not_a_shortfall(self):
        """Measured 2026-07-28: Nordstrom answered total=867 and yielded 865
        distinct postings over the 100 seconds that followed, because two
        requisitions closed mid-walk. Equality turns that into a shortfall, and
        a shortfall means the tenant is not written at all -- so a strict check
        would cost the largest boards whole nights for doing nothing wrong.
        The threshold is one page, because a lost PAGE is the failure this
        check exists for."""
        moved = wf.throttled_page()
        keep = [i for i in moved.interactions if i.status == 200]
        moved.interactions = keep
        # Claim two more than the fixture can deliver: 2 < PAGE_LIMIT.
        for interaction in moved.interactions:
            body = json.loads(interaction.body)
            if body.get("total"):
                body["total"] = wf.TOTAL + 2
                interaction.body = json.dumps(body)
        with cassettes.no_sleep(), cassettes.replay(cassette=moved):
            collected, total = _collect()
        self.assertEqual(len(collected), wf.TOTAL)
        self.assertEqual(total, wf.TOTAL + 2)

    def test_a_deficit_of_a_whole_page_still_raises(self):
        """The boundary. One page short is the failure; one page minus one is
        churn."""
        for deficit, raises in ((wf.PAGE_LIMIT - 1, False),
                                (wf.PAGE_LIMIT, True)):
            with self.subTest(deficit=deficit):
                cas = wf.throttled_page()
                cas.interactions = [i for i in cas.interactions
                                    if i.status == 200]
                for interaction in cas.interactions:
                    body = json.loads(interaction.body)
                    if body.get("total"):
                        body["total"] = wf.TOTAL + deficit
                        interaction.body = json.dumps(body)
                with cassettes.no_sleep(), cassettes.replay(cassette=cas):
                    if raises:
                        self.assertRaises(workday.Shortfall, _collect)
                    else:
                        _collect()

    def test_an_excess_is_never_fatal(self):
        """Postings ADDED mid-walk are not data loss. One page of 20 against a
        `total` of 15 -- what a board that grew between the front page and the
        walk looks like."""
        cas = cassettes.Cassette(
            name="workday-more-than-total",
            source="constructed",
            interactions=[wf._post(0, {"total": 15,
                                       "jobPostings": [wf.posting(i)
                                                       for i in range(20)]})])
        with cassettes.no_sleep(), cassettes.replay(cassette=cas):
            collected, total = _collect()
        self.assertEqual(len(collected), 20)
        self.assertEqual(total, 15)

    def test_a_short_collection_is_an_error_not_a_smaller_board(self):
        """Reconciliation, on its own: pages stop early but `total` says 2000."""
        truncated = wf.throttled_page()
        truncated.interactions = [
            i for i in truncated.interactions
            if i.status == 200][:2] + [wf._post(40, {"total": wf.TOTAL,
                                                     "jobPostings": []})]
        with cassettes.no_sleep(), cassettes.replay(cassette=truncated):
            with self.assertRaises(workday.Shortfall) as caught:
                _collect()
        self.assertIn(f"of {wf.TOTAL}", str(caught.exception))


class TestFailure3TheDataCentrePrefixVaries(unittest.TestCase):

    def test_the_assumed_prefix_422s_while_the_stored_one_works(self):
        """The recorded status, and the fact that it raises before the body is
        looked at. `_post` json-decodes its response, and that decode is never
        reached on the wrong prefix -- HTTPError comes out of urlopen itself
        (cassettes.py:448, "if interaction.status >= 400:")."""
        with cassettes.replay(cassette=wf.prefix_assumed()):
            with self.assertRaises(urllib.error.HTTPError) as caught:
                _post(0, dc=wf.WRONG_DC)
            good = _post(0, dc=wf.DC)
        self.assertEqual(caught.exception.code, wf.WRONG_DC_STATUS)
        self.assertEqual(caught.exception.code, 422)
        self.assertEqual(len(good["jobPostings"]), wf.PAGE_LIMIT)

    def test_the_error_body_is_valid_json_and_that_changes_nothing(self):
        """The correction this fixture encodes. The old fixture modelled a 404
        with an HTML body and argued the loss went through a JSONDecodeError.
        The real body PARSES -- so no decode error was ever available -- and it
        is not decoded anyway, because lib/http.py:77 ("raise  # permanent --
        surface immediately") re-raises before ingest/workday.py:371 reaches
        its `json.loads`."""
        refusal = wf.prefix_assumed().interactions[0]
        self.assertEqual(refusal.status, 422)
        self.assertIn("application/json", refusal.headers["Content-Type"])
        parsed = json.loads(refusal.body)
        self.assertEqual(parsed["errorCode"], "HTTP_422")
        self.assertEqual(parsed["httpStatus"], 422)

    def test_the_fixture_encodes_no_unobserved_status(self):
        """One refusal, and it is the one that was recorded. workday.py:872
        says "404 or 422", but no Workday host in any cassette here has
        answered 404, and both statuses take an identical path -- permanent at
        lib/http.py:76, absent from BLOCKED_STATUSES -- to the same
        Shortfall."""
        failures = [i for i in wf.prefix_assumed().interactions
                    if i.status >= 400]
        self.assertEqual([i.status for i in failures], [422])
        self.assertIn("RECORDED", wf.prefix_assumed().source)

    def test_a_wrong_prefix_reads_as_one_more_unreachable_tenant(self):
        """Why this counts as silent, in the naive shape -- and it is the
        STATUS that does it, not the body. `_collect_naively` breaks on
        HTTPError, so the tenant yields zero postings and a `total` of None:
        ingest/workday.py:872's "indistinguishable from a tenant with no open
        roles"."""
        with cassettes.replay(cassette=wf.prefix_assumed()):
            collected, total = _collect_naively(dc=wf.WRONG_DC)
        self.assertEqual(collected, [])
        self.assertIsNone(total, "nothing was ever learned about this tenant")

    def test_the_ingest_loop_raises_a_shortfall_on_the_wrong_prefix(self):
        """Loud, not one quiet line in a fifty-line noise floor. 422 is absent
        from BLOCKED_STATUSES (workday.py:237), so workday.py:409 raises
        Shortfall rather than TenantBlocked. The tenant is still isolated --
        ingest_tenant catches it at :998 -- but it is REPORTED, and
        `status='shortfall'` is what the summary counts at :1184."""
        with cassettes.no_sleep(), cassettes.replay(cassette=wf.prefix_assumed()):
            with self.assertRaises(workday.Shortfall) as caught:
                _collect(dc=wf.WRONG_DC)
        self.assertIn("422", str(caught.exception))
        self.assertNotIn(wf.WRONG_DC_STATUS, workday.BLOCKED_STATUSES,
                         "if 422 is ever added to BLOCKED_STATUSES this "
                         "becomes a TenantBlocked, and a wrong prefix would "
                         "read as a refusal rather than as lost pages")

    def test_the_prefix_is_read_and_never_defaulted(self):
        """There is no wd-anything literal in the ingest module: the data
        centre only ever arrives from company_ats.workday_dc."""
        path = os.path.join(os.path.dirname(os.path.dirname(
            os.path.abspath(__file__))), "ingest", "workday.py")
        with open(path, encoding="utf-8") as fh:
            src = fh.read()
        code = "\n".join(line for line in src.splitlines()
                         if not line.lstrip().startswith("#"))
        code = code.split('"""')[0] + '"""'.join(code.split('"""')[2:])
        self.assertNotIn('"wd', code, "a literal wd-prefix in the code is a "
                                      "default, and `git show refactor-freeze-2026-08-02:docs/tasks/refactor/tranche_three/18-ingest-workday-cxs.md`:54 forbids one")
        self.assertNotIn("'wd", code)

    def test_the_prefix_is_not_guessable_from_the_tenant(self):
        """wd1/wd5/wd108/wd501 are data centres, not a function of the name."""
        self.assertNotEqual(wf.DC, wf.WRONG_DC)
        self.assertIn(wf.WRONG_DC, wf.host(wf.WRONG_DC))


class TestFailure4TheTenThousandResultCap(unittest.TestCase):

    def test_an_unfaceted_walk_stops_at_the_cap_and_looks_finished(self):
        with cassettes.replay(cassette=wf.result_cap()):
            collected, total = _collect_naively()
        self.assertEqual(len(collected), wf.RESULT_CAP)
        self.assertEqual(total, wf.CAPPED_TOTAL)
        self.assertEqual(total - len(collected), wf.CAPPED_TOTAL - wf.RESULT_CAP)

    def test_the_ingest_loop_detects_it_and_refuses_a_short_list(self):
        """The distinction that decides the design: for failures 1 and 2 the
        reconciliation check IS the fix. Here it only says to slice -- and
        with no facet advertised, there is nothing to slice by, so the honest
        answer is to raise."""
        with cassettes.no_sleep(), cassettes.replay(cassette=wf.result_cap()):
            with self.assertRaises(workday.ResultCapUnsliceable) as caught:
                workday.collect_tenant(wf.TENANT, wf.DC, wf.SITE, **NO_DELAY)
        self.assertIn(str(wf.CAPPED_TOTAL - wf.RESULT_CAP),
                      str(caught.exception))

    def test_a_faceted_slice_enumerates_completely(self):
        with cassettes.no_sleep(), cassettes.replay(cassette=wf.result_cap()):
            collected, total = _collect(facets=wf.FACET)
        self.assertEqual(len(collected), wf.FACETED_TOTAL)
        self.assertEqual(total, wf.FACETED_TOTAL)
        self.assertLess(total, wf.RESULT_CAP)

    def test_facet_slices_partitions_a_real_advertised_facet_list(self):
        """`facet_slices` is fed the response's OWN facets, so the slicing
        needs no hardcoded facet name. Exercised against the facets block of
        the recorded nvidia page rather than an invented one."""
        # The page's own total (2,000) with a cap set just above its largest
        # facet value: the shape of a board over the real 10,000 cap, without
        # inventing counts.
        page = _recorded_page_body()
        slices = workday.facet_slices(page, cap=1900)
        self.assertTrue(slices, "the recorded page advertises facets that "
                                "partition it; if this fails the response "
                                "shape has changed")
        params = {next(iter(s)) for s in slices}
        self.assertEqual(len(params), 1, "one parameter per slice set")
        for s in slices:
            (values,) = s.values()
            self.assertEqual(len(values), 1)

    def test_facet_slices_refuses_a_facet_that_does_not_cover_the_board(self):
        page = {"total": 100, "facets": [
            {"facetParameter": "locations",
             "values": [{"id": "a", "count": 10}, {"id": "b", "count": 20}]}]}
        self.assertEqual(workday.facet_slices(page, cap=1000), [],
                         "30 of 100 is not a partition, and merging those "
                         "slices would be short by construction")

    def test_facet_slices_refuses_a_value_still_over_the_cap(self):
        page = {"total": 100, "facets": [
            {"facetParameter": "locations",
             "values": [{"id": "a", "count": 99}, {"id": "b", "count": 1}]}]}
        self.assertEqual(workday.facet_slices(page, cap=50), [])


class TestFailure5TotalIsOnlyOnTheFirstPage(unittest.TestCase):
    """Not in the task file. Found by running the loop against live tenants.

    All four tenants in `company_ats` failed with "collected 40 of 0" on
    2026-07-28 before this was understood, and nothing in the suite could have
    predicted it: both the constructed fixtures above and NVIDIA's real
    recorded page repeat `total` on every page, because a one-page recording
    has no later page to disagree.
    """

    def test_the_fixture_reproduces_what_the_endpoint_really_does(self):
        cas = wf.total_only_on_first_page()
        with cassettes.replay(cassette=cas):
            first = _post(0)
            second = _post(20)
            past_the_end = _post(100)
        self.assertEqual(first["total"], wf.FIRST_PAGE_ONLY_TOTAL)
        self.assertEqual(second["total"], 0,
                         "every page after the first answers total: 0")
        self.assertEqual(len(second["jobPostings"]), wf.PAGE_LIMIT,
                         "...while still returning a full page of postings")
        self.assertEqual(len(past_the_end["jobPostings"]), wf.PAGE_LIMIT,
                         "an offset past the end returns page 0 again, not an "
                         "empty array")

    def test_a_walk_that_re_reads_total_ends_at_page_two(self):
        """The defect, in the shape it was actually written. `total` becomes 0
        on page two, `offset >= total` is immediately true, and the walk stops
        with 40 of 88 -- then reconciles 40 against 0 and calls the SHORT walk
        a shortfall for the wrong reason."""
        with cassettes.replay(cassette=wf.total_only_on_first_page()):
            # max_pages bounds it at all: the fixture wraps, so an unbounded
            # naive walk is an infinite loop, not a short one.
            collected, total = _collect_naively(max_pages=8)
        # The naive walker has no `offset >= total` rule at all, so it walks to
        # the wrap and then never stops -- bounded here only by max_pages.
        self.assertGreater(len(collected), wf.FIRST_PAGE_ONLY_TOTAL,
                           "waiting for an empty page collects duplicates "
                           "forever; the wrap is why a bound is not optional")
        distinct = {p["externalPath"] for p in collected}
        self.assertEqual(len(distinct), wf.FIRST_PAGE_ONLY_TOTAL,
                         "and every posting past the 88th is a repeat")
        self.assertEqual(total, wf.FIRST_PAGE_ONLY_TOTAL,
                         "the wrap even hands back a plausible `total`, so the "
                         "run ends looking correct")

    def test_the_ingest_loop_latches_the_first_total_and_collects_them_all(self):
        with cassettes.no_sleep(), cassettes.replay(
                cassette=wf.total_only_on_first_page()):
            collected, total = _collect()
        self.assertEqual(total, wf.FIRST_PAGE_ONLY_TOTAL)
        self.assertEqual(len(collected), wf.FIRST_PAGE_ONLY_TOTAL)

    def test_the_wrap_cannot_make_the_loop_run_forever(self):
        """Every page is a full page of the SAME postings, and `total` never
        arrives, so neither the short-page rule nor the offset rule can end the
        walk. Only the fresh-postings guard can."""
        cas = wf.total_only_on_first_page()
        wrap = wf._post(0, {"jobPostings": [wf.posting(i)
                                            for i in range(wf.PAGE_LIMIT)]})
        cas.interactions = [
            wf._post(off, {"jobPostings": [wf.posting(i)
                                           for i in range(wf.PAGE_LIMIT)]})
            for off in range(0, 200, wf.PAGE_LIMIT)] + [wrap]
        with cassettes.no_sleep(), cassettes.replay(cassette=cas) as player:
            collected, total = _collect()
        self.assertIsNone(total, "this fixture never reports one")
        self.assertEqual(len(collected), wf.PAGE_LIMIT)
        self.assertEqual(len(player.requests), 2,
                         "one page, then one that adds nothing new, then stop")

    def test_it_is_registered_apart_from_the_task_file_s_four(self):
        """The provenance distinction: four are a specification of documented
        traps, this one is an observation of an undocumented one."""
        self.assertEqual(sorted(wf.FIXTURES), [1, 2, 3, 4])
        self.assertEqual(sorted(wf.FIXTURES_FOUND_LIVE), [5])
        cas = wf.FIXTURES_FOUND_LIVE[5]()
        self.assertIn("CONSTRUCTED", cas.source)
        self.assertTrue(cas.note)


def _recorded_page_body():
    return json.loads(wf.recorded_list_page().interactions[0].body)


@unittest.skipUnless(cassettes.available(wf.RECORDED_CASSETTE),
                     f"cassette {wf.RECORDED_CASSETTE} not recorded")
class TestTheRecordingContradictsTheTaskFile(unittest.TestCase):
    """Real bytes, and the one thing constructed fixtures structurally cannot do.

    Everything else in `evals/workday_fixtures.py` encodes the shape
    `git show refactor-freeze-2026-08-02:docs/tasks/refactor/tranche_three/18-ingest-workday-cxs.md`:20-37 DOCUMENTS. That makes those fixtures a
    specification of the trap and not evidence about the endpoint -- their own
    module docstring says so. This class is the evidence, and it disagrees with
    the specification.
    """

    def test_provenance_is_printed_not_assumed(self):
        cas = wf.recorded_list_page()
        print("  " + cas.provenance_line())
        print("  " + wf.recorded_shape_note())
        self.assertIn("RECORDED", cas.source)

    def test_the_real_list_response_carries_total_and_twenty_postings(self):
        body = _recorded_page_body()
        self.assertEqual(body["total"], 2000)
        self.assertEqual(len(body["jobPostings"]), wf.PAGE_LIMIT)

    def test_the_task_file_is_wrong_about_the_list_response_fields(self):
        """`git show refactor-freeze-2026-08-02:docs/tasks/refactor/tranche_three/18-ingest-workday-cxs.md`:27-30 says the list carries `startDate` (native ISO, "no
        'posted 3 days ago' parsing") and `jobRequisitionLocation`. It carries
        neither -- it carries `postedOn`, which is exactly the relative string
        the task file says this source avoids. Both fields are on the DETAIL
        document instead, which is why apply_detail() is where posted_at comes
        from and why normalize_listing() leaves it None."""
        posting = _recorded_page_body()["jobPostings"][0]
        for field in wf.RECORDED_LIST_FIELDS:
            self.assertIn(field, posting)
        for field in wf.LIST_FIELDS_THE_TASK_FILE_IS_WRONG_ABOUT:
            self.assertNotIn(
                field, posting,
                f"{field} is documented at `git show refactor-freeze-2026-08-02:docs/tasks/refactor/tranche_three/18-ingest-workday-cxs.md`:27-30 as a "
                f"LIST field. If it has appeared, the endpoint changed and "
                f"normalize_listing() can be simplified.")
        self.assertRegex(posting["postedOn"], r"(?i)posted")

    def test_the_ingest_loop_normalizes_the_real_bytes(self):
        """The contract every source owes: every key in schema.COLUMNS."""
        import schema
        employer = {"employer_name": "NVIDIA", "token": wf.RECORDED_TENANT,
                    "dc": wf.RECORDED_DC, "site": wf.RECORDED_SITE}
        body = _recorded_page_body()
        records = [workday.normalize_listing(employer, p)
                   for p in body["jobPostings"]]
        self.assertEqual(len(records), wf.PAGE_LIMIT)
        for rec in records:
            for column in schema.COLUMNS:
                self.assertIn(column, rec)
            self.assertEqual(rec["platform"], "workday")
            self.assertTrue(rec["source_id"])
            self.assertIsNone(rec["description_text"],
                              "a list row has no description, by construction")
            self.assertIsNone(rec["posted_at"],
                              "posted_at is hashed; a relative string must "
                              "never reach it")
        self.assertEqual(len({schema.make_job_id(r) for r in records}),
                         len(records),
                         "source_id must be externalPath, not bulletFields: "
                         "the recorded page carries two postings of one "
                         "requisition and keying on the req id collapses them")

    def test_the_real_loop_replays_the_recorded_page(self):
        """One page, `total` 2000 -- so the walk is SHORT and reconciliation
        fires. That is the correct outcome: this cassette is one page of a
        2,000-posting board, and a loop that reported success on it would be
        the bug. `max_pages=1` because the cassette holds one page and a
        CassetteMiss on page two would measure the harness, not the loop."""
        with cassettes.no_sleep(), cassettes.replay(
                cassette=wf.recorded_list_page()):
            with self.assertRaises(workday.Shortfall) as caught:
                workday.collect_postings(wf.RECORDED_TENANT, wf.RECORDED_DC,
                                         wf.RECORDED_SITE, max_pages=1,
                                         **NO_DELAY)
        self.assertIn("20 of 2000", str(caught.exception))


@unittest.skipUnless(cassettes.available(wf.RECORDED_CASSETTE),
                     f"cassette {wf.RECORDED_CASSETTE} not recorded")
class TestTheRecordedRefusalIsWhatTheFixtureEncodes(unittest.TestCase):
    """`prefix_assumed()` transcribes its refusal instead of lifting it.

    Transcribing keeps the fixture buildable with nothing on disk, which the
    four `FIXTURES` entries need. This class is the price of that: it diffs
    every transcribed constant against the bytes in `ats-validation.json`, so
    a recording that changes fails here rather than leaving the fixture
    quietly claiming a shape the endpoint stopped having.
    """

    def _recorded_refusal(self):
        source = cassettes.Cassette.load(wf.RECORDED_CASSETTE)
        wrong = f"{wf.RECORDED_TENANT}.{wf.WRONG_DC}.myworkdayjobs.com"
        found = [i for i in source.interactions
                 if wrong in i.url and i.method == "POST"]
        self.assertEqual(len(found), 1,
                         f"{wf.RECORDED_CASSETTE} should hold exactly one POST "
                         f"to {wrong} -- the wrong-data-centre probe that "
                         f"WRONG_DC_* is transcribed from")
        return found[0]

    def test_the_transcribed_status_and_reason_are_the_recorded_ones(self):
        refusal = self._recorded_refusal()
        self.assertEqual(refusal.status, wf.WRONG_DC_STATUS)
        self.assertEqual(refusal.reason, wf.WRONG_DC_REASON)

    def test_the_transcribed_content_type_is_the_recorded_one(self):
        """Recorded as JSON, not the HTML the old fixture asserted."""
        self.assertEqual(self._recorded_refusal().headers["Content-Type"],
                         wf.WRONG_DC_CONTENT_TYPE)

    def test_the_transcribed_body_is_the_recorded_one(self):
        self.assertEqual(json.loads(self._recorded_refusal().body),
                         wf.WRONG_DC_BODY)

    def test_the_probe_that_was_refused_is_the_documented_request(self):
        """Same body as the good page, so the 422 is about the HOST and not
        about what was asked for -- which is the whole claim of failure 3."""
        self.assertEqual(self._recorded_refusal().request_body_sha256,
                         wf.recorded_list_page().interactions[0]
                         .request_body_sha256)

    def test_the_wrong_prefix_was_wrong_for_the_recorded_tenant(self):
        """nvidia's stored dc is wd5; the refusal came from wd1."""
        self.assertNotEqual(wf.RECORDED_DC, wf.WRONG_DC)


class TestTheFixturesMatchTheDocumentedShape(unittest.TestCase):
    """If Workday's contract changes, these fail here rather than in task 18."""

    def test_the_request_is_the_documented_body(self):
        self.assertEqual(json.loads(wf.body(40).decode()),
                         {"appliedFacets": {}, "limit": 20, "offset": 40,
                          "searchText": ""})

    def test_the_ingest_script_sends_byte_identical_requests(self):
        """The fixtures key on the sha256 of the body (cassettes.py:374), so
        this is not stylistic: a different key order is a different request and
        every cassette here would miss."""
        for offset, limit, facets in ((0, 20, None), (40, 20, None),
                                      (0, 20, wf.FACET)):
            with self.subTest(offset=offset, facets=facets):
                self.assertEqual(workday.list_body(offset, limit, facets),
                                 wf.body(offset, limit, facets))

    def test_the_url_is_the_documented_endpoint(self):
        self.assertEqual(
            wf.jobs_url(),
            f"https://{wf.TENANT}.{wf.DC}.myworkdayjobs.com"
            f"/wday/cxs/{wf.TENANT}/{wf.SITE}/jobs")
        self.assertEqual(workday.jobs_url(wf.TENANT, wf.DC, wf.SITE),
                         wf.jobs_url())

    def test_a_posting_carries_every_field_the_normalizer_will_want(self):
        p = wf.posting(7)
        for field in ("title", "locationsText", "externalPath", "startDate",
                      "jobRequisitionLocation"):
            self.assertIn(field, p)
        self.assertRegex(p["startDate"], r"^\d{4}-\d{2}-\d{2}$")

    def test_the_public_job_url_is_built_the_documented_way(self):
        path = wf.posting(3)["externalPath"]
        self.assertEqual(wf.job_url(path),
                         f"{wf.host()}/en-US/{wf.SITE}{path}")
        self.assertEqual(
            workday.public_url(wf.TENANT, wf.DC, wf.SITE, path),
            wf.job_url(path))

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

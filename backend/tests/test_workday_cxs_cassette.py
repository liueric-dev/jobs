"""The recorded msk.wd108 walk: failure 5, from real bytes rather than a mock.

WHY THIS FILE EXISTS SEPARATELY FROM test_workday_fixtures.py
    That file drives `collect_postings` / `collect_tenant` through five
    CONSTRUCTED failure fixtures. Constructed fixtures prove the code handles
    the behaviour someone remembered; they cannot prove the behaviour is still
    real, and failure 5 -- `total` on the first page only -- is the one that
    is not in the task file at all. It was found live on 2026-07-28 and until
    now the only fixture for it was one the pipeline wrote itself.

    `docs/ingest/workday.md:553-557` asked for a recording that closes that
    gap. `evals/record_cassettes.py record_workday_cxs()` makes it; this
    replays it.

WHAT THE BYTES SAY (recorded 2026-07-28, msk.wd108/MSKCC_Careers_Primary)
    Four list pages at limit=20 -- totals 79, 0, 0, 0 -- and one detail
    document. The board was 87 open reqs when `company_ats` last validated it
    and 79 when this was recorded; that churn is why nothing here asserts an
    exact posting count against the database.

EVERY ASSERTION IS ABOUT THE RECORDING, NOT ABOUT A MOCK. If Workday ever
starts reporting `total` on every page, `test_total_is_reported_on_the_first
_page_only` fails on re-record and the latch at workday.py:476 can be
revisited on evidence.
"""

import json
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from evals import cassettes  # noqa: E402
from evals.ingest_modules import load as load_ingest  # noqa: E402

CASSETTE = "workday-cxs"
TENANT, DC, SITE = "msk", "wd108", "MSKCC_Careers_Primary"


@unittest.skipUnless(cassettes.available(CASSETTE),
                     f"no {CASSETTE} cassette; record it with "
                     f"`python3 evals/record_cassettes.py {CASSETTE}`")
class WorkdayCxsCassette(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.workday = load_ingest("workday")
        cls.cassette = cassettes.Cassette.load(CASSETTE)

    def _list_pages(self):
        return [i for i in self.cassette.interactions
                if i.method == "POST" and i.url.endswith("/jobs")]

    # -- the recording itself -----------------------------------------------

    def test_the_recording_is_a_multi_page_walk(self):
        """A one-page cassette would pin nothing recorded_list_page() does not."""
        self.assertGreaterEqual(len(self._list_pages()), 3)

    def test_total_is_reported_on_the_first_page_only(self):
        """Failure 5, in bytes from a live tenant.

        This is the assertion the whole cassette is for. It is deliberately
        made against the RESPONSE bodies rather than against what
        collect_postings returns: the parser could latch the first total
        correctly while the upstream behaviour had changed underneath it, and
        then the fixture would be pinning the workaround instead of the
        problem it works around.
        """
        totals = [json.loads(i.raw.decode("utf-8")).get("total")
                  for i in self._list_pages()]
        self.assertTrue(totals[0], f"first page reported total={totals[0]}")
        self.assertEqual([0] * (len(totals) - 1), totals[1:],
                         f"later pages reported {totals[1:]}, not all zero -- "
                         f"failure 5 may no longer be real; see "
                         f"workday.py:463-475 before changing the latch")

    def test_every_recorded_page_was_asked_for_at_the_production_limit(self):
        """The limit<=20 landmine, checked from the REQUEST side.

        CLAUDE.md: "Workday `limit` cannot exceed 20. Ask for 100 and it
        returns an empty array with no error." The recorded response bodies
        cannot show that -- an over-limit request and an exhausted board
        return the same bytes. What CAN show it is what was sent, and a POST
        is keyed in this harness on the sha256 of its body
        (cassettes.py:222-223). So: rebuild the body `list_body` produces at
        each offset the walk would use, and require the recording to hold
        exactly those digests.

        Same technique docs/ingest/workday.md:542-547 used to establish that
        `recorded_list_page()` is the request ats.py actually makes.
        """
        import hashlib
        recorded = {i.request_body_sha256 for i in self._list_pages()}
        limit = self.workday.PAGE_LIMIT
        self.assertLessEqual(limit, self.workday.MAX_PAGE_LIMIT)
        for page_no in range(len(self._list_pages())):
            body = self.workday.list_body(page_no * limit, limit=limit)
            # list_body() already returns encoded bytes -- it is handed
            # straight to urllib as the request body.
            digest = hashlib.sha256(body).hexdigest()
            self.assertIn(
                digest, recorded,
                f"no recorded interaction was requested with "
                f"list_body(offset={page_no * limit}, limit={limit}) -- the "
                f"cassette does not hold the request production sends")

    # -- the real walk, over the real bytes ----------------------------------

    def test_collect_tenant_walks_the_recorded_board(self):
        with cassettes.no_sleep(), cassettes.replay(CASSETTE) as player:
            postings, total = self.workday.collect_tenant(TENANT, DC, SITE, delay=0)
        pages = len(self._list_pages())
        # Every posting the board reported, and no shortfall raised -- which
        # is only true because the first total is latched.
        self.assertEqual(total, len(postings))
        self.assertGreater(len(postings), self.workday.PAGE_LIMIT,
                           "a single page is not a walk")
        # One request per recorded page, plus the detail fetch if it was made.
        self.assertGreaterEqual(len(player.requests), pages)

    def test_the_walk_ends_on_a_short_page_not_on_an_empty_one(self):
        """79 postings is 3.95 pages; the last one is short.

        The distinction matters because `collect_postings` treats a short page
        as the end of the list (workday.py:497-501) and an offset past the end
        does NOT return an empty page -- it wraps to page one. A cassette
        whose walk ended exactly on a page boundary would exercise neither.
        """
        with cassettes.no_sleep(), cassettes.replay(CASSETTE):
            postings, _total = self.workday.collect_tenant(TENANT, DC, SITE, delay=0)
        self.assertNotEqual(0, len(postings) % self.workday.PAGE_LIMIT,
                            "the recorded board divides evenly into pages, so "
                            "the short-page terminator is untested by it")

    def test_externalPaths_are_distinct(self):
        """No duplicate survived the walk.

        The dedupe at workday.py:479-487 is what makes the reconciliation
        compare DISTINCT postings against `total` -- without it a repeated
        posting satisfies the count while a real one is missing.
        """
        with cassettes.no_sleep(), cassettes.replay(CASSETTE):
            postings, _ = self.workday.collect_tenant(TENANT, DC, SITE, delay=0)
        paths = [p.get("externalPath") for p in postings]
        self.assertEqual(len(paths), len(set(paths)))

    def test_a_detail_document_was_recorded_and_normalizes(self):
        """The list page + detail join, over real bytes for both halves."""
        with cassettes.no_sleep(), cassettes.replay(CASSETTE):
            postings, _ = self.workday.collect_tenant(TENANT, DC, SITE, delay=0)
            detail = self.workday.fetch_detail(
                TENANT, DC, SITE, postings[0]["externalPath"])
        self.assertIn("jobPostingInfo", detail)
        # normalize_listing takes the company_ats ROW, not a name: it needs
        # token/dc/site to build the public URL (workday.py:672-674).
        employer = {"token": TENANT, "dc": DC, "site": SITE,
                    "employer_name": "Memorial Sloan Kettering Cancer Center"}
        rec = self.workday.normalize_listing(employer, postings[0])
        rec = self.workday.apply_detail(rec, detail, listing=postings[0])
        self.assertTrue(rec.get("title"))
        self.assertTrue(rec.get("description_text"),
                        "the detail document carried no description -- the "
                        "whole reason the detail call is budgeted")


if __name__ == "__main__":
    unittest.main()

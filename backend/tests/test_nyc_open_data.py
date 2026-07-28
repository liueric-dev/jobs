"""ingest/nyc-open-data.py -- the Socrata crawl, its arithmetic, its closures.

WHAT IS PINNED HERE AND WHY EACH ONE EARNS ITS PLACE

  * **A short page is not the end of a list.** SODA answers a throttled
    request and a last page with the same shape: fewer rows than were asked
    for. The whole design answer is reconcile(), so it is tested three ways
    -- as pure arithmetic, against the real recorded crawl, and against a
    DERIVED cassette in which the middle page comes back empty. That last
    one is the failure CLAUDE.md's landmine describes ("one published
    account lost 1,960 of 2,000 jobs"), reproduced rather than argued.

  * **A 429 mid-crawl must not end the crawl.** lib/http.py retries it, but
    that is only true as long as this script keeps going through
    lib/http.py; a derived cassette holds the 429 and asserts the crawl
    still completes and still reconciles.

  * **Closure is written from `post_until`, not from the clock.** The date
    in `closed_at` is the City's published deadline. That is the property
    that makes this source better than the other six, and it is one UPDATE
    away from being silently replaced by utc_now_str().

  * **The Internal filter.** 1,146 of 2,376 rows on 2026-07-28 are postings
    open only to existing City employees. The recorded slice deliberately
    contains both kinds so the filter has something to drop.

OFFLINE except where it says otherwise. Every HTTP test replays a committed
cassette and `cassettes.CassetteMiss` is fatal, so an unrecorded request
fails rather than quietly going back to the network. The database tests skip
when there is no Postgres rather than passing vacuously.
"""

import copy
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import schema                                                  # noqa: E402
from evals import cassettes, scratchdb                         # noqa: E402
from evals.cassettes import Cassette, Interaction              # noqa: E402
from evals.ingest_modules import load as load_ingest           # noqa: E402
from evals.record_cassettes import (NYC_OPEN_DATA_PAGE_SIZE,   # noqa: E402
                                    NYC_OPEN_DATA_WHERE)
from lib import envfile                                        # noqa: E402
from lib.upsert import upsert_checked                          # noqa: E402

#: The pipeline's own .env, the way run-daily.py loads it -- copied from
#: tests/test_scratchdb.py:63-66 for the same reason: a test must not depend
#: on the caller having exported anything.
envfile.load(os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), ".env"))

CASSETTE = "nyc-open-data"

#: The recorded slice's size. Asserted rather than assumed, so that a
#: re-recording that lost half the rows fails here instead of quietly
#: weakening every test below.
RECORDED_ROWS = 49

requires_db = unittest.skipUnless(
    scratchdb.available(),
    "no scratch database: set DATABASE_URL (or JOBS_SCRATCH_DATABASE_URL)")

require_cassette = unittest.skipUnless(
    cassettes.available(CASSETTE),
    f"cassette {CASSETTE} not recorded -- "
    f"`python3 evals/record_cassettes.py {CASSETTE}`")

_ANNOUNCED = set()


def replaying():
    """Replay the cassette, printing its provenance once per process.

    Same rule as tests/test_ingest_cassettes.py:45-50: a fixture recorded in
    July becomes December's specification whether anyone meant it to or not.
    """
    if CASSETTE not in _ANNOUNCED:
        _ANNOUNCED.add(CASSETTE)
        print("  " + Cassette.load(CASSETTE).provenance_line())
    return cassettes.replay(CASSETTE)


def crawl(nyc):
    """The recorded count/crawl/count, through the script's own functions."""
    before = nyc.fetch_count(where=NYC_OPEN_DATA_WHERE)
    fetched = nyc.fetch_all(where=NYC_OPEN_DATA_WHERE,
                            page_size=NYC_OPEN_DATA_PAGE_SIZE, delay=0)
    after = nyc.fetch_count(where=NYC_OPEN_DATA_WHERE)
    return before, fetched, after


class NYCOpenDataTest(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.nyc = load_ingest("nyc-open-data")


# ---------------------------------------------------------------------------
# reconcile() -- pure, so the shapes that matter can be tested directly
# ---------------------------------------------------------------------------

class TestReconcile(NYCOpenDataTest):

    def test_a_complete_crawl_reconciles(self):
        self.assertTrue(self.nyc.reconcile(2376, 2376, 2376).ok)

    def test_a_throttled_first_page_does_not_read_as_the_end_of_the_list(self):
        """The landmine, as arithmetic. 40 rows arrived, 2,000 exist; without
        a count to check against, `len(batch) < limit` says "done"."""
        checked = self.nyc.reconcile(40, 2000, 2000)
        self.assertFalse(checked.ok)
        self.assertEqual(checked.shortfall, 1960)
        self.assertIn("TRUNCATED", checked.note)
        self.assertIn("refusing to close", checked.note)

    def test_a_dataset_that_moved_during_the_crawl_still_reconciles(self):
        """DCAS republishes in batches; a row withdrawn between the count and
        the last page is a difference of one, not a truncation."""
        checked = self.nyc.reconcile(2375, 2376, 2375)
        self.assertTrue(checked.ok)
        self.assertIn("dataset moved", checked.note)

    def test_collecting_more_than_either_count_is_not_an_error(self):
        checked = self.nyc.reconcile(2380, 2376, 2378)
        self.assertTrue(checked.ok)
        self.assertIn("over the higher count", checked.note)

    def test_the_allowance_has_an_absolute_floor_for_small_slices(self):
        """2% of 49 is zero, so without RECONCILE_FLOOR a one-row edit in a
        small `$where` slice would fail every run."""
        self.assertTrue(self.nyc.reconcile(46, 49, 49).ok)
        self.assertFalse(self.nyc.reconcile(20, 49, 49).ok)

    def test_an_empty_dataset_reconciles_only_against_zero(self):
        self.assertTrue(self.nyc.reconcile(0, 0, 0).ok)
        self.assertFalse(self.nyc.reconcile(7, 0, 0).ok)

    def test_zero_rows_against_a_real_count_is_the_loudest_failure(self):
        """The shape a revoked endpoint or a renamed dataset takes: 200 OK,
        empty array, no exception anywhere. CLAUDE.md: "Silence is this
        system's failure mode."."""
        self.assertFalse(self.nyc.reconcile(0, 2376, 2376).ok)


# ---------------------------------------------------------------------------
# normalization -- pure
# ---------------------------------------------------------------------------

class TestParsing(NYCOpenDataTest):

    def test_post_until_parses_the_one_shape_the_dataset_uses(self):
        self.assertEqual(self.nyc.parse_post_until("12-SEP-2026"), "2026-09-12")
        self.assertEqual(self.nyc.parse_post_until("01-jan-2027"), "2027-01-01")

    def test_an_unreadable_deadline_is_None_rather_than_a_guess(self):
        """A deadline that cannot be read must fall through to
        disappearance-based closure, never close a posting early."""
        for bad in (None, "", "2026-09-12", "32-SEP-2026", "12-XXX-2026",
                    "SEP-2026", "soon"):
            self.assertIsNone(self.nyc.parse_post_until(bad), bad)

    def test_the_deadline_day_itself_is_still_open(self):
        """"Post until 12-SEP" means applications are taken THROUGH the
        twelfth, so the comparison is strictly less-than."""
        record = {"post_until": "2026-09-12"}
        self.assertFalse(self.nyc.is_expired(record, "2026-09-11"))
        self.assertFalse(self.nyc.is_expired(record, "2026-09-12"))
        self.assertTrue(self.nyc.is_expired(record, "2026-09-13"))

    def test_a_posting_with_no_deadline_is_never_expired(self):
        self.assertFalse(self.nyc.is_expired({"post_until": None}, "2030-01-01"))

    def test_all_three_description_fields_are_concatenated(self):
        text = self.nyc.description_of({
            "job_description": "the narrative",
            "minimum_qual_requirements": "a baccalaureate degree",
            "preferred_skills": "python, prompt engineering",
        })
        for fragment in ("the narrative", "a baccalaureate degree",
                         "python, prompt engineering"):
            self.assertIn(fragment, text)

    def test_preferred_skills_survives_extract_pys_3000_char_cut(self):
        """The reordering argued for at DESCRIPTION_PARTS, asserted.

        extract.py:180 caps its prompt at 3,000 characters and extract.py:257
        applies it. Measured over 400 External postings, `job_description`
        alone has a median of 3,946 characters -- so under the field order
        the task file states, `preferred_skills` lands past the cut on 83% of
        the postings that have one, and the field the concatenation exists to
        capture never reaches the model.
        """
        text = self.nyc.description_of({
            "job_description": "narrative " * 1000,
            "minimum_qual_requirements": "quals",
            "preferred_skills": "machine learning",
        })
        self.assertIn("machine learning", text[:3000])
        self.assertGreater(len(text), 3000, "this fixture must be long enough "
                                            "for the cut to bite")

    def test_missing_description_fields_are_skipped_not_blank_headed(self):
        text = self.nyc.description_of({"job_description": "only this"})
        self.assertNotIn("PREFERRED SKILLS", text)
        self.assertIn("only this", text)
        self.assertIsNone(self.nyc.description_of({}))

    def test_salary_is_the_stated_band(self):
        self.assertEqual(
            self.nyc.salary_text({"salary_range_from": "60000",
                                  "salary_range_to": "65000",
                                  "salary_frequency": "Annual"}),
            "$60,000-$65,000 Annual")
        self.assertEqual(
            self.nyc.salary_text({"salary_range_from": "16.5",
                                  "salary_range_to": "16.5",
                                  "salary_frequency": "Hourly"}),
            "$16.50 Hourly")
        self.assertIsNone(self.nyc.salary_text({"salary_frequency": "Annual"}))

    def test_a_street_address_is_still_new_york_city(self):
        """text.NYC_PATTERN matched only 340 of 1,230 work_location values
        (27.6%). Deriving location_is_nyc from it would file most of the City
        of New York's own postings as not-in-New-York, and
        config/relevance.json's location_columns is exactly
        [location_is_nyc, location_is_remote]."""
        from lib import text as libtext
        for address in ("100 Gold Street", "City Hall", "Rikers Island",
                        "30-30 Thomson Ave L I City Qns"):
            self.assertIsNone(libtext.NYC_PATTERN.search(address),
                              f"{address} would not need the override")
            record = self.nyc.normalize({"job_id": "1", "agency": "DDC",
                                         "business_title": "Analyst",
                                         "work_location": address})
            self.assertTrue(record["location_is_nyc"])

    def test_career_level_is_carried_but_never_written_as_a_column(self):
        """The task file is explicit: career_level is a free independent
        label on a field task 06 found unstable, and is worth more to task 07
        as a check on extract.py than as a shortcut around it."""
        record = self.nyc.normalize({"job_id": "1", "agency": "DDC",
                                     "business_title": "Analyst",
                                     "career_level": "Entry-Level"})
        self.assertEqual(record["career_level"], "Entry-Level")
        self.assertNotIn("career_level", schema.COLUMNS)
        self.assertNotIn("career_level", self.nyc.HASH_FIELDS)


class TestDedupe(NYCOpenDataTest):
    """`job_id` is not unique in this dataset, and the twins disagree.

    Found by running the ingest for real on 2026-07-28: 1,230 External rows,
    1,219 distinct job_ids, and two of the duplicate pairs held one expired
    and one live deadline. The first run wrote the live twin and then closed
    it from the expired twin's date.
    """

    def _row(self, job_id, post_until, title="Analyst"):
        return {"job_id": job_id, "agency": "DEPT OF ENVIRONMENTAL PROT",
                "business_title": title, "post_until": post_until}

    def test_twins_collapse_to_one_row(self):
        records = [self.nyc.normalize(self._row("781780", "25-JUL-2026")),
                   self.nyc.normalize(self._row("781780", "13-SEP-2026"))]
        self.assertEqual(len(self.nyc.dedupe(records)), 1)

    def test_the_later_deadline_wins_whichever_order_they_arrive_in(self):
        early = self.nyc.normalize(self._row("781780", "25-JUL-2026"))
        late = self.nyc.normalize(self._row("781780", "13-SEP-2026"))
        for pair in ([early, late], [late, early]):
            kept = self.nyc.dedupe(pair)
            self.assertEqual(kept[0]["post_until"], "2026-09-13")

    def test_no_deadline_outranks_every_deadline(self):
        """No `post_until` means open-ended, which is later than any date --
        and the safe direction, because the rule decides what may CLOSE a
        posting."""
        dated = self.nyc.normalize(self._row("781780", "13-SEP-2026"))
        undated = self.nyc.normalize(self._row("781780", None))
        for pair in ([dated, undated], [undated, dated]):
            self.assertIsNone(self.nyc.dedupe(pair)[0]["post_until"])

    def test_a_live_twin_is_never_closed_by_its_expired_twin(self):
        """The defect, stated as the property that prevents it."""
        records = self.nyc.dedupe([
            self.nyc.normalize(self._row("781780", "25-JUL-2026")),
            self.nyc.normalize(self._row("781780", "13-SEP-2026"))])
        expired = [r for r in records if self.nyc.is_expired(r, "2026-07-28")]
        self.assertEqual(expired, [])

    def test_different_agencies_are_different_postings(self):
        """The primary key is (platform, company_token, source_id), so the
        same job_id under two agencies is two rows, not a collision."""
        first = self.nyc.normalize(self._row("1", "13-SEP-2026"))
        second = self.nyc.normalize({"job_id": "1", "agency": "DEPT OF FINANCE",
                                     "business_title": "Analyst",
                                     "post_until": "13-SEP-2026"})
        self.assertEqual(len(self.nyc.dedupe([first, second])), 2)

    def test_distinct_postings_are_untouched(self):
        records = [self.nyc.normalize(self._row(str(i), "13-SEP-2026"))
                   for i in range(5)]
        self.assertEqual(len(self.nyc.dedupe(records)), 5)


# ---------------------------------------------------------------------------
# the recorded crawl
# ---------------------------------------------------------------------------

@require_cassette
class TestRecordedCrawl(NYCOpenDataTest):

    def test_the_crawl_paginates_and_reconciles(self):
        with replaying() as player:
            before, fetched, after = crawl(self.nyc)
        self.assertEqual(len(fetched.rows), RECORDED_ROWS)
        self.assertEqual((before, after), (RECORDED_ROWS, RECORDED_ROWS))
        self.assertEqual(fetched.pages, 3, "the recorded slice is three pages")
        self.assertFalse(fetched.hit_page_cap)
        self.assertTrue(self.nyc.reconcile(len(fetched.rows), before, after).ok)
        # Every page asked for a stable order. Without it Socrata may serve a
        # different row order per request, and offset paging then both skips
        # and duplicates rows -- which reconcile() cannot see, because the
        # COUNT still matches.
        pages = [url for _m, url in player.requests if "%24offset" in url]
        self.assertEqual(len(pages), 3)
        for url in pages:
            self.assertIn("%24order=job_id", url)

    def test_every_external_record_satisfies_the_column_contract(self):
        """schema.py:118-120: "Every normalize_* function must supply every
        key here: upsert binds them as named parameters, so a missing one
        fails that record"."""
        with replaying():
            _before, fetched, _after = crawl(self.nyc)
        records = [self.nyc.normalize(r) for r in fetched.rows
                   if r.get("posting_type") == self.nyc.EXTERNAL]
        self.assertTrue(records)
        for record in records:
            missing = [c for c in schema.COLUMNS if c not in record]
            self.assertEqual(missing, [], f"record is missing {missing}")
            self.assertEqual(record["platform"], "nyc_open_data")
            self.assertTrue(record["title"])
            self.assertTrue(record["source_id"])
            self.assertTrue(record["job_url"].startswith(self.nyc.JOB_URL_BASE))
            self.assertTrue(schema.make_job_id(record))
        ids = [schema.make_job_id(r) for r in records]
        self.assertEqual(len(ids), len(set(ids)),
                         "two records share a primary key")

    def test_internal_postings_are_present_and_are_dropped(self):
        """Both halves matter: the filter must fire, and the fixture must be
        able to prove it fired."""
        with replaying():
            _before, fetched, _after = crawl(self.nyc)
        kinds = [r.get("posting_type") for r in fetched.rows]
        self.assertIn(self.nyc.INTERNAL, kinds)
        external = [r for r in fetched.rows
                    if r.get("posting_type") == self.nyc.EXTERNAL]
        self.assertLess(len(external), len(fetched.rows))
        self.assertEqual(len(fetched.rows) - len(external),
                         kinds.count(self.nyc.INTERNAL))

    def test_a_null_post_until_normalizes_to_no_deadline_and_never_expires(self):
        """The recorded slice IS the null-post_until slice, so this is the
        edge case task 14 asks for, on real bytes rather than invented ones.
        These rows fall through to disappearance-based closure."""
        with replaying():
            _before, fetched, _after = crawl(self.nyc)
        records = [self.nyc.normalize(r) for r in fetched.rows]
        self.assertTrue(all(r.get("post_until") is None for r in fetched.rows))
        self.assertTrue(all(r["post_until"] is None for r in records))
        self.assertFalse(any(self.nyc.is_expired(r, "2099-01-01")
                             for r in records))

    def test_an_unrecorded_request_is_not_a_live_call(self):
        with replaying():
            with self.assertRaises(cassettes.CassetteMiss):
                self.nyc.fetch_page(0, limit=999, where="agency='NOWHERE'")


# ---------------------------------------------------------------------------
# derived cassettes -- the failures no live endpoint will perform on demand
# ---------------------------------------------------------------------------

def _with_page_replaced(name, offset, body, status=200):
    """The recorded cassette with one page's response swapped out.

    DERIVED IN CODE, NOT COMMITTED AS A SECOND FILE -- the argument
    tests/test_ingest_cassettes.py:436-447 makes for Apify's
    immediate-success fixture. A committed copy silently stops matching the
    recording it came from the first time either is re-recorded.
    """
    original = Cassette.load(name)
    interactions = []
    for recorded in original.interactions:
        if f"%24offset={offset}" in recorded.url:
            interactions.append(Interaction(
                method=recorded.method, url=recorded.url, status=status,
                headers=recorded.headers, body=body,
                reason="derived: throttled page"))
        else:
            interactions.append(copy.copy(recorded))
    return Cassette(name=f"{name}+offset{offset}={status}",
                    source=original.source, recorded_at=original.recorded_at,
                    note="derived from the recording", interactions=interactions)


def _with_page_prefixed(name, offset, body, status):
    """The recorded cassette with an extra response BEFORE one page's."""
    original = Cassette.load(name)
    interactions = []
    for recorded in original.interactions:
        if f"%24offset={offset}" in recorded.url and status:
            interactions.append(Interaction(
                method=recorded.method, url=recorded.url, status=status,
                headers=recorded.headers, body=body,
                reason="derived: rate limited"))
            status = None          # only once, before the first match
        interactions.append(copy.copy(recorded))
    return Cassette(name=f"{name}+429", source=original.source,
                    recorded_at=original.recorded_at,
                    note="derived from the recording",
                    interactions=interactions)


@require_cassette
class TestAThrottledPageIsNotTheEndOfTheList(NYCOpenDataTest):

    def test_an_empty_middle_page_reads_as_the_end_and_is_caught(self):
        """The landmine, reproduced end to end.

        The second page comes back `[]` -- a 200, no error, the exact shape
        of a last page. fetch_all() stops, as it must: it cannot tell the
        difference. What catches it is the count, and this asserts both
        halves: that the crawl DOES stop short, and that reconcile() refuses
        to believe it.
        """
        with cassettes.replay(cassette=_with_page_replaced(
                CASSETTE, NYC_OPEN_DATA_PAGE_SIZE, "[]")):
            before, fetched, after = crawl(self.nyc)
        self.assertEqual(len(fetched.rows), NYC_OPEN_DATA_PAGE_SIZE)
        self.assertEqual(fetched.pages, 2)
        checked = self.nyc.reconcile(len(fetched.rows), before, after)
        self.assertFalse(checked.ok)
        self.assertEqual(checked.shortfall, RECORDED_ROWS - NYC_OPEN_DATA_PAGE_SIZE)

    def test_a_429_mid_crawl_is_retried_rather_than_ending_the_crawl(self):
        """Anonymous Socrata callers share a throttling pool, so a 429 is the
        expected cost of running without an app token. lib/http.py:75-81
        retries it; this asserts the crawl still completes and still
        reconciles, which is the property that would break if this script
        ever stopped going through lib/http.py."""
        cassette = _with_page_prefixed(
            CASSETTE, NYC_OPEN_DATA_PAGE_SIZE, "Too Many Requests", 429)
        with cassettes.no_sleep(), cassettes.replay(cassette=cassette):
            before, fetched, after = crawl(self.nyc)
        self.assertEqual(len(fetched.rows), RECORDED_ROWS)
        self.assertTrue(self.nyc.reconcile(len(fetched.rows), before, after).ok)


# ---------------------------------------------------------------------------
# writing and closing -- against a real Postgres
# ---------------------------------------------------------------------------

@requires_db
@require_cassette
class TestWriteAndClose(NYCOpenDataTest):
    """Closure is a claim about UPDATE statements, so it needs a server.

    Written into a throwaway `scratch_<hex>` schema built by the REAL
    schema.ensure_schema() -- evals/scratchdb.py. Nothing here touches the
    production table.
    """

    def _records(self):
        with replaying():
            _before, fetched, _after = crawl(self.nyc)
        return [self.nyc.normalize(r) for r in fetched.rows
                if r.get("posting_type") == self.nyc.EXTERNAL]

    def _spec(self):
        return schema.spec(self.nyc.HASH_FIELDS,
                           blank_if_falsy=("description_text", "salary_text"))

    def test_records_write_despite_carrying_keys_that_are_not_columns(self):
        """`post_until` and `career_level` ride along on the record the way
        hn-hiring.py:326 carries thread_id. upsert() binds columns by name,
        so an extra key must be ignored by the write rather than failing the
        record -- and a failed record is one line of a summary, not an
        exception, which is why this is asserted rather than assumed."""
        records = self._records()
        with scratchdb.scratch_schema() as (conn, _name):
            result = upsert_checked(conn, self._spec(), records,
                                    schema.make_job_id, logger=lambda _l: None)
            self.assertEqual(result.errors, [])
            self.assertEqual(result.new, len(records))
            stored = conn.execute(
                "SELECT count(*) FROM jobs WHERE platform = %s",
                (self.nyc.PLATFORM,)).fetchone()[0]
        self.assertEqual(stored, len(records))

    def test_closed_at_is_the_published_deadline_not_the_clock(self):
        """The property that makes this source different from the other six.

        One UPDATE away from being silently replaced by utc_now_str(), at
        which point the pipeline would still close the right rows and would
        have thrown away the only date the City actually published.
        """
        records = self._records()
        self.assertTrue(records)
        expired = [{**records[0], "post_until": "2026-03-04"}]
        with scratchdb.scratch_schema() as (conn, _name):
            upsert_checked(conn, self._spec(), records, schema.make_job_id,
                           logger=lambda _l: None)
            closed = self.nyc.close_expired(conn, expired,
                                            now="2026-07-28T00:00:00")
            row = conn.execute(
                "SELECT status, closed_at FROM jobs WHERE id = %s",
                (schema.make_job_id(expired[0]),)).fetchone()
        self.assertEqual(closed, 1)
        self.assertEqual(row, ("closed", "2026-03-04T00:00:00"))

    def test_closing_by_deadline_leaves_every_other_row_open(self):
        records = self._records()
        expired = [{**records[0], "post_until": "2026-03-04"}]
        with scratchdb.scratch_schema() as (conn, _name):
            upsert_checked(conn, self._spec(), records, schema.make_job_id,
                           logger=lambda _l: None)
            self.nyc.close_expired(conn, expired, now="2026-07-28T00:00:00")
            still_open = conn.execute(
                "SELECT count(*) FROM jobs WHERE status = 'open'").fetchone()[0]
        self.assertEqual(still_open, len(records) - 1)

    def test_a_row_seen_this_run_is_not_closed_as_stale(self):
        """close_stale() is the disappearance half of the closure story. It
        must not touch anything the current run just wrote -- which is what
        makes it safe to run it every night at STALE_AFTER_DAYS = 7."""
        records = self._records()
        with scratchdb.scratch_schema() as (conn, _name):
            upsert_checked(conn, self._spec(), records, schema.make_job_id,
                           logger=lambda _l: None)
            closed = schema.close_stale(conn, self.nyc.PLATFORM,
                                        self.nyc.STALE_AFTER_DAYS)
        self.assertEqual(closed, 0)

    def test_a_row_that_vanished_from_the_feed_is_closed_as_stale(self):
        """The fallback for the 2% of postings that carry no post_until at
        all -- which is every row in the recorded slice, by construction."""
        records = self._records()
        with scratchdb.scratch_schema() as (conn, _name):
            upsert_checked(conn, self._spec(), records, schema.make_job_id,
                           logger=lambda _l: None)
            conn.execute("UPDATE jobs SET last_seen = %s WHERE id = %s",
                         ("2020-01-01T00:00:00",
                          schema.make_job_id(records[0])))
            conn.commit()
            closed = schema.close_stale(conn, self.nyc.PLATFORM,
                                        self.nyc.STALE_AFTER_DAYS)
        self.assertEqual(closed, 1)

    def test_a_reappearing_posting_is_reopened_rather_than_left_closed(self):
        """schema.spec()'s revive_column: a row closed by deadline whose
        post_until is later extended comes back through the ordinary upsert
        path, and must not stay closed because its content hash matched."""
        records = self._records()
        with scratchdb.scratch_schema() as (conn, _name):
            upsert_checked(conn, self._spec(), records, schema.make_job_id,
                           logger=lambda _l: None)
            self.nyc.close_expired(conn,
                                   [{**records[0], "post_until": "2026-03-04"}],
                                   now="2026-07-28T00:00:00")
            again = upsert_checked(conn, self._spec(), records,
                                   schema.make_job_id, logger=lambda _l: None)
            row = conn.execute(
                "SELECT status, closed_at FROM jobs WHERE id = %s",
                (schema.make_job_id(records[0]),)).fetchone()
        self.assertEqual(again.updated, 1, "the revived row counts as updated")
        self.assertEqual(again.unchanged, len(records) - 1)
        self.assertEqual(row, ("open", None))


if __name__ == "__main__":
    unittest.main()

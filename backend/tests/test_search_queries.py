"""Search queries as a first-class object (tranche_four/25).

THE NORMALISER IS THE TASK. Everything the design claims -- "the fifth Builder
to search 'AI operations NYC' costs nothing", one row, two watchers, one
provider call -- rests entirely on two phrasings collapsing to one key. So the
normaliser is swept as a table of cases in BOTH directions: the pairs that must
collapse, and the pairs that must NOT. The second table is the more valuable
one. A normaliser that is too clever produces cache hits between queries that
mean different things, which the task file calls worse than a cache miss, and
that failure is invisible -- it looks like a good hit rate.
"""

import json
import os
import sys
import unittest
import unittest.mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import extract  # noqa: E402
import schema  # noqa: E402
import searchnorm  # noqa: E402
import searchqueries  # noqa: E402
from evals import scratchdb  # noqa: E402
from lib import envfile  # noqa: E402

_BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

#: The pipeline's own .env, as tests/test_pursuit_gate.py:56 does it. Tests must
#: not depend on the caller having exported anything.
envfile.load(os.path.join(_BACKEND, ".env"))

requires_db = unittest.skipUnless(
    scratchdb.available(),
    "no scratch database: set DATABASE_URL (or JOBS_SCRATCH_DATABASE_URL)")

SEED_FILE = os.path.join(_BACKEND, "config", "search-queries.json")


class TestNormaliseCollapses(unittest.TestCase):
    """Pairs that MUST become one row. Each is a cache hit the design is
    counting on, and each one that broke would show up only as a bill."""

    COLLAPSE = [
        ("case", "AI Operations", "ai operations"),
        ("leading and trailing space", "  ai operations  ", "ai operations"),
        ("interior whitespace runs", "ai    operations", "ai operations"),
        ("tabs and newlines", "ai\toperations\n", "ai operations"),
        ("trailing punctuation", "ai operations!", "ai operations"),
        ("commas", "ai, operations", "ai operations"),
        ("hyphens become a space", "ai-operations", "ai operations"),
        ("slashes become a space", "ai/operations", "ai operations"),
        ("quotes", '"ai operations"', "ai operations"),
        ("curly quotes", "“ai operations”", "ai operations"),
        ("em dash", "ai — operations", "ai operations"),
        ("accents", "café manager", "cafe manager"),
        ("decomposed accents", "café manager", "cafe manager"),
        ("fullwidth forms", "ＡＩ operations", "ai operations"),
        ("ligature", "oﬃce manager", "office manager"),
        ("eszett casefolds", "große", "grosse"),
        ("location comma", "New York, NY", "new york ny"),
        ("location spacing", "new york,  ny", "new york ny"),
    ]

    def test_each_pair_collapses(self):
        for label, raw, expected in self.COLLAPSE:
            with self.subTest(label):
                self.assertEqual(searchnorm.normalize(raw), expected)

    def test_normalisation_is_idempotent(self):
        # normalize(normalize(x)) == normalize(x) for every case above. Not a
        # nicety: the stored key is re-normalised by nothing today, but a
        # migration or a repair script that ran the function over the column
        # would silently re-key every row if this were false.
        for label, raw, _ in self.COLLAPSE:
            with self.subTest(label):
                once = searchnorm.normalize(raw)
                self.assertEqual(searchnorm.normalize(once), once)

    def test_it_is_total(self):
        # None and "" are answers, not exceptions. validate() is what rejects
        # an empty query; normalize() itself must never raise, because it is
        # also called on a location that may legitimately be absent.
        self.assertEqual(searchnorm.normalize(None), "")
        self.assertEqual(searchnorm.normalize(""), "")
        self.assertEqual(searchnorm.normalize("!!!"), "")


class TestNormaliseDoesNotCollapse(unittest.TestCase):
    """Pairs that must stay APART. This is the table that matters.

    Every entry here is a merge somebody could plausibly add to the normaliser
    -- sorting, stemming, stopword removal, an alias table -- and every one of
    them would show up as a BETTER cache hit rate while showing Builders results
    for searches they did not run.
    """

    DISTINCT = [
        ("word order carries meaning",
         "ai operations", "operations ai"),
        ("no stopword or qualifier removal -- the cohort is entry-level and "
         "'junior' is the most load-bearing word in the query",
         "junior data analyst", "data analyst"),
        ("no stemming", "ai engineer", "ai engineers"),
        ("no plural folding on the head noun", "operation", "operations"),
        ("# is not punctuation to strip", "c#", "c"),
        ("+ is not punctuation to strip", "c++", "c"),
        ("c# and c++ are not each other", "c#", "c++"),
        ("no alias table: nyc is not new york ny",
         "nyc", "new york ny"),
        ("no synonym table", "ml engineer", "machine learning engineer"),
        ("no repeated-word deduplication", "data data analyst", "data analyst"),
        ("a separator becomes a space, not nothing",
         "front-end", "frontend"),
        ("prefix is not a match", "ai", "ai ops"),
    ]

    def test_each_pair_stays_distinct(self):
        for label, left, right in self.DISTINCT:
            with self.subTest(label):
                self.assertNotEqual(searchnorm.normalize(left),
                                    searchnorm.normalize(right), label)

    def test_location_is_part_of_the_key(self):
        # Same words, different place, two rows. Otherwise a Brooklyn search
        # would be answered with Manhattan results from someone else's cache.
        self.assertNotEqual(
            searchnorm.normalize_query("data analyst", "Brooklyn, NY"),
            searchnorm.normalize_query("data analyst", "New York, NY"))

    def test_absent_location_defaults_rather_than_wildcarding(self):
        # "" would make "any location" and "the field was never filled in" the
        # same key, and would hand a provider nothing to search.
        self.assertEqual(
            searchnorm.normalize_query("data analyst", None),
            searchnorm.normalize_query("data analyst", searchnorm.DEFAULT_LOCATION))


class TestValidate(unittest.TestCase):

    def test_empty_after_normalisation_is_rejected(self):
        with self.assertRaises(searchnorm.InvalidQuery) as caught:
            searchnorm.validate("!!!  ???")
        self.assertEqual(caught.exception.code, "empty_query")

    def test_length_is_checked_on_the_raw_input(self):
        # 300 characters of punctuation normalises to "" -- so if length were
        # checked after normalising, a 300-character query would come back as
        # "empty" and a real one would reach the unique index. Both orders
        # matter and this pins them.
        with self.assertRaises(searchnorm.InvalidQuery) as caught:
            searchnorm.validate("a" * (searchnorm.MAX_QUERY_CHARS + 1))
        self.assertEqual(caught.exception.code, "query_too_long")
        with self.assertRaises(searchnorm.InvalidQuery) as caught:
            searchnorm.validate("!" * (searchnorm.MAX_QUERY_CHARS + 1))
        self.assertEqual(caught.exception.code, "query_too_long")

    def test_location_length(self):
        with self.assertRaises(searchnorm.InvalidQuery) as caught:
            searchnorm.validate("ai ops", "x" * (searchnorm.MAX_LOCATION_CHARS + 1))
        self.assertEqual(caught.exception.code, "location_too_long")


class TestSuppression(unittest.TestCase):
    """The privacy control. tranche_five/28's rules, at this task's threshold."""

    def test_two_watchers_and_zero_watchers_are_indistinguishable(self):
        # THE test. In a thirty-person cohort who see each other in a room, a
        # count of one or two is close to an identifier, and "no badge" must not
        # be readable as "exactly one or two". Every sub-threshold count returns
        # the same thing, and it is the same thing an unwatched query returns.
        self.assertEqual(schema.search_watcher_bucket(0), schema.search_watcher_bucket(2))
        self.assertIsNone(schema.search_watcher_bucket(0))
        for watchers in range(0, schema.SEARCH_MIN_WATCHERS):
            with self.subTest(watchers=watchers):
                self.assertIsNone(schema.search_watcher_bucket(watchers))

    def test_the_threshold_is_four_and_higher_than_the_cohort_signal_one(self):
        # Pinned literally, and deliberately NOT computed from anything: it is a
        # privacy control, so moving it has to be an edit somebody makes on
        # purpose while reading the argument beside it in searchnorm.py.
        #
        # It is higher than tranche_five/28's 3 for two reasons that do not
        # apply to a save count: the observed object is attacker-chosen (a query
        # is created by submitting it, so an observer can plant one), and the
        # planter is always a watcher (so a threshold of 3 gives an anonymity
        # set of 2).
        self.assertEqual(schema.SEARCH_MIN_WATCHERS, 4)

    def test_buckets_do_not_overlap(self):
        # 28's sketch writes '3-5' | '6-10' | '10+', where 10 falls in two of
        # three. A value that can be in two buckets is a boundary that leaks
        # which side it was on.
        # The labels themselves must be unambiguous, which is the one place
        # this vocabulary deviates from COHORT_BUCKETS -- see the constant.
        # Parsed back out of the label rather than read off the tuple, so the
        # assertion is about what a Builder SEES and not about the encoding.
        seen = {}
        for watchers in range(schema.SEARCH_MIN_WATCHERS, 60):
            label = schema.search_watcher_bucket(watchers)
            if label.endswith("+"):
                self.assertGreaterEqual(watchers, int(label[:-1]))
            else:
                low, high = (int(part) for part in label.split("-"))
                self.assertTrue(low <= watchers <= high,
                                f"{watchers} watchers is labelled {label!r}")
            seen[label] = seen.get(label, 0) + 1
        self.assertEqual(set(seen), set(schema.SEARCH_WATCHER_BUCKET_LABELS))

    def test_every_bucket_above_the_threshold_is_covered(self):
        for watchers in range(schema.SEARCH_MIN_WATCHERS, 200):
            self.assertIn(schema.search_watcher_bucket(watchers), schema.SEARCH_WATCHER_BUCKET_LABELS)

    def test_bucket_is_monotone(self):
        # Adding a watcher may never LOWER the exposed bucket. Cheap, and a
        # non-monotone bucket table would be a genuinely confusing leak.
        order = {label: i for i, label in enumerate(schema.SEARCH_WATCHER_BUCKET_LABELS)}
        previous = -1
        for watchers in range(schema.SEARCH_MIN_WATCHERS, 60):
            current = order[schema.search_watcher_bucket(watchers)]
            self.assertGreaterEqual(current, previous)
            previous = current

    def test_it_is_shaped_like_its_neighbour(self):
        # cohort_bucket() and search_watcher_bucket() are the same function over
        # different vocabularies, and they must stay that way: two suppression
        # rules with different shapes is how the second one acquires a bug the
        # first already fixed.
        self.assertIsNone(schema.cohort_bucket(schema.COHORT_MIN_SAVERS - 1))
        self.assertIsNone(
            schema.search_watcher_bucket(schema.SEARCH_MIN_WATCHERS - 1))
        self.assertEqual(schema.SEARCH_WATCHER_BUCKETS[-1][0], None,
                         "the final bucket must be open-ended, as "
                         "COHORT_BUCKETS' is")
        self.assertGreater(schema.SEARCH_MIN_WATCHERS, schema.COHORT_MIN_SAVERS,
                           "a search is attacker-chosen where a posting is not; "
                           "see the constant's own argument")

    def test_the_database_check_is_generated_from_the_labels(self):
        # The vocabulary cannot be widened in Python while Postgres keeps
        # refusing the new value. Same construction as schema_web's
        # _PRIOR_DOMAIN_CHECK, and this asserts it stayed generated.
        for label in schema.SEARCH_WATCHER_BUCKET_LABELS:
            self.assertIn(f"'{label}'", schema._SEARCH_BUCKET_CHECK)
        for source in schema.SEARCH_SOURCES:
            self.assertIn(f"'{source}'", schema._SEARCH_SOURCE_CHECK)


class TestCadence(unittest.TestCase):

    NOW = "2026-08-02T00:00:00"

    def test_a_new_query_is_due_immediately(self):
        # Whatever its source and whether or not anyone watches it. The
        # asynchronous promise is "next cycle", not "next cycle after a
        # cadence window".
        for source in schema.SEARCH_SOURCES:
            with self.subTest(source):
                self.assertTrue(searchnorm.is_due(self.NOW, None, 0, source))

    def test_a_watched_query_reruns_after_the_window(self):
        self.assertFalse(searchnorm.is_due(self.NOW, "2026-08-01T10:00:00", 1,
                                           "builder"))
        self.assertTrue(searchnorm.is_due(self.NOW, "2026-08-01T03:00:00", 1,
                                          "builder"))

    def test_the_freshness_floor_is_twenty_hours_and_still_binds(self):
        # WAS test_the_window_is_twenty_hours_not_twenty_four, which asserted
        # the constant and one query either side of it. docs/adr/0007 decision
        # 4 demoted RERUN_HOURS from deciding whether a query runs to a
        # minimum-freshness floor, which does not make that assertion wrong --
        # it makes it insufficient, because it passes identically whether the
        # constant is a floor or the whole rule.
        #
        # What a floor means, and what the old test could not tell apart: a
        # query inside the window is refused NO MATTER HOW MUCH BUDGET THERE
        # IS. An unlimited allowance does not buy a re-ask of a question whose
        # answer is still fresh.
        self.assertEqual(searchnorm.RERUN_HOURS, 20)
        self.assertTrue(searchnorm.is_due(self.NOW, "2026-08-01T04:00:00", 1,
                                          "builder"))
        for allowance in (None, 1, 10_000):
            with self.subTest(allowance=allowance):
                self.assertFalse(
                    searchnorm.is_due(self.NOW, "2026-08-01T10:00:00", 1,
                                      "builder", None, allowance),
                    "budget must not buy a re-run inside the freshness floor")

    def test_pacing_and_not_cadence_is_what_picks_the_query(self):
        # The other half, and the one the demotion is FOR: a query the floor
        # has cleared is still refused when the run has no budget left. Before
        # decision 4 nothing could refuse it, because the floor was the only
        # gate there was.
        #
        # source='seeded', deliberately. An unwatched 'builder' query that has
        # already run is never due whatever its statistics say, so writing this
        # against 'builder' with 0 watchers would pass for the wrong reason and
        # go on passing if the allowance were ignored entirely.
        stale = "2026-07-01T00:00:00"
        self.assertTrue(searchnorm.is_due(self.NOW, stale, 0, "seeded", None, 5))
        self.assertFalse(searchnorm.is_due(self.NOW, stale, 0, "seeded", None, 0))

    def test_an_exhausted_budget_outranks_the_never_run_shortcut(self):
        # A never-run query is due immediately -- that is the asynchronous
        # promise -- but "immediately" cannot mean "on a run with nothing left
        # to spend". The budget check therefore sits ABOVE the shortcut, and
        # this is the case that pins the order; moved below it, a bank of
        # never-run rows would spend straight past the cap.
        self.assertTrue(searchnorm.is_due(self.NOW, None, 0, "seeded", None, 1))
        self.assertFalse(searchnorm.is_due(self.NOW, None, 0, "seeded", None, 0))

    def test_a_generous_budget_does_not_resurrect_a_retired_query(self):
        # NOT an ordering assertion, deliberately, and it was written as one
        # first: retirement and the budget are both refusals, so swapping the
        # two guards is behaviourally indistinguishable and a test named for
        # the order passes under either. Reordering them is safe; what is not
        # safe is a budget large enough to look like "no limit" reaching a
        # retired row, which is what this actually pins.
        self.assertFalse(searchnorm.is_due(self.NOW, None, 5, "builder",
                                           "2026-07-01T00:00:00", 10_000))
        self.assertFalse(searchnorm.is_due(self.NOW, None, 5, "builder",
                                           "2026-07-01T00:00:00", 0))

    def test_an_unpaced_call_is_exactly_the_old_behaviour(self):
        # `allowance=None` is what every caller with no plan data passes, and
        # it must be indistinguishable from the predicate before decision 4 --
        # otherwise a vendor outage silently changes which queries run.
        for last_run, watchers, source in (
                (None, 0, "builder"), ("2026-08-01T10:00:00", 1, "builder"),
                ("2026-08-01T03:00:00", 1, "builder"),
                ("2026-07-01T00:00:00", 0, "builder"),
                ("2026-07-01T00:00:00", 0, "seeded")):
            with self.subTest(last_run=last_run, source=source):
                self.assertEqual(
                    searchnorm.is_due(self.NOW, last_run, watchers, source),
                    searchnorm.is_due(self.NOW, last_run, watchers, source,
                                      None, None))

    def test_an_unwatched_builder_query_stops_running(self):
        # It is not retired -- a second Builder typing the same words still
        # lands on the cached row -- it just costs nothing meanwhile.
        self.assertFalse(searchnorm.is_due(self.NOW, "2026-07-01T00:00:00", 0,
                                           "builder"))

    def test_seeded_queries_run_without_a_watcher(self):
        # They are the catalogue a Builder with no search term is shown, so
        # they must have results before anyone watches them.
        for source in searchnorm.UNDECAYABLE_SOURCES:
            with self.subTest(source):
                self.assertTrue(searchnorm.is_due(self.NOW, "2026-07-01T00:00:00",
                                                  0, source))

    def test_a_retired_query_is_never_due(self):
        self.assertFalse(searchnorm.is_due(self.NOW, None, 5, "builder",
                                           retired_at="2026-07-01T00:00:00"))


class TestRunAllowance(unittest.TestCase):
    """searchnorm.run_allowance() -- the whole of docs/adr/0007 decision 4's
    arithmetic, and pure, so it is swept over a table rather than reasoned
    about."""

    def test_credits_remaining_over_days_remaining(self):
        self.assertEqual(searchnorm.run_allowance(250, 31), 8)
        self.assertEqual(searchnorm.run_allowance(250, 10), 25)
        self.assertEqual(searchnorm.run_allowance(250, 1), 250)

    def test_an_idle_week_raises_the_allowance_rather_than_stranding_credit(self):
        # THE ROW'S CENTRAL CLAIM, as arithmetic. A contributor whose machine
        # was shut for a week did not spend, so `left` did not fall while
        # `days_left` did -- and the allowance rises to absorb the backlog
        # instead of holding them to the cadence that let it build up.
        steady = searchnorm.run_allowance(250, 31)
        after_idle_week = searchnorm.run_allowance(250, 24)
        self.assertGreater(after_idle_week, steady)
        # And it converges: the same credits over fewer days keeps rising, so
        # the last day of the cycle spends the remainder rather than 1/31 of it.
        self.assertEqual(searchnorm.run_allowance(250, 1), 250)

    def test_a_remainder_too_small_to_divide_is_spent_not_stranded(self):
        # 3 credits over 10 days floors to 0, which would strand all three
        # until they expire -- the exact loss decision 4 exists to stop. The
        # floor of 1 is the rule, not a rounding artefact.
        self.assertEqual(searchnorm.run_allowance(3, 10), 1)
        self.assertEqual(searchnorm.run_allowance(1, 31), 1)

    def test_an_empty_account_paces_to_zero_and_the_reserve_is_honoured(self):
        # Zero is a real answer and is NOT None: the vendor was reached and
        # said there is nothing left. Conflating the two would make an
        # exhausted account dispatch as though it were unmetered.
        self.assertEqual(searchnorm.run_allowance(0, 10), 0)
        self.assertEqual(searchnorm.run_allowance(-5, 10), 0)
        self.assertEqual(searchnorm.run_allowance(10, 10, reserve=10), 0)
        self.assertEqual(searchnorm.run_allowance(10, 10, reserve=4), 1)
        # The reserve is checked BEFORE the floor of 1, or "hold 10 back"
        # would still spend one a run and drain the reserve it named.
        self.assertEqual(searchnorm.run_allowance(11, 100, reserve=10), 1)
        self.assertEqual(searchnorm.run_allowance(10, 100, reserve=10), 0)

    def test_unknown_plan_data_is_unpaced_and_not_zero(self):
        # serp/quota.py's direction, inherited rather than re-decided: the
        # cost of allowing is one refused search and the cost of refusing is
        # the whole bank. None here, 0 above, and they must never be swapped.
        self.assertIsNone(searchnorm.run_allowance(None, 10))
        self.assertIsNone(searchnorm.run_allowance(250, None))

    def test_it_does_no_io(self):
        # The purity clause, asserted rather than asserted-in-a-docstring.
        # A predicate that needs a connection is a predicate nobody sweeps.
        import socket
        with unittest.mock.patch.object(
                socket, "socket",
                side_effect=AssertionError("run_allowance opened a socket")):
            self.assertEqual(searchnorm.run_allowance(250, 10), 25)
            self.assertTrue(searchnorm.is_due("2026-08-02T00:00:00",
                                              "2026-07-01T00:00:00", 0,
                                              "seeded", None, 5))


class TestDaysLeftInCycle(unittest.TestCase):
    """The cycle boundary the vendor does not send. See OQ-36."""

    def test_it_counts_today_so_the_last_day_spends_the_remainder(self):
        self.assertEqual(
            searchnorm.days_left_in_cycle("2026-08-31T23:00:00"), 1)
        self.assertEqual(
            searchnorm.days_left_in_cycle("2026-08-01T00:00:00"), 31)
        self.assertEqual(
            searchnorm.days_left_in_cycle("2026-08-02T00:00:00"), 30)

    def test_it_is_never_zero(self):
        # A zero would be a division by zero in run_allowance() on exactly one
        # day a month -- the day the whole feature matters most.
        for day in range(1, 29):
            stamp = f"2026-02-{day:02d}T12:00:00"
            with self.subTest(stamp):
                self.assertGreaterEqual(
                    searchnorm.days_left_in_cycle(stamp), 1)

    def test_a_late_signup_anchor_is_a_parameter_not_a_constant(self):
        # SerpApi bills from the signup date, so an account opened on the 12th
        # turns over on the 12th. The default of 1 is the vendor's own framing
        # (`this_month_usage`), not a verified fact about any real account --
        # which is what OQ-36 asks for.
        self.assertEqual(
            searchnorm.days_left_in_cycle("2026-08-02T00:00:00", 12), 10)
        self.assertEqual(
            searchnorm.days_left_in_cycle("2026-08-12T00:00:00", 12), 31)

    def test_an_anchor_past_the_end_of_a_short_month_clamps(self):
        # A cycle anchored on the 31st turns over on the 28th of February,
        # the way every monthly-billing system resolves it. Unclamped this
        # raises ValueError and takes the nightly run with it.
        self.assertEqual(
            searchnorm.days_left_in_cycle("2026-02-10T00:00:00", 31), 18)
        self.assertEqual(
            searchnorm.days_left_in_cycle("2026-04-10T00:00:00", 31), 20)


class TestDecay(unittest.TestCase):

    NOW = "2026-08-02T00:00:00"
    OLD = "2026-07-01T00:00:00"        # 32 days
    RECENT = "2026-07-30T00:00:00"     # 3 days

    def test_zero_watchers_and_no_results_for_fourteen_days_retires(self):
        self.assertTrue(searchnorm.should_retire(
            self.NOW, "builder", 0, self.OLD, None))

    def test_both_conditions_are_required(self):
        # A watched query that has found nothing is not abandoned -- somebody
        # is still asking.
        self.assertFalse(searchnorm.should_retire(
            self.NOW, "builder", 1, self.OLD, None))
        # An unwatched query that keeps returning postings is feeding the
        # shared corpus every other Builder reads.
        self.assertFalse(searchnorm.should_retire(
            self.NOW, "builder", 0, self.OLD, self.RECENT))

    def test_the_window_is_fourteen_days(self):
        self.assertEqual(searchnorm.DECAY_DAYS, 14)
        self.assertFalse(searchnorm.should_retire(
            self.NOW, "builder", 0, "2026-07-25T00:00:00", None))

    def test_seeded_queries_never_decay(self):
        # Nobody can watch a suggestion that has already been retired for
        # having no watchers; decaying the catalogue would switch the seeding
        # feature off after two weeks.
        for source in searchnorm.UNDECAYABLE_SOURCES:
            with self.subTest(source):
                self.assertFalse(searchnorm.should_retire(
                    self.NOW, source, 0, self.OLD, None))

    def test_first_requested_at_is_the_fallback_clock(self):
        # A query that never returned anything has no last_result_at, and must
        # still be able to retire rather than living forever on a NULL.
        self.assertTrue(searchnorm.should_retire(
            self.NOW, "builder", 0, self.OLD, None))

    def test_an_already_retired_query_is_left_alone(self):
        self.assertFalse(searchnorm.should_retire(
            self.NOW, "builder", 0, self.OLD, None, retired_at=self.OLD))


class TestSeedCatalogue(unittest.TestCase):

    def setUp(self):
        with open(SEED_FILE) as fh:
            self.cfg = json.load(fh)
        self.seeds = searchqueries.load_seeds(SEED_FILE)

    def test_every_role_track_is_seeded_exactly_once(self):
        # The DoD item, and the reason it is an equality rather than a subset:
        # a tenth track added to extract.ROLE_TRACK without a seed is a track
        # nobody can browse to, and a seed for a track that no longer exists is
        # a daily provider call for a dead vocabulary value.
        tracks = [s["role_track"] for s in self.seeds]
        self.assertEqual(sorted(tracks), sorted(extract.ROLE_TRACK))
        self.assertEqual(len(tracks), len(set(tracks)))

    def test_the_vocabulary_is_nine_values(self):
        self.assertEqual(len(extract.ROLE_TRACK), 9)

    def test_every_seed_normalises_to_something(self):
        for seed in self.seeds:
            with self.subTest(seed["role_track"]):
                normalized_text, normalized_location = searchnorm.validate(
                    seed["text"], seed["location"])
                self.assertTrue(normalized_text)
                self.assertTrue(normalized_location)

    def test_no_two_seeds_collide(self):
        # Two seeds normalising to one key would silently drop a track: the
        # second insert would find the first's row and the catalogue would have
        # eight entries for nine tracks.
        keys = [searchnorm.normalize_query(s["text"], s["location"])
                for s in self.seeds]
        self.assertEqual(len(keys), len(set(keys)))

    def test_the_seed_text_is_not_a_machine_identifier(self):
        # A track is a machine value; a query is what someone types into Google
        # Jobs. Seeding `solutions_and_implementation` verbatim would spend a
        # provider call on a string no employer has ever written.
        #
        # The property is "no identifier punctuation in the query text", NOT
        # "text differs from role_track": `revenue_operations` and
        # `business_operations` normalise to exactly their own English phrasing,
        # which is a coincidence and a correct seed, and an inequality assertion
        # would force a worse query text to satisfy a test.
        for seed in self.seeds:
            with self.subTest(seed["role_track"]):
                self.assertNotIn("_", seed["text"])
                self.assertNotEqual(seed["text"], seed["role_track"])

    def test_the_config_carries_its_documentation(self):
        # `_comment` fields in config JSON are load-bearing documentation
        # (.claude/CLAUDE.md). This is the same assertion the relevance config
        # gets, for the same reason: the rejected alternatives are the valuable
        # half and nothing else records them.
        self.assertIn("_comment", self.cfg)
        self.assertTrue(any("REJECTED" in line for line in self.cfg["_comment"]))

    def test_comment_keys_do_not_reach_the_loader(self):
        for seed in self.seeds:
            self.assertEqual(set(seed), {"role_track", "text", "location"})


@requires_db
class TestTwoBuildersOneRow(unittest.TestCase):
    """The cost argument, against a real schema and the statements that ship.

    These execute searchnorm's SQL constants -- the same strings webapp/search.py
    executes -- rather than a paraphrase, which is the only way this test says
    anything about the product. The webapp cannot be imported here: it is a
    separate process with its own venv and fastapi is not installed for the
    system python3 the pipeline suite runs under.
    """

    def _register(self, conn, text, app_user_id, location=None,
                  profile="pursuit", now="2026-08-02T00:00:00"):
        normalized_text, normalized_location = searchnorm.validate(text, location)
        query_id = conn.execute(
            searchnorm.REGISTER_QUERY_SQL,
            (normalized_text, normalized_location, text,
             location or searchnorm.DEFAULT_LOCATION, None, "builder", None,
             now)).fetchone()[0]
        conn.execute(searchnorm.REGISTER_WATCHER_SQL,
                     (query_id, app_user_id, profile, now))
        conn.commit()
        return query_id

    def test_two_builders_one_row_two_watchers_one_due_query(self):
        with scratchdb.scratch_schema() as (conn, _name):
            first = self._register(conn, "AI Operations", "user-a")
            second = self._register(conn, "  ai   operations!  ", "user-b")

            self.assertEqual(first, second, "two phrasings must be one row")
            self.assertEqual(
                conn.execute("SELECT count(*) FROM search_queries").fetchone()[0], 1)
            self.assertEqual(
                conn.execute("SELECT count(*) FROM search_query_watchers "
                             "WHERE removed_at IS NULL").fetchone()[0], 2)

            # ONE provider call, which is what the row count buys: the runner
            # dispatches per due QUERY, not per watcher and not per submission.
            due = searchqueries.due_queries(conn, now="2026-08-02T01:00:00")
            self.assertEqual(len(due), 1)
            self.assertEqual(due[0]["watchers"], 2)

    def test_the_display_text_is_first_writer_wins(self):
        with scratchdb.scratch_schema() as (conn, _name):
            self._register(conn, "AI Operations", "user-a")
            self._register(conn, "ai operations", "user-b")
            stored = conn.execute(
                "SELECT display_text FROM search_queries").fetchone()[0]
            self.assertEqual(stored, "AI Operations",
                             "a second requester must not re-attribute the "
                             "spelling -- that would be a recency channel")

    def test_registration_is_idempotent_for_the_same_builder(self):
        with scratchdb.scratch_schema() as (conn, _name):
            self._register(conn, "ai operations", "user-a")
            self._register(conn, "ai operations", "user-a")
            self.assertEqual(
                conn.execute("SELECT count(*) FROM search_query_watchers")
                .fetchone()[0], 1)

    def test_unwatch_is_an_update_and_re_watch_clears_it(self):
        with scratchdb.scratch_schema() as (conn, _name):
            query_id = self._register(conn, "ai operations", "user-a")
            conn.execute(searchnorm.UNWATCH_SQL,
                         ("2026-08-03T00:00:00", query_id, "user-a"))
            conn.commit()
            row = conn.execute("SELECT removed_at FROM search_query_watchers "
                               "WHERE app_user_id = 'user-a'").fetchone()
            self.assertEqual(row[0], "2026-08-03T00:00:00")
            # The row survives -- who reversed what is itself signal.
            self.assertEqual(
                conn.execute("SELECT count(*) FROM search_query_watchers")
                .fetchone()[0], 1)
            self._register(conn, "ai operations", "user-a")
            self.assertIsNone(
                conn.execute("SELECT removed_at FROM search_query_watchers")
                .fetchone()[0])

    def test_unwatch_does_not_move_an_existing_timestamp(self):
        with scratchdb.scratch_schema() as (conn, _name):
            query_id = self._register(conn, "ai operations", "user-a")
            for stamp in ("2026-08-03T00:00:00", "2026-08-04T00:00:00"):
                conn.execute(searchnorm.UNWATCH_SQL, (stamp, query_id, "user-a"))
            conn.commit()
            self.assertEqual(
                conn.execute("SELECT removed_at FROM search_query_watchers")
                .fetchone()[0], "2026-08-03T00:00:00")

    def test_the_query_row_carries_no_builder_identity(self):
        # Structural, not a promise: there is no column on search_queries that
        # could name a person, so no endpoint reading it can leak one.
        with scratchdb.scratch_schema() as (conn, name):
            columns = {row[0] for row in conn.execute(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_schema = %s AND table_name = 'search_queries'",
                (name,)).fetchall()}
            for forbidden in ("app_user_id", "profile", "created_by",
                              "requested_by", "email", "watcher_count"):
                self.assertNotIn(forbidden, columns)


@requires_db
class TestPrivateIdentitiesCannotReachTheCount(unittest.TestCase):
    """The fold, and what it refuses to expose."""

    def _watch(self, conn, query_id, app_user_id, profile="pursuit",
               removed_at=None):
        conn.execute(
            "INSERT INTO search_query_watchers "
            "(query_id, app_user_id, profile, created_at, removed_at) "
            "VALUES (%s, %s, %s, %s, %s)",
            (query_id, app_user_id, profile, "2026-08-02T00:00:00", removed_at))
        conn.commit()

    def _query(self, conn, text="ai operations"):
        normalized_text, normalized_location = searchnorm.validate(text)
        query_id = conn.execute(
            searchnorm.REGISTER_QUERY_SQL,
            (normalized_text, normalized_location, text,
             searchnorm.DEFAULT_LOCATION, None, "builder", None,
             "2026-08-02T00:00:00")).fetchone()[0]
        conn.commit()
        return query_id

    def test_below_the_threshold_no_row_exists_at_all(self):
        # Not a row with a NULL bucket. A NULL-bucket row would be PRESENT for
        # 1, 2 or 3 watchers and ABSENT for none, and that presence is the count
        # leaking back out through the door the bucketing closed.
        with scratchdb.scratch_schema() as (conn, _name):
            query_id = self._query(conn)
            for i in range(schema.SEARCH_MIN_WATCHERS - 1):
                self._watch(conn, query_id, f"user-{i}")
            searchqueries.refresh(conn, 'pursuit', now="2026-08-02T02:00:00")
            self.assertEqual(
                conn.execute("SELECT count(*) FROM search_query_signal")
                .fetchone()[0], 0)

    def test_two_watchers_and_zero_watchers_are_indistinguishable(self):
        with scratchdb.scratch_schema() as (conn, _name):
            quiet = self._query(conn, "quiet search")
            two = self._query(conn, "two watcher search")
            self._watch(conn, two, "user-a")
            self._watch(conn, two, "user-b")
            searchqueries.refresh(conn, 'pursuit', now="2026-08-02T02:00:00")
            rows = conn.execute(
                "SELECT query_id FROM search_query_signal").fetchall()
            self.assertEqual(rows, [], "neither may produce a signal row")
            # And the read shape agrees: a LEFT JOIN gives both the same NULL.
            for query_id in (quiet, two):
                bucket = conn.execute(
                    "SELECT sig.watcher_bucket FROM search_queries q "
                    "LEFT JOIN search_query_signal sig ON sig.query_id = q.id "
                    "WHERE q.id = %s", (query_id,)).fetchone()[0]
                self.assertIsNone(bucket)

    def test_at_the_threshold_a_bucket_appears(self):
        with scratchdb.scratch_schema() as (conn, _name):
            query_id = self._query(conn)
            for i in range(schema.SEARCH_MIN_WATCHERS):
                self._watch(conn, query_id, f"user-{i}")
            searchqueries.refresh(conn, 'pursuit', now="2026-08-02T02:00:00")
            row = conn.execute(
                "SELECT watcher_bucket, cohort_profile FROM search_query_signal "
                "WHERE query_id = %s", (query_id,)).fetchone()
            self.assertEqual(row[0], schema.search_watcher_bucket(schema.SEARCH_MIN_WATCHERS))
            self.assertEqual(row[1], "pursuit")

    def test_an_unwatch_removes_the_badge(self):
        # The fold DELETEs and re-INSERTs precisely so a badge can disappear.
        # An upsert would leave last night's bucket in place as a fossil.
        with scratchdb.scratch_schema() as (conn, _name):
            query_id = self._query(conn)
            for i in range(schema.SEARCH_MIN_WATCHERS):
                self._watch(conn, query_id, f"user-{i}")
            searchqueries.refresh(conn, 'pursuit', now="2026-08-02T02:00:00")
            conn.execute(searchnorm.UNWATCH_SQL,
                         ("2026-08-03T00:00:00", query_id, "user-0"))
            conn.commit()
            searchqueries.refresh(conn, 'pursuit', now="2026-08-03T02:00:00")
            self.assertEqual(
                conn.execute("SELECT count(*) FROM search_query_signal")
                .fetchone()[0], 0)

    def test_removed_watchers_never_count(self):
        with scratchdb.scratch_schema() as (conn, _name):
            query_id = self._query(conn)
            for i in range(schema.SEARCH_MIN_WATCHERS):
                self._watch(conn, query_id, f"user-{i}",
                            removed_at="2026-08-01T00:00:00")
            searchqueries.refresh(conn, 'pursuit', now="2026-08-02T02:00:00")
            self.assertEqual(
                conn.execute("SELECT count(*) FROM search_query_signal")
                .fetchone()[0], 0)

    def test_the_fold_is_within_cohort(self):
        # Two cohorts, three watchers each, six in total. Neither crosses the
        # threshold, and the union must not be allowed to. tranche_five/28:
        # a Builder's activity visible to people they have never met is a
        # different privacy promise than the one made.
        with scratchdb.scratch_schema() as (conn, _name):
            query_id = self._query(conn)
            for i in range(3):
                self._watch(conn, query_id, f"a-{i}", profile="pursuit")
                self._watch(conn, query_id, f"b-{i}", profile="cohort-two")
            searchqueries.refresh(conn, 'pursuit', now="2026-08-02T02:00:00")
            self.assertEqual(
                conn.execute("SELECT count(*) FROM search_query_signal")
                .fetchone()[0], 0)

    def test_the_signal_table_stores_no_exact_count(self):
        with scratchdb.scratch_schema() as (conn, name):
            columns = {row[0] for row in conn.execute(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_schema = %s AND table_name = 'search_query_signal'",
                (name,)).fetchall()}
            self.assertEqual(columns, {"query_id", "cohort_profile",
                                       "watcher_bucket", "computed_at"})

    def test_the_database_refuses_a_sub_threshold_bucket(self):
        # Belt and braces: even a writer bypassing fold_signal cannot store a
        # label the vocabulary does not contain, and NOT NULL means it cannot
        # store "present but suppressed" either.
        import psycopg
        with scratchdb.scratch_schema() as (conn, _name):
            query_id = self._query(conn)
            with self.assertRaises(psycopg.errors.CheckViolation):
                conn.execute(
                    "INSERT INTO search_query_signal "
                    "(query_id, cohort_profile, watcher_bucket, computed_at) "
                    "VALUES (%s, 'pursuit', '1-2', %s)",
                    (query_id, "2026-08-02T02:00:00"))
            conn.rollback()
            with self.assertRaises(psycopg.errors.NotNullViolation):
                conn.execute(
                    "INSERT INTO search_query_signal "
                    "(query_id, cohort_profile, watcher_bucket, computed_at) "
                    "VALUES (%s, 'pursuit', NULL, %s)",
                    (query_id, "2026-08-02T02:00:00"))
            conn.rollback()


@requires_db
class TestSeedingAndDecayAgainstTheSchema(unittest.TestCase):

    def test_seeding_is_idempotent_and_covers_every_track(self):
        with scratchdb.scratch_schema() as (conn, _name):
            created = searchqueries.seed(conn, SEED_FILE, now="2026-08-02T00:00:00")
            self.assertEqual(created, len(extract.ROLE_TRACK))
            again = searchqueries.seed(conn, SEED_FILE, now="2026-08-03T00:00:00")
            self.assertEqual(again, 0)
            tracks = {row[0] for row in conn.execute(
                "SELECT role_track FROM search_queries WHERE source = 'track'"
            ).fetchall()}
            self.assertEqual(tracks, set(extract.ROLE_TRACK))

    def test_a_dry_seed_counts_what_it_would_create_and_writes_nothing(self):
        """--dry-run became a SPEND ESTIMATE when task 23 gave run_due() a real
        provider, and skipping the seed made that estimate wrong in the
        expensive direction. A seeded query has never run; searchnorm.is_due()
        makes a never-run query due immediately whatever its source; every due
        query is one metered provider call. So a dry run against an unseeded
        database answered `due=0` for a night that would have dispatched the
        whole catalogue -- measured on the live database on 2026-08-02, which
        held zero search_queries rows at the time.
        """
        with scratchdb.scratch_schema() as (conn, _name):
            would_create = searchqueries.seed(conn, SEED_FILE,
                                              now="2026-08-02T00:00:00",
                                              dry_run=True)
            self.assertEqual(would_create, len(extract.ROLE_TRACK))
            self.assertEqual(
                conn.execute("SELECT count(*) FROM search_queries")
                .fetchone()[0], 0,
                "a dry seed wrote rows")
            # And the count it reported is the count a real seed then creates.
            self.assertEqual(
                searchqueries.seed(conn, SEED_FILE, now="2026-08-02T00:00:00"),
                would_create)

    def test_seeding_does_not_steal_a_builder_query(self):
        # If someone typed "data analyst" before the catalogue landed, the row
        # is theirs. Upgrading it to source='track' would make it undecayable
        # for having been typed early -- a rule nobody would guess.
        with scratchdb.scratch_schema() as (conn, _name):
            normalized_text, normalized_location = searchnorm.validate(
                "data analyst", searchnorm.DEFAULT_LOCATION)
            conn.execute(searchnorm.REGISTER_QUERY_SQL,
                         (normalized_text, normalized_location, "data analyst",
                          searchnorm.DEFAULT_LOCATION, None, "builder", None,
                          "2026-08-01T00:00:00"))
            conn.commit()
            searchqueries.seed(conn, SEED_FILE, now="2026-08-02T00:00:00")
            row = conn.execute(
                "SELECT source, role_track, first_requested_at FROM search_queries "
                "WHERE normalized_text = %s", (normalized_text,)).fetchone()
            self.assertEqual(row[0], "builder")
            self.assertIsNone(row[1])
            self.assertEqual(row[2], "2026-08-01T00:00:00")

    def test_decay_retires_the_abandoned_and_spares_the_catalogue(self):
        with scratchdb.scratch_schema() as (conn, _name):
            searchqueries.seed(conn, SEED_FILE, now="2026-07-01T00:00:00")
            normalized_text, normalized_location = searchnorm.validate("abandoned")
            abandoned = conn.execute(
                searchnorm.REGISTER_QUERY_SQL,
                (normalized_text, normalized_location, "abandoned",
                 searchnorm.DEFAULT_LOCATION, None, "builder", None,
                 "2026-07-01T00:00:00")).fetchone()[0]
            conn.commit()

            retired = searchqueries.apply_decay(conn, now="2026-08-02T00:00:00")
            self.assertEqual(retired, [abandoned])
            still_running = conn.execute(
                "SELECT count(*) FROM search_queries "
                "WHERE source = 'track' AND retired_at IS NULL").fetchone()[0]
            self.assertEqual(still_running, len(extract.ROLE_TRACK))

    def test_a_retired_query_stops_being_due(self):
        with scratchdb.scratch_schema() as (conn, _name):
            normalized_text, normalized_location = searchnorm.validate("abandoned")
            conn.execute(searchnorm.REGISTER_QUERY_SQL,
                         (normalized_text, normalized_location, "abandoned",
                          searchnorm.DEFAULT_LOCATION, None, "builder", None,
                          "2026-07-01T00:00:00"))
            conn.commit()
            self.assertEqual(
                len(searchqueries.due_queries(conn, now="2026-08-02T00:00:00")), 1)
            searchqueries.apply_decay(conn, now="2026-08-02T00:00:00")
            self.assertEqual(
                searchqueries.due_queries(conn, now="2026-08-02T00:00:00"), [])

    def test_a_watcher_revives_a_retired_query(self):
        # Retirement is a timestamp, not a delete, precisely so the cache
        # survives: the words are still one row and watching it makes it due.
        with scratchdb.scratch_schema() as (conn, _name):
            normalized_text, normalized_location = searchnorm.validate("abandoned")
            query_id = conn.execute(
                searchnorm.REGISTER_QUERY_SQL,
                (normalized_text, normalized_location, "abandoned",
                 searchnorm.DEFAULT_LOCATION, None, "builder", None,
                 "2026-07-01T00:00:00")).fetchone()[0]
            conn.commit()
            searchqueries.apply_decay(conn, now="2026-08-02T00:00:00")
            conn.execute(searchnorm.REGISTER_WATCHER_SQL,
                         (query_id, "user-a", "pursuit", "2026-08-02T00:00:00"))
            conn.execute("UPDATE search_queries SET retired_at = NULL WHERE id = %s",
                         (query_id,))
            conn.commit()
            self.assertEqual(
                len(searchqueries.due_queries(conn, now="2026-08-02T00:00:00")), 1)

    def test_record_run_separates_ran_from_found_something(self):
        # last_run_at always moves; last_result_at only on a non-empty run.
        # That is what makes "no results in 14 days" mean what it says while
        # the cadence still holds for a query that keeps coming back empty.
        with scratchdb.scratch_schema() as (conn, _name):
            normalized_text, normalized_location = searchnorm.validate("empty run")
            query_id = conn.execute(
                searchnorm.REGISTER_QUERY_SQL,
                (normalized_text, normalized_location, "empty run",
                 searchnorm.DEFAULT_LOCATION, None, "builder", None,
                 "2026-07-01T00:00:00")).fetchone()[0]
            conn.commit()
            searchqueries.record_run(conn, query_id, "test", 0,
                                     now="2026-08-01T00:00:00")
            row = conn.execute(
                "SELECT last_run_at, last_result_at, run_count "
                "FROM search_queries WHERE id = %s", (query_id,)).fetchone()
            self.assertEqual(row[0], "2026-08-01T00:00:00")
            self.assertIsNone(row[1])
            self.assertEqual(row[2], 1)

            searchqueries.record_run(conn, query_id, "test", 3,
                                     now="2026-08-02T00:00:00")
            row = conn.execute(
                "SELECT last_run_at, last_result_at, run_count, "
                "result_count_last_run FROM search_queries WHERE id = %s",
                (query_id,)).fetchone()
            self.assertEqual(row[1], "2026-08-02T00:00:00")
            self.assertEqual(row[2], 2)
            self.assertEqual(row[3], 3)

    def test_run_due_with_no_provider_reports_rather_than_pretending(self):
        # The deferral, made observable. A runner that silently did nothing
        # would be indistinguishable from a provider whose key was revoked --
        # silence is this system's failure mode.
        with scratchdb.scratch_schema() as (conn, _name):
            searchqueries.seed(conn, SEED_FILE, now="2026-08-02T00:00:00")
            dispatched, due = searchqueries.run_due(conn, provider=None,
                                                    now="2026-08-02T01:00:00")
            self.assertEqual(dispatched, 0)
            self.assertEqual(due, len(extract.ROLE_TRACK))
            # And nothing was recorded as having run.
            self.assertEqual(
                conn.execute("SELECT sum(run_count) FROM search_queries")
                .fetchone()[0], 0)

    def test_a_deferring_provider_writes_nothing_and_stays_due(self):
        # "A deferral is not a failure" (.claude/CLAUDE.md), applied here: a
        # provider returning None records no run, so the query is still due on
        # the next pass rather than going quiet for RERUN_HOURS.
        with scratchdb.scratch_schema() as (conn, _name):
            searchqueries.seed(conn, SEED_FILE, now="2026-08-02T00:00:00")
            dispatched, due = searchqueries.run_due(
                conn, provider=lambda query: None, now="2026-08-02T01:00:00")
            self.assertEqual(dispatched, 0)
            self.assertEqual(
                len(searchqueries.due_queries(conn, now="2026-08-02T02:00:00")),
                due)


@requires_db
class TestResultsRouteThroughTheGate(unittest.TestCase):
    """A posting reaches a Builder only through jobs_app, whatever the provider
    returned. The gate is the JOIN, not a filter anybody has to remember."""

    JOB = {
        "id": "relister-1",
        "platform": "google_jobs",
        "company_token": "reputed",
        "company_name": "Reputed Company",
        "source_id": "abc",
        "title": "AI Operations Coordinator",
        "job_url": "https://example.invalid/1",
        "description_text": "Confidential posting from a reputed company.",
        "status": "open",
        "first_seen": "2026-08-02T00:00:00",
        "last_seen": "2026-08-02T00:00:00",
    }

    def _job(self, conn, **overrides):
        row = dict(self.JOB, **overrides)
        columns = ", ".join(row)
        placeholders = ", ".join(["%s"] * len(row))
        conn.execute(f"INSERT INTO jobs ({columns}) VALUES ({placeholders})",
                     list(row.values()))
        conn.commit()
        return row["id"]

    def _linked_query(self, conn, job_id):
        normalized_text, normalized_location = searchnorm.validate("ai operations")
        query_id = conn.execute(
            searchnorm.REGISTER_QUERY_SQL,
            (normalized_text, normalized_location, "ai operations",
             searchnorm.DEFAULT_LOCATION, None, "builder", None,
             "2026-08-02T00:00:00")).fetchone()[0]
        searchqueries.attach_results(conn, query_id, [job_id], provider="test",
                                     now="2026-08-02T00:00:00")
        return query_id

    def _visible(self, conn, query_id):
        return conn.execute(
            "SELECT v.id FROM jobs_app v "
            "JOIN search_query_results r ON r.job_id = v.id "
            "WHERE r.query_id = %s", (query_id,)).fetchall()

    def test_a_posting_with_no_match_row_is_not_visible(self):
        # match.py writes a job_matches row only for postings that pass
        # relevance.union_sql. No match row means the gate said no, and the
        # search route cannot see it however it got into the table.
        with scratchdb.scratch_schema() as (conn, _name):
            job_id = self._job(conn)
            query_id = self._linked_query(conn, job_id)
            self.assertEqual(self._visible(conn, query_id), [])

    def test_the_link_row_exists_regardless(self):
        # attach_results takes NO gate decision, deliberately: raising max_tier
        # or fixing a `\y` pattern must retroactively surface postings this
        # pipeline already paid to fetch.
        with scratchdb.scratch_schema() as (conn, _name):
            job_id = self._job(conn)
            query_id = self._linked_query(conn, job_id)
            self.assertEqual(
                conn.execute("SELECT count(*) FROM search_query_results "
                             "WHERE query_id = %s", (query_id,)).fetchone()[0], 1)

    def test_a_gated_posting_becomes_visible_when_matched(self):
        with scratchdb.scratch_schema() as (conn, _name):
            job_id = self._job(conn)
            query_id = self._linked_query(conn, job_id)
            conn.execute(
                "INSERT INTO job_matches (job_id, profile, match_score, "
                "match_reasons, facts_version, criteria_version, matched_at) "
                "VALUES (%s, 'pursuit', 40, '[]', 3, 1, %s)",
                (job_id, "2026-08-02T00:00:00"))
            conn.commit()
            self.assertEqual(self._visible(conn, query_id), [(job_id,)])

    def test_an_incomplete_posting_stays_invisible_even_when_matched(self):
        # jobs_app's four completeness predicates apply here too -- the search
        # route inherits them by joining the view rather than the table.
        with scratchdb.scratch_schema() as (conn, _name):
            job_id = self._job(conn, id="no-description", description_text=None)
            query_id = self._linked_query(conn, job_id)
            conn.execute(
                "INSERT INTO job_matches (job_id, profile, match_score, "
                "match_reasons, facts_version, criteria_version, matched_at) "
                "VALUES (%s, 'pursuit', 40, '[]', 3, 1, %s)",
                (job_id, "2026-08-02T00:00:00"))
            conn.commit()
            self.assertEqual(self._visible(conn, query_id), [])

    def test_a_closed_posting_leaves_the_results(self):
        with scratchdb.scratch_schema() as (conn, _name):
            job_id = self._job(conn)
            query_id = self._linked_query(conn, job_id)
            conn.execute(
                "INSERT INTO job_matches (job_id, profile, match_score, "
                "match_reasons, facts_version, criteria_version, matched_at) "
                "VALUES (%s, 'pursuit', 40, '[]', 3, 1, %s)",
                (job_id, "2026-08-02T00:00:00"))
            conn.execute("UPDATE jobs SET status = 'closed' WHERE id = %s", (job_id,))
            conn.commit()
            self.assertEqual(self._visible(conn, query_id), [])


class TestTheBudgetPacesTheDispatch(unittest.TestCase):
    """docs/adr/0007 decision 4 against the schema, not against the predicate."""

    NOW = "2026-08-02T00:00:00"

    def _seed(self, conn, n, *, source="seeded", first_requested="2026-07-01T00:00:00"):
        """`n` rows, none of them ever run, all of them due."""
        ids = []
        for i in range(n):
            normalized_text, normalized_location = searchnorm.validate(f"query {i}")
            ids.append(conn.execute(
                searchnorm.REGISTER_QUERY_SQL,
                (normalized_text, normalized_location, f"query {i}",
                 searchnorm.DEFAULT_LOCATION, None, source, None,
                 first_requested)).fetchone()[0])
        conn.commit()
        return ids

    def test_the_allowance_caps_what_the_run_will_spend(self):
        with scratchdb.scratch_schema() as (conn, _name):
            self._seed(conn, 10)
            self.assertEqual(
                len(searchqueries.due_queries(conn, now=self.NOW)), 10,
                "unpaced, every never-run row is due -- the pre-decision-4 rule")
            self.assertEqual(
                len(searchqueries.due_queries(conn, now=self.NOW, allowance=3)), 3)
            self.assertEqual(
                len(searchqueries.due_queries(conn, now=self.NOW, allowance=0)), 0)

    def test_the_cut_falls_at_the_bottom_of_the_fair_share_order(self):
        # The order is last_run_at NULLS FIRST, id -- and the budget must take
        # a PREFIX of it, not an arbitrary subset. Otherwise the queries the
        # budget drops are not the ones whose turn had not come, and a row at
        # the back of the queue could starve for good.
        with scratchdb.scratch_schema() as (conn, _name):
            ids = self._seed(conn, 6)
            paced = [q["id"] for q in
                     searchqueries.due_queries(conn, now=self.NOW, allowance=4)]
            self.assertEqual(paced, sorted(ids)[:4])

    def test_a_second_run_the_same_day_reaches_what_the_budget_cut_off(self):
        # THIS IS WHAT DEMOTING RERUN_HOURS BUYS, and the row's "catch up
        # rather than being rate-limited to one run per RERUN_HOURS".
        #
        # Before decision 4 the freshness floor was the only gate, so a run
        # that dispatched took every due row and left nothing for 20 hours.
        # Now the first run stops at its budget and the SECOND run two hours
        # later picks up the remainder -- the rows it reaches were never run,
        # so the floor never sees them and cannot refuse them.
        with scratchdb.scratch_schema() as (conn, _name):
            ids = self._seed(conn, 10)
            first = [q["id"] for q in
                     searchqueries.due_queries(conn, now=self.NOW, allowance=4)]
            for query_id in first:
                searchqueries.record_run(conn, query_id, "serpapi", 1, now=self.NOW)
            later = "2026-08-02T02:00:00"      # two hours on, well inside the floor
            second = [q["id"] for q in
                      searchqueries.due_queries(conn, now=later, allowance=4)]
            self.assertEqual(len(second), 4)
            self.assertFalse(set(first) & set(second),
                             "the four already run are inside the freshness "
                             "floor and must not be re-asked")
            self.assertEqual(sorted(first + second), sorted(ids)[:8])

    def test_the_floor_still_refuses_a_fresh_query_however_large_the_budget(self):
        # The same claim as the predicate test, but through the SQL: a run
        # with money left over does not re-ask a question answered an hour ago.
        with scratchdb.scratch_schema() as (conn, _name):
            ids = self._seed(conn, 3)
            for query_id in ids:
                searchqueries.record_run(conn, query_id, "serpapi", 1, now=self.NOW)
            later = "2026-08-02T02:00:00"
            self.assertEqual(
                searchqueries.due_queries(conn, now=later, allowance=10_000), [])

    def test_an_idle_week_catches_up_where_the_old_cadence_could_not(self):
        # The row's "Done when", end to end and against the schema.
        #
        # Ten watched queries, nobody home for a week. On the machine's first
        # run back, all ten are past the floor -- but under the old rule that
        # was the whole story and the run could do nothing more until the next
        # 20-hour window. Now the allowance is what decides, so the elevated
        # figure an idle week produces (credits did not fall, days did) is
        # spent on the backlog in the runs that follow, on the same day.
        with scratchdb.scratch_schema() as (conn, _name):
            self._seed(conn, 10, first_requested="2026-07-01T00:00:00")
            idle = searchnorm.run_allowance(250, searchnorm.days_left_in_cycle(
                "2026-08-24T00:00:00"))          # a week of not spending
            steady = searchnorm.run_allowance(250, searchnorm.days_left_in_cycle(
                "2026-08-01T00:00:00"))
            self.assertGreater(idle, steady)
            wake = "2026-08-24T00:00:00"
            dispatched = [q["id"] for q in
                          searchqueries.due_queries(conn, now=wake, allowance=idle)]
            self.assertEqual(len(dispatched), 10,
                             "the elevated allowance covers the whole backlog")
            self.assertGreater(
                len(dispatched),
                len(searchqueries.due_queries(conn, now=wake, allowance=steady)),
                "and it reaches more than the steady-state figure would")


class TestPacingAllowanceReadsThePlan(unittest.TestCase):
    """searchqueries.pacing_allowance() -- the one place the plan data is
    fetched, so the two functions above can stay pure."""

    NOW = "2026-08-02T00:00:00"                  # 30 days left on the default

    class _Ledger:
        def __init__(self, data, config=None):
            self._data = data
            self.config = config if config is not None else {"serpapi": {}}

        def account(self, name, *, refresh=False):
            return self._data

    class _Provider:
        name = "serpapi"

        def __init__(self, ledger):
            self.ledger = ledger

    def test_it_divides_the_vendors_own_left_figure(self):
        provider = self._Provider(self._Ledger({"left": 240}))
        self.assertEqual(
            searchqueries.pacing_allowance(provider, now=self.NOW), 8)

    def test_an_unreachable_vendor_is_unpaced_and_not_zero(self):
        # serp/quota.py:141's account() returns None when it cannot reach the
        # vendor and that module's docstring says the disposition is ALLOW.
        # Reading it as 0 would turn a network blip into a night with no
        # searches, which is the failure that docstring exists to forbid.
        provider = self._Provider(self._Ledger(None))
        self.assertIsNone(searchqueries.pacing_allowance(provider, now=self.NOW))

    def test_a_vendor_with_no_left_figure_is_unpaced(self):
        provider = self._Provider(self._Ledger({"used": 10}))
        self.assertIsNone(searchqueries.pacing_allowance(provider, now=self.NOW))

    def test_an_exhausted_account_paces_to_zero(self):
        # Reached, and it said nothing is left. A real 0, distinct from None.
        provider = self._Provider(self._Ledger({"left": 0}))
        self.assertEqual(
            searchqueries.pacing_allowance(provider, now=self.NOW), 0)

    def test_it_reads_the_same_reserve_the_hard_refusal_reads(self):
        # quota.Ledger.check() raises ProviderRefused when left - reserve <= 0.
        # Pacing reads the SAME config entry, so the soft cap and the hard
        # refusal cannot disagree about how much of the account is ours.
        ledger = self._Ledger({"left": 60}, {"serpapi": {"reserve": 30}})
        self.assertEqual(
            searchqueries.pacing_allowance(self._Provider(ledger), now=self.NOW), 1)
        ledger = self._Ledger({"left": 60}, {"serpapi": {"reserve": 60}})
        self.assertEqual(
            searchqueries.pacing_allowance(self._Provider(ledger), now=self.NOW), 0)

    def test_a_provider_without_a_ledger_is_unpaced(self):
        # serp/dispatch.py's SearchQueryProvider takes `ledger=None` and every
        # test double in this tree is a bare callable with a `.name`.
        self.assertIsNone(searchqueries.pacing_allowance(None, now=self.NOW))
        self.assertIsNone(
            searchqueries.pacing_allowance(self._Provider(None), now=self.NOW))

    def test_run_due_derives_the_allowance_when_it_is_not_handed_one(self):
        # The wiring itself: main() derives it so it can print it, but any
        # other caller handing run_due() a provider and no allowance must get
        # the same pacing rather than an unpaced run.
        with scratchdb.scratch_schema() as (conn, _name):
            for i in range(6):
                normalized_text, normalized_location = searchnorm.validate(f"q{i}")
                conn.execute(searchnorm.REGISTER_QUERY_SQL,
                             (normalized_text, normalized_location, f"q{i}",
                              searchnorm.DEFAULT_LOCATION, None, "seeded", None,
                              "2026-07-01T00:00:00"))
            conn.commit()
            calls = []

            class Provider(self._Provider):
                def __call__(self, query):
                    calls.append(query["id"])
                    return []

            provider = Provider(self._Ledger({"left": 60}))   # 60/30 == 2
            dispatched, due = searchqueries.run_due(conn, provider=provider,
                                                    now=self.NOW)
            self.assertEqual((dispatched, due), (2, 2))
            self.assertEqual(len(calls), 2,
                             "four queries the budget declined must not reach "
                             "the provider at all -- that is the spend")


class TestTheNightlyStepIsWired(unittest.TestCase):

    def test_searchqueries_runs_before_extract(self):
        # It is ingest-shaped: what it dispatches produces `jobs` rows, so it
        # has to run before extract turns new postings into facts. Asserted
        # rather than assumed because the ordering is the one thing about
        # run-daily.py's list that is load-bearing.
        import importlib.util
        path = os.path.join(_BACKEND, "run-daily.py")
        spec = importlib.util.spec_from_file_location("run_daily", path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        names = [step if isinstance(step, str) else step[0] for step in module.STEPS]
        self.assertIn("searchqueries.py", names)
        self.assertLess(names.index("searchqueries.py"), names.index("extract.py"))


class TestTheContributorDatasetString(unittest.TestCase):
    """docs/adr/0009's wire format. Parsed on this side, written on api/'s."""

    def test_it_round_trips(self):
        for query_id in (1, 42, 9999999):
            self.assertEqual(
                searchqueries.query_id_from_dataset(
                    searchqueries.dataset_for_query(query_id)),
                query_id)

    def test_the_other_claim_modes_datasets_are_not_ours(self):
        """Both modes write submission_log.dataset, so this is the only thing
        telling them apart. A false positive here would advance a
        `search_queries` row from a `job_ingest_state` submit."""
        self.assertIsNone(
            searchqueries.query_id_from_dataset("google_jobs:query:ai-eng"))

    def test_nonsense_is_none_rather_than_a_raise(self):
        """This parses a free-TEXT column that predates the convention, so a
        row it cannot read is an ordinary thing to meet -- and a reconciler
        that raised on one would stop the whole nightly step."""
        for bad in (None, "", "search_query:", "search_query:x",
                    "search_query:1.5", "searchquery:1"):
            self.assertIsNone(searchqueries.query_id_from_dataset(bad), bad)


class TestTheReconcileStepSitsWhereTheDocstringSaysItDoes(unittest.TestCase):
    """The module docstring calls the five-step order load-bearing and gives
    two reasons for this one's place. Both are silent failures if it moves:
    after the decay, a query a contributor is actively feeding can retire on a
    last_result_at that had not been posted yet; after the dispatch, the
    pipeline re-runs tonight the query somebody already paid for.

    SOURCE ORDER RATHER THAN A RUN, because the alternative is standing up a
    database, a profile and a provider to observe the ordering of three calls.
    T-31 pinned "the read is above the early exit" the same way and for the
    same reason.
    """

    def _main_source(self):
        import inspect
        return inspect.getsource(searchqueries.main)

    def test_reconcile_runs_before_the_decay_and_before_the_dispatch(self):
        src = self._main_source()
        recon = src.index("reconcile_contributor_runs(conn)")
        self.assertLess(recon, src.index("apply_decay(conn"),
                        "reconcile must precede the decay: should_retire reads "
                        "last_result_at")
        self.assertLess(recon, src.index("run_due(conn"),
                        "reconcile must precede the dispatch: that is the "
                        "whole point of it")

    def test_reconcile_runs_after_the_seed(self):
        src = self._main_source()
        self.assertLess(src.index("seed(conn"),
                        src.index("reconcile_contributor_runs(conn)"))

    def test_the_count_is_printed_every_run(self):
        """Alert on volume, not errors: `reconciled=0` every night is how a
        wire that came loose is visible at all."""
        self.assertIn("reconciled={reconciled}", self._main_source())

    def test_a_dry_run_reconciles_nothing(self):
        """It WRITES, and --dry-run is a report. seed() takes a dry_run flag
        for the inverse reason and the docstring says so."""
        src = self._main_source()
        recon_line = next(ln for ln in src.splitlines()
                          if "reconcile_contributor_runs(conn)" in ln)
        self.assertIn("args.dry_run", recon_line)

    def test_the_allowance_is_printed_every_run(self):
        """Same rule as `reconciled=0`. The budget is now what decides whether
        anything is dispatched, so a run that spent nothing because the cap
        was 0 must not read as a night when nothing was due."""
        self.assertIn("allowance=", self._main_source())

    def test_the_allowance_is_derived_once_and_passed_on(self):
        """main() derives it so it can print it; run_due() derives it when it
        is handed None. Two derivations in one run could disagree -- the
        vendor read is cached, but a second call is a second chance to."""
        src = self._main_source()
        self.assertEqual(src.count("pacing_allowance("), 1)
        self.assertIn("allowance=allowance", src)

    def test_an_exhausted_account_says_so_on_stderr(self):
        """Pacing declines before any query reaches the provider, so
        serp/__init__.py:231's ledger.check() never raises and the step exits
        0 where it used to fail. That is deliberate; being quiet about it
        would not be."""
        src = self._main_source()
        self.assertIn("allowance == 0", src,
                      "`not allowance` would catch None -- unpaced means the "
                      "vendor was unreachable, not that it reported zero")
        exhausted = src[src.index("allowance == 0"):]
        self.assertIn("stderr", exhausted[:exhausted.index("if due and")])


if __name__ == "__main__":
    unittest.main()

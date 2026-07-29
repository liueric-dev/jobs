"""Ranking against a label, and the two ways this harness could invent a number.

Run:  python3 -m unittest tests.test_metrics_ranking

WHAT IS PINNED HERE AND WHY EACH ONE IS WORTH A TEST

`average_precision` and `precision_at_k` (evals/metrics.py) exist because
CLAUDE.md says "Report average precision as the measurement, precision@20 as
the objective" and neither was in this repo -- the only average precision was
tools/learned-ranker-probe.py:133 via sklearn, which is not in
requirements.txt. So these are new arithmetic with no incumbent to disagree
with, and the hand-computed cases below are the whole of their correctness.

TIES ARE THE INTERESTING CASE, NOT AN EDGE CASE.
backend/docs/HANDOFF-match-quality.md:155 (4.2) records 59 postings sharing
one fit_score, so a top-k boundary falls inside a tie block and ~half of any
top-k is an arbitrary draw. match_score is free arithmetic over a small
integer weight table and clusters the same way. A tie-blind implementation
would report whatever `sorted()` happened to do with the input order, so the
tie cases below assert two things: the hand-computed expectation, and that
permuting the input cannot move the answer.

THE TWO WAYS tools/mock-acceptance.py COULD INVENT AN ACCURACY FIGURE

  1. Writing to `public`. The driver runs extract.py and score.py IN-PROCESS
     against a live Postgres and is safe only while evals/scratchdb.py has
     repointed schema.SCHEMA at a throwaway schema (scratchdb.py:143). The
     refusal is pinned below, including that it fires before the connection
     argument is touched -- the guard tests pass None as the connection, so a
     guard that ran late would raise AttributeError instead of
     ContainmentError.

  2. Counting "the posting does not say" as a model error. A key field whose
     `value` is null means NOT DETERMINABLE FROM THE POSTING. Scoring it would
     mark the model wrong for not knowing something nobody could know, and
     every rate computed that way is fiction. It must leave the denominator,
     not enter it as a failure.
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import importlib.util  # noqa: E402

import relevance       # noqa: E402
import schema          # noqa: E402
from evals import metrics, scratchdb  # noqa: E402

_DRIVER = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                       "tools", "mock-acceptance.py")
_spec = importlib.util.spec_from_file_location("mock_acceptance", _DRIVER)
driver = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(driver)


class AveragePrecisionTest(unittest.TestCase):

    def test_a_perfect_ranking_scores_one(self):
        """Every positive above every negative is average precision 1.0.

        The definition's fixed point. If this fails nothing below means
        anything (evals/metrics.py average_precision).
        """
        r = metrics.average_precision([9, 8, 3, 1], [1, 1, 0, 0])
        self.assertEqual(r.n_positive, 2)
        self.assertAlmostEqual(r.value, 1.0)
        self.assertTrue(r.complete)

    def test_a_reversed_ranking_scores_its_hand_computed_value(self):
        """[0,0,1,1] gives precision 1/3 and 2/4 at the two positives.

        (1/3 + 1/2) / 2 = 0.4166..., computed by hand rather than by running
        the function -- a test that asserts the implementation's own output is
        a tautology.
        """
        r = metrics.average_precision([9, 8, 3, 1], [0, 0, 1, 1])
        self.assertAlmostEqual(r.value, (1 / 3 + 1 / 2) / 2)

    def test_an_all_positive_corpus_scores_one(self):
        """Nothing to get wrong: precision is 1 at every rank."""
        r = metrics.average_precision([5, 4, 3], [1, 1, 1])
        self.assertEqual(r.n_positive, 3)
        self.assertAlmostEqual(r.value, 1.0)

    def test_an_all_negative_corpus_returns_none_rather_than_zero(self):
        """No positives is an absent question, not a failed ranking.

        0.0 would read in a report as "the ranker put every good posting last",
        which is a different claim from "there were no good postings".
        """
        r = metrics.average_precision([5, 4, 3], [0, 0, 0])
        self.assertIsNone(r.value)
        self.assertEqual(r.n_positive, 0)
        self.assertEqual(r.n, 3)

    def test_an_empty_corpus_returns_none(self):
        """metrics.wilson's convention: an empty cell still has to print."""
        r = metrics.average_precision([], [])
        self.assertIsNone(r.value)
        self.assertEqual((r.n, r.n_positive, r.n_dropped), (0, 0, 0))

    def test_two_tied_rows_one_positive_score_the_mean_of_both_orderings(self):
        """One tie block, hand-enumerated.

        The two tie-breaks give AP 1.0 and 0.5, so the expectation is 0.75.
        A tie-blind implementation returns whichever of the two the input
        order happened to produce (metrics.TIE_MODES).
        """
        self.assertAlmostEqual(
            metrics.average_precision([7, 7], [1, 0]).value, 0.75)

    def test_three_tied_rows_one_positive_score_eleven_eighteenths(self):
        """The positive lands at rank 1, 2 or 3 with probability 1/3 each,
        giving (1 + 1/2 + 1/3) / 3 = 11/18. Hand-computed."""
        self.assertAlmostEqual(
            metrics.average_precision([7, 7, 7], [1, 0, 0]).value, 11 / 18)

    def test_the_tie_modes_bracket_the_expectation(self):
        """optimistic >= expected >= pessimistic, and the bounds are the two
        extreme tie-breaks: 1.0 and 0.5 for one positive in a block of two."""
        args = ([7, 7], [1, 0])
        opt = metrics.average_precision(*args, ties="optimistic").value
        pess = metrics.average_precision(*args, ties="pessimistic").value
        exp = metrics.average_precision(*args).value
        self.assertAlmostEqual(opt, 1.0)
        self.assertAlmostEqual(pess, 0.5)
        self.assertLessEqual(pess, exp)
        self.assertLessEqual(exp, opt)

    def test_permuting_a_tied_input_cannot_move_the_answer(self):
        """The property the expectation buys, stated directly.

        `sorted()` is stable, so a tie-blind implementation gives a different
        number for [1,0] than for [0,1] at the same scores -- and the caller
        (tools/mock-acceptance.py) feeds it rows in answer-key order, which is
        not a meaningful ordering.
        """
        a = metrics.average_precision([5, 5, 5, 5], [1, 1, 0, 0]).value
        b = metrics.average_precision([5, 5, 5, 5], [0, 1, 0, 1]).value
        c = metrics.average_precision([5, 5, 5, 5], [0, 0, 1, 1]).value
        self.assertAlmostEqual(a, b)
        self.assertAlmostEqual(b, c)

    def test_ties_between_blocks_still_respect_the_blocks(self):
        """A tied block below a clean positive: hand-computed at 0.75.

        Scores [9, 5, 5]: the 9 is a positive at rank 1 (precision 1), and one
        of the two tied rows is a positive at rank 2 or 3 with equal
        probability -- precision 2/2 or 2/3. AP = (1 + (1 + 2/3)/2) / 2.
        """
        r = metrics.average_precision([9, 5, 5], [1, 1, 0])
        self.assertAlmostEqual(r.value, (1.0 + (1.0 + 2 / 3) / 2) / 2)

    def test_a_row_with_no_score_is_dropped_rather_than_ranked_last(self):
        """None is "the ranker produced no number", which is not a rank.

        Ranking it last would score a missing answer as a confident bad one;
        this is metrics.within()'s argument (evals/metrics.py:157-168) applied
        to an ordering.
        """
        r = metrics.average_precision([9, None, 1], [1, 1, 0])
        self.assertEqual(r.n_positive, 1)
        self.assertAlmostEqual(r.value, 1.0)
        self.assertEqual((r.n, r.n_dropped, r.n_dropped_positive), (2, 1, 1))
        self.assertFalse(r.complete)

    def test_an_unknown_tie_mode_raises(self):
        """A typo must not silently select the default and report a number
        under a mode nobody ran (metrics.TIE_MODES)."""
        with self.assertRaises(ValueError):
            metrics.average_precision([1, 2], [0, 1], ties="average")


class UnscorableRowTest(unittest.TestCase):
    """The drop is right; hiding it is not.

    A row scores None exactly when the pipeline failed to score it, and in
    tools/mock-acceptance.py that means extraction tombstoned the posting or
    never wrote facts. Those failures are correlated with the thing being
    measured -- a posting whose description defeats the extractor is likelier
    to be one of the deliberately awkward ones -- so every drop removes a hard
    case and EVERY DROP MAKES THE RANKER LOOK BETTER.

    That is trap 4.1 (backend/docs/HANDOFF-match-quality.md:147, "do not
    compute metrics over a floor-filtered sample") pointing the other way:
    there MATCH_FLOOR hid the easy low end and cost one identical ranking
    function 0.619 -> 0.326.
    """

    def test_an_unscorable_positive_does_not_score_the_same_as_a_last_place_one(self):
        """The inflation, stated as a number.

        The same corpus with the same labels: one where the second positive
        has no score, one where it was scored dead last. Dropping it gives a
        perfect 1.0; ranking it last gives (1/1 + 2/3) / 2 = 0.833. If these
        ever agree, the drop has stopped being visible in the value.
        """
        dropped = metrics.average_precision([5, None, 1], [1, 1, 0])
        last = metrics.average_precision([5, 0, 1], [1, 1, 0])
        self.assertAlmostEqual(dropped.value, 1.0)
        self.assertAlmostEqual(last.value, (1.0 + 2 / 3) / 2)
        self.assertNotAlmostEqual(dropped.value, last.value)
        self.assertGreater(dropped.value, last.value)

    def test_the_drop_counts_come_back_with_the_statistic(self):
        """The caller cannot obtain the value without them: they are fields of
        the same return, and the two corpora above differ in `n_dropped` even
        where a reader might otherwise see two comparable percentages."""
        dropped = metrics.average_precision([5, None, 1], [1, 1, 0])
        last = metrics.average_precision([5, 0, 1], [1, 1, 0])
        self.assertEqual((dropped.n, dropped.n_dropped,
                          dropped.n_dropped_positive), (2, 1, 1))
        self.assertEqual((last.n, last.n_dropped, last.n_dropped_positive),
                         (3, 0, 0))

    def test_unpacking_the_old_two_tuple_now_raises(self):
        """`ap, n = average_precision(...)` was the shape before the drop
        counts existed, and it is exactly the call that would discard them.
        It must fail loudly rather than silently bind the wrong two fields."""
        with self.assertRaises(ValueError):
            _ap, _n = metrics.average_precision([5, 1], [1, 0])
        with self.assertRaises(ValueError):
            _p, _k = metrics.precision_at_k([5, 1], [1, 0], k=2)

    def test_coverage_prints_n_over_total(self):
        """docs/score-validation.md:270's shape ("55 usable in every repeat"
        of 120), so the report follows a precedent rather than inventing a
        format."""
        r = metrics.average_precision([5, None, None, 1], [1, 1, 0, 0])
        self.assertEqual(r.coverage(), "2/4")
        self.assertEqual(metrics.average_precision([5, 1], [1, 0]).coverage(),
                         "2/2")

    def test_dropping_a_positive_can_promote_a_negative_into_the_top_k(self):
        """Worse for precision@k than for average precision: a drop does not
        only shrink the denominator, it moves whatever was behind it up.

        Scores [9, None, 3] labels [1, 1, 0] at k=2 puts the negative in the
        top 2 at 0.5, where the same corpus with the positive scored 5 gives
        1.0 -- and n_dropped_positive is the 1 that explains the difference.
        """
        dropped = metrics.precision_at_k([9, None, 3], [1, 1, 0], k=2)
        scored = metrics.precision_at_k([9, 5, 3], [1, 1, 0], k=2)
        self.assertAlmostEqual(dropped.value, 0.5)
        self.assertAlmostEqual(scored.value, 1.0)
        self.assertEqual(dropped.n_dropped_positive, 1)
        self.assertEqual(scored.n_dropped_positive, 0)

    def test_a_corpus_where_everything_is_unscorable_reports_the_whole_drop(self):
        """The --dry-run case, and the "extraction is down" case. `.value` is
        None and `n_dropped` is the entire corpus, so the report can say which
        of the two it is looking at."""
        r = metrics.average_precision([None, None], [1, 0])
        self.assertIsNone(r.value)
        self.assertEqual((r.n, r.n_dropped, r.n_dropped_positive), (0, 2, 1))
        self.assertEqual(r.coverage(), "0/2")


class DroppedGoodPostingsAreNamedTest(unittest.TestCase):
    """An extraction failure on an intended-good posting is a finding.

    Not a caveat on the ranking figure and not a count: it is a pipeline
    defect on a posting the answer key says should have worked, and this
    corpus exists to catch exactly that. So the driver lists them by id.
    """

    def test_unscored_good_postings_are_listed_by_id(self):
        scored = [("mock_001", 90, True), ("mock_002", None, True),
                  ("mock_003", 10, False), ("mock_004", None, False)]
        q = driver.ranking_quality(scored, k=2)
        self.assertEqual(q["unscored_good"], ["mock_002"])
        self.assertEqual(q["unscored_bad"], ["mock_004"])
        self.assertEqual(q["n_unscored_good"], 1)

    def test_coverage_and_totals_travel_with_the_figures(self):
        """n, n_total and the "n/total" string are all in the same dict as the
        average precision, so an artifact cannot carry one without the other."""
        scored = [("mock_001", 90, True), ("mock_002", None, True),
                  ("mock_003", 10, False)]
        q = driver.ranking_quality(scored, k=2)
        self.assertEqual((q["n"], q["n_total"], q["coverage"]), (2, 3, "2/3"))
        self.assertFalse(q["complete"])

    def test_a_complete_corpus_says_so(self):
        """The control: with nothing dropped the lists are empty and
        `complete` is True, so the report suppresses the whole block."""
        scored = [("mock_001", 90, True), ("mock_003", 10, False)]
        q = driver.ranking_quality(scored, k=2)
        self.assertTrue(q["complete"])
        self.assertEqual(q["unscored_good"], [])
        self.assertEqual(q["n_unscored"], 0)

    def test_the_report_names_the_lost_good_postings_in_its_text(self):
        """Pinned on the rendered text, not just the dict: the number that
        gets quoted is the one that gets printed."""
        import io
        scored = [("mock_001", 90, True), ("mock_042", None, True),
                  ("mock_003", 10, False)]
        report = _blank_report(ranking=driver.ranking_quality(scored, k=2))
        buf = io.StringIO()
        driver.print_report(report, out=buf)
        text = buf.getvalue()
        self.assertIn("mock_042", text)
        self.assertIn("INTENDED-GOOD POSTINGS LOST TO EXTRACTION", text)
        self.assertIn("2/3", text)


def _blank_report(**overrides):
    """The minimum print_report() needs, so a rendering assertion does not
    require a database."""
    report = {
        "schema": "scratch_0123abcd", "mode": "test", "n_postings": 3,
        "n_scope": 3, "n_undecided": 0, "undecided_ids": [], "unkeyed": [],
        "facts": {"extracted": 2, "tombstoned": 1, "missing": 0},
        "matched": 1, "narratives": {}, "match_floor": 40,
        "field_accuracy": {}, "pooled": {"k": 0, "n": 0, "rate": None,
                                         "ci": (0.0, 1.0)},
        "gate": driver.gate_confusion([]), "max_tier_to_score": 2,
        "ranking": driver.ranking_quality([]), "branding_traps": [],
        "by_generator": {}, "confound": "", "teardown": "test",
    }
    report.update(overrides)
    return report


class PrecisionAtKTest(unittest.TestCase):

    def test_precision_at_k_counts_the_positives_in_the_top_k(self):
        """Two positives in the top 3 of a clean ordering is 2/3."""
        r = metrics.precision_at_k([9, 8, 7, 1], [1, 1, 0, 0], k=3)
        self.assertEqual(r.k, 3)
        self.assertAlmostEqual(r.value, 2 / 3)

    def test_k_larger_than_the_corpus_uses_the_corpus_size(self):
        """min(k, n), following top_k_overlap (evals/metrics.py:229).

        Dividing by 20 over 2 rows reports a ceiling of 0.1 that no ranker
        could beat, which would make the objective CLAUDE.md names
        unachievable by arithmetic rather than by quality.
        """
        r = metrics.precision_at_k([9, 1], [1, 0], k=20)
        self.assertEqual(r.k, 2)
        self.assertAlmostEqual(r.value, 0.5)

    def test_k_of_zero_returns_none_rather_than_dividing_by_zero(self):
        """`pursuit`'s daily_narrative_budget is 0, so an empty shortlist is a
        real configuration (score.py:1036-1040) and the table still prints."""
        r = metrics.precision_at_k([9, 1], [1, 0], k=0)
        self.assertIsNone(r.value)
        self.assertEqual(r.k, 0)

    def test_a_negative_k_returns_none(self):
        """Same branch, and it must not be reached by min() producing a
        negative slot count."""
        r = metrics.precision_at_k([9, 1], [1, 0], k=-5)
        self.assertIsNone(r.value)
        self.assertEqual(r.k, 0)

    def test_a_tie_across_the_k_boundary_is_averaged_not_broken(self):
        """Scores [2,1,1] labels [1,1,0] at k=2: the boundary falls inside the
        tied pair, which contributes its positive rate (1/2) for the one slot
        it fills. (1 + 0.5) / 2 = 0.75, hand-computed."""
        r = metrics.precision_at_k([2, 1, 1], [1, 1, 0], k=2)
        self.assertEqual(r.k, 2)
        self.assertAlmostEqual(r.value, 0.75)

    def test_a_tie_across_the_boundary_is_order_independent(self):
        """The same guarantee as the average precision case: which of two
        equal-scoring rows the caller listed first is not information."""
        a = metrics.precision_at_k([2, 1, 1], [1, 1, 0], k=2).value
        b = metrics.precision_at_k([2, 1, 1], [1, 0, 1], k=2).value
        self.assertAlmostEqual(a, b)

    def test_an_empty_corpus_returns_none(self):
        r = metrics.precision_at_k([], [], k=20)
        self.assertIsNone(r.value)
        self.assertEqual((r.n, r.k), (0, 0))


class ContainmentTest(unittest.TestCase):
    """The refusal that makes an in-process run against a live server safe.

    tools/mock-acceptance.py calls extract.main() and score.run_for_profile()
    in the SAME process, so every write goes wherever schema.SCHEMA points --
    and scratchdb.scratch_schema() moving it is the only thing standing
    between this driver and 11k production rows (scratchdb.py:143).
    """

    def setUp(self):
        self.original = schema.SCHEMA
        self.addCleanup(setattr, schema, "SCHEMA", self.original)

    def test_it_refuses_to_write_when_the_schema_is_public(self):
        """The default. schema.SCHEMA is "public" (schema.py:111) in any
        process that has not been through scratchdb.scratch_schema()."""
        schema.SCHEMA = "public"
        with self.assertRaises(driver.ContainmentError):
            driver.require_scratch_schema()

    def test_it_accepts_a_name_scratchdb_could_have_created(self):
        """The pattern is scratchdb's own (scratchdb.py:70), not a second
        copy: the only names this driver may write to are the ones that module
        creates and will later drop."""
        schema.SCHEMA = "scratch_0123abcd"
        self.assertEqual(driver.require_scratch_schema(), "scratch_0123abcd")
        self.assertTrue(scratchdb.SCRATCH_NAME.match("scratch_0123abcd"))

    def test_a_name_that_merely_is_not_public_is_still_refused(self):
        """"Not public" is satisfied by every typo. `scratch_prod`,
        `scratch_`, and a 9-hex name are all rejected."""
        for name in ("scratch_prod", "scratch_", "scratch_0123abcde",
                     "SCRATCH_0123ABCD", "jobs", ""):
            with self.subTest(name=name):
                with self.assertRaises(driver.ContainmentError):
                    driver.require_scratch_schema(name)

    def test_none_is_refused_rather_than_read_as_absent(self):
        """require_scratch_schema(None) means "check schema.SCHEMA", so the
        None case has to be reached through the global -- and a global that is
        somehow None must refuse, not pass."""
        schema.SCHEMA = None
        with self.assertRaises(driver.ContainmentError):
            driver.require_scratch_schema()

    def test_install_profiles_refuses_before_it_touches_the_connection(self):
        """Passing None as the connection is the assertion: a guard that ran
        after the first conn.execute() would raise AttributeError instead."""
        schema.SCHEMA = "public"
        with self.assertRaises(driver.ContainmentError):
            driver.install_profiles(None)

    def test_load_postings_refuses_before_it_touches_the_connection(self):
        schema.SCHEMA = "public"
        with self.assertRaises(driver.ContainmentError):
            driver.load_postings(None, [], None)

    def test_run_match_refuses_before_it_touches_the_connection(self):
        schema.SCHEMA = "public"
        with self.assertRaises(driver.ContainmentError):
            driver.run_match(None, [])

    def test_run_narratives_refuses_before_it_touches_the_connection(self):
        schema.SCHEMA = "public"
        with self.assertRaises(driver.ContainmentError):
            driver.run_narratives(None, None, 5)

    def test_run_extract_refuses_before_it_spends_anything(self):
        """extract.main() drains whatever the active profiles' union selects.
        Against `public` that is the production backlog and a real bill."""
        schema.SCHEMA = "public"
        with self.assertRaises(driver.ContainmentError):
            driver.run_extract()


class NarrativeLimitTest(unittest.TestCase):

    def setUp(self):
        self.original = schema.SCHEMA
        schema.SCHEMA = "scratch_0123abcd"
        self.addCleanup(setattr, schema, "SCHEMA", self.original)

    def test_a_missing_limit_is_refused_rather_than_narrating_nothing(self):
        """score.run_for_profile does `limit = budget if limit is None else
        limit` (score.py:1040) and `pursuit`'s budget is 0, so None would
        write zero narratives and report a silent success."""
        with self.assertRaises(ValueError):
            driver.run_narratives(None, None, None)


class PermissiveProfileTest(unittest.TestCase):
    """`mock_all` is the profile that makes the gate measurable at all.

    extract._eligible_sql gates on the union of ACTIVE profiles
    (extract.py:541-579), so without a second permissive profile the postings
    `pursuit` rejects would never acquire facts -- and measurement (b) could
    say which ones were rejected but never whether rejecting them was right.
    """

    def test_the_permissive_gate_admits_every_row(self):
        """Empty include lists collapse row_ok to TRUE and empty
        location_columns collapse loc_ok to TRUE, so tier_sql's CASE returns 1
        for every row (relevance.py:224-300)."""
        cfg = relevance.load(cfg=driver.PERMISSIVE_RELEVANCE)
        sql, params = relevance.tier_sql(cfg)
        self.assertEqual(params, {})
        self.assertIn("CASE WHEN (TRUE) AND (TRUE) THEN 1", sql)
        self.assertEqual(relevance.max_tier(cfg), 3)

    def test_the_permissive_config_is_non_empty_so_it_is_actually_stored(self):
        """profiles.upsert writes `json.dumps(cfg) if cfg else None`
        (profiles.py:207) and relevance.for_profile reads NULL as "use the
        shared config/relevance.json" (relevance.py:100-110).

        So a permissive gate expressed as `{}` would be stored as NULL and
        silently inherit the AUTHOR's software-title gate, which rejects most
        of this corpus -- the failure would look like a bad model rather than
        a bad config.
        """
        self.assertTrue(driver.PERMISSIVE_RELEVANCE)
        self.assertTrue(driver.PERMISSIVE_RELEVANCE.get("max_tier_to_score"))


class KeyDenominatorTest(unittest.TestCase):
    """A null key value means NOT DETERMINABLE, and must leave the denominator.

    This is the single easiest way to get a wrong number out of this harness:
    scoring "the posting does not say" as a model error marks the model wrong
    for not knowing something nobody could know, and inflates the error rate
    by however many fields the key left open.
    """

    KINDS = {"seniority_level": "enum", "years_experience_min": "int"}

    def entry(self, **fields):
        return {"verdict": "good",
                "fields": {k: {"value": v, "quote": None, "quote_field": None}
                           for k, v in fields.items()}}

    def test_a_null_key_value_leaves_the_denominator(self):
        """n counts only determinable fields; the null lands in
        `not_determinable` (tools/mock-acceptance.py expected_value)."""
        rows = [(self.entry(seniority_level="junior",
                            years_experience_min=None),
                 {"seniority_level": "junior", "years_experience_min": 5})]
        cells = driver.field_accuracy(rows, self.KINDS)
        self.assertEqual(cells["years_experience_min"]["n"], 0)
        self.assertEqual(cells["years_experience_min"]["not_determinable"], 1)
        self.assertIsNone(cells["years_experience_min"]["rate"])

    def test_a_null_key_value_is_not_counted_as_an_error(self):
        """The inverted form of the same assertion: the model answering 5
        where the key says "not determinable" must not lower any rate."""
        rows = [(self.entry(seniority_level="junior",
                            years_experience_min=None),
                 {"seniority_level": "junior", "years_experience_min": 5})]
        pooled = driver.pooled(driver.field_accuracy(rows, self.KINDS))
        self.assertEqual((pooled["k"], pooled["n"]), (1, 1))
        self.assertAlmostEqual(pooled["rate"], 1.0)

    def test_a_field_the_key_does_not_mention_at_all_is_also_excluded(self):
        """An absent field and a null value are the same statement: the key
        has no answer, so there is nothing to be right or wrong about."""
        rows = [(self.entry(seniority_level="junior"),
                 {"seniority_level": "junior", "years_experience_min": 5})]
        cells = driver.field_accuracy(rows, self.KINDS)
        self.assertEqual(cells["years_experience_min"]["n"], 0)
        self.assertEqual(cells["years_experience_min"]["not_determinable"], 1)

    def test_the_two_nulls_mean_opposite_things_and_are_never_collapsed(self):
        """The one assertion that puts them side by side.

        Same posting, same two fields, both null somewhere:

          * the KEY's null on years_experience_min -- the posting does not
            determine it. Leaves the denominator entirely.
          * the MODEL's null on seniority_level, against a key that answers
            "junior" -- the model failed to return a fact the posting states.
            Stays in the denominator, as a miss.

        Collapsing them in either direction invents the headline number: treat
        the key's null as an error and every rate drops by the fixture's own
        silence; treat the model's null as not-measurable and a model that
        returns nothing scores 100%.
        """
        rows = [(self.entry(seniority_level="junior",
                            years_experience_min=None),
                 {"seniority_level": None, "years_experience_min": None})]
        cells = driver.field_accuracy(rows, self.KINDS)
        self.assertEqual((cells["seniority_level"]["k"],
                          cells["seniority_level"]["n"]), (0, 1))
        self.assertEqual(cells["seniority_level"]["not_determinable"], 0)
        self.assertEqual((cells["years_experience_min"]["k"],
                          cells["years_experience_min"]["n"]), (0, 0))
        self.assertEqual(cells["years_experience_min"]["not_determinable"], 1)

    def test_a_field_the_model_omitted_is_a_miss_without_being_a_tombstone(self):
        """A live facts row that simply has NULL in one column. Not a
        tombstone -- `no_facts` stays 0 -- but still a miss, because the key
        says the posting determines it and the pipeline stored nothing."""
        rows = [(self.entry(seniority_level="junior"),
                 {"seniority_level": None, "tombstone": False})]
        cells = driver.field_accuracy(rows, self.KINDS)
        self.assertEqual((cells["seniority_level"]["k"],
                          cells["seniority_level"]["n"]), (0, 1))
        self.assertEqual(cells["seniority_level"]["no_facts"], 0)

    def test_a_determinable_field_the_model_got_wrong_is_counted(self):
        """The control. Without this the test above would pass on an
        implementation that excludes everything."""
        rows = [(self.entry(seniority_level="junior"),
                 {"seniority_level": "senior"})]
        cells = driver.field_accuracy(rows, self.KINDS)
        self.assertEqual((cells["seniority_level"]["k"],
                          cells["seniority_level"]["n"]), (0, 1))

    def test_a_tombstoned_row_is_a_miss_and_not_a_drop(self):
        """A posting the model could not read is a worse outcome than a wrong
        answer, not an absent one. Dropping tombstones would let a model that
        tombstones everything report perfect accuracy."""
        rows = [(self.entry(seniority_level="junior"),
                 {"seniority_level": None, "tombstone": True})]
        cells = driver.field_accuracy(rows, self.KINDS)
        self.assertEqual((cells["seniority_level"]["k"],
                          cells["seniority_level"]["n"]), (0, 1))
        self.assertEqual(cells["seniority_level"]["no_facts"], 1)

    def test_a_posting_with_no_facts_row_is_a_miss_and_not_a_drop(self):
        """Same argument for a row extraction never reached at all."""
        rows = [(self.entry(seniority_level="junior"), None)]
        cells = driver.field_accuracy(rows, self.KINDS)
        self.assertEqual((cells["seniority_level"]["k"],
                          cells["seniority_level"]["n"]), (0, 1))
        self.assertEqual(cells["seniority_level"]["no_facts"], 1)


class GateConfusionTest(unittest.TestCase):
    """Measurement (b): the cell nothing else in this repo can fill.

    Every existing quality figure -- task 05's 6.7%, task 10's 10.0% strict --
    is precision over rows the pipeline already surfaced. A rejected posting
    never acquires facts, a match, a score or a label, so no sample drawn from
    the live database contains one.
    """

    def test_the_false_negative_cell_counts_good_postings_the_gate_rejected(self):
        rows = [("good", True, "mock_001"), ("good", False, "mock_002"),
                ("bad", True, "mock_003"), ("bad", False, "mock_004")]
        g = driver.gate_confusion(rows)
        self.assertEqual(g["good_rejected"], 1)
        self.assertEqual(g["false_negatives"], ["mock_002"])
        self.assertEqual(g["false_positives"], ["mock_003"])
        self.assertAlmostEqual(g["gate_recall"], 0.5)
        self.assertAlmostEqual(g["gate_precision"], 0.5)

    def test_undecided_rows_are_excluded_from_every_cell(self):
        """The key carries at least one `undecided` verdict (mock_042 --
        "bachelor's degree or equivalent experience" against a cohort floor of
        no degree required). Folding it into either cell would decide by
        default the thing the key deliberately left open."""
        rows = [("good", True, "mock_001"), ("undecided", False, "mock_042")]
        g = driver.gate_confusion(rows)
        self.assertEqual(sum((g["good_admitted"], g["good_rejected"],
                              g["bad_admitted"], g["bad_rejected"])), 1)
        self.assertEqual(g["false_negatives"], [])

    def test_an_empty_cell_reports_none_rather_than_zero(self):
        """metrics.wilson's convention (evals/metrics.py:81-83): no intended
        -good postings means the recall question was not asked, which is not
        the same as recall 0."""
        g = driver.gate_confusion([("bad", False, "mock_004")])
        self.assertIsNone(g["gate_recall"])
        self.assertIsNone(g["gate_precision"])


class RankingQualityTest(unittest.TestCase):

    def test_the_chance_level_is_reported_beside_the_average_precision(self):
        """Average precision's chance level is the positive RATE, so 0.55 on a
        55%-good corpus is exactly no signal. Reporting the number without the
        baseline is how it gets read as a passing grade."""
        scored = [("a", 90, True), ("b", 80, True), ("c", 10, False)]
        q = driver.ranking_quality(scored, k=2)
        self.assertAlmostEqual(q["baseline"], 2 / 3)
        self.assertAlmostEqual(q["average_precision"], 1.0)
        self.assertAlmostEqual(q["precision_at_k"], 1.0)
        self.assertEqual(q["k"], 2)

    def test_k_is_clamped_to_the_corpus_and_both_values_are_recorded(self):
        """The default k is 20 (metrics.TOP_K) and this corpus has 3 rows, so
        the reported k is 3 -- and `k_requested` keeps the fact that 20 was
        asked for, because a bare "precision@3" in an artifact reads as a
        choice somebody made."""
        scored = [("a", 90, True), ("b", 80, True), ("c", 10, False)]
        q = driver.ranking_quality(scored)
        self.assertEqual((q["k"], q["k_requested"]), (3, metrics.TOP_K))

    def test_the_tie_interval_is_reported_so_a_tied_ranking_is_visible(self):
        """A completely tied ranking has an average precision that says
        nothing about the ranker, and the optimistic/pessimistic gap is what
        makes that legible instead of a plausible-looking point estimate."""
        scored = [("a", 50, True), ("b", 50, False), ("c", 50, True),
                  ("d", 50, False)]
        q = driver.ranking_quality(scored, k=2)
        self.assertGreater(q["ap_optimistic"] - q["ap_pessimistic"], 0.2)
        self.assertEqual(q["ties"]["distinct"], 1)
        self.assertEqual(q["ties"]["largest"], 4)


class ConfoundNoteTest(unittest.TestCase):
    """Measurement (e) exists to produce one specific sentence when it is true.

    Postings written by a model may be systematically easier for a model to
    extract from. 45 of the 55 are; 10 are human-written. If the human cell
    scores materially below the model cells, the headline number is inflated
    and the report has to say so in those words rather than leaving the reader
    to notice a table.
    """

    def cell(self, k, n, postings):
        return {"k": k, "n": n, "rate": k / n, "ci": metrics.wilson(k, n),
                "postings": postings}

    def test_a_large_human_model_gap_says_the_headline_is_inflated(self):
        note = driver.confound_note({
            "human": self.cell(60, 100, 10),
            "glm": self.cell(190, 200, 20),
            "claude": self.cell(190, 200, 20),
        })
        self.assertIn("INFLATED", note)

    def test_a_small_gap_says_no_confound_is_visible(self):
        note = driver.confound_note({
            "human": self.cell(94, 100, 10),
            "glm": self.cell(190, 200, 20),
        })
        self.assertIn("no confound visible", note)

    def test_no_human_postings_means_no_claim_either_way(self):
        """Silence rather than a reassuring sentence: with no human cell there
        is no confound check, and saying nothing is the honest output."""
        self.assertEqual(driver.confound_note({"glm": self.cell(19, 20, 20)}),
                         "")


if __name__ == "__main__":
    unittest.main()

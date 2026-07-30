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

THE PAIRING IN `bootstrap_delta` IS THE WHOLE FUNCTION, SO IT GETS A TEST THAT
FAILS IF IT IS LOST. Two orderings that differ by a monotone rescaling are the
same ordering, so a paired bootstrap must report a delta of exactly zero with a
zero-width interval. An independent bootstrap on the same two inputs reports
[-0.48, +0.47] instead -- that comparison is asserted directly below, with the
unpaired version written out in the test, because "it is paired" is otherwise a
claim about code nobody re-reads.

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

import math
import os
import random
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


#: A twelve-row corpus with the positives spread through it, so average
#: precision genuinely moves from resample to resample -- an interval on a
#: corpus whose statistic barely varies would pass the pairing test below for
#: the wrong reason.
_A = [100, 95, 90, 85, 80, 75, 70, 65, 60, 55, 50, 45]
_Y = [1, 0, 1, 1, 0, 0, 1, 0, 1, 0, 0, 1]

#: The SAME ordering as _A, expressed on a different scale. 3x + 7 is monotone,
#: so every ranking statistic in this module is identical on the two, and a
#: paired bootstrap must say so exactly.
_A_RESCALED = [3 * x + 7 for x in _A]

#: Draws for these tests. 400, not metrics.BOOTSTRAP_DRAWS, because the suite
#: runs on every commit and the endpoints asserted below are far enough from
#: their thresholds that a fifth of the draws resolves them.
_DRAWS = 400


def _unpaired_delta(scores_a, scores_b, labels, draws=_DRAWS,
                    seed=metrics.BOOTSTRAP_SEED):
    """What bootstrap_delta would be if it resampled the two sides separately.

    Written out here rather than exposed as an option on the real function:
    this is the wrong answer, and the only reason it exists is to be compared
    against the right one. Same percentile rule (metrics._percentile) and same
    draw count, so the two interval WIDTHS are comparable.
    """
    rng = random.Random(seed)
    n = len(labels)
    deltas = []
    for _ in range(draws):
        ia = [rng.randrange(n) for _ in range(n)]
        ib = [rng.randrange(n) for _ in range(n)]
        va = metrics.average_precision([scores_a[i] for i in ia],
                                       [labels[i] for i in ia]).value
        vb = metrics.average_precision([scores_b[i] for i in ib],
                                       [labels[i] for i in ib]).value
        if va is not None and vb is not None:
            deltas.append(va - vb)
    deltas.sort()
    return metrics._percentile(deltas, 0.025), metrics._percentile(deltas,
                                                                   0.975)


class PairedBootstrapTest(unittest.TestCase):
    """The property that distinguishes this from two separate intervals.

    Lifted from tools/learned-ranker-probe.py:410, where it was reachable only
    through an sklearn probe fitted on job_scores.fit_score -- CLAUDE.md's L1
    layer. Task 30 needs the same statistic over human labels (L0), which is
    why it now lives in evals/metrics.py.
    """

    def test_a_monotone_rescaling_of_the_same_ranking_gives_exactly_zero(self):
        """3x + 7 is the same ordering, so the delta is 0 on EVERY resample.

        Not "close to zero": the same index list scores both sides, the two
        statistics are equal on it, and the difference is exactly 0.0, so both
        percentiles are 0.0 too. This is the assertion that fails the instant
        the pairing is lost.
        """
        d = metrics.bootstrap_delta(_A, _A_RESCALED, _Y, draws=_DRAWS)
        self.assertEqual(d.value, 0.0)
        self.assertEqual((d.lo, d.hi), (0.0, 0.0))
        self.assertEqual(d.verdict(), "not distinguishable")

    def test_an_unpaired_bootstrap_would_manufacture_a_spread_here(self):
        """The same two inputs, resampled independently: [-0.48, +0.47].

        A width of ~0.95 average precision on two rankings that are the same
        ranking. That is the number the paired version exists to not print,
        and the pair of assertions is the reason the docstring's claim about
        overlapping intervals is not just a claim.
        """
        paired = metrics.bootstrap_delta(_A, _A_RESCALED, _Y, draws=_DRAWS)
        lo, hi = _unpaired_delta(_A, _A_RESCALED, _Y)
        self.assertEqual(paired.hi - paired.lo, 0.0)
        self.assertGreater(hi - lo, 0.5)

    def test_both_rankings_are_scored_on_the_identical_resample(self):
        """The pairing asserted on the rows the metric actually receives.

        _A's values are distinct and _A_RESCALED is 3x + 7 of them, so the two
        score lists a draw produces are equal under that map if and only if
        the two calls got the same index list in the same order. Checking the
        delta alone could not tell "same rows" from "different rows that
        happened to score alike".
        """
        seen = []

        def recording(scores, labels):
            seen.append(list(scores))
            return metrics.average_precision(scores, labels)

        metrics.bootstrap_delta(_A, _A_RESCALED, _Y, recording, draws=5)
        self.assertEqual(len(seen), 12)          # 1 observed + 5 draws, x2
        for i in range(0, len(seen), 2):
            self.assertEqual([3 * x + 7 for x in seen[i]], seen[i + 1])

    def test_identical_rankings_give_a_delta_of_exactly_zero(self):
        """The degenerate case of the same property, and the one a reader is
        most likely to try first: the same list on both sides."""
        d = metrics.bootstrap_delta(_A, list(_A), _Y, draws=_DRAWS)
        self.assertEqual((d.value, d.lo, d.hi), (0.0, 0.0, 0.0))
        self.assertEqual(d.n_undefined, 0)

    def test_a_clearly_better_ranking_is_called_better(self):
        """The control. Without it every assertion above would pass on an
        implementation that returns zero unconditionally.

        A perfect ordering against its own reverse, on 60 rows with 15
        positives: +0.855 [+0.769, +0.913].
        """
        n = 60
        a = [n - i for i in range(n)]
        y = [1 if i < 15 else 0 for i in range(n)]
        d = metrics.bootstrap_delta(a, list(reversed(a)), y, draws=_DRAWS)
        self.assertGreater(d.value, 0.8)
        self.assertGreater(d.lo, 0.0)
        self.assertEqual(d.verdict(), "better")
        self.assertEqual(
            metrics.bootstrap_delta(list(reversed(a)), a, y,
                                    draws=_DRAWS).verdict(), "worse")

    def test_the_verdict_needs_the_interval_to_exclude_zero_not_just_a_sign(self):
        """tools/learned-ranker-probe.py:585-586's rule, which is the whole
        reason the interval is in the return value.

        Twelve rows and a reversed ordering give a point estimate of +0.100 --
        a number that would read as a win -- inside [-0.42, +0.65]."""
        d = metrics.bootstrap_delta(_A, list(reversed(_A)), _Y, draws=_DRAWS)
        self.assertGreater(d.value, 0.0)
        self.assertLess(d.lo, 0.0)
        self.assertEqual(d.verdict(), "not distinguishable")


class BootstrapReproducibilityTest(unittest.TestCase):

    def test_the_same_seed_gives_the_same_interval_twice(self):
        """The claim the docstring makes about a quoted figure. random.Random
        is seeded per call, so this holds across processes too."""
        args = (_A, list(reversed(_A)), _Y)
        first = metrics.bootstrap_delta(*args, draws=_DRAWS)
        second = metrics.bootstrap_delta(*args, draws=_DRAWS)
        self.assertEqual(first, second)
        self.assertEqual(first.seed, metrics.BOOTSTRAP_SEED)

    def test_a_different_seed_moves_the_endpoints_but_not_the_estimate(self):
        """Why the seed is worth changing once: the point estimate is the
        observed statistic and cannot move, while the endpoints can -- so a
        verdict that flips between seeds was never a verdict."""
        args = (_A, list(reversed(_A)), _Y)
        first = metrics.bootstrap_delta(*args, draws=_DRAWS, seed=11)
        other = metrics.bootstrap_delta(*args, draws=_DRAWS, seed=12)
        self.assertEqual(first.value, other.value)
        self.assertNotEqual((first.lo, first.hi), (other.lo, other.hi))
        self.assertEqual(other.seed, 12)

    def test_the_point_estimate_is_the_observed_delta_not_the_resample_mean(self):
        """tools/learned-ranker-probe.py:428 reports np.mean(deltas), which no
        reader can recompute from the corpus. This reports the statistic on the
        full sample, so it is reproducible with two calls to
        average_precision and no RNG at all."""
        d = metrics.bootstrap_delta(_A, list(reversed(_A)), _Y, draws=_DRAWS)
        a = metrics.average_precision(_A, _Y).value
        b = metrics.average_precision(list(reversed(_A)), _Y).value
        self.assertAlmostEqual(d.value, a - b)

    def test_the_reported_draws_is_the_number_actually_performed(self):
        d = metrics.bootstrap_delta(_A, _A_RESCALED, _Y, draws=37)
        self.assertEqual(d.draws, 37)


class BootstrapDeltaShapeTest(unittest.TestCase):
    """A delta must not be printable without its interval. Ranked's argument.

    Ranked (evals/metrics.py) makes the drop counts unavoidable by being a
    5-tuple where callers expected two; Delta does the same to the three-tuple
    tools/learned-ranker-probe.py:428-430 returns, and additionally renders the
    interval from __str__ so the natural f-string carries it.
    """

    def test_unpacking_the_probes_three_tuple_now_raises(self):
        """`delta, lo, hi = bootstrap_delta(...)` was the old shape and is
        exactly the call that would discard the level, the n and the drop
        counts."""
        with self.assertRaises(ValueError):
            _d, _lo, _hi = metrics.bootstrap_delta(_A, _A_RESCALED, _Y,
                                                   draws=10)

    def test_formatting_the_delta_carries_the_interval(self):
        """f"{d}" is what a report writes, so that is what must be safe."""
        d = metrics.bootstrap_delta(_A, list(reversed(_A)), _Y, draws=_DRAWS)
        text = f"{d}"
        self.assertEqual(text, d.interval())
        self.assertIn("[", text)
        self.assertIn(f"{d.lo:+.3f}", text)
        self.assertIn(f"{d.hi:+.3f}", text)

    def test_an_undefined_delta_says_so_rather_than_formatting_none(self):
        """The empty and all-negative cases still have to print, and
        "undefined" is readable where "+None [+None, +None]" would be a
        TypeError in the middle of a report."""
        self.assertEqual(metrics.bootstrap_delta([], [], []).interval(),
                         "undefined")
        self.assertEqual(metrics.bootstrap_delta([], [], []).verdict(),
                         "undefined")

    def test_the_level_travels_with_the_interval(self):
        """"[+0.01, +0.09]" means different things at 95% and at 50%."""
        args = (_A, list(reversed(_A)), _Y)
        wide = metrics.bootstrap_delta(*args, draws=_DRAWS)
        narrow = metrics.bootstrap_delta(*args, draws=_DRAWS, level=0.5)
        self.assertEqual(wide.level, metrics.CI_LEVEL)
        self.assertEqual(narrow.level, 0.5)
        self.assertLess(narrow.hi - narrow.lo, wide.hi - wide.lo)

    def test_precision_at_k_can_be_the_metric(self):
        """CLAUDE.md's objective, as opposed to its measurement. k has to be
        bound by the caller because the metric is called as f(scores, labels).
        """
        n = 60
        a = [n - i for i in range(n)]
        y = [1 if i < 15 else 0 for i in range(n)]
        d = metrics.bootstrap_delta(
            a, list(reversed(a)), y,
            lambda s, yy: metrics.precision_at_k(s, yy, k=20),
            draws=_DRAWS)
        self.assertGreater(d.value, 0.0)
        self.assertEqual(d.verdict(), "better")


def _else_zero_delta(scores_a, scores_b, labels, draws=_DRAWS,
                     seed=metrics.BOOTSTRAP_SEED):
    """The rejected variant: score a degenerate resample 0.0, not skip it.

    tools/learned-ranker-probe.py:438's `... if 0 < yy.sum() < len(yy) else
    0.0`, transplanted onto this module's average_precision so the ONLY
    difference from bootstrap_delta is the substitution. Same seed, same draw
    count, same percentile rule, so the two intervals below differ for exactly
    one reason.
    """
    rng = random.Random(seed)
    n = len(labels)
    deltas = []

    def ap(scores, labs):
        value = metrics.average_precision(scores, labs).value
        return 0.0 if value is None else value

    for _ in range(draws):
        idx = [rng.randrange(n) for _ in range(n)]
        labs = [labels[i] for i in idx]
        deltas.append(ap([scores_a[i] for i in idx], labs)
                      - ap([scores_b[i] for i in idx], labs))
    deltas.sort()
    return metrics._percentile(deltas, 0.025), metrics._percentile(deltas,
                                                                   0.975)


class DegenerateResampleTest(unittest.TestCase):
    """A resample with no positives is skipped and counted, never scored 0.0.

    tools/learned-ranker-probe.py:438 substitutes 0.0 for the average precision
    of a resample with no positives. Both arms get 0.0, so that draw's DELTA is
    exactly 0.0, and enough of them drag the near end of the interval onto zero
    -- "not distinguishable" produced by an arithmetic guard rather than by the
    data. Rare at n in the hundreds; routine at the per-`role_track` n of about
    a dozen task 30 needs, where one positive in twelve rows makes (11/12)^12 =
    35% of draws degenerate.

    Note which half of that guard is at fault. `yy.sum() == 0` is genuinely
    undefined, so 0.0 is invented -- that is the biasing case, and it is what
    these tests pin. `yy.sum() == len(yy)` is NOT undefined: every ordering of
    an all-positive set has average precision 1.0, so the substitution is a
    wrong value whose error cancels in the difference (1.0 - 1.0 and 0.0 - 0.0
    are both 0.0). The guard is wrong twice and biasing once, and the second
    test below is the one that shows the cancelling half.
    """

    #: Twelve rows, one positive: the cell size task 30 will use, and 35% of
    #: draws contain no positive at all.
    SPARSE_N = 12

    def sparse(self):
        """A perfect ordering, its reverse, and one positive in twelve."""
        a = [self.SPARSE_N - i for i in range(self.SPARSE_N)]
        y = [1] + [0] * (self.SPARSE_N - 1)
        return a, list(reversed(a)), y

    def test_degenerate_draws_are_counted_and_do_not_pull_the_delta_to_zero(self):
        """The test that would have caught the original.

        Twelve rows, one positive, a perfect ordering against its reverse.
        Roughly a third of the draws contain no positive, so `draws_used` is
        well below `draws` -- and the interval still sits entirely above zero,
        because the draws that had nothing to compare were skipped rather than
        recorded as a tie.
        """
        a, b, y = self.sparse()
        d = metrics.bootstrap_delta(a, b, y, draws=_DRAWS)
        self.assertLess(d.draws_used, d.draws)
        self.assertGreater(d.n_undefined, _DRAWS // 5)
        self.assertAlmostEqual(d.value, 11 / 12)
        self.assertGreater(d.lo, 0.5)
        self.assertEqual(d.verdict(), "better")

    def test_the_rejected_else_zero_would_call_this_not_distinguishable(self):
        """Same corpus, same seed, same draws: the substitution puts the near
        end of the interval exactly on zero and flips the verdict.

        +0.917 [+0.823, +0.917] against +0.917 [+0.000, +0.917]. The point
        estimate is untouched -- this is not a difference in the statistic, it
        is a difference in what the interval is computed over -- which is why
        `value` alone could never have revealed it.
        """
        a, b, y = self.sparse()
        d = metrics.bootstrap_delta(a, b, y, draws=_DRAWS)
        lo, hi = _else_zero_delta(a, b, y)
        self.assertEqual(lo, 0.0)
        self.assertGreater(d.lo, lo)
        self.assertAlmostEqual(hi, d.hi)          # the far end is unaffected

    def test_draws_used_is_draws_minus_the_undefined_count(self):
        """A property, not an eleventh field, so it cannot disagree with the
        two counts it is derived from."""
        a, b, y = self.sparse()
        d = metrics.bootstrap_delta(a, b, y, draws=_DRAWS)
        self.assertEqual(d.draws_used, d.draws - d.n_undefined)
        clean = metrics.bootstrap_delta(_A, _A_RESCALED, _Y, draws=50)
        self.assertEqual(clean.draws_used, 50)

    def test_three_rows_do_not_distinguish_the_two_and_the_reason_is_arithmetic(self):
        """Why the obvious tiny construction is NOT the test for this.

        At n=3 with one positive, a draw of three copies of that positive has
        probability (1/3)^3 = 3.7%, which is more than the 2.5% the lower
        percentile sits at -- and an all-positive draw has a delta of exactly
        0.0 LEGITIMATELY, since every ordering of an all-positive set scores
        1.0. So the 2.5th percentile is 0.0 with or without the substitution,
        and a test written here would have passed on the buggy version.
        """
        a, b, y = [9, 8, 7], [7, 8, 9], [1, 0, 0]
        d = metrics.bootstrap_delta(a, b, y, draws=_DRAWS)
        lo, _hi = _else_zero_delta(a, b, y)
        self.assertEqual(d.lo, 0.0)
        self.assertEqual(lo, 0.0)
        self.assertAlmostEqual(
            metrics.average_precision([9, 8, 7], [1, 1, 1]).value, 1.0)

    def tie_refusing(self):
        """A caller-supplied metric with an undefined case of its own.

        Not hypothetical: metrics.spearman returns None when either column is
        constant, and top_k_overlap returns None with no comparable rows, so a
        metric with a precondition the resample can violate is the normal
        shape. This one refuses a resample containing duplicated rows -- which
        is almost every resample, since drawing 8 of 8 rows all distinct has
        probability 8!/8^8 = 0.2%.
        """
        def metric(scores, labels):
            if len(set(scores)) < len(scores):
                return None
            return metrics.average_precision(scores, labels)
        return metric

    def eight_rows(self):
        n = 8
        a = [n - i for i in range(n)]
        return a, list(reversed(a)), [1] + [0] * (n - 1)

    def test_a_metric_undefined_on_most_draws_reports_nothing(self):
        """The MIN_USABLE_FRACTION floor, reached the only way it can be.

        No corpus with a positive in it can reach the floor through empty
        draws: ((n - p) / n)^n is bounded above by 1/e = 0.368 for every n and
        p >= 1, which is the point of the test below. So the floor exists for a
        caller-supplied metric with undefined cases of its own -- and an
        interval computed from 1 usable draw out of 400 is exactly what it is
        there to refuse to print.
        """
        a, b, y = self.eight_rows()
        d = metrics.bootstrap_delta(a, b, y, self.tie_refusing(), draws=_DRAWS)
        self.assertLess(d.draws_used, metrics.MIN_USABLE_FRACTION * d.draws)
        self.assertIsNone(d.value)
        self.assertIsNone(d.lo)
        self.assertEqual(d.verdict(), "undefined")

    def test_refusing_still_reports_the_counts_that_explain_the_refusal(self):
        """"Too sparse to bootstrap" is a finding, so n, draws and draws_used
        survive the refusal, and the rendered string names the reason rather
        than printing a blank that could equally mean "no labels here"."""
        a, b, y = self.eight_rows()
        d = metrics.bootstrap_delta(a, b, y, self.tie_refusing(), draws=_DRAWS)
        self.assertEqual((d.n, d.draws), (len(y), _DRAWS))
        self.assertIn(f"{d.draws_used}/{d.draws}", d.interval())
        self.assertIn("usable", d.interval())

    def test_the_metric_being_undefined_on_the_sample_is_a_different_outcome(self):
        """`draws` is 0 when the statistic does not exist on the corpus itself,
        against `draws_used` < `draws` when it existed and the draws ate it.
        Both give value None, and a report that cannot tell them apart cannot
        say whether to label more postings or to stop asking."""
        a, b, y = self.eight_rows()
        no_positives = metrics.bootstrap_delta(a, b, [0] * len(y),
                                               draws=_DRAWS)
        ate_the_draws = metrics.bootstrap_delta(a, b, y, self.tie_refusing(),
                                                draws=_DRAWS)
        self.assertEqual(no_positives.draws, 0)
        self.assertEqual(ate_the_draws.draws, _DRAWS)
        self.assertIsNone(no_positives.value)
        self.assertIsNone(ate_the_draws.value)

    def test_the_floor_is_not_reachable_by_empty_draws_alone(self):
        """The bound the constant's comment claims, checked rather than
        asserted in prose: ((n-1)/n)^n rises to 1/e and never reaches 0.5, so a
        one-positive corpus always keeps more than half its draws."""
        for n in (2, 3, 5, 12, 100):
            with self.subTest(n=n):
                self.assertLess(((n - 1) / n) ** n, 1 / math.e)
                self.assertLess(((n - 1) / n) ** n,
                                1 - metrics.MIN_USABLE_FRACTION)


class PercentileTest(unittest.TestCase):
    """The interval is a percentile one, and the percentile is hand-checked.

    Deliberately not numpy: evals/metrics.py's "NOT sklearn" comment gives the
    reason -- neither numpy nor sklearn is in requirements.txt, so the probe
    this was lifted from does not run on a clean checkout. That makes
    _percentile new arithmetic with no incumbent to agree with, so the
    hand-computed values below are the whole of its correctness.
    """

    #: Five elements, so (len - 1) * q lands between indices for most q and the
    #: interpolation is actually exercised.
    V = [0.0, 0.1, 0.2, 0.3, 0.4]

    def test_the_endpoints_are_the_extremes(self):
        self.assertAlmostEqual(metrics._percentile(self.V, 0.0), 0.0)
        self.assertAlmostEqual(metrics._percentile(self.V, 1.0), 0.4)

    def test_a_percentile_landing_on_an_index_is_that_element(self):
        """(5 - 1) * 0.25 = 1.0 exactly, so this is V[1] and no interpolation
        happens."""
        self.assertAlmostEqual(metrics._percentile(self.V, 0.25), 0.1)
        self.assertAlmostEqual(metrics._percentile(self.V, 0.5), 0.2)

    def test_a_percentile_between_two_indices_interpolates_linearly(self):
        """(5 - 1) * 0.3 = 1.2, so V[1] + (V[2] - V[1]) * 0.2 = 0.12.
        Hand-computed; this is numpy.percentile's default `linear` method,
        which is what tools/learned-ranker-probe.py:429-430 used."""
        self.assertAlmostEqual(metrics._percentile(self.V, 0.3), 0.12)
        self.assertAlmostEqual(metrics._percentile(self.V, 0.975), 0.39)

    def test_the_two_five_percent_tail_of_five_elements_is_one_percent_in(self):
        """(5 - 1) * 0.025 = 0.1, so V[0] + (V[1] - V[0]) * 0.1 = 0.01 -- NOT
        V[0]. Truncating to int(q * n) would give 0.0 here, which is the
        shortcut the docstring rejects."""
        self.assertAlmostEqual(metrics._percentile(self.V, 0.025), 0.01)
        self.assertNotAlmostEqual(metrics._percentile(self.V, 0.025), 0.0)

    def test_a_single_element_is_its_own_every_percentile(self):
        self.assertAlmostEqual(metrics._percentile([7.5], 0.025), 7.5)
        self.assertAlmostEqual(metrics._percentile([7.5], 0.975), 7.5)

    def test_an_empty_vector_is_none_rather_than_an_index_error(self):
        self.assertIsNone(metrics._percentile([], 0.5))


class BootstrapEdgeCaseTest(unittest.TestCase):
    """None where the statistic does not exist; never a zero, never a raise.

    average_precision's convention (evals/metrics.py): 0.0 would read in a
    report as "the two rankings are equally good", which is a different claim
    from "there was nothing here to compare".
    """

    def test_an_empty_corpus_returns_none_rather_than_raising(self):
        d = metrics.bootstrap_delta([], [], [])
        self.assertIsNone(d.value)
        self.assertIsNone(d.lo)
        self.assertEqual((d.n, d.n_dropped, d.draws), (0, 0, 0))

    def test_no_resampling_is_attempted_on_an_empty_corpus(self):
        """`draws` is 0, not 2000, so a report cannot say it bootstrapped
        something it never touched."""
        self.assertEqual(metrics.bootstrap_delta([], [], []).draws, 0)

    def test_a_corpus_with_no_positives_returns_none_rather_than_zero(self):
        """Undefined on the sample itself, so resampling it would put an
        interval around a number that does not exist. n survives, because
        "there were 12 rows and none of them were positive" is the finding."""
        d = metrics.bootstrap_delta(_A, list(reversed(_A)), [0] * len(_A))
        self.assertIsNone(d.value)
        self.assertEqual(d.n, len(_A))
        self.assertEqual(d.draws, 0)

    def test_a_single_row_does_not_raise_and_reports_its_n_of_one(self):
        """Every resample of one row is that row, so the interval collapses to
        a point. That is the resampling saying there is no variability to
        estimate -- NOT that the difference is certain -- and `n` is the field
        that makes it obvious which of the two a reader is looking at."""
        d = metrics.bootstrap_delta([5], [7], [1], draws=_DRAWS)
        self.assertEqual((d.value, d.lo, d.hi), (0.0, 0.0, 0.0))
        self.assertEqual(d.n, 1)

    def test_a_single_negative_row_is_undefined_rather_than_zero(self):
        """n=1 with a negative label: average precision does not exist on it,
        and the pair of tests keeps the two n=1 outcomes apart."""
        d = metrics.bootstrap_delta([5], [7], [0], draws=_DRAWS)
        self.assertIsNone(d.value)
        self.assertEqual(d.n, 1)

    def test_undefined_resamples_are_counted_rather_than_scored_as_zero(self):
        """tools/learned-ranker-probe.py:438 returns 0.0 when a resample has no
        positives, which injects exact zeros into the delta distribution and
        narrows both percentiles for a reason unrelated to the rankings.

        Four rows with one positive: (3/4)^4 = 32% of draws contain no
        positive at all, so the count is large and visible."""
        d = metrics.bootstrap_delta([9, 8, 7, 6], [6, 7, 8, 9], [1, 0, 0, 0],
                                    draws=300)
        self.assertIsNotNone(d.value)
        self.assertGreater(d.n_undefined, 0)
        self.assertLess(d.n_undefined, d.draws)

    def test_a_row_unscorable_on_either_side_is_dropped_and_counted(self):
        """Keeping it would score the two rankings over different row sets,
        which is the pairing gone. Ranked's warning applies to both sides at
        once, so the count and the positives among it come back in the
        Delta."""
        d = metrics.bootstrap_delta([9, None, 7, 6], [9, 8, None, 6],
                                    [1, 1, 0, 0], draws=50)
        self.assertEqual(d.n, 2)
        self.assertEqual(d.n_dropped, 2)
        self.assertEqual(d.n_dropped_positive, 1)
        self.assertFalse(d.complete)

    def test_a_corpus_scorable_on_both_sides_is_complete(self):
        """The control for the drop counts."""
        d = metrics.bootstrap_delta(_A, _A_RESCALED, _Y, draws=50)
        self.assertTrue(d.complete)
        self.assertEqual((d.n_dropped, d.n_dropped_positive), (0, 0))

    def test_a_length_mismatch_raises(self):
        """A caller bug, not an outcome of the data: zip() would silently
        truncate to the shortest and report a delta over a prefix."""
        with self.assertRaises(ValueError):
            metrics.bootstrap_delta([1, 2, 3], [1, 2], [1, 0, 0])
        with self.assertRaises(ValueError):
            metrics.bootstrap_delta([1, 2], [1, 2], [1, 0, 0])

    def test_an_unusable_draws_or_level_raises(self):
        """Same argument as average_precision's unknown tie mode: a typo must
        not silently produce a number under a protocol nobody ran."""
        with self.assertRaises(ValueError):
            metrics.bootstrap_delta(_A, _A_RESCALED, _Y, draws=0)
        for level in (0.0, 1.0, 95, -0.5):
            with self.subTest(level=level):
                with self.assertRaises(ValueError):
                    metrics.bootstrap_delta(_A, _A_RESCALED, _Y, level=level)


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

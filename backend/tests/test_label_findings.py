"""The one statistic in tools/label-findings.py that has a judgement call in it.

Run:  python3 -m unittest tests.test_label_findings

WHY THIS FILE EXISTS WHEN NO OTHER tools/ SCRIPT HAS ONE

Read-only reporting tools in tools/ are not unit-tested here, and that is
mostly right: their output is a count you can eyeball against the rows it came
from. `interval_stats` is the exception, for a specific and documented reason.

The per-posting labelling rate was published at 154 s off FOUR intervals, went
into two documents, and became the basis of every Builder-session estimate in
the run -- "twenty minutes is ~8 postings", "the ten overlap rows are ~26
minutes", "the DoD is ~4.3 hours". Re-derived at n=29 the median is 93 s. The
error was not arithmetic; it was that the sample was entirely inside a warm-up
curve nobody had checked for, while the note printed beside the number asserted
the opposite ("the fastest interval is the first, which is the opposite of a
warm-up curve").

So the two things pinned below are the two things that were wrong:

  1. A BREAK IS NOT A POSTING. One 5,765 s gap in a real sitting drags the mean
     from 110 s to 299 s. Excluding it is a judgement call with a threshold, so
     the threshold's behaviour is asserted rather than left to be re-derived by
     the next person who wonders why two means differ by 3x.
  2. THE CURVE MUST BE ABLE TO SAY "I DON'T KNOW". `curve` compares the first
     and last quartile, and at small n a quartile is one or two intervals --
     which would manufacture a trend out of two adjacent postings. It returns
     None instead, and that refusal is the assertion.

The real 2026-07-31 sitting is used as the fixture rather than invented
numbers, so that if this ever disagrees with `tools/label-findings.py --timing`
against the live table, one of the two is wrong and the disagreement is visible.
"""

import os
import sys
import unittest
import importlib.util

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# tools/label-findings.py is hyphenated, which is deliberate -- everything in
# tools/ is a command rather than an importable module -- so it is loaded by
# path rather than by name.
_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                     "tools", "label-findings.py")
_spec = importlib.util.spec_from_file_location("label_findings", _PATH)
label_findings = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(label_findings)

#: The 2026-07-31 sitting, verbatim: successive MIN(labelled_at) per job_id
#: over the first 31 labelled postings of pursuit-v1. One labeller, round 1.
#: The 5765 is a break in the sitting, not a posting that took 96 minutes.
SITTING = [87, 170, 247, 110, 5765, 81, 178, 83, 133, 93,
           125, 74, 113, 131, 119, 171, 116, 80, 69, 251,
           43, 101, 38, 78, 50, 67, 91, 76, 73, 149]


class IntervalStats(unittest.TestCase):

    def test_the_break_is_excluded_and_it_moves_the_mean_by_almost_3x(self):
        """The whole reason --break-secs exists, stated as a number."""
        st = label_findings.interval_stats(SITTING, 600)
        self.assertEqual(st["breaks"], [5765])
        self.assertEqual(len(st["kept"]), 29)
        # Including the break, the "mean seconds per posting" is a statistic
        # about someone's dinner. This is the gap the threshold closes.
        self.assertAlmostEqual(st["mean_all"], 298.7, places=1)
        self.assertAlmostEqual(st["mean"], 110.2, places=1)
        self.assertEqual(st["median"], 93)

    def test_the_warm_up_curve_the_n_equals_4_sample_could_not_see(self):
        """First quartile 137 s, last quartile 83 s -- on the same sitting.

        The original four intervals (87, 170, 247, 110) are the first four
        entries of SITTING and average 153 s. That is not a rate; it is the
        top of the curve.
        """
        st = label_findings.interval_stats(SITTING, 600)
        q, first, last = st["curve"]
        self.assertEqual(q, 7)
        self.assertAlmostEqual(first, 137.0, places=0)
        self.assertAlmostEqual(last, 83.0, places=0)
        self.assertLess(last, first * 0.8, "the speeding-up branch must fire")
        self.assertAlmostEqual(sum(SITTING[:4]) / 4, 153.5, places=1)

    def test_a_raised_threshold_readmits_the_break(self):
        """The threshold is an argument, not a constant, and it is load-bearing."""
        st = label_findings.interval_stats(SITTING, 6000)
        self.assertEqual(st["breaks"], [])
        self.assertEqual(len(st["kept"]), 30)
        self.assertAlmostEqual(st["mean"], 298.7, places=1)

    def test_the_curve_refuses_rather_than_inventing_a_trend(self):
        """Below n=12 a quartile is two intervals, and two points are not a trend."""
        for n in range(2, 12):
            st = label_findings.interval_stats(list(range(10, 10 + n)), 600)
            self.assertIsNone(st["curve"], f"n={n} must not report a curve")
        st = label_findings.interval_stats(list(range(10, 22)), 600)
        self.assertIsNotNone(st["curve"], "n=12 is three per quartile, so it can")

    def test_an_entirely_interrupted_sitting_returns_None_rather_than_raising(self):
        """A real outcome -- the caller still has to print something."""
        self.assertIsNone(label_findings.interval_stats([9000, 9000], 600))


if __name__ == "__main__":
    unittest.main()

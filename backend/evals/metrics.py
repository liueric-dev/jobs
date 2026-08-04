"""Per-field comparison rules, and the arithmetic that turns them into a number.

PROMOTED, NOT REWRITTEN
    The comparison rules come from tools/compare-extract.py:52-60 -- its
    SCALAR_FIELDS list and its jaccard(). What is added here is the kind
    lookup (evals/tasks/extract.py:23 FIELD_KINDS, so the rule lives beside
    the field list), grouping by platform, and an interval.

COMPARISON RUNS AFTER normalize()
    Comparing raw model output would score formatting: "Mid-Level" and "mid"
    are the same answer and extract._enum() already knows it. Every value
    reaching this module has been through tasks/extract.py parse(), which is
    the exact dict job_facts would have stored.

TWO AGREEMENT NUMBERS, BECAUSE THEY ANSWER DIFFERENT QUESTIONS
    `agree2` is repeat 1 against repeat 2 -- exactly the protocol that
    produced the provisional n=17 figures (two extractions, identical
    prompt, identical parameters). It is the number those are comparable
    to, and it is a clean Bernoulli trial per record, so a Wilson interval
    on it is valid.

    `unanimous` is all N repeats identical. It is strictly the harder
    question and it is what distinguishes "flips between two values" from
    "unstable across three" -- but it is NOT comparable to a figure measured
    over two runs, and the calibration thresholds in
    backend/config/criteria.json were set against two-run numbers. Reporting
    only unanimity would trip a gate that was drawn for a different quantity.

    `pairwise` -- the mean over all C(N,2) pairs -- estimates the same
    quantity as `agree2` using more data, so it is reported as a point
    estimate. It gets no interval: the C(N,2) pairs from one record are not
    independent trials, and a Wilson interval over 3n dependent pairs would
    be narrower than the evidence supports.

WILSON, NOT NORMAL APPROXIMATION
    At the sample sizes a per-platform cell actually has -- 9 records for
    lever, because 9 is every lever row in production -- the normal
    approximation gives intervals that run past 1.0 and are meaningless at
    the boundary. Wilson is well behaved at small n and at proportions near
    1, which is where every number in this measurement sits.

A RECORD NOT OK IN EVERY REPEAT IS NOT SILENTLY DROPPED
    If repeat 1 parses and repeat 2 tombstones, excluding the record would
    flatter the model by hiding its least stable answers. Field agreement is
    computed over records usable in every repeat, and the count that were
    not is reported beside it -- never folded away.
"""

import json
import math
import random
from typing import NamedTuple

#: greenhouse and ashby are the "clean ATS" end that the README hypothesises
#: the 95% figure actually describes. Everything else is the messy end.
#: Grouped here rather than at the call site so the clean-vs-messy gap is
#: computed from one definition.
CLEAN_PLATFORMS = ("greenhouse", "ashby")

Z95 = 1.959963984540054

#: Tolerance bands reported for a `score` field, in fit_score points.
#:
#: ALL THREE, NEVER ONE. Picking a single band is picking an answer: at +/-0
#: fit_score looks unstable, at +/-10 it looks fine, and the gap between them
#: is the finding. 5 is one step of the granularity the model actually uses --
#: 1,098 of the 1,240 non-NULL fit_scores in production are multiples of 5
#: (measured 2026-07-28) -- so +/-5 is "one notch", not a tuned threshold.
SCORE_TOLERANCES = (0, 5, 10)

#: k for top-k ranking overlap. 20 because that is the shortlist a person
#: actually sees (score.py's daily_narrative_budget defaults to 20) and
#: because CLAUDE.md names precision@20 as the objective. It is reported
#: BESIDE rank correlation, never instead of it: a count of twenty cannot
#: resolve the differences being decided on, which is the same document's
#: reason for making average precision the measurement.
TOP_K = 20


def wilson(k, n, z=Z95):
    """Wilson score interval for k successes in n trials. (lo, hi).

    Returns (0.0, 1.0) for n == 0 rather than raising: an empty cell is a
    real outcome of a stratified corpus and the table still has to print.
    """
    if n <= 0:
        return 0.0, 1.0
    p = k / n
    denom = 1.0 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = (z / denom) * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return max(0.0, centre - half), min(1.0, centre + half)


def _as_set(value):
    """tech_stack as normalize() stores it: a JSON array in a string.

    Tolerates a list, a None and a non-JSON string, because the point of
    this harness is measuring real malformed answers rather than assuming
    they do not occur.
    """
    if value is None:
        return set()
    if isinstance(value, (list, tuple, set)):
        return {str(v) for v in value}
    try:
        parsed = json.loads(value)
    except (TypeError, ValueError):
        return {str(value)}
    if isinstance(parsed, list):
        return {str(v) for v in parsed}
    return {str(parsed)}


def jaccard(a, b):
    """tools/compare-extract.py:99. Two empty sets agree."""
    sa, sb = _as_set(a), _as_set(b)
    if not sa and not sb:
        return 1.0
    return len(sa & sb) / len(sa | sb)


def compare(kind, a, b):
    """Agreement between two values of one field, in [0, 1].

    `int` compares None as distinct from 0 -- "the posting did not say" and
    "the posting said zero" are different facts and `==` already keeps them
    apart, which is why this is not special-cased.
    """
    if kind == "set":
        return jaccard(a, b)
    return 1.0 if a == b else 0.0


def exact(kind, a, b):
    """Agreement as a yes/no, including for `set`.

    The three headline columns must all mean the same thing or the table is
    unreadable: a `set` field whose agree2 is an exact-match rate and whose
    pairwise column is a graded Jaccard mean invites reading 32% and 67% as
    a contradiction. Jaccard is reported in its own column instead, which is
    also the figure the provisional "tech_stack 90% (Jaccard)" is comparable
    to.
    """
    return compare(kind, a, b) == 1.0


def _identical(kind, values):
    return all(exact(kind, values[0], v) for v in values[1:])


# --------------------------------------------------------------------------
# Ranking. Only a `score` field has these, and the reason is in
# evals/tasks/score.py: there is no ground truth for fit_score, so the
# measurable properties are whether the model reproduces its own NUMBER
# (tolerance) and its own ORDER (correlation, overlap).
# --------------------------------------------------------------------------

def within(a, b, tol):
    """Do two numeric answers agree to within `tol`? None is not a number.

    A None on either side is not agreement at any tolerance -- "the model did
    not give a usable score" and "it gave 50" are different outcomes, and
    treating a shared None as agreement would let a model that tombstones
    everything report perfect stability. Two Nones are counted separately, as
    `undefined`.
    """
    if a is None or b is None:
        return False
    return abs(a - b) <= tol


def _ranks(values):
    """Competition-free average ranks, ties sharing the mean of their ranks.

    Average ranks rather than first-seen order because fit_score is heavily
    tied by construction -- 32 distinct values over 1,294 production rows --
    and breaking ties arbitrarily would manufacture an ordering the model
    never expressed, then measure the correlation of the manufactured part.
    """
    order = sorted(range(len(values)), key=lambda i: values[i])
    ranks = [0.0] * len(values)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and values[order[j + 1]] == values[order[i]]:
            j += 1
        mean_rank = (i + j) / 2.0 + 1.0
        for k in range(i, j + 1):
            ranks[order[k]] = mean_rank
        i = j + 1
    return ranks


def spearman(xs, ys):
    """Spearman rho over the positions where BOTH values are numbers.

    Returns (rho, n). rho is None when fewer than two comparable pairs remain
    or when either side is constant -- a model that answered 50 for every
    posting has no ordering to correlate, and printing 0.0 there would read
    as disagreement rather than as absence.
    """
    pairs = [(x, y) for x, y in zip(xs, ys) if x is not None and y is not None]
    n = len(pairs)
    if n < 2:
        return None, n
    rx = _ranks([p[0] for p in pairs])
    ry = _ranks([p[1] for p in pairs])
    mx, my = sum(rx) / n, sum(ry) / n
    num = sum((a - mx) * (b - my) for a, b in zip(rx, ry))
    denx = math.sqrt(sum((a - mx) ** 2 for a in rx))
    deny = math.sqrt(sum((b - my) ** 2 for b in ry))
    if denx == 0 or deny == 0:
        return None, n
    return num / (denx * deny), n


def top_k_overlap(ids, xs, ys, k=TOP_K):
    """|top-k by xs INTERSECT top-k by ys| / k, over comparable records.

    Ties at the k boundary are broken by job_id so the answer is
    deterministic, and that arbitrariness is exactly why this is reported
    beside rho rather than instead of it: with 59 postings sharing one
    fit_score, which twenty land in the top twenty is partly the sort's
    choice, not the model's.
    """
    rows = [(i, x, y) for i, x, y in zip(ids, xs, ys)
            if x is not None and y is not None]
    if not rows or k <= 0:
        return None, len(rows)
    kk = min(k, len(rows))
    top_x = {r[0] for r in sorted(rows, key=lambda r: (-r[1], str(r[0])))[:kk]}
    top_y = {r[0] for r in sorted(rows, key=lambda r: (-r[2], str(r[0])))[:kk]}
    return len(top_x & top_y) / kk, len(rows)


def tie_histogram(values):
    """The tie structure of one column of answers.

    `p_tie` is the probability that two records drawn at random share a value
    -- one number for "how coarse is this scale", which is what makes a before
    /after comparison across a normalisation rule readable. A rule that clamps
    or rounds can only push it up.

    None is counted in `undefined` and excluded from everything else: a shared
    absence is not a tie, it is two missing answers.
    """
    present = [v for v in values if v is not None]
    counts = {}
    for v in present:
        counts[v] = counts.get(v, 0) + 1
    n = len(present)
    p_tie = (sum(c * (c - 1) for c in counts.values()) / (n * (n - 1))
             if n > 1 else None)
    return {
        "n": n,
        "undefined": len(values) - n,
        "distinct": len(counts),
        "largest": max(counts.values()) if counts else 0,
        "p_tie": p_tie,
        "top": sorted(counts.items(), key=lambda kv: (-kv[1], kv[0])),
    }


# --------------------------------------------------------------------------
# Ranking against a LABEL rather than against another run.
#
# Everything above measures a model against itself, because for fit_score
# there is no ground truth. A constructed corpus with an intended verdict per
# posting is the case where there IS one, and the question changes from "does
# the model reproduce its own ordering" to "does the ordering put the good
# postings first". CLAUDE.md: "Report average precision as the measurement,
# precision@20 as the objective."
#
# NOT sklearn. tools/learned-ranker-probe.py:133 reaches for
# sklearn.metrics.average_precision_score, and sklearn is not in
# requirements.txt (`psycopg[binary]` alone) -- so that probe does not run on
# a clean checkout of this repo. These are stdlib, and they differ from
# sklearn's in the tie handling below, deliberately.
# --------------------------------------------------------------------------

#: How average_precision() and precision_at_k() treat equal scores.
#:
#: TIES ARE NOT AN EDGE CASE HERE, THEY ARE THE COMMON CASE.
#: Trap 4.2 (`git show refactor-freeze-2026-08-02:docs/MEASUREMENT-TRAPS.md`, which
#: keeps the 4.1-4.7 numbering so citations still resolve) records 59 postings
#: sharing one fit_score, and match_score is free arithmetic over a small integer
#: weight table, so it clusters just as hard. A top-k boundary that falls
#: inside a tie block makes half of any top-k an arbitrary draw, and a
#: first-seen tie-break measures the sort's choice rather than the ranker's.
#:
#: `expected` is the default and is the only one of the three that is a
#: property of the RANKER: it is the mean over every tie-break, so permuting
#: the input cannot change the answer. The closed form is McSherry & Najork
#: (2008), "Computing Information Retrieval Performance Measures Efficiently
#: in the Presence of Tied Scores" -- an O(n) sum, not an enumeration.
#:
#: `optimistic` and `pessimistic` are the best and worst tie-breaks, reported
#: together as an interval when the gap matters. They bound what a real sort
#: could have produced; `expected` is what it produces on average.
TIE_MODES = ("expected", "optimistic", "pessimistic")


class Ranked(NamedTuple):
    """A ranking statistic and the rows it could NOT be computed over.

    THE DROP COUNTS ARE NOT DIAGNOSTICS, THEY ARE PART OF THE ANSWER, and
    that is why they are in the return value rather than available from a
    second call. A row with no score leaves the denominator (see
    _score_blocks), and in every caller this module has, "no score" is not
    random: it means the pipeline failed to produce one. In
    tools/mock-acceptance.py a posting scores None exactly when extraction
    tombstoned it or never wrote facts, and a posting whose description
    defeats the extractor is more likely to be one of the deliberately
    awkward ones -- so the rows that vanish are correlated with the thing
    being measured, and EVERY DROP MAKES THE RANKER LOOK BETTER.

    That is trap 4.1 ("do not compute metrics over a floor-filtered sample",
    `git show refactor-freeze-2026-08-02:docs/MEASUREMENT-TRAPS.md`) in a second costume. There
    it was job_matches' MATCH_FLOOR hiding the low end and moving one
    identical ranking function from +0.619 to +0.326; here it is extraction
    failure hiding the hard end and moving it the other way.

    A 5-tuple rather than the (value, n) pair the rest of this module returns,
    deliberately: `ap, n = average_precision(...)` now raises instead of
    quietly discarding the drop counts, so a caller written against the old
    shape has to look at them.

      value                -- the statistic, or None when it is undefined
      n                    -- rows it was computed over
      n_positive           -- positives among those n
      n_dropped            -- rows with no score, excluded
      n_dropped_positive   -- of which were labelled positive. THIS IS THE
                              ONE THAT INFLATES THE NUMBER.
      k                    -- precision_at_k only: the k actually used
    """

    value: object
    n: int
    n_positive: int
    n_dropped: int
    n_dropped_positive: int
    k: object = None

    @property
    def complete(self):
        """Was every row scorable? False means the figure is conditioned."""
        return self.n_dropped == 0

    def coverage(self):
        """"55/120", the shape `git show refactor-freeze-2026-08-02:docs/score-validation.md:270` already uses.

        One string so that no caller has to decide how to render it, and so
        that a report cannot print the statistic having forgotten it.
        """
        return f"{self.n}/{self.n + self.n_dropped}"


def _drops(scores, labels):
    """(n_dropped, n_dropped_positive) for the rows with no score."""
    n = sum(1 for s in scores if s is None)
    pos = sum(1 for s, y in zip(scores, labels) if s is None and y)
    return n, pos


def _score_blocks(scores, labels):
    """(block_size, positives_in_block) descending by score, ties grouped.

    Positions where the score is None are dropped: "the ranker produced no
    number" is not a rank, and giving it one -- last, or 0 -- would score a
    missing answer as a confident bad one. How many were dropped, and how
    many of those were positives, is carried out to the caller in Ranked --
    the drop is defensible, silence about it is not.
    """
    rows = sorted(((s, 1 if y else 0) for s, y in zip(scores, labels)
                   if s is not None),
                  key=lambda r: -r[0])
    blocks = []
    i = 0
    while i < len(rows):
        j = i
        while j + 1 < len(rows) and rows[j + 1][0] == rows[i][0]:
            j += 1
        blocks.append((j - i + 1, sum(r[1] for r in rows[i:j + 1])))
        i = j + 1
    return blocks


def average_precision(scores, labels, *, ties="expected"):
    """Average precision of `scores` against binary `labels`. A Ranked.

    `.value` is None when there are no positives or no comparable rows -- a
    corpus with nothing to find has no precision, and returning 0.0 there
    would read as "the ranker failed" rather than as "the question was not
    asked".

    Never 0.5-for-random: average precision's chance level is the positive
    RATE, so 0.55 on a corpus that is 55% positive is exactly no signal.
    Report the rate beside it, and `.coverage()` beside that, or the number
    is uninterpretable in two independent ways.
    """
    if ties not in TIE_MODES:
        raise ValueError(f"ties must be one of {TIE_MODES}, got {ties!r}")
    blocks = _score_blocks(scores, labels)
    n = sum(size for size, _ in blocks)
    n_pos = sum(r for _, r in blocks)
    dropped, dropped_pos = _drops(scores, labels)
    if not n_pos:
        return Ranked(None, n, n_pos, dropped, dropped_pos)

    total = 0.0
    above, rel_above = 0, 0          # items and positives in earlier blocks
    for size, rel in blocks:
        if rel:
            if ties == "optimistic":
                # Every positive in the block ahead of every negative.
                total += sum((rel_above + m) / (above + m)
                             for m in range(1, rel + 1))
            elif ties == "pessimistic":
                # ... and behind every negative.
                total += sum((rel_above + m) / (above + size - rel + m)
                             for m in range(1, rel + 1))
            else:
                # E[precision at position j | the item there is relevant],
                # times P(it is relevant). The inner term is 1 plus the mean
                # of a hypergeometric draw over the rest of the block.
                for j in range(1, size + 1):
                    ahead = (1.0 if size == 1
                             else 1.0 + (j - 1) * (rel - 1) / (size - 1))
                    total += (rel / size) * (rel_above + ahead) / (above + j)
        above += size
        rel_above += rel
    return Ranked(total / n_pos, n, n_pos, dropped, dropped_pos)


def precision_at_k(scores, labels, k=TOP_K):
    """Precision over the top k. A Ranked, with `.k` the k actually used.

    `.k` is min(k, comparable rows), following top_k_overlap above: a corpus
    of 12 has no top 20, and dividing by 20 anyway reports a ceiling of 0.6
    that no ranker could beat. k <= 0 gives `.value` None rather than raising
    -- an empty shortlist is a real configuration (`pursuit`'s
    daily_narrative_budget is 0) and the table still has to print.

    UNSCORABLE ROWS ARE DROPPED BEFORE k IS RESOLVED, which is the same
    inflation Ranked describes and is worse here than for average precision:
    dropping rows does not only remove them from the denominator, it PROMOTES
    whatever was behind them into the top k. `.n_dropped_positive` is the
    number that says how much of the top k was vacated rather than earned.

    Ties are averaged rather than broken, for the reason in TIE_MODES: when
    the boundary falls inside a block of equal scores, the block contributes
    its positive rate times the slots it fills, which is the expectation over
    every tie-break. That makes a fractional numerator possible and 0.75 over
    2 slots a correct answer, not a rounding error.
    """
    blocks = _score_blocks(scores, labels)
    n = sum(size for size, _ in blocks)
    n_pos = sum(r for _, r in blocks)
    dropped, dropped_pos = _drops(scores, labels)
    kk = min(k, n)
    if kk <= 0:
        return Ranked(None, n, n_pos, dropped, dropped_pos, k=0)

    hits, slots = 0.0, kk
    for size, rel in blocks:
        if slots <= 0:
            break
        take = min(size, slots)
        hits += rel * take / size
        slots -= take
    return Ranked(hits / kk, n, n_pos, dropped, dropped_pos, k=kk)


# --------------------------------------------------------------------------
# Comparing TWO orderings against the same labels.
#
# average_precision and precision_at_k above answer "how good is this
# ordering". The question task 30 actually has to answer is "is this ordering
# better than the one it replaces"
# (`git show refactor-freeze-2026-08-02:docs/tasks/refactor/tranche_six/30-within-track-ordering.md:98` -- "a paired
# bootstrap against the pre-refactor baseline"), and two of the numbers above,
# each with its own interval, cannot answer it: see bootstrap_delta.
#
# LIFTED FROM tools/learned-ranker-probe.py:410, NOT SHARED WITH IT.
# That copy resamples numpy arrays and is called with sklearn metrics on
# out-of-fold predictions fitted against job_scores.fit_score -- CLAUDE.md's
# L1 layer, which "never evaluate on the layer you trained on" puts off limits
# for the comparison task 30 needs. Neither numpy nor sklearn is in
# requirements.txt (`psycopg[binary]` alone), so that probe does not run on a
# clean checkout at all; this is stdlib, like everything else in this module.
# --------------------------------------------------------------------------

#: Resamples for bootstrap_delta. Identical to
#: tools/learned-ranker-probe.py:163's BOOTSTRAP_DRAWS, so an interval from
#: here is the same WIDTH of evidence as the ones that probe has printed and a
#: change in an interval cannot be a change in the draw count. 2000 puts ~50
#: draws in each tail past the 2.5th and 97.5th percentiles; a few hundred
#: gives an interval whose ENDPOINTS move by more than the differences being
#: decided on, which is a resampling artefact reported as a result.
BOOTSTRAP_DRAWS = 2000

#: Coverage of the reported interval. Travels in the return value rather than
#: living only here, because "[+0.01, +0.09]" means different things at 95% and
#: at 50% and a report that prints the numbers without the level is unreadable.
CI_LEVEL = 0.95

#: Fraction of `draws` that must yield a defined statistic before
#: bootstrap_delta will report an interval at all. Below it, `value` is None.
#:
#: The surviving draws are conditioned on the resample containing a positive,
#: so past some point the percentiles describe a minority subset selected by
#: something correlated with the statistic, and `value` should be nothing
#: rather than that.
#:
#: A BACKSTOP, NOT A ROUTINE GATE, and the arithmetic says which. For average
#: precision the only degenerate draw is one with no positives, and its
#: probability is ((n - p) / n)^n, maximised at p = 1 and bounded above by
#: 1/e = 0.368 for every n (0.296 at n=3, 0.352 at n=12, 0.366 at n=100). A
#: corpus with at least one positive therefore cannot reach this floor, and a
#: reader who sees it fire is looking at a caller-supplied metric with
#: undefined cases of its own, not at a sparse corpus.
#:
#: That is the reason 0.5 and not something tighter. 0.9 and 0.7 were both
#: rejected: at either, the per-`role_track` cells this exists for report
#: nothing at all -- one positive in twelve rows makes 35% of draws degenerate,
#: which is INHERENT to bootstrapping a cell that size and not a fault of the
#: corpus -- and a blank cell hides the smallness it was meant to flag. `n` and
#: `draws_used` are what say how thin the evidence is; they travel in the
#: return value and a report should print them.
MIN_USABLE_FRACTION = 0.5

#: Default RNG seed, so the same inputs give the same interval on every
#: machine and a figure quoted in a doc can be reproduced.
#:
#: tools/learned-ranker-probe.py DID seed (its `seed=SEED`, SEED = 11 at
#: line 147) -- this is not a fix, it is the same discipline with the seed
#: moved out of a probe-wide constant that also drives that tool's CV splits
#: and its shuffles, where changing the bootstrap means changing the splits.
#:
#: 11 is that probe's number, kept so the two tools are seeded alike. It does
#: NOT make the two reproduce each other's endpoints: random.Random and
#: numpy.random.default_rng draw different index lists from the same seed, so
#: an interval from here and one from the probe agree only to resampling
#: error. Nothing should be built on comparing their digits.
BOOTSTRAP_SEED = 11


class Delta(NamedTuple):
    """A difference between two rankings, and the interval it sits inside.

    THE POINT ESTIMATE IS NEVER THE ANSWER ON ITS OWN, which is why it cannot
    be got out of here without the interval beside it. This module already
    refuses to hand back a bare number twice -- Ranked carries its drop counts
    (see its docstring) and spearman/top_k_overlap carry their n -- and a
    delta is the case where a bare number is most misleading: "+0.04 average
    precision" reads as a win and is routinely one draw of noise on a corpus
    of a few hundred labels.

    Three things enforce that here:

      * A 10-tuple, so `delta, lo, hi = bootstrap_delta(...)` -- the shape
        tools/learned-ranker-probe.py:428-430 returns -- raises ValueError
        instead of quietly working. Same device as Ranked's 5-tuple.
      * __str__ renders "+0.041 [-0.003, +0.085]", so the natural
        f"{d}" carries the interval. Only `.value` prints bare, and a reader
        who typed `.value` has decided to.
      * verdict() is the sign test, so no call site has to re-derive
        "does the interval exclude zero" -- lifted from the probe's own
        `call` at tools/learned-ranker-probe.py:585-586, which is the one
        piece of that print block worth keeping.

      value                -- observed metric(a) - metric(b) on the full
                              paired sample, or None where undefined
      lo, hi               -- percentile interval on the resampled deltas
      level                -- coverage of (lo, hi), e.g. 0.95
      n                    -- rows resampled (paired and scorable on BOTH)
      n_dropped            -- rows excluded because one side had no score
      n_dropped_positive   -- of which were labelled positive. Ranked's
                              caps-lock warning applies unchanged: a drop
                              flatters whichever ranking lost the row.
      draws                -- resamples actually performed
      n_undefined          -- draws whose statistic did not exist (a resample
                              can contain no positives). NOT folded to zero;
                              see bootstrap_delta.
      seed                 -- the seed that produced this interval

    `draws_used` -- draws - n_undefined -- is the number the interval actually
    rests on and is a property rather than an eleventh field, so it cannot
    disagree with the two counts it is derived from.
    """

    value: object
    lo: object
    hi: object
    level: float
    n: int
    n_dropped: int
    n_dropped_positive: int
    draws: int
    n_undefined: int
    seed: object

    def verdict(self):
        """"better", "worse", "not distinguishable", or "undefined".

        tools/learned-ranker-probe.py:585-586's rule: the interval has to
        exclude zero, not merely have the right sign. "not distinguishable"
        rather than "no difference" deliberately -- an interval spanning zero
        on 300 labels is a statement about the corpus, not about the rankers.
        """
        if self.value is None or self.lo is None:
            return "undefined"
        if self.lo > 0:
            return "better"
        if self.hi < 0:
            return "worse"
        return "not distinguishable"

    @property
    def complete(self):
        """Was every row scorable on both sides? Follows Ranked.complete."""
        return self.n_dropped == 0

    @property
    def draws_used(self):
        """Draws the interval actually rests on: draws - n_undefined.

        Print it beside the interval whenever it is below `draws`. A 95%
        interval from 140 usable draws of 2000 is not the same evidence as one
        from 2000, and the two render identically without this number.
        """
        return self.draws - self.n_undefined

    def interval(self):
        """"+0.041 [-0.003, +0.085]", the shape the probe already prints.

        One string so that no caller has to decide how to render it, and so
        that a report cannot print the delta having forgotten the interval --
        Ranked.coverage()'s argument, applied to the other half of the answer.

        The undefined cases render as text rather than as a formatted None, and
        the too-few-usable-draws case names itself: a blank cell that could
        equally mean "no labels here" or "no positives here" or "this corpus is
        too sparse to resample" sends a reader to the code.
        """
        if self.value is None:
            if self.draws:
                return (f"undefined ({self.draws_used}/{self.draws} draws "
                        f"usable)")
            return "undefined"
        return f"{self.value:+.3f} [{self.lo:+.3f}, {self.hi:+.3f}]"

    def __str__(self):
        return self.interval()


def _percentile(values, q):
    """numpy.percentile's default linear interpolation, in stdlib.

    Written out rather than approximated by indexing at int(q * n), which is
    the obvious stdlib shortcut and is off by up to one draw. At 2000 draws
    that is invisible; at the few hundred a test or a small corpus uses it
    moves the endpoint by a visible amount, and the endpoint is the thing being
    read. Matching numpy's default also means an interval from here and one
    from tools/learned-ranker-probe.py:429-430 are at least the same
    definition, even though their RNGs differ.

    `values` must be sorted ascending.
    """
    if not values:
        return None
    if len(values) == 1:
        return values[0]
    pos = (len(values) - 1) * q
    lo = math.floor(pos)
    hi = math.ceil(pos)
    if lo == hi:
        return values[lo]
    return values[lo] + (values[hi] - values[lo]) * (pos - lo)


def _stat(metric, scores, labels):
    """One metric value, accepting a Ranked, a (value, n) pair or a float.

    Everything in this module returns a tuple whose first field is the
    statistic, so `metric=average_precision` works with no adapter at the call
    site and `metric=lambda s, y: precision_at_k(s, y, k=20)` works for the
    objective. None propagates: an undefined statistic is not a zero.
    """
    out = metric(scores, labels)
    if isinstance(out, tuple):
        return out[0]
    return out


def _delta(metric, a, b, labels):
    """metric(a) - metric(b) on the SAME rows. None if either is undefined."""
    va = _stat(metric, a, labels)
    vb = _stat(metric, b, labels)
    if va is None or vb is None:
        return None
    return va - vb


def bootstrap_delta(scores_a, scores_b, labels, metric=None, *,
                    draws=BOOTSTRAP_DRAWS, level=CI_LEVEL,
                    seed=BOOTSTRAP_SEED):
    """Interval for metric(scores_a) - metric(scores_b). A Delta.

    PAIRED: ONE RESAMPLE, SCORED TWICE.
    Each draw picks n row indices with replacement and evaluates BOTH
    rankings on that same index list, so every resample compares the two
    orderings on the same postings. This is the whole content of the function
    and it is not an optimisation. Resampling the two sides independently
    estimates the variance of each statistic separately, and two intervals
    that happen to overlap say far less than one interval on the difference --
    the overlap heuristic is how a real gain gets talked out of existence, and
    also how a difference that is entirely shared-corpus luck gets called a
    win. tools/learned-ranker-probe.py:411-421 makes the same argument.

    On this data the pairing does most of the work. The corpus is task 29's
    `pursuit-v1` label set -- n=200 drawn, >=100 labelled by its definition of
    done (`git show refactor-freeze-2026-08-02:docs/tasks/refactor/tranche_five/29-labelling-session.md:51`, :163) --
    and at that size the sampling variance of average precision is far larger
    than the differences task 30 is deciding between. Worse, the two orderings
    it compares differ only in bucketing and within-bucket sort, not in the
    underlying match_score, so they agree on most rows. That agreement cancels
    in the difference and survives in two separate variances, which is to say
    the unpaired version is at its most misleading exactly here.

    `value` IS THE OBSERVED DELTA, NOT THE MEAN OF THE RESAMPLES.
    The probe returns np.mean(deltas) as its point estimate
    (learned-ranker-probe.py:428). That is the bootstrap's estimate of the
    mean, which differs from the statistic on the actual sample by the
    bootstrap bias, and it means the headline number is one no reader can
    recompute from the corpus. Here the point estimate is what the metric says
    on the full paired sample; the resamples only ever set (lo, hi).

    ONLY THE DIFFERENCE IS TRUSTWORTHY, which the probe's own docstring says
    and which is worth carrying over: resampling with replacement lets one
    posting occupy several slots of a top k, so the absolute level of a
    resampled statistic drifts from the level on the real corpus. It drifts the
    same way on both sides of a paired draw. Read `value`, `lo` and `hi`; do
    not reconstruct either ranking's average precision from them.

    A DEGENERATE RESAMPLE IS SKIPPED AND COUNTED. IT IS NEVER SCORED 0.0.
    This is the substantive reason the function is worth moving rather than
    copying. A resample drawn with replacement can contain no positives at all,
    where average precision does not exist and average_precision() returns
    None. The probe's metric substitutes 0.0 instead --
    `average_precision_score(yy, s) if 0 < yy.sum() < len(yy) else 0.0`
    (learned-ranker-probe.py:438) -- and REJECTING that substitution is the
    change. Both sides of a degenerate draw get 0.0, so the delta for it is
    exactly 0.0, and every such draw is one more exact zero in the middle of
    the distribution the percentiles are read off: the interval widens toward
    zero at the near end, which manufactures "not distinguishable" out of an
    arithmetic guard. At n in the hundreds this is rare. At the per-
    `role_track` n of about a dozen that task 30 needs it is routine -- one
    positive in twelve rows makes (11/12)^12 = 35% of draws degenerate -- and
    it changes the answer. On twelve rows with one positive, a perfect ordering
    against its own reverse is +0.917 [+0.823, +0.917] here and
    +0.917 [+0.000, +0.917] with the substitution: "better" against "not
    distinguishable", on identical data (measured 2026-07-30, 400 draws, seed
    11; pinned in tests/test_metrics_ranking.py). The guard would be silently
    deciding the very comparison it was written to protect.

    Note precisely which half of that guard does the damage, because the two
    halves fail differently. `yy.sum() == 0` is genuinely undefined and 0.0 is
    an invented value: this is the biasing case. `yy.sum() == len(yy)` is NOT
    undefined -- every ordering of an all-positive set has average precision
    1.0, and this module returns that -- so there the substitution is a wrong
    metric value whose error cancels in the difference (1.0 - 1.0 and 0.0 - 0.0
    are both 0.0). The guard is wrong twice and biasing once.

    Skipped draws are counted in `n_undefined`, and `draws_used` is what the
    interval rests on. When `draws_used` falls below MIN_USABLE_FRACTION of
    `draws`, `value` is None and no interval is reported: past that point the
    surviving draws are a minority subset selected by something correlated with
    the statistic, which is trap 4.1
    (`git show refactor-freeze-2026-08-02:docs/MEASUREMENT-TRAPS.md`) -- a quality figure computed over
    a sample a filter chose rather than the question -- in a third costume. For
    average precision that floor is unreachable on a corpus with a positive in
    it; see MIN_USABLE_FRACTION for the 1/e bound and for why a tighter floor
    was rejected.

    DETERMINISTIC BY DEFAULT. random.Random(seed) with seed=BOOTSTRAP_SEED, so
    a quoted interval is reproducible from the inputs alone, and `seed` comes
    back in the Delta so a report can print it. Pass a different seed to check
    that a conclusion is not an artefact of this one -- the endpoints will
    move a little; a verdict that moves with the seed was never there.

    ROWS UNSCORABLE ON EITHER SIDE ARE DROPPED BEFORE RESAMPLING, and the
    count comes back in the Delta. Keeping a row where only one side has a
    number would score the two rankings over different sets and break exactly
    the pairing this exists for; Ranked's warning about which direction a drop
    moves the number applies to both sides at once.

    Returns `value` None (and lo/hi None) rather than raising when there is
    nothing to compare: no rows, no positives on the sample itself, or too few
    usable draws. That is average_precision's convention -- an absent question
    is not a zero result -- and it is what lets a per-track table print a row
    for a track with two labels in it. The three are distinguishable without
    reading the code: `n` is 0 for the first, `draws` is 0 for the second, and
    `draws_used` is below `draws` for the third.

    A length mismatch or an unusable `draws`/`level` DOES raise: those are
    caller bugs, not outcomes of the data, and the precedent is
    average_precision's ValueError on an unknown tie mode.

    Default metric is average_precision, because CLAUDE.md makes average
    precision the measurement and precision@20 only the objective. For the
    objective, pass `lambda s, y: precision_at_k(s, y, k=20)`.

    tools/learned-ranker-probe.py KEEPS ITS OWN COPY. Repointing it is
    deliberate follow-up work and is not free: it is called with numpy arrays
    and sklearn metrics under a fancy-indexing contract this signature does
    not offer, so the change is a rewrite of its call sites rather than an
    import, and it belongs in a commit that can be reviewed as such.
    """
    if not (len(scores_a) == len(scores_b) == len(labels)):
        raise ValueError(
            f"scores_a, scores_b and labels must be the same length, got "
            f"{len(scores_a)}, {len(scores_b)}, {len(labels)}")
    if not 0.0 < level < 1.0:
        raise ValueError(f"level must be in (0, 1), got {level!r}")
    if draws < 1:
        raise ValueError(f"draws must be at least 1, got {draws!r}")
    if metric is None:
        metric = average_precision

    rows = [(a, b, 1 if y else 0)
            for a, b, y in zip(scores_a, scores_b, labels)
            if a is not None and b is not None]
    dropped_labels = [y for a, b, y in zip(scores_a, scores_b, labels)
                      if a is None or b is None]
    dropped = len(dropped_labels)
    dropped_pos = sum(1 for y in dropped_labels if y)
    n = len(rows)

    col_a = [r[0] for r in rows]
    col_b = [r[1] for r in rows]
    col_y = [r[2] for r in rows]

    observed = _delta(metric, col_a, col_b, col_y) if n else None
    if observed is None:
        # No rows, or the metric is undefined on the sample itself (an
        # all-negative corpus). Resampling a corpus with nothing to find
        # would produce an interval around a number that does not exist.
        return Delta(None, None, None, level, n, dropped, dropped_pos,
                     0, 0, seed)

    rng = random.Random(seed)
    deltas = []
    undefined = 0
    for _ in range(draws):
        idx = [rng.randrange(n) for _ in range(n)]     # ONE list, used twice
        d = _delta(metric, [col_a[i] for i in idx], [col_b[i] for i in idx],
                   [col_y[i] for i in idx])
        if d is None:
            undefined += 1
        else:
            deltas.append(d)

    if len(deltas) < MIN_USABLE_FRACTION * draws:
        # Too many degenerate resamples for the percentiles to describe
        # anything but the subset that happened to contain a positive. The
        # counts still come back, because "this cell is too sparse to
        # bootstrap" is a finding about the corpus.
        return Delta(None, None, None, level, n, dropped, dropped_pos,
                     draws, undefined, seed)

    deltas.sort()
    tail = (1.0 - level) / 2.0
    return Delta(observed, _percentile(deltas, tail),
                 _percentile(deltas, 1.0 - tail),
                 level, n, dropped, dropped_pos, draws, undefined, seed)


def ranking(per_record_values, ids, *, tolerances=SCORE_TOLERANCES, k=TOP_K):
    """Run-to-run stability of an ORDERING, from per-record repeat tuples.

    `per_record_values` is one tuple of repeat values per record, the same
    shape field_cell() takes; `ids` are the job_ids in the same order.

    Every pair of repeats contributes one rho and one overlap, and the mean
    and the worst are both reported. The worst is the one that matters: a
    model whose passes correlate 0.95, 0.94 and 0.61 is not a 0.83 model, it
    is a model with an unstable pass, and a mean hides that.
    """
    n_repeat = len(per_record_values[0]) if per_record_values else 0
    columns = [[vals[r] for vals in per_record_values] for r in range(n_repeat)]

    rhos, overlaps = [], []
    for i in range(n_repeat):
        for j in range(i + 1, n_repeat):
            rho, _ = spearman(columns[i], columns[j])
            if rho is not None:
                rhos.append(rho)
            ov, _ = top_k_overlap(ids, columns[i], columns[j], k=k)
            if ov is not None:
                overlaps.append(ov)

    bands = {}
    for tol in tolerances:
        kk = sum(1 for vals in per_record_values
                 if len(vals) >= 2 and within(vals[0], vals[1], tol))
        n = len(per_record_values)
        bands[tol] = {"k": kk, "n": n, "rate": (kk / n) if n else None,
                      "ci": wilson(kk, n)}

    diffs = [abs(a - b) for vals in per_record_values
             for a, b in _pairs(vals) if a is not None and b is not None]
    return {
        "k": k,
        "n_repeat": n_repeat,
        "spearman_mean": (sum(rhos) / len(rhos)) if rhos else None,
        "spearman_min": min(rhos) if rhos else None,
        "spearman_pairs": len(rhos),
        f"top{k}_overlap_mean": (sum(overlaps) / len(overlaps))
                                if overlaps else None,
        f"top{k}_overlap_min": min(overlaps) if overlaps else None,
        "mean_abs_diff": (sum(diffs) / len(diffs)) if diffs else None,
        "max_abs_diff": max(diffs) if diffs else None,
        "bands": bands,
        "ties": [tie_histogram(col) for col in columns],
    }


def _pairs(values):
    for i in range(len(values)):
        for j in range(i + 1, len(values)):
            yield values[i], values[j]


def _flips(kind, per_record_values):
    """Which value pairs a field actually flips between, most common first.

    A rate says how often the model disagrees with itself; this says what
    the disagreement IS, and for `ai_involvement` those are different
    findings with different consequences. `uses_ai_tools` flipping to
    `builds_llm_features` is two adjacent readings of the same posting and
    the cohort's targeting survives it. Either of them flipping to `none` is
    a job leaving the opportunity space between one night and the next.

    Only for kinds whose values are small and hashable. `set` is excluded:
    the interesting quantity there is Jaccard, and listing every distinct
    tech_stack pair would be a wall of noise.
    """
    if kind not in ("enum", "bool", "int"):
        return []
    counts = {}
    for values in per_record_values:
        distinct = sorted({str(v) for v in values})
        if len(distinct) < 2:
            continue
        key = " <-> ".join(distinct)
        counts[key] = counts.get(key, 0) + 1
    return sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))


def field_cell(kind, per_record_values):
    """Aggregate one field over a list of per-record repeat-value tuples."""
    n = len(per_record_values)
    agree2_k = 0
    unan_k = 0
    pair_sum = 0.0
    jac_sum = 0.0
    for values in per_record_values:
        if len(values) >= 2 and exact(kind, values[0], values[1]):
            agree2_k += 1
        if _identical(kind, values):
            unan_k += 1
        scores = [1.0 if exact(kind, a, b) else 0.0 for a, b in _pairs(values)]
        if scores:
            pair_sum += sum(scores) / len(scores)
        if kind == "set":
            js = [jaccard(a, b) for a, b in _pairs(values)]
            if js:
                jac_sum += sum(js) / len(js)
    cell = {
        "kind": kind,
        "n": n,
        "flips": _flips(kind, per_record_values),
        "agree2_k": agree2_k,
        "agree2": (agree2_k / n) if n else None,
        "agree2_ci": wilson(agree2_k, n),
        "unan_k": unan_k,
        "unanimous": (unan_k / n) if n else None,
        "unanimous_ci": wilson(unan_k, n),
        "pairwise": (pair_sum / n) if n else None,
        "jaccard": (jac_sum / n) if (n and kind == "set") else None,
    }
    return cell


def selfcheck(runs, records, field_kinds, *, skip_kinds=("prose",)):
    """Per-field and per-platform self-consistency across N repeat runs.

    `runs` is a list of runner.Run over the SAME records in the same order.
    `records` supplies the platform for each position.
    """
    if len(runs) < 2:
        raise ValueError("self-consistency needs at least 2 repeats")
    lengths = {len(r.results) for r in runs}
    if len(lengths) != 1 or lengths.pop() != len(records):
        raise ValueError("every repeat must cover the same records")

    from . import runner as runner_mod

    platforms = {}
    comparable = []          # indices usable in every repeat
    not_ok = []              # (job_id, [status per repeat])
    for i, rec in enumerate(records):
        statuses = [run.results[i].status for run in runs]
        if all(s == runner_mod.OK for s in statuses):
            comparable.append(i)
        elif any(s != runner_mod.SKIPPED for s in statuses):
            # All-SKIPPED is the pipeline declining to send the record at
            # all -- not a model failure, and extract.py would not have
            # asked either. Anything else is instability worth naming.
            not_ok.append((runs[0].results[i].job_id, statuses))
        platforms[i] = rec.get("platform") or "unknown"

    fields = {}
    for field, kind in sorted(field_kinds.items()):
        if kind in skip_kinds:
            continue
        by_platform_values = {}
        overall_values = []
        for i in comparable:
            values = tuple((run.results[i].normalized or {}).get(field)
                           for run in runs)
            overall_values.append(values)
            by_platform_values.setdefault(platforms[i], []).append(values)
        fields[field] = {
            "overall": field_cell(kind, overall_values),
            "by_platform": {p: field_cell(kind, v)
                            for p, v in sorted(by_platform_values.items())},
            "clean": field_cell(kind, [
                v for i, v in zip(comparable, overall_values)
                if platforms[i] in CLEAN_PLATFORMS]),
            "messy": field_cell(kind, [
                v for i, v in zip(comparable, overall_values)
                if platforms[i] not in CLEAN_PLATFORMS]),
        }

    # Ranking, for any field whose kind is `score`. Detected from the kinds
    # rather than passed in, so a task that declares one gets the block with
    # no change at the call site (evals/__main__.py:218) and a task that does
    # not is unaffected.
    rank_blocks = {}
    for field, kind in sorted(field_kinds.items()):
        if kind != "score":
            continue
        per_record = [tuple((run.results[i].normalized or {}).get(field)
                            for run in runs) for i in comparable]
        ids = [runs[0].results[i].job_id for i in comparable]
        rank_blocks[field] = ranking(per_record, ids)

    # Whole-record identity over the compared fields only: `summary` is prose
    # and is never compared, so including it would make this 0 by
    # construction and say nothing.
    scored = [(f, k) for f, k in sorted(field_kinds.items())
              if k not in skip_kinds]
    whole_k = 0
    for i in comparable:
        norms = [run.results[i].normalized or {} for run in runs]
        if all(_identical(k, tuple(nz.get(f) for nz in norms))
               for f, k in scored):
            whole_k += 1

    return {
        "repeat": len(runs),
        "n_records": len(records),
        "n_comparable": len(comparable),
        "not_ok": not_ok,
        "platform_counts": {p: sum(1 for i in comparable
                                   if platforms[i] == p)
                            for p in sorted(set(platforms.values()))},
        "fields": fields,
        "ranking": rank_blocks,
        "whole_record": {"k": whole_k, "n": len(comparable),
                         "rate": (whole_k / len(comparable))
                                 if comparable else None},
    }

#!/usr/bin/env python3
"""
Is the free rules ranking good enough to gate the paid narrative tier?

THE QUESTION, PRECISELY
    match.py decides which ~20 postings a profile sees. It replaced an LLM
    that used to score every posting. So the thing that has to be true is not
    "the rules agree with the LLM about every job" -- it is "the rules put the
    same jobs at the TOP". A rules score that is 15 points low on a job nobody
    will ever scroll to costs nothing; one that drops a genuine 85 out of the
    top 150 costs a user their best lead.

    Hence:

      spearman  rank correlation over every job scored both ways. A broad
                sanity check that the two orderings are related at all.
      recall    of the postings the LLM scored >= 80, how many stay inside the
                rules' top 150. Defined by score rather than rank because
                fit_score is heavily tied -- see recall_at().

COMPARE AGAINST THE BASELINE, NOT AGAINST THE LLM
    Both thresholds below were set during design, before any measurement, and
    the recall one turned out to be aspirational rather than informative.

    The LLM never ranked anything. It scored postings in arrival order and
    nothing sorted the results, because there is no surfacing layer. So the
    status quo this replaces is RECENCY, and that is what the final block of
    output compares against. Measured on this corpus: the rules put 8 of 20
    good postings in front of a user, newest-first put 5, and a random draw
    puts 3.1.

    GET THE DIRECTION OF THE BASELINE RIGHT. This block sorted first_seen
    ASCENDING until 2026-07-26, so the row labelled "recency" was the 20
    OLDEST postings and scored 1/20. That made the rules look 8x better than
    the status quo when the honest figure is 8 vs 5. The random row had the
    same shape of error -- a single seed that happened to draw 5/20 against a
    500-seed mean of 3.1 -- which made recency look worse than random, a
    conclusion that was entirely an artifact of the reversed sort. Both are
    fixed; a baseline is only useful if it is the thing you actually replaced.

    A quality bar invented before the baseline is measured tells you nothing
    about whether to ship. Read the baseline block, not just the PASS/FAIL.

THE LABELS ARE FREE
    jobs.job_scores already holds real LLM judgements for profile `tech`,
    produced by the pipeline this replaces. They cost real money once and are
    sitting there. Using them as ground truth means calibration needs no new
    API calls at all -- this script is READ-ONLY and makes zero LLM requests.

WHAT IT IS NOT
    The LLM is not right, it is just the incumbent. A disagreement is a
    prompt to look at the posting, which is why --disagreements prints the
    reasons alongside. Tuning the weights until Spearman hits 1.0 would be
    fitting to the thing being replaced, including its mistakes.

USAGE
    python3 tools/calibrate-match.py
    python3 tools/calibrate-match.py --profile tech --good 80 --within 150
    python3 tools/calibrate-match.py --disagreements 15
"""

import argparse
import json
import random
import os
import statistics
import sys

_d = os.path.dirname(os.path.abspath(__file__))
while _d != os.path.dirname(_d) and not os.path.isdir(os.path.join(_d, "pipelib")):
    _d = os.path.dirname(_d)
sys.path.insert(0, _d)
sys.path.insert(0, os.path.join(_d, "jobs"))

import llm         # noqa: E402
import match       # noqa: E402
import profiles    # noqa: E402
import schema      # noqa: E402
from pipelib import dbconn  # noqa: E402

#: Ship thresholds from the design. Below these the rules tier is not ranking
#: well enough to be trusted to choose what the narrative tier spends on.
MIN_SPEARMAN = 0.6
MIN_RECALL = 0.8

#: How many draws the random baseline averages over. One draw is not a
#: baseline -- see the note in the baseline block at the bottom of main().
RANDOM_DRAWS = 500


def load_pairs(conn, profile_obj):
    """Every LLM-scored posting that has facts, scored by the rules in-process.

    NOT a join against job_matches, and this is the whole correctness of the
    measurement. job_matches only holds rows at or above MATCH_FLOOR, so
    joining it silently restricts the sample to postings the rules already
    liked -- and the low end is exactly where rules and LLM agree most (both
    say "bad"). Removing it drags the correlation down for a reason that has
    nothing to do with ranking quality.

    Measured on this corpus: the joined version reported Spearman +0.326 at
    floor 40 and +0.619 at floor 0, for one identical ranking function. The
    floor is a storage policy; this script measures the ranking.
    """
    rows = conn.execute(
        f"""
        SELECT s.job_id, s.fit_score, j.title, j.company_name, j.first_seen
        FROM {schema.SCORES_TABLE} s
        JOIN {schema.TABLE} j ON j.id = s.job_id
        WHERE s.profile = %s
          AND s.fit_score IS NOT NULL
          AND s.scoring_model NOT LIKE %s
        """,
        (profile_obj.profile, f"{llm.FAILED_PREFIX}%"),
    ).fetchall()
    labelled = {r[0]: (r[1], r[2], r[3], r[4]) for r in rows}

    pairs = []
    for f in match.load_facts(conn):
        if f["job_id"] not in labelled:
            continue
        fit, title, company, first_seen = labelled[f["job_id"]]
        score, reasons = match.score_job(f, profile_obj.criteria)
        pairs.append({"job_id": f["job_id"], "fit": fit, "match": score,
                      "reasons": reasons, "title": title, "company": company,
                      "first_seen": first_seen})

    # Sorted, because Postgres does not promise row order without an ORDER BY
    # and three things below depend on it: which of a block of tied
    # match_scores lands inside top-`within`, which postings the random
    # baseline draws, and the order ties break in. Two runs against an
    # unchanged database reported recall 0.440 and 0.433, and a random
    # baseline of 3.1 and 2.9, with nothing whatsoever having changed. Small
    # enough to shrug at, which is the problem -- it is indistinguishable from
    # a small real effect, and this file exists to measure small real effects.
    pairs.sort(key=lambda p: p["job_id"])
    return pairs


def count_dropped(pairs):
    """Of the scored sample, how many fall below MATCH_FLOOR and so would
    never be stored -- and the best fit_score among them.

    Reported rather than filtered. The floor is a storage decision; a posting
    the LLM scored 80 that the rules put under it is a weighting bug worth
    seeing, not a row to hide.
    """
    below = [p for p in pairs if p["match"] < schema.MATCH_FLOOR]
    return len(below), max((p["fit"] for p in below), default=0)


def recall_at(pairs, threshold, within):
    """Of the postings the LLM scored >= `threshold`, how many does the rules
    ranking keep inside its top `within`? The gating metric.

    DEFINED BY SCORE, NOT BY RANK, AND THAT MATTERS
        The obvious version -- "of the LLM's top 50" -- is not well defined on
        this data. fit_score is heavily tied: 59 postings share the value 85
        and the top-50 boundary falls inside that block, so 24 of any "top 50"
        are an arbitrary draw from the tie. Recall computed that way partly
        measures tie-breaking noise, and moves when nothing about the ranking
        has changed.

        A threshold has no such boundary problem: "everything the LLM called
        80 or better" is the same set every time, which is also the set a user
        would actually care about not losing.

    Returns None when the window is not meaningfully smaller than the sample
    -- if everything fits inside `within`, the metric reports 1.000 while
    measuring nothing.
    """
    if within >= len(pairs):
        return None, 0, 0
    wanted = [p for p in pairs if p["fit"] >= threshold]
    if len(wanted) < 20:
        return None, 0, 0
    by_rules = sorted(pairs, key=lambda p: -p["match"])[:within]
    keep = {p["job_id"] for p in by_rules}
    hits = sum(1 for p in wanted if p["job_id"] in keep)
    return hits / len(wanted), hits, len(wanted)


def main():
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--profile", default=None,
                    help="default: the only profile with scores, or 'tech'")
    ap.add_argument("--good", type=int, default=80,
                    help="fit_score at or above which a posting counts as one "
                         "the rules must not lose (default 80)")
    ap.add_argument("--within", type=int, default=150)
    ap.add_argument("--disagreements", type=int, default=10,
                    help="how many worst disagreements to print (0 to skip)")
    args = ap.parse_args()

    conn = dbconn.connect_or_exit("calibrate-match", schema=schema.SCHEMA)
    profile = args.profile or schema.DEFAULT_PROFILE
    if not args.profile:
        row = conn.execute(
            f"SELECT profile, count(*) FROM {schema.SCORES_TABLE} "
            f"GROUP BY profile ORDER BY 2 DESC LIMIT 1").fetchone()
        if row:
            profile = row[0]

    profile_obj = profiles.load_one(conn, profile)
    if not profile_obj:
        print(f"calibrate-match FAILED: no profile named {profile!r}")
        sys.exit(1)
    pairs = load_pairs(conn, profile_obj)
    dropped, dropped_max = count_dropped(pairs)
    conn.close()

    print(f"calibrate-match: profile={profile}")
    if len(pairs) < 20:
        print(f"  only {len(pairs)} jobs scored by both -- not enough to "
              f"calibrate. Run jobs/extract.py and jobs/match.py first.")
        sys.exit(1)

    fits = [p["fit"] for p in pairs]
    matches = [p["match"] for p in pairs]
    rho = statistics.correlation(fits, matches, method="ranked")

    print(f"  jobs scored by both     {len(pairs)}")
    print(f"  below floor ({schema.MATCH_FLOOR}), not stored  {dropped}"
          + (f"  (highest was fit_score {dropped_max})" if dropped else ""))
    print(f"  fit_score   mean {statistics.mean(fits):5.1f}  "
          f"stdev {statistics.stdev(fits):5.1f}")
    print(f"  match_score mean {statistics.mean(matches):5.1f}  "
          f"stdev {statistics.stdev(matches):5.1f}")
    print()
    print(f"  spearman                {rho:+.3f}   "
          f"(need >= {MIN_SPEARMAN})  {'PASS' if rho >= MIN_SPEARMAN else 'FAIL'}")

    recall, hits, of = recall_at(pairs, args.good, args.within)
    if recall is None:
        print(f"  recall                  n/a -- too few postings at "
              f"fit_score >= {args.good}, or window >= sample")
    else:
        print(f"  recall fit>={args.good} in top{args.within}  "
              f"{recall:.3f}   (need >= {MIN_RECALL})  "
              f"{'PASS' if recall >= MIN_RECALL else 'FAIL'}  [{hits}/{of}]")

    if args.disagreements:
        # Rank difference, not score difference: the scales are not
        # commensurate (the LLM uses the whole 0-100 range, the rules cluster
        # around base), so a 30-point gap means nothing while a 400-place gap
        # means a lot.
        n = len(pairs)
        llm_rank = {p["job_id"]: i for i, p in
                    enumerate(sorted(pairs, key=lambda p: -p["fit"]))}
        rule_rank = {p["job_id"]: i for i, p in
                     enumerate(sorted(pairs, key=lambda p: -p["match"]))}
        worst = sorted(pairs,
                       key=lambda p: -(rule_rank[p["job_id"]] - llm_rank[p["job_id"]]))
        print(f"\n  RULES RANK THESE FAR LOWER THAN THE LLM DID "
              f"(the expensive kind of error, out of {n}):")
        for p in worst[:args.disagreements]:
            drop = rule_rank[p["job_id"]] - llm_rank[p["job_id"]]
            why = ", ".join(f"{r['rule']}{r['delta']:+d}" for r in p["reasons"])
            print(f"    fit {p['fit']:3} -> match {p['match']:3}  "
                  f"(rank {llm_rank[p['job_id']]}->{rule_rank[p['job_id']]}, "
                  f"{drop:+})  {p['title'][:52]}")
            print(f"        {why[:110]}")

    # Against the baseline, not just against the thresholds. The thresholds
    # were set before any measurement; these rows say whether the ranking beats
    # what it replaces, which is the question that decides shipping.
    #
    # "recency" is the honest baseline: the LLM never ranked anything, it
    # scored postings in arrival order, and nothing sorted the results. So the
    # status quo is whatever arrived most recently -- DESCENDING first_seen.
    # Sorting it the other way measures the oldest postings in the corpus,
    # which is not a baseline anybody was ever served. See the docstring.
    k = min(20, len(pairs))
    by_rules = sorted(pairs, key=lambda p: -p["match"])[:k]
    by_recent = sorted(pairs, key=lambda p: p.get("first_seen") or "",
                       reverse=True)[:k]

    # Averaged over many draws rather than one seed. A single sample of 20 from
    # a ~15% positive base rate has a standard deviation of ~1.5 hits, so one
    # seed can land anywhere from 1 to 6 and any of those looks like a fact.
    fit_sum = good_sum = 0.0
    for seed in range(RANDOM_DRAWS):
        random.seed(seed)
        sel = random.sample(pairs, k)
        fit_sum += statistics.mean([p["fit"] for p in sel])
        good_sum += sum(1 for p in sel if p["fit"] >= args.good)

    print("\n  TOP 20 QUALITY vs BASELINE (what actually reaches a user):")
    for label, sel in (("rules (match_score)", by_rules),
                       ("recency (newest first)", by_recent)):
        fits = [p["fit"] for p in sel]
        good = sum(1 for f in fits if f >= args.good)
        print(f"    {label:<26} mean fit {statistics.mean(fits):5.1f}   "
              f"{good:5.1f}/{k} at fit>={args.good}")
    print(f"    {f'random (mean of {RANDOM_DRAWS})':<26} "
          f"mean fit {fit_sum / RANDOM_DRAWS:5.1f}   "
          f"{good_sum / RANDOM_DRAWS:5.1f}/{k} at fit>={args.good}")

    ok = rho >= MIN_SPEARMAN and (recall is None or recall >= MIN_RECALL)
    print(f"\n  {'READY' if ok else 'BELOW THRESHOLD'}: the rules tier "
          f"{'meets' if ok else 'does not meet'} the ship thresholds -- but "
          f"read\n  the baseline rows above before treating that as a verdict.")
    sys.exit(0 if ok else 2)


if __name__ == "__main__":
    main()

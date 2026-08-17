#!/usr/bin/env python3
"""
What did the weights actually DO to the list a user sees?

THE QUESTION, PRECISELY
    `match_score` orders the list, and every score is a sum of named deltas
    that match.py already stores per row (`job_matches.match_reasons`, an
    invariant CLAUDE.md protects). So the number on any posting is fully
    attributable -- but nothing has ever printed the attribution. Reading
    match.py tells you what the rules ARE; this tells you what they DID.

    It exists to be disagreed with. Scan the top N, find a row you would not
    have ranked there, and the ledger beside it names the rule that put it
    there. That is a weight to change, located in one step rather than by
    re-deriving the arithmetic by hand.

NOT A MEASUREMENT, AND DELIBERATELY NOT ONE
    There is no ground truth here and this script invents none. It prints what
    the weights did; whether that was RIGHT is a judgement it leaves entirely
    to the reader. config/pursuit-criteria.json's `_unfitted` note is the
    standing statement of why no number in this repo can currently settle
    that, and printing a PASS/FAIL would be exactly the provisional number
    CLAUDE.md forbids re-tuning on.

    For the closest thing to a measurement that exists, see
    tools/calibrate-match.py -- rank correlation against the LLM tier, on the
    one profile where those judgements are not downstream of the weights being
    judged. This script makes zero LLM calls and is READ-ONLY.

THE RULE SUMMARY IS THE POINT
    The per-posting ledgers show you individual mistakes. The two summary
    blocks show you which rules are load-bearing at all: a weight that fires
    on 2% of rows cannot be why the ranking is wrong, and one that fires on
    every row is the base rate rather than a discriminator. Compare the
    top-N column against the whole-population column -- a rule that fires far
    more often up top is doing the actual sorting.

READS THROUGH jobs_app, NOT jobs
    The base table is deliberately unfiltered (see CLAUDE.md); the view is
    where the four required fields are enforced. A ledger built on `jobs`
    would show rows no user can ever be shown.

USAGE
    python3 tools/score-ledger.py
    python3 tools/score-ledger.py --profile pursuit -n 40
    python3 tools/score-ledger.py --profile pursuit --rule archetype:support_ops
    python3 tools/score-ledger.py --profile pursuit --floor-edge
"""

import argparse
import collections
import json
import os
import sys

# tools/ sits one level below the pipeline modules it imports. Python puts THIS
# file's directory on sys.path, not its parent, so the parent is added by hand.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import schema
from lib import dbconn, envfile

# Already-exported values still win -- see envfile.load(). tools/ scripts have
# historically required the caller to source .env the way the shell entry
# points do; loading it here means `python3 tools/score-ledger.py` works from a
# bare shell, which is how this one will actually be run.
envfile.load(os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), ".env"))


def busiest_profile(conn):
    """The profile with the most stored matches, or DEFAULT_PROFILE."""
    row = conn.execute(
        f"SELECT profile, count(*) FROM {schema.MATCHES_TABLE} "  # noqa: S608 -- splices schema.MATCHES_TABLE, a module-level constant
        f"GROUP BY profile ORDER BY 2 DESC LIMIT 1").fetchone()
    return row[0] if row else schema.DEFAULT_PROFILE


def load_rows(conn, profile, limit=None):
    """Scored postings for one profile, best first, read through the view."""
    sql = (f"SELECT id, match_score, match_reasons, title, company_name, "  # noqa: S608 -- splices schema.APP_VIEW, a module-level constant
           f"       seniority_level, role_archetype, ai_involvement, "
           f"       location_is_nyc, location_is_remote, fit_score "
           f"FROM {schema.APP_VIEW} WHERE profile = %s "
           f"ORDER BY match_score DESC, first_seen DESC")
    params = [profile]
    if limit is not None:
        sql += " LIMIT %s"
        params.append(limit)
    out = []
    for r in conn.execute(sql, params).fetchall():
        reasons = r[2]
        # match_reasons is written as JSON; psycopg hands back a str for a
        # json/text column and a list for jsonb. Accept either rather than
        # depending on which one the column happens to be.
        if isinstance(reasons, str):
            reasons = json.loads(reasons)
        out.append({
            "id": r[0], "score": r[1], "reasons": reasons or [],
            "title": r[3], "company": r[4],
            "seniority": r[5], "archetype": r[6], "ai": r[7],
            "nyc": r[8], "remote": r[9], "fit": r[10],
        })
    return out


def fmt_ledger(reasons, indent="      "):
    """The deltas of one posting, one per line, widest name first column."""
    if not reasons:
        return indent + "(no reasons stored)"
    width = max(len(str(x.get("rule", "?"))) for x in reasons)
    lines = []
    for x in reasons:
        delta = x.get("delta", 0)
        lines.append(f"{indent}{x.get('rule','?')!s:<{width}}  {delta:+d}")
    return "\n".join(lines)


def summarise(rows):
    """(fires, total_delta) per rule name over `rows`."""
    fires = collections.Counter()
    total = collections.Counter()
    for row in rows:
        for x in row["reasons"]:
            rule = str(x.get("rule", "?"))
            fires[rule] += 1
            total[rule] += x.get("delta", 0)
    return fires, total


def normalise(rule):
    """`archetype:pm` -> `archetype`, so families aggregate.

    Rules are colon-namespaced by convention (match.py's block comment on
    naming). The family is the discriminator worth counting; the specific
    value is what the per-posting ledger already shows.
    """
    return rule.split(":", 1)[0] if ":" in rule else rule


def _fold(counter):
    """Collapse a per-rule Counter onto rule families, summing collisions."""
    out = collections.Counter()
    for rule, value in counter.items():
        out[normalise(rule)] += value
    return out


def main():
    ap = argparse.ArgumentParser(
        description="Print the per-rule delta ledger behind match_score.")
    ap.add_argument("--profile", default=None,
                    help="default: the profile with the most stored matches")
    ap.add_argument("-n", "--top", type=int, default=40,
                    help="how many postings to print ledgers for (default 40)")
    ap.add_argument("--rule", default=None,
                    help="print only postings whose ledger contains this rule "
                         "(substring match, e.g. 'archetype:' or 'ai:none')")
    ap.add_argument("--floor-edge", action="store_true",
                    help="print the postings straddling MATCH_FLOOR instead of "
                         "the top -- where a weight change flips visibility")
    ap.add_argument("--families", action="store_true",
                    help="aggregate the summary by rule family rather than by "
                         "exact rule name")
    args = ap.parse_args()

    try:
        conn = dbconn.connect()
    except Exception as exc:                        # noqa: BLE001
        print(f"score-ledger FAILED: {exc}")
        return 1

    profile = args.profile or busiest_profile(conn)
    everything = load_rows(conn, profile)
    if not everything:
        known = conn.execute(
            f"SELECT DISTINCT profile FROM {schema.MATCHES_TABLE}"  # noqa: S608 -- splices schema.MATCHES_TABLE, a module-level constant
        ).fetchall()
        print(f"score-ledger: no scored postings for profile {profile!r}. "
              f"Profiles with matches: {[r[0] for r in known]}")
        return 1

    floor = schema.MATCH_FLOOR
    above = [r for r in everything if r["score"] >= floor]

    print(f"score-ledger: profile={profile}  scored={len(everything)}  "
          f"at-or-above MATCH_FLOOR({floor})={len(above)} "
          f"({100.0 * len(above) / len(everything):.1f}%)")
    print()

    # -- which postings to show ledgers for ---------------------------------
    if args.floor_edge:
        # The rows a weight change actually moves in or out of view. Ordered
        # by distance from the floor so the closest calls are adjacent.
        shown = sorted(everything, key=lambda r: abs(r["score"] - floor))
        shown = shown[:args.top]
        shown.sort(key=lambda r: -r["score"])
        heading = f"POSTINGS STRADDLING THE FLOOR ({floor})"
    else:
        shown = everything[:args.top]
        heading = f"TOP {min(args.top, len(everything))} BY match_score"

    if args.rule:
        shown = [r for r in shown
                 if any(args.rule in str(x.get("rule", ""))
                        for x in r["reasons"])]
        heading += f"  [filtered to rule ~ {args.rule!r}]"

    print(f"  {heading}")
    print(f"  {'-' * len(heading)}")
    for i, row in enumerate(shown, 1):
        total = sum(x.get("delta", 0) for x in row["reasons"])
        # The stored score is clamped to 0..100 and a hard-exclude returns 0
        # outright, so the deltas need not sum to it. Say so when they differ
        # rather than printing two numbers and leaving it to the reader.
        note = "" if total == row["score"] else f"  (deltas sum to {total}; clamped or hard-excluded)"
        fit = f"  fit {row['fit']}" if row["fit"] is not None else ""
        loc = "NYC" if row["nyc"] else ("remote" if row["remote"] else "elsewhere")
        print(f"  {i:>3}. [{row['score']:>3}]{fit}  {(row['title'] or '')[:64]}")
        print(f"       {(row['company'] or '?')[:40]}  |  {loc}  |  "
              f"{row['seniority'] or '?'} / {row['archetype'] or '?'} / "
              f"{row['ai'] or '?'}{note}")
        print(fmt_ledger(row["reasons"]))
        print()

    if not shown:
        print("  (nothing matched)")
        print()

    # -- rule summary -------------------------------------------------------
    # Two populations side by side: the rules firing in the visible top N, and
    # the same rules across everything scored. A rule whose share is the same
    # in both columns is not sorting anything.
    top_pop = everything[:args.top]
    f_top, t_top = summarise(top_pop)
    f_all, t_all = summarise(everything)
    if args.families:
        # SUM, never overwrite. A dict comprehension keyed on normalise(k)
        # silently keeps only the last member of each family -- `archetype:pm`
        # would clobber `archetype:data`'s count -- which reads as a plausible
        # table rather than as an error. Every one of the four counters is
        # accumulated with += for that reason.
        f_top, f_all, t_top, t_all = (_fold(f_top), _fold(f_all),
                                      _fold(t_top), _fold(t_all))

    print(f"  RULE ACTIVITY -- top {len(top_pop)} vs all {len(everything)} scored")
    print(f"  {'rule':<38} {'top n':>10} {'all':>12} {'mean delta':>11}")
    print(f"  {'-' * 38} {'-' * 10} {'-' * 12} {'-' * 11}")
    for rule, n_all in f_all.most_common():
        n_top = f_top.get(rule, 0)
        mean = t_all[rule] / n_all if n_all else 0.0
        print(f"  {rule[:38]:<38} "
              f"{n_top:>4} {100.0 * n_top / max(len(top_pop), 1):>4.0f}% "
              f"{n_all:>5} {100.0 * n_all / len(everything):>4.0f}% "
              f"{mean:>+10.1f}")

    print()
    print("  Read the last column as 'what this rule is worth when it fires'.")
    print("  A rule with a near-identical top-n and all share is the base rate,")
    print("  not a discriminator. This script asserts nothing about whether any")
    print("  of these numbers is correct -- see the module docstring.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

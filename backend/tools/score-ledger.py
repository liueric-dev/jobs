#!/usr/bin/env python3
"""
What did the weights actually DO to the list a user sees?

THE QUESTION, PRECISELY
    `match_score` orders the list, and every score is a sum of named deltas
    that match.py builds per posting (`job_matches.match_reasons`, an
    invariant CLAUDE.md protects). So the number on any posting is fully
    attributable -- but nothing has ever printed the attribution. Reading
    match.py tells you what the rules ARE; this tells you what they DID.

    It exists to be disagreed with. Scan the list, find a row you would not
    have ranked there, and the ledger beside it names the rule that put it
    there. That is a weight to change, located in one step rather than by
    re-deriving the arithmetic by hand.

IT SCORES THE WHOLE POPULATION, AND THAT IS THE WHOLE POINT
    match.py stores a row ONLY when it clears MATCH_FLOOR (match.py:622). So
    `job_matches` -- and `jobs_app`, and anything built on either -- contains
    survivors and nothing else.

    MEASURING RULE INCIDENCE THERE IS A SELECTION-BIAS TRAP, and this tool fell
    into it on its first version: `ai:uses_ai_tools` fires on 74% of stored
    pursuit rows, which reads as "so common it cannot be sorting anything."
    That inference is exactly backwards. Scored across all 996 relevant
    postings instead of the 186 stored ones, zeroing that one weight drops the
    survivor count from 186 to 103. It was not a base rate; it was the rule
    doing the selecting, and it looked flat only because it was being measured
    on the population it had already selected.

    So this re-scores every posting `match.load_facts()` returns, in-process,
    with score_job() -- pure, no I/O, no LLM calls, nothing written. The stored
    rows are read only to report drift against them.

    The same trap is why the floor's effect is printed as N of M and not as a
    percentage of the stored set, where it is always 100%.

NOT A MEASUREMENT, AND DELIBERATELY NOT ONE
    There is no ground truth here and this invents none. It prints what the
    weights did; whether that was RIGHT is left entirely to the reader.
    config/pursuit-criteria.json's `_unfitted` note is the standing statement
    of why no number in this repo can currently settle that, and printing a
    PASS/FAIL would be the provisional number CLAUDE.md forbids re-tuning on.

    For the closest thing to a measurement that exists, see
    tools/calibrate-match.py -- rank correlation against the LLM tier, on the
    one profile whose judgements are not downstream of the weights being
    judged.

READS THE BASE `jobs` TABLE FOR TITLES, DELIBERATELY
    CLAUDE.md says read through `jobs_app`. That rule is about the read edge an
    app serves, and this tool's subject is precisely the postings that never
    reach it -- a below-floor row has no `jobs_app` row to read. Titles are
    therefore joined from `jobs`, where the four view-required fields are not
    guaranteed; a missing one prints as `?` rather than dropping the row.

USAGE
    python3 tools/score-ledger.py --profile pursuit
    python3 tools/score-ledger.py --profile pursuit --floor-edge
    python3 tools/score-ledger.py --profile pursuit --rejected
    python3 tools/score-ledger.py --profile pursuit --rule ai:none
"""

import argparse
import collections
import os
import sys

# tools/ sits one level below the pipeline modules it imports. Python puts THIS
# file's directory on sys.path, not its parent, so the parent is added by hand.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import match
import profiles
import relevance
import schema
from lib import dbconn, envfile

# Already-exported values still win -- see envfile.load(). tools/ scripts have
# historically required the caller to source .env the way the shell entry points
# do; loading it here means `python3 tools/score-ledger.py` works from a bare
# shell, which is how this one will actually be run.
envfile.load(os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), ".env"))


def busiest_profile(conn):
    """The profile with the most stored matches, or DEFAULT_PROFILE."""
    row = conn.execute(
        f"SELECT profile, count(*) FROM {schema.MATCHES_TABLE} "  # noqa: S608 -- splices schema.MATCHES_TABLE, a module-level constant
        f"GROUP BY profile ORDER BY 2 DESC LIMIT 1").fetchone()
    return row[0] if row else schema.DEFAULT_PROFILE


def load_population(conn, prof):
    """Every relevant posting, re-scored now. Best first.

    Not "every stored match" -- see the module docstring. This is the input
    match.py sees, before the floor removes four fifths of it.
    """
    facts = list(match.load_facts(conn, [relevance.for_profile(prof)]))
    if not facts:
        return []

    ids = [f["job_id"] for f in facts]
    titles = {
        r[0]: (r[1], r[2]) for r in conn.execute(
            f"SELECT id, title, company_name FROM {schema.TABLE} "  # noqa: S608 -- splices schema.TABLE, a module-level constant
            f"WHERE id = ANY(%s)", (ids,)).fetchall()}
    stored = {
        r[0]: r[1] for r in conn.execute(
            f"SELECT job_id, match_score FROM {schema.MATCHES_TABLE} "  # noqa: S608 -- splices schema.MATCHES_TABLE, a module-level constant
            f"WHERE profile = %s", (prof.profile,)).fetchall()}
    fits = {
        r[0]: r[1] for r in conn.execute(
            f"SELECT job_id, fit_score FROM {schema.SCORES_TABLE} "  # noqa: S608 -- splices schema.SCORES_TABLE, a module-level constant
            f"WHERE profile = %s", (prof.profile,)).fetchall()}

    rows = []
    for f in facts:
        score, reasons = match.score_job(f, prof.criteria)
        title, company = titles.get(f["job_id"], (None, None))
        rows.append({
            "id": f["job_id"], "score": score, "reasons": reasons,
            "title": title, "company": company,
            "seniority": f.get("seniority_level"),
            "archetype": f.get("role_archetype"),
            "ai": f.get("ai_involvement"),
            "nyc": f.get("location_is_nyc"),
            "remote": f.get("location_is_remote"),
            "fit": fits.get(f["job_id"]),
            "stored": stored.get(f["job_id"]),
        })
    # Ties broken by job_id so two runs over unchanged data print in the same
    # order -- a ledger you cannot diff against yesterday's is worth less.
    rows.sort(key=lambda r: (-r["score"], r["id"]))
    return rows


def fmt_ledger(reasons, indent="      "):
    """The deltas of one posting, one per line, name column padded to fit."""
    if not reasons:
        return indent + "(no reasons)"
    width = max(len(str(x.get("rule", "?"))) for x in reasons)
    return "\n".join(
        f"{indent}{x.get('rule', '?')!s:<{width}}  {x.get('delta', 0):+d}"
        for x in reasons)


def summarise(rows):
    """(fires, total_delta) per rule name over `rows`."""
    fires, total = collections.Counter(), collections.Counter()
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
    """Collapse a per-rule Counter onto rule families, summing collisions.

    SUM, never overwrite. A dict comprehension keyed on normalise(k) silently
    keeps only the last member of each family -- `archetype:pm` would clobber
    `archetype:data`'s count -- which reads as a plausible table rather than
    as an error.
    """
    out = collections.Counter()
    for rule, value in counter.items():
        out[normalise(rule)] += value
    return out


def print_rows(rows, heading, floor):
    print(f"  {heading}")
    print(f"  {'-' * len(heading)}")
    if not rows:
        print("  (nothing matched)")
        print()
        return
    for i, row in enumerate(rows, 1):
        total = sum(x.get("delta", 0) for x in row["reasons"])
        # The score is clamped to 0..100 and a hard-exclude returns 0 outright,
        # so the deltas need not sum to it. Say so when they differ rather than
        # printing two numbers and leaving it to the reader.
        note = ("" if total == row["score"]
                else f"  (deltas sum to {total}; clamped or hard-excluded)")
        mark = " " if row["score"] >= floor else "x"
        fit = f"  fit {row['fit']}" if row["fit"] is not None else ""
        # A stored score that disagrees with the recomputed one means the
        # weights changed since match.py last ran -- worth seeing, because
        # every other number here describes the NEW weights and the app is
        # still serving the old ones.
        drift = ("" if row["stored"] is None or row["stored"] == row["score"]
                 else f"  [stored {row['stored']}]")
        loc = "NYC" if row["nyc"] else ("remote" if row["remote"] else "elsewhere")
        print(f"  {mark}{i:>3}. [{row['score']:>3}]{fit}{drift}  "
              f"{(row['title'] or '?')[:62]}")
        print(f"        {(row['company'] or '?')[:40]}  |  {loc}  |  "
              f"{row['seniority'] or '?'} / {row['archetype'] or '?'} / "
              f"{row['ai'] or '?'}{note}")
        print(fmt_ledger(row["reasons"]))
        print()


def main():
    ap = argparse.ArgumentParser(
        description="Print the per-rule delta ledger behind match_score.")
    ap.add_argument("--profile", default=None,
                    help="default: the profile with the most stored matches")
    ap.add_argument("-n", "--top", type=int, default=40,
                    help="how many postings to print ledgers for (default 40)")
    ap.add_argument("--rule", default=None,
                    help="print only postings whose ledger contains this rule "
                         "(substring, e.g. 'archetype:' or 'ai:none')")
    ap.add_argument("--floor-edge", action="store_true",
                    help="print the postings straddling MATCH_FLOOR -- both "
                         "sides -- instead of the top")
    ap.add_argument("--rejected", action="store_true",
                    help="print the highest-scoring postings the floor "
                         "REMOVED, which no other view in this repo shows")
    ap.add_argument("--families", action="store_true",
                    help="aggregate the summary by rule family rather than by "
                         "exact rule name")
    args = ap.parse_args()

    try:
        conn = dbconn.connect()
    except Exception as exc:                        # noqa: BLE001
        print(f"score-ledger FAILED: {exc}")
        return 1

    name = args.profile or busiest_profile(conn)
    prof = profiles.load_one(conn, name)
    if not prof:
        print(f"score-ledger FAILED: no profile named {name!r}")
        return 1

    rows = load_population(conn, prof)
    if not rows:
        print(f"score-ledger: profile {name!r} has no relevant extracted "
              f"postings -- nothing to score.")
        return 1

    floor = schema.MATCH_FLOOR
    above = [r for r in rows if r["score"] >= floor]
    drifted = sum(1 for r in rows
                  if r["stored"] is not None and r["stored"] != r["score"])

    print(f"score-ledger: profile={name}  criteria_version={prof.criteria_version}")
    print(f"  relevant postings scored   {len(rows)}")
    print(f"  clear MATCH_FLOOR ({floor})       {len(above)}  "
          f"({100.0 * len(above) / len(rows):.1f}%)  <- what a user can see")
    print(f"  removed by the floor       {len(rows) - len(above)}")
    if drifted:
        print(f"  !! {drifted} stored score(s) disagree with these weights -- "
              f"run `python3 match.py` to refresh job_matches")
    print()

    # -- which postings to show ledgers for ---------------------------------
    if args.rejected:
        shown = [r for r in rows if r["score"] < floor][:args.top]
        heading = f"HIGHEST-SCORING POSTINGS THE FLOOR REMOVED (< {floor})"
    elif args.floor_edge:
        # Both sides, ordered by distance from the floor, so the closest calls
        # are adjacent and a weight change's effect is visible as a boundary.
        shown = sorted(rows, key=lambda r: abs(r["score"] - floor))[:args.top]
        shown.sort(key=lambda r: -r["score"])
        heading = f"POSTINGS STRADDLING THE FLOOR ({floor}); x = removed"
    else:
        shown = rows[:args.top]
        heading = f"TOP {min(args.top, len(rows))} BY match_score"

    if args.rule:
        shown = [r for r in shown
                 if any(args.rule in str(x.get("rule", ""))
                        for x in r["reasons"])]
        heading += f"  [rules matching {args.rule!r}]"

    print_rows(shown, heading, floor)

    # -- rule summary -------------------------------------------------------
    # Visible vs everything scored. A rule whose share is the same in both is
    # not selecting anything; a rule far commoner among survivors is doing the
    # work. Measured over the FULL population precisely because measuring it
    # over the survivors is the trap the docstring describes.
    f_vis, _ = summarise(above)
    f_all, t_all = summarise(rows)
    if args.families:
        f_vis, f_all, t_all = _fold(f_vis), _fold(f_all), _fold(t_all)

    print(f"  RULE ACTIVITY -- {len(above)} visible vs {len(rows)} scored")
    print(f"  {'rule':<36} {'visible':>12} {'all scored':>14} {'mean':>8}")
    print(f"  {'-' * 36} {'-' * 12} {'-' * 14} {'-' * 8}")
    for rule, n_all in f_all.most_common():
        n_vis = f_vis.get(rule, 0)
        print(f"  {rule[:36]:<36} "
              f"{n_vis:>5} {100.0 * n_vis / max(len(above), 1):>5.0f}% "
              f"{n_all:>6} {100.0 * n_all / len(rows):>5.0f}% "
              f"{t_all[rule] / n_all:>+8.1f}")

    print()
    print("  Last column: what the rule is worth WHEN IT FIRES. A rule whose")
    print("  visible and all-scored shares differ is selecting; one where they")
    print("  match is a base rate. This asserts nothing about whether any of")
    print("  these numbers is correct -- see the module docstring.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

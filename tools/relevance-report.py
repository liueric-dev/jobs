#!/usr/bin/env python3
"""
Show what config/relevance.json actually does to the current table.

READ-ONLY. Run this after every edit to relevance.json. A relevance filter
fails silently in the direction that hurts -- a pattern that matches nothing
does not error, it just quietly demotes good postings to tier 3 where nothing
will score them and nobody will look. The only way to know is to read the
tiers back.

    python3 tools/relevance-report.py              # distribution + samples
    python3 tools/relevance-report.py --samples 20 # more per tier
    python3 tools/relevance-report.py --dead       # which patterns match nothing

WHAT TO LOOK FOR
    tier 3 samples  -- the important one. Anything here you would actually
                       apply to is a false negative, and false negatives are
                       invisible in production. This is the check.
    --dead          -- patterns matching zero rows. Usually a typo or a
                       Postgres/Python regex-dialect mistake (\\y not \\b).
"""

import os
import sys
import argparse

# ingest/ and tools/ sit one level below the pipeline modules they import
# (schema, relevance, llm, ...). Python puts THIS file's directory on sys.path,
# not its parent, so the parent is added by hand. pipelib needs nothing -- it is
# an installed package (pip install --user -e ~/apps/pipelib).
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import schema     # noqa: E402
import relevance  # noqa: E402
import score      # noqa: E402
from pipelib import dbconn  # noqa: E402


def distribution(conn, expr, params, profile):
    rows = conn.execute(
        f"""SELECT {expr} AS tier, count(*) FROM {schema.TABLE} j
            WHERE j.status = %(status)s
              AND NOT EXISTS (SELECT 1 FROM {schema.SCORES_TABLE} s
                              WHERE s.job_id = j.id AND s.profile = %(profile)s)
            GROUP BY 1 ORDER BY 1""",
        {**params, "status": schema.STATUS_OPEN, "profile": profile},
    ).fetchall()
    return rows


def samples(conn, expr, params, profile, tier, n):
    return conn.execute(
        f"""SELECT j.title, j.company_name FROM {schema.TABLE} j
            WHERE j.status = %(status)s
              AND NOT EXISTS (SELECT 1 FROM {schema.SCORES_TABLE} s
                              WHERE s.job_id = j.id AND s.profile = %(profile)s)
              AND ({expr}) = %(tier)s
            ORDER BY random() LIMIT %(n)s""",
        {**params, "status": schema.STATUS_OPEN, "profile": profile,
         "tier": tier, "n": n},
    ).fetchall()


def dead_patterns(conn, cfg):
    """Patterns matching zero open titles -- typos and dialect mistakes."""
    out = []
    for key in ("title_include", "title_exclude"):
        for pat in cfg[key]:
            n = conn.execute(
                f"SELECT count(*) FROM {schema.TABLE} "
                f"WHERE status = %s AND title ~* %s",
                (schema.STATUS_OPEN, pat),
            ).fetchone()[0]
            if n == 0:
                out.append((key, pat))
    return out


def main():
    p = argparse.ArgumentParser(description="Report on relevance.json (read-only).")
    p.add_argument("--samples", type=int, default=10, help="titles to show per tier")
    p.add_argument("--dead", action="store_true", help="list patterns matching nothing")
    p.add_argument("--profile", default=None)
    args = p.parse_args()

    cfg = relevance.load()
    expr, params = relevance.tier_sql(cfg)
    conn = dbconn.connect_or_exit("relevance-report", schema=schema.SCHEMA)
    profile = args.profile or schema.resolve_profile(score.load_persona())
    cap = relevance.max_tier(cfg)

    rows = distribution(conn, expr, params, profile)
    total = sum(n for _, n in rows) or 1
    print(f"unscored open jobs for profile {profile!r}: {total}")
    print(f"max_tier_to_score = {cap}\n")
    for tier, n in rows:
        mark = "scored" if tier <= cap else "SKIPPED"
        print(f"  tier {tier}: {n:>6}  ({100*n/total:>5.1f}%)  {mark}")
    eligible = sum(n for t, n in rows if t <= cap)
    print(f"\n  eligible now: {eligible} of {total} "
          f"({100*(1-eligible/total):.1f}% filtered out)")

    if args.dead:
        dead = dead_patterns(conn, cfg)
        print(f"\n{'='*66}\nPATTERNS MATCHING NOTHING\n{'='*66}")
        if not dead:
            print("  none -- every pattern matches at least one open title")
        for key, pat in dead:
            print(f"  {key:<16} {pat!r}")

    for tier, _ in rows:
        note = ""
        if tier == 3:
            note = "   <-- anything here you'd apply to is a false negative"
        print(f"\n{'='*66}\nTIER {tier} sample{note}\n{'='*66}")
        for title, company in samples(conn, expr, params, profile, tier, args.samples):
            print(f"  {(title or '')[:56]:<58} {(company or '')[:20]}")
    conn.close()


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
Show what config/relevance.json actually does to the current table.

READ-ONLY. Run this after every edit to relevance.json. A relevance filter
fails silently in the direction that hurts -- a pattern that matches nothing
does not error, it just quietly demotes good postings to tier 3 where nothing
will score them and nobody will look. The only way to know is to read the
tiers back.

    python3 tools/relevance-report.py                    # distribution + samples
    python3 tools/relevance-report.py --samples 20       # more per tier
    python3 tools/relevance-report.py --dead             # which patterns match nothing
    python3 tools/relevance-report.py --profile pursuit  # that profile's own gate

WHAT TO LOOK FOR
    tier 3 samples  -- the important one. Anything here you would actually
                       apply to is a false negative, and false negatives are
                       invisible in production. This is the check.
    --dead          -- patterns matching zero rows. Usually a typo or a
                       Postgres/Python regex-dialect mistake (\\y not \\b).

--profile RESOLVES THE PROFILE'S OWN relevance_json
    A profile's relevance_json overrides the shared file (relevance.for_profile,
    relevance.py:100), and a per-profile gate that has never been reported on
    is a gate nobody has checked. Passing --profile therefore changes BOTH which
    already-scored rows are excluded from the counts and which config is being
    reported. Without it, the shared config is reported, as before.

WHICH COLUMN A PATTERN IS TESTED AGAINST
    Each list is tested against the column tier_sql actually applies it to:
    title_exclude against title, company_exclude against company_name,
    platform_exclude against platform, description_exclude against
    description_text.

    The two INCLUDE lists are the exception: they are tested against
    title || description_text, not against one column. That is deliberate.
    Since description_include exists, an include term is a claim about the
    posting's text rather than about its header, and this report's job is to
    catch the dialect mistake -- a term that can match NOTHING, ANYWHERE --
    not to prune terms that are simply rare in titles. relevance.json's
    _dead_patterns_note makes exactly that distinction: '\\yattorney\\y' and
    '\\ywarehouse\\y' are kept on purpose. Testing include terms per-column
    would report a dozen correct patterns ('zapier', 'copilot', 'make\\.com')
    as dead purely because no title happens to contain them, and a report that
    cries wolf is a report nobody reads.
"""

import os
import sys
import argparse

# ingest/ and tools/ sit one level below the pipeline modules they import
# (schema, relevance, llm, ...). Python puts THIS file's directory on sys.path,
# not its parent, so the parent is added by hand. That same insert is what
# reaches lib/ -- there is nothing to install.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import schema     # noqa: E402
import relevance  # noqa: E402
import profiles   # noqa: E402
import score      # noqa: E402
from lib import dbconn, envfile  # noqa: E402

# Read-only tool, so it loads the pipeline's own .env rather than requiring the
# caller to export DATABASE_URL first. override=False, so an exported value
# still wins -- pointing this at a scratch database stays a matter of exporting
# one variable.
envfile.load(os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env"))


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


#: Which column each list is checked against. See the module docstring for why
#: the include lists are checked against title || description_text rather than
#: against title alone.
_POSTING_TEXT = "COALESCE(title, '') || ' ' || COALESCE(description_text, '')"
_DEAD_COLUMNS = {
    "title_include": _POSTING_TEXT,
    "description_include": _POSTING_TEXT,
    "title_exclude": "COALESCE(title, '')",
    "company_exclude": "COALESCE(company_name, '')",
    "platform_exclude": "COALESCE(platform, '')",
    "description_exclude": "COALESCE(description_text, '')",
}


def dead_patterns(conn, cfg):
    """Patterns matching zero open rows -- typos and dialect mistakes.

    Flattens the include lists' group structure (relevance._include_groups):
    a conjunctive gate is several groups of terms, and the point of this
    report is that EVERY term is individually reachable. Checking the joined
    alternation instead would hide a dead term behind its live neighbours,
    which is the exact failure the \\y-vs-\\b landmine produces.
    """
    out = []
    for key, column in _DEAD_COLUMNS.items():
        patterns = cfg.get(key) or []
        if key.endswith("_include"):
            patterns = [p for group in relevance._include_groups(patterns)
                        for p in group]
        for pat in patterns:
            n = conn.execute(
                f"SELECT count(*) FROM {schema.TABLE} "
                f"WHERE status = %s AND {column} ~* %s",
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

    conn = dbconn.connect_or_exit("relevance-report", schema=schema.SCHEMA)
    profile = args.profile or schema.resolve_profile(score.load_persona())

    # for_profile, not load(): a profile with its own relevance_json is gated
    # by that and not by the shared file, and reporting the shared file for it
    # would describe a filter that is not running.
    row = profiles.load_one(conn, profile)
    cfg = relevance.for_profile(row) if row else relevance.load()
    source = ("its own relevance_json" if row and row.relevance is not None
              else "the shared config/relevance.json")
    expr, params = relevance.tier_sql(cfg)
    cap = relevance.max_tier(cfg)

    rows = distribution(conn, expr, params, profile)
    total = sum(n for _, n in rows) or 1
    print(f"unscored open jobs for profile {profile!r}: {total}")
    print(f"gated by {source}"
          f"{'' if row else '  (profile not in the profiles table)'}")
    if row and not row.active:
        print("  NOTE: this profile is INACTIVE. extract.py and match.py do "
              "not see it (profiles.load_active), so these tiers are a "
              "projection, not production behaviour.")
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

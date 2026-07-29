#!/usr/bin/env python3
"""
Add job_scores.facts_version / .persona_sha / .prompt_version /
.criteria_version, and count -- without touching -- the rows that predate them.

WHY A MIGRATION IS NEEDED AT ALL
    Not for the DDL. ensure_schema() adds all four columns on the next run of
    any script (schema.py:585), so the column add here is belt and braces --
    runnable on demand, before a deploy, rather than waiting for the nightly
    pipeline to be the thing that alters a table.

    The reason this file exists is the CENSUS. job_scores shipped with no
    version columns at all, so re-scoring triggered only on an anti-join for
    "no row exists" (score.select_shortlist, score.py:262-263). Every row
    written before today is therefore unversioned, and nobody can say how many
    that is or what re-scoring them would cost without asking. This script is
    how an operator learns the size of the exposure BEFORE anyone types a
    re-scoring flag. The number it prints is the bill.

WHAT IT DELIBERATELY DOES NOT DO
    IT BACKFILLS NOTHING. That is the whole difference between this migration
    and migrate_extraction_passes.py, which backfilled extraction_passes = 1
    because that was a fact: until that change the script could not make a
    second LLM call, so every pre-existing row had had exactly one. Here there
    is no equivalent fact. Every candidate value is a guess about the past
    dressed up as a record of it, and the four columns fail in four different
    ways:

    prompt_version is not backfilled. score.build_prompt changed mid-history
    in e1cdf7b (the D16 buckets fix, task 08) on 2026-07-28. Stored scores
    span 2026-07-25T20:26 -> 2026-07-28T04:07, so the corpus straddles the
    change -- and even if it did not, a commit timestamp records when code
    landed, not when the running process picked it up. Writing
    SCORE_PROMPT_VERSION onto all of them would claim every stored narrative
    came from today's template when a fraction demonstrably did not. This is
    vote_unanimity = 1.0 in a different costume.

    persona_sha is not backfilled, and this is the strongest case of the four.
    profiles.upsert overwrites persona_json wholesale on every
    migrate_profiles.py --apply (profiles.py:175-211); there is no history
    table, no prior blob, nothing to hash. Today's persona is not evidence
    about 2026-07-25's persona. Stamping today's digest on old rows would
    assert that every stored narrative was written under the current persona,
    which is exactly the claim nobody is in a position to make.

    facts_version is not backfilled, and this is the tempting one -- the
    backfill the next person will propose, because it looks free. job_facts
    has the column already, so `UPDATE job_scores s SET facts_version =
    f.facts_version FROM job_facts f WHERE f.job_id = s.job_id` is one
    statement and it runs. It also DESTROYS INFORMATION. Task 12 re-extracted
    859 rows on 2026-07-28, AFTER most of these scores were written; copying
    today's value onto a narrative written from v2 facts stamps it v3-current
    and permanently hides a genuinely stale row from the one query the column
    exists to answer. A NULL that says "unknown" is recoverable. A confident
    wrong version is not.

    criteria_version is not backfilled. tech sits at criteria_version = 5
    today; the scores under that profile were written under something earlier
    and nothing anywhere records which. The column is provenance for L2
    analysis (schema.py:566-571), and provenance invented after the fact is
    not provenance.

    It also re-scores nothing. Spending 1,000-odd LLM calls is an operator's
    decision made with this report in hand, not a side effect of a migration.

UNVERSIONED IS A THIRD STATE, NOT A STALE ONE
    This is the load-bearing part of the NULL semantics and the reason the
    columns are nullable with no DEFAULT. A row whose recorded version differs
    from the current one is stale: something upstream moved and we know it. A
    row with no recorded version is neither stale nor fresh -- it is unknown,
    and the honest response to unknown is to report it in its own bucket and
    leave it alone. So this report counts unversioned rows separately, and
    score.py grows --rescore-unversioned as a flag DISTINCT from
    --rescore-stale. An operator who wants to pay for the unknowns says so.
    Collapsing the two states -- by backfilling, or by treating NULL as
    "version 0" -- is what makes that separation impossible, which is why NULL
    must stay NULL.

USAGE
    python3 migrations/migrate_score_versions.py            # report only
    python3 migrations/migrate_score_versions.py --apply    # adds columns

IDEMPOTENT, and more strongly than most: the default path is a pure read, and
--apply's only write is the column add, which checks the catalog first (see
lib/dbconn.add_missing_columns -- a bare ADD COLUMN IF NOT EXISTS still takes
an ACCESS EXCLUSIVE lock every run). Running --apply twice, or running it
after ensure_schema has already added the columns, adds nothing and writes
nothing. There is no backfill to re-run because there is no backfill.
"""

import argparse
import os
import sys

# migrations/ sits one level below the pipeline modules it imports (schema,
# profiles, ...). Python puts THIS file's directory on sys.path, not its
# parent, so the parent is added by hand. That same insert is what reaches
# lib/ -- there is nothing to install.
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _REPO_ROOT)

import schema  # noqa: E402
from lib import dbconn, envfile  # noqa: E402

# Establishes its own environment, following migrate_company_ats.py rather
# than the older migrations that assume a shell which already sourced .env.
# Already-exported values still win -- see envfile.load().
envfile.load(os.path.join(_REPO_ROOT, ".env"))

NEW_COLUMNS = [
    ("facts_version", "INTEGER"),
    ("persona_sha", "TEXT"),
    ("prompt_version", "INTEGER"),
    ("criteria_version", "INTEGER"),
]

#: A score row is a tombstone when the call failed: score.py writes the row
#: anyway with scoring_model = "FAILED:<label>" so a posting that could not be
#: scored is not retried nightly forever (score.py:87, :501).
TOMBSTONE_LIKE = "FAILED:%"


def _reachable_sql():
    """The join score.select_shortlist actually uses, minus its anti-join.

    THE POINT OF THIS QUERY: a count of job_scores overstates what re-scoring
    can cost. select_shortlist (score.py:250-268) reaches a posting only
    through job_matches, and only while j.status = open. Rows whose job has
    since closed, or that never cleared MATCH_FLOOR into job_matches, are
    unreachable by that path -- no flag routed through the shortlist can touch
    them, whatever a total says. The job_facts join is reproduced too because
    it is an inner join there: a score with no facts row would not be
    selected either.

    This is the number that prices a re-score. The total is the number that
    prices nothing.
    """
    return f"""
        FROM {schema.SCORES_TABLE} s
        JOIN {schema.MATCHES_TABLE} m
          ON m.job_id = s.job_id AND m.profile = s.profile
        JOIN {schema.TABLE} j ON j.id = s.job_id
        JOIN {schema.FACTS_TABLE} f ON f.job_id = s.job_id
        WHERE j.status = %(status)s
    """


def _counts(conn, have_columns):
    """Per-profile census. Returns {profile: dict}."""
    stats = {}

    def row(p):
        return stats.setdefault(p, {"rows": 0, "scored": 0, "reachable": 0,
                                    "tombstones": 0, "versioned": None,
                                    "criteria_version": None, "budget": None,
                                    "active": None})

    for p, total, scored, tombs in conn.execute(
            f"SELECT profile, count(*), count(fit_score), "
            f"       count(*) FILTER (WHERE scoring_model LIKE %(t)s) "
            f"FROM {schema.SCORES_TABLE} GROUP BY profile",
            {"t": TOMBSTONE_LIKE}).fetchall():
        r = row(p)
        r["rows"], r["scored"], r["tombstones"] = total, scored, tombs

    for p, n in conn.execute(
            f"SELECT s.profile, count(*) {_reachable_sql()} GROUP BY s.profile",
            {"status": schema.STATUS_OPEN}).fetchall():
        row(p)["reachable"] = n

    if have_columns:
        # The proof that no backfill happened. Every one of these must be 0.
        for p, n in conn.execute(
                f"SELECT profile, count(*) FROM {schema.SCORES_TABLE} "
                f"WHERE facts_version IS NOT NULL OR persona_sha IS NOT NULL "
                f"   OR prompt_version IS NOT NULL "
                f"   OR criteria_version IS NOT NULL "
                f"GROUP BY profile").fetchall():
            row(p)["versioned"] = n
        for r in stats.values():
            if r["versioned"] is None:
                r["versioned"] = 0

    # Profiles with no scores at all still belong in the census -- pursuit is
    # the active profile and its absence from job_scores is the fact that
    # makes this whole gap survivable.
    for p, cv, budget, active in conn.execute(
            f"SELECT profile, criteria_version, daily_narrative_budget, active "
            f"FROM {schema.PROFILES_TABLE}").fetchall():
        r = row(p)
        r["criteria_version"], r["budget"], r["active"] = cv, budget, active
        if have_columns and r["versioned"] is None:
            r["versioned"] = 0

    return stats


def _report(conn, have_columns, missing):
    stats = _counts(conn, have_columns)
    order = sorted(stats, key=lambda p: (-stats[p]["rows"], p))

    ver = "versioned" if have_columns else "versioned*"
    print(f"\n  {'profile':<12}{'rows':>8}{'scored':>8}{'reachable':>11}"
          f"{'tombstone':>11}{ver:>11}   profile config")
    tot = {k: 0 for k in ("rows", "scored", "reachable", "tombstones",
                          "versioned")}
    for p in order:
        r = stats[p]
        cfg = ("--" if r["criteria_version"] is None else
               f"criteria v{r['criteria_version']}, budget {r['budget']}, "
               f"{'active' if r['active'] else 'inactive'}")
        shown = "n/a" if r["versioned"] is None else str(r["versioned"])
        print(f"  {p:<12}{r['rows']:>8}{r['scored']:>8}{r['reachable']:>11}"
              f"{r['tombstones']:>11}{shown:>11}   {cfg}")
        for k in tot:
            tot[k] += r[k] or 0
    print(f"  {'TOTAL':<12}{tot['rows']:>8}{tot['scored']:>8}"
          f"{tot['reachable']:>11}{tot['tombstones']:>11}"
          f"{(tot['versioned'] if have_columns else 'n/a'):>11}")

    if not have_columns:
        # Cannot count what does not exist yet, and saying so is better than
        # printing a zero that reads like "the backfill already ran".
        print(f"\n  * the version columns do not exist yet "
              f"({', '.join(missing)}), so no row can carry one. After "
              f"--apply this column must read 0 and stay 0 -- it is the "
              f"proof that nothing was backfilled.")
    elif tot["versioned"]:
        print(f"\n  ** {tot['versioned']} row(s) carry a non-null version. "
              f"Rows written since the columns landed do this legitimately; "
              f"if the count jumped for old rows, something backfilled, and "
              f"a backfill here is the one thing this design forbids.")
    else:
        print("\n  every existing row is unversioned, as intended. That is a "
              "THIRD STATE -- not stale, not fresh, unknown -- and nothing "
              "re-scores it automatically.")

    # Calls, not dollars. There is no committed per-call price for scoring
    # anywhere in this repo, and a number invented here gets quoted back as
    # fact six weeks from now.
    unreachable = tot["rows"] - tot["reachable"]
    print(f"\n  WHAT RE-SCORING WOULD COST, IN LLM CALLS")
    print(f"    {tot['reachable']} call(s) to re-score every reachable row.")
    # The overstatement is measured against the real bill, not against the
    # inflated one: quoting 1293 when 1018 is payable is 27% too high, not
    # 21%. Dividing by the total is the flattering arithmetic.
    over = (round(100.0 * unreachable / tot["reachable"])
            if tot["reachable"] else 0)
    print(f"    {unreachable} row(s) are NOT reachable via "
          f"score.select_shortlist -- closed jobs, or never above "
          f"MATCH_FLOOR ({schema.MATCH_FLOOR}) into {schema.MATCHES_TABLE}. "
          f"No flag routed through that path can reach them. Quoting the "
          f"{tot['rows']}-row total as the bill overstates it by {over}%.")

    tombs = conn.execute(
        f"SELECT scoring_model, count(*) FROM {schema.SCORES_TABLE} "
        f"WHERE scoring_model LIKE %(t)s GROUP BY scoring_model "
        f"ORDER BY count(*) DESC", {"t": TOMBSTONE_LIKE}).fetchall()
    if tombs:
        # Broken out because it is the cheap bucket: retrying the failures is
        # a different, much smaller decision than re-scoring the corpus, and
        # some of these failed under a model that is not the production pin.
        print(f"\n  TOMBSTONES ({tot['tombstones']} row(s), by failing model)")
        for model, n in tombs:
            print(f"    {n:>6}  {model}")
        print(f"    Retrying these is {tot['tombstones']} call(s) and is a "
              f"separate decision from the {tot['reachable']} above.")

    span = conn.execute(
        f"SELECT min(scored_at), max(scored_at) FROM {schema.SCORES_TABLE}"
    ).fetchone()
    if span and span[0]:
        print(f"\n  Stored scores span {span[0]} -> {span[1]}. The corpus "
              f"straddles the build_prompt change in e1cdf7b, which is why "
              f"prompt_version cannot be inferred -- see the docstring.")


def main():
    p = argparse.ArgumentParser(
        description="Add job_scores' four version columns and report the "
                    "unversioned corpus (read-only by default). Backfills "
                    "nothing, ever -- the census IS the deliverable.")
    p.add_argument("--apply", action="store_true",
                   help="add the columns if absent. No row is written.")
    args = p.parse_args()

    conn = dbconn.connect_or_exit("migrate-score-versions",
                                  schema=schema.SCHEMA)

    present = dbconn.existing_columns(conn, schema.SCORES_TABLE)
    missing = [c for c, _ in NEW_COLUMNS if c not in present]
    print(f"migrate-score-versions: columns missing: "
          f"{missing if missing else 'none'}")

    if args.apply:
        added = dbconn.add_missing_columns(conn, schema.SCORES_TABLE,
                                           NEW_COLUMNS)
        print(f"  added: {added if added else 'nothing (already present)'}")
        missing = [c for c, _ in NEW_COLUMNS
                   if c not in dbconn.existing_columns(conn,
                                                       schema.SCORES_TABLE)]

    _report(conn, not missing, missing)
    conn.close()

    if args.apply:
        print(f"\nmigrate-score-versions: schema only. No job_scores row was "
              f"read into an UPDATE and none was written. Re-scoring is "
              f"score.py --rescore-unversioned with an explicit --limit, and "
              f"it is an operator's call, not a migration's.")
    else:
        print("\nDRY RUN -- nothing written. Re-run with --apply to add the "
              "columns (that is all --apply does).")


if __name__ == "__main__":
    main()

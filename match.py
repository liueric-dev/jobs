#!/usr/bin/env python3
"""
Rank every posting for every profile. No LLM, no network, no marginal cost.

WHAT THIS REPLACED
    score.py used to answer "how good is this job for this person" with an
    LLM call per (job, profile). That is the only part of the old pipeline
    that scaled with BOTH corpus size and user count, and it is the reason a
    new profile could not see a ranked list for about four hours.

    Once extract.py has turned a posting into structured facts, the same
    question is arithmetic: compare the facts against the profile's declared
    criteria and add up the deltas. It costs nothing, it runs over the whole
    corpus in seconds, and -- unlike an LLM's answer -- it can explain itself
    and be tuned against evidence.

THIS IS WHAT RANKS. job_scores DOES NOT.
    match_score decides which postings a user sees and in what order.
    job_scores.fit_score annotates the handful that get a narrative. Sorting
    by fit_score would put an LLM call back on the critical path for every
    job a user might see, which is the exact property this design removes.
    See the SCORING IS TWO TIERS note in schema.py.

EVERY DELTA IS RECORDED
    match_reasons stores the rule name and points for each contribution, so
    "why is this ranked 8th" is answerable from the row, and tuning a weight
    is an informed edit rather than a guess. tools/calibrate-match.py reads
    these when a rules score disagrees with the LLM's.

INCREMENTAL BY VERSION, NOT BY TIMESTAMP
    A row is stale when its facts_version or criteria_version no longer
    matches. That makes the two things that should trigger a recompute --
    re-extracting a job, editing a profile's weights -- the only things that
    do. A timestamp comparison would also fire on unrelated writes, and
    "recompute everything nightly" would waste the property that makes this
    cheap enough to run on every profile.

USAGE
    python3 match.py                 # only stale/missing rows
    python3 match.py --profile tech  # one profile
    python3 match.py --rebuild       # recompute everything, ignore versions
    python3 match.py --dry-run       # report, write nothing
"""

import argparse
import json
import sys

import llm
import profiles
import relevance
import schema
from pipelib import dbconn
from pipelib.timeparse import utc_now_str

#: A delta this negative disqualifies outright rather than being summed. Using
#: a magnitude rather than a separate config key means "never show me research
#: roles" is expressed the same way as every other weight -- one number, in
#: the same units -- instead of as a second parallel mechanism.
HARD_EXCLUDE_AT = -100

#: Ordered worst-to-best. Distance along this scale is what
#: seniority.penalty_per_level multiplies, so a staff role is penalised more
#: than a senior one without the config having to enumerate every pair.
SENIORITY_ORDER = ("intern", "new_grad", "junior", "mid", "senior", "staff",
                   "principal", "director", "exec")


def _clamp(n, lo=0, hi=100):
    return max(lo, min(hi, n))


def score_job(facts, criteria):
    """(match_score, reasons) for one posting against one profile's criteria.

    Pure: no database, no clock, no config lookup. Everything it needs is in
    its two arguments, which is what makes it unit-testable against
    hand-written facts and what lets calibrate-match.py sweep weights without
    touching the pipeline.

    `facts` is a job_facts row plus the two location booleans that already
    live on jobs.jobs -- pipelib.text computes those at ingest for free, so
    re-deriving them from an LLM would be paying for something we have.
    """
    reasons = []
    total = criteria.get("base", 0)
    reasons.append({"rule": "base", "delta": total})

    def add(rule, delta):
        nonlocal total
        if delta:
            total += delta
            reasons.append({"rule": rule, "delta": delta})
        return delta <= HARD_EXCLUDE_AT

    # -- seniority ----------------------------------------------------------
    sen_cfg = criteria.get("seniority") or {}
    level = facts.get("seniority_level")
    if level in (sen_cfg.get("hard_exclude") or ()):
        add(f"seniority:{level}:excluded", HARD_EXCLUDE_AT)
        return 0, reasons
    if level is None:
        add("seniority:unknown", sen_cfg.get("unknown_penalty", 0))
    elif level in (sen_cfg.get("target") or ()):
        pass  # on target: no delta, and no reason -- silence is the signal
    else:
        tolerate = sen_cfg.get("tolerate") or {}
        if level in tolerate:
            add(f"seniority:{level}", tolerate[level])
        else:
            # Not named anywhere: fall back to distance from the nearest
            # target level so an unlisted level is never silently free.
            targets = [SENIORITY_ORDER.index(t)
                       for t in (sen_cfg.get("target") or ())
                       if t in SENIORITY_ORDER]
            if targets and level in SENIORITY_ORDER:
                gap = min(abs(SENIORITY_ORDER.index(level) - t) for t in targets)
                add(f"seniority:{level}:{gap}_levels_off",
                    -gap * sen_cfg.get("penalty_per_level", 0))

    # -- years of experience ------------------------------------------------
    yr_cfg = criteria.get("years_experience") or {}
    required = facts.get("years_experience_min")
    ceiling = yr_cfg.get("max_required")
    if required is not None and ceiling is not None and required > ceiling:
        over = required - ceiling
        penalty = min(over * yr_cfg.get("over_penalty_per_year", 0),
                      yr_cfg.get("over_penalty_cap", 10 ** 6))
        add(f"years:{required}_wanted_vs_{ceiling}", -penalty)

    # -- archetype ----------------------------------------------------------
    archetype = facts.get("role_archetype")
    arch_cfg = criteria.get("archetypes") or {}
    if archetype in arch_cfg:
        if add(f"archetype:{archetype}", arch_cfg[archetype]):
            return 0, reasons

    # -- AI involvement -----------------------------------------------------
    ai_cfg = criteria.get("ai_involvement") or {}
    involvement = facts.get("ai_involvement")
    if involvement in ai_cfg:
        if add(f"ai:{involvement}", ai_cfg[involvement]):
            return 0, reasons

    # -- tech stack ---------------------------------------------------------
    # Substring rather than equality: postings write "node.js", "Node", and
    # "nodejs" for one thing, and the alternative is a synonym table nobody
    # maintains. Capped, so breadth of stack is not itself a signal.
    tech_cfg = criteria.get("tech") or {}
    boosts = tech_cfg.get("boost") or {}
    stack = facts.get("tech_stack") or []
    earned = 0
    for term, delta in boosts.items():
        if any(term in item for item in stack):
            earned += delta
    if earned:
        add("tech", min(earned, tech_cfg.get("cap", 10 ** 6)))

    # -- location -----------------------------------------------------------
    # Reads the booleans already on jobs.jobs, falling back to the extracted
    # remote_policy only to distinguish "onsite somewhere else" (a real no)
    # from "we could not classify this" (a data gap, penalised less).
    loc_cfg = criteria.get("location") or {}
    if not (loc_cfg.get("accept_nyc") and facts.get("location_is_nyc")) and \
       not (loc_cfg.get("accept_remote") and facts.get("location_is_remote")):
        if facts.get("remote_policy") == "onsite":
            add("location:onsite_elsewhere",
                loc_cfg.get("onsite_elsewhere_penalty", 0))
        else:
            add("location:unmatched", loc_cfg.get("neither_penalty", 0))

    # -- boolean flags ------------------------------------------------------
    for flag, delta in (criteria.get("flags") or {}).items():
        if facts.get(flag):
            if add(f"flag:{flag}", delta):
                return 0, reasons

    return _clamp(round(total)), reasons


_SELECT_FACTS = f"""
    SELECT f.job_id, f.facts_version, f.seniority_level,
           f.years_experience_min, f.role_archetype, f.tech_stack,
           f.ai_involvement, f.ml_research_required, f.advanced_degree_required,
           f.customer_facing, f.remote_policy, f.gap_friendly_language,
           j.location_is_nyc, j.location_is_remote
    FROM {schema.FACTS_TABLE} f
    JOIN {schema.TABLE} j ON j.id = f.job_id
    WHERE j.status = %(status)s
      AND f.extraction_model NOT LIKE %(failed)s
      AND {{union}}
"""


def load_facts(conn, cfgs):
    """Every usable extracted posting, as plain dicts.

    Loaded whole rather than streamed: 11k rows is a few MB, and holding them
    lets every profile be scored in one pass over the data instead of one
    query per profile. The cross product is computed in Python precisely
    because the arithmetic is trivial and the round trips are not.

    Tombstones are excluded here rather than in the caller -- a FAILED row has
    NULL in every fact column and would otherwise be scored as though the
    posting genuinely had no seniority, no archetype and no stack.

    THE RELEVANCE UNION IS APPLIED HERE, NOT ONLY IN extract.py
        Facts outlive the config that produced them. A posting extracted last
        week keeps its job_facts row forever, so filtering only at extraction
        time means a row that config later rejects still gets scored, still
        clears MATCH_FLOOR, and still sits at the top of the ranking.

        That was not hypothetical: 113 Google Jobs rows naming a relist site as
        the employer had already been extracted, and 19 of them held
        match_score >= 90 -- one at match 99 against an LLM fit of 15. Adding
        company_exclude to config/relevance.json demoted them to tier 3 for
        future extraction and changed nothing about the ranking until this
        filter existed.

        The union (not one profile's config) because facts are shared: a
        posting one profile rejects may be exactly what another wants, and
        per-profile precision is what the criteria weights are for.
    """
    union, union_params = relevance.union_sql(cfgs, table_alias="j")
    rows = conn.execute(_SELECT_FACTS.format(union=union),
                        {"status": schema.STATUS_OPEN,
                         "failed": f"{llm.FAILED_PREFIX}%",
                         **union_params}).fetchall()
    cols = ("job_id", "facts_version", "seniority_level",
            "years_experience_min", "role_archetype", "tech_stack",
            "ai_involvement", "ml_research_required",
            "advanced_degree_required", "customer_facing", "remote_policy",
            "gap_friendly_language", "location_is_nyc", "location_is_remote")
    out = []
    for r in rows:
        d = dict(zip(cols, r))
        try:
            d["tech_stack"] = json.loads(d["tech_stack"] or "[]")
        except (TypeError, json.JSONDecodeError):
            d["tech_stack"] = []
        out.append(d)
    return out


def existing_versions(conn, profile):
    """job_id -> (facts_version, criteria_version) already computed."""
    rows = conn.execute(
        f"SELECT job_id, facts_version, criteria_version "
        f"FROM {schema.MATCHES_TABLE} WHERE profile = %s", (profile,)).fetchall()
    return {r[0]: (r[1], r[2]) for r in rows}


def prune_orphans(conn, profile, facts, *, dry_run=False):
    """Drop match rows for postings that are no longer scoreable at all.

    Distinct from the demotion path inside match_profile(), which only fires
    for a job still present in `facts` whose score fell below MATCH_FLOOR. A
    job that leaves `facts` entirely -- closed upstream, tombstoned, or newly
    excluded by config/relevance.json -- never enters that loop, so without
    this its stale row survives every subsequent run and keeps being shown.

    Deliberately keyed on the loaded fact set rather than on a fresh query, so
    "what match.py just considered" and "what match.py keeps" cannot disagree.
    """
    keep = [f["job_id"] for f in facts]
    if dry_run:
        return conn.execute(
            f"SELECT count(*) FROM {schema.MATCHES_TABLE} "
            f"WHERE profile = %s AND NOT (job_id = ANY(%s))",
            (profile.profile, keep)).fetchone()[0]
    n = conn.execute(
        f"DELETE FROM {schema.MATCHES_TABLE} "
        f"WHERE profile = %s AND NOT (job_id = ANY(%s))",
        (profile.profile, keep)).rowcount
    conn.commit()
    return n


def match_profile(conn, profile, facts, *, rebuild=False, dry_run=False):
    """Recompute one profile's matches. Returns (written, deleted, skipped)."""
    seen = {} if rebuild else existing_versions(conn, profile.profile)
    now = utc_now_str()

    to_write, to_delete, skipped = [], [], 0
    for f in facts:
        current = (f["facts_version"], profile.criteria_version)
        if seen.get(f["job_id"]) == current:
            skipped += 1
            continue
        score, reasons = score_job(f, profile.criteria)
        if score >= schema.MATCH_FLOOR:
            to_write.append((f["job_id"], profile.profile, score,
                             json.dumps(reasons), f["facts_version"],
                             profile.criteria_version, now))
        elif f["job_id"] in seen:
            # It used to clear the floor and no longer does -- a weight edit
            # can demote a job, and leaving the old row would keep showing it.
            to_delete.append(f["job_id"])

    if dry_run:
        return len(to_write), len(to_delete), skipped

    if to_write:
        conn.cursor().executemany(
            f"""
            INSERT INTO {schema.MATCHES_TABLE}
                (job_id, profile, match_score, match_reasons,
                 facts_version, criteria_version, matched_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (job_id, profile) DO UPDATE SET
                match_score=EXCLUDED.match_score,
                match_reasons=EXCLUDED.match_reasons,
                facts_version=EXCLUDED.facts_version,
                criteria_version=EXCLUDED.criteria_version,
                matched_at=EXCLUDED.matched_at
            """, to_write)
    if to_delete:
        conn.execute(
            f"DELETE FROM {schema.MATCHES_TABLE} "
            f"WHERE profile = %s AND job_id = ANY(%s)",
            (profile.profile, to_delete))
    conn.commit()
    return len(to_write), len(to_delete), skipped


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--profile", help="only this profile (default: all active)")
    p.add_argument("--rebuild", action="store_true",
                   help="recompute every row, ignoring version bookkeeping")
    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args()

    conn = dbconn.connect_or_exit("job-match", schema=schema.SCHEMA)
    schema.ensure_schema(conn)

    if args.profile:
        one = profiles.load_one(conn, args.profile)
        if not one:
            print(f"job-match FAILED: no profile named {args.profile!r}")
            sys.exit(1)
        active = [one]
    else:
        active = profiles.load_active(conn)
    if not active:
        print("job-match: no active profiles.")
        conn.close()
        return

    cfgs = [relevance.for_profile(p) for p in active]
    facts = load_facts(conn, cfgs)
    if not facts:
        print("job-match: no extracted facts yet -- run extract.py first.")
        conn.close()
        return

    parts = []
    for prof in active:
        written, deleted, skipped = match_profile(
            conn, prof, facts, rebuild=args.rebuild, dry_run=args.dry_run)
        orphaned = prune_orphans(conn, prof, facts, dry_run=args.dry_run)
        parts.append(f"{prof.profile}: {written} matched"
                     + (f", {deleted} demoted" if deleted else "")
                     + (f", {orphaned} orphaned" if orphaned else "")
                     + (f", {skipped} current" if skipped else ""))
    print(f"job-match{' [dry run]' if args.dry_run else ''}: "
          f"{len(facts)} facts x {len(active)} profile(s) -- "
          + "; ".join(parts) + f", floor={schema.MATCH_FLOOR}")
    conn.close()


if __name__ == "__main__":
    main()

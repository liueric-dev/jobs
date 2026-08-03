#!/usr/bin/env python3
"""
Create the `pursuit` profile: the Pursuit AI-Native cohort's relevance gate,
INACTIVE.

WHAT THIS WRITES, AND WHAT IT DELIBERATELY DOES NOT
    relevance_json  REAL. The description-first, conjunctive cohort gate that
                    task 10 measured -- see
                    `git show refactor-freeze-2026-08-02:docs/pursuit-description-gate.md`
                    for the numbers and the hand-check behind every list. The
                    gate itself now lives in config/pursuit-relevance.json;
                    COHORT_RELEVANCE below is loaded from it.
    persona_json    PLACEHOLDER, and labelled as one in its own text.
    criteria_json   PLACEHOLDER: base only, no archetypes, no flags, no tech
                    boosts.

    Task 13 owns the cohort's real persona and weights, and it is blocked on
    product judgement about what the cohort is actually optimising for -- how
    an AI-adjacent operations role at a non-tech NYC employer should rank
    against a product internship at an AI lab, which of the four archetypes
    (if any) survive retargeting, whether "entry-level" is a boost or a hard
    filter. Guessing those numbers here would be worse than leaving them
    empty, because a wrong weight looks exactly like a right one in
    job_matches and nothing downstream would flag it. They are absent on
    purpose. Do not "fill them in" without task 13.

active=False IS THE SAFETY MECHANISM, NOT A CONVENIENCE
    profiles.load_active (profiles.py:94-106) filters on `active`, and it is
    the only way extract.py and match.py ever learn that a profile exists.
    relevance.union_sql (relevance.py:307) is built from exactly that list, so
    an inactive profile contributes no clause to the extraction gate.

    The consequence is the point: this migration provably cannot move
    production extraction volume. The cohort gate admits 876 rows the author's
    profiles do not, and none of them become eligible for an LLM call until a
    human runs `python3 -c "..." profiles.set_active(conn, 'pursuit', True)`
    or an equivalent, having first read the projected volume in task 12.
    Creating the row and activating it are two decisions; this script makes
    only the first.

WHY A SCRIPT AND NOT ensure_schema()
    Same reasoning as migrate_profiles.py: this writes rows, not structure,
    and the profile name it writes decides which job_scores and job_matches
    rows the pipeline will consider its own. Dry run is the default.

USAGE
    python3 migrations/migrate_pursuit_profile.py            # report, change nothing
    python3 migrations/migrate_pursuit_profile.py --apply    # create it, inactive
    python3 migrations/migrate_pursuit_profile.py --apply --active   # ... and turn it on

    --active is separated from --apply so that "create the row" and "start
    spending LLM calls on it" cannot be the same keystroke. It exists for the
    human who has read task 12's projection, not for a re-run.

IDEMPOTENT: re-running refreshes relevance_json and leaves criteria_version
alone (profiles.upsert only bumps when asked). Re-running WITHOUT --active
after someone has activated the profile will deactivate it again -- that is
the safe direction, but it is a real effect, so it is reported before it
happens.

TASK 13 HAS LANDED, WHICH CHANGES WHAT RE-RUNNING THIS COSTS
    The two stand-ins below are no longer the profile's contents.
    config/pursuit-criteria.json and config/pursuit-persona.json are, imported
    by migrations/migrate_profiles.py. So a re-run of THIS script -- the
    obvious thing to do to refresh the relevance gate, which it is still the
    owner of -- would overwrite real weights and real prose with the stand-ins
    and leave the profile ranking uniformly again, at a criteria_version the
    matcher considers current. Nothing downstream would notice: job_matches
    would still be full, still look fresh, and every score would be `base`.

    So it now REFUSES rather than doing that. --force-placeholders is the way
    past, and wanting it is almost always a sign that migrate_profiles.py is
    the script you actually want. To refresh only the gate, use:

        python3 migrations/migrate_profiles.py --apply \\
            --profile pursuit \\
            --persona-file config/pursuit-persona.json \\
            --criteria-file config/pursuit-criteria.json \\
            --relevance-file config/pursuit-relevance.json

    All three file flags are load-bearing. criteria_json and persona_json are
    overwritten WHOLESALE on every run (migrate_profiles.py:124-128), and
    --persona-file defaults to config/persona.json -- the AUTHOR's tech
    persona. Omitting them writes the wrong profile's prose into `pursuit`
    while looking like a gate refresh. No --bump: relevance gates extraction,
    not scoring inputs, so criteria_version must not move.

    Since the gate moved to config/pursuit-relevance.json, that command is the
    ONLY write path for it. This script is the historical owner and no longer
    a working one.
"""

import argparse
import json
import os
import sys

# migrations/ sits one level below the pipeline modules it imports (schema,
# profiles, ...). Python puts THIS file's directory on sys.path, not its
# parent, so the parent is added by hand. That same insert is what reaches
# lib/ -- there is nothing to install.
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _REPO_ROOT)

import profiles  # noqa: E402
import relevance  # noqa: E402
import schema  # noqa: E402
from lib import dbconn  # noqa: E402

PROFILE = "pursuit"

# ---------------------------------------------------------------------------
# The gate. Every list is measured; `git show refactor-freeze-2026-08-02:docs/pursuit-description-gate.md`
# records the method, the date and the hand-check behind it.
#
# IT LIVES IN config/pursuit-relevance.json, NOT HERE. It was a literal in
# this file until 2026-07-29, which made a migration script that REFUSES TO
# RUN (see the refusal in main()) the source of truth for a gate three other
# things read. Every sibling is already a file -- config/relevance.json,
# config/pursuit-criteria.json, config/pursuit-persona.json -- and
# migrate_profiles.py --relevance-file had nothing to point at.
#
# The move changed no behaviour, and that was checked rather than assumed:
# the dict loaded from the file was equal to the stored profiles.relevance_json
# key for key, and relevance.tier_sql compiled byte-identical SQL and params
# from both.
#
# tools/mock-acceptance.py reads THE SAME FILE. It used to importlib this
# module for the dict. If the gate ever moves again, move that with it -- the
# harness would otherwise measure one gate while the pipeline runs another and
# report "no change", which reads as the fix having done nothing.
# ---------------------------------------------------------------------------

GATE_FILE = os.path.join(_REPO_ROOT, "config", "pursuit-relevance.json")


def load_gate(path=GATE_FILE):
    """The cohort gate, from its file.

    Deliberately NOT comment-stripped. relevance.load() drops the _-prefixed
    keys at read time (relevance.py:88-97), so the documentation survives into
    profiles.relevance_json, where the next person to read the gate will find
    it. migrate_profiles.py:130-135 records why that asymmetry with criteria
    is on purpose.
    """
    with open(path) as f:
        return json.load(f)


COHORT_RELEVANCE = load_gate()

# ---------------------------------------------------------------------------
# Stand-ins. TASK 13 HAS REPLACED BOTH, in config/pursuit-criteria.json and
# config/pursuit-persona.json. They are kept here because this script must
# still be able to create the profile from nothing -- profiles.validate
# rejects a persona missing any of its four required keys, so creating the row
# needs something in them -- and because is_placeholder() below reads them to
# decide whether a re-run would be destructive.
# ---------------------------------------------------------------------------

PLACEHOLDER_PERSONA = {
    "_placeholder":
        "PLACEHOLDER, written by migrations/migrate_pursuit_profile.py (task "
        "10) purely to satisfy profiles.validate. This is NOT a description of "
        "the Pursuit cohort. Task 13 writes the real one. Nothing reads this "
        "except the narrative prompt, and the profile is inactive, so nothing "
        "reads it at all today.",
    "profile": PROFILE,
    "display_name": "Pursuit AI-Native cohort (placeholder)",
    "background_summary":
        "PLACEHOLDER -- task 13 owns this. Pursuit AI-Native Builders: roughly "
        "30 people, entry-level, seeking AI-adjacent roles across all "
        "industries in New York City. No background prose has been written "
        "yet.",
    "strengths": [
        "PLACEHOLDER -- task 13 owns this. Do not score against this list.",
    ],
    "honest_gaps": [
        "PLACEHOLDER -- task 13 owns this. Do not score against this list.",
    ],
    "scoring_instructions":
        "PLACEHOLDER -- task 13 owns this. This profile is inactive and must "
        "not be activated until a real persona replaces this text; an LLM "
        "asked to score against a placeholder will produce confident, "
        "meaningless narratives.",
}

PLACEHOLDER_CRITERIA = {
    "_placeholder":
        "PLACEHOLDER, written by migrations/migrate_pursuit_profile.py (task "
        "10). `base` only. archetypes, flags and tech.boost are EMPTY ON "
        "PURPOSE: every posting this profile matches scores exactly `base`, so "
        "the ranking is uniform and visibly uninformative rather than "
        "plausibly wrong. Task 13 owns the real weights and is blocked on "
        "cohort product judgement. Filling these in from the `tech` profile's "
        "numbers would be worse than leaving them empty -- those weights "
        "encode one software engineer's positioning and would rank the cohort "
        "against a persona it does not share.",
    "base": 50,
    "archetypes": {},
    "flags": {},
    "tech": {"boost": {}},
}


def is_placeholder(profile):
    """True if this stored profile still holds the stand-ins above.

    Keyed on the CRITERIA rather than on a marker string, because the criteria
    are what ranking depends on and because a marker is the kind of thing an
    editor tidies away. `archetypes` empty is the specific property the
    stand-in has and a real profile cannot: task 13's file prices all 26
    values of extract.ARCHETYPE, and a criteria_json with no archetypes at all
    scores every posting at `base` -- which is what PLACEHOLDER_CRITERIA's own
    comment says it is for.
    """
    return not (profile.criteria or {}).get("archetypes")


def main():
    p = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--apply", action="store_true",
                   help="write the profile (default is a dry run)")
    p.add_argument("--force-placeholders", action="store_true",
                   help="overwrite REAL criteria and persona with the "
                        "stand-ins in this file. Task 13 landed the real "
                        "ones; this throws them away.")
    p.add_argument("--active", action="store_true",
                   help="create it ACTIVE -- this starts spending extraction "
                        "budget on it. Read task 12's projection first.")
    p.add_argument("--profile", default=PROFILE,
                   help=f"profile name (default: {PROFILE})")
    p.add_argument("--budget", type=int, default=0,
                   help="daily_narrative_budget (default 0 -- the criteria are "
                        "placeholders, so a narrative would be meaningless)")
    args = p.parse_args()

    try:
        profiles.validate(PLACEHOLDER_PERSONA, PLACEHOLDER_CRITERIA,
                          COHORT_RELEVANCE)
    except ValueError as e:
        print(f"migrate-pursuit-profile FAILED: {e}")
        sys.exit(1)

    # Compile the gate before touching the database. tier_sql is where a
    # malformed location column or a mixed include list raises, and a config
    # that cannot compile must not reach a row.
    cfg = relevance.load(cfg=COHORT_RELEVANCE)
    _, params = relevance.tier_sql(cfg)

    conn = dbconn.connect_or_exit("migrate-pursuit-profile",
                                  schema=schema.SCHEMA)
    schema.ensure_schema(conn)

    existing = profiles.load_one(conn, args.profile)
    scored = conn.execute(
        f"SELECT count(*) FROM {schema.SCORES_TABLE} WHERE profile = %s",
        (args.profile,)).fetchone()[0]
    matched = conn.execute(
        f"SELECT count(*) FROM {schema.MATCHES_TABLE} WHERE profile = %s",
        (args.profile,)).fetchone()[0]

    print("migrate-pursuit-profile:")
    print(f"  profile                 : {args.profile}"
          f"{' (exists)' if existing else ' (new)'}")
    print(f"  active                  : {args.active}"
          f"{'' if args.active else '   <-- invisible to extract.py and match.py'}")
    print(f"  persona / criteria      : "
          + ("the stand-ins in this file (task 13's real ones live in "
             "config/pursuit-*.json)" if not existing or is_placeholder(existing)
             else f"STORED ARE REAL -- "
                  f"{len(existing.criteria.get('archetypes', {}))} archetypes "
                  f"priced; see the refusal below"))
    print(f"  relevance patterns      : "
          f"{sum(len(g) for g in COHORT_RELEVANCE['title_include'])} include, "
          f"{len(COHORT_RELEVANCE['title_exclude'])} title_exclude, "
          f"{len(COHORT_RELEVANCE['platform_exclude'])} platform_exclude")
    print(f"  bound regex params      : {', '.join(sorted(params))}")
    print(f"  existing job_scores     : {scored}")
    print(f"  existing job_matches    : {matched}")

    if existing and existing.active and not args.active:
        print("\n  WARNING: this profile is currently ACTIVE and re-running "
              "without --active will deactivate it.\n"
              "  That is the safe direction, but it will stop extract.py "
              "considering its rows. Pass --active to keep it on.")

    if existing and not is_placeholder(existing) and not args.force_placeholders:
        print(f"\nmigrate-pursuit-profile REFUSING: {args.profile!r} holds "
              f"REAL criteria -- {len(existing.criteria.get('archetypes', {}))} "
              f"archetypes priced, criteria_version "
              f"{existing.criteria_version}.\n"
              "  Task 13 wrote them (config/pursuit-criteria.json, "
              "config/pursuit-persona.json). Applying this script would "
              "replace them with the stand-ins in this file and leave the "
              "profile ranking every posting at `base`, at a criteria_version "
              "match.py considers current -- so job_matches would stay full "
              "and look fresh while meaning nothing.\n"
              "  To refresh the RELEVANCE GATE, which this script does own, "
              "run migrate_profiles.py: it preserves relevance_json when no "
              "--relevance-file is given, and takes one when there is a "
              "change to make.\n"
              "  --force-placeholders overrides this.")
        conn.close()
        sys.exit(1)

    if not args.apply:
        print("\ndry run -- nothing changed. Re-run with --apply.")
        conn.close()
        return

    profiles.upsert(conn, args.profile, PLACEHOLDER_PERSONA,
                    PLACEHOLDER_CRITERIA,
                    relevance_cfg=COHORT_RELEVANCE,
                    display_name=PLACEHOLDER_PERSONA["display_name"],
                    daily_narrative_budget=args.budget,
                    active=args.active)
    written = profiles.load_one(conn, args.profile)
    print(f"\n  written. active={written.active}, "
          f"criteria_version={written.criteria_version}, "
          f"budget={written.daily_narrative_budget}")
    if not written.active:
        print("  It contributes no clause to relevance.union_sql until "
              "someone activates it. Extraction volume is unchanged.")
    else:
        print("  ACTIVE. extract.py will now consider this profile's rows on "
              "its next run.")
    conn.close()


if __name__ == "__main__":
    main()

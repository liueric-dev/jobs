#!/usr/bin/env python3
"""
Seed jobs.profiles from the config files that used to be the source of truth.

WHAT THIS MOVES
    config/persona.json  -> profiles.persona_json   (prose, for the LLM)
    config/criteria.json -> profiles.criteria_json  (weights, for match.py)
    config/relevance.json stays shared and is NOT copied per profile: today
    every profile wants the same title filter, and duplicating it into each
    row would mean editing N places to retarget the pipeline. A profile that
    genuinely needs its own gets relevance_json set later; NULL means "use
    the shared default", which is the right default for almost everyone.

WHY A SCRIPT AND NOT ensure_schema()
    Same reasoning as migrate_scores.py and migrate_google_ids.py: this writes
    rows, not structure, and the profile name it writes decides which
    job_scores rows the pipeline will consider its own. Getting that wrong
    silently orphans 900 existing scores. Dry run is the default.

THE PROFILE NAME MATTERS
    It defaults to persona.json's own `profile` key ("tech"), which is exactly
    what schema.resolve_profile() has been returning all along -- so the 912
    job_scores rows already in the table belong to the profile this creates,
    and calibration can use them immediately. Passing --profile something-else
    starts an empty score set instead, which is occasionally what you want and
    never what you want by accident.

USAGE
    python3 migrate_profiles.py                     # report, change nothing
    python3 migrate_profiles.py --apply             # create/refresh
    python3 migrate_profiles.py --apply --bump      # ... and invalidate matches

    --bump increments criteria_version, which is what tells match.py to
    recompute this profile's rows. Use it whenever criteria.json changed;
    omitting it after a weight edit leaves stale match_scores that look
    current. That is the one genuinely wrong combination.

IDEMPOTENT: re-running without --bump refreshes the text and leaves
criteria_version alone, so match.py does no work.
"""

import argparse
import json
import os
import sys

import profiles
import schema
from lib import dbconn

CRITERIA_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                             "config", "criteria.json")


def strip_comments(cfg):
    """Drop the _-prefixed documentation keys, same convention as relevance.load()."""
    return {k: v for k, v in cfg.items() if not k.startswith("_")}


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--apply", action="store_true",
                   help="write the profile (default is a dry run)")
    p.add_argument("--bump", action="store_true",
                   help="increment criteria_version, invalidating job_matches")
    p.add_argument("--profile", default=None,
                   help="profile name (default: persona.json's own 'profile' key)")
    p.add_argument("--persona-file", default=None)
    p.add_argument("--criteria-file", default=CRITERIA_FILE)
    p.add_argument("--budget", type=int, default=20,
                   help="daily_narrative_budget (default 20)")
    args = p.parse_args()

    try:
        persona = profiles.load_persona_file(args.persona_file)
        with open(args.criteria_file) as f:
            criteria = strip_comments(json.load(f))
    except (OSError, json.JSONDecodeError) as e:
        print(f"migrate-profiles FAILED: could not read config: {e}")
        sys.exit(1)

    profile = args.profile or schema.resolve_profile(persona)

    try:
        profiles.validate(persona, criteria)
    except ValueError as e:
        print(f"migrate-profiles FAILED: {e}")
        sys.exit(1)

    conn = dbconn.connect_or_exit("migrate-profiles", schema=schema.SCHEMA)
    schema.ensure_schema(conn)

    existing = profiles.load_one(conn, profile)
    scored = conn.execute(
        f"SELECT count(*) FROM {schema.SCORES_TABLE} WHERE profile = %s",
        (profile,)).fetchone()[0]
    matched = conn.execute(
        f"SELECT count(*) FROM {schema.MATCHES_TABLE} WHERE profile = %s",
        (profile,)).fetchone()[0]

    print("migrate-profiles:")
    print(f"  profile                 : {profile}"
          f"{' (exists)' if existing else ' (new)'}")
    print(f"  persona keys            : {len(persona)} "
          f"({', '.join(sorted(k for k in persona if not k.startswith('_')))[:70]}...)")
    print(f"  criteria sections       : {', '.join(sorted(criteria))}")
    print(f"  existing job_scores     : {scored}")
    print(f"  existing job_matches    : {matched}")
    if existing:
        print(f"  criteria_version        : {existing.criteria_version}"
              f"{' -> ' + str(existing.criteria_version + 1) if args.bump else ' (unchanged)'}")
        if existing.criteria != criteria and not args.bump:
            print("\n  WARNING: criteria.json differs from the stored criteria and "
                  "--bump was not passed.\n"
                  "  match.py keys its rebuild on criteria_version, so the "
                  f"{matched} existing job_matches rows would keep scores "
                  "computed under the OLD weights while looking current.\n"
                  "  Re-run with --bump unless you know the difference is "
                  "cosmetic.")

    if not args.apply:
        print("\ndry run -- nothing changed. Re-run with --apply.")
        conn.close()
        return

    profiles.upsert(conn, profile, persona, criteria,
                    display_name=persona.get("display_name"),
                    daily_narrative_budget=args.budget,
                    bump_criteria=args.bump)
    written = profiles.load_one(conn, profile)
    print(f"\n  written. criteria_version={written.criteria_version}, "
          f"budget={written.daily_narrative_budget}, active={written.active}")
    if args.bump and matched:
        print(f"  {matched} job_matches rows are now stale -- "
              f"run match.py to recompute.")
    conn.close()


if __name__ == "__main__":
    main()

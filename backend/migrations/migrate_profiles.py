#!/usr/bin/env python3
"""
Seed jobs.profiles from the config files that used to be the source of truth.

WHAT THIS MOVES
    config/persona.json  -> profiles.persona_json   (prose, for the LLM)
    config/criteria.json -> profiles.criteria_json  (weights, for match.py)
    config/relevance.json stays shared and is NOT copied per profile: today
    most profiles want the same title filter, and duplicating it into each
    row would mean editing N places to retarget the pipeline. A profile that
    genuinely needs its own gets relevance_json set -- pass --relevance-file,
    or leave it alone and this script preserves whatever is already there.
    NULL means "use the shared default", which is right for almost everyone.

ABSENT MEANS PRESERVE, NOT RESET
    Three columns are NOT derived from the config files and therefore have no
    business being overwritten by a run that did not mention them:
    relevance_json, daily_narrative_budget and active. Every one of them was
    an unexploded charge before 2026-07-28 (task 13), because profiles.upsert
    writes all ten columns on every call and this script fed it defaults:

      relevance_json         upsert was called WITHOUT relevance_cfg, so the
                             ON CONFLICT branch wrote NULL. Running this
                             against `pursuit` would have erased the
                             description-first cohort gate task 10 measured
                             (migrations/migrate_pursuit_profile.py:126-365)
                             and silently widened it to the shared software
                             title filter.
      daily_narrative_budget --budget defaulted to 20 and was always passed,
                             so a run intended to change weights would have
                             turned on paid narrative LLM calls for a profile
                             deliberately held at 0.
      active                 upsert defaults active=True and this script never
                             passed it, so refreshing `tech` -- deactivated by
                             task 12 precisely to stop re-extracting its 5,317
                             eligible rows at every FACTS_VERSION bump -- would
                             have switched it back on.

    All three are now preserve-on-absent for an existing profile, and keep
    their documented defaults (NULL / 20 / active) for a new one. Say
    --relevance-file, --budget or --active/--inactive to change them; the dry
    run prints the resolved value beside the stored one either way.

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
    python3 migrations/migrate_profiles.py                     # report, change nothing
    python3 migrations/migrate_profiles.py --apply             # create/refresh
    python3 migrations/migrate_profiles.py --apply --bump      # ... and invalidate matches

    # the cohort profile (task 13). Its relevance_json, budget and active flag
    # are already correct in the table, so none of them is mentioned here:
    python3 migrations/migrate_profiles.py --apply --bump \
        --profile pursuit \
        --persona-file config/pursuit-persona.json \
        --criteria-file config/pursuit-criteria.json

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

# migrations/ sits one level below the pipeline modules it imports (schema,
# profiles, ...). Python puts THIS file's directory on sys.path, not its
# parent, so the parent is added by hand. That same insert is what reaches
# lib/ -- there is nothing to install.
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _REPO_ROOT)

import profiles  # noqa: E402
import schema  # noqa: E402
from lib import dbconn  # noqa: E402

# Resolved against the repo root, not this file's directory: config/ stayed at
# the root when the migrations moved down into migrations/.
CRITERIA_FILE = os.path.join(_REPO_ROOT, "config", "criteria.json")

#: What a NEW profile gets for the three preserve-on-absent columns. An
#: existing profile keeps whatever it already has instead -- see the
#: ABSENT MEANS PRESERVE note in the module docstring.
NEW_PROFILE_BUDGET = 20
NEW_PROFILE_ACTIVE = True
NEW_PROFILE_RELEVANCE = None


def strip_comments(cfg):
    """Drop the _-prefixed documentation keys, same convention as relevance.load()."""
    return {k: v for k, v in cfg.items() if not k.startswith("_")}


def resolve_preserved(existing, *, relevance_cfg=None, budget=None, active=None):
    """The three columns this script does not derive from the config files.

    Returns (relevance_cfg, budget, active), each being the flag's value when
    the caller passed one, the stored value when it did not and the profile
    exists, and the documented new-profile default otherwise.

    Split out from main() so it is testable without a database: every one of
    these three was a silent overwrite before task 13, and "absent means
    preserve" is the kind of property that is easy to assert and easy to
    regress in a refactor of an argument-parsing block nobody reads.

    NOTE the asymmetry with criteria_json and persona_json, which ARE
    overwritten wholesale on every run: those two have a file that is their
    source of truth, so a run necessarily has an opinion about them. These
    three do not, so a run that did not mention them has no opinion and must
    not express one.

    relevance_cfg is deliberately NOT comment-stripped. relevance.load()
    strips _-prefixed keys at read time (relevance.py:88-97), so the
    documentation survives into jobs.profiles.relevance_json where the next
    person to read the gate will find it -- which is what
    migrations/migrate_pursuit_profile.py already does with COHORT_RELEVANCE.
    criteria_json is stripped, because nothing strips it downstream.
    """
    if relevance_cfg is None:
        relevance_cfg = (existing.relevance if existing
                         else NEW_PROFILE_RELEVANCE)
    if budget is None:
        budget = (existing.daily_narrative_budget if existing
                  else NEW_PROFILE_BUDGET)
    if active is None:
        active = existing.active if existing else NEW_PROFILE_ACTIVE
    return relevance_cfg, budget, active


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
    p.add_argument("--relevance-file", default=None,
                   help="per-profile relevance_json. OMITTED PRESERVES what "
                        f"the profile already has (NULL, i.e. the shared "
                        f"config/relevance.json, for a new one) -- it does "
                        f"not erase it.")
    p.add_argument("--budget", type=int, default=None,
                   help="daily_narrative_budget. Omitted preserves the stored "
                        f"value ({NEW_PROFILE_BUDGET} for a new profile).")
    active = p.add_mutually_exclusive_group()
    active.add_argument("--active", dest="active", action="store_true",
                        default=None,
                        help="make the profile active. Omitted preserves the "
                             "stored value -- a refresh must not silently "
                             "reactivate a profile someone paused.")
    active.add_argument("--inactive", dest="active", action="store_false",
                        help="pause the profile: invisible to extract.py and "
                             "match.py.")
    args = p.parse_args()

    try:
        persona = profiles.load_persona_file(args.persona_file)
        with open(args.criteria_file) as f:
            criteria = strip_comments(json.load(f))
        relevance_arg = None
        if args.relevance_file:
            with open(args.relevance_file) as f:
                relevance_arg = json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        print(f"migrate-profiles FAILED: could not read config: {e}")
        sys.exit(1)

    profile = args.profile or schema.resolve_profile(persona)

    try:
        profiles.validate(persona, criteria, relevance_arg)
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

    relevance_cfg, budget, active = resolve_preserved(
        existing, relevance_cfg=relevance_arg, budget=args.budget,
        active=args.active)

    def shown(value, flag, given):
        """The resolved value AND where it came from. Omitting a flag is a
        decision here, so it has to be visible in the dry run rather than
        inferred from the absence of output."""
        if given is not None:
            source = f"from {flag}"
        else:
            source = "preserved" if existing else "new-profile default"
        return f"{value}   ({source})"

    print("migrate-profiles:")
    print(f"  profile                 : {profile}"
          f"{' (exists)' if existing else ' (new)'}")
    print(f"  persona keys            : {len(persona)} "
          f"({', '.join(sorted(k for k in persona if not k.startswith('_')))[:70]}...)")
    print(f"  criteria sections       : {', '.join(sorted(criteria))}")
    print("  relevance_json          : "
          + shown(f"{len(relevance_cfg)} keys" if relevance_cfg
                  else "NULL (shared config/relevance.json)",
                  "--relevance-file", relevance_arg))
    print("  daily_narrative_budget  : "
          + shown(budget, "--budget", args.budget))
    print("  active                  : "
          + shown(active, "--active/--inactive", args.active))
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
                    relevance_cfg=relevance_cfg,
                    display_name=persona.get("display_name"),
                    daily_narrative_budget=budget,
                    active=active,
                    bump_criteria=args.bump)
    written = profiles.load_one(conn, profile)
    print(f"\n  written. criteria_version={written.criteria_version}, "
          f"budget={written.daily_narrative_budget}, active={written.active}, "
          f"relevance_json="
          f"{'set' if written.relevance else 'NULL (shared default)'}")
    if args.bump and matched:
        print(f"  {matched} job_matches rows are now stale -- "
              f"run match.py to recompute.")
    conn.close()


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
Create the `pursuit` profile: the Pursuit AI-Native cohort's relevance gate,
INACTIVE.

WHAT THIS WRITES, AND WHAT IT DELIBERATELY DOES NOT
    relevance_json  REAL. The description-first, conjunctive cohort gate that
                    task 10 measured -- see docs/pursuit-description-gate.md
                    for the numbers and the hand-check behind every list in
                    COHORT_RELEVANCE below.
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

        python3 migrations/migrate_profiles.py --apply --bump \\
            --profile pursuit \\
            --persona-file config/pursuit-persona.json \\
            --criteria-file config/pursuit-criteria.json

    ...which preserves relevance_json, or pass it a --relevance-file.
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
# The gate. Every list below is measured; docs/pursuit-description-gate.md
# records the method, the date, and the hand-check.
# ---------------------------------------------------------------------------

#: AI-tool vocabulary. Task 05's regex (docs/pursuit-gate-volume.md:42) plus
#: three terms, see _ai_vocab_note.
AI_VOCAB = [
    "chatgpt",
    "claude",
    "copilot",
    "gemini",
    "\\yllm\\y",
    "large language model",
    "prompt engineer",
    "prompting",
    "generative ai",
    "\\ygen ai\\y",
    "automation",
    "workflow automation",
    "zapier",
    "\\yn8n\\y",
    "make\\.com",
    "ai tool",
    "ai-powered",
    "machine learning",
    "\\yai\\y",
    "ai-driven",
    "ai-enabled",
]

#: Entry-level signals. Task 05's list (docs/pursuit-gate-volume.md:48) plus
#: the intern family, see _entry_level_note.
ENTRY_LEVEL = [
    "\\yentry.?level\\y",
    "\\yjunior\\y",
    "\\yassociate\\y",
    "\\ycoordinator\\y",
    "\\yassistant\\y",
    "\\yspecialist\\y",
    "\\yanalyst\\y",
    "\\yno experience\\y",
    "\\ywill train\\y",
    "\\yapprentice\\y",
    "\\yintern(ship)?s?\\y",
]

COHORT_RELEVANCE = {
    "_comment":
        "Relevance gate for the Pursuit AI-Native cohort: entry-level, "
        "AI-adjacent, all industries, NYC. Lives on the profile rather than in "
        "config/relevance.json because the shared file is the AUTHOR's "
        "software-title gate and must keep working unchanged -- see that "
        "file's own _comment. relevance.union_sql gates both in one pass, so "
        "having two is free.",

    "_gate_shape_note":
        "The gate is CONJUNCTIVE and that is the whole design: a row must "
        "carry AI-tool vocabulary AND an entry-level signal, in the same "
        "field. Task 05 hand-checked the vocabulary ALONE at 6.7% precision "
        "over 2,975 rows -- 93% junk -- because every AI-adjacent employer "
        "(Pinterest, Brex, Notion, Anthropic, OpenAI) ships an AI blurb in the "
        "header of every requisition, so the vocabulary selects for the "
        "COMPANY being AI-ish, not the ROLE. A single-list gate on it is not "
        "worth extracting. The conjunction is expressed as the list-of-lists "
        "shape relevance._include_groups understands: one term from each "
        "group. Measured 2026-07-28: 876 rows eligible, hand-checked at 10.0% "
        "strict / 23.3% generous, n=30. Better than 6.7%, still mostly noise.",

    "_regex_dialect":
        "POSTGRES regexes (~*), not Python ones. Word boundary is \\y -- in "
        "Postgres \\b means BACKSPACE, so a \\b pattern silently matches "
        "nothing and quietly demotes everything it was meant to catch to tier "
        "3. Positive control, measured 2026-07-28 against description_text: "
        "\\yllm\\y -> 1,127 rows, \\bllm\\b -> 0 rows and no error. Also note "
        "make\\.com: the dot MUST stay escaped. Unescaped, make.com matches "
        "116 rows table-wide against 2, a 58x inflation, because it also "
        "catches 'make a common...' and 'makes com...'. Run "
        "tools/relevance-report.py --dead --profile pursuit after any edit.",

    "_ai_vocab_note":
        "Task 05's regex verbatim (docs/pursuit-gate-volume.md:42) plus "
        "\\yai\\y, ai-driven and ai-enabled. NOT lifted unchanged despite what "
        "the task file says: task 05's list has no bare \\yai\\y, so it misses "
        "3 of the 9 genuine tier-3 rows it itself identified, and the two "
        "hyphenated forms are how half the corpus writes it. The bare \\yai\\y "
        "is the expensive one -- it matches 9,273 of 11,824 descriptions on "
        "its own, and removing it takes the gate from 1,671 rows to 1,177 -- "
        "but it is load-bearing for recall and the entry-level conjunct is "
        "what makes it affordable. REJECTED: dropping 'automation', 'ai tool' "
        "and 'ai-powered', which task 05 measured as the junk generators (62% "
        "of its matches came from those three alone). Rejected because the "
        "conjunction already removes most of what they pulled in, and because "
        "'automation' is the single best word for the roles this cohort "
        "actually wants -- an ops job that runs Zapier flows says 'automation' "
        "and nothing else. REJECTED: adding 'agentic', 'rpa', 'no-code' and "
        "'low-code' -- not measured, so not added; add them only with a count "
        "beside them. KNOWN FALSE POSITIVES, kept anyway: 'gemini' matches "
        "Gemini the crypto exchange (26 of 90 tier-3 matches in task 05, and "
        "one landed in this task's own hand-check sample), and 'claude' "
        "matches the given name. Both are cheap to lose downstream and "
        "expensive to lose here.",

    "_entry_level_note":
        "Task 05's list (docs/pursuit-gate-volume.md:48) plus "
        "\\yintern(ship)?s?\\y, which it lacks -- an omission that dropped "
        "every internship and new-grad programme, and those are the most "
        "reliably entry-level postings in the corpus (both genuine rows in "
        "this task's hand-check are Databricks intern/new-grad requisitions). "
        "REJECTED: bare \\yintern -- it matches 'internal', which appears in "
        "most job descriptions. The trailing boundary is what makes the "
        "pattern safe. KNOWN WEAKNESS: \\yassociate\\y also matches 'Associate "
        "Director' and 'Associate General Counsel', and \\yanalyst\\y matches "
        "'Senior Marketing Data Analyst'. title_exclude's seniority block "
        "below is what catches those; the two lists are designed together.",

    "title_include": [AI_VOCAB, ENTRY_LEVEL],

    "_title_include_note":
        "Both groups against the title, so 'AI Operations Coordinator' clears "
        "the gate on its header alone. Worth only 7 rows beyond what "
        "description_include already admits (measured 2026-07-28), because job "
        "descriptions restate their own title 81% of the time -- but those 7 "
        "are the best rows in the set: 'FT/PT Remote AI Prompt Engineering & "
        "Evaluation - Will Train', 'Technical Specialist, Claude Code', 'AI "
        "Specialist, Treasury Finance Operations'. Cheap insurance, and it is "
        "also the only path for the 37 rows that have no description_text at "
        "all.",

    "description_include": [AI_VOCAB, ENTRY_LEVEL],

    "_description_include_note":
        "The reason this profile exists. The cohort's target roles say nothing "
        "about AI in the header and everything in the body -- Harvey's 'User "
        "Operations Specialist' asks for 'working fluency with AI tools (e.g. "
        "ChatGPT, Claude, Gemini); you use them, not just know of them' and "
        "sits at tier 3 under the shared config. relevance.tier_sql ORs this "
        "against title_include (relevance.py:223-226), so a body match carries a "
        "posting on its own. REJECTED: requiring the two signals in DIFFERENT "
        "fields (AI anywhere in title-or-body AND entry-level anywhere in "
        "title-or-body). It admits 132 more rows and a 30-row sample of that "
        "delta was ~100% junk -- 'Senior Oracle Procurement Specialist', "
        "'Associate General Counsel, Commercial', 'Global Filing Specialist, "
        "Tax' -- because it pairs an entry-level word in the title with "
        "company AI boilerplate in the body, which is precisely the failure "
        "mode task 05 documented. Co-location in one field is a weak proxy for "
        "'the AI vocabulary is about the work', but it is not no proxy.",

    "title_exclude": [
        "\\yaccount executive\\y",
        "sales development",
        "\\ysdr\\y",
        "\\ybdr\\y",
        "business development",
        "\\yrecruiter\\y",
        "\\yrecruiting\\y",
        "talent acquisition",
        "\\ypayroll\\y",
        "\\ybenefits\\y",
        "\\ycompensation\\y",
        "\\ytax\\y",
        "\\ycontroller\\y",
        "\\yaccounting\\y",
        "\\yauditor\\y",
        "\\ycompliance officer\\y",
        "\\yparalegal\\y",
        "\\ycounsel\\y",
        "\\yattorney\\y",
        "\\ytherapist\\y",
        "\\ynurse\\y",
        "\\yclinician\\y",
        "\\yphysician\\y",
        "\\ycustomer success\\y",
        "\\yexecutive assistant\\y",
        "\\yoffice manager\\y",
        "\\yfacilities\\y",
        "\\ywarehouse\\y",
        "\\ydriver\\y",
        "chief .* officer",
        "\\yvp,?\\y",
        "vice president",
        "\\ysenior\\y",
        "\\ysr\\.?\\y",
        "\\ystaff\\y",
        "\\yprincipal\\y",
        "\\ydirector\\y",
        "\\yhead of\\y",
    ],

    "_title_exclude_note":
        "config/relevance.json's list verbatim, plus a seniority block. The "
        "shared list is copied rather than referenced because relevance.load "
        "merges a profile's config over DISABLED, not over the file "
        "(relevance.py:88-89) -- deliberately, so a profile's behaviour never "
        "depends on a file it does not mention. The cost is that the two "
        "drift; check them against each other when either moves. The seniority "
        "block is NEW and is specific to this profile: the cohort is "
        "explicitly entry-level, and task 05 measured 59.5% of the AI-vocab "
        "population as senior/lead/director/VP-shaped. It removes 448 rows "
        "(1,324 -> 876, measured 2026-07-28). REJECTED: \\ymanager\\y (would "
        "remove 111 more, 876 -> 765) and \\ylead\\y (43 more, 876 -> 833). "
        "Both are genuinely ambiguous -- 'Manager, Customer Experience "
        "Specialist' is not entry-level but 'Lead Teacher' can be, and "
        "config/relevance.json's own _title_exclude_note argues at length that "
        "broad co-occurring words are the wrong thing to exclude. Three of the "
        "30 hand-checked rows were Manager titles, which is n=3 and not a "
        "reason to change a list. The numbers are recorded so task 13 can "
        "decide with them rather than re-derive them.",

    "company_exclude": [
        "\\yremote zest\\y",
        "\\yremote click\\y",
        "\\yv?mysmartpros\\y",
        "\\yvacancy global\\y",
        "\\ybrighthush\\y",
        "\\yjobgether\\y",
    ],

    "_company_exclude_note":
        "config/relevance.json's list verbatim, and for the same reason: these "
        "six are relist sites that Google Jobs reports AS the employer, so the "
        "real employer is unknown. This is a provenance judgement, not a role "
        "judgement, so it transfers to any profile unchanged. Their titles are "
        "keyword-stuffed in exactly the way an include regex rewards -- 19 "
        "reached match_score >= 90, one hit 99 against an LLM fit of 15 -- and "
        "the description-first gate makes them MORE dangerous, not less, "
        "because a stuffed body matches too. See that file's "
        "_company_exclude_scope_note for the eleven aggregators deliberately "
        "NOT listed here, and its _company_exclude_rejected_note for the "
        "SerpApi `via` heuristic that was measured and rejected.",

    "platform_exclude": [
        "^builtin$",
        "^weworkremotely$",
        "^hn_whoishiring$",
    ],

    "_platform_exclude_note":
        "The three tech-company sources. They stay configured for the author's "
        "profiles -- Built In and Hacker News Who Is Hiring are good sources "
        "of the software roles that gate wants -- and are dropped only here. "
        "Task 05 measured them at 157 of 2,975 AI-vocabulary rows (5.3%), and "
        "under this gate they contribute 116 of 1,664 before exclusion. "
        "Anchored ^...$ rather than \\y-bounded because these are exact values "
        "of the `platform` column, not words in prose. NOTE the value is "
        "`builtin`, not `builtin-nyc` as the task files write it; the live set "
        "is greenhouse, ashby, google_jobs, builtin, weworkremotely, "
        "hn_whoishiring, lever. REJECTED: also dropping `lever` -- it has 9 "
        "rows total and 0 reach this gate, so excluding it would be a "
        "statement about a source nobody has measured yet.",

    "description_exclude": [
        "reputed company",
    ],

    "_description_exclude_note":
        "config/relevance.json's list verbatim. Some relisters scrub the "
        "employer's name out of the body and substitute a placeholder, leaving "
        "text like 'reputed company is redefining IT operations for the modern "
        "reputed company'. A posting whose employer has been deleted cannot be "
        "applied to no matter how good the body looks. Keep this list tiny and "
        "literal: it scans description_text, and under a description-first "
        "gate a loose pattern here would bury thousands of legitimate rows "
        "rather than the hundreds it could bury before.",

    "location_columns": ["location_is_nyc", "location_is_remote"],

    "_location_note":
        "Any-of, and it decides tier 1 vs tier 2, not admission -- NULL "
        "(source could not tell) reads as tier 2 so an undetectable location "
        "never buries a good posting. The cohort is NYC, and 'remote' is kept "
        "beside it because a remote posting is reachable from NYC. 444 of the "
        "876 eligible rows (50.7%) are NYC-or-remote, measured 2026-07-28.",

    "max_tier_to_score": 2,

    "_max_tier_note":
        "2, matching config/relevance.json, and for the reason recorded in its "
        "_max_tier_exclusion_note and DECISIONS.md:300-330: tier 3 is where "
        "the exclusion lists SEND things. relevance.py:266-278 folds "
        "title_exclude, company_exclude, platform_exclude and "
        "description_exclude into the same row_ok predicate that the includes "
        "drive, and anything failing row_ok falls to tier 3 (relevance.py:297-299), "
        "while union_sql admits on tier <= max_tier (relevance.py:331). So 3 "
        "is an UNCONDITIONAL PASS -- it does not widen this gate, it removes "
        "it, along with all four exclusion lists at once. Do not raise it.",
}

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

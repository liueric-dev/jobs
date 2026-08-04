#!/usr/bin/env python3
"""
Run the real pipeline over 55 constructed postings and compare it to an answer
key.

WHAT THIS MEASURES THAT NOTHING ELSE IN THIS REPO CAN
    Every quality figure this codebase has -- task 05's 6.7%, task 10's 10.0%
    strict, task 13's 16-of-20 -- is PRECISION over rows the pipeline already
    chose to surface. None of them can see a posting the gate rejected,
    because a rejected posting never acquires facts, a match, a score or a
    label. Recall is unbounded from below by construction.

    A constructed corpus with an intended verdict per posting bounds it from
    the other side. Measurement (b) below is a confusion matrix of the gate's
    admission against the key's verdict, and its false-negative cell -- good
    postings the gate threw away -- is the number that does not exist today.

    The price of that is that these 55 postings are synthetic and 45 of them
    were written by a language model, which is why measurement (e) exists:
    if the 10 human-written postings score materially below the 45
    model-written ones then a model is finding a model's prose easier to read
    than a person's, and the headline number is inflated. That check is not
    decoration, and its result belongs in the same paragraph as any figure
    taken from here.

CONTAINMENT COMES FIRST, AND IT IS A REFUSAL RATHER THAN A WARNING
    This driver runs extract.py and score.py IN-PROCESS against a live
    Postgres, which is only safe because evals/scratchdb.scratch_schema()
    (scratchdb.py:122) has repointed the module global schema.SCHEMA at a
    throwaway schema first. If that patch is not in place, every write in
    here lands in `public` -- 11k real postings, real job_facts, real
    job_matches.

    So require_scratch_schema() checks schema.SCHEMA against scratchdb's own
    SCRATCH_NAME pattern (scratchdb.py:70) before any statement that writes,
    and raises. It is the same guard, in the same shape, as the one
    scratchdb.drop() applies before a DROP SCHEMA CASCADE, and for the same
    reason: `public` reaches these functions the moment somebody calls one
    outside the context manager.

IN-PROCESS, AND IT CANNOT BE SUBPROCESSES
    scratch_schema() works by assigning schema.SCHEMA (scratchdb.py:143). A
    `subprocess python3 extract.py` child re-imports schema and gets
    "public" -- it would extract the production corpus and bill for it. Only
    an in-process call sees the patch.

    extract.py's worker threads DO see it: extract_one_job() calls
    dbconn.connect(schema=schema.SCHEMA) at extract.py:1089, reading the
    global at call time inside the thread. score.py's workers do the same at
    score.py:978. Threads share the process's globals; processes do not.

TWO PROFILES, AND THE SECOND ONE IS THE WHOLE DESIGN
    `pursuit` is the real cohort profile: the relevance gate from
    migrations/migrate_pursuit_profile.py and the weights from
    config/pursuit-criteria.json.

    `mock_all` is a permissive gate that admits every row. It exists because
    extract._eligible_sql gates on the UNION of active profiles
    (extract.py:541-579, relevance.union_sql at relevance.py:307) and
    match.load_facts applies the union too, deliberately (match.py:290-337).
    So with both active, all 55 postings get extracted and all 55 get scored
    under `pursuit`'s weights -- while `pursuit`'s own tier, computed
    separately in step 4, records what the live gate WOULD have done.

    That separation is what makes the gate measurable independently of the
    weights. Gate the corpus with `pursuit` alone and a posting it rejects
    has no facts, so measurement (b) could report which postings were
    rejected and measurement (c) could never say whether rejecting them was
    right.

WHAT IT COSTS
    55 extraction calls (one pass each: "mock" is absent from
    config/extraction-policy.json's measured_agreement, so passes_for()
    returns default_passes = 1, extract.py:176-190) plus one narrative call
    per above-floor row, ~30. --dry-run does everything except those two
    steps and spends nothing.

USAGE
    python3 tools/mock-acceptance.py --dry-run
    python3 tools/mock-acceptance.py --no-narratives
    python3 tools/mock-acceptance.py --out data/mock-acceptance.json
    python3 tools/mock-acceptance.py --keep          # leave the schema behind
"""

import argparse
import json
import os
import sys
from collections import Counter

import psycopg

# tools/ sits one level below the pipeline modules it imports (schema,
# relevance, match, ...). Python puts THIS file's directory on sys.path, not
# its parent, so the parent is added by hand. That same insert is what reaches
# lib/ and evals/ -- there is nothing to install.
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _REPO_ROOT)

import extract     # noqa: E402
import llm         # noqa: E402
import match       # noqa: E402
import profiles    # noqa: E402
import relevance   # noqa: E402
import schema      # noqa: E402
import score       # noqa: E402
from evals import metrics, scratchdb          # noqa: E402
from lib import envfile                       # noqa: E402
from lib.upsert import upsert_checked         # noqa: E402

#: The cohort profile, as the live database spells it.
PURSUIT = "pursuit"

#: The second active profile. Its only job is to widen the extraction union so
#: that the postings `pursuit`'s gate rejects still get facts -- see TWO
#: PROFILES above. Named so that a stray row in a real database would be
#: obviously not a user.
MOCK_ALL = "mock_all"

#: A gate that admits everything, expressed as a config rather than as a
#: special case in relevance.py.
#:
#: NON-EMPTY ON PURPOSE. profiles.upsert stores `json.dumps(cfg) if cfg else
#: None` (profiles.py:207) and relevance.for_profile reads NULL as "use the
#: shared config" (relevance.py:100-110) -- so a profile written with `{}`
#: would silently inherit config/relevance.json, which is the AUTHOR's
#: software-title gate and would reject most of this corpus. The empty lists
#: are what make it permissive; the keys are what make it stored.
PERMISSIVE_RELEVANCE = {
    "_comment":
        "Admits every row. Written by tools/mock-acceptance.py so that the "
        "extraction union covers the whole mock corpus, including the "
        "postings `pursuit` rejects -- measuring a gate requires facts for "
        "the rows it turned down. Never write this to a production database.",
    "title_include": [],
    "description_include": [],
    "title_exclude": [],
    "company_exclude": [],
    "platform_exclude": [],
    "description_exclude": [],
    "location_columns": [],
    "max_tier_to_score": 3,
}

PERMISSIVE_PERSONA = {
    "_comment":
        "Not a persona. This profile exists to widen the extraction gate and "
        "is never narrated; profiles.validate requires the four keys below, "
        "so they are present and say what they are.",
    "profile": MOCK_ALL,
    "display_name": "mock acceptance -- extraction gate widener",
    "background_summary":
        "NOT A PERSON. tools/mock-acceptance.py creates this profile inside a "
        "throwaway scratch schema so that every mock posting is eligible for "
        "extraction, including the ones `pursuit` rejects.",
    "strengths": ["not scored against"],
    "honest_gaps": ["not scored against"],
    "scoring_instructions":
        "Never send this profile to a model. Its daily_narrative_budget is 0 "
        "and mock-acceptance.py only ever narrates `pursuit`.",
}

#: Base only, so this profile's job_matches rows are visibly uninformative
#: rather than plausibly wrong -- the same argument
#: migrations/migrate_pursuit_profile.py:187-202 makes for its own stand-in.
PERMISSIVE_CRITERIA = {
    "_comment":
        "`base` only: every row scores 50 and the ordering carries no "
        "information, which is correct for a profile that exists to widen a "
        "gate. Every figure this script reports comes from `pursuit`.",
    "base": 50,
    "archetypes": {},
    "flags": {},
    "tech": {"boost": {}},
}

#: The fields measurement (a) scores, with the comparison rule each one gets.
#: Imported rather than re-listed: evals/tasks/extract.py:23 FIELD_KINDS is
#: where the rule lives beside the field, and a second copy here would drift.
#: `summary` is prose and is excluded for the reason metrics.selfcheck
#: excludes it -- there is no answer key for a paragraph.
def field_kinds():
    from evals.tasks.extract import FIELD_KINDS
    return {f: k for f, k in FIELD_KINDS.items() if k != "prose"}


#: The failure mode measurement (d) reports one posting at a time.
BRANDING_TRAP = "branding_trap"


class ContainmentError(RuntimeError):
    """schema.SCHEMA is not a scratch schema and a write was about to happen."""


def require_scratch_schema(name=None):
    """Refuse to continue unless writes will land in a throwaway schema.

    Checked against scratchdb.SCRATCH_NAME (scratchdb.py:70) rather than
    against "not public", because "not public" is satisfied by every typo. The
    only names this driver may write to are the ones scratchdb itself creates
    and will later drop.

    Called at the top of every function that writes, not once at startup: the
    functions are importable and a test, a notebook or a later caller can
    reach them without the context manager, and that caller is exactly who
    this is for.
    """
    name = schema.SCHEMA if name is None else name
    if not scratchdb.SCRATCH_NAME.match(name or ""):
        raise ContainmentError(
            f"refusing to write: schema.SCHEMA is {name!r}, which does not "
            f"match {scratchdb.SCRATCH_NAME.pattern}. This driver runs "
            f"extract.py and score.py in-process, so a non-scratch schema "
            f"means every write lands in the production tables. Run it "
            f"inside evals.scratchdb.scratch_schema().")
    return name


# --------------------------------------------------------------------------
# The corpus. Agent B's module owns the mapping; this file owns nothing about
# the postings' shape.
# --------------------------------------------------------------------------

def load_corpus(postings_path=None, key_path=None):
    """(postings, key, by_db_id) from evals/mock_corpus.py.

    `by_db_id` maps the job_id the pipeline will actually use -- sha256 over
    platform:token:source_id (schema.py:302) -- to (mock_id, posting, entry).
    The two ids are different and both are needed: the database knows the
    hash, the answer key and every report line are readable only by mock_NNN.

    THE KEY IS LOOKED UP UNDER EITHER ID. mock_corpus.load_key() returns
    {job_id: entry} and which job_id that is -- the file's "mock_041" or the
    hash -- is agent B's choice, not something this file should encode. Both
    are tried, in that order, and a posting whose entry is missing under both
    is reported rather than skipped: a corpus row with no key is a hole in
    the measurement, and dropping it silently would shrink the denominator.
    """
    from evals import mock_corpus

    postings = mock_corpus.load_postings(postings_path)
    try:
        key = mock_corpus.load_key(key_path)
    except mock_corpus.MockCorpusError as e:
        # Legible rather than a traceback: the key is a separate deliverable
        # from the corpus and from this driver, and "the answer key is not on
        # disk yet" is a normal state during the run that builds it -- not a
        # defect in the pipeline this script is pointed at.
        raise SystemExit(
            f"mock-acceptance FAILED: the answer key did not load.\n"
            f"  {e}\n"
            f"  Every measurement here is against that key; there is nothing "
            f"to report without it. Pass --key to point at another one.")

    by_db_id, unkeyed = {}, []
    for posting in postings:
        mock_id = posting.get("job_id")
        db_id = mock_corpus.job_id_for(posting)
        entry = key.get(mock_id)
        if entry is None:
            entry = key.get(db_id)
        if entry is None:
            unkeyed.append(mock_id)
        by_db_id[db_id] = (mock_id, posting, entry or {})
    return postings, key, by_db_id, unkeyed


# --------------------------------------------------------------------------
# Steps 2-4: everything that writes, and everything --dry-run still does.
# --------------------------------------------------------------------------

def install_profiles(conn, *, pursuit_relevance=None, criteria=None,
                     persona=None):
    """Create `pursuit` and `mock_all`, both active, in the scratch schema.

    profiles.upsert() rather than a call into migrate_profiles.py or
    migrate_pursuit_profile.py, and the reason is the warning in HANDOFF:
    a bare `migrate_profiles.py --apply` used to overwrite the three columns
    it was not given (fixed in fa2d7a7, resolve_preserved at
    migrate_profiles.py:113). That fix makes "absent means preserve" true,
    which is right for a live database and wrong here -- this schema is empty,
    so there is nothing to preserve and every value should be stated. Passing
    all three explicitly to profiles.upsert() is the form where a missing
    argument cannot be mistaken for an intention.

    The CONTENTS are the production files, all three of them: the gate from
    config/pursuit-relevance.json, and the weights and prose from the same two
    files migrate_profiles.py reads. A hand-typed copy of the gate would be
    measuring a gate the pipeline does not run. That invariant is asserted by
    tests/test_pursuit_gate.py rather than left to this paragraph, because it
    has already been load-bearing once: the gate used to be a dict literal
    inside migrate_pursuit_profile.py and this function used to importlib it.

    criteria_version is 1 here against 2 in production (profiles.upsert
    inserts 1 and only bumps when asked, profiles.py:194-201). It is a cache
    key, not a weight -- nothing in a fresh schema was computed under 2 -- but
    it is recorded in the artifact so a figure from here is never compared
    against a production row on the assumption they match.
    """
    require_scratch_schema()
    pursuit_relevance = (cohort_relevance() if pursuit_relevance is None
                         else pursuit_relevance)
    criteria = pursuit_criteria() if criteria is None else criteria
    persona = pursuit_persona() if persona is None else persona

    profiles.upsert(conn, PURSUIT, persona, criteria,
                    relevance_cfg=pursuit_relevance,
                    display_name=persona.get("display_name", PURSUIT),
                    daily_narrative_budget=0, active=True)
    profiles.upsert(conn, MOCK_ALL, PERMISSIVE_PERSONA, PERMISSIVE_CRITERIA,
                    relevance_cfg=PERMISSIVE_RELEVANCE,
                    display_name=PERMISSIVE_PERSONA["display_name"],
                    daily_narrative_budget=0, active=True)
    return profiles.load_active(conn)


def cohort_relevance(path=None):
    """The `pursuit` gate, from the file that owns it.

    Read like its siblings above, and that is the whole point: this used to
    importlib migrations/migrate_pursuit_profile.py for a dict literal. When
    the gate moved to config/pursuit-relevance.json (2026-07-29) this had to
    move with it. Had it not, the harness would have kept compiling the old
    literal while the pipeline ran the new file, and reported the gate
    unchanged -- which reads as the fix having done nothing, rather than as
    the instrument pointing at the wrong object.

    NOT comment-stripped, matching the stored column: relevance.load() drops
    the _-prefixed keys at read time (relevance.py:88-97).
    """
    with open(path or os.path.join(_REPO_ROOT, "config",
                                   "pursuit-relevance.json")) as f:
        return json.load(f)


def _strip_comments(cfg):
    """migrate_profiles.strip_comments (migrate_profiles.py:107), inlined.

    criteria_json is comment-stripped and persona_json is not, which is that
    script's asymmetry and not a slip: relevance.load() strips _-prefixed keys
    at read time so the documentation survives into the stored gate, and
    nothing strips criteria downstream -- profiles.validate would reject a
    string where it wants a number.
    """
    return {k: v for k, v in cfg.items() if not k.startswith("_")}


def pursuit_criteria(path=None):
    with open(path or os.path.join(_REPO_ROOT, "config",
                                   "pursuit-criteria.json")) as f:
        return _strip_comments(json.load(f))


def pursuit_persona(path=None):
    with open(path or os.path.join(_REPO_ROOT, "config",
                                   "pursuit-persona.json")) as f:
        return json.load(f)


def load_postings(conn, postings, mock_corpus):
    """Write the 55 records through the real upsert path. Returns the result.

    upsert_checked, never upsert: UpsertResult.__iter__ yields three values
    and `.errors` is the fourth, so a bare three-tuple unpack drops every
    per-record failure on the floor -- the defect in at least four ingest
    scripts (CLAUDE.md's landmine, lib/upsert.py:303). A silently half-loaded
    corpus here would move every accuracy figure and nothing would say so.
    """
    require_scratch_schema()
    records = [mock_corpus.to_job_record(p) for p in postings]
    return upsert_checked(conn, mock_corpus.spec(), records,
                          schema.make_job_id)


def pursuit_tiers(conn, cfg):
    """{job_id: tier} under `pursuit`'s own gate, and the tier that admits.

    Computed with relevance.tier_sql (relevance.py:189-300) against every row
    in the table rather than inferred from what got extracted, because the
    whole point of the second profile is that extraction no longer tells you
    what the gate did. Tier 1 is "relevant and NYC-or-remote", 2 is "relevant,
    location unknown or elsewhere", 3 is "rejected, by an include list or by
    one of the four exclude lists" (relevance.py:296-299).
    """
    expr, params = relevance.tier_sql(cfg)
    rows = conn.execute(
        f"SELECT j.id, {expr} FROM {schema.TABLE} j", params).fetchall()  # noqa: S608 -- splices schema.TABLE, a module-level constant
    return {r[0]: r[1] for r in rows}, relevance.max_tier(cfg)


# --------------------------------------------------------------------------
# Steps 5-7: the paid stages, plus the free one between them.
# --------------------------------------------------------------------------

def run_extract():
    """extract.main(), in-process. Returns nothing; it prints its own summary.

    main() rather than the inner functions, and that is a deliberate choice
    between two defensible ones. extract.py has NO CLI flags at all -- main()
    takes no arguments (extract.py:1162) -- so there is nothing to configure
    and nothing to pass. Calling select_unextracted_jobs/extract_one_job by
    hand would reimplement the drain loop, the batch connection policy and
    the deadline, which is three pieces of production behaviour this run
    exists to exercise rather than to imitate.

    The scratch schema is what makes that safe: main() drains whatever the
    active profiles' union selects, and in this schema that is 55 rows.
    """
    require_scratch_schema()
    extract.main()


def run_match(conn, active):
    """match.main()'s body, minus its argument parsing. Per-profile counts.

    Inlined rather than called because match.main() opens its own connection
    via dbconn.connect_or_exit and parses sys.argv -- both fine in a cron job,
    both wrong inside a driver that already holds a connection and has its own
    flags. The three lines that matter (load_facts over the union, then
    match_profile per profile) are called directly and are the same functions
    the nightly run calls.
    """
    require_scratch_schema()
    cfgs = [relevance.for_profile(p) for p in active]
    facts = match.load_facts(conn, cfgs)
    out = {}
    for prof in active:
        written, deleted, skipped = match.match_profile(conn, prof, facts)
        out[prof.profile] = {"matched": written, "demoted": deleted,
                             "current": skipped}
    return facts, out


def run_narratives(conn, profile_obj, limit):
    """score.run_for_profile over the above-floor rows. Returns its Counter.

    AN EXPLICIT LIMIT IS REQUIRED and that is not defensive coding.
    `pursuit`'s daily_narrative_budget is 0, and run_for_profile does
    `limit = budget if limit is None else limit` (score.py:1040) -- the
    corrected form of a `limit or budget` that used to turn "spend nothing"
    into 20. Passing None here would narrate nothing and report a silent zero.
    """
    require_scratch_schema()
    if limit is None:
        raise ValueError("run_narratives needs an explicit limit: `pursuit`'s "
                         "daily_narrative_budget is 0, so None narrates "
                         "nothing (score.py:1040)")
    return score.run_for_profile(conn, profile_obj, limit=limit)


# --------------------------------------------------------------------------
# Reading back what happened.
# --------------------------------------------------------------------------

_FACT_COLUMNS = ("job_id", "facts_version", "seniority_level",
                 "years_experience_min", "years_experience_max",
                 "role_archetype", "tech_stack", "ai_involvement",
                 "ml_research_required", "advanced_degree_required",
                 "customer_facing", "remote_policy", "employment_type",
                 "comp_min", "comp_max", "comp_currency",
                 "gap_friendly_language", "visa_sponsorship",
                 "extraction_model")


def read_facts(conn):
    """{job_id: dict}, tombstones included and flagged.

    Tombstones are kept rather than filtered the way match.load_facts filters
    them (match.py:298-300), because a row the model could not read is an
    outcome of this measurement and excluding it would flatter every field
    rate. `tombstone` is True when extraction_model carries llm.FAILED_PREFIX.
    """
    rows = conn.execute(
        f"SELECT {', '.join(_FACT_COLUMNS)} FROM {schema.FACTS_TABLE}"  # noqa: S608 -- splices _FACT_COLUMNS and schema.FACTS_TABLE -- both module-level constants
    ).fetchall()
    out = {}
    for r in rows:
        d = dict(zip(_FACT_COLUMNS, r))
        d["tombstone"] = bool(d["extraction_model"]
                              and d["extraction_model"].startswith(
                                  llm.FAILED_PREFIX))
        out[d["job_id"]] = d
    return out


def read_matches(conn, profile):
    rows = conn.execute(
        f"SELECT job_id, match_score, match_reasons "  # noqa: S608 -- splices schema.MATCHES_TABLE, a module-level constant
        f"FROM {schema.MATCHES_TABLE} WHERE profile = %s", (profile,)).fetchall()
    return {r[0]: {"match_score": r[1], "match_reasons": r[2]} for r in rows}


def read_scores(conn, profile):
    rows = conn.execute(
        f"SELECT job_id, fit_score, primary_track "  # noqa: S608 -- splices schema.SCORES_TABLE, a module-level constant
        f"FROM {schema.SCORES_TABLE} WHERE profile = %s", (profile,)).fetchall()
    return {r[0]: {"fit_score": r[1], "primary_track": r[2]} for r in rows}


def read_jobs(conn):
    rows = conn.execute(
        f"SELECT id, title, company_name, platform, location_is_nyc, "  # noqa: S608 -- splices schema.TABLE, a module-level constant
        f"location_is_remote FROM {schema.TABLE}").fetchall()
    return {r[0]: {"title": r[1], "company_name": r[2], "platform": r[3],
                   "location_is_nyc": r[4], "location_is_remote": r[5]}
            for r in rows}


# --------------------------------------------------------------------------
# (a) and (e): per-field extraction accuracy against the key.
# --------------------------------------------------------------------------

def expected_value(entry, field):
    """(value, quote, determinable) for one key field.

    A NULL `value` MEANS "NOT DETERMINABLE FROM THE POSTING" AND IS NOT AN
    ANSWER. It goes in `not_determinable` and never in the denominator.
    Scoring it as an error would be scoring the model for failing to know
    something the posting does not say, and every accuracy figure computed
    that way is invented. This is the single easiest way to get a wrong number
    out of this harness, which is why it is one function with one caller.
    """
    fields = (entry or {}).get("fields") or {}
    if field not in fields:
        return None, None, False
    spec = fields[field] or {}
    value = spec.get("value")
    return value, spec.get("quote"), value is not None


def field_accuracy(rows, kinds):
    """Per-field agreement with the key. {field: cell}.

    `rows` is a list of (entry, facts) pairs -- one per posting in scope.
    A posting with no facts row at all, or a tombstoned one, counts as a MISS
    on every determinable field rather than being dropped: "the pipeline
    produced no answer" is a worse outcome than a wrong answer, not an absent
    one, and dropping it would let a model that tombstones everything report
    perfect accuracy. `no_facts` records how many.
    """
    out = {}
    for field, kind in sorted(kinds.items()):
        k = n = not_determinable = no_facts = 0
        for entry, facts in rows:
            value, _quote, determinable = expected_value(entry, field)
            if not determinable:
                not_determinable += 1
                continue
            n += 1
            if not facts or facts.get("tombstone"):
                no_facts += 1
                continue
            if metrics.exact(kind, value, facts.get(field)):
                k += 1
        out[field] = {
            "kind": kind, "k": k, "n": n,
            "rate": (k / n) if n else None,
            "ci": metrics.wilson(k, n),
            "not_determinable": not_determinable,
            "no_facts": no_facts,
        }
    return out


def pooled(cells):
    """One agreement figure over every field cell, with its Wilson interval.

    Pooled rather than a mean of rates: a field with 3 determinable values
    and a field with 50 are not two equally informative observations, and
    averaging the rates would weight them as though they were.
    """
    k = sum(c["k"] for c in cells.values())
    n = sum(c["n"] for c in cells.values())
    return {"k": k, "n": n, "rate": (k / n) if n else None,
            "ci": metrics.wilson(k, n)}


# --------------------------------------------------------------------------
# (b): the gate against the intended verdict.
# --------------------------------------------------------------------------

def gate_confusion(rows):
    """Admission vs intended verdict. `rows` is (verdict, admitted, mock_id).

    THE FALSE-NEGATIVE CELL IS THE MEASUREMENT: intended-good postings the
    gate rejected. Everything else here is already measurable in production;
    that cell is not, because a rejected posting never acquires facts, a
    match, a score or a label, and so never appears in any sample anyone
    could draw from the live database.

    Returns the four cells, the two ids lists that are worth reading, and
    recall/precision -- named `gate_recall` and `gate_precision` rather than
    the bare words, because the pipeline reports a different precision at
    every later stage and two of them are already confused with each other in
    the docs.
    """
    cells = Counter()
    false_negatives, false_positives = [], []
    for verdict, admitted, mock_id in rows:
        if verdict not in ("good", "bad"):
            continue
        cells[(verdict, bool(admitted))] += 1
        if verdict == "good" and not admitted:
            false_negatives.append(mock_id)
        if verdict == "bad" and admitted:
            false_positives.append(mock_id)

    tp = cells[("good", True)]
    fn = cells[("good", False)]
    fp = cells[("bad", True)]
    tn = cells[("bad", False)]
    return {
        "good_admitted": tp, "good_rejected": fn,
        "bad_admitted": fp, "bad_rejected": tn,
        "false_negatives": sorted(false_negatives),
        "false_positives": sorted(false_positives),
        "gate_recall": (tp / (tp + fn)) if (tp + fn) else None,
        "gate_recall_ci": metrics.wilson(tp, tp + fn),
        "gate_precision": (tp / (tp + fp)) if (tp + fp) else None,
        "gate_precision_ci": metrics.wilson(tp, tp + fp),
    }


# --------------------------------------------------------------------------
# (c): does score_job() put the good ones first?
# --------------------------------------------------------------------------

def ranking_quality(scored, k=metrics.TOP_K):
    """Average precision and precision@k for `scored`: (mock_id, score, good).

    SCORED IN-PROCESS OVER EVERY ROW, NOT JOINED AGAINST job_matches. That
    table holds only rows at or above MATCH_FLOOR (schema.py:228,
    match.py:389), so joining it restricts the sample to postings the rules
    already liked and measures a storage policy -- the same error
    tools/calibrate-match.py:93-105 documents costing it 0.326 against a true
    0.619 on one identical ranking function.

    `baseline` is the positive RATE, and the average precision means nothing
    without it: average precision's chance level is the prevalence, so 0.55
    on a corpus that is 55% good is exactly no signal, not a passing grade.

    The tie interval is reported because match_score is free arithmetic over a
    small integer weight table and clusters hard. If `ap_optimistic` and
    `ap_pessimistic` are far apart, the point estimate is describing the tie
    structure at least as much as the ranking -- see metrics.TIE_MODES.

    THE OTHER FLOOR-FILTERED SAMPLE, AND IT IS THE ONE THAT HIDES
        A posting scores None here exactly when it has no usable job_facts
        row -- extraction tombstoned it, or never reached it. Those rows leave
        the denominator (metrics.Ranked), and they are NOT a random sample:
        a posting whose description defeats the extractor is likelier to be
        one of the deliberately awkward ones this corpus was built out of, so
        every drop removes a hard case and makes the ranker look better.

        That is trap 4.1
        (`git show refactor-freeze-2026-08-02:docs/MEASUREMENT-TRAPS.md`) pointing
        the other way -- there MATCH_FLOOR hid the easy low end and cost a
        ranking 0.619 -> 0.326; here extraction failure hides the hard end and
        pays it back with interest.

        So `coverage` carries n/total in the shape
        `git show refactor-freeze-2026-08-02:docs/score-validation.md:270`
        already prints ("55 usable of 120"), and `unscored_good` lists the
        intended-GOOD postings that were dropped BY ID. That last one is not a
        caveat on the ranking figure, it is a finding of its own: an extraction
        failure on a posting the key calls good is a pipeline defect, and this
        corpus exists to catch exactly that.
    """
    scores = [s for _id, s, _good in scored]
    labels = [1 if good else 0 for _id, _s, good in scored]
    ap = metrics.average_precision(scores, labels)
    p_at_k = metrics.precision_at_k(scores, labels, k=k)

    unscored_good = sorted(mock_id for mock_id, s, good in scored
                           if s is None and good)
    unscored_bad = sorted(mock_id for mock_id, s, good in scored
                          if s is None and not good)
    return {
        "n": ap.n,
        "n_total": ap.n + ap.n_dropped,
        "coverage": ap.coverage(),
        "complete": ap.complete,
        "n_unscored": ap.n_dropped,
        "n_unscored_good": ap.n_dropped_positive,
        "unscored_good": unscored_good,
        "unscored_bad": unscored_bad,
        "n_good": ap.n_positive,
        "baseline": (ap.n_positive / ap.n) if ap.n else None,
        "average_precision": ap.value,
        "ap_optimistic": metrics.average_precision(
            scores, labels, ties="optimistic").value,
        "ap_pessimistic": metrics.average_precision(
            scores, labels, ties="pessimistic").value,
        # `k` and `k_requested` both, and the key name does not embed either:
        # min(k, n) means the two differ on a small corpus, and a key that
        # renamed itself with k would make two artifacts un-diffable.
        "k": p_at_k.k,
        "k_requested": k,
        "precision_at_k": p_at_k.value,
        "ties": metrics.tie_histogram(scores),
    }


# --------------------------------------------------------------------------
# (d): the branding traps, one line each.
# --------------------------------------------------------------------------

def branding_traps(scope, key_fm):
    """One row per branding-trap posting. Never a rate.

    HANDOFF's top section records task 13's four floor misses as carrying
    ai_involvement='none' at AI-branded employers, and says only labels can
    settle whether those are weight errors or correct rejections. A rate
    cannot settle it either -- the question is whether the model read a
    specific posting the way a person would, and that is answered one posting
    at a time or not at all. So this returns the model's answer, the key's
    answer, and the score beside each other, and the reader decides.
    """
    out = []
    for row in scope:
        if BRANDING_TRAP not in (key_fm.get(row["mock_id"]) or []):
            continue
        expected_ai, quote, determinable = expected_value(
            row["entry"], "ai_involvement")
        facts = row["facts"] or {}
        out.append({
            "mock_id": row["mock_id"],
            "company_name": row["job"].get("company_name"),
            "title": row["job"].get("title"),
            "verdict": row["verdict"],
            "model_ai_involvement": facts.get("ai_involvement"),
            "key_ai_involvement": expected_ai if determinable else None,
            "key_not_determinable": not determinable,
            "key_quote": quote,
            "agrees": (metrics.exact("enum", expected_ai,
                                     facts.get("ai_involvement"))
                       if determinable and facts else None),
            "tier": row["tier"],
            "admitted": row["admitted"],
            "match_score": row["match_score"],
            "above_floor": (row["match_score"] is not None
                            and row["match_score"] >= schema.MATCH_FLOOR),
            "fit_score": (row["score"] or {}).get("fit_score"),
        })
    return sorted(out, key=lambda r: r["mock_id"] or "")


# --------------------------------------------------------------------------
# The report.
# --------------------------------------------------------------------------

def _pct(x):
    return "  n/a" if x is None else f"{100 * x:5.1f}%"


def _ci(cell):
    lo, hi = cell["ci"]
    return f"[{100 * lo:4.1f}-{100 * hi:4.1f}]"


def print_report(report, out=None):
    """The whole measurement, as text. The JSON artifact is the same numbers."""
    p = (lambda *a: print(*a, file=out)) if out else print
    r = report

    p("")
    p("=" * 76)
    p(f"mock acceptance -- {r['n_postings']} postings, schema {r['schema']}")
    p("=" * 76)
    p(f"  mode                 : {r['mode']}")
    p(f"  extracted / tombstone: {r['facts']['extracted']} / "
      f"{r['facts']['tombstoned']}   (no facts row: {r['facts']['missing']})")
    p(f"  matched >= floor {schema.MATCH_FLOOR:<3} : {r['matched']}")
    p(f"  narratives           : "
      + (", ".join(f"{k}={v}" for k, v in sorted(r["narratives"].items()))
         or "none (skipped)"))
    p(f"  in scope / undecided : {r['n_scope']} / {r['n_undecided']}"
      f"   (undecided: {', '.join(r['undecided_ids']) or 'none'})")
    if r["unkeyed"]:
        p(f"  NO KEY ENTRY         : {', '.join(r['unkeyed'])}"
          "   <-- a hole in the measurement, not a pass")

    p("")
    p("(a) per-field extraction accuracy vs the answer key")
    p(f"    {'field':<26} {'k/n':>9}  {'rate':>6}  {'wilson 95%':>13}  "
      f"{'n/d':>4} {'nofacts':>7}")
    for field, c in r["field_accuracy"].items():
        p(f"    {field:<26} {str(c['k']) + '/' + str(c['n']):>9}  "
          f"{_pct(c['rate'])}  {_ci(c):>13}  {c['not_determinable']:>4} "
          f"{c['no_facts']:>7}")
    pool = r["pooled"]
    p(f"    {'POOLED':<26} {str(pool['k']) + '/' + str(pool['n']):>9}  "
      f"{_pct(pool['rate'])}  "
      f"[{100 * pool['ci'][0]:4.1f}-{100 * pool['ci'][1]:4.1f}]")
    p("    n/d = the key says the posting does not determine this field. "
      "Excluded from n.")

    g = r["gate"]
    p("")
    p("(b) gate admission vs intended verdict  -- the number nothing else "
      "here can measure")
    p(f"    {'':<14}{'admitted':>10}{'rejected':>10}")
    p(f"    {'intended good':<14}{g['good_admitted']:>10}"
      f"{g['good_rejected']:>10}   <-- rejected = FALSE NEGATIVES")
    p(f"    {'intended bad':<14}{g['bad_admitted']:>10}{g['bad_rejected']:>10}")
    p(f"    gate recall    : {_pct(g['gate_recall'])} "
      f"[{100 * g['gate_recall_ci'][0]:.1f}-{100 * g['gate_recall_ci'][1]:.1f}]"
      f"   ({g['good_rejected']} good posting(s) thrown away)")
    p(f"    gate precision : {_pct(g['gate_precision'])} "
      f"[{100 * g['gate_precision_ci'][0]:.1f}-"
      f"{100 * g['gate_precision_ci'][1]:.1f}]")
    if g["false_negatives"]:
        p(f"    false negatives: {', '.join(g['false_negatives'])}")
    if g["false_positives"]:
        p(f"    false positives: {', '.join(g['false_positives'])}")

    q = r["ranking"]
    p("")
    p("(c) score_job() separating intended-good from intended-bad")
    if not q["n"]:
        p(f"    NOT MEASURED: none of the {q['n_unscored']} in-scope postings "
          f"has a match_score, because none has usable facts. This is the "
          f"expected --dry-run result; in a full run it means extraction "
          f"failed.")
    # n/total ON EVERY LINE, not once in a footnote. The coverage is a
    # property of each figure, and a reader who sees "36.0%" and has to scroll
    # for "over 41 of 54" is a reader who will quote the 36.0%.
    cov = f"  [{q['coverage']} scored]"
    p(f"    average precision : {_pct(q['average_precision'])}{cov}   "
      f"(ties: {_pct(q['ap_pessimistic'])} .. {_pct(q['ap_optimistic'])})")
    p(f"    precision@{q['k']:<8}: {_pct(q['precision_at_k'])}{cov}"
      + ("" if q["k"] == q["k_requested"]
         else f"   (asked for {q['k_requested']}; {q['n']} row(s) scored)"))
    p(f"    chance level      : {_pct(q['baseline'])}  "
      f"({q['n_good']} good of {q['n']} scored, {q['n_unscored']} unscored) "
      f"-- average precision below this is worse than a coin")
    t = q["ties"]
    p(f"    tie structure     : {t['distinct']} distinct scores over {t['n']}, "
      f"largest block {t['largest']}, p_tie "
      f"{'n/a' if t['p_tie'] is None else format(t['p_tie'], '.3f')}")

    # The drops, and the good ones BY ID. An extraction failure on a posting
    # the key calls good is a defect this corpus was built to catch, not a
    # footnote on a ranking figure -- and because every drop removes a hard
    # case, the two figures above are conditioned on this list being empty.
    #
    # Only when SOMETHING was scored. With n == 0 every row is unscored by
    # construction -- the --dry-run case -- and listing all 23 good postings
    # as individual pipeline defects would be false: nothing was attempted.
    # The NOT MEASURED line above already carries that.
    if q["n_unscored"] and q["n"]:
        p(f"    UNSCORED          : {q['n_unscored']} of {q['n_total']} "
          f"in-scope postings have no match_score (no usable job_facts row). "
          f"Both figures above are computed over the other {q['n']}.")
        if q["n_unscored_good"]:
            p(f"    INTENDED-GOOD POSTINGS LOST TO EXTRACTION "
              f"({q['n_unscored_good']}): "
              f"{', '.join(q['unscored_good'])}")
            p(f"      Each is a pipeline defect in its own right, and each "
              f"removed a hard case from the two figures above -- so they are "
              f"biased UPWARD by an unknown amount, not merely noisier.")
        if q["unscored_bad"]:
            p(f"    intended-bad, unscored ({len(q['unscored_bad'])}): "
              f"{', '.join(q['unscored_bad'])}")

    p("")
    p("(d) the branding traps, one posting at a time -- HANDOFF's open "
      "question")
    if not r["branding_traps"]:
        p("    none in scope.")
    for b in r["branding_traps"]:
        p(f"    {b['mock_id']}  {str(b['company_name'])[:28]:<28} "
          f"model={str(b['model_ai_involvement']):<18} "
          f"key={str(b['key_ai_involvement']):<18} "
          f"tier={b['tier']} match={b['match_score']} "
          f"fit={b['fit_score']}")
        if b["key_quote"]:
            p(f"              key quote: {str(b['key_quote'])[:96]}")

    p("")
    p("(e) accuracy by who wrote the posting -- a confound check, not "
      "decoration")
    p(f"    {'generated_by':<14}{'k/n':>10}{'rate':>8}  {'wilson 95%':>13}"
      f"{'postings':>10}")
    for gen, c in r["by_generator"].items():
        p(f"    {gen:<14}{str(c['k']) + '/' + str(c['n']):>10}"
          f"{_pct(c['rate']):>8}  "
          f"[{100 * c['ci'][0]:4.1f}-{100 * c['ci'][1]:4.1f}]"
          f"{c['postings']:>10}")
    if r["confound"]:
        p(f"    {r['confound']}")

    p("")
    p(f"  scratch schema       : {r['schema']}")
    p(f"  teardown             : {r['teardown']}")
    p("=" * 76)


def confound_note(by_generator, human_key="human"):
    """The sentence measurement (e) exists to make it possible to write.

    Named thresholds rather than a judgement call at the call site: "materially
    below" has to mean something fixed before the number is seen, or it means
    whatever the reader wants once it is. 5 points is one notch of the
    granularity these rates have at n<=170 determinable values per cell, and
    the interval check is what stops a 6-point gap on n=20 reading as a
    finding.
    """
    human = by_generator.get(human_key)
    if not human or not human["n"]:
        return ""
    model_k = sum(c["k"] for g, c in by_generator.items() if g != human_key)
    model_n = sum(c["n"] for g, c in by_generator.items() if g != human_key)
    if not model_n:
        return ""
    gap = (model_k / model_n) - (human["rate"] or 0.0)
    if gap < 0.05:
        return (f"    human-written postings are within {100 * gap:.1f} points "
                f"of model-written ones: no confound visible at this n.")
    lo_model = metrics.wilson(model_k, model_n)[0]
    overlaps = human["ci"][1] >= lo_model
    verdict = ("the intervals still overlap, so this is suggestive rather "
               "than established"
               if overlaps else
               "the intervals do not overlap")
    return (f"    THE HEADLINE NUMBER IS INFLATED: the 10 human-written "
            f"postings score {100 * gap:.1f} points below the model-written "
            f"ones ({_pct(human['rate']).strip()} vs "
            f"{_pct(model_k / model_n).strip()}), which is what it looks like "
            f"when a model finds a model's prose easier to read than a "
            f"person's -- {verdict}.")


# --------------------------------------------------------------------------
# Driver.
# --------------------------------------------------------------------------

def build_report(*, postings, by_db_id, unkeyed, jobs, facts, tiers, max_tier,
                 matches, scores, criteria, schema_name, mode, narratives,
                 mock_corpus):
    """Everything above, assembled. Pure: no database, no clock, no LLM."""
    # `verdict` and `failure_modes` are read off the key ENTRY rather than
    # through mock_corpus.verdicts()/failure_modes(), which return dicts keyed
    # by job_id -- and which job_id that is (mock_NNN or the hash) is agent B's
    # choice. load_corpus() has already resolved the entry for each posting
    # under either convention, so reading the entry cannot pick the wrong one.
    kinds = field_kinds()

    rows = []
    for db_id, (mock_id, posting, entry) in sorted(by_db_id.items(),
                                                   key=lambda kv: kv[1][0]):
        f = facts.get(db_id)
        m = matches.get(db_id)
        # score_job over the facts row directly rather than reading
        # job_matches: that table is floored, and the ranking is what is being
        # measured. NULL when the row has no usable facts at all.
        if f and not f["tombstone"]:
            facts_for_score = dict(f)
            try:
                facts_for_score["tech_stack"] = json.loads(
                    f.get("tech_stack") or "[]")
            except (TypeError, ValueError):
                facts_for_score["tech_stack"] = []
            job = jobs.get(db_id, {})
            facts_for_score["location_is_nyc"] = job.get("location_is_nyc")
            facts_for_score["location_is_remote"] = job.get("location_is_remote")
            match_score, match_reasons = match.score_job(facts_for_score,
                                                         criteria)
        else:
            match_score, match_reasons = None, None
        tier = tiers.get(db_id)
        rows.append({
            "mock_id": mock_id,
            "job_id": db_id,
            "generated_by": posting.get("generated_by") or "unknown",
            "verdict": (entry or {}).get("verdict"),
            "failure_modes": (entry or {}).get("failure_modes") or [],
            "entry": entry,
            "job": jobs.get(db_id, {}),
            "facts": f,
            "tier": tier,
            "admitted": (tier is not None and tier <= max_tier),
            "match_score": match_score,
            "match_reasons": match_reasons,
            "stored_match": (m or {}).get("match_score"),
            "score": scores.get(db_id),
        })

    scope = [r for r in rows if r["verdict"] in ("good", "bad")]
    undecided = [r for r in rows if r["verdict"] not in ("good", "bad")]

    cells = field_accuracy([(r["entry"], r["facts"]) for r in scope], kinds)
    by_generator = {}
    for gen in sorted({r["generated_by"] for r in scope}):
        subset = [r for r in scope if r["generated_by"] == gen]
        c = pooled(field_accuracy([(r["entry"], r["facts"]) for r in subset],
                                  kinds))
        c["postings"] = len(subset)
        by_generator[gen] = c

    key_fm = {r["mock_id"]: r["failure_modes"] for r in rows}
    scored = [(r["mock_id"], r["match_score"], r["verdict"] == "good")
              for r in scope]

    n_tomb = sum(1 for r in rows if r["facts"] and r["facts"]["tombstone"])
    n_facts = sum(1 for r in rows if r["facts"] and not r["facts"]["tombstone"])

    return {
        "schema": schema_name,
        "mode": mode,
        "n_postings": len(postings),
        "n_scope": len(scope),
        "n_undecided": len(undecided),
        "undecided_ids": sorted(r["mock_id"] for r in undecided),
        "unkeyed": sorted(unkeyed),
        "facts": {"extracted": n_facts, "tombstoned": n_tomb,
                  "missing": len(rows) - n_facts - n_tomb},
        "matched": sum(1 for r in rows if r["stored_match"] is not None),
        "narratives": narratives,
        "criteria_version": 1,
        "match_floor": schema.MATCH_FLOOR,
        "field_accuracy": cells,
        "pooled": pooled(cells),
        "gate": gate_confusion([(r["verdict"], r["admitted"], r["mock_id"])
                                for r in rows]),
        "max_tier_to_score": max_tier,
        "ranking": ranking_quality(scored),
        "branding_traps": branding_traps(scope, key_fm),
        "by_generator": by_generator,
        "confound": confound_note(by_generator),
        "rows": rows,
        "teardown": "not yet",
    }


def _write(path, report):
    with open(path, "w") as f:
        json.dump(report, f, indent=2, default=str)


def observe_teardown(name, *, kept=False, url=None):
    """Did the DROP actually run? Asked of the server, not inferred.

    A fresh connection, because the one scratch_schema() held has been closed
    by the time this is callable -- which is the whole point: this runs after
    the context manager's finally, so it sees what a later operator would see.

    Returns a sentence for the report rather than a boolean: "kept on purpose"
    and "should have gone and did not" are different outcomes and only one of
    them needs somebody to do something.
    """
    try:
        with psycopg.connect(url or scratchdb.scratch_url(),
                             connect_timeout=5) as conn:
            present = conn.execute(
                "SELECT 1 FROM information_schema.schemata "
                "WHERE schema_name = %s", (name,)).fetchone() is not None
    except Exception as e:      # noqa: BLE001 -- reporting, never fatal
        return f"UNKNOWN -- could not re-check {name}: {type(e).__name__}: {e}"
    if kept:
        return (f"SKIPPED (--keep); {name} is "
                + ("present as asked" if present
                   else "GONE, which --keep says it should not be"))
    if present:
        return (f"DID NOT RUN -- {name} is still there. Drop it: "
                f"DROP SCHEMA {name} CASCADE;")
    return f"ran -- {name} is gone (verified)"


def main(argv=None):
    p = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--dry-run", action="store_true",
                   help="everything except the two paid stages: the schema, "
                        "the profiles, the 55 rows, the relevance tiers, the "
                        "match pass and the whole report. Spends nothing.")
    p.add_argument("--keep", action="store_true",
                   help="leave the scratch schema behind for inspection. It "
                        "is named on both the success and the failure path "
                        "either way.")
    p.add_argument("--no-narratives", action="store_true",
                   help="extract and match, but skip the ~30 narrative calls. "
                        "Measurements (a)-(e) are all computable without "
                        "them; only fit_score in the (d) table goes blank.")
    p.add_argument("--score-limit", type=int, default=None,
                   help="cap the narrative calls (default: every above-floor "
                        "row). An explicit 0 spends nothing, which is what "
                        "score.py:1036-1040's fix makes possible.")
    p.add_argument("--out", default=None,
                   help="write the JSON artifact here (default: "
                        "data/mock-acceptance-<schema>.json)")
    p.add_argument("--postings", default=None, help="override the corpus path")
    p.add_argument("--key", default=None, help="override the answer key path")
    args = p.parse_args(argv)

    # Same file systemd reads. Loaded here rather than relied on from the
    # shell so that `python3 tools/mock-acceptance.py` behaves the same way
    # from a terminal as from run-daily.py -- override=False, so a variable
    # already exported still wins (lib/envfile.py:85).
    envfile.load(os.path.join(_REPO_ROOT, ".env"))

    from evals import mock_corpus

    if not args.dry_run:
        if not llm.api_key():
            print("mock-acceptance FAILED: JOB_SCORING_API_KEY (or "
                  "GLM_API_KEY) not set. --dry-run needs no key.")
            return 1
        mismatch = llm.model_mismatch()
        if mismatch:
            print(f"mock-acceptance FAILED: {mismatch}")
            return 1

    postings, _key, by_db_id, unkeyed = load_corpus(args.postings, args.key)
    name = None
    try:
        with scratchdb.scratch_schema(keep=args.keep) as (conn, name):
            print(f"[mock-acceptance] scratch schema {name}")
            require_scratch_schema(name)

            active = install_profiles(conn)
            pursuit_obj = next(p for p in active if p.profile == PURSUIT)
            result = load_postings(conn, postings, mock_corpus)
            print(f"[mock-acceptance] loaded {result.new} new, "
                  f"{result.updated} updated, {len(result.errors)} failed")

            cfg = relevance.for_profile(pursuit_obj)
            tiers, max_tier = pursuit_tiers(conn, cfg)

            if args.dry_run:
                mode = "dry-run (no LLM calls)"
            else:
                run_extract()
                mode = "full"

            _facts, match_counts = run_match(conn, active)
            print(f"[mock-acceptance] match: {match_counts}")

            narratives = {}
            if args.dry_run or args.no_narratives:
                if not args.dry_run:
                    mode = "full, narratives skipped"
            else:
                above = sum(1 for jid, m in read_matches(conn, PURSUIT).items()
                            if m["match_score"] is not None)
                limit = above if args.score_limit is None else args.score_limit
                narratives = dict(run_narratives(conn, pursuit_obj, limit))
                print(f"[mock-acceptance] narratives: {narratives}")

            report = build_report(
                postings=postings, by_db_id=by_db_id, unkeyed=unkeyed,
                jobs=read_jobs(conn), facts=read_facts(conn),
                tiers=tiers, max_tier=max_tier,
                matches=read_matches(conn, PURSUIT),
                scores=read_scores(conn, PURSUIT),
                criteria=pursuit_obj.criteria, schema_name=name, mode=mode,
                narratives=narratives, mock_corpus=mock_corpus)
            report["teardown"] = ("SKIPPED (--keep)" if args.keep
                                  else "pending -- checked after the run")

            out_path = args.out or os.path.join(
                _REPO_ROOT, "data", f"mock-acceptance-{name}.json")
            os.makedirs(os.path.dirname(out_path), exist_ok=True)
            _write(out_path, report)

        # OBSERVED, NOT ASSUMED. HANDOFF:821 records two orphaned scratch
        # schemas -- scratch_5ce56323 and scratch_cafb8b05, still present --
        # from task 09's harness, so "the context manager drops it" is a claim
        # that has already been false once. This asks the server, after the
        # DROP would have run, and the answer goes in the artifact.
        report["teardown"] = observe_teardown(name, kept=args.keep)
        _write(out_path, report)
        print_report(report)
        print(f"  artifact             : {out_path}")
    finally:
        # HANDOFF:821 records two orphaned scratch schemas from task 09's
        # harness -- the teardown does not always run. The name is printed on
        # BOTH paths so that a run which dies mid-extraction still tells
        # somebody what to drop, and the drop is one statement:
        #     DROP SCHEMA <name> CASCADE;
        if name:
            print(f"[mock-acceptance] scratch schema was {name}"
                  + ("  (KEPT -- drop it by hand)" if args.keep else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())

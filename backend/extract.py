#!/usr/bin/env python3
"""
Extract profile-independent facts from a posting. One LLM call per job, ever.

WHY THIS EXISTS
    score.py used to make one LLM call per (job, profile). That is correct and
    it does not scale: cost, latency and rate-limit consumption all grow as
    jobs x profiles. Measured on this corpus at 100 profiles it is 11,500
    calls a day, and a new profile sees nothing until its whole eligible
    backlog has been scored -- about four hours.

    Almost none of what that call produced actually depended on the persona.
    "Is this a staff-level role", "does it want 8 years", "is it remote",
    "does it require a PhD" are facts about the POSTING. Only the narrative --
    how this candidate should frame their gap for this job -- needs both.

    So the facts are extracted once here, shared by every profile that will
    ever exist, and match.py turns them into a per-profile ranking with
    arithmetic instead of tokens. This stage is flat in the number of users;
    it costs the same at one profile as at a thousand.

THE PROMPT HAS NO PERSONA IN IT, AND THAT IS THE POINT
    Not just because facts should not be persona-shaped, but because the
    instruction block is then byte-identical for every job AND every user, so
    it is one cache prefix across the entire corpus. Measured on the scoring
    prompt, a warm prefix cache bills at 1/50th -- the persona was the largest
    single thing preventing that from being shared.

    Consequence: the posting goes LAST. Anything variable placed before the
    fixed instructions would truncate the common prefix and forfeit the cache.

VOCABULARIES ARE CLOSED, AND COERCED HERE
    match.py compares these strings exactly. A model that answers "Senior/Mid"
    or "mid-level" instead of "mid" does not error -- it silently scores as
    unknown for every profile forever. So every enum answer is normalised
    against a fixed vocabulary on the way in, and anything unrecognised
    becomes NULL rather than being stored verbatim. NULL is a data gap the
    matcher can reason about; "Mid-Level" is a landmine.

FAILURE HANDLING IS score.py'S, DELIBERATELY UNCHANGED
    SCORED / REJECTED / DEFERRED, with the same reasoning: a model that
    cannot produce usable JSON for a posting gets a tombstone so it is not
    retried nightly forever, and a 429 gets nothing written so it is. Getting
    that backwards permanently discards jobs that were never evaluated.

SOME SOURCES GET THREE CALLS, NOT ONE
    "One LLM call per job" above is now "one call per job on six of the seven
    platforms". Task 06 measured this model disagreeing with ITSELF at
    temperature 0, and unevenly: ai_involvement self-agrees 92.2% on
    greenhouse/ashby and 77.8% on hn_whoishiring. config/extraction-policy.json
    holds the measured figures and the threshold; a platform below it gets
    three passes and a field-wise majority vote (vote_facts() below), and every
    other platform is unchanged at one call. The cost is +4.2% of calls, not
    3x -- the arithmetic is in that file. The shared-facts property is
    untouched: it is still ONE job_facts row per posting, paid once, read by
    every profile.

    job_facts.extraction_passes and .vote_unanimity record what a row actually
    got, so "how sure are we about this row" is a query rather than an
    assumption. Task 11 consumes them.

IT DRAINS THE BACKLOG, IT DOES NOT DO ONE BATCH
    This script used to extract exactly EXTRACT_BATCH_SIZE postings per
    invocation, and run-daily.py invokes it once. That is a hard 40/day
    ceiling against 43/day of eligible intake (task 05) and 80/day recently:
    the backlog could only grow, and ORDER BY first_seen DESC decided which
    postings were never looked at. It now loops batches until the backlog is
    empty or a wall-clock deadline passes -- and stops immediately on a batch
    that makes no progress, because a rate-limited endpoint would otherwise
    spin until the deadline and leave things strictly worse.

USAGE
    python3 extract.py
    EXTRACT_BATCH_SIZE=40 EXTRACT_MAX_WORKERS=3 python3 extract.py
    EXTRACT_DEADLINE_SECS=3600 python3 extract.py
    DEBUG_PRINT_KEYS=1 python3 extract.py

    JOBS_EXPECTED_MODEL, if set, pins the model this stage is allowed to run
    under -- see llm.model_mismatch(). Resolved via the same JOB_SCORING_MODEL
    / LLM_MODEL / llm.DEFAULT_MODEL chain score.py uses.
"""

import os
import sys
import json
import time
import urllib.parse
import concurrent.futures
from collections import Counter

import llm
import profiles
import relevance
import schema
from lib import dbconn
from lib.timeparse import utc_now_str

EXTRACT_BATCH_SIZE = int(os.environ.get("EXTRACT_BATCH_SIZE", "40"))
EXTRACT_MAX_WORKERS = int(os.environ.get("EXTRACT_MAX_WORKERS", "3"))

#: How long main() may keep starting new batches, measured on a MONOTONIC
#: clock (time.monotonic, not wall time) so a clock step or a DST change
#: cannot make the nightly run stop early or never stop.
#:
#: 3600s is chosen against task 04's measurement, not guessed: 7.7s p50 /
#: 13.1s p95 per call, and 2.85s/call EFFECTIVE at EXTRACT_MAX_WORKERS=3
#: (DECISIONS.md:331 -- the concurrent figure is the only one this script
#: ever experiences, since it always runs its batches through the pool). One
#: hour is therefore ~1,260 calls, against 43 eligible postings/day measured
#: by task 05 and ~80/day recently. That is roughly 15x headroom on a normal
#: night, and on the abnormal one -- the 6,000-row burn-down after a
#: FACTS_VERSION bump -- it closes the backlog in about five nights instead
#: of the 150 nights the old 40/invocation ceiling needed.
#:
#: The deadline is checked BETWEEN batches, never inside one, so the last
#: batch always finishes and the real ceiling is one batch of overshoot. It
#: is also not checked before the FIRST batch: one batch per invocation is
#: exactly the old behaviour and is the floor this must never fall below.
EXTRACT_DEADLINE_SECS = int(os.environ.get("EXTRACT_DEADLINE_SECS", "3600"))

DEBUG_PRINT_KEYS = os.environ.get("DEBUG_PRINT_KEYS", "") == "1"

#: Per-platform pass counts and the measured agreement they come from. Same
#: shape of indirection relevance.py uses for config/relevance.json: the
#: numbers live in the file, the mechanism lives here.
POLICY_FILE = os.environ.get(
    "JOBS_EXTRACTION_POLICY_FILE",
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "config",
                 "extraction-policy.json"),
)

#: Used when config/extraction-policy.json is absent: one pass for everything,
#: i.e. exactly the behaviour that predates the file. Same choice
#: relevance.DISABLED makes -- a missing config degrades to what the pipeline
#: did before the config existed, never to something more expensive.
#:
#: It degrades SILENTLY, which is the one thing this pipeline cannot afford,
#: so main()'s summary line prints the platforms it will actually vote on
#: (multi_pass=...) on every run. A file that failed to load reads
#: "multi_pass=none" in the nightly log rather than looking like a normal
#: night that happened to cost less.
POLICY_DISABLED = {
    "agreement_threshold": 0.0,
    "passes_below_threshold": 1,
    "default_passes": 1,
    "measured_agreement": {},
}


def load_policy(path=None):
    """The extraction policy from disk, or the one-pass default."""
    try:
        with open(path or POLICY_FILE) as f:
            cfg = json.load(f)
    except FileNotFoundError:
        return dict(POLICY_DISABLED)
    return {**POLICY_DISABLED,
            **{k: v for k, v in cfg.items() if not k.startswith("_")}}


def passes_for(platform, policy=None):
    """How many extraction calls one posting from `platform` is worth.

    Derived from the measured figures rather than stored as a second list of
    platform names, so the config cannot say "hn_whoishiring: 3 passes" next
    to a measurement that no longer justifies it. An UNMEASURED platform gets
    default_passes (1): an unmeasured source is not a bad source, and
    tripling it would be paying for a number nobody has. See the config's
    _default_passes_note.
    """
    policy = load_policy() if policy is None else policy
    agreement = policy["measured_agreement"].get(platform)
    if agreement is None or agreement >= policy["agreement_threshold"]:
        return policy["default_passes"]
    return policy["passes_below_threshold"]

#: Same 3000-char cut score.py used. Kept identical so the two stages see the
#: same text and a fact can always be traced back to something the narrative
#: stage could also have read.
MAX_DESCRIPTION_CHARS = 3000

#: Without all of these a row cannot be matched on, so a response missing any
#: is treated as unusable rather than stored half-empty. Everything else --
#: comp, visa, years -- is genuinely often absent from a posting and NULL is
#: the honest answer.
REQUIRED_FIELDS = ("seniority_level", "role_archetype", "remote_policy",
                   "tech_stack", "summary")

SENIORITY = ("intern", "new_grad", "junior", "mid", "senior", "staff",
             "principal", "director", "exec")
ARCHETYPE = ("backend", "frontend", "fullstack", "ai_integration",
             "ml_research", "forward_deployed", "solutions", "data",
             "devops", "security", "pm", "other")
AI_INVOLVEMENT = ("none", "uses_ai_tools", "builds_llm_features",
                  "core_ml_research")
REMOTE_POLICY = ("onsite", "hybrid", "remote_local", "remote_anywhere",
                 "unknown")
EMPLOYMENT_TYPE = ("full_time", "part_time", "contract", "internship",
                   "unknown")
VISA = ("offered", "not_offered", "unknown")

#: Fixed prefix. Everything above the posting is identical for every call --
#: see the caching note in the module docstring. Edit with that in mind: any
#: change here invalidates the cache for the whole corpus and should come with
#: a schema.FACTS_VERSION bump if it changes the meaning of an answer.
_INSTRUCTIONS = f"""You are extracting structured facts from a job posting. You are NOT judging fit for any candidate -- extract only what the posting itself states or clearly implies.

Respond with ONLY a single JSON object -- no markdown code fences, no explanation before or after.

Use exactly these values for the enumerated fields:
  seniority_level: {" | ".join(SENIORITY)}
  role_archetype: {" | ".join(ARCHETYPE)}
  ai_involvement: {" | ".join(AI_INVOLVEMENT)}
  remote_policy: {" | ".join(REMOTE_POLICY)}
  employment_type: {" | ".join(EMPLOYMENT_TYPE)}
  visa_sponsorship: {" | ".join(VISA)}

Field guidance:
  seniority_level        the level the posting is hiring AT, from its title and requirements -- not the seniority of the team.
  role_archetype         the single closest match. "forward_deployed" means embedded with customers to build solutions; "solutions" means sales/customer-facing technical work; "ai_integration" means building LLM/agent features into a product; "ml_research" means training models or research-scientist work.
  years_experience_min   the smallest number of years the posting requires. null if unstated. Do not invent a number from the seniority level.
  years_experience_max   only if the posting gives a range. null otherwise.
  tech_stack             concrete technologies named in the posting, lowercased. Do not include soft skills, methodologies, or company names. Empty list if none are named.
  ml_research_required   true only if the role genuinely requires research-level ML: publications, training models from scratch, or an advanced ML degree.
  advanced_degree_required  true only if a Master's or PhD is stated as required, not "preferred".
  customer_facing        true if the role routinely works directly with external customers.
  gap_friendly_language  true only if the posting EXPLICITLY welcomes career breaks, returnships, or non-traditional paths. Not merely because it is entry-level.
  comp_min / comp_max    annual base salary in whole units of comp_currency. null if the posting states no salary.
  summary                two neutral sentences describing what the role is. No evaluation, no adjectives about quality.

Respond with exactly this JSON schema (no other text):
{{
  "seniority_level": "<enum>",
  "years_experience_min": <integer or null>,
  "years_experience_max": <integer or null>,
  "role_archetype": "<enum>",
  "tech_stack": ["...", "..."],
  "ai_involvement": "<enum>",
  "ml_research_required": <true or false>,
  "advanced_degree_required": <true or false>,
  "customer_facing": <true or false>,
  "remote_policy": "<enum>",
  "employment_type": "<enum>",
  "comp_min": <integer or null>,
  "comp_max": <integer or null>,
  "comp_currency": "<3-letter code or null>",
  "gap_friendly_language": <true or false>,
  "visa_sponsorship": "<enum>",
  "summary": "<two sentences>"
}}

JOB POSTING TO EXTRACT FROM:
"""


def build_prompt(job):
    description = (job.get("description_text") or "")[:MAX_DESCRIPTION_CHARS]
    return (
        f"{_INSTRUCTIONS}"
        f"Title: {job.get('title')}\n"
        f"Company: {job.get('company_name')}\n"
        f"Location: {job.get('location_raw')}\n"
        f"Source: {job.get('platform')}\n"
        f"Description: {description}"
    )


def _eligible_sql(cfgs, limit=None):
    """The FROM + WHERE that defines "still needs extraction", and its params.

    ONE definition, two callers. select_unextracted_jobs() and remaining()
    have to agree exactly -- remaining() is what the summary line reports as
    the backlog, and a predicate that drifts from the selection would report
    a number no batch will ever burn down. Their docstrings used to promise
    that ("if one changes the other must"); building both from this string
    makes it structural instead of a promise.

    The LEFT JOIN replaces a NOT EXISTS, and does one more thing than
    exclude: it exposes whether a stale facts row exists, which is what
    select_unextracted_jobs() orders on. job_facts.job_id is the PRIMARY KEY
    (schema.py:345), so the join is at most one row per posting and cannot
    fan out -- and given that, "no row at the current version" and "no row at
    all OR a row below the current version" are the same predicate.

    Tombstoned rows (extraction_model LIKE 'FAILED:%') are stored at the
    current version precisely so they do NOT come back here. The version
    comparison rather than a bare "has any facts row" is what makes a schema
    change to job_facts a resumable backlog burn-down: bump FACTS_VERSION and
    yesterday's rows become eligible again, one batch at a time, without a
    TRUNCATE and without losing the rows that are still perfectly good for
    the fields that did not change.
    """
    union, params = relevance.union_sql(cfgs)
    params.update({"status": schema.STATUS_OPEN,
                   "version": schema.FACTS_VERSION})
    if limit is not None:
        params["limit"] = limit
    sql = f"""
        FROM {schema.TABLE} j
        LEFT JOIN {schema.FACTS_TABLE} f ON f.job_id = j.id
        WHERE j.status = %(status)s
          AND coalesce(j.description_text, '') <> ''
          AND {union}
          AND (f.job_id IS NULL OR f.facts_version < %(version)s)
    """
    return sql, params


def select_unextracted_jobs(conn, limit, cfgs):
    """Open, described, union-relevant jobs with no current-version facts.

    ORDERING: never-extracted rows first, then oldest-first within each
    group. It used to be `ORDER BY first_seen DESC`, which CLAUDE.md forbids
    for eval corpora because it is ~85% greenhouse/ashby -- clean ATS
    postings -- and which was making exactly that biased selection in
    production, where it decides which postings are never looked at at all.
    With the drain loop the order is irrelevant in steady state; it decides
    what gets DROPPED whenever the deadline fires, including during task 12's
    full re-extraction.

    Rejected: plain FIFO. After a FACTS_VERSION bump it would make tonight's
    postings queue behind ~5,000 re-extractions, so the freshest postings --
    the only ones anyone is waiting on -- would be the last served. Ordering
    never-extracted rows ahead of stale ones keeps new postings in front
    while FIFO within each group guarantees nothing starves: a row cannot be
    passed over twice for the same reason, because everything ahead of it is
    extracted and leaves the queue.
    """
    where, params = _eligible_sql(cfgs, limit=limit)
    rows = conn.execute(
        f"""
        SELECT j.id, j.title, j.company_name, j.location_raw, j.platform,
               j.description_text
        {where}
        ORDER BY (f.job_id IS NOT NULL), j.first_seen ASC
        LIMIT %(limit)s
        """,
        params,
    ).fetchall()
    cols = ["id", "title", "company_name", "location_raw", "platform",
            "description_text"]
    return [dict(zip(cols, r)) for r in rows]


def remaining(conn, cfgs):
    """How many jobs still need extraction. Same predicate as
    select_unextracted_jobs -- see _eligible_sql, which both are built from."""
    where, params = _eligible_sql(cfgs)
    return conn.execute(f"SELECT count(*) {where}", params).fetchone()[0]


def _enum(value, allowed, default=None):
    """Coerce a model's answer onto a closed vocabulary, or None.

    Tolerates the shapes models actually produce -- "Mid", "mid-level",
    "REMOTE_ANYWHERE" -- because rejecting those would tombstone a perfectly
    good extraction over formatting. Anything still unrecognised becomes the
    default rather than being stored: see the closed-vocabulary note in the
    module docstring.
    """
    if not isinstance(value, str):
        return default
    v = value.strip().lower().replace("-", "_").replace(" ", "_")
    if v in allowed:
        return v
    # "mid_level" -> "mid", "full_time_employee" -> "full_time"
    for a in allowed:
        if v.startswith(a + "_") or v == a.replace("_", ""):
            return a
    return default


def _int_or_none(value, lo=0, hi=1_000_000):
    """Numbers only, in a plausible range. Models answer "5+" and "competitive"."""
    if isinstance(value, bool) or value is None:
        return None
    try:
        n = int(value)
    except (TypeError, ValueError):
        return None
    return n if lo <= n <= hi else None


def normalize(result):
    """Model output -> the exact column values job_facts stores.

    Returns None when the response cannot be used at all, which the caller
    turns into a tombstone.
    """
    if not llm.has_fields(result, REQUIRED_FIELDS):
        return None

    stack = result.get("tech_stack")
    if not isinstance(stack, list):
        stack = []
    stack = sorted({str(t).strip().lower() for t in stack if str(t).strip()})

    summary = result.get("summary")
    summary = summary.strip() if isinstance(summary, str) else None

    seniority = _enum(result.get("seniority_level"), SENIORITY)
    archetype = _enum(result.get("role_archetype"), ARCHETYPE, "other")
    if seniority is None and archetype == "other" and not stack and not summary:
        # Nothing usable came back under any name -- treat as unparseable
        # rather than writing a row that is NULL in every column that matters.
        return None

    yr_min = _int_or_none(result.get("years_experience_min"), 0, 50)
    yr_max = _int_or_none(result.get("years_experience_max"), 0, 50)
    if yr_min is not None and yr_max is not None and yr_max < yr_min:
        yr_min, yr_max = yr_max, yr_min

    return {
        "seniority_level": seniority,
        "years_experience_min": yr_min,
        "years_experience_max": yr_max,
        "role_archetype": archetype,
        "tech_stack": json.dumps(stack),
        "ai_involvement": _enum(result.get("ai_involvement"), AI_INVOLVEMENT,
                                "none"),
        "ml_research_required": bool(result.get("ml_research_required")),
        "advanced_degree_required": bool(result.get("advanced_degree_required")),
        "customer_facing": bool(result.get("customer_facing")),
        "remote_policy": _enum(result.get("remote_policy"), REMOTE_POLICY,
                               "unknown"),
        "employment_type": _enum(result.get("employment_type"),
                                 EMPLOYMENT_TYPE, "unknown"),
        "comp_min": _int_or_none(result.get("comp_min")),
        "comp_max": _int_or_none(result.get("comp_max")),
        "comp_currency": (result.get("comp_currency") or None
                          if isinstance(result.get("comp_currency"), str)
                          else None),
        "gap_friendly_language": bool(result.get("gap_friendly_language")),
        "visa_sponsorship": _enum(result.get("visa_sponsorship"), VISA,
                                  "unknown"),
        "summary": summary,
    }


_FACT_COLUMNS = ("seniority_level", "years_experience_min",
                 "years_experience_max", "role_archetype", "tech_stack",
                 "ai_involvement", "ml_research_required",
                 "advanced_degree_required", "customer_facing",
                 "remote_policy", "employment_type", "comp_min", "comp_max",
                 "comp_currency", "gap_friendly_language", "visa_sponsorship",
                 "summary")


# ---------------------------------------------------------------------------
# THE VOTE
#
# vote_facts() is PURE -- no I/O, no clock, no database, in the spirit of
# match.score_job(). It takes the normalize()d output of N passes and returns
# the one row job_facts should store. Everything that decides an answer is
# therefore unit-testable and sweepable without spending a single LLM call,
# which is the only reason the tie behaviour below can be pinned at all.
#
# It votes on the NORMALIZED dicts, not on raw model JSON. By that point every
# enum has already been coerced onto its closed vocabulary (_enum) and every
# number range-checked (_int_or_none), so "Mid-Level" and "mid" are the same
# vote rather than two. Voting before normalization would count formatting
# differences as disagreement and manufacture instability that is not there.
# ---------------------------------------------------------------------------

#: Plain majority. Values are either a closed-vocabulary string or None, and
#: None VOTES: two passes answering "the posting does not say" outrank one
#: that names a level, which is the honest reading of that evidence.
VOTE_ENUM_FIELDS = ("seniority_level", "role_archetype", "ai_involvement",
                    "remote_policy", "employment_type", "visa_sponsorship",
                    "comp_currency")

#: Plain majority, same rule. normalize() has already forced these through
#: bool(), so there is no None case to handle.
VOTE_BOOL_FIELDS = ("ml_research_required", "advanced_degree_required",
                    "customer_facing", "gap_friendly_language")

#: Median, not majority: three passes reading "3-5 years" as 3, 3 and 4 have
#: no majority answer at all, and a mode would fall back to an arbitrary one.
VOTE_INT_FIELDS = ("years_experience_min", "years_experience_max",
                   "comp_min", "comp_max")

#: NOT voted. Carried whole from one pass -- see _majority_pass_index().
VOTE_CARRIED_FIELDS = ("tech_stack", "summary")


def _majority_value(values):
    """The most common value, ties broken toward the FIRST pass.

    Why the first pass and not "unknown": with three passes a 3-way tie means
    the model gave three different answers and the vote has no information to
    prefer any of them. The first pass's value is exactly what this script
    wrote before voting existed, so the fallback is never worse than the
    behaviour it replaces -- and vote_unanimity records that the row was
    contested, so the tie is visible rather than laundered into a confident
    row. The same loop handles the 2-2 tie an even pass count would produce.
    """
    counts = Counter(values)
    best = max(counts.values())
    for v in values:            # first value that achieves the top count
        if counts[v] == best:
            return v


def _median_value(values):
    """Median of the non-None values; None if None is the majority answer.

    None here means "the posting does not state a number", which is a real
    answer and not a missing one, so it votes: if at least half the passes
    say None the result is None. Otherwise the Nones are dropped and the
    median is taken over what is left -- a pass that failed to spot a salary
    should not drag the two that did.

    On an even count this takes the LOWER of the two middle values rather
    than their mean, so the stored number is always one an extraction pass
    actually produced. Averaging 3 and 5 into 4 would invent a years_min no
    model ever said and no posting contains.
    """
    known = [v for v in values if v is not None]
    if len(known) * 2 <= len(values):
        return None
    known.sort()
    return known[(len(known) - 1) // 2]


def _majority_pass_index(results, voted_enums):
    """Which pass's prose to keep: the first whose enums best match the vote.

    Free text is not votable. Three summaries of the same posting are three
    different sentences, so a per-field majority would find no majority, and
    a per-word or per-token merge would produce prose no pass wrote and no
    posting supports. tech_stack is grouped with it for the same reason at
    one remove: a union would accumulate every hallucinated library across
    three passes, and an intersection would delete a technology two passes
    named because the third did not.

    So the prose is carried WHOLE from a single pass, and the pass chosen is
    the one whose enum vector agrees most with the voted enums -- i.e. the
    pass whose reading of the posting the vote endorsed. That keeps summary
    and tech_stack consistent with the seniority/archetype/ai_involvement the
    row actually stores, instead of describing a reading that was outvoted.
    Ties go to the earliest such pass.
    """
    best_i, best_agreement = 0, -1
    for i, r in enumerate(results):
        agreement = sum(r[f] == voted_enums[f] for f in VOTE_ENUM_FIELDS)
        if agreement > best_agreement:
            best_i, best_agreement = i, agreement
    return best_i


def vote_facts(results):
    """N normalize() dicts -> (the row to store, unanimity fraction or None).

    `results` must be non-empty and must contain no Nones -- an unusable pass
    is dropped by the caller, not voted on, because a failed parse is not
    evidence for any value.

    The unanimity fraction is over the VOTED fields only (enums, booleans and
    integers -- 15 of the 17 columns): the share of them on which every pass
    gave the same value. It is None for a single pass, deliberately. One pass
    agrees with itself trivially, and storing 1.0 for it would make an
    unmeasured row indistinguishable from a genuinely unanimous three-pass
    row in exactly the query task 11 wants to run.
    """
    if not results:
        raise ValueError("vote_facts() needs at least one result")
    if len(results) == 1:
        return dict(results[0]), None

    voted = {}
    unanimous = 0
    for field in VOTE_ENUM_FIELDS + VOTE_BOOL_FIELDS:
        values = [r[field] for r in results]
        voted[field] = _majority_value(values)
        unanimous += len(set(values)) == 1
    for field in VOTE_INT_FIELDS:
        values = [r[field] for r in results]
        voted[field] = _median_value(values)
        unanimous += len(set(values)) == 1

    winner = results[_majority_pass_index(results, voted)]
    for field in VOTE_CARRIED_FIELDS:
        voted[field] = winner[field]

    n_voted = len(VOTE_ENUM_FIELDS) + len(VOTE_BOOL_FIELDS) + len(VOTE_INT_FIELDS)
    return voted, unanimous / n_voted


def update_job_facts(conn, job_id, facts, model_label, passes=1,
                     unanimity=None):
    """Write one job's facts.

    ON CONFLICT DO UPDATE rather than DO NOTHING: re-extraction is a
    deliberate act (a FACTS_VERSION bump, a better model), and the newer
    answer is the one that should stand. match.py notices via facts_version.

    `passes` and `unanimity` are the stability signal, and they describe what
    this row ACTUALLY got rather than what the policy asks for: a three-pass
    platform whose second and third calls were rate-limited stores 1, not 3.
    Writing the intended number would make the column a restatement of
    config/extraction-policy.json instead of a measurement.
    """
    cols = ", ".join(_FACT_COLUMNS)
    placeholders = ", ".join(["%s"] * len(_FACT_COLUMNS))
    updates = ", ".join(f"{c}=EXCLUDED.{c}" for c in _FACT_COLUMNS)
    conn.execute(
        f"""
        INSERT INTO {schema.FACTS_TABLE}
            (job_id, facts_version, {cols}, extracted_at, extraction_model,
             extraction_passes, vote_unanimity)
        VALUES (%s, %s, {placeholders}, %s, %s, %s, %s)
        ON CONFLICT (job_id) DO UPDATE SET
            facts_version=EXCLUDED.facts_version, {updates},
            extracted_at=EXCLUDED.extracted_at,
            extraction_model=EXCLUDED.extraction_model,
            extraction_passes=EXCLUDED.extraction_passes,
            vote_unanimity=EXCLUDED.vote_unanimity
        """,
        (job_id, schema.FACTS_VERSION,
         *[facts[c] for c in _FACT_COLUMNS],
         utc_now_str(), model_label, passes, unanimity),
    )
    conn.commit()


def mark_extract_failed(conn, job_id, model_label):
    """Tombstone at the current facts_version so it is not retried nightly.

    Stored at the current version rather than a sentinel so that a future
    FACTS_VERSION bump gives every tombstoned job one more chance under the
    new prompt -- which is usually exactly what a prompt change is for.
    """
    conn.execute(
        f"""
        INSERT INTO {schema.FACTS_TABLE}
            (job_id, facts_version, extracted_at, extraction_model)
        VALUES (%s, %s, %s, %s)
        ON CONFLICT (job_id) DO UPDATE SET
            facts_version=EXCLUDED.facts_version,
            extracted_at=EXCLUDED.extracted_at,
            extraction_model=EXCLUDED.extraction_model
        """,
        (job_id, schema.FACTS_VERSION, utc_now_str(),
         llm.failed_label(model_label)),
    )
    conn.commit()


#: extract_one_job outcomes. Same three-way split as score.py -- see there.
EXTRACTED, REJECTED, DEFERRED = "extracted", "rejected", "deferred"


def extract_facts(job, policy=None, call=None):
    """Run this posting's passes and vote. No database, no schema, no clock.

    Returns (outcome, facts, passes_used, unanimity). facts is None unless
    the outcome is EXTRACTED. `call` is injectable so the pass COUNT can be
    asserted in a test without spending anything -- the property that one
    platform gets three calls and every other gets exactly one is the whole
    of decision A1, and it is not something to verify by reading the config.

    The three-way outcome is score.py's, generalised over N passes rather
    than changed:

      any pass usable   -> EXTRACTED, voting on the usable ones only. A
                           partial result is kept rather than thrown away:
                           the calls are paid for either way, one good pass
                           is exactly what this script stored before voting
                           existed, and extraction_passes records that this
                           row got fewer than the policy asked for.
      else any transient-> DEFERRED. Nothing written, so it comes back.
      else              -> REJECTED. Every pass answered and none of the
                           answers were usable: that is evidence about the
                           posting, and it earns a tombstone.

    Passes run SEQUENTIALLY inside the worker thread. The pool already runs
    EXTRACT_MAX_WORKERS jobs at once, and fanning each job's passes out again
    would multiply the real concurrency by three against an endpoint whose
    429s are this stage's main failure mode.
    """
    call = call or llm.call
    n = passes_for(job.get("platform"), policy)
    prompt = build_prompt(job)

    usable, transient = [], False
    for _ in range(n):
        try:
            raw = call(prompt)
        except llm.TransientError as e:
            transient = True
            if DEBUG_PRINT_KEYS:
                print(f"[debug] deferring {job['id']} ({job.get('title')!r}): {e}",
                      file=sys.stderr)
            continue
        except (RuntimeError, json.JSONDecodeError) as e:
            if DEBUG_PRINT_KEYS:
                print(f"[debug] extraction call failed for {job['id']}: {e}",
                      file=sys.stderr)
            continue
        facts = normalize(llm.parse_json(raw)) if raw else None
        if facts:
            usable.append(facts)

    if usable:
        facts, unanimity = vote_facts(usable)
        return EXTRACTED, facts, len(usable), unanimity
    if transient:
        return DEFERRED, None, 0, None
    return REJECTED, None, 0, None


def extract_one_job(job, model_label, policy=None):
    """Runs in a worker thread, with its own connection: psycopg connections
    are not safe for concurrent use and search_path is per-connection."""
    outcome, facts, passes, unanimity = extract_facts(job, policy)
    if outcome is DEFERRED:
        return DEFERRED

    conn = dbconn.connect(schema=schema.SCHEMA)
    try:
        if outcome is EXTRACTED:
            update_job_facts(conn, job["id"], facts, model_label, passes,
                             unanimity)
            if DEBUG_PRINT_KEYS:
                print(f"[debug] {job.get('title')!r}: {facts['seniority_level']}/"
                      f"{facts['role_archetype']}/{facts['remote_policy']} "
                      f"({passes} pass(es), unanimity={unanimity})",
                      file=sys.stderr)
            return EXTRACTED

        mark_extract_failed(conn, job["id"], model_label)
        if DEBUG_PRINT_KEYS:
            print(f"[debug] unusable extraction for {job['id']} "
                  f"({job.get('title')!r})", file=sys.stderr)
        return REJECTED
    finally:
        conn.close()


#: Why the drain loop stopped. These three need to stay distinguishable all
#: the way out to run-daily.py's log: "drained" is a finished night,
#: "deadline" is a night that did not keep up with intake, and "no-progress"
#: is an endpoint that is down. Silence is this system's failure mode -- an
#: exhausted key returns zero rows rather than raising -- so the summary line
#: names which of the three happened, on every run, including a clean one.
DRAINED, DEADLINE_HIT, NO_PROGRESS = "drained", "deadline", "no-progress"


def drain_loop(fetch_batch, run_batch, deadline_secs, clock=time.monotonic):
    """Run batches until the backlog is empty, the clock runs out, or a batch
    makes no progress. Returns (Counter of outcomes, batches run, reason).

    Pure control flow: both the fetch and the work arrive as callables, so
    the three stopping conditions are testable without a database, an
    endpoint or a real second passing.

    THE ZERO-PROGRESS BREAK IS THE LOAD-BEARING PART. A DEFERRED row is
    written nowhere and stays eligible, by design -- that is what makes a 429
    retryable rather than a discarded posting. It also means a rate-limited
    or down endpoint re-selects the SAME batch every iteration, so without
    this break the loop would spin until the deadline, hammer an endpoint
    that is already asking it to stop, and make things strictly worse than
    the single batch it replaces. A batch that extracts nothing and rejects
    nothing has learned nothing; stop.

    The deadline is monotonic and is checked between batches only, never
    before the first: one batch per invocation is the old behaviour and the
    floor this must not fall below.
    """
    deadline = clock() + deadline_secs
    totals = Counter()
    batches = 0
    while True:
        if batches and clock() >= deadline:
            return totals, batches, DEADLINE_HIT
        jobs = fetch_batch()
        if not jobs:
            return totals, batches, DRAINED
        outcomes = run_batch(jobs)
        totals += outcomes
        batches += 1
        if outcomes[EXTRACTED] + outcomes[REJECTED] == 0:
            return totals, batches, NO_PROGRESS


def main():
    if not llm.api_key():
        print("job-extract FAILED: JOB_SCORING_API_KEY (or GLM_API_KEY as a "
              "fallback) not set.")
        sys.exit(1)

    mismatch = llm.model_mismatch()
    if mismatch:
        print(f"job-extract FAILED: {mismatch}")
        sys.exit(1)

    conn = dbconn.connect_or_exit("job-extract", schema=schema.SCHEMA)
    schema.ensure_schema(conn)

    active = profiles.load_active(conn)
    if not active:
        print("job-extract: no active profiles -- nothing is waiting on facts.")
        conn.close()
        return

    cfgs = [relevance.for_profile(p) for p in active]
    policy = load_policy()
    endpoint_host = urllib.parse.urlparse(llm.base_url()).hostname or llm.base_url()
    model_label = f"{llm.model()}@{endpoint_host}"
    conn.close()  # each worker opens its own -- see extract_one_job()

    # A CONNECTION PER BATCH, not one held open across the whole drain. These
    # connections are not autocommit, so a single conn.execute() opens a
    # transaction that stays open until the next commit -- and holding one
    # across an hour of LLM calls is precisely the "idle in transaction"
    # zombie that once blocked a run for minutes behind an ACCESS EXCLUSIVE
    # lock (see lib/dbconn.add_missing_columns and DATABASE.md). A handful of
    # connects per night costs nothing next to that.
    def fetch_batch():
        c = dbconn.connect(schema=schema.SCHEMA)
        try:
            return select_unextracted_jobs(c, EXTRACT_BATCH_SIZE, cfgs)
        finally:
            c.close()

    def run_batch(jobs):
        with concurrent.futures.ThreadPoolExecutor(
                max_workers=EXTRACT_MAX_WORKERS) as pool:
            return Counter(pool.map(
                lambda job: extract_one_job(job, model_label, policy), jobs))

    outcomes, batches, stopped = drain_loop(
        fetch_batch, run_batch, EXTRACT_DEADLINE_SECS)
    if not batches:
        return  # nothing to do -- silent, same convention as the ingest scripts

    conn = dbconn.connect(schema=schema.SCHEMA)
    left = remaining(conn, cfgs)
    conn.close()

    # Counted, not assumed: a policy file that failed to load, or a platform
    # renamed out from under it, would silently drop every source back to one
    # pass. This line is where that becomes visible.
    voted = sorted(p for p in policy["measured_agreement"]
                   if passes_for(p, policy) > 1)
    deferred = outcomes[DEFERRED]
    total = sum(outcomes.values())
    print(f"job-extract: {outcomes[EXTRACTED]} extracted, "
          f"{outcomes[REJECTED]} unusable, {deferred} deferred (will retry), "
          f"{left} remaining, stopped={stopped}, batches={batches}, "
          f"profiles={len(active)}, model={model_label}, "
          f"batch_size={EXTRACT_BATCH_SIZE}, workers={EXTRACT_MAX_WORKERS}, "
          f"deadline={EXTRACT_DEADLINE_SECS}s, "
          f"multi_pass={','.join(voted) if voted else 'none'}")

    if stopped == DEADLINE_HIT:
        print(f"  NOTE: stopped on the {EXTRACT_DEADLINE_SECS}s wall-clock "
              f"guard, NOT because the backlog is empty -- {left} posting(s) "
              f"still have no current-version facts. One night is expected "
              f"after a FACTS_VERSION bump; two in a row means intake is "
              f"outrunning extraction and the backlog is growing. Raise "
              f"EXTRACT_DEADLINE_SECS or EXTRACT_MAX_WORKERS.")
    elif stopped == NO_PROGRESS:
        print(f"  NOTE: stopped after a batch that extracted nothing and "
              f"rejected nothing -- every call deferred, so the endpoint is "
              f"rate-limiting or down. Nothing was discarded and {left} "
              f"posting(s) remain; retrying within the same run would only "
              f"re-select the same batch. Lower EXTRACT_MAX_WORKERS "
              f"(currently {EXTRACT_MAX_WORKERS}) if this persists.")
    elif deferred > total / 2:
        print(f"  NOTE: {deferred}/{total} calls never got a response -- "
              f"the endpoint is rate-limiting or down. Nothing was discarded; "
              f"lower EXTRACT_MAX_WORKERS (currently {EXTRACT_MAX_WORKERS}) "
              f"if this persists.")


if __name__ == "__main__":
    main()

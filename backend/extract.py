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

USAGE
    python3 extract.py
    EXTRACT_BATCH_SIZE=40 EXTRACT_MAX_WORKERS=3 python3 extract.py
    DEBUG_PRINT_KEYS=1 python3 extract.py
"""

import os
import sys
import json
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
DEBUG_PRINT_KEYS = os.environ.get("DEBUG_PRINT_KEYS", "") == "1"

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


def select_unextracted_jobs(conn, limit, cfgs):
    """Open, described, union-relevant jobs with no current-version facts.

    The version comparison rather than a bare NOT EXISTS is what makes a
    schema change to job_facts a resumable backlog burn-down: bump
    FACTS_VERSION and yesterday's rows become eligible again, one batch at a
    time, without a TRUNCATE and without losing the rows that are still
    perfectly good for the fields that did not change.

    Tombstoned rows (extraction_model LIKE 'FAILED:%') are stored at the
    current version precisely so they do NOT come back here.
    """
    union, params = relevance.union_sql(cfgs)
    params.update({"status": schema.STATUS_OPEN, "limit": limit,
                   "version": schema.FACTS_VERSION})
    rows = conn.execute(
        f"""
        SELECT j.id, j.title, j.company_name, j.location_raw, j.platform,
               j.description_text
        FROM {schema.TABLE} j
        WHERE j.status = %(status)s
          AND coalesce(j.description_text, '') <> ''
          AND {union}
          AND NOT EXISTS (
                SELECT 1 FROM {schema.FACTS_TABLE} f
                WHERE f.job_id = j.id AND f.facts_version >= %(version)s)
        ORDER BY j.first_seen DESC
        LIMIT %(limit)s
        """,
        params,
    ).fetchall()
    cols = ["id", "title", "company_name", "location_raw", "platform",
            "description_text"]
    return [dict(zip(cols, r)) for r in rows]


def remaining(conn, cfgs):
    """How many jobs still need extraction. Mirrors select_unextracted_jobs's
    WHERE clause -- if one changes the other must."""
    union, params = relevance.union_sql(cfgs)
    params.update({"status": schema.STATUS_OPEN,
                   "version": schema.FACTS_VERSION})
    return conn.execute(
        f"""
        SELECT count(*) FROM {schema.TABLE} j
        WHERE j.status = %(status)s
          AND coalesce(j.description_text, '') <> ''
          AND {union}
          AND NOT EXISTS (
                SELECT 1 FROM {schema.FACTS_TABLE} f
                WHERE f.job_id = j.id AND f.facts_version >= %(version)s)
        """,
        params,
    ).fetchone()[0]


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


def update_job_facts(conn, job_id, facts, model_label):
    """Write one job's facts.

    ON CONFLICT DO UPDATE rather than DO NOTHING: re-extraction is a
    deliberate act (a FACTS_VERSION bump, a better model), and the newer
    answer is the one that should stand. match.py notices via facts_version.
    """
    cols = ", ".join(_FACT_COLUMNS)
    placeholders = ", ".join(["%s"] * len(_FACT_COLUMNS))
    updates = ", ".join(f"{c}=EXCLUDED.{c}" for c in _FACT_COLUMNS)
    conn.execute(
        f"""
        INSERT INTO {schema.FACTS_TABLE}
            (job_id, facts_version, {cols}, extracted_at, extraction_model)
        VALUES (%s, %s, {placeholders}, %s, %s)
        ON CONFLICT (job_id) DO UPDATE SET
            facts_version=EXCLUDED.facts_version, {updates},
            extracted_at=EXCLUDED.extracted_at,
            extraction_model=EXCLUDED.extraction_model
        """,
        (job_id, schema.FACTS_VERSION,
         *[facts[c] for c in _FACT_COLUMNS],
         utc_now_str(), model_label),
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


def extract_one_job(job, model_label):
    """Runs in a worker thread, with its own connection: psycopg connections
    are not safe for concurrent use and search_path is per-connection."""
    conn = dbconn.connect(schema=schema.SCHEMA)
    try:
        try:
            raw = llm.call(build_prompt(job))
        except llm.TransientError as e:
            if DEBUG_PRINT_KEYS:
                print(f"[debug] deferring {job['id']} ({job.get('title')!r}): {e}",
                      file=sys.stderr)
            return DEFERRED
        except (RuntimeError, json.JSONDecodeError) as e:
            if DEBUG_PRINT_KEYS:
                print(f"[debug] extraction call failed for {job['id']}: {e}",
                      file=sys.stderr)
            raw = None

        facts = normalize(llm.parse_json(raw)) if raw else None
        if facts:
            update_job_facts(conn, job["id"], facts, model_label)
            if DEBUG_PRINT_KEYS:
                print(f"[debug] {job.get('title')!r}: {facts['seniority_level']}/"
                      f"{facts['role_archetype']}/{facts['remote_policy']}",
                      file=sys.stderr)
            return EXTRACTED

        mark_extract_failed(conn, job["id"], model_label)
        if DEBUG_PRINT_KEYS:
            print(f"[debug] unusable extraction for {job['id']} "
                  f"({job.get('title')!r})", file=sys.stderr)
        return REJECTED
    finally:
        conn.close()


def main():
    if not llm.api_key():
        print("job-extract FAILED: JOB_SCORING_API_KEY (or GLM_API_KEY as a "
              "fallback) not set.")
        sys.exit(1)

    conn = dbconn.connect_or_exit("job-extract", schema=schema.SCHEMA)
    schema.ensure_schema(conn)

    active = profiles.load_active(conn)
    if not active:
        print("job-extract: no active profiles -- nothing is waiting on facts.")
        conn.close()
        return

    cfgs = [relevance.for_profile(p) for p in active]
    jobs = select_unextracted_jobs(conn, EXTRACT_BATCH_SIZE, cfgs)
    if not jobs:
        conn.close()
        return  # nothing to do -- silent, same convention as the ingest scripts

    left = remaining(conn, cfgs)
    endpoint_host = urllib.parse.urlparse(llm.base_url()).hostname or llm.base_url()
    model_label = f"{llm.model()}@{endpoint_host}"
    conn.close()  # each worker opens its own -- see extract_one_job()

    with concurrent.futures.ThreadPoolExecutor(
            max_workers=EXTRACT_MAX_WORKERS) as pool:
        results = list(pool.map(
            lambda job: extract_one_job(job, model_label), jobs))

    outcomes = Counter(results)
    deferred = outcomes[DEFERRED]
    print(f"job-extract: {outcomes[EXTRACTED]} extracted, "
          f"{outcomes[REJECTED]} unusable, {deferred} deferred (will retry), "
          f"{left - outcomes[EXTRACTED] - outcomes[REJECTED]} remaining, "
          f"profiles={len(active)}, model={model_label}, "
          f"batch_size={EXTRACT_BATCH_SIZE}, workers={EXTRACT_MAX_WORKERS}")
    if deferred > len(results) / 2:
        print(f"  NOTE: {deferred}/{len(results)} calls never got a response -- "
              f"the endpoint is rate-limiting or down. Nothing was discarded; "
              f"lower EXTRACT_MAX_WORKERS (currently {EXTRACT_MAX_WORKERS}) "
              f"if this persists.")


if __name__ == "__main__":
    main()

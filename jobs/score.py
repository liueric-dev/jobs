#!/usr/bin/env python3
"""
LLM-driven job fit scoring -- Postgres edition.

Scores newly-ingested jobs (from ANY source -- ATS, Built In NYC, WWR, HN
Who's Hiring, Google Jobs) against a persona profile
(config/persona.json), producing a fit_score (0-100), a primary_track
classification, a gap_bridging_angle (concrete framing for the application),
key technologies, and risk factors. This is the "surfacing" layer the rest
of the pipeline has been missing -- everything else collects and tags
jobs; this is what actually judges relevance.

SWAPPABLE LLM BACKEND, NO HERMES DEPENDENCY -- REVISED 2026-07-24: this
used to shell out to `hermes -z`. Changed because Eric wants this script
to run standalone on other (SerpApi/Apify worker) machines, which
shouldn't need a full Hermes install/config just to score jobs -- and
Hermes itself was never necessary for swappability, only convenient.
Instead this calls a plain OpenAI-compatible `/chat/completions` endpoint
directly via stdlib urllib -- that wire format is a de facto standard
supported by OpenAI itself, most free-tier cloud providers (Groq,
OpenRouter, etc.), and local model servers (Ollama, LM Studio). Swapping
backends is JOB_SCORING_BASE_URL / JOB_SCORING_API_KEY / JOB_SCORING_MODEL
env vars, not a code change, and this now has zero Hermes dependency --
just Python + psycopg + network access.

WHY THE DEFAULT MODEL IS glm-4.5-flash, NOT glm-4.7 -- A REAL DEAD END
WORTH RECORDING: the account's GLM_API_KEY (already in ~/.hermes/.env)
was assumed to work for whatever model Hermes itself was successfully
using (glm-4.7, per ~/.hermes/config.yaml). Direct calls to
api.z.ai/api/paas/v4/chat/completions with that exact key and "glm-4.7"
returned "Insufficient balance or no resource package" -- yet
`hermes -z -m glm-4.7 --provider zai` kept working throughout the same
session. Never fully root-caused why Hermes's own routing succeeds where
an identical-looking direct call fails (hermes auth's credential pool
listing claims it uses the same GLM_API_KEY env var directly, which makes
the discrepancy stranger, not simpler) -- possibly routed through Nous
Portal's own infrastructure rather than a raw pay-per-token Z.ai account.
What DID get confirmed by testing several model-ID strings against the
same endpoint/key: glm-4.5-flash (the free-tier model) works cleanly via
a plain direct call, including with response_format=json_object. So
that's the default here -- swap JOB_SCORING_MODEL to glm-4.7 (or anything
else) once/if that balance question gets resolved on Z.ai's side directly
(a billing matter, not something fixable in this script).

Tools/function-calling are simply never included in the request body --
unlike the old CLI approach there's no separate flag needed to suppress
them, a bare chat-completions call has no tool-use surface unless you ask
for one.

JSON RELIABILITY: llm.parse_json() still strips markdown fencing and pulls
out the {...} substring rather than requiring the entire response to be
valid JSON -- kept as a tolerant fallback even though response_format
is now requested explicitly on every call (some OpenAI-compatible servers,
especially smaller local ones, either ignore that field or honor it
loosely).

FAILURE HANDLING: a job whose scoring call fails or returns unparseable
JSON still gets scored_at set (with scoring_model="FAILED:<label>" and
fit_score left NULL) rather than being left alone -- otherwise it would
get retried, and fail, on every single future run forever. Same lesson as
ingest/hn-hiring.py's hn_seen_comments tombstone table: a permanent
failure needs a permanent marker, not silent endless retry.

COST/VOLUME CONTROL: SCORE_BATCH_SIZE caps how many unscored jobs get
scored per run (default 30) -- newest jobs first (ORDER BY first_seen
DESC), so a capped batch always prioritizes the freshest postings over
working through a backlog. Raise this once a model/cost combination is
trusted.

CONCURRENT SCORING -- WHY: measured directly (2026-07-24) against the
current default endpoint -- three identical, trivial requests took 17s,
4.6s, and 29s respectively. That's not prompt size, it's the free-tier
endpoint itself (almost certainly queued/deprioritized behind paid
traffic). Scoring jobs one at a time, sequentially, made that latency
additive: 30 jobs x ~17s average is 8-9 minutes for this one step alone.
Each job's scoring call is fully independent (no shared state, no
ordering requirement between jobs), so score_one_job() runs under a
ThreadPoolExecutor with SCORE_MAX_WORKERS (default 5) concurrent workers
instead -- wall-clock time drops roughly proportionally to the worker
count, bounded by whatever concurrency the endpoint itself tolerates
before rate-limiting. Each worker opens its OWN psycopg connection rather
than sharing the main() connection -- psycopg connections aren't safe for
concurrent use across threads, and a fresh connection per job is cheap
enough at this volume that it's not worth a connection pool. Raise
SCORE_MAX_WORKERS if the endpoint tolerates more concurrency; lower it if
a burst of requests starts getting rate-limited (a 429 just surfaces as a
per-job failure -- marked FAILED per the tombstone lesson below, not a
crashed run -- but a lower worker count avoids manufacturing those in the
first place).

DEPENDENCY: psycopg (same as ingest/ats.py). No LLM SDK, no Hermes --
stdlib urllib against a plain HTTPS JSON endpoint.

INSTALL: lives in ~/.hermes/scripts/jobs/ alongside config/persona.json.
Portable to other machines -- just needs Python, psycopg, network access
to both Postgres and whatever LLM endpoint is configured, and the three
JOB_SCORING_* env vars below (or their fallback defaults).

DATABASE: same Postgres instance/schema as ingest/ats.py. Adds columns to
the existing jobs.jobs table via ALTER TABLE ADD COLUMN IF NOT EXISTS
(CREATE TABLE IF NOT EXISTS is a no-op on an existing table and would
silently skip these -- explicit ALTERs are required for schema changes on
a table other scripts already created, per nyc-events-ingest.py precedent).

CONFIG:
    DATABASE_URL             -- postgres connection string
    JOB_SCORING_BASE_URL     -- OpenAI-compatible API base (default:
                                "https://api.z.ai/api/paas/v4" -- the
                                already-working Z.ai endpoint on this
                                machine). Point at a local Ollama/LM Studio
                                server, Groq, OpenRouter, etc. to swap.
    JOB_SCORING_MODEL        -- model id sent in the request body (default:
                                "glm-4.5-flash" -- see WHY THE DEFAULT MODEL
                                above for why not glm-4.7).
    JOB_SCORING_API_KEY      -- bearer token for JOB_SCORING_BASE_URL.
                                Falls back to GLM_API_KEY (already in
                                ~/.hermes/.env) if unset, since that's the
                                credential the default base_url/model
                                actually needs on this machine -- set this
                                explicitly on any other machine/provider.
    JOB_SCORING_PERSONA_FILE -- path to config/persona.json (default:
                                alongside this script)
    SCORE_BATCH_SIZE         -- how many unscored jobs to score per run
                                (default 30)

SCHEDULE: not scheduled directly -- see run-daily.py, which runs
this as the final step, after all ingestion sources.

TEST BEFORE SCHEDULING:
    python3 score.py
    DEBUG_PRINT_KEYS=1 python3 score.py
    JOB_SCORING_BASE_URL=http://localhost:11434/v1 JOB_SCORING_MODEL=llama3.1 \\
        JOB_SCORING_API_KEY=unused DEBUG_PRINT_KEYS=1 python3 score.py
"""

import os
import sys
import json
import urllib.error
import urllib.parse
import concurrent.futures
from collections import Counter

_d = os.path.dirname(os.path.abspath(__file__))
while _d != os.path.dirname(_d) and not os.path.isdir(os.path.join(_d, "pipelib")):
    _d = os.path.dirname(_d)
sys.path.insert(0, _d)
sys.path.insert(0, os.path.join(_d, "jobs"))

import schema  # noqa: E402  (jobs/schema.py)
import relevance  # noqa: E402  (jobs/relevance.py)
from pipelib import dbconn, llm  # noqa: E402
from pipelib.timeparse import utc_now_str  # noqa: E402

PERSONA_FILE = os.environ.get(
    "JOB_SCORING_PERSONA_FILE",
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "config/persona.json"),
)
SCORE_BATCH_SIZE = int(os.environ.get("SCORE_BATCH_SIZE", "30"))
SCORE_MAX_WORKERS = int(os.environ.get("SCORE_MAX_WORKERS", "5"))
DEBUG_PRINT_KEYS = os.environ.get("DEBUG_PRINT_KEYS", "") == "1"

REQUIRED_FIELDS = (
    "fit_score", "primary_track", "gap_friendly_signal",
    "key_technologies", "gap_bridging_angle", "risk_factors",
)


def load_persona():
    with open(PERSONA_FILE) as f:
        return json.load(f)


def select_unscored_jobs(conn, limit, profile, rel_cfg=None):
    """Open, relevant, not-yet-scored-for-this-profile jobs -- best tier first.

    Two filters, doing different jobs:

    The anti-join is against (job_id, profile), not "is this job scored at
    all" -- a job scored under a different persona is still unscored here.
    That is the whole reason job_scores is keyed by profile; see SCORES ARE
    PER PROFILE in schema.py.

    The tier gate stops the batch being spent on postings this persona would
    never apply to. Ordering is (tier, first_seen DESC) rather than
    first_seen alone, so a fresh irrelevant posting never outranks a slightly
    older relevant one -- which is exactly what the unfiltered version did,
    every night, while the real backlog aged out. See jobs/relevance.py.

    The description gate is the third: a row with no description_text gives
    the model nothing but a title, a company and a location to judge on, and
    the answer it invents from that is worse than no answer -- it gets stored
    as if it were real, and the anti-join then treats the job as done.

    This is not hypothetical. Every builtin row carried an empty description
    (see ingest/builtin-nyc.py) and, being the newest tier-1 rows, they sorted
    to the front of every batch. Rows become eligible on their own once the
    description lands, so nothing is lost by skipping them -- and no tombstone
    is written, because none of them was ever evaluated.
    """
    cfg = rel_cfg if rel_cfg is not None else relevance.load()
    tier_expr, tier_params = relevance.tier_sql(cfg)
    params = {"status": schema.STATUS_OPEN, "profile": profile,
              "max_tier": relevance.max_tier(cfg), "limit": limit,
              **tier_params}
    rows = conn.execute(
        f"""
        SELECT j.id, j.title, j.company_name, j.location_raw, j.platform,
               j.description_text, {tier_expr} AS tier
        FROM {schema.TABLE} j
        WHERE j.status = %(status)s
          AND coalesce(j.description_text, '') <> ''
          AND NOT EXISTS (SELECT 1 FROM {schema.SCORES_TABLE} s
                          WHERE s.job_id = j.id AND s.profile = %(profile)s)
          AND {tier_expr} <= %(max_tier)s
        ORDER BY tier, j.first_seen DESC
        LIMIT %(limit)s
        """,
        params,
    ).fetchall()
    cols = ["id", "title", "company_name", "location_raw", "platform",
            "description_text", "tier"]
    return [dict(zip(cols, r)) for r in rows]


def build_prompt(persona, job):
    buckets_text = "\n".join(
        f"- {name}: {b['description']} ({b['fit_signal']})"
        for name, b in persona["buckets"].items()
    )
    strengths_text = "\n".join(f"- {s}" for s in persona["strengths"])
    gaps_text = "\n".join(f"- {g}" for g in persona["honest_gaps"])
    description = (job.get("description_text") or "")[:3000]

    return f"""You are evaluating a job posting for fit against a specific candidate's background. Respond with ONLY a single JSON object -- no markdown code fences, no explanation before or after.

CANDIDATE BACKGROUND:
{persona['background_summary']}

STRENGTHS:
{strengths_text}

HONEST GAPS:
{gaps_text}

POSITIONING BUCKETS:
{buckets_text}

SCORING INSTRUCTIONS:
{persona['scoring_instructions']}

JOB POSTING TO EVALUATE:
Title: {job.get('title')}
Company: {job.get('company_name')}
Location: {job.get('location_raw')}
Source: {job.get('platform')}
Description: {description}

Respond with exactly this JSON schema (no other text):
{{
  "fit_score": <integer 0-100>,
  "primary_track": "<one of: Core SWE, AI Integration, Bridge & Solutions, Re-Entry & Growth, Poor Fit>",
  "gap_friendly_signal": <true or false>,
  "key_technologies": ["...", "..."],
  "gap_bridging_angle": "<1-2 concrete sentences specific to this posting>",
  "risk_factors": ["...", "..."]
}}"""


def update_job_score(conn, job_id, profile, result, model_label):
    """Write one (job, profile) score.

    ON CONFLICT DO UPDATE rather than DO NOTHING: re-scoring an already-scored
    job is a deliberate act (a new model, a revised persona under the same
    profile name), and the newer answer is the one that should stand.
    """
    conn.execute(
        f"""
        INSERT INTO {schema.SCORES_TABLE}
            (job_id, profile, fit_score, primary_track, gap_friendly_signal,
             key_technologies, gap_bridging_angle, risk_factors,
             scored_at, scoring_model)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (job_id, profile) DO UPDATE SET
            fit_score=EXCLUDED.fit_score,
            primary_track=EXCLUDED.primary_track,
            gap_friendly_signal=EXCLUDED.gap_friendly_signal,
            key_technologies=EXCLUDED.key_technologies,
            gap_bridging_angle=EXCLUDED.gap_bridging_angle,
            risk_factors=EXCLUDED.risk_factors,
            scored_at=EXCLUDED.scored_at,
            scoring_model=EXCLUDED.scoring_model
        """,
        (
            job_id,
            profile,
            result.get("fit_score"),
            result.get("primary_track"),
            bool(result.get("gap_friendly_signal")),
            json.dumps(result.get("key_technologies") or []),
            result.get("gap_bridging_angle"),
            json.dumps(result.get("risk_factors") or []),
            utc_now_str(),
            model_label,
        ),
    )
    conn.commit()


def mark_score_failed(conn, job_id, profile, model_label):
    """Permanent marker for a failed/unparseable scoring attempt -- without
    this, a job that fails once gets retried (and fails) on every future
    run forever. Same lesson as ingest/hn-hiring.py's hn_seen_comments
    tombstone table.

    The tombstone is per profile too: a job that one persona failed to score
    is still worth attempting for another."""
    conn.execute(
        f"""
        INSERT INTO {schema.SCORES_TABLE} (job_id, profile, scored_at, scoring_model)
        VALUES (%s, %s, %s, %s)
        ON CONFLICT (job_id, profile) DO UPDATE SET
            scored_at=EXCLUDED.scored_at, scoring_model=EXCLUDED.scoring_model
        """,
        (job_id, profile, utc_now_str(), llm.failed_label(model_label)),
    )
    conn.commit()


#: score_one_job outcomes.
SCORED, REJECTED, DEFERRED = "scored", "rejected", "deferred"


def score_one_job(job, persona, profile, model_label):
    """Runs inside a worker thread -- opens its own connection rather than
    sharing one across threads (psycopg connections aren't safe for
    concurrent use).

    Returns SCORED, REJECTED (the model answered but the answer was unusable
    -- tombstoned, never retried) or DEFERRED (the endpoint never gave us an
    answer -- nothing written, retried next run).

    That three-way split matters more than it looks. Tombstoning is right for
    a model that cannot produce parseable JSON for a given posting: retrying
    forever would burn a call a night on the same failure. It is badly wrong
    for an HTTP 429, which says nothing about the posting -- and the current
    default model rate-limits hard enough that a batch can be mostly 429s.
    Recording those as failures silently and permanently discards jobs that
    were never actually evaluated.
    """
    # search_path is per-connection, so a worker's fresh connection needs it
    # set again -- dbconn.connect(schema=...) does that for every connection
    # it hands out, which is what makes the threaded case correct by
    # construction instead of by remembering.
    conn = dbconn.connect(schema=schema.SCHEMA)
    try:
        prompt = build_prompt(persona, job)
        try:
            raw = llm.call(prompt)
        except llm.TransientError as e:
            if DEBUG_PRINT_KEYS:
                print(f"[debug] deferring {job['id']} ({job.get('title')!r}): {e}",
                      file=sys.stderr)
            return DEFERRED
        except (RuntimeError, json.JSONDecodeError) as e:
            # A definite answer we can't use (4xx, malformed envelope).
            if DEBUG_PRINT_KEYS:
                print(f"[debug] scoring call failed for {job['id']} ({job.get('title')!r}): {e}",
                      file=sys.stderr)
            raw = None

        result = llm.parse_json(raw) if raw else None

        if llm.has_fields(result, REQUIRED_FIELDS):
            update_job_score(conn, job["id"], profile, result, model_label)
            if DEBUG_PRINT_KEYS:
                print(f"[debug] {job.get('title')!r} @ {job.get('company_name')}: "
                      f"fit={result.get('fit_score')} track={result.get('primary_track')!r}",
                      file=sys.stderr)
            return SCORED

        mark_score_failed(conn, job["id"], profile, model_label)
        if DEBUG_PRINT_KEYS:
            print(f"[debug] unparseable/invalid result for {job['id']} ({job.get('title')!r})",
                  file=sys.stderr)
        return REJECTED
    finally:
        conn.close()


def main():
    if not llm.api_key():
        print("job-score FAILED: JOB_SCORING_API_KEY (or GLM_API_KEY as a fallback) not set.")
        sys.exit(1)

    conn = dbconn.connect_or_exit("job-score", schema=schema.SCHEMA)
    schema.ensure_schema(conn)

    try:
        persona = load_persona()
    except (OSError, json.JSONDecodeError, KeyError) as e:
        print(f"job-score FAILED: could not load {PERSONA_FILE}: {e}")
        conn.close()
        sys.exit(1)

    profile = schema.resolve_profile(persona)
    rel_cfg = relevance.load()
    jobs = select_unscored_jobs(conn, SCORE_BATCH_SIZE, profile, rel_cfg)
    if not jobs:
        conn.close()
        return  # nothing to score -- stay silent, same convention as the other scripts

    endpoint_host = urllib.parse.urlparse(llm.base_url()).hostname or llm.base_url()
    model_label = f"{llm.model()}@{endpoint_host}"
    conn.close()  # each worker opens its own connection -- see score_one_job()

    with concurrent.futures.ThreadPoolExecutor(max_workers=SCORE_MAX_WORKERS) as pool:
        results = list(pool.map(
            lambda job: score_one_job(job, persona, profile, model_label), jobs))

    outcomes = Counter(results)
    tiers = ",".join(f"t{t}={n}" for t, n in sorted(
        Counter(j["tier"] for j in jobs).items()))
    deferred = outcomes[DEFERRED]
    print(f"job-score: {outcomes[SCORED]} scored, {outcomes[REJECTED]} unparseable, "
          f"{deferred} deferred (will retry), "
          f"profile={profile}, tiers[{tiers}], model={model_label}, "
          f"batch_size={SCORE_BATCH_SIZE}, workers={SCORE_MAX_WORKERS}")
    if deferred > len(results) / 2:
        # Worth saying out loud: the run "succeeded" but mostly did nothing,
        # and the usual cause is SCORE_MAX_WORKERS outpacing the endpoint.
        print(f"  NOTE: {deferred}/{len(results)} calls never got a response -- "
              f"the endpoint is rate-limiting or down. Nothing was discarded; "
              f"lower SCORE_MAX_WORKERS (currently {SCORE_MAX_WORKERS}) if this persists.")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
The narrative tier: why THIS posting, for THIS person.

WHAT THIS STOPPED DOING
    This script used to be the whole scoring pipeline -- one LLM call per
    (job, profile), over every relevant posting. That is the only part of the
    old design that scaled with corpus size AND user count, and at 100
    profiles it is ~11,500 calls a day with a four-hour wait before a new
    profile sees anything.

    Ranking now happens in match.py, for free, from the facts extract.py
    pulled out of each posting once. What is left here is the part that
    genuinely needs a model to have read both the posting and the persona:
    gap_bridging_angle, risk_factors, and a fit_score that annotates the
    shortlist. Everything it is asked about is already in the top 20 for
    someone, so the call is spent on jobs a person will actually look at.

    Consequence for cost: this is bounded by what gets SHOWN, not by how many
    jobs exist. Adding a profile costs `daily_narrative_budget` calls a day
    that they are active, and nothing at all while they are not.

IT DOES NOT RANK. match_score DOES.
    fit_score is displayed as a refinement and must never be used to order a
    list. The moment ordering depends on it, every job a user might see needs
    an LLM call before it can be placed -- which is the property this split
    exists to remove. See the SCORING IS TWO TIERS note in schema.py.

VERSIONS ARE CACHE KEYS, AND RE-SCORING IS OPT-IN
    Every job_scores row records the four inputs that decided its narrative:
    facts_version (the job_facts row the facts block was built from),
    persona_sha (a digest of exactly the five persona keys build_prompt
    reads), prompt_version (schema.SCORE_PROMPT_VERSION) and scoring_model,
    which already existed. CLAUDE.md's rule -- a derived row records the
    version of everything upstream, and is stale iff any RECORDED version
    differs from current -- only now applies to this table: it shipped with
    no cache keys at all, so re-scoring fired solely on "no row exists".

    THREE OF THE FOUR ARE IN THE PREDICATE: facts_version, persona_sha and
    prompt_version. criteria_version is recorded and deliberately excluded.
    select_shortlist reads m.match_score and m.match_reasons, but
    build_prompt and _facts_block never do, so criteria decides WHICH jobs
    are asked about and never WHAT is asked; a weight edit that reorders the
    shortlist does not change one word of any prompt. It is stored anyway
    because L2 analysis of job_events has to know which weight generation
    ordered the list a user actually saw. The exclusion is enforced by
    tests/test_score_versions.py, not by this paragraph.

    scoring_model is not in the predicate either, for a different reason: a
    model swap is an operator decision with a known price, and
    scripts/backfill-scores.py:144-152 already expresses it as a deliberate
    delete-by-model. Putting it in the staleness predicate would turn
    editing a JOB_SCORING_MODEL env var into a four-figure call count.

    NO VERSION CHANGE EVER AUTOMATICALLY SPENDS A CALL, and everything above
    is arranged to keep that true. A stale row is inert: it becomes eligible
    only under --rescore-stale or --rescore-unversioned, each of which
    requires an explicit --limit, and run-daily.py passes neither -- see the
    comment on its score.py step, which is the one place the nightly spend is
    decided. --stale-report answers "what would it cost" and is handled
    before the credential check, so it runs on a machine with no API key.

    UNVERSIONED IS A THIRD STATE, NOT STALE. The columns are nullable with no
    DEFAULT and nothing backfills them, so every row written before they
    existed is NULL on all three. The predicate uses `<>` behind an explicit
    IS NOT NULL guard rather than IS DISTINCT FROM, precisely because IS
    DISTINCT FROM treats NULL as "differs" and would have marked all 1,293
    pre-existing rows stale the instant the column landed. NULL is not
    version 0, it is "nobody recorded it" -- reported as its own census
    bucket and reachable only through its own flag.

    facts_version COMPARES TO THE JOINED ROW, NOT schema.FACTS_VERSION. A
    narrative is stale when the facts IT READ have since changed. Comparing
    against the global constant would instead mark a score stale because
    EXTRACTION is behind, which is extract.py's backlog to burn down and
    would make all 5,029 v2 rows permanently and pointlessly stale here.

    KNOWN GAP, NAMED SO IT IS NOT MISREAD AS COVERED: title, company_name
    and location_raw reach the prompt from the `jobs` table (_facts_block)
    and are versioned by nothing at all. A posting re-titled in place
    silently invalidates its narrative and no version column notices. Out of
    scope -- there is no jobs-row version to compare against -- but it is a
    real hole in "the prompt's inputs are exactly four".

THE PROMPT READS FACTS, NOT THE POSTING
    Stage 2 already distilled each posting into structured facts plus a
    neutral two-sentence summary, so this sends those instead of the
    3,000-char description. Same persona, much smaller variable part, and
    the persona prefix still caches across a profile's whole batch -- which
    is why run_for_profile does one profile at a time rather than
    interleaving them.

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

A GLM CREDENTIAL DEAD END, KEPT FOR THE REASONING -- NOT A STATEMENT OF
WHAT RUNS TODAY: this pipeline's DEFAULT_MODEL is now deepseek-v4-flash
(see llm.py), pinned once a paid endpoint was confirmed working. glm
never became the default for a business reason, only a credential one,
recorded here in case it comes up again: the account's GLM_API_KEY (in
./.env, and also still in ~/.hermes/.env for the harness's own use) was
assumed to work for whatever model Hermes itself was successfully
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
a plain direct call, including with response_format=json_object -- proof
the structured-output path works against a real OpenAI-compatible
endpoint, independent of which model ends up pinned. glm-4.5-flash is
still a fine fallback if the deepseek endpoint or its balance ever falls
over; the balance question itself is billing, not something fixable here.

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

COST/VOLUME CONTROL: each profile's daily_narrative_budget (jobs.profiles,
default 20) caps how many narratives it gets per run, and the shortlist is
ordered by match_score, so a capped batch spends its calls on the
highest-ranked postings rather than merely the freshest. SCORE_BATCH_SIZE
is no longer the limit -- it survives only as a fallback for callers that
do not pass one.

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

INSTALL: lives in ~/apps/jobs/backend alongside config/persona.json.
Portable to other machines -- just needs Python, psycopg, network access
to both Postgres and whatever LLM endpoint is configured, and the three
JOB_SCORING_* env vars below (or their fallback defaults).

DATABASE: the same `jobs` database as ingest/ats.py, everything in its
`public` schema (since slice E of the reorg; these tables used to be a `jobs`
schema inside the events database). Reads job_matches (the ranking) joined to
job_facts (the posting, as facts) and writes job_scores keyed
(job_id, profile). Scores have not lived on the `jobs` table since the
job_scores migration; personas have not lived in config/persona.json since the
profiles migration.

CONFIG:
    DATABASE_URL             -- postgres connection string
    JOB_SCORING_BASE_URL     -- OpenAI-compatible API base (default:
                                "https://api.z.ai/api/paas/v4" -- the
                                already-working Z.ai endpoint on this
                                machine). Point at a local Ollama/LM Studio
                                server, Groq, OpenRouter, etc. to swap.
    JOB_SCORING_MODEL        -- model id sent in the request body. Defaults
                                to llm.DEFAULT_MODEL ("deepseek-v4-flash",
                                the production pin -- see llm.py's module
                                comment). See the GLM CREDENTIAL DEAD END
                                section above for a still-relevant quirk if
                                this ever points back at a glm model.
    JOB_SCORING_API_KEY      -- bearer token for JOB_SCORING_BASE_URL.
                                Falls back to GLM_API_KEY (in ./.env) if
                                unset, since that's the
                                credential the default base_url/model
                                actually needs on this machine -- set this
                                explicitly on any other machine/provider.
    JOB_SCORING_PERSONA_FILE -- path to config/persona.json (default:
                                alongside this script)
    JOBS_EXPECTED_MODEL      -- if set, this stage refuses to start unless
                                the resolved model equals it exactly. See
                                llm.model_mismatch().
    SCORE_BATCH_SIZE         -- how many unscored jobs to score per run
                                (default 30)

RE-SCORING, WHICH COSTS MONEY AND SO IS NEVER AUTOMATIC:
    python3 score.py --stale-report              # free: no call, no write
    python3 score.py --rescore-stale --limit 50
    python3 score.py --rescore-unversioned --limit 50

SCHEDULE: not scheduled directly -- see run-daily.py, which runs
this as the final step, after all ingestion sources.

TEST BEFORE SCHEDULING:
    python3 score.py
    DEBUG_PRINT_KEYS=1 python3 score.py
    JOB_SCORING_BASE_URL=http://localhost:11434/v1 JOB_SCORING_MODEL=llama3.1 \\
        JOB_SCORING_API_KEY=unused DEBUG_PRINT_KEYS=1 python3 score.py
"""

import os
import re
import sys
import json
import hashlib
import argparse
import urllib.error
import urllib.parse
import concurrent.futures
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import schema  # schema.py
import profiles  # profiles.py
import llm  # llm.py
from lib import dbconn, pipelinelog
from lib.timeparse import utc_now_str

log = pipelinelog.get_logger("score")

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

#: The primary_track vocabulary, in the EXACT form job_scores stores.
#:
#: TITLE CASE IS THE STORED FORM AND THAT IS A DECISION, NOT AN ACCIDENT.
#: extract.py's vocabularies are snake_case, so extract._enum() lowercases and
#: replaces separators with underscores. Passing these five through it would
#: map "Core SWE" -> "core_swe" and silently rewrite every value already in
#: job_scores -- 1,231 rows as of 2026-07-28. Changing the stored form is a
#: migration with a reader to update (schema.py:628 selects s.primary_track);
#: normalising is not. So _track() canonicalises only for COMPARISON and
#: returns the display form from this tuple.
#:
#: Kept in the same order as the prompt's schema line (build_prompt below), so
#: a track added to one and not the other is visible in a diff.
#:
#: OQ-8, decided 2026-08-03: THIS TUPLE IS NOT GETTING PURSUIT-DESCRIBING
#: NAMES. Two of these five values -- "Re-Entry & Growth" and "Poor Fit" --
#: are fit judgments, not job families, which is a tell that this is the
#: original single-user job search's vocabulary rather than a role taxonomy.
#: Renaming it to something Pursuit-shaped (e.g. "AI Integration" ->
#: "AI Engineer/Integration") would be exactly the invented narrowness
#: config/pursuit-persona.json's `_population_not_person_comment` warns
#: against: the cohort has no single target role. The role-shaped label
#: belongs on a different axis entirely -- extract.ROLE_TRACK, which is
#: per-job rather than per-profile, already has nine cluster-derived slugs
#: with hand-written plain-language copy (config/search-queries.json), and is
#: already live end-to-end (webapp/jobs.py's LIST_COLUMNS, frontend fixtures).
#: This tuple stays as-is and stays dead code for pursuit, where
#: daily_narrative_budget is 0.
TRACKS = ("Core SWE", "AI Integration", "Bridge & Solutions",
          "Re-Entry & Growth", "Poor Fit")


def load_persona():
    """The seed persona from disk.

    Retained for tools/cost-test.py and tools/compare-models.py, which measure
    a prompt without needing a database profile. The pipeline reads personas
    from jobs.profiles via profiles.py -- a file cannot describe more than one
    user.
    """
    with open(PERSONA_FILE) as f:
        return json.load(f)


#: The persona keys build_prompt() actually reads. Nothing else about a user
#: reaches any prompt in this pipeline, which is what makes a digest of these
#: five a complete pin on the persona half of the input.
PERSONA_PROMPT_KEYS = ("background_summary", "strengths", "honest_gaps",
                       "buckets", "scoring_instructions")


def persona_sha(persona):
    """Digest of the five keys build_prompt() reads. Nothing else.

    EDIT THIS AND build_prompt TOGETHER. build_prompt defines the field set;
    PERSONA_PROMPT_KEYS only records it. A key the prompt starts reading and
    this does not digest is a persona edit that changes every narrative and
    marks nothing stale -- silently, which is this system's failure mode.

    Deliberately not a digest of the whole persona blob: `_comment`,
    `display_name` and `profile` do not reach a prompt, and a digest that
    changed when someone fixed a typo in a comment would train people to
    ignore it -- and, now that it is a cache key, would offer to re-score a
    profile's whole shortlist over a comment.

    Lives here rather than in evals/tasks/score.py, where it started, because
    the pipeline must not import from the eval harness. The harness imports
    the pipeline and re-exports this, which keeps the dependency pointing the
    way it already pointed.
    """
    material = {k: persona.get(k) for k in PERSONA_PROMPT_KEYS}
    blob = json.dumps(material, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class ScoreContext:
    """Everything a narrative is written under, carried as one value.

    Built once per profile in run_for_profile and threaded through
    score_one_job to the writers, which take it INSTEAD of a bare
    (profile, model_label) pair. That is the point: there is no longer a way
    to write a job_scores row without also recording the versions it was
    written under, in the same way update_job_score cannot be handed a raw
    model response (D15). A provenance column that a caller may pass or
    forget is a column that will be NULL on the row someone needs it for.

    facts_version is NOT here. It is a property of the posting's job_facts
    row, not of the run, and it differs per job -- see select_shortlist,
    which returns it, and the writers, which take it separately.
    """
    profile: str
    persona: dict
    model_label: str
    persona_sha: str
    prompt_version: int
    criteria_version: int


def context_for(profile_obj, model_label=None):
    """The ScoreContext for one profile. The only place one is constructed.

    model_label defaults to the resolved endpoint, which needs no credential
    -- so --stale-report can build a context on a machine with no API key.
    """
    if model_label is None:
        host = urllib.parse.urlparse(llm.base_url()).hostname or llm.base_url()
        model_label = f"{llm.model()}@{host}"
    return ScoreContext(
        profile=profile_obj.profile,
        persona=profile_obj.persona,
        model_label=model_label,
        persona_sha=persona_sha(profile_obj.persona),
        prompt_version=schema.SCORE_PROMPT_VERSION,
        criteria_version=profile_obj.criteria_version,
    )


#: The staleness arms of select_shortlist's WHERE, shared with stale_census so
#: the report and the selection can never disagree about what "stale" means.
#:
#: `<>` BEHIND AN IS NOT NULL GUARD, NOT `IS DISTINCT FROM`. The latter treats
#: NULL as "differs", which would have marked all 1,293 rows written before
#: these columns existed stale the instant the migration landed. CLAUDE.md
#: says a row is stale iff any RECORDED version differs from current, and a
#: NULL is not a recorded version -- unversioned is a third state with its own
#: bucket and its own flag.
#:
#: f.facts_version is THE JOINED ROW, never schema.FACTS_VERSION: a score is
#: stale when the facts it read have since changed, not because extraction is
#: behind on some other posting.
_STALE_FACTS = "(s.facts_version  IS NOT NULL AND s.facts_version  <> f.facts_version)"
_STALE_PERSONA = "(s.persona_sha    IS NOT NULL AND s.persona_sha    <> %(persona_sha)s)"
_STALE_PROMPT = "(s.prompt_version IS NOT NULL AND s.prompt_version <> %(prompt_version)s)"
_STALE_ANY = f"({_STALE_FACTS} OR {_STALE_PERSONA} OR {_STALE_PROMPT})"

#: A row that exists and records nothing. Never stale, by the rule above.
_UNVERSIONED = ("(s.job_id IS NOT NULL AND s.persona_sha IS NULL "
                "AND s.prompt_version IS NULL AND s.facts_version IS NULL)")

#: A failed-scoring marker. coalesce because scoring_model is nullable and
#: `NULL NOT LIKE ...` is NULL, not true -- a row with no model recorded would
#: otherwise fall into no census bucket at all and the counts would stop
#: summing to the population.
_TOMBSTONE = "(coalesce(s.scoring_model, '') LIKE %(failed)s)"

#: The population every version query runs over: this profile's ranked, open,
#: extracted postings. The same FROM for selection and for the census, so the
#: report cannot promise rows that selection would not return.
_SHORTLIST_FROM = """
        FROM {matches} m
        JOIN {jobs} j ON j.id = m.job_id
        JOIN {facts} f ON f.job_id = m.job_id
        LEFT JOIN {scores} s ON s.job_id = m.job_id AND s.profile = %(profile)s
        WHERE m.profile = %(profile)s
          AND j.status = %(status)s
"""


def _shortlist_from():
    return _SHORTLIST_FROM.format(
        matches=schema.MATCHES_TABLE, jobs=schema.TABLE,
        facts=schema.FACTS_TABLE, scores=schema.SCORES_TABLE)


def select_shortlist(conn, limit, profile, *, versions=None,
                     include_stale=False, include_unversioned=False):
    """The top-ranked postings this profile needs a narrative written for.

    Ordered by match_score, which match.py already computed for free. That is
    the whole point: choosing what to spend a call on costs nothing, so the
    calls go to the jobs a person is actually about to see.

    WITH BOTH FLAGS FALSE THIS IS EXACTLY THE OLD ANTI-JOIN -- "no row exists
    for (job_id, profile)" and nothing else. A version column moving does not
    select a single extra row, which is the property that keeps a persona edit
    or a prompt bump from spending money nobody asked to spend. The LEFT JOIN
    replaced a NOT EXISTS because the predicate needs to read the score row's
    recorded versions; `s.job_id IS NULL` is the same anti-join written over
    the join.

    The keys are keyword-only so that no caller acquires staleness by
    accident, and so tools/claude-bench.py:121's positional
    select_shortlist(conn, n, profile) keeps meaning what it meant.

    ORDERING: never-scored ahead of stale, then match_score, then newest.
    Same argument select_unextracted_jobs makes (extract.py:590-600): a
    backfill must not put tonight's postings behind a queue of re-scores, or
    the only rows anyone is waiting on are the last served.

    `versions` is a ScoreContext. It is required by either flag -- a
    staleness predicate with nothing to compare against would silently select
    nothing, or worse, everything.

    No relevance tier here any more. A row only reaches job_matches if it
    cleared the profile's own relevance gate in extract.py AND scored above
    MATCH_FLOOR, so the filtering has already happened twice by this point.
    """
    if (include_stale or include_unversioned) and versions is None:
        raise ValueError("select_shortlist needs a ScoreContext to compare "
                         "against before it can select stale rows")
    rows = conn.execute(
        f"""
        SELECT j.id, j.title, j.company_name, j.location_raw, j.platform,
               m.match_score, m.match_reasons,
               f.summary, f.seniority_level, f.years_experience_min,
               f.role_archetype, f.tech_stack, f.remote_policy,
               f.ai_involvement, f.gap_friendly_language, f.comp_min,
               f.comp_max, f.facts_version
        {_shortlist_from()}
          AND (
                s.job_id IS NULL
             OR (%(include_stale)s AND {_STALE_ANY})
             OR (%(include_unversioned)s AND {_UNVERSIONED})
          )
        ORDER BY (s.job_id IS NOT NULL), m.match_score DESC, j.first_seen DESC
        LIMIT %(limit)s
        """,
        {"profile": profile, "status": schema.STATUS_OPEN, "limit": limit,
         "include_stale": bool(include_stale),
         "include_unversioned": bool(include_unversioned),
         "persona_sha": versions.persona_sha if versions else None,
         "prompt_version": versions.prompt_version if versions else None},
    ).fetchall()
    cols = ["id", "title", "company_name", "location_raw", "platform",
            "match_score", "match_reasons", "summary", "seniority_level",
            "years_experience_min", "role_archetype", "tech_stack",
            "remote_policy", "ai_involvement", "gap_friendly_language",
            "comp_min", "comp_max", "facts_version"]
    return [dict(zip(cols, r)) for r in rows]


#: The census buckets, in the order they are reported and in the order the
#: FILTERs below claim rows. They are DISJOINT and they sum to the population:
#: a row stale on two axes is counted once, under the first bucket that
#: applies, so an operator adding the numbers up gets the population back
#: rather than an estimate that pays for the same row twice.
CENSUS_BUCKETS = ("never_scored", "unversioned", "stale_tombstone",
                  "stale_facts", "stale_persona", "stale_prompt", "current")


def stale_census(conn, profile, ctx):
    """bucket -> count over this profile's shortlist population.

    Pure SQL. No LLM call, no write, no credential -- this is the thing an
    operator runs BEFORE deciding whether to spend anything, so it must be
    runnable on a machine that could not spend anything if it tried.

    stale_tombstone is broken out of the stale buckets because those rows are
    cheap and disproportionately worth retrying: 40 of the 57 tombstones in
    production were written by FAILED:glm-4.5-flash@api.z.ai, which is not the
    production pin and was failing for a credential reason rather than
    anything about the posting. A tombstone is evidence about the prompt that
    was sent, so a version change makes it eligible again -- the same rule
    extract.mark_extract_failed applies by storing at the current
    facts_version. Retrying them is still behind the opt-in flag.

    NOTE that today's tombstones are all unversioned, so they are counted
    under `unversioned`; stale_tombstone only becomes non-zero for tombstones
    written after these columns existed.
    """
    row = conn.execute(
        f"""
        SELECT
          count(*) FILTER (WHERE s.job_id IS NULL),
          count(*) FILTER (WHERE {_UNVERSIONED}),
          count(*) FILTER (WHERE NOT {_UNVERSIONED} AND {_STALE_ANY}
                             AND {_TOMBSTONE}),
          count(*) FILTER (WHERE NOT {_UNVERSIONED} AND NOT {_TOMBSTONE}
                             AND {_STALE_FACTS}),
          count(*) FILTER (WHERE NOT {_UNVERSIONED} AND NOT {_TOMBSTONE}
                             AND NOT {_STALE_FACTS} AND {_STALE_PERSONA}),
          count(*) FILTER (WHERE NOT {_UNVERSIONED} AND NOT {_TOMBSTONE}
                             AND NOT {_STALE_FACTS} AND NOT {_STALE_PERSONA}
                             AND {_STALE_PROMPT}),
          count(*) FILTER (WHERE s.job_id IS NOT NULL AND NOT {_UNVERSIONED}
                             AND NOT {_STALE_ANY})
        {_shortlist_from()}
        """,
        {"profile": profile, "status": schema.STATUS_OPEN,
         "persona_sha": ctx.persona_sha, "prompt_version": ctx.prompt_version,
         "failed": f"{llm.FAILED_PREFIX}%"},
    ).fetchone()
    return dict(zip(CENSUS_BUCKETS, row))


def _facts_block(job):
    """The posting, as facts rather than prose.

    Replaces the 3,000-char description the old prompt carried. Only fields
    that are actually present are emitted -- a wall of "unknown" lines invites
    a model to treat absence as a negative signal, when it usually just means
    the posting did not say.
    """
    stack = job.get("tech_stack")
    try:
        stack = ", ".join(json.loads(stack or "[]")[:20])
    except (TypeError, json.JSONDecodeError):
        stack = ""
    comp = ""
    if job.get("comp_min") or job.get("comp_max"):
        comp = f"\nCompensation: {job.get('comp_min')}-{job.get('comp_max')}"
    years = ("" if job.get("years_experience_min") is None
             else f"\nYears required: {job['years_experience_min']}+")
    return (
        f"Title: {job.get('title')}\n"
        f"Company: {job.get('company_name')}\n"
        f"Location: {job.get('location_raw')} ({job.get('remote_policy')})\n"
        f"Level: {job.get('seniority_level')}{years}\n"
        f"Role type: {job.get('role_archetype')}\n"
        f"AI involvement: {job.get('ai_involvement')}\n"
        f"Technologies: {stack or 'not stated'}"
        f"{comp}\n"
        f"Explicitly welcomes career breaks: "
        f"{'yes' if job.get('gap_friendly_language') else 'not stated'}\n"
        f"Summary: {job.get('summary')}"
    )


def build_prompt(persona, job):
    """The narrative prompt.

    Accepts either shape of `job`: a shortlist row (facts) or a raw jobs row
    with description_text. The latter is what tools/cost-test.py and
    tools/compare-models.py pass, and keeping both working means the
    measurement tools did not need rewriting alongside the pipeline.

    BUCKETS ARE OPTIONAL AND THE PROMPT DROPS THE SECTION WITHOUT THEM (D16).
    This used to hard-index persona["buckets"], which profiles.validate()
    does not require (profiles.py:139-142) -- so a profile saved without it
    validated cleanly and then raised KeyError inside the thread pool, taking
    down the whole profile's batch because run_for_profile materialises
    pool.map through list(). That is not hypothetical any more: the `pursuit`
    profile is active with no `buckets` key, and stays quiet only because its
    daily_narrative_budget is 0.

    The fix is here rather than in profiles.validate() -- see the note there.
    A persona with no positioning buckets is a legitimate persona under the
    Pursuit scope (there is no single target role to bucket against), so
    requiring the key would reject a profile that is already live. An empty
    section header inviting the model to fill a void would be worse than no
    section, so the whole block is omitted.
    """
    # `_`-prefixed keys are documentation, not buckets. CLAUDE.md makes
    # `_comment` load-bearing in every config JSON in this repo, so a persona
    # whose buckets{} carries one is a persona someone followed the
    # convention writing -- and its STRING value hits .get() below and raises
    # AttributeError, which score_one_job's blanket handler turns into
    # ERRORED for every job in the batch, because every job in a batch shares
    # one persona. That is D16 with a different key. Non-dict values are
    # tolerated the way None already was, for the same reason: one malformed
    # bucket must not cost a profile its whole night.
    buckets = persona.get("buckets") or {}
    buckets_text = "\n".join(
        f"- {name}: {b.get('description')} ({b.get('fit_signal')})"
        for name, b in ((n, v if isinstance(v, dict) else {})
                        for n, v in buckets.items()
                        if not str(n).startswith("_"))
    )
    buckets_block = (f"\nPOSITIONING BUCKETS:\n{buckets_text}\n"
                     if buckets_text else "")
    strengths_text = "\n".join(f"- {s}" for s in (persona.get("strengths") or []))
    gaps_text = "\n".join(f"- {g}" for g in (persona.get("honest_gaps") or []))
    posting = (_facts_block(job) if "summary" in job else
               f"Title: {job.get('title')}\n"
               f"Company: {job.get('company_name')}\n"
               f"Location: {job.get('location_raw')}\n"
               f"Source: {job.get('platform')}\n"
               f"Description: {(job.get('description_text') or '')[:3000]}")

    return f"""You are evaluating a job posting for fit against a specific candidate's background. Respond with ONLY a single JSON object -- no markdown code fences, no explanation before or after.

CANDIDATE BACKGROUND:
{persona['background_summary']}

STRENGTHS:
{strengths_text}

HONEST GAPS:
{gaps_text}
{buckets_block}
SCORING INSTRUCTIONS:
{persona['scoring_instructions']}

JOB POSTING TO EVALUATE:
{posting}

Respond with exactly this JSON schema (no other text):
{{
  "fit_score": <integer 0-100>,
  "primary_track": "<one of: Core SWE, AI Integration, Bridge & Solutions, Re-Entry & Growth, Poor Fit>",
  "gap_friendly_signal": <true or false>,
  "key_technologies": ["...", "..."],
  "gap_bridging_angle": "<1-2 concrete sentences specific to this posting>",
  "risk_factors": ["...", "..."]
}}"""


def _canon(value):
    """Comparison key for a track name. Not a stored value -- see TRACKS.

    Everything that is not a letter or a digit becomes a space, so "&", "-",
    "_" and "/" are all separators, and a standalone "and" is dropped because
    a model writing "Bridge and Solutions" for "Bridge & Solutions" has given
    the right answer in the wrong punctuation.
    """
    words = [w for w in re.split(r"[^a-z0-9]+", value.strip().lower())
             if w and w != "and"]
    return " ".join(words)


#: canonical -> display. Two keys per track: the spaced canonical form and the
#: separator-free one, so "CoreSWE" resolves as well as "core_swe". Same
#: tolerance extract._enum() extends with its `v == a.replace("_", "")` arm.
_TRACK_BY_CANON = {}
for _t in TRACKS:
    _TRACK_BY_CANON[_canon(_t)] = _t
    _TRACK_BY_CANON[_canon(_t).replace(" ", "")] = _t


def _track(value):
    """A model's answer coerced onto TRACKS, in stored (Title Case) form, or None.

    None rather than a default, for the reason extract.normalize() gives:
    absence has to survive normalisation or a value the model never gave is
    indistinguishable from one it did. `Poor Fit` in particular must NOT be
    the fallback -- it is a real, negative answer, and defaulting to it would
    manufacture rejections out of malformed JSON.

    Measured (2026-07-28, production `job_scores`): the only off-vocabulary
    value in 1,237 model-written rows is `frontend_core`, 3 rows, all on the
    `frontend` profile -- the model answering with the PROFILE name in
    extraction's snake_case. It coerces to None here, deliberately: it is not
    one of the five, and guessing which one it meant would be inventing an
    answer.

    A trailing explanation is tolerated ("Poor Fit - too senior"), first-wins,
    the same arbitration extract._enum() applies to "Senior/Mid".
    """
    if not isinstance(value, str):
        return None
    canon = _canon(value)
    if not canon:
        return None
    if canon in _TRACK_BY_CANON:
        return _TRACK_BY_CANON[canon]
    for key, display in _TRACK_BY_CANON.items():
        if " " in key and canon.startswith(key + " "):
            return display
    return None


def _fit_score(value):
    """An integer 0-100, or None. Mirrors extract._int_or_none()'s contract.

    OUT OF RANGE IS None, NOT A CLAMP. A clamp invents a value the model did
    not give: 850 clamped to 100 is a top-of-list annotation manufactured out
    of a typo, and match.py already refuses to let fit_score order anything
    precisely so that a wrong one is cheap. NULL is the honest record and the
    tombstone path already writes it.

    Booleans are rejected before int() sees them -- bool is an int subclass in
    Python, so True would otherwise store as 1.
    """
    if isinstance(value, bool) or value is None:
        return None
    try:
        n = int(value)
    except (TypeError, ValueError):
        return None
    return n if 0 <= n <= 100 else None


def _prose(value):
    """A non-empty string, or None. Prose columns are displayed, never scored."""
    if not isinstance(value, str):
        return None
    value = value.strip()
    return value or None


def _string_list(value):
    """A list of non-empty strings, de-duplicated, original order and case kept.

    NOT lowercased, unlike extract.normalize()'s tech_stack. That field is
    matched against a profile's tech config, so case is noise; these two are
    rendered to a person, and rewriting "PostgreSQL" as "postgresql" in a
    narrative is a downgrade for no gain.
    """
    if not isinstance(value, list):
        return []
    out, seen = [], set()
    for item in value:
        # None explicitly, before str(): str(None) is the four-character
        # string "None", which is how a null in a model's array becomes a
        # technology nobody has ever used.
        if item is None or isinstance(item, (dict, list)):
            continue
        text = str(item).strip()
        if text and text.lower() not in seen:
            seen.add(text.lower())
            out.append(text)
    return out


def normalize(result):
    """Model output -> the exact column values job_scores stores, or None.

    None means the response is unusable and the caller writes a tombstone --
    the same contract as extract.normalize(), and the reason this returns a
    dict of COLUMN values rather than passing `result` through to SQL: the
    coercion has to happen in one place that a test can call without a
    database, which is what audit item 8 (D15) was about.

    THE "NOTHING USABLE CAME BACK" GUARD is `fit_score is None and
    primary_track is None`. llm.has_fields() checks that the six keys are
    PRESENT, not that any of them holds a usable value (llm.py:365-366), so
    {"fit_score": null, "primary_track": null, ...} passes it and used to be
    written as a row -- indistinguishable from a real score in every query
    that does not also read scoring_model. Three such rows exist in
    production (measured 2026-07-28: fit_score set, primary_track NULL,
    gap_bridging_angle NULL, scoring_model 'FAILED:...'). A row that is NULL
    in both columns anything reads is a tombstone; it should be written as
    one.

    gap_friendly_signal is tri-state for the reason extract._tristate_bool()
    gives: bool() laundered an absent key, an explicit false, and a
    non-boolean answer into the same False. The column is nullable and
    nothing scores it, so the honest value is the cheap one.
    """
    if not llm.has_fields(result, REQUIRED_FIELDS):
        return None

    fit = _fit_score(result.get("fit_score"))
    track = _track(result.get("primary_track"))
    if fit is None and track is None:
        return None

    signal = result.get("gap_friendly_signal")
    return {
        "fit_score": fit,
        "primary_track": track,
        "gap_friendly_signal": signal if isinstance(signal, bool) else None,
        "key_technologies": _string_list(result.get("key_technologies")),
        "gap_bridging_angle": _prose(result.get("gap_bridging_angle")),
        "risk_factors": _string_list(result.get("risk_factors")),
    }


def update_job_score(conn, job_id, values, ctx, facts_version):
    """Write one (job, profile) score. `values` is normalize()'s output.

    ON CONFLICT DO UPDATE rather than DO NOTHING: re-scoring an already-scored
    job is a deliberate act (a new model, a revised persona under the same
    profile name), and the newer answer is the one that should stand.

    Takes normalized values, not the raw `result` dict. That is the fix for
    D15: there is now no path from a model response to this table that skips
    the coercion, because this function cannot see a raw response.

    Takes a ScoreContext rather than (profile, model_label) for the same
    structural reason: the profile, the model and the three version columns
    arrive together or not at all, so there is no call shape that writes a
    narrative without recording what produced it. facts_version is separate
    because it belongs to the posting's job_facts row, not to the run.

    THE PARAMETER ORDER IS PINNED. tests/test_score.py asserts params[0:4] and
    params[5] positionally, so the four version columns are APPENDED after
    scoring_model and nothing before them moves.
    """
    conn.execute(
        f"""
        INSERT INTO {schema.SCORES_TABLE}
            (job_id, profile, fit_score, primary_track, gap_friendly_signal,
             key_technologies, gap_bridging_angle, risk_factors,
             scored_at, scoring_model,
             facts_version, persona_sha, prompt_version, criteria_version)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (job_id, profile) DO UPDATE SET
            fit_score=EXCLUDED.fit_score,
            primary_track=EXCLUDED.primary_track,
            gap_friendly_signal=EXCLUDED.gap_friendly_signal,
            key_technologies=EXCLUDED.key_technologies,
            gap_bridging_angle=EXCLUDED.gap_bridging_angle,
            risk_factors=EXCLUDED.risk_factors,
            scored_at=EXCLUDED.scored_at,
            scoring_model=EXCLUDED.scoring_model,
            facts_version=EXCLUDED.facts_version,
            persona_sha=EXCLUDED.persona_sha,
            prompt_version=EXCLUDED.prompt_version,
            criteria_version=EXCLUDED.criteria_version
        """,  # noqa: S608 -- splices schema.SCORES_TABLE, a module-level constant
        (
            job_id,
            ctx.profile,
            values["fit_score"],
            values["primary_track"],
            values["gap_friendly_signal"],
            json.dumps(values["key_technologies"]),
            values["gap_bridging_angle"],
            json.dumps(values["risk_factors"]),
            utc_now_str(),
            ctx.model_label,
            facts_version,
            ctx.persona_sha,
            ctx.prompt_version,
            ctx.criteria_version,
        ),
    )
    conn.commit()


def mark_score_failed(conn, job_id, ctx, facts_version):
    """Permanent marker for a failed/unparseable scoring attempt -- without
    this, a job that fails once gets retried (and fails) on every future
    run forever. Same lesson as ingest/hn-hiring.py's hn_seen_comments
    tombstone table.

    The tombstone is per profile too: a job that one persona failed to score
    is still worth attempting for another.

    IT CLEARS THE NARRATIVE COLUMNS, and that is a fix rather than tidying.
    This module's docstring promises a tombstone leaves "fit_score left NULL",
    but the ON CONFLICT clause used to update only scored_at and
    scoring_model -- so a row update_job_score had already written kept its
    old fit_score and narrative under a 'FAILED:' model label. The result is a
    row whose score says one thing and whose provenance says another, and
    every reader that does not also select scoring_model believes the score.
    Overwriting with NULL loses a stale narrative; keeping it publishes one.

    IT OVERWRITES ALL FOUR VERSION COLUMNS FOR THAT SAME REASON. A tombstone
    written over a previously-scored row would otherwise inherit that row's
    versions, and the result is exactly the D43 shape above one level up: a
    row whose tombstone describes one attempt and whose provenance describes
    a different, earlier one. The versions recorded here are the versions of
    the attempt that failed, which is also what makes the tombstone eligible
    again when the prompt or the persona moves -- a failed narrative is
    evidence about the prompt that was sent, not about the posting.
    """
    conn.execute(
        f"""
        INSERT INTO {schema.SCORES_TABLE}
            (job_id, profile, scored_at, scoring_model,
             facts_version, persona_sha, prompt_version, criteria_version)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (job_id, profile) DO UPDATE SET
            scored_at=EXCLUDED.scored_at, scoring_model=EXCLUDED.scoring_model,
            fit_score=NULL, primary_track=NULL, gap_friendly_signal=NULL,
            key_technologies=NULL, gap_bridging_angle=NULL, risk_factors=NULL,
            facts_version=EXCLUDED.facts_version,
            persona_sha=EXCLUDED.persona_sha,
            prompt_version=EXCLUDED.prompt_version,
            criteria_version=EXCLUDED.criteria_version
        """,  # noqa: S608 -- splices schema.SCORES_TABLE, a module-level constant
        (job_id, ctx.profile, utc_now_str(),
         llm.failed_label(ctx.model_label),
         facts_version, ctx.persona_sha, ctx.prompt_version,
         ctx.criteria_version),
    )
    conn.commit()


#: score_one_job outcomes. ERRORED is its own outcome rather than folded into
#: DEFERRED because the two have different causes and different fixes: a
#: deferral is the endpoint being busy and resolves itself, an error is a bug
#: in this process. Counting them together would let a persona that crashes
#: every job in a batch print main()'s "the endpoint is rate-limiting" note,
#: which is the wrong thing to go and check.
SCORED, REJECTED, DEFERRED, ERRORED = ("scored", "rejected", "deferred",
                                       "errored")


def score_one_job(job, ctx):
    """Runs inside a worker thread -- opens its own connection rather than
    sharing one across threads (psycopg connections aren't safe for
    concurrent use).

    Returns SCORED, REJECTED (the model answered but the answer was unusable
    -- tombstoned, never retried), DEFERRED (the endpoint never gave us an
    answer -- nothing written, retried next run) or ERRORED (a bug on our
    side -- nothing written, loud, retried next run).

    That split matters more than it looks. Tombstoning is right for
    a model that cannot produce parseable JSON for a given posting: retrying
    forever would burn a call a night on the same failure. It is badly wrong
    for an HTTP 429, which says nothing about the posting -- and the current
    default model rate-limits hard enough that a batch can be mostly 429s.
    Recording those as failures silently and permanently discards jobs that
    were never actually evaluated.

    An UNEXPECTED exception is ERRORED, one job, and the batch continues.
    Before this guard the only try around build_prompt was a bare
    try/finally that closed the connection and re-raised, so a KeyError from
    a malformed persona escaped into run_for_profile's list(pool.map(...))
    and ended the profile's whole batch -- and because every job in a batch
    shares one persona, the first job to fail was also the last. Nothing was
    written, so nothing recorded that it happened. That is D16, and it is
    worse than the 3am deferred batch profiles.validate()'s docstring
    describes, because a deferred batch is at least a batch.

    Nothing is written for an ERRORED job: a tombstone would permanently
    discard a posting over a bug in this process, which is the same wrong
    trade the DEFERRED/REJECTED split exists to avoid for a 429.
    """
    try:
        return _score_one_job(job, ctx)
    except Exception as e:  # noqa: BLE001 -- deliberate: see above
        # Loud unconditionally, not behind DEBUG_PRINT_KEYS. Silence is this
        # system's failure mode and this is the branch that means a bug.
        log.error(f"job-score ERROR on {job.get('id')} ({job.get('title')!r}): "
                  f"{type(e).__name__}: {e}")
        return ERRORED


def _score_one_job(job, ctx):
    """The body score_one_job guards. Same contract, minus the isolation.

    facts_version comes off the shortlist row, so what gets recorded is the
    version of the facts THIS prompt was built from -- not whatever
    job_facts holds by the time the write lands.
    """
    # search_path is per-connection, so a worker's fresh connection needs it
    # set again -- dbconn.connect(schema=...) does that for every connection
    # it hands out, which is what makes the threaded case correct by
    # construction instead of by remembering.
    conn = dbconn.connect(schema=schema.SCHEMA)
    facts_version = job.get("facts_version")
    try:
        prompt = build_prompt(ctx.persona, job)
        try:
            raw = llm.call(prompt)
        except llm.TransientError as e:
            if DEBUG_PRINT_KEYS:
                log.debug(f"deferring {job['id']} ({job.get('title')!r}): {e}")
            return DEFERRED
        except (RuntimeError, json.JSONDecodeError) as e:
            # A definite answer we can't use (4xx, malformed envelope).
            if DEBUG_PRINT_KEYS:
                log.debug(f"scoring call failed for {job['id']} ({job.get('title')!r}): {e}")
            raw = None

        result = llm.parse_json(raw) if raw else None
        values = normalize(result) if result is not None else None

        if values is not None:
            update_job_score(conn, job["id"], values, ctx, facts_version)
            if DEBUG_PRINT_KEYS:
                print(f"[debug] {job.get('title')!r} @ {job.get('company_name')}: "
                      f"fit={values['fit_score']} track={values['primary_track']!r}",
                      file=sys.stderr)
            return SCORED

        mark_score_failed(conn, job["id"], ctx, facts_version)
        if DEBUG_PRINT_KEYS:
            log.debug(f"unparseable/invalid result for {job['id']} ({job.get('title')!r})")
        return REJECTED
    finally:
        conn.close()


def run_for_profile(conn, profile_obj, limit=None, model_label=None, *,
                    include_stale=False, include_unversioned=False):
    """Write narratives for one profile's shortlist. Returns a Counter.

    Importable rather than buried in main() because a login path would call it
    directly: a user signing in is exactly the moment their top 20 should get
    narratives, and it is the trigger that would make cost track engagement
    rather than registration. THAT PATH IS DOCUMENTED AND UNBUILT -- nothing
    under webapp/ imports this module, and main() below is the only caller
    today. The cost model is the reason to keep the function importable; the
    claim that something already imports it was wrong.

    One profile at a time, deliberately. The persona is the bulk of the prompt
    and it caches as a prefix; interleaving profiles would evict it between
    every call.

    THE RE-SCORE FLAGS DO NOT RAISE THE CAP. Stale rows compete for the same
    `limit` slots as never-scored ones, behind them in the ORDER BY, so
    passing one can never spend more than the operator asked for.
    """
    # `limit or budget` was wrong in the direction that costs money: --limit 0
    # is what someone types to mean "spend nothing", and `0 or 20` is 20.
    # (It was also right by accident for pursuit, whose budget is 0 -- but
    # only for limit=None, which is not the case anyone was worried about.)
    limit = profile_obj.daily_narrative_budget if limit is None else limit
    ctx = context_for(profile_obj, model_label)
    jobs = select_shortlist(conn, limit, profile_obj.profile, versions=ctx,
                            include_stale=include_stale,
                            include_unversioned=include_unversioned)
    if not jobs:
        return Counter()

    with concurrent.futures.ThreadPoolExecutor(
            max_workers=SCORE_MAX_WORKERS) as pool:
        results = list(pool.map(lambda job: score_one_job(job, ctx), jobs))
    return Counter(results)


def main():
    p = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--profile", help="one profile (default: all active)")
    p.add_argument("--limit", type=int, default=None,
                   help="override the profile's daily_narrative_budget")
    p.add_argument("--active-within-days", type=int, default=None,
                   help="warm pass: skip profiles with no job_events in this "
                        "window, so dormant accounts cost nothing")
    p.add_argument("--stale-report", action="store_true",
                   help="print the staleness census for every profile, paused "
                        "ones included, and exit. Spends nothing: no LLM "
                        "call, no write, no API key needed")
    p.add_argument("--rescore-stale", action="store_true",
                   help="also re-score rows whose recorded persona, prompt or "
                        "facts version differs from current. Requires --limit")
    p.add_argument("--rescore-unversioned", action="store_true",
                   help="also re-score rows written before the version "
                        "columns existed. Requires --limit")
    args = p.parse_args()

    # BOTH RE-SCORE FLAGS REQUIRE AN EXPLICIT --limit, and argparse refuses
    # rather than defaulting. daily_narrative_budget is a NIGHTLY WARM-PASS
    # quantity; reusing it as a backfill quantity is how an operator signs up
    # for 51 consecutive nights of re-scoring `tech` by typing one flag. The
    # sizes are different too -- 0 stale and 835 unversioned on `tech` today
    # -- which is why these are two flags and not one.
    if (args.rescore_stale or args.rescore_unversioned) and args.limit is None:
        p.error("--rescore-stale and --rescore-unversioned require an "
                "explicit --limit: this spends one LLM call per row and the "
                "backlog is larger than any nightly budget. Run "
                "--stale-report first to see how many rows there are.")

    # BEFORE the credential check, deliberately, and that placement is the
    # proof rather than a comment: a report that cannot run without an API key
    # is a report an operator cannot use to decide whether to spend one.
    if args.stale_report:
        _print_stale_report(args.profile)
        return

    if not llm.api_key():
        print("job-score FAILED: JOB_SCORING_API_KEY (or GLM_API_KEY as a "
              "fallback) not set.")
        sys.exit(1)

    mismatch = llm.model_mismatch()
    if mismatch:
        print(f"job-score FAILED: {mismatch}")
        sys.exit(1)

    conn = dbconn.connect_or_exit("job-score", schema=schema.SCHEMA)
    schema.ensure_schema(conn)

    if args.profile:
        one = profiles.load_one(conn, args.profile)
        if not one:
            print(f"job-score FAILED: no profile named {args.profile!r}")
            conn.close()
            sys.exit(1)
        targets = [one]
    else:
        targets = profiles.load_active(conn)

    if args.active_within_days is not None:
        targets = [t for t in targets
                   if _recently_active(conn, t.profile, args.active_within_days)]

    if not targets:
        conn.close()
        return  # nothing to do -- silent, same convention as the other scripts

    host = urllib.parse.urlparse(llm.base_url()).hostname or llm.base_url()
    model_label = f"{llm.model()}@{host}"

    total = Counter()
    parts = []
    for prof in targets:
        outcomes = run_for_profile(
            conn, prof, args.limit, model_label,
            include_stale=args.rescore_stale,
            include_unversioned=args.rescore_unversioned)
        if not outcomes:
            continue
        total.update(outcomes)
        parts.append(f"{prof.profile}: {outcomes[SCORED]} scored"
                     + (f", {outcomes[REJECTED]} unparseable"
                        if outcomes[REJECTED] else "")
                     + (f", {outcomes[DEFERRED]} deferred"
                        if outcomes[DEFERRED] else "")
                     + (f", {outcomes[ERRORED]} ERRORED"
                        if outcomes[ERRORED] else ""))
    conn.close()

    if not parts:
        return  # every profile's shortlist was already written
    n = total[SCORED] + total[REJECTED] + total[DEFERRED] + total[ERRORED]
    # The rescore flags are named in the summary line because a log that
    # cannot tell a nightly warm pass from an operator's backfill cannot
    # answer "why did last Tuesday cost that much".
    rescoring = ",".join(f for f, on in (("stale", args.rescore_stale),
                                         ("unversioned",
                                          args.rescore_unversioned)) if on)
    print(f"job-score: " + "; ".join(parts)
          + f", model={model_label}, workers={SCORE_MAX_WORKERS}"
          + (f", rescore={rescoring}" if rescoring else ""))
    if total[ERRORED]:
        # Named separately from the rate-limit note below: an error is a bug
        # here, not a busy endpoint, and sending someone to SCORE_MAX_WORKERS
        # for it would waste the trip. The stderr line from score_one_job
        # carries the exception.
        print(f"  NOTE: {total[ERRORED]}/{n} job(s) raised an unexpected "
              f"exception and were skipped -- see the job-score ERROR lines "
              f"on stderr. A persona missing a key does this to every job in "
              f"a batch.")
    if total[DEFERRED] > n / 2:
        print(f"  NOTE: {total[DEFERRED]}/{n} calls never got a response -- "
              f"the endpoint is rate-limiting or down. Nothing was discarded; "
              f"lower SCORE_MAX_WORKERS (currently {SCORE_MAX_WORKERS}) if "
              f"this persists.")


def _print_stale_report(profile=None):
    """The census, per profile, and what each flag would cost to act on.

    EVERY PROFILE, not just the active ones. `tech` and `frontend` are paused
    and hold every score in the table; a report that skipped them would print
    zeroes for the only rows that exist. A paused profile's backlog is
    precisely what an operator wants to see before un-pausing it.

    Counts are CALLS, never dollars. There is no committed per-call scoring
    price anywhere in this repo, and a number invented for a report gets
    quoted back as a fact -- see the measurement-discipline note in
    CLAUDE.md.
    """
    conn = dbconn.connect_or_exit("job-score", schema=schema.SCHEMA)
    schema.ensure_schema(conn)
    try:
        if profile:
            names = [profile]
        else:
            names = [r[0] for r in conn.execute(
                f"SELECT profile FROM {schema.PROFILES_TABLE} "  # noqa: S608 -- splices schema.PROFILES_TABLE, a module-level constant
                f"ORDER BY profile").fetchall()]
        print(f"job-score staleness (prompt_version="
              f"{schema.SCORE_PROMPT_VERSION}, no calls made):")
        for name in names:
            prof = profiles.load_one(conn, name)
            if not prof:
                print(f"  {name}: no such profile")
                continue
            census = stale_census(conn, name, context_for(prof))
            stale = sum(census[b] for b in
                        ("stale_tombstone", "stale_facts", "stale_persona",
                         "stale_prompt"))
            print(f"  {name}{'' if prof.active else ' (paused)'}: "
                  + ", ".join(f"{census[b]} {b}" for b in CENSUS_BUCKETS))
            print(f"      --rescore-stale would select {stale} row(s), "
                  f"--rescore-unversioned {census['unversioned']}; "
                  f"one LLM call each, capped by --limit")
    finally:
        conn.close()


def _recently_active(conn, profile, days):
    """Has this profile generated any engagement inside the window?

    Used by the nightly warm pass so a returning user finds narratives already
    written while a dormant account costs nothing. A profile that has never
    produced an event counts as active -- otherwise a brand-new signup would
    be skipped by the very pass meant to prepare their first list.
    """
    row = conn.execute(
        f"SELECT count(*) FROM {schema.EVENTS_TABLE} WHERE profile = %s",  # noqa: S608 -- splices schema.EVENTS_TABLE, a module-level constant
        (profile,)).fetchone()
    if not row[0]:
        return True
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)
              ).strftime("%Y-%m-%dT%H:%M:%S")
    return bool(conn.execute(
        f"SELECT 1 FROM {schema.EVENTS_TABLE} "  # noqa: S608 -- splices schema.EVENTS_TABLE, a module-level constant
        f"WHERE profile = %s AND occurred_at >= %s LIMIT 1",
        (profile, cutoff)).fetchone())


if __name__ == "__main__":
    main()

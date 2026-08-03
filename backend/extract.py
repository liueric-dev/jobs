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

NOT EVERYTHING THAT ARRIVES IS A JOB POSTING
    An ingest path that captures the wrong bytes used to get them laundered
    into structured facts, because nothing between the database and the model
    had any opinion about what it was reading. Eight rows in this corpus carry
    residual browser markup in description_text -- one of them a scraped
    ChatGPT web UI that extracted as role_archetype='data' at facts_version=3,
    another 2,700 characters of a staffing firm's navigation menu that
    extracted as 'ml_research' and reached a job_scores row.

    So there is now a gate immediately before build_prompt(): a posting whose
    prompt window is more than MARKUP_REJECT_RATIO markup is REJECTED without
    a call. It sits there and not in the eligibility SQL on purpose -- see the
    block above the gate.

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
import re
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
from lib import dbconn, pipelinelog
from lib.timeparse import utc_now_str

log = pipelinelog.get_logger("extract")

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
#:
#: THIS IS A SHAPE GATE, NOT A CONTENT GATE, and it stays that way now that
#: NULL is meaningful. llm.has_fields (llm.py:366) tests key PRESENCE only, so
#: {"role_archetype": null} passes it. That was worth re-deciding when
#: normalize() stopped defaulting these fields, and the answer is that
#: presence is still the right test: the question here is "did the model
#: answer the schema we asked for", and the question "did it actually say
#: anything" belongs to the guard in normalize() below, which can see all four
#: signals at once instead of one key in isolation. Requiring non-null would
#: TOMBSTONE a posting whose archetype the model honestly could not determine
#: -- writing off the row permanently for giving the newly-correct answer,
#: which is the missingness bug in a worse form. (has_fields also lives in
#: llm.py and is shared with score.py; changing it there would move a gate
#: this task never measured.)
#: role_track is deliberately NOT here: it is nullable by design, so requiring
#: its key would tombstone rows over a field nothing scores.
REQUIRED_FIELDS = ("seniority_level", "role_archetype", "remote_policy",
                   "tech_stack", "summary")

SENIORITY = ("intern", "new_grad", "junior", "mid", "senior", "staff",
             "principal", "director", "exec")

#: role_archetype's closed vocabulary, and the input to match.py's single most
#: predictive feature.
#:
#: DERIVED, NOT INVENTED. The original twelve were all software-engineering
#: values, which made every non-software role `other` -- priced at 0 by
#: config/criteria.json, i.e. indistinguishable from a missing value. The
#: fourteen added below come from docs/role-track-derivation.md (a), measured
#: against 863 cohort-eligible postings and the 427 rows already sitting at
#: `other`. That document reports employer SPREAD beside every count, because
#: a candidate whose mass sits at one employer is that employer's hiring spree
#: rather than a vocabulary value. The fourteen reclaim 242 of the 427 (56.7%).
#:
#: Its headline finding is worth carrying next to the list, because it is not
#: what the task file assumed: `other` was mostly a TECH vocabulary gap, not an
#: ops one. 240 of the 427 `other` titles contain the word "engineer"; the five
#: ops values reclaim 54 rows, the nine tech values reclaim 203.
#:
#: CONSIDERED AND DROPPED ON EVIDENCE, recorded so they are not proposed again:
#:   automation_specialist -- 5 cohort postings, 1 `other` row. The spread is
#:     fine, the mass is not, and the genuine automation work in this corpus
#:     already lands in implementation_analyst and business_systems.
#:   data_coordination     -- 9 cohort postings, 8 of them one employer's "Data
#:     Annotation Specialist". Two employers is not a vocabulary value; it is
#:     precisely the near-duplicate trap that analysis was built to catch.
#:   Between them they would have reclaimed ONE row of the 427.
#:
#: ai_operations is the value this whole change is motivated by and it is the
#: THINNEST of the fourteen: 5 cohort postings across 3 employers. It is
#: carried deliberately -- its absence is exactly the failure being fixed --
#: but it is the first thing to re-check when Phase 3 lands new sources.
#:
#: THE ESCAPE HATCH, RECORDED NOW: if a third vertical ever appears, stop
#: hand-growing this and adopt O*NET/SOC codes. Hand-maintained taxonomies that
#: lag reality are the documented failure mode -- it is why LinkedIn abandoned
#: theirs. Two verticals does not justify SOC's complexity; four would. This
#: change takes the hand-maintained list from 12 to 26, which is most of the
#: way to where that trade flips, so the next person to want another eight
#: values should read docs/role-track-derivation.md, "The O*NET/SOC escape
#: hatch", before adding them.
ARCHETYPE = (
    # The original twelve. All software engineering.
    "backend", "frontend", "fullstack", "ai_integration",
    "ml_research", "forward_deployed", "solutions", "data",
    "devops", "security", "pm", "other",
    # Ops (5). Reclaim 54 of the 427 `other` rows.
    "ai_operations", "implementation_analyst", "support_ops",
    "marketing_ops", "admin_ops",
    # Tech (9). Reclaim 203. This is where the `other` mass actually was.
    "hardware_embedded", "infrastructure_compute", "engineering_management",
    "qa_test", "program_management", "mobile", "business_systems",
    "it_internal", "developer_relations",
)

#: The browsable role families the UI groups by -- a coarser grain than
#: ARCHETYPE, and a separate axis rather than a rollup of it.
#:
#: PROVISIONAL, AND THE REASON MATTERS. These nine are cluster names from
#: docs/role-track-derivation.md (b): agglomerative clustering over posting
#: TITLES (descriptions rebuild the employer list, not a role taxonomy -- 94%
#: of title-only clusters span 4+ employers against 30% for title+description).
#: The corpus they came from is pre-Phase-3 and tech-heavy, and the task file
#: (tranche_two/11-archetype-superset-role-track.md:56-64) is explicit that a
#: taxonomy derived from it "will not describe the population's opportunity
#: space" and expects revision. backend/tools/derive-role-tracks.py exists to
#: re-run the derivation; this is not a settled vocabulary.
#:
#: NULLABLE BY DESIGN, and _INSTRUCTIONS says so to the model. The nine tracks
#: cover 83.2% of clusters at n>=5; the tail below that forms on incidental
#: shared title words (a Site Reliability Engineer and a Pharmacy Technician
#: both saying "technician") and is explicitly not trusted. A vocabulary that
#: forces a value on the other 16.8% would be inventing one.
#:
#: `security` and AI/agent engineering both surfaced as clean clusters and are
#: deliberately NOT tracks: they already exist as ARCHETYPE values, and giving
#: the UI two controls that do the same thing at different grains is worse than
#: giving it one.
#:
#: business_systems appears in BOTH vocabularies, at different grains, and that
#: is intended rather than a copy-paste slip: as an archetype it is the role
#: (Business Systems Analyst, Salesforce/Workday/ERP configuration), as a track
#: it is the browsable family that role sits in. Do not "fix" it by deleting
#: either one.
ROLE_TRACK = ("software_engineering", "technical_support", "business_analysis",
              "product_and_marketing", "solutions_and_implementation",
              "data_and_analytics", "revenue_operations", "business_systems",
              "business_operations")

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
  role_track: {" | ".join(ROLE_TRACK)} | null
  ai_involvement: {" | ".join(AI_INVOLVEMENT)}
  remote_policy: {" | ".join(REMOTE_POLICY)}
  employment_type: {" | ".join(EMPLOYMENT_TYPE)}
  visa_sponsorship: {" | ".join(VISA)}

Field guidance:
  seniority_level        the level the posting is hiring AT, from its title and requirements -- not the seniority of the team.
  role_archetype         the single closest match. "forward_deployed" means embedded with customers to build solutions; "solutions" means sales/customer-facing technical work; "ai_integration" means building LLM/agent features into a product; "ml_research" means training models or research-scientist work. Pairs that are easy to confuse: "support_ops" vs "it_internal" differ by WHO IS SERVED -- "support_ops" serves external customers or users of the product, "it_internal" serves the company's own staff. "engineering_management" means managing engineers; "pm" means product management, deciding what gets built. "infrastructure_compute" means networks, data centres, SRE and compute platforms; "devops" means the delivery pipeline -- CI/CD, build, release. "ai_operations" means running or enabling AI systems and workflows inside a business rather than building them, and it is an uncommon role -- use it only when the posting is clearly that, not whenever AI is mentioned. Answer "other" when none of the listed values fit: "other" is a real answer and is not the same as omitting the field.
  role_track             the broad role family this posting belongs to, a coarser grouping than role_archetype. Use null if none of the listed tracks clearly describes the role. Do not force a value -- null is the correct answer for a role that belongs to no listed track, and is more useful than a wrong one.
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
  "role_track": "<enum or null>",
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


# ---------------------------------------------------------------------------
# THE INPUT-SANITY GATE
#
# Until this existed, extraction had NO opinion about what it was reading. The
# whole of input preparation was one slice of description_text, and the only
# content predicate anywhere was `coalesce(j.description_text,'') <> ''`
# (_eligible_sql above). Anything non-empty went to the model, and whatever
# came back was stored as fact.
#
# What that laundered, found live: job ff9f9d9f9643e185af0f48ca (Taboola,
# "Product Analyst") whose description_text is a scraped ChatGPT web UI. It was
# re-extracted at facts_version=3 and produced CONFIDENT facts from that markup
# -- role_archetype='data', role_track='data_and_analytics'. Job
# 53cbf3ae21a12bff1ff73476 is 2,700 characters of a staffing firm's navigation
# menu and produced 'senior'/'ml_research'/'core_ml_research', and that one got
# as far as a job_scores row. Nothing in the pipeline noticed either.
#
# The gate is here, and not in _eligible_sql, deliberately: a WHERE clause would
# remove these rows from remaining() instead of reporting them, and silence is
# this system's failure mode. Rejecting at extract_facts() costs zero LLM calls,
# writes a tombstone at the current FACTS_VERSION so the row is not retried
# nightly, and shows up in the `unusable` count on the summary line.
# ---------------------------------------------------------------------------

#: Residual HTML/CSS that survived lib/text.strip_html() -- one alternative per
#: shape, each of which is markup and none of which is prose.
#:
#: THIS IS A STRIPPER LEAK, NOT A SCRAPER BUG, and that is why the gate belongs
#: to extraction rather than to any one ingest script. strip_html() strips with
#: `_TAG` (lib/text.py:152-155), whose FIRST alternative treats a double-quoted
#: attribute value as opaque. Before that alternative existed the pattern was a
#: bare `re.sub(r"<[^>]+>", " ", text)`, which ended a tag at the first ">" in
#: the source -- including one inside a quoted value. Modern Tailwind class
#: names contain them:
#:
#:     <section class="... [&:has([data-writing-block])>*]:pointer-events-auto ...
#:                                                     ^ the old regex ended the tag HERE
#:
#: so everything after that ">" -- the rest of the class list, then
#: `data-testid="conversation-turn-136"`, then the real closing ">" -- was
#: emitted as TEXT. Every contaminated row in the corpus is that one mechanism,
#: and it fired source-independently: on greenhouse, where an employer pasted a
#: rendered page into their own JD editor (the markup is in the API's `content`
#: field -- see ingest/ats.py:584,716, it is not something this pipeline added),
#: and on google_jobs, where a careers page was scraped.
#:
#: THE GATE DID NOT BECOME DEAD WHEN _TAG DID. `<[^>]+>` survives as _TAG's
#: second alternative (lib/text.py:154) and still fires for everything the
#: quote-aware form cannot parse -- unbalanced quotes, single-quoted values --
#: and the contaminated rows already in the table were stored before the fix and
#: were never re-stripped. This gate reads what is in description_text now, not
#: what a fresh strip would produce.
#:
#: `\]:[a-z]` and not `\]:`. The looser form matches "[ONSITE]: We are looking
#: for..." -- standard Who's Hiring prose -- and hn_whoishiring row
#: 415fcb871b101301330b9a67 is exactly that. Requiring a lowercase letter with no
#: space after the colon keeps the Tailwind variant boundary ("*]:pointer-events-
#: auto", "[&_hr]:my-3") and drops the prose. It was a measured false positive
#: before the tightening, which is the only reason this note can be specific.
_MARKUP_RESIDUE = re.compile(
    r'[A-Za-z][A-Za-z0-9_-]*="'   # an HTML attribute assignment: data-testid="
    r"|var\(--"                   # a CSS custom-property reference
    r"|\[&"                       # a Tailwind arbitrary-variant selector
    r"|\[--"                      # a Tailwind arbitrary custom property
    r"|\]:[a-z]"                  # a Tailwind variant -> utility boundary
    r"|!important"
    r"|--tw-"
)

#: Reject when leaked markup is at least this fraction of the prompt window.
#:
#: MEASURED, NOT CHOSEN. tools/audit-description-markup.py sweeps the signature
#: above over every described posting; on 2026-07-28, 13,282 rows, it scored
#: exactly 0.0 on all but eight, and those eight split with a gap in the middle:
#:
#:     0.593  6fc72985f864b17e3c4c2513  greenhouse   Fireblocks
#:     0.137  516d19374b2b9caf27ac6cf3  greenhouse   Affirm
#:     0.129  ff9f9d9f9643e185af0f48ca  greenhouse   Taboola      <- the reported one
#:     0.080  1074b7f0354bc3cceed49194  greenhouse   Per Scholas
#:     0.064  e93ddca38b45bb929e6e46cd  greenhouse   Databricks
#:     0.045  7bdfba1a4e254be44463737c  google_jobs  SpeedyApply
#:     0.025  53cbf3ae21a12bff1ff73476  google_jobs  Get Hire Technologies
#:     - - - - - - - - - - - - - - - - gap - - - - - - - - - - - - - - - - - -
#:     0.004  cc7d1b61574ffdac2d112a8d  greenhouse   twelve stray characters
#:     0.000  the other 13,274
#:
#: 0.01 is the GEOMETRIC MIDPOINT of that gap -- sqrt(0.0040 * 0.0247) = 0.0099 --
#: so it clears the worst clean row by 2.5x and the mildest poisoned one by 2.5x
#: rather than sitting against either. FALSE POSITIVES OVER THE FULL TABLE: 0.
#:
#: It deliberately does NOT reject cc7d1b61574ffdac2d112a8d. That posting carries
#: twelve characters of stray Tailwind in an otherwise complete job description,
#: and tombstoning a readable posting is a worse outcome than extracting one with
#: a nick in it. The threshold is set where a prompt stops being a posting, not
#: where it stops being clean.
#:
#: CONSIDERED AND REJECTED ON MEASUREMENT, recorded so it is not proposed again:
#:   a marker blocklist (`data-testid=`, `pointer-events-auto`) -- the query
#:     HANDOFF.md:410-413 used. It finds 3 of the 8 contaminated rows. It misses
#:     both google_jobs rows and both of the Tailwind-only greenhouse rows,
#:     because those leaked class names and no data- attribute.
#:   repeated-content density (duplicate 60-char shingles in the window) -- aimed
#:     at the navigation-menu case. It scores 0.000 on ALL EIGHT contaminated
#:     rows and its six highest-scoring rows are legitimate postings: six false
#:     positives, zero true ones. It measures boilerplate, which real postings
#:     also have.
MARKUP_REJECT_RATIO = 0.01

#: Prefixed onto the model label of an input-sanity tombstone, so
#: "the input was not a posting" is queryable and does not sit in the same
#: undifferentiated pile as "the model could not answer about a real posting".
#: Without it the only trace of a gate firing is a +1 on the `unusable` counter,
#: which is exactly the silence this gate was added to end.
#:
#: It goes in the model label rather than in a new column BY DESIGN. The
#: FAILED: prefix llm.failed_label() writes is what every consumer actually
#: tests -- match.py:285 excludes tombstones with NOT LIKE 'FAILED:%',
#: evals/corpus.py:171 buckets them the same way -- so a suffix carries the
#: reason without moving any predicate, and job_facts grows no column.
INPUT_REJECT_LABEL = "input-markup"


def prompt_description(job):
    """The description text a prompt will actually carry.

    ONE definition, two callers -- build_prompt() and the gate below -- for the
    same reason _eligible_sql() exists. A gate that judged the whole stored
    description while the prompt only ever sees the first MAX_DESCRIPTION_CHARS
    would reject postings over bytes no model was ever going to read.
    """
    return (job.get("description_text") or "")[:MAX_DESCRIPTION_CHARS]


def markup_ratio(text):
    """Share of `text` occupied by whitespace-delimited tokens that are markup.

    Pure -- no I/O, no clock -- in the spirit of vote_facts() and
    match.score_job(), so the threshold above can be re-swept over a corpus
    without a database or an LLM call.

    Token-level rather than match-level: `data-testid="conversation-turn-136"` is
    one leaked token of 38 characters, and counting the four-character signature
    inside it would price a heavily contaminated prompt the same as a lightly
    contaminated one. The +1s are the whitespace that split() consumed, so a
    window that is entirely markup scores 1.0 rather than something short of it.
    """
    if not text:
        return 0.0
    leaked = sum(len(t) + 1 for t in text.split() if _MARKUP_RESIDUE.search(t))
    return leaked / (len(text) + 1)


def is_unusable_input(job):
    """Is this posting's prompt window markup rather than a job posting?

    Called twice per rejected job -- once by extract_facts() to decide, once by
    extract_one_job() to label the tombstone. That is deliberate over threading a
    reason through extract_facts()'s return tuple: it is a pure function of the
    job dict, so two calls cannot disagree, and the alternative would have
    widened a 4-tuple that three tests and one caller already unpack.
    """
    return markup_ratio(prompt_description(job)) >= MARKUP_REJECT_RATIO


def build_prompt(job):
    description = prompt_description(job)
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
    (schema.py:386), so the join is at most one row per posting and cannot
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
    "REMOTE_ANYWHERE", "QA/Test" -- because rejecting those would tombstone a
    perfectly good extraction over formatting. Anything still unrecognised
    becomes the default rather than being stored: see the closed-vocabulary
    note in the module docstring.

    "/" is a separator like "-" and " ". The module docstring has always named
    "Senior/Mid" as a shape that must not silently score as unknown, and this
    is the line that was failing to deliver it: a slash survived the two
    replaces, so "QA/Test" matched nothing. Consequence, stated because it is
    a real judgement and not free: a compound answer now resolves to the value
    named FIRST in the string ("Senior/Mid" -> senior, "Mid/Senior" -> mid)
    rather than to NULL. That is the same first-wins arbitration the prefix
    rule below already applies to "mid_level" and "full_time_employee", the
    vocabularies are single-valued so SOMETHING has to be discarded, and a
    value the posting names beats a null it does not.
    """
    if not isinstance(value, str):
        return default
    v = (value.strip().lower()
         .replace("-", "_").replace(" ", "_").replace("/", "_"))
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


def _tristate_bool(value):
    """True, False, or None for "the response did not say".

    bool() used to be here, and it laundered three different things into
    False: an explicit false, an absent key, and an answer that was not a
    boolean at all. Only the first is evidence about the posting. The other
    two are the extractor failing, and match.py can price a NULL at the
    unknown rate but cannot price a False that was really a shrug -- which
    systematically rewarded the postings extraction did worst on, exactly the
    bias tranche_two/11 section 3 exists to remove.

    A non-bool is None rather than truthiness-tested, so the model answering
    1, "true" or "yes" reads as "could not tell" instead of as a confident
    True. That is the conservative direction: these four fields are scored,
    and inventing a True from a string is how a posting gets penalised for a
    requirement it never stated.
    """
    return value if isinstance(value, bool) else None


def normalize(result):
    """Model output -> the exact column values job_facts stores.

    Returns None when the response cannot be used at all, which the caller
    turns into a tombstone.

    ABSENCE SURVIVES THIS FUNCTION. Every enum below used to carry a default
    -- "other", "none", "unknown" -- so a field the model never answered was
    stored as a real-looking value, and match.py could not tell the two apart.
    A NULL role_archetype and a role_archetype the extractor guessed at score
    identically only if you never write the NULL down. So the defaults are
    gone: unrecognised or absent is None, and the columns are nullable to hold
    it. employment_type and visa_sponsorship keep theirs, because "unknown" is
    a legitimate VALUE in those two vocabularies (a posting really does say
    nothing about sponsorship) and nothing scores them either way.
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
    archetype = _enum(result.get("role_archetype"), ARCHETYPE)

    # THE "NOTHING USABLE CAME BACK" GUARD. Treat as unparseable rather than
    # writing a row that is NULL in every column that matters.
    #
    # It used to read `archetype == "other"`, which was only ever correct
    # because "other" was ALSO the default the line above returned for an
    # absent or unrecognised answer -- i.e. it was using "other" as a proxy
    # for "the model said nothing useful". Now that the default is None, that
    # comparison would silently stop firing on exactly the responses it exists
    # to catch, and junk would be stored instead of tombstoned.
    #
    # `archetype in (None, "other")` is EXACTLY the old predicate, not an
    # approximation of it: _enum(x, ARCHETYPE, "other") returns "other" iff x
    # coerced to "other" OR nothing matched and it fell through to the
    # default, i.e. iff _enum(x, ARCHETYPE) is "other" or None. Same
    # responses tombstone as before -- test_extract.py asserts the equivalence
    # over a matrix of raw values rather than trusting this paragraph.
    #
    # What changed is downstream, and is the point: a model that explicitly
    # answers "other" ("none of these archetypes fit") now stores "other",
    # while a model that answered nothing recognisable stores NULL. Those were
    # the same value before and they are different evidence.
    if (seniority is None and archetype in (None, "other")
            and not stack and not summary):
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
        "role_track": _enum(result.get("role_track"), ROLE_TRACK),
        "tech_stack": json.dumps(stack),
        "ai_involvement": _enum(result.get("ai_involvement"), AI_INVOLVEMENT),
        "ml_research_required": _tristate_bool(
            result.get("ml_research_required")),
        "advanced_degree_required": _tristate_bool(
            result.get("advanced_degree_required")),
        "customer_facing": _tristate_bool(result.get("customer_facing")),
        "remote_policy": _enum(result.get("remote_policy"), REMOTE_POLICY),
        # "unknown" survives as a DEFAULT in these two alone: it is a real
        # value in both vocabularies rather than a stand-in for absence, and
        # nothing in match.py scores either field.
        "employment_type": _enum(result.get("employment_type"),
                                 EMPLOYMENT_TYPE, "unknown"),
        "comp_min": _int_or_none(result.get("comp_min")),
        "comp_max": _int_or_none(result.get("comp_max")),
        "comp_currency": (result.get("comp_currency") or None
                          if isinstance(result.get("comp_currency"), str)
                          else None),
        "gap_friendly_language": _tristate_bool(
            result.get("gap_friendly_language")),
        "visa_sponsorship": _enum(result.get("visa_sponsorship"), VISA,
                                  "unknown"),
        "summary": summary,
    }


_FACT_COLUMNS = ("seniority_level", "years_experience_min",
                 "years_experience_max", "role_archetype", "role_track",
                 "tech_stack",
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
#:
#: role_track votes exactly like its neighbours -- it is a closed-vocabulary
#: string that is None when unknown, which is the case _majority_value() was
#: already written for. Adding it also widens _majority_pass_index()'s
#: agreement vector by one, which is intended: the pass whose track the vote
#: endorsed is more likely to be the pass whose prose describes the same
#: reading of the posting.
VOTE_ENUM_FIELDS = ("seniority_level", "role_archetype", "role_track",
                    "ai_involvement", "remote_policy", "employment_type",
                    "visa_sponsorship", "comp_currency")

#: Plain majority, same rule -- and these are now TRI-STATE. normalize() used
#: to force them through bool(), so None could not occur; it no longer does,
#: because an absent answer and an explicit false are different evidence (see
#: _tristate_bool). None votes here for the same reason it votes above: two
#: passes that could not tell outrank one that claimed it could.
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
    integers -- 16 of the 18 columns): the share of them on which every pass
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
        """,  # noqa: S608 -- splices schema.FACTS_TABLE and _FACT_COLUMNS -- both module-level constants
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

    IT CLEARS THE FACT COLUMNS, and that is a fix rather than tidying. This is
    the same hole score.mark_score_failed() closed one stage over, left open
    here: the ON CONFLICT clause used to update only facts_version,
    extracted_at and extraction_model, so a posting that extracted cleanly at
    v2 and tombstoned at v3 kept its v2 summary, seniority_level, archetype,
    remote_policy and comp fields -- stamped with the CURRENT facts_version and
    labelled 'FAILED:'. A row whose facts say one thing and whose provenance
    says another, and every reader that does not also select extraction_model
    believes the facts.

    match.load_facts() does check, filtering `extraction_model NOT LIKE
    'FAILED:%%'` -- but ../schema.py's jobs_app view does not: it is a bare
    LEFT JOIN on job_facts, so the webapp served the stale values with no way
    to tell. Clearing them loses nothing real. The facts were evidence about a
    posting under a prompt that has since changed, and the attempt that would
    have refreshed them is the one that just failed.

    NO ROW LEAVES jobs_app BECAUSE OF THIS. The view's four completeness
    filters -- company_name, title, job_url, description_text -- are all on
    `jobs`, never on job_facts, so a tombstoned posting still lists; it lists
    with empty facts instead of wrong ones.

    extraction_passes and vote_unanimity go too. They describe a vote that
    produced values, and there are no values.
    """
    nulls = ", ".join(f"{c}=NULL" for c in _FACT_COLUMNS)
    conn.execute(
        f"""
        INSERT INTO {schema.FACTS_TABLE}
            (job_id, facts_version, extracted_at, extraction_model)
        VALUES (%s, %s, %s, %s)
        ON CONFLICT (job_id) DO UPDATE SET
            facts_version=EXCLUDED.facts_version,
            extracted_at=EXCLUDED.extracted_at,
            extraction_model=EXCLUDED.extraction_model,
            {nulls},
            extraction_passes=NULL,
            vote_unanimity=NULL
        """,  # noqa: S608 -- splices schema.FACTS_TABLE and _FACT_COLUMNS -- both module-level constants
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

    A FOURTH PATH RUNS FIRST AND SPENDS NOTHING. If the prompt window is
    markup rather than a posting (is_unusable_input above), this returns
    REJECTED before the model is reached: no call, no tokens, and a tombstone
    at the current FACTS_VERSION so it is not retried nightly. That is the same
    disposition an unusable RESPONSE earns, for the same reason -- it is
    evidence about the posting and not about the endpoint -- and it means a
    FACTS_VERSION bump gives the row one more chance, which is the right
    behaviour if the employer has since fixed their job description.

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
    # BEFORE build_prompt(), and before `call` is even resolved, so that "this
    # costs zero LLM calls" is structural rather than a claim in a comment.
    if is_unusable_input(job):
        if DEBUG_PRINT_KEYS:
            log.debug(f"rejecting {job['id']} ({job.get('title')!r}): "
                      f"markup_ratio="
                      f"{markup_ratio(prompt_description(job)):.3f}")
        return REJECTED, None, 0, None

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
                log.debug(f"deferring {job['id']} ({job.get('title')!r}): {e}")
            continue
        except (RuntimeError, json.JSONDecodeError) as e:
            if DEBUG_PRINT_KEYS:
                log.debug(f"extraction call failed for {job['id']}: {e}")
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

        # Same tombstone, different label: an input the gate refused to send
        # and a response the model could not produce are both REJECTED, but
        # only one of them is evidence about the MODEL.
        label = (f"{INPUT_REJECT_LABEL}/{model_label}"
                 if is_unusable_input(job) else model_label)
        mark_extract_failed(conn, job["id"], label)
        if DEBUG_PRINT_KEYS:
            log.debug(f"unusable extraction for {job['id']} "
                      f"({job.get('title')!r}) -> {llm.failed_label(label)}")
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

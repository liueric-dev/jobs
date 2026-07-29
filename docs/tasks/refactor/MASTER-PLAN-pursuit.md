# MASTER PLAN — retargeting `jobs` at the Pursuit AI-Native cohort

**Written** 2026-07-28, against `webapp-service` @ `dd49a27`.
**Supersedes** `PLAN-scoring-and-ranking.md`, the roadmap in `backend/docs/SCORING.md`,
and the next-move recommendation in `backend/docs/HANDOFF-match-quality.md` §3.
**Does not supersede** `docs/scoring.md` (2026-07-27) — that remains the accurate
description of how the system works today, and is the input to this plan.

---

## 1. Scope — locked

| decision | value |
|---|---|
| Primary users | ~30 Pursuit AI-Native Builders per cohort, rolling |
| Author's role | **Builder, not staff.** No roster access, no instructor authority, no placement data |
| Target roles | Entry-level, AI-adjacent (`ai_involvement = uses_ai_tools`), **all industries** |
| Geography | NYC metro |
| Tenancy | **One cohort profile.** `role_track` is a fact, not a profile |
| Author's own profile | Retained as second tenant / regression test |
| Budget | Effectively $0. Constraint is **quota and wall-clock**, not dollars |
| Hosting | Home server, Cloudflare Tunnel |
| Corpus | Fresh start acceptable; existing 11,517 rows retained as substrate |
| Community feature | Pooled corpus, **anonymous** cohort signal |
| Display | Tracks + reasoning. **No 0–100 score surfaced** |

Two consequences worth stating plainly because they constrain everything downstream:

- **There will never be outcome labels.** No ATS callback, no institutional placement
  data, and self-reported status decays. `applied` is the terminal signal, and it
  measures intent, not result. Any design that assumes outcome calibration is dead
  on arrival.
- **There is no single target role.** Builders are at different stages with a
  hands-off curriculum. The shared floor — entry-level, AI-adjacent, NYC, no degree
  required — is well-defined. Anything narrower is invented.

---

## 2. What already exists

More than the earlier plans assumed. Read this before scoping any task.

**Landed and working:**
- Four-stage pipeline: `relevance.py` → `extract.py` → `match.py` → `score.py`
- 11,517 job rows, 2 active profiles, `FACTS_VERSION = 2`
- Six ingest sources; `run-daily.py` orchestrates nine steps under systemd
- **Google SSO, session cookies, `require_user`** (`docs/tasks/job_ingest/03`, done)
- **`GET /v1/jobs`, `GET /v1/jobs/{id}`, `POST /v1/events`** (task 04, done)
- `app_users` / `app_sessions` / `oauth_logins`, `jobs_web` role, admin CLI (task 02)
- Per-profile `relevance_json`, and `relevance.union_sql()` — the gate **already
  serves N profiles with different configs in one pass**
- Measurement tooling: `calibrate-match.py`, `compare-extract.py`,
  `relevance-report.py`, `learned-ranker-probe.py`, `cost-test.py`
- **`backend/api/`** — the contributor service: volunteers claim stale queries and
  run them against SerpApi **with their own keys**, posting raw results back.
  Built, tested, **never deployed**, and `docs/tasks/README.md` records it as
  expected-to-be-deprecated

**Not built:**
- `frontend/` — a single `.gitkeep`
- Any path from signup to a criteria vector
- Any reader of `job_events` beyond `score.py:_recently_active`

**The contributor API is the community feature, and it should be revived rather
than deprecated.** The architecture matters: each Builder runs their own worker
against their own free 250 searches/month. That is thirty people each using their
own allocation within its limits — not one application exceeding one allocation.
It is materially more defensible than key-pooling, it degrades gracefully when a
Builder graduates, and it is already written.

---

## 3. Architecture — what changes

**Unchanged:** the four-stage split, the shared-`job_facts` / per-profile-scores
invariant, version-keyed incremental recompute, `match_reasons`, `score_job()`
purity, all measurement tooling, auth, the events endpoint.

**Changed, and only here:**

| # | change | why |
|---|---|---|
| 1 | Relevance gate becomes **description-first** | `title_include` is `engineer\|software\|developer\|swe\|…`. An operations role using ChatGPT daily never reaches extraction. Postgres full-text over `description_text`; free, no LLM |
| 2 | `role_archetype` vocabulary becomes a **superset** | Twelve software values. A non-tech ops role extracts as `other` = 0 delta = indistinguishable from unknown |
| 3 | New fact: **`role_track`** | Cluster label derived from the corpus. Groups the UI, replaces per-track profiles |
| 4 | `criteria.json` → **cohort profile** | Current weights target mid-level forward-deployed engineers. `new_grad: -40` zeroes out the population |
| 5 | Ingest sources **rebuilt** | Every current source is tech-company-shaped |
| 6 | Event schema gains **`rank`, `request_id`, `dwell_ms`, `reason`, `visibility`** | Position bias is uncorrectable without rank; skip-above is underivable without request_id |
| 7 | `job_scores` gains **`persona_version`, `prompt_version`** | Editing a persona currently re-scores nothing |
| 8 | Explicit **missingness** on every nullable feature | Only `seniority` has `unknown_penalty`. A NULL archetype scores identically to on-target |

Items 2, 3 and 8 all require a `FACTS_VERSION` bump. **Do them in one bump, not
three.** At ~$0.000385/posting that is roughly $4 for the full corpus — and it
simultaneously re-validates `ai_involvement`, which was extracted under a prompt
written for software roles and has never been checked on non-tech text.

### On `ai_involvement` — the classifier already exists

`job_facts.ai_involvement` carries `builds_llm_features / uses_ai_tools / none /
core_ml_research`. **`uses_ai_tools` is "AI-adjacent."** There is no new classifier
to build and no new cost centre. What is missing is only that the gate never
surfaces those postings (change 1) and that `criteria.json` weights `uses_ai_tools`
at 6, below `builds_llm_features` at 12 — an ordering that inverts for Builders.

### On tracks — why a fact, not a profile

Eight track profiles would cost eight hand-authored `criteria.json` files.
Hand-tuning weights is precisely what `learned-ranker-probe.py` identified as the
bottleneck; eight unvalidatable configs is worse than one. Compute is not the
constraint — `job_matches` is arithmetic, and narratives are already gated by
`--active-within-days` and narrative-on-login, so tracks nobody opens generate
nothing.

`role_track` as a `job_facts` column gets the browsable-role-families product with
one config. If a track later proves to need its own weights, promote it to a
profile — `profiles` already supports that, so nothing is foreclosed.

---

## 4. The contracts

Settle these before writing code; they are expensive to change later.

**C1 — Labels.** Three layers, and never evaluate on the layer you trained on.

| layer | source | train | evaluate |
|---|---|---|---|
| L0 | human (≈10 Builder volunteers × 20 postings) | never | always |
| L1 | `job_scores.fit_score` | yes | cheap iteration only |
| L2 | `job_events` | not yet | sanity signal |

L0 is collected on **two independent axes**, and the distinction is the whole point:

- **Axis A — is the extraction correct?** Objective, persona-independent, transfers
  to every future user and every future vertical. Validates `job_facts`, the one
  tier computed once and shared forever. Never measured against a human;
  `compare-extract.py` measures the model against *itself*.
- **Axis B — would you apply?** Subjective, cohort-bound.

**C2 — Events.** Append-only, scores recorded as-of impression.

```sql
job_events (
    id, profile, job_id, event,
    request_id  TEXT NOT NULL,   -- NEW: groups one rendered list
    rank        INTEGER,         -- NEW: 1-based position
    dwell_ms    INTEGER,         -- NEW: 'open' only; gate/weight, never a label
    reason      TEXT,            -- NEW: dismiss enum
    visibility  TEXT NOT NULL,   -- NEW: 'private' | 'cohort_anon'
    match_score, fit_score, model_version, occurred_at
)
```

`skip` is derived server-side, never client-sent: an `open` at rank *k* marks
un-actioned impressions at rank < *k* in the same `request_id` as examined-and-passed.

`visibility` encodes the community decision: saves and finds are `cohort_anon`
(aggregated to "4 Builders saved this", never attributed); applications are
`private`. Thirty people competing for entry-level roles should not see who else
applied.

**C3 — Features.** A declared, versioned list. Every feature must be computable for
a posting first seen five minutes ago and a profile created five minutes ago. Every
nullable feature carries an `is_missing` indicator.

**C4 — Versions. DONE 2026-07-29.** Every derived row records every upstream
version; a row is stale iff any *recorded* version differs. True for `job_matches`,
and now for `job_scores`: `facts_version`, `persona_sha`, `prompt_version` and
`criteria_version`, with `select_shortlist()` version-aware rather than
existence-aware.

Three deviations from what this line asked for, each recorded in `DECISIONS.md`:
`persona_version` is a **content digest, not an integer** with a bump discipline;
`criteria_version` is stored but **deliberately excluded from the staleness
predicate**, because criteria decide which jobs are asked about and never what is
asked; and `model_version` was not added because `scoring_model` already is it.

The clause "a row is stale iff any differs" needed one correction to be
implementable: a row that records *nothing* is unknown rather than stale, and
collapsing the two would have marked all 1,018 pre-existing rows stale — and
payable — the instant the columns landed.

**C5 — Explanations.** `match_reasons` survives any ranker change. This rules out
gradient-boosted trees in favour of linear models, deliberately: `coefficient ×
value` drops into the existing `{"rule", "delta"}` shape at zero cost, and both the
webapp and `calibrate-match.py` depend on it.

---

## 5. Sourcing

Ranked by payoff per unit effort. All free.

| tier | source | yields | effort |
|---|---|---|---|
| 1 | **NYC Open Data `kpav-sd4t`** — SODA API, free app token | Full descriptions, salary, **explicit `post_until` closure date**. ~20–60 new external postings/day, City agencies | Low |
| 1 | **Adzuna** free API (~1,000 calls/mo) | Broad multi-industry NYC, descriptions + salary | Low |
| 2 | **Public ATS feeds** — Greenhouse, Lever, Ashby, Workable, Recruitee, SmartRecruiters | Full descriptions, clean closure detection. ~50–150/day at a few hundred tokens | Medium — the work is *company discovery*, not fetching |
| 2 | **USAJobs** free API | Federal NYC, explicit close dates. ~5–15/day | Low |
| 3 | **schema.org/JobPosting JSON-LD** from Workday/iCIMS career pages | **The only free route to hospitals, insurers, universities** — the "all industries" promise lives here | High |
| 3 | **Idealist**, nonprofit boards | Mission-aligned; per-listing expiration | Medium |
| supp | **Contributor API** (existing, revive) | Google Jobs via Builders' own keys | Already built |

**Retire or demote:** `builtin-nyc`, `weworkremotely`, `hn-hiring` are tech-company
sources and no longer serve the population. Keep them running for the author's
second profile; drop them from the cohort gate.

**Free-tier tooling** where plain HTTP is not enough: Apify ($5/mo, prebuilt actors
for Indeed/Glassdoor, ATS discovery), Firecrawl (1,000/mo, JSON-LD career pages —
note it hard-blocks LinkedIn), JobsPipe (100/mo, the only free Workday/iCIMS reach).
Apify's **Creator Plan grants $500 over 6 months for publishing an Actor** — a
published "NYC entry-level AI-adjacent jobs" Actor is portfolio artifact and funding
in one move.

**Do not** scrape LinkedIn. Reddit's October 2025 suit named SerpApi and Oxylabs;
Google sued SerpApi in December 2025. The DMCA claims were dismissed, but the terrain
is live and this is a nonprofit's students.

---

## 6. Phases

Each ends in a gate. A failed gate sends you back, not forward. These map 1:1 onto
`docs/tasks/pursuit/NN-*.md` following the existing convention.

### Phase 0 — Baseline (no code changes; do first)

1. **Quota and wall-clock test.** Rewrite `cost-test.py` to measure requests/day,
   requests/minute, and wall-clock — not dollars. The current table prices
   `deepseek-v4-flash` while production runs `glm-4.5-flash`, described in
   `score.py:63` as the free-tier model. The binding constraint is almost certainly
   quota.
2. **Corpus volume under a widened gate.** Pure SQL, free: how many rows pass a
   description-first AI-adjacent gate? This is the multiplier on everything.
3. **`FACTS_VERSION` bump dry run** at corpus scale. It has been bumped once; verify
   the full re-extraction path completes within the nightly window before depending
   on it.

**GATE 0.** Nightly extraction at the projected new volume fits the window and the
quota. If it does not, `max_tier_to_score` is the throttle and the plan proceeds with
a smaller corpus.

### Phase 1 — Retarget the pipeline

4. Description-first matching in `relevance.py`, config-driven; cohort `relevance_json`.
5. Archetype superset + `role_track` + missingness indicators; **one** `FACTS_VERSION`
   bump; re-extract.
6. Cohort `criteria.json`: entry-level target, `uses_ai_tools` weighted above
   `builds_llm_features`, `new_grad` and `intern` no longer penalised, non-tech
   archetypes weighted.

**GATE 1.** A hand-picked list of 20 postings that *should* qualify (drawn from real
Pursuit-relevant roles) all pass the gate and extract with correct `ai_involvement`.

### Phase 2 — Sourcing rebuild

7. NYC Open Data ingest.
8. ATS company discovery for NYC non-tech employers + token list; retarget `ats.py`.
9. USAJobs + Adzuna ingest.
10. JSON-LD parser for Workday/iCIMS career pages.
11. Revive `backend/api/` contributor service; deploy behind the tunnel.

**GATE 2.** ≥200 new Pursuit-relevant postings/day across sources, with closure
detection working on at least NYC Open Data and the ATS feeds.

### Phase 3 — Multi-tenancy and events

12. Profile creation via API — the gap `migrate_profiles.py` currently fills by hand.
    Auth already exists; this is the missing half.
13. Event schema migration (C2) + server-side `skip` derivation + replay tests.
14. Anonymous cohort aggregation (`cohort_anon` counts on the list endpoint).

**GATE 3.** One rendered list produces a complete `request_id` group: impressions at
every rank, and an `open` at rank *k* producing *k−1* skips. Verify by hand once —
silent event bugs are undetectable later.

### Phase 4 — Ground truth

15. Two-axis labelling session with ~10 Builder volunteers, 20 postings each,
    stratified: top-20, the 20–50 boundary, below-floor, and gate-rejected. The
    rejected bucket is the only way to estimate recall.
16. Compute Axis A agreement (extraction correctness) and Axis B agreement
    (`fit_score` vs Builder preference). Working bar: κ ≥ 0.6.

**GATE 4.** If Axis A is poor, the extraction prompt is wrong for non-tech text and
Phase 1 repeats. If Axis B is poor, `persona.json`'s rubric is wrong. Either way,
do not proceed to ranking work on an unvalidated label.

### Phase 5 — Ranking and display

17. Within-track ordering; buckets not scores; `gap_bridging_angle` promoted to the
    primary narrative output.
18. Dismiss demotes persistently, and specifically — a `wrong_level` dismiss is
    evidence about the seniority weight, not about one posting.

**GATE 5.** Precision@20 measured **within track** against L0 beats the current
rules baseline, with a paired bootstrap CI excluding zero.

### Phase 6 — Frontend and deployment

19. Frontend against the existing endpoints.
20. Cloudflare Tunnel; split the nightly pipeline (home, no inbound, no uptime SLA)
    from the webapp (needs both).

---

## 7. Not doing

- **Per-Builder criteria authoring.** One cohort profile. Revisit only if L0 shows
  Builders disagreeing with each other more than with the cohort config.
- **The learned ranker, for now.** `learned-ranker-probe.py`'s 12.7/20 was measured
  against the author's persona and is an imitation-fidelity number besides. Re-run
  the probe after Phase 4 against L0 before investing.
- **New extraction fields** beyond `role_track`. `HANDOFF-match-quality.md` §5
  remains correctly shelved.
- **Embeddings, two-tower, LLM-as-ranker.** Retrieval is not the problem at this
  corpus size, and the rule that LLMs explain but never rank stands.
- **Résumé upload, initially.** See §9.
- **LinkedIn, at all.**

---

## 8. Measurement

Inherit all seven traps from `HANDOFF-match-quality.md` §4 — that section is
domain-independent and is the most durable asset in the docs. Three additions:

1. Never evaluate on the layer you trained on.
2. Pin the L0 set by sorted `job_id`; never train on it; top up with fresh stratified
   samples rather than recycling.
3. Report average precision as the measurement, precision@20 as the objective. A
   count of twenty cannot resolve the differences being decided on.

North-star metric: **dismiss-to-apply ratio on the top 20**, computable from events
already defined, and the metric LinkedIn used for the equivalent rework.

---

## 9. Operations

- **Cloudflare Tunnel**, not port forwarding: no static IP, no open inbound ports,
  TLS handled, sidesteps residential-ISP server restrictions.
- **Split pipeline from app.** The nightly job needs no inbound connectivity and no
  uptime guarantee. The webapp needs both. A power cut should cost one night of
  ingest, not thirty people's access.
- **Free-tier key rotation is the real operational risk.** Four providers, any of
  which can rate-limit or revoke without notice. Fewer sources done reliably beats
  many done fragilely. Alert on ingest volume dropping, not on errors — a silently
  revoked key returns zero rows, not an exception.
- **PII.** `user_facts` from résumé uploads means storing personal documents for
  thirty low-income adults on a residential connection. Prefer a structured
  onboarding form; if résumés are used, extract fields and discard the source.
  Defer entirely until there is somewhere better to put it. This is a
  responsibility question, not only a technical one.

---

## 10. Documentation

The repo already answers this question — the practice just needs applying
consistently. There are **two kinds of document here and they have opposite
lifecycles**:

**Generated reference** (`docs/ingest/*.md`, 11 files, ~4,600 lines) carries YAML
frontmatter with `script:`, `commit:`, `generated:`. These are derived artifacts.
**Regenerate them at phase boundaries; never hand-edit.** Their provenance header is
what makes staleness detectable — a doc generated at `dd49a27` against a file that
has since changed is visibly, mechanically stale. Regenerating is cheap and
intermediate states are noise.

**Hand-written rationale** (`docs/scoring.md`, `backend/docs/*.md`) is the opposite.
Write it at decision time, because the reasoning is freshest then and cannot be
reconstructed later. The proof is in `config/relevance.json`'s `_comment` fields —
*"Rejected alternative: flag rows where SerpApi's `via` field matches company_name.
It catches 160 rows but false-positives on every company posting to its own careers
site"* — nobody reconstructs that six months on. It is the single most valuable
convention in the repo and it should continue in every new config.

**So: neither update-as-you-go nor regenerate-at-the-end. The rule is by document
type.** For hand-written docs the practice is **staleness markers, not continuous
rewriting** — mark a doc superseded the moment it becomes wrong (one line at the
top, thirty seconds), and fix it properly at a phase boundary. Three half-updated
docs are worse than one honestly-stale doc, because you cannot tell which is current.

### Specific dispositions

| document | disposition |
|---|---|
| `docs/scoring.md` (784L, 2026-07-27) | **Keep as the current-state reference.** Add a header noting it describes the pre-Pursuit system. Regenerate the measured figures after Phase 1 |
| `backend/docs/SCORING.md` (516L) | **Archive.** Superseded by `docs/scoring.md`; two hand-written scoring docs is drift |
| `backend/docs/HANDOFF-match-quality.md` | **Split.** §4 (the seven traps) is domain-independent — promote to `docs/MEASUREMENT-TRAPS.md`. The rest is persona-bound findings → `docs/archive/` with a header stating what it measured and why it does not transfer |
| `docs/ingest/*.md` | Regenerate at each phase boundary. Delete the three for retired sources |
| `docs/tasks/job_ingest/` | **Never rewrite.** Append-only historical record; all five are marked done and that record is accurate |
| `docs/ingestion_tests/` | Review — six hand-written planning docs. Fold what survives into the new task tree |
| `backend/api/README.md` | Update: "never deployed / expected to be deprecated" is now wrong. It is the community feature |
| `README.md`, `backend/README.md`, `DEVELOPER.md` | **Regenerate at the end.** Operational reference; stale operational docs actively mislead |
| `PLAN-scoring-and-ranking.md` | Superseded by this document. Archive |

### Create

- `docs/tasks/pursuit/README.md` + `01`–`20`, following the existing table convention
- `docs/archive/` with a `README.md` explaining that everything inside was measured
  against the author's software-engineer persona and does not transfer
- One line at the top of every archived doc: what it measured, when, and what
  superseded it

---

## 11. Risks

| risk | mitigation |
|---|---|
| Extraction degrades on non-tech postings | Axis A labels, Phase 4. This is why the two-axis split exists |
| Widened gate blows the nightly window | Phase 0 measures it before anything is built; `max_tier_to_score` throttles |
| Free-tier key revoked silently | Alert on volume drop, not errors; multiple independent sources |
| Cohort churns; a class ends | Corpus and role tracks persist; profiles are cheap to recreate |
| Home server outage | Split pipeline from app; tunnel |
| L0 volunteers do not materialise | 10 Builders × 20 is the floor; 5 × 20 still beats zero |
| Author graduates | The contributor model degrades gracefully; document the runbook early |
| Scam/ghost postings reaching inexperienced users | ATS and public-sector sources are employer-verified; retiring Google-Jobs-as-primary removes the relister vector that `relevance.json` already documents |

---

## 12. The one-paragraph version

Fold into the existing repo — the data model is already multi-tenant, the gate
already serves N profiles in one pass, auth and the events endpoint already landed,
and the contributor service that implements the community feature is already
written. Retarget rather than rebuild: one description-first gate, one archetype
superset, one `FACTS_VERSION` bump, one cohort profile, and `role_track` as a fact so
Builders get browsable role families without eight hand-authored configs. Rebuild
ingest around NYC Open Data, public ATS feeds, USAJobs, Adzuna and JSON-LD, because
every current source is tech-company-shaped and the population is not. Instrument
events with rank and request_id before the frontend exists, because that is the only
thing that cannot be backfilled. Then stop and collect human labels on two axes —
extraction correctness, which transfers forever, and Builder preference, which does
not — because every quality number in the repo is currently anchored to an
unvalidated proxy for one software engineer's taste. Ranking work resumes only after
that. Cost is not the constraint; quota, wall-clock, and the operational fragility of
four free-tier keys on a home server are.

# docs/tasks/pursuit/

Work breakdown for retargeting the pipeline from one software engineer's job
search to the Pursuit AI-Native cohort — ~30 Builders, entry-level, AI-adjacent
roles, all industries, NYC.

The full reasoning is in [`MASTER-PLAN-pursuit.md`](../../../MASTER-PLAN-pursuit.md),
[`SOURCING-STRATEGY.md`](../../../SOURCING-STRATEGY.md) and
[`ADDENDUM-google-jobs-providers.md`](../../../ADDENDUM-google-jobs-providers.md).
This file is the ordered index.

It absorbs the outstanding work from
[`docs/ingestion_tests/`](../../ingestion_tests/) — tasks 03, 04 and 05 there
become 07, 08 and 09 here — because the evals harness turned out to be on the
critical path rather than beside it. See [Why evals moved to the front](#why-evals-moved-to-the-front).

## Phase 0 — Prerequisites and truth

Nothing downstream is trustworthy until these land. None of them are large.

| | Task | Lands | |
|---|---|---|---|
| 01 | [Pin the production model](01-pin-production-model.md) | one answer to "what runs in production", enforced in code | done |
| 02 | [Triage the ingest audit defects](02-triage-audit-defects.md) | [`docs/ingest/DEFECTS.md`](../../ingest/DEFECTS.md) — 42 defects enumerated, classified, scheduled | done |
| 03 | [Stop discarding upsert errors](03-fix-silent-upsert-errors.md) | `UpsertResult.errors` read in every ingest path — all 8 sites | done |
| 04 | [Quota and wall-clock baseline](04-quota-baseline.md) | `cost-test.py` measuring requests and seconds, not dollars — **the binding constraint is `EXTRACT_BATCH_SIZE=40`, not quota** | done |
| 05 | [Corpus volume under a widened gate](05-widened-gate-volume.md) | a number: how many rows a Pursuit gate would admit — **N = 43/day**, [`docs/pursuit-gate-volume.md`](../../pursuit-gate-volume.md) | done |
| 06 | [Re-run self-consistency at n=120](06-self-consistency-n120.md) | whether the 76% figure is real — **no; and the gate says STOP**, `ai_involvement` 77.8% on hn_whoishiring | done |
| — | Extraction policy — the two conversational decisions (`943d899`) | `config/extraction-policy.json`, `extract.vote_facts()`, `drain_loop()` — **selective majority-of-3 at +4.2% of calls, and the 40/day ceiling lifted**. No task file; see [`HANDOFF.md`](HANDOFF.md) | done |

## Phase 1 — Finish the evals harness

| | Task | Lands | |
|---|---|---|---|
| 07 | [Metrics and the golden set](tranche_two/07-metrics-and-golden-set.md) | `labels.py`, `/v1/label` behind the existing SSO, three-quantity measurement — **tooling built, zero labels; the labelling itself is task 29 and needs people** | done |
| 08 | [Score validation](tranche_two/08-score-validation.md) | `score.normalize()`, an `evals` score task, closes audit item 8 (D15) — **and the measurement task 30 needed: the bucket reproduces at 89%, the number at 24%**, [`docs/score-validation.md`](../../score-validation.md) | done |
| 09 | [Fetcher harness](tranche_two/09-fetcher-harness.md) | HTTP cassettes and a scratch DB for the non-LLM scripts — all six sources | done |

## Phase 2 — Retarget the pipeline

| | Task | Lands | |
|---|---|---|---|
| 10 | [Description-first relevance gate](tranche_two/10-description-first-gate.md) | AI-tool vocabulary matched against `description_text` — **876 rows eligible for the cohort, 573 newly, 13.2/day; precision 10.0% vs task 05's 6.7%**, [`docs/pursuit-description-gate.md`](../../pursuit-description-gate.md) | done |
| 11 | [Archetype superset, `role_track`, missingness](tranche_two/11-archetype-superset-role-track.md) | 12 archetypes → **26**, derived from the corpus; provisional 9-value `role_track`; `normalize()` stops laundering absence into sentinels — **`other` was mostly a TECH gap: 203 of 427 reclaimed by tech values, 54 by ops**, [`docs/role-track-derivation.md`](../../role-track-derivation.md) | done |
| 12 | [`FACTS_VERSION` bump and re-extract](tranche_two/12-facts-version-bump.md) | one bump carrying 11's changes — **and the extraction gate retargeted to `pursuit`, which took the bump from 5,317 rows to 863. `other` ROSE to 31.1%**, [`docs/facts-v3-diff.md`](../../facts-v3-diff.md) | done |
| 13 | [Cohort criteria profile](tranche_two/13-cohort-criteria-profile.md) | entry-level target, `uses_ai_tools` weighted above `builds_llm_features` — **done; 144 matched of 859. DoD 122-123 partially unmet and deliberately not tuned into being met: 16/20 above floor, 10/20 in the top 20** | done |

## Phase 3 — Sourcing

| | Task | Lands | est. relevant/day |
|---|---|---|---|
| 14 | [NYC Open Data ingest](tranche_three/14-ingest-nyc-open-data.md) | `kpav-sd4t` via SODA; `post_until` closure — **done; measured ~1.8/day, not 20–60**, [`docs/ingest/nyc-open-data.md`](../../ingest/nyc-open-data.md) | ~~20–60~~ **1.8** |
| 15 | USAJobs and Adzuna ingest | two free APIs | 35–95 |
| 16 | [ATS token discovery](tranche_three/16-ats-token-discovery.md) | seed list bootstrap, regex probe, `company_ats` table — **7 validated non-tech NYC tokens, 1,513 open jobs**; done |
| 17 | [Retarget `ats.py`](tranche_three/17-retarget-ats-ingest.md) | roster from `company_ats`; **six vendors** (3 new); closure conditional on reconciliation — done, [`docs/ingest/ats.md`](../../ingest/ats.md) | 50–150 |
| 18 | [Workday CXS ingest](tranche_three/18-ingest-workday-cxs.md) | `/wday/cxs/` + **upstream relevance gating** — done; 1,366 reachable/night from 4 tenants at 11% detail cost. **Yield deliberately not reported until task 13**, [`docs/ingest/workday.md`](../../ingest/workday.md) | re-measure |
| 19 | [JSON-LD parser](tranche_three/19-jsonld-parser.md) | measured before building — **2 of 55 employers publish `JobPosting`, 1 of 35 in the target population. DROPPED**, [`docs/jsonld-coverage.md`](../../jsonld-coverage.md) | ~~30–60~~ **≤1.1–2.3 (ceiling)** |
| 20 | iCIMS via Firecrawl | reserved 1,000 credits/month | 20–40 |
| 21 | Nonprofit boards | Idealist and peers — **premise broken: it was "cheap because task 19's parser does most of the work", and 19 is dropped. Re-scope or measure first** | 10–25, unverified |

## Phase 4 — Google Jobs

| | Task | Lands | |
|---|---|---|---|
| 22 | [JobSpy spike](tranche_four/22-jobspy-spike.md) | does self-hosted work from the home IP — **no: dropped**, [`docs/jobspy-spike.md`](../../jobspy-spike.md) | done |
| 23 | SERP abstraction | `serp/` package, provider adapters, quota ledger, router, cache — **descoped**: 2 adapters not 8, no JobSpy, no router step 2 | todo |
| 24 | Revive the contributor API | `backend/api/` deployed; Builder key onboarding | todo |
| 25 | Search queries | query as a first-class object, caching, cohort signal | todo |

## Phase 5 — Multi-tenancy and events

| | Task | Lands | |
|---|---|---|---|
| 26 | Profile creation API | the gap `migrate_profiles.py` fills by hand | todo |
| 27 | Event schema | `rank`, `request_id`, `dwell_ms`, `reason`, `visibility`, derived `skip` | todo |
| 28 | Anonymous cohort aggregation | "4 Builders saved this" without attribution | todo |

## Phase 6 — Ground truth

| | Task | Lands | |
|---|---|---|---|
| 29 | Two-axis labelling session | Axis A extraction correctness, Axis B Builder preference | todo |

## Phase 7 — Ranking and display

| | Task | Lands | |
|---|---|---|---|
| 30 | Within-track ordering | buckets not scores; `gap_bridging_angle` promoted | todo |
| 31 | Dismiss demotion | persistent, and specific to the reason given | todo |

## Phase 8 — Delivery

| | Task | Lands | |
|---|---|---|---|
| 32 | Frontend | against the endpoints that already exist | todo |
| 33 | Deployment | Cloudflare Tunnel; pipeline split from app | todo |

## Cross-cutting

| | Task | Lands | |
|---|---|---|---|
| 34 | [Documentation cleanup](34-documentation-cleanup.md) | archive, promote, regenerate — by document type | todo |
| 35 | [Extraction input sanity](tranche_six/35-extraction-input-sanity.md) | reject browser-DOM markup before it becomes facts; 0 false positives in 13,282 | done |

---

## Why evals moved to the front

[`docs/ingestion_tests/README.md`](../../ingestion_tests/README.md) records that
`deepseek-v4-flash` does not agree with itself at temperature 0 — 76% on
`seniority_level`, 94% on `ai_involvement`, whole-record identical 0 of 17.

Two facts make that decisive for this refactor rather than merely interesting.

**It is the production model.** Confirmed 2026-07-28. The finding is not a
hypothetical about a model nobody runs.

**The reconciliation predicts this refactor's main risk.** The README's own
explanation is corpus, not model: `compare-extract.py` selects `ORDER BY
first_seen DESC`, which is ~85% greenhouse and ashby — clean ATS postings — while
the stratified fixture includes HN free-text. So the reassuring 95% describes the
easy sources.

Every source added in Phase 3 moves *toward* the messy end: government boilerplate,
Workday free text, whatever an employer wrote into JSON-LD, nonprofit boards. The
Pursuit corpus will be systematically harder to extract than the current one, and
the evals harness is the only instrument that would detect it.

And `ai_involvement` is now the product. `uses_ai_tools` is the entire targeting
mechanism for the cohort — a 6% flip rate between identical runs on *clean* sources,
unmeasured on messy ones, decides whether the app works at all.

Hence: task 06 re-runs self-consistency at n=120 before anything is retuned, and
task 12's `FACTS_VERSION` bump is gated on task 07 so extraction quality is measured
on the new corpus before committing to a full re-extraction.

## The decisions this tree encodes

**One cohort profile, `role_track` as a fact.** Eight track profiles would mean
eight hand-authored `criteria.json` files, and hand-tuning weights is what
`learned-ranker-probe.py` identified as the bottleneck. `job_matches` is arithmetic
and narratives are already gated by `--active-within-days`, so tracks cost nothing
to carry. Task 11.

**The AI-adjacent classifier already exists.** `job_facts.ai_involvement` carries
`uses_ai_tools`. There is no new model to build — only a gate that never surfaces
those postings (task 10) and a weight that ranks them below `builds_llm_features`
(task 13).

**Fix silent failures before adding sources.** The audit found `UpsertResult` unpacked
as a three-tuple with `.errors` never read in at least four ingest scripts. Adding
five more sources multiplies that across nine paths. Task 03 precedes all of Phase 3.

**Quota, not dollars.** Free-tier scraping, a free-tier model and a home server mean
marginal cost is near zero. What binds is requests/day, wall-clock in the nightly
window, and the operational fragility of keys that fail *silently*. Task 04.

**Instrument events before the frontend exists.** `rank` and `request_id` cannot be
backfilled; every day of impressions logged without them is permanently
un-debiasable. Task 27 does not wait for task 32.

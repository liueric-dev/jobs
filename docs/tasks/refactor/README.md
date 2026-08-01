---
kind: contract
written: 2026-07-28
generator: none
---

# docs/tasks/refactor/

*(This tree was called `pursuit/` while it was being planned and is `refactor/` on disk. The old name survives in `MASTER-PLAN-pursuit.md` and a few task files, which are left as written.)*

Work breakdown for retargeting the pipeline from one software engineer's job
search to the Pursuit AI-Native cohort — ~30 Builders, entry-level, AI-adjacent
roles, all industries, NYC.

The full reasoning is in [`MASTER-PLAN-pursuit.md`](MASTER-PLAN-pursuit.md),
[`SOURCING-STRATEGY.md`](SOURCING-STRATEGY.md) and
[`ADDENDUM-google-jobs-providers.md`](ADDENDUM-google-jobs-providers.md).
This file is the ordered index. **[`AUDIT.md`](AUDIT.md) is the one-page state of the
run** — what is measured, with the instrument for each figure, and what is open.

It absorbs the outstanding work from
[`docs/ingestion_tests/`](../../ingestion_tests/) — tasks 03, 04 and 05 there
become 07, 08 and 09 here — because the evals harness turned out to be on the
critical path rather than beside it. See [Why evals moved to the front](#why-evals-moved-to-the-front).

## Phase 0 — Prerequisites and truth

Nothing downstream is trustworthy until these land. None of them are large.

| | Task | Lands | |
|---|---|---|---|
| 01 | [Pin the production model](tranche_one/01-pin-production-model.md) | one answer to "what runs in production", enforced in code | done |
| 02 | [Triage the ingest audit defects](tranche_one/02-triage-audit-defects.md) | [`docs/ingest/DEFECTS.md`](../../ingest/DEFECTS.md) — **45** defects enumerated, classified, scheduled (`D01`–`D45`; this row said 42 and `CLAUDE_UPDATES.md` said 41 — both were counts taken before `D43`–`D45` were added by tasks 08 and 19) | done |
| 03 | [Stop discarding upsert errors](tranche_one/03-fix-silent-upsert-errors.md) | `UpsertResult.errors` read in every ingest path — all 8 sites | done |
| 04 | [Quota and wall-clock baseline](tranche_one/04-quota-baseline.md) | `cost-test.py` measuring requests and seconds, not dollars — **the binding constraint is `EXTRACT_BATCH_SIZE=40`, not quota** | done |
| 05 | [Corpus volume under a widened gate](tranche_one/05-widened-gate-volume.md) | a number: how many rows a Pursuit gate would admit — **N = 43/day**, [`docs/pursuit-gate-volume.md`](../../pursuit-gate-volume.md) | done |
| 06 | [Re-run self-consistency at n=120](tranche_one/06-self-consistency-n120.md) | whether the 76% figure is real — **no; and the gate says STOP**, `ai_involvement` **77.8% (`pairwise`)** on `hn_whoishiring`. The three metrics and the command that reproduces them are owned by [`AUDIT.md`](AUDIT.md) § *The three self-consistency metrics* | done |
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
| 10 | [Description-first relevance gate](tranche_two/10-description-first-gate.md) | AI-tool vocabulary matched against `description_text` — **876 rows eligible for the cohort, 573 newly, 13.2/day; precision 10.0% vs task 05's 6.7%**, [`docs/pursuit-description-gate.md`](../../pursuit-description-gate.md). **Amended 2026-07-29:** it handed the description path a *title* entry-level vocabulary, so the conjunction could not be satisfied on a description — mock gate recall 48.3%. Fixed in Cross-cutting below; the figures above are unrestated | done |
| 11 | [Archetype superset, `role_track`, missingness](tranche_two/11-archetype-superset-role-track.md) | 12 archetypes → **26**, derived from the corpus; provisional 9-value `role_track`; `normalize()` stops laundering absence into sentinels — **`other` was mostly a TECH gap: 203 of 427 reclaimed by tech values, 54 by ops**, [`docs/role-track-derivation.md`](../../role-track-derivation.md). **Amended 2026-07-31:** that reclaim was measured over every `facts_version` the project has had — 58% of those rows predate the vocabulary being evaluated — so it describes the TWELVE-value corpus. At `facts_version = 3` the same nine tech values reclaim **9 of 294**, and the vocabulary is re-derived: one further value, `revenue_commercial`, is **proposed and deliberately not applied** while `pursuit-v1` is being labelled. DEC-64, DEC-65 | done |
| 12 | [`FACTS_VERSION` bump and re-extract](tranche_two/12-facts-version-bump.md) | one bump carrying 11's changes — **and the extraction gate retargeted to `pursuit`, which took the bump from 5,317 rows to 863. `other` ROSE to 31.1%**, [`docs/facts-v3-diff.md`](../../facts-v3-diff.md) | done |
| 13 | [Cohort criteria profile](tranche_two/13-cohort-criteria-profile.md) | entry-level target, `uses_ai_tools` weighted above `builds_llm_features` — **done; 144 matched of 859. DoD 122-123 partially unmet and deliberately not tuned into being met: 16/20 above floor, 10/20 in the top 20** | done |

## Phase 3 — Sourcing

| | Task | Lands | est. relevant/day |
|---|---|---|---|
| 14 | [NYC Open Data ingest](tranche_three/14-ingest-nyc-open-data.md) | `kpav-sd4t` via SODA; `post_until` closure — **done; measured ~1.8/day, not 20–60**, [`docs/ingest/nyc-open-data.md`](../../ingest/nyc-open-data.md) | ~~20–60~~ **1.8** |
| 15 | [USAJobs and Adzuna ingest](tranche_three/15-ingest-usajobs-adzuna.md) | two free APIs | 35–95 |
| 16 | [ATS token discovery](tranche_three/16-ats-token-discovery.md) | seed list bootstrap, regex probe, `company_ats` table — **7 validated non-tech NYC tokens, 1,513 open jobs**; done |
| 17 | [Retarget `ats.py`](tranche_three/17-retarget-ats-ingest.md) | roster from `company_ats`; **six vendors** (3 new); closure conditional on reconciliation — done, [`docs/ingest/ats.md`](../../ingest/ats.md) | 50–150 |
| 18 | [Workday CXS ingest](tranche_three/18-ingest-workday-cxs.md) | `/wday/cxs/` + **upstream relevance gating** — done; 1,366 reachable/night from 4 tenants at 11% detail cost. **Yield deliberately not reported until task 13**, [`docs/ingest/workday.md`](../../ingest/workday.md) | re-measure |
| 19 | [JSON-LD parser](tranche_three/19-jsonld-parser.md) | measured before building — **2 of 55 employers publish `JobPosting`, 1 of 35 in the target population. DROPPED**, [`docs/jsonld-coverage.md`](../../jsonld-coverage.md) | ~~30–60~~ **≤1.1–2.3 (ceiling)** |
| 20 | [iCIMS via Firecrawl](tranche_three/20-ingest-icims-firecrawl.md) | reserved 1,000 credits/month | 20–40 |
| 21 | [Nonprofit boards](tranche_three/21-ingest-nonprofit-boards.md) | Idealist and peers — **premise broken: it was "cheap because task 19's parser does most of the work", and 19 is dropped. Re-scope or measure first** | 10–25, unverified |

## Phase 4 — Google Jobs

| | Task | Lands | |
|---|---|---|---|
| 22 | [JobSpy spike](tranche_four/22-jobspy-spike.md) | does self-hosted work from the home IP — **no: dropped**, [`docs/jobspy-spike.md`](../../jobspy-spike.md) | done |
| 23 | [SERP abstraction](tranche_four/23-serp-abstraction.md) | `serp/` package, provider adapters, quota ledger, router, cache — **descoped**: 2 adapters not 8, no JobSpy, no router step 2 | todo |
| 24 | [Revive the contributor API](tranche_four/24-revive-contributor-api.md) | `backend/api/` deployed; Builder key onboarding | todo |
| 25 | [Search queries](tranche_four/25-search-queries.md) | query as a first-class object, caching, cohort signal | todo |

## Phase 5 — Multi-tenancy and events

| | Task | Lands | |
|---|---|---|---|
| 26 | [Profile creation API](tranche_five/26-profile-creation.md) | the gap `migrate_profiles.py` fills by hand | todo |
| 27 | [Event schema](tranche_five/27-event-schema.md) | `rank`, `request_id`, `dwell_ms`, `reason`, `visibility`, derived `skip` | todo |
| 28 | [Anonymous cohort aggregation](tranche_five/28-cohort-aggregation.md) | "4 Builders saved this" without attribution | todo |

## Phase 6 — Ground truth

| | Task | Lands | |
|---|---|---|---|
| 29 | [Two-axis labelling session](tranche_five/29-labelling-session.md) | Axis A extraction correctness, Axis B Builder preference — **labelling has started: 186 label rows over 31 of the 200 postings, all ten `overlap` rows answered, and ONE labeller. `evals label report` still refuses to report, correctly: with one labeller there is no inter-annotator ceiling to denominate a model score against** | in progress |

## Phase 7 — Ranking and display

| | Task | Lands | |
|---|---|---|---|
| 30 | [Within-track ordering](tranche_six/30-within-track-ordering.md) | buckets not scores; `gap_bridging_angle` promoted | todo |
| 31 | [Dismiss demotion](tranche_six/31-dismiss-demotion.md) | persistent, and specific to the reason given | todo |

## Phase 8 — Delivery

| | Task | Lands | |
|---|---|---|---|
| 32 | [Frontend](tranche_six/32-frontend.md) | against the endpoints that already exist | todo |
| 33 | [Deployment](tranche_six/33-deployment.md) | Cloudflare Tunnel; pipeline split from app | todo |

## Cross-cutting

| | Task | Lands | |
|---|---|---|---|
| 34 | [Documentation cleanup](34-documentation-cleanup.md) | archive, promote, regenerate — by document type; **plus the cleanup and bugfix backlog, re-verified against the code 2026-07-31 rather than inherited from a document.** Its own file was missing until then, which this table linked to regardless | **done** |
| 35 | [Extraction input sanity](tranche_six/35-extraction-input-sanity.md) | reject browser-DOM markup before it becomes facts; 0 false positives in 13,282 | done |
| — | `job_scores` version keys — no task file; [`HANDOFF.md`](HANDOFF.md) step 2 | `facts_version`/`persona_sha`/`prompt_version`/`criteria_version`, `select_shortlist` version-aware — **inert by default: 0 rows stale, 0 re-scored, and the bill is 1,018 calls not 1,293**. C4 of the master plan | done |
| — | Mock acceptance run — no task file; [`docs/mock-acceptance.md`](../../mock-acceptance.md) | 55 synthetic postings, quote-backed key, real pipeline in a scratch schema — **gate recall 48.3%: 15 of 29 good postings never enter. Extraction 86.4% pooled, `ai_involvement` 98.1%; `score_job` AP 91.9% / p@20 90.0%. A SPECIFICATION TEST — it does not reduce task 29** | done |
| — | `lib/text.strip_html()` — no task file; [`HANDOFF.md`](HANDOFF.md) step 3 | superset-by-construction regex, stdlib only; **6 greenhouse rows whose descriptions had been replaced by CSS restored from `raw_json`; markup rows above threshold 5 → 0** | done |
| — | The `pursuit` relevance gate — no task file; [`HANDOFF.md`](HANDOFF.md) step 0. Fixes a defect in task 10 | gate out of a migration that refuses to run and into `config/pursuit-relevance.json` (proven no-op); entry-level vocabulary split into title nouns and description phrases; `customer success` narrowed to manager-and-above — **mock gate recall 48.3% → 89.7%, on a corpus built to contain that failure mode. Live tier ≤ 2 869 → 880, which is +1.3% and moves GATE 2 not at all** | done |

## Phase 9 — Hygiene

**The system, then the sweep.** Task 34 paid down the debt it could find by hand; this tranche
makes the same work *checkable*, because the one documentation rule that has held in this repo
is the one with a script attached. [`docs/DOCS-POLICY.md`](../../DOCS-POLICY.md) is the system
these seven tasks execute — read it first; each task file cites a rule from it by number.

| | Task | Lands | |
|---|---|---|---|
| 36 | [Make the doc policy enforceable](tranche_seven/36-enforce-doc-policy.md) | `backend/tools/audit-docs.py` — six checks, `audit-doc-links.py`'s contract, wired into the suite. **Lands red on purpose**: check C5 has real failures in the tree today | todo |
| 37 | [Classify every document](tranche_seven/37-classify-every-doc.md) | `kind:` frontmatter tree-wide; the `docs/README.md` index that has never existed, which is what makes orphan detection possible at all. **C1 and C2 both clean, zero orphans.** Ten false statements found in seven per-script contracts — six still said upsert errors were discarded four days after `e353e3e` fixed all eight sites | done |
| 38 | [One figure, one owner](tranche_seven/38-one-figure-one-owner.md) | **No self-consistency number here is wrong — one word is overloaded.** Three metrics — `agree2`, `pairwise`, `unanimous` — all n=115, all in circulation, one of them ever named. [`AUDIT.md`](AUDIT.md) § *The three self-consistency metrics* now owns all three with the command; no test count is typed anywhere. Resolved from committed data 2026-08-01; nothing needed re-measuring | done |
| 39 | [Split the `D<n>` namespace](tranche_seven/39-split-the-d-namespace.md) | `D` = defects, `DEC` = decisions, one allocator each, declared in both headers. **The twenty decision entries re-prefixed to `DEC-46`–`DEC-65`** — numbers preserved, `<a id="dNN">` anchors left behind so inbound `#d46` citations still land. `ats-discover.py`'s dozen `D45` citations mean the **defect**, were verified one by one and deliberately not swept; `CLAUDE_UPDATES.md` and `docs/archive/` are `kind: record` and are exempt | done |
| 40 | [Roll the handoff forward](tranche_seven/40-roll-the-handoff-and-clear-the-archive.md) | `HANDOFF.md`'s entry point still sends every session to do task 34, justified by a premise task 34 **struck as wrong**. Plus `docs/WORKING-METHOD.md`, promoted; plus § *Still to archive*, cleared | todo |
| 41 | [Git and repo hygiene](tranche_seven/41-git-and-repo-hygiene.md) | 41a was a live production bug sitting uncommitted — the Workday gate died on `UndefinedColumn` because `platform_exclude` landed in `7d94bb1` and `_GATE_TEXT_COLUMNS` did not follow; committed alone as `7d839f5`. **41b also un-ignored `.claude/CLAUDE.md`**, which is what let tasks 38 and 40 commit their edits to it at all. **41c surfaced three branch decisions and took none — they are the owner's, recorded as deferred** | done |
| 42 | [Close the six UNBLOCKED defects](tranche_seven/42-close-the-unblocked-defects.md) | D02, D03, D05, D11, D13, D23 all closed, each with a test that fails without its fix. **Three of the six were never blocked at all** — D05, D11 and D13 needed no harness, and two say so in their own text. Every count the register quoted for them was wrong | done |
| 43 | [Split `docs/scoring.md`](tranche_seven/43-split-scoring-doc.md) | the contract half extracted, the measured half frozen as a dated record. **The decision is already taken — `DEC-70` names the rejected option**; this executes it | todo |
| 44 | [Archive the handoff history](tranche_seven/44-archive-the-handoff-history.md) | **`HANDOFF.md` is two documents** — a `rolling` entry point sitting on a frozen session narrative, and rule 1 has no name for that. Found by check C4, which hit nineteen restatements below line 380 and none above it. One `doc-figures.json` allowance exists only until this lands | todo |

---

## Why evals moved to the front

[`docs/ingestion_tests/README.md`](../../ingestion_tests/README.md) records that
`deepseek-v4-flash` does not agree with itself at temperature 0 — ~~76% on
`seniority_level`, 94% on `ai_involvement`, whole-record identical 0 of 17~~.

> **Superseded, marked not deleted (`DOCS-POLICY.md` rule 4).** That pair is the
> provisional **n=17** measurement of 2026-07-27, and task 06 re-ran it at n=115: the
> live figures are `seniority_level` **85.2% (`agree2`)** and `ai_involvement` **94.8%
> (`agree2`)**, whole-record identical 25 of 115. Both are owned by
> [`AUDIT.md`](AUDIT.md) § *The three self-consistency metrics*, which also names the
> other two metrics the same run reports. The pair is left visible because published
> text still cites it — check the **n** before reusing either number. The conclusion
> below does not move: the finding was that the model disagrees with itself at all,
> and at n=115 it still does.

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

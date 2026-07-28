# docs/ingestion_tests/

Work breakdown for `backend/evals/` — the harness that makes model, prompt and
cost decisions on the LLM stages *measurable* instead of argued.

It exists because of [`docs/ingest/`](../ingest/): an audit of every ingestion
path, whose findings are enumerated, classified and scheduled in
[`docs/ingest/DEFECTS.md`](../ingest/DEFECTS.md). Rather than hand-fix them
one at a time, the decision was to build the thing that would have caught
them.

| | Task | Lands | |
|---|---|---|---|
| 01 | [Per-call model handles](01-llm-per-call-handles.md) | `llm.call_detailed()` with model/URL/key overrides and a `Completion` carrying usage | done |
| 02 | [Evals substrate](02-evals-substrate.md) | `backend/evals/` — ModelSpec, frozen fixtures, replay cache, runner, reporting | done |
| 03 | [Metrics and golden set](03-metrics-and-golden-set.md) | `metrics.py`, `labels.py`, the labelling CLI, self-consistency baselines | next |
| 04 | [Score validation](04-score-validation.md) | a `score` task, `score.normalize()`, closing audit item 8 | todo |
| 05 | [Fetcher harness](05-fetcher-harness.md) | HTTP cassettes and a scratch database for the six non-LLM scripts | done — **resequenced, see below** |

01 and 02 landed 2026-07-27 in `fb733df`. Suite went 232 → 263 tests.

## 05 moved, and it is now the tightest constraint in the plan

**Here, 05 was last: `todo`, depends on 02, blocks nothing.** That ordering was
correct for the question this directory was written to answer — the LLM stages
are where model, prompt and cost decisions get argued, and the fetchers were
the part that already worked.

The refactor plan changed the question.
[`docs/tasks/refactor/tranche_two/09-fetcher-harness.md`](../tasks/refactor/tranche_two/09-fetcher-harness.md)
moves it **in front of Phase 3**, where it blocks all seven ingest tasks
(14–21). The reason is arithmetic, and it is the same argument this directory
already makes about frozen fixtures, one layer down:

- The harness was scoped for six ingest scripts. Phase 3 adds seven more — NYC
  Open Data, USAJobs/Adzuna, retargeted ATS, Workday CXS, JSON-LD, iCIMS,
  nonprofit boards.
- Writing thirteen ingest paths against live HTTP with no way to replay a
  response means every one of them is tested by running it against production
  and reading the logs. That is precisely how the defects in
  [`docs/ingest/DEFECTS.md`](../ingest/DEFECTS.md) came to exist — ten of them
  are dispositioned "fix with harness — task 09" for exactly this reason.
- Building it *after* Phase 3 means retrofitting cassettes onto seven scripts
  written without them. Building it *before* means seven scripts written
  against it.

The new sources are also the ones that most need it. Workday CXS alone has
four documented silent-failure modes; its fixtures now live in
`backend/evals/workday_fixtures.py` and were built by this task rather than by
task 18, so that task 18 is written against a reproduction instead of
producing one.

**What that means for anyone reading this directory in isolation:** 05 is no
longer optional polish at the end of a sequence. Its definition of done —
which this file's own task documents did not originally contain, and which is
now written into
[`05-fetcher-harness.md`](05-fetcher-harness.md#definition-of-done) — gates
seven scripts that do not exist yet. "Cassette committed" is a line in each of
their definitions of done.

## The finding that should shape task 03

**`deepseek-v4-flash` does not agree with itself at temperature 0.**

Measured 2026-07-28 on **all 115 eligible records of
`backend/evals/fixtures/corpus-v2.jsonl`** (n=120, 5 have no description and
`extract.py`'s own selector excludes them), extracted **three** times with
identical prompts and identical parameters, caching off:

```
cd backend && python3 -m evals selfcheck --model deepseek-v4-flash \
    --corpus evals/fixtures/corpus-v2.jsonl --repeat 3 \
    --out ../docs/ingestion_tests/selfcheck-n120-2026-07-28.json
```

345 live calls. Full table in
[`selfcheck-n120-2026-07-28.json`](selfcheck-n120-2026-07-28.json).

`agree2` is repeat 1 against repeat 2 — the same two-run protocol the
superseded figures below used, so the two columns are comparable. `unan` is
all three identical. Intervals are 95% Wilson.

| field | agree2 | 95% CI | unan (of 3) | scored by `match.py`? |
|---|---|---|---|---|
| `ai_involvement` | **109/115 = 94.8%** | **[89.1–97.6]** | 87.0% | yes — and it is the product |
| `seniority_level` | 98/115 = 85.2% | [77.6–90.6] | 77.4% | yes |
| `role_archetype` | 97/115 = 84.3% | [76.6–89.9] | 80.0% | yes |
| `remote_policy` | 94/115 = 81.7% | [73.7–87.7] | 71.3% | yes |
| `tech_stack` | 70.4% exact; **85.4% Jaccard** | [61.5–78.0] | 64.3% | yes |
| `employment_type` | 104/115 = 90.4% | [83.7–94.6] | 88.7% | no |
| `customer_facing` | 110/115 = 95.7% | [90.2–98.1] | 93.0% | yes |
| `comp_currency` | 112/115 = 97.4% | [92.6–99.1] | 97.4% | partly |
| `visa_sponsorship` | 111/115 = 96.5% | [91.4–98.6] | 96.5% | partly |
| `comp_min`, `comp_max`, `years_experience_*` | 99–100% | | 99–100% | yes |
| `ml_research_required`, `advanced_degree_required`, `gap_friendly_language` | 100% | [96.8–100] | 100% | yes |

Whole-record identical across all three runs: **25 of 115 (21.7%,
[15.1–30.2])**, over the fifteen compared fields — `summary` is prose and is
never compared.

All three passes returned usable JSON for 115/115 records. No tombstones, no
deferrals; this is disagreement about *content*, not a flaky endpoint.

### Superseded: the provisional n=17 figures

Retained because published text still cites them, and because the direction
of the error matters. Measured 2026-07-27 on 17 jobs from
`corpus-v1.jsonl`, extracted **twice**:

| field | n=17 self-agreement | n=115 `agree2` | verdict |
|---|---|---|---|
| `seniority_level` | 76% (13/17, [53–90]) | 85.2% [77.6–90.6] | low draw. The two intervals overlap heavily, so the n=17 *measurement* was not wrong — but its point estimate was 9pt low and falls just outside the n=115 interval |
| `remote_policy` | 76% | 81.7% [73.7–87.7] | consistent |
| `tech_stack` | 90% (Jaccard) | 85.4% (Jaccard) | consistent |
| `role_archetype` | 94% (16/17, [73–99]) | 84.3% [76.6–89.9] | **optimistic; 94% falls outside the n=115 interval** |
| `ai_involvement` | 94% | 94.8% [89.1–97.6] | held exactly |
| whole record identical | 0 of 17 ([0–18]) | 25 of 115 (21.7%) | 0/17 was consistent with anything up to 18% |

**So: 76% was an artifact of seventeen jobs — but so was 94% on
`role_archetype`, in the opposite direction.** At n=17 the worst field was
13-of-17, an interval of [53–90], consistent with almost anything. Two of the
six figures moved by roughly 10 points, one up and one down, which is exactly
what sampling noise at n=17 looks like and exactly why the README said
*"nothing should be re-tuned on it until it is re-run at n=120."*

The useful lesson is not that the old numbers were wrong. It is that at n=17
**no** field's interval was narrow enough to distinguish 76% from 95%, so
none of them could have supported a decision either way.

### The corpus hypothesis is refuted

This README hypothesised that the reconciliation was corpus, not model:
`tools/compare-extract.py` selects `ORDER BY first_seen DESC`, which is ~85%
greenhouse and ashby, so its 95% would describe the easy sources while the
stratified fixture's 76% described the hard ones. If true, every downstream
figure would have to be reported stratified or it would average two
populations that do not belong in the same mean.

**It is not true.** Splitting the n=115 run into clean (greenhouse+ashby,
n=34) and messy (everything else, n=81):

| field | clean | messy | gap |
|---|---|---|---|
| `ai_involvement` | 97% [85–99] | 94% [86–97] | **+3pt** |
| `seniority_level` | 82% [66–92] | 86% [77–92] | −4pt |
| `role_archetype` | 85% [70–94] | 84% [74–90] | +1pt |
| `remote_policy` | 79% [63–90] | 83% [73–89] | −3pt |
| `tech_stack` | 65% [48–79] | 73% [62–81] | −8pt |

The largest gap across **all sixteen** compared fields is 8.1 points
(`tech_stack`), and its sign is *negative* — the messy sources agree with
themselves slightly **better**. Every gap is well inside its own noise.

Agreement is a property of the **field**, not of the source. A plausible
reading: HN and weworkremotely postings are short and blunt ("remote",
"senior"), while long ATS boilerplate gives the model more room to be
ambiguous. Either way, later figures do **not** need to be reported
stratified to be valid — which is the question
[`03-metrics-and-golden-set.md`](03-metrics-and-golden-set.md) §"Report that
run per platform" was posed to settle.

That also means `criteria.json`'s 95% is not explained by an easy corpus. It
is simply not reproducible — see the gate decision below.

### What the disagreements *are*, which the rate does not tell you

A rate says how often the model contradicts itself. For `ai_involvement` the
consequence depends entirely on *which* values it moves between, because
`none` is the boundary of the cohort's opportunity space:

| pattern | records | crosses `none`? |
|---|---|---|
| `builds_llm_features` ↔ `uses_ai_tools` | 6 | no |
| `none` ↔ `uses_ai_tools` | 4 | **yes** |
| `builds_llm_features` ↔ `core_ml_research` | 1 | no |
| `builds_llm_features` ↔ `core_ml_research` ↔ `none` | 1 | **yes** |
| `builds_llm_features` ↔ `none` | 1 | **yes** |
| `builds_llm_features` ↔ `none` ↔ `uses_ai_tools` | 1 | **yes** |
| `core_ml_research` ↔ `none` | 1 | **yes** |

**8 of 115 records (7.0%, [3.6–13.1]) changed whether the job is in the AI
opportunity space at all**, between three runs of the same prompt on the same
text. The other 7 moved *within* it, where the cohort's targeting survives.

That 7% is the number the product turns on, and the 94.8% headline hides it.

### It still changes what a golden set can tell you

If a model disagrees with *itself* 15% of the time on `seniority_level`, then
measuring it at 80% agreement against human labels says almost nothing
without that floor beside it. Task 03 therefore measures three quantities,
not one: model self-consistency, human self-agreement, and model-vs-human.

The floor is now measured, so the labelling budget can be spent knowingly:
`remote_policy` (81.7%) and `tech_stack` (70.4% exact) are the fields a human
label is least able to settle, because the model cannot hold an opinion
steady long enough to be scored against one.

`llm.py:44-60` pins temperature to 0 and cites a measurement showing
`qwen2.5:14b` going from Spearman 0.666 to 1.000. That reasoning is sound and
the setting should stay — but it evidently does not make *every* provider
deterministic, and the module comment reads as though it does.

## Gate decision — task 06, 2026-07-28

[`docs/tasks/refactor/tranche_one/06-self-consistency-n120.md`](../tasks/refactor/tranche_one/06-self-consistency-n120.md)
gates tasks 07, 11, 12 and 13 on this measurement. Its four branches, against
what was measured:

| branch | condition | fired? |
|---|---|---|
| proceed | `ai_involvement` ≥ 95% on **all** platforms | **no** — 3 of 7 platforms below: greenhouse 94.1%, builtin 86.7%, hn_whoishiring 85.7% |
| proceed with mitigations | `ai_involvement` 90–95% | yes, on the **aggregate**: 94.8% [89.1–97.6] |
| **stop** | `ai_involvement` < 90% on the messy platforms | **YES — builtin 13/15 = 86.7%, hn_whoishiring 18/21 = 85.7%** |
| per-source quality budget | clean-vs-messy gap > 10 points | **no** — largest gap across all fields is 8.1pt, and `ai_involvement`'s is +3pt in the clean direction |

**Branch taken: STOP.** Tasks 10 and 13 need rethinking before they are
built. Per the task file, that is a design decision for the repo owner and
nothing was tuned in response to it.

Two qualifications, both of which belong beside the decision:

**The per-platform cells cannot resolve the threshold.** builtin's interval
is [62–96] at n=15 and hn_whoishiring's is [65–95] at n=21; both straddle
90%. The stop fires on the point estimates. Widening those cells is not
possible for every source — `lever` has **9 rows in all of production**, so
its cell can never exceed 9 whatever the corpus size.

**The stronger evidence is not the per-platform split.** It is the 7.0%
boundary-crossing rate, which is measured on the full n=115 and does not
depend on any per-platform cell: roughly **1 job in 14 changes AI-space
membership between identical nightly runs**. `uses_ai_tools` is how the
Pursuit cohort's entire opportunity space is identified, so this is a
product-level fact, not a data-quality footnote.

The obvious mitigations are the ones the middle branch already names — a
confidence field (task 11) and down-weighting unstable extractions (task 13)
— plus majority-of-3 for `ai_involvement` alone, which this run shows would
yield a determinate answer for **13 of the 15** unstable records. The other
2 returned three *different* values in three runs, so no majority exists and
a third call would not settle them. None of this was implemented here; a
measurement task's deliverable is the number.

## The decisions this work encodes

**Frozen fixtures, not live selection.** Every tool under `tools/` selects its
corpus with `ORDER BY first_seen DESC LIMIT n` against production, so the
corpus changes nightly and no two runs are comparable — a drop in agreement is
equally well explained by a worse model or a scrappier batch of postings.

**The pool is per-platform.** Sampling the globally-most-recent rows returned
zero HN and zero weworkremotely records: greenhouse and ashby are ~9,800 of
11,517 rows and ingest continuously, while `weworkremotely`, `hn_whoishiring`
and `lever` last wrote on 2026-07-24. The source with the messiest parsing was
the one a naive corpus structurally could not test.

**Cost and latency are never reported from cache.** A replayed response carries
the latency of a call made months ago against a possibly different endpoint
revision. `report.py` refuses to print either for a run containing a replayed
result — enforced where the number would be printed, not by asking each caller
to remember.

**The API key is not part of the cache key.** Rotating a credential must not
discard a corpus of paid-for answers, and a key must never reach disk.

**Tasks are adapters, never copies.** Prompt text and coercion rules stay in
`extract.py` and `score.py`. An eval that measures a copy of the prompt
measures nothing.

## What already exists, and must not be rebuilt

`tools/` is not superseded — it is where a one-off question still belongs. But
four of its scripts solved problems that are now shared, and task 03 onward
should read them rather than reinvent:

- **`tools/cost-test.py:115` `usage_fields()`** — normalises the provider usage
  block, handling the prompt-cache split and reasoning tokens. Its docstring
  explains why the old `chars/4` estimate was ~1.7x wrong. This is the right
  cost accounting; lift it, don't rewrite it.
- **`tools/compare-extract.py:52-60`** — the per-field comparison rules
  (`SCALAR_FIELDS`, `jaccard()`) and the argument for why extraction agreement
  is directly checkable where narrative quality is not.
- **`tools/calibrate-match.py`** — why *ranking* is the thing to measure for
  scoring, and the warning about baselines invented before measurement.
- **`tools/claude-bench.py:192-229`** — the `claude -p` envelope shape,
  including `total_cost_usd`, already lifted into `llm._call_claude`.

## Constraints that outlive these tasks

- **Row identity is frozen.** `content_hash` comes from a per-source tuple
  (`schema.py:131-137`) and `tests/test_row_identity.py` pins digests as
  literals across ~11,400 rows. Nothing here may touch a hash tuple,
  `lib/text.py:strip_html`, or `posted_at_timestamp`.
- **There is no staging database.** `tools/` and `evals/` are read-only;
  `scripts/` and `ingest/` drive real runs. Do not run an ingest script to
  check a fix.
- **`llm.py` is on the production path.** Changes to it stay additive and are
  verified by `python3 -m unittest discover -s tests -t .`

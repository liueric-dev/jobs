# docs/ingestion_tests/

Work breakdown for `backend/evals/` — the harness that makes model, prompt and
cost decisions on the LLM stages *measurable* instead of argued.

It exists because of [`docs/ingest/`](../ingest/): an audit of every ingestion
path that found 16 defects at `dd49a27`. Rather than hand-fix them one at a
time, the decision was to build the thing that would have caught them.

| | Task | Lands | |
|---|---|---|---|
| 01 | [Per-call model handles](01-llm-per-call-handles.md) | `llm.call_detailed()` with model/URL/key overrides and a `Completion` carrying usage | done |
| 02 | [Evals substrate](02-evals-substrate.md) | `backend/evals/` — ModelSpec, frozen fixtures, replay cache, runner, reporting | done |
| 03 | [Metrics and golden set](03-metrics-and-golden-set.md) | `metrics.py`, `labels.py`, the labelling CLI, self-consistency baselines | next |
| 04 | [Score validation](04-score-validation.md) | a `score` task, `score.normalize()`, closing audit item 8 | todo |
| 05 | [Fetcher harness](05-fetcher-harness.md) | HTTP cassettes and a scratch database for the six non-LLM scripts | todo |

01 and 02 landed 2026-07-27 in `fb733df`. Suite went 232 → 263 tests.

## The finding that should shape task 03

**`deepseek-v4-flash` does not agree with itself at temperature 0.** Measured
2026-07-27 on 17 jobs from `evals/fixtures/corpus-v1.jsonl`, extracted twice
with identical prompts and identical parameters:

| field | self-agreement | scored by `match.py`? |
|---|---|---|
| `seniority_level` | 76% | yes |
| `remote_policy` | 76% | yes |
| `tech_stack` | 90% (Jaccard) | yes |
| `role_archetype` | 94% | yes |
| `ai_involvement` | 94% | yes |
| every boolean, every integer | 100% | partly |

Whole-record identical: **0 of 17**.

Three things follow, and they are why this is written at the top of a README
rather than buried in a task file.

**It contradicts a figure the pipeline is currently calibrated against.**
`backend/config/criteria.json`'s `_hard_exclude_comment` justifies its penalty design
with "`tools/compare-extract.py` measures `seniority_level` agreeing with
itself 95% of the time and `role_archetype` 90%". The likely reconciliation is
corpus, not model: `compare-extract.py` selects `ORDER BY first_seen DESC`,
which is ~85% greenhouse and ashby — clean ATS postings. The fixture used here
is stratified across all seven platforms and includes HN free-text rows. If
that is the explanation, then the 95% describes the easy sources and the
calibration rests on it.

**It changes what a golden set can tell you.** If a model disagrees with
*itself* 24% of the time on `seniority_level`, then measuring it at 80%
agreement against your labels says almost nothing without that floor beside
it. Task 03 therefore measures three quantities, not one: model
self-consistency, human self-agreement, and model-vs-human.

**It is not yet a solid number.** n=17 is 13-out-of-17 on the worst field and
the interval is wide. *Nothing should be re-tuned on it until it is re-run at
n=120.* The harness makes that cheap; it has not been done.

`llm.py:44-60` pins temperature to 0 and cites a measurement showing
`qwen2.5:14b` going from Spearman 0.666 to 1.000. That reasoning is sound and
the setting should stay — but it evidently does not make *every* provider
deterministic, and the module comment reads as though it does.

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

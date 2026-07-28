# `evals/` — evaluation harness for the LLM stages

Answers three questions about `extract.py` and `score.py` without touching the
production corpus: **is a model's output correct**, **what does it cost**, and
**did a change make either worse**.

## Why this exists

Nine scripts under `tools/` already answer one question each — and each
rebuilds the same plumbing to do it. Three parse `MODEL@URL@KEY` differently,
four `import llm` and then reimplement the HTTP call anyway, and every one
selects its corpus with `ORDER BY first_seen DESC LIMIT n` against production.

That last one is the expensive part. The corpus changes every night, so two
runs a week apart are not comparable: a drop in agreement is equally well
explained by a worse model or by a scrappier batch of postings. Freezing the
corpus is what turns "the numbers moved" into evidence about the thing that
changed.

`tools/` is still the right place for a one-off question. This is the shared
floor underneath it.

## Quick start

```bash
cd backend

# 1. Snapshot a fixture. Reads production, writes a file. Read-only.
python3 -m evals corpus snapshot --n 120 --out evals/fixtures/corpus-v1.jsonl

# 2. Run a stage against it. First run buys the responses; every later run
#    replays them for free.
python3 -m evals run --task extract --corpus evals/fixtures/corpus-v1.jsonl \
    --model "deepseek-v4-flash@$DEEPSEEK_BASE_URL@env:DEEPSEEK_API_KEY"

# 3. Measure cost and latency honestly -- never from cache.
python3 -m evals run --task extract --corpus evals/fixtures/corpus-v1.jsonl \
    --model "$SPEC" --no-cache

# 4. Ask the same model the same thing three times: how stable is it?
python3 -m evals selfcheck --model "$SPEC" --repeat 3 \
    --corpus evals/fixtures/corpus-v2.jsonl
```

`.env` is loaded the same way `run-daily.py` loads it, with the same
precedence: an exported value wins, the file is the fallback.

## The model spec

| Form | Meaning |
|---|---|
| `MODEL@BASE_URL@API_KEY` | any OpenAI-compatible endpoint |
| `MODEL@BASE_URL@env:VARNAME` | key read from the environment at use time |
| `MODEL` | base URL and key from the environment, as the pipeline reads them |
| `claude:MODEL` | the `claude -p` CLI, billed to a Pro/Max subscription |

Prefer `env:VARNAME`. A spec string reaches run metadata and error messages,
and a literal key there is a key on disk.

Parsing splits on the **first two** `@` only. `tools/compare-models.py:213`
splits on every `@` and treats the last field as the key, which truncates any
key containing one; base URLs do not contain a bare `@`, keys routinely do.

## Self-consistency, and the cache bug that would fake it

`selfcheck` runs the corpus N times and reports how often the model agrees
with **itself** — the floor under every other number here. A model that
disagrees with itself 15% of the time cannot be scored at 80% against human
labels and called 80% accurate.

The cache is content-addressed, and a self-consistency run asks the same
model the same prompt on purpose. Without disambiguation repeat 2 reads back
repeat 1's stored answer and the run reports **100% agreement** — on exactly
the quantity it was built to measure, with no error and nothing in the output
to suggest anything is wrong. Two defences: `cache.key_for()` takes a
`repeat_index` that enters the digest, and `runner.run_repeated()` turns
caching off by default whenever `repeat > 1`. `tests/test_evals.py`
demonstrates the failure rather than only asserting the fix — with the index
removed the same run reports 100%, and the test pins that.

Read the numbers in `docs/ingestion_tests/README.md`. Three columns, because
they answer different questions: `agree2` (repeat 1 vs 2) is comparable to a
two-run figure and carries a valid Wilson interval; `unan` is all N
identical; `pair` uses every pair and gets no interval, because pairs from
one record are not independent trials.

## What is cached, and what is never cached

The cache is keyed on `sha256(backend, model, base_url, temperature,
json_object, prompt[, repeat_index])` and stores the **raw response text,
pre-`parse_json`** —
fences, chatter, truncation and all. That is what makes it possible to iterate
on `llm.parse_json()` and on coercion code against real malformed answers.

The API key is deliberately **not** in the key. Rotating a credential must not
throw away a corpus of paid-for answers, and a key must never reach disk.

Cost and latency are **never reported from cache**. A replayed response
carries the latency of a call made months ago, possibly against a different
endpoint revision; printing that as measured is how a harness produces a
confident wrong number. `report.py` refuses to print either for a run
containing a replayed result, and names the flag that would produce them.
`runner.py` only records the fact — the judgement lives at the point of
printing, so no caller has to remember the rule.

Use `--no-cache` to measure, `--refresh` to re-buy and re-cache.

## What the corpus contains

Stratified across all seven platforms, and deliberately seeded with the rows
that break things — `PATHOLOGY` in `corpus.py`:

- **`long_title`** — HN rows holding a comment body where a title belongs. The
  longest in production runs to 415 characters; `docs/ingest/hn-hiring.md`
  item 15 is about exactly these.
- **`no_description`** — rows `extract.py`'s selector excludes, so nothing has
  ever run a prompt against one.
- **`tombstoned`** — rows whose `extraction_model` is `FAILED:%`. The sharpest
  available test of a candidate replacement is what it does with the postings
  the incumbent could not handle.

The pool query takes the most recent *N per platform* rather than the most
recent N overall. This matters more than it sounds: `greenhouse` and `ashby`
are ~9,800 of 11,517 rows and ingest continuously, while `weworkremotely`,
`hn_whoishiring` and `lever` last wrote on 2026-07-24. A globally-recent pool
of 720 rows contained **none** of the latter three — so the sources with the
messiest parsing were the ones a naive corpus could never test.

## The golden set: three quantities, never one

`selfcheck` answers "is the model stable". It cannot answer "is the model
right", because it never consults a human. `labels.py` is the other half, and
the rule it enforces is that **model-vs-human alone is uninterpretable**:

| quantity | what it is | where it comes from |
|---|---|---|
| **floor** | how often the model agrees with *itself* | `metrics.selfcheck` — task 06, n=120 |
| **ceiling** | how often two *people* agree | `labels.inter_annotator` |
| **the question** | model vs the majority human answer | `labels.model_vs_human` |

A model scored at 85% against labels has been shown nothing until you know it
self-agrees at 91% (it is unstable, not wrong) or that two humans agree at 85%
(it has saturated what the label can resolve).

So the API makes the bad report **unrepresentable rather than discouraged**.
`labels.Interpretable` refuses to be constructed without all three and names
which one is missing and the command that produces it; `report.render_labels`
takes nothing else. There is no `--force`. This follows the precedent task 16
set when its coverage tool refused to print one denominator alone.

```bash
python3 -m evals label init-schema            # DDL, admin credential, once
python3 -m evals label sample --n 60 --overlap 20
python3 -m evals label export --out evals/fixtures/golden-v1.jsonl
python3 -m evals label report --run results.jsonl --selfcheck sc.json
```

**Nothing under `label` writes a label.** People do that in a browser at
`/v1/label` (`backend/webapp/label.py`), signed in with the Google SSO that
already exists there. A CLI is right for the author and unusable for the ~10
Builder volunteers the labels actually come from.

### Two axes, keyed independently

| axis | question | scope | survives the cohort? |
|---|---|---|---|
| **A** | is the extraction correct? | objective | **yes** — every future user, every future vertical |
| **B** | would you apply to this? | subjective | no |

Axis A validates `job_facts`, which is extracted once and shared by every
profile forever, and which has **never** been measured against a human —
`tools/compare-extract.py` measures the model against itself, which catches
instability and is structurally blind to systematic error.

The independence is in the schema, not in a convention: two *partial* unique
indexes rather than one composite key over a nullable `profile`. Postgres
treats NULLs as distinct, so the composite key would have enforced nothing at
all on axis A. `tests/test_labels.py` pins this against a real server, because
a fake connection accepts the insert either way.

Axis A ordering is `ai_involvement`, `seniority_level` first, and that is a
finding rather than a preference: task 06 put `ai_involvement` at 77.8%
pairwise self-agreement on `hn_whoishiring`, and it is the entire mechanism by
which the cohort's opportunity space is identified.

### The sample contains rows the pipeline threw away

Everything measured before this was something the pipeline had already chosen
to surface, so only **precision** was estimable and recall was not.

| stratum | has `job_facts`? | has `job_matches`? | makes estimable |
|---|---|---|---|
| `surfaced` | yes | yes (≥ `MATCH_FLOOR`) | precision |
| `below_floor` | yes | **no** — `match.py:291` stores only at or above the floor | recall |
| `gate_rejected` | **no** — relevance tier > `max_tier_to_score` | no | recall |

"No `job_matches` row" has two causes — under the floor, or `match.py` has not
caught up — and SQL cannot tell them apart. `score_job()` is pure, so
`confirm_scores()` recomputes the exact number and evicts the second kind
rather than documenting the ambiguity. On the first real run against
production that was **6 rows of 40**; a recall figure over that stratum would
have been partly a measurement of the scheduler.

### The ceiling is the measurement attrition takes first

`--overlap N` marks the first N rows of the set as shown to *every* labeller,
and `next_item()` serves those before anything else. A volunteer who labels ten
postings and stops has still contributed to the inter-annotator number; if the
shared rows came last they would have contributed nothing to it. Intra-
annotator (one person, two rounds) is computed too — a labeller who is
self-consistent and disagrees with everyone has a different reading of the
*question*, and only having both numbers tells that apart from noise.

An abstention (`I can't tell from this posting`) is stored as NULL, excluded
from every rate, and counted beside it. Two people who both gave up have not
agreed about anything, and a labeller with no way to abstain guesses.

## Comparison happens after `normalize()`

A model's raw JSON is compared only after `extract.normalize()` has run, which
is what `job_facts` would actually store. Comparing raw output would score
formatting: `"Mid-Level"` and `"mid"` are the same answer and
`extract._enum()` already knows it.

Prose fields (`summary`) are not compared at all. Two correct summaries differ.

## Layout

| File | Responsibility |
|---|---|
| `models.py` | `ModelSpec` — one parser, credentials kept out of identity |
| `corpus.py` | fixtures, stratified sampling, read-only production snapshot |
| `cache.py` | content-addressed response store |
| `runner.py` | executes a task over a corpus; records provenance |
| `metrics.py` | per-field comparison rules, Wilson intervals, platform split |
| `report.py` | human table and JSONL; enforces the cost/latency rule |
| `labels.py` | L0 human labels: schema, stratified sampler, agreement, the three-quantity gate |
| `tasks/` | thin adapters over the real `build_prompt`/`normalize` |

Tasks are adapters on purpose. The prompt text and coercion rules stay in
`extract.py` and `score.py`; a copy here would drift, and an eval that
measures a copy of the prompt measures nothing.

## The frozen corpora

| Fixture | Snapshotted | n | Cited by |
|---|---|---|---|
| `corpus-v1.jsonl` | 2026-07-27 | 120 | task 04's quota and wall-clock figures |
| `corpus-v2.jsonl` | 2026-07-28 | 120 | task 06's n=115 self-consistency figures |

Both are pinned by the sha256 of their sorted `job_id` list, as literals in
`tests/test_evals.py`. A fixture regenerated in place would silently change
what every published figure was measured on, and the figures would still be
sitting in the docs, unchanged and now wrong. Never mutate one — snapshot a
new version.

They overlap by only 17 records: greenhouse and ashby ingest continuously, so
a day's gap replaces most of the clean end, while `lever` (**9 rows in all of
production**), `hn_whoishiring` and `weworkremotely` move slowly. That makes
v2 close to an independent sample rather than a re-run of v1.

## Status

Phase 1 (substrate) is built and tested. Phase 2 is landed as **tooling**:
`metrics.py`, `selfcheck`, `labels.py`, the `label` subcommands and the
`/v1/label` surface all exist, and the self-consistency floor is measured at
n=120.

- **Phase 2 (the labels themselves)** — **not done, and deliberately not
  startable from here.** The tables are empty. Filling them needs ~10 Builder
  volunteers, which is task 29. Generating labels with a model would reproduce
  `claude-bench.py:417`'s defect inside the tool built to detect it, so there
  is no code path from a model's output into `eval_labels` and
  `tests/test_labels.py` asserts the module contains none.
- **Phase 3** — `score.py` output validation (`score.py:359-361` stores
  `fit_score` and `primary_track` with no coercion) plus a `score` task.
- **Phase 4** — the six non-LLM fetchers: recorded HTTP fixtures and a scratch
  database.

## Tests

```bash
cd backend && python3 -m unittest discover -s tests -t .
```

`tests/test_evals.py` is self-contained — no network, no database. It pins the
properties that are about honesty rather than arithmetic: that a replayed
latency is never reported as measured, that a credential reaches neither the
cache key nor a results file, and that a record the pipeline would never send
is not counted against the model.

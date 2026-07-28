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

Phase 1 (substrate) is built and tested. Phase 2 is partly landed:
`metrics.py` and the `selfcheck` subcommand exist and the self-consistency
floor is measured. Still to come:

- **Phase 2 (rest)** — the golden set. `labels.py` and the labelling CLI do
  not exist yet. `tasks/extract.py` already declares `FIELD_KINDS` and
  `PRIORITY_FIELDS`, and `metrics.py` reads them.
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

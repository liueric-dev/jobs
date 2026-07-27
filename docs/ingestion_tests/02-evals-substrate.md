# 02 — The `evals/` substrate

**Status:** done, 2026-07-27, `fb733df`.
**Depends on:** 01. **Blocks:** 03, 04, 05.

The shared floor the nine `tools/` scripts should have had: one model handle,
a frozen corpus, a replay cache, and reporting that refuses to lie about cost.

## Files

```
backend/evals/
├── __init__.py       why the package exists; why it is `evals`, not `eval`
├── __main__.py       CLI: corpus snapshot|info, run, cache stats
├── models.py         ModelSpec — one parser, credentials out of identity
├── corpus.py         JSONL fixtures, stratified sampling, read-only snapshot
├── cache.py          content-addressed response store
├── runner.py         executes a task over a corpus, records provenance
├── report.py         human table + JSONL; enforces the cost/latency rule
├── tasks/extract.py  adapter over the real build_prompt/normalize
├── fixtures/
│   └── corpus-v1.jsonl   120 records, 7 platforms, 628K
└── README.md
```

`evals`, not `eval`: the latter is a builtin, and a package by that name means
any module doing `import eval` silently loses it.

## The seam that made this cheap

Both stages already separate pure logic from I/O, and both selectors return a
plain list of dicts:

- `extract.py`: `select_unextracted_jobs()` → `build_prompt(job)` →
  `llm.call` → `parse_json` → `normalize()` → `update_job_facts()`
- `score.py`: `select_shortlist()` → `build_prompt(persona, job)` → …

So **a fixture is that list, frozen to JSONL**, and `build_prompt`/`normalize`
run against it unchanged. Nothing in the pipeline needed restructuring.

One record carries both stages' inputs — the posting *and* its `job_facts`
row — because `score.build_prompt` embeds a facts block (`score.py:249`).
That keeps the score task runnable without first running extract.

## Three things found while building

**The `MODEL@URL@KEY` parsers genuinely disagree.** `compare-models.py:213`
splits on every `@` and rejoins the middle, treating the *last* field as the
key; `cost-test.py:156` and `compare-extract.py:124` use `split('@', 2)`,
treating the *rest* as the key. On `m@https://x/v1@sk-a@b` the first yields
`base_url='https://x/v1@sk-a'`, the second `key='sk-a@b'`. Keys containing `@`
are ordinary; base URLs with a bare `@` are not. `ModelSpec` unifies on
`split('@', 2)` and a test pins it.

**The pool query had to become per-platform.** This was the important one. The
first snapshot returned zero HN and zero weworkremotely rows. `greenhouse` and
`ashby` are ~9,800 of 11,517 rows and ingest continuously; `weworkremotely`,
`hn_whoishiring` and `lever` last wrote 2026-07-24. A 720-row recency-ordered
pool never reaches them — so the HN parser, the one that guesses titles out of
free text, was the thing the corpus structurally could not test.
`ROW_NUMBER() OVER (PARTITION BY j.platform ORDER BY j.first_seen DESC)` fixes
it. The fixture now carries HN rows with 351- and 409-character "titles"
holding comment bodies: exactly the shape `docs/ingest/hn-hiring.md` item 15
is about.

**Lazy credential resolution billed before failing.** `env:VARNAME` was
resolved inside `call_kwargs()` per record, so an unset variable raised out of
a worker thread *after* some records had been paid for, and reached the user
as a traceback. Now resolved once in `runner.run()` before the pool starts,
with a test asserting zero calls were made.

## The cache contract

Key: `sha256(backend, model, base_url, temperature, json_object, prompt)`.

- **Backend and base URL are in the key** — `llm.py` reaches the same model
  label through `_call_http` and `_call_claude`, and those do not return the
  same thing.
- **The API key is not** — rotating a credential must not discard a corpus of
  paid-for answers, and a key must never reach disk.
- **Raw text is stored, pre-`parse_json`** — fences, chatter and truncation
  are exactly the inputs `parse_json()` and `normalize()` have to survive, and
  they cannot be reconstructed from a successful parse.
- **Transient failures are never cached.** `llm.TransientError` means the
  prompt was not evaluated; storing it would poison the cache with a
  non-answer and counting it would blame the model for a busy endpoint. It is
  recorded `deferred`, matching `extract.py:365`.

`report.py` refuses to print cost or latency for a run containing a replayed
result, and names the flag that would measure it. `runner.py` only records the
fact — the judgement lives at the point of printing, so no caller has to
remember the rule.

## Verified live

Against `deepseek-v4-flash`, 20 fixture jobs, 2026-07-27:

- 17/17 usable (100% JSON validity); 3 skipped as ineligible (empty
  `description_text`, which `extract.py`'s own selector excludes — the model
  was never asked, so they are not counted against it)
- median latency 11.0s
- prompt cache confirmed working: 20,352 cached input tokens against 1,140
  misses — the fixed-prefix behaviour `cost-test.py` documents
- replay reproduced the live pass **byte-identically** in 0.117s against ~90s
  of calls, with stable `prompt_sha`
- an unreachable endpoint yielded `deferred`, not `tombstone`, and wrote
  nothing to the cache
- both `FAILED:`-tombstoned rows in the slice extracted cleanly

## Tests

`tests/test_evals.py`, 26 tests, no network and no database. It pins the
properties that are about honesty rather than arithmetic: a replayed latency
is never reported as measured, a credential reaches neither the cache key nor
a results file, a record the pipeline would never send is not counted against
the model, and rotating a key does not invalidate the cache.

# 05 — A harness for the six non-LLM fetchers

**Status:** todo. **Depends on:** 02. **Blocks:** nothing.

Everything in tasks 01-04 is about the two LLM stages. Six of the nine
pipeline scripts have no LLM in them at all, and that is where every P0 in the
audit lives.

## Why this is a different harness

`ingest/ats.py`, `hn-hiring.py`, `weworkremotely.py`, `builtin-nyc.py`,
`google-serpapi.py` and `google-apify.py` are fetch → normalize → upsert.
Model choice, token cost and human-rated labels do not apply. What they need
is the two things `evals/` has not built:

- **Recorded HTTP fixtures (cassettes).** A saved upstream response per source,
  so a normalizer can be exercised against the real bytes an API returned.
- **A scratch database.** `lib/dbconn.connect()` already accepts `schema=` and
  `url=` overrides (`lib/dbconn.py:107`) and `schema.ensure_schema()` creates
  everything, so a throwaway database is cheap. `ensure_schema`'s refusal to
  run against a database containing `public.events` — FOOTGUN 2 in
  `lib/dbconn.py:19` — is a feature here; keep it.

**There is still no staging instance.** Nothing in this task may run
`ingest/` or `scripts/` against production to "check" anything.

## The defects this would catch

From the audit. Each is written up in `docs/ingest/`, with full file:line
context, and each was verified against the code at `dd49a27`.

| # | Defect | Site |
|---|---|---|
| 1 | `UnboundLocalError` when an Apify actor run succeeds immediately — `run` is bound only inside the `while` body, and an already-`SUCCEEDED` start skips the loop | `google-apify.py:179-190` |
| 2 | `lib.upsert` errors discarded at every call site — `UpsertResult.__iter__` makes the three-tuple unpack hide `.errors`; no production caller reads it | 8 sites incl. `ats.py:337`, `api/query_claims.py:445` |
| 3 | `match.py` has no per-record isolation — `score_job` unguarded at `:290`, `executemany` at `:304` all-or-nothing, no per-profile try/except at `:358`. The only write path without `lib/upsert.py`'s SAVEPOINT | `match.py:290,304` |
| 4 | HN ledger commits *before* the upsert — a crash between them marks comments processed with no row written, and the ledger gates re-fetching | `hn-hiring.py:422` |
| 5 | Null HN items re-fetched forever — `if not comment: continue` returns before the ledger insert | `hn-hiring.py:409-412` |
| 6 | Uncaught `KeyError` on malformed config, before the `try` | `ats.py:320-323`, `google-serpapi.py:213-214` |
| 7 | Normalization outside the per-unit `try` in four scripts, so a normalizer exception kills the whole run rather than one unit. `weworkremotely.py:196-198` gets it right | `ats.py:334` +3 |

Items 1, 4, 5 and 7 are all naturally expressible as cassette tests. Items 2
and 3 need the scratch database.

**Item 3 is not confined to `match.py`.** A trace of the scoring prompt done
for task 04 found the same class in the LLM half: `score_one_job` builds its
prompt at `score.py:421` under a `try` that has only a `finally`, and
`run_for_profile` materialises `pool.map` through `list()`
(`score.py:478-481`), so a `KeyError` from a malformed persona ends the whole
profile's batch. Write-up in
[`04-score-validation.md`](04-score-validation.md).

So "no per-record isolation" is a property of the pipeline, not a quirk of one
script — three of the nine scripts are now known to have it. Whoever builds the
scratch database should treat it as a pipeline-wide invariant to test for,
rather than writing a `match.py`-shaped test that happens to catch one
instance.

## Suggested shape

```
backend/evals/
├── cassettes.py            record/replay for lib/http.py
├── scratchdb.py            create/drop a throwaway schema, ensure_schema
├── fixtures/cassettes/
│   ├── ats-greenhouse.json
│   ├── hn-item-null.json       the deleted-item case, item 5
│   └── apify-immediate-success.json   the item 1 case
└── tasks/…
```

Record against the real upstream once, commit the bytes, replay forever. The
awkward responses are the point: an Apify start response already
`SUCCEEDED`, an HN item id answering `null`, a Greenhouse payload with a
missing `content` field.

## Open question worth settling first

`lib/upsert.py` and the Google claim SQL have **no concurrency coverage of any
kind** today, and a scratch database is the first thing that would make such a
test possible. Whether to write those tests is a real decision — they are
slow, they are fiddly, and the current behaviour is not known to be wrong. But
right now nobody can assert it is right either, and the honest position is to
say so rather than to imply the paths are tested.

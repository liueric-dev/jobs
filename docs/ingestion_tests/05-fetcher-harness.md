# 05 — A harness for the six non-LLM fetchers

**Status:** done 2026-07-28. **Depends on:** 02.
**Blocks:** all of Phase 3 — this task was resequenced in front of it. The
amendment is [`docs/tasks/refactor/tranche_two/09-fetcher-harness.md`](../tasks/refactor/tranche_two/09-fetcher-harness.md);
the reasoning is arithmetic and is restated in [the README](README.md).

> **This file had no Definition of done.** `09-fetcher-harness.md:69` begins
> "Everything in `05-fetcher-harness.md`'s definition of done, plus: …" and
> there was nothing to inherit. One is written below, derived from "Suggested
> shape" and "The defects this would catch" — the two sections that already
> said what finishing looked like without ever calling it that.

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

### What actually landed, and the three places it differs

**The seam is `urllib.request.urlopen`, not `lib/http.py`.** Hooking
`lib/http.py` would have replayed two of the six sources and silently made
live calls for the other four, which build their own `Request` to send a
browser-ish User-Agent that `lib/http.py` takes no parameter for —
`weworkremotely.py:124`, `google-serpapi.py:280`, `builtin-nyc.py:182` and
`:241`. `lib/http.py:66` resolves `urlopen` at call time, so one seam covers
all six and `lib/` — vendored byte-identical to another repo — needs no test
hook.

**Three awkward responses, three fixtures, none of them hand-written.** The
null HN item is `item/99999999999.json`, which really does answer `null`. The
missing-`content` Greenhouse payload is the same board fetched without
`?content=true` — the real bytes `ats.py:152` would get if that parameter were
ever lost, which would turn every description on every greenhouse board NULL
while the run reported success. The already-`SUCCEEDED` Apify start is derived
in code from the recorded run object rather than committed as a fourth file,
because Apify's start and run endpoints return the same resource and a stored
copy would stop matching the recording it came from.

**Two modules more than the sketch:** `evals/ingest_modules.py` (importlib by
path, since five of six scripts have hyphens in their filenames) and
`evals/workday_fixtures.py` (task 18's four failure modes, which task 09
absorbed when it moved in front of Phase 3).

## Open question, settled 2026-07-28

> The question, as written: `lib/upsert.py` and the Google claim SQL have no
> concurrency coverage of any kind, a scratch database is the first thing that
> makes such a test possible, and nobody can currently assert the paths are
> right.

**Answer: the claim SQL yes, `lib/upsert.py` no.** They are not the same
decision, and treating them as one is what made this look like a coin flip.

**`state.try_claim` is *defined* by the concurrent case.** Its docstring
(`lib/state.py:96-99`) says it "guards metered API budgets against two
overlapping runs spending the same quota twice", and both Google scripts build
their scheduling on it (`google-serpapi.py:200-212`,
`google-apify.py:138-142`). Single-process it is trivially true and proves
nothing. If it is wrong the symptom is a double-spend of SerpApi/Apify quota
that reports success — silence, and money, which is this pipeline's
characteristic failure mode. Two tests, in `tests/test_scratchdb.py`.

**`lib/upsert.py` has no cross-process contract to test.** `run-daily.py` is
the single cron entry point and runs the ingest scripts *sequentially* as
subprocesses — stated at `ingest/ats.py:97-102` and repeated in every other
script's CONCURRENCY note — so two upserts racing on one row is not a state
this system reaches. A test would pin behaviour nothing depends on, would be
slow and order-dependent, and would be maintained by people who reasonably
assume it is load-bearing.

**What actually motivated the question is testable without concurrency.** The
claim `lib/upsert.py:191-197` makes is about Postgres *transactions*: a plain
try/except is not enough because a failed statement aborts the whole
transaction, so one bad row loses the batch unless each record gets a
SAVEPOINT. `tests/test_upsert_checked.py`'s fake connection cannot falsify
that — it keeps going after a raise whether or not the SAVEPOINT is there. A
real server can. Measured with the SAVEPOINT removed, on a five-record batch
whose third record violates `company_name NOT NULL`:

| | new | errors | rows actually stored |
|---|---|---|---|
| with the per-record SAVEPOINT | 4 | 1 | 4 |
| without it | 2 | 3 | **0** |

That is the first evidence in this repo that the mechanism works, and it needed
a scratch database, not a concurrency harness.

## Definition of done

Derived from "Suggested shape" and "The defects this would catch" above; see
the note at the top of this file for why it is being written now.

- **`evals/cassettes.py` records and replays** every HTTP call the six scripts
  make, exercising their real fetch and normalize functions. Adapters, never
  copies: no parsing logic is reimplemented in the harness or in a test.
- **A request with no recorded response fails.** Falling through to the network
  on a miss is how a replayed test quietly becomes a live test again.
- **No credential reaches disk and no credential is part of the cache key.**
  Rotating `SERPAPI_API_KEY` or `APIFY_API_TOKEN` must not discard a recorded
  corpus.
- **Cost and latency are never reported from replay** — enforced where the
  number would be read, not by asking each caller to remember.
- **`evals/scratchdb.py` creates and drops a throwaway schema through the real
  `schema.ensure_schema()`**, not a hand-maintained DDL copy, and keeps
  `ensure_schema`'s refusal to run against a database holding `public.events`
  (`lib/dbconn.py:19` FOOTGUN 2) — that refusal is a feature here.
- **Nothing in this task runs `ingest/` or `scripts/` against production.**
  There is still no staging instance.
- **One cassette per source, recorded from the real upstream and committed** —
  the six of `ats.py` (×3 platforms), `hn-hiring.py`, `weworkremotely.py`,
  `builtin-nyc.py`, `google-serpapi.py`, `google-apify.py`.
- **The three awkward responses named above each exist as a fixture**: an
  already-`SUCCEEDED` Apify start, an HN item answering `null`, a Greenhouse
  payload with no `content` field.
- **Audit items 1, 4, 5 and 7 are expressible as cassette tests, and item 1 is
  reproduced.** Item 1 (`google-apify.py:179-190`) has a test that asserts the
  `UnboundLocalError`, so whoever fixes D17 flips one assertion. Items 4, 5 and
  7 have their *inputs* pinned; the fixes are not in this task's scope — task
  02 produces a register, not fixes.
- **Audit items 2 and 3 have their mechanism tested against a real server.**
  Per-record isolation is a pipeline-wide invariant, not a `match.py` quirk.
- **The open question above is answered in writing, with its reasoning.**
- **The suite does not go down.**

# 09 — Fetcher harness

**Status:** DONE, `68f026f`. **Depends on:** 02. **Blocks:** all of Phase 3 — see below.

**This task is [`docs/ingestion_tests/05-fetcher-harness.md`](../../../ingestion_tests/05-fetcher-harness.md).**
HTTP cassettes and a scratch database for the non-LLM scripts.

## It moved, and that is the whole amendment

In `docs/ingestion_tests/README.md` this is task 05 — last in the sequence, marked
`todo`, blocking nothing. Under this plan it moves **in front of Phase 3**, and the
reason is arithmetic.

The harness was scoped for six ingest scripts. Phase 3 adds seven more: NYC Open
Data, USAJobs, Adzuna, retargeted ATS, Workday CXS, JSON-LD, iCIMS, nonprofit boards.
Writing thirteen ingest paths against live HTTP, with no way to replay a response,
means every one of them is tested by running it against production and reading the
logs — which is precisely how the sixteen defects in task 02 came to exist.

Building it after Phase 3 means retrofitting cassettes onto seven scripts written
without them. Building it before means seven scripts written against it.

The new sources are also the ones that most need it:

| source | why a cassette matters |
|---|---|
| **Workday CXS** | four documented silent-failure modes (`SOURCING-STRATEGY.md` §4) — `limit>20` returning empty, throttled pages reading as end-of-list, varying `wd{N}` prefix, per-job detail fetch. Each needs a fixture that reproduces it |
| **NYC Open Data** | SODA pagination and `post_until` parsing |
| **JSON-LD** | wildly variable completeness across employers; the fixture *is* the specification |
| **Google Jobs providers** | eight providers, one normalised shape (task 23). Cassettes are how you prove the adapters agree |

## What carries over unchanged

Everything in `05-fetcher-harness.md`, including its "defects this would catch"
section, which should be cross-referenced against the register from task 02 — some
entries will already have ids.

The design rules from the evals harness apply here too and should be restated rather
than rediscovered:

- **Cost and latency are never reported from replay.** `report.py` already enforces
  this where the number would be printed, rather than asking each caller to remember.
- **The API key is not part of the cache key.** Rotating a credential must not
  discard a corpus of recorded responses, and a key must never reach disk. This
  matters more here than in the LLM harness, because Phase 3 and 4 involve eight
  scraping providers with rotating free-tier keys.
- **Adapters, never copies.** Parsing logic stays in the ingest script; the harness
  replays bytes into it. A cassette test that exercises a copy of the parser measures
  nothing.

## What to add

### A scratch database that survives schema drift

The scratch DB has to track `FACTS_VERSION` and the migrations in Phase 2 and 5. Make
schema creation share the real path (`init-schema`, per `33469fe`) rather than a
hand-maintained DDL copy, or the harness will silently test a schema that no longer
exists.

### Record-mode discipline

Cassettes recorded against a live source embed that source's state on that day.
Record with a fixed date, store the recording date in the cassette, and have the test
report it — otherwise a fixture recorded in July silently becomes the specification
in December.

## Definition of done

Everything in `05-fetcher-harness.md`'s definition of done, plus:

- Cassettes exist for the existing six sources **before** Phase 3 begins.
- The four Workday silent-failure modes each have a fixture that reproduces them,
  ready for task 18 to test against.
- Every Phase 3 task's definition of done includes "cassette committed."
- `docs/ingestion_tests/README.md` records that 05 moved and why.

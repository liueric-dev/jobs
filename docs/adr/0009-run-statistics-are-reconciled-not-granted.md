---
kind: decision
written: 2026-08-09
generator: none
---

# 0009 — a contributor's run is reconciled by the pipeline, not written by the service

**Status:** accepted, 2026-08-09. Answers `T-38`.

## Context

`search_queries` carries five run statistics — `last_run_at`, `run_count`, `provider_last_used`,
`result_count_last_run`, `last_result_at` — and `searchqueries.record_run()` is their only writer.
`T-26` gave the table three claim columns so `0007`'s per-query dispatch could lease a row to a
contributor, and stopped there. `T-38` reported the gap: `release_search_query_claim` frees the row
with `last_run_at` untouched, so `due_queries()` returns it again and a second contributor spends a
second SerpApi credit on a search that already happened.

**Three things about that framing were checked before deciding; two were wrong.**

1. **Not reachable today.** All three query routes in `api/app.py` lease a dataset string in
   `job_ingest_state`; nothing calls `try_claim_search_query` or its siblings. The endpoint half of
   per-query dispatch is unbuilt too. So this is decided before the first writer lands — the call
   `T-26` made for `claim_granted_at`, for its stated reason: a guard added after the writer is a
   guard added after the corruption.
2. **`T-38`'s shape (2) is not narrower than shape (1).** A "narrow server-side writer in `api/`"
   needs the identical `GRANT UPDATE (last_run_at, …)`. The split between these roles "is enforced
   by GRANT, not by comment" (`backend/schema.py:992`); shape (2) buys the same exposure and pays
   with a convention.
3. **Shape (3) named a table that cannot carry the fact.** `jobs_api` holds `SELECT` on
   `search_query_results` and nothing else, deliberately (`backend/schema.py:1001`), so a
   contributor's submit writes no row there at all.

## Decision

**The five stay the pipeline's. `jobs_api` never gains `UPDATE` on them. The fact crosses as data,
in `submission_log`** — which `api/` already holds `INSERT` on and the pipeline **owns**, verified
on the deployed database rather than inferred. **No grant changes in either direction.**

1. **A fourth action, `run`**, written by the dispatch endpoint `0007` owes, on the branch
   `mark_success` sits on in the other mode. Not inferred from the existing `submit` row, because
   `api/app.py` writes one on the success path *and* both refusal paths and `reason` does not
   separate them (`backend/api/app.py:596`). Counting a refused submit as a run is `D08` rebuilt one
   table over.
2. **`searchqueries.reconcile_contributor_runs()`**, step 2 of the nightly step: after the seed,
   **before the decay** (`should_retire` reads `last_result_at`) and **before the dispatch**. It
   **calls `record_run`** rather than holding its own `UPDATE`, so that function stays the one
   writer and its `last_result_at` rule applies without being copied.
3. **One definition of the wire format.** `dataset_for_query()` and `CONTRIBUTOR_RUN_ACTION` live in
   `searchqueries.py`, imported by `api/query_claims.py` — the only direction `.claude/CLAUDE.md`'s
   layout rule allows.

## Consequences

**The cost is a lag, and it is real:** between submit and the next cycle the row is claimable with
`last_run_at` untouched, so one duplicated search per cycle is possible. That was weighed against a
grant letting any bug on the service side silence a query for *every* Builder by writing a future
`last_run_at`. If the bound proves too loose, hold the claim through the reconcile — do not widen
the grant.

**The reader exists before its writer**, which is `D41` inverted rather than repeated: it is pinned
by tests against a writer of the right shape, one of which drives the real `log_submission`.

**The boundary is asserted, not described.** The GRANT is the enforcement but lives on a database,
and issuing it is `OQ-29`. So a test fails if any statement in `api/` names one of the five, if the
documented GRANT widens, or if the guard's column list and `record_run`'s `SET` clause diverge — in
CI, where no database exists, and it is the only check that survives the wider grant being issued
by hand.

**Not decided here:** the dispatch endpoint itself, still unbuilt and unscoped by this ADR.

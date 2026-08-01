---
script: none -- this is a register over every ingest path, not a per-script reference
written: 2026-07-28
code_at: dd49a27 (audit base) + 28f1d0e (current HEAD, webapp-service)
generator: none
---

> **Provenance.** `generator: none` is literal: nothing in this repo produces
> `docs/ingest/*.md`. Earlier versions carried `generated:` frontmatter naming a
> tool that was never written, which made `.claude/CLAUDE.md`'s *"never hand-edit"*
> instruction unfollowable — the only way to fix a wrong line was to break the rule.
> The claim was dropped across all fourteen files on 2026-07-31; see
> [`34-documentation-cleanup.md`](../tasks/refactor/34-documentation-cleanup.md) §A2.
> These files are hand-written and are maintained by hand.

# Ingest audit defect register

`docs/ingestion_tests/README.md:7` said the `docs/ingest/` audit "found 16
defects at `dd49a27`," scattered across eleven generated documents with no
single list. This is that list.

**Method.** Walked all eleven `docs/ingest/*.md` files plus
`docs/ingestion_tests/04-score-validation.md` and `05-fetcher-harness.md` (the
two that trace defects into `score.py` and give the audit's own numbered
"defects this would catch" table). Pulled every row from a failure-behaviour
table describing a defect rather than intended behaviour, then grepped all
thirteen documents for `discarded`, `defect`, `silently`, `silent`, and `never
read` to find the rest. Every site below was re-checked against the code at
the current commit (`git log dd49a27..HEAD` touches only `backend/llm.py`,
`score.py`'s model-mismatch guard, and docs/tests for task 01 — no line
numbers cited here moved as a result, confirmed by direct read).

**Total: 45 entries** (`D01`–`D45`, verified unique and gapless) — `D43` and
`D44` were found by task 08 while closing `D15`, and `D45` by task 19's
coverage spike, not by the original pass; all three are recorded in full
below — more than the 16
the README named, because that count
was itself informal (nobody had built the list yet) and because triaging
means finding the remainder, per task 03's instruction to "audit the
remaining sources... before assuming four is the total." 25 are genuinely new
findings from this pass, not previously written up as a defect anywhere.

**Classes** (defined in `docs/tasks/refactor/tranche_one/02-triage-audit-defects.md`):
**silent data loss** (run reports success, rows missing or wrong — fix now),
**loud failure** (crashes/raises — fix opportunistically, harness catches
regressions), **cosmetic** (misleading comment, duplicated work, dead code —
fold into task 34).

**Disposition**, independent of class: **fix now**, **fix with harness**
(needs task 09's fetcher cassettes, or task 08's eval harness, to test
safely — do not fix blind against production), or **won't-fix** (reason
given).

## Allocator — this register owns the `D` prefix

Per [`DOCS-POLICY.md`](../DOCS-POLICY.md) rule 6, one allocator per register and no
register issues an identifier in another's space. **This file owns `D<n>` and nothing
else does.** Decisions are `DEC-<n>` and live in
[`DECISIONS.md`](../tasks/refactor/DECISIONS.md); task numbers live in
[`tasks/refactor/README.md`](../tasks/refactor/README.md).

**Next free: `D66`.** Allocated `D01`–`D45`; **`D46`–`D65` are burnt and must never be
issued.** They are not defects and never were — `DECISIONS.md` continued this register's
count when it started allocating decision IDs mid-file, so those twenty numbers circulate
in eighty-odd places meaning *decisions*. Task 39 re-prefixed the live sites to `DEC-46`–
`DEC-65`, but `CLAUDE_UPDATES.md` and `docs/archive/` are `kind: record` and are
deliberately left unswept, so the old spelling survives in the tree on purpose. Issuing a
defect `D52` would make it ambiguous against those, which is the exact failure rule 6
exists to prevent. Skipping twenty integers is cheap; a number that resolves two ways is
not.

**Cross-register references are written out** — *"defect D45"*, *"decision DEC-52"* —
because a bare `D45` in a code comment cannot be resolved by a reader who does not already
know which file it came from. `backend/tools/ats-discover.py` is the worked example: its
dozen citations all read *"defect D45"* and all mean this register.

---

## Task 34's pass over this register, 2026-07-31

**Eleven closed, six re-dispositioned, three left open with reasons.** Every row
below was re-checked against the code rather than taken from this file.

**Two entries were already done and still listed as owed** — which is the register's
own failure mode, and the reason this pass re-read the code instead of the table:

- **D45's body has said `### D45 — fixed` since task 16's follow-up landed**, while its
  index row said *"**open** — needs a task"*. The index is the part anyone scans.
- **D27's five unused imports are all absent from `ats.py`**, verified name by name.

**Nine were dispositioned *"fix with harness — task 09"*, and task 09 landed three
tranches ago** (`09-fetcher-harness.md`, `68f026f`). Nothing rescheduled them, so they
were neither open-with-an-owner nor closed — invisible in both directions. Three are now
fixed (D10, D12, D17); six are marked **open, UNBLOCKED**, which is a real status rather
than a stale blocker.

**D17 was the cheapest confirmed bug in the repo** and had been waiting on a fix of two
lines. `run_actor_query()` bound `run` only inside the poll loop, so an actor run that
came back `SUCCEEDED` immediately skipped the loop, passed the status check, and read a
name that was never assigned — **a paid Apify run whose results are never collected,
reported as one failed query among many.** The reproduction was already committed at
`tests/test_ingest_cassettes.py`, written to assert the `UnboundLocalError` on purpose
with a note saying *"whoever fixes the defect flips this assertion."* It is flipped.

**Three counts in this register were wrong**, all in the same direction — the code had
more of the defect than the entry claimed:

| entry | recorded | actual |
|---|---|---|
| D28 | *"4 unused imports"* | **5** — the whole `from datetime import …` line is dead |
| D30 | *"5 unused imports"* | 5, but `timezone` **is** used and would have gone in a sweep |
| A5 (task 34) | two stale docstring sites | **three**, plus the cassette's own `note` |

Counted with an AST walk over binding-vs-`Name`-use rather than by grep, because grep
cannot tell an import from the word appearing in a comment — which is exactly how D32's
`ids` was miscounted in the first place.

**Three are left open on purpose, with the reason recorded:**

- **D31** (three of six ingests bypass `lib.http` retry/backoff) — *"I could not
  determine whether this is deliberate or an incomplete migration"* is still the honest
  state, and `weworkremotely.md` says so. Each of the three imports `http` **solely for
  `DEFAULT_TIMEOUT`** and then calls `urllib.request.urlopen` directly, which is either a
  deliberate opt-out of backoff for a cheap endpoint or a migration nobody finished.
  **This is a decision, not a fix**, and making it silently uniform would change retry
  behaviour on three live sources to settle a documentation question.
- **D33** (`google_jobs_query_stats` accumulates, read by nothing) — the adaptive-cadence
  consumer that was meant to read it is **task 25**. Deleting the table now destroys the
  input; wiring it now is task 25's job. Left with the pointer.
- **D34** (22 orphaned `job_ingest_state` watermark rows) — a DELETE against the live
  database, not a code change. It needs the owner at a psql prompt and gains nothing from
  being run by an agent mid-refactor.

## Index

| id | class | disposition | one-line |
|---|---|---|---|
| [D01](#d01) | silent data loss | **fixed** — task 03 | Per-record upsert errors discarded at 8 call sites |
| [D02](#d02) | silent data loss | **open, UNBLOCKED** — task 09 landed | `builtin-nyc.py` title/company zip can silently misattribute |
| [D03](#d03) | silent data loss | **open, UNBLOCKED** — task 09 landed | `builtin-nyc.py` salary regex unscoped, captures false positives |
| [D04](#d04) | silent data loss | won't-fix (documented) | `weworkremotely.py` token from display name — silent duplicate rows |
| [D05](#d05) | silent data loss | **open, UNBLOCKED** — task 09 landed | `weworkremotely.py` drops items with zero counters at any verbosity |
| [D06](#d06) | silent data loss | won't-fix (documented) | `weworkremotely.py` all-feeds-empty indistinguishable from a quiet day |
| [D07](#d07) | silent data loss | won't-fix (mitigated) | Google sources: non-English relative dates silently lose `posted_at` |
| [D08](#d08) | silent data loss | fix before deploy — task 24 | Contributor API: empty submit still advances the watermark |
| [D09](#d09) | silent data loss | fix before deploy — task 24 | Contributor API: unreadable query bank silently mislabels `mode` |
| [D10](#d10) | silent data loss | **fixed** — task 34, 2026-07-31 — now reported, still `[]` | `match.py`: bad `tech_stack` JSON silently becomes `[]` |
| [D11](#d11) | silent data loss | **open, UNBLOCKED** — task 09 landed | `match.py`: demoted/orphaned rows deleted with no recoverable log |
| [D12](#d12) | silent data loss | **fixed** — task 34, 2026-07-31 — `check_criteria_sections()`, 4 tests | `match.py`: a typo'd `criteria.json` section silently disables itself |
| [D13](#d13) | silent data loss | **open, UNBLOCKED** — task 09 landed | `match.py`/`extract.py`: seniority vocabulary drift scores as free |
| [D14](#d14) | silent data loss | won't-fix (documented, low current risk) | `match.py --profile` can silently prune another profile's rows |
| [D15](#d15) | silent data loss | **fixed** — task 08 | `score.py`: `fit_score`/`primary_track` stored unvalidated (audit item 8) |
| [D16](#d16) | loud failure | **fixed** — task 08 | `score.py`: missing `buckets` key kills a profile's whole batch |
| [D17](#d17) | loud failure | **fixed** — task 34, 2026-07-31 — reproduction flipped to assert the rows | `google-apify.py`: `UnboundLocalError` on immediate-success poll (audit item 1) |
| [D18](#d18) | loud failure | fix opportunistically | Uncaught `KeyError` on malformed config (audit item 6) |
| [D19](#d19) | loud failure | fix opportunistically | Normalization outside the per-unit `try` in 4 scripts (audit item 7) |
| [D20](#d20) | loud failure | fix opportunistically | `match.py`: no per-record isolation, one bad row kills the run (audit item 3) |
| [D21](#d21) | loud failure | fix opportunistically | `hn-hiring.py`: `relevance.json` load failure crashes at import |
| [D22](#d22) | loud failure | won't-fix (deliberate) | `ensure_schema` raises uncaught if `public.events` exists |
| [D23](#d23) | silent data loss | **open, UNBLOCKED** — task 09 landed | `hn-hiring.py`: ledger-before-upsert crash window strands comments (audit item 4) |
| [D24](#d24) | silent data loss (unconfirmed) | won't-fix (unconfirmed; revisit if it recurs) | `extract.py`: 15 rows possibly permanently starved at `facts_version=1` |
| [D25](#d25) | silent data loss | **fixed** — `28f1d0e` | Live model silently differed from the documented default |
| [D26](#d26) | cosmetic | **fixed** — task 34, 2026-07-31 — the surviving half was a test's *reason* | Stale "`unescape=False`" claim in two files contradicts `ats.py` |
| [D27](#d27) | cosmetic | **fixed** — verified 2026-07-31, all five absent | `ats.py`: 5 unused imports |
| [D28](#d28) | cosmetic | **fixed** — task 34, 2026-07-31 — **5** unused, not the 4 recorded | `builtin-nyc.py`: 4 unused imports, `http` imported for one constant |
| [D29](#d29) | cosmetic | **fixed** — task 34, 2026-07-31 | `weworkremotely.py`: `parse_posted_at` called twice on the same value |
| [D30](#d30) | cosmetic | **fixed** — task 34, 2026-07-31 — `timezone` IS used and was kept | `weworkremotely.py`: 5 unused imports |
| [D31](#d31) | cosmetic | **open — needs a decision, not a fix** | Inconsistent `lib.http` usage — 3 of 6 ingest scripts bypass retry/backoff |
| [D32](#d32) | cosmetic | **fixed** — task 34, 2026-07-31 | `hn-hiring.py`: 3 unused imports |
| [D33](#d33) | cosmetic | **open — belongs to task 25** | `google_jobs_query_stats` accumulates, read by nothing |
| [D34](#d34) | cosmetic | **open — a data cleanup, needs the live DB** | 22 orphaned `job_ingest_state` watermark rows |
| [D35](#d35) | cosmetic | **fixed** — task 34, 2026-07-31 — env var now actually read | `CLAIM_TTL_MINUTES` documented but unread by `google-serpapi.py` |
| [D36](#d36) | silent data loss | won't-fix (patched API-side) | `claimed_by` asymmetry already caused a real ownership-check bug |
| [D37](#d37) | cosmetic | won't-fix (low stakes) | `google-apify.py`: abandoned actor runs billed and untracked |
| [D38](#d38) | cosmetic | won't-fix (harmless) | `POST /v1/events` impression-dedup race under concurrent requests |
| [D39](#d39) | cosmetic | fix opportunistically | `extract.py`: concurrent runs would double-spend LLM calls (no lock) |
| [D40](#d40) | cosmetic | fix opportunistically | `score.py`: login-triggered and nightly runs can double-spend |
| [D41](#d41) | cosmetic | fix before deploy — task 24 | Contributor API: `claim` is unmetered beyond the daily cap (self-documented gap) |
| [D42](#d42) | cosmetic | **fixed** — task 34, 2026-07-31 — marked seen, counted, reported | `hn-hiring.py`: null comment items re-fetched forever (audit item 5) |
| [D43](#d43) | silent data loss | **fixed** — task 08 | `score.py`: a tombstone left the previous score in place, and `has_fields` let an all-null answer through |
| [D44](#d44) | loud failure | **fixed** — task 08 | `evals/__main__.py`: `evals run` raised `UnboundLocalError` for every task |
| [D45](#d45) | silent under-sizing | **fixed** — verified 2026-07-31; the body has said so and this row did not | `company_ats`: the `never_found` write-back from `ats_seed` is partial. 35 rows against a true population of 139 |

---

## Silent data loss — fix now, before Phase 3

This is the only class that justifies delaying Phase 3, because it is the
only class the operator cannot detect by watching the nightly run.

### D01 — fixed

**Per-record upsert errors discarded, at every one of 8 call sites.**
`lib/upsert.py:157-166`'s `UpsertResult.__iter__` yields `(new, updated,
unchanged)` and never `.errors`, so `x, y, z = upsert(...)` reads naturally
and silently drops every per-record failure. Confirmed at:

- `backend/ingest/ats.py:337`
- `backend/ingest/builtin-nyc.py:404`
- `backend/ingest/google-serpapi.py:325`
- `backend/ingest/weworkremotely.py:225`
- `backend/ingest/hn-hiring.py:426-427` (reads `.new` only; `.errors` never touched)
- `backend/ingest/google-apify.py:232`
- `backend/api/app.py:336`
- `backend/api/query_claims.py:444` (`upsert()` also omits `debug=`, so there
  is no stderr fallback either)

Blast radius: **all ingest** — every write path in the pipeline. A run with a
hundred failed records and zero read errors reports success; the only symptom
is a corpus quietly smaller than it should be. **Status: fixed**
(`docs/tasks/refactor/tranche_one/03-fix-silent-upsert-errors.md`) —
`lib/upsert.py` gained `upsert_checked()`, which logs an `upsert-summary:`
line carrying `errors=N` on every call including when N is zero, and raises
`UpsertErrorRate` above a 5% per-run failure rate. All 8 sites call it;
`UpsertResult.__iter__` is deliberately unchanged. `run-daily.py` now reports
per-step written/dropped counts, so "ran and wrote nothing" and "ran and
dropped everything" no longer print identically.
`backend/tests/test_upsert_checked.py` covers all 8 paths.

### D02

**`builtin-nyc.py` pairs titles and companies by list index, not by
containment**, and nothing verifies the pairing (`backend/ingest/builtin-nyc.py:316-333`).
A card with no company anchor, or an extra `company-title` anchor anywhere
earlier on the page, shifts every subsequent pairing by one — silently
attaching the wrong company to the wrong title, indistinguishable from a
correct row. Whether this has ever fired is unknown; there is no assertion,
no counter, and no stored `raw_json` to audit against.

Blast radius: one source (`builtin`). Disposition: **fix with harness** —
needs a cassette fixture (`docs/ingestion_tests/05-fetcher-harness.md`'s
suggested `fixtures/cassettes/`) to safely exercise a desync case without
scraping the live site to check.

### D03

**`SALARY_PATTERN` is not scoped to a salary element** — it matches
`[0-9]{1,3}K-[0-9]{1,3}K` anywhere in a builtin card window
(`backend/ingest/builtin-nyc.py:148`, `:338`). Any "100K-150K"-shaped
substring is captured as `salary_text`; 135 of 351 live rows have a non-empty
value, none verified against the actual salary field. Blast radius: one
source (`builtin`). Disposition: **fix with harness** — task 09, same
fixture work as D02 (both need a cassette of real `builtin` HTML to change
the regex against without scraping production to check).

### D04

**`weworkremotely.py`'s `company_token` is derived from the posting's display
name**, via `slugify` (`backend/ingest/weworkremotely.py:165`), not a stable
id the way `ingest/ats.py`'s config-sourced token is. A company that changes
how it writes its own name in the RSS title produces a different token,
hence a different primary key, hence a second row for the same posting.
Nothing detects this. Blast radius: one source (`weworkremotely`).
Disposition: **won't-fix** — no alternative stable id exists in the feed;
documented as a known limitation, not actionable without a fuzzy-match layer
the docstring explicitly declines to build.

### D05

**`weworkremotely.py` drops items via three separate `continue` statements
with zero counters at any verbosity**: no colon in `<title>`
(`:146-149`), a `NON_TECH_EXCLUDE_PATTERN` match (`:150-151`), and an empty
`source_id` (`:159-161`); a fourth path, cross-listed duplicates, is also
uncounted (`:206-211`). The summary reports only `len(all_records)`. A regex
change to the exclude pattern that started matching legitimate engineering
titles "would produce no signal at all" (`docs/ingest/weworkremotely.md:309-312`).
Blast radius: one source (`weworkremotely`). Disposition: **fix with
harness** — task 09; adding counters is low-risk but this script is one of
the six task 09 covers, and a cassette confirms the counts match what the
fixture actually drops before changing production output.

### D06

**All four `weworkremotely` feeds returning zero items with zero errors is
indistinguishable from a quiet day.** The failure gate is `if not
all_records and category_errors` (`backend/ingest/weworkremotely.py:219`), so
a run where every feed answers 200 with an empty or fully-filtered body exits
0 silently. Blast radius: one source. Disposition: **won't-fix** — the
document's own analysis holds: `close_stale` is time-based, not diff-based,
so this is not a mass-close risk, only a slow-news-day false negative.

### D07

**Non-English relative timestamps silently fail to parse.**
`hl=en&gl=us` on the SerpApi request is "load-bearing"
(`docs/ingest/google-serpapi.md:398-401`) — without it, Google intermittently
returns relative dates like `"há 2 dias"`, which
`text.parse_relative_posted_at`'s English-only regex cannot parse, losing
`posted_at` with no visible error. Currently mitigated by the two query
params on every call. Blast radius: google sources
(`google-serpapi.py`, `google-apify.py` — shared `google_jobs.py` normalizer).
Disposition: **won't-fix**, currently mitigated; revisit if the query
parameters are ever dropped or a non-US locale is added.

### D08

**A contributor submitting `jobs: []` still advances the query's
watermark.** `submit` performs no non-empty check; `qc.upsert(conn, [])`
writes nothing, then `mark_success` runs unconditionally
(`backend/api/app.py:336-341`), marking the query covered for the next 20
hours. A buggy or lazy contributor worker can silently mark a query "done"
with zero rows collected. Blast radius: one source (contributor API; never
deployed). Disposition: **fix before deploy** — `docs/tasks/refactor/README.md`
Phase 4 task 24 revives this service; this should be closed as part of that
work, not before.

### D09

**`_mode_for_slug` silently returns `"unknown"`** when the query bank is
unreadable at submit time (`backend/api/app.py:389-401`), which feeds
`location_is_remote` via `normalize_job`'s `mode` parameter — a config read
failure at exactly the wrong moment quietly corrupts a stored fact rather
than rejecting the submission. Blast radius: one source (contributor API;
never deployed). Disposition: **fix before deploy** — task 24.

### D10

**`match.py` silently coerces a `tech_stack` JSON parse failure to
`[]`** (`backend/match.py:237-240`), losing that job's tech-match signal for
every profile with no counter anywhere. Blast radius: all profiles (match
stage). Disposition: **fix with harness** — task 09 (match.py fixes need the
scratch database it builds, per its own "do not fix blind against
production" principle); log a counter, no semantic change needed since `[]`
is a reasonable fallback.

### D11

**Demoted and orphaned `job_matches` rows are deleted with no recoverable
log of which jobs.** Only counts reach stdout
(`backend/match.py:274`, `:298`, `:363-369`). A weight edit that demotes
hundreds of rows reports a number with no way to see which — and the rows
are already gone by the time anyone looks. Blast radius: all profiles (match
stage). Disposition: **fix with harness** — task 09; log job ids at
`DEBUG_PRINT_KEYS` verbosity at minimum, since `match.py` currently reads
that flag nowhere.

### D12

**`criteria_json` structure is not validated at scoring time.** Every
section lookup defaults via `.get()` (`backend/match.py:97`, `:122`, `:133`,
`:139`, `:149`, `:163`, `:173`), so a typo'd section name in a profile's
criteria silently disables that entire section's penalty rather than
erroring. `profiles.validate()` runs before every write but nothing re-checks
at read time. Blast radius: all profiles (match stage). Disposition: **fix
with harness** — task 09.

### D13

**`match.py`'s `SENIORITY_ORDER` must stay a superset of `extract.py`'s
`SENIORITY` vocabulary, and nothing asserts it**
(`backend/match.py:65-66`, `:116`; `backend/extract.py:82-83`). A level
present in one and absent from the other silently scores as free rather than
raising. Blast radius: all profiles (match/extract coupling). Disposition:
**fix with harness** — task 09; a shared constant or a startup assertion
would close this cheaply, verified against the scratch database rather than
production.

### D14

**`match.py --profile X` can silently prune another profile's valid match
rows.** `prune_orphans` deletes any `job_matches` row for the run's
profile(s) whose `job_id` is not in the loaded fact set
(`backend/match.py:271-274`), but `load_facts` applies the relevance union
of only the **selected** profile(s) (`:351-352`). Running
`match.py --profile frontend` therefore loads facts filtered by `frontend`'s
config alone, and any `frontend` match row for a job that only `tech`'s
config admits would be pruned as an orphan. Whether this is intended is not
determinable from the code — the union exists specifically to avoid this
class of problem, but is applied over `active` profiles or the single
`--profile`, never over all profiles regardless of selection. Blast radius:
manual single-profile runs only (the nightly nine-step run always scores all
active profiles together, so it is not exposed there). Disposition:
**won't-fix, for now** — no task currently owns this and it has not been
observed to fire; the reason it is left open rather than fixed is that its
intended behavior is itself unresolved (the union exists specifically to
avoid this class of problem, but is not applied consistently across
`--profile` and default runs). Revisit before Phase 5's multi-tenancy work
makes `--profile` a routine, rather than exceptional, invocation.

### D15 — fixed

**`score.py` writes `fit_score` and `primary_track` straight from model
output with no coercion, unlike `extract.py`'s `_enum()`/`_int_or_none()`**
(`backend/score.py:372-373`; full write-up and SQL to run first in
`docs/ingestion_tests/04-score-validation.md:38-83`) — this is "audit item
8." Scoring's vocabulary is Title Case with spaces (`Core SWE`, `AI
Integration`, ...), which is a different trap from extraction's snake_case
one: naively reusing `extract._enum()` would *silently rewrite* every stored
value. A drifted `primary_track` is invisible until something renders it
(`match.py` never reads it); an out-of-range or wrongly-typed `fit_score`
persists unclamped. Blast radius: all profiles (score stage). Disposition:
**fixed** — task 08, 2026-07-28.

`score.normalize()` (`backend/score.py`) now returns the exact column values
or `None`, with its own `TRACKS` vocabulary in stored Title Case and a
canonicalising comparison; `update_job_score` takes normalize()'s output and
indexes its keys, so there is no longer a path from a model response to the
table that skips coercion. Covered by `backend/tests/test_score.py`, which
also asserts the trap: `extract._enum()` rewrites all five track names.

**The register was right that this was worth checking before deciding how
much to coerce.** Measured against production on 2026-07-28 (method and full
output in `docs/score-validation.md`): 1,294 rows, `fit_score` between 0 and
95, and exactly **three** off-vocabulary `primary_track` values — all
`frontend_core`, all on the `frontend` profile, all written by
`deepseek-v4-flash`. So the drift is real but rare (3 of 1,237 model-written
rows, 0.24%), which is why the fix is a guard rather than a migration: the
stored form stays Title Case and no existing row is rewritten.

### D43 — fixed

**A tombstone left the previous score in place, and `llm.has_fields` let an
answer that was null in every column through as a row.** Two halves of one
outcome — a row in `job_scores` that reads as a real score and is not one.
Found by task 08 while running D15's diagnostic SQL.

`mark_score_failed`'s `ON CONFLICT` updated only `scored_at` and
`scoring_model` (`backend/score.py`, before this task), so a row
`update_job_score` had already written kept its `fit_score`, `primary_track`
and narrative under a `FAILED:` model label — contradicting this module's own
docstring, which promises a tombstone leaves "`fit_score` left NULL". And
`llm.has_fields` (`backend/llm.py:365-366`) checks that the six keys are
**present**, not that any holds a usable value, so `{"fit_score": null,
"primary_track": null, ...}` passed the write gate.

**Measured, not inferred:** 3 rows in production carry a `FAILED:` label with
a non-NULL `fit_score` (15, 80, 80) and a NULL `primary_track` and NULL
`gap_bridging_angle` — the combination only these two paths together can
produce. Every query that reads `fit_score` without also reading
`scoring_model` believes them. Blast radius: all profiles (score stage);
small in count, but silent by construction. Disposition: **fixed** — task 08:
the tombstone's `ON CONFLICT` now nulls all six narrative columns, and
`score.normalize()` rejects a response with nothing usable in it before it
can be written. The three existing rows are not backfilled — database
contents are staging data, and the next score of those postings overwrites
them correctly.

---

## Loud failure — fix opportunistically; the harness catches regressions

### D16 — fixed

**`score.py`'s `build_prompt` hard-indexes `persona["buckets"]`, but
`profiles.validate()` does not require the `buckets` key**
(`backend/score.py:301-303`; `backend/profiles.py:139-142` lists only
`background_summary`, `strengths`, `honest_gaps`, `scoring_instructions`). A
profile saved without `buckets` validates cleanly, then raises an uncaught
`KeyError` at scoring time. `score_one_job`'s only exception handling around
`build_prompt` is an outer `try/finally` (`:431`, `:462`) that just closes the
connection and re-raises; the inner `try` catches only
`llm.TransientError`/`(RuntimeError, JSONDecodeError)` around `llm.call`
(`:433-445`) and sits *below* the `build_prompt` call at `:432`. Because
`run_for_profile` materializes `pool.map` through `list()` (`:490`), the
`KeyError` takes down the **whole profile's remaining batch** — worse than a
deferred call, because a deferral is at least recorded. Full write-up:
`docs/ingestion_tests/04-score-validation.md:122-177`.

Blast radius: one profile's entire batch per occurrence (score stage). Not
`match.py`-class in blast radius, but the same missing-isolation defect
class as D20. Disposition: **fixed** — task 08, 2026-07-28.

**It was armed, not hypothetical.** The `pursuit` profile is `active` with a
persona that has no `buckets` key (verified 2026-07-28), and the only reason
it has never fired is `daily_narrative_budget = 0` — `select_shortlist` is
asked for zero rows, so `build_prompt` is never reached. The first budget
task 13 sets would have ended that profile's every batch.

**Only one of the two changes task 08 scoped was made, and the other was
deliberately rejected.** `build_prompt` now treats `buckets` as optional and
omits the section entirely when it is absent (the prompt is byte-identical
when it is present, so no cached response or prior comparison is
invalidated), and `score_one_job` guards its body: an unexpected exception
is a new `ERRORED` outcome — one job, nothing written, loud on stderr, and
named separately in `main()`'s summary so it cannot be misread as the
endpoint rate-limiting.

Adding `buckets` to `profiles.validate()`'s required keys was **not** done.
Under the Pursuit scope a persona with no positioning buckets is legitimate —
there is no single target role to bucket against — so requiring the key would
reject a profile that already exists and is active. Doing both would have
converted a scoring-time crash into a save-time one rather than removing it.
The reasoning is left as a comment at `backend/profiles.py:139-149` so the
absence does not read as the oversight it originally was.

### D17

**`google-apify.py`'s `run` variable is referenced before assignment when an
actor's start response already reports `SUCCEEDED`.** `run` is bound only
inside the polling `while` body (`backend/ingest/google-apify.py:179-190`);
a status of `SUCCEEDED` (or anything outside `("READY", "RUNNING")`) at the
*first* check skips the loop entirely, so `run["data"]["defaultDatasetId"]`
at line 190 raises `UnboundLocalError` — not in the caught list at
`:223-224` — and propagates, killing the step rather than counting as an
ordinary query error. This is "audit item 1." Whether Apify can return
`SUCCEEDED` synchronously from run-creation was not confirmed against the
live API. Blast radius: one source (`google-apify`). Disposition: **fix with
harness** — `docs/ingestion_tests/05-fetcher-harness.md` names the exact
fixture needed: `apify-immediate-success.json`.

### D18

**Uncaught `KeyError` on malformed config, before the guarded load
completes.** Two sites: `company["platform"]`/`company["token"]` in
`backend/ingest/ats.py:320-321` (subscripted before the `try` at `:325`,
inside the per-company loop, so one config entry missing either key kills
the whole run); and `bucket["queries"]`/`bucket["daily_budget"]` in
`backend/ingest/google-serpapi.py:213-214` (subscripted inside
`pick_stale_queries_by_bucket`, which runs after `load_query_buckets`'s
`try/except KeyError` at `:300` has already returned — the guard only covers
the top-level `buckets` key, not per-bucket structure). This is "audit item
6." Blast radius: one source each. Contrast: `google-apify.py`'s equivalent
subscripting sits *inside* the function its own `try` wraps
(`docs/ingest/google-apify.md:303-307`), so it is the better-guarded of the
two Google scripts. Disposition: fix opportunistically — move the
subscripting inside the guarded load, matching the apify script's pattern.

### D19

**Normalization/parsing happens outside the per-unit `try` block in four of
six ingest scripts**, so one malformed record's exception kills the entire
run rather than one unit. This is "audit item 7."

- `backend/ingest/ats.py:334` — normalize call outside the fetch-only `try`
  at `:325-332`.
- `backend/ingest/builtin-nyc.py:390` — `parse_page` outside the fetch-only
  `try` at `:382-388`.
- `backend/ingest/google-serpapi.py:324` — normalize outside the `try` at
  `:314-322`.
- `backend/ingest/google-apify.py:231` — normalize outside the `try` at
  `:221-229`.

`weworkremotely.py` gets this right — its parse call is inside the `try` at
`:196-198` (`docs/ingest/weworkremotely.md:295-296`). Blast radius: one
source each, four sources total. Disposition: fix opportunistically — move
each normalize/parse call inside its script's existing `try`.

### D20

**`match.py` has no per-record isolation anywhere in the stage** — the only
write path in the pipeline without `lib/upsert.py`'s per-record SAVEPOINT.
`score_job` is called unguarded at `backend/match.py:290`; a non-numeric
`criteria.json` weight raises an uncaught `TypeError` at `total += delta`
(`:92`). The `executemany` at `:304-316` is a single statement with no
per-row isolation, so one bad tuple aborts the whole batch. Any exception
propagates out of `match_profile` and kills the run **for all profiles**,
including ones already computed but not yet committed. This is "audit item
3," and `docs/ingestion_tests/05-fetcher-harness.md:45-57` notes the same
class recurs in `score.py` (D16) — three of nine pipeline scripts now known
to lack it, making this "a pipeline-wide invariant to test for," not a quirk
of one script.

Blast radius: all profiles, all of `job_matches` (match stage — the only
stage with no external call, which is also the reason isolation was skipped
here in the first place, per the doc's own speculation). Disposition: fix
opportunistically — no task currently owns this specifically; the fetcher
harness (task 09) is the natural place to add regression coverage once a
scratch database exists.

### D21

**`hn-hiring.py` has a hard, unguarded import-time dependency on
`config/relevance.json`.** `relevance.load()` runs at module import
(`backend/ingest/hn-hiring.py:90`, `:152`, into module-level `ROLE_PATTERN` at
`:164`). `_python_role_pattern` guards only `re.error` from pattern
translation (`:158-161`), not the file read itself. A config file that
cannot be read or parsed crashes at import, before `main()` runs and before
the standard `FAILED:` reporting convention applies. Blast radius: one
source (`hn_whoishiring`). Disposition: fix opportunistically.

### D22

**`schema.ensure_schema` raises an uncaught `RuntimeError` if
`public.events` exists in the target database**
(`backend/schema.py:261-266`; nothing catches it at `backend/ingest/ats.py:301`,
and by the same call pattern, every other ingest script). Blast radius: all
ingest (shared `ensure_schema` call). Disposition: **won't-fix** —
`docs/ingestion_tests/05-fetcher-harness.md:19-22` names this "FOOTGUN 2" in
`lib/dbconn.py` and explicitly calls it a *feature* to keep, since it is
what stops a script from running against a database still holding the
legacy `events` table shape.

### D23

**A crash between the `hn-hiring.py` ledger commit and the `jobs` upsert
commit permanently strands comments.** The ledger commits once, after the
whole comment loop (`backend/ingest/hn-hiring.py:422`); the `jobs` upsert
commits separately, at the end of its own batch
(`backend/lib/upsert.py:235`). A crash between the two leaves comments
marked seen in `hn_seen_comments` with no corresponding `jobs` row — and
because the ledger is what gates re-fetching, a subsequent normal run would
skip them permanently; only `--reparse` recovers them. This is "audit item
4." No test covers this and no evidence in the journal that it has
occurred. Blast radius: one source (`hn_whoishiring`), unconfirmed
frequency. Disposition: **fix with harness** — task 09 lists this as
naturally expressible as a cassette test (crash-injection between the two
commits).

### D24

**15 `job_facts` rows are possibly permanently starved at
`facts_version=1`.** They match `select_unextracted_jobs`'s `NOT EXISTS ...
facts_version >= 2` predicate and so should be re-extracted
(`backend/extract.py:184-186`), but `ORDER BY j.first_seen DESC LIMIT 40`
puts the newest eligible rows first every run — if newer eligible rows
keep arriving ahead of them in the queue, these 15 could never be reached.
Whether they are actually starved by ordering, or simply excluded by the
relevance union or a closed status, was not determined; confirming it
requires running the query against live data with the current profile
configs, which is out of scope for a read-only audit. Blast radius: one
source (extract stage), 15 rows currently. Disposition: **won't-fix,
unconfirmed** — no task currently owns this and the number is small (15
rows); a one-line diagnostic query (not a fix) would settle whether it is
real, and should be run before Phase 3's volume increase makes the answer
harder to see, but nothing today depends on the answer.

### D25 — fixed

**The live extraction/scoring model silently differed from the documented
default.** All `job_facts`/`job_scores` rows were written by
`deepseek-v4-flash@api.deepseek.com`, while `backend/llm.py`'s
`DEFAULT_MODEL` and `backend/README.md`'s configuration table both named
`glm-4.5-flash` — three sources (code default, `.env`, docs) giving three
different answers to "what runs in production," with nothing in code
enforcing agreement. This mattered specifically because every
self-consistency figure this refactor's decisions rest on
(`docs/ingestion_tests/README.md`'s 76%/94% numbers) is model-specific.
Blast radius: measurement validity across the whole pipeline (extract +
score stages). **Status: fixed, commit `28f1d0e`**
(`docs/tasks/refactor/tranche_one/01-pin-production-model.md`) — `llm.py`'s
`DEFAULT_MODEL` now pins `deepseek-v4-flash`, and `llm.model_mismatch()`
refuses to start under a different resolved model when
`JOBS_EXPECTED_MODEL` is set, wired into both `extract.py` and `score.py`.

### D36

**`job_ingest_state.claimed_by`/`claim_granted_at` exist but are never set
by `ingest/google-serpapi.py`, only by the contributor API's claim path** —
an asymmetry that already caused a real bug: the pipeline taking over an
expired claim leaves `claimed_by` stale as the previous contributor's id, so
a naive `claimed_by == caller` ownership check on the API side would pass
for a contributor whose claim had already been taken over
(`docs/ingest/google-serpapi.md` Open Questions;
`docs/ingest/contributor-api.md` "`holds_claim` and the takeover problem",
`backend/api/query_claims.py:243-285`). The fix (`claim_granted_at` as a
second condition) was applied API-side only — the root asymmetry in
`job_ingest_state`'s write pattern still exists. Blast radius: cross-component
(google ingest scripts + contributor API, sharing one table). Disposition:
**won't-fix** — already patched at the point that mattered; recorded here so
the next person touching the claim schema knows the asymmetry is load-bearing
for that fix, not an oversight to "complete" by having the ingest scripts set
the same columns.

### D44 — fixed

**`python3 -m evals run` raised `UnboundLocalError` for every task, on every
invocation.** `cmd_run` re-imported `corpus as corpus_mod` inside its
`--golden` branch (`backend/evals/__main__.py:143`, before this task) even
though the module already imports it at `:31`. Python decides local-vs-global
at compile time, so that one line made `corpus_mod` a local for the whole
function — and `:99`, which loads the corpus on every run, referenced it
before assignment. The `--golden` branch that caused it never had to execute.

Found by task 08 running its own definition of done
(`python3 -m evals run --task score --corpus ...`). It is not
score-specific: `--task extract` fails identically, because the failing line
runs before the task is used at all. It was introduced by task 07 (`3a8b42c`,
2026-07-28) alongside the `--golden` flag, so the window was one day.
`evals selfcheck` was unaffected — it has no such re-import — which is
why the gap went unnoticed. Blast radius: the eval harness CLI only, nothing
in the pipeline. Disposition: **fixed** — task 08 deleted the redundant
import; both `--task extract` and `--task score` now run.

---

### D45 — fixed

**`company_ats.status = 'never_found'` holds 35 rows against a true population
of 139, and the 35 are an alphabetical block.** `ats_seed` records a probe
outcome per employer (`backend/migrations/migrate_company_ats.py:98-116`);
`last_probe_outcome = 'not_found'` — "page fetched, no ATS signature", the real
negative — is **139** of its 376 rows. Only **35** of those got a `never_found`
row written back into `company_ats`; **104** never got a row at all.

The 35 are not a sample. Grouped by first letter of `employer_name` they are
`M=8 N=20 O=2 P=5` — a contiguous block, which is the signature of a write-back
that stopped partway rather than of anything about employers. Reproduce:

```sql
SELECT left(employer_name,1), count(*) FROM company_ats
WHERE status='never_found' GROUP BY 1 ORDER BY 1;

SELECT count(*) FROM ats_seed WHERE last_probe_outcome='not_found';        -- 139
SELECT count(*) FROM ats_seed s WHERE s.last_probe_outcome='not_found'
  AND NOT EXISTS (SELECT 1 FROM company_ats a
                  WHERE a.employer_name=s.employer_name AND a.status='never_found');  -- 104
```

**Why it matters more than its size.** `company_ats.status` is what downstream
work sizes itself against. Task 19 names `never_found` as its entire population
(`19-jsonld-parser.md:15-17`), so its brief was written against 25% of the set it
meant to describe. Task 17's roster and task 16's coverage figures read the same
column. Nothing crashes; the numbers are just quietly too small, which is this
system's documented failure mode — *"Silence is this system's failure mode"*
(CLAUDE.md), and *"alert on volume, not errors."*

Found by task 19's coverage spike (`2fecec5`) while assembling its probe
population, not by the original triage pass. The spike worked around it by
probing 35 target rows plus a 20-employer control drawn from `ats_seed`
directly, and the workaround is what surfaced the discrepancy.

**Root cause: two durability cadences on two different axes.** A probe writes
two tables. `record_probe()` leaves an `UPDATE ats_seed` pending on the
connection and the loop committed it **every 20 iterations**; the `company_ats`
rows were buffered in a Python list and flushed **every 50 records**
(`FLUSH_EVERY`). Because one counted *employers* and the other counted
*records*, no choice of constants could align them — and any run that died
before the final flush kept the seed outcome durably while silently discarding
the buffer. `--limit` defaulting to 20 with `ORDER BY last_probed_at NULLS
FIRST, employer_name` made successive runs walk the roster alphabetically,
which is where the block shape comes from.

The database still holds the fingerprint. Three passes ran on 2026-07-28
(`ats_seed.last_probed_at`): 07:14 probed 140 employers, 07:36 probed 40, 07:40
probed 100. Every one of those 280 outcomes is in `ats_seed`. `company_ats`
received rows from the 07:40 pass only, and **exactly 50** of them — `never_found`
35 + `valid` 7 + `unvalidated` 5 + `dead` 3 — which is one flush batch and not a
number any probe result would produce. The 104 shortfall is 71 + 22 from the two
passes that wrote nothing plus 11 from the truncated tail of the third.

Fixed in `backend/tools/ats-discover.py`:

- **One boundary, on the iteration axis.** `commit_batch()` is now the only
  place either table is made durable, called at `i % FLUSH_EVERY == 0` and once
  at the end (`probe_pass()`). `flush()` → `upsert()` commits, and that commit
  lands the pending `record_probe()` UPDATEs in the same transaction, so the
  two tables are partial by the same amount or not at all. `FLUSH_EVERY` is 20.
- **The loop was lifted out of `main()` into `probe_pass()`** so the cadence can
  be tested rather than argued. `tests/test_ats_discovery.py::CadenceTests`
  kills a pass at every one of 60 indices and asserts the two committed sets are
  equal. Against the pre-fix cadence that test fails at 31 of the 60 kill points;
  against the fix it passes at all 60.
- **A dropped record no longer exits 0.** `flush()` still survives one bad batch,
  but `reconcile_seed_outcomes()` re-reads `company_ats` for the batch's ids and
  clears `last_probed_at` / `last_probe_outcome` for any employer whose row is
  absent, so the employer is re-probed instead of being recorded as settled. This
  closes the last one-record-wide version of the same divergence: `upsert()`
  isolates per-record failures with a SAVEPOINT and commits the survivors
  *before* `check_error_rate` raises (`lib/upsert.py:198,:235`), so the seed
  outcome would otherwise have outlived the row. The run then exits 1.
- **Backfill, no network.** `--backfill-never-found` re-derives a row for every
  `ats_seed.last_probe_outcome = 'not_found'` via `ats_discovery.never_found_row()`.
  Applied 2026-07-28: 104 new, 35 unchanged, 0 dropped. `never_found` 35 → **139**;
  `valid` 75, `unvalidated` 5, `dead` 3 all unchanged. A second run reports 139
  unchanged. The 35 original rows keep `discovered_via = 'probe'`; the 104 carry
  `'backfill-from-ats_seed'`.

**Blast radius: reporting and sizing only, never ingest.** `never_found` rows
have `ats = ''` and `token = ''`, and `ingest/ats_sources.py:107-115` filters on
`ats = ANY(HANDLED_PLATFORMS)`, `status = ANY(('valid','unvalidated'))` *and*
`token <> ''` — three independent exclusions. Measured: the roster is 70 rows
before the backfill and 70 after.

**The widened column is still a floor, and is now measurably so.** `never_found`
means *"no ATS URL in the served HTML"*, not *"no ATS"*
(`backend/ats_discovery.py:499-508`). Of the four positive controls with a
verified live board — Datadog, MongoDB, Justworks, Ramp — the probe returned
`not_found` for all four, because their careers pages are client-rendered. All
four now carry a `never_found` row *alongside* their valid `greenhouse`/`ashby`
token row, so the column carries its own falsification: **≥4 of 139 rows are
provably wrong**, and every coverage figure derived from it is a lower bound.
Backfilling 104 rows widens a population that is already false-negative-heavy;
it does not make it more correct, it makes it complete.

Disposition: **fixed** — cadence aligned, backfill applied, 8 tests added (782 →
790). Unchanged and still open: 96 of 376 `ats_seed` rows have `last_probed_at`
NULL and have never been probed at all, which is why the `never_found`
first-letter histogram now runs A–R and stops. That is a separate gap in the
probe's coverage of the roster, not in this write-back.

**Follow-up for whoever owns `tools/jsonld-probe.py`** (not touched here):
`SEED_NOT_FOUND_SQL` at `:1000-1007` selects seed `not_found` rows *without* a
`company_ats` row as its wider control population. That set is now empty by
construction, which is correct behaviour but makes `--extra-sample` a no-op, and
the comment at `:995-999` still says "company_ats holds 35 never_found rows".

---

## Cosmetic — fold into task 34

### D26

**A stale claim about `ats.py` appears in two other files and contradicts
the code.** `backend/lib/text.py:112-114` and
`backend/tests/test_row_identity.py:171` both say "ats.py passes
`unescape=False`," but at this commit `normalize_lever`, `normalize_ashby`,
and `greenhouse_description` all use the default `unescape=True`
(`backend/ingest/ats.py:193`, `:261`, `:291`). `backend/migrations/migrate_ats_descriptions.py:6`
uses the past tense — "ingest/ats.py **passed** `unescape=False`" — and
appears to be the accurate account; the other two comments were not updated
when the behavior changed.

### D27

**5 unused imports in `ats.py`**: `re` (`:118`), `hashlib` (`:119`),
`urllib.request` (`:120`), `timedelta` (`:122`), `ids` (`:132`, used
indirectly through `lib/upsert.py` but never referenced by name in this
file).

### D28

**4 unused imports in `builtin-nyc.py`**: `hashlib` (`:112`), `datetime`,
`timedelta`, `timezone` (`:116`), plus `ids` (`:126`) unreferenced. `http` is
imported only for the `DEFAULT_TIMEOUT` constant, not its retry logic.

### D29

**`weworkremotely.py`'s `parse_posted_at` is called twice on the same
input** — once directly (`:172`) and once nested inside
`text.posted_at_timestamp` (`:173`) — producing the same value both times.
Explicitly flagged in `docs/ingest/weworkremotely.md:412-415` as "duplicated
work rather than a defect," with no comment explaining why the
already-computed value at `:172` is not reused. (This is the known member
named directly in `docs/tasks/refactor/tranche_one/02-triage-audit-defects.md:66-68`.)

### D30

**5 unused imports in `weworkremotely.py`**: `hashlib` (`:77`), `html as
html_module` (`:76`), `datetime`, `timedelta` (`:83`), `ids` (`:93`). `http`
is imported only for the `DEFAULT_TIMEOUT` constant.

### D31

**Retry/backoff usage is inconsistent across the six ingest scripts, with
no comment anywhere explaining the split.** `ats.py`, `hn-hiring.py`, and
`google-apify.py` go through `lib.http.get_json`/`post_json` and get 5
retries with exponential backoff; `weworkremotely.py`, `builtin-nyc.py`, and
`google-serpapi.py` call `urllib.request.urlopen` directly and get one
attempt, no backoff, no `Retry-After`. `lib/http.py:3-5` cites exactly this
scenario — "a single transient 503 from one ATS board failed that company
for the day" — as the reason the module exists. `docs/ingest/weworkremotely.md`
Open Questions: "I could not determine whether this is deliberate or an
incomplete migration." Failures here are counted (as category/query errors),
not silent, so this is a robustness gap rather than a correctness bug — but
it does mean transient upstream errors cost more completeness on three of
six sources than on the other three for no stated reason.

### D32

**3 unused imports in `hn-hiring.py`**: `hashlib` (`:77`), `timedelta`
(`:81`), `ids` (`:92`).

### D33

**`google_jobs_query_stats` accumulates and is read by nothing.**
Written by both `google-serpapi.py:334` and `google-apify.py:240`; the
adaptive-cadence logic it was built for was never implemented
(`backend/google_jobs.py:68-74`). Nothing prunes it; 32 rows currently.

### D34

**22 orphaned `job_ingest_state` watermark rows** keyed
`google_jobs:query:*` do not correspond to any of the 32 slugs in
`config/google-queries.json` — evidently from an earlier query bank.
`pick_stale_queries_by_bucket` only ever selects `WHERE dataset =
ANY(current_slugs)`, so they are inert but permanent; nothing prunes them.

### D35

**`CLAIM_TTL_MINUTES` is documented in `backend/README.md` as a
configuration variable but `google-serpapi.py` never reads it** —
`state.try_claim` is called without a `ttl_minutes` argument
(`backend/ingest/google-serpapi.py:235`), so the library default
(`DEFAULT_CLAIM_TTL_MINUTES = 15`, `backend/lib/state.py:90`) silently
applies instead. No code comment addresses the discrepancy between the
README and the call site.

### D37

**Abandoned Apify actor runs are billed and untracked.** A poll timeout
raises at `backend/ingest/google-apify.py:187-188` and the claim is released
immediately (`:226`), but the actor keeps running on Apify's infrastructure
and keeps billing. The `run_id` exists only inside the exception message,
printed under `DEBUG_PRINT_KEYS` only. No reconciliation against Apify's own
billing exists. Disposition: won't-fix — dollar amounts here are small
(≤$0.15/query) and the fix (persisting and polling abandoned run ids) is
disproportionate engineering for the stakes.

### D38

**`POST /v1/events`'s impression-dedup has a race under concurrent
requests.** The `NOT EXISTS` check is evaluated inside the same `INSERT`
statement (`backend/webapp/jobs.py:307-310`), so two simultaneous impression
posts for the same (profile, job) can both find no prior row and both
insert. There is no unique constraint, deliberately — the table is an
append-only log, not a state store. Disposition: won't-fix — a duplicate
impression row is noise, not incorrect data, in an append-only log.

### D39

**`extract.py` has no lock or claim; two concurrent runs (the nightly
pipeline overlapping `backend/scripts/backfill-facts.sh`) would both select
overlapping batches and double-spend LLM calls** (`backend/extract.py:176-191`).
`ON CONFLICT (job_id) DO UPDATE` means the second write does not error, just
costs twice. Disposition: fix opportunistically — a `FOR UPDATE SKIP LOCKED`
on the selection query would close this cheaply if it is ever observed to
matter.

### D40

**A login-triggered `score.py` run and the nightly run can double-spend.**
Both use the same unlocked `NOT EXISTS` anti-join
(`backend/score.py:234-235` in `select_shortlist`); `ON CONFLICT DO UPDATE`
prevents an error but not the duplicate LLM call. Depends on deployment,
which has not happened. Disposition: fix opportunistically, same shape of
fix as D39.

### D41

**Contributor API's `claim` endpoint has no rate limit beyond the daily
per-contributor cap.** `backend/api/README.md:214-224` names this as a known
gap before opening up: an unmetered claim-loop could lock the whole query
bank and starve the operator's own nightly pipeline. The daily cap counts
`submission_log` rows, and a claim that is never submitted writes no such
row, so a pure claim-loop is uncapped by that mechanism. Blast radius: one
source, never deployed. Disposition: **fix before deploy** — task 24.

### D42

**`hn-hiring.py` re-fetches HN items answering `null` forever.** `if not
comment: continue` (`backend/ingest/hn-hiring.py:409-410`) returns *before*
the ledger insert at `:412`, so an id HN answers with `null` is never marked
seen and is refetched on every subsequent run. This is "audit item 5." Not
data loss — the comment never produced a row either way — but a permanent,
low-volume waste of requests with no comment explaining why null bodies
should behave differently from the deliberate "transient failure, don't
mark seen" convention already used for fetch errors at the same site.
Disposition: fix with harness — task 09 lists this as naturally expressible
as a cassette test (`fixtures/cassettes/hn-item-null.json`).

---

## Cross-reference to prior write-ups

For readers arriving from a task file rather than this register:

| Elsewhere called | Here |
|---|---|
| "the original" upsert-discard defect, `ats.py:337` | D01 |
| "audit item 1" (`docs/ingestion_tests/05-fetcher-harness.md:34`) | D17 |
| "audit item 2" (ibid., `:35`) | D01 |
| "audit item 3" (ibid., `:36`, `:45-57`) | D20 (and D16, the same class in `score.py`) |
| "audit item 4" (ibid., `:37`) | D23 |
| "audit item 5" (ibid., `:38`) | D42 |
| "audit item 6" (ibid., `:39`) | D18 |
| "audit item 7" (ibid., `:40`) | D19 |
| "audit item 8" (`docs/ingestion_tests/04-score-validation.md:5`) | D15 |
| the `buckets` `KeyError`, "a second defect" (ibid., `:122-177`) | D16 |
| `weworkremotely.py`'s duplicated `parse_posted_at` call | D29 |

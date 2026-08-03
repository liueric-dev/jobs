---
kind: contract
written: 2026-08-02
generator: none
budget: 400
---

# State of the system

**This file replaced 42,777 lines of Markdown across 137 files on 2026-08-02.** Everything else
under `docs/` was deleted in the same commit. Nothing was lost: it is all in git, and
`refactor-freeze-2026-08-02` tags the tree as it stood immediately before. To read any of it:

```bash
git show refactor-freeze-2026-08-02:docs/tasks/refactor/DECISIONS.md   # or any other path
git ls-tree -r --name-only refactor-freeze-2026-08-02 docs/            # the full list
```

Written from the code, the three test suites and `git log` — **not** from the documents it
replaced. Where the two disagreed, the code won and the disagreement is recorded in § 7.

## 0. How this was produced, and what to distrust

Twenty read-only agents over two runs on 2026-08-02: eight read one code area each, one ran all
three suites, two read the history for tasks 01–29 and 30–54, four checked every task file's
Definition of done against the tree, and four audited the documentation adversarially. The two workflow
scripts that constitute the method, the salvage and extraction tools, the raw structured results
and the extracted registers are all in `orientation-2026-08-02/` beside this file.

**Both workflows were retired 2026-08-03 and the archived copies do not run.** They shell out to
`tools/audit-docs.py` and read ~40 paths under `docs/`, all deleted in the commit that produced
this file — the method audited prose against code, and the prose is gone. They are kept as the
record of how this file was made, not as something to invoke; the registered
`/orientation-from-code` and `/orientation-phase2` skills were removed with them.
`salvage.py` regenerates `orientation-phase2.js`'s inlined ground truth from `phase1.json`, so
nothing was lost by dropping the 443 KB working copy.

**Three things to distrust:**

1. **No finding here was adversarially verified.** The skeptic phase was cut for cost. Each claim
   below rests on one agent's reading plus its citation. The citations are checkable; treat them
   as the evidence, not the prose.
2. **Nothing was read from a running database.** Every claim is about code paths, not data. The
   18 questions in § 4 marked *needs a database* are the ones this created.
3. **The agents' briefs contained 37 factual errors that the code refuted.** That is the method
   working, not failing — but it means a brief-shaped assumption anywhere in this tree is worth
   re-deriving. The largest: relevance.py is not a pipeline stage (§ 1), and the bare-`upsert()`
   defect class no longer exists (§ 5).

## 1. What the pipeline does today

**There are three executable stages, not four.** `backend/relevance.py` reads and writes no rows —
it is a pure SQL-fragment builder with no database access, no `main()` and no `__main__` guard, and
it does not appear in `run-daily.py`'s step list (`backend/relevance.py:1-334`). The executable
stages are `extract.py` → `match.py` → `score.py`.

**`run-daily.py` runs 14 steps, not nine.** `STEPS` holds 14 entries: `tools/ats-discover.py`, 8
ingest scripts, `searchqueries.py`, then extract, match, score, and `cohort.py`
(`backend/run-daily.py:124-241`). Runtime output was always correct because it uses `len(STEPS)`.

*Corrected 2026-08-03.* The stale "nine" is gone from all seven places in `run-daily.py`'s own
docstring, from `deploy/systemd/jobs-ingest.service:41` and from `tools/cost-test.py:113` — the
2026-08-02 commit had fixed it only in `.claude/CLAUDE.md`. The surviving comments name no count
at all, which is the durable fix: `len(STEPS)` cannot drift.

**Two steps cost LLM calls: extract and score.** That claim survives the count drift.

**`match_score` orders the list; `fit_score` only annotates it.** Holds in the code.

**`score_job()` is pure.** Holds. Its `tech:missing` branch is unreachable from the pipeline —
`load_facts()` coerces a NULL `tech_stack` to `[]` (`backend/match.py:396-402`,
comment at `:283-285`).

**A deferral is not a failure.** Holds.

*The tombstone hole beside it was closed 2026-08-03.* `extract.mark_extract_failed()`'s
`ON CONFLICT` used to update only `facts_version`, `extracted_at` and `extraction_model`, so a
posting that extracted at v2 and tombstoned at v3 kept its v2 facts under a `FAILED:` label and
the current `facts_version`. It now NULLs every fact column plus `extraction_passes` and
`vote_unanimity`, mirroring `score.mark_score_failed()`, which had closed the identical hole one
stage over. Ranking was always safe — `match.load_facts()` filters
`extraction_model NOT LIKE 'FAILED:%'` — but the `jobs_app` view does not, and served the stale
values. **No row leaves the view because of this:** its four completeness filters are all on
`jobs`, never on `job_facts`.

**Versions are cache keys — with two exceptions that matter.** `_STALE_ANY` has exactly three
arms, not four: `criteria_version` is recorded for provenance and deliberately excluded
(`backend/score.py:384-387`; `backend/schema.py:764-769`; pinned by
`backend/tests/test_score_versions.py:277-296`). Each arm is guarded by `IS NOT NULL` and uses `<>`
rather than `IS DISTINCT FROM`, precisely so the pre-existing rows that are NULL on all four
columns are not swept into "stale" (`backend/schema.py:774-787`). **Rewriting that predicate with
`IS DISTINCT FROM` silently turns the whole backlog stale, and with a rescore flag spends a call
per row.**

**`FACTS_VERSION=3` is not a passing grade for `vote_facts()`.** The 3-pass path has never run
against real data: the only platform below the agreement threshold is `hn_whoishiring` (0.778) and
every such posting is currently rejected by the relevance union under the `pursuit`-only active
profile set (`backend/schema.py:320-327`).

**`config/extraction-policy.json` changes extraction semantics without bumping `FACTS_VERSION`,
and says so.** A `job_facts` row records `extraction_passes` but not which policy produced it. A
policy file that fails to load degrades silently to one pass everywhere — `load_policy()` catches
`FileNotFoundError` and returns `POLICY_DISABLED`, signalled only by `multi_pass=none` on the
summary line. A JSON syntax error is not caught at all (`backend/extract.py:157-174`, `:1220-1230`).

## 2. What the surfaces are

Three processes, three interpreters, three suites, none of which imports the others' *process*
code — but the "shares only `schema.py` and `lib/`" claim understates the coupling by four modules.

| | |
|---|---|
| pipeline | top level, system `python3`, no venv. `psycopg[binary]` is its only dependency |
| `backend/webapp/` | own venv, `include-system-site-packages = false`. Port 8421 |
| `backend/api/` | own venv, same setting. Port 8420. May not start — a **live-DB** question, not a code one; § 4 |
| `frontend/` | no build step, no npm, no `package.json`. Five screens, all routed |

**`backend/docs/` is not this file's tree and survived the 2026-08-02 purge**, which deleted only
the repo-root `docs/`. One file remains, with a declared `kind:` header and not a contract:
`SCORING.md` (`kind: rationale` — the weight provenance and cost model, append-only and dated by
construction). `DEVELOPER.md`, `OVERVIEW.md` and `HANDOFF-match-quality.md` were deleted
2026-08-03 in the follow-up commit; every structural claim in them had gone false, and
`backend/README.md` had already been rewritten to say they were gone before they were.
`HANDOFF-multimachine-google-jobs.md` (`kind: record`) was the last of that kind and was removed
2026-08-03 (`OQ-16`, decided: close the carve-out rather than keep an exception for one frozen
document). Its two still-live facts moved before deletion: the SerpApi multi-machine locking
section's known bug moved to `backend/README.md`, and its unapplied id-migration (Step 3) became
`TASKS.md`'s `T-20`. The rest — SerpApi account mechanics, the `htidocid` stable-id rationale — was
already duplicated in code comments (`lib/ids.py`) and is readable from `git show
refactor-freeze-2026-08-02:backend/docs/HANDOFF-multimachine-google-jobs.md` if the full narrative
is ever wanted. **The rule is now unqualified: no document may claim current state except the
three `kind: contract` files, with no carve-out.**

**The real import graph:** `webapp/` additionally imports the pipeline's `profiles`
(`onboarding.py:54`), `searchnorm` (`search.py:55`) and `evals.labels` (`label.py:156`); `api/`
imports `google_jobs` (`query_claims.py:61`). What *is* true: `api/` and `webapp/` import nothing
from each other, and no pipeline module imports either (`backend/schema.py:617` states the
stronger claim).

**The webapp binds nothing itself.** `config.PORT` defaults to 8421 and is annotated
"Documentation only"; `app.py` has no `uvicorn.run()`. The only code that turns it into a bind is
`frontend/serve.py:162,177` — which makes the "documentation only" comment wrong, since serve.py is
the supported launcher (`backend/webapp/config.py:123-124`).

**The frontend is shipping, not scaffolding.** 13 ES modules, a 553-line hand-written stylesheet,
five routed screens — Today, Job detail, Saved, Search and Onboarding — 30 shipped fixtures, both
checkers green (`frontend/js/app.mjs:120-137`; `frontend/index.html:45-48`). Search landed in
`3c0452f`, onboarding in `9a774e1`. What is *not* built: the Contribute surface, and the phone test
(needs a device and a Google Cloud Console redirect-URI change).

**The client authenticates with `credentials: "same-origin"`, not `'include'`, and `BASE = ""`**
(`frontend/js/api.mjs:27,74`). Served from any host other than the API's own origin, every request
goes out without the session cookie and returns 401, which the client renders as the sign-in
screen — indistinguishable from being logged out, with no error text anywhere.
`serve.py:78` mounting the page onto the webapp process is what makes it work.

### The suites, as the runner printed them (2026-08-03)

| suite | command | result |
|---|---|---|
| pipeline | `cd backend && python3 -m unittest discover -s tests` | `Ran 1428`, OK, 0 skipped |
| webapp | `cd backend/webapp && .venv/bin/python -m unittest discover -s tests` | `Ran 352`, OK, 0 skipped |
| api | `cd backend/api && .venv/bin/python -m unittest discover -s tests` | `Ran 117`, OK, 0 skipped |

*1469 → 1421 when the 48 doc-policy tests retired with the documents they checked, → 1425 with
`tests/test_citations.py`, → 1428 with its three git-ignore cases. **Re-run rather than quoting
these** — that is the rule this one number has now broken three times in two days, which is the
whole argument for `Ran N tests` over anything written down.*

**Zero tests skipped in any suite.** Twelve backend modules gate on `scratchdb.available()` and all
twelve ran: each calls `envfile.load(backend/.env)` at import time, three lines above the gate, so
an unset shell `DATABASE_URL` does not silence them
(`backend/tests/test_ingest_isolation.py:53-58`). `available()` opens a real connection inside a
bare `except Exception: return False`, so an unreachable Postgres — **or a genuine driver bug** —
reads as a skip (`backend/evals/scratchdb.py:73-99`). `pytest` is installed in none of the three
interpreters. Python is 3.14.

**Never grep for skips with `-iE 'skip'`** — every hit is a test *named* for skipping. The reliable
marker is the literal `... skipped`, or unittest's `(skipped=N)` suffix, which it prints only when
non-zero.

## 3. What is genuinely done

56 task verdicts were formed by checking each Definition of done against the tree. **28 are clean;
28 are a mismatch, partial, or blocked.** The mismatches run in both directions, which is why the
status column was never trustworthy on its own.

**Marked done, actually partial** (the dangerous direction):

| task | what is actually unmet |
|---|---|
| 08 Score validation | The post-task-12 diagnostic queries were scheduled and never run |
| 12 FACTS_VERSION bump | Axis A agreement was never measured before or after, and **now cannot be** — the pre-bump corpus is gone and `job_facts_v2_snapshot` was dropped. A v3 regression is not rollbackable |
| 13 Cohort criteria | 16/20 and 10/20 against a DoD asking 20/20. Correctly not tuned into being met |
| 16 ATS token discovery | 96 of 376 employers never probed; the nightly backfill trips its own circuit breaker (48% > 35%) and exits 1. The positive control failed 4 of 4, so `not_found` is not evidence of absence |
| 18 Workday CXS | Block rate needs a week of runs; three exist, all one day |
| 23 SERP abstraction | Two SerpApi implementations coexist and **disagree**: `ingest/google-serpapi.py:335-337` raises on any `error` key, so "no results" is recorded as a query failure; `serp/providers/serpapi.py:78-94` treats it as empty. Held back on purpose by `DEC-99`. Router fallthrough is unimplemented and unflagged |
| 26 Profile creation | The four onboarding preferences are stored and filter nothing |
| 34 Cleanup | Genuinely done; the Status line still says `NEXT` |

**Marked todo, actually further along:** 30 (two DoD items met), 25 (six of seven), 48 (done, its
own row never flipped until this commit).

**Two task numbers are used twice.** `tranche_seven/47-widen-the-c4-match-body.md` and
`tranche_eight/47-split-the-entry-point.md` are different tasks; only the second has a register
row, so the index implies 47 is done when half of it was never started. Duplicate 34 was diagnosed
and closed on 2026-07-31 (`3f42e2d`) — that one is resolved.

**Task 15 has no commit and no code at all.** Blocked on an Adzuna account
(`backend/tools/ats-discover.py:57-58`).

**There is no `git revert` anywhere in this history.** Every reversal is a prose change inside a
forward commit, so a mechanical revert scan under-reports what was undone.

## 4. What is genuinely open

### (a) Needs work — someone could pick these up

- **`api/` may not start — but nothing in the code says so, and this entry was wrong twice.**
  Re-checked 2026-08-03. `verify_schema()` is at `backend/api/app.py:82` (not `:143`; the column
  loop is `:143-154`, the raise `:156-161`), and it requires `submission_log.action`
  (`query_claims.py:128`). **There is no mismatch between the two definitions:**
  `qc.ensure_schema` creates the table *with* `action TEXT` (`query_claims.py:233`) *and*
  backfills it via `dbconn.add_missing_columns` (`:244`), so `manage_users.py init-schema`
  satisfies the check on a fresh or an existing database. What remains is a claim about **live
  database state** — that init-schema has not been run against the deployed DB — which this repo
  can neither confirm nor refute. Run it and see.
  The recovery claim was also wrong: `JOBS_ADMIN_DATABASE_URL` is indeed absent from
  `backend/api/.env`, but `manage_users.py:42` reads
  `os.environ.get("JOBS_ADMIN_DATABASE_URL", qc.DATABASE_URL)` and **falls back**. If anything
  blocks self-repair it is that `jobs_api` lacks CREATE on public — a grant question, not an
  env-file one.
- ~~`renders.forgetAll()` is exported and called by nothing~~ **Fixed 2026-08-03.** `signOut()`
  now flushes first — the outgoing Builder's events are theirs — then calls `stopObserving()`,
  `forgetAll()` and a new `events.forgetImpressions()` (`frontend/js/app.mjs:17,221-222`;
  `events.mjs:68`). Three checks in `frontend/check_client.mjs:1222-1257` cover the
  sign-out/sign-in cycle that nothing covered before, and they were verified to fail with the fix
  reverted.
- ~~`POST /v1/events` is spelled twice~~ **Fixed 2026-08-03.** The unload flush goes through
  `api.postEvents` with a `keepalive` option like every other caller, and its rejection is at least
  logged (`frontend/js/events.mjs:30,191`; `api.mjs:304-314`). The old literal could only ever have
  caught a synchronous `fetch()` throw — never a rejection or an HTTP error — while the queue was
  already spliced, so a refused unload batch vanished silently.
- **`ensure_app_view`'s DROP fallback destroys GRANTs with no re-grant anywhere in the repo.** A
  column reorder raises `InvalidTableDefinition`, the handler DROPs the view, and DROP VIEW takes
  every GRANT with it. It surfaces on the *next* nightly run as the webapp refusing to start
  (`backend/schema.py:1215-1223`).
- ~~The 24h impression dedup is keyed `(profile, job_id)`, not `(app_user_id, job_id)`~~ **Fixed
  2026-08-03 (OQ-2).** Thirty Builders share the `pursuit` profile, so one Builder's render used to
  suppress another's impression — and the skips derived from it — for the rest of the window.
  Rekeyed to `(app_user_id, job_id)` (`backend/webapp/jobs.py:950-954`); the existing
  `idx_job_events_user_job` partial index already served the new predicate, so no schema change was
  needed. Existing `job_events` rows written under the old key are not backfilled.
- **`tools/compare-models.py` and `tools/claude-bench.py` still select their corpus with
  `ORDER BY j.first_seen DESC` against production** — the exact pattern the evals package exists to
  replace. Any comparison made with either is not reproducible
  (`backend/tools/compare-models.py:84`; `claude-bench.py:113`).
- **`tools/learned-ranker-probe.py` trains and evaluates on the same layer.** Re-checked
  2026-08-03, and this entry overstated one half and misstated the other. The numpy/sklearn
  imports are **not** a defect: they are wrapped in `try/except ImportError` ending in a
  `sys.exit` that prints the throwaway-venv recipe (`:127-143`), which is the tool announcing that
  scikit-learn is deliberately not a repo dependency. The real problem is narrower and worse — it
  defines `GOOD = 80` on `fit_score` (`:149-152`), draws its pairs from
  `calibrate-match.load_pairs` (`:181-215`), and then scores itself with `average_precision_score`
  against that same `fit_score`-derived label. Training and evaluating on one layer.
  **And the rule as this file stated it was wrong:** § 6 puts *never train* on **L0**, not L1
  (`backend/evals/__main__.py` and § 6 below). L1 is the layer you may train on and must not
  *evaluate* on. Figures from this tool are unreproducible for the dependency reason anyway.
- **Stale `file:line` citations throughout — 305 as of 2026-08-03, and there is a checker now.**
  `tools/audit-citations.py` counts them and `tests/test_citations.py` fails the suite on a *new*
  one; the existing ones are accepted in `config/citation-baseline.json` with their reason.
  **Run the tool for the number rather than quoting this line** — it has already been stated as
  309, 308, 306 and 305 in four consecutive commits, and only the tool is current. The original
  estimate here ("four in `schema.py`/`extract.py`/`state.py`, four in
  `config/pursuit-criteria.json`") was low by two orders of magnitude, and the drift is not
  uniform — `evals/labels.py`'s self-citations run +266 (`_item_key()` cited `:1329`, actually
  `:1595`) but `model_vs_human()`'s `no_consensus` runs +338, so no single offset fixes them.
  Eight `migrate_pursuit_profile.py` citations pointing past a 333-line file were fixed
  2026-08-03. **The class the checker cannot see is the dangerous one**, and the tree's one known
  instance was closed 2026-08-03: `extract.py:404` cited `lib/text.py:119` for a
  `re.sub(r"<[^>]+>", " ", text)` that had been folded into `_TAG` — the line resolved and the
  claim was false. The comment now names `_TAG` (`backend/extract.py:399-423`;
  `lib/text.py:152-155`) and the worked example lives at `git show 20ee7d0:backend/extract.py`,
  because keeping a false comment in the tree to demonstrate a limitation is paying for the lesson
  twice.
- ~~Dead imports~~ **Fixed 2026-08-03, and one of the four was not dead.** `relevance` in
  `score.py`, `urllib.request` in `ingest/hn-hiring.py` and `ingest/google-apify.py` were removed
  (`urllib.error` on the following line of each is live — do not remove that). **`schema` in
  `webapp/search.py` stays:** nothing in the module references `schema.`, but
  `webapp/tests/test_search_signal.py:97` asserts `search.schema is schema`, pinning that the
  route and the nightly fold read one `SEARCH_MIN_WATCHERS` rather than two that can drift. It is
  now commented as such. A grep-only audit calls this dead; the suite does not.

### (b) Needs the owner — a decision, an account, a device, or a person

1. **Is `api/` being retired or kept warm?** `jobs-api.service:6-9` says deprecated and says to
   delete the unit and its cloudflared ingress rule *together* — an ingress hostname with nothing
   behind it is a 502 that reads as an outage. Meanwhile tranche work landed in it on 2026-08-02.
   Opposite signals; only you can settle it. **This also decides task 24 and the Contribute surface.**
2. **Deployment is entirely owner-side.** A Cloudflare account, a domain, and one
   `cloudflared tunnel create` to fill `deploy/cloudflared/config.yml`'s placeholders; a
   `cloudflared` binary (`/usr/local/bin/cloudflared` does not exist); install the **eleven absent
   units** — `deploy/systemd/` holds 14 and 3 are installed, so the "twelve" here was off by one.
   Re-verified 2026-08-03: the three live at `~/.config/systemd/user/` (**user** units, not
   `/etc/systemd/system/`, where none of them appear), are dated 2026-07-26, are regular-file
   copies rather than symlinks — unlike the `garmin-*` units beside them, which *are* symlinked —
   and **differ from the repo copies today**, so editing `deploy/systemd/` changes nothing that
   runs.
3. **`~/.config/jobs-backup.env` does not exist**, so backups would run local-disk-only, tolerated
   silently by the `-` prefix. No verified restore has been performed.
4. **The volume alarm is half wired, and the missing half is the half that fires.** Re-checked
   2026-08-03: history is now accruing — `backend/.run-volumes.jsonl` exists and
   `tools/volume-check.py` **exits 0**, reporting `9 source(s) evaluated, 1 run(s) in history` with
   every source `skip … (insufficient history)`. It no longer exits 1 with `no_history`. What is
   still missing is the reader: `jobs-volume-check.timer` is not installed, so nothing runs the
   check. `systemctl --user list-unit-files` shows only `jobs-failure@.service`,
   `jobs-ingest.service` and `jobs-ingest.timer`. One run is also not enough history to compare
   against — that accrues on its own; the timer will not.
5. **Which of the two committed n=115 selfchecks is the floor of record?** See § 6. Neither JSON
   carries a supersession marker.
6. **Name the tracks.** `config/pursuit-persona.json`'s `_no_buckets_comment` records that
   `score.TRACKS`' five names "do not describe this population" and assigns naming to task 30. It
   blocks the display half independently of the experiment.
7. **Task 29 round 2** (~2026-08-09) and ≥100 distinct postings from ≥5 labellers. Today: 2
   labellers, 36 postings, 10 overlap. Every model-vs-human figure is denominated by a ceiling
   computed from those 10.
8. **The phone test** — a device, plus a Google redirect-URI registration that is not in this repo.
9. **Is the duplication between `ingest/google-*.py` and `serp/providers/*` temporary or
   permanent?** The code supports both readings and they imply different fixes.
10. **Registrations that block work:** Adzuna and USAJobs (task 15), Firecrawl (task 20).
11. **Is `SESSION_COOKIE_SECURE` true in the deployed `.env`?** If false anywhere but local plain
    HTTP, the session cookie — the client's only credential — travels in the clear.
12. **Has any contributor API key ever been minted and handed to a person?** `api_keys` is empty
    here; a key minted elsewhere would not show up.

## 5. Landmines

The ones that cost something. `.claude/CLAUDE.md` owns the short list; this is the rest.

- **Postgres word boundary is `\y`, not `\b`.** In Postgres `\b` is BACKSPACE, so the pattern
  silently matches nothing. Run `backend/tools/relevance-report.py --dead` after any pattern edit —
  **but pass `--profile pursuit`**: the default resolves to `tech`, which the tool itself reports as
  INACTIVE, so the default invocation reports on a projection
  (`backend/tools/relevance-report.py:146,163-166`).
- **Workday `limit` cannot exceed 20.** Ask for 100 and it returns an empty array with no error.
- **A throttled page is not the end of a list.** Reconcile against the `total` the API returned.
  Workday's own tolerance means a deficit of up to 19 postings is never fatal, reported as a
  printed ALERT rather than an exit code (`backend/ingest/workday.py:521-533`).
- **Silence is this system's failure mode.** Exhausted keys, revoked keys, blocked scrapers and
  changed endpoints all return zero rows rather than raising. Alert on volume, not errors.
- **CORS `allow_methods` is the literal list `['GET','POST','OPTIONS']`.** Any DELETE route added
  later fails at preflight with no message anyone sees (`backend/webapp/app.py:84`).
- **SQL fragments are spliced ahead of the WHERE clause and their parameters must lead the params
  list.** Getting the order wrong does not raise — it compares a user id against a profile name,
  matches nothing, and reports every Builder as having no state
  (`backend/webapp/jobs.py:303-324`; `search.py:94-102`).
- **`api/query_claims.py:494` defines a function named `upsert` returning an `UpsertResult`**, whose
  docstring says "It still unpacks to (new, updated, unchanged)". It is safe today, but it is the
  exact shape of the historical defect and a `grep` audit hits it first.
- **`daily_budget` in `config/google-queries.json` is enforced per request, not per day.** What
  actually limits a slug to one fetch a day is `MIN_HOURS_BETWEEN_RUNS=20`
  (`backend/api/query_claims.py:441-452`).
- **`config/criteria.json`'s `unknown_penalty` block is inert.** `jobs.profiles.criteria_json` is
  authoritative; editing the file changes nothing observable until `migrate_profiles.py --apply`.
- **Ten migrations exist and nothing records which have been applied.** No `schema_migrations`
  table, no runner.
- **`ensure_schema` creates 14 tables**, not the 13 its own docstring and `lib/dbconn.py` claim.

**Closed, contrary to long-standing belief:** the bare-`upsert()` three-tuple unpack. All nine
ingest writes use `upsert_checked` and seven read `.errors`; `grep -rn '= upsert(' backend/ingest/`
returns nothing. Closed in `e353e3e`. Two tests pin it by reading source text.

## 6. Figures, with their instruments

**A percentage without its metric name is a rumour with a decimal point.** The selfcheck computes
three distinct metrics over the same run; `--repeat 3` is the *run*, not a metric.

| value | subject | metric | source |
|---|---|---|---|
| 85.2% [77.6–90.6] | `seniority_level` | `agree2` | `evals/fixtures/results/selfcheck-n120-2026-07-28.json` |
| 94.8% [89.1–97.6] | `ai_involvement` | `agree2` | same run |
| 90.7% | `ai_involvement` | `pairwise` | same run |
| 87.0% | `ai_involvement` | `unanimous` | same run |

All four reproduce exactly from that file's `.fields.<field>.overall.agree2`, n_comparable 115.

**A second n=115 run on the same frozen corpus and the same model, five days later, disagrees
substantially** (`evals/fixtures/results/selfcheck-n120-2026-08-02.json`): `ai_involvement` 0.9043 vs 0.9478,
`seniority_level` 0.8957 vs 0.8522, `remote_policy` 0.9130 vs 0.8174, `tech_stack` 0.7739 vs
0.7043. Wilson intervals overlap heavily. Candidate explanations that cannot be separated from
code: a silent provider-side revision behind the `deepseek-v4-flash` label, a prompt change in
`extract.py` between the dates, or sampling noise.

**OQ-9, decided 2026-08-03: quote both runs as a range, per field, and tune against the lower
bound.** Neither file supersedes the other — both carry a `_comment` recording this. The spread
itself is the finding: a model moving up to 9.6 points at temperature 0 across five days has a
stability problem, and collapsing that to one number would delete the most important thing this
pair of runs showed. Acting figures (the floor of the two, `agree2`, n=115):

| field | floor | source run |
|---|---|---|
| `seniority_level` | 85.2% [77.6–90.6] | 2026-07-28 |
| `ai_involvement` | 90.4% | 2026-08-02 |
| `remote_policy` | 81.7% | 2026-07-28 |
| `tech_stack` | 70.4% | 2026-07-28 |

The newer run is still the only one carrying a `role_track` floor.

**`~85% greenhouse/ashby` has no instrument anywhere in the tree.** It is restated in ten places,
every one citing `CLAUDE.md`, and nothing computes it. The *rule* it supports — never select an
eval corpus with `ORDER BY first_seen DESC` — is sound and independently motivated; the number is
not evidence.

**The inter-annotator ceiling is thin.** 2 labellers, 36 distinct postings, 10 overlap, against a
printed threshold of ≥100 from ≥5 (`backend/evals/__main__.py:455-456`). The refusal machinery
(`Uninterpretable`) is doing more load-bearing work than the number.

**Never evaluate on the layer you trained on.** L0 human labels (never train), L1 `fit_score`,
L2 `job_events`. Report average precision as the measurement, precision@20 as the objective — a
count of twenty cannot resolve the differences being decided on.

## 7. What the deleted documents claimed that the code does not support

168 disagreements were found; **none was adversarially verified**, so treat each as a lead with a
citation rather than a finding. 141 were against files now deleted and are listed in
`orientation-2026-08-02/disagreements-index.txt`. The 27 against files that survive are in
`orientation-2026-08-02/claudemd-disagreements.txt`; the substantive ones have been corrected in
`.claude/CLAUDE.md` and the root READMEs in this commit.

The pattern worth keeping: **every one of the high-severity findings was a document describing a
state of the world that had since changed** — `frontend/` called empty, seven sources called eight,
nine steps called fourteen, thirteen tables called fourteen, one migration called ten. Not one was
a document that had never been true. The documents were accurate when written and nothing brought
them forward. That is the argument for this file being short, and for the registers below living
next to the code instead of in prose.

---
kind: contract
written: 2026-08-03
generator: none
---

# CLAUDE.md

Context for Claude Code sessions in this repo. Read before starting any task.

**`docs/STATE-OF-THE-SYSTEM.md` is the other file worth reading first.** It is the only surviving
document — on 2026-08-02, 137 files and 42,777 lines of Markdown under `docs/` were deleted in one
commit, after an audit found 168 places they contradicted the code. All of it is in git behind the
tag `refactor-freeze-2026-08-02`; nothing was destroyed. This file holds the rules; that one holds
the state, the landmines and the open questions.

**Path-scoped landmines live in `.claude/rules/`, not here** — SQL/`\y` (`sql.md`), ingest failure
modes (`ingest.md`), eval discipline (`measurement.md`), config JSON conventions (`config.md`), the
two HTTP services' CORS and `upsert` traps (`services.md`), the frontend's no-build-step constraint
(`frontend.md`) — loading only when a session touches a matching path, so this file stays the part
every session pays for. A landmine goes where the session that can act on it loads it.

**What is left to do lives in exactly two files, and between them that is the whole list.**
[`TASKS.md`](../TASKS.md) (`T-`) holds everything a session can do unaided;
[`DEV_TASKS.md`](../DEV_TASKS.md) (`OQ-`) holds everything needing a machine, an account, a device,
other people, or a decision only the owner can take. A decision, once taken, goes to
[`docs/adr/`](../docs/adr/) — one file per decision, frozen on write, never into prose here. Work
tracked in neither file is not tracked.

**What this is:** a job discovery and tracking pipeline, retargeted from one software engineer's job
search to the Pursuit AI-Native cohort — ~30 Builders, entry-level, AI-adjacent roles, all
industries, NYC.

## Commands

Everything resolves relative to `backend/`, never the repo root. `cd backend` first.

**`python3` below means 3.14, and on a Mac it is 3.9 — check before believing an error.** The repo
pins 3.14 in three places (`backend/pyproject.toml:25`, `backend/pyproject.toml:177`,
`.github/workflows/ci.yml:53`) and every command here is written `python3` because on the server
that is what `python3` is. On macOS it is not, by two independent routes: `/usr/bin/python3` is the
3.9 the OS ships, and a `pyenv` whose global is unset falls through to that same 3.9 via its shim.
Homebrew's `python3` **is** 3.14 and loses both races. The failure does not mention versions — it is
`TypeError: unsupported operand type(s) for |` from `backend/lib/timeparse.py:52`, a PEP 604
annotation evaluated at import, and it reads like broken code rather than a wrong interpreter.

**The fix is a venv, not a PATH edit, and Homebrew forces it**: its Python is PEP 668
externally-managed, so `pip install --user psycopg` is refused outright. `backend/.venv` is
therefore a fourth venv beside the three below, holding the same `requirements.txt` — the pipeline
is still one third-party dependency, it is just not reachable from a bare `python3` on every
machine. Where a command below says `python3`, that machine reads `.venv/bin/python`.

```bash
# Tests. No pytest in any interpreter; unittest is stdlib and works.
python3 -m unittest discover -s tests            # whole suite
python3 -m unittest tests.test_match             # one module

# The nightly run, and any step standalone.
python3 run-daily.py                             # 14 steps, in order
python3 ingest/ats.py                            # every ingest script runs alone
DEBUG_PRINT_KEYS=1 python3 ingest/google-serpapi.py   # verbose, convention everywhere

# Evals. Frozen fixtures, replay cache. --no-cache is `run`-only; `selfcheck`
# has the inverse, an opt-in --cache, off by default.
python3 -m evals run --task extract --corpus evals/fixtures/corpus-v1.jsonl --model "$SPEC"
python3 -m evals selfcheck --model "$SPEC" --n 120 --repeat 3
```

**The webapp and the contributor API are separate processes with their own venvs, and their tests
are the second and third suites, not part of the first** — both set
`include-system-site-packages = false`, so system `python3` cannot import either `app.py`:

```bash
cd backend/webapp && .venv/bin/python -m unittest discover -s tests
cd backend/api    && .venv/bin/python -m unittest discover -s tests
```

**Standing a database up from nothing is one command** — the DDL lives in six functions across four
modules (`tools/provision-database.py:181-186`) and nothing else invokes all six. **Read the banner
at the top of the file before running it against anything populated**: step 3's fallback DROPs a
view and takes every GRANT with it (`backend/schema.py:1313`, fixed by `T-13`, re-grant not
re-decision — see
[`docs/adr/0004`](../docs/adr/0004-provision-database-issues-no-grants.md)).

```bash
cd backend
python3 tools/provision-database.py                 # all six, in the one order that works
python3 tools/provision-database.py --verify-only   # report, change nothing
.venv-dev/bin/ruff check . --statistics    # dev-only linter; run it for the number, don't quote one
.venv-dev/bin/mypy                          # dev-only, config-driven, scoped to lib/, schema.py, score_job()
```

**There is CI, and a green run is the claim — a number in prose is a rumour.**
`.github/workflows/ci.yml`, on push/PR to `main`: **suites** (all three, against a provisioned
`postgres:16` service, asserting **nothing skipped**); **checkers** (citations, both frontend);
**lint** (`ruff`, `continue-on-error` until its baseline hits zero); **types** (`mypy`, blocking).
Put the run URL in the commit message.

**What did not change, and must not:** `psycopg[binary]` is the only third-party **runtime**
dependency — every added package is one more thing missing on one of the several unattended
machines this runs on. `ruff`/`mypy` are dev tools, in none of the three `requirements.txt`.
Exception: `tools/learned-ranker-probe.py` (numpy, sklearn) **cannot run on a clean checkout**.

## Layout

**`backend/` holds three deliberately separate processes** — the nightly pipeline at the top level,
`api/` (the contributor work queue — **staying, per `OQ-1`**; credential mechanism decided,
unbuilt, `docs/adr/0006`; **may not start against the deployed database**) and `webapp/` (port 8421).
Each has its own `.env`, venv and Postgres role. `api/`/`webapp/` import nothing from each other and
no pipeline module imports either — but `webapp/` imports the pipeline's `profiles`, `searchnorm`
and `evals.labels`, and `api/` imports `google_jobs`: each a coupling a pipeline change can break
elsewhere.

**`frontend/` is a shipping client** — see `.claude/rules/frontend.md` for the no-build-step
constraint and how to serve it. **Read through the `jobs_app` view, not the `jobs` table**: the base
table is deliberately unfiltered (`ingest/ats.py` pulls entire company boards, so roughly two
thirds of it is roles this pipeline exists to ignore), and the view's four required fields are
deliberately *not* `NOT NULL` constraints — `ingest/builtin-nyc.py` legitimately writes a listing
row first and fills `description_text` later. Enforce completeness at the read edge, not the
column.

## Architecture invariants

**There are three executable stages: `extract.py` → `match.py` → `score.py`.** `relevance.py` is a
pure SQL-fragment builder — no database access, no `main()`, not in the nightly step list. Extract
and score cost LLM calls; match is free arithmetic. **`run-daily.py` runs 14 steps** — any comment
saying nine is stale; runtime output is correct because it uses `len(STEPS)`.

**`job_facts` is shared; scores are per profile.** One extraction per posting, ever. `job_matches`
and `job_scores` are keyed `(job_id, profile)` — the property that makes cost flat in users. Do not
break it. `match_reasons` (per-rule attribution on every row) must survive any ranker change, which
rules out gradient-boosted trees in favour of linear models, deliberately.

**`match_score` orders the list; `fit_score` only annotates it.** Sorting by `fit_score` would put
an LLM call on the critical path for every posting — **LLMs explain, never rank**, and no LLM call
may sit between a user and an ordering. `score_job()` itself is pure: no I/O, unit-testable,
sweepable. Keep it that way. **A deferral is not a failure**, though: an endpoint that never answers
(429, timeout, 5xx) writes nothing and retries next run; only a model that answered unusably gets a
tombstone row (`scoring_model="FAILED:..."`, NULL `fit_score`) — collapsing the two discards
postings nobody ever evaluated.

**Versions are cache keys, with two exceptions you must not "fix".** `job_scores` records
`facts_version`, `persona_sha`, `prompt_version` and `criteria_version` — but `_STALE_ANY` has
exactly **three** arms: `criteria_version` is provenance only, excluded so a weight edit does not
re-score narratives it never changed. Each arm uses `<>`, not `IS DISTINCT FROM`, so pre-existing
NULL rows are not swept into "stale" — **rewriting with `IS DISTINCT FROM` stales the whole
backlog.** There is no `persona_version`, `features_version` or `model_version`.

## Conventions

**Cite `file:line` when explaining a claim about the code.** That is what makes a claim checkable.
`tools/audit-citations.py` checks it in the suite, so a **new** citation naming a file or a line
that does not exist is a red test — it checks only that the path exists and the line is in range,
**and cannot tell you whether the line still says what you claim.** Already-drifted citations are
accepted in `config/citation-baseline.json` rather than swept in one commit — **run the tool for
the count**, do not quote one written here, and never add to that file to silence a finding. Cite a
document deleted on 2026-08-02 as `git show refactor-freeze-2026-08-02:<path>` — allowed
deliberately, not validated, and that tag's tree is rooted at the repo root, not `backend/`.

## Do not

- Do not add a second definition of the Google Jobs record shape (de-duplicated in `0c3ae51`), or
  reimplement relevance matching in Python — one implementation, many callers.
- Do not scrape LinkedIn, or backfill `rank` on existing `job_events` rows — a guessed rank is worse
  than a missing one.
- Do not re-tune on a provisional number or a 20-row eval, or restore `docs/` wholesale — pull the
  one file needed out of the tag and put it where the code that needs it lives.

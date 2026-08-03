---
kind: contract
written: 2026-08-02
generator: none
---

# CLAUDE.md

Context for Claude Code sessions in this repo. Read before starting any task.

**`docs/STATE-OF-THE-SYSTEM.md` is the other file worth reading first.** It is the only surviving
document — on 2026-08-02, 137 files and 42,777 lines of Markdown under `docs/` were deleted in one
commit, after an audit found 168 places they contradicted the code. All of it is in git behind the
tag `refactor-freeze-2026-08-02`; nothing was destroyed. This file holds the rules; that one holds
the state, the landmines and the open questions.

**What is left to do lives in exactly two files, and between them that is the whole list.**
`TASKS.md` owns the prefix `T-` and holds everything a session can do unaided. `DEV_TASKS.md`
owns `OQ-` and holds everything needing a machine, an account, a device, other people, or a
decision only the owner can take. A decision, once taken, goes to `docs/adr/` — not into prose
here. Work tracked in neither file is not tracked.

## What this is

A job discovery and tracking pipeline, retargeted from one software engineer's job search to the
Pursuit AI-Native cohort — ~30 Builders, entry-level, AI-adjacent roles, all industries, NYC.

## Commands

Everything resolves relative to `backend/`, never the repo root. `cd backend` first.

```bash
# Tests. No pytest in any interpreter; unittest is stdlib and works.
python3 -m unittest discover -s tests            # whole suite
python3 -m unittest tests.test_match             # one module
python3 -m unittest tests.test_match.TestName.test_case   # one case

# The nightly run, and any step standalone.
python3 run-daily.py                             # 14 steps, in order
python3 ingest/ats.py                            # every ingest script runs alone
DEBUG_PRINT_KEYS=1 python3 ingest/google-serpapi.py   # verbose, convention everywhere

# After any config/relevance.json edit. Not optional — see the `\y` landmine.
# Pass --profile: the default resolves to `tech`, which is INACTIVE, so the
# default invocation reports on a projection rather than on production.
python3 tools/relevance-report.py --dead --profile pursuit

# Evals. Frozen fixtures, replay cache.
python3 -m evals run --task extract --corpus evals/fixtures/corpus-v1.jsonl --model "$SPEC"
python3 -m evals selfcheck --model "$SPEC" --n 120 --repeat 3
```

`--no-cache` exists only on `evals run`. `evals selfcheck` has the inverse — an opt-in `--cache`,
off by default.

The webapp and the contributor API are separate processes with their own venvs, and **their tests
are the second and third suites, not part of the first**:

```bash
cd backend/webapp && .venv/bin/python -m unittest discover -s tests
cd backend/api    && .venv/bin/python -m unittest discover -s tests
```

Both venvs set `include-system-site-packages = false`, so system `python3` cannot import either
`app.py` — they need `fastapi`, which the top level does not have and is not getting.

**`ruff` is the linter and formatter, as of 2026-08-03.** It is a *development and CI* tool,
installed into a dev venv and configured in `backend/pyproject.toml`; it is deliberately absent
from all three `requirements.txt`. This reverses a recorded decision — the tranche-nine README
said wiring one in was "wrong for this repo regardless of where it came from" — on the reasoning
in `TASK-52-harness.md`: a rule with no check is a suggestion, and the standard implementation of
that is a linter and CI rather than a hand-rolled `audit-*.py` per rule. See `T-1` in `TASKS.md`.

**What did not change, and must not:** `psycopg[binary]` is the pipeline's only third-party
**runtime** dependency and the intent is that it stays that way. These scripts run unattended on
several machines and every added package is another thing that can be missing on one of them. A
dev tool is not a runtime dependency; a linter finding that would be fixed by importing a library
is not a reason to import one. The one exception is
`tools/learned-ranker-probe.py`, which imports numpy and sklearn and therefore **cannot run on a
clean checkout** — treat any figure from it as unreproducible.

## Layout

**`backend/` holds three deliberately separate processes** — the nightly pipeline at the top level,
`api/` (the contributor work queue, expected to be deprecated, and **currently unable to start**)
and `webapp/` (port 8421). Each has its own `.env`, venv and Postgres role.

`api/` and `webapp/` import nothing from each other, and no pipeline module imports either. But the
sharing is wider than `schema.py` and `lib/`: `webapp/` also imports the pipeline's `profiles`,
`searchnorm` and `evals.labels`; `api/` imports `google_jobs`. Each is a coupling a pipeline change
can break in another process.

**`frontend/` is a shipping client.** Plain HTML, one stylesheet, ES modules — **no build step, no
framework, no npm, no `package.json`**, and that is a constraint to keep. Five screens exist and all
five are routed: Today, Job detail, Saved, Search and Onboarding. Not built: Contribute, and the
phone test. Run it with `frontend/serve.py`, which mounts the page on the **webapp's own origin**
(8421) rather than a second dev server, because the client uses `credentials: "same-origin"` with
`BASE = ""` — served from any other host, every request loses the session cookie and returns 401,
which renders as the sign-in screen with no error anywhere.

```bash
cd backend/webapp && .venv/bin/python ../../frontend/serve.py   # then http://localhost:8421/
python3 frontend/verify_fixtures.py    # fixtures still describe the server
node frontend/check_client.mjs         # client still agrees with the fixtures
```

**Read through the `jobs_app` view, not the `jobs` table.** The base table is deliberately
unfiltered — `ingest/ats.py` pulls entire company boards, so roughly two thirds of it is roles this
pipeline exists to ignore. The view guarantees the four fields a listing cannot render without, and
those are deliberately *not* `NOT NULL` constraints: `ingest/builtin-nyc.py` legitimately writes a
listing row first and fills `description_text` on a later pass. Enforce completeness at the read
edge, not the column.

## Architecture invariants

**There are three executable stages: `extract.py` → `match.py` → `score.py`.** `relevance.py` is a
pure SQL-fragment builder — no database access, no `main()`, not in the nightly step list. Extract
and score cost LLM calls; match is free arithmetic.

**`run-daily.py` runs 14 steps.** Any comment saying nine is stale; runtime output is correct
because it uses `len(STEPS)`.

**`job_facts` is shared; scores are per profile.** One extraction per posting, ever. `job_matches`
and `job_scores` are keyed `(job_id, profile)`. This is the property that makes cost flat in users —
do not break it.

**`match_score` orders the list. `fit_score` only annotates it.** Sorting by `fit_score` would put
an LLM call on the critical path for every posting.

**LLMs explain, never rank.** No LLM call may sit between a user and an ordering.

**`score_job()` is pure.** No I/O. Unit-testable and sweepable. Keep it that way.

**A deferral is not a failure.** The endpoint never answering (429, timeout, 5xx) writes nothing and
retries next run; only a model that answered unusably gets a tombstone row
(`scoring_model="FAILED:..."`, NULL `fit_score`). Collapsing the two would permanently discard
postings nobody ever evaluated.

**Versions are cache keys, with two exceptions you must not "fix".** `job_scores` records
`facts_version`, `persona_sha`, `prompt_version` and `criteria_version` — but `_STALE_ANY` has
exactly **three** arms: `criteria_version` is provenance only, deliberately excluded so a weight
edit does not re-score narratives it never changed. Each arm is guarded by `IS NOT NULL` and uses
`<>`, not `IS DISTINCT FROM`, so the pre-existing rows that are NULL on all four are not swept into
"stale". **Rewriting that predicate with `IS DISTINCT FROM` turns the whole backlog stale, and with
a rescore flag spends a call per row.** There is no `persona_version`, `features_version` or
`model_version`.

**`match_reasons` must survive any ranker change.** Per-rule attribution on every row. This rules
out gradient-boosted trees in favour of linear models, deliberately.

## Landmines

**Postgres word boundary is `\y`, not `\b`.** In Postgres `\b` is BACKSPACE, so a `\b` pattern
silently matches nothing and quietly demotes everything it was meant to catch.

**Workday `limit` cannot exceed 20.** Ask for 100 and it returns an empty array with no error,
identical to "no more results."

**A throttled page is not the end of a list.** Reconcile collected counts against the `total` the
API returned. One published account lost 1,960 of 2,000 jobs to this.

**Silence is this system's failure mode.** Exhausted keys, revoked keys, blocked scrapers and
changed endpoints all return zero rows rather than raising. Alert on volume, not errors.

**Use `upsert_checked`, and read `.errors`.** `UpsertResult.__iter__` yields three values, so a bare
three-tuple unpack silently discards errors. Every current call site is correct — this is a rule to
preserve, not a defect to go fix.

**`deepseek-v4-flash` is the production model and it does not agree with itself at temperature 0.**
**85.2% [77.6–90.6] on `seniority_level`, 94.8% [89.1–97.6] on `ai_involvement`**, n=115, both
**`agree2`**. **Name the metric whenever you quote one of these** — the same run yields `agree2`
94.8%, `pairwise` 90.7% and `unanimous` 87.0% for `ai_involvement`, all correct and all in
circulation; `--repeat 3` is the *run*, not the metric. A second n=115 run on the same frozen corpus
five days later disagrees by up to 9.6 points, and **which is the floor of record is an open owner
decision** — `docs/STATE-OF-THE-SYSTEM.md` § 6 has both, with their file paths.

`docs/STATE-OF-THE-SYSTEM.md` § 5 carries the rest, several of which will bite before these do.

## Measurement discipline

**Never evaluate on the layer you trained on.** L0 is human labels (never train), L1 is `fit_score`,
L2 is `job_events`.

**Never select an eval corpus with `ORDER BY first_seen DESC`** — it measures the easy sources. Use
the frozen fixtures in `backend/evals/fixtures/`. (`tools/compare-models.py` and
`tools/claude-bench.py` still do this against production; figures from either are not reproducible.)

**Report average precision as the measurement, precision@20 as the objective.** A count of twenty
cannot resolve the differences being decided on.

**Pin eval sets by sorted `job_id`.** Never train on them, never recycle them.

**Read the `Ran N tests` line, not a count written down anywhere** — including here. Counts in prose
go stale silently, and that is most of why `docs/` was deleted.

## Conventions

**`_comment` fields in config JSON are load-bearing documentation.** They record where numbers came
from and — more valuably — what was rejected and why. Every new config gets them, in the existing
style. Read the ones in `config/relevance.json` before writing new ones. **With `docs/` gone these
are the primary written rationale in the repo**; treat deleting one as deleting a decision record.

**Cite `file:line` when explaining a claim about the code.** That is what makes a claim checkable.
`tools/audit-citations.py` now checks it, and `tests/test_citations.py` runs it in the suite, so a
**new** citation naming a file or a line that does not exist is a red test. It checks two things
and only two: the path exists, and the line is within the file. It declines to judge a third —
a **git-ignored** path, whose presence depends on whether the pipeline has been run here rather
than on the tree. **It cannot tell you whether the line still says what you claim.** That class is
real; the one known instance was closed 2026-08-03, which is not evidence there are no others.
**This file is in scope** — it was exempt until 2026-08-03, so a bad `file:line` added here is now
a red test like anywhere else.

The already-drifted citations are accepted in `config/citation-baseline.json` rather than swept in
one commit. **Run `python3 tools/audit-citations.py` for the count** — it has been written down as
309, 308, 306 and 305 in four consecutive commits, which is the same way every count in prose in
this repo has gone wrong. That file is meant to shrink; do not add to it to silence a finding. If
what you are citing is one of the 137 documents deleted on 2026-08-02, cite it as
`git show refactor-freeze-2026-08-02:<path>` — the checker allows that form deliberately, and does
not validate it, so get the path right.

## Do not

- Do not add a second definition of the Google Jobs record shape. Deliberately de-duplicated in
  `0c3ae51`.
- Do not reimplement relevance matching in Python. One implementation, many callers.
- Do not scrape LinkedIn.
- Do not backfill `rank` on existing `job_events` rows. A guessed rank is worse than a missing one.
- Do not re-tune on a provisional number, or on a 20-row eval.
- Do not restore `docs/` wholesale. Pull the one file you need out of the tag and put it where the
  code that needs it lives.

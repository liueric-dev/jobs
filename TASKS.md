---
kind: rolling
written: 2026-08-03
generator: none
subject: .
budget: 400
---

# Session tasks — everything a session can do without the owner

**This file owns the prefix `T-`.** One allocator. **The next free number is `T-19`.** Numbers are
never reused and never renumbered, so a citation to a closed row keeps resolving.

**It is the other half of [`DEV_TASKS.md`](DEV_TASKS.md)**, which owns `OQ-` and holds everything
that needs a machine, an account, a device, other people, or a decision only the owner can take.
Nothing here needs any of those. **Between the two files, that is meant to be the whole list** —
if work exists in neither, it is not tracked, and that is the condition this file exists to end.

This replaces `git show refactor-freeze-2026-08-02:docs/tasks/refactor/tranche_nine/54-replan-the-product.md`.
54 was a task to *write* a plan against `docs/STATE-OF-THE-SYSTEM.md`; this is the plan. Its
central requirement survives verbatim: **every row carries machine-checkable acceptance criteria —
the exact command and what it should print.** Its second requirement survives too, and matters
more here: *if this list turns out to be short, that is a finding and not a failure.*

## The ceiling

**Work discovered while executing a row becomes a row here, an `OQ-` row, or an ADR. It never
becomes a sub-tranche or a new document.** The failure mode this whole effort exists to correct is
a meta-project that grows: tasks 36–47 were twelve consecutive tasks of documentation
infrastructure, every one green, and they produced no product movement. The ceiling only works
when it is enforced at the inconvenient moment.

## The goal these rows serve

Standard tooling instead of hand-rolled convention. **The bound:** `ruff`, CI and type checking
are development tools. **No new runtime dependency enters `backend/requirements.txt`,
`backend/api/requirements.txt` or `backend/webapp/requirements.txt`.** The pipeline runs unattended
on several machines and every added package is another thing that can be missing on one of them;
that reasoning is unchanged and `T-1` has a grep proving it holds.

## Order

`T-1` and `T-2` first — they are the enforcement layer every other row leans on, and they are what
makes the next session's claims checkable without hand-transcription. `T-11` and `T-13` are the
two rows with a live correctness consequence. Everything else is schedulable in any order.

---

## Toolchain

### T-1 — `ruff`, configured and baselined

`.claude/CLAUDE.md` said "There is no linter and no formatter" and
`git show refactor-freeze-2026-08-02:docs/tasks/refactor/tranche_nine/README.md` said wiring one in
was "wrong for this repo regardless of where it came from." **Reversed 2026-08-03 by owner
decision, scoped to dev tooling**, on the reasoning in [`TASK-52-harness.md`](TASK-52-harness.md):
CI and a linter are the standard answer to *what is guaranteed to happen*, and the repo was
answering that row with prose plus per-rule Python checkers, two of which were deleted along with
their subject.

New `backend/pyproject.toml` carrying `[tool.ruff]` only — no build backend, no packaging, no
project metadata, because nothing here is installed as a package. Install into a dev venv that is
none of the three runtime venvs.

**Land against a recorded baseline, not a mass reformat.** A large unreviewable diff is the exact
move that produced the documents this repo just deleted. Fix by rule, one commit per rule.

```bash
cd backend && .venv-dev/bin/ruff check . --statistics    # record this output; it is the baseline
grep -rn "ruff" requirements.txt api/requirements.txt webapp/requirements.txt   # must print nothing
```

**Done when:** `pyproject.toml` exists with `[tool.ruff]`, the baseline is recorded in the commit
message, the grep is empty, and all three suites still print `OK`.

---

### T-2 — CI on `liueric-dev/jobs`

There is a live remote and no CI and no git hooks; `.git/hooks` holds only samples. Every result
this repo relies on is verified by hand and transcribed into a commit message, which is how the
citation count got written as 309, 308, 306 and 305 in four consecutive commits and the suite
count four different ways in two days.

`.github/workflows/ci.yml` runs, on push and PR: the three suites, `tools/audit-citations.py`,
`frontend/verify_fixtures.py`, `node frontend/check_client.mjs`, and (after `T-1`) `ruff check`.
The DB-gated modules need a Postgres service container — twelve backend modules gate on
`evals/scratchdb.available()` and all twelve currently run locally, so a CI job without Postgres
would silently drop them and report green on less.

**Done when:** a green run exists on the remote, its URL is in the commit that adds the workflow,
and the run's `Ran N tests` lines match a local run. **If the suite counts differ, CI is wrong or
local is wrong and that is the first thing this row bought.**

---

### T-3 — Pin the three `requirements.txt`

All three carry `>=` floors and there is no lockfile. The stated reason for the stdlib rule is that
the pipeline runs unattended on several machines; unpinned floors undercut exactly that. Pin to
`==` with the floor and its rationale preserved in the existing comment headers — those headers are
`_comment`-style decision records and deleting one is deleting a decision.

**Done when:** no `>=` remains in any of the three files, every pin has the installed version it
was taken from, and all three suites plus both frontend checkers pass against the pinned set.

---

### T-4 — ADRs at `docs/adr/`, the successor to `DECISIONS.md`

`DECISIONS.md` was append-only rationale that the tranche README called *"the single most valuable
file in the repo"* and forbade rewriting; `5046f98` deleted it anyway, and nothing took its slot.
Rationale now lives only in commit messages — which in this repo are unusually long and load-bearing
precisely because they are improvising an ADR.

A new `docs/adr/`, one decision per file, named `NNNN-short-title` with a four-digit serial, frozen
on write, standard format: context · decision · consequences. Seed it with the decisions already
taken and currently recorded nowhere:
the linter reversal (`T-1`), `51`'s delete-instead-of-`git mv` deviation, and whatever Layer 3 of
`TASK-52-harness.md` settles on.

**Done when:** `docs/adr/` holds at least those three, each under 60 lines, and `.claude/CLAUDE.md`
names it as where a decision goes.

---

### T-10 — A migration runner and a `schema_migrations` table

`backend/migrations/` holds ten scripts and **nothing records which have been applied** — no table,
no runner (`docs/STATE-OF-THE-SYSTEM.md` § 5). On any box but this one, the only way to know is to
inspect the schema and infer. Stdlib only; no Alembic, which would be a runtime dependency for a
problem a table and a loop solve.

**Done when:** a new runner under `backend/migrations/` reports, on `--status`, all ten as applied
or not-applied; running it twice applies nothing the second time; and the existing ten scripts are
registered without being rewritten.

---

## Harness

`T-5` … `T-9` are the layers of [`TASK-52-harness.md`](TASK-52-harness.md), listed here so they are
schedulable. That file carries the argument, the ordering constraint and the definition of done;
do not restate it here.

| row | layer | one line |
|---|---|---|
| `T-5` | 1 — what a session knows | `.claude/CLAUDE.md` under 150 lines; five path-scoped files under `.claude/rules/` |
| `T-6` | 2 — who does the work | `plan-verifier` and `artifact-reviewer`, read-only, each invoked once on real work |
| `T-7` | 4 — what is guaranteed | `PostToolUse` hook running `tools/audit-citations.py` on the touched path |
| `T-8` | 5 — what travels | `~/.claude/CLAUDE.md`: scope discipline, verify-before-claiming, never echo credentials |
| `T-9` | 5 — what travels | `~/.claude/skills/whatsnew/` — **task 53's Part B, never built.** Run once, first report committed |

---

## App code

Every row below is already in `docs/STATE-OF-THE-SYSTEM.md` § 4a. What they gain here is acceptance
criteria. **§ 0 of that file warns that nothing in it was adversarially verified**, so re-derive
each against the tree before working it — `47dd212` is the worked example of what happens otherwise.

### T-11 — The seven silent `except Exception` sites

Silence is this system's stated failure mode, and these seven swallow an exception into a `pass` or
a falsy return with nothing logged: `backend/evals/record_cassettes.py:591`,
`backend/evals/scratchdb.py:99`, `backend/lib/ids.py:119`, `backend/tools/jsonld-probe.py:312`,
`:1341`, `:1352`, `backend/tools/verify-date-filter.py:86`.

`scratchdb.py:99` is the one with a consequence and `docs/STATE-OF-THE-SYSTEM.md` § 2 names it: it
opens a real connection inside the bare handler, so **an unreachable Postgres and a genuine driver
bug both read as a skip.** Twelve modules gate on it. That one gets a distinguishable signal, not
just a log line.

**Done when:** each of the seven either logs before returning or narrows to the exception it means;
`scratchdb.available()` distinguishes unreachable from broken; all three suites print `OK`.

---

### T-12 — `logging` on the pipeline stages' failure paths

1065 lines call `print()` across the 105 non-test modules; 5 of all 171 import `logging`.
**This is not a wholesale conversion and a row proposing one should be rejected.** The printed
output is load-bearing — `DEBUG_PRINT_KEYS=1`
is a convention across every ingest script, and `tools/volume-check.py` reads the run history the
nightly writes. Converting it blind breaks the one alarm this system has.

Scope: the failure and deferral paths of `extract.py`, `match.py`, `score.py` and `run-daily.py`
only. Stdlib `logging`, stderr, format decided once in `lib/`. Summary lines stay on stdout.

**Done when:** a forced failure in each of the four produces a structured stderr record;
`python3 tools/volume-check.py` still parses the run history; the nightly summary lines are
byte-identical to before on a successful run.

---

### T-13 — `ensure_app_view`'s DROP fallback destroys GRANTs

A column reorder raises `InvalidTableDefinition`, the handler DROPs the view, and `DROP VIEW` takes
every GRANT with it — with no re-grant anywhere in the repo. It surfaces on the *next* nightly run
as the webapp refusing to start (`backend/schema.py:1215-1223`). `OQ-7` is the recorded instance of
this class costing a day of the whole webapp being down while the row read as a nicety.

**Done when:** the fallback re-grants, or refuses and says what to run; a test creates the view,
grants, forces the reorder path, and asserts the grant survives.

---

### T-14 — Two tools still select their corpus from production by recency

`backend/tools/compare-models.py:84` and `backend/tools/claude-bench.py:113` both use
`ORDER BY j.first_seen DESC` against production — the exact pattern `backend/evals/` exists to
replace, and the one thing the measurement rules name as never acceptable, because it measures the
easy sources. Any figure either has produced is not reproducible.

**Done when:** both read a frozen fixture from `backend/evals/fixtures/`, or both are deleted with
the reason recorded. Deleting them is a real answer — check whether `evals run` already covers what
they do before rebuilding.

---

### T-15 — `learned-ranker-probe.py` trains and evaluates on the same layer

It defines `GOOD = 80` on `fit_score` (`backend/tools/learned-ranker-probe.py:149-152`), then scores
itself with `average_precision_score` against that same `fit_score`-derived label. L1 is the layer
you may train on and must not evaluate on. It also cannot run on a clean checkout — numpy and
sklearn are deliberately absent — so its figures are unreproducible twice over.

**Done when:** it evaluates against L0 human labels, or it is deleted, or its docstring states in
its output that its numbers are not evidence. Any of the three; not silence.

---

### T-16 — f-string SQL identifiers

Roughly 25 non-test sites splice identifiers by f-string — `backend/schema.py`,
`backend/lib/dbconn.py:171`, `backend/migrations/*`. **These interpolate module-level constants,
not user input.** Nobody should read this row as an unpatched injection hole, and nobody should
close it by claiming they fixed one. The reason to touch them is that `T-1`'s linter flags every one
and a suppression that carries no reason is worse than the splice.

**Done when:** each site either uses `psycopg.sql.Identifier` or carries a `# noqa` naming the
constant it splices; `ruff check` is clean on the rule; the suites print `OK`.

---

### T-17 — Gradual typing on the seams only

One of 171 modules imports `typing`. **Do not type the tree.** Type the boundaries where a wrong
shape travels furthest: `backend/lib/`, `backend/schema.py`'s public functions, and `score_job()` —
which is pure and unit-testable and is the one function the ranking rests on.

**Done when:** a type checker runs in CI over exactly that subset and is clean, and the config makes
clear it is a subset by design rather than an unfinished sweep.

---

### T-18 — Shrink the citation baseline

`backend/config/citation-baseline.json` accepts **305 pre-existing unresolvable citations, 0 new**
as of 2026-08-03 (`cd backend && python3 tools/audit-citations.py`). **Run the tool for the number;
do not quote this line** — it has already been written four different ways in four commits, which
is the failure this row is a small piece of undoing. The file is meant to shrink and must never be
added to in order to silence a finding.

The drift is not uniform — `evals/labels.py` self-citations run +266 in one place and +338 in
another — so no single offset fixes them. Work them by owning file, a few per commit.

**Done when:** the count is lower than when the commit started and the tool still reports `0 new`.
There is no target; there is a direction.

---

## Closed — kept so citations resolve

*(none yet)*

---
kind: rolling
written: 2026-08-03
generator: none
subject: .
budget: 400
---

# Session tasks — everything a session can do without the owner

**This file owns the prefix `T-`.** One allocator. **The next free number is `T-21`.** Numbers are
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

**`T-1` and `T-2` are closed, and they were the reason for the ordering** — the enforcement layer
every other row leans on, and what makes a session's claims checkable without hand-transcription.
`T-4` closed with them. Everything below now runs against CI rather than against a hand-transcribed
count.

**`T-11` and `T-13` were the two rows with a live correctness consequence and are closed, 2026-08-03,
alongside `T-20`** (a live migration, not toolchain debt, but also closed the same day — see its own
row). Everything remaining below is schedulable in any order.

**None of these rows is the critical path.** [`DEV_TASKS.md`](DEV_TASKS.md)'s `OQ-3` is — the
scoring redesign completed 2026-07-28 and has never been validated, and every row here improves a
system nobody has confirmed works. It needs people, so no session can start it.

---

## Toolchain

### ~~T-1~~ — `ruff`, configured and baselined

**Closed 2026-08-03** in `56ce823`. `backend/pyproject.toml` carries `[tool.ruff]` and nothing else,
the baseline is **1076** and recorded in that commit, the grep is empty and CI enforces it, and all
three suites print `OK`. **Run the tool for the number; do not quote the one in this paragraph.**
The reasoning is now an ADR: [`docs/adr/0001-ruff-as-a-dev-only-linter.md`](docs/adr/0001-ruff-as-a-dev-only-linter.md).

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

### ~~T-2~~ — CI on `liueric-dev/jobs`

**Closed 2026-08-03.** Green run: `https://github.com/liueric-dev/jobs/actions/runs/30818425894`.
Its three `Ran N tests` lines are **1428 / 352 / 117**, matching a local run exactly — which is the
clause that mattered, because a CI job reporting green on *less* was the specific failure this row
was built to catch.

**One clause was met across three commits rather than one, and that is worth recording rather than
rounding off.** The row asked for the green run's URL to be in "the commit that adds the workflow."
The workflow was added in `56ce823`; its first run was **red** (`720da46`), and the green run
arrived two commits later in `b89c377`. Nobody could have written a green URL into the adding
commit, because the workflow's whole value was that it failed first. The URL above is the answer.

**What it bought by being red:** a database entry point that did not exist, a test-isolation
defect, and the answer to a question nobody had asked — see `T-19`.

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

### ~~T-3~~ — Pin the three `requirements.txt`

**Closed 2026-08-03.** All three now pin `==` at the version already installed in the interpreter
each file governs — the pipeline's system `python3`, `api/.venv`, `webapp/.venv` — instead of a
floor: `psycopg[binary]==3.3.4` in `backend/requirements.txt`; `fastapi==0.140.0`,
`uvicorn[standard]==0.51.0`, `psycopg[binary]==3.3.4`, `pydantic==2.13.4` in
`backend/api/requirements.txt`; the same four plus `httpx==0.28.1` in
`backend/webapp/requirements.txt`. Every existing comment header is untouched — only the
specifier changed.

`.github/workflows/ci.yml:53,111,142` install fresh via `pip install -r` on Python 3.14 with no
lockfile and no cache carried between runs, so pinning to versions already validated locally is
the same environment CI installs on a clean runner, not a departure from it.

`grep -rn ">=" requirements.txt api/requirements.txt webapp/requirements.txt` is empty. All three
suites still print `OK` at the same counts recorded at `f0c3e52`: 1433 / 354 / 117. Both frontend
checkers still pass: `verify_fixtures.py` and `node check_client.mjs` (57 checks, 0 failed).

---

### ~~T-4~~ — ADRs at `docs/adr/`, the successor to `DECISIONS.md`

**Closed 2026-08-03.** `docs/adr/` holds four seed decisions and a README, each under 60 lines, and
`.claude/CLAUDE.md` names it as where a decision goes — a clause that had been *written but not
true* since `56ce823`, because the directory it pointed at did not exist.

`DECISIONS.md` was append-only rationale that the tranche README called *"the single most valuable
file in the repo"* and forbade rewriting; `5046f98` deleted it anyway, and nothing took its slot.
Rationale then lived only in commit messages — which in this repo are unusually long and
load-bearing precisely because they were improvising an ADR each time.

Seeded with the decisions that were taken and recorded nowhere else: the linter reversal
(`0001`, from `T-1`), `51`'s delete-instead-of-`git mv` deviation (`0002`), Layer 3 of
`TASK-52-harness.md` — **which resolves as a recorded deferral, not a build** (`0003`) — and
`provision-database.py`'s deliberate refusal to issue GRANTs (`0004`, from `T-19`).

**Two decisions were deliberately left where they are** and `docs/adr/README.md` says why: the
isort `known-first-party` entry and the non-blocking CI lint step are each argued beside the
setting they govern, and an ADR that only restates a config comment creates a second copy to keep
in sync. `_comment` fields in `config/*.json` stay put for the same reason.

**The rule that decides whether this directory survives**, and it is in the README rather than
here: *an ADR records why, not what the code does today.* Every one of the 137 deleted documents
described a state of the world that then changed, and not one had been false when written.

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

### ~~T-11~~ — The seven silent `except Exception` sites

**Closed 2026-08-03.** `backend/evals/scratchdb.py:85-116`'s `available()` — the one of the seven
with a real consequence, since twelve modules gate on it via `skipUnless` — now splits
`psycopg.OperationalError` (every connection-level failure: refused, timed out, wrong credentials,
confirmed empirically to carry no finer SQLSTATE to split on further) from anything else. The
routine case, no Postgres on this machine, stays exactly as silent as before; a genuine driver bug
now prints one stderr line naming the exception type before returning the same `False`, so it is no
longer indistinguishable from the routine case. The `skipUnless` contract every gated module relies
on is unchanged.

The other six narrow rather than log, per the row's own "logs before returning or narrows to the
exception it means" — narrowing was cleaner because each is an expected decode/parse-fallback case,
not a failure: `backend/lib/ids.py:118` and `backend/tools/verify-date-filter.py:85` (the same
base64/JSON decode logic, duplicated, fixed independently rather than deduplicated — out of scope
here) both narrow to `except ValueError:`, which on this Python is a complete narrowing since
`binascii.Error`, `json.JSONDecodeError` and `UnicodeDecodeError` are all `ValueError` subclasses.
`backend/tools/jsonld-probe.py:1343,1350,1354`'s `_parse_date` narrows all three attempts the same
way, confirmed both `datetime.date.fromisoformat` and `datetime.datetime.fromisoformat` raise only
`ValueError` on this Python. `backend/evals/record_cassettes.py:590` narrows to `except (ValueError,
AttributeError):` and does log — unlike the others this one is positional (`totals[0]` is assumed to
be page 0's total), so a silently dropped parse would misalign the exact evidence this recorder
validates. `backend/tools/jsonld-probe.py:311`'s `allowed()` does real network I/O transitively and
reuses this same file's own pre-existing `self.verbose` debug-print convention rather than a new
one.

Two new tests in `backend/tests/test_scratchdb.py`'s `TestTheGuards` pin `available()`'s two
branches with a mocked `psycopg.connect`. All three suites print `OK` (1433 / 354 / 117, 0
skipped) — pipeline is +4 over the `1429` recorded at `a80f254` (2 here, 2 from T-13 below). `ruff`
went **down** 1085 → 1078: narrowing five blind `except Exception` sites removes their `BLE001`
findings.

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

### ~~T-13~~ — `ensure_app_view`'s DROP fallback destroys GRANTs

**Closed 2026-08-03.** The fallback now re-grants. Two new helpers in `backend/schema.py`:
`_view_grants(conn, view_name)` reads `pg_class.relacl` via `aclexplode` — not
`information_schema.role_table_grants`, which is restricted to rows where the *connecting* role is
grantor or grantee and would silently miss a grant a separate admin role issued, confirmed by live
experiment against this repo's real Postgres. `_regrant(conn, view_name, grants)` reissues each
captured `(grantee, privilege, is_grantable)` via `psycopg.sql.Identifier`/`sql.SQL`, never raw
f-string splicing, since these values come from catalog introspection rather than a module
constant. `PUBLIC` (grantee oid `0`, which casts to `'-'` rather than the string `'PUBLIC'`) is
special-cased as a SQL keyword. `ensure_app_view` (`backend/schema.py:1253`) now calls
`_view_grants` before the `DROP` and `_regrant` after the `CREATE OR REPLACE`, inside the same
`except psycopg.errors.InvalidTableDefinition:` branch.

Confirmed this does not conflict with `docs/adr/0004-provision-database-issues-no-grants.md` — that
ADR is about `provision-database.py` inventing *new* privilege decisions on a bare database, and its
own "Consequences" section names this row by number as the accepted fix for this exact hazard. This
fix only carries a grant forward across the DROP that this function itself causes; no new privilege
decision is made.

New file `backend/tests/test_schema_ensure_app_view.py`, two cases, both run live against this
repo's Postgres: a minimal stand-in view forced down the `InvalidTableDefinition` path by a genuine
column reorder, and the real `jobs_app` view itself, corrupted via rename-and-reselect so the next
`ensure_app_view()` call hits the DROP branch on its own. Both assert a `GRANT ... TO PUBLIC` issued
beforehand is still present afterward.

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

### ~~T-19~~ — This project had never been stood up from nothing, and CI proved it

**Closed 2026-08-03.** `backend/tools/provision-database.py` creates all 23 objects across the five
DDL entry points, and CI runs it before the suites. Verified by reproducing the CI failure against a
throwaway `postgres:16` container, provisioning, and running all three suites green against it —
1428 / 352 / 117. The finding is kept below, because it is worth more than the fix.

**Found by `T-2`'s first run**, which is the whole reason that row exists:
`https://github.com/liueric-dev/jobs/actions/runs/30815935804`. The pipeline suite ran **1428 with
zero skipped** against the Postgres service — matching local exactly, so the DB gating and the
no-skip guard both work. The webapp suite ran **352, the same count as local, and two failed.**

Both failures are in `backend/webapp/tests/test_builder_profiles.py:395-415`. They open a
`web_scratch_schema()` like every test around them, but the code they exercise —
`schema_web.profile_mapping_problems()` and `schema_web.verify_schema()` — reads `public.*` **by
hardcoded name**, so the scratch schema is not what they measure. On a clean database `public` is
empty, `verify_schema()` reports all 23 objects missing, and the assertion for one specific problem
never gets there.

**Do not "fix" `profile_mapping_problems()` to complain about the missing table.** Returning empty
when either table is absent is deliberate and documented at `backend/webapp/schema_web.py:818-820`:
the caller already reports it, and a second complaint derived from the first would bury it. That
was checked before this row was written.

**What it actually said:** every green webapp suite until 2026-08-03 depended on a `public` schema
provisioned by hand on one machine over several months. The two tests were the messenger; the
finding was that the DDL had no single entry point and nobody had noticed, because the one machine
that mattered never needed one.

**How it was closed.** The DDL was spread across five functions in four modules — `ensure_schema`,
`ensure_search_query_schema` and `ensure_app_view` in `backend/schema.py`, `ensure_schema` in
`backend/evals/labels.py`, and `ensure_schema` in `backend/webapp/schema_web.py`. Nothing invoked
all five. `backend/tools/provision-database.py` now does, in the one order that works, and CI runs
it before the suites. **No GRANTs** — `verify_schema()` checks
`has_table_privilege(current_user, ...)`, so a database whose owner is the connecting role has
nothing to issue, and a deployment's three roles are still a by-hand step in
`backend/webapp/README.md`. A tool that hands out privileges is a different tool.

**It carries one hazard, stated at the top of the file.** Step 3 is `schema.ensure_app_view()`,
whose fallback DROPs the view on a column reorder — taking every GRANT with it, with no re-grant
anywhere in the repo (`backend/schema.py:1215-1223`, and `T-13`). Unreachable on an empty database;
real against a populated deployment. `--verify-only` exists for that.

**Two things `T-2` proved by being red rather than green.** The pipeline suite ran 1428 with zero
skipped against the service container on the very first run, so the DB gating and the no-skip guard
both work. And the failure was *reproducible on a laptop* — a throwaway `postgres:16` container
reproduced it exactly, which is what allowed the fix to be verified before it was pushed instead of
by pushing it.

---

### ~~T-20~~ — Apply the Google Jobs id migration, written and dry-run-verified 2026-07-25 and never run

**Closed 2026-08-03.** Preconditions checked immediately before `--apply`: `pgrep -af score.py`
empty (no real process — the only match was the invoking shell echoing its own command text, not a
hit), and a fresh backup taken (`docker exec nyc-events-postgres pg_dump -U jobs_pipeline -d jobs |
gzip > ~/backups/pre-googleid-20260803.sql.gz`, ~36MB). The dry run immediately before `--apply`
matched this row's own recorded numbers exactly — no drift in the 9 days since they were last
checked: 1344 rows, 1180 re-key-only, 24 merge groups, 576 scores on affected rows, 1 collision.

`python3 migrations/migrate_google_ids.py --apply` reported `rows removed: 24`, `google_jobs rows
now: 1320 (distinct source_id: 1320)`, no `FAILED groups` line and no `WARNING` line. Verified
directly per the row's own done-when: `SELECT count(*), count(DISTINCT source_id) FROM jobs WHERE
platform='google_jobs'` → `(1320, 1320)`. Re-ran the dry run afterward to confirm idempotency, per
the script's own docstring claim: `merge groups: 0`, `re-key only: 0`, `nothing to do -- every row
is already keyed on a stable id.` `--keep-stats` was deliberately not passed — the script truncated
94 rows of `google_jobs_query_stats`, which is not data loss (see the row's own reasoning below: the
table measured SerpApi cache expiry under the broken key, not real novelty). All three suites still
print `OK` (1433 / 354 / 117, 0 skipped) against the migrated database.

**Original finding, kept below for history:**

**Found 2026-08-03 while closing `OQ-16`** (the last `kind: record` handoff document, about to be
deleted). Its Step 3 was left `NOT APPLIED` at write time, pending confirmation nothing was
concurrently writing scores. Nobody came back to it. Checked today:

```bash
cd backend
export $(grep -v '^#' .env | grep DATABASE_URL)
pgrep -af score.py                       # confirm empty first -- see the migration's own STOP section
python3 migrations/migrate_google_ids.py # dry run, no --apply
```

**Still live, 9 days later:** `1344` `google_jobs` rows, `1329` distinct `source_id` — 15 duplicate
groups today (the original finding was 205 duplicate rows / 32% inflation before Step 2's stable-id
fix landed in code; Step 2 is live — `lib/ids.py`'s `google_source_id()` exists and is called from
both `ingest/google-serpapi.py` and `ingest/google-apify.py` — but Step 3, the one-time re-key of
**existing** rows onto it, was never run). The dry run above currently reports `1180` rows needing
re-key and `24` merge groups.

**Do not run `--apply` without reading the migration's own "STOP — read before running `--apply`"
section first** (`migrations/migrate_google_ids.py`, or the deleted handoff doc via
`git show refactor-freeze-2026-08-02:backend/docs/HANDOFF-multimachine-google-jobs.md` if the
in-script version has drifted) — `apply_merge()` moves scores off losing rows before deleting them,
`ON DELETE CASCADE`, and a concurrent `score.py` write between the read and the delete silently
destroys that score. `pgrep -af score.py` returning empty is the precondition, and a fresh backup
is the second one:

```bash
docker exec nyc-events-postgres pg_dump -U jobs_pipeline -d jobs | gzip > ~/backups/pre-googleid-$(date +%Y%m%d).sql.gz
python3 migrations/migrate_google_ids.py --apply
```

**Done when:** `SELECT count(*), count(DISTINCT source_id) FROM jobs WHERE platform='google_jobs'`
returns two equal numbers.

**Separately, and not part of this row:** the handoff doc's Step 5 (Postgres publishing
`0.0.0.0:5432` to the LAN) is **already fixed** — checked 2026-08-03, `docker ps` shows
`nyc-events-postgres` bound to `127.0.0.1:5432` only. Steps 4 (`job_sources` provenance table) and
6 (a second worker) are unbuilt and, per the doc, 6 was confirmed never planned (2026-07-26) — left
off this list rather than turned into rows nobody asked for, per this file's own ceiling.

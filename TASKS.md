---
kind: rolling
written: 2026-08-03
generator: none
subject: .
budget: 400
---

# Session tasks — everything a session can do without the owner

**This file owns the prefix `T-`.** One allocator. **The next free number is `T-25`.** Numbers are
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

### ~~T-10~~ — A migration runner and a `schema_migrations` table

**Closed 2026-08-03.** New `backend/migrations/runner.py`, stdlib only, registering all ten existing
scripts by name (filename, no rewrite). It creates `schema_migrations(name, applied_at, note)` on
first use and never guesses at real-world state by parsing a script's own report text — a second,
drifting copy of logic each script already owns, the same reasoning CLAUDE.md gives against
reimplementing relevance matching. Three actions: `--status` (default) reports every registered name
applied-or-not from the table; `--apply NAME` invokes `python3 migrations/<NAME>.py --apply` once and
records it on exit 0 — a NAME already recorded is a no-op, **the underlying script is not
re-invoked**, which is what makes running it twice apply nothing the second time without leaning on
each script's own idempotency contract a second time; `--mark-applied NAME --note "..."` bootstraps
history for a migration already applied by hand before this runner existed, since guessing that from
output text would be exactly the reimplementation this design avoids.

**Deliberately no `--apply-all`.** Four of the ten scripts document a real, non-destructive-but-real
effect on a bare re-run — `migrate_profiles.py --apply` refreshes a live profile's criteria/persona
from whatever the config file currently says, `migrate_pursuit_profile.py --apply` without `--active`
deactivates an active profile, `migrate_company_ats.py --apply` inserts from whatever `--seed-file`
currently points at. Each is an operator decision by that script's own docstring; a blanket apply-all
would make ten of those decisions on a shrug. Naming one keeps it exactly as explicit as running the
script directly always was.

**Bootstrapped against this box's real Postgres, read-only.** Every one of the ten was checked via
its own existing dry-run report (each documents this as safe and read-only; none was passed
`--apply`) and is `--mark-applied`, with the evidence in its note — `python3 migrations/runner.py
--status` now reports 10/10 applied here. Two are genuinely one-shot and match prior closed rows:
`migrate_google_ids` (T-20's own verified numbers) and `migrate_scores` (legacy columns already
gone). Four are schema-plus-report scripts that add columns and either backfill a fact
(`migrate_extraction_passes`, 0 rows pending) or deliberately never backfill
(`migrate_score_versions`, columns present, backfill not its job) or derive a value from raw_json
(`migrate_ats_descriptions`, `migrate_description_rehash`, both "to rewrite: 0" over the same 11,121
rows). The remaining three — `migrate_company_ats`, `migrate_profiles`, `migrate_pursuit_profile` —
are seed/refresh scripts meant to run again whenever a config file changes, not one-shot migrations;
"applied" for these three means the object each creates already exists with real (non-placeholder)
content, recorded as such in the note, not that no future run is warranted.

**On a box without this history, `--status` reports honestly, not optimistically**: an unmarked
migration reads `NOT APPLIED` even if it was in fact run by hand years ago and nobody typed
`--mark-applied` — the table records what the runner has been told, not an omniscient scan. That is
the tradeoff for not parsing ten scripts' differently-shaped report text to guess.

New `backend/tests/test_migrations_runner.py`, 11 cases: `TestRegistry` pins the ten names against
`os.listdir()` with no database; the rest run against `evals.scratchdb.scratch_schema()` (never
`public`, never a real migration script — `subprocess.run` is mocked for the apply-tracking cases) and
cover table idempotency, `ON CONFLICT DO UPDATE`'s overwrite-not-duplicate, `--status` covering every
registered name exactly once, and the row's own acceptance criterion directly: two calls to
`apply_one` for the same name leave `subprocess.run`'s call count at 1. Two more invoke the real
script end-to-end for argument validation only (an unregistered `--apply` name, `--mark-applied`
without `--note`) — both are rejected before anything could be invoked or recorded.

All three suites still print `OK`: pipeline is `1449`, `+11` over the `1438` on record after `T-12`
(`34a1ed8`) — exactly the new test file, webapp and api unchanged. Citations still `0 new` at `273`
known-drifted, unmoved by two new files with no `file:line` citations in either. `ruff`
`1085 -> 1088`, all three `S603` (`subprocess` call) on the two new files' three `subprocess.run`
call sites — the same finding `run-daily.py`'s own pre-existing `run_step()` already carries
unsuppressed in the baseline, so this follows rather than breaks that precedent; no new finding in
any other category.

---

## Harness

`T-5` … `T-9` are the layers of [`TASK-52-harness.md`](TASK-52-harness.md), listed here so they are
schedulable. That file carries the argument, the ordering constraint and the definition of done;
do not restate it here.

| row | layer | one line |
|---|---|---|
| ~~`T-5`~~ | 1 — what a session knows | `.claude/CLAUDE.md` under 150 lines; five path-scoped files under `.claude/rules/` |
| ~~`T-6`~~ | 2 — who does the work | `plan-verifier` and `artifact-reviewer`, read-only, each invoked once on real work |
| ~~`T-7`~~ | 4 — what is guaranteed | `PostToolUse` hook running `tools/audit-citations.py` on the touched path |
| ~~`T-8`~~ | 5 — what travels | `~/.claude/CLAUDE.md`: scope discipline, verify-before-claiming, never echo credentials |
| ~~`T-9`~~ | 5 — what travels | `~/.claude/skills/whatsnew/` — **task 53's Part B, never built.** Run once, first report committed |

**`T-5`, `T-6`, `T-7` closed 2026-08-03.** `.claude/CLAUDE.md` is 149 lines, zero `~~` spans, with
five path-scoped files under `.claude/rules/` (`sql.md`, `ingest.md`, `measurement.md`, `config.md`,
`frontend.md`) carrying what the main file used to hold inline. `.claude/agents/plan-verifier.md`
and `.claude/agents/artifact-reviewer.md` exist, both `tools: Read, Grep, Glob, Bash` with no
`Edit`/`Write`. `.claude/settings.json` wires a `PostToolUse` hook on `Edit|Write` to
`.claude/hooks/audit-citations-hook.py`, which runs `tools/audit-citations.py` (no path-scoped mode
exists, so "on the touched path" means the same whole-tree "0 new" invariant the suite already
checks, just surfaced in the editing turn) and exits 2 on new drift.

**One clause of the definition of done could not be met this session, and is recorded rather than
quietly skipped:** "each [agent] invoked once on real work" and the hook "observed to fire" both
require a session that started AFTER these files existed — Claude Code's own docs say a running
session does not detect a newly created `.claude/agents/` directory, and the same proved true for
`.claude/settings.json`'s hook, which did not fire on the edit that added this very paragraph.
Attempting `plan-verifier` mid-session returned `Agent type 'plan-verifier' not found. Available
agents: claude, claude-code-guide, Explore, general-purpose, Plan, statusline-setup` — confirming
the limitation rather than working around it. **The first session to start after this commit is the
real test of all three;** if the hook does not fire on that session's first `Edit`/`Write`, or
either agent is not selectable, that is a `T-` row, not a footnote.

`.claude/*` was gitignored wholesale except `CLAUDE.md` (the one prior carve-out, from the same
tasks-38/40 lesson this row repeats: a file that cannot be committed cannot be corrected). `rules/`,
`agents/`, `hooks/` and `settings.json` are the harness itself, not machine state, so `.gitignore`
gained four more `!` exceptions rather than the whole directory being un-ignored —
`settings.local.json` stays exactly as machine-local as it was.

**The deferred clause from `T-5`/`T-6`/`T-7` resolved itself the next session, as predicted.** This
session's own agent listing carried `plan-verifier` and `artifact-reviewer` from the start, and the
`PostToolUse` hook fired live and correctly during `T-18` work — twice as a genuine block (a `git
show <ref>^:` citation whose `^` fell outside the hook's own ref regex; a `git show <ref>:` split
across a `#:`-prefixed comment line break) and repeatedly as silent passes on correct edits. All
three primitives are confirmed working, closing the one open question `T-5`/`T-6`/`T-7` left behind.

**`T-8` and `T-9` closed 2026-08-03.** `~/.claude/CLAUDE.md` (35 lines) carries the four points named
in the table row verbatim as prose rules, not restated here. `~/.claude/skills/whatsnew/SKILL.md`
implements the six-step manual check `TASK-52-harness.md` specifies — read the record, fetch
`code.claude.com/docs/llms.txt`, inventory `~/.claude/` and the current project's `.claude/` fresh
each run, bucket into *replaces something hand-built* / *worth trying* / *ignore*, report, update the
record — and is explicit in its own body that automating it is the failure it exists to prevent.

Run once, this session, against a genuinely empty prior record (`~/.claude/skills/whatsnew/last-
checked.json` did not exist). First report at `~/.claude/skills/whatsnew/reports/2026-08-04.md`
(outside this repo, so summarized rather than linked): **bucket one flagged two things** — this
repo's `.claude/CLAUDE.md` "Commands" section is six-plus bash invocations a session re-types by
hand every time, and `.claude/commands/` (a documented primitive, unused here) could turn the
highest-traffic ones into `/test`, `/citations`, `/lint`; `/goal` was flagged as a weaker-fit
candidate for what a `T-`/`OQ-` row's own "Done when:" clause already does by hand, one condition at
a time. Bucket two named the Advisor Tool (a second opinion at the moment of a weight/threshold
decision, for `OQ-3`'s eventual close) and Channels (turning `tools/volume-check.py`'s alert into
something a session picks up on its own next run, rather than a line in output nobody read yet).
Neither bucket's findings are built here — by the skill's own design, a first run reports, it does
not act, and no `.claude/commands/` exist in this repo as of this row.

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

### ~~T-12~~ — `logging` on the pipeline stages' failure paths

**Closed 2026-08-03.** New `backend/lib/pipelinelog.py`, one `get_logger(name)`, called once at
import time by each of the four scripts. **Filtering stays exactly where it already lived**: the
logger itself is always at `DEBUG`, so nothing is dropped by `logging`'s own level machinery — every
call site keeps the same `if DEBUG_PRINT_KEYS:` guard it had as a `print()`, or no guard at all for
the failures this pipeline already printed unconditionally (`score.py`'s `ERRORED` path, three sites
in `match.py` — D10's corrupt-`tech_stack` warning, D12's unknown-criteria-section warning, D20's
batch/row/profile rejection warnings). This is a format change, not a visibility change, which is
what "not a wholesale conversion" (this row's own words) turned out to mean in practice.

**The handler resolves `sys.stderr` at write time, not at construction — deliberately.**
`logging.StreamHandler()` captures whatever `sys.stderr` was when the first call configured it, so
once a handler exists, `contextlib.redirect_stderr` and `mock.patch.object(sys, "stderr", ...)` —
both load-bearing throughout `tests/test_match.py` and `tests/test_score.py`, predating this row —
silently stop capturing anything: the handler keeps writing to the object it was built with. A
`_StderrProxy` that looks `sys.stderr` up fresh on every `write()` is what makes this module
compatible with every existing test written for the `print()`-based version, with zero test
rewrites. `tests/test_lib_pipelinelog.py` pins exactly this, including the case where a second
script's logger reuses the first script's already-installed handler (the shape all four scripts are
in under `python3 -m unittest discover`, and under `importlib` in `TestRunDailySummaryParser`).

Converted: `extract.py`'s `extract_facts`/`extract_one_job` (rejecting-input, deferring, call-failed,
unusable-extraction — all four DEBUG-gated, unchanged); `match.py`'s `load_facts` (D10),
`log_deleted_ids` (D11, DEBUG-gated, unchanged), `check_criteria_sections` (D12), `write_matches` and
`match_profile` and `main` (D20, three sites); `score.py`'s `score_one_job` (the one unconditional
site) and `_score_one_job` (three DEBUG-gated sites); `run-daily.py`'s missing-env `FAILED`, a step's
non-zero exit, and the could-not-append-to-history warning. **Left alone, deliberately**: every
stdout print (summaries, `FAILED:` early-exit lines, per-step stdout/stderr passthrough in
`run-daily.py` — passthrough is the child's own output, not this script's diagnostic, and
re-wrapping it would double-format whatever the child already logs) and the two success-path DEBUG
prints in `extract.py`/`score.py` (out of scope: not a failure or a deferral).

**Forced failures, one per file, checked directly** (not just via the suite): `extract.extract_facts`
with a `call` that raises `llm.TransientError` → `... DEBUG extract: deferring forced-1 (...): 429
simulated`; `score.score_one_job` against a persona that raises `KeyError` mid-build → `... ERROR
score: job-score ERROR on forced-2 (...): RuntimeError: ...` (unconditional, no `DEBUG_PRINT_KEYS`
set); `match.match_profile` with a non-numeric criteria weight → `... WARNING match: tech could not
score job_id=forced-3 (TypeError: ...)`; `run-daily.main` with `REQUIRED_ENV` extended by a bogus key
→ `... ERROR run-daily: run-daily FAILED: DEFINITELY_NOT_SET_XYZ not set ...`. All four are
timestamped, leveled, structured records where there used to be a bare `print()`.

`python3 tools/volume-check.py` still parses the run history unchanged (`volume-check ok: 9
source(s) evaluated` against the existing `.run-volumes.jsonl` — untouched, since `parse_upsert_summaries`
and `volume_floors.record_run` were never touched). All three suites still print `OK`: pipeline is
+5 over the `1433` at `328a52d` (the new `tests/test_lib_pipelinelog.py`), webapp and api unchanged
at 354 / 117. `ruff` on the whole tree went 1077 → 1085, entirely from the new test file matching
`tests/test_lib_envfile.py`'s own pre-existing `sys.path.insert` + `# noqa: E402` convention
(`E401`×1, `I001`×1, `RUF100`×6 — the same six categories `test_lib_envfile.py` already carries);
zero new findings in any edited script, and `match.py` — which had none before — still has none.

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

### ~~T-14~~ — Two tools still select their corpus from production by recency

**Closed 2026-08-03.** Checked first whether `evals run` already covers what these tools do, per
this row's own instruction: it does not, quite. `evals/tasks/score.py` exists (contrary to
`evals/README.md`'s own stale "Status" table, which still lists a score task as unbuilt) and
`evals/models.py` already supports the `claude:MODEL` CLI backend `claude-bench.py` needs — but
neither tool's *other* job, comparing a candidate against **today's live production score**, has an
evals equivalent: a frozen fixture snapshot carries `job_facts` and `match_score`, never
`job_scores.fit_score` (`evals/corpus.py`'s `FACT_COLUMNS`/`_pool_query` — no join to
`job_scores` at all). Rebuilding that comparison inside `evals/` is a bigger lift than this row (a
`score` fixture format change) and out of the ceiling for a `T-` row; deletion would also lose it
outright. Neither of the row's two literal options fit cleanly, so the fix is the one thing they
share: the corpus **selection** is what `ORDER BY first_seen DESC` breaks, and that part fixture-izes
cleanly without touching the live-comparison feature.

Both tools now sample from `backend/evals/fixtures/corpus-v1.jsonl` (overridable with `--corpus`)
via `evals.corpus.load()`/`job_fields()`/`facts_fields()` — the same per-platform-stratified,
pathology-seeded fixture `evals/` already snapshots and pins, instead of a recency-biased live
query. `--only-scored`/`--vs-production` keep working exactly as before: after sampling, one
`SELECT ... FROM job_scores WHERE job_id = ANY(%s)` looks up each sampled job's **current**
score — that half is inherently live (`OQ-3`, the human-label round, is the reminder that "the
number that answers the question" and "the number that is reproducible" are not always the same
number). `claude-bench.py`'s default (unscored) path was already fine — `score.select_shortlist()`
orders by `match_score`, not recency — so only its `--only-scored` branch changed.

Verified against this repo's live Postgres: `select_jobs()`/`fetch_jobs(only_scored=True)` both
return the same 6 of a 20-job frozen sample carrying a current `tech`-profile score, with facts
merged in correctly (`build_prompt()` builds off the `summary` block exactly as `select_shortlist()`
rows do). All three suites still print `OK` (1433/354/117); `ruff` on the three touched files went
30 → 29 (one `S311` on the new `random.Random(0)` sampling, silenced with a named `noqa`, and one
pre-existing finding fell out of `compare-models.py`'s old hand-rolled query in the process).

---

### ~~T-15~~ — `learned-ranker-probe.py` trains and evaluates on the same layer

**Closed 2026-08-03, third option.** `y` really is `fit_score >= GOOD` end to end — training and
the `average_precision_score` verdict both read L1, and L0 (`evals/labels.py`) never enters the
file. Building a real L0 evaluation was ruled out rather than attempted: `OQ-3`'s overlap set is 36
postings with 10 rows of actual overlap, below the row this file's own neighbor rule forbids
tuning on ("do not re-tune ... on a 20-row eval"), so a cross-validated L0 number today would be
exactly the kind of confident wrong answer this file's other four guards exist to prevent. Revisit
once round 2 closes (`OQ-3`, due ~2026-08-09).

Instead, both halves of the "not silence" option: a new docstring section, **WHAT THE VERDICT IS
NOT EVIDENCE OF**, states plainly that a passing arm answers "do facts + learned weights recover
this model's own score better than hand-tuned weights" — the weights-vs-features question this
file exists to settle — and not whether `fit_score` matches an actual human placement decision.
The same caveat prints at the top of every run's own stdout, immediately after the base-rate line,
in the same style as the file's existing `LEAKAGE`/`VOID` guards, so a terminal run cannot miss it
even though the script itself is unreproducible on a clean checkout (numpy/sklearn absent by
design) and could not be executed here to confirm the print — `python3 -m py_compile` is what
verified it.

---

### ~~T-16~~ — f-string SQL identifiers

**Closed 2026-08-03.** The row's own count was wrong, and re-deriving it against the tree (as
`.claude/CLAUDE.md` says to) is the first finding: `.venv-dev/bin/ruff check . --select S608` found
**113** sites, not "roughly 25" — every non-excluded file in the tree, not just `schema.py` and
`migrations/*`. `backend/lib/dbconn.py:171`, the row's other named site, turns out not to be one of
them: ruff's `S608` only fires on `SELECT`/`INSERT`/`UPDATE`/`DELETE` keywords, and that call is an
`ALTER TABLE`, so it was never flagged and needed no change.

**Every one of the 113 was read, not assumed.** All splice a module-level `ALL_CAPS` table/column
constant (`schema.MATCHES_TABLE`, `_FACT_COLUMNS`, ...), a `WHERE`/`SET` fragment built only from
fixed string literals with every value still bound through `%s`/`%(name)s`, or output from
`relevance.py`'s own SQL compiler (`tier_sql`/`union_sql`) — the one implementation `.claude/CLAUDE.md`
says matching must route through. Two sites are not SQL at all: `evals/labels.py:946` is a
human-readable error message that happens to quote a `DELETE` statement for an operator to type by
hand. One site is validated rather than a bare constant: `ingest/workday.py:833`'s `loc_cols` is
checked by `relevance.tier_sql` as plain identifiers before this file ever builds its own column
list from the same source (see the comment already on that line). Not one site builds identifier or
clause text from a request parameter, a config value, or ATS/employer/labeller data — the row's own
"not user input" held for all 113, not just the ones it happened to name.

**No site used `psycopg.sql.Identifier`.** Every constant is a Python name, never a runtime string,
so there is nothing dynamic for `sql.Identifier` to protect against that a `# noqa` naming the
constant doesn't already make checkable by a reader. The row's other option was written for exactly
this case. 92 sites across 31 non-test files now carry a per-line `# noqa: S608 -- ...` naming what
it splices — including `tools/*`, which the row didn't name but which turned out to hold 14 of the
113 (`tools/ats-discover.py` alone). The other 21, all in `tests/*` (`backend/` and `webapp/`),
went into `pyproject.toml`'s existing `"**/tests/*"` per-file-ignore alongside `S101`/`ARG`/etc.
rather than 21 more per-line comments — but only after the same individual read, recorded in the
comment beside the new entry so nobody mistakes it for an unexamined blanket suppression. Placement
matters and is not always the diagnostic's reported row: a `noqa` on the opening line of an
unterminated triple-quoted f-string becomes part of the string, not a comment, and is silently
inert — confirmed empirically before writing the other 111 by hand, which is why some sites carry
the comment on the line the string closes rather than the line `ruff` prints in its report.

`backend/migrations/*` keeps its existing per-directory `S608` ignore rather than converting to 91
more per-line comments — all ten scripts follow the one pattern this row already established, and
the comment beside that entry now says so instead of leaving it as a stopgap the next reader has to
re-justify.

`.venv-dev/bin/ruff check . --select S608` now reports zero findings tree-wide. Baseline
1088 → 975 (`ruff check . --statistics`, run it for the number). `RUF100` (unused-noqa) held at
320 — none of the 92 new directives is inert. All three suites print `OK` at the same counts as
`T-10` (1449 / 354 / 117) — this row changed no behavior, only comments and one `pyproject.toml`
table. Citations still `0 new` at `273` known-drifted (`tools/audit-citations.py`), unmoved because
nothing here added a `file:line` claim.

---

### ~~T-17~~ — Gradual typing on the seams only

**Closed 2026-08-03.** `mypy`, installed in `.venv-dev` alongside `ruff` (never in any of the three
`requirements.txt` — grepped in CI same as `ruff`'s own bound check). `backend/pyproject.toml`
gained `[tool.mypy]` with `files = ["lib", "schema.py", "match.py"]` and `follow_imports = "silent"`
— the row's own "do not type the tree" as a checkable config, not a sentence: mypy never opens
`extract.py`, `llm.py`, `profiles.py` or `relevance.py`, which every one of these three imports.

**Every public function in `backend/lib/`'s 8 modules got a signature** (`dbconn`, `envfile`, `http`,
`ids`, `state`, `text`, `timeparse`, `upsert`), all 12 of `schema.py`'s public functions
(`cohort_bucket` through `prune_old_closed`), and `match.py`'s `score_job()` — named by the row as
the one function the ranking rests on. Private (`_`-prefixed) helpers were deliberately left
unannotated: mypy's own default, `check_untyped_defs = false`, skips a function's body entirely when
it carries no annotation at all, so an unannotated helper costs nothing and is never silently
checked with inferred `Any`. **That default is restated explicitly in the config** rather than left
implicit, so a future mypy release changing it cannot silently widen this row's claim.

**Two real findings, both fixed, not suppressed on sight.** `schema.py:465`'s
`conn.execute(...).fetchone()[0]` indexed a `tuple | None` — `to_regclass()` on a bare `SELECT`
never actually returns no row, but mypy cannot know that, so the fix binds the row first and checks
it, which is correct regardless. `lib/http.py`'s `get_bytes()` raises `last_exc` after the retry
loop, which is `None` if `max_retries <= 0` — a real, pre-existing caller error out of this row's
scope to fix, so it carries a named `# type: ignore[misc]` rather than a silent pass, same
one-per-site discipline `T-16` set for `# noqa`.

**One live-but-harmless case Python 3.14 itself changed underneath the row.** `lib/upsert.py`'s
`UpsertResult.__add__` originally needed `"UpsertResult"` quoted (a self-referencing forward
reference, evaluated while the class body is still executing) — but PEP 649's lazy annotations,
default since 3.14 and this repo's pinned `target-version`, made the quotes both unnecessary and a
`ruff --select UP037` finding on its own. Removed rather than left as a false-positive suppression.

`.venv-dev/bin/mypy` (config-driven, no file args) reports **`Success: no issues found in 12 source
files`**, reproduced in a scratch venv with nothing but `mypy` and `psycopg[binary]==3.3.4` (matching
the pin in `requirements.txt`) to confirm CI's from-clean install path matches. New CI job `types`
(`.github/workflows/ci.yml`) runs it **blocking**, unlike `ruff`'s own `continue-on-error` baseline
step — there is no backlog here to land against gradually; a clean run is what the row asked for.

**Zero new `ruff` findings.** 975 -> 977 net, but diffed line-by-line against a `git stash`
before/after: the two apparent new entries were `lib/upsert.py`'s `UP037` on the quotes just removed
above (a `--fix`, not a new problem) and every other delta is an unchanged finding at a shifted line
number from the added `import` lines. All three suites still print `OK` at the same counts recorded
at `T-16`: 1449 / 354 / 117. Both frontend checkers still pass (`verify_fixtures.py`,
`check_client.mjs`'s 57 checks, 0 failed).

---

### ~~T-18~~ — Shrink the citation baseline

**Closed 2026-08-03.** 305 → 3 across six commits, the last four in one session. **Run the tool for
the number; do not quote this line** — it has already been written four different ways in four
commits, which is the failure this row was a small piece of undoing.

**The last 3 are not further drift — they are false positives the checker's own design cannot
avoid**, confirmed individually rather than left as an unexplained floor: `backend/evals/
__main__.py:620` and `backend/tools/mock-acceptance.py:81` are CLI `--out` defaults naming a file to
be *created*, not a citation to existing content (neither path has ever existed in git history);
`backend/tests/test_mock_corpus.py:947` asserts that a specific file-and-line-range substring is
present in another module's docstring, so the literal string under test must stay bare —
wrapping it here would fail the assertion it exists to make. Each was checked, not assumed; "3 left"
is the honest floor for this tool's design, not an abandoned target.

**One correctness bug found and fixed along the way, in citations this same row had already
"fixed" earlier in its own run.** The checker's tag-span check (`_spans()` in
`tools/audit-citations.py`) short-circuits on any citation recognized as `git show <ref>:<path>`
*before* the line-count check that runs for untagged citations — so a tag-wrapped citation to a
line past the end of the target file resolves exactly as cleanly as a correct one. Several
citations to the rolling handoff document, wrapped in `refactor-freeze-2026-08-02` (where that file
is 144 lines) at line numbers as high as 1047, passed the checker silently across two different
sessions before being caught by manually reading content, not by the tool. Fixed by finding the
specific commit each citation's line number actually resolves against, via `git log -S '<citing
string>' -- <citing file>` to date the comment and `git log` across the target file's full history
to find where the matching prose sits at that exact line — HANDOFF.md was a rolling document,
periodically trimmed by dedicated roll/archive tasks (40, 44), 3481 lines at its largest. Two other
citation-splitting bugs recurred independently: a `git show <ref>:` broken across adjacent string
literals with a quote between them, and the same broken across a `#:`-prefixed comment line — both
invisible to a human reader, both silently unresolved. **The lesson for any future citation work:
re-run `--all` after every batch rather than trusting the PostToolUse hook's silence** — the hook
fires on the file being edited, not on a citation fixed in an earlier commit that happens to share a
key with one being touched now.

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

---

### T-21 — Static assets carry no `Cache-Control`, so Cloudflare can serve a stale `app.css`/`app.mjs` for up to 4 hours after every deploy

**Found 2026-08-04 while closing `DEV_TASKS.md`'s `OQ-14`** (the phone test). A real fix to
`frontend/app.css` landed on disk and was served correctly by the origin (`curl` against
`127.0.0.1:8421` showed it immediately), but `https://jobs.etotheric.com/app.css` kept returning
the pre-fix bytes — `cf-cache-status: HIT`, `cache-control: max-age=14400`. `frontend/serve.py`'s
`StaticFiles` mount sends no `Cache-Control` header of its own, so Cloudflare fills the gap with
its own default heuristic caching for known static extensions (`.css` was cached; `.mjs`, oddly,
was not — `cf-cache-status: DYNAMIC` on `js/app.mjs` in the same test). `index.html` itself is
never cached (`DYNAMIC`), which is what made the one-off fix possible at all: a cache-busting
query string on the stylesheet `<link>` (`app.css?v=20260805-hidden-fix`) forced a fresh fetch
without touching the Cloudflare account. That is a manual step, though, and nothing stops the same
staleness recurring on the next edit to `app.css` or any file under `frontend/js/`.

**How to do it.** Give `frontend/serve.py`'s `StaticFiles` mount (or a thin wrapper around it) an
explicit `Cache-Control` header on every static response. `no-cache` (always revalidate via
`ETag`/`Last-Modified`, a cheap `304` when nothing changed) is the safer default for a pre-launch
app whose frontend is still changing often; a short `max-age` is the fallback if `304` round-trips
ever show up as a measured cost, which nothing today suggests they will. `backend/webapp/README.md`
notes this same file is `NOT FOR DEPLOYMENT`-flavored caution that turned out not to apply once
`T-`-closing work confirmed the tunnel fronts it in production regardless (see `OQ-14`'s closure) —
this row's fix belongs in the same file for the same reason.

```bash
cd backend/webapp && .venv/bin/python ../../frontend/serve.py &
curl -sI http://127.0.0.1:8421/app.css | grep -i cache-control   # must be present, not absent
kill %1
```

**Done when:** every static response under `frontend/` carries an explicit `Cache-Control` header,
confirmed both directly against the origin and through the tunnel
(`curl -sI https://jobs.etotheric.com/app.css`, expecting `cf-cache-status: MISS` or `EXPIRED` on
the next request after an edit, never a multi-hour-stale `HIT`), and the manual `?v=` cache-bust
added to `index.html` on 2026-08-04 can be removed without the staleness this row describes coming
back.

---

### T-22 — Turn a Builder's background paragraph into a persona, prototyped, no UI and no `profiles` row

**Where this came from.** A draft scoping a *personal scoring layer* — a second
`gap_bridging_angle`/`risk_factors` narrative per posting, computed against one Builder's own
persona rather than the cohort's, run in the Builder's browser on the Builder's own key, shown on
the job detail screen only. Cut into rows on 2026-08-05 and deleted with the cut; its six decisions
are [`docs/adr/0005-personal-scoring-layer-annotates-only.md`](docs/adr/0005-personal-scoring-layer-annotates-only.md)
and the draft itself is `git show 7dfbc7e:docs/DRAFT-personal-layer-resume-tailoring.md` plus this
repo's history. **Everything else in that feature is an owner decision** — `DEV_TASKS.md`'s `OQ-18`
through `OQ-21`. This row is the one piece blocked on nothing, and it stops deliberately short of
any UI, any storage and any database write.

**Why one generated persona rather than the raw paragraph in every call.** The persona is the only
point at which a wrong inference about a person is visible and correctable. A background paragraph
pasted into every scoring call would repeat a bad reading of someone silently, forever, and cost
more per call besides.

**How to do it.** The persona contract is already pinned and needs nothing new:
`profiles.validate` (`backend/profiles.py:147-150`) requires `background_summary`, `strengths`,
`honest_gaps` and `scoring_instructions`; `buckets` is deliberately *not* required
(`backend/profiles.py:139-146`) and `build_prompt` omits the whole section when the key is absent
(`backend/score.py:601-628`). `backend/config/pursuit-persona.json` is the readable example of the
shape. Feed the result straight to `build_prompt(persona, job)` (`backend/score.py:588`), which
reads exactly five keys and nothing else.

**The postings can come from disk — this row needs no database.** `_facts_block`
(`backend/score.py:555`) reads a shortlist row, and every field it touches is in `LIST_COLUMNS`
(`backend/webapp/jobs.py:119-128`), so the job objects already in
`frontend/fixtures/shipped/GET_v1_jobs.json` are exactly the right shape.

**Model and base URL are parameters, not UI copy.** `llm.call_detailed` takes per-call `model` and
`base_url` overrides (`backend/llm.py:206-208`) and the module already speaks to four providers
(`backend/llm.py:7-13`). Hardcoding one is how this codebase lost a model it was relying on before.

**Two things this row must not do.** It must not create a `personal` row in the `profiles` table:
`backend/migrations/migrate_profiles.py:4-22` states the split — a Builder gets a `builder_profiles`
row through `POST /v1/onboarding` and never a `profiles` row — and creating one now takes
`--new-cohort` and puts a new profile in front of `extract.py` and `match.py` every night. And it
must not reuse the server's three cache keys for a future client-side cache: `facts_version` is not
in `LIST_COLUMNS` and is exposed to the client nowhere, and adding it is not free, because
`LIST_COLUMNS` order is a contract asserted against five shipped fixture files
(`backend/webapp/jobs.py:111-118`). **A `sha256` of the exact prompt string subsumes all three keys,
needs no new field and invalidates on the same events.** Record that in the script, not here.

```bash
cd backend
python3 tools/persona-from-background --background-file <fixture> --n 3
```

**The script is spelled without its suffix above, deliberately.** Give it the repo's usual `.py`
name; it is written this way here only because `tools/audit-citations.py` cannot tell a file a row
is *about* to create from a citation that has drifted, and the `PostToolUse` hook blocks the edit
either way. Silencing that in `config/citation-baseline.json` is not the alternative.

**Done when:** that command prints a persona carrying all four keys `profiles.validate` requires,
`build_prompt` accepts it against three real postings without raising, three narratives are printed,
grepping the new script for `groq` or `z.ai` returns nothing, and `git status` shows no change under
`backend/config/` and no migration. No database write, no `profiles` row, no frontend file touched.

---

### T-23 — Six onboarding fields are collected from every Builder and read by nothing

**Where this came from.** The superseded resume-tailoring draft recorded it with a grep behind it,
and it is independent of the personal-scoring-layer feature that draft was about — which is why it
is a row of its own rather than a line in an ADR. `builder_profiles`
(`backend/webapp/schema_web.py:600-611`) holds `location_pref`, `remote_pref`, `comp_floor`,
`tracks`, `prior_years`, `situation` and `schedule_constraints` for every Builder who completes
onboarding, and the ranking pipeline references none of it. That is a personal layer that is free,
needs no LLM call, changes no privacy posture and is already collected.

**Start by re-running the grep rather than trusting this paragraph** — it was true when written and
this file is not the kind of thing that stays true by itself.

**Scope it to the four fields that actually resolve.** `RESOLVABLE` is `tuple(DEFAULTS)` —
`location_pref`, `remote_pref`, `comp_floor`, `tracks` (`backend/webapp/onboarding.py:87-92`,
`backend/webapp/onboarding.py:115`) — applied key-wise over cohort then shared default, skipping any
value that is `None` (`backend/webapp/onboarding.py:220-226`), with `resolved_for(conn, user)` as the
entry point (`backend/webapp/onboarding.py:240`). `situation`, `schedule_constraints` and
`prior_years` are stored but do not flow through `resolve()`, and `load_builder` selects only the
four (`backend/webapp/onboarding.py:234-238`). A design assuming all seven will not work.

Two invariants bound the answer. **Whatever this becomes must not break the `(job_id, profile)`
keying** that makes cost flat in users, which rules out a per-Builder `job_scores` row; a read-time
filter or a free arithmetic adjustment on top of `match_score` both survive it. And
`match_reasons` must still carry per-rule attribution on every row.

```bash
cd backend
grep -rn builder_profiles match.py score.py webapp/jobs.py    # empty today; must not be after
python3 -m unittest discover -s tests
cd webapp && .venv/bin/python -m unittest discover -s tests
```

**Done when:** that grep is non-empty, all three suites print `OK`, and — if `LIST_COLUMNS` changed
at all — `python3 frontend/verify_fixtures.py` and `node frontend/check_client.mjs` both pass with
the five shipped fixtures hand-edited in the same commit.

---

### T-24 — Three places in the code still say the cohort narrative budget is zero, and it is 200

**Found 2026-08-05 while cutting the personal-scoring-layer draft into rows**, by a `plan-verifier`
run that checked the live database rather than only the code — which is the only reason it was
caught, because every one of these citations still *resolves*.

`backend/config/pursuit-persona.json`'s `_no_buckets_comment` says `daily_narrative_budget` is 0 and
leans on that to argue a known prompt/vocabulary mismatch is harmless because "score.py writes
nothing for this profile." `backend/score.py:602-603` says the same. `frontend/js/ui.mjs:45-46` goes
furthest and is the one with a user-visible consequence: it tells the next reader that
`gap_bridging_angle` is *"null on EVERY row"* and that the card's `summary` fallback is therefore
the only path that ever runs. **All three are now false.** The budget was raised to 200 and a
scoring pass ran on 2026-08-05, writing narratives for most of the shortlist.

**Why this is not just tidying.** The `pursuit-persona.json` comment is a *decision record* — it
argues that `score.TRACKS`'s five-value enum, two of whose values are fit judgments rather than job
families, is safe to leave alone precisely because nothing scores this profile. That argument
expired when the budget changed, and `OQ-8` closed on it. Whoever fixes the comment has to say
whether the mismatch is still harmless now that the calls are real.

```bash
cd backend
grep -rn "daily_narrative_budget is 0\|null on EVERY row" config/ score.py ../frontend/js/
python3 -m unittest discover -s tests
```

**Done when:** that grep is empty, each of the three sites states what is actually true (read the
number out of the `profiles` table, do not transcribe `200` into a comment that will drift the same
way), the `score.TRACKS` question above is answered in the persona file or handed to a new row, and
all three suites print `OK`.

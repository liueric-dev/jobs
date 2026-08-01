---
kind: task
written: 2026-08-01
generator: none
---

# 41 — Git and repo hygiene

**Status:** DONE 2026-08-01 — 41a `7d839f5`, 41b `9b7bb5e`, 41c/41d in § *Outcome* below. **Depends on:**
nothing. **Blocks:** nothing, but every other task's "both suites green" check is measured
against whatever baseline 41a establishes.

Four items. **41a is a live production bug whose fix is sitting uncommitted** and is the only
urgent thing in the tranche.

## 41a — a nightly-run bugfix exists only in the working tree

`git status` shows `backend/ingest/workday.py` and `backend/tests/test_workday_ingest.py`
modified and uncommitted. The change is the `_GATE_TEXT_COLUMNS` / `platform` fix plus three
new tests.

**The defect is real and live**, verified 2026-08-01 by reading the code rather than the
comment:

| | evidence |
|---|---|
| `platform_exclude` is configured | `backend/config/pursuit-relevance.json:158` — three platforms excluded |
| `tier_sql` emits the column for it | `backend/relevance.py:271` — `AND {a}.platform !~* %(..._pfexcl)s` |
| the Workday gate never built it | `_GATE_TEXT_COLUMNS` was `("title", "company_name", "description_text")` |
| when it landed | `7d94bb1`, *"Add the description-first cohort gate (tranche_two/10)"* |

The Workday gate is **the only caller of `tier_sql` that does not run against the `jobs`
table** — every other caller gets all four columns for free — so nothing else broke and nothing
spoke up. This is `.claude/CLAUDE.md`'s *"Silence is this system's failure mode"* with a stack
trace attached: the step died while the rest of the run reported success.

**Commit it first, and alone.** It is a production fix; it must be reviewable without cleanup
edits tangled into it. This is the same discipline `3383f9a` used — *"committed as-is, before
any cleanup edits, so that task 34's own diff is readable against a clean base."*

The three new tests deliberately **do not** use the database, and the reason is in the test's own
docstring: the surrounding gate tests are gated on `scratchdb.available()`, and *"a check that
can skip is no guard at all against a failure whose whole character is that nothing spoke up."*
Preserve that property — do not "tidy" the new class into the `@requires_db` block below it.

**Establish the post-commit baseline by running both suites and reading `Ran N tests`**, not by
adding 3 to a number from a document. Task 38 then owns wherever that number is recorded.

## 41b — `scripts/tranche-two-launcher.sh` is untracked forever

`183b4dc` untracked it deliberately and `3383f9a` said it would: it is an agent-orchestration
harness, not project code — it hard-codes this machine, drives `tmux`, and runs tranche_two
tasks that are all done. **It was not deleted on purpose**: it is the owner's file and the
owner's call whether it moves to `~/bin/`.

But it is untracked *and* unignored, so it shows in every `git status` as `??` — and it has
**already been re-added once by a `git add -A`**, which is what `183b4dc` exists to undo.

**Add it to `.gitignore`** with a comment saying why, in the style of the existing `.env` block
(which explains its reasoning at length). That makes the deliberate exclusion durable instead of
depending on nobody typing `-A`.

## 41c — branch topology

Verified 2026-08-01:

```bash
git log --oneline origin/main..main | wc -l          # unpushed
git symbolic-ref refs/remotes/origin/HEAD            # the repo's default branch
for b in $(git branch -r --format='%(refname:short)' | grep -v HEAD); do
  echo "$b: ahead $(git log --oneline main..$b | wc -l) behind $(git log --oneline $b..main | wc -l)"
done
```

Two facts and they are independent:

- **`main` has unpushed commits.** `backend/docs/DEVELOPER.md` records the intended workflow —
  *"each worker machine runs `git pull --ff-only && python3 run-daily.py`"* — which unpushed
  commits silently defeat: a second machine runs older code and says nothing.
- **`origin/HEAD` points at `origin/jobs-app-readiness`, which is far behind `main`.** Every
  remote branch is **ahead 0**, so nothing anywhere holds work that `main` does not.

**Both are owner decisions and this task does not take them.** Pushing publishes; moving a
default branch changes what a fresh clone gets. What this task does is **write the state down
where it is visible** and offer the two commands:

```bash
git push origin main
git remote set-head origin main        # local view only
# moving the real default branch is a host-side setting, not a git command
```

The local `webapp-service` branch is fully contained in `main` (ahead 0) and is safe to delete —
also the owner's call, and `origin/webapp-service` keeps the ref either way.

## 41d — cassette age

The suite prints a cassette manifest with ages on every run. They are recorded fixtures for the
six non-LLM sources and they drift from the live APIs silently.

**Do not re-record as part of this task.** Task 34's rule 4 is explicit: *"do not re-record the
`workday-cxs` cassette without reading `record_workday_cxs()`'s refusal guard"* — the guard
exists because re-recording destroys the only evidence of a recorded failure mode, and
`record_cassettes.py`'s own docstring already disagrees with what its cassette holds (four pages
over 79 postings, not five over 88).

The deliverable here is a **policy line, not a re-recording**: state in
[`DOCS-POLICY.md`](../../../DOCS-POLICY.md) or the fetcher-harness doc what age makes a cassette
stale, who decides, and what the refusal guard protects. Then it is a decision with a written
reason rather than a number everyone reads past.

## Definition of done

| | item | how it is checked |
|---|---|---|
| | The Workday fix is committed **alone**, no cleanup edits in the diff | `git show --stat` on that commit — two files, nothing else |
| | Post-fix baseline recorded from a real run, both suites | the `Ran N tests` lines, quoted in the commit message |
| | The new test class still runs without a database | `cd backend && python3 -m unittest tests.test_workday_ingest -v` with `DATABASE_URL` unset — the three tests run, not skip |
| | `scripts/` entry in `.gitignore` with a why-comment | `git status --short` is clean of `??` |
| | Branch state written down where a reader will see it, with both commands | it is in this file's outcome section or `AUDIT.md` |
| | Push / default-branch / branch-deletion decisions **recorded**, whichever way they go | `DECISIONS.md`, or a line here saying the owner deferred them |
| | A cassette staleness policy line exists | grep for it |
| | Both suites green and not smaller | read `Ran N tests` from each |

## Out of scope

- **Pushing, moving `origin/HEAD`, deleting branches.** Owner decisions. This task surfaces them
  and stops.
- **Re-recording any cassette.** See 41d and task 34's rule 4.
- **Deleting `scripts/tranche-two-launcher.sh`.** `183b4dc` decided not to; ignoring it is not
  reversing that.

---

## Outcome — 2026-08-01

**41a — DONE, `7d839f5`.** Committed alone, before any cleanup edit, so its diff reads
against a clean base. Two files. The three new tests still run without a database.

**41b — DONE, `9b7bb5e`.** `scripts/` ignored with the why-comment. **And the owner
decided `.claude/CLAUDE.md` should stop being ignored**, so the rule is now `.claude/*`
with `!.claude/CLAUDE.md`: the brief every session reads first is tracked, and
`settings.local.json` — this machine's permission state, meaningless on another — is not.
That decision unblocked tasks 38 and 40, both of which needed to edit `CLAUDE.md` and
neither of which could have committed the edit before it.

**41c — branch state, verified 2026-08-01. Three facts, and all three are the owner's.**

```bash
git log --oneline origin/main..main | wc -l          # 24 unpushed
git symbolic-ref refs/remotes/origin/HEAD            # refs/remotes/origin/jobs-app-readiness
git log --oneline main..webapp-service | wc -l       # 0 — fully contained in main
```

| fact | measured | why it matters |
|---|---|---|
| `main` has **24 unpushed commits** | `origin/main` is behind 24 | `backend/docs/DEVELOPER.md` records the intended workflow as *"each worker machine runs `git pull --ff-only && python3 run-daily.py`"*. Unpushed commits defeat it silently: a second machine runs older code and says nothing |
| `origin/HEAD` points at **`origin/jobs-app-readiness`**, which is **behind 100** | every remote branch is **ahead 0** | nothing anywhere holds work `main` does not. A fresh clone gets a hundred-commit-old default branch |
| local `webapp-service` is **ahead 0** | contained in `main` | safe to delete; `origin/webapp-service` keeps the ref either way |

**This task does not take any of them, by design.** Pushing publishes; moving a default
branch changes what a fresh clone gets; deleting a branch is not this task's to do. The
commands, for whoever decides:

```bash
git push origin main
git remote set-head origin main        # local view only
git branch -d webapp-service           # ahead 0, safe
# moving the REAL default branch is a host-side setting, not a git command
```

**Recorded as deferred, per this task's own Definition of done** — the owner was asked and
these three were not among the decisions taken. They stay open and visible here rather than
being decided by silence.

**41d — DONE.** The cassette staleness policy is in
[`DOCS-POLICY.md`](../../../DOCS-POLICY.md) § *Cassette staleness*. No cassette was
re-recorded.

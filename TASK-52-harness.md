---
kind: task
written: 2026-08-03
generator: none
supersedes: git show refactor-freeze-2026-08-02:docs/tasks/refactor/tranche_nine/52-build-the-harness.md
---

# 52 — build the harness: move each answer to the row it belongs in

**Status:** TODO. **Tracked as `T-5` … `T-9` in [`TASKS.md`](TASKS.md)**, which is where it gets
scheduled; this file is the argument and the ordering. Under 150 lines, deliberately.

## Why this was rewritten

The original is behind `refactor-freeze-2026-08-02` and **cannot be executed as written**. Its
Layer 4 specifies a `PostToolUse` hook running two checkers that no longer exist —
`git show refactor-freeze-2026-08-02:backend/tools/audit-docs.py` and
`git show refactor-freeze-2026-08-02:backend/tools/audit-doc-links.py` — against a `docs/**/*.md`
tree that no longer exists either. All three went in `5046f98`: the tools with the documents they
checked. Its Layer 1 targets six `~~` strikethrough spans in `.claude/CLAUDE.md` that are also
gone. Half of it describes a tree that is not there.

The diagnosis it was built on still holds, and it is worth restating because everything below
follows from it: **this repo answered five different questions with one instrument.**

| the question | what should answer it | what answered it |
|---|---|---|
| what does a session know at the start | `CLAUDE.md`, path-scoped rules, skills | one long `CLAUDE.md` plus "go read these docs" |
| who does the work | subagents, forks | hand-rolled subagents and worktrees |
| what decides what runs next | a lead agent, or a script | the owner, typing |
| **what is guaranteed to happen** | **CI, hooks, a linter** | **prose, plus hand-rolled Python checkers** |
| where state lives between sessions | `/resume`, memory, files | ~46,000 lines of Markdown |

**Row 4 is the row that changed.** The original tranche forbade a linter outright. That was the
same error one layer lower: *a rule with no check is a suggestion* is correct, and the standard
implementation of it is CI and a linter, not a bespoke `audit-*.py` per rule. The two hand-rolled
doc checkers were deleted along with their subject and nothing caught the resulting drift at all —
which is the argument for using tooling that outlives whatever it is pointed at.

**The bound that does not move.** `ruff` and CI are development and CI tools. **No new runtime
dependency enters `backend/requirements.txt`, `backend/api/requirements.txt` or
`backend/webapp/requirements.txt`.** The reason for the stdlib rule — the pipeline runs unattended
on several machines and every added package is another thing that can be missing on one of them —
is untouched. `T-1`'s acceptance criteria include a grep proving it.

## The ordering is a requirement, not a preference

**One primitive at a time. Explain it, build it, use it once, then move on.** The reason prompts
were being repeated is not laziness — a primitive existed and was not known, so it got reinvented
in Markdown. Building a harness the owner does not understand reproduces that failure with better
tooling. **If a layer is not understood after it is built, it does not ship** — it becomes a row
in [`DEV_TASKS.md`](DEV_TASKS.md) as a question.

---

## Layer 1 — what a session knows at the start → `T-5`

`.claude/CLAUDE.md` is **214 lines and carries zero `~~` spans**, so the original's second
requirement is already met and only the length remains. Target under 150.

Keeps: what this is, the commands, the three interpreters and three suites, the architecture
invariants, a pointer to the rules and to the two task files.

`.claude/rules/`, **path-scoped so they load only when relevant** — this is where the landmines go:

| file | `paths:` | carries |
|---|---|---|
| `sql.md` | `backend/**/*.py` | `\y` not `\b`; fragments splice ahead of WHERE and their params must lead (`backend/webapp/jobs.py:303-324`); identifiers are spliced by f-string and why that is constants-only |
| `ingest.md` | `backend/ingest/**` | `upsert_checked` and read `.errors`; Workday `limit` ≤ 20; a throttled page is not the end of a list; alert on volume |
| `measurement.md` | `backend/evals/**`, `backend/tools/*.py` | the model floor, name the metric, the four eval rules, L0/L1/L2 |
| `config.md` | `backend/config/*.json` | `_comment` fields are decision records; run `relevance-report.py --dead --profile pursuit` after any pattern edit |
| `frontend.md` | `frontend/**` | no build step, no npm, `.mjs` both ways, serve on the webapp's own origin |

`docs.md` from the original is dropped — its subject was deleted. `sql.md` takes its slot.

**Run `/context` before and after and record both.** Rules that load on demand cost nothing on a
session that never touches those files; that is the whole point of the split.

## Layer 2 — who does the work → `T-6`

`.claude/agents/`. Two, both read-only, `tools: Read, Grep, Glob, Bash`, no `Edit` or `Write`:

- **`plan-verifier`** — reads a task file and the code it cites, and reports contradictions
  *before* implementation. This repo has the worked example: `47dd212` found that three of five
  findings in the preceding cleanup commits were introduced by those commits. **A plan's numbers
  being right and its claims about the code being wrong are independent failures.**
- **`artifact-reviewer`** — reads the finished diff after the suite is green. **A green suite means
  the code does what it was written to do, not that what it was written to do was wanted.**

Each must be **invoked once on real work** before the layer counts as shipped.

## Layer 3 — what decides what runs next

**Nothing is built here, deliberately, and this is unchanged from the original.** The candidates —
`/batch`, saved workflows, `/goal` — should be picked from experience, not in advance. Record the
choice as an ADR under `docs/adr/` (`T-4`); do not build all three.

## Layer 4 — what is guaranteed to happen → `T-1`, `T-2`, `T-7`

**This is the layer that carries the change.** Three pieces, in this order:

1. **CI** (`T-2`) — a GitHub Actions workflow on `liueric-dev/jobs`, running all three suites,
   `tools/audit-citations.py`, `frontend/verify_fixtures.py` and `node frontend/check_client.mjs`.
   This replaces transcribing results into commit messages by hand, which is the practice that
   wrote the citation count as 309, 308, 306 and 305 in four consecutive commits and the suite
   count four different ways in two days. **A green CI run is the claim; a number in prose is a
   rumour.**
2. **`ruff`** (`T-1`) — lint and format, configured in a new `backend/pyproject.toml`, installed
   into a dev venv that is not any of the three runtime venvs. Land against a recorded baseline
   rather than a mass reformat: a large unreviewable diff is the move that produced the documents
   this repo just deleted.
3. **The hook** (`T-7`) — `PostToolUse` on `Edit|Write` in `.claude/settings.json`, running
   `backend/tools/audit-citations.py` on the touched path. It is the one checker that survived the
   purge, it is already pinned by `backend/tests/test_citations.py`, and `.claude/CLAUDE.md` has
   been in its scope since 2026-08-03. Drift gets caught in the turn that causes it rather than in
   the next session's re-verification.

`audit-citations.py` stays as it is. It is already wired into a suite, which is the bar, and it
knows two things it cannot judge — git-ignored paths and whether a resolving line still says what
the citing comment claims. Do not let CI's arrival tempt anyone into widening its claims.

## Layer 5 — what travels → `T-8`, `T-9`

`~/.claude/`, user-level, applies to every project including ones that do not exist yet. Only ~16
of 100 measured sessions were this repo, and the other projects have no `CLAUDE.md` at all.

- `~/.claude/CLAUDE.md`: scope discipline (*do the task asked and stop*), verify-before-claiming,
  never echo credentials, enumerate the runtime environment before editing service config.
- `~/.claude/skills/whatsnew/` (`T-9`) — **this is task 53's Part B, which was never built.** The
  tranche's own diagnosis is that good engineering went one layer too low because the available
  primitives were not known; that recurs by default. Read the last-checked version from a record
  file, anchor on `code.claude.com/docs/llms.txt`, filter against what is actually in `~/.claude/`
  and this repo's `.claude/`, and report in three buckets — **replaces something hand-built** ·
  worth trying · ignore. Bucket one is the one that matters and it is the bucket that would have
  caught both hooks and CI. Manual first; automate only after it has proven useful by hand.

## Definition of done

- [ ] `.claude/CLAUDE.md` under 150 lines, still zero `~~` spans; `/context` recorded before and after
- [ ] Five path-scoped rule files exist under `.claude/rules/`
- [ ] Two read-only agents exist and **each has been invoked once on real work**
- [ ] CI is green on `liueric-dev/jobs` and its run link is in the commit that adds it
- [ ] `ruff check` runs against a recorded baseline; `grep -rn ruff backend/requirements.txt backend/*/requirements.txt` returns nothing
- [ ] The `PostToolUse` hook fires on a test edit and is **observed** to fire
- [ ] `~/.claude/` carries the cross-project rules and `whatsnew` has been run once, its first report committed
- [ ] Layer 3 is a **recorded ADR, not a build**
- [ ] **For each primitive built, one paragraph explaining what it does and why it is that slot
      rather than another.** If that paragraph cannot be written, the primitive does not ship

---
kind: contract
written: 2026-08-02
generator: none
---

# tranche_nine — retire the documentation system and replace it with the harness

**Seven tasks, 48–54. This tranche has a hard ceiling and it is the point of the tranche.**

## Why this exists

Tasks 36–47 were twelve consecutive tasks of documentation infrastructure. Every one landed
green and the work was correct. It also produced **no product movement**, and the tree grew to
~46,000 lines of Markdown against ~74,500 lines of Python — **1,730 Markdown edits against 1,352
Python edits** over the measured window (`/insights`, 2026-08-02).

The diagnosis is not carelessness and not a missing rule. It is that **this repo answers five
different questions with one instrument.**

| the question | what should answer it | what answers it today |
|---|---|---|
| what does a session know at the start | `CLAUDE.md`, path-scoped rules, skills | one 255-line `CLAUDE.md` plus "go read these docs" |
| who does the work | subagents, forks, background sessions | hand-rolled subagents and worktrees |
| what decides what runs next | Claude, a lead agent, or a script | the owner, typing |
| what is guaranteed to happen | hooks, permission rules, goal conditions | prose, plus `audit-docs.py` |
| where state lives between sessions | `/resume`, checkpoints, auto memory, files | ~46,000 lines of Markdown |

A Markdown file is a good answer to row 5 and a bad answer to row 4. `DOCS-POLICY.md` rule 7 —
*a rule with no check is a suggestion* — is the right principle implemented one layer too low.

**This tranche moves each answer to its row.** It does not throw the thinking away. Rule 7,
`MEASUREMENT-TRAPS.md`, the `_comment` convention and the landmines all survive; they change
address, not status.

## The ceiling

**There is no task 55.** If this tranche discovers work — and it will, because tasks 44 and 47
both did — the finding goes to `OWNER-QUEUE.md` or `DECISIONS.md`. It does not become an eighth
task. The failure mode this tranche exists to correct is *a meta-project that grows*, and a
meta-project about meta-projects that grows is the same defect with better branding.

**Every task file in this tranche is under 150 lines** and that is a deliberate demonstration,
not a shortcut. `47-split-the-entry-point.md` is 260 lines about a document being too long.

## Order

Strictly sequential. 49 is the load-bearing one and everything after it depends on its output.

| | task | lands |
|---|---|---|
| 48 | [Stop clean](48-stop-clean.md) | a green, committed, known state to cut from |
| 49 | [Orientation from the code](49-orientation-from-code.md) | `docs/STATE-OF-THE-SYSTEM.md`, written from code and git, **not from the docs** |
| 50 | [Extract the durable core](50-extract-durable-core.md) | the ~300 lines out of ~46,000 that cannot be regenerated |
| 51 | [Archive the rest](51-archive-the-rest.md) | `git mv`. Nothing deleted. Tree under 8,000 lines |
| 52 | [Build the harness](52-build-the-harness.md) | `.claude/` and `~/.claude/` — each row of the table above, answered in its own slot |
| 53 | [Owner queue and the changelog routine](53-owner-queue-and-changelog.md) | one file that says what is on the owner, with instructions; a standing ecosystem check |
| 54 | [Re-plan the product work](54-replan-the-product.md) | a new, small task list against 49's understanding |

## What this tranche must not do

- **Not delete anything.** 51 is `git mv` and stubs. `git log` reaches everything either way;
  the stubs are so an inbound citation still lands.
- **Not rewrite `DECISIONS.md`.** It is append-only rationale and it is the single most valuable
  file in the repo *because* the owner has lost the thread. It is the only artifact that answers
  "why is it like this" for a system nobody currently holds in their head.
- **Not add a linter.** `DOCS-POLICY.md` § *What this policy deliberately does not change* is
  explicit and it stays explicit. Any recommendation to wire `ruff` into a hook is wrong for this
  repo regardless of where it came from.
- **Not touch product code.** 54 plans it; nothing here implements it.

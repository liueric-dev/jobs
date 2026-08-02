---
kind: task
written: 2026-08-02
generator: none
---

# 53 — one file for what is on the owner, and a standing check on the ecosystem

**Status:** TODO. **Depends on:** 49 § 4 (the *needs the owner* list), 51, 52.
**Blocks:** 54.

Two standing needs, one task, because both are the same shape: **a thing the owner must track
that currently has no home and therefore lives in their head.**

---

## Part A — `docs/OWNER-QUEUE.md`

### The problem, stated precisely

"What is on me" is currently derivable only by reading five documents and cross-referencing:
`README.md`'s status column, `HANDOFF.md`'s *what is next*, `OPEN-QUESTIONS.md`, `DECISIONS.md`
for the open ones, and inside individual task files. **State distributed across prose is the
same disease this whole tranche exists to treat**, and here it has the sharpest cost: five of
the eight open items need a machine, an account, a device, other people or a decision, and none
of them can be started by a session. They are the critical path, and they are the least visible
thing in the repo.

`OPEN-QUESTIONS.md` is already most of the answer — `kind: rolling`, owns `OQ-`, eight rows, six
open and every one the owner's. What is missing is that it records **the question and not how to
do the thing**, and that it is not the complete set.

### The move

**Rename `OPEN-QUESTIONS.md` → `docs/OWNER-QUEUE.md` and keep the `OQ-` prefix.** No
renumbering — C5 stays satisfied, existing citations keep resolving, and a namespace migration
is exactly the kind of work this tranche has a ceiling to prevent. Promote it out of
`docs/tasks/refactor/` because it outlives the refactor.

Absorb every owner-blocked item found by 49 and every one stranded in `STANDING-GUIDANCE.md`
before 51 archives it. **After this task, anything anywhere that says "the owner's" links here
rather than restating** — rule 2, applied to work rather than to figures.

### The row format, and the fourth column is the point

| field | what it holds |
|---|---|
| **`OQ-n`** | the identifier, allocated here |
| **What** | one sentence |
| **Why it is the owner's** | machine · account · device · people · decision. **The category, because it determines whether waiting helps** |
| **How to do it** | concrete steps. Commands where there are commands, the actual decision and its options where it is a decision, who to ask where it is people |
| **What it unblocks** | task IDs. This is what makes the queue orderable |
| **How you would know it is done** | a check, not a feeling |

The fourth column is why this file exists rather than a checkbox list. Losing track of what is
on you is only half the problem; the other half is opening the item and having to reconstruct
what it involved. **A decision row carries the options and the recommendation** — `DEC-84`'s
three options for the credential-issuing page is the model.

`kind: rolling`, `budget: 250`, so C7 enforces it. When it grows past that, rows have been
written as narrative and the fix is to move the narrative out — not to raise the budget.

### Surfacing it

`HANDOFF.md` § *what is next* points here in one line. The `resume` skill from 52 reports
**how many owner rows are open and what they unblock** before picking a task, so the queue is
seen every session without being read every session.

---

## Part B — the ecosystem check

### Why this is not optional

The whole diagnosis of this tranche is that good engineering went one layer too low because the
available primitives were not known. **That failure recurs by default**, since the platform ships
weekly and a model's own training data is stale about it. `DOCS-POLICY.md` rule 7 was derived
independently and implemented in Python, months after hooks existed for exactly that.

### The skill

`~/.claude/skills/whatsnew/SKILL.md` — **user-level, because it is not about this repo.**

1. Read the last-checked version from a local record file.
2. Fetch the weekly digest and the changelog since then. Anchor navigation on
   `code.claude.com/docs/llms.txt`, the machine-readable docs index, rather than on recalled
   URLs or training data.
3. **Filter against the actual setup** — what is in `~/.claude/` and this repo's `.claude/`.
   A feature for a stack not in use is noise.
4. Report in three buckets: **replaces something hand-built** · **worth trying** · **ignore**.
   Bucket one is the one that matters and it is the bucket that would have caught hooks.
5. Append to a `kind: record` file. Frozen on write, so it cannot accrete.

Manual first. Once it has run a few times and the output is useful, a `/loop` or a scheduled
routine can drive it — **but not before it has proven useful by hand**, because an unread
automated report is worse than no report.

Note for anyone reading this file later: `.claude/commands/` is the legacy format. Skills are
current and support both `/name` invocation and autonomous matching.

## Definition of done

- [ ] `docs/OWNER-QUEUE.md` exists, `kind: rolling`, `budget: 250`, owns `OQ-`, under budget
- [ ] Every open owner-blocked item from 49 § 4 is a row, and **every row has a non-empty
      *How to do it***
- [ ] No document outside it restates an owner-blocked item; all link
- [ ] `HANDOFF.md` points here in one line and did not grow otherwise
- [ ] The `resume` skill reports the open owner count
- [ ] `whatsnew` exists at user level, **has been run once**, and its first report is committed
- [ ] The first report's *replaces something hand-built* bucket is non-empty or explicitly empty
      with a reason

---
kind: task
written: 2026-08-02
generator: none
---

# 54 — re-plan the remaining product work, and close the run

**Status:** TODO. **Depends on:** 49, 51, 52, 53. **Blocks:** nothing. **This is the last task
in the tranche and there is no task 55.**

## What this task is for

The refactor's remaining work is currently described by a 47-row index, six `in progress` rows
whose bodies contain amendments to amendments, and a set of planning documents archived by 51.
**None of that is a plan any more; it is a history of one.** This task writes a small new list
against `STATE-OF-THE-SYSTEM.md` — what the system actually is — rather than against what was
intended for it eight tranches ago.

## The constraint that shapes it

From 49 § 4, and it should be read carefully before any planning happens: **most of what is left
is not session-doable.** The deploy half of 24, the machine half of 33, the phone test and live
Google login in 32, the labelling in 29, the ownership decision behind `Contribute` — these need
a machine, an account, a device, other people, or a decision. They are now rows in
`OWNER-QUEUE.md`.

So the plan splits cleanly and **the split is the deliverable**:

- **Owner rows** — already in `OWNER-QUEUE.md` with instructions. Not tasks. Ordered by what
  they unblock.
- **Session-doable work** — a small numbered list, in the existing convention, in a new tranche.

If the second list is very short, **that is a finding and not a failure.** It means the refactor
is done and the project is waiting on the owner, which is a far more actionable position than
"the refactor is enormous and I am lost."

## How to write the task files this time

The convention stays; the size does not. This run's task files run to 300–800 lines, and
`47-split-the-entry-point.md` is 260 lines about a document being too long. Every file in
tranche nine is under 150. Carry that forward:

- **A task file states the work and the Definition of done.** The findings from doing it go to
  `DECISIONS.md` and the session record, not back into the task file as a growing preamble.
- **Machine-checkable acceptance criteria** — exact commands and what they should print. This is
  what `plan-verifier` reads, and what any future `/batch` or workflow run needs as input.
- **Every task gets run through `plan-verifier` before implementation.** Its numbers being right
  and its claims about the code being wrong are independent failures.

## Closing the run

1. **Retire `HANDOFF.md` for the refactor.** Its subject has landed; `DOCS-POLICY.md` rule 4's
   second half says a rolling document whose subject has landed is archived in the same commit
   that lands it. The new tranche gets its own entry point, or — better — `OWNER-QUEUE.md` plus
   `STATE-OF-THE-SYSTEM.md` plus a status column turn out to be sufficient and there is no
   handoff document at all. **Try that first.** The `resume` skill and `/resume` now do what
   the handoff was built to do, and the handoff was a context-scarcity artifact in a world where
   context is 2% full.
2. **Final measurement**, all reported with their commands: Markdown line count against the
   ~46,000 at the freeze; `/context` at session start against the 23.4k baseline; all three
   suites; both doc checkers.
3. **One `kind: record` session file** closing the tranche. What was carried, what was archived,
   what the harness replaced, and — the useful part — **what this tranche got wrong**, because
   44 and 47 both found their own premises wrong by one and that is the most reusable thing
   either produced.

## Definition of done

- [ ] A new tranche exists with session-doable tasks only, every file under 150 lines, every one
      carrying machine-checkable acceptance criteria
- [ ] Every non-session-doable item is an `OWNER-QUEUE.md` row and appears in no task file
- [ ] `HANDOFF.md` is retired or explicitly justified as still needed, with the reason recorded
- [ ] The final measurements are recorded with the command that produced each
- [ ] `DECISIONS.md` carries an entry for the tranche as a whole: what the documentation system
      was for, why it grew to ~46,000 lines, and what replaced each of its five jobs
- [ ] **No task 55 exists.** Anything discovered late is an `OWNER-QUEUE.md` row or a
      `DECISIONS.md` entry

## The thing this tranche is most likely to get wrong

**That it becomes tranche seven again.** Twelve tasks of infrastructure, all green, no product.
The guard is the ceiling, and the ceiling only works if it is enforced when it is inconvenient —
which will be around task 51, when the archive sweep turns up something interesting and the
obvious move is to open a task for it. **Do not.** Write it down and keep going.

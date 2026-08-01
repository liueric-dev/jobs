---
kind: task
written: 2026-08-01
generator: none
---

# 44 — `HANDOFF.md` is two documents; archive the frozen half

**Status:** DONE, 2026-08-01. **Depends on:** 40, done (`6b74e0b`, `8e9e343`, `6b6ae71`) —
the entry point is already rolled forward and the method already promoted. **Blocks:**
nothing, but one declared allowance in `backend/config/doc-figures.json` existed only until
this landed, and it is now removed.

> **One premise of this file was wrong, and it changed the work.** § *How it surfaced* says
> the nineteen restatements are all *"below line 380"* and § *The work* says that a red C4
> after the move means *"something that should have been archived was not"*. Seventeen of the
> nineteen behaved that way. **The other two sat in live `rolling` sections** — a
> `suite 1030 → 1058` delta inside the next-steps list and a `Suite 1171 → 1178` delta inside
> an open follow-up — where archiving them would have archived current content. Both became
> **citations of a document that already carried the pair** (`docs/archive/handoff-gate-fix.md`
> and `CLAUDE_UPDATES.md`), which is rule 2's fix rather than rule 4's move, and no figure was
> lost. **A figure inside a rolling document is not evidence that the section around it is
> history.**
>
> **What landed:** § *State at handoff* and § *What 08, 12 and 19 changed about the plan* →
> [`docs/archive/handoff-state-2026-07-31.md`](../../../archive/handoff-state-2026-07-31.md).
> § *Nothing is in flight* → [`docs/archive/handoff-tree-state.md`](../../../archive/handoff-tree-state.md),
> **minus two parts**: its FAQ is standing guidance and stayed, and its four cross-stream
> lessons were promoted to [`docs/MEASUREMENT-TRAPS.md`](../../../MEASUREMENT-TRAPS.md) under
> rule 5 — they are about a shared database and a pinned set, not about this cohort or model.
> The one edit to the moved text was repointing four `](AUDIT.md)` links, which are relative
> and stopped resolving one directory over; `audit-doc-links.py` named the fix.

## The finding, and it came from a check rather than from a reading

`HANDOFF.md` is the tree's only `kind: rolling` document. Rule 1 says a rolling document is
rewritten each session and **may not be stale**.

It is also, below roughly line 380, a **frozen session narrative** — what was measured on
which night, which numbers were superseded by which, struck-and-kept sequences like
`~~1107~~ ~~1160~~ ~~1166~~ ~~1171~~ 1178`. That content is a `record` by every test rule 1
gives: it is history, it says so, and **rewriting it would destroy the evidence rule 4
exists to keep**.

**Rule 1 has no name for one file with two lifecycles.** That is the finding.

### How it surfaced

Task 38 registered the main suite test count in `doc-figures.json` and allowed `HANDOFF.md`
**nowhere**, arguing — correctly on what it knew — that the only `rolling` document in the
tree is the worst possible exemption, since it is the live entry point every session reads
first.

Check C4 then found **nineteen** restatements in that file. Every one is below line 380:
none in the START HERE block, none in the three standing `READ THIS FIRST` sections. Those
were cleaned in 40a and stay clean. So the strict reading and the evidence disagreed, and
the allowance was granted with the disagreement written into `_allowed_note` rather than
smoothed over.

**Until this task lands, that row is blind to `HANDOFF.md`, and that is a known hole rather
than a clean result.**

## The work

**Move the frozen narrative to `docs/archive/`**, with the provenance header
[`docs/archive/README.md`](../../../archive/README.md) requires — what it measured, when,
and what superseded it — and a stub and link where each section was, so inbound citations
still land (rule 4).

**What must NOT move**, and task 40 already argued this about the file: the three standing
`READ THIS FIRST` sections are **standing**. One open track (task 29) and two findings later
work must not re-derive. They are the file's whole remaining job. The four that described
finished work were archived by task 34; do not treat "old" as "finished".

**Then remove the allowance.** Delete `docs/tasks/refactor/HANDOFF.md` from the
`main suite test count` row's `allowed` list in `backend/config/doc-figures.json` and strike
the paragraph in its `_allowed_note` that explains it. If C4 goes red after the move,
**something that should have been archived was not** — that is the check doing its job, not
a reason to keep the exemption.

## Definition of done

| | item | how it is checked |
|---|---|---|
| | The frozen narrative is under `docs/archive/` with a provenance header | `python3 backend/tools/audit-docs.py --check C6` — clean |
| | `HANDOFF.md` retains exactly its three standing sections | `grep -c '^## READ THIS FIRST' docs/tasks/refactor/HANDOFF.md` is 3 — **note the `^##` anchor**; without it the count is 5, two of them prose |
| | A stub and link remain where each moved section was | read them; `audit-doc-links.py` reports 0 |
| | `HANDOFF.md` is removed from the `allowed` list and C4 is still 0 | `python3 backend/tools/audit-docs.py --check C4` |
| | `doc-policy-baseline.json` still has empty `findings` everywhere | it is pruned, never grown |
| | Both suites green and not smaller | read `Ran N tests` from each — the floor is the reading you take before starting |

## Out of scope

- **Compressing `HANDOFF.md` for its own sake.** Task 34 took it from 3,481 lines to ~2,690
  by moving *finished* content. Length is not the target; the lifecycle split is.
- **Rewriting any moved figure.** They are the record of the drift. Struck-and-kept, moved
  verbatim.
- **A sixth `kind:`.** Task 37 found the same gap from the other direction — the three dated
  planning documents have no `plan` kind either. Whether the taxonomy grows is a separate
  decision and needs both cases argued together, not one task inventing a label.

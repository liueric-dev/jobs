---
kind: decision
written: 2026-08-03
generator: none
---

# 0002 — Task 51 deleted 137 documents where its spec said `git mv` and stubs

**Status:** accepted after the fact, 2026-08-03. Recorded here because it was taken in `5046f98`
and written down nowhere — which is itself an instance of the problem this directory exists to fix.

## Context

Tranche nine's task 51 was *archive the rest*. Its README was explicit about the method:
**"Not delete anything. 51 is `git mv` and stubs."**
(`git show refactor-freeze-2026-08-02:docs/tasks/refactor/tranche_nine/README.md`).

`5046f98` deleted 137 files and 42,777 lines under `docs/` and left no stubs at all, replacing the
whole tree with one file written from the code. The deviation was not argued in the commit and no
register recorded it; it surfaced only when [`../../DEV_TASKS.md`](../../DEV_TASKS.md) was written
and the tranche's state had to be reconciled row by row (`../../DEV_TASKS.md:442-445`).

The reasoning that justified it is sound and worth preserving. An audit found 168 places where those
documents contradicted the code. A stub that points at a document which was wrong is a slower path
to the same wrong answer, and the surviving `docs/` tree would have kept implying that reading it
was how you learn this system. The tag `refactor-freeze-2026-08-02` preserves every byte, so nothing
was destroyed — the question was only what a reader finds by default.

## Decision

Stand by the deletion. Do **not** restore `docs/` wholesale, and do not add stubs retroactively.
When a deleted document is needed, pull the one file out of the tag and put it where the code that
needs it lives:

```bash
git show refactor-freeze-2026-08-02:docs/tasks/refactor/DECISIONS.md
git ls-tree -r --name-only refactor-freeze-2026-08-02 docs/
```

Record the deviation rather than the intent: the spec said `git mv`, the commit deleted, and the
delete was the better call.

## Consequences

- **The bill was four commits.** `c052f23`, `25c8f19`, `47dd212` and `3644eba` repointed links the
  purge left dangling, corrected counts, and fixed the survivor where re-checking refuted it.
  `47dd212` found that three of five findings in the preceding cleanup commits had been *introduced*
  by those commits. Deleting a documentation tree is not free even when it is right.
- `DECISIONS.md` went with it and nothing took its slot for a day. This directory is that slot
  (`T-4`).
- The citation checker `backend/tools/audit-citations.py` treats a bare `docs/…` path as a finding
  and the `git show refactor-freeze-2026-08-02:<path>` form as valid, deliberately. It does not
  validate the path behind the tag, so get it right by hand.
- The durable lesson, from `../STATE-OF-THE-SYSTEM.md:406-411`: every high-severity finding was a
  document describing a state of the world that had since changed. **Not one had ever been false
  when written.** That is the argument for few documents, and for rationale over description.

---
kind: task
written: 2026-08-02
generator: none
---

# 51 — archive the narrative surface; keep the registers

**Status:** TODO. **Depends on:** 50, complete and reviewed. **Blocks:** 52.

**Nothing is deleted by this task.** Every move is `git mv` plus a stub, following
`docs/archive/README.md`: a provenance header saying what it was, when, and what superseded it,
and a stub left where the content was so an inbound citation still lands. `git log` reaches
everything regardless; the stubs are for readers, not for recovery.

## What goes, and why each one

| file | lines | disposition |
|---|---|---|
| `CLAUDE_UPDATES.md` | 2,993 | **Archive.** A per-session changelog. `git log` and `sessions/` both already hold this, and it silently stopped being written for four sessions once without anything going red |
| `STANDING-GUIDANCE.md` | 1,697 | **Split, then archive the remainder.** 26 struck spans, three `## READ THIS FIRST:` sections and four `## ARCHIVED:` sections in one `contract`. Live rules → `.claude/rules/` (52). Blocked-on-owner rows → `OWNER-QUEUE.md` (53). What is left is history |
| `tranche_seven/*`, `tranche_eight/*` | ~13 files | **Archive as a set.** Twelve task files documenting completed documentation work. The lessons are in `DECISIONS.md` and `WORKING-METHOD.md` |
| `MASTER-PLAN-pursuit.md`, `SOURCING-STRATEGY.md`, `ADDENDUM-google-jobs-providers.md` | ~1,190 | **Archive.** Planning documents for a plan that has been executed and amended past recognition. 49's output supersedes them |
| `AUDIT.md` | 300 | **Archive, after 49 confirms every figure it owns has moved.** It owns run-level figures; `STATE-OF-THE-SYSTEM.md` § 6 is the new owner. **Do not archive it until C4's owner map is updated**, or the check will fire |
| `LABELLING-NIGHT.md` | 556 | **Archive.** Operational reference for one night that has passed |
| `docs/ingestion_tests/` | ~700 | **Archive.** Its own README already says the tasks moved |

## What stays, and this list is short on purpose

`DECISIONS.md` · `DEFECTS.md` · `OPEN-QUESTIONS.md` (becomes `OWNER-QUEUE.md` in 53) ·
`HANDOFF.md` · `README.md` (the status column) · `DOCS-POLICY.md` · `WORKING-METHOD.md` ·
`MEASUREMENT-TRAPS.md` · `STATE-OF-THE-SYSTEM.md` · `sessions/` · `docs/ingest/*.md` ·
`RUNBOOK.md` · the per-process READMEs · all task files for tasks that are **not** done.

## The three checks this will break, and that is expected

Archiving at this scale moves text between directory depths, which is the exact operation that
broke **47 relative links** in task 47. Budget for it:

1. **C2 (orphans)** fires for anything the index no longer reaches. Fix the index, not the check.
2. **C4 (one figure, one owner)** fires if `AUDIT.md` moves before its figures are re-owned.
   Order matters: re-own first.
3. **`audit-doc-links.py`** will report a large number. It gives a unique target where one
   exists and **refuses to guess where it does not** — that refusal is the behaviour that stops
   a sweep inventing a file. Run it from the repo root with the path passed explicitly.

Land red if the checkers are red, and fix forward. **A sweep whose first run is green has been
tested against nothing** — this run's own precedent, tasks 36 and 47.

## The measurement that closes this task

```bash
find . -name "*.md" -not -path "./.git/*" -not -path "./docs/archive/*" -exec cat {} + | wc -l
```

**Target: under 8,000 lines, from ~46,000.** Report the number; do not type it into a document
that is not this task's record.

## Definition of done

- [ ] Every move is `git mv`. **Zero `rm`.** `git status` shows renames, not deletions
- [ ] Every archived file has a provenance header and a stub at its former location
- [ ] `audit-docs.py` and `audit-doc-links.py` both green **from the repo root** at the end
- [ ] Live tree under 8,000 lines of Markdown, excluding `docs/archive/`
- [ ] All three suites still green — **archiving documentation must not touch code**, and if a
      test fails, something was moved that a test reads
- [ ] `DECISIONS.md` byte-identical to its state at the freeze tag

## The thing to watch for

**The urge to fix a stale claim while moving it.** Do not. A file being archived does not need
to be correct; it needs a header saying what superseded it. Correcting text on the way to the
archive is how a one-day sweep becomes a week.

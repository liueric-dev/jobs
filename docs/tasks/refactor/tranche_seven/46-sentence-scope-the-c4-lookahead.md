---
kind: task
written: 2026-08-02
generator: none
---

# 46 — C4's compliance lookahead is line-scoped; the claim is a sentence

**Status:** todo. **Depends on:** 36 (C4), 38 (the patterns and their `_pattern_note`
counts). **Blocks:** the `backend` suite going green, together with 45.

**C4 reports two findings on `.claude/CLAUDE.md` that are false positives, and the file is
right both times.** The check is what is wrong.

## The defect

`backend/config/doc-figures.json`'s rows make a line compliant when it names its metric or
cites the figure's owner. **That lookahead is scoped to the physical line.**
`.claude/CLAUDE.md` is hard-wrapped at ~88 columns, so a compliant sentence can put the
figure on one line and the token that licenses it on the next:

| finding | the figure | where the licence actually is |
|---|---|---|
| `.claude/CLAUDE.md:121` | `94.8%` … `85.2%` | `` `agree2` `` on line 122 — *"n=115, both **`agree2`** (task 06)"* |
| `.claude/CLAUDE.md:190` | `~~1182~~` | `AUDIT.md` cited on line 191, and the number is struck |

Join either paragraph and it satisfies rule 3's corollary exactly as written. **The unit of
the claim is the sentence. The unit of the check is the line.**

The second one is doubly compliant: the figure is *struck through* and the surrounding
prose exists to say it was wrong. A check that flags a number whose own sentence disowns it
is measuring the wrong thing twice.

## Why task 38 did not see this

38 measured every one of these patterns line-by-line over `docs/`, and no registered figure
there happened to straddle a wrap. The design was correct against the corpus it was
measured on. **Widening the scanned set to the two roots is what changed the corpus** — it
added the one file in the repo that is hard-wrapped narrow enough and dense enough with
owned figures for the two units to come apart. This is the same shape as
[`MEASUREMENT-TRAPS.md`](../../../MEASUREMENT-TRAPS.md)'s entries: the instrument was
fine until the population moved.

## The work, and the trap inside it

Re-scope the compliance lookahead from the line to the sentence or paragraph, and
**re-record the `_pattern_note` counts in `backend/config/doc-figures.json`** — they are
line-measured and will not survive the change.

> **Widening a match can only ever CLEAR findings, never add them.** So this task can make
> the check pass without making it better, which is exactly the failure
> [`DOCS-POLICY.md`](../../../DOCS-POLICY.md) rule 7 exists to prevent. The measurement
> is not "does it go green" — it is **how many findings the widening clears tree-wide, and
> whether every one of them is a true false-positive on inspection.** If it clears anything
> in `docs/` that was a real restatement, the scope is too wide and the answer is a
> narrower rule, not a bigger window.

Report that count. A silent green here is worse than the red it replaces.

## Definition of done

- The lookahead is scoped to the claim rather than the line, with the chosen unit stated.
- Every finding the change clears tree-wide is listed and individually confirmed to be a
  false positive. The count is in the task record.
- `_pattern_note` counts in `doc-figures.json` re-recorded against the new scope.
- `python3 backend/tools/audit-docs.py` reports 0 C4 findings; C1 clears with task 45.
- The declared baseline is still empty — nothing here is fixed by declaring it.

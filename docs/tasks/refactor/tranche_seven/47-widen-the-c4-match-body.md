---
kind: task
written: 2026-08-02
generator: none
---

# 47 — C4's *match* is still line-scoped, and it has two known false negatives

**Status:** todo. **Depends on:** 46 (which scoped the *licence* to the sentence and left
the match alone, deliberately — `DEC-78`). **Blocks:** nothing.

Task 46 corrected C4's compliance lookahead from the physical line to the enclosing
sentence, and exempted struck figures. **It deliberately did not touch the match body**, so
`check_figures` still asks its question one line at a time. That is a strict-subset change
by construction and was the right scope for that task. This one is the other half, and it
is a *different* kind of change with a different risk profile.

## Why this is not a tidy-up

Task 46's own text states a law:

> **Widening a match can only ever CLEAR findings, never add them.**

**That is false for the three proximity rows in `backend/config/doc-figures.json`** — the
rows whose patterns require a figure and a nearby token on the same line. Widening the match
to a sentence or paragraph makes those rows see pairs that a line cannot hold. Measured
2026-08-02 during task 46: a paragraph-scoped match **clears 10 and invents 2**.

**Both invented matches are real.** Neither is a regex artefact:

| | what straddles the wrap |
|---|---|
| [`../LABELLING-NIGHT.md`](../LABELLING-NIGHT.md)`:508-509` | `at the measured 93` / `s/posting` — the labelling-rate figure and its unit |
| [`../tranche_five/29-labelling-session.md`](../tranche_five/29-labelling-session.md)`:791-792` | `` `backend/webapp/` `` ends the line above `` `Ran 93 tests` `` |

So **the line-scoped match has false negatives of exactly the same shape as the false
positives task 46 removed.** A figure hard-wrapped away from the token that identifies it is
invisible in one direction and was a spurious finding in the other. Both sit in files those
rows already `allow`, so neither is a finding today — which is precisely why this can wait,
and precisely why it will not surface on its own.

## The trap, and it is the mirror of task 46's

Task 46's deliverable was *"the list of findings the change clears, each confirmed a true
false positive"*, because widening a licence can only quieten a check and a silent green is
worse than the red it replaces.

**Here the risk runs the other way.** Widening the match can only ever *add* findings, so
this task cannot go quietly green — it will go red, and the deliverable is:

- **Every finding the widening adds, tree-wide, each individually confirmed as a genuine
  restatement rather than a regex artefact.** A pair that a sentence brings together but
  that means two different things is a false positive, and it is the failure mode to expect:
  the proximity rows use nearness as a proxy for "these two tokens are about each other",
  and the wider the window the weaker that proxy gets.
- **A decision on the unit**, which need not match `DEC-78`'s. The licence and the match are
  different questions and there is no reason the same window serves both. State it either
  way.
- **`_pattern_note` re-recorded again** for whichever rows move. They were re-measured under
  the new licence scope on 2026-08-02 and carry both the 2026-08-01 line-scoped figures and
  the current ones; a third column is fine, overwriting the second is not.

## What must not happen

**Do not add anything to the declared baseline.** It is pruned, never grown, and it has been
empty since task 36. Findings this surfaces are documents to fix or `allowed` globs to
declare with a written reason, in that order of preference.

**Do not widen the match to make the two known instances match and stop there.** Two
instances found while looking for something else are evidence that the class exists, not a
measurement of it. The population is every registered figure in every scanned file.

**Do not assume the answer is "widen".** A defensible outcome is that the proximity proxy
does not survive a wider window and the right fix is a narrower rule — an explicit
`_licence_tokens` list per row, say — or that the two known instances are better fixed by
unwrapping two lines in two documents. **Measure first; the deliverable is the decision.**

## Definition of done

- The unit chosen for the match body is stated, with the measurement behind it.
- Every finding the change adds is listed and individually confirmed genuine or artefact.
  The count is in the task record.
- The two known instances above are resolved one way or the other, explicitly.
- `_pattern_note` counts re-recorded for whichever rows moved, keeping the earlier
  measurements rather than overwriting them.
- `python3 backend/tools/audit-docs.py` exits 0, and the declared baseline is still empty.

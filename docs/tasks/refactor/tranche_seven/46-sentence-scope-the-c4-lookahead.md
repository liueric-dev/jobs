---
kind: task
written: 2026-08-02
generator: none
---

# 46 — C4's compliance lookahead is line-scoped; the claim is a sentence

**Status:** DONE 2026-08-02, **with one of its two premises wrong** — see *What the work
turned up*. **Depends on:** 36 (C4), 38 (the patterns and their `_pattern_note` counts).
**Blocks:** the `backend` suite going green, together with 45.

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

## What the work turned up

### The premise above is wrong on `:190`, and right on `:121`

**The table in *The defect* says both findings are the same defect. They are not.** Of the
nine rows in [`doc-figures.json`](../../../../backend/config/doc-figures.json), eight carry
a `^(?![^\n]*…)` compliance lookahead and **`main suite test count` carries none** — it is
a bare band, `1[0-9]{3}` with lookarounds. There is nothing in that row for a wider scope to
satisfy: join the paragraph at `:190` on a space and it still matches `1182`. Verified
before any code was written, and it is why re-scoping alone could never have taken C4 to
zero.

The licence `:190` actually has is the one this file already noticed and then filed as a
bonus — **the figure is struck**: `~~**1182** as of 2026-07-31~~, in a sentence whose
entire purpose is to say the number was wrong. `DOCS-POLICY.md` rule 4 mandates
struck-and-kept, and **235 struck spans across 48 documents under `docs/`** are complying
with it. A check that reports a number its own sentence disowns penalises the single
behaviour the policy requires outright, which is how a check gets switched off.

So this landed as **two independent fixes**, and each clears exactly one of the two
findings.

### The unit is the sentence, and the match did not move

The licence is now tested against the **sentence** — a maximal run of consecutive non-blank
unfenced lines, joined **with a space**, split at `.`/`!`/`?` followed by whitespace. Not
the paragraph: measured 2026-08-02, the sentence licenses 3 lines and the paragraph 7, and
the extra 4 are figures licensed by a token belonging to a *different* claim that happens to
be adjacent. This task says the answer to over-clearing is a narrower rule, so the narrowest
unit that clears the false positive is the one that landed.

**Three traps, all of which bit something:**

- **Joining on `\n` looks right and is silently catastrophic.** Every pattern uses `^`
  without `re.MULTILINE` and `[^\n]*`, so a newline in the block confines *both* the
  lookahead and the match to the block's first line. The check reports fewer findings and
  looks fixed while having gone blind to every figure below a paragraph's first line, which
  is most of them. Pinned by `test_c4_sees_a_figure_below_a_paragraphs_first_line`.
- **`[^\n]*` is greedy, so a later copy shadows an earlier one.** The first implementation
  matched the sentence per occurrence and intersected on end offsets; that cleared
  `docs/ingestion_tests/README.md:268`, a real restatement of the `hn_whoishiring`
  per-platform cell in a gate table, purely because an identical copy of it sat two lines
  below. (This paragraph quoted that cell on the first attempt and C4 fired on it — the
  eleventh finding of the session, in the file arguing the check should be narrower, and
  the reason it is written this way now.) The licence test is therefore **binary
  per sentence** — falsify the lookahead and an anchored pattern matches nowhere in the
  sentence, which is exactly the question being asked.
- **Fence-skipping had to survive the grouping.** A gap in the line numbers
  `outside_fences()` yields means a fence was skipped, and that ends the run.

### “Widening a match can only ever CLEAR findings” — this task's own claim is false

It is true of a lookahead and **false of these patterns**. Three rows are *proximity*
patterns (`\bwebapp\b` within 60 characters of `93`; `93\s*s\b`; `\bai_involvement\b` within
60 of `50%`), and running one against a joined paragraph pairs a keyword on one line with a
number on the next. Measured over `docs/` plus the two roots, **a naive paragraph re-scope
invents 2 matches while clearing 10.**

**Both invented matches are real**, which is the more interesting half:
`tranche_five/29-labelling-session.md:792` (`backend/webapp/` ends the line above `Ran 93
tests`) and `LABELLING-NIGHT.md:508-509` (`at the measured 93` / `s/posting`). The line
scope has **false negatives of exactly the shape as its false positives**; both sit in files
those rows already allow, so neither is a finding today. Widening the *match* is a real
follow-up with its own measurement and its own decision — it is not this change.

So the implementation keeps the match line-scoped and widens only the licence, which makes
the new finding set a **strict subset of the old one by construction** rather than by
argument.

### The measurement this task asked for

Tree-wide over every scanned file, ignoring `owner` and `allowed` so that what is measured
is the *pattern*: **145 matching lines before, 135 after — 10 cleared, 0 invented.** Every
one inspected individually, and none was a real restatement:

| # | where | cleared by | why it is a false positive |
|---|---|---|---|
| 1 | `docs/archive/handoff-state-2026-07-31.md:31` | struck | `~~1107 is the floor now…~~` |
| 2 | `docs/archive/handoff-state-2026-07-31.md:56` | struck | `~~**1070 is…~~` |
| 3 | `docs/archive/handoff-state-2026-07-31.md:95` | struck | `~~**1166 and 75 are the floors…~~` |
| 4 | `docs/archive/handoff-state-2026-07-31.md:96` | struck | `~~**1171 and 93 are the floors now** (2026-07-31).~~` |
| 5 | `docs/archive/handoff-tree-state.md:31` | struck | `1166` inside a strike spanning `:30-32` |
| 6 | `tranche_seven/46-…md:25` | struck | this file's own table quoting `~~1182~~` |
| 7 | `.claude/CLAUDE.md:196` | struck | **the finding.** `~~**1182** as of 2026-07-31~~` |
| 8 | `.claude/CLAUDE.md:127` | sentence | **the finding.** `n=115, both **`agree2`**` on the next line |
| 9 | `docs/ingestion_tests/selfcheck-n120-2026-08-02.md:159` | sentence | table row licensed by its own column header at `:146`, `\| field \| agree2 \| 95% CI \| unanimous \| pairwise \|` |
| 10 | `docs/tasks/refactor/DECISIONS.md:73` | sentence | `` `ai_involvement` pairwise agreement by platform: `` opens `:72`; the wrap puts `**hn_whoishiring 77.8%**` on `:73` |

Six of the seven struck lines and both of the non-root sentence lines sit in files their row
already allows, so **only rows 7 and 8 were findings**. The rest is the pattern behaving
better on documents that were never being reported.

**Row 10 is the result that matters most.** This task assumed the two roots held the only
figures straddling a wrap — *"no registered figure there happened to straddle a wrap"*.
`DECISIONS.md:72-73` is a second instance, in `docs/`, that task 38's line-by-line sweep
also could not see. The instrument was wrong before the population moved; widening the
scanned set is what made it *visible*, not what made it *true*.

### `_pattern_note`s

Re-recorded for all nine rows, with the shared reasoning stated **once** in a new
`_unit_note` rather than nine times — rule 2 applied to the config file itself. The
2026-08-01 counts are kept rather than overwritten: they are superseded twice over (they are
line-scoped *and* `docs/`-only), and they are the measurement each pattern was *shaped* by,
which the new counts do not replace.

| row | line-scoped | new scope |
|---|---|---|
| main suite test count | 81 lines / 16 files | 74 / 14 |
| webapp suite test count | 5 / 2 | 5 / 2 |
| ai_involvement agree2 | 9 / 5 | 8 / 4 |
| ai_involvement pairwise | 3 / 3 | 2 / 2 |
| ai_involvement unanimous | 1 / 1 | 1 / 1 |
| hn_whoishiring per-platform | 9 / 6 | 8 / 5 |
| labelling rate, s per posting | 20 / 6 | 20 / 6 |
| Pursuit gate volume | 14 / 7 | 14 / 7 |
| labelled-36 ai_involvement | 3 / 2 | 3 / 2 |

Reproduce with `python3 backend/tools/audit-docs.py --check C4`; the per-row counts come
from `figure_hits()` against `scanned_files()`, no network and no database.

### Note on the line numbers in this file

Task 45 added six lines to the top of `.claude/CLAUDE.md` in the same session — a
four-line frontmatter block and the blank after it — so
**`:121` and `:190` above are now `:127` and `:196`.** The original numbers are left as
written — they were correct when the finding was reported, and this file is `kind: task`.

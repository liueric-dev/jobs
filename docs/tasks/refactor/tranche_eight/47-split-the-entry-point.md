---
kind: task
written: 2026-08-02
generator: none
---

# 47 — the entry point regrew what task 44 archived; split it by lifecycle and give it a budget

**Status:** DONE, 2026-08-02. **Depends on:** 44, done (`29a7d99`) — this is its diagnosis
carried one step further, and it needs 44's archive convention already in place. **Blocks:**
nothing.

> **THE PREMISE WAS WRONG BY ONE, AND THE MISSING ONE IS THE LARGEST PIECE.** This file says
> `HANDOFF.md` is four documents. **Doing the split found a fifth lifecycle**, and it holds
> more lines than the other four together: content that is neither the entry point nor a dated
> record but **true until the code changes** — the three prohibitions, the labelling surface's
> operational reference, the FAQ, what is blocked, the documented claims that are wrong about
> the code, GATE 2, and the follow-ups no task owns. It is a `contract`. Leaving it in a
> `rolling` file is what made that file unreadable; calling it a `record` would have frozen
> guidance that must not freeze. It is now
> [`../STANDING-GUIDANCE.md`](../STANDING-GUIDANCE.md).
>
> **What landed:** `HANDOFF.md` **2669 → 119 lines** against a declared budget of 150.
> [`../OPEN-QUESTIONS.md`](../OPEN-QUESTIONS.md) (`rolling`, owns `OQ-`),
> [`../STANDING-GUIDANCE.md`](../STANDING-GUIDANCE.md) (`contract`),
> [`../sessions/2026-08-02-four-streams-and-the-five-decisions.md`](../sessions/2026-08-02-four-streams-and-the-five-decisions.md)
> (`record`), and
> [`../../../archive/handoff-run-narrative-through-2026-08-01.md`](../../../archive/handoff-run-narrative-through-2026-08-01.md).
> **Every body was extracted by line range rather than retyped**, so the text is byte-identical
> and `git log -p -- docs/tasks/refactor/HANDOFF.md` still reaches all of it.
>
> **C7 landed GREEN, and that is a departure from this run's own precedent.** Task 36 and the
> rule-7 widening both landed red on the argument that a checker whose first run is green has
> been tested against nothing. C7 was tested against a synthetic tree
> (`tests/test_docs_policy.py`, five cases) and against `HANDOFF.md` with sixty lines appended
> — because its subject is the document every session opens first, and leaving it broken to
> prove a point costs every reader in between. Part A ran before part B on purpose, so there
> was nothing for a baseline row to record.
>
> **AND THE LINK SWEEP WAS THE REAL WORK, WHICH TASK 44 ALSO FOUND AND THIS FILE DID NOT
> PLAN FOR.** Moving text one directory deeper broke **47 relative links** — `](AUDIT.md)`
> resolves from `docs/tasks/refactor/` and not from `sessions/`. `audit-doc-links.py` gave a
> unique target for 44 of them and refused to guess on 3, which is the behaviour that stops a
> sweep inventing a file. **`STANDING-GUIDANCE.md` broke none**, because it stayed at the same
> depth — the cost is the depth change, not the move.
>
> **A trap worth carrying, found while chasing those links: `audit-doc-links.py` defaults its
> root to `docs` RELATIVE TO CWD, and `backend/docs/` exists.** Run from `backend/`, it
> scanned the wrong tree and reported **0 broken links** while 47 were live. It was
> `tests/test_docs_policy.py` that caught it, because that test passes `REPO_ROOT`. **Always
> `python3 backend/tools/audit-doc-links.py docs` from the repo root** — and note this is the
> same shape as the `--facts-version` and `labels.pool()` defects the register already
> carries: *a tool that resolves its own population by default resolves the wrong one, and
> nothing looks wrong.*

## The finding, and it is a measurement rather than an opinion

Task 44 archived `HANDOFF.md`'s frozen half on 2026-08-01. **It went 2771 → 2272 lines
(`6b74e0b` → `29a7d99`), a cut of 499. Thirty-six hours later it is 2669 (`5c7edfa`) — a
regrowth of 397, or four fifths of what the archival removed.**

```bash
# The instrument. Nothing here is typed from memory.
for c in 6b74e0b 29a7d99 5c7edfa; do
  printf "%s %s %s\n" "$c" "$(git log -1 --format=%ad --date=short $c)" \
                      "$(git show $c:docs/tasks/refactor/HANDOFF.md | wc -l)"
done
```

**Nothing was red at any point in that window.** `audit-docs.py` reports 0 findings across
C1–C6 and `audit-doc-links.py` 0 broken links, before the regrowth and after it. That is not
a checker failure — it is a scope statement. **Every existing check measures *consistency***:
C1 that a kind is declared, C2 that nothing is orphaned, C3 that a `rolling` document is not
stale against its subject, C4 that an owned figure is not restated, C5 that an identifier is
not defined twice, C6 the archive convention. **None measures volume, and none measures
whether the first thing a session reads is still the first thing it needs.**

### Why the regrowth is structural, not carelessness

`DOCS-POLICY.md` rule 4 says **mark, do not delete**. Applied to a `rolling` document that is
also carrying narrative, that makes *appending* the correct behaviour for every correction —
so the file can only grow, and the only mechanism that ever shrinks it is an archival with no
trigger. Rule 4's second half fixes retirement-with-no-trigger for a document whose *subject*
has landed. **It has nothing to say about a document whose subject is still live and whose
size is the problem.** That is the gap.

**Task 44 found `HANDOFF.md` was two documents. It is now four**, and two of the four arrived
after 44 landed:

| lifecycle | what it is | correct kind | added |
|---|---|---|---|
| the entry point | START HERE, state table, what is next | `rolling` | original |
| the session narrative | *"What landed"*, *"THE PROCESS LESSON"*, *"the one finding to carry forward"* | **`record`** — frozen on write | original, and 44 archived one instalment of it |
| the open-questions register | § *THE OPEN QUESTIONS, IN ONE PLACE* | **`rolling`, its own file, its own prefix** | 2026-08-02 |
| a recommendations essay | § *A session's read on the five decisions* | **`record`** | 2026-08-02, `5c7edfa` |

A `record` is frozen on write and therefore **never accretes strikes**. That property, not
the archival, is what stops the growth: the narrative sections regrow because they are
*supposed* to be edited in place, and they are supposed to be edited in place because they
live in a `rolling` file.

### The open questions are cited by row position, which rule 6 exists to prevent

The table has no allocated identifiers. Its rows currently read **1, 2, 3, ~~7~~, 8, 4, 5,
6** — already reordered, already carrying a struck number. And they are cited by that number
from outside the file: `tranche_six/32-frontend.md:13` says *"open question 1"* and `:280`
says *"open question 7"*.

**Rule 6 says every register owns an ID prefix declared in its own header**, and this is a
register that never got one. `DEFECTS.md` owns `D`, `DECISIONS.md` owns `DEC`; the open
questions own a column of a markdown table in a file that is rewritten every session.

### What C4 cannot see here, and why that is not a bug in C4

The open-questions table is restated in prose in `AUDIT.md` and several task files. **C4 reads
a declared list of figures in `config/doc-figures.json` and is scoped honestly to that** —
its own docstring says a general duplicate detector is not possible and is not attempted. A
restated *table row* is not a figure. **The fix is one owner for the table (rule 2), not a
wider C4**, and widening C4 to chase it would be the exact over-reach task 46 warned about.

## The work

### A. Split `HANDOFF.md` by lifecycle

1. **`HANDOFF.md` → the entry point only.** State table, what is open, what is next, links
   out. **Declare `budget: 150` in its frontmatter** beside `kind: rolling`.
2. **`docs/tasks/refactor/sessions/YYYY-MM-DD-<slug>.md`**, `kind: record`, one per session.
   The narrative sections move here, split by the session that wrote them — `git log` on the
   file gives the boundaries and they are not guesses.
3. **`docs/tasks/refactor/OPEN-QUESTIONS.md`**, `kind: rolling`, declaring prefix **`OQ-`**
   in its own header per rule 6, with an allocator note in the same form `DEFECTS.md` uses.
   The eight rows move whole and keep their present numbers as `OQ-1`…`OQ-8` — **renumbering
   them would break the two inbound citations from `32-frontend.md` for no gain**, and the
   out-of-order sequence is the record of how they were closed.
4. **Struck content leaves via `docs/archive/`** with the rule-4 provenance header and a stub
   where it stood. **Marked, not deleted.** The discipline is not what failed here; the
   absence of a ceiling is.
5. **The § *A session's read on the five decisions* essay relocates into the first session
   record**, with a stub. It was committed to `HANDOFF.md` in `5c7edfa` deliberately, so that
   this move is a separable operation rather than a content decision folded into a commit of
   someone else's finished work.

### B. C7 — a size budget on `rolling` documents

`backend/tools/audit-docs.py` already has the shape. One `check_*(root, files)` generator per
check yielding `Finding`; `CHECKS` at `:806`; `check_rolling` (C3) at `:637` is the nearest
neighbour, since it already reads `rolling` frontmatter.

- Read `budget:` from frontmatter. **A document with no `budget:` key yields nothing** — an
  undeclared budget is not a violation, exactly as C3 reports nothing for an untracked file
  rather than guessing.
- **`Finding.key` must stay line-independent** (`:224-228`). The token is `budget`, one per
  file — never the line count, which changes on every commit and would make the baseline go
  stale on unrelated edits.
- The message names the count, the budget and the fix: move narrative to a session record.
- Register it in `DOCS-POLICY.md` rule 7 and in the maintenance-loop table.

**Land it green, by doing (A) first.** The baseline is *pruned, never grown* — tasks 36 and
45 both say so — and there is no predecessor finding here to inherit, so there is nothing a
baseline entry could honestly record.

### C. The convention that stops it at the source

In `docs/WORKING-METHOD.md` § *How this run works*, where the per-session loop lives, and in
`DOCS-POLICY.md`'s maintenance-loop table's **at session end** row:

> **A session appends to its own record file and edits only the entry point's state table.
> It never appends narrative to `HANDOFF.md`.**

Without this, (A) is a second one-time cut with no trigger — which is what 44 was, and the
measurement at the top of this file is what that produced in thirty-six hours.

## Definition of done

1. `wc -l docs/tasks/refactor/HANDOFF.md` is **at or under its declared budget**, and the
   budget is declared in its frontmatter.
2. `HANDOFF.md` contains no *"what landed"* narrative and no open-questions table; both
   resolve through links.
3. `OPEN-QUESTIONS.md` exists, is `kind: rolling`, declares the `OQ-` prefix in its header,
   and holds all eight rows. The two citations in `32-frontend.md` resolve.
4. At least one file under `sessions/` exists, is `kind: record`, and holds the narrative and
   the five-decision essay.
5. **C7 is in `CHECKS`, is registered in rule 7, and `audit-docs.py` reports 0 findings** —
   green, with an empty baseline.
6. A C7 unit test in `backend/tests/test_docs_policy.py`, alongside the existing check tests:
   a fixture over budget yields one finding, one under it yields none, **one with no
   `budget:` key yields none**.
7. `audit-doc-links.py` reports 0 broken links, and `tests/test_defect_register.py` still
   passes — every moved section is a chance to break an anchor.
8. All three suites at or above their floors, measured **in this tree before any change**:
   backend **1379**, webapp **350**, api **117**. Read the `Ran N tests` line.

## What this deliberately does not do

- **It does not delete anything, and it does not rewrite tasks 01–46.** Those are `kind:
  task` and mostly done: frozen history whose *"What the work turned up"* sections are where
  this run's findings actually live. A clean break was considered and rejected — it costs the
  record and fixes nothing, because the regrowth measured above is structural.
- **It does not widen C4.** See above.
- **It does not touch `DECISIONS.md` (3,240 lines) or `CLAUDE_UPDATES.md` (2,993).** Both are
  append-only by design and neither is an entry point; a register that grows is a register
  doing its job. **Size is only a defect in a document someone has to read first.**
- **It does not resolve any open question.** `OQ-2`/D75 in particular stays exactly as open
  after this task as before it. Moving a question is not answering it.

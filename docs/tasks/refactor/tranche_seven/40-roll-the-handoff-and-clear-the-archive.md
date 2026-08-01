---
kind: task
written: 2026-08-01
generator: none
---

# 40 — Roll the handoff forward, promote what is durable, clear the archive backlog

**Status:** TODO. **Depends on:** 36 (check C3 is what stops this recurring), 37 (kinds are
assigned before anything moves). **Blocks:** nothing.

Three separate changes, **three separate commits**, in this order. Task 34 established why:
doing the archival move in the same commit as the split *"would have made that split
unreviewable."* The same argument applies here and is the reason this is one task file and not
one commit.

## 40a — the entry point is telling every session to do a finished task

[`../HANDOFF.md`](../HANDOFF.md) `:3-52`, `kind: rolling`, is the sixty-second block a fresh
session reads first. It currently says:

> **THE NEXT SESSION IS CLEANUP, BUGFIXES AND DOCUMENTATION — decided 2026-07-31**
> … **Task 34 is the next session's task**, and its file did not exist until this decision —
> `README.md` linked to `34-documentation-cleanup.md` and nothing was there.

Both halves are now false, and the second was **already** false when it was written:

| claim | reality |
|---|---|
| task 34 is next | it is **done** — [`../README.md`](../README.md) row 34, and its own Definition of done is checked off item by item |
| its file did not exist | **it existed**, tracked since `28f1d0e`. `../34-documentation-cleanup.md:14` strikes this exact sentence as **"WRONG, AND CORRECTED"** |

So the entry point repeats, as its justification, a premise that the file it links to retracted.
Nothing was red. **This is `DOCS-POLICY.md` rule 4's specimen** — a `rolling` document with no
retirement trigger — and 36's check C3 exists because of it.

**Rewrite the block** for what is actually true: phases 1–3 built and measured, task 34 landed,
this tranche is the current work, and the labelling ask is unchanged and still the owner's.
Struck-and-kept for the old text, per rule 4 — a reader who acted on it needs to see it.

The table in that block also carries a test count; task 38 owns that line. Coordinate or let 38
land first.

### What must NOT be archived

`HANDOFF.md`'s three remaining "READ THIS FIRST" sections are **standing**, and the file argues
this about itself at `:213`: one open track (`:321`, task 29) and two findings that later work
must not re-derive (`:830`, task 13's unmet DoD; `:869`, the active-profile cost lever). They
stay. The four that described finished work were already archived by task 34.

**If a fourth appears, check whether it is finished history before adding it.** That is the rule
the file states and did not have a check for.

## 40b — promote § *How this run works* (rule 5)

`HANDOFF.md:1479`–`:1590` is roughly a hundred lines of method that is **domain-independent**:

- *"Verify the plan against the code before implementing it, not after"* — three agents, ten
  errors, four of which changed the work
- *"Verify the plan's ARITHMETIC against the artifact, not against the algebra"* — the formula
  said 110 distinct postings, the drawn set had 84; the formula was describing a different
  mechanism
- *"A green suite does not mean the brief was met"*
- *"A finished artifact is where to look for the defects the checks cannot see"* — three of task
  29's four were found that way
- *"A measurement's denominator needs an adversarial reader who cannot see how the numerator was
  built"*
- *"Verify, do not trust the report"* — with four cited instances

Every one of those survives the product changing, which is rule 5's test. None of it is about
Pursuit, Builders, or job postings. It is currently reachable only by scrolling 1,479 lines into
a handoff about a labelling session.

**Promote to `docs/WORKING-METHOD.md`**, `kind: contract`. `docs/MEASUREMENT-TRAPS.md` is the
precedent and the model — same promotion, same reason, and it is now cited from
`.claude/CLAUDE.md`. Leave a stub and link where the section was.

**Cite it from `.claude/CLAUDE.md`.** A durable method document nothing points at is the orphan
problem again, one level up.

## 40c — clear § *Still to archive*

[`../../../archive/README.md`](../../../archive/README.md) `:45-53` names two files
dispositioned for the archive by task 34 § D that were **not** moved, with the reason recorded:
both are live citations, so moving them is its own change with its own link sweep. **This is that
change.**

### `backend/docs/SCORING.md`

§ D: *"Archive. Superseded by `docs/scoring.md`; two hand-written scoring docs is drift."*

Both are live and each opens by pointing at the other — `docs/scoring.md:15` calls `SCORING.md`
*"the design argument"*, `SCORING.md:11` calls `docs/scoring.md` *"the contract"*. That is a
deliberate split, not drift, **and it contradicts § D's disposition.** So this is a decision, not
a chore:

- **archive it**, per § D, and fold the design argument into `docs/scoring.md`; or
- **keep both** and retire § D's disposition, recording that the split is intentional.

**Recommend keeping both and retiring the disposition** — the two files declare different jobs
in their own opening paragraphs, which is what rule 1 asks of a document. But note the real
finding either way: `SCORING.md` carries a cost table that task 04 superseded and a
*"76% self-agreement"* line that task 06 superseded. **Whatever is decided about the file, those
figures are task 38's** and must be marked.

Record the choice in `DECISIONS.md` with the rejected option, and update
`docs/archive/README.md` § *Still to archive* to match. **It must not still say "not moved" when
the decision was to keep it.**

### The `HANDOFF-match-quality.md` remainder

§ 4 was already promoted to `MEASUREMENT-TRAPS.md`. The rest measures the author's
software-engineer persona and does not transfer. Archive it with the provenance header
`docs/archive/README.md` requires, and **relabel its 12.7/20 as imitation fidelity against a
non-target persona** — the archive README already says this must happen before anyone quotes it,
and until it does the number reads as a quality score.

## Definition of done

| | item | how it is checked |
|---|---|---|
| | `HANDOFF.md`'s START HERE describes the current state; the old text is struck, not deleted | read `:3-52`; `git diff` shows strikethrough |
| | No document claims task 34 is next or that its file did not exist | `grep -rn 'file did not exist\|34 is the next' docs/` returns only struck text |
| | 36's check C3 is clean | `python3 backend/tools/audit-docs.py` |
| | `docs/WORKING-METHOD.md` exists, `kind: contract`, cited from `.claude/CLAUDE.md`; a stub remains at `HANDOFF.md:1479` | it exists; `audit-doc-links.py` reports 0 |
| | The `SCORING.md` decision is **made**, recorded in `DECISIONS.md` with the rejected option, and § *Still to archive* matches it | read all three |
| | `HANDOFF-match-quality.md`'s remainder is archived with a provenance header, 12.7/20 relabelled | read the header |
| | `HANDOFF.md` still has exactly three "READ THIS FIRST" sections, all standing | `grep -c 'READ THIS FIRST' docs/tasks/refactor/HANDOFF.md` |
| | Three commits, in order, each reviewable alone | `git log --oneline` |
| | Both suites green and not smaller | read `Ran N tests` from each |

## Out of scope

- **Rewriting the three standing sections.** They are the file's whole remaining job.
- **Compressing `HANDOFF.md` for its own sake.** Task 34 took it from 3,481 lines to ~2,690 by
  moving *finished* content. Length is not the target; staleness is.
- **`CLAUDE_UPDATES.md`.** Append-only, and its dated sequence is the thing that makes it
  readable — task 34 rejected pasting narratives into it for exactly that reason.

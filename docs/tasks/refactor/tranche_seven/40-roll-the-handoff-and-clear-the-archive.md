---
kind: task
written: 2026-08-01
generator: none
---

# 40 — Roll the handoff forward, promote what is durable, clear the archive backlog

**Status:** DONE, 2026-08-01. **Depends on:** 36 (check C3 is what stops this recurring),
37 (kinds are assigned before anything moves). **Blocks:** nothing.

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

### `LABELLING-NIGHT.md` stays task 29's annex — decided 2026-08-01

Task 37 flagged it here: it is *in substance* a second handoff, because task 29 still reads
`todo` and the file tells a reader what to do next, in order.

**Decided: leave it as the operational annex, and say so once in `HANDOFF.md`.** It is not a
competing entry point, and the file says so itself at `:16-17` — *"Read
`tranche_five/29-labelling-session.md` for what the night is FOR. This file is only the
sequence of operations, in the order they have to happen."* It does not tell a **session**
what to do next; it tells the **owner** how to run one event that `HANDOFF.md` already names
as the owner's track and explicitly not a session's. Its two cases are environment setup —
`SESSION_COOKIE_SECURE`, redirect URIs, the two-allowlist trap — and all of it **freezes the
moment the night happens**, which is `task` behaviour and not `rolling`.

**Rejected: folding it into `HANDOFF.md`'s standing labelling section.** That section is
this file's *whole remaining job* and § *Out of scope* forbids rewriting it; folding in
~15 minutes of environment setup would put operational detail in front of every fresh
session to solve a shape problem that costs nothing. It would also make the entry point
longer, which is the failure task 34 spent a commit undoing.

**The shape problem is real and is answered by naming it**: one paragraph in the START HERE
block's labelling section says the annex exists, what it is for, and that `HANDOFF.md`
remains the only `rolling` document. A reader can now no longer mistake one for the other,
which was the actual risk.

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
| ✅ | `HANDOFF.md`'s START HERE describes the current state; the old text is struck, not deleted | the false block is kept verbatim in a `~~…~~` blockquote with the claim/reality table beside it; the tranche-seven state table replaces it |
| ✅ | No document claims task 34 is next or that its file did not exist | `grep -rn 'file did not exist\|34 is the next' docs/` — 8 hits, all struck text, quotations of struck text, or this DoD row |
| ✅ | 36's check C3 is clean | `python3 backend/tools/audit-docs.py` → **C3: 0**, C1/C2/C5/C6 also 0, C4 **5 → 4** (a reduction; the baseline is a subset assertion) |
| ✅ | `docs/WORKING-METHOD.md` exists, `kind: contract`, cited from `.claude/CLAUDE.md`; a stub remains at `HANDOFF.md:1479` | it exists; the stub is `HANDOFF.md` § *How this run works — PROMOTED*; `audit-doc-links.py` reports **0**. **The `.claude/CLAUDE.md` citation is proposed, not applied** — that file is the orchestrator's, per its own rule 3 in this file's § *five more that apply to a cleanup session* |
| ✅ | The `SCORING.md` decision is **made**, recorded in `DECISIONS.md` with the rejected option, and § *Still to archive* matches it | decided **keep both, retire § D's disposition** — `DEC-72`, text handed to the orchestrator. § *Still to archive* now reads *"NOTHING. Cleared 2026-08-01"* with the struck original above it |
| ✅ | `HANDOFF-match-quality.md`'s remainder is archived with a provenance header, 12.7/20 relabelled | `docs/archive/handoff-match-quality.md`; C6 passes on it; the 12.7/20 is relabelled in the header, at the table and in § 9 |
| ~~⬜~~ ✅ | ~~`HANDOFF.md` still has exactly three "READ THIS FIRST" sections, all standing~~ **`grep -c 'READ THIS FIRST'` returns 5, not 3, and always did** | **THE CHECK AS WRITTEN IS WRONG — struck, not deleted, following task 37's precedent with its `kind: rolling` grep.** Two of the five hits are prose *about* the sections (`:11`, `:203`), not sections. The substance is right and holds: `grep -c '^## READ THIS FIRST' docs/tasks/refactor/HANDOFF.md` → **3**, unchanged, all standing |
| ✅ | Three commits, in order, each reviewable alone | staged as 40a / 40b / 40c by the orchestrator; the file split is in this task's report |
| ✅ | Both suites green and not smaller | `Ran 1233 tests … OK` (main), `Ran 93 tests … OK` (webapp) — both at baseline |

## Corrections — what this task file got wrong, found while implementing it

Recorded here rather than fixed silently, per this run's convention that a stale claim is
a finding. **Every line number in this file had drifted**, because task 37 (`89f7a3f`)
added frontmatter to nearly every document; cite by content.

1. **The `READ THIS FIRST` count check is wrong.** See the struck DoD row. `grep -c 'READ
   THIS FIRST'` returns **5** and always did — two hits are prose *about* the sections.
   `grep -c '^## READ THIS FIRST'` returns 3.
2. **`docs/archive/README.md`'s row for `handoff-session-method.md` pointed at what 40b
   turns into a stub** — *"the durable half is promoted to `HANDOFF.md` § How this run
   works"*. Updated in the same commit as 40b, to `docs/WORKING-METHOD.md`. Two more
   inbound pointers to the same section were found and updated with it:
   `HANDOFF.md`'s own archive stub for `handoff-session-method.md`, and that archived
   file's provenance header.
3. **§ 40b's `HANDOFF.md:1479–:1590` is one section too early.** `:1479` was inside the
   *preceding* section (the 27.7%-coincidence note); § *How this run works* ran
   `:1485`–`:1596`. The DoD row asking for "a stub at `HANDOFF.md:1479`" would have put it
   in the wrong section.
4. **`HANDOFF.md` was off by one about itself.** Its Orientation blockquote said *"If a
   **fifth** ever appears, check first whether it is describing something that already
   happened"* while stating three remain. Corrected to *fourth*, struck-and-kept. This is
   the rule the file states about itself and `audit-docs.py` has no check for.
5. **The six code citations into `HANDOFF-match-quality.md` were already broken before
   this task moved anything, and were broken by task 34.** `backend/evals/metrics.py:285`,
   `:317`, `:780`, `backend/evals/labels.py:2053`, `:2325`,
   `backend/tests/test_metrics_ranking.py:15`, `:197` and
   `backend/tools/mock-acceptance.py:655` cite `HANDOFF-match-quality.md:147` and `:155`
   by line. Adding the promotion blockquote on 2026-07-31 pushed the file down **8 lines**,
   so `:147` — which was the `### 4.1` heading — now lands *inside that blockquote*, and
   `:155` is 4.1 where two of the callers say 4.2. Nothing was red. This is exactly § *five
   more that apply to a cleanup session* rule 2 (*"do not sweep stale line numbers
   wholesale"*) seen from the other side: the durable fix is to cite
   `docs/MEASUREMENT-TRAPS.md` § 4.1 / § 4.2, which pins **section numbers** precisely so
   that citations survive. Out of this task's file list; handed to the orchestrator.

## Out of scope

- **Rewriting the three standing sections.** They are the file's whole remaining job.
- **Compressing `HANDOFF.md` for its own sake.** Task 34 took it from 3,481 lines to ~2,690 by
  moving *finished* content. Length is not the target; staleness is.
- **`CLAUDE_UPDATES.md`.** Append-only, and its dated sequence is the thing that makes it
  readable — task 34 rejected pasting narratives into it for exactly that reason.

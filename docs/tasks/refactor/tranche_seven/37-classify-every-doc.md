---
kind: task
written: 2026-08-01
generator: none
---

# 37 — Classify every document, and act on the classification

**Status:** TODO. **Depends on:** 36 (the checker tells you when this is finished).
**Blocks:** 40, which archives what this task exposes.

Give every document the `kind:` frontmatter [`DOCS-POLICY.md`](../../../DOCS-POLICY.md) rule 1
requires, build the index that makes orphans visible, and **act on what the classification
turns up** — because the point of classifying is not the label, it is that a label makes the
wrong-shaped document obvious.

## Inventory — get the number, do not read it here

Per policy rule 3, this file does not type counts a command produces:

```bash
cd /home/eric/apps/jobs
find docs -name '*.md' | wc -l                              # in scope
find . -name '*.md' -not -path './.git/*' -not -path '*/.venv/*' | wc -l   # repo-wide
for f in $(find docs -name '*.md'); do [ "$(head -1 $f)" = '---' ] || echo "$f"; done
```

The third command is the work: today it prints everything **except** the fourteen
`docs/ingest/*.md` files, which task 34 § A2 already gave frontmatter. Those fourteen are the
pattern to copy.

## The starting assignment

Task 34 § D's disposition table is the prior, not a blank sheet. It was written before the run
and it was right about most of the tree. Translating it into kinds:

| tree | kind | why |
|---|---|---|
| `docs/ingest/*.md` | `contract` | what each script does **now**. Already have frontmatter; add `kind:` beside `generator: none` |
| `docs/ingest/DEFECTS.md` | `contract` | a live register. Entries close; the file is never done |
| `docs/tasks/**/*.md` | `task` | frozen at DONE |
| `docs/tasks/refactor/DECISIONS.md` | `rationale` | its header already says append-only |
| `docs/tasks/refactor/CLAUDE_UPDATES.md` | `record` | dated session log |
| `docs/tasks/refactor/HANDOFF.md` | `rolling` | **the only one in the tree that should be** |
| `docs/tasks/refactor/AUDIT.md` | `contract` | state of the run, owns the figures under rule 2 |
| `docs/archive/*.md` | `record` | frozen by definition |
| `docs/MEASUREMENT-TRAPS.md`, `DOCS-POLICY.md` | `contract` | promoted, domain-independent |
| the measurement write-ups | **`record`** | see below — this is the one that needs judgement |

### The judgement call, and it is the substance of this task

**Most of `docs/` is `record` and has been read as `contract`.**

`docs/pursuit-gate-volume.md`, `docs/facts-v3-diff.md`, `docs/score-validation.md`,
`docs/jsonld-coverage.md`, `docs/jobspy-spike.md`, `docs/google-jobs-query-experiment.md`,
`docs/role-track-derivation.md`, `docs/mock-acceptance.md`, `docs/ats-token-discovery.md`,
`docs/pursuit-description-gate.md` — every one is **a measurement taken on a date**. They are
`record`. They are frozen. Nobody has to keep them current, and **nobody should try**, because
§ D already found the trap: *"three half-updated docs are worse than one honestly-stale doc,
because you cannot tell which is current."*

Two are not so simple and must be split rather than labelled:

- **`docs/scoring.md`** opens *"Every figure below was measured against the live database on
  2026-07-27"* and then serves as the scoring **contract** the whole repo cites. It is both.
  Decide: either the contract half is extracted and the measured half becomes a dated `record`,
  or the whole file is `contract` and every figure in it gets re-derived on a schedule someone
  is actually going to keep. **Recommend the first**; record the choice in `DECISIONS.md`.
- **`backend/docs/DEVELOPER.md`** carries an *Open Questions / TODOs* list of decisions taken
  2026-07-24 that later work superseded — the git-based script distribution is describing a repo
  that is now a git repo, and the quota pacing is *"designed, not yet built"* a fortnight on.
  That list is `record` wearing a `contract`'s clothes. Mark, do not delete (rule 4).

## `docs/README.md` — the index that does not exist

There is none, for a tree of ninety-odd files. This is why C2 (orphan detection) has never been
possible: **reachability needs a root, and `docs/` has never had one.**

One page. Grouped by kind, not by folder. One line per document saying what question it answers —
`docs/tasks/refactor/README.md` is the model for tone and density. Its job is to be the thing C2
walks from, so **every entry is a real relative link**, and `audit-doc-links.py` must stay at 0
after it lands.

## Act on the classification

Labelling alone is worth little. What the labels expose:

1. **Anything that cannot be assigned a kind is a document that does not know what it is for.**
   Do not force a label. Report it — that is a finding, and per § *The rule this task runs under*
   in `../34-documentation-cleanup.md`, a finding is the deliverable, not a chore.
2. **Any `rolling` document other than `HANDOFF.md` is either mislabelled or a second handoff.**
   The tree should end this task with exactly one.
3. **Any `contract` whose subject has changed since it was written is a defect.** Fix it in place
   or reclassify it as `record` with a date. Those are the only two options; leaving it is not one.
4. **Orphans.** Run 36's C2 as soon as `docs/README.md` exists. Anything unreachable gets linked,
   archived, or reported — and *nothing is deleted*.

## Definition of done

| | item | how it is checked |
|---|---|---|
| | Every `.md` under `docs/` has valid `kind:` frontmatter | `python3 backend/tools/audit-docs.py` — C1 clean |
| | `docs/README.md` exists, groups by kind, one line per document | it exists; `audit-doc-links.py` still reports 0 |
| | C2 reports zero orphans, or each remaining one is listed here with a reason | run it; paste the output into this file |
| | `docs/scoring.md`'s contract-vs-record split is **decided** and recorded in `DECISIONS.md` | the entry exists and names the rejected option |
| | `DEVELOPER.md`'s superseded TODO block is struck-and-kept, not deleted | `git diff` shows strikethrough, not removal |
| | Exactly one `kind: rolling` document in the tree | `grep -rl 'kind: rolling' docs/ \| wc -l` is 1 |
| | Every document that could not be classified is **named here with why** | this file has the list, or states there were none |
| | Both suites green and not smaller | read `Ran N tests` from each |

## Out of scope

- **Rewriting any `record`.** They are frozen. Adding frontmatter is not rewriting.
- **`backend/**/*.md`.** Task 36 starts the checker at `docs/`; widening is a later call.
- **Archiving.** This task *identifies*; task 40 *moves*. Splitting them keeps the move
  reviewable, which is task 34's stated reason for deferring the `SCORING.md` archive in the
  first place.

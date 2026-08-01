---
kind: task
written: 2026-08-01
generator: none
---

# 43 — Split `docs/scoring.md` into a contract and a dated record

**Status:** TODO. **Depends on:** nothing — `DEC-70` already made the decision this task
executes. **Blocks:** nothing.

`docs/scoring.md` opens *"Every figure below was measured against the live database on
2026-07-27"* and then serves as the scoring **contract** the whole repo cites. Under
[`DOCS-POLICY.md`](../../../DOCS-POLICY.md) rule 1 it cannot be both: a contract may not
be stale, a measurement is frozen at its date.

**The decision is already taken and is not reopened here.** `DEC-70` decided: extract the
contract half, freeze the measured half as a dated `record`. It named and rejected the
alternative — make the whole file a `contract` and re-derive every figure on a schedule —
because the schedule has no owner, and this run produced eight numbers that went stale
behind exactly that assumption.

Task 37 deferred execution deliberately: pulling a contract out of a dated measurement is
content work, and doing it inside a tree-wide frontmatter sweep would have made both
unreviewable. That is task 34's stated reason for deferring the `SCORING.md` archive,
applied again.

## The work

**The contract half** — what a score means, whether two scores are comparable, the
four-stage ordering, the failure behaviour, where each weight came from. This is what every
citation of `docs/scoring.md` in the repo is actually citing.

**The record half** — every figure measured against the live database on 2026-07-27. Frozen,
dated, `kind: record`, and **nobody keeps it current**. Task 37 § *The judgement call*
already found the trap: *"three half-updated docs are worse than one honestly-stale doc,
because you cannot tell which is current."*

**`backend/docs/SCORING.md` is not in scope and is not a duplicate.** `DEC-72` settled that
in task 40: the two files declare different jobs in their own opening paragraphs — design
argument and cost, against contract — which is what rule 1 asks of a document. Do not merge
them, and do not re-open task 34 § D's archive disposition, which `DEC-72` retired.

## Definition of done

| | item | how it is checked |
|---|---|---|
| | The contract half and the record half are separate documents, each with valid `kind:` | `python3 backend/tools/audit-docs.py` — C1 clean |
| | Every inbound citation of `docs/scoring.md` lands on the half it meant | `grep -rn 'scoring\.md' --include='*.md' --include='*.py' .` and read each |
| | The record half carries its date and is marked frozen | read it |
| | Both are reachable from [`docs/README.md`](../../../README.md) | C2 clean |
| | No figure is restated across the two | C4 clean |
| | `audit-doc-links.py` still reports 0 | run it |
| | Both suites green and not smaller | read `Ran N tests` from each — the floor is the reading you take before starting |

## Out of scope

- **Re-measuring anything.** The figures are a 2026-07-27 record and stay exactly as
  written. This is a split, not a refresh.
- **`backend/docs/SCORING.md`.** See `DEC-72`.
- **Re-opening `DEC-70`.** The decision and its rejected alternative are recorded; this task
  performs it.

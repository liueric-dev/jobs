---
kind: task
written: 2026-08-02
generator: none
---

# 49 — rebuild the understanding of this system from the code, not from the documents

**Status:** TODO. **Depends on:** 48. **Blocks:** 50, 51, 52, 53, 54.

**This is the load-bearing task in the tranche.** Everything after it either extracts against
its output or plans against it. If it is done cheaply, the rest inherits the confusion it was
written to end.

## The rule that makes this different from every previous audit

**The documents are not an input.** They are what produced the confusion; reading them first
reproduces it. The sources of truth, in order:

1. **The code** — `backend/`, `frontend/`, `deploy/`
2. **The test suites** — a test that passes is a claim someone verified
3. **`git log`** — what actually landed, and when
4. **The config `_comment` fields** — rationale that lives with the thing it describes

The docs are consulted **last and adversarially**: for every claim they make, ask whether the
code agrees. Where they disagree, **the code wins and the disagreement gets recorded** — that
list is an output of this task and it is the input to task 51's disposition.

This inverts the current dependency, in which every session opens a document and trusts it.

## Why this is a good first use of the harness

The corpus is larger than one context window can hold usefully, the readings are independent,
and the results need cross-checking. That is the exact shape a dynamic workflow is for: the
script holds the loop and the intermediate results, and only the synthesis reaches the
conversation.

```
use a workflow to answer, from the code and tests only: what does this pipeline
actually do today, stage by stage; which of the 47 tasks are genuinely complete
by evidence in the tree; and where the documentation disagrees with the code.
adversarially verify each finding before reporting it.
```

Run it on one directory first to see the shape and the token cost before committing to the
whole tree (`/workflows` shows per-agent usage as it goes). If the workflow route is not
wanted, the same work is a fan-out of read-only subagents over disjoint areas — that is the
pattern `WORKING-METHOD.md` already prescribes: *fan out on reading, never on a chain of
edits*.

**Either way, one instruction is mandatory in every agent's brief:** *if any fact in this brief
contradicts what you find in the code, STOP and report the contradiction rather than proceeding.*
Task 47 recorded briefs containing factual errors that only the subagents caught.

## The output

**`docs/STATE-OF-THE-SYSTEM.md`**, `kind: contract`, **`budget: 400`**.

Written from scratch. Not assembled from `AUDIT.md`, `MASTER-PLAN-pursuit.md`,
`STANDING-GUIDANCE.md` or `HANDOFF.md`. It answers, with `file:line` citations:

1. **What the pipeline does today** — the four stages, what each reads and writes, what costs
   an LLM call, what the nightly run actually executes
2. **What the surfaces are** — three processes, three interpreters, three suites; what the
   frontend serves and what it does not
3. **What is genuinely done** — by evidence in the tree, not by a status column
4. **What is genuinely open**, split into *needs work* and *needs the owner* — the second list
   is task 53's input
5. **What the documents claim that the code does not support** — the disagreement list
6. **Every figure in circulation, with its instrument** — the self-consistency metrics in
   particular, where three correct percentages circulate and a number without its metric name
   is a rumour with a decimal point

## Definition of done

- [ ] `docs/STATE-OF-THE-SYSTEM.md` exists, is `kind: contract`, declares `budget: 400`, and is
      under it
- [ ] Every claim in it carries a `file:line` or a command that reproduces it
- [ ] Section 5 is non-empty — **if the audit found zero disagreements across ~46,000 lines of
      documentation, it did not look**
- [ ] Section 4's *needs the owner* list is complete enough to hand to 53 unedited
- [ ] The old documents are **unchanged by this task**. 51 dispositions them; 49 only reports
- [ ] The workflow or agent briefs are attached to the session record, so the method is
      reproducible

## The trap this task is most likely to hit

**A total is not a composition.** Task 29's four defects were all found by reading the artifact
rather than the marginals, which summed correctly. When this task reports "33 tasks done", read
a sample of the rows underneath rather than trusting the count — tasks 36 and 40 were marked
todo while DONE, and the reverse is equally available.

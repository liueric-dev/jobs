---
kind: decision
written: 2026-08-03
generator: none
---

# 0003 — Nothing is built at harness Layer 3

**Status:** accepted. The decision is **to defer**, and deferral here is a position, not an
unfinished row.

## Context

[`../../TASK-52-harness.md`](../../TASK-52-harness.md) splits the harness into five layers by the
question each answers. Layer 3 is *what decides what runs next* — today, the owner, typing. The
candidate primitives are `/batch`, saved workflows and `/goal`.

The tranche's own diagnosis is the reason to be careful here. Prompts were being repeated across
sessions not out of laziness but because **a primitive existed, was not known, and got reinvented
in Markdown**. Twelve consecutive tasks (36–47) built documentation infrastructure, every one green,
and produced no product movement. Building a harness the owner does not understand reproduces that
failure with better tooling — which is why `TASK-52-harness.md` makes the ordering a requirement
rather than a preference: one primitive at a time, explain it, build it, use it once, then move on.

Layer 3 is the layer where that trap is easiest to fall into, because all three candidates are
cheap to build and none of them is obviously the right one. Choosing between them from the armchair
means choosing on aesthetics.

## Decision

**Build none of the three.** Record the deferral here, per `../../TASK-52-harness.md:92-96`, which
asks for exactly this: *"Record the choice as an ADR under `docs/adr/`; do not build all three."*

The choice is to be made from experience — after enough sessions have run under Layers 1, 2 and 4
that there is evidence about which decisions actually get made by hand, repeatedly, and would be
worth automating.

**What would trigger revisiting this**, so it does not sit here indefinitely as a synonym for
forgotten:

1. The same multi-step sequence is typed by hand in three or more sessions. That is the signal a
   saved workflow is being reinvented in prose — the original failure, one layer up.
2. Layers 1, 2 and 4 are all shipped and used (`T-5` … `T-9`, `T-1`, `T-2`), so there is a working
   harness to observe rather than a hypothesis.
3. The owner finds themselves sequencing rows from `../../TASKS.md` by hand often enough that
   ordering, not execution, is the bottleneck.

Any one of the three reopens this. Until then the answer is the owner, typing, and that is fine.

## Consequences

- Layer 3 has no acceptance criteria in `../../TASKS.md`, correctly — `T-5` … `T-9` cover Layers 1,
  2, 4 and 5 and Layer 3 has no row. Its absence from that file is the decision, not an oversight.
- `TASK-52-harness.md`'s Definition of done lists "Layer 3 is a **recorded ADR, not a build**" as
  its own checkbox. This file is that checkbox.
- If a future session proposes building `/batch`, saved workflows or `/goal`, the burden is to name
  which of the three triggers above has fired. "It would be useful" is not one of them.

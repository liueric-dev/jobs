# What these sessions measured, and what it means

> **Archived from `docs/tasks/refactor/HANDOFF.md` on 2026-07-31**, when that file was split.
>
> **What it is:** Session narrative through 2026-07-31. Retained for the figures and their instruments; the live numbers are in HANDOFF.md § State at handoff and AUDIT.md.
>
> Moved, not deleted. `git log --follow` on this path reaches the original text, and a stub
> and link remain where this section was.

---

## What these sessions measured, and what it means

Four numbers landed that change how the rest of the plan should be read.

**The Phase 3 estimates are not reliable, and this is still the run's headline finding.**
Three sources measured, three far below estimate:

| task | estimate | measured |
|---|---|---|
| 05 (gate volume) | — | 43/day, ≈3/day usable |
| 14 (NYC Open Data) | 20–60/day | **1.8/day** |
| 18 (Workday) | 80–200/day | **~1/day** at four tenants; ~12/day extrapolated to fifty |
| 19 (JSON-LD) | 30–60/day | **≤1.1–2.3/day**, a ceiling that is not reachable — **dropped** |

**Four for four.** This is no longer a caution about one estimate; it is the most
reliable finding of the whole run. Every Phase 3 number that has been checked has
come back an order of magnitude high, and they were all produced by the same
method from the same table. **Tasks 15, 20 and 21 are sized identically and should
be treated as unfounded until measured.** A spike costs an afternoon; task 19's
cost 333 HTTP requests and no LLM calls at all.

Tasks 15, 19, 20 and 21 are sized from the same table by the same method. **Measure before
building.**

**Task 11 measured the same shortfall from a third direction, and it is the sharpest
version yet.** Across 863 cohort-eligible postings — the ones that already pass task 10's
gate — the AI-operations archetype the whole retarget is aimed at appears **5 times, across
3 employers**. Not 5%: five postings. The vocabulary hole was real and is now fixed, but
fixing it revealed that the roles are not there to be classified. Meanwhile the `other`
bucket, which the task file assumed was full of ops roles, turned out to be **47.5% tech
roles the vocabulary simply lacked** against 12.6% ops. The corpus is still a software
corpus.

**And the shape of the shortfall matters more than its size.** Of 329 Workday postings
pulled from four NYC employers — a hospital system, a bank, a retailer — **zero have any AI
vocabulary in the title**, by any method. Task 10 reached the same place from the other
direction: its gate improved precision from 6.7% to 10.0% and is still 90% junk. The
problem is not that the boards are unreachable or that the gate is too tight. **These
employers are not posting these roles.** That is a question about the plan's premise, and
it is not answerable by building more ingest.

**The gate is not the bottleneck; sourcing is.** Task 10 raised hand-checked precision from
task 05's 6.7% to 10.0% — a real improvement, and still 90% junk. Its own report says the
bottleneck is sourcing rather than gating, and task 14's 1.8/day is the same finding from
the other side.

**Extraction capacity is no longer the constraint.** The drain loop replaced a hard 40/day
ceiling with ~1,260 calls/hour of headroom against 43–80/day of intake. Whatever binds
next, it is not this.

**Silence is still the failure mode, and it was caught live.** Task 18's first run dropped
**161 of NewYork-Presbyterian's postings** — real NYC hospital jobs — while printing
`4/4 tenants ok`. The task found it itself, on a third run, after having already reported
success. Nothing else in the pipeline would have noticed. When a source's numbers look
clean that is not evidence: reconcile against the count the API itself returned.

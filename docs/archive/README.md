---
kind: contract
written: 2026-07-31
generator: none
---

# docs/archive/

**Everything in this directory was true when it was written and is not the current
state.** Nothing here is deleted, because this run's convention is *mark, do not delete*:
a reader who acted on an old number has to be able to see what they had, and the fact
that a number was once wrong is itself evidence about how the system was tuned.

Two kinds of file live here.

**Superseded measurements**, most of them taken against the repo author's own
software-engineer persona. **They do not transfer to the Pursuit cohort** — different
corpus, different seniority band, different definition of a good posting. A figure from
one of these is not a quality figure for the current system, and `HANDOFF-match-quality`'s
12.7/20 in particular is *imitation fidelity against a non-target persona*, not a quality
score. Do not quote them forward.

**Finished narrative**, moved out of `docs/tasks/refactor/HANDOFF.md` when that file was
split. `HANDOFF.md` is meant to be read in sixty seconds by a session about to do work;
it had grown to 3,481 lines with seven sections each titled "READ THIS FIRST", most of
them describing work that had already landed. Those sections are history, and history
belongs beside the run log rather than in front of the next reader.

## The rule for adding to this directory

Every file gets a header, before anything else, saying **what it measured, when, and what
superseded it**. A file in an archive with no provenance line is worse than one left in
place, because the reader cannot tell whether they are holding the current answer.

Every section moved out of a live document leaves a **stub and a link** where it was, so
an inbound citation still lands somewhere. `git log --follow` reaches the original text in
every case.

## What is here

| file | what it was | why it is here |
|---|---|---|
| [`handoff-stopwatch-reading.md`](handoff-stopwatch-reading.md) | the per-posting labelling rate, measured at n=4 (154 s) and re-derived the same day at n=29 (93 s median) | the live number is one entry in `HANDOFF.md` § *Pending follow-ups*; this is how it was got and how the first reading was wrong |
| [`handoff-sampler-defects.md`](handoff-sampler-defects.md) | four defects in `labels.sample()` found before the 200-row set was drawn, and a fifth found after it was pinned | all fixed 2026-07-29; the set is drawn and can never be redrawn |
| [`handoff-ceiling-and-preflight.md`](handoff-ceiling-and-preflight.md) | why the inter-annotator ceiling was unreachable, and the two pre-flight values that were wrong and produced no error | fixed and verified 2026-07-30. **The two operational subsections stayed in `HANDOFF.md`** — `FRONTEND_ORIGIN` and the `app_users` schema are configuration, not narrative |
| [`handoff-gate-fix.md`](handoff-gate-fix.md) | step 0's relevance-gate fix: mock recall 48.3% → 89.7%, live tier ≤2 869 → 880 | its own first line reads *"What follows is the record, not a plan."* The four forbidden phrase families are now guarded by a test rather than by this prose |
| [`handoff-owner-decisions.md`](handoff-owner-decisions.md) | the two extraction decisions taken in conversation — selective majority-of-3, and the 40/day ceiling | landed in `943d899`; the rationale lives in `DECISIONS.md` under EXTRACT |
| [`handoff-match-quality.md`](handoff-match-quality.md) | how well `match.py` ranked for profile `tech` — the repo author's own software-engineer search — over 917 already-LLM-scored postings, 2026-07-26 | the persona is not the Pursuit cohort. § 4 is promoted to [`docs/MEASUREMENT-TRAPS.md`](../MEASUREMENT-TRAPS.md); **its 12.7/20 is imitation fidelity against a non-target persona and is relabelled as such in the file.** A stub and link remain at `backend/docs/HANDOFF-match-quality.md` |
| [`handoff-session-measurements.md`](handoff-session-measurements.md) | session-by-session narrative of what was measured through 2026-07-31 | ~~live figures are in `HANDOFF.md` § *State at handoff*~~ **that section is itself archived — see the row below, added 2026-08-01** — and the current figures are in `AUDIT.md` |
| [`handoff-state-2026-07-31.md`](handoff-state-2026-07-31.md) | `HANDOFF.md` § *State at handoff* and § *What 08, 12 and 19 changed about the plan*: the run's dated state at 2026-07-31, the suite-count drift table, and the commit table three task files cite | **task 44, 2026-08-01.** `HANDOFF.md` is the only `kind: rolling` document in the tree and rule 1 forbids it to be stale, but below § *State at handoff* it was a frozen session narrative — one file with two lifecycles, which rule 1 has no name for. Every figure is a dated reading; `AUDIT.md` owns the current ones |
| [`handoff-tree-state.md`](handoff-tree-state.md) | `HANDOFF.md` § *Nothing is in flight — but the tree is NOT clean*: what was committed and what was only a database write, with the content digests that proved nothing else moved | **task 44, 2026-08-01**, same split. **Two parts of it did not come here:** the FAQ *"the next session's likely first question"* is standing guidance and stayed, and the four cross-stream lessons were promoted to [`../MEASUREMENT-TRAPS.md`](../MEASUREMENT-TRAPS.md) under rule 5 |
| [`handoff-session-method.md`](handoff-session-method.md) | method notes from those sessions | the durable half was promoted to `HANDOFF.md` § *How this run works*, and ~~that~~ **is now [`docs/WORKING-METHOD.md`](../WORKING-METHOD.md)** — promoted again 2026-08-01 by task 40 under rule 5, leaving a stub in `HANDOFF.md`. This row pointed at what became that stub for the length of one commit; it is the inbound citation rule 4 exists for |

## Still to archive — ~~two files~~ **NOTHING. Cleared 2026-08-01 by task 40**

> ~~These were dispositioned for the archive by task 34 § D and have **not** been moved:
> `backend/docs/SCORING.md` … and the persona-bound remainder of
> `backend/docs/HANDOFF-match-quality.md` … Both are live citations today, so moving them
> is a separate change with its own link sweep.~~
>
> **That was the correct deferral and this is the change it deferred to.** Struck and kept
> per rule 4, because the two files did not get the same answer:

| file | task 34 § D said | decided 2026-08-01 |
|---|---|---|
| `backend/docs/HANDOFF-match-quality.md` | archive the persona-bound remainder | **archived** → [`handoff-match-quality.md`](handoff-match-quality.md), stub and link left at the original path, **12.7/20 relabelled** as imitation fidelity against a non-target persona |
| `backend/docs/SCORING.md` | *"Archive. Superseded by `docs/scoring.md`; two hand-written scoring docs is drift."* | **kept, and § D's disposition retired — decision `DEC-72`.** Not drift: a deliberate split, and each file declares the split in its own opening paragraph |

**Why `SCORING.md` stays.** `docs/scoring.md` § *Scope* (~~`:15-21`~~ — line numbers into a
live contract drift, and this one did when task 43 split the file on 2026-08-01) calls it
*"the design argument — why
the work is split into four stages and what each one costs"*; `SCORING.md:9-13` calls
`docs/scoring.md` *"the contract"* and points at it for what a score means and where every
weight came from. Two documents that each declare a different job in their own first
paragraph is what `DOCS-POLICY.md` rule 1 asks for, not the duplication § D read them as.
§ D was written from the file list rather than from the openings. **The real finding is
underneath it and was addressed instead:** `SCORING.md` carried a cost table task 04
superseded and a `76% self-agreement` line task 06 superseded, and both are now marked at
the figure, citing the owning document rather than restating the current number.

**The archive backlog is empty.** If a file is dispositioned for this directory again, it
is moved in the commit that decides it — rule 4 makes retirement an event with a cause,
and a standing *"still to archive"* list is exactly the schedule with no owner that
`DOCS-POLICY.md` § *Choosing between contract and record* warns about.

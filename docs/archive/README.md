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
| [`handoff-session-measurements.md`](handoff-session-measurements.md) | session-by-session narrative of what was measured through 2026-07-31 | live figures are in `HANDOFF.md` § *State at handoff* and in `AUDIT.md` |
| [`handoff-session-method.md`](handoff-session-method.md) | method notes from those sessions | the durable half is promoted to `HANDOFF.md` § *How this run works* |

## Still to archive

These were dispositioned for the archive by task 34 § D and have **not** been moved:
`backend/docs/SCORING.md` (superseded by `docs/scoring.md`; two hand-written scoring docs
is drift) and the persona-bound remainder of `backend/docs/HANDOFF-match-quality.md`
(its § 4 was promoted to [`docs/MEASUREMENT-TRAPS.md`](../MEASUREMENT-TRAPS.md); the rest
measures a non-target persona and its 12.7/20 must be relabelled as imitation fidelity
before anyone quotes it). Both are live citations today, so moving them is a separate
change with its own link sweep.

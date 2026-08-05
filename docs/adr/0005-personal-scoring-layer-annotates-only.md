---
kind: decision
written: 2026-08-05
generator: none
---

# 0005 — The personal scoring layer annotates; resume tailoring is cut

**Status:** accepted. It decides both what the personal layer is and what it deliberately is not.

## Context

Scoring has one layer: the cohort's. `score.py` writes one `gap_bridging_angle` and one
`risk_factors` per `(job_id, profile)` — one narrative shared by roughly thirty Builders. Sharing is
what makes cost flat in users, and `.claude/CLAUDE.md` names it an invariant.

Two drafts asked what a *personal* layer on top would be. The first proposed resume tailoring from a
master work-history document; the second cut tailoring and kept per-Builder narrative scoring.

## Decision

**Resume tailoring is deferred, not rejected.** Every one of its hard problems is downstream of one
requirement: holding a structured work history. That brings a master-document editor (more UI than
the whole client has, under a no-build-step constraint), a storage problem with no good answer, a
rendering problem with no library available, and an ID-addressable design existing only to make "no
invented experience" checkable. None of it appears in the narrative feature.

Six decisions define what survives.

1. **Re-score the same corpus; do not widen it.** A persona can only reorder and annotate what the
   queries went looking for and the gate let through. Widening per Builder also cannot be measured:
   a posting rejected before it reaches anyone never generates the feedback that would show the
   rejection was wrong.
2. **The personal persona layers over the cohort** — same shape as `onboarding.resolve()`: Builder
   override, else cohort, else shared default. The cohort persona stays the floor.
3. **Client-side, on the Builder's own key, and the reason is cost.** Thirty Builders × N postings
   of server-side calls breaks the `(job_id, profile)` keying. That is sufficient alone, and it must
   not be recorded as a privacy decision: a background paragraph is *less* sensitive than the
   `comp_floor` and `situation` `builder_profiles` already holds server-side.
4. **Job detail screen only.** No card may change under a scrolling thumb.
5. **Annotate, never order.** No LLM call may sit between a user and an ordering.
6. **The persona is generated once, reviewed, then reused** — the only point at which a wrong
   inference about a person is visible and correctable. **It is built from background, not
   preferences:** `builder_profiles` already holds the preferences as constrained enums, and asking
   again in prose creates a second source that can contradict it — in a prompt, the prose wins.

## Consequences

- No new API field. Every fact `score._facts_block()` sends the model is already in
  `webapp/jobs.LIST_COLUMNS`. `facts_version` is not, so a client cache cannot reuse the server's
  three cache keys — a hash of the prompt string subsumes them and costs nothing.
- The cohort narrative this sits beside became real on 2026-08-05, when that profile's nightly
  budget went from zero to 200 and the first narratives were written. Whether a personal one
  replaces it or sits beside it is `DEV_TASKS.md`'s `OQ-19`.
- Validating the premise first is blocked, not cheap: this repo refuses to print model-vs-human
  agreement without an inter-annotator ceiling, and has no override. That is `OQ-18`.
- Both drafts are deleted; the first is
  `git show 7dfbc7e:docs/DRAFT-personal-layer-resume-tailoring.md`. Its one finding independent of
  this decision — six onboarding fields collected and read by nothing — is `TASKS.md`'s `T-23`.

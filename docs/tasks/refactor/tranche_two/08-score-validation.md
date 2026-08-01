---
kind: task
written: 2026-07-28
generator: none
---

# 08 — Score validation

**Status:** ~~todo.~~ **DONE, `e1cdf7b`.** **Depends on:** 07. **Blocks:** nothing, but
should precede 30.
**Corrected 2026-07-30:** this line still read `todo` after the task landed.
[`README.md`](../README.md)'s Phase 1 row for 08 says `done` and records the finding —
*"the bucket reproduces at 89%, the number at 24%"* — and `HANDOFF.md`'s *State at
handoff* table carries `08 | score validation, score.normalize(), D15/D16/D43/D44 |
e1cdf7b`. `git log -1 e1cdf7b` reads *"Score validation, score.normalize(),
D15/D16/D43/D44 (tranche_two/08)"*. The stale `todo` made this task look like a live
dependency of 30.

**This task is [`docs/ingestion_tests/04-score-validation.md`](../../../ingestion_tests/04-score-validation.md).**
It needs almost no amendment. This file records the two places the pivot touches it.

## What carries over unchanged

The framing at `04:8-37` is the important part and becomes *more* true under this
plan, not less:

> **It validates the shape of score output, not its accuracy.**
> There is no fact of the matter about whether 72 is the right `fit_score` for a
> posting.

Under the Pursuit scope there is no single target role at all — Builders are at
different stages with a hands-off curriculum. So `fit_score` accuracy is not merely
hard to establish, it is **not well defined**. That is the reasoning behind task 30's
decision to display buckets and reasoning rather than a number, and this task is
where the evidence for it gets recorded.

The defect at `04:38-63` also carries over unchanged: `score.py:359-362` writes
`fit_score` and `primary_track` straight through with no coercion, while
`extract.py:217-247` has `_enum()` and `_int_or_none()` sitting right there, and
`extract.py:34-40` treats exactly this risk as serious — *"'Mid-Level' is a
landmine."*

## What changes

### Run the diagnostic SQL twice

`04` records that this has never been run:

```sql
SELECT primary_track, count(*) FROM job_scores GROUP BY 1 ORDER BY 2 DESC;
SELECT min(fit_score), max(fit_score) FROM job_scores;
```

Run it **before** task 11 and again **after** task 12's re-extraction. The
`primary_track` vocabulary is about to change — task 11 introduces `role_track` and
widens the archetype set — so a coercion rule written against today's five track
names will be wrong within two tasks. Knowing the before-state also tells you whether
any existing garbage was introduced by the model or by the vocabulary change.

### The `buckets` KeyError is a register entry

`04:122` documents a second defect found while tracing the prompt. Give it an id in
`docs/ingest/DEFECTS.md` (task 02) so it is tracked in one place rather than only
inside a task file that will eventually be marked done.

### Expect the tie structure to matter

`HANDOFF-match-quality.md` §4.2 notes 59 postings sharing `fit_score` 85. That is the
documented signature of coarse pointwise scoring, and it interacts directly with this
task: a normalisation rule that silently collapses more values makes it worse. If
`score.normalize()` clamps or rounds, measure the resulting tie distribution before
and after.

## Definition of done

Everything in `04-score-validation.md`'s definition of done, plus:

- The diagnostic SQL is run and its output committed, before and after task 12.
- The `buckets` KeyError has a defect id.
- Tie distribution is reported before and after normalisation.

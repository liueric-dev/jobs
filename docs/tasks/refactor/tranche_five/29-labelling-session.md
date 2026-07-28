# 29 — Two-axis labelling session

**Status:** todo. **Depends on:** 07, 12, 26. **Blocks:** 30, 31.

Collect the first human labels this system has ever had. Everything downstream of
`job_facts` is currently validated against an LLM's opinion of an LLM's output.

## The gap this closes

`docs/ingestion_tests/03` states it plainly: every existing tool substitutes a model
for a human — `claude-bench.py:417` treats sonnet-batch-1 as ground truth,
`calibrate-match.py:47` uses existing `job_scores`. That *"measures agreement, not
correctness, and is blind to any error two models share."*

And `tools/compare-extract.py` measures the model against **itself**, which catches
instability and is structurally blind to systematic error. A model can be perfectly
self-consistent and consistently wrong. Task 06 measured the self-consistency floor;
this task measures the thing above it.

## Two axes, and the split is the durable part

| axis | question | scope | survives a cohort ending? |
|---|---|---|---|
| **A** | Is the extraction correct? Does `seniority_level` match the posting? Is `ai_involvement` right? | objective | **yes — and survives a change of vertical** |
| **B** | Would you apply to this? | subjective | no |

**Axis A is the asset.** It validates `job_facts`, the tier computed once and shared
by every profile forever. It transfers to every future Builder, every future cohort,
and any future vertical. Collect it carefully and it never needs collecting again.

Axis B dies with the cohort. Collect it anyway — it is what task 30 is measured
against — but do not confuse its shelf life with Axis A's.

Label both on the same postings in the same sitting. The marginal cost of the second
axis is small once someone has read the posting.

## The sample

Drawn per task 07's design, stratified — **random sampling would spend labels where
the ranker never operates.**

| bucket | n | answers |
|---|---|---|
| top 20 by `match_score` | 50 | is the head correct |
| ranks ~20–50 | 60 | where does the cutoff belong |
| scored, below `MATCH_FLOOR` | 40 | false negatives from the floor |
| tier-2/3, gate-rejected | 30 | **false negatives from `relevance.py`** |
| the `fit_score` tie block | 20 | does the score have sub-band resolution |

That fourth bucket is the only way recall is estimable. Everything measured to date
was something the pipeline already chose to surface, so only precision has ever been
knowable. `labels.py` must accept rows with no `job_scores` entry at all (task 07).

Pin the sample by sorted `job_id` and never train on it.

## Logistics — you are a Builder, not staff

This shapes the design more than anything else.

There is no roster access and no instructor authority, so this is **asking ~10
classmates for twenty minutes**, not running a sanctioned exercise. Plan accordingly:

- **10 volunteers × 20 postings = 200 labels.** Five volunteers still gets 100, which
  beats zero. Design the analysis to work at either.
- **Overlap 20 postings across everyone.** That gives inter-annotator agreement — the
  ceiling measurement — for the cost of no extra postings. It is a better ceiling than
  one person labelling twice a week apart, and it is free.
- **Twenty minutes, in person, in one sitting.** Asynchronous labelling homework will
  not come back.
- **The interface must assume no terminal.** Task 07 specifies a web form behind the
  existing Google SSO. Build that, not a CLI.
- **Blind to `fit_score`.** Seeing the model's number first collapses a human's
  judgement onto it. This is the single easiest way to invalidate the whole exercise.

It doubles as a class activity with genuine content — evaluating whether a posting is a
realistic target is a skill this population needs, and doing it as a group surfaces
disagreements worth discussing. That is a legitimate reason to ask, not a
rationalisation.

## Analysis

Report three quantities per field, per task 07's design — model self-consistency (from
task 06), inter-annotator agreement, and model-vs-human. **Model-vs-human alone is
uninterpretable**; a model at 80% agreement with humans who agree with each other 78%
of the time is doing well, and the same 80% against humans agreeing 96% is not.

Break out by source platform. Task 06's reconciliation predicts extraction degrades on
messy sources, and Phase 3 just added several. A blended number would hide exactly
that effect.

## Gates

| finding | consequence |
|---|---|
| Axis A poor on `ai_involvement` | the cohort's targeting mechanism is unreliable. Return to task 11's mitigation — confidence field or majority-of-3 |
| Axis A poor on the new Phase 3 sources specifically | the extraction prompt needs source-aware handling before those sources are trusted |
| Axis B poor — `fit_score` does not track Builder preference | `persona.json`'s rubric is wrong. Fix it before task 30 does anything with the number |
| Gate-rejected bucket contains good roles | task 10's gate is too tight. Fix before anything else, because no ranking work recovers a posting that never entered |

## Definition of done

- ≥100 labelled postings across both axes, from ≥5 labellers.
- 20 postings overlapped across all labellers; inter-annotator agreement computed.
- All five strata represented, including gate-rejected rows.
- Labellers were blind to `fit_score`.
- Three quantities reported per field, broken out by source platform.
- The sample is pinned and marked never-train.
- The gate decision above is recorded, including which branch was taken.

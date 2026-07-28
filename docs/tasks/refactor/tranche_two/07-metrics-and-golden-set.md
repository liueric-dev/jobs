# 07 — Metrics and the golden set

**Status:** todo. **Depends on:** 06. **Blocks:** 12, 29, 30.

**This task is [`docs/ingestion_tests/03-metrics-and-golden-set.md`](../../ingestion_tests/03-metrics-and-golden-set.md).**
Do not rewrite it — the three-quantity design there is correct and better specified
than anything this plan proposed independently. This file records only what the
Pursuit pivot changes.

## What carries over unchanged

The core insight stands and is the reason this sits on the critical path:

> measuring model-vs-human alone is uninterpretable

Three quantities, not one — model self-consistency (the floor), human self-agreement
(the ceiling), model-vs-human (the question). Task 06 supplies the first at n=120.
This task supplies the other two.

Also unchanged: the observation at `03:7-16` that every existing tool substitutes an
LLM for a human — `claude-bench.py:417` treats sonnet-batch-1 as ground truth,
`calibrate-match.py:47` uses existing `job_scores` — and that this *"measures
agreement, not correctness, and is blind to any error two models share."*

## What changes

### The labels split into two axes

The original task assumes one labeller producing one kind of judgement. The Pursuit
cohort forces a split, and the split is the most durable thing in this whole plan.

| axis | question | scope | transfers? |
|---|---|---|---|
| **A** | Is the extraction correct? Does `seniority_level` match the posting? Is `ai_involvement` right? | objective | **to every future user and every future vertical** |
| **B** | Would you apply to this? | subjective | dies when the cohort changes |

Axis A validates `job_facts` — the one tier computed once and shared by every
profile forever. It has never been measured against a human;
`compare-extract.py` measures the model against *itself*, which catches instability
and is blind to systematic error. A model can be perfectly self-consistent and
consistently wrong.

`labels.py` needs a schema that carries both, keyed independently, so Axis A survives
a cohort ending.

### The labeller is not the author

Labels come from ~10 Builder volunteers (task 29), not from one engineer. Two
consequences for the CLI spec:

- **It must be usable by someone who has never opened a terminal.** The original
  spec's CLI is fine for the author; for Builders it needs to be a web form or a
  single-command wrapper. Simplest path: reuse the existing auth and add a
  `/v1/label` endpoint, since Google SSO and sessions already exist.
- **Human self-agreement becomes inter-annotator agreement.** The original design
  measures one person labelling 5–10 jobs twice, a week apart. With ten labellers you
  get the stronger measurement — overlap 20 postings across all of them and compute
  agreement between people, not just within one. That is a better ceiling and it
  costs nothing extra.

### The sample is stratified for recall, not just precision

The eval set must include postings the pipeline **rejected** — below `MATCH_FLOOR`,
and tier-3 gate rejects. Everything currently measured was something the pipeline
already chose to surface, so only precision is estimable. Task 29 specifies the
strata; this task must make `labels.py` able to hold rows that have no `job_scores`
entry at all.

### `ai_involvement` gets priority

If task 06 shows this field unstable on messy platforms, it is the first field to
label, because it is the cohort's entire targeting mechanism. Sequence Axis A on
`ai_involvement` and `seniority_level` before anything else.

## Definition of done

Everything in `03-metrics-and-golden-set.md`'s definition of done, plus:

- `labels.py` schema carries Axis A and Axis B independently.
- The labelling surface is usable by a non-engineer.
- Inter-annotator agreement is computed, not just intra-annotator.
- The set includes gate-rejected and below-floor rows.
- `docs/ingestion_tests/README.md` links here, so the two trees do not drift.

# 07 — Metrics and the golden set

**Status:** DONE, `3a8b42c`. **Depends on:** 06. **Blocks:** 12, 29, 30.

**This task is [`docs/ingestion_tests/03-metrics-and-golden-set.md`](../../ingestion_tests/03-metrics-and-golden-set.md).**
Do not rewrite it — the three-quantity design there is correct and better specified
than anything this plan proposed independently. This file records only what the
Pursuit pivot changes.

> **Correction, 2026-07-30 — the two ceilings, and this file's own contradiction.**
> Three documents disagreed about which human ceiling gets measured, and the
> disagreement was invisible because each of the three was internally consistent.
> Resolved in § *Both ceilings are collectable now* below; read that before
> § *What changes*, because it retracts a word in it.
>
> The word is **"supersedes"**. This file said inter-annotator
> *"is a better ceiling and it costs nothing extra"* — originally at `:57-59`, now struck
> through at `:71-75` — and its Definition of done asked for it. But the DoD line that
> inherits `docs/ingestion_tests/03-metrics-and-golden-set.md` **wholesale** (`:143`
> now, `:77` when this was written) pulls in that file's requirement of *"the
> self-consistency floor and human self-agreement ceiling beside each number"*
> (`03:179` now, `03:142` when this was written) — and `03:25` defines human
> self-agreement as *"5-10 jobs labelled twice, a week apart"*, the **intra**-annotator
> quantity. So this file simultaneously replaced a requirement and inherited it.
>
> **Every cross-reference in this block is given twice on purpose**, because writing
> this correction moved the lines it cites. Quote the text; the digits decay.

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
- ~~**Human self-agreement becomes inter-annotator agreement.** The original design
  measures one person labelling 5–10 jobs twice, a week apart. With ten labellers you
  get the stronger measurement — overlap 20 postings across all of them and compute
  agreement between people, not just within one. That is a better ceiling and it
  costs nothing extra.~~
  **AMENDED 2026-07-30. "Becomes" was wrong and "costs nothing extra" was wrong.**
  Inter-annotator does not *replace* intra-annotator — they are different quantities
  and `test_the_two_ceilings_are_different_quantities`
  (`backend/tests/test_labels.py:464` as of 2026-07-30 — cite it by NAME, the number
  has moved twice) exists because that distinction is the point. Inter-annotator is free on an overlapped set; intra-annotator costs a
  **second sitting per labeller, seven days later**
  (`backend/evals/labels.py:1007`, `ROUND_TWO_DELAY_DAYS = 7`). The reading that
  survives: inter-annotator is the **better** ceiling and the one that comes free, and
  intra-annotator is the **weaker** one kept because attrition may leave it as the only
  one with any n (`labels.py:1358`).

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

## Both ceilings are collectable now

**Added 2026-07-30.** Until this date the intra-annotator ceiling was **unreachable
from production**, which is why nobody had to resolve the contradiction above:
`labels.intra_annotator()` was correct and tested and no code path could ever feed it.
`webapp/label.py` never passed `round_no` to `labels.record()`, and `next_item()`'s
queue filter had no `round_no` predicate at all — so once a labeller answered a
posting it was never served to them again, and `round_no` was 1 on every row that
could ever exist.

That is fixed. `next_item(..., round_no=2)` serves the **overlap block only**,
restricted to rows that labeller answered in round 1 and has not answered in round 2
(`backend/evals/labels.py:1112-1145`); `labels.round_two_ready()` (`:1010`) enforces
the seven-day delay and returns a **date**, so the form can say *"come back on the
8th"* rather than showing an empty page; `progress()` counts round 2 against the
overlap block rather than the 200-row set (`:903-925`); and the form carries `?round=2`
through the POST and the 303 (`webapp/label.py:257`, `:320`, `:360`).

**So the "second pass" clause is TRUE AGAIN** — `03:127-128`, which was `03:107-108`
before this update grew that file. It claims the tool *"supports a second pass over
already-labelled jobs for the self-agreement figure"*, and from the day it was written
until 2026-07-30 that sentence was false — the CLI it describes never existed, and
the web form that replaced it could not re-serve a posting. It now describes something
real, reached a different way than it imagined.

**What this resolves, and what it deliberately does not.** The capability question is
closed: both ceilings are collectable, on **identical postings** — round 2 re-serves
the same overlap block the inter-annotator ceiling is computed over, so the two can be
read against each other rather than differing for two reasons at once
(`labels.py:1068-1080`).

**The spending question is open and is not an implementer's to close.** The
intra-annotator ceiling costs every volunteer a **second sitting of ~10 minutes, seven
days after the first** — and that delay is the measurement, not politeness: served an
hour later it measures whether they remember their first answer
(`labels.py:996-1006`). Whether ten volunteers' second ten minutes is worth the
weaker of two ceilings is a judgement about people who are donating their time, and it
belongs to the repo owner on the night. **This file does not decide it.** Both paths
are implemented; the round-2 link is simply not sent unless someone chooses to send it
(`docs/tasks/refactor/LABELLING-NIGHT.md`, § *Optional follow-up*).

## Definition of done

Everything in `03-metrics-and-golden-set.md`'s definition of done, plus:

- `labels.py` schema carries Axis A and Axis B independently.
- The labelling surface is usable by a non-engineer.
- ~~Inter-annotator agreement is computed, not just intra-annotator.~~
  **AMENDED 2026-07-30: both are computed, and neither is inherited away.** Read this
  line as "inter-annotator agreement is computed **as well as** intra-annotator" —
  which is also what `:143`'s wholesale inheritance of `03:179` requires, and the two
  requirements are now consistent rather than in conflict. **`interpretable()`
  (`labels.py:1682`) accepts the INTER-annotator cell as `ceiling`**, so a report is
  renderable with the free ceiling alone; the intra-annotator figure is an additional
  number, not a gate on printing anything.
- The set includes gate-rejected and below-floor rows.
- `docs/ingestion_tests/README.md` links here, so the two trees do not drift.

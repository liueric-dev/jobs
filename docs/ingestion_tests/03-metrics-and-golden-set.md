# 03 — Metrics and the golden set

**Status:** next. **Depends on:** 02. **Blocks:** 04.

Turn a run into a number that means something, against labels a human wrote.

## Why this is the hard one

[`backend/docs/DEVELOPER.md:21`](../../backend/docs/DEVELOPER.md) has
specified this since before the harness
existed — "build a golden set of ~20-30 already-scored jobs with hand-checked
expected `primary_track`/rough score" — and it was never built. So every tool
substitutes an LLM for a human: `claude-bench.py:417` treats sonnet-batch-1 as
ground truth, `calibrate-match.py:47` uses existing `job_scores`. That measures
agreement, not correctness, and is blind to any error two models share.

## Measure three quantities, not one

This is the change forced by the self-consistency finding in the
[README](README.md). Measuring model-vs-human alone is uninterpretable.

| quantity | how | why |
|---|---|---|
| **model self-consistency** | same model, same prompt, N runs | the floor. `deepseek-v4-flash` at temperature 0 agrees with itself 76% on `seniority_level` (n=17, provisional) |
| **human self-agreement** | 5-10 jobs labelled twice, a week apart | the ceiling. Without it, "80% agreement" has no scale |
| **model vs human** | the actual question | only interpretable between the two above |

**Do this first, before any labelling:** re-run the self-consistency
measurement at n=120 with `--repeat 3`. It is cheap, it needs no human time,
and it decides whether the 76% figure is real or an artifact of 17 jobs. If it
holds, it also means `backend/config/criteria.json`'s calibration rests on a number
measured only on the easy sources — which is a finding in its own right and
belongs back in `docs/ingest/extract.md`.

**Report that run per platform, not just in aggregate.** The
[README](README.md) states the likely reconciliation as corpus rather than
model — `compare-extract.py` selects `ORDER BY first_seen DESC`, which is ~85%
greenhouse and ashby, while `corpus-v1.jsonl` is stratified across all seven
and includes HN free-text. That hypothesis is directly testable and the
fixture is *already* stratified, so a per-platform breakdown costs nothing
beyond a `GROUP BY` in the reporting. It is the difference between "the model
agrees with itself 76% of the time" and "the model agrees with itself 95% on
clean ATS postings and 50% on HN," which are the same number and completely
different findings.

If it is the second, agreement is a property of the *source*, not of the model,
and every figure downstream — including the golden-set numbers — has to be
reported stratified or it averages two populations that do not belong in the
same mean.

## Work

### `runner.py` — add `--repeat N`

Currently one call per record. Self-consistency needs N, with cache keys
disambiguated per repeat (the cache is content-addressed, so repeat 2 would
otherwise hit repeat 1's entry and report perfect agreement — a silent, very
convincing bug). Simplest correct approach: bypass the cache entirely when
`repeat > 1`, since the measurement is about live variance.

### `metrics.py`

Promote `tools/compare-extract.py:52-60` rather than rewriting it. Comparison
runs **after `normalize()`** — comparing raw output would score formatting,
and `"Mid-Level"` vs `"mid"` is the same answer.

| kind | rule | fields |
|---|---|---|
| `enum` | exact after `normalize()` | `seniority_level`, `role_archetype`, `ai_involvement`, `remote_policy`, `employment_type`, `visa_sponsorship`, `comp_currency` |
| `bool` | exact | `ml_research_required`, `advanced_degree_required`, `customer_facing`, `gap_friendly_language` |
| `int` | exact; `None` distinct from `0` | `years_experience_*`, `comp_*` |
| `set` | Jaccard (`compare-extract.py:jaccard`) | `tech_stack` |
| `prose` | not compared | `summary` |

`tasks/extract.py` already declares `FIELD_KINDS` and `PRIORITY_FIELDS` for
this to read. For scoring (task 04), `fit_score` additionally needs a ±N
tolerance band **and** rank correlation — `calibrate-match.py` is right that
ranking is what matters, since a score 15 points low on a job nobody scrolls
to costs nothing.

Cost accounting: lift `tools/cost-test.py:115` `usage_fields()`, which already
handles the cache split and reasoning tokens correctly across both wire shapes.

**Scope note: this measures the cost of an *eval* run, not of production.** The
pipeline records no usage at all, and no task in this list owns fixing that.
`llm.Completion` carries `usage`, `latency_s` and `cost_usd`
(`llm.py:133-151`), but `llm.call()` returns `.text` and drops the rest
(`llm.py:170`) — and both stages call `llm.call`, not `call_detailed`, whose
only caller today is `evals/runner.py:92`. What survives per row is
`job_facts.extraction_model` / `job_scores.scoring_model` and a timestamp:
no token counts, no cache-hit counts, no latency, no cost. `ratelimit.py`
counts *requests* per model per day, never tokens.

The consequence is that "what did last night's run cost" cannot be answered
from the database — only by re-running the corpus under `tools/cost-test.py`
and paying for it a second time. Recorded here because this is where cost
accounting is discussed; whether it becomes its own task is an open decision.

### `labels.py` and the labelling CLI

```
python3 -m evals label --corpus evals/fixtures/corpus-v1.jsonl --n 30
```

Writes `evals/fixtures/golden-v1.jsonl`, keyed by job id, **separate from the
corpus** so the two version independently. Records labeller and timestamp, and
supports a second pass over already-labelled jobs for the self-agreement
figure.

**Label only `PRIORITY_FIELDS` first.** 30 jobs × 17 extract fields is a lot of
human hours, and the five in `PRIORITY_FIELDS` are the ones `match.py` scores
on — an error in `seniority_level` changes what a person is shown, an error in
`comp_currency` does not. `metrics.py` scores only labelled fields, so the set
deepens later without rework.

**Let the selfcheck narrow that set further.** This is the second reason the
self-consistency run comes first, and the more useful one: a field that cannot
agree with *itself* will not be rescued by human labels. Labelling it produces
a number, but the number describes variance, and the fix it points to is a
prompt or model change rather than anything a golden set can supply. Spend the
labelling budget where a label can actually settle a disagreement, and record
the rest as known-unstable.

Sample the 30 from the existing 120-record fixture with
`corpus.stratify(seed=...)` so the pathology buckets are represented, and show
the labeller the full `description_text` — the point is a human judgement on
the same input the model got.

### `report.py`

Add an agreement table and a `compare` subcommand for two runs. Keep the
existing rule: no cost or latency from replayed data.

## Definition of done

- `python3 -m evals selfcheck --model "$SPEC" --n 120 --repeat 3` prints
  per-field self-consistency, broken down by platform as well as in aggregate
- the per-platform split is compared against the README's corpus hypothesis,
  and the answer decides whether later figures are reported stratified
- `python3 -m evals label` produces `golden-v1.jsonl`
- `python3 -m evals run --golden` prints model-vs-human per field, with the
  self-consistency floor and human self-agreement ceiling beside each number
- new tests in `tests/test_evals.py`, still no network and no database
- if the n=120 self-consistency figure diverges from
  `backend/config/criteria.json`'s 95%, that is written up — do not silently re-tune
  penalties

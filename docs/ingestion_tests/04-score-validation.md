---
kind: task
written: 2026-07-27
generator: none
---

# 04 — Score validation, and a `score` task

**Status:** todo. **Depends on:** 03. **Blocks:** nothing.

Close audit item 8 using the harness, rather than by reading the code and
hoping.

## What this task can and cannot establish

**It validates the shape of score output, not its accuracy.** Worth stating
before the work, because task 03's machinery makes it easy to assume otherwise
and the assumption produces an acceptance criterion nothing can satisfy.

Extraction is checkable. `tools/compare-extract.py:6-20` makes the argument:
its fields are closed vocabularies over facts a posting either states or does
not, so a disagreement is unambiguous and one of the two answers is simply
wrong. A human label settles it.

Scoring has no such ground truth. There is no fact of the matter about whether
72 is the right `fit_score` for a posting, and a labeller asked to produce one
is inventing a number, not recording an observation. `tools/calibrate-match.py`
already reached the same conclusion from the other direction — *ranking* is the
measurable property, since a score 15 points low on a job nobody scrolls to
costs nothing.

And the only honest source of ranking ground truth is engagement:
`job_events` (`schema.py:391-400`), which records the event alongside the
`match_score` and `fit_score` in force at the time. It has zero rows, and
`schema.py:385-390` says outright that nothing in the pipeline reads it. Its
one consumer is a boolean liveness check at `score.py:552-570` deciding whether
a profile is worth spending calls on.

So: this task makes `job_scores` well-formed and its enum enforceable. Whether
`fit_score` is *good* stays open until `job_events` has data, which makes what
the webapp's event endpoint captures a prerequisite for ever answering it — a
dependency worth naming now rather than discovering later.

## The defect

`score.py:359-362` writes model output straight through:

```python
result.get("fit_score"),
result.get("primary_track"),
```

The prompt asks for an integer 0-100 and one of five track names
(`score.py:325-326`), but unlike `extract.py` nothing normalises them.
`extract.py:217-247` has `_enum()` and `_int_or_none()` sitting right there,
and `extract.py:34-40` treats exactly this risk as serious — *"'Mid-Level' is
a landmine"*. Full write-up in [`docs/ingest/score.md`](../ingest/score.md).

**Check what is actually stored before deciding how much to coerce:**

```sql
SELECT primary_track, count(*) FROM job_scores GROUP BY 1 ORDER BY 2 DESC;
SELECT min(fit_score), max(fit_score) FROM job_scores;
```

This has not been run. It may show the problem is theoretical, or it may show
a spread of `"Core SWE "`, `"core_swe"` and `"AI integration"` already in the
column. Either way the answer shapes the fix.

## The vocabularies differ, and that is the trap

`extract._enum()` lowercases and replaces spaces and hyphens with underscores,
because extraction's vocabularies are already `snake_case`
(`extract.py:82-93`). Scoring's are **Title Case with spaces**:

```
Core SWE | AI Integration | Bridge & Solutions | Re-Entry & Growth | Poor Fit
```

Passing those through `_enum()` unchanged would map `"Core SWE"` to
`"core_swe"` and silently rewrite every value in `job_scores.primary_track`.
So `score.normalize()` needs its own vocabulary constant and either a
canonicalising comparison or a display-form lookup — not a reuse of extract's
coercion as-is.

Decide deliberately whether the *stored* form stays Title Case. It is what
`job_scores` holds today and what any consumer reads; changing it is a
migration, not a normalisation.

## Work

### `evals/tasks/score.py`

Adapter over `score.build_prompt(persona, job)` and the new
`score.normalize()`. Needs `score.load_persona()` and a profile — take it from
`schema.resolve_profile(persona)` as `score.py:main` does. The fixture already
carries the `job_facts` columns `_facts_block` needs, so no new corpus work.

**The persona is the fixture contract.** `build_prompt` reads exactly five
keys — `background_summary`, `strengths[]`, `honest_gaps[]`, `buckets{}` and
`scoring_instructions` (`score.py:290-318`) — and nothing else about the user
reaches any prompt in the pipeline. Pin those five in the eval and the input is
fully determined; a change to any of them is a re-score, and the harness should
treat a persona edit the way it treats a model change.

Field kinds for `metrics.py`:

| field | kind |
|---|---|
| `fit_score` | `int`, compared **run-to-run** — tolerance band for drift, rank correlation for ordering. Not against a label; see the boundary above |
| `primary_track` | `enum` (Title Case vocabulary) |
| `gap_friendly_signal` | `bool` |
| `key_technologies` | `set` |
| `gap_bridging_angle`, `risk_factors` | `prose` — not compared |

Self-consistency is the metric that survives the missing ground truth: two runs
of the same persona over the same corpus should rank the same postings the same
way, and a model that cannot reproduce its own ordering is disqualified without
anyone having to agree on what the right ordering was.

### `score.normalize()`

Mirrors `extract.normalize()`: returns the exact column values `job_scores`
stores, or `None` when the response is unusable at all, which the caller turns
into a tombstone. Validate it against **real cached responses** from task 02's
cache — that is what the raw-text-pre-`parse_json` storage decision was for.

### A second defect, found while tracing the prompt: the `buckets` KeyError

Not part of audit item 8, but it lives in this stage and the fix touches the
same two files.

`build_prompt` hard-indexes three persona keys (`score.py:290-295`):

```python
for name, b in persona["buckets"].items()
"\n".join(f"- {s}" for s in persona["strengths"])
"\n".join(f"- {g}" for g in persona["honest_gaps"])
```

`profiles.validate()` requires four keys, and `buckets` is not among them
(`profiles.py:139-142`):

```python
for key in ("background_summary", "strengths", "honest_gaps",
            "scoring_instructions"):
```

So a profile saved without `buckets` validates cleanly and then raises
`KeyError` at scoring time, and nothing catches it.

`score_one_job` calls `build_prompt` at `score.py:421`, inside a `try` whose
only clause is `finally: conn.close()` (`score.py:451-452`) — it releases the
connection and re-raises. The one real handler is the *inner* try at `:422`,
which sits below `build_prompt` and catches only `llm.TransientError` and
`(RuntimeError, json.JSONDecodeError)` around the `llm.call`. A `KeyError`
raised while building the prompt passes both.

`run_for_profile` then materialises `pool.map` through `list()`
(`score.py:478-481`), so the exception surfaces there and takes down the whole
profile's batch — and because every job in that batch shares the persona, the
first job to fail is also the last.

The irony is worth recording, because it is the argument for the fix.
`validate()`'s own docstring says the point is that a bad profile

> fails at the moment someone saves it, naming the field, rather than at 3am
> inside a thread pool where the only evidence is a deferred batch.

That is precisely the failure it does not prevent — and the outcome is worse
than the one it describes, because a deferred batch is at least recorded.
Nothing here is.

Two changes, and they are independent:

- add `buckets` to `validate()`'s required keys, so it fails at save time as
  intended. Cheap, and it is what the docstring already promises.
- guard the per-job body in `score_one_job` so an unexpected exception
  tombstones or defers one job rather than killing the run. This is the same
  missing-per-record-isolation class as audit item 3 in
  [`05-fetcher-harness.md`](05-fetcher-harness.md) — `match.py` at `:290,304`.
  Fixing only the first leaves the batch fragile to the next unguarded
  `KeyError`; fixing only the second hides malformed profiles until 3am.

`profiles.py` is on the production write path, so this stays additive and is
verified by the existing suite.

### Tests

`tests/test_evals.py` gains end-to-end coverage of `score_one_job` off cached
fixtures — the first such test in the suite, joining the existing no-network
arrangement.

A profile missing `buckets` is a natural unit test for both halves: that
`validate()` now rejects it, and that `score_one_job` degrades to one lost job
rather than an exception escaping `run_for_profile`.

## Definition of done

- the two SQL checks above are run and their answers recorded here
- `score.normalize()` exists, with its own vocabulary, and is exercised
  against real malformed responses from the cache
- `python3 -m evals run --task score` works against `corpus-v1.jsonl`
- `profiles.validate()` requires `buckets`, and `score_one_job` cannot let one
  job's exception end the batch — both covered by tests
- `python3 -m unittest discover -s tests -t .` green
- audit item 8 marked closed in [`docs/ingest/score.md`](../ingest/score.md)

Explicitly **not** in scope, per the boundary at the top: any claim about
whether `fit_score` values are correct. This task ends at well-formed and
self-consistent. Correctness waits on `job_events`.

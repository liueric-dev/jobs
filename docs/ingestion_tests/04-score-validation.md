# 04 — Score validation, and a `score` task

**Status:** todo. **Depends on:** 03. **Blocks:** nothing.

Close audit item 8 using the harness, rather than by reading the code and
hoping.

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

Field kinds for `metrics.py`:

| field | kind |
|---|---|
| `fit_score` | `int` + tolerance band + rank correlation |
| `primary_track` | `enum` (Title Case vocabulary) |
| `gap_friendly_signal` | `bool` |
| `key_technologies` | `set` |
| `gap_bridging_angle`, `risk_factors` | `prose` — not compared |

### `score.normalize()`

Mirrors `extract.normalize()`: returns the exact column values `job_scores`
stores, or `None` when the response is unusable at all, which the caller turns
into a tombstone. Validate it against **real cached responses** from task 02's
cache — that is what the raw-text-pre-`parse_json` storage decision was for.

### Tests

`tests/test_evals.py` gains end-to-end coverage of `score_one_job` off cached
fixtures — the first such test in the suite, joining the existing no-network
arrangement.

## Definition of done

- the two SQL checks above are run and their answers recorded here
- `score.normalize()` exists, with its own vocabulary, and is exercised
  against real malformed responses from the cache
- `python3 -m evals run --task score` works against `corpus-v1.jsonl`
- `python3 -m unittest discover -s tests -t .` green
- audit item 8 marked closed in [`docs/ingest/score.md`](../ingest/score.md)

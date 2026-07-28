# 03 — Stop discarding upsert errors

**Status:** DONE, `e353e3e`. **Depends on:** 02 (for the register entry). **Blocks:** all of
Phase 3.

Every ingest script throws away per-record upsert failures. Fix it in one place
before writing five more scripts from the same template.

## The defect

`backend/lib/upsert.py` returns an `UpsertResult` carrying inserted, updated and
**errors**. `__iter__` (`:164-166`) yields the first three as a tuple, so this reads
naturally and is wrong:

```python
inserted, updated, skipped = upsert(...)   # .errors never touched
```

Confirmed at four call sites, each independently documented by the audit:

| script | line | audit note |
|---|---|---|
| `ingest/ats.py` | 337 | the original; the others cite it |
| `ingest/builtin-nyc.py` | 404 | `docs/ingest/builtin-nyc.md:340` |
| `ingest/google-serpapi.py` | 325 | `docs/ingest/google-serpapi.md:362` |
| `ingest/weworkremotely.py` | 225 | `docs/ingest/weworkremotely.md:305` |

Audit the remaining sources — `hn-hiring.py`, `google-apify.py`, and the contributor
path in `backend/api/query_claims.py:425-446` — before assuming four is the total.

## Why this is the one that blocks Phase 3

A run with a hundred failed records and zero read errors reports success. There is no
alert, no non-zero exit, no log line. The only symptom is that the corpus is quietly
smaller than it should be — which is indistinguishable from a slow hiring week.

Phase 3 adds seven ingest paths. Written from these templates, they inherit it. And
the new sources are exactly the ones where per-record failures are *likely*:
government feeds with unusual field shapes, Workday tenants with varying schemas,
JSON-LD of wildly varying completeness.

This is the same failure mode named in
[`ADDENDUM-google-jobs-providers.md`](../../../ADDENDUM-google-jobs-providers.md) §5
for SERP providers — an exhausted key returns zero rows, not an exception. Silence is
the house failure mode of this pipeline, and the alerting fix in task 04 depends on
this data being available to alert on.

## Work

### `lib/upsert.py`

Do not change `__iter__` — the tuple unpack is used widely and `lib/` is vendored,
byte-identical to another repo (`3972fb8`), with drift reported by
`tools/lib-parity.sh`. Changing shared semantics here creates parity churn for a
problem that belongs to the callers.

Instead add a helper that makes the correct thing the easy thing:

```python
def upsert_checked(*args, threshold=0.0, logger=None, **kwargs) -> UpsertResult:
    """Upsert, log any per-record errors, and raise if the failure rate
    exceeds `threshold`. Returns the full result including .errors."""
```

If `lib/` must stay byte-identical, put `upsert_checked` in `backend/ingest/_common.py`
instead and note the reason in a comment. Parity matters more than location.

### Every call site

Replace the three-tuple unpack with `upsert_checked`. Each ingest script should:

- log a summary line including the error count, always — including when it is zero,
  so the absence of the field is visibly a bug rather than good news
- raise when the per-run failure rate exceeds a threshold (start at 5%, tune once
  there is data)
- include the error count in whatever `run-daily.py` reports, so a partial failure is
  visible in the nightly summary rather than only in a log file

### `run-daily.py`

`:169` prints `{len(failures)}/{len(STEPS)} step(s) failed`. A step that upserted 400
records and dropped 100 currently counts as a success. Extend the summary to carry
per-step record counts and error counts.

### Tests

One test per ingest path, asserting that a deliberately malformed record produces a
non-zero `.errors` and a raised exception at the threshold. These are cheap now and
become cassette-backed in task 09.

## Definition of done

- `grep -rn "= upsert(" backend/` returns no bare three-tuple unpacks.
- Every ingest script logs an error count on every run.
- A malformed-record test exists per path and fails loudly.
- `run-daily.py`'s summary distinguishes "ran and wrote nothing" from "ran and
  dropped everything."
- The register entry from task 02 is marked fixed with this commit.

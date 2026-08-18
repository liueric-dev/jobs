---
paths:
  - "backend/ingest/**"
---

# Ingest landmines

**Silence is this system's failure mode.** Exhausted keys, revoked keys, blocked scrapers and
changed endpoints all return zero rows rather than raising. Alert on volume, not errors —
`tools/volume-check.py` is what watches for this, and it is the only thing that does.

**Use `upsert_checked`, and read `.errors`.** `UpsertResult.__iter__` yields three values
(`new, updated, unchanged`), so a bare three-tuple unpack silently discards `.errors`. Every
current call site in this tree is correct — this is a rule to preserve, not a defect to go fix.
`upsert_checked` logs the error count on every call (even when it is zero) and raises
`UpsertErrorRate` past a threshold; `upsert()` itself does neither.

**Workday `limit` cannot exceed 20.** Ask for 100 and it returns an empty array with no error,
identical to "no more results." `_check_page_limit()` in `ingest/workday.py` raises rather than
letting a future edit override `PAGE_LIMIT` upward.

**A throttled page is not the end of a list.** Reconcile collected counts against the `total` the
API returned rather than trusting an empty page. One published account lost 1,960 of 2,000 jobs to
this exact failure on Workday's CXS endpoint.

**The reconciliation cannot be an equality, and the tolerance is one page, not a number.**
`ingest/workday.py:520-537` is the argument: a board changes while it is being walked — Nordstrom
answered `total=867` and yielded 865 over the next 100 seconds — so a strict check would cost the
largest boards whole nights for nothing. A deficit smaller than `limit` cannot be a lost page and
does not raise (`:538-540`); it is still reported, as a printed `workday-ingest: ALERT` line rather
than an exit code (`:1189-1193`, printed at `:1202-1203`). **A run that alerts and exits 0 is the
designed path, so a green exit is not evidence a board came back whole.**

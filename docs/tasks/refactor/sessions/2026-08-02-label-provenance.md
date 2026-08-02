---
kind: record
written: 2026-08-02
generator: none
---

# Session record — 2026-08-02, `facts_version` on `eval_labels`

**Frozen on write.** A `record` says what happened on a date and is corrected by a later
record rather than rewritten ([`../../../DOCS-POLICY.md`](../../../DOCS-POLICY.md) rule 4).
Nothing here is a figure: [`AUDIT.md`](../AUDIT.md) owns the run-level numbers and
[`../../../labelling-report-2026-08-02.md`](../../../labelling-report-2026-08-02.md) owns the
labelling ones.

## What was taken, and why this one

The first of the three items [`../HANDOFF.md`](../HANDOFF.md) § *What is next* listed. It
was picked over the other two for one reason: it was the only one with a deadline. Round 2
matures ~2026-08-09, and every label written without provenance is a row that can never
acquire any.

## What landed

`eval_labels` gains two columns, `facts_version` and `facts_version_known`, written by
`labels.record()` as a scalar subquery inside its existing `INSERT`. `DEC-95` carries the
argument for two columns rather than one and for refusing the backfill; it is not restated
here.

Six behavioural tests against a real Postgres scratch schema, five structural ones, and two
in the webapp suite. **All thirteen were watched failing against the unfixed code** —
`git stash push` on the three source files with the tests left in place — and nothing else
failed in that state.

## Four things a next session should not re-derive

**`scratchdb.scratch_schema()` already runs the pipeline's full `ensure_schema()`**
(`evals/scratchdb.py`), so `job_facts` exists in every scratch schema and the label tests
needed no new fixture. The plan for this work assumed otherwise and was wrong.

**`job_facts` is declared in `labels.WEB_READS`, deliberately not in `WEB_PRIVILEGES`.**
Two reasons, and the second is the one that would have bitten. `set(WEB_PRIVILEGES) ==
set(TABLES)` is a real invariant with a test on it. And `webapp/schema_web.py` does
`REQUIRED_TABLES.update(_labels.WEB_PRIVILEGES)` over a dict that **already declares
`job_facts` at line 45** — identical today, so a merge would be invisible, and silently
authoritative the day the two disagree.

**No GRANT was needed and that was verified rather than assumed.** Both startup gates were
run against the live database as `jobs_web`: `schema_web.verify_schema()` and
`labels.verify_schema()` both returned clean.

**`DECISIONS.md`'s allocator was stale by one before this session touched it** — it read
*"Allocated `DEC-46`–`DEC-93`"* while `DEC-94` was already in the file. Corrected to
`DEC-95` in passing. Rule 6 gives the register one allocator; nothing checks that the
allocator has kept up.

## The live migration

`python3 -m evals label init-schema` ran against the live database. `add_missing_columns`
took the additive path, every pre-existing label row read back as unrecorded, and the label,
posting and labeller counts were unchanged by it. `evals label status` prints the
provenance breakdown; `label report` was deliberately left alone, because its output is a
committed document and this command owns nothing.

## What is NOT done

**The end-to-end submit through `/v1/label` was not performed.** It needs a session cookie
and a real judgement, and writing a fabricated label into `eval_labels` to prove a column
works would put invented evidence in the one table this whole subsystem exists to keep
clean. The write path is proven against real Postgres in the scratch schema instead. The
first genuine label of round 2 is what will confirm it in production.

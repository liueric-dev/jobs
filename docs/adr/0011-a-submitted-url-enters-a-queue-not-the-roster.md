---
kind: decision
written: 2026-08-18
generator: none
---

# 0011 — a submitted URL enters a queue the pipeline drains, never the ATS roster

**Status:** accepted, 2026-08-18. Answers `T-63`, which holds the measurements this rests on.

## Context

The submission channel was chosen on its compounding half: a pasted URL that resolves to an ATS slug
seeds the roster, and that employer's whole board is pulled nightly from then on. The instruction
said to reuse the discovery tool and did not say who writes the roster row. That is the decision.

**Three measured facts constrain it, each recorded in `T-63` with its command.** The roster table
`company_ats` is created by a function `backend/tools/ats-discover.py` calls on every run and
`backend/tools/provision-database.py` does not call at all. Slug detection is a pure function over
text in `backend/ats_discovery.py`, not in the CLI the instruction named, and it imports only stdlib
— so which process detects is not forced by dependencies, and a pasted URL can be identified with no
network. And `backend/ingest/ats_sources.py` admits `unvalidated` rows beside `valid` ones, with
discovery ordered before ingest in `backend/run-daily.py`, so a token that arrives today is pulled
tonight without a probe in between.

**What settles it is not a measurement.** `backend/schema.py:992` states the rule this repo uses
for every table two processes touch — *ownership follows who computes* — and
[`0009`](0009-run-statistics-are-reconciled-not-granted.md) applied it to the neighbouring case: a
contributor's run reaches `search_queries` as a row the nightly step reconciles, never as a widened
GRANT. A Builder's paste is the same shape of claim from the same direction.

## Decision

**The webapp identifies and never writes the roster.** A submission stores what the paste looked like
— identified platform and token beside the raw URL — in a pipeline-owned table the service holds
`SELECT, INSERT` and no `UPDATE` on, which is the `search_queries` grant shape. It reaches
`ats_discovery` through the `sys.path` insert `backend/webapp/config.py` already performs: nothing
installed, no dependency added, `include-system-site-packages = false` untouched.

**`tools/ats-discover.py` drains the queue**, because it owns the roster, already creates its schema,
already writes through the shared `TableSpec`, and already runs before ingest. Submitted rows enter
`unvalidated` with `discovered_via` naming the channel: pulled that night, and told apart from probed
rows in every report after. **Identification is offline**: confirming a token or reading a careers
page is the probe's work, on the probe's schedule and inside its error accounting, so no request path
fetches a URL.

**`company_ats` and `ats_seed` join `provision-database.py`'s step list; their rows do not.** The DDL
function is idempotent and writes no rows, which is what makes it a step rather than a migration.
Which employers to probe stays an operator act.

**A per-Builder daily cap is counted in SQL over the submission table**, the shape `api/app.py`
already meters claims with. Neither service has an HTTP rate limiter and this does not add one.

## Consequences

**Given up:** immediacy — a paste compounds on the next nightly run, not on submit — and any path for
a Builder to correct a roster row they seeded. Both are what keeps the grant where it is.

**Gained:** no new privilege crosses the two roles; a mistaken paste costs one row and one 404 the
probe converts to `dead` on its own schedule; provenance is a column that already exists.

**Residual:** the detector recognises platforms `ingest/ats.py` cannot pull, so a submission can be
understood and still not compound — recorded rather than silent. And the pipeline's own tables have
no `verify_schema` at all; two more in the step list does not change that (`T-65`).

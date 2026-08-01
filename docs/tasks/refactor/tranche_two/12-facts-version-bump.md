---
kind: task
written: 2026-07-28
generator: none
---

# 12 — `FACTS_VERSION` bump and re-extract

**Status:** ~~todo.~~ **DONE, `c4a8ff5` and `2b4dba2`.** **Depends on:** 04, 07, 11.
**Blocks:** 13, 30.
**Corrected 2026-07-30:** this line still read `todo` after the task landed.
[`README.md`](../README.md)'s Phase 2 row for 12 says `done` — *"the extraction gate
retargeted to `pursuit`, which took the bump from 5,317 rows to 863"* — and `HANDOFF.md`'s
*State at handoff* table carries `12 | FACTS_VERSION 3, extraction gate retargeted to
pursuit | c4a8ff5, 2b4dba2`. `git log -1 c4a8ff5` reads *"FACTS_VERSION 3, retarget the
extraction gate to pursuit (tranche_two/12)"*; `2b4dba2` is *"Sharpen 12's ai_operations
re-check: the spread, not the 3.4x"*. Task 13 was **not** blocked by this when it ran.

Carry task 11's three changes into `job_facts` with one version bump and one full
re-extraction.

## Why one bump and not three

Task 11 changes the archetype vocabulary, adds `role_track`, and adds missingness
handling. Each independently invalidates every existing `job_facts` row. Three bumps
means three full re-extractions; one bump means one.

It also re-validates `ai_involvement` for free — a field extracted under a prompt
written for software roles, which has never been checked against non-tech text, and
which is now the cohort's entire targeting mechanism.

## Why it is gated on task 07

The instinct is to bump first and measure after. Do the opposite.

Task 07 lands the golden set and Axis A labels — extraction correctness against a
human. Running that **before** the bump gives a baseline for the current prompt on
the current corpus. Running it again after gives a comparison. Bump first and there
is no fixed point; you will have changed the vocabulary, the corpus and the prompt
simultaneously and be unable to attribute any movement to any of them.

This is the trap `HANDOFF-match-quality.md` §4 documents in three separate forms.

## Why it is gated on task 04

`SCORING.md` estimates ~$0.000385/posting, so ~$4 for the current 11,517 rows. The
money is irrelevant. **The wall-clock is not:** extraction measured 9.3s/call. At
11,517 postings that is 30 hours of serial calls, and a widened gate plus Phase 3
sources will make the corpus larger.

Task 04 supplies the real numbers — requests/minute ceiling, p95 latency, daily quota.
Size the backfill against those before starting, not after discovering the nightly
window cannot absorb it.

`scripts/backfill-scores.py` exists as precedent for a long-running catch-up job;
`extract.py` already has a backlog-burndown mode. Reuse rather than reinvent.

## Verify the path before depending on it

`FACTS_VERSION` is at 2, so it has been bumped once. That does not prove the path
works at current scale. Before committing:

- Confirm the version-keyed staleness check actually selects every row — a partial
  selection would silently leave a mixed-version corpus.
- Confirm `job_matches` recompute is triggered by the facts version change, since
  `match.py` keys on both `facts_version` and `criteria_version`.
- Run a dry run on 100 rows and diff old against new field by field. The diff is the
  most informative artifact this task produces: it shows exactly what the vocabulary
  change did, per field, and it is what task 08's before/after SQL will corroborate.

## Rollback

A re-extraction that produces worse facts than it replaced is recoverable only if the
old rows still exist.

- Snapshot `job_facts` before the bump. Storage is free; a 11,517-row table is
  nothing.
- Do not delete the snapshot until Axis A labels confirm the new extraction is at
  least as good.
- If extraction quality regresses on any field measured in task 07, restore and
  investigate before proceeding to task 13.

## Order of operations

1. Task 07's Axis A baseline recorded against the current corpus.
2. Snapshot `job_facts`.
3. Dry run on 100 rows; commit the field-by-field diff.
4. Bump `FACTS_VERSION` to 3.
5. Re-extract, sized against task 04's quota and window.
6. Confirm `job_matches` recomputed and no mixed-version rows remain.
7. Re-run task 07's Axis A measurement; compare.
8. Run task 08's diagnostic SQL again.

## Definition of done

- `FACTS_VERSION = 3`; zero rows remain at version 2.
- `job_matches` fully recomputed; no stale `facts_version` references.
- The 100-row field-by-field diff is committed.
- Axis A agreement is reported before and after, per field.
- Snapshot retained until the comparison passes.
- Total wall-clock and request count recorded, so the next bump can be sized from
  evidence rather than estimate.

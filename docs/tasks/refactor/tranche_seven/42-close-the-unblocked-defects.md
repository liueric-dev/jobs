---
kind: task
written: 2026-08-01
generator: none
---

# 42 — Close the six UNBLOCKED defects

**Status:** DONE 2026-08-01. **Depends on:** nothing — task 09 landed three tranches ago and this task's
whole premise is that its blocker is gone. **Blocks:** nothing.

Six defects in [`../../../ingest/DEFECTS.md`](../../../ingest/DEFECTS.md) are marked
**open, UNBLOCKED**. They were all dispositioned *"fix with harness — task 09"*; task 09 landed
in `68f026f` and **nothing rescheduled them**, so for three tranches they were neither
open-with-an-owner nor closed. Task 34 found that and re-marked them honestly. This task closes
them.

## Why this is a task and not a backlog

Task 34's pass recorded the failure mode precisely: *"Nine were dispositioned 'fix with harness
— task 09', and task 09 landed three tranches ago. Nothing rescheduled them, so they were
neither open-with-an-owner nor closed — **invisible in both directions**."* Three were fixed
there; six were left correctly marked and unowned.

**A disposition that names a blocker needs something that fires when the blocker clears.** That
is a real gap in the register and it is worth fixing here — one line per entry naming what
unblocks it, so a future reader can grep for dispositions whose blocker has landed.

## The six, and what each needs

The cassettes exist. `builtin-nyc`, `wwr-feeds` and `hn-hiring` are all in the committed
manifest the suite prints, so four of the six can be tested against recorded bytes today.

| | defect | site | needs |
|---|---|---|---|
| **D02** | `builtin-nyc.py` pairs titles and companies **by list index**, not by containment; one stray anchor shifts every later pairing silently | `ingest/builtin-nyc.py:316-333` | the `builtin-nyc` cassette, plus a **desync fixture** — a card with a missing company anchor. That fixture is the deliverable as much as the fix |
| **D03** | `SALARY_PATTERN` matches `100K-150K` anywhere in the card window, not in a salary element. 135 of 351 live rows carry an unverified value | `ingest/builtin-nyc.py:148`, `:338` | same cassette. **Scope the pattern to the element**, then re-derive how many rows still get a salary |
| **D05** | `weworkremotely.py` drops items at **four** `continue` sites with zero counters at any verbosity | `ingest/weworkremotely.py:146-149`, `:150-151`, `:159-161`, `:206-211` | counters, reported in the summary. `weworkremotely.md:309-312` states the consequence: an exclude-pattern change that started eating real titles *"would produce no signal at all"* |
| **D11** | demoted/orphaned `job_matches` rows are deleted with only counts to stdout | `match.py:274`, `:298`, `:363-369` | log job ids at `DEBUG_PRINT_KEYS` verbosity — which `match.py` **reads nowhere today**, so wiring the flag is part of the fix |
| **D13** | `match.SENIORITY_ORDER` must stay a superset of `extract.SENIORITY`; **nothing asserts it**, and a drifted level scores as free rather than raising | `match.py:65-66`, `:116`; `extract.py:82-83` | **no harness at all.** A shared constant or an import-time assertion. See below |
| **D23** | a crash between `hn-hiring.py`'s ledger commit and the `jobs` upsert **permanently strands** comments — the ledger gates re-fetching, so only `--reparse` recovers them | `ingest/hn-hiring.py:422`; `lib/upsert.py:235` | the `hn-hiring` cassette with **crash injection between the two commits**, which `05-fetcher-harness.md` already names as naturally expressible |

### D13 is the cheapest and was never actually blocked

It needs a shared constant or an assertion — no cassette, no scratch database, no fixture. It was
dispositioned *"fix with harness"* alongside the others and inherited a blocker it did not have.

**That is worth reporting as a finding, not just fixing.** Task 34 found the identical shape in
D17 — *"the cheapest confirmed bug in the repo, waiting on a fix of two lines"* — and it had sat
because a disposition written for its neighbours was applied to it. **Check the other five for
the same error before assuming each needs what its row claims.**

### D11 changes an interface, so decide before writing

`match.py` reads `DEBUG_PRINT_KEYS` nowhere, and `.claude/CLAUDE.md` documents that flag as the
verbose convention *everywhere*. Adding it is consistent, but it is a new output surface on a
stage that runs nightly. Record the choice in `DECISIONS.md` — including whether the ids go to
stdout or to a table, and why a deleted row's id is worth keeping at all.

## The rule this task runs under

**Verify each entry against the code before fixing it.** Task 34's pass found three counts in
this register wrong, all in the same direction — the code had *more* of the defect than the
entry claimed — and found two entries describing work that was already done. The register is
evidence, not truth.

Where a count is quoted here (135 of 351, four `continue` sites), **re-derive it** and report
what the re-check found. A stale claim is a finding.

## Definition of done

| | item | how it is checked |
|---|---|---|
| | Each of the six is **fixed**, or left open with a written reason in the register | read `DEFECTS.md`; no row still says "open, UNBLOCKED" without an owner |
| | Every fix has a test that fails without it | delete the fix, run the test, see it fail — then restore |
| | D02 and D23's tests use **recorded cassettes**, not the live network | run with the network down |
| | D13's guard fires on a real drift | add a value to one vocabulary, see it raise, remove it |
| | Every re-derived count is reported **with what the re-check found** | this file gains an outcome section |
| | The register gains a mechanism so a cleared blocker becomes visible | a grep-able convention, described in `DEFECTS.md`'s header |
| | D11's interface choice recorded in `DECISIONS.md` with the rejected option | read the entry |
| | Both suites green and **larger** — six fixes should add tests | read `Ran N tests` from each |

## Out of scope

- **The `fix opportunistically` class** (D18–D21) and the three deliberately-open entries (D31
  needs a decision, D33's consumer is task 25, D34 is a live-database DELETE). Their reasons are
  recorded and unchanged.
- **Re-recording cassettes.** Task 34 rule 4 and task 41d. If a cassette cannot express a case,
  add a **fixture** beside it rather than re-recording the capture.
- **`won't-fix` entries.** They carry documented reasons; reopening one needs a new fact, not a
  cleanup pass.

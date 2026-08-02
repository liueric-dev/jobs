---
kind: record
written: 2026-08-02
generator: none
---

# Session record — 2026-08-02, the freeze

**Frozen on write.** A `record` says what happened on a date and is corrected by a later
record rather than rewritten ([`../../../DOCS-POLICY.md`](../../../DOCS-POLICY.md) rule 4).
**Nothing here is a figure** — [`AUDIT.md`](../AUDIT.md) owns the run-level numbers, and the
suite counts in particular are deliberately not restated below. What this file is entitled to
record is the command and the **verdict**.

[Task 48](../tranche_nine/48-stop-clean.md). It holds no plan; the plan is
[`tranche_nine/README.md`](../tranche_nine/README.md).

## Why the run is stopping

**Tasks 36–47 were twelve consecutive tasks of documentation infrastructure, all green, and
they moved no product.** Tranche nine retires the documentation system in favour of the
harness, and 49, 50 and 51 all read the tree as ground truth. This is the single known point
they cut from — tagged, so getting back to it is one command.

## The premise, and it needed checking

`48-stop-clean.md` states the tally as `33 done, 6 in progress, 1 todo` and says to confirm
rather than inherit it. Its own command, from the repo root:

```
$ grep -oE "\| (done|todo|in progress) \|?$" docs/tasks/refactor/README.md | sort | uniq -c
     33 | done |
      6 | in progress |
      8 | todo |
```

**Eight `todo`, not one.** The difference is exactly the seven tranche-nine rows, linked into
the register by `40626a3` after 48 was written. The task's figure was right when it was typed
and the premise survives.

**The instrument does not see the whole table, and that is recorded here rather than fixed.**
The regex requires a bare `| done |`, so five rows written `| **done** |` are invisible to it
(tasks 23, 27, 31, 34, 47); and Phase 3's table carries `est. relevant/day` where the others
carry status, so its eight rows state their disposition in prose and cannot be counted at all.
Rows with a status cell plus Phase 3's rows account for every task row in the file. 48 §
*What this task must not do* forbids fixing it in a freeze, and a freeze that also repaired
its own instrument would not be one.

## What was open, checked against the files rather than the prose

**Task 30 is the only `todo` that predates this tranche, and a session cannot take it.**
`tranche_six/30-within-track-ordering.md` gates the within-band experiment, the bucket
decision and the thresholds on task 29's labels — people, with round 2 maturing ~2026-08-09 —
and its own DoD records the remaining display decision as gated on
`config/pursuit-persona.json`'s `_no_buckets_comment`, which makes naming the tracks an owner
call. The data half landed earlier the same day.

**One session-doable item is genuinely open and is not a task row.** The two nightly ingest
scripts still call `serpapi.com` and `api.apify.com` directly; only `choose_date_chip` moved
into `serp/`. `DEC-99` held the migration back on purpose. It is now written into task 23's
row in [`README.md`](../README.md), because the status column is where 48 tells a session to
look and prose in an entry point is exactly what this run has been caught by before.

**This is the mirror of the failure 48 was written against.** On 2026-08-02 `HANDOFF.md` said
there was nothing to start while the column listed task 23 as open. Today the column is clean
and the prose names something real. The lesson is not *"trust the column"* — it is that the
two have to be read against each other, and that whichever one is right, the fix is to move
the fact into the column.

## The readings

Taken before anything was edited, then the two checkers again after — steps 2, 3 and 4 all add
text under `docs/`, so this task's own changes are live surfaces for C1, C2, C4 and C7.

| command | verdict |
|---|---|
| `cd backend && python3 -m unittest discover -s tests` | `OK` |
| `cd backend/webapp && .venv/bin/python -m unittest discover -s tests` | `OK` |
| `cd backend/api && .venv/bin/python -m unittest discover -s tests` | `OK` |
| `python3 backend/tools/audit-docs.py` | `0 finding(s)`, C1–C7 each zero, exit 0 |
| `python3 backend/tools/audit-doc-links.py docs` | `0 broken link(s)`, exit 0 |

Three suites, three interpreters, no failures and no errors in any of them. **The counts are
[`AUDIT.md`](../AUDIT.md)'s figures and are not written here** — the same wall
[`2026-08-02-d31-the-http-split.md`](2026-08-02-d31-the-http-split.md) hit, for the same
reason, and C4 would be right to fire on this paragraph if it did.

Two things worth knowing about those commands rather than their output.
`audit-doc-links.py` is given its root explicitly and run from the repo root: it defaults to
`docs` relative to the working directory and `backend/docs/` exists, so run from `backend/`
it scans the wrong tree and reports zero while links are broken (task 47). And the main suite
prints `[retry]` lines and HTTP 500s from the Workday cassette — those are recorded fixtures
replaying a recorded failure mode, not a network call.

## The tag

`refactor-freeze-2026-08-02`, on the commit carrying this file. Everything after 48 cuts from
there. It is what makes task 51 safe to do quickly: 51 is `git mv` and stubs, and the
guarantee that the pre-archival tree is one checkout away is the whole reason it can move
fast without deleting anything.

## What did not change

**No product code.** The commit touches `docs/` only. No stale document was fixed, no defect
was closed and nothing was tidied in passing — every extra change would make 49's measurement
one step less trustworthy, and 49 measures the tree this tag names.

One deviation from the session convention, recorded because
[`../../../DOCS-POLICY.md`](../../../DOCS-POLICY.md) § *The maintenance loop* states it:
`CLAUDE_UPDATES.md` was **not** appended to. Task 48's Definition of done enumerates what this
task produces and that is not on it, and a freeze whose commit reaches further than its own
list is not a freeze.

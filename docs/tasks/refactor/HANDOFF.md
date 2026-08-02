---
kind: rolling
written: 2026-08-02
generator: none
subject: .
budget: 150
---

# Handoff — the `docs/tasks/refactor/` run

## START HERE — a fresh session's sixty seconds

**This file is the entry point and nothing else, as of 2026-08-02
([task 47](tranche_eight/47-split-the-entry-point.md)).** It carries a `budget:` in its
frontmatter and check **C7** enforces it. If you are about to append a paragraph about what
your session did, **that paragraph goes in `sessions/`, not here** — see § *Where things live*.

**Nothing on this page is a figure.** Per [`../../DOCS-POLICY.md`](../../DOCS-POLICY.md)
rules 2 and 3, every number in this run is owned by one document and produced by a command.
Run the commands; do not trust a count, including one you just ran in another tree.

```bash
cd backend       && python3 -m unittest discover -s tests   # read the `Ran N tests` line
cd backend/webapp && .venv/bin/python -m unittest discover -s tests
cd backend/api    && .venv/bin/python -m unittest discover -s tests   # a THIRD suite, DEC-81
cd backend && python3 tools/audit-docs.py && python3 tools/audit-doc-links.py
python3 backend/tools/label-findings.py                     # labelling state, read-only
```

Three suites, three interpreters. `backend/api/.venv` and `backend/webapp/.venv` both set
`include-system-site-packages = false`, so a claim about an import is a claim about **which
interpreter you ran**. A skip is not a failure.

## Where things live

| | |
|---|---|
| **what is done** | [`README.md`](README.md)'s status column — the ordered index |
| **state of the run, with an instrument beside every figure** | [`AUDIT.md`](AUDIT.md), which *owns* the run-level numbers |
| **what still binds** — prohibitions, the labelling surface, the FAQ, what is blocked, claims that are wrong about the code, GATE 2, unowned follow-ups | [`STANDING-GUIDANCE.md`](STANDING-GUIDANCE.md) |
| **what is open, and it is all the owner's** | [`OPEN-QUESTIONS.md`](OPEN-QUESTIONS.md), which owns the `OQ-` prefix |
| **what happened, per session** | [`sessions/`](sessions/) — `kind: record`, frozen on write |
| **why each choice was made** | [`DECISIONS.md`](DECISIONS.md) (`DEC-`) |
| **what is broken** | [`../../ingest/DEFECTS.md`](../../ingest/DEFECTS.md) (`D`) |
| **how to work on any of it** | [`../../WORKING-METHOD.md`](../../WORKING-METHOD.md) |
| **the traps that invalidated conclusions already written down** | [`../../MEASUREMENT-TRAPS.md`](../../MEASUREMENT-TRAPS.md) |
| **narrative before 2026-08-02** | [`../../archive/handoff-run-narrative-through-2026-08-01.md`](../../archive/handoff-run-narrative-through-2026-08-01.md) |

## What is next

**Read [`OPEN-QUESTIONS.md`](OPEN-QUESTIONS.md) first.** Six of its eight rows are open and
every one is the owner's; a session cannot close them. What a session *can* do is below.

**Check [`README.md`](README.md)'s status column before believing any sentence on this
page about there being nothing to do.** On 2026-08-02 this section said a session should
expect to find nothing it could start alone, while the index listed **task 23** as `todo`
— named as a blocker by two other tasks, needing no credential, no person and no device.
Both documents were correct; *"the product/API track has nothing left"* simply reads as
*"the run has nothing left"* to anyone skimming. **The status column is where the answer
lives.** ([record](sessions/2026-08-02-task-23-the-provider-seam.md))

**The product/API track has no session-doable work left.** 24's deploy half, 33's machine
half, and 32's phone test and live Google login all need a person, an account or a device.
`Contribute` is 32's sixth surface and is blocked on `OQ-1`'s ownership question rather than
on effort. **Do not open that track expecting to write code.**

**The labelling track is gated on people, not effort.** More *postings* buy nothing — what
`labels.inter_annotator()` needs is more labellers on the **same ten `overlap` rows**, and
round 2 matures ~2026-08-09. `OQ-3`.

~~**Two things a session can take today**~~ ~~Three~~ — **both are now done or the
owner's, as of 2026-08-02. A session opening this run today should expect to find nothing
it can start alone.**

1. ~~**`D31` — the ingest scripts that call `urlopen` directly.**~~ **Decided 2026-08-02**
   (`DEC-96`, [record](sessions/2026-08-02-d31-the-http-split.md)). Three of four sites went
   through `lib.http`; `builtin-nyc.fetch_description` deliberately did not, and a test pins
   it at one request per posting. The warning above was right about the shape — it was a
   mixed disposition, not a migration — and wrong about the count: four sites, not three.
2. **`OQ-2`/`D75` — the impression dedup key**, if the owner takes it. It is one predicate
   (`webapp/jobs.py:934-937`), and `job_events` is append-only, so every day it runs adds
   rows whose meaning has to be caveated permanently. ~~**This is the only row left here.**~~
   **It was not** — see 3. `D75` is now formally **reserved** for this in the register's
   allocator rather than merely spoken for (`DEC-98`), so nothing else can take the number.
3. ~~**Task 23 — the SERP abstraction.**~~ **DONE 2026-08-02**
   (`DEC-97`–`DEC-99`, [record](sessions/2026-08-02-task-23-the-provider-seam.md)).
   `backend/serp/` exists, `searchqueries.run_due()` has a real provider, and
   `search_query_results` has a writer — so 32's search screen reads a table something
   fills. Two of its DoD lines are reported unmet on purpose. **The follow-up it names is
   session-doable and is the next thing on this list**: `ingest/google-serpapi.py` and
   `ingest/google-apify.py` still talk to their providers directly, and moving them onto
   `serp/` is what closes *"no second definition exists"* for the fetch path. It was held
   back deliberately — that is the live nightly path and it carries claim and watermark
   semantics the interface does not model yet (`DEC-99`).

**`facts_version` on `eval_labels` landed 2026-08-02** (`DEC-95`,
[record](sessions/2026-08-02-label-provenance.md)), before round 2 rather than
after, which was the whole point of its deadline. The migration ran against the live
database; every row labelled before it reads as unrecorded and stays that way, because a
backfill was available and refused for `job_events.rank`'s reason. `evals label status`
prints the breakdown.

## Three standing prohibitions, and each is guarded by something other than this page

1. **Do not re-tune task 13's weights.** Its Definition of done is unmet *on purpose*; only
   task 29's labels license a change. [`STANDING-GUIDANCE.md`](STANDING-GUIDANCE.md) § *the
   ranking is a product now*.
2. **Do not reactivate `tech` or raise `daily_narrative_budget` casually.** Either restores a
   four-figure re-extraction or re-scoring bill. Run `score.py --stale-report` first; it needs
   no API key. § *the cost lever that was hiding in the profiles table*.
3. **Do not add the four rejected phrase families to the relevance gate.**
   `backend/tests/test_pursuit_gate.py` asserts their absence with the counts in its
   docstring — the mock harness scores all four as free and they admit live junk rows.

And two that guard the record rather than the code: **`evals label report` exits 2 at one
labeller by design — there is no `--force` and none may be added**; and **`redraw_refusal()`
refuses every redraw of `pursuit-v1`**, so the drawn set is permanent.

## Verify before you trust — including this page

This file has been measurably wrong about its own line numbers, its own SQL, which tests a
change would break, how many copies of `AI_VOCAB` existed, and whether `fastapi` was
installed. **Cite `file:line`, then re-read the line** — and quote the line's *text* when the
claim depends on it, because a line number is a pointer into a file that is still being
written. Every `evals/labels.py` citation written before 2026-07-30 is low by roughly
100–170; the symbol name plus `grep -n` is the durable form.

**A completed task here is not a validated one.** Task 13 is committed and unmet. The mock
acceptance run is a *specification* test and reduces task 29 by zero postings —
`docs/tasks/refactor/mock/` is **not** task 29's data, and that question has been asked out
loud already.

## How this file stays this size

**A session appends to its own record in [`sessions/`](sessions/) and edits only this page's
*What is next*.** It does not append narrative here. That convention is the whole of task 47's
part C, and it exists because 44's archival had no trigger: the file went 2771 → 2272 lines
and was back to 2669 within thirty-six hours, with all six doc checks green the entire time.
**C7 is the check that makes the budget above real** rather than a sentence about itself —
`DOCS-POLICY.md` rule 7's own bar.

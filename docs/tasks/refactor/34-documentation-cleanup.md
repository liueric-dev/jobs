# 34 — Cleanup, bugfixes and documentation

**Status:** NEXT. **Depends on:** nothing. **Blocks:** the product/API phase (24–28, 31, 32)
only by convention — this is the run paying down its debt before opening a new surface.

Phases 1–3 are built and measured: 20 of 35 tasks done or deliberately dropped. This task
is the pause before 24–28.

> **This file did not exist until 2026-07-31.** `README.md` linked to it from the day the
> plan was written and nothing was there. That is not an anecdote — **it is specimen #1 of
> what this task is for**, and it is why every item below carries the evidence that it is
> real rather than a citation of a document that claims it is.

## The rule this task runs under

**Verify before you act, and report what the verification found.** The previous session
re-checked one follow-up that had been marked *"still owed"* in two files and discovered it
had landed three days earlier — and the re-check turned up a number nobody had (the
recorded board was 79 postings over four pages, not the 88 over five that every document
predicted). **A stale claim is a finding, not just a chore.**

Four rules, from `HANDOFF.md` § *THE NEXT SESSION IS CLEANUP*:

1. **Mark, do not delete.** Struck-and-kept is this run's convention. Tidying by deletion
   removes the only evidence a number was ever wrong.
2. **Do not sweep stale line numbers wholesale** — `HANDOFF.md` forbids it by name.
3. **Do not edit `.claude/CLAUDE.md`.** Propose the diff here; the owner applies it.
4. **Do not "fix"** `job_scores`' NULL version columns, and do not re-record the
   `workday-cxs` cassette without reading `record_workday_cxs()`'s refusal guard.

---

## A. Documentation — confirmed, verified 2026-07-31

### A1. Sixteen broken relative links, ten of them in the ordered index

Verified by resolving every non-HTTP `.md` link under `docs/tasks/refactor/` against the
filesystem. **The index that `HANDOFF.md` calls "the ordered index" has ten.**

| file | broken target | why |
|---|---|---|
| `README.md` | `01-…` … `06-self-consistency-n120.md` (6) | the files are in `tranche_one/`; the links omit the prefix |
| `README.md` | `../../../MASTER-PLAN-pursuit.md`, `../../../SOURCING-STRATEGY.md`, `../../../ADDENDUM-google-jobs-providers.md` | wrong depth — all three are **siblings** of `README.md` |
| `README.md`, `HANDOFF.md` | `34-documentation-cleanup.md` | fixed by this file existing |
| `tranche_four/22-…`, `tranche_one/03-…` | `../../../ADDENDUM-google-jobs-providers.md` | same depth error |
| `tranche_two/07-…`, `08-…`, `09-…` | `../../ingestion_tests/0{3,4,5}-*.md` | wrong depth: `docs/ingestion_tests/` needs `../../../ingestion_tests/` |

**Size:** minutes. **Agent-safe.** Re-run the audit after fixing; the script is six lines of
`os.path.normpath` and belongs in the commit.

### A2. Ten of fourteen `docs/ingest/*.md` claim a generator that does not exist

`.claude/CLAUDE.md` says `docs/ingest/*.md` are *"generated with `script:`/`commit:`/
`generated:` frontmatter — regenerate, never hand-edit"*. **No generator exists.** Three
files have already been converted and carry a provenance note instead — `ats.md`,
`nyc-open-data.md`, `workday.md`. `ats.md`'s block is the established pattern:

```
---
script: backend/ingest/ats.py
hand_written: 2026-07-28
supersedes: the generated 2026-07-27 version at commit dd49a27
---
```

**The remaining ten**: `builtin-nyc`, `contributor-api`, `DEFECTS`, `engagement-events`,
`extract`, `google-apify`, `google-serpapi`, `hn-hiring`, `match`, `score`,
`weworkremotely`. **Decide once and apply uniformly: either write the generators or drop
the claim.** The three converted files have already made the decision de facto; leaving the
other ten is the worst of both, because CLAUDE.md's instruction is *"never hand-edit"* and
following it on a file with no generator means never fixing it.

**Size:** ~1h for the frontmatter route. **Needs the owner** only if the answer is "write
the generators".

### A3. `.claude/CLAUDE.md` is wrong about the suite size by 9×

`.claude/CLAUDE.md:103` — *"5. Run the suite. It was at 263 tests; it should not go down."*
Measured today: **main 1178, webapp 93**. Any agent following that line literally is
checking against a number nine times too small to catch a regression.

**Proposed diff — do not apply without the owner:**

```diff
-5. Run the suite. It was at 263 tests; it should not go down.
+5. Run the suite. `cd backend && python3 -m unittest discover -s tests` (1178 as of
+   2026-07-31) and `cd backend/webapp && .venv/bin/python -m unittest discover -s tests`
+   (93). Neither should go down. NOTE: pytest is installed in no interpreter here.
```

Two further CLAUDE.md items to check and propose in the same diff: the `lib/` parity rule,
and whether the `docs/ingest` "never hand-edit" instruction survives A2.

### A4. `HANDOFF.md` is 3,481 lines with seven "READ THIS FIRST" sections

It has said *"that is six too many"* about itself for a week, and the count has only gone
up. Current sections: `:304`, `:414`, `:799`, `:1038`, `:1384`, `:1408`, `:1518`, under a
`START HERE` at `:3` and an `Orientation` at `:200`.

**The archival split is the deliverable, not a rewrite.** Most of those sections are
*finished* history — the gate fix, the sampler defects, the pre-flight — and belong in
`CLAUDE_UPDATES.md`, which is now current and is the right home for per-session history.
`HANDOFF.md` should keep: the `START HERE` block, what is blocked, the standing
prohibitions, and the open follow-ups. **Move, do not delete**, and leave a stub line where
each section was so an inbound citation still lands somewhere.

**Size:** ~2h. **Agent-safe with review** — this is the one item where a mistake destroys
record, so do it last and in its own commit.

### A5. `record_cassettes.py` describes a recording it does not match

`record_cassettes.py:510` — *"msk is 88 postings: five pages, the last one short"* — and the
note built at `:546`, *"five pages ending in a short one"*. The committed cassette holds
**four** pages over a **79**-posting board (`total` 79, 0, 0, 0; 20+20+20+19). The board
moved between task 16's validation and the 2026-07-28 recording.

**Restate the docstring; do not re-record.** Re-recording without reading the refusal guard
(`if not (totals[0] and not any(totals[1:]))`) is how failure 5's only recorded evidence
gets destroyed. **Size:** minutes.

---

## B. Bugs and repo hygiene

*Being verified — see the survey. Do not act on any item here that does not carry evidence.*

---

## C. Explicitly out of scope

- **Task 29.** A second labeller is the owner's to arrange. Nothing here touches
  `eval_labels`, `labels.py` or `webapp/label.py`.
- **Applying `revenue_commercial` / bumping `FACTS_VERSION`.** D64: land the vocabulary, do
  not bump, while labelling is open.
- **Re-tuning task 13's weights.** Only task 29 licenses that.
- **The product/API phase** (24–28, 31, 32) and the two scoping calls the owner holds
  (21's broken premise, 23 → 25).

## Definition of done

- Every relative link under `docs/tasks/refactor/` resolves; the audit script is committed.
- The `docs/ingest/` frontmatter question is decided once and applied to all fourteen.
- A CLAUDE.md diff is **proposed** in this file, not applied.
- `HANDOFF.md`'s finished sections are moved to `CLAUDE_UPDATES.md`, with stubs left behind.
- Every confirmed bug in §B is fixed or has a written reason it was not.
- **Both suites green and not smaller: main ≥1178, webapp ≥93.**
- Each stale claim retired is reported with *what the re-check found*, not merely that it
  was retired.

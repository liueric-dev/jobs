---
kind: task
written: 2026-07-31
generator: none
---

# 34 — Cleanup, bugfixes and documentation

**Status:** NEXT. **Depends on:** nothing. **Blocks:** the product/API phase (24–28, 31, 32)
only by convention — this is the run paying down its debt before opening a new surface.

Phases 1–3 are built and measured: 20 of 35 tasks done or deliberately dropped. This task
is the pause before 24–28.

> ~~**This file did not exist until 2026-07-31.** `README.md` linked to it from the day the
> plan was written and nothing was there. That is not an anecdote — **it is specimen #1 of
> what this task is for**, and it is why every item below carries the evidence that it is
> real rather than a citation of a document that claims it is.~~
>
> **WRONG, AND CORRECTED 2026-07-31 BY THE SESSION THAT EXECUTED THIS TASK. The file
> existed.** `docs/tasks/refactor/tranche_six/34-documentation-cleanup.md` has been tracked
> since `28f1d0e`, carrying a full by-document-type dispositions table. What was broken was
> `README.md:102`'s **link** — it omitted the `tranche_six/` prefix, which is *the identical
> defect §A1's own table records for the six `tranche_one/` links three rows above it.*
>
> **So it is still specimen #1, but of something sharper than "a doc was missing."** A
> broken link was read as a missing file; nobody ran the six-line resolver §A1 asks for; and
> the remedy created a **second** task 34 at the un-prefixed path, which then silently went
> on asserting the *"`docs/ingest/*.md` are generated, never hand-edit"* claim that §A2
> exists to kill. **The tool that would have prevented this is the one this task was already
> committing to write.** It is now written — `backend/tools/audit-doc-links.py` — and it
> reports *"wrong prefix"* rather than *"no such file"* precisely so this cannot recur.
>
> The two files are merged below (§D) and the orphan is a pointer. The false premise is
> struck rather than deleted, per rule 1: a reader who acted on it needs to see it.

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
3. ~~**Do not edit `.claude/CLAUDE.md`.** Propose the diff here; the owner applies it.~~
   **SUPERSEDED 2026-07-31 — the owner reviewed the proposed diff and directed that it be
   applied.** The rule was right in general and wrong for this file's specific contents:
   three of the paths it cites do not exist, so every session between the proposal and the
   review would have gone on following instructions that cannot be followed. What was
   applied and what was left alone is recorded in §C.
4. **Do not "fix"** `job_scores`' NULL version columns, and do not re-record the
   `workday-cxs` cassette without reading `record_workday_cxs()`'s refusal guard.

---

## A. Documentation — confirmed, verified 2026-07-31

### A1. ~~Sixteen~~ **Nineteen** broken relative links — DONE, and the count was wrong twice

> **CLOSED 2026-07-31. All nineteen fixed; `backend/tools/audit-doc-links.py` reports zero.**
> The re-check found the count wrong in **both** directions, which is why the number is
> worth reporting rather than just the fix:
>
> - **Sixteen was a pre-fix count.** By the time anyone re-ran it, fourteen remained — the
>   two missing were the `34-documentation-cleanup.md` links this file's own table marks
>   *"fixed by this file existing"*. 14 + 2 = 16 reconciles exactly.
> - **But the scope was too narrow, and that hid five more.** §A1 audited only
>   `docs/tasks/refactor/`. Run across all of `docs/`, there were **five further links of
>   the identical class** — `docs/tasks/README.md:14-18`, every one of the five `job_ingest/`
>   task links, all missing the same kind of directory prefix. **An audit scoped to the
>   directory you already suspect confirms what you knew.** The committed script defaults to
>   all of `docs/` for this reason.
> - **The table below is also wrong about the fix**, and a sweep would have propagated it.
>   It groups `tranche_four/22-…` and `tranche_one/03-…` with the `README.md` rows as *"same
>   depth error"*. They are not the same fix: from `docs/tasks/refactor/` the correct target
>   is a **bare filename**, from `docs/tasks/refactor/tranche_*/` it is **`../`**. Blanket
>   "strip one `../`" fixes two of them and leaves three broken.
>
> **Thirteen more index rows named a file and linked to nothing at all** — tasks 15, 20, 21,
> 23–28 and 30–33. Not broken links, so no resolver would ever have caught them; the same
> defect one step earlier. All thirteen now link.

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

**It is in the commit — `backend/tools/audit-doc-links.py`.** It walks all of `docs/` by
default, prints `file:line`, the broken target and the unique correct target where one
exists, and exits non-zero. It deliberately **refuses to guess** when a basename matches
zero or several files, because guessing at a missing target is what produced the duplicate
task 34.

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

## D. Document dispositions — merged from `tranche_six/34-documentation-cleanup.md`

**This section is the content of the orphaned duplicate**, moved here 2026-07-31 rather
than left in a file nothing links to. It is the *plan-time* half of task 34 — written before
the run started, organised by document type — and §§A/B are the *verified* half. Neither
supersedes the other; the duplicate was invisible, not wrong.

**The rule it establishes, and it is the reusable part:** dispositions go **by document
type, not by schedule**. Generated reference is regenerated at phase boundaries and never
hand-edited. Hand-written rationale is written at decision time, because the reasoning
cannot be reconstructed later — `relevance.json`'s *"Rejected alternative: flag rows where
SerpApi's `via` field matches company_name. It catches 160 rows but false-positives on every
company posting to its own careers site"* is information that existed for about an hour.
For hand-written docs the practice is **staleness markers, not continuous rewriting**: one
line at the top the moment a doc becomes wrong, proper fix at a phase boundary. *Three
half-updated docs are worse than one honestly-stale doc, because you cannot tell which is
current.*

> **§A2 invalidates the first half of that rule as applied to `docs/ingest/`.** The
> "generated reference" category was asserted, never built — there is no generator. The
> category survives as a *principle*; `docs/ingest/` is not a member of it. See §A2 and §C.

| document | lines | disposition |
|---|---|---|
| `docs/scoring.md` | 784 | **Keep as current-state reference.** Header noting it describes the pre-Pursuit system; regenerate its measured figures after task 12 |
| `backend/docs/SCORING.md` | 516 | **Archive.** Superseded by `docs/scoring.md`; two hand-written scoring docs is drift. Its cost table is retained in the archive because task 04 supersedes rather than deletes it |
| `backend/docs/HANDOFF-match-quality.md` | 350 | **Split.** §4 (the seven measurement traps) is domain-independent — promote to `docs/MEASUREMENT-TRAPS.md`. The rest is persona-bound findings → `docs/archive/` |
| `backend/docs/HANDOFF-multimachine-google-jobs.md` | 349 | Review against task 24 — some may now be operator documentation rather than a handoff |
| `docs/ingest/*.md` | 4,600 | ~~Regenerate at each phase boundary.~~ **See §A2 — there is no generator.** Delete the three for retired sources; add nine for the new ones |
| `docs/tasks/job_ingest/` | 726 | **Never rewrite.** Append-only historical record; all five accurately marked done |
| `docs/ingestion_tests/` | 700 | Tasks 03–05 became 07–09 here. Update its README to point at the new tree and record that 05 moved earlier and why |
| `backend/api/README.md` | 237 | Task 24 corrects the "never deployed / expected to be deprecated" line. Verify it did |
| `docs/tasks/README.md` | 68 | Same deprecation note; same correction |
| `backend/docs/DEVELOPER.md` | 263 | **Regenerate at the end.** Its opening gap — "the pipeline scores every job it ingests and delivers none of them" — is closed by task 32 |
| `README.md`, `backend/README.md` | 621 | **Regenerate at the end.** Operational reference; stale operational docs actively mislead |
| `backend/evals/README.md`, `backend/webapp/README.md` | 425 | Update in place as their subsystems change |

**Create:** `docs/archive/` with a README explaining that everything inside was measured
against the author's software-engineer persona and does not transfer, and one line per file
recording what it measured, when, and what superseded it. `docs/MEASUREMENT-TRAPS.md`,
promoted from the handoff — *"the most durable thing in the repo and currently buried in a
document about a persona that is no longer the target."* `docs/ingest/DEFECTS.md`, the
register from task 02, kept current as entries close.

**Figures to correct, not delete** — superseded rather than wrong, and the superseded
version is evidence about how the system was tuned: `SCORING.md`'s cost table (right model,
wrong denomination, task 04); `compare-extract.py`'s 95%/90% self-agreement cited in
`criteria.json:_hard_exclude_comment`; `HANDOFF-match-quality.md`'s 12.7/20, **relabelled
explicitly as imitation fidelity against a non-target persona**; and
`docs/ingestion_tests/README.md`'s n=17 figures.

**Keep the `_comment` convention.** Every new config file gets `_comment` fields in the
existing style, recording where numbers came from and what was rejected. *"This is the
single most valuable documentation practice in the repo. It should survive the refactor
unchanged."*

---

## C. Explicitly out of scope

- **Task 29.** A second labeller is the owner's to arrange. Nothing here touches
  `eval_labels`, `labels.py` or `webapp/label.py`.
- **Applying `revenue_commercial` / bumping `FACTS_VERSION`.** DEC-64: land the vocabulary, do
  not bump, while labelling is open.
- **Re-tuning task 13's weights.** Only task 29 licenses that.
- **The product/API phase** (24–28, 31, 32) and the two scoping calls the owner holds
  (21's broken premise, 23 → 25).

## Definition of done — checked 2026-07-31

| | item | outcome |
|---|---|---|
| ✅ | Every relative link under `docs/tasks/refactor/` resolves; the audit script is committed | **Exceeded.** All of `docs/` resolves, not just this subtree — the narrower scope was hiding five. `backend/tools/audit-doc-links.py`, exits non-zero, reports the correct target rather than the absence |
| ✅ | The `docs/ingest/` frontmatter question is decided once and applied to all fourteen | **Decided: drop the claim.** No generator was ever written, so *"never hand-edit"* was unfollowable. All fourteen carry `generator: none`; `.claude/CLAUDE.md`'s rule amended in the same commit |
| ⚠️ | A CLAUDE.md diff is **proposed** in this file, not applied | **Deliberately not met — the owner directed that it be applied.** See rule 3 above, struck and explained. Applied in `3c4cee0` |
| ⚠️ | `HANDOFF.md`'s finished sections are moved to `CLAUDE_UPDATES.md`, with stubs left behind | **Met with the destination changed**, on the owner's call: sections went to **`docs/archive/`**, not `CLAUDE_UPDATES.md`. That log is an append-only *dated* record; pasting six finished narratives into it would have dated them all to today and destroyed the sequence that makes it readable. Stubs and links left behind as specified; 3,481 → 2,690 lines |
| ✅ | Every confirmed bug in §B is fixed or has a written reason it was not | 11 fixed, 6 re-marked **open, UNBLOCKED** (their blocker landed three tranches ago), 3 left open with reasons in the register (D31 needs a decision, D33's consumer is task 25, D34 is a live-DB DELETE) |
| ✅ | **Both suites green and not smaller: main ≥1178, webapp ≥93** | main **1182**, webapp **93**, both green. And both *run* — every count in this run before today was a `grep 'def test_'`, which cannot see a skip |
| ✅ | Each stale claim retired is reported with *what the re-check found* | Nine, listed in `CLAUDE_UPDATES.md`'s entry for this session. The four most useful are in §A above |

**Two items were met differently than written and both are marked ⚠️ rather than ✅**, because
a Definition of done that gets edited to match what happened is not a Definition of done.

**The one thing this task did not do:** §D dispositions `backend/docs/SCORING.md` and the
remainder of `backend/docs/HANDOFF-match-quality.md` for the archive. Neither moved. Both
are live citations from several documents, so relocating them is its own change with its
own link sweep, and doing it in the same commit as the `HANDOFF.md` split would have made
that split unreviewable. Recorded in `docs/archive/README.md` § *Still to archive*.

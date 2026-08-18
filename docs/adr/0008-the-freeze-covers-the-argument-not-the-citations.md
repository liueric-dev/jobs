---
kind: decision
written: 2026-08-09
generator: none
---

# 0008 — the freeze covers the argument, not the citations

**Status:** accepted, 2026-08-09. Answers `T-43`.

## Context

`README.md` says files here are frozen on write and gives no exception. `T-43` found citations in
three of them naming the wrong lines and could not fix them: correcting one would be inventing an
exception in passing, which is how a convention stops meaning anything.

**A fourth, found 2026-08-09, forces the question.**
`0004-provision-database-issues-no-grants.md:50` cited `backend/schema.py:1215-1223` for the
fallback that DROPs `jobs_app` and takes every GRANT with it — now a column list inside
`_APP_VIEW_SQL`. `.claude/CLAUDE.md` documented the same hazard and cited `:1253`, wrong
differently. **Both pointers to the repo's one operational landmine missed it, and
`.claude/CLAUDE.md` sends the reader here for the detail.** That sentence exists to stop somebody
running `provision-database.py` against a populated deployment, so this is not bookkeeping.

`T-43` concluded its citations were all wrong on arrival, so "the defect is that a citation into a
moving file was never checked at its target, not that files move". The fourth refutes that half — it
was right at `45d6d3a` and has moved 98 lines since. `audit-citations.py` sees neither mechanism: all
resolve, and it checks only that a path exists and a line is in range.

## Decision

**1. The freeze protects the claim, not the bookkeeping.** A citation, link or typo may be corrected
in place in a frozen file. Nothing that changes what a decision *says* — its reasoning, options,
what it gave up, its status — may be. The test is whether a reader's understanding of the choice
changes; if it does, it is a new ADR naming the old one, as before. A line number was never part of
a choice, and the alternative was a superseding ADR reading *"0002's line numbers were wrong"*.

**2. A frozen file may not carry a line number into a task file.** `TASKS.md` and `DEV_TASKS.md` are
renumbered wholesale by routine maintenance — `T-47` cut 177 lines from one in a single commit — so
any line number into them is stale within days. Name the section instead. Code and
`../STATE-OF-THE-SYSTEM.md` keep line numbers: the repo's convention depends on them and
`audit-citations.py` guards their existence.

**3. Prefer the `git show refactor-freeze-2026-08-02:<path>:LINE` form where it applies.** It freezes
both ends, so it cannot drift; `0006-contributor-credential-auto-minted-local-daemon.md:17` is the
worked example. `audit-citations.py` does not validate the line behind a tag — verify it by hand.

## Consequences

Four citations are corrected by this ADR's landing, none of them a decision: `README.md:20` and
`0002-task-51-deleted-instead-of-git-mv.md:54`, both `../STATE-OF-THE-SYSTEM.md:444-449` (the
inter-annotator ceiling, a different subject) → `:459-464`; the same file's `:21`,
the `DEV_TASKS.md` line range → the `## Tranche nine` section named rather than numbered, per
decision 2; and `0004-provision-database-issues-no-grants.md:50` → `backend/schema.py:1313`, with
`.claude/CLAUDE.md` corrected to match. **None of this licenses editing a frozen file while working
an unrelated row:** a correction is its own change, with its own commit line saying what moved.

**`docs/adr/` can now take the settled halves of open `OQ-` rows**, which was `OQ-34`'s third route
and was gated on this. That makes the option available; it does not decide `OQ-34`.

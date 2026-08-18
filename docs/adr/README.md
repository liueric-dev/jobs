---
kind: contract
written: 2026-08-03
generator: none
---

# Architecture decision records

**One decision per file, `NNNN-short-title.md`, four-digit serial.** Serials are never reused and
never renumbered, so a citation to an ADR keeps resolving. Format: **context · decision ·
consequences**, under 60 lines.

**Files here are frozen on write.** A decision that has been overturned gets a *new* ADR naming the
old one, and the old file gains one line at the top pointing forward. The old file is never
rewritten and never deleted — the reason it existed is the thing worth keeping.

**An ADR records why, not what the code does today.** This is the one rule that decides whether
this directory survives. Every one of the 137 documents deleted on 2026-08-02 failed the same way:
each described a state of the world, the world changed, and nothing brought the document forward.
Not one of them had been false when written (`../STATE-OF-THE-SYSTEM.md:474-479`). A file that says
*why we chose this and what we gave up* cannot go stale that way, because the choice was made once
and stays made.

So: no line counts, no test counts, no "currently" — those belong in `../STATE-OF-THE-SYSTEM.md`,
which is rewritten from the code rather than maintained. If an ADR needs a number to make its
argument, cite the file that produces it rather than transcribing it.

## Why this exists

`DECISIONS.md` was append-only rationale that the tranche-nine README called *"the single most
valuable file in the repo"* and explicitly forbade rewriting. `5046f98` deleted it along with the
other 136, and nothing took its slot. Rationale then lived only in commit messages — which is why
the commit messages in this repo are unusually long and load-bearing: they were improvising an ADR
each time. Read the original with:

```bash
git show refactor-freeze-2026-08-02:docs/tasks/refactor/DECISIONS.md
```

Tracked as `T-4` in [`../../TASKS.md`](../../TASKS.md).

## What is not here

**Decisions already argued in place stay in place.** Two from `b89c377` are well recorded beside
the settings they govern, and copying them here would create a second copy to keep in sync — which
is the failure this directory is built to avoid:

- **isort's `known-first-party` includes `config` and `schema_web`** because `webapp/` and `api/`
  are reached by a `sys.path` insert rather than installed, so isort classified them wrongly and
  `ruff check --fix` proposed a reorder that would have broken the program. The argument is in
  `backend/pyproject.toml` under `[tool.ruff.lint.isort]`.
- **The CI lint job is `continue-on-error` until the baseline reaches zero.** The argument is in
  `.github/workflows/ci.yml` at the `ruff baseline` step.

**`_comment` fields in `backend/config/*.json` are also decision records** and stay where they are,
next to the number they explain. Do not migrate them here.

## Index

| # | decision |
|---|---|
| [0001](0001-ruff-as-a-dev-only-linter.md) | `ruff` is adopted as a development-and-CI tool, reversing an outright ban |
| [0002](0002-task-51-deleted-instead-of-git-mv.md) | Task 51 deleted 137 documents where its spec said `git mv` and stubs |
| [0003](0003-layer-3-is-recorded-not-built.md) | Nothing is built at harness Layer 3 — deferred, deliberately |
| [0004](0004-provision-database-issues-no-grants.md) | `provision-database.py` creates objects and issues no privileges |
| [0005](0005-personal-scoring-layer-annotates-only.md) | The personal scoring layer annotates and never orders; resume tailoring is cut |
| [0006](0006-contributor-credential-auto-minted-local-daemon.md) | Contributor credentials auto-mint on login; the SerpApi worker stays local and long-running, never proxied server-side |
| [0007](0007-contributor-credential-opt-in-scheduled-worker.md) | Credentials mint at opt-in instead; the worker is OS-scheduled rather than resident, and the server dictates interval, pause and budget — superseding `0006` 1, 2 and 4 |
| [0008](0008-the-freeze-covers-the-argument-not-the-citations.md) | The freeze protects the claim, not the bookkeeping: a citation may be corrected in place, and a frozen file may not carry a line number into a task file |
| [0009](0009-run-statistics-are-reconciled-not-granted.md) | `search_queries`' run statistics stay the pipeline's; a contributor's run reaches them as a `submission_log` row the nightly step reconciles, not as a widened GRANT |

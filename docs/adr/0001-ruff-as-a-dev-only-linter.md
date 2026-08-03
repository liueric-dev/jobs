---
kind: decision
written: 2026-08-03
generator: none
---

# 0001 — `ruff` is a development and CI tool, and the ban on it is reversed

**Status:** accepted, 2026-08-03. Landed as `T-1`.

## Context

The tranche-nine README said that wiring in a linter was *"wrong for this repo regardless of where
it came from"* (`git show refactor-freeze-2026-08-02:docs/tasks/refactor/tranche_nine/README.md`).
That was not an arbitrary ban. It followed from a real and still-correct constraint: the pipeline
runs unattended on several machines, `psycopg[binary]` is its only third-party runtime dependency,
and every added package is another thing that can be missing on one of them.

What made the ban wrong was a category error one layer down, diagnosed in
[`../../TASK-52-harness.md`](../../TASK-52-harness.md): this repo answered five different questions
with one instrument, and the question *what is guaranteed to happen* was being answered with prose
plus a hand-rolled `audit-*.py` per rule. Its Layer 4 states the principle — **a rule with no check
is a suggestion** — and that principle is right. The standard implementation of it is a linter and
CI.

The evidence that the hand-rolled version does not survive contact: the two doc checkers this repo
had, `audit-docs.py` and `audit-doc-links.py`, were deleted in `5046f98` along with the documents
they checked, and nothing caught the resulting drift at all. The following four commits were spent
finding it by hand.

## Decision

Adopt `ruff`, **scoped to development and CI**, configured in `backend/pyproject.toml` carrying
`[tool.ruff]` and nothing else — no build backend, no `[project]` table, because nothing in this
repo is installed as a package.

**The bound does not move.** No new *runtime* dependency enters `backend/requirements.txt`,
`backend/api/requirements.txt` or `backend/webapp/requirements.txt`. `ruff` is installed into
`backend/.venv-dev`, which is none of the three runtime venvs, and CI enforces its absence from all
three with a grep that fails the build.

**Land against a recorded baseline, not a mass reformat.** The baseline is in the commit that adds
the config; it comes down one rule per commit. `ruff format` is configured and deliberately not
run. A large unreviewable diff is the exact move that produced the documents this repo had just
finished deleting.

## Consequences

- A finding that would be fixed by importing a library is not a reason to import one. Suppress it
  and say why, or fix it in stdlib.
- **A linter is a source of findings, not of edits, until each rule has been looked at once.**
  This was not theoretical: on the first new file it touched, `ruff check --fix` proposed an import
  reorder that would have broken the program at runtime. See `[tool.ruff.lint.isort]` in
  `backend/pyproject.toml`.
- The CI lint job is non-blocking until the baseline reaches zero, then flips. Until then, a green
  CI run does not mean `ruff` is clean, and `.claude/CLAUDE.md` says so.
- `RUF100` stays selected rather than hidden: the largest single line item in the first baseline is
  hand-written `# noqa` directives for a linter that was never run. That is the whole thesis in one
  rule — the convention was performed and the check behind it never existed.

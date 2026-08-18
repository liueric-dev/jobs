---
kind: decision
written: 2026-08-18
generator: none
---

# 0010 — the documentation layer checks citations, not documents

**Status:** accepted, 2026-08-18. Answers `T-59`, and retires `T-61` unbuilt.

## Context

The August refactor deleted 137 documents and the five-file layer that kept them honest — C1–C7 in
`tools/audit-docs.py` and its link checker, figure registry, baseline and suite, all intact at
`refactor-freeze-2026-08-02`. Restoring it was specified as one instruction: *restore and retarget,
do not rewrite.* The design was sound and tested. Measuring first produced two facts it lacked.

**The layer is larger than what it would guard** — compare `git show refactor-freeze-2026-08-02
--stat` on those five paths against `cat docs/*.md docs/adr/*.md | wc -l`. `TASKS.md:28` records the
cost: *"tasks 36–47 were twelve consecutive documentation-infrastructure tasks, every one green,
producing no product movement."* A full restore is the thirteenth, and `.claude/CLAUDE.md`'s ceiling
exists to stop that.

**None of C1–C7 catches the drift that actually happened.** A review on 2026-08-18 found
`config/relevance.json` citing four `relevance.py` lines that had all moved, the same file citing
`extract.py:70` for a constant at `:115`, `tools/provision-database.py` and `.claude/CLAUDE.md` both
saying five DDL functions where the list has six, and three live sites saying `ensure_schema` creates
13 tables where it creates 14. Every one is one shape: **a citation that still resolves and no longer
says what the citing text claims.** `.claude/CLAUDE.md:136-137` names that shape;
`tools/audit-citations.py` names it as its own blind spot and calls it *"not checkable here."*

Half right. Whether a claim is *correct* is not mechanically checkable. Whether the cited line has
*changed since someone last confirmed it* is — and that question catches all four.

## Decision

**Restore C3 and C4 only** — a `kind: rolling` document has not sat still while its subject moved,
and a figure in `doc-figures.json` does not appear outside its owning document. Those two catch drift
this repo has actually suffered.

**Do not restore C1, C2 or C6.** Kind-declaration, orphan-reachability and archive-provenance are
proportionate to 137 documents and ceremony at twelve; C6's tree, `docs/archive/`, is gone.

**Do not restore C7, and delete the `budget:` field it enforced.** Three files declare it in a unit
that does not measure what it claims — a line is 71 bytes in one and 352 in another, so the field
ranks them in the opposite order from their size. An unenforced budget teaches that frontmatter is
decorative; one enforced in the wrong unit teaches worse. Deleting is the honest half of *enforce it
or delete it*.

**Close the blind spot instead: snapshot every cited line.** `audit-citations.py` records a digest of
what each cited line said when the citation was last confirmed and reports when it changes. That
detects drift; it does not adjudicate correctness, and the tool must keep saying so.

## Consequences

**Given up:** a tested policy suite, and any mechanical guarantee that a new document declares a kind
or is linked from anywhere. At twelve documents both are answerable by reading.

**Gained:** the four drifts go red on the commit that causes them rather than surviving two sessions
as `T-18` did, and the check covers the whole repo, not only `docs/` — where none of the four lived.

**Residual, so nobody reads more into a green run:** a snapshot proves a cited line has not changed
since it was confirmed, never that the claim was right when confirmed. A citation written wrong is
snapshotted wrong. `--update-snapshots` is an assertion by a person, and the only place in this layer
where human judgement is recorded as fact.

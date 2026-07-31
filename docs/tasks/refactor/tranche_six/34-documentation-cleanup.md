# 34 — Documentation cleanup — MOVED

**This file's content is now [`../34-documentation-cleanup.md`](../34-documentation-cleanup.md) § D.**
Moved 2026-07-31. Nothing is lost; `git log --follow` on this path reaches the original.

## Why this file was orphaned, which is the part worth keeping

This was the plan-time task-34 file, tracked since `28f1d0e`. **Nothing ever linked to it.**
`README.md:102` linked to `34-documentation-cleanup.md` without this `tranche_six/` prefix —
the same defect that broke the six `tranche_one/` links in the same table.

On 2026-07-31 a session followed that broken link, found nothing at the un-prefixed path,
concluded *"this file did not exist"*, and wrote a **second** task 34 there. For a day the
run had two task-34 files with two live `Status:` lines, and the invisible one went on
asserting that `docs/ingest/*.md` are generated and must never be hand-edited — the exact
claim the visible one's §A2 was written to retire.

**The failure was not that a document went stale. It was that a broken link is
indistinguishable from a missing file to anyone who does not resolve it**, and resolving it
is six lines of `os.path.normpath` that nobody had run. That resolver now exists at
`backend/tools/audit-doc-links.py`, reports the *correct* target rather than merely the
absence, and covers all of `docs/` — because scoping it to the directory already under
suspicion is what let five more of the same class survive in `docs/tasks/README.md`.

Left as a pointer rather than deleted, per this run's *"mark, do not delete"* rule: a reader
who reaches this path from an old citation has to be able to find where the content went.

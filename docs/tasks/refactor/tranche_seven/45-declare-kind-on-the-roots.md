---
kind: task
written: 2026-08-02
generator: none
---

# 45 — Declare `kind:` on the two reachability roots

**Status:** DONE 2026-08-02. **Depends on:** 36 (the check), and the widening that task 46
shares a cause with. **Blocks:** the `backend` suite going green.

Two files now in `audit-docs.py`'s scanned set carry no frontmatter:
`.claude/CLAUDE.md` and the repo root `README.md`. Both are C1 findings as of 2026-08-02.

## Why this was invisible until now

`audit-docs.py` walked `docs/` only. Task 36 scoped it there deliberately and recorded that
widening was a later call; [`../AUDIT.md`](../AUDIT.md) § *What is open* carried the gap as
a rule 7 item — *"a figure in `.claude/CLAUDE.md` is on the honour system, and it is the
first thing every session reads."* The widening landed 2026-08-02 and these two findings
are the first thing it saw.

**Both files were already declared reachability roots for C2**, which is what made them
scannable at all — the widening derives the external roots from `ROOTS` rather than from a
second hand-written list, so the set cannot drift out of agreement with C2's.

## The fix, and the one judgement in it

Add a frontmatter block to each. Both read as `contract` under
[`../../../DOCS-POLICY.md`](../../../DOCS-POLICY.md) rule 1's table: they state what is
true and are maintained against the code rather than dated and frozen.

**The judgement is whether `.claude/CLAUDE.md` should carry frontmatter at all.** It is not
only a document — it is the instruction file every session loads, and a `---` block at the
top is content the model reads before anything else. Two defensible answers:

- **Declare it `contract`**, and rule 1 holds tree-wide with no exception to remember.
- **Exempt it explicitly** in `audit-docs.py`, the way `CLAUDE_UPDATES.md` and
  `docs/archive/` are exempted from task 39's namespace sweep as `kind: record`.

The first is preferred because an exemption is a thing to remember and rule 7 is the
argument that this repo's documentation rules only hold when a script holds them. But the
file belongs to the repo owner in a way no other document does, and this task should not
edit it without that being an explicit decision. **Record whichever is chosen as a `DEC-`
entry**; do not leave it implicit in a diff.

## What this task must not do

**Do not add these to the declared baseline.** `test_docs_policy.py` says it in as many
words — the baseline is for findings that predate task 36 and is *pruned, never grown*.
These postdate it. Two findings in a red check are the correct state until the files are
fixed; a baseline entry would make them permanent and silent.

## Definition of done

- Both files declare `kind:`, or the exemption is implemented and its reason recorded.
- The choice for `.claude/CLAUDE.md` is recorded as a `DEC-` entry in
  [`../DECISIONS.md`](../DECISIONS.md), naming the rejected option.
- `python3 backend/tools/audit-docs.py` reports **0 C1 findings**. It will still exit 1 on
  C4 until task 46 lands — say so rather than reporting this task as clearing the check.
- The declared baseline is still empty.

## What the work turned up

**The owner chose to declare, and the exemption was rejected** (`DEC-76`). Both files now
open with `kind: contract` / `written: 2026-08-02` / `generator: none`. C1 went 2 → 0.
Task 46 landed in the same session, so the CLI reports **0 findings and exits 0** — but
this task did not clear C4 and the two are separately verifiable with
`python3 backend/tools/audit-docs.py --check C1`.

Three things worth the next reader's time:

- **`frontmatter()` requires `---` to be the literal first line** — no blank line, no BOM,
  no leading comment ([`audit-docs.py`](../../../../backend/tools/audit-docs.py), the
  `lines[0].strip() != "---"` guard). An unterminated block returns `present=False` and
  reads as *"no frontmatter block"*, not as a malformed one, so a typo in the closing `---`
  produces a finding whose message points at the wrong problem.
- **The frontmatter shifted every line number in `.claude/CLAUDE.md` by 6.** Anything
  citing that file by line — task 46's own table, `HANDOFF.md`, `AUDIT.md` — is off by six
  for citations written before 2026-08-02. The two C4 findings moved from `:121` and `:190`
  to `:127` and `:196`.
- **Nothing else read the file's first line.** Checked before editing: no loader, no test
  and no tool parses `.claude/CLAUDE.md`; `audit-docs.py` is the only reader, and the
  harness treats the block as prose. The cost of declaring is four lines a session reads
  before anything else, which is the whole of the judgement this task flagged.

The regression is pinned on the real tree, not only in the synthetic one:
`TestTheReachabilityRootsAreDeclared` in
[`test_docs_policy.py`](../../../../backend/tests/test_docs_policy.py) asserts both roots
declare `kind: contract`, so deleting either block turns the suite red rather than only the
CLI.

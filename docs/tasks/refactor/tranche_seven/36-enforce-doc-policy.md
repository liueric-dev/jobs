---
kind: task
written: 2026-08-01
generator: none
---

# 36 — Make the documentation policy enforceable

**Status:** NEXT. **Depends on:** [`docs/DOCS-POLICY.md`](../../../DOCS-POLICY.md), written.
**Blocks:** 37, 38, 40 — each of those executes a rule this task makes checkable, and doing
them first would mean hand-verifying work a script is about to verify anyway.

The policy is seven rules. This task turns six of them into a script that exits non-zero, and
**writes down which one it could not check and why.**

## The argument, stated once so the rest of the tranche can cite it

Two documentation rules were written in this repo by careful people, in the same task. One of
them held.

| rule | written | has a script | outcome |
|---|---|---|---|
| every relative link resolves | task 34 § A1 | **yes** — `backend/tools/audit-doc-links.py` | holds; reports 0 today |
| dispositions go by document type | task 34 § D | no | four documents drifted out from under it |

That is the case for this task. It is not a claim that prose rules are useless — § D's rule is
*correct*, and this tranche is built on it. It is a claim that **a correct rule with no check
decays at the speed of the surrounding work**.

### The correction that shapes the deliverable, verified 2026-08-01

**`audit-doc-links.py` is wired into nothing.** No test imports it, `.git/hooks` holds only
`.sample` files, and there is no CI configuration in the repo:

```bash
grep -rn 'audit-doc-links' backend/tests/    # nothing
ls .git/hooks/ | grep -v '\.sample$'         # nothing
ls -d .github .gitlab-ci.yml .circleci       # nothing
```

So the row above overstates its case. The script has held for **one day**, and only because a
person typed the command. **A script nobody runs automatically is exactly one step better than
prose** — which means this task's deliverable is not "another tool in `tools/`". It is **two
checkers failing a suite that is already being run.**

**`audit-doc-links.py` gets wired in as part of this task.** It is a two-line test and it closes
the same gap in the tool this task's whole argument rests on. There are **no existing doc tests**
to sit alongside — `backend/tests/test_docs_policy.py` is the first.

## The deliverable

`backend/tools/audit-docs.py`. Same contract as `audit-doc-links.py`, because that is the
contract that worked:

- prints `file:line`, the problem, **and the correct fix where exactly one is unambiguous**
- **refuses to guess** when the fix is ambiguous. Guessing at a missing target is what produced
  a duplicate task 34 (`../34-documentation-cleanup.md` § A1)
- exits non-zero when anything fires
- **offline.** No network, no database, no LLM. It must be runnable in a pre-commit hook and in
  the suite, where a network check is a flake rather than a test
- stdlib only, per `.claude/CLAUDE.md` — `psycopg[binary]` is the pipeline's only third-party
  dependency and this is not the task that changes that

Wired into the suite as `backend/tests/test_docs_policy.py` — **the repo's first doc test** — so
it fails in `python3 -m unittest discover -s tests` and not only when someone remembers.
`audit-doc-links.py` gets a case in the same file, for the reason given above.

## The six checks

### C1 — every document declares a valid `kind:` (rule 1)

Frontmatter present, `kind:` present, value in `{contract, rationale, record, rolling, task}`.

**Suggests the fix.** For a file under a directory whose siblings agree on a kind, name that
kind in the message. Do not write it — this check reports, task 37 applies.

### C2 — no orphan documents (rule 1, and the defect that motivated the tranche)

Every `.md` under `docs/` is reachable by a relative link from at least one other document, or
is an index that others link to. `audit-doc-links.py` proves that every link *resolves*; nothing
proves that every file is *reached*.

**This is the check that would have caught the duplicate task 34 on the day it was written.** It
was tracked, invisible, and asserting a claim its visible twin existed to retire — for a day —
and no resolver would ever have found it, because a file nothing links to has no broken link.

Roots are declared, not inferred: `README.md`, `docs/README.md` (task 37 creates it),
`.claude/CLAUDE.md`. Reachability is transitive from the roots.

### C3 — `rolling` documents are rolled forward or retired (rule 4)

For each `kind: rolling` document, compare its own last-modified commit against the last commit
touching the tree it describes. A rolling document that has not moved while its subject has is
**stale**, and the script says so with both dates and both commits.

**Threshold is a declared constant with a comment, not a magic number**, in the style of
`config/extraction-policy.json`. Start permissive — the goal is to catch a document that missed
an entire session, not to nag.

**This is the check with the highest false-positive risk in the set.** If it cannot be made
quiet enough to leave on, say so in the Definition of done and ship it behind a flag rather than
shipping a check everyone learns to ignore. **A check that cries wolf is worse than no check**,
because it teaches the reflex that retires all the others.

### C4 — owned figures are not copied (rules 2 and 3)

A small declaration — `backend/config/doc-figures.json`, with `_comment` fields in the existing
style — maps a figure to its owning document and a pattern:

```
{
  "_comment": "Figures that appear in exactly one document, per DOCS-POLICY rule 2. ...",
  "_why": "The main suite's count is written three ways in three live documents and none ...",
  "figures": [
    {"name": "main suite test count", "owner": "docs/tasks/refactor/AUDIT.md",
     "pattern": "\\b11[0-9]{2}\\b", "_note": "..."}
  ]
}
```

The check flags any match **outside** the owner. Allowances are explicit rows, not a global
ignore, because "we decided this copy is fine" is exactly the kind of decision that has to be
written down where the next reader sees it.

**Scope honestly.** A general duplicate-number detector is not possible and must not be
attempted. This checks a *declared* list, it will never be complete, and the declaration is the
deliverable as much as the code is.

### C5 — register prefixes do not collide (rule 6)

`D<n>` is defined only in `docs/ingest/DEFECTS.md`; `DEC-<n>` only in `DECISIONS.md`; no
identifier is **defined twice inside one register**.

**A definition is a heading in a register file. Everything else is discussion, and discussion is
not checked.** This distinction is the whole difficulty of the check, and a naive version gets it
wrong immediately — a prototype run on 2026-08-01 flagged four "collisions" that were all
legitimate prose:

| flagged | what it actually is |
|---|---|
| `docs/score-validation.md:216` `### D16: the buckets KeyError` | a section *about* defect D16 |
| `42-close-the-unblocked-defects.md:43`, `:53` | headings in the task file that **fixes** those defects |
| `39-split-the-d-namespace.md:63` | the old heading quoted inside a fenced code block |

Three of the four are in this tranche's own files. **A check that fires on the documents written
to satisfy it is a check that gets switched off in week one.** Restrict definitions to the two
register files, and skip fenced code blocks.

**Scoped that way it still fires today, and that is how it gets tested:** every `D45`–`D65`
heading in `DECISIONS.md` is a `D<n>` definition in the wrong register, and `D45` is defined
twice there besides. Task 39 clears all of them. Write the check first and watch it go red on
real input — **a checker whose first run is green has been tested against nothing.**

### C6 — archived files carry provenance (rule 4)

Every file under `docs/archive/` opens with a header naming **what it measured, when, and what
superseded it**. `docs/archive/README.md` already requires this in prose; it has never been
checked.

## The red baseline, measured 2026-08-01

A prototype of C1/C2/C5/C6 was run against the tree so "lands red" means something checkable.
**These are approximate** — the prototype is thrown away, not committed — but they are the right
order of magnitude and C2's list is worth reading before starting.

| check | prototype result |
|---|---|
| **C1** no `kind:` frontmatter | ~93 of ~101 documents. The fourteen `docs/ingest/*.md` have frontmatter but no `kind:` key |
| **C2** orphans | **11** — seven of them `docs/ingest/*.md`, plus `docs/tasks/README.md`, `LABELLING-NIGHT.md`, the mock answer-key addendum, and `tranche_six/34-documentation-cleanup.md` |
| **C5** `D<n>` defined outside `DEFECTS.md` | every `D45`–`D65` heading in `DECISIONS.md`, `D45` twice |
| **C6** archive files without provenance | **0** — `docs/archive/README.md`'s rule is already being followed |

**C2's list contains a deliberate orphan and the checker must be able to say so.**
`tranche_six/34-documentation-cleanup.md` is the pointer stub task 34 left behind on purpose;
nothing links to it *by design*, and that is the whole point of the file. Orphan-by-intent needs
a declared allowance — a frontmatter key or a declared list — or C2 will keep reporting the one
file in the tree whose orphanhood was a decision.

Note also that **seven `docs/ingest/*.md` are unreachable**, which is a real finding: the root
`README.md` calls that directory *"the per-script reference for all eleven entry points"* and
then links to the directory rather than to the files. Task 37's `docs/README.md` fixes it.

## What is deliberately not checked, and must be said in the script's docstring

Whether a `rationale` entry is any good, whether a `record` is interesting, and **whether any
sentence in any document is true.** No script can check those. Naming them in the docstring is
the point: a reader who sees a green tick must know how narrow it is, or the tick becomes a
claim the tool never made.

This is rule 7's own caveat and it is not decoration — `AUDIT.md` § *How to audit this run in an
hour* exists because passing a mechanical check is not the same as being right.

## Definition of done

| | item | how it is checked |
|---|---|---|
| | `backend/tools/audit-docs.py` exists, stdlib only, offline, exits non-zero on failure | `python3 backend/tools/audit-docs.py; echo $?` with the tree as it stands today — **it must be non-zero**, because C5 has real failures in it |
| | All six checks implemented, or a check is **absent with a written reason in the docstring** | read the docstring against C1–C6 |
| | C5 fires on `DECISIONS.md`'s two `D45` definitions and **not** on the four prose headings listed above | run it; grep the output for `score-validation.md` and the two tranche_seven files — **they must not appear** |
| | C2 reports `tranche_six/34-documentation-cleanup.md` as **allowed**, not as a finding | run it; the deliberate-orphan mechanism exists and is used |
| | **`audit-doc-links.py` is invoked by the suite** | `grep -rn 'audit.doc.links' backend/tests/` returns a test |
| | C3's threshold is a named constant with a comment explaining the number | grep the constant; a bare integer is a fail |
| | `backend/config/doc-figures.json` exists with `_comment` and `_why` | `python3 -c "import json;json.load(open('backend/config/doc-figures.json'))"` |
| | Wired into the suite | `cd backend && python3 -m unittest tests.test_docs_policy` |
| | Both suites still green and not smaller | read the `Ran N tests` line from each, per `AUDIT.md` |
| | `--help` documents every check by name | `python3 backend/tools/audit-docs.py --help` |

## Out of scope

- **Fixing anything the script reports.** That is tasks 37–40. This task may leave the tree
  failing its own new check, and **should** — a checker that lands green has not been shown to
  work.
- **Checking `backend/**/*.md`.** Start at `docs/`. `audit-doc-links.py` made the opposite
  mistake in the other direction (too narrow) and the fix was cheap; widening later is cheap too,
  and a first version that tries to classify every README in the tree will stall on judgement
  calls that task 37 has not made yet.

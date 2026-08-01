---
kind: task
written: 2026-08-01
generator: none
---

# 39 — Split the `D<n>` namespace

**Status:** TODO. **Depends on:** nothing — this is independent of 36–38 and can run first or in
parallel. **Blocks:** nothing, but 36's check C5 stays red until it lands.

`D45` currently resolves to three different things, and the ambiguity has already reached the
code. Give each register its own prefix, per [`DOCS-POLICY.md`](../../../DOCS-POLICY.md) rule 6.

## What is actually true, verified 2026-08-01

The plan for this task assumed a duplicate ID that needed renumbering. **That is wrong, and the
correction changes the work.** Reading the headings rather than grepping the identifiers:

```bash
grep -nE '^#{2,4} *D[0-9]+' docs/tasks/refactor/DECISIONS.md
grep -nE '^## '            docs/tasks/refactor/DECISIONS.md | head -3
```

`##` appears in `DECISIONS.md` **only from `D46` onward**. The first 1,191 lines contain no `##`
heading at all — every entry there is `### <topic> —`: `### 00 — Scope of this run`,
`### 06 — THE GATE`, `### SCORE-VERSIONS — invalidation is inert`, and **`### D45 — …`, twice.**

So the two `### D45` entries are not a duplicated identifier. They are **topic headings, and the
topic is defect D45** — exactly as `### 06 —` means "decisions taken while doing task 06". The
second one's own body says so: *"The design question D45 declined to decide, answered yes."*

| site | what it is | prefix it should carry |
|---|---|---|
| `docs/ingest/DEFECTS.md:653` | the defect — `company_ats`'s `never_found` write-back is partial, 35 rows against 139 | `D45`, **unchanged** |
| `DECISIONS.md:1063` | a decision taken while fixing that defect | not an ID at all |
| `DECISIONS.md:1076` | a second decision taken while fixing it | not an ID at all |
| `DECISIONS.md:1192`–`:1972` | twenty allocated decision IDs | `DEC-46` … `DEC-65` |

**`D46` started a new scheme mid-file** — a new numbering *and* a new heading level — continuing
the defect register's count so the two would not collide. It was a reasonable call and it
produced a namespace where a bare `D52` cannot be resolved without knowing which file it came
from.

### The code is already correct, and must not be swept

`backend/tools/ats-discover.py` and `backend/tests/test_ats_discovery.py` cite `D45` a dozen
times, and **every one of them means the defect**: `:502` reads *"defect D45"*, `:1027` reads
*"(defect D45)"*. They are right today and they stay right after this task. A regex sweep over
`D45` would corrupt them.

**That is the trap in this task.** The identifier to be swept and the identifier to be left
alone are the same string, and only the surrounding sentence tells them apart. `sed` is not the
tool. Resolve each hit by reading it.

## The work

### 39a — retitle the two `### D45` entries

Make the reference explicit, keep the position, **change no body text**:

```
### D45 — One durability boundary, on the iteration axis
### Defect D45 — one durability boundary, on the iteration axis
```

`DECISIONS.md` is append-only for *entries*; a heading that names its subject more precisely is
not a rewrite of the reasoning. If that reading is contested, the safe alternative is to leave
both headings and append a disambiguation note — say which was chosen, in `DECISIONS.md`.

### 39b — re-prefix `D46`–`D65` to `DEC-46`–`DEC-65`

**Numbers are preserved.** No renumbering: `D52` becomes `DEC-52`, never `DEC-07`. Renumbering
would invalidate every inbound citation *silently*, which is the failure mode this whole tranche
is about.

Old anchors stay resolvable. Markdown auto-anchors `## D46 — …` as `#d46`; the new heading
anchors as `#dec-46`. Leave an explicit `<a id="d46"></a>` beside each so an inbound `#d46`
still lands. Rule 4 — an inbound citation must land somewhere.

### 39c — sweep the inbound citations

Get the size, do not read it here (rule 3):

```bash
grep -rnoE '\bD(4[6-9]|5[0-9]|6[0-5])\b' --include='*.md' --include='*.py' . | wc -l
grep -rlE  '\bD(4[6-9]|5[0-9]|6[0-5])\b' --include='*.md' --include='*.py' .
```

Note the range **starts at 46**. `D45` is excluded because it is the ambiguous one and is
handled by hand.

`CLAUDE_UPDATES.md` and `DECISIONS.md` are append-only. **Correcting an identifier is not
rewriting an entry** — but say so in the commit message, because the diff will look like a
violation to anyone who does not know why. If that is too fine a distinction, the fallback is to
leave historical logs alone and sweep only the live documents; **decide, and record the choice.**

### 39d — declare the allocators

One line in each register's header naming the prefix it owns and the next free number:
`DEFECTS.md` owns `D`, `DECISIONS.md` owns `DEC`, `README.md` owns task numbers. Cross-register
references are written out — *"defect D45"*, *"decision DEC-52"* — so a bare identifier in a
code comment is always resolvable.

## Definition of done

| | item | how it is checked |
|---|---|---|
| | 36's check C5 is clean | `python3 backend/tools/audit-docs.py` — no register-prefix findings |
| | `D45` in `ats-discover.py` and `test_ats_discovery.py` is **untouched** | `git diff backend/tools/ats-discover.py backend/tests/test_ats_discovery.py` is empty |
| | Every `D46`–`D65` citation reads `DEC-nn` | the first grep above returns nothing outside a historical-log exemption named here |
| | `#d46`–`#d65` anchors still resolve | `grep -c 'a id="d' docs/tasks/refactor/DECISIONS.md` equals the number of re-prefixed entries |
| | No entry body text changed | `git diff` on `DECISIONS.md` shows only heading lines, anchors, the header, and appended content |
| | Both registers declare their prefix and next free number | read the two headers |
| | `audit-doc-links.py` still reports 0 | run it |
| | Both suites green and not smaller | read `Ran N tests` from each — `test_ats_discovery.py` is the one at risk |

## Out of scope

- **Renumbering anything.** Numbers are preserved; only the prefix changes.
- **Merging the two registers.** They answer different questions — *what is broken* and *why was
  this chosen* — and rule 6 exists so both can keep their own counter.
- **Retrofitting `DEC-` to the pre-D46 topical entries.** `### 06 —`, `### SCORE-VERSIONS —` and
  the rest were never identifiers and do not become ones here. Allocation starts where it
  actually started.

---
kind: task
written: 2026-08-02
generator: none
---

# 52 — build the harness: move each answer to the row it belongs in

**Status:** TODO. **Depends on:** 50 (extraction) and 51 (archive). **Blocks:** 53.

**This task is pedagogical before it is structural, and the ordering is a requirement rather
than a preference.** The reason prompts were being repeated is not laziness — it is that a
primitive existed and was not known, so it got reinvented in Markdown. Building a harness the
owner does not understand reproduces that failure with better tooling.

**So: one primitive at a time. Explain it, build it, use it once, then move on.** If a layer is
not understood after it is built, it does not ship — it goes to `OWNER-QUEUE.md` as a question.

## Layer 1 — what a session knows at the start

`.claude/CLAUDE.md`, **target under 150 lines, zero strikethroughs.** The current file is 255
lines carrying six struck spans (`~~76% / 94%~~`, `~~It was at 263 tests~~`,
`~~frontend/ is empty.~~`). Rule 4's *mark, do not delete* is correct for append-only rationale
and **wrong for a file loaded in full into every session**: every session pays to read facts
labelled as untrue, then has to work out which half is live. Git holds the history. This is the
one document where marking costs more than it buys.

Keeps: what this is, the commands, the three interpreters and three suites, the architecture
invariants, a pointer to the rules.

`.claude/rules/`, **path-scoped so they load only when relevant** — this is where the landmines
from task 50 go:

| file | `paths:` | carries |
|---|---|---|
| `postgres.md` | `backend/**/*.py`, `backend/config/*.json` | `\y` not `\b`; run `relevance-report.py --dead` after any pattern change |
| `ingest.md` | `backend/ingest/**` | `upsert_checked`; Workday `limit` ≤ 20; a throttled page is not the end of a list; alert on volume |
| `measurement.md` | `backend/evals/**`, `backend/tools/*.py` | the model floor, name the metric, the four eval rules |
| `docs.md` | `docs/**/*.md` | the five kinds, one figure one owner, never type a scriptable number |
| `frontend.md` | `frontend/**` | no build step, no npm, `.mjs` both ways, serve on the API's origin |

**Run `/context` before and after.** The point is not only tidiness: rules that load on demand
cost nothing on a session that never touches those files.

## Layer 2 — who does the work

`.claude/agents/`. Two, both read-only, both taken directly from `WORKING-METHOD.md`:

- **`plan-verifier`** — reads a task file and the code it cites and reports contradictions
  *before* implementation. `WORKING-METHOD.md` already prescribes this: three agents checking
  step 0's claims found ten errors, four of which changed the work, in a plan produced by a
  careful session with live measurements. Its numbers were right and its claims about the code
  were not; **those fail independently.**
- **`artifact-reviewer`** — reads the finished diff after the suite is green. Three of task 29's
  four defects were found this way. **A green suite means the code does what it was written to
  do, not that what it was written to do was wanted.**

Both get `tools: Read, Grep, Glob, Bash` and no `Edit` or `Write`.

## Layer 3 — what decides what runs next

**Nothing is built here yet, deliberately.** The manual decompose-into-task-files-and-clear loop
has candidate replacements — `/batch`, saved dynamic workflows, `/goal` — and task 49 will have
used one of them for real. **Pick based on that experience, not in advance.** Record the choice
in `DECISIONS.md`; do not build all three.

## Layer 4 — what is guaranteed to happen

`.claude/settings.json`. Hooks are the slot `DOCS-POLICY.md` rule 7 was reaching for: they run
regardless of what Claude decides, where CLAUDE.md is only context.

- **`PostToolUse` on `Edit|Write` matching `*.md`** → `audit-docs.py` and `audit-doc-links.py`,
  from the repo root with the path passed explicitly. Drift is caught in the turn that causes
  it rather than in the next session's re-verification.
- **No linter, no formatter.** `DOCS-POLICY.md` forbids it and that stands. Any suggestion to
  wire `ruff` here — including from `/insights` — is wrong for this repo.
- Run **`/fewer-permission-prompts`** to build the allowlist from actual transcripts rather than
  guessing.

`audit-docs.py` stays exactly as it is. It is already wired into a suite, which is rule 7's own
bar, and it is better than what a hook alone would give.

## Layer 5 — what travels

`~/.claude/`, user-level, applies to every project including ones that do not exist yet. Only
~16 of 100 measured sessions were this repo; the Garmin pipeline, the media stack and the
tracker automation have no CLAUDE.md at all, and that is where the binding-to-127.0.0.1,
backup-excludes-dropping-8-of-9-databases and leaked-passkey incidents happened.

`~/.claude/CLAUDE.md`: scope discipline (*do the task asked and stop; a question is a question,
not a directive to benchmark and redesign*), verify-before-claiming, never echo credentials,
enumerate the runtime environment before editing service config.

`~/.claude/skills/`: `resume` and `wrap`, generalised. `~/.claude/agents/`: `artifact-reviewer`.

## Run `/doctor` at the end

It finds unused skills, MCP servers and plugins against their context cost, flags slow hooks,
dedupes local `CLAUDE.md` against the checked-in one, and **migrates always-loaded guidance into
skills and nested `CLAUDE.md` files that load on demand** — which is this task, done by the
tool. It reports first and asks before changing anything. Anything it proposes that contradicts
`DOCS-POLICY.md` gets declined and recorded.

## Definition of done

- [ ] `.claude/CLAUDE.md` under 150 lines with **zero `~~` spans**
- [ ] Five path-scoped rule files exist; `/context` readings recorded before and after
- [ ] Two read-only agents exist and **each has been invoked once on real work**
- [ ] The `*.md` hook fires on a test edit and is observed to fire
- [ ] `~/.claude/` carries the four cross-project rules and two skills
- [ ] Layer 3 is a **recorded decision**, not a build
- [ ] `/doctor` run, output recorded, every declined suggestion given a reason
- [ ] **For each primitive built, one paragraph in the session record explaining what it does
      and why it is that slot rather than another.** If that paragraph cannot be written, the
      primitive does not ship

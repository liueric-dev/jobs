---
kind: contract
written: 2026-08-01
generator: none
---

# The documentation system

**What each document in this repo is for, how long it stays true, and what retires it.**

This file is itself `kind: contract` — it describes what is true now, it is edited in place,
and a stale line in it is a defect rather than history.

## Why this exists, in one paragraph

`AUDIT.md` names this run's clearest lesson: *"Documentation goes stale without going red."*
Task 34 § D already wrote the right principle — dispositions go **by document type, not by
schedule** — and then left it inside a single task file, where no future document could ever be
checked against it. Four documents drifted out from under it within a day.

The asymmetry that motivates this file: **`backend/tools/audit-doc-links.py` reports zero broken
links and § D's disposition table did not survive one session.** One had a script; the other did
not.

**But state the evidence honestly, because it is weaker than that sentence sounds.**
`audit-doc-links.py` is wired into **nothing** — no test, no git hook, no CI (verified
2026-08-01: `ls .git/hooks`, `grep -rn audit-doc-links backend/tests/`). It has held for **one
day**, and only because someone types the command. So the real lesson is narrower and sharper:

> A script is one step better than prose. **A script nobody runs automatically is exactly one
> step better**, and it decays the moment the person who remembers it stops running it.

That is why rule 7 says *checked*, not *scripted*, and why task 36 wires both checkers into the
suite rather than adding a second unrun tool.

## Rule 1 — Every document declares its kind

In frontmatter, first thing in the file. Five kinds; each has exactly one lifecycle.

| `kind:` | the question it answers | how it changes | may it be stale? |
|---|---|---|---|
| `contract` | what is true of the system **now** | edited in place, by the commit that changes the behaviour it describes | **no.** A stale contract is a defect, not history |
| `rationale` | why this was chosen, and what was rejected | **append-only.** Entries are never rewritten, only struck and superseded | **cannot be** — every entry is dated by construction |
| `record` | what happened, or what was measured, and when | **frozen** at write time | irrelevant. It is history and says so |
| `rolling` | what should I do next, and what must I not break | rewritten each session; **exactly one** per active workstream | **must be rolled forward or retired** — see rule 4 |
| `task` | what is this piece of work, and is it done | frozen once `Status:` reads DONE | frozen |

This is not a new taxonomy imposed on the tree — it is a name for what the tree already does.
`DECISIONS.md` is append-only rationale and says so in its own header. `CLAUDE_UPDATES.md` is a
dated record. `HANDOFF.md` is rolling. `docs/ingest/*.md` are contracts. The kinds were always
there; nothing could *check* them because nothing declared them.

**Precedent that a tree-wide frontmatter sweep is practical:** task 34 § A2 applied
`generator: none` to all fourteen `docs/ingest/` files in one commit.

### Choosing between `contract` and `record`

The distinction that matters and is easy to get wrong: **a measurement is a `record`; the
number the system currently runs on is a `contract`.** `docs/pursuit-gate-volume.md` records a
measurement taken on a date and is frozen. `config/relevance.json`'s `_comment` fields describe
the gate that is live tonight and must move when it moves. Writing a measurement as a contract
is what makes a document need continuous rewriting; writing a contract as a record is what lets
it quietly stop being true.

## Rule 2 — One figure, one owner

**A number appears with its instrument in exactly one document. Everywhere else cites that
document.**

`AUDIT.md` is the owner for run-level figures — it was built for exactly this and its own header
says it *"indexes; it does not restate."*

The failure this prevents is already in the tree. The main suite's test count is written as
three different values in three live documents, and none of them is what the runner prints. Each
was correct on the day it was typed. Nothing was wrong; the number was simply copied to four
places and only one of them was ever updated again.

## Rule 3 — A number a script can produce is never typed into prose

Test counts, defect counts, task counts, link counts, row counts. The document records **how to
get the number**, not what it was.

`AUDIT.md` already half-applies this — *"Read the `Ran N tests` line, not a static count"* — and
the half it applies is the half that has not drifted.

Where a figure is genuinely expensive to reproduce (an LLM eval, a labelling session), it is a
`record`, it carries its date and its n, and rule 2 puts it in one place.

**Corollary — cite the metric, not just the value.** `ai_involvement` self-consistency circulates
in this repo as three different percentages. All three are correct: they are the repeat-3 metric,
the pairwise two-run metric, and a per-platform cell. A number written without the metric beside
it is not a measurement, it is a rumour with a decimal point.

## Rule 4 — Mark, do not delete — and retire on a trigger

The first half is this run's existing convention and does not change: **tidying by deletion
removes the only evidence a number was ever wrong.** Struck-and-kept, with the correction beside
it.

The second half is what was missing. **A `rolling` document whose subject has landed is archived
in the same commit that lands it.** Retirement is an event with a cause, not a chore someone
eventually notices.

Without that trigger, `HANDOFF.md`'s sixty-second entry point went on telling every fresh
session to go do a task that was already finished — and repeating, as its justification, a
premise that the finished task's own file had struck as **WRONG**. Nothing was red. The document
was simply never given a reason to stop.

Archived files follow `docs/archive/README.md`: a provenance header saying **what it measured,
when, and what superseded it**, and a **stub and link** left where the content was, so an
inbound citation still lands somewhere.

## Rule 5 — Promote durable content out of bound contexts

**If it would still be true for a different cohort, persona, model or product, it does not
belong inside a document about this one.**

`docs/MEASUREMENT-TRAPS.md` is the model: seven traps that apply to any measurement anywhere,
which spent weeks buried in a handoff about a persona that is no longer the target. Promoting it
cost one commit and it is now cited from `.claude/CLAUDE.md`.

The test is a question — *would this sentence survive the product changing?* If yes, it belongs
at the top level of `docs/`, not in a task file, a handoff, or a session log.

## Rule 6 — Every register owns an ID prefix, declared in its own header

One allocator per register. No register may issue an identifier in another's space.

| prefix | register | means |
|---|---|---|
| `D` | [`ingest/DEFECTS.md`](ingest/DEFECTS.md) | a defect |
| `DEC` | [`tasks/refactor/DECISIONS.md`](tasks/refactor/DECISIONS.md) | a decision |
| task number | [`tasks/refactor/README.md`](tasks/refactor/README.md) | a unit of work |

Cross-references between registers are **written out** — *"defect D45"*, *"decision DEC-52"* —
because a bare `D45` in a code comment cannot be resolved by a reader who does not already know
which file it came from.

This is a live problem, not a hypothetical: `D45` currently resolves to a defect **and** to two
different decision entries, and the ambiguity has already propagated into
`backend/tools/ats-discover.py`. Task 39 resolves it.

## Rule 7 — A rule with no check is a suggestion

**Every rule above is mechanically checked *by something that runs without being remembered*,
or it is documented as unenforced.**

This is the rule that makes the other six worth writing. It is stated as an empirical claim
about this specific repository, with the caveat recorded above: the one scripted rule here has
held for a day and is invoked by hand. **"Has a script" is not the bar. "Fails a suite someone
is already running" is the bar** — otherwise the check joins the prose it was meant to replace,
one indirection later.

`backend/tools/audit-docs.py` (task 36) is the checker. It follows
`audit-doc-links.py`'s contract exactly, because that contract is the one that worked:

- reports `file:line`, the problem, **and the correct fix where one is unambiguous**
- **refuses to guess** when the fix is ambiguous — guessing at a missing target is what
  produced a duplicate task 34
- exits non-zero
- runs offline, with no network and no database, so it can never be a flake

**What is deliberately not checked**, and is therefore convention rather than rule: whether a
`rationale` entry is *good*, whether a `record` is *interesting*, and whether prose is accurate.
No script can check those, and pretending otherwise would put a green tick beside a document
nobody read.

## The maintenance loop — using this while developing

| when | what happens | enforced by |
|---|---|---|
| **at decision time** | append to `DECISIONS.md`. The reasoning cannot be reconstructed later — `relevance.json`'s rejected-alternative note is information that existed for about an hour | convention |
| **at land time** | the commit that changes behaviour edits the `contract` document describing it, in the same commit | ~~`audit-docs.py`~~ **convention — unenforced, corrected 2026-08-01. See below** |
| **at session end** | append to `CLAUDE_UPDATES.md`; **roll forward or retire** the `rolling` document | `audit-docs.py` staleness check |
| **at phase boundary** | run `audit-docs.py` and `audit-doc-links.py`; archive what they flag | both suites |

**The "at land time" row claimed an enforcement that does not exist, and task 37 found it by
being caught by it.** No check compares a `contract`'s last-modified commit against its
subject's. C3 does exactly that comparison and does it **only for `kind: rolling`**. Rule 7
allows a rule to be unenforced; it does not allow one to *claim* a checker it does not have,
which is the same failure as a stale contract and in the file that defines the term.

The cost was immediate and measurable: **six per-script contracts still said upsert errors
were discarded four days after `e353e3e` moved all eight sites to `upsert_checked`** — in the
*"Logged vs. swallowed"* table, which is exactly where a reader goes to ask *"would I find
out?"*. Generalising C3 from `rolling` to every `contract` with a declared subject is the
obvious next check and is not yet written.

The convention that all of these move in the same commit as the code is older than this file.
**It has failed once**, and the failure is instructive: `CLAUDE_UPDATES.md` silently stopped
being written for four sessions and nothing was red, *because a document that stops being
written looks exactly like a document with nothing to say.* That is the specific hole rule 7 is
cut to fit.

## What this policy deliberately does not change

- **No linter, no formatter.** There is none configured and that is intentional. Do not add one
  as part of "cleanup".
- **`psycopg[binary]` stays the only third-party dependency** of the pipeline. `api/` and
  `webapp/` have their own venvs with `include-system-site-packages = false`.
- **`_comment` fields in config JSON.** Task 34 called this *"the single most valuable
  documentation practice in the repo"*. It is `rationale`, it lives in the config file rather
  than in `docs/`, and it stays exactly as it is.
- **Append-only means append-only.** Nothing in this policy licenses rewriting an existing
  `DECISIONS.md` or `CLAUDE_UPDATES.md` entry. Identifiers and anchors may be corrected; entry
  text may not.

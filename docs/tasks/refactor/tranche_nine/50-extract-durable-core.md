---
kind: task
written: 2026-08-02
generator: none
---

# 50 — extract the knowledge that cannot be regenerated, before anything is archived

**Status:** TODO. **Depends on:** 49. **Blocks:** 51 — **and 51 must not start until this is
done and reviewed.**

**The ordering is the whole safety property.** Archive first and the extraction becomes an
archaeology exercise against `git log`. Extract first and 51 is a `git mv` with nothing at
stake.

## The test

`DOCS-POLICY.md` rule 5 already states it: **would this sentence survive the product changing?**
Add a second, sharper one for this task:

> **Could this be recovered by reading the code?**

If yes, it does not need extracting — 49 already wrote it down, and a document that restates
what the code says is exactly the content `/doctor` cuts. What must be extracted is the
opposite: **knowledge that cost an incident to learn and leaves no trace in the source.**

## The four kinds worth carrying

**1. Landmines.** Facts about the world that the code cannot tell you, each of which cost a
real defect: Postgres word boundary is `\y` and `\b` is BACKSPACE, so a `\b` pattern silently
matches nothing. Never unpack `upsert()` as a bare three-tuple. Workday `limit` cannot exceed 20
and returns an empty array rather than an error. A throttled page is not the end of a list —
reconcile against the `total` the API returned. **Silence is this system's failure mode: alert
on volume, not on errors.**

**2. Measurement discipline.** `docs/MEASUREMENT-TRAPS.md` is already promoted and already
domain-independent — it moves unchanged. Beside it: never evaluate on the layer you trained on;
never select a corpus with `ORDER BY first_seen DESC`; average precision is the measurement and
precision@20 the objective; pin eval sets by sorted `job_id`. And the model floor —
`deepseek-v4-flash` does not agree with itself at temperature 0, **and the metric name travels
with the number or the number is meaningless.**

**3. Architecture invariants.** The properties that make the system cost what it costs:
`job_facts` shared and scores per profile; `match_score` orders and `fit_score` only annotates;
LLMs explain and never rank; `score_job()` is pure; a deferral is not a failure; versions are
cache keys. These are recoverable from the code with effort — but the *reason they must not be
broken* is not, and that is what gets carried.

**4. Method.** `docs/WORKING-METHOD.md` moves nearly unchanged. Its evidence is dated incidents
and that is the point. Rule 7 — *a rule with no check is a suggestion, and the bar is failing a
suite someone is already running* — is the most transferable sentence this run produced and it
belongs at user level, not repo level (task 52).

## What is explicitly NOT extracted

- **`DECISIONS.md`.** It is not extracted because **it is not going anywhere.** Append-only
  rationale, 3,350 lines, and the only artifact that answers *why is it like this* for a system
  the owner no longer holds in their head. It stays exactly where it is, at its current size.
- **`_comment` fields in config.** Already living with the thing they describe. Task 34 called
  this the single most valuable documentation practice in the repo. Untouched.
- **`DEFECTS.md`.** A structured register with a checked namespace. Untouched by this tranche;
  revisit only when other people are in the repo.
- **Anything 49 could reconstruct from the code.**

## The output

Extraction targets, and **each is a destination that already exists or is created here** — not a
new pile:

| content | destination | kind |
|---|---|---|
| landmines | `.claude/rules/` — path-scoped, task 52 | contract |
| measurement discipline | `docs/MEASUREMENT-TRAPS.md` (extend) | contract |
| architecture invariants | `.claude/CLAUDE.md` (task 52) | contract |
| method, generalised | `~/.claude/CLAUDE.md` (task 52) | contract |
| everything else durable | `docs/STATE-OF-THE-SYSTEM.md` (from 49) | contract |

**Total target: under 400 lines carried out of ~46,000.** If the extraction is running to
1,500 lines, the test in § *The test* is not being applied — most of what feels essential is
recoverable from the code and was written down because writing it down was the available work.

## Definition of done

- [ ] Every extracted line has a destination in the table above; nothing lands in a new file
      invented by this task
- [ ] Extracted content is **byte-identical to its source where possible** — extract by line
      range, never retype. Task 47's precedent: `git log -p` still reaches all of it
- [ ] Total extracted is under 400 lines, and the number is reported
- [ ] `DECISIONS.md`, `DEFECTS.md` and every `_comment` field are unmodified
- [ ] A `kind: record` session file lists what was carried and, more usefully, **what was
      considered and left behind, with the reason** — that list is the argument 51 rests on

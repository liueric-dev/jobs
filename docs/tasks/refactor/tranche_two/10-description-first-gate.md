# 10 — Description-first relevance gate

**Status:** todo. **Depends on:** 05. **Blocks:** 12, 13, all of Phase 3.

Make the gate find postings whose title says nothing about AI and whose description
says everything.

## The problem, stated precisely

`config/relevance.json`'s `title_include` is a list of software job titles. The
population's target roles — *AI Operations Coordinator*, *Prompt Specialist*, *AI
Implementation Analyst*, *Automation Associate* — match none of them, fall to tier 3,
and `max_tier_to_score` is 2. They are never extracted, never scored, never seen.

The signal for these roles is not in the header. It is in the body: mentions of
ChatGPT, Claude, prompting, automation platforms, "AI tools." So the gate has to read
`description_text`.

**This is free.** Postgres regex or full-text over a column that is already stored.
No LLM, no new dependency, no per-posting cost. The only budget it consumes is the
downstream extraction volume that task 05 measured.

## What already works and must not be broken

`relevance.py` is in better shape than the config suggests:

- `load(path=None, cfg=None)` merges a per-profile dict from `profiles.relevance_json`
  over a shared default (`:66-88`)
- `for_profile(profile, default_cfg)` resolves per profile (`:89`)
- **`union_sql(cfgs)` already gates N profiles with different configs in one pass**
  (`:199`)

So the multi-tenancy is done. `relevance.json:_comment` states it plainly: this file
*"is the ONLY file that knows this pipeline is currently pointed at software roles"* —
`relevance.py` itself is generic. That was good foresight and this task should keep it
true.

## Work

### Extend `tier_sql()` with description matching

Today `tier_sql` (`:112`) composes title include/exclude, company exclude, description
exclude, and location columns. Add `description_include`, and redefine the tiers so a
description match can carry a posting on its own:

| tier | rule |
|---|---|
| 1 | (title match **or** description match) **and** location acceptable |
| 2 | (title match **or** description match), location unknown or elsewhere |
| 3 | everything else |

Keep `title_exclude` and `company_exclude` applying to both paths — a posting whose
description mentions ChatGPT but whose title is "Account Executive" is still not
wanted, and the existing exclusions already encode that judgement carefully. The
`_title_exclude_note` explaining why broad words like "manager" are deliberately
absent should survive unchanged.

### The pattern

Lift it verbatim from task 05's report rather than reinventing it, along with that
task's hand-checked precision figure.

**Use `\y`, not `\b`.** `relevance.json:_regex_dialect` records that in Postgres `\b`
is BACKSPACE, so a `\b` pattern silently matches nothing and quietly demotes
everything it was meant to catch. `tools/relevance-report.py --dead` exists to catch
exactly this mistake; run it after every pattern change.

### Regex or full-text

Start with regex (`~*`) for consistency with the existing patterns and because the
dead-pattern tooling already understands them. If `EXPLAIN` shows sequential scans
dominating the nightly window, move to a `tsvector` GIN index on `description_text`
— but measure first. Task 04's wall-clock baseline is the reference.

### A cohort `relevance_json`

The new patterns belong in the cohort profile's `relevance_json`, **not** in
`config/relevance.json`'s shared default. The author's profile keeps the current
software-title gate. Both are gated in one pass by `union_sql`, which is the property
that makes this cheap.

Write `_comment` fields for every new pattern group, in the style of the existing
ones. `_title_include_note` and `_company_exclude_rejected_note` are the most valuable
documentation in the repo precisely because they record rejected alternatives; the new
patterns deserve the same.

### Do not delete the tech sources yet

`builtin-nyc`, `weworkremotely` and `hn-hiring` still serve the author's profile.
Drop them from the *cohort* gate, not from the repo.

## Definition of done

- A posting titled "Operations Coordinator" whose description mentions ChatGPT
  reaches tier 1 or 2 for the cohort profile.
- The author's profile's tier assignments are **unchanged** — verify by diffing tier
  counts before and after.
- `tools/relevance-report.py --dead` reports no dead patterns.
- Hand-check 30 newly-admitted rows; record the precision figure.
- Tier-count-by-platform is recorded before and after, so task 12's extraction volume
  projection has a real input.
- Every new pattern group has a `_comment`.

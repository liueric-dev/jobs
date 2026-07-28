# 05 — Corpus volume under a widened gate

**Status:** todo. **Depends on:** nothing. **Blocks:** 04's projection, 10, 12.

Answer one question with SQL and no LLM calls: **how many postings would a
Pursuit-targeted gate admit, per day?**

It is free, it takes an afternoon, and it is the multiplier on every cost, quota and
wall-clock figure in the plan.

## The current gate excludes the target population

`config/relevance.json`'s `title_include` is `engineer`, `engineering`, `developer`,
`development engineer`, `software`, `swe`, `programmer`, `architect`, `sre`, `site
reliability`, `devops`, `platform`.

Now consider what Builders are targeting: *AI Operations Coordinator* at a hospital
system, *Prompt Specialist* at an agency, *AI Implementation Analyst* at an insurer,
*Automation Associate* in logistics. None match. All fall to tier 3.
`max_tier_to_score` is 2. They are never scored, never extracted, never seen.

So the current corpus cannot answer the question — the postings are either absent, or
present and untouched at tier 3.

## Measure

Against the live database (11,517 rows at `dd49a27`, larger now), with no LLM calls.

### 1. What is already there but gated out

Count rows at tier 3 whose `description_text` matches AI-tool vocabulary. Start with
a deliberately broad pattern and narrow it:

```
chatgpt | claude | copilot | gemini | \yllm\y | large language model |
prompt engineer | prompting | generative ai | \ygen ai\y |
automation | workflow automation | zapier | \yn8n\y | make\.com |
ai tool | ai-powered | machine learning
```

Postgres regex, `~*`, and **`\y` for word boundary, not `\b`** —
`relevance.json:_regex_dialect` records that `\b` is BACKSPACE in Postgres and a `\b`
pattern silently matches nothing. That note exists because someone already lost time
to it.

### 2. Cross-tabulate against entry-level signals

Of those rows, how many carry entry-level signals in the title or description:
`entry level`, `junior`, `associate`, `coordinator`, `assistant`, `specialist`,
`analyst`, `no experience`, `will train`, `apprentice`? And how many are NYC or
remote by `location_is_nyc` / `location_is_remote`?

### 3. Where do they come from

Group by `platform`. The expectation is that almost none come from
`builtin-nyc`, `weworkremotely` or `hn_whoishiring` — those are tech-company sources
— and that whatever exists arrives via `google_jobs` and the broader ATS pull. If
that holds, it is direct evidence for the Phase 3 sourcing rebuild.

### 4. Rate, not stock

The stock is a curiosity; the **rate** sizes the pipeline. Group the matching rows by
`first_seen::date` over the last 30 days to get postings/day. That is the `N` in task
04's derived sentence.

### 5. False-positive check

Read 30 matching rows by hand. `automation` and `machine learning` will pull in
manufacturing and ML-research roles that are wrong in opposite directions. The point
is not to perfect the pattern here — task 10 does that — but to know roughly what
fraction of the count is junk, so the projection is not built on a number that is 40%
noise.

## Output

A short report committed to `docs/` — not a script that must be re-run to be
understood:

| quantity | value |
|---|---|
| tier-3 rows matching AI vocabulary | |
| …also entry-level signalled | |
| …also NYC or remote | |
| new per day, 30-day mean | |
| by platform | |
| hand-checked precision, n=30 | |

Plus the pattern used, verbatim, so task 10 starts from it rather than reinventing it.

## Definition of done

- The table above is filled in and committed.
- The regex is recorded in a form task 10 can lift directly.
- `N` postings/day is stated as a single number with its date range, and referenced
  from task 04.
- Nothing was extracted, scored, or re-tuned.

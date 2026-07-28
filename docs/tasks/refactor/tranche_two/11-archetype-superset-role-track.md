# 11 — Archetype superset, `role_track`, and missingness

**Status:** DONE, `da4942c`. **Depends on:** 06, 10.
**Blocks:** 12, 13, 30.

> **Correction, 2026-07-28.** Section 3 below is wrong about the code it describes. The
> fields it says are NULL were never NULL — `extract.normalize()` substituted `"other"`,
> `"none"`, `"unknown"` and `false` for absent answers, so 0 of 5,321 non-tombstoned rows
> held a NULL in any of them. The bias is real but lives in extraction, not scoring, and
> the fix had to land in both. See `DECISIONS.md`, "11 — `normalize()` stopped defaulting".
> Section 1's framing is also off in proportion: `other` was mostly a *tech* vocabulary
> gap, not an ops one. Read the code before this file.

Three changes to `job_facts`, designed together because they ship in one
`FACTS_VERSION` bump (task 12).

## 1. The archetype superset

`config/criteria.json`'s twelve archetypes are all software engineering:
`forward_deployed`, `solutions`, `ai_integration`, `fullstack`, `backend`,
`frontend`, `data`, `devops`, `security`, `pm`, `ml_research`, `other`.

An AI operations role at an insurance company extracts as `other`, worth exactly 0 —
**identical to a missing value**. The single most predictive feature in
`score_job()` is uniformly uninformative across the cohort's entire opportunity
space.

### Why a superset rather than per-vertical vocabularies

`job_facts` is shared across profiles and extraction runs once per posting, ever.
Per-vertical archetypes would break one of those two properties. So one vocabulary
covers both populations, and `criteria.json` decides what each value is worth — a
software profile weights the ops archetypes at or below zero, the cohort profile does
the reverse.

Add values grounded in what the corpus actually contains (task 05's report), not in
imagination. Candidates to validate against the data: `ai_operations`,
`automation_specialist`, `implementation_analyst`, `support_ops`, `marketing_ops`,
`data_coordination`, `admin_ops`.

**Escape hatch, recorded now:** if a third vertical ever appears, stop hand-growing
this and adopt O\*NET/SOC codes. Hand-maintained taxonomies that lag reality are the
documented failure mode — it is why LinkedIn abandoned theirs. Two verticals does not
justify SOC's complexity; four would.

## 2. `role_track` as a fact

A new nullable `job_facts` column carrying a cluster label — the browsable role
families the UI groups by.

### Why a fact and not a profile

Eight track *profiles* would mean eight hand-authored `criteria.json` files, and
`learned-ranker-probe.py` already identified hand-tuned weights as the bottleneck:
eight configs nobody can validate is worse than one. Compute is not the constraint —
`job_matches` is arithmetic, and narratives are gated by `--active-within-days` and
narrative-on-login, so tracks nobody opens generate nothing.

If a track later proves to need its own weights, promote it to a profile. `profiles`
already supports that; nothing is foreclosed.

### Derive it, do not author it

The tracks come from clustering the corpus, not from a workshop. Cluster titles and
descriptions of postings that pass task 10's gate, read what falls out, and name the
clusters. Run this against the corpus **after** Phase 3 has added the new sources if
possible — a taxonomy derived from today's tech-heavy corpus will not describe the
population's opportunity space.

Practical sequencing: define the column and the extraction slot now, populate with a
provisional vocabulary from task 05's corpus, and expect to revise it once Phase 3
lands. Record that expectation in the config comment so the first vocabulary is not
mistaken for a settled one.

## 3. Explicit missingness

`score_job()` handles unknown seniority explicitly (`unknown_penalty: -4`) and
handles unknown *everything else* by falling through with no delta — which scores
identically to being on target. A NULL `role_archetype` reads as a perfect archetype
match. A NULL `advanced_degree_required` is indistinguishable from `false`.

Given task 06 is measuring how often extraction produces unstable or absent values on
messy sources, this is a systematic bias that **rewards postings the extractor failed
on** — and Phase 3 is about to add the messiest sources yet.

### Work

- Every nullable feature gets an explicit `unknown_penalty` in `criteria.json`,
  alongside the existing seniority one.
- The feature vector carries a paired `is_missing` indicator per nullable field
  (contract C3 in the master plan), so a future ranker can learn the difference
  rather than inheriting the bias.
- `match_reasons` records missingness as its own reason entry, not silence. "Why is
  this ranked 8th" should be answerable when the answer is "we could not tell what
  it was."

## Gate from task 06

If `ai_involvement` self-agreement came in below 90% on the messy platforms, this
task also carries the mitigation — a confidence field, or majority-of-3 extraction
for that field alone. Do not proceed to task 12 without deciding which.

## Definition of done

- Archetype vocabulary extended, grounded in corpus evidence, with a `_comment`
  recording where the values came from and the O\*NET escape hatch.
- `role_track` column exists, populated provisionally, with its provisional status
  documented.
- Every nullable `job_facts` field has an `unknown_penalty` and an `is_missing`
  indicator.
- `score_job()` remains pure — no I/O, still unit-testable and sweepable.
- `match_reasons` emits missingness entries.
- Existing tests in `tests/test_match.py` pass; new ones cover each missingness path.
- **Nothing is re-extracted yet.** That is task 12.

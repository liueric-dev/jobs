# 13 — Cohort criteria profile

**Status:** todo. **Depends on:** 11, 12. **Blocks:** 26, 29, 30.

> **Correction, 2026-07-28.** Three things below are wrong about the code as it stands.
> This is the seventh task file confirmed so; the other six are listed at
> `HANDOFF.md:302-308`. Read the code before this file.
>
> 1. **`entry` is not in the vocabulary and was not added.** Section "Seniority" asks for
>    `target: ["entry", "junior", "new_grad"]` (line 39). `entry` appears in neither
>    `match.SENIORITY_ORDER` (`match.py:65-66`) nor `extract.SENIORITY`
>    (`extract.py:205-206`). `match.py:152-154` filters the target list through
>    `if t in SENIORITY_ORDER` before computing the distance fallback, so an `entry`
>    target would be dropped there **silently**, and no extracted value could ever match
>    it because the extractor cannot emit it. Adding it means a `FACTS_VERSION` bump and a
>    full re-extraction of the corpus, to buy a synonym for two values already present.
>    Shipped as `target: ["new_grad", "junior"]`.
> 2. **The Definition of done's line 125 cannot be executed as written, and was replaced
>    with a stronger assertion.** It asks for a top-50 diff of the author's rankings before
>    and after. `tech` and `frontend` are inactive as of task 12, and their `job_matches`
>    sit at `facts_version = 2` while `job_facts` v3 exists only for the pursuit corpus, so
>    `match.py` cannot recompute `tech` without first re-extracting ~5,000 postings — which
>    is the bill task 12 was run to avoid. What was asserted instead: `tech`'s
>    `criteria_json` md5, its `criteria_version`, and the md5 of all 3,085 of its
>    `job_matches` rows are **byte-identical** before and after. That is unchanged
>    *rankings* proved by unchanged *stored scores*, which is stronger than a top-50 diff
>    and costs nothing. See `DECISIONS.md`.
> 3. **The Definition of done's lines 122-123 are not met, and were not tuned into being
>    met.** They ask for 20 hand-picked target roles that all clear the floor *and* all
>    appear in the top 20. A list picked blind — on title, company and location, the three
>    fields `score_job()` cannot see — gives **16 of 20 above the floor and 10 of 20 in the
>    top 20**. Line 124 is met in full, 10 of 10. Three of the four misses carry
>    `ai_involvement = 'none'` and are arguably correct rejections: they read AI-adjacent
>    only because the employer is an AI company, which is the exact failure mode task 05
>    measured at 6.7% precision. The numbers, the diagnosis and the reason nothing was
>    re-tuned are in `backend/evals/fixtures/pursuit-criteria-goldens.json`.

Author the first `criteria.json` that describes someone other than the repo's owner.

## What the current weights do to the population

Straight from `config/criteria.json`, against `base: 35`:

| setting | value | effect on a Builder's target role |
|---|---|---|
| `seniority.target` | `["mid"]` | wrong tier entirely |
| `seniority.tolerate.new_grad` | **−40** | clamps to 0 — the exact postings needed are zeroed |
| `seniority.hard_exclude` | includes `intern` | removes apprenticeships, a real entry path for career changers |
| `archetypes.*` | twelve software values | a hospital AI-ops role extracts as `other` = 0 |
| `ai_involvement.builds_llm_features` | 12 | out of reach |
| `ai_involvement.uses_ai_tools` | **6** | **the actual target, weighted half as much** |
| `years_experience.max_required` | 6 | incidentally helpful — penalises senior postings |
| `flags.advanced_degree_required` | −45 | transfers unchanged |

Three independent mechanisms exclude the cohort's opportunity space. This task fixes
the third; tasks 10 and 11 fixed the first two.

## The shared floor is real; the target role is not

There is no single role to aim at — Builders are at different stages with a hands-off
curriculum. But the floor is well defined and that is what this config encodes:

**entry-level · AI-adjacent · NYC or remote · no degree required**

Anything narrower is invented, and inventing it is what task 11's `role_track`
exists to avoid.

## Work

### Seniority

`target: ["entry", "junior", "new_grad"]`. Remove `intern` from `hard_exclude` —
paid apprenticeships and fellowships are a legitimate path for this population and
Pursuit's own model includes embedded placements. Hard-exclude `staff`, `principal`,
`director`, `exec` instead.

Set `unknown_penalty` deliberately rather than inheriting −4. Given task 06's
findings on `seniority_level` instability, an unknown seniority on a messy source is
common and should not be punished as though it were evidence.

### `ai_involvement`

Invert the ordering:

```
uses_ai_tools:       <highest>
builds_llm_features: <positive but lower>
none:                <negative>
core_ml_research:    <hard negative>
```

`uses_ai_tools` is the cohort's entire targeting mechanism. Weight it accordingly,
and record in a `_comment` that this inversion is deliberate and is the single line
most likely to be "corrected" by someone reading the author's profile alongside it.

### Archetypes

Weight task 11's new values positively; weight the software-specific ones at or near
zero rather than negative — a Builder who does have some technical aptitude should
not be actively steered away from a junior developer posting.

### Years of experience

The current `max_required: 6` with `over_penalty_per_year: 8` happens to help, but
for the wrong reason. Set it explicitly for this population: penalise postings
demanding more than ~2 years, steeply.

**Do not model prior-domain experience here.** A Builder may be fifteen years senior
in nursing and entry-level in AI; `seniority_level` describes the *posting*, not the
person. The transferable-skills story belongs in `gap_bridging_angle` (task 30), which
is the narrative tier's job and which LLMs are genuinely good at. Trying to encode it
as a scalar weight is how you get a config nobody can reason about.

### Missingness

Set the `unknown_penalty` for every nullable field introduced in task 11. Start
conservative — a small penalty, not a large one — because the messy sources arriving
in Phase 3 will produce many unknowns and an aggressive penalty would systematically
suppress exactly the non-tech employers this refactor exists to surface.

### Location

`accept_nyc` and `accept_remote` both positive. Keep `onsite_elsewhere_penalty`
strong: the cohort is local and in-person.

Per the master plan, **stop discarding non-NYC rows at ingest** — filter here, at the
per-profile gate, not upstream. Storage is free, the fetch already happened, and it
makes any future geographic expansion a config change rather than a re-crawl.

### Write the comments

Every weight gets a `_comment` explaining where the number came from — and, where
applicable, what was rejected. The existing `_hard_exclude_comment` and
`_title_include_note` are the most valuable documentation in the repo because they
record reasoning that could only be written at the moment of the decision. Match that
standard.

Note that `_hard_exclude_comment` currently justifies its penalty design by citing
`compare-extract.py`'s 95% / 90% self-agreement figures. Task 06 may have superseded
those. Correct the citation rather than leaving it.

## Leave the author's profile alone

`criteria_version` bumps per profile. The author's profile keeps its current weights
and becomes the regression test: a genuinely different persona hitting the same
shared `job_facts`, which exercises the per-profile config surface honestly rather
than through a synthetic fixture. If task 11's archetype superset breaks something,
it will show up in a list the author reads daily.

## Definition of done

- A cohort profile exists in `profiles` with its own `criteria_json`,
  `relevance_json` and `persona_json`, created through code that task 26 will
  generalise — not hand-inserted SQL.
- A hand-picked list of 20 plausible Pursuit target roles scores above
  `MATCH_FLOOR` and appears in the top 20.
- A hand-picked list of 10 senior software roles scores below the floor.
- The author's profile's rankings are **unchanged** — diff top-50 before and after.
- Every weight has a `_comment`.
- The stale self-agreement citation is corrected.

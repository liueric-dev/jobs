# `job_facts` version 2 → version 3: the field-by-field diff

**Date:** 2026-07-28. **Task:** `docs/tasks/refactor/tranche_two/12-facts-version-bump.md`.
**Bump:** `schema.FACTS_VERSION` 2 → 3 (`backend/schema.py:199`).

### Where the numbers come from

Every figure below is either printed by a command run against the live database
on 2026-07-28, or is stated arithmetic on two such figures. The sources, named
so any of them can be re-run:

| source | what it produced |
|---|---|
| `extract.remaining()` over the active profiles | every eligible count in the table below |
| `extract._eligible_sql` + `GROUP BY` | the platform and prior-state splits of the 863 |
| the snapshot-vs-live diff over `extract._FACT_COLUMNS` | the per-field change table, the archetype and `role_track` distributions, the vote columns |
| the open/described/relevance predicates *without* the `facts_version` clause | the reachability of the 427 `other` rows |
| `backend/scripts/backfill-facts.sh` stdout | wall clock, call count, batches, stop reason |
| `python3 match.py` and `match.py --dry-run` | the recompute counts |
| direct counts over `job_facts`, `job_matches`, `job_scores`, `profiles` | table totals, tombstones, per-profile row counts |
| the ops-five query below | the per-value row and employer counts, including `ai_operations` |

The ops-five counts are quoted in full because that section makes an argument
about employer spread, and the spread is only as trustworthy as the grouping
that produced it:

```sql
SELECT f.role_archetype, count(*), count(DISTINCT j.company_name)
FROM job_facts f JOIN jobs j ON j.id = f.job_id
WHERE f.facts_version = 3 AND f.role_archetype IN
  ('ai_operations','implementation_analyst','support_ops','marketing_ops','admin_ops')
GROUP BY 1 ORDER BY 2 DESC;
```

It groups on `jobs.company_name`, a free-text field — so two spellings of one
employer count twice, and the `Confidential` caveat below is the visible case of
the same limitation. The employer counts are therefore upper bounds.

Two figures are **arithmetic, not printed**, and are marked where they appear:
non-NULL `role_track` counts (624 = 863 − 239 NULL; 372 = 579 − 207 NULL).

Where a number is a prediction from another document rather than a measurement
here, it is labelled as such in the same sentence. The scripts themselves were
scratch tooling and are not committed; each is one query over the tables named
above and is reconstructible from the SQL quoted inline.

**Two rows of that table are no longer re-runnable**, and this is the cost of
dropping the snapshot (see the last section): anything sourced from
`job_facts_v2_snapshot` — the per-field change table and the `other`-row
reachability count — can now only be reproduced by re-extracting. Everything
sourced from the live tables can be re-run today.

---

## What was done, in order

1. **Active profile set switched.** `tech` and `frontend` deactivated,
   `pursuit` activated, via `profiles.set_active` (`backend/profiles.py:214`).
   Reversible; deletes nothing. `prune_orphans` runs inside `match.py`'s loop
   over *active* profiles (`match.py:454-457`), so the deactivated profiles'
   rows were untouched — verified after the switch: `job_matches` still
   `tech` 3,085 + `frontend` 293 = 3,378, `job_scores` still `tech` 1,111 +
   `frontend` 183 = 1,294.
2. **Snapshot.** `CREATE TABLE job_facts_v2_snapshot AS SELECT * FROM
   job_facts` — 5,328 rows, 3,080 kB. Dropped after this document was written
   and its numbers checked against the tool output.
3. **`FACTS_VERSION = 3`**, and the four-item outstanding-debt block at
   `schema.py:159-184` replaced with a version-3 record.
4. **Re-extraction**, `EXTRACT_MAX_WORKERS=6` via
   `backend/scripts/backfill-facts.sh`.
5. **`python3 match.py`** to recompute matches.

### The eligible count at each step, from `extract.remaining()`

| state | active profiles | `FACTS_VERSION` | `remaining()` |
|---|---|---|---|
| before | `tech`, `frontend` | 2 | 182 |
| after the profile switch | `pursuit` | 2 | 579 |
| after the bump | `pursuit` | 3 | **863** |
| after the re-extraction | `pursuit` | 3 | **0** |

The 863 splits **579 never extracted + 284 already at version 2**, and by
platform: greenhouse 513, ashby 239, google_jobs 90, nyc_open_data 14,
workday 7. That split matters for reading everything below, because the two
halves answer different questions: the 284 are a controlled before/after on
identical postings, and the 579 are the first look at postings nothing had ever
extracted.

---

## Cost and wall clock, for sizing the next bump

Recorded because task 12's definition of done asks for it, and because the task
file's own estimate was 30 hours of serial calls.

| | measured |
|---|---|
| wall clock | **28m31s** (18:40:37Z → 19:09:08Z) |
| LLM calls | **863** |
| rows extracted | 863 |
| unusable (tombstoned) | 0 |
| deferred (retried) | 0 |
| batches | 18 |
| stop reason | `drained` — not the deadline, not no-progress |
| workers | 6 |
| effective rate | **1.98 s/call** at `EXTRACT_MAX_WORKERS=6` |

Calls equal rows exactly: zero deferrals means no posting was paid for twice,
and every row took one pass (see *The vote did not fire*, below). Against
`DECISIONS.md`'s 2.85 s/call effective at `EXTRACT_MAX_WORKERS=3`, doubling the
workers bought about 1.44x, not 2x.

**Sizing the next bump from this rather than from an estimate:** ~2 s/call at
six workers. A re-extraction of the full 5,907-row table would be roughly 3.3
hours and 5,907 calls, and would fit inside one nightly `EXTRACT_DEADLINE_SECS`
window only if that window were raised from its 3,600 s default
(`extract.py:119`).

---

## The version invariant, and the one part of the DoD that is unreachable

Task 12's definition of done says "zero rows remain at version 2." **That is
unreachable by construction and no run can satisfy it.** `_eligible_sql`
requires `j.status = 'open'` (`extract.py:405`), so a facts row whose job has
since closed is never selected again, at any version, forever.

The invariant a bump *can* hold is **"no open, relevance-eligible row sits below
the current version"** — which is exactly `extract.remaining() == 0`, and which
holds:

```
extract.remaining() -- open, described, relevant, below current version: 0
```

The rows below version 3, and why each group is there (`verify_invariant.py`):

| rows | version | job status | why it is not a backlog |
|---:|---|---|---|
| 15 | 1 | closed | Unreachable forever — `status = 'open'` excludes them. |
| 70 | 2 | closed | Same. |
| 4,959 | 2 | **open** | Open, but not relevant to `pursuit`. Extracted for `tech`/`frontend`, which are now inactive, so the relevance union no longer selects them. |
| **5,044** | | | |

None of these were deleted, and none should be. The 85 closed-job rows are the
last facts anyone has about postings that no longer exist.

**The 4,959 are a cost warning, not a defect.** Reactivating `tech` would make
roughly 5,000 rows eligible in one step — a ~5,000-call, ~3-hour re-extraction
on the numbers above, not a resumption. Plan for it before flipping a profile
back on.

### `job_matches` recomputed

`python3 match.py` wrote 863 rows for `pursuit`. Verified three ways:

- `match.py --dry-run` immediately after reports `0 matched, 863 current` — the
  version bookkeeping (`match.py:379-382`) settled, so nothing is stale.
- `job_matches` rows for the active profile with `facts_version < 3`: **0**.
- `job_matches` rows whose `facts_version` disagrees with the `job_facts` row
  they point at: **0**.

`tech` (3,085 rows at v2) and `frontend` (293 at v2) still sit at version 2, and
that is correct: they are inactive, `match.py` never looped over them, and their
facts are still version 2 too.

---

## Per-field diff — n = 284, and it cannot be more

Cohort: rows present in **both** `job_facts_v2_snapshot` and the live table at
version 3 — i.e. the same posting, extracted twice, once under each version.

**284 is a hard ceiling on this table, not a sample size that could have been
raised.** The bump re-extracted 863 rows, but 579 of them were first-time
extractions with no prior value to diff against. A per-field change rate is only
definable on the 284. **Every rate in this section is `/284`. Do not read any of
them as an 863-row rate** — the two populations differ systematically (see the
`other` split below, where the 579 behave nothing like the 284), so rescaling one
to the other would be wrong, not merely imprecise.

The denominator is repeated in the column header for that reason.

| field | changed **/284** | % of 284 | → NULL | NULL → |
|---|---:|---:|---:|---:|
| `seniority_level` | 44 / 284 | 15.5 | 0 | 0 |
| `years_experience_min` | 6 / 284 | 2.1 | 3 | 2 |
| `years_experience_max` | 2 / 284 | 0.7 | 2 | 0 |
| `role_archetype` | 86 / 284 | 30.3 | 0 | 0 |
| `role_track` | 252 / 284 | 88.7 | 0 | 252 |
| `tech_stack` | 102 / 284 | 35.9 | 0 | 0 |
| `ai_involvement` | 54 / 284 | 19.0 | 4 | 0 |
| `ml_research_required` | 2 / 284 | 0.7 | 0 | 0 |
| `advanced_degree_required` | 5 / 284 | 1.8 | 0 | 0 |
| `customer_facing` | 15 / 284 | 5.3 | 0 | 0 |
| `remote_policy` | 69 / 284 | 24.3 | 0 | 0 |
| `employment_type` | 8 / 284 | 2.8 | 0 | 0 |
| `comp_min` | 3 / 284 | 1.1 | 3 | 0 |
| `comp_max` | 3 / 284 | 1.1 | 3 | 0 |
| `comp_currency` | 5 / 284 | 1.8 | 3 | 1 |
| `gap_friendly_language` | 0 / 284 | 0.0 | 0 | 0 |
| `visa_sponsorship` | 4 / 284 | 1.4 | 0 | 0 |
| `summary` | 284 / 284 | 100.0 | 0 | 0 |

The `→ NULL` and `NULL →` columns are also out of 284, and are counts rather
than rates.

### Reading this against the self-consistency floor

**A change rate below the model's disagreement-with-itself rate is not
evidence of anything.** CLAUDE.md states the floor: `deepseek-v4-flash` does
not agree with itself at temperature 0 — 76% on `seniority_level`, 94% on
`ai_involvement`. Task 06 measured 84.3% on `role_archetype` and 85.2% on
`seniority_level` on the frozen corpus. **Every rate below is out of 284.** So:

- `seniority_level` **44/284 = 15.5%** changed against a **~24%** noise floor.
  **Inside the noise.** Nothing can be concluded about it, in either direction,
  and the distribution barely moved (senior 124→122, mid 98→105).
- `role_archetype` **86/284 = 30.3%** against a **~16%** floor. **Roughly twice
  the floor** — real movement, and expected: the vocabulary went from 12 values
  to 26.
- `ai_involvement` **54/284 = 19.0%** against a **~6%** floor. **Roughly three
  times the floor** — the largest signal-to-noise ratio in the table, and the
  field that matters most, since it is the cohort's entire targeting mechanism.
  The shift is `builds_llm_features` 107→96 and `uses_ai_tools` 79→90: the new
  extraction is **more conservative about what counts as building LLM
  features**. Four rows went to NULL, which version 2 could not express.
- `summary` **284/284 = 100%** changed. Free text from a non-deterministic
  model; the only surprising outcome would have been any other number.
- `gap_friendly_language` **0/284 = 0%** changed. Perfectly stable, and worth
  recording because it is the one field that did not move at all.

`remote_policy` at 69/284 = 24.3% has no published self-consistency figure, so it
is reported without interpretation. `tech_stack` at 102/284 = 35.9% is a set
comparison on free-form strings and is not comparable to the enum rates at all.

**None of these rates is known for the other 579 rows**, and the self-consistency
floors above were measured on a different corpus again. A field that looks stable
on the 284 may not be on the postings the cohort actually consists of.

---

## `role_archetype`: the 12 → 26 vocabulary change

### On the 284 controlled rows, `other` roughly halved

| | snapshot (v2) | live (v3) |
|---|---:|---:|
| cohort rows at `other` | 25 (8.8%) | 13 (4.6%) |

Where the snapshot's 25 `other` rows went:

| → | rows |
|---|---:|
| `other` (unchanged) | 8 |
| `infrastructure_compute` | 3 |
| `qa_test` | 3 |
| `support_ops` | 3 |
| `ai_operations` | 2 |
| `business_systems` | 2 |
| `data` | 1 |
| `hardware_embedded` | 1 |
| `it_internal` | 1 |
| `program_management` | 1 |

**16 of 25 (64%) were reclaimed by the 14 new values** — 5 by the ops five, 11
by the tech nine. One more moved to `data`, an original-twelve value.

### Task 11's `other`/427 prediction is NOT tested by this run

`docs/role-track-derivation.md:219-227` predicts the fourteen new values reclaim
**242 of 427** `other` rows (56.7%), split **54 ops / 203 tech**. **This bump
cannot confirm or falsify that**, and the reason is structural rather than a
shortfall in the run:

> Of the snapshot's 427 `other` rows, only **25** are reachable by this bump —
> open, described, and relevance-eligible for `pursuit`. The other **402** are
> `tech`-profile rows that the `pursuit` relevance union rejects.

Printed by a script that computes reachability from the open/described/relevance
predicates *without* the `facts_version` clause, precisely because that clause
is a burn-down cursor and would have deflated the count as the run progressed.

The 25-row result (64% reclaimed, 5 ops / 11 tech) is *directionally consistent*
with the 56.7% prediction and *inverts* its ops/tech split, but **n = 25 and the
sample is the pursuit-relevant slice of a tech corpus**. Per CLAUDE.md, "`n=17`
is not a result"; neither is this. It is recorded, not concluded from.

**Task 11's 203/54 prediction ends this run untested, not falsified.** Stated in
those words because the distinction erodes with retelling, and the difference
matters to whoever picks this up: nothing here is evidence against the
prediction. It was never put in a position to fail. Testing it requires
re-extracting the 402 unreachable `other` rows, which means reactivating `tech`
— the ~5,000-row re-extraction costed in the invariant section above.

### What this run tests instead — a weaker, adjacent proposition

The same table in `docs/role-track-derivation.md` has a second column: a **title
probe** over the 863 cohort-eligible postings, which that document explicitly
calls **a floor**, "since the probe reads titles and the extractor reads the
whole posting." All 863 were re-extracted here, so that column is directly
testable.

**Read this test asymmetrically — it is not symmetric evidence, and the two
directions are worth very different amounts:**

- **Over the floor confirms nothing.** The extractor reads the whole posting and
  the probe reads only the title, so finding *more* is the expected outcome
  under any hypothesis. It establishes that the floor was a floor and nothing
  else. It is **not** the vocabulary being borne out.
- **Under the floor is a real negative result.** The extractor had strictly more
  information than the probe and still assigned the new values to *fewer*
  postings. That is falsifiable, and it is what happened.

| set | title-probe floor | extractor actual | reading |
|---|---:|---:|---|
| ops (5 values) | 179 (20.7%) | **137 (15.9%)** | **42 below — negative result** |
| tech (9 values) | 69 (8.0%) | 92 (10.7%) | 23 over — confirms nothing, see above |
| **all 14** | **237 (27.5%)** | **229 (26.5%)** | **8 below — negative result** |

**The finding of this bump is the ops shortfall.** Against a floor it had more
information than, the extractor applied the five ops values to 42 fewer postings
than titles alone predicted, and that deficit is large enough to pull the
all-fourteen total under its floor despite the tech overshoot. The tech line is
reported for completeness and **should not be read as the tech nine performing
well**; a probe-beating count there was always the null expectation.

Two explanations, and this run does not distinguish them: either the title probe
over-counts ops (a title containing "Support" or "Marketing" is not
automatically a `support_ops`/`marketing_ops` role), or the extractor
under-applies the ops values because its `role_archetype` guidance was written
for software roles. The second is checkable with task 07's Axis A labels and is
the more useful thing to check first.

**This does not substitute for the `other`/427 test.** It is an adjacent, weaker
proposition about a different population, and it is reported here because it is
what the corpus permitted — not because it stands in for what task 11 actually
claimed.

### The five ops values individually, and the `ai_operations` re-check

The shortfall above is a total; the five values do not contribute to it equally.
Counts over all 863 version-3 rows, with distinct employers:

| value | rows / 863 | % | distinct employers | employers/posting |
|---|---:|---:|---:|---:|
| `support_ops` | 82 | 9.5 | 25 | 0.30 |
| `marketing_ops` | 19 | 2.2 | 16 | 0.84 |
| **`ai_operations`** | **17** | **2.0** | **14** | **0.82** |
| `admin_ops` | 12 | 1.4 | 12 | 1.00 |
| `implementation_analyst` | 7 | 0.8 | 6 | 0.86 |
| *(total, distinct rows)* | *137* | *15.9* | | |

**`support_ops` at 82 rows is nearly 5x `ai_operations` and is where the ops mass
actually is** — 60% of the 137 on its own. That is worth stating next to the
shortfall above, because the two findings agree: the ops five came in 42 under
their floor, and the ops work this corpus does contain is **support-shaped, not
AI-shaped**. The value the vocabulary change was motivated by is not the value
the cohort's employers are hiring for.

`support_ops` is also the most concentrated of the five at 0.30 employers per
posting — 82 postings across 25 employers — where the other four sit near one
employer per posting. Worth a look on its own terms later: that ratio is the
shape a few large support organisations produce, and it is the one ops value
whose spread would not survive the test `emp` exists to apply.

**`ai_operations` deserves its own paragraph, because the handoff carries a
standing caution about it** — 5 postings across 3 employers in the title probe,
"carried, and the value the whole task was motivated by; re-check it after
Phase 3 before anything is built on it." `extract.py:234-237` says the same, and
`docs/role-track-derivation.md:160-176` calls it "the weakest of the 14 by some
margin". **This run is the first re-check, and it moves two numbers:**

- **Count: 5 → 17 (3.4x).** The 5 was a title probe, the 17 is the extractor
  reading whole postings — the same probe-versus-extractor asymmetry set out
  above, applied to one value. **17 supersedes 5 for the cohort corpus.** Note
  which direction this is: an overshoot against a title probe, which by that
  section's own rule confirms nothing on its own. It is the employer count below
  that carries the information.
- **Employer spread: 3 → 14, and this moved further than the posting count did.**
  It is also the more meaningful of the two, because of how each reads: **"5
  postings at 3 employers" reads like three anomalous companies; "17 across 14"
  reads like a thin but genuine market.** That is the difference between a
  vocabulary value and an artifact. 14 employers over 17 postings, maximum 2 at
  any one — no concentration at all. Since `emp` is the column
  `docs/role-track-derivation.md:148-150` says to "read first", precisely because
  "a candidate whose mass sits at one employer is that employer's hiring spree",
  **the specific concern that caution encodes is retired.** For scale: 0.82
  employers per posting, against the two values
  `docs/role-track-derivation.md:174-176` held up as better-distributed when it
  called `ai_operations` the weakest — `admin_ops` at 15 employers on 19 postings
  (0.79) and `marketing_ops` at 29 on 52 (0.56). On this measure `ai_operations`
  now leads both.

**The honest reading, which is narrower than those numbers invite.** 3.4x
sounds like vindication and is not. `ai_operations` is **still 2.0% of the
cohort corpus** — 17 postings — and the conclusion it was recorded against is
unchanged: these employers are largely not posting these roles. What has changed
is that the floor is less alarming than 5 made it look, and that the value is no
longer the fragile one-employer artifact the `emp` column exists to catch. It is
thin but real, and it is no longer the weakest of the fourteen on spread.

Two caveats kept next to the number rather than below it: one of the 14
employers is literally `Confidential`, so the true distinct count is 13–14
depending on how that row is treated; and this is the extractor's own
assignment, not a human label, so it inherits `role_archetype`'s ~16%
self-disagreement floor. At n=17 that floor is worth about ±3 rows. Task 07's
Axis A labels are what would settle it.

### The finding nobody predicted: `other` is 31% of the cohort

Over all 863 version-3 rows, `role_archetype = 'other'` is **268 rows, 31.1%**.
The snapshot's rate was **427 of 5,328, 8.0%**. Expanding the vocabulary from 12
values to 26 was followed by `other` roughly *quadrupling* as a share.

That is not a contradiction, and the split says why:

| slice | n | at `other` | rate |
|---|---:|---:|---:|
| re-extracted, had v2 facts | 284 | 13 | **4.6%** |
| newly extracted, never had facts | 579 | 255 | **44.0%** |

On the same postings the superset works — `other` halved. The 44% is the first
honest look at postings the pipeline had never extracted: entry-level,
all-industry, NYC. **A vocabulary derived from a tech-heavy corpus leaves 44% of
the actual cohort corpus unnamed.** `docs/role-track-derivation.md` anticipated
this in principle for `role_track` ("will not describe the population's
opportunity space"); this is the number for `role_archetype`, and it is the
strongest available argument for re-running the derivation against a corpus that
now exists. It also raises the O*NET/SOC escape hatch recorded at
`extract.py:239-246` earlier than that comment expected.

`other` is priced at 0 by `config/criteria.json`, so 31% of the cohort currently
contributes nothing from its single most predictive feature.

---

## `role_track`: the new field

NULL on every version-2 row by definition — the snapshot has **0** non-NULL
`role_track` values, which is the correct baseline and not a measurement.

| slice | n | non-NULL | rate |
|---|---:|---:|---:|
| controlled cohort | 284 | 252 | **88.7%** |
| newly extracted | 579 | 372 † | 64.2% |
| **all v3 rows** | **863** | **624** † | **72.3%** |

† arithmetic: the counts printed were the NULLs (207 of 579, 239 of 863).

Distribution over all 863:

| `role_track` | rows |
|---|---:|
| *(NULL)* | 239 |
| `solutions_and_implementation` | 168 |
| `software_engineering` | 106 |
| `technical_support` | 81 |
| `business_operations` | 68 |
| `data_and_analytics` | 58 |
| `product_and_marketing` | 58 |
| `revenue_operations` | 47 |
| `business_systems` | 24 |
| `business_analysis` | 14 |

All nine values are populated; none is dead.

The NULL rate is **27.7%**. The nearest published figure is `extract.py:274-278`:
the nine tracks "cover 83.2% of clusters at n>=5", leaving 16.8%. **Those two
numbers are not comparable** — 16.8% is a share of *title clusters*, 27.7% is a
share of *postings*, and a cluster carries no weight in the first. Stated
because they are similar enough in size to be mistaken for a prediction and its
outcome, and they are not. The honest reading is that this run establishes the
posting-level NULL rate for the first time, at 27.7%, and there was no prior
figure to compare it against.

`role_track` is nullable by design and the prompt says so to the model
(`extract.py:323`). A 27.7% NULL rate is the design working, not failing — but
it is also the number to watch after the derivation is re-run.

> **Note added 2026-07-30 — THIS 27.7% IS `239 / 863`, and a second unrelated 27.7%
> existed for one day.** A measurement taken 2026-07-29 for the labelling form put
> `role_track` NULL at **244 of 881** rows at `facts_version = 3`, which is *also* 27.7%
> — a different denominator, a different run, and no relationship to this figure beyond
> the rounding. **Two independent numbers that agree to one decimal place are exactly
> what gets quoted as one confirming the other**, and this pair was one sentence away
> from it.
>
> The coincidence is now broken: after the nightly run of 2026-07-30 the corpus rate is
> **261 of 917 = 28.5%**. **The section above is not restated** — it is this run's record
> and 239/863 is what it measured. Anyone comparing NULL rates across dates must match
> the denominator first; see `docs/role-track-derivation.md`, § *A corpus statistic here
> has a shelf life of one night*.

---

## The vote did not fire, and version 3 does not certify it

**Stated plainly because the version number would otherwise imply otherwise.**
One of the four changes this bump settles is the selective majority-of-3 vote
(`config/extraction-policy.json`, `extract.vote_facts`). It was **not exercised
by this run**:

```
passes=1 unanimity=None -> 863 row(s)
```

Every one of the 863 rows is a single draw. `hn_whoishiring` is the only
platform below the 0.90 agreement threshold, and it contributed **0** of the
863 — not because of status or description filtering (208 of its postings are
open and described) but because the relevance union for `pursuit` rejects all of
them. The platforms actually re-extracted were greenhouse 513, ashby 239,
google_jobs 90, nyc_open_data 14, workday 7.

The policy file itself loaded correctly — `extract.py`'s summary line prints
`multi_pass=hn_whoishiring`, which is the counted-not-assumed check at
`extract.py:1024-1028` confirming the threshold lookup works. What is untested
is the path that runs three passes and votes.

**So version 3 means "extracted under the per-platform policy", and nothing
more.** The first `hn_whoishiring` row to become eligible is the first
production test of `vote_facts()`. Do not read 3 as a passing grade for it.

---

## What this document does not cover

- **Axis A agreement before and after** (task 07). Not measured here.
  `backend/evals/**` is owned by another track this session, and task 12's
  definition of done requires the before/after comparison to come from task 07's
  golden set — measuring it with anything else would defeat the purpose of
  gating 12 on 07. Until that comparison exists, **the rollback criterion in
  task 12's "Rollback" section has not been evaluated**, and this bump has not
  been shown to improve extraction quality on any human-labelled field. It has
  been shown to change it, per field, above.
- **Task 08's diagnostic SQL**, re-run. Not this task's file.
- **The snapshot is gone.** `job_facts_v2_snapshot` was dropped after these
  numbers were produced, under the repo owner's standing instruction that
  database contents are staging data optimised for build speed rather than
  preservation. This diff is what survives of it. Task 12's "retain the snapshot
  until Axis A confirms" step was therefore **adapted, not met** — recorded here
  so that a later Axis A regression is understood to be un-rollbackable from
  this side, and would have to be handled by a forward re-extraction.

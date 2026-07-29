# Score validation

**Task:** `docs/tasks/refactor/tranche_two/08-score-validation.md`, which is
`docs/ingestion_tests/04-score-validation.md`. **Closes:** audit item 8 (D15),
plus D16, D43 and D44 found along the way. **Measured:** 2026-07-28, branch
`webapp-service`, model `deepseek-v4-flash@api.deepseek.com`.

## What this establishes, and what it cannot

**The shape of score output, not its accuracy.** Extraction's fields are
closed vocabularies over facts a posting either states or does not, so a
disagreement is unambiguous and a human label settles it
(`backend/tools/compare-extract.py:6-20`). Scoring has no such ground truth:
there is no fact of the matter about whether 72 is the right `fit_score`, and
a labeller asked to produce one is inventing a number rather than recording an
observation.

Under the Pursuit scope that gets stronger, not weaker. ~30 Builders at
different stages with a hands-off curriculum means there is no single target
role, so `fit_score` accuracy is not merely hard to establish — it is **not
well defined**. This document is the evidence behind task 30's proposal to
display buckets and reasoning rather than a number, and §4 is the part of it
that actually decides anything.

The honest source of ranking ground truth is engagement: `job_events`
(`backend/schema.py:391-400`). It has **0 rows**, and its only consumer is a
liveness check deciding whether a profile is worth spending calls on
(`backend/score.py:_recently_active`). Nothing here waits on it.

## Method, and what it cost

Three kinds of evidence, kept separate on purpose:

1. **Production SQL** (§1, §2) — read-only, no writes, no backfill.
2. **Synthesised responses** (§2, §3) — `backend/tests/test_score.py`. Every
   coercion path is exercised without a model, because a malformed response
   manufactured to test a guard proves something about the guard and nothing
   about the model.
3. **Live model calls** (§2, §4) — **223 of them**, which is a deviation from
   this task's instruction to synthesise rather than spend, recorded here so
   the next person sizing an evals run has the real number rather than
   inferring it from a cache that gets cleared:

   | what | live calls | tokens |
   |---|---|---|
   | `evals selfcheck --repeat 3` (§4) | 165 | 277,483 |
   | `evals run --task score`, full corpus (§2) | 52 | 92,959 |
   | `evals run --task score --n 8`, first smoke test | 3 | — |
   | `evals run --task extract --n 3`, D44 regression check | 3 | — |

   The selfcheck is the spend that earned itself: self-consistency is the only
   quantity that survives the missing ground truth, and it cannot be
   synthesised — a fabricated second opinion is not a second opinion. The
   52-call run was the cheaper decision it looks like: those responses are
   content-addressed in `backend/evals/.cache`, so §2's before/after
   comparison replays at zero cost for as long as that directory survives, and
   they are the **first score responses the cache has ever held**.

   `.cache` is gitignored, so that is a local convenience, not an archive. The
   one artifact that had to be committed is the selfcheck table — see §4.

---

## 1. The before-state: what is actually stored

Run against production on 2026-07-28. This is the diagnostic
`04-score-validation.md:53-58` records as never having been run.

```
$ cd backend && (set -a; . ./.env; set +a; python3 - <<'PY' ... )
   SELECT primary_track, count(*) FROM job_scores GROUP BY 1 ORDER BY 2 DESC;
   SELECT min(fit_score), max(fit_score), count(*) FROM job_scores;

  primary_track          rows        fit_score:  min 0, max 95, n 1,294
  --------------------   ----        by profile: tech 1,111, frontend 183
  'Poor Fit'              550        distinct fit_score values: 32
  'Bridge & Solutions'    241        NULL fit_score: 54
  'AI Integration'        230        scoring_model 'FAILED:%': 57
  'Core SWE'              204
  NULL                     57
  'Re-Entry & Growth'       9
  'frontend_core'           3
```

Three things in that output, in descending order of how much they matter.

**`frontend_core` is D15, live.** Three rows, all on the `frontend` profile,
all written by `deepseek-v4-flash` on 2026-07-26, with `fit_score` 90, 82 and
85. It is the profile's own name in *extraction's* snake_case, sitting in a
column whose other five values are Title Case with spaces. Nothing coerced it
and nothing noticed: `match.py` never reads `primary_track`, so a drifted
value is invisible until something renders it.

The rate is the useful part: **3 of 1,237 model-written rows, 0.24%**. That is
why the fix is a guard rather than a migration — see §3.

**The 57 NULL tracks are the tombstone path, and they line up exactly.** 57
rows carry a `FAILED:` model label, 57 have a NULL `primary_track`, and the
two sets are identical (`primary_track IS NULL AND scoring_model NOT LIKE
'FAILED:%'` returns 0, and the converse returns 0). So the NULLs are not
drift; they are the tombstone doing its job.

**Except for three of them, which is D43.** Three `FAILED:` rows carry a
non-NULL `fit_score` (15, 80, 80) alongside a NULL `primary_track` and NULL
`gap_bridging_angle`. Only two defects together produce that combination:
`llm.has_fields()` gates the write on the six keys being *present*, not
usable, so `{"fit_score": 15, "primary_track": null, ...}` was written as a
row; and `mark_score_failed`'s `ON CONFLICT` updated only `scored_at` and
`scoring_model`, so tombstoning that row later left the score behind. Every
query that reads `fit_score` without also reading `scoring_model` believes
them. Both halves are fixed; the three rows are not backfilled (staging data,
and the next score overwrites them).

**A note on `min(fit_score)=0, max=95`.** Nothing out of range is stored
today, which is the outcome `04:59-62` said the SQL might show. It is not
evidence that the risk is theoretical — the column is `INTEGER` and would have
raised on a string, so a model answering `"85"` would have crashed a batch
rather than stored anything; and 850 would have stored silently.

### The after-run, and why it is not here

08 asks for this SQL **again after task 12's re-extraction**, because task 11
widens the archetype set and introduces `role_track`, so a coercion rule
written against today's five names may be wrong within two tasks. Task 12 has
not run. The comparison is outstanding, deliberately, and the command above is
the one to re-run — with `score.TRACKS` checked against whatever vocabulary 11
leaves behind.

---

## 2. Tie structure, before and after normalisation

08's specific worry: a normalisation rule that clamps or rounds can only make
the tie problem worse, so measure it rather than assume.

**The stored column, today.** 32 distinct values over 1,240 non-NULL rows,
and 1,098 of them (88.5%) are multiples of 5. The largest tie groups:

```
fit_score  15 → 141 rows    85 → 97    35 → 65    45 → 59    80 → 48
           25 → 120         65 → 87    30 → 63    55 → 57    70 → 47
           20 → 118         75 → 68              (NULL → 54)
```

`backend/docs/HANDOFF-match-quality.md` §4.2 recorded "59 postings share the
value 85" for `profile='tech'`; the same query today returns **86**, and the
tie block around it has grown the same way (88 → 26 rows, 82 → 24, 80 → 47).
The problem has got worse, not better, which is the documented signature of
coarse pointwise scoring and the reason §4 reports rank correlation rather
than exact agreement.

**Before vs after `normalize()`, on real responses.** 53 cached responses from
the run in §4, each passed through `llm.parse_json()` and then through
`score.normalize()`:

```
ties BEFORE normalize: n=53 distinct=19 largest=6 p_tie=0.0588
ties AFTER  normalize: n=53 distinct=19 largest=6 p_tie=0.0588
track values changed by normalize: []      fit values changed: []
```

Identical, and that is the intended result: `normalize()` is a **guard, not a
transform**. It rejects (out-of-range → NULL, off-vocabulary → NULL) and never
merges two in-range values, so it cannot increase `p_tie` for anything it
keeps. `backend/tests/test_score.py` pins that property directly rather than
relying on this one sample: over a synthetic column spanning in-range,
out-of-range and wrongly-typed values, `distinct`, `largest` and `n` are
unchanged and `p_tie` cannot rise.

**Projected onto the stored rows:** applying today's `normalize()` to the
1,294 values already in `job_scores` would change **3** — the `frontend_core`
tracks, to NULL — and **0** `fit_score`s. (The 3 D43 rows are cleared by the
tombstone fix, not by `normalize()`.) No tie group gains a member. Nothing is
backfilled either way.

---

## 3. The fix

`score.normalize()` (`backend/score.py`) returns the exact column values
`job_scores` stores, or `None` when the response is unusable at all — which
the caller turns into a tombstone. Same contract as `extract.normalize()`.

**The stored form stays Title Case, and that was the decision to get right.**
`extract._enum()` lowercases and replaces separators with underscores because
extraction's vocabularies are already snake_case. Passing the five track names
through it would map `Core SWE` → `core_swe` and **silently rewrite every
value in the column**. So `score.TRACKS` holds the display forms, `_track()`
canonicalises only for comparison (case, `-`/`_`/`&`/`/` as separators,
`and` ≡ `&`, a separator-free fallback so `CoreSWE` resolves, and first-wins
on a trailing explanation), and returns the display form. Changing the stored
form would be a migration with a reader to update
(`backend/schema.py:628`); normalising is not.

Four judgements worth naming, because each could reasonably have gone the
other way:

- **Out of range is `None`, not a clamp.** 850 clamped to 100 is a
  top-of-list annotation manufactured out of a typo. `match_score` orders the
  list precisely so a wrong `fit_score` is cheap; NULL is the honest record.
- **`Poor Fit` is never the fallback.** Defaulting an unrecognised track to it
  would turn malformed JSON into a recorded rejection of the posting. NULL
  says nothing; `Poor Fit` says something false.
- **`gap_friendly_signal` is tri-state**, replacing `bool(...)`, for the
  reason `extract._tristate_bool()` gives: `bool()` laundered an absent key,
  an explicit false and a non-boolean into one False.
- **`key_technologies` keeps its display case**, unlike `tech_stack`. That
  field is matched against config, so case is noise; this one is rendered to a
  person, and rewriting `PostgreSQL` as `postgresql` is a downgrade for no
  gain.

Structurally, `update_job_score()` now takes `normalize()`'s output and
indexes its keys, so a raw model response cannot reach the table even by
mistake. A test asserts that it raises rather than writing.

### D16: the `buckets` KeyError

Already registered by task 02 — it did not need a new id. It was **armed**:
the `pursuit` profile is `active` with a persona that has no `buckets` key,
and the only thing keeping it quiet is `daily_narrative_budget = 0`. The first
budget task 13 sets would have ended that profile's every batch.

`build_prompt` now treats `buckets` as optional and omits the section when it
is absent. With buckets present the prompt is **byte-identical** to before
(asserted against `git show HEAD:backend/score.py`), so no cached response or
prior comparison is invalidated.

`score_one_job` guards its body: an unexpected exception is a new `ERRORED`
outcome — one job, nothing written, loud on stderr unconditionally, and named
separately in `main()`'s summary so it cannot be misread as the endpoint
rate-limiting. Nothing is written because a bug here says nothing about the
posting, and a tombstone would discard it permanently.

**`profiles.validate()` was deliberately NOT changed to require `buckets`,
against the task file's own instruction** (`04:168-172`). Under the Pursuit
scope a persona with no positioning buckets is legitimate, and `pursuit`
already exists with one; requiring the key would convert a scoring-time crash
into a save-time crash for a profile that is fine. The reasoning is a comment
at `backend/profiles.py:139-149` so the absence does not read as the oversight
it originally was.

---

## 4. Self-consistency: the measurement that survives the missing ground truth

Two runs of the same persona over the same corpus should rank the same
postings the same way. A model that cannot reproduce its own ordering is
disqualified without anyone having to agree on what the right ordering was.

```
$ cd backend && python3 -m evals selfcheck --task score \
      --model deepseek-v4-flash --corpus evals/fixtures/corpus-v1.jsonl \
      --repeat 3 --workers 3 \
      --out ../docs/ingestion_tests/score-selfcheck-n120-2026-07-28.json
```

**The full table is archived at
[`docs/ingestion_tests/score-selfcheck-n120-2026-07-28.json`](ingestion_tests/score-selfcheck-n120-2026-07-28.json)**,
beside task 06's extract equivalent (`selfcheck-n120-2026-07-28.json`). Every
figure below is in it, including the per-platform cells and the per-pass tie
histograms this section only summarises. Re-deriving it costs 165 live calls,
so check it against the file rather than by re-running.

The persona is the other half of the input, and nothing in `job_scores`
records it (§5). This run used `backend/config/persona.json`, whose five
prompt-reaching keys digest to
`a4386b2ccc4677b536304239546ebaa15ddb39fd58c414490c29de4b1e671cff`
(`evals.tasks.score.persona_sha`). A run whose digest differs is not
comparable to this table.

120 fixture records, **55 usable in every repeat** (65 skipped: no `job_facts`
row, so `select_shortlist`'s inner join means the pipeline would never send
them). Live calls, no cache — `run_repeated` turns caching off whenever
`repeat > 1` because a replayed answer has no variance in it.

| field | agree2 | 95% CI | unanimous (3/3) | note |
|---|---|---|---|---|
| `gap_friendly_signal` | 100% (55/55) | [93–100] | 100% | |
| `primary_track` | **89%** (49/55) | [78–95] | 84% | |
| `fit_score` | 24% (13/55) | [14–36] | 9% | exact match |
| `key_technologies` | 20% (11/55) | [12–32] | 11% | Jaccard 35% |
| whole record | 2% (1/55) | [0–10] | | all four fields |

And the ranking block, which is what `fit_score` should be read on:

```
  fit_score
      spearman rho   mean 0.915  worst pair 0.905  (3 pairs)
      top-20 overlap  mean  83%  worst pair  75%
      |diff|         mean 6.61   max 33
      within +/-0     24% [14-36]   (13/55, repeat 1 vs 2)
      within +/-5     62% [49-73]   (34/55)
      within +/-10    91% [80-96]   (50/55)
      pass 1 ties    19 distinct over 55, largest 7, p_tie 5%
      pass 2 ties    17 distinct over 55, largest 6, p_tie 6%
      pass 3 ties    18 distinct over 55, largest 8, p_tie 6%
```

**Read this as three different questions, which is why all three are
printed.** As an exact number `fit_score` is unstable — the model reproduces
itself 24% of the time and once disagreed with itself by 33 points on the same
posting. As a *notch* it is decent (62% within one 5-point step, 91% within
two). As an *ordering* it is good: ρ ≈ 0.92, and 83% of a top-20 is the same
top-20 next run.

`p_tie` is printed beside those because it is the floor under the floor: with
~5% of random pairs sharing a value by construction, some of every agreement
figure above is coincidence rather than stability.

**This is the evidence task 30 asked for.** The bucket is stable (89%,
[78–95]) and the number is not (24%, [14–36]). Displaying `primary_track` and
the narrative rather than a two-digit score shows the part of this output the
model can reproduce. The six `primary_track` disagreements are also worth
reading: `Core SWE ↔ Poor Fit` ×3, `AI Integration ↔ Bridge & Solutions` ×2,
`Bridge & Solutions ↔ Poor Fit` ×2 — the ones that cross into `Poor Fit` are a
posting leaving the list between one night and the next, and they are not the
adjacent-reading kind.

Two incidental findings from the same run:

- **The persona prefix really does cache.** `prompt_cache_hit_tokens` was
  48,256 of 57,149 on pass 1 (84%) and 54,400 of 57,149 on passes 2 and 3
  (95%) — the prefix warming as the run proceeds is itself the evidence.
  `docs/ingest/score.md` lists "persona-prefix caching… nothing verifies a
  hit" as an undocumented assumption. It is now verified for this endpoint.
- **2 of 55 responses came back as the empty string** — not an error, not
  unparseable JSON, just `""` with a 200. Silence is this system's failure
  mode; they tombstone correctly as `unparseable_json`.

### The corpus caveat

`corpus-v1.jsonl` is stratified by platform, but only 55 of 120 records have
facts, and the survivors skew to `google_jobs` (16) and `hn_whoishiring` (11)
with `lever` at 2. The per-platform cells in the harness output are too small
to decide anything — `fit_score` at `lever` reads 0% on n=2. Treat the overall
row as the measurement and the platform table as a hypothesis generator.

---

## 5. What is still missing, and it is not small

**~~`job_scores` has no version column at all.~~ FIXED 2026-07-29.** This
section is kept rather than deleted because its diagnosis was right and the
fix is shaped by it.

`job_scores` now carries four columns — `facts_version`, `persona_sha`,
`prompt_version` and `criteria_version` — and `select_shortlist`'s anti-join
is version-aware. Three of the four are cache keys; `criteria_version` is
recorded for provenance only, because `build_prompt` and `_facts_block` never
read `match_score` or `match_reasons`, so criteria changes *which* jobs are
asked about and never *what* is asked. `model_version` was not added: the
existing `scoring_model` already is it.

`persona_sha()` moved from `evals/tasks/score.py` into `score.py` beside
`build_prompt`, which defines its field set, and the harness re-exports it. It
was kept as a **digest rather than an invented `persona_version` integer**: an
explicit bump can be forgotten, and this repo has already caught the profile
authoring path writing wrong values silently (`fa2d7a7`).

**What the fix deliberately does NOT do is re-score anything.** The 1,293 rows
described below are all unversioned, and an unversioned row is a *third state*
— not stale, not fresh — reported in its own bucket and never selected
automatically. Nothing here spends an LLM call until an operator passes
`--rescore-stale` or `--rescore-unversioned` with an explicit `--limit`.
`score.py --stale-report` prices it first and needs no credential to run:
**1,018 calls, not 1,293**, because 275 rows are closed or never cleared
`MATCH_FLOOR` and no flag routed through the shortlist can reach them.

**`normalize()` was not validated against real *malformed* cached
responses**, as `04:119-120` asks. There were none: every entry in
`backend/evals/.cache` was an extract response, because no score run had ever
been made through the harness — `evals run` itself was broken (D44). This task
made the first ones: **53 real score responses are now cached** and were
replayed through `normalize()` for §2. All 53 are well-formed, so the
coercion paths themselves are exercised by synthesised inputs in
`backend/tests/test_score.py` plus the two shapes production actually produced
(`frontend_core`, and the fit-score-without-a-track row). The DoD bullet
overstated what existed; this is as close as it can be met without
manufacturing malformed answers, which would prove nothing about the model.

**Axis B (human labels) is empty and `job_events` has 0 rows.** Neither is a
blocker for anything above, and neither is waited on. Whether `fit_score` is
*good* stays open until `job_events` has data, which makes what the webapp's
event endpoint captures a prerequisite for ever answering it.

---

## 6. Definition of done

From `04-score-validation.md:192-201`:

| item | status |
|---|---|
| the two SQL checks are run and their answers recorded | **met** — §1 |
| `score.normalize()` exists, with its own vocabulary | **met** — §3 |
| …exercised against real malformed responses from the cache | **adapted** — §5; there were none, and there now are 53 real (well-formed) ones. Malformed shapes are synthesised from what production produced |
| `python3 -m evals run --task score` works against `corpus-v1.jsonl` | **met** — 53/55 usable, 2 tombstoned, 65 skipped. Required fixing D44 first |
| `profiles.validate()` requires `buckets` | **rejected, with reason** — §3. `pursuit` is active without it; the fix went into `build_prompt` |
| `score_one_job` cannot let one job's exception end the batch | **met** — `ERRORED`, covered by `test_run_for_profile_completes_despite_a_broken_persona` |
| `unittest discover` green | **met** — 782 tests, 0 failures |
| audit item 8 marked closed in `docs/ingest/score.md` | **adapted** — closed in `docs/ingest/DEFECTS.md` (D15) instead. `score.md` carries `script:`/`generated:` frontmatter and CLAUDE.md says regenerate, never hand-edit; it will regenerate correct from the new `score.py` |

From `08-score-validation.md:60-66`:

| item | status |
|---|---|
| diagnostic SQL run and committed, **before** task 12 | **met** — §1 |
| …and **after** task 12 | **outstanding** — task 12 has not run; command recorded in §1 |
| the `buckets` KeyError has a defect id | **already met** — D16, registered by task 02. No duplicate created |
| tie distribution reported before and after normalisation | **met** — §2, on real responses and on the stored column |

Explicitly **not** in scope, per the boundary at the top: any claim about
whether `fit_score` values are correct. This task ends at well-formed and
self-consistent.

# HANDOFF: extraction fields and match quality

**Written** 2026-07-26, at the end of the multi-user scoring rework.
**Task** improve how well `match.py` ranks, primarily by testing whether richer
`job_facts` fields close the gap.

Read `jobs/SCORING.md` first for how the pipeline works. This document is only
about the open quality question, what has already been ruled out, and the traps
that cost time getting here.

---

## 1. The state you are inheriting

The pipeline works end to end and is live (cron `43f2e0330e75`, `0 0 * * *`,
resumed). Nothing here is broken. The open question is quality, not
correctness.

| | value |
|---|---|
| `job_facts` rows | 4,977 (1 tombstoned) |
| `job_matches` rows | 3,214 `tech` + 298 `frontend` |
| LLM-labelled postings usable for evaluation | **917** |
| `FACTS_VERSION` | 1 |
| `criteria_version` for `tech` | 4 |

Current measured quality for profile `tech`:

```
spearman                  +0.619
recall fit>=80 in top150   0.440   [59/134]

TOP 20 QUALITY vs BASELINE
  rules (match_score)      mean fit  69.3    8/20 at fit>=80
  recency (old behaviour)  mean fit  35.2    1/20 at fit>=80
  random                   mean fit  47.6    5/20 at fit>=80
```

Reproduce with:

```bash
set -a && . ~/.hermes/.env && set +a
python3 jobs/tools/calibrate-match.py --profile tech --disagreements 10
```

**Write these numbers down before you change anything.** Several of them moved
during the last session for reasons that had nothing to do with ranking
quality — see §4.

---

## 2. What is already ruled out — do not redo

**Weight tuning is exhausted.** A sweep over the whole plausible space —
`base` 22–55, location penalty 0 to −55, tech cap 18–34, `MATCH_FLOOR` 0–40 —
moves recall only between **0.468 and 0.484**. `base` cannot affect rank
correlation at all (adding a constant does not reorder). If a weight change
appears to move Spearman a lot, you have hit trap §4.1, not a real effect.

**Reasoning tokens stay ON for extraction.** Measured: 4.9x cheaper and 3.9x
faster with them off, but against a 98.6% self-consistency floor they shift
`ai_involvement` and `remote_policy` by 17.5 points and `role_archetype` by 10.
Re-verify with `tools/compare-extract.py --arms off-off` (floor) then
`--arms on-off`, never one without the other.

**Hard excludes on unreliable fields are a mistake.** `role_archetype` agrees
with itself only 90% of the time, so a −100 turned 1-in-10 extraction slips
into deleted postings ("Java Full Stack with AI Integration" read as
`new_grad`, "Senior Software Engineer" read as `ml_research`). Hard excludes
are now only on `intern`/`director`/`exec` and `ml_research_required`. If you
add a field, do not give it a −100 until `compare-extract.py` shows it is
stable.

---

## 3. Start here: is it the features or the weights?

**Run this before spending a cent on new extraction fields.** It costs zero LLM
calls and it decides the whole direction of the work.

Fit a simple model — logistic regression or a small gradient-boosted tree — on
the **existing 17 fields**, with the 917 labelled postings as ground truth
(`fit_score >= 80` as the positive class). Then compare its precision@20
against the hand-tuned rules' 8/20.

- **Learned model does much better than 8/20** → the features are fine and
  hand-tuned weights are the bottleneck. Skip new extraction fields entirely
  and go straight to the learned ranker (roadmap step 3 in `SCORING.md`). This
  is the cheaper outcome.
- **Learned model is also ~8/20** → the 17 coarse fields genuinely cannot
  express what the LLM reads from prose. New fields are the right investment,
  and §5 is your list.

Dependencies are open for this — the repo is stdlib+psycopg by discipline, but
an experiment script under `jobs/tools/` that imports scikit-learn is fine and
does not commit the pipeline to anything. Keep it read-only.

Feature extraction for this is already done for you: `match.load_facts(conn)`
returns every posting as a dict with the facts plus `location_is_nyc` /
`location_is_remote`.

---

## 4. Measurement traps — all five of these bit during the last session

These cost more time than the actual engineering. Every one produced a
plausible-looking number that was wrong.

### 4.1 Do not compute metrics over a floor-filtered sample
`job_matches` only holds rows at or above `MATCH_FLOOR`. Joining it to
evaluate discards the low end, which is exactly where rules and LLM agree most
(both say "bad"). That reported **Spearman +0.326 for a ranking that actually
scores +0.619** — same function, different sample. `calibrate-match.py` now
scores from `job_facts` in-process for this reason. A storage policy must not
be able to move a quality metric.

### 4.2 "Top K" is not well defined on this data
`fit_score` is heavily tied — 59 postings share the value 85 — and a top-50
boundary falls inside that block, so ~24 of any "top 50" are an arbitrary draw.
Recall is now defined by threshold (`fit >= 80`). If you introduce a new
rank-based metric, check the tie structure first:
```sql
SELECT fit_score, count(*) FROM job_scores WHERE profile='tech'
  AND fit_score IS NOT NULL GROUP BY 1 ORDER BY 1 DESC LIMIT 12;
```

### 4.3 Recall@fixed-window is not comparable across corpus sizes
The identical ranking scored 0.476 over 806 ranked postings and 0.440 over
3,214, purely because the window is a narrower slice of a bigger pool. If the
corpus grows during your work, either scale the window or use precision@20,
which does not have this problem.

### 4.4 Pin temperature in any measurement tool
`cost-test.py` and `compare-extract.py` originally did not send `temperature`,
so they measured provider-default sampling while production pins it to 0. That
inflated the apparent disagreement floor from 98.6% to 93.9% and nearly
justified a wrong decision. Both are fixed; any new tool must send
`llm.DEFAULT_TEMPERATURE`.

### 4.5 Set quality bars relative to a baseline
`MIN_SPEARMAN = 0.6` / `MIN_RECALL = 0.8` in `calibrate-match.py` were invented
during design, before any measurement. Recall "fails" against a number that was
never grounded, while the same ranking is 8x better than the system it
replaced. **Use precision@20 against the recency baseline as your objective**,
not the PASS/FAIL line.

---

## 5. Candidate extraction fields, ranked

Only pursue these if §3 says features are the bottleneck. Ordered by expected
value, and every one is a hypothesis rather than a recommendation — the reason
to test is that the current schema has no way to express what the LLM keys on.

1. **`role_blend`** — does the posting combine production engineering with
   customer-facing or applied-AI work? `persona.json` calls `bridge_solutions`
   the strongest-fit bucket, and the current schema can only say
   `archetype=forward_deployed`, which is a title-shaped answer to a
   content-shaped question.
2. **`seniority_flexibility`** — does the posting state a range or say
   "or equivalent experience"? A 5-YOE candidate is viable for many "senior"
   postings, and `seniority_level` alone forces a binary the LLM does not make.
3. **`company_stage`** — startup / growth / enterprise. Plausibly drives the
   LLM's judgement and is entirely absent today.
4. **`requirements_strictness`** — are the listed years and degrees framed as
   hard requirements or preferences? Would let `advanced_degree_required` stop
   being a blunt boolean.
5. **`role_scope`** — IC breadth vs narrow specialisation.

Add fields to `extract.py`'s `_INSTRUCTIONS`, `REQUIRED_FIELDS` (only if
genuinely required), `normalize()`, `_FACT_COLUMNS`, and the `job_facts` DDL in
`schema.py`. **Bump `schema.FACTS_VERSION`** — that is what makes re-extraction
a resumable backlog burn-down rather than a TRUNCATE, and it gives tombstoned
rows one more attempt under the new prompt.

---

## 6. How to run a cheap experiment

**Do not re-extract all 4,977 postings to test a hypothesis.** Only the 917
labelled ones can be evaluated, so extract exactly those.

```sql
-- the evaluable set: has an LLM label AND has facts
SELECT s.job_id FROM job_scores s
JOIN job_facts f ON f.job_id = s.job_id
WHERE s.profile='tech' AND s.fit_score IS NOT NULL
  AND s.scoring_model NOT LIKE 'FAILED:%';
```

At the measured $0.000385/posting that is **~$0.35 per experiment round**, and
about 4 minutes at `EXTRACT_MAX_WORKERS=40`. A full corpus re-extraction is
~$1.90 and ~15 minutes — cheap enough to do once you have a winner, wasteful as
an inner loop.

Suggested loop:
1. Bump `FACTS_VERSION`, add the field.
2. Extract only the labelled subset (add a `--only-labelled` flag to
   `extract.py`, or a one-off script — do not hand-edit the main selector).
3. Add the field to `criteria.json` with a plausible weight.
4. `python3 jobs/migrate_profiles.py --apply --bump --profile tech`
5. `python3 jobs/match.py --profile tech`
6. `python3 jobs/tools/calibrate-match.py --profile tech` — read
   **precision@20**, not the PASS/FAIL.

Keep `MATCH_FLOOR` fixed while comparing rounds; changing it moves the stored
population and hence anything computed from `job_matches`.

---

## 7. Practical warnings

- **Pause cron before a long run.** It is live now and runs `0 0 * * *`.
  `hermes cron pause 43f2e0330e75`, and resume when done. Concurrent
  `extract.py` runs are safe (the anti-join prevents duplicate work) but they
  will compete for the same rate limit and confuse your timings.
- **`--bump` or your results are stale.** `match.py` keys its incremental
  rebuild on `criteria_version`. Editing `criteria.json` without bumping leaves
  `match_score`s computed under the old weights that look current.
  `migrate_profiles.py` warns about this; do not ignore it.
- **Two profiles exist.** `tech` (the real one, 917 labels) and `frontend` (a
  synthetic profile created to prove the flat-cost property — no labels, no
  evaluation value). Delete it if it is in your way; nothing depends on it.
- **Nothing is committed.** The working tree holds the entire rework. Commit or
  branch before experimenting so you can get back.
- **A DB backup exists** at `~/.hermes/backups/pre-googleid-20260725-235811.sql.gz`,
  taken before the Google id migration. Take a fresh one before any migration
  of your own.

---

## 8. Files that matter

| file | why |
|---|---|
| `jobs/SCORING.md` | how the pipeline works, all measured costs |
| `jobs/extract.py` | the extraction prompt and `normalize()` — where new fields go |
| `jobs/match.py` | `score_job()` is pure and unit-tested; the ranking function |
| `jobs/config/criteria.json` | weights, with calibration history in `_comment` keys |
| `jobs/tools/calibrate-match.py` | the quality gate, incl. the baseline block |
| `jobs/tools/compare-extract.py` | field-level agreement; always run `--arms off-off` first |
| `jobs/tools/cost-test.py` | `--stage extract` measures the extraction prompt |
| `jobs/tests/test_match.py` | 18 tests; keep them passing, they pin the hard-exclude short-circuit |

---

## 9. The one-paragraph version

The rules tier ranks 8x better than what it replaced but reaches only 40%
precision@20, and weight tuning is exhausted. Before adding extraction fields,
fit a learned model on the existing 17 features against the 917 labelled
postings: if it beats 8/20, the weights were the bottleneck and you should
build the learned ranker instead; if it does not, the features genuinely are
the ceiling and §5 is the list. Either way the objective is precision@20 versus
the recency baseline, not the invented 0.8 recall threshold — and read §4
before trusting any number you measure.

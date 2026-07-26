# HANDOFF: extraction fields and match quality

**Written** 2026-07-26, at the end of the multi-user scoring rework.
**Task** improve how well `match.py` ranks, primarily by testing whether richer
`job_facts` fields close the gap.

Read `SCORING.md` first for how the pipeline works. This document is only
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
recall fit>=80 in top150   0.433   [58/134]

TOP 20 QUALITY vs BASELINE
  rules (match_score)      mean fit  69.3    8.0/20 at fit>=80
  recency (newest first)   mean fit  48.9    5.0/20 at fit>=80
  random (mean of 500)     mean fit  46.6    3.0/20 at fit>=80
```

The two baseline rows read 1/20 and 5/20 in the first draft of this document.
Both were wrong — see §4.6. The rules tier beats the status quo 8 to 5, not
8 to 1.

Reproduce with:

```bash
set -a && . ./.env && set +a
python3 tools/calibrate-match.py --profile tech --disagreements 10
```

**Write these numbers down before you change anything.** Several of them moved
during the last session for reasons that had nothing to do with ranking
quality — see §4.

---

## 2. What is already ruled out — do not redo

**Hand-tuning weights is exhausted.** A sweep over the whole plausible space —
`base` 22–55, location penalty 0 to −55, tech cap 18–34, `MATCH_FLOOR` 0–40 —
moves recall only between **0.468 and 0.484**. `base` cannot affect rank
correlation at all (adding a constant does not reorder). If a weight change
appears to move Spearman a lot, you have hit trap §4.1, not a real effect.

  Do not extend this to "the features are at capacity", which is what the
  first draft of this document did. A sweep only explores the shapes
  `criteria.json` can express and cannot represent an interaction. §3 fits a
  model on the identical features and gets 12.7/20 against the rules' 8.0, so
  there is a great deal left in them — just not reachable by hand.

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

## 3. ANSWERED: it is the weights

This section used to say "run this before spending a cent on new extraction
fields". It has been run — `tools/learned-ranker-probe.py`, zero LLM
calls, about twenty minutes — and it came back on the cheaper side.

Fitting a model on **exactly the inputs `score_job()` reads**, cross-validated
against the same 917 labels:

| ranking | precision@20 | avg precision |
|---|---|---|
| rules (`match_score`), hand-tuned | 8.0 | 0.347 |
| **learned, identical features** | **12.7 ± 1.0** | **0.498 ± 0.015** |
| learned, + the unused `job_facts` columns | 11.6 ± 1.4 | 0.480 ± 0.025 |
| learned, + tf-idf over the full description | 14.7 ± 1.3 | 0.520 ± 0.031 |

Out-of-fold, 10× 5-fold, seed 11. Paired bootstrap of the difference against
the rules: **+0.167 average precision [+0.099, +0.240]**.

Reproduce with:

```bash
python3 -m venv /tmp/mlvenv
/tmp/mlvenv/bin/pip install scikit-learn 'psycopg[binary]'
set -a && . ./.env && set +a
/tmp/mlvenv/bin/python tools/learned-ranker-probe.py --profile tech
```

**What follows from it:**

- **The features were never the bottleneck.** The same 17 fields, weighted by
  fitting rather than by hand, close most of the gap. §5 is not the next move.
- **The unused `job_facts` columns are worthless here.** `employment_type`,
  `visa_sponsorship`, `comp_*`, `years_experience_max` are already extracted
  and free to adopt — and they make the model slightly *worse*.
  `visa_sponsorship` is 96% `unknown`, `comp_*` is 13% populated.
- **The prose adds little.** The text arm first scored 0.534 and its top
  positive terms were `18808` and `18808 ljbffr` — a republisher's footer on
  41 `google_jobs` postings that happen to be 34% `fit>=80` against a 13.9%
  base rate. It had learned which board scraped the page. Stripped, the arm
  falls to 0.520, within one standard deviation of structured-only. The probe
  now strips it; see `_BOILERPLATE` and read the term list before the number.
- **Why §2's sweep misled.** A weight sweep only explores the shapes
  `criteria.json` can express — a base, a per-level penalty, a capped additive
  boost. It cannot represent an interaction, so exhausting it says nothing
  about what the features contain. "Tuning is exhausted" and "the features are
  at capacity" are different claims and only the first was measured.

**Next move: build the learned ranker** (`SCORING.md` roadmap step 3), trained
on `fit_score` for cold start and swapped to `job_events` labels as they
accumulate.

---

## 4. Measurement traps — all seven of these bit on this codebase

These cost more time than the actual engineering. Every one produced a
plausible-looking number that was wrong. 4.1–4.5 were found during the scoring
rework; 4.6 and 4.7 were found afterwards, reading the tool that reports the
others.

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
never grounded, while the same ranking is a real improvement on the system it
replaced. **Use precision@20 against the recency baseline as your objective**,
not the PASS/FAIL line — but read §4.6 first, because the baseline itself was
wrong.

### 4.6 Check the direction of your baseline, and average it
The `recency` row in `calibrate-match.py` sorted `first_seen` **ascending**
until 2026-07-26, so what it called "the old behaviour" was the 20 **oldest**
postings in the corpus — an ordering no user was ever served. It scored 1/20
where true newest-first scores 5/20. The `random` row alongside it used a
single seed that drew 5/20 against a 500-seed mean of 3.1.

Together those two errors produced a conclusion that was stated as fact in
`SCORING.md`: that the rules tier was *8x* the status quo, and that recency was
*worse than random*. Neither is true. The honest figures are 8 / 5 / 3.1, and
newest-first is modestly better than random rather than worse. Both are fixed.

The general lesson: a baseline is the most load-bearing number in a quality
measurement, because every decision is a comparison against it — and it is
usually the number nobody checks, precisely because it is "just the thing we
already do". Sanity-check its direction, and average anything stochastic.
A single draw of 20 from a ~15% base rate has a standard deviation of ~1.5
hits, so one seed can land anywhere from 1 to 6 and any of those reads as fact.

### 4.7 Pin the row order, not just the seed
`load_pairs` and `load_facts` issue SELECTs with no `ORDER BY`, and a seeded
`random.sample` over an unordered list is not reproducible. Two runs of
`calibrate-match.py` against an *unchanged* database reported recall 0.440 and
0.433, and a random baseline of 3.1 and 2.9.

Those gaps are small enough to shrug at, which is exactly the problem: they are
the same size as the effects this tool exists to detect, so a real +0.007 and
a row-order shuffle are indistinguishable. Both tools now sort by `job_id`
before anything indexes into the list. If you add a third, sort it too — a
pinned seed over an unpinned sequence is not a pinned experiment.

---

## 5. Candidate extraction fields, ranked — SHELVED, §3 says do not

**§3 has been run and it says the features are not the bottleneck.** Do not
start here. This section is kept because the hypotheses may become worth
testing once the learned ranker has taken the weighting gain and the ceiling
moves again — and because the probe's `--terms` output is now real evidence
about which of them would pay, where the list below is five guesses.

The prose terms the text arm leans on, after boilerplate stripping, do line up
with hypotheses 1 and 5: `solutions`, `customer-facing`, `customers`,
`integrations`, `end-to-end`, `ship`, `agents`, `ai coding` on the positive
side; `senior`, `staff`, `mentor`, `lead`, `devops`, `infrastructure`,
`pipelines`, `ml` on the negative. Note how much of that the existing schema
*already* encodes — `customer_facing`, `role_archetype`, `seniority_level`,
`ai_involvement` — which is the same finding from the other direction: the
signal is present and the hand-tuned weights are not extracting it.

Ordered by expected value, and every one is a hypothesis rather than a
recommendation.

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
4. `python3 migrate_profiles.py --apply --bump --profile tech`
5. `python3 match.py --profile tech`
6. `python3 tools/calibrate-match.py --profile tech` — read
   **precision@20**, not the PASS/FAIL.

Keep `MATCH_FLOOR` fixed while comparing rounds; changing it moves the stored
population and hence anything computed from `job_matches`.

---

## 7. Practical warnings

- **Stop the timer before a long run.** The nightly run is live and fires at
  midnight local. `systemctl --user stop jobs-ingest.timer`, and `start` it
  again when done. (This was `hermes cron pause 43f2e0330e75` before slice D of
  the reorg moved the pipeline onto a systemd user timer.) In practice the
  `flock -n -E 0` in the unit already makes an overlap exit 0 rather than run
  twice, so this is about not confusing your own measurements. Concurrent
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
| `SCORING.md` | how the pipeline works, all measured costs |
| `extract.py` | the extraction prompt and `normalize()` — where new fields go |
| `match.py` | `score_job()` is pure and unit-tested; the ranking function |
| `config/criteria.json` | weights, with calibration history in `_comment` keys |
| `tools/calibrate-match.py` | the quality gate, incl. the baseline block |
| `tools/learned-ranker-probe.py` | §3's experiment; needs scikit-learn in a throwaway venv, read-only, zero LLM calls |
| `tools/compare-extract.py` | field-level agreement; always run `--arms off-off` first |
| `tools/cost-test.py` | `--stage extract` measures the extraction prompt |
| `tests/test_match.py` | 18 tests; keep them passing, they pin the hard-exclude short-circuit |

---

## 9. The one-paragraph version

The rules tier reaches 8/20 precision@20 against 5/20 for the recency it
replaced and 3.0/20 for random — a real gain, smaller than this document first
claimed. Hand-tuned weight *sweeping* is exhausted, but that turned out not to
mean what it looked like: a learned model on **exactly the same 17 fields**
reaches 12.7/20 and +0.167 average precision over the rules, paired CI
[+0.099, +0.240]. So the features were never the ceiling, the weighting
function was. Adding extraction fields (§5) is shelved; the next move is the
learned ranker in `SCORING.md` roadmap step 3, trained on `fit_score` for cold
start and on `job_events` as engagement accumulates. Measure it with average
precision and report precision@20 — p@20 is the objective but it is a count of
twenty things and cannot resolve the differences you will be deciding on. Read
§4 before trusting any number you measure; three of its six traps were found
after the conclusions they invalidated had already been written down as fact.

---
kind: contract
written: 2026-07-31
generator: none
---

# Measurement traps

**Promoted 2026-07-31 from `backend/docs/HANDOFF-match-quality.md` § 4**, which is
persona-bound findings about one software engineer's job search. These seven are not:
they are properties of measuring a ranking against a corpus, and they transfer to every
future user, vertical and model. `.claude/CLAUDE.md` has instructed every session to read
this file since before it existed — the instruction is now true.

**Three of the seven were found only *after* the conclusions they invalidated had been
written down as fact**, and one of those conclusions (*"the rules tier is 8x the status
quo, and recency is worse than random"*) was stated in `SCORING.md` and is false. That is
the reason this file is separate and the reason it is read first.

Section numbering is kept as `4.1`–`4.7` so that every existing citation still resolves.

**Later additions, from this run rather than from the original seven:**

- **Never evaluate on the layer you trained on.** L0 is human labels (never train on
  them), L1 is `fit_score`, L2 is `job_events`. `backend/tools/calibrate-match.py` takes
  its ground truth from `job_scores` — the LLM — so sweeping weights with it after a
  labelling session fits the model the labels exist to check.
- **Never select an eval corpus with `ORDER BY first_seen DESC`.** It is ~85%
  greenhouse/ashby — clean ATS postings — so it measures the easy sources and reports a
  reassuring number. Use the frozen fixtures in `backend/evals/fixtures/`.
- **Report average precision as the measurement and precision@20 as the objective.** A
  count of twenty cannot resolve the differences being decided on.
- **Quote the population with the rate, always.** `other` at 8.0% and at 31.3% differ by
  vocabulary *and* by corpus; the pair cannot be read as one change.
- **A caveat that names its own instrument is worth more than one that hedges.** The n=4
  labelling-rate reading said "re-check this as the count grows"; the re-check at n=29
  overturned it and halved the budget. A caveat with a command attached gets run.

**Promoted 2026-08-01 from `docs/tasks/refactor/HANDOFF.md` § *Nothing is in flight*** by
task 44, under `DOCS-POLICY.md` rule 5 — both would still be true for a different cohort,
model or product. The dated narrative they were extracted from is at
[`archive/handoff-tree-state.md`](archive/handoff-tree-state.md).

- **File ownership does not isolate database state — take the baseline, then attribute every
  delta.** Three instances here, and none of them was a mistake anyone made. Agents running
  on strictly *disjoint files* still interact, because the database is shared: task 35's
  remediation deleted rows from the corpus task 13 was scoring, so 13's frozen eval fixture
  had to be re-pinned 863 → 859 and another profile's `job_matches` digest changed for a
  reason that had nothing to do with 13. Then a count moved mid-session with two agents on
  disjoint files and **neither did it** — the nightly `run-daily.py` timer fired at 04:08 and
  closed a posting. **The other agent in the room is the cron job.** All three were isolated
  only because a snapshot was taken first. And take a **content digest** — `md5` over
  `string_agg` of the columns at issue, in a pinned row order — not a row count: a count
  cannot see an overwrite, and *"the counts match"* is exactly the reassuring sentence a
  silent re-score would produce.
- **A pin on set membership buys nothing about the derived facts.** An eval set pinned by
  sorted `job_id` cannot drift and its `sha256` proves it — **but the facts underneath its
  rows can, and did.** One posting acquired a `role_track` overnight, taking the set's NULL
  rate 27.7% → 28.5% inside a single working session, after the first figure had already been
  handed to a writer. The two earlier instances above moved *counts of rows*; this one moved
  a *rate about a frozen sample*, which is the version that looks safe to quote. **Any figure
  computed from a derived table about a pinned set carries the date it was taken, and one
  quoted without a date is unverified.** Second-order: the superseded rate and an unrelated
  document's rate rounded to the same 27.7% from different denominators — which is precisely
  the shape in which one measurement gets quoted as corroborating another. If you meet a bare
  rate, establish its population first.

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

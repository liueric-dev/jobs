# Decisions taken while running `docs/tasks/refactor/`

Hand-written, not generated — there is no `script:` frontmatter here and this file is
never regenerated. It is appended to as tasks land, one entry per decision that a
reader of the diff would otherwise have to reverse-engineer.

**What counts as an entry.** A choice the task file left open, a place where the task
file was wrong about the code, or a deviation from what it asked for. Not routine
implementation detail — the commit shows that.

**Format.** Claim, the alternative rejected, one line of why, and whether it is
reversible. The reversibility field is there so this can be skimmed for the entries
that actually constrain later work.

Run started 2026-07-28, from `36d83f5`, on branch `webapp-service`. Tasks 01 and 02
were already committed (`28f1d0e`, `36d83f5`).

---

### 00 — Scope of this run, and where it stops

Tasks 03–34 attempted in dependency order. Two classes of wall are expected and are
routed around rather than stopped at: credentials that require registering an account
(15 USAJobs/Adzuna, 20 Firecrawl, 24 Builder keys, 33 Cloudflare, 14's Socrata token),
and human judgement that cannot be substituted (07's golden set, 29's labelling
session, and 30 behind them).

The human wall is load-bearing rather than procedural: Axis B *is* Builder preference,
so a model standing in for it makes the measurement circular — the defect
`docs/ingestion_tests/03-metrics-and-golden-set.md:13` names in `claude-bench.py:417`,
which treats `sonnet-batch-1` as ground truth. Reversible only in the sense that the
labels can be collected later.

### 05 — The rate came from `posted_at_ts`, not `first_seen`

The task specifies grouping by `first_seen::date` over 30 days. That cannot work here:
the database was re-seeded on 2026-07-24, so `first_seen` spans five days and 11,000 of
11,824 rows carry the same date. Following the task literally would have returned a
four-day window and a meaningless mean. Used `posted_at_ts` (populated on
2,974/2,975 of the matching set). Rejected: waiting for 30 days of organic history.
Reversible — re-run against `first_seen` once the table has the history, and expect a
different, better number.

### 05 — Tier computed by importing `relevance.tier_sql()`

There is no `relevance_tier` column on `jobs`; tier is derived per query. Imported
`backend/relevance.py:112`'s `tier_sql()` rather than hand-writing the predicate in the
measurement, per CLAUDE.md's "one implementation, two callers". Rejected: a standalone
SQL transcription, which would have been a second definition of the gate and would
drift from it silently. Not reversible in any meaningful sense — it is the correct
dependency direction.

### 05 — Hand-check sample pinned by `md5(id)`

Drew the n=30 false-positive sample with `ORDER BY md5(id) LIMIT 30` and recorded the
ids. Rejected: `ORDER BY first_seen DESC` (forbidden by CLAUDE.md's measurement
discipline — it selects the easy sources) and unpinned `random()` (not reproducible).
The set is L0: never train on it, never recycle it. Reversible only by drawing a new
sample under a new name.

### 05 — Precision reported strictly at 6.7%, with the generous reading beside it

Two of thirty postings genuinely describe AI work reachable by an entry-level Builder.
A third — an OpenAI B2B marketing leadership hire that mentions "AI-powered workflows"
— was counted as junk, since the role is neither entry-level nor AI work. Counting it
gives 10%. Reported the strict figure as the headline with the generous one stated, so
the later comparison in task 10 has a fixed definition rather than a flattering one.
Reversible: the ids are pinned, so anyone can re-judge them.

### 05 — The task file's premise does not hold, and this changes tasks 04 and 10

`05-widened-gate-volume.md:13-20` says `title_include` is twelve software-engineering
terms and that AI-titled roles "all fall to tier 3 … never scored, never extracted,
never seen." That describes an earlier config. `backend/config/relevance.json:12-47`
now has **34** terms including `\yai\y`, `\yllm\y`, `\yml\y` and `machine learning`, so
any title with a standalone "AI" token already reaches tier 1 or 2. Measured: of 43
titles carrying both entry-level and AI signals, **34 are already admitted and 9 sit at
tier 3**.

Consequence, recorded here because two later tasks are scoped on the false premise:
the target population is not waiting untouched behind the gate — there is almost none
of it in the corpus at all. **The bottleneck is sourcing, not gating.** Task 04's
projection must not assume a widened gate unlocks a hidden corpus, and task 10 should
expect to recover ~9 on-target postings while admitting ~2,975 that are 93%
boilerplate. Not reversible — it is a fact about the config, not a choice.

### 00 — A real cycle in the task graph

`24-revive-contributor-api.md:3` depends on 33 for the tunnel; `33-deployment.md:3`
depends on 24 and 32. Circular as written. Recorded here rather than silently
resolved: 33 has to split, with the tunnel standing up before 24 and the
pipeline/app split landing after 32. Both halves sit behind a Cloudflare account
regardless, so the cycle is not on the critical path of this run. Reversible.

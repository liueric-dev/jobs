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

### 04 — `max_tier_to_score` stays at 2, and throughput was never the objection

The old `_max_tier_note` said "set to 3 to open the floodgates once throughput allows."
Throughput now allows — 4.8 hours and $1.73 for the one-time backfill, 0.1% of the
provider's concurrency ceiling — and it is still the wrong move. Three findings, in
increasing order of decisiveness:

1. **Quality.** The tier-3 AI-vocabulary population is 93% junk (task 05), and widening
   buys 9 on-target postings for 6,183 rows of noise.
2. **Throughput does not actually allow it either, for a different reason.**
   `EXTRACT_BATCH_SIZE=40` against one nightly `extract.py` invocation already binds at
   tier 1+2 — 66 eligible/day into a 40/day pipe. Tier 3 makes it 152/day into the same
   pipe. The effect is not "more postings get looked at" but "the backlog never closes
   and `ORDER BY first_seen DESC` decides which ones do."
3. **Decisive: `max_tier_to_score = 3` is an unconditional pass, not a wider gate.**
   `relevance.py:189` builds `CASE WHEN row_ok AND loc_ok THEN 1 WHEN row_ok THEN 2
   ELSE 3 END`, and `:223` admits on `tier <= max_tier`. Every row is `<= 3`. Since
   `row_ok` folds in `title_include`, `title_exclude`, `company_exclude` and
   `description_exclude`, the one-character change silently disables **four** exclusion
   lists at once: 1,906 rows return on `title_exclude` alone (account executive,
   recruiter, nurse, controller, VP), plus 182 unique relist-spam rows. And they return
   **at the top** — 19 of them already reach `match_score >= 90`, one hits 99 against an
   LLM fit of 15, because keyword-stuffed titles are exactly what `title_include`
   rewards.

Rejected, both measured before rejecting: relying on `MATCH_FLOOR` to suppress the junk
(the relist rows score *highest*, so the floor filters the wrong end), and subdividing
tier 2 as the task file suggested (tier 2 is already fully extracted — 2,313 of 2,313 —
so it solves nothing). Reversible, and task 10 is what would change it: making the
provenance exclusions a separate predicate that no tier number can switch off.

### 04 — Latency measured at the pipeline's own concurrency, not at `workers=1`

7.7s p50 / 13.1s p95 per call, 2.85s/call effective at `EXTRACT_MAX_WORKERS=3`. The
previous tool defaulted to one worker; latency at one worker is not latency the
pipeline ever experiences, so it could not be compared against the nightly window.
Rejected: reporting both, which invites quoting the wrong one. Reversible.

### 04 — The old `cost-test.py` bypassed the rate limiter, and now does not

It built its own HTTP request rather than going through `llm.call_detailed()`, so
`ratelimit.acquire()` never applied to it. A measurement tool that does not obey the
pipeline's own throttle is measuring a different system. Now routed through
`call_detailed()`. Not reversible in intent — it was a defect.

### 04 — The throttle probe was dropped, on instruction

The task asks for a requests/minute ceiling "observed, by pushing until throttled."
Not done: the limit is a known 2,500-concurrent ceiling, and probing it would risk the
nightly window for a number already in hand. Recorded in `SCORING.md` as
**operator-stated, not measured**, with its date, so a later reader knows its
provenance. Reversible — measure it properly if the provider ever becomes the binding
constraint, which today it is not by three orders of magnitude.

### 03 — `upsert_checked` went into `lib/upsert.py`, not the `ingest/_common.py` fallback

The task file offers `backend/ingest/_common.py` as a fallback "if `lib/` must stay
byte-identical" to another repo, and CLAUDE.md states that constraint as live with
drift reported by `tools/lib-parity.sh`. **That script does not exist anywhere in the
repo**, and `backend/lib/__init__.py` plus `backend/tests/test_lib_contract.py:5`
both record that `lib/` "used to be a shared package and is now this repo's own code."
The constraint is dead. Put the helper beside `upsert` where it belongs. Rejected: the
fallback location, which two of the eight call sites (`api/app.py`, `api/query_claims.py`)
could not have imported from cleanly anyway. Reversible, but there is no longer a
reason to. **CLAUDE.md's `lib/` parity rule is stale and should be corrected in task 34.**

### 03 — `UpsertResult.__iter__` left exactly as it was

The task said not to change it and that is right: the three-tuple unpack is the
documented shape, and rewriting it would move the surprise rather than remove it. The
fix is a wrapper that cannot be called without logging the error count, so the correct
call is also the shorter one. Not reversible in intent — it is the design.

### 03 — The failure rate is checked at two scopes, not one

Scripts that upsert inside a per-source loop (`ats.py`, both Google scripts) apply the
threshold twice: per batch, where one bad source is survivable and is recorded the way
an unreachable source already was, and again over the accumulated total at the end of
the run, where it is not. Hence `check_error_rate()` exists separately from
`upsert_checked()`, and `UpsertErrorRate` carries `.result` — `upsert()` commits before
raising, so the records that succeeded *are* written and a caller that catches it can
still count them. Single-batch scripts (`hn-hiring`, `builtin-nyc`, `weworkremotely`)
need only the one scope. Reversible.

### 03 — The 5% threshold is a guess, and is labelled as one

`DEFAULT_THRESHOLD = 0.05` per the task file. There has never been a run with the error
count recorded, so there is no distribution to choose from — the constant says so in
its own comment rather than presenting itself as calibrated. Reversible, and should be
revisited once real error counts exist.

### 03 — The contributor API's `accepted` now means "written", and a `dropped` field appears

`POST /submit` previously returned `accepted: len(records)` — the count that *normalized*
cleanly, which said nothing about whether they reached the table. It now returns the
count actually written, adds `dropped`, and populates `submission_log.reason`. Not
literally required by the task, which only demanded the error count stop being
discarded; kept because the alternative preserves the exact defect at the API boundary,
and a contributor whose rows vanished has no other channel to learn it. The two values
differ **only when records were dropped** — that is, only in the case where the old
answer was wrong. `docs/tasks/refactor/API-CONTRACT-v1.md` freezes the frontend read
endpoints and does not cover this one, so no frozen contract is broken.

**Reversible in code, but it is a deployed surface** — a client that treats `accepted`
as "how many I sent that parsed" would now see a smaller number on a partial failure,
which is the intended correction. Flagged rather than buried because it is the one
change in task 03 that is visible outside the repo.

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

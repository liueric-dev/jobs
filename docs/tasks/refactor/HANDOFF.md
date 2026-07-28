# Handoff — the `docs/tasks/refactor/` run

Written 2026-07-28, and rolling — last updated after 08, 12 and 19 landed
(`e1cdf7b`, `c4a8ff5`, `2b4dba2`, `2fecec5`, `05b7fa2`, `b86df11`). Read this first, then
[`DECISIONS.md`](DECISIONS.md) (why each choice was made) and
[`CLAUDE_UPDATES.md`](CLAUDE_UPDATES.md) (what happened, per task).
[`README.md`](README.md)'s status column is the ordered index.

## READ THIS FIRST: the cost lever that was hiding in the profiles table

**The corpus was never the problem. The active profile set was.**
`extract._eligible_sql` (`extract.py:397`) gates the extraction queue on
`relevance.union_sql(ACTIVE profiles)`. Both of the repo owner's original
software-engineer job-search profiles — `tech` and `frontend` — were still
`active=True`, so every `FACTS_VERSION` bump was re-extracting *their* corpus.

| active set | eligible at a bump | calls | wall clock |
|---|---|---|---|
| `tech` + `frontend` | 5,317 | 5,659 | ~4.5h, ~5 nights |
| `pursuit` only | **863** | 863 | **28m31s measured** |

Task 12 flipped it (`profiles.set_active`). **Reversible and destructive of
nothing** — `prune_orphans` runs inside the loop over *active* profiles
(`match.py:457`), so `tech`'s 3,085 matches and 1,111 scores are untouched and
flipping back resumes them. If the owner ever wants their own job search served
again, that is the switch; it costs the 5,317-row bill each bump.

**Operating stance set by the repo owner on 2026-07-28: database contents are
STAGING DATA. Optimize for build speed and cost, not preservation.** That is why
task 12 used a throwaway `job_facts_v2_snapshot` instead of building
`--dry-run --limit` into `extract.py`, and why its Axis A gate was waived rather
than waited on. Do not build preservation machinery without checking that this
still holds.

## State at handoff

**Branch `webapp-service`, suite green at 782 tests** (task files say 263, the
previous handoff 717; 782 is the floor now). The last code commit is `b86df11`.
**The whole suite passes** — `python3 -m unittest discover -s backend/tests` from
the repo root. Working tree is clean apart from untracked `scripts/`, which
predates this run and is not ours.

`backend/webapp/tests/` is a separate matter: **`fastapi` is not installed here**, so five
modules fail to import and always have. Not a regression, and not covered by the count
above.

Thirteen tasks committed, one experiment, plus the two conversational decisions:

| | task | commit |
|---|---|---|
| 03 | stop discarding upsert errors | `e353e3e` |
| 04 | quota and wall-clock baseline | `c3275be` |
| 05 | corpus volume under a widened gate | `e4bddd3` |
| 06 | self-consistency at n=120 | `5092568` |
| 09 | fetcher harness | `68f026f` |
| 16 | ATS token discovery | `49d51bf` |
| 22 | JobSpy spike | `66c9d18` |
| — | Google Jobs query-bank experiment | `eee979d` |
| — | **the two extraction decisions** | `943d899` |
| 10 | description-first cohort gate | `7d94bb1` |
| 07 | golden-set tooling (no labels) | `3a8b42c` |
| 14 | NYC Open Data ingest | `7221620` |
| 17 | retarget `ats.py`, 3 new platforms | `597662b` |
| 18 | Workday CXS, gated upstream | `fabe381` |
| 11 | archetype superset, `role_track`, missingness | `da4942c` |
| 08 | score validation, `score.normalize()`, D15/D16/D43/D44 | `e1cdf7b` |
| 12 | `FACTS_VERSION` 3, extraction gate retargeted to `pursuit` | `c4a8ff5`, `2b4dba2` |
| 19 | JSON-LD coverage spike — **dropped on the evidence** | `2fecec5` |
| — | `workday-cxs` cassette (a pending follow-up, now closed) | `05b7fa2` |
| — | **D45** — the `company_ats` write-back is partial | `b86df11` |

01 and 02 were already committed before this run (`28f1d0e`, `36d83f5`).

## What 08, 12 and 19 changed about the plan

**1. The number the product should display is settled (task 08).** Three repeats
over 55 records: `primary_track` reproduces at **89%** [78–95], `fit_score` at
**24%** [14–36] with a maximum self-disagreement of 33 points, and `fit_score` as
an *ordering* at **ρ 0.915, 83% top-20 overlap**. The bucket is stable, the
two-digit number is not, the ordering is fine. **That is task 30's evidence, and
it is now measured rather than argued.** Artifact:
`docs/ingestion_tests/score-selfcheck-n120-2026-07-28.json`.

**2. Widening the archetype vocabulary made `other` WORSE, not better (task 12).**
This is the session's headline and it is a negative result. Task 11 went from 12
values to 26 specifically to shrink `other`. After re-extraction `other` is
**31.1% of the cohort corpus**, against 8.0% before. The split says why:

| slice | n | at `other` |
|---|---:|---:|
| re-extracted, already had v2 facts | 284 | **4.6%** |
| first-time extractions | 579 | **44.0%** |

The vocabulary fits the corpus it was derived from and fails on the part of the
cohort corpus nobody had looked at. **Task 13 should know this before pricing 26
archetypes**: a weight on a value that 44% of new postings do not match is a
weight doing nothing.

**3. Two things task 12 did NOT establish**, recorded so they are not
misremembered as settled:
- **The majority-of-3 vote has still never fired.** `hn_whoishiring` is the only
  platform under the 0.90 threshold and contributes **0** of the 863, so
  `extraction_passes = 1` and `vote_unanimity IS NULL` on all 5,907 rows. The
  debt is paid on paper; the mechanism is unexercised.
- **Task 11's 203/54 `other` prediction is UNTESTED, not falsified.** Only 25 of
  those 427 rows survive the pursuit union. Testing it means reactivating `tech`
  — the ~5,000-row re-extraction the profile switch avoided.

**4. `ai_operations` re-checked, and the employer spread is the finding.** The
standing caution said 5 postings across 3 employers. It is now **17 across 14,
maximum 2 at any one** — 0.82 employers/posting, ahead of `admin_ops` (0.79) and
`marketing_ops` (0.56), the two the derivation doc held up as better-distributed
when it called `ai_operations` "the weakest of the 14 by some margin." **That
specific concern is retired.** Read the direction carefully though: 5 → 17 is an
overshoot against a *title probe*, which confirms nothing on its own. And it is
**still 2.0% of the corpus**. Worth knowing: 11 of those 14 employers are tech
companies (Brex, Harvey, Coinbase, Databricks, Figma, Samsara, Vanta, …), so the
value is being found where the pipeline was already strong, not in the
all-industries NYC market the retarget is aimed at.

**5. `support_ops` is where the ops mass actually is** — 82 rows, 60% of the ops
137, nearly 5x `ai_operations`. The ops five came in **42 under** their
title-probe floor, which *is* falsifiable (the extractor read whole postings and
still applied them to fewer). The cohort's ops work is support-shaped, not
AI-shaped.

**6. Task 19 is dropped, and the population it was scoped against was wrong
(D45).** 2 of 55 employers publish parseable `JobPosting` — and only **1 of the
35 in the target population**, Moody's, which publishes no `validThrough`, the
one field that makes re-crawl affordable. The other hit, Etsy, came from the
control set and is a well-resourced tech employer on a bespoke careers site, not
the Taleo/ADP long tail the task describes. **The fourth Phase 3 estimate checked,
the fourth an order of magnitude high.**

## The two decisions the repo owner made in conversation — LANDED

They existed nowhere but this file, and the two agents mid-flight on them at the previous
handoff left **nothing in the tree**. Both were re-run from scratch and are now committed
in `943d899`. Kept here because they are the *why*, and the commit is only the *what*.

**1. Selective majority-of-3, keyed on measured per-source agreement.** Task 06's gate
fired its stop branch — `ai_involvement` self-agrees only 77.8% on `hn_whoishiring`
against 92.2% on greenhouse/ashby, and it is the cohort's entire targeting mechanism.
Sources measured below a threshold get three extraction passes and a majority vote;
sources above it stay at one. This satisfies both fired gate branches with one mechanism.
Rejected: uniform majority-of-3, a confidence field alone, and proceeding as-is.

**As built:** threshold 0.90 (task 06's own gate line), so exactly one platform qualifies
— **+4.2% of calls, not 3x**. `config/extraction-policy.json`, `extract.vote_facts()`,
and `job_facts.extraction_passes` / `.vote_unanimity` as the stability signal task 11
consumes.

**2. The 40/day extraction ceiling: drain loop with a wall-clock guard, AND fix the
selection order.** Both, not either. `EXTRACT_BATCH_SIZE = 40` against one `extract.py`
invocation in `run-daily.py` capped the pipeline at 40 postings a night against 43/day
intake and 80/day recently. Selection was `ORDER BY first_seen DESC`, which CLAUDE.md
forbids for eval corpora and which was making the same biased selection in production.

**As built:** `drain_loop()` with `EXTRACT_DEADLINE_SECS=3600`, a **zero-progress break**
(without it a rate-limited endpoint re-selects the same batch until the deadline —
strictly worse than one batch), `stopped=drained|deadline|no-progress` in the summary
line, and never-extracted-first-then-FIFO selection.

**`FACTS_VERSION` was deliberately NOT bumped. Task 12 must carry it.** The debt is
recorded at `schema.py:158`.

## Nothing is in flight

**The tree is clean.** Every agent across all three sessions completed, was verified
against the code and the database, and was committed — six in the session that landed
03–18, three in the session that landed 11, three in the session that landed 08/12/19.
Nothing is half-written and nothing is waiting on a reply.

`run-daily.py`'s `STEPS` is fully wired — `ingest/workday.py` and `ingest/nyc-open-data.py`
were added by the orchestrator, and `ats.py` was already there. **Tasks 08, 12 and 19
touched no ingest path and no scheduled step**, so the nightly run is unchanged in shape.
What changed underneath it: the nightly `extract.py` step now serves one profile instead of
two and has a much smaller queue, and `score.py` writes nothing at all because `pursuit`'s
`daily_narrative_budget` is 0.

**Start here:** `python3 -m unittest discover -s backend/tests` from the repo root should
report **782, OK**. `backend/.env` is not exported by default — scripts that reach the
database need `cd backend && (set -a; . ./.env; set +a; python3 ...)`.

**Live state after this session**, so a fresh session can tell drift from damage:
```
job_facts  5,907 = 863 @v3 (the pursuit corpus) + 5,029 @v2 + 15 @v1
           the 5,044 below v3 are 85 on closed jobs and 4,959 open-but-not-pursuit-relevant
           extraction_passes = 1 and vote_unanimity IS NULL on every row
job_matches 4,241 = pursuit 863 @(3,1) + tech 3,085 @(2,5) + frontend 293 @(2,1)
job_scores  1,294 = tech 1,111 + frontend 183; pursuit has none and will not until 13
profiles    pursuit active; tech and frontend inactive but intact
```

## How this run works

**One fresh subagent per task; the orchestrator verifies and commits.** Nothing is
committed by a subagent. The orchestrator checks each Definition of done against the
files, writes the decision-log entries, and commits with the task number.

**Verify, do not trust the report.** This mattered repeatedly:

- Task 16 reported itself finished while its report contained a literal
  `## RESULTS_PLACEHOLDER` and `company_ats` held **zero rows**. Caught by querying the
  database rather than reading the summary. It took two more passes to finish.
- Several agents complete their work and go idle **without sending a report at all**.
  Verify the artifacts directly; do not wait for a summary that may never arrive. **Task
  11 confirmed this at 3 of 3** — every agent went idle silently and every one had done
  the work. Treat the idle notification as "go look", not as a failure.
- Task 11's corpus agent shipped a document claiming "every number below is printed by
  the tool". Four of its headline figures were printed nowhere and no flag produced them.
  The analysis was sound; the reproducibility claim was not. **Re-run the tool and grep
  its output for the numbers the prose asserts.**
- Test counts drift while other agents work concurrently, so a count quoted by one agent
  may include another's in-flight tests.

**Give each subagent an explicit do-not-touch file list.** Parallel agents collide
otherwise. Three ran concurrently for most of the first session on that basis, and task
11's three had zero collisions across six files.

**When a number disagrees, make the tool print both rather than picking one.** Task 11's
doc said the ops archetypes reclaim 54 rows; the orchestrator's independent recount said
55. Neither was wrong — 54 is the five recommended values, 55 is all seven proposed. The
fix was to print both rows, labelled, so the ambiguity cannot recur. Silently adopting
either number would have buried a real distinction.

**Send an agent back to its own file; do not fix it yourself.** The ownership boundary is
what makes parallelism safe, and it does not lapse because the agent went idle. Task 11's
corpus agent fixed its own tool and doc on a second pass.

**Hand a downstream agent its inputs inline.** Task 11's extraction agent needed the
vocabulary its sibling had just derived, while that sibling was still editing the file it
lived in. Pasting the values into the prompt removed the race entirely.

## What is blocked, and on what

**Human judgement — cannot be substituted.** Task **07**'s golden set needs human labels:
`docs/ingestion_tests/03-metrics-and-golden-set.md:25` requires the human self-agreement
ceiling ("5-10 jobs labelled twice, a week apart") and tranche two's 07 adds
inter-annotator agreement, needing two people. Axis B *is* Builder preference — a model
standing in for it makes the measurement circular, the exact defect `03:13` names in
`claude-bench.py:417`, which treats `sonnet-batch-1` as ground truth. **07's tooling is
now built (`3a8b42c`) and produced zero labels, by design and by test.** The form is
server-rendered HTML at `/v1/label` behind the existing Google SSO; what is missing is
people. Task **29** is the labelling session itself and stops entirely. **30** sits behind it. **12** needs Axis A figures. **13** additionally
needs product judgement — the 20 plausible Pursuit target roles and the weights are
cohort calls, not implementation.

**Credentials needing an account:** **15** (USAJobs key, Adzuna `app_id`/`app_key`),
**20** (Firecrawl), **24** (Builder key onboarding), **33** (Cloudflare domain), and
**14**'s optional Socrata token — 14 can run anonymously and throttled meanwhile.

**A real cycle:** 24 depends on 33 for the tunnel; 33 depends on 24 and 32. 33 has to
split — tunnel before 24, pipeline/app split after 32.

## Findings later tasks must not inherit

Each of these is a documented claim that is **wrong about the code as it now stands**.

- **CLAUDE.md's `lib/` parity rule is stale.** It states `lib/` is vendored
  byte-identical with drift reported by `tools/lib-parity.sh`. That script does not
  exist, and `lib/__init__.py` and `tests/test_lib_contract.py:5` both record that `lib/`
  is now this repo's own code. It misdirected task 03. **Not corrected — it is the
  owner's instruction file. Propose the diff in task 34; do not edit it unasked.**
- **Task 05's AI regex is incomplete.** No bare `\yai\y`, no `ai-driven`, no `ai-enabled`
  — drops 3 of 9 genuine rows. Its own document invites task 10 to lift it verbatim.
  Do not. The entry-level regex also lacks `\yintern\y`.
- **`max_tier_to_score = 3` is an unconditional pass, not a wider gate.**
  `relevance.py:189` sends everything failing `row_ok` to tier 3 and `:223` admits on
  `tier <= max_tier`. It would disable `title_include`, `title_exclude`,
  `company_exclude` and `description_exclude` at once. `relevance.json`'s
  `_max_tier_note` makes widening conditional on task 10 delivering a separate
  provenance predicate.
- **`google_jobs.py:98-99` discards `detected_extensions.work_from_home`** — verified,
  the field is read into a local and referenced nowhere. All genuinely remote Google Jobs
  postings carry both location flags FALSE and sit at tier 2.
- **The SerpApi ledger undercounts real spend 3.3x.** `google_jobs_query_stats` read 41
  searches this month; the account read 137. **97 left of 250, not 209.** Task 23's
  descope keeps the quota ledger — it must reconcile against the vendor's counter.
- **Task 16's `not_found` does not mean "no ATS".** Its positive control found **zero of
  four** known-good tokens because those boards render client-side. All its coverage
  figures are floors; `company_ats.validation_note` says so per row.
- **The platform value is `builtin`**, not `builtin-nyc` as task files write it.
- **Task 11 section 3 describes a bug that was not in the code.** It says a NULL
  `role_archetype` "reads as a perfect archetype match" and a NULL
  `advanced_degree_required` "is indistinguishable from `false`". **Neither field was ever
  NULL** — `normalize()` substituted `"other"` / `"none"` / `"unknown"` / `false`, so 0 of
  5,321 non-tombstoned rows carried a NULL in any of them. The bias was real and one layer
  up. Fixed in `da4942c` at both layers; the task file now carries a correction block.
- **`other` was mostly a TECH vocabulary gap, not an ops one.** Task 11 section 1 opens
  with "an AI operations role at an insurance company". Of 427 `other` rows the seven
  proposed ops candidates reclaim **54**; nine tech values the original twelve simply
  lacked reclaim **203**. Anyone reading section 1 for proportion will get it backwards.
- ~~**`ai_operations` has 5 postings across 3 employers in this corpus.**~~
  **SUPERSEDED by task 12 (`c4a8ff5`, `2b4dba2`).** The re-check the caution asked for has
  been done. It is **17 postings across 14 employers, max 2 at any one** — 0.82
  employers/posting, ahead of `admin_ops` (0.79) and `marketing_ops` (0.56), so the
  weakest-on-spread concern is retired. But it is **still 2.0% of the cohort corpus**, 11
  of the 14 employers are tech companies, and 5 → 17 is an overshoot against a *title
  probe*, which confirms nothing on its own. The conclusion the caution was recorded
  against is unchanged: **these employers are largely not posting these roles.**
- **The task files were written from the plan, not from the code.** Six are now confirmed
  wrong about what they describe: 05's premise, 10's instruction to lift a regex verbatim,
  17's "current coverage is Greenhouse and Lever" (Ashby already existed), the `generated:`
  frontmatter claim, 14's 20–60/day estimate against a measured 1.8, and **11's section 3,
  which describes a NULL-handling bug in code that never produced a NULL**. **Read the code
  before trusting a task file's account of it**, and expect the Definition-of-done counts
  to be off.
- **`fastapi` is not installed in this environment**, so `backend/webapp/tests/` cannot
  run at all — five modules fail to import, four of which predate this run. It is not a
  regression and not task 07's doing. `backend/tests/` is the suite that gates work here;
  anything under `webapp/` is unverified by CI as things stand.
- **`docs/ingest/*.md` claim `generated:` frontmatter but no generator exists.** Task 34
  must decide: write generators, or drop the claim.

## Recommended next steps

**Task 13 is now the whole critical path, and its urgency changed character on
2026-07-28: `pursuit` is the ONLY active profile and it ships placeholder
criteria.** Ranking is live and meaningless until 13 lands. That is a different
situation from the previous handoff, where 13 was blocking work that had not
started.

1. **Task 13 — the cohort criteria profile.** `pursuit` is `active=True` as of
   `c4a8ff5`, matching 863 postings, with `criteria.archetypes = {}` and a
   persona whose `background_summary` literally begins `PLACEHOLDER`. Every
   archetype therefore prices through `match.py:191`'s `archetype:{v}:unpriced`
   path at the missingness penalty. Nothing is broken; the ordering is simply not
   yet a product.

   **Three inputs 13 did not have before:**
   - The vocabulary exists — 26 archetypes with per-value corpus evidence in
     `docs/role-track-derivation.md`, and an `unknown_penalty` block to copy.
   - **`other` is 31.1% of the cohort corpus and 44.0% of first-time
     extractions.** Price the vocabulary knowing nearly half of new postings do
     not match any of it. This is the single most important thing 13 should read.
   - The ops mass is `support_ops` (82), not `ai_operations` (17). Weighting
     `ai_operations` heavily targets 2.0% of the corpus, 11 of whose 14 employers
     are tech companies.

   **Do not set `daily_narrative_budget` above 0 without checking D16 first.** It
   is fixed (`e1cdf7b`), but the profile has no `buckets` key and that was the
   detonator.

2. **Task 29 — the labelling session.** 07's tooling is built and produced zero
   labels by design. The form is at `/v1/label` behind the existing Google SSO.
   What is missing is ~10 Builders and an afternoon. **Task 08 sharpened what the
   labels are for**: Axis A now has a specific question to settle — whether the
   ops shortfall is the title probe over-counting or the extractor
   under-applying.

Then, in order:

3. **The browser-DOM poisoning, and it is now WORSE than the previous handoff
   recorded.** Job `ff9f9d9f9643e185af0f48ca` (Taboola, *Product Analyst*) has a
   `description_text` beginning `*]:pointer-events-auto … data-testid="conversation-turn-136"`
   — a scraped ChatGPT web UI, not a posting. **It was re-extracted at
   `facts_version = 3` and produced confident facts from that markup**:
   `role_archetype = 'data'`, `role_track = 'data_and_analytics'`. Three postings
   carry browser-DOM markers:
   ```sql
   SELECT count(*) FROM jobs WHERE description_text LIKE '%data-testid=%'
      OR description_text LIKE '%pointer-events-auto%';   -- 3
   ```
   The re-extraction propagated the poison rather than clearing it, and nothing
   in the pipeline notices. Still has no task of its own. **Give it one**, and
   note the general shape: extraction has no input-sanity gate at all, so any
   ingest path that captures the wrong bytes gets laundered into structured facts.

4. **D45 — the `company_ats` write-back is partial.** 35 `never_found` rows
   against a true population of 139, the 35 being a contiguous alphabetical block.
   Tasks 16 and 17 read that column too. Needs a task; the repair is a re-run of
   the write-back, but whether `company_ats` should hold every negative is a
   design question.

5. **Task 21 has lost its premise.** It was scoped as "cheap because task 19's
   parser does most of the work." 19 is dropped. Either re-scope it as a
   standalone Idealist parser or measure first — and note that Idealist's
   per-listing expiration date was the good closure case, which survives.

6. **Tasks 15 and 20 need credentials**, and **their estimates come from the same
   table that has now been wrong four times out of four.** Measure before
   building. That is no longer a caution; it is the run's most reliable finding.

7. **Workday will not scale sequentially.** Task 18 costs ~14 min of nightly
   window at **four** tenants at 1.5s apart. `18-ingest-workday-cxs.md:97`
   anticipates ~50. Measured and recorded, not solved.

8. **Task 23, descoped** — but see the reprioritisation argument in
   `DECISIONS.md`: on the evidence **25 is where the 12x yield difference lives
   and it is a config edit**, and **24 is 7,500 searches/month against code
   already written and tested**.

9. **`job_scores` has no version key at all** — no `prompt_version`,
   `persona_version` or `criteria_version` (`schema.py:328-343`). Re-scoring
   triggers only on an anti-join for "no row exists" (`score.py:242-244`), so a
   persona or prompt edit silently leaves stale narratives. Task 08 documented it
   and deliberately did not fix it. **Task 13 edits the persona**, so this bites
   next.

## What these sessions measured, and what it means

Four numbers landed that change how the rest of the plan should be read.

**The Phase 3 estimates are not reliable, and this is still the run's headline finding.**
Three sources measured, three far below estimate:

| task | estimate | measured |
|---|---|---|
| 05 (gate volume) | — | 43/day, ≈3/day usable |
| 14 (NYC Open Data) | 20–60/day | **1.8/day** |
| 18 (Workday) | 80–200/day | **~1/day** at four tenants; ~12/day extrapolated to fifty |
| 19 (JSON-LD) | 30–60/day | **≤1.1–2.3/day**, a ceiling that is not reachable — **dropped** |

**Four for four.** This is no longer a caution about one estimate; it is the most
reliable finding of the whole run. Every Phase 3 number that has been checked has
come back an order of magnitude high, and they were all produced by the same
method from the same table. **Tasks 15, 20 and 21 are sized identically and should
be treated as unfounded until measured.** A spike costs an afternoon; task 19's
cost 333 HTTP requests and no LLM calls at all.

Tasks 15, 19, 20 and 21 are sized from the same table by the same method. **Measure before
building.**

**Task 11 measured the same shortfall from a third direction, and it is the sharpest
version yet.** Across 863 cohort-eligible postings — the ones that already pass task 10's
gate — the AI-operations archetype the whole retarget is aimed at appears **5 times, across
3 employers**. Not 5%: five postings. The vocabulary hole was real and is now fixed, but
fixing it revealed that the roles are not there to be classified. Meanwhile the `other`
bucket, which the task file assumed was full of ops roles, turned out to be **47.5% tech
roles the vocabulary simply lacked** against 12.6% ops. The corpus is still a software
corpus.

**And the shape of the shortfall matters more than its size.** Of 329 Workday postings
pulled from four NYC employers — a hospital system, a bank, a retailer — **zero have any AI
vocabulary in the title**, by any method. Task 10 reached the same place from the other
direction: its gate improved precision from 6.7% to 10.0% and is still 90% junk. The
problem is not that the boards are unreachable or that the gate is too tight. **These
employers are not posting these roles.** That is a question about the plan's premise, and
it is not answerable by building more ingest.

**The gate is not the bottleneck; sourcing is.** Task 10 raised hand-checked precision from
task 05's 6.7% to 10.0% — a real improvement, and still 90% junk. Its own report says the
bottleneck is sourcing rather than gating, and task 14's 1.8/day is the same finding from
the other side.

**Extraction capacity is no longer the constraint.** The drain loop replaced a hard 40/day
ceiling with ~1,260 calls/hour of headroom against 43–80/day of intake. Whatever binds
next, it is not this.

**Silence is still the failure mode, and it was caught live.** Task 18's first run dropped
**161 of NewYork-Presbyterian's postings** — real NYC hospital jobs — while printing
`4/4 tenants ok`. The task found it itself, on a third run, after having already reported
success. Nothing else in the pipeline would have noticed. When a source's numbers look
clean that is not evidence: reconcile against the count the API itself returned.

## How these sessions ran it, and what worked

**Task 11's session: three subagents in two rounds.** Round 1 ran the corpus-evidence
agent and the scoring agent in parallel — disjoint files, neither blocking the other.
Round 2 ran the extraction agent, which needed round 1's derived vocabulary. The
orchestrator took the baseline, verified every claim, made the one judgement call it would
not delegate (pricing 14 new archetypes for the author's profile), and committed.

**The first session: six subagents in parallel, orchestrator verifying and committing.**
Nothing was committed by a subagent in either session. Every task was checked against the
code and the database before its commit. Mechanics worth keeping:

- **Every agent gets an explicit file-ownership list.** Five ran concurrently with one
  genuine collision all session (`record_cassettes.py`, below).
- **`run-daily.py`'s `STEPS` is orchestrator-only.** It is the one file every ingest task
  wants to edit. Agents report the line they want; the orchestrator wires it.
- **Take the baseline before the first agent starts.** Tier-count-by-platform for every
  active profile, and the test count. Task 10's "the author's profile is unaffected" claim
  was only checkable because that snapshot existed — and by the time it was checked, a
  concurrent agent had added 1,030 rows on a new platform, which would otherwise have
  looked like a regression.
- **The handoff is rolling, not terminal.** This file, `DECISIONS.md`, `CLAUDE_UPDATES.md`
  and `README.md` were updated in the same turn as every commit. The previous handoff was
  written once at the end, from a context already spent, which is why it read as recall
  rather than record.

**Five of six agents in the first session, and three of three in task 11's, completed
without sending a report at all.** They go idle silently. Do not wait for a summary; check
the artifacts. That is the norm, not the exception.

**Verification that actually caught things in task 11, in order of value.** Reading the
diff caught the most; the suite caught the least. Worth copying:

1. **Re-run the agent's own tool and grep for the prose's numbers.** Caught the
   unreproducible figures.
2. **Recompute a headline number independently.** Surfaced the 54-vs-55 distinction.
3. **Prove an equivalence claim by exhaustion, not by reading.** The rewritten tombstone
   guard was checked over a 192-case cross product of the four signals it reads.
4. **AST-check the invariant.** `score_job()`'s purity is a CLAUDE.md rule; walking the
   function for I/O calls and imports is three lines and does not rely on a promise.
5. **`match.py --dry-run` against the live database.** The claim "this change is inert in
   production" is worth exactly nothing unverified; it reports 0 matched or it does not.

**The one real collision:** `backend/evals/record_cassettes.py` accumulated two agents'
changes at once. Task 14's commit deliberately excluded it rather than ship task 17's
half-finished work under 14's number, and 17's commit carried both. The general fix is the
one `STEPS` already has — shared files get a single owner, named in advance.

## Pending follow-ups with no task of their own

- **`backend/evals/record_cassettes.py` owes a `workday-cxs` recipe** — a full multi-page
  walk against `msk.wd108` (88 postings, ~5 requests) plus one detail document. That would
  turn task 18's `total`-only-on-first-page finding from a *constructed* fixture into a
  recorded one. Not done because `backend/evals/` was owned by another agent; the exact
  recipe is specified in `docs/ingest/workday.md`.
- **Task 09's `workday_fixtures.prefix_assumed()` models the wrong failure shape.** It
  models a wrong data centre as HTTP 404 with an HTML body; the real recorded probe in
  `ats-validation.json` shows `nvidia.wd1` answering **HTTP 422 with a JSON `errorCode`**.
  The consequence is identical — both permanent, neither retried, both surface — so it was
  recorded rather than silently edited.
- **Accepted, and worth knowing it was a deviation:** task 18 kept `_collect_naively`
  against the letter of `18-ingest-workday-cxs.md:121`. It is a stand-in for the *defect*,
  not for the ingest loop, and it is the only thing that can show a constructed fixture
  still reproduces the failure it names. A fixture that no longer triggers its own failure
  reads like coverage and is worse than none.
- **Fixtures written from a specification test the specification.** All three failure modes
  task 18 found live were invisible to the four constructed fixtures, because those encode
  the shapes the task file *describes*. Task 09's cassettes are the counterweight and
  should be preferred wherever a real endpoint can be recorded.

- **Task 11's `role_track` column is NULL on all 5,328 rows** and stays that way until
  task 12 re-extracts. Nothing has been extracted for it, so there is nothing to backfill
  — the same rule as `job_events.rank`. Its nine-value vocabulary is **provisional**,
  derived pre-Phase-3 from a tech-heavy corpus; `tools/derive-role-tracks.py` re-runs the
  derivation and `docs/role-track-derivation.md` holds the evidence.
- **Nothing task 11 touched is live.** No `criteria_version` bump, so the 26 archetype
  weights and the `unknown_penalty` block are inert until
  `migrate_profiles.py --apply --bump`. Verified: `match.py --dry-run` reports 0 matched
  for both active profiles. Whoever bumps should know `years_experience_min` is NULL on
  **52.9%** of the corpus, so its penalty is a corpus-wide re-ranking, and the magnitudes
  are unfitted guesses.
- **Two leftover scratch schemas hold a full `job_facts` each** — `scratch_5ce56323` and
  `scratch_cafb8b05`, from task 09's harness. Harmless (`search_path` is `public`) but it
  means the teardown does not always run, and an `information_schema` query without a
  `table_schema` filter triples its rows. Noticed while verifying task 11's column add.
- **The SerpApi ledger reconciliation** (above).
- **Task 12 must carry the majority-of-3 change into its `FACTS_VERSION` bump.**
  Extraction semantics changed; CLAUDE.md: "Versions are cache keys."
- **`match.py` has no per-record isolation** (register entry D20) and is now testable via
  task 09's harness. **D17** is pinned as still-broken with an assertion ready to flip.
- **Steady-state Google Jobs yield is unmeasured.** The experiment's 0.56 genuine/search
  is a first-run rate with no date chip; no query on either bank has run more than twice.
  Rerun the same 16 queries with `chips=date_posted:week`.

# Handoff — the `docs/tasks/refactor/` run

Written 2026-07-28 to hand this run to a fresh session. Read this first, then
[`DECISIONS.md`](DECISIONS.md) (why each choice was made) and
[`CLAUDE_UPDATES.md`](CLAUDE_UPDATES.md) (what happened, per task).
[`README.md`](README.md)'s status column is the ordered index.

## State at handoff

**Branch `webapp-service`, HEAD `fabe381`, suite green at 663 tests** (task files say 263; it
has grown — 663 is the floor now). **The whole suite passes** — `python3 -m unittest
discover -s backend/tests` from the repo root. Working tree is clean apart from untracked
`scripts/`, which predates this run and is not ours.

`backend/webapp/tests/` is a separate matter: **`fastapi` is not installed here**, so five
modules fail to import and always have. Not a regression, and not covered by the count
above.

Ten tasks committed, one experiment, plus the two conversational decisions:

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

01 and 02 were already committed before this run (`28f1d0e`, `36d83f5`).

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

All six agents this session completed, were verified against the code and the database,
and were committed. **The tree is clean.** `run-daily.py`'s `STEPS` is fully wired —
`ingest/workday.py` and `ingest/nyc-open-data.py` were added by the orchestrator, and
`ats.py` was already there.

## How this run works

**One fresh subagent per task; the orchestrator verifies and commits.** Nothing is
committed by a subagent. The orchestrator checks each Definition of done against the
files, writes the decision-log entries, and commits with the task number.

**Verify, do not trust the report.** This mattered repeatedly:

- Task 16 reported itself finished while its report contained a literal
  `## RESULTS_PLACEHOLDER` and `company_ats` held **zero rows**. Caught by querying the
  database rather than reading the summary. It took two more passes to finish.
- Several agents complete their work and go idle **without sending a report at all**.
  Verify the artifacts directly; do not wait for a summary that may never arrive.
- Test counts drift while other agents work concurrently, so a count quoted by one agent
  may include another's in-flight tests.

**Give each subagent an explicit do-not-touch file list.** Parallel agents collide
otherwise. Three ran concurrently for most of this session without conflict on that basis.

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
- **The task files were written from the plan, not from the code.** Five are now confirmed
  wrong about what they describe: 05's premise, 10's instruction to lift a regex verbatim,
  17's "current coverage is Greenhouse and Lever" (Ashby already existed), the `generated:`
  frontmatter claim, and 14's 20–60/day estimate against a measured 1.8. **Read the code
  before trusting a task file's account of it**, and expect the Definition-of-done counts
  to be off.
- **`fastapi` is not installed in this environment**, so `backend/webapp/tests/` cannot
  run at all — five modules fail to import, four of which predate this run. It is not a
  regression and not task 07's doing. `backend/tests/` is the suite that gates work here;
  anything under `webapp/` is unverified by CI as things stand.
- **`docs/ingest/*.md` claim `generated:` frontmatter but no generator exists.** Task 34
  must decide: write generators, or drop the claim.

## Recommended next steps

**Two tasks are now the whole critical path, and both are held on human judgement, not on
code.**

1. **Task 13 — the cohort criteria profile.** It is what makes everything else this
   session built *mean* anything. The `pursuit` profile exists (`7d94bb1`) but ships
   `active=False` with **labelled placeholder** persona and criteria, because the weights
   are a cohort product call. Until it lands: task 10's gate is inert in production, and
   **task 18 cannot report a yield at all** — its 4-of-149 measures today's SWE-shaped
   `relevance.json`, not Workday. Activating the profile is a deliberate act worth **+573
   rows, 13.2/day**.
2. **Task 29 — the labelling session.** 07's tooling is built and produced zero labels by
   design. The form is at `/v1/label` behind the existing Google SSO. What is missing is
   ~10 Builders and an afternoon.

Then, in order:

3. **Task 11** — archetype superset, `role_track`, missingness. Unblocked by 10, and
   `job_facts.vote_unanimity` now gives it a per-row stability signal to record.
4. **Task 12** — and it **must** carry the `FACTS_VERSION` bump for the majority-of-3
   change. See `schema.py:158`. One re-extraction pays for both; do not bump separately.
5. **Task 08** — score validation; needs 07's tooling but not its human labels.
6. **Tasks 19, 21** — the remaining unblocked Phase 3 ingest. 15 and 20 need credentials.
   **Do not trust their estimates** — see the finding below.
7. **The ChatGPT-DOM defect.** Job `ff9f9d9f9643e185af0f48ca`'s `description_text` begins
   `data-testid="conversation-turn-136"` — some ingest path captured a browser DOM rather
   than a posting body, and it is silently poisoning extraction input. Found by task 10,
   out of its scope, still has no task of its own.
8. **Workday will not scale sequentially.** Task 18 costs ~14 min of nightly window at
   **four** tenants at 1.5s apart. `18-ingest-workday-cxs.md:97` anticipates ~50. The
   delay, the concurrency or the per-tenant cadence has to change before task 16's tenant
   backlog is drained into it. Measured and recorded, not solved.
9. **Task 23, descoped** — but see the reprioritisation argument in `DECISIONS.md`: on the
   evidence **25 is where the 12x yield difference lives and it is a config edit**, and
   **24 is 7,500 searches/month against code already written and tested**.

## What this session measured, and what it means

Three numbers landed that change how the rest of the plan should be read.

**The Phase 3 estimates are not reliable.** Task 14 measured **1.8 relevant/day against an
estimate of 20–60**. Task 05 measured 43/day resolving to ≈3/day usable. Task 18 declined
to report one at all, correctly. Tasks 15, 19, 20 and 21 are sized from the same table by
the same method. **Measure before building.**

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

## How this session ran it, and what worked

**Six subagents, run in parallel, orchestrator verifying and committing.** Nothing was
committed by a subagent. Every task was checked against the code and the database before
its commit. Four mechanics worth keeping:

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

**Five of six agents completed without sending a report at all.** They go idle silently.
Do not wait for a summary; check the artifacts. That is now the norm rather than the
exception.

**The one real collision:** `backend/evals/record_cassettes.py` accumulated two agents'
changes at once. Task 14's commit deliberately excluded it rather than ship task 17's
half-finished work under 14's number, and 17's commit carried both. The general fix is the
one `STEPS` already has — shared files get a single owner, named in advance.

## Pending follow-ups with no task of their own

- **The SerpApi ledger reconciliation** (above).
- **Task 12 must carry the majority-of-3 change into its `FACTS_VERSION` bump.**
  Extraction semantics changed; CLAUDE.md: "Versions are cache keys."
- **`match.py` has no per-record isolation** (register entry D20) and is now testable via
  task 09's harness. **D17** is pinned as still-broken with an assertion ready to flip.
- **Steady-state Google Jobs yield is unmeasured.** The experiment's 0.56 genuine/search
  is a first-run rate with no date chip; no query on either bank has run more than twice.
  Rerun the same 16 queries with `chips=date_posted:week`.

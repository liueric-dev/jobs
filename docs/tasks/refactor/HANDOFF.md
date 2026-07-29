# Handoff — the `docs/tasks/refactor/` run

Written 2026-07-28, and rolling — last updated after a **planning-only session that
measured the gate fix (step 0) against the live corpus and wrote no code**. Its finding
inverts step 0's own vocabulary recommendation; read § *the gate fix is planned and
measured* before touching anything. Before that: the **mock acceptance run and the
`strip_html` fix**, which were recommended next step 3 and a new measurement; **`job_scores`'
version keys** (`d18ea54`); and **13, 35 and D45** (`fa2d7a7`,
`303f7b9`, `e11fabf`). Read this first, then
[`DECISIONS.md`](DECISIONS.md) (why each choice was made) and
[`CLAUDE_UPDATES.md`](CLAUDE_UPDATES.md) (what happened, per task).
[`README.md`](README.md)'s status column is the ordered index.

## Orientation — there are four "READ THIS FIRST" sections, in this order

That is three too many, and the file has earned each one. If you read nothing else:

1. **Do the gate fix — it is now planned, measured and ready to implement** (§ *the gate
   throws away half the cohort*, then § *the gate fix is planned and measured*). Unblocked,
   small, free to re-measure, and the largest measured loss in the pipeline. It is step
   **0** under "Recommended next steps" and it goes before task 29, because every posting
   the gate rejects is one the labelling session will never be shown. **Do not re-derive
   the vocabulary from the mock corpus — that is the trap the measurement caught.**
2. **Do not re-tune task 13's weights** (§ *the ranking is a product now*). Its DoD is
   unmet on purpose. Nothing measured since — including the mock corpus's 5-of-5 on
   branding traps — licenses changing them. Only task 29 does.
3. **Do not reactivate `tech` or raise `daily_narrative_budget` casually**
   (§ *the cost lever hiding in the profiles table*). Either one restores a ~5,000-row
   re-extraction bill or a ~1,018-call re-scoring bill. Run `score.py --stale-report`
   first; it needs no API key.

**The one sentence a fresh session most often gets wrong:** a completed task here is not
a validated one. 13 is committed and unmet; the mock acceptance run is a *specification*
test and does not reduce task 29 by one posting.

**Verify before you trust — including this file.** It has been measurably wrong about
its own line numbers, about which three tests a change would break, and about its own
SQL. Cite `file:line`, then re-read the line.

## READ THIS FIRST: the ranking is a product now, and the DoD it did not meet

**Task 13 landed (`fa2d7a7`). `pursuit` has real weights, `criteria_version` 2, 144
matched of 859.** Until it did, every matched posting scored exactly 50 against a
floor of 40 and the ordering carried no information. That is fixed.

**What did NOT happen, and must not be misread as an oversight: 13's Definition of
done at lines 122-123 is unmet, and was deliberately not tuned into being met.**
It asks for 20 hand-picked target roles all above the floor and all in the top 20.
Measured: **16 of 20 above the floor, 10 of 20 in the top 20.** Line 124 is met in
full at 10 of 10.

The golden set was picked on **title, company and location** — the three fields
`score_job()` cannot see (`match.py:276-287`). That is what makes it the one
non-circular test of the weights available, and it is why tuning against it was
refused. Three of the four floor misses carry `ai_involvement = 'none'` and read as
AI-adjacent only because the employer is an AI company, which is the failure mode
task 05 measured at 6.7% precision — **they may be correct rejections rather than
weight errors, and task 29's labels are the only thing that can settle it.**

**Do not re-tune to close that gap before 29.** The weights are unfitted by
construction — no labels, no `job_events` — and `match_score` is free arithmetic,
so the cost of the current set being wrong is one `match.py --rebuild`.

## READ THIS FIRST: the gate throws away half the cohort, and it is now measured

**Gate recall is 48.3% [31.4–65.6]. Fifteen of twenty-nine intended-good postings are
tier 3 and never enter the pipeline.** Measured 2026-07-29 against a 55-posting
synthetic corpus with a quote-backed answer key —
[`docs/mock-acceptance.md`](../../mock-acceptance.md), harness
`backend/tools/mock-acceptance.py`, 90 live calls, run entirely in a scratch schema.

This is the **fourth stratum of task 29's sample measured early**, and it is the one
quantity nothing else in this repo can produce: every existing figure is precision
over rows the pipeline already chose to surface. It fires 29's own gate row — *"task
10's gate is too tight. Fix before anything else, because no ranking work recovers a
posting that never entered."*

**Two distinct causes, needing different fixes:**

1. **`ENTRY_LEVEL` is title vocabulary applied to descriptions (14 of the 15).** The
   pursuit gate is conjunctive — one AI term **and** one entry-level term in the *same
   field* (`migrate_pursuit_profile.py:216,229`). The entry group is `associate,
   coordinator, assistant, specialist, analyst, …`: title nouns. A description does not
   repeat its own title's seniority noun, so the AI half matches and the entry half
   does not. `mock_022`'s *"No retail or e-commerce experience required; training
   provided"* matches neither `\yno experience\y` nor `\ywill train\y`. **Task 10 built
   a description-first gate and gave it a title vocabulary.**
2. **`title_exclude` silently overrides the description-first gate.**
   `relevance.py:232-234` applies it to **both** paths, so a title exclusion vetoes a
   posting whose description passes both groups. `pursuit`'s list still carries
   `customer success`, `executive assistant`, `office manager`, `facilities`,
   `warehouse`, `driver` — inherited from the software-engineer profile, and several are
   exclusions on the cohort's own target population.

**What the same run says about the rest of the pipeline, so the gate is read in
proportion:** extraction pooled **86.4%** [82.8–89.3] with `ai_involvement` at
**98.1%**; `score_job()` separates intended-good from intended-bad at **AP 91.9%,
precision@20 90.0%** against a 53.7% chance level. **The ranking is good and the gate
in front of it is the constraint.**

**And it answers HANDOFF's standing branding-trap question, for constructed
instances.** All five AI-branded employers whose roles use no AI tools were extracted
`ai_involvement = none` — matching the key 5 of 5 — and all five scored below the
floor. **The extractor is not fooled by the company name.** That is evidence the
mechanism works when the trap is unambiguous; it is **not** evidence about task 13's
four actual floor misses, which remain unlabelled. **Do not re-tune on it.**

**Read the limitation with the number.** `HANDOFF.md`'s own rule applies to this
deliverable: fixtures written from a specification test the specification. The corpus
was built to contain the failure modes being looked for. It does not reduce task 29 by
one posting and nothing from it reached `eval_labels`.

## READ THIS FIRST: the gate fix is planned and measured, and the mock corpus lied about it

**Session of 2026-07-29, planning only. No code was written, nothing was committed, the
database was read but never written.** The deliverable is a plan and seven numbers. The
plan is at `~/.claude/plans/read-the-handoff-document-squishy-flurry.md`, outside the repo
and not durable. **Step 0 below is the source of truth and carries everything load-bearing**
— it was rewritten from that plan rather than pointing at it, deliberately, so nothing here
depends on a file the repo does not hold.

**The finding: candidate fixes ranked on the mock corpus rank the opposite way on the live
corpus.** Step 0 named three phrase families to recover the 15 lost postings. Each was
compiled through `relevance.tier_sql` against the live table (13,447 open rows, read-only):

| family | mock recall recovered | live rows admitted | verdict |
|---|---|---:|---|
| `no <X> experience/background/license required/needed/necessary` | 11 of 15 | **+4** | ship |
| `does not require … experience/background` | 1 (mock_012) | +0 | ship, dead-but-kept |
| `training (is) provided` | 0 new | +0 | ship |
| `we provide/offer … training` | 1 (mock_017) | **+17** | **reject** |
| `we (will) train` | 0 new | **+5** | **reject** |
| `preferred but not required` | 1 (mock_016) | **+5** | **reject** |
| `experience … preferred / is a plus` | 1 (mock_018) | **+123** | **reject** |

What the rejected four admit live: `Software Engineer, RL Training Infra | OpenAI`,
`Full-Stack Software Engineer, Reinforcement Learning | Anthropic`, `Product Manager,
Gen AI | Scale AI`. **`\ywe train\y` matched OpenAI's "we train models"** — a false friend
that cannot exist on a synthetic corpus.

**On the mock corpus all four measured as FREE — zero added false positives.** They look
free there because every intended-bad mock posting carrying that phrasing has no AI
vocabulary at all, which is a property of a corpus written to a specification and not of
the world. This is `CLAUDE.md`'s *"fixtures written from a specification test the
specification"* firing on the deliverable that introduced the rule. **The four rejected
families are the single most likely thing for a future session to re-add**, because the
harness will say they cost nothing. A sentinel test is specified in step 0 for exactly
that reason.

**Measured end state of the planned fix:**

| metric | before | after |
|---|---|---|
| mock gate recall | 14/29 = 48.3% | **26/29 = 89.7% [73.6–96.4]** |
| mock gate precision | 14/24 = 58.3% | **26/36 = 72.2%** |
| mock false positives | 10 ids | **the same 10 ids, unchanged** |
| live tier ≤2, open | 869 (t1 450 / t2 419) | **880 (t1 456 / t2 424)** |
| `extract.remaining` | 2 | **13** |

**Recall stops at 89.7%, not 100%, on purpose.** mock_016, mock_017 and mock_018 are
reachable only through the rejected families, at +145 live junk rows. That trade is
refused and the refusal is recorded rather than silently omitted.

**The backlog is 11 extraction calls** — under half of one `EXTRACT_BATCH_SIZE=40` batch
(`extract.py:113-134`), ~$0.004, drained on the first nightly run. **HANDOFF's own caution
pointed at the cheap risk.** "Widening the gate widens the extraction queue — check the
volume against `extract.py`'s drain" is answered and was never the constraint. The
expensive risk is precision, and it is concentrated in precisely the families the mock
corpus scores as free.

**The 11-row delta was hand-checked as a census, not a sample:** ~7 on-target (Customer
Success Associate/Specialist ×6, Applied AI Specialist), 1 clear false positive
(`Research Engineer, Interpretability | Anthropic`, which really does say "no research
experience is required"), 3 ambiguous. **~64% strict, against the incumbent gate's 10.0%
strict / 23.3% generous** (`migrate_pursuit_profile.py:166-167`). The rows being added are
better than the rows already in — that comparison is the argument for shipping and belongs
in the commit message.

**Six things step 0 said that the code does not support**, recorded under *Findings later
tasks must not inherit* below. The two that will bite hardest: **`tools/mock-acceptance.py`
is a consumer of the thing being edited, not a neutral instrument** — it `importlib`s the
gate out of `migrate_pursuit_profile.py` (`:314-331`), so if the source of truth moves to
JSON without repointing that function, the harness keeps measuring the old gate and
reports "no change", which reads as *the fix did nothing*. And **`title_exclude` gating
both paths is deliberate and pinned by test** (`relevance.py:227-231`,
`test_relevance.py:203-211`), not a silent override — the fix is to edit the *list*, never
`tier_sql`.

## The measurement that should shape what comes next

**The cohort's addressable set is 55 postings.** Over the 859 at `facts_version = 3`:
entry-level (`intern`/`new_grad`/`junior`) is 163 (18.9%), `uses_ai_tools` is 309
(35.8%), and the intersection — the shared floor the whole retarget is aimed at — is
**55 (6.4%)**. The corpus is 77.6% mid/senior and 47.2% `ai_involvement = none`.

This is the **fifth** measurement pointing where the GATE 2 section below points, and
the first taken *after* the gate, the extraction and the vocabulary were all fixed.
The weights are ordering 55 postings, not 859.

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

**Branch `webapp-service`, suite green at 1030 tests** (task files say 263, earlier
handoffs 782, 837 and 878; **1030 is the floor now**).
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
| — | D45 **fixed** — one durability cadence, 104 rows backfilled | `e11fabf` |
| 35 | extraction input-sanity gate — **8 poisoned rows, not 3** | `303f7b9` |
| 13 | cohort criteria profile — **DoD 122-123 unmet, not tuned** | `fa2d7a7` |
| — | **`job_scores` version keys — inert by default, 0 rows re-scored** | `d18ea54` |
| — | **mock acceptance run — gate recall 48.3%, the finding** | `8306e7b` |
| — | **`lib/text.strip_html()` fixed — 6 corrupted rows restored** | `8306e7b` |
| — | task-07 gaps: per-platform breakout, `fit_score` blindness pinned | `8306e7b` |
| — | **step 0 planned and measured against the live corpus** | **NO COMMIT — plan only** |

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

**The 2026-07-29 planning session wrote no code and made no commit.** Four agents ran —
three read-only exploration, one design pass that compiled candidate gates through
`relevance.tier_sql` against the live table. **Every database access was a `SELECT`**; no
scratch schema was created, no row was written, `profiles` was read and not modified. The
only files changed are this one and the plan outside the repo. Its output is step 0 above;
implementation has not started.

**The tree is clean.** Every agent across all six prior sessions completed, was verified
against the code and the database, and was committed — six in the session that landed
03–18, three in the session that landed 11, three in the session that landed 08/12/19,
three in the session that landed 13/35/D45, two in the session that landed the
`job_scores` version keys, five in the session that landed the mock acceptance run and
the `strip_html` fix. Nothing is half-written and nothing is waiting on a reply.
Untracked `scripts/` predates this run and is not ours.

`run-daily.py`'s `STEPS` is fully wired — `ingest/workday.py` and `ingest/nyc-open-data.py`
were added by the orchestrator, and `ats.py` was already there. **No task since 12 has
touched `STEPS`**, so the nightly run is unchanged in shape — and that is now asserted
by test rather than left to habit (`test_score_versions.py`, two tests: the score entry
verbatim, and no `--rescore-*` flag anywhere in the schedule). Four things changed
underneath it:

- the nightly `extract.py` step serves one profile with a much smaller queue (task 12);
- **it can now REJECT before calling the model** (task 35). A posting whose prompt window
  is ≥1% markup is tombstoned for zero LLM calls and counted in `unusable` on the summary
  line. If that counter starts climbing, an ingest path is capturing the wrong bytes —
  `tools/audit-description-markup.py` is the instrument;
- `match.py` now writes a real ranking instead of 863 identical scores (task 13), and
  `score.py` still writes nothing at all because `pursuit`'s `daily_narrative_budget`
  is 0;
- **`score.py` can now be told a stored narrative is out of date, and still will not
  act on it.** `job_scores` carries version keys, but the nightly step passes no
  `--rescore-*` flag and the default selection is the old existence-only anti-join.
  A persona edit or a prompt bump changes what `--stale-report` says and changes
  nothing about what the pipeline spends;
- **the bytes it stores are no longer contaminated at the source.** `lib/text.strip_html()`
  is fixed, so the `unusable` counter above should now stay at 0 for greenhouse. It is
  still the alarm and still guards the ~13,000 rows the old stripper wrote — its tests
  were re-pointed, not retired, precisely so that a future reader does not find a gate
  with no reachable trigger and remove it as dead code.

**Start here:** `cd backend && python3 -m unittest discover -s tests -t .` should report
**1030, OK**. `backend/.env` is not exported by default — scripts that reach the
database need `cd backend && (set -a; . ./.env; set +a; python3 ...)`.

**Then read this, because it is the one thing a fresh session will get wrong:** task 13
is committed and its Definition of done is *not* met. See the top of this file. A
completed task here is not a validated one.

### The next session's likely first question, answered

**"Step 0 says it is planned and measured. Can I just implement it, or do I need to
re-derive anything?"** Implement it. The vocabulary, the `title_exclude` decision, the
commit sequence and every gate figure in step 0 came from compiling candidate configs
through `relevance.tier_sql` against the live table on 2026-07-29. **Re-confirm the
baselines first** — the nightly has run since, so the absolute counts (450/419/12,578,
`extract.remaining` = 2) will have moved even though the deltas should not. The two things
still genuinely open are the `\yexecutive assistant\y` call, which wants 9 descriptions
read, and the `\yfacilities\y` single row.

**"The mock harness says the four rejected phrase families cost nothing. Why not add
them?"** Because the mock corpus cannot see their cost. They admit +17/+5/+5/+123 live
rows of senior engineering requisitions at AI employers. This is the single most likely
thing for a fresh session to "fix", which is why step 0 specifies a sentinel test that
asserts their absence and carries the counts in its docstring. See § *the gate fix is
planned and measured*.

**"The mock corpus measured gate recall at 48.3%. Does that mean task 29 is done, or
partly done?"** Neither. It measured task 29's *fourth stratum* on **constructed**
postings, which is why it could be done at all without people. Nothing was written to
`eval_labels`, no Axis B exists, and the corpus was built to contain the failure modes
it then found — `HANDOFF.md:805-808`. Task 29's scope is unchanged. What did change is
that one of its four gate rows has now fired early, and it is the one that says fix the
gate before anything downstream.

**"Can I re-tune the weights now that the branding traps came back 5 of 5 correct?"**
No, and this is the most likely misreading in the file. Those five were *constructed* to
be unambiguous traps. Task 13's four actual floor misses are real postings and are still
unlabelled. The mock result is evidence the mechanism works when the trap is obvious; it
is not evidence about the four. Everything under "Can I re-tune the weights?" below still
holds.

**"`docs/mock-acceptance.md` reports `role_archetype` at 57.4% and `remote_policy` at
55.6%. Is extraction broken on those fields?"** Not established, and do not act on
either number without reading the disagreements first. `remote_policy` is a likely
**vocabulary mismatch**: `extract.REMOTE_POLICY` is
`onsite/hybrid/remote_local/remote_anywhere/unknown` while the corpus's own field is
`onsite/hybrid/remote`, so the key had to pick a side per posting. `role_archetype` is
26 values inferred over a whole posting, and its key entries are the weakest evidence in
the file — treat it as a floor. A rate that far below its neighbours, on fields this
mechanical, is more likely a definition problem than a model problem.

**"The mock report says `n/d = the key says the posting does not determine this field`
for `tech_stack`, `comp_*`, `employment_type`, `visa_sponsorship` and
`years_experience_max`. What did the key decide about them?"** Nothing — those fields are
not in the key at all, and the label is wrong about them. Known cosmetic defect in
`tools/mock-acceptance.py`'s renderer; **no number is affected** (they are excluded
either way, and `POOLED` = 440 is exactly the nine keyed fields). Worth splitting the
two cases if anyone touches that output.

**"Why is `pursuit` only matching 144 postings when it used to match 863?"** Because the
weights are real now. 863 was every posting scoring exactly `base = 50` against a floor
of 40. Nothing regressed. `match.py --rebuild` reproduces it.

**"Can I re-tune the weights?"** Not usefully, and see the top of this file. There is
nothing to fit against until task 29 produces labels — no `job_events`, no L0. The
weights are unfitted guesses by construction and are *recorded as such* in
`config/pursuit-criteria.json`'s `_comment` blocks. Changing them costs one
`match.py --rebuild` and buys no information.

**"`job_scores` has version columns and every one of them is NULL. Is that a bug or a
missing backfill?"** Neither — it is the design, and it is the single thing most likely
to be "fixed" into a four-figure LLM bill. An unversioned row is a **third state**:
not stale, not fresh, unknown. Nothing recoverable exists to backfill (the prompt
changed mid-history, `persona_json` is overwritten with no history, and copying today's
`facts_version` across would stamp a v2-era narrative v3-current and permanently *hide*
a genuinely stale row). Run `score.py --stale-report` — it needs no API key — before
touching anything.

**"I edited the persona / the prompt. What re-scores?"** Nothing, automatically, ever.
`--rescore-stale` and `--rescore-unversioned` are separate flags and both require an
explicit `--limit`. That inertness is what pays for the absolute prompt-version bump
rule; if re-scoring is ever made automatic, that rule has to be renegotiated first.

**"Where do the eval fixtures come from?"** `backend/evals/fixtures/pursuit-criteria-corpus.jsonl`
(859 frozen `job_facts` rows) and `pursuit-criteria-goldens.json` (20 + 10 hand-picked
`job_id`s with pinned scores and ranks). **There is no generator script for either** —
they were produced ad hoc and re-pinned by hand once already. Anyone regenerating them
writes that code, and should probably leave it behind as `tools/`.

**Live state after the mock-acceptance / strip_html session (2026-07-29T05:40Z).**
Baseline taken before any agent started, digests re-checked after: `jobs` 14,049,
`job_facts` **5,923**, `job_matches` 3,521, `job_scores` 1,293. The only deltas this
session caused are the **−2 `job_facts`** rows remediated as markup-derived; the
`job_matches` and `job_scores` content digests (`90715a5f…`, `af8a273f…`) are
**byte-identical** before and after, which is the proof nothing was overwritten. The
mock run touched `public` not at all: 0 rows at `platform='mock'`, no `mock_all`
profile, no new scratch schemas. `scratch_5ce56323` and `scratch_cafb8b05` are still
the only orphans and still predate this run.

**Numbers below are from the previous session and are superseded by the paragraph
above**, kept because their commentary is still the reasoning:
```
job_facts  5,903 = 859 @v3 (the pursuit corpus) + 5,029 @v2 + 15 @v1
           4 v3 rows deleted by task 35's remediation -- they were markup, not postings
           extraction_passes = 1 and vote_unanimity IS NULL on every row
job_matches 3,521 = pursuit 144 @(3,2) + tech 3,084 @(2,5) + frontend 293 @(2,1)
           pursuit fell 863 -> 144 because the weights are real now, not because
           anything broke. tech lost exactly 1 row to task 35, NOT to task 13.
job_scores  1,293 = tech 1,110 + frontend 183; pursuit still has none and will not
           until daily_narrative_budget is raised above 0 -- read D16 first
           NOW CARRIES facts_version / persona_sha / prompt_version /
           criteria_version, and ALL FOUR ARE NULL ON ALL 1,293 ROWS. That is
           deliberate: unversioned is a third state, never automatically stale.
           `score.py --stale-report` reads 0 stale, 1,018 unversioned, and needs
           no API key. The BILL IS 1,018 CALLS, NOT 1,293 -- 275 rows are closed
           or never cleared MATCH_FLOOR, and no flag can reach them.
company_ats  139 never_found (was 35) + 75 valid + 5 unvalidated + 3 dead
profiles    pursuit active @criteria_version 2; tech and frontend inactive but intact
jobs        13,655 total / 13,082 open as of 2026-07-29T04:10. THE NIGHTLY RAN
           DURING THIS SESSION -- max(first_seen) 2026-07-29T04:08:38, 148 postings
           closed. job_facts and job_matches are UNCHANGED by it, so the newest
           intake is not yet extracted or ranked. Do not read that gap as damage.
```

**`job_facts` and `job_matches` above are exactly the pre-session numbers**, which is
the useful part: two agents and a nightly run moved nothing in the derived tables.

**A cross-stream lesson worth keeping.** Three agents ran in parallel on strictly
disjoint *files* and still interacted, because **the database is shared**. Task 35's
remediation deleted 4 rows from the pursuit corpus while task 13 was scoring it, so
13's frozen eval fixture had to be re-pinned 863 → 859 and `tech`'s `job_matches`
md5 changed for a reason that had nothing to do with 13. Both were caught only
because a baseline was taken first. **File ownership does not isolate database
state; take the baseline and attribute every delta before recording a conclusion.**

**It happened again in the version-keys session, and the culprit was the pipeline
itself.** A `tech` count moved 835 → 834 mid-session with two agents running on
disjoint files. Neither did it: the **nightly `run-daily.py` timer fired at 04:08**
and closed a greenhouse posting. The narrative content digest and `max(scored_at)`
were byte-identical throughout, which is how the delta was isolated to a job closing
rather than a re-score. **The other agent in the room is the cron job**, and a
snapshot taken at the start is the only thing that can tell you so.

**Take a content digest, not just counts.** `md5` over `string_agg` of the narrative
columns ordered by `(profile, job_id)` is what proves *nothing was overwritten*. A
row count cannot see an overwrite, and "the counts match" is exactly the reassuring
sentence a silent re-score would produce.

## How this run works

**One fresh subagent per task; the orchestrator verifies and commits.** Nothing is
committed by a subagent. The orchestrator checks each Definition of done against the
files, writes the decision-log entries, and commits with the task number.

**The orchestrator should OWN the shared input, not just the shared output.** `STEPS`
was already an orchestrator-only file because every ingest task wants to edit it. The
version-keys session generalised it: `schema.py` was the input *both* agents needed,
so the orchestrator wrote it first and handed both agents a stable file to read. That
removed the race task 11 had to solve by pasting values into a prompt, and it is
cheaper than either — one small edit before the agents start.

**A measurement's denominator needs an adversarial reader who cannot see how the
numerator was built.** The mock-acceptance session gave two agents the same contract and
no sight of each other's work: one wrote the answer key, the other wrote the loader that
validates it. The loader **refused** the key — `location_is_nyc` is not a `job_facts`
column (`match.py:281`), so the model never produces it and scoring it would have
compared the loader's own mapping against the key's reading of the same twenty
characters. Two of eleven "extraction accuracy" fields would have been a field agreeing
with itself. **One reader reviewing both files would not have caught it**; the refusal
came from the boundary, not from care. Design the boundary in on purpose. **D47.**

**Re-verify a function after you change it, including when you were the one who
changed it.** The orchestrator brute-force-verified `average_precision`'s tie handling
against every permutation, then sent back a correction that altered its signature. A
verified-then-modified function is unverified; the check was re-run and only then
trusted.

**Make a migration prove its own method before it writes.**
`migrate_description_rehash.py` reconstructs `content_hash` and reports that it
reproduces the *stored* hash on 10,405/10,405 untouched rows. A reconstruction method
that could not reproduce existing hashes is caught before it touches anything, which is
a stronger guarantee than a dry-run diff and costs one extra column in the report.

**A green suite does not mean the brief was met.** The version-keys session's test
agent delivered 37 tests, all passing, with one required test missing — the one
asserting `run-daily.py`'s `STEPS` entry verbatim. The suite was green *without* it,
because it is a test about a constant nobody had changed. It was caught by reading
the agent's test list against the brief, not by running anything. **Check the
deliverable list item by item; the suite only tells you the code you wrote works.**

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
people. Task **29** is the labelling session itself and stops entirely. **30** sits behind it. **12** needs Axis A figures.

**13 is committed but its judgement inputs were supplied provisionally, and that is now
the sharpest open question.** The weights were chosen by the repo owner from three
simulated variants, and the "20 plausible Pursuit target roles" were picked by an agent
from titles, companies and locations — blind to the scores, which is what makes them a
valid test, but not blind to the fact that an agent rather than a Builder decided what a
Builder wants. **The 30 picks in
`backend/evals/fixtures/pursuit-criteria-goldens.json` are the artifact a human should
review first**, ahead of the weights: if the list is wrong, the 16/20 and 10/20 figures
measure nothing, and if it is right, they are the sharpest statement available about how
the weights are doing. Reviewing 30 titles is an hour; the labelling session is a day.

**Credentials needing an account:** **15** (USAJobs key, Adzuna `app_id`/`app_key`),
**20** (Firecrawl), **24** (Builder key onboarding), **33** (Cloudflare domain), and
**14**'s optional Socrata token — 14 can run anonymously and throttled meanwhile.

**A real cycle:** 24 depends on 33 for the tunnel; 33 depends on 24 and 32. 33 has to
split — tunnel before 24, pipeline/app split after 32.

## Findings later tasks must not inherit

Each of these is a documented claim that is **wrong about the code as it now stands**.

- **`title_exclude` overrides the description-first gate, and nothing in task 10's
  documentation says so.** `relevance.py:232-234` applies it to *both* the title and the
  description path, so a posting whose description passes both required groups is still
  rejected on a title term. Anyone reading `docs/pursuit-description-gate.md` as "the
  gate now reads descriptions" will be wrong about 1 of every 15 good postings.
  **AMENDED 2026-07-29: "silently" was wrong.** It is documented as deliberate at
  `relevance.py:227-231` and pinned by `test_relevance.py:203-211`. The behaviour is real
  and the consequence is real; the framing is not. **The fix is to edit the LIST.**
  Changing `tier_sql` so `title_exclude` gates only the title path would break the pinned
  test and re-admit the 1,906 rows `config/relevance.json:121` counts. And the exclusions
  are load-bearing on the description path specifically: the seniority block is the only
  thing standing between it and every senior requisition at an AI employer.
- **The mock-acceptance harness is a CONSUMER of the gate, not a neutral instrument.**
  `tools/mock-acceptance.py:314-331` `importlib`s the gate out of
  `migrate_pursuit_profile.py` — not from the database, and it never reads the `pursuit`
  row at all (it installs its own copy into the scratch schema, `:272-311`). **A green mock
  run does not mean production changed**, and moving the gate to a config file without
  repointing that function leaves the harness measuring the old object while reporting "no
  change". HANDOFF presented `--dry-run` as free re-measurement; it is free, and it is
  measuring whatever the migration module holds.
- **Candidate gate terms ranked on the mock corpus rank the OPPOSITE way on the live
  corpus, and the mock corpus scores the bad ones as free.** Measured 2026-07-29:
  `we provide … training` +17 live rows, `we (will) train` +5, `preferred but not required`
  +5, `experience … is a plus` +123 — all four admitting senior engineering requisitions at
  AI employers, and `\ywe train\y` matching OpenAI's *"we train models"*. On the mock corpus
  all four add **zero** false positives, because every intended-bad mock posting carrying
  that phrasing has no AI vocabulary at all. **That is a property of a corpus written to a
  specification.** Any vocabulary decision taken on `mock-acceptance.py` alone is untrusted;
  compile the candidate through `relevance.tier_sql` against the live table before shipping
  it. See step 0.
- **Step 0's cost caution pointed at the wrong risk.** "Widening the gate widens the
  extraction queue — check the volume against `extract.py`'s drain" is answered and was
  never the constraint: the planned fix is **+11 rows**, `extract.remaining` 2 → 13, under
  half of one `EXTRACT_BATCH_SIZE=40` batch. Extraction has ~15x headroom
  (`EXTRACT_DEADLINE_SECS=3600` × 3 workers ≈ 1,260 calls/hour against 43–80/day intake),
  and `drain_loop` (`extract.py:1125-1159`) lifted the old 40/day ceiling. **A widened gate
  is priced by the one-time backlog it creates, not by steady state**, and the real cost is
  precision.
- **Fixing the gate does not meaningfully change what task 29's labellers see.** +11
  postings on an 869-row pool is **+1.3%**. Doing it first is still right — the defect is
  real, the fix is cheap, and a labelling session run through a knowingly-broken gate is
  wasted — but step 0's ordering rationale implies a recovery it does not deliver, and it
  moves the GATE 2 "≥200/day" question not at all.
- **48.3% is a recall figure against a corpus built to contain the failure mode it
  measures.** The best new term matches **19 rows anywhere** in 13,447 open live postings.
  The fix is still correct, but "recall was 48.3% and is now 89.7%" is a statement about
  the mock corpus and must be written that way wherever it is quoted.
- **`migrate_profiles.py` does NOT leave criteria and persona untouched.** It overwrites
  both wholesale from the files on every run (`:124-128`, `:256-261`), and `--persona-file`
  defaults to `config/persona.json`, **the author's tech persona** (`profiles.py:221-224`).
  Only `relevance_json`, `daily_narrative_budget` and `active` are preserve-on-absent
  (`resolve_preserved`, `:112-145`). Running it against `pursuit` without both file flags
  writes the wrong persona. It is safe for step 0's commit 4 only because both files were
  confirmed dict-equal to the stored values first — **that is a pre-flight check, not a
  property of the script.**
- **`ENTRY_LEVEL` is a title vocabulary and the pursuit gate applies it to descriptions.**
  Measured: it fails on 14 of 15 rejected good postings. The gate is conjunctive
  (`migrate_pursuit_profile.py:216,229`), so this single group is what makes recall 48%.
- **HANDOFF named the wrong three tests for the `strip_html` fix.** It predicted
  `test_row_identity.py:161-168` would need its digest updated; the digest **did not
  move**. The two that actually broke were task 35's *gate* tests, red because fixing
  the stripper cleaned the fixture the gate is tested against. **Fixing a defect can
  silently disarm the alarm built for it** — that generalises well beyond this case.
- **`sklearn` is not installed and `tools/learned-ranker-probe.py` does not run on a
  clean checkout.** `requirements.txt` is `psycopg[binary]` alone; the probe imports
  `sklearn.metrics` at `:133`. Any figure quoted from it was produced in an environment
  this repo does not describe. Stdlib `average_precision` / `precision_at_k` now live in
  `evals/metrics.py:260+` and are verified against brute-force enumeration over every
  tie-break permutation.
- **`tools/mock-acceptance.py` mislabels fields absent from the answer key.** It prints
  `n/d = the key says the posting does not determine this field` for `tech_stack`,
  `comp_*`, `employment_type`, `visa_sponsorship` and `years_experience_max`, which the
  key simply does not cover. Cosmetic — no number is affected, `POOLED` = 440 is exactly
  the nine keyed fields — but it reads as a judgement that was never made.

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
- **This file's own browser-DOM query was wrong, and its number was wrong.** The
  `LIKE '%data-testid=%' OR LIKE '%pointer-events-auto%'` query recorded here found
  **3**; there were **8**, and that predicate misses both `google_jobs` rows and both
  Tailwind-only greenhouse rows, which leaked class names and no `data-` attribute.
  Superseded by `303f7b9`. A marker blocklist is the wrong shape for this — see the
  measurement in `DECISIONS.md`.
- **`entry` is not a seniority value.** Task 13's file asks for it; it is in neither
  `extract.SENIORITY` (`extract.py:205-206`) nor `match.SENIORITY_ORDER`
  (`match.py:65-66`), and `match.py:152-154` would drop it **silently**. Anything
  proposing an `entry` target is proposing a `FACTS_VERSION` bump.
- **`migrate_profiles.py` used to overwrite what it was not given.** `relevance_json`,
  `daily_narrative_budget` and `active` were all written from flag defaults, so a
  routine re-run against `pursuit` would have nulled the cohort gate and switched on
  paid LLM scoring. Fixed in `fa2d7a7`; any document describing a bare
  `migrate_profiles.py --apply` as safe predates that.
- **`strip_comments()` drops only TOP-LEVEL underscore keys.** Nested `_comment`
  documentation reaches the database. Both behaviours are now pinned by test, so
  "comments never reach the DB" is false as stated.
- **`score.py`'s "the login path calls it directly" was false.** `run_for_profile`'s
  docstring claimed a webapp login triggers narrative generation, which is where the
  "cost tracks engagement, not registration" model comes from. **Nothing under
  `webapp/` imports the module**; `main()` is the only caller. The cost model is
  documented and unbuilt. Corrected in `d18ea54`, reasoning kept — but any plan
  costed on "narratives are written at login" is costing a thing that does not exist.
- **`strip_comments()` is not merely top-level-only for the persona — the persona
  never passes through it at all.** `migrate_profiles.py` hands
  `load_persona_file()` straight to `upsert` and strips only *criteria*. So
  `config/persona.json`'s `_comment` and `_profile_comment` are in the database
  today. This is why `persona_sha` digests five named keys rather than the blob.
- **A nested `_comment` inside `persona.buckets` does not leak, it CRASHES, and it
  takes the whole batch.** `build_prompt` does `(b or {}).get('description')`; a
  string value raises `AttributeError` into `score_one_job`'s blanket handler, so
  every job in the batch returns `ERRORED`. That is D16 with a different key.
  Guarded in `d18ea54`. Documenting a persona the way every other config in this
  repo is documented would have taken the nightly run down.
- **A re-scoring bill quoted from `count(job_scores)` is 27% too high.**
  `select_shortlist` reaches a posting only through `job_matches` and only while
  `status = open`, so the payable number is **1,018, not 1,293** — and no flag
  routed through that path can ever reach the other 275.
- **Line numbers in this file drift.** `job_scores`' DDL is at `schema.py:342-361`,
  not the `328-343` recorded above; the re-scoring anti-join is `score.py:262-263`,
  not `242-244`. Both were ~15 lines out within one session. **Cite `file:line` and
  then re-read the line before trusting it.**

## The plan-level question: GATE 2 is the one at risk

`MASTER-PLAN-pursuit.md:251` sets **GATE 2 — ≥200 new Pursuit-relevant postings/day
across sources** as the exit condition for the sourcing phase. That gate now looks
unreachable by the sources the plan names, and it is the only gate whose premise
this run has actually damaged.

**What the named sources have measured:**

| source | plan estimate | measured |
|---|---|---|
| 14 NYC Open Data | 20–60/day | 1.8 |
| 18 Workday | 80–200/day | ~1 at four tenants (~12 extrapolated to fifty) |
| 19 JSON-LD | 30–60/day | ≤1.1–2.3 ceiling — **dropped** |
| 15, 20, 21 | 65–160/day combined | **unmeasured, same method, same table** |

The three Phase 3 sources that have been measured contribute roughly **3/day
between them**. The plan needed those three plus JSON-LD to carry most of the 200.

**What the cohort gate's total intake is: not yet cleanly measurable, and that is
itself worth recording.** Every day in the table so far carries a backfill
component — 7/24 is the initial 11,000-row load (greenhouse 7,182 + ashby 2,561),
and 7/28's 1,802 includes this session's NYC Open Data and Workday loads. The two
least-contaminated days read **0 and 28** cohort-relevant postings; the least-bad
four-day window averages ~27/day and is still not clean.

**Do not quote a steady-state figure until a clean window exists** — a naive
`count/days` over the current table returns ~130/day, which is almost entirely the
initial load and would be wrong by an order of magnitude in the flattering
direction. **The first job of the next sourcing session is to measure this
properly**, over a window with no backfill in it. Until then the honest statement
is: tens per day against a gate of 200.

**A CLEAN WINDOW CANNOT BE MINED BACKWARD, AND THAT IS NOW SETTLED** (measured
2026-07-29 while doing other work; no tool was built, so this is a finding, not a
deliverable). Rows by `first_seen` × platform: 7/24 → 11,000 (the initial load),
7/25 → 72, 7/26 → 355, 7/27 → 90, 7/28 → 1,802 (NYC Open Data 1,030 + Workday 330
one-time loads). Pursuit-relevant by day: **803 / 0 / 28 / 0 / 80**.

The two days this file previously called "least contaminated" — 7/25 at 0 and 7/27
at 28 — are not clean steady-state days. The platform breakdown says why: on both,
the ATS step contributed almost nothing (7/25 is builtin-only). **They are days the
pipeline mostly did not run**, so averaging them understates as badly as including
7/24 overstates. There is also **no run-log table**, and `run-daily.py`'s
`upsert-summary` line landed *after* the last scheduled run, so no history exists to
reconstruct from — `first_seen` + `platform` is the entire available signal, and
nothing records ingest provenance per row.

**So the window has to be collected forward. The first honest night is 2026-07-29,
which has now run** (`max(first_seen)` 2026-07-29T04:08:38, 148 postings closed).
Both new sources are in `STEPS`, so from here their contribution is genuine
incremental intake. Count complete nights from 7/29 and do not include it with any
earlier day.

**Settle the definition before measuring: "Pursuit-relevant" is ambiguous across
three predicates that differ by an order of magnitude** — the relevance gate
(`tier <= 2`, which is what `docs/pursuit-description-gate.md`'s 13.2/day used),
`job_matches` above `MATCH_FLOOR` (144 rows), and the `job_facts` entry-level ∧
`uses_ai_tools` intersection (55 of 859). GATE 2's wording does not say which, and
the answer changes whether the gate is missed by 10x or 100x. Note also that all
three prior per-day figures in this repo used **`posted_at_ts`**, not `first_seen`;
a forward-collected intake measurement is a deliberate departure and must say so.

**This does not invalidate the plan; it relocates the risk.** Phases 1 and 2 —
the pipeline retarget — are essentially done and their premises held. What has not
held is the assumption that the long tail is reachable by adding feeds. Four
independent measurements now say the same thing from four directions: task 10's
gate is 90% junk after improving precision to 10.0%; task 18 found *zero* AI
vocabulary in 329 Workday postings from a hospital, a bank and a retailer; task
19 found 1 of 35 target employers publishing structured data; and task 12 found
44% of first-time cohort extractions unclassifiable even at 26 archetypes.

**The question that needs an answer before more ingest is built** is not "which
source next" but whether ≥200/day of entry-level AI-adjacent NYC postings exists
to be found at all. If it does not, GATE 2 should move rather than be chased, and
the plan's Display decision (*"Tracks + reasoning, no 0–100 score surfaced"*)
matters more than its sourcing decisions — because with a small corpus, ordering
quality beats volume. That is a call for the repo owner, not for an implementer.

## Recommended next steps

**Task 29 is still the whole critical path and still the one thing in this plan that
cannot be done by an agent.** But the order below changed: **the gate fix now goes
first**, because it is unblocked, cheap, and the largest measured loss in the pipeline —
and because every posting the gate rejects is one task 29's labellers will never be
shown. **Measured since, and the rationale needs qualifying:** the fix adds 11 postings to
an 869-row pool, **+1.3%**, so it does not meaningfully change what the labellers see. It
still goes first — the defect is real, the fix is cheap, and a labelling session run
through a knowingly-broken gate is wasted — but do not expect it to move GATE 2.

0. **Fix the relevance gate. PLANNED AND MEASURED 2026-07-29 — IMPLEMENT IT.** Measured
   48.3% recall on the mock corpus, 15 of 29 intended-good postings rejected (see the two
   sections at the top of this file, and `docs/mock-acceptance.md`). The plan below is
   measured end to end against the **live** corpus; the numbers are in § *the gate fix is
   planned and measured*. **Nothing here is a guess except where it says so.**

   **The whole change is config.** No change to `relevance.py`, no change to `tier_sql`,
   no change to `config/relevance.json`.

   **(a) Split the entry-level vocabulary; do not widen it.** `ENTRY_LEVEL`
   (`migrate_pursuit_profile.py:133-145`) becomes `ENTRY_LEVEL_TITLE` — the same 11 nouns,
   byte-identical — and `ENTRY_LEVEL_DESCRIPTION`, **a strict superset**: those same 11
   nouns plus three phrases. `title_include` keeps the title group, so the title path can
   only be unchanged and the description path can only gain rows. Superset by
   construction, the same argument the `strip_html` fix used.

   **This is not a stylistic preference and the alternative is catastrophic.** Measured:
   the description group with the phrases *instead of* the nouns takes the live gate from
   **869 rows to 39**, because the conjunction needs both signals in one field and
   descriptions restate their own title 81% of the time (`_title_include_note`). One
   shared widened list gives 873 against the split's 873 — identical, because titles do
   not contain sentences — so it buys nothing and gives up a provable invariant.

   The three terms, Postgres dialect, all three already executed against live Postgres so
   `ARE` validity and `\y` behaviour are confirmed (2.1–3.1s vs 1.8s baseline over 13,447
   rows). Raw live match counts, for the `_comment`: **19 / 0 / 11**.

   ```
   \yno\y[^.;:]{0,40}\y(?:experience|background|license)\y[^.;:]{0,25}\y(?:required|needed|necessary)\y
   \ydoes not require\y[^.;:]{0,40}\y(?:experience|background)\y
   \ytraining (?:is |will be )?provided\y
   ```

   - **`degree` is deliberately absent** from the first noun set. *"No engineering degree
     required"* pulled in a Scale AI consultant role and recovers nothing; the persona
     treats no-degree as a **constraint**, not a seniority signal.
   - **The window is `{0,40}`.** `{0,30}` loses mock_025's *"No insurance license or prior
     claims experience required"*. `[^.;:]` stops it crossing a sentence or a bullet colon.
   - **The alternations are wrapped in `(?:…)`** because `relevance._alternation`
     (`:112-120`) joins terms with a bare `|` and `--dead` tests each term standalone — a
     term with a top-level `|` is two terms wearing a trenchcoat.
   - **Term 2 matches 0 live rows and is kept on purpose.** Same standing as `\yattorney\y`
     under `config/relevance.json`'s `_dead_patterns_note`: verified against mock_012, a
     working pattern waiting for its first live posting. `--dead` will report it. Do not
     delete it on that report alone; do check it is still `\y` and not `\b`.

   **(b) `title_exclude`: narrow one term, decide one, leave three, record the zeros.**
   Rows each of the six inherited terms alone is blocking, live, under the widened
   description group:

   | term | rows blocked | what they are |
   |---|---:|---|
   | `\ycustomer success\y` | **12** | 6× CS Associate/Specialist (Datadog, AlphaSense, EliseAI), 5× Manager/CSM, 1× Applied AI Specialist |
   | `\yexecutive assistant\y` | **9** | EA at Databricks, Scale AI, Braze ×2, Figma ×3, Ramp |
   | `\yfacilities\y` | 1 | `Critical Facilities Technical Instructor \| Per Scholas` |
   | `\yoffice manager\y` / `\ywarehouse\y` / `\ydriver\y` | **0** | — |

   - **`\ycustomer success\y` — narrow, do NOT remove.** Removing it imports 5
     `Manager, Customer Success` rows that the seniority block deliberately does not catch
     (`\ymanager\y` was rejected at `:299-307`). Replace the one term with four:
     `\ycustomer success manager\y`, `\ymanager, customer success\y`,
     `\yhead of customer success\y`, `\ydirector of customer success\y`. Measured: admits
     exactly the 7 target rows, blocks the 5 manager rows, all four non-dead (120/7/4/1 raw
     title matches). This is also the only thing that recovers mock_045.
   - **`\yexecutive assistant\y` — decide it on 9 read descriptions, not on a paragraph.**
     n=9 is the whole population, so decide it completely rather than sample. The persona's
     `scoring_instructions` name "administrative" as a target, but `honest_gaps` says prior
     seniority does not transfer — an EA at Figma wanting 5 years supporting executives is
     a mismatch even though the function is in scope. **If undecided, ship without it.** A
     relevance list is cheap to widen later and expensive to have widened wrongly.
   - **The three zero-row terms — leave them, and record the zeros.** No measurement can
     decide a term that admits nothing; deciding them is a persona question. Put the counts
     in `_title_exclude_note` so the next person decides with them rather than re-deriving
     them — exactly what `:306-307` already does for `\ymanager\y` and `\ylead\y`.
   - **The seniority block (`:281-286`) is untouched.** `_entry_level_note:211-214` is right
     that it is what catches "Associate Director"; the widened description group makes it
     *more* load-bearing, not less, because it is the only thing between the description
     path and every senior requisition at an AI employer.

   **(c) Move the gate into `config/pursuit-relevance.json`, as a separate no-op commit
   first.** Today the gate is a Python dict inside a migration script that **refuses to
   run** (`migrate_pursuit_profile.py:526-543`, because a re-run would clobber task 13's
   weights), whose own docstring (`:71-78`) tells you to use a different script and a file
   that **does not exist**. Every sibling is already a file. `migrate_profiles.py
   --relevance-file` (`:159-163`) has nothing to point at.

   **Repoint `tools/mock-acceptance.py:314-331` in the same commit.** `cohort_relevance()`
   `importlib`s the gate out of the migration module. **This is the highest-consequence
   edit in the task:** miss it and the harness measures the old gate and reports "no
   change", which reads as *the fix did nothing* rather than *the instrument is looking at
   the wrong object*. Its own docstring at `:286-290` states the invariant.

   **Four commits, and nothing is written to `profiles` until the last.**

   1. **Extract the gate to JSON as a proven no-op.** Byte-faithful dump including every
      `_comment` (`relevance_json` is deliberately *not* comment-stripped,
      `migrate_profiles.py:130-135`); repoint the migration and the harness; extend
      `TestCohortConfigFilesAreImportable` (`test_profiles_migration.py:203-215`).
      **Gate:** `tier_sql` SQL **and** params byte-identical; mock `--dry-run` still
      14/15/10/15; suite ≥1030. **Do not touch the vocabulary here** — a combined change
      makes the mock delta unattributable.
   2. **The description-group superset + the new tests.** **Gate:** mock 26/29 with
      `bad_admitted` unchanged at the same 10 ids; live 869→873; `--dead` shows exactly one
      new dead term; suite green.
   3. **Narrow `\ycustomer success\y`.** **Gate:** live 873→880; the 7 admitted CS rows are
      the Associate/Specialist ones; all four new terms non-dead; mock_045 recovered. The
      `\yexecutive assistant\y` call ships here or not at all.
   4. **The write.**
      ```
      cd backend && (set -a; . ./.env; set +a; python3 migrations/migrate_profiles.py --apply \
          --profile pursuit \
          --persona-file config/pursuit-persona.json \
          --criteria-file config/pursuit-criteria.json \
          --relevance-file config/pursuit-relevance.json)
      ```
      **No `--bump`** — relevance gates extraction, not scoring inputs, so `criteria_version`
      stays 2, `match.py:381` recomputes nothing and existing `job_matches` are untouched.
      **`--persona-file` and `--criteria-file` are mandatory, not optional:** `criteria_json`
      and `persona_json` are overwritten wholesale on every run (`:124-128`, `:256-261`) and
      `--persona-file` defaults to `config/persona.json`, **the author's tech persona**.
      Both files were confirmed read-only to be dict-equal to the stored values — that
      confirmation is a pre-flight step, not a property of the script. **Run it without
      `--apply` first: absence of the criteria WARNING (`:242-249`) is the proof the write
      is criteria-neutral.** If it appears, stop. **Never `--force-placeholders`.**

   **Tests: the suite has ZERO coverage of the vocabulary.** Nothing in the 1030 asserts on
   `AI_VOCAB`, `ENTRY_LEVEL` or the pursuit `title_exclude` — which is exactly why a 48%
   recall defect sat green. New `backend/tests/test_pursuit_gate.py`, five classes, all but
   the last DB-free: shape invariants (the two `AI_VOCAB` copies equal, the description
   group a superset, `params["rel_include2"]` pinned so **the title path is provably
   byte-identical**); regex dialect (no `\b` anywhere, `make\.com`'s dot escaped); **the
   defect itself** — verbatim `description_text` from mock_012/019/022/023/025/029/044/045
   must clear both description groups, which **fails today**; **a sentinel asserting the
   four rejected phrases stay absent**, carrying the live +17/+5/+5/+123 counts in its
   docstring; and one `@skipUnless(scratchdb.available())` class putting ~8 synthetic rows
   through the real `tier_sql`, the only test that exercises the actual Postgres dialect.
   `test_relevance.py` needs **no** changes — its golden is over `config/relevance.json`,
   which this task does not touch.

   **Baseline before you start, read-only, outside the 04:00–05:00 cron window** — the
   nightly fires ~04:08 and is the other agent in the room. `SELECT count(*),
   max(first_seen) FROM jobs GROUP BY status`; `tools/relevance-report.py --profile pursuit`
   (expect **450 / 419 / 12,578**); the same with `--dead`, to tell new dead terms from
   incumbents; `extract.remaining(conn, cfgs)` (expect **2** — `extract.py` has no CLI, so
   this is a five-line throwaway script, and `load_active` returns **only `pursuit`**);
   `criteria_version`, budget, `active` and an md5 of each of the three JSON columns;
   `tools/mock-acceptance.py --dry-run` against
   `backend/data/mock-acceptance-scratch_c1388ee2.json`. **All the live figures above were
   taken 2026-07-29 and the nightly has run since — re-confirm them before attributing
   anything.**

   **Stop conditions, any one of which halts the sequence:** `bad_admitted` moves off 10 on
   the mock corpus; more than one new dead term; live tier ≤2 moves by more than ~30 rows;
   the criteria WARNING appears on the dry run; the suite drops below 1030; `first_seen`
   shows the cron ran mid-sequence (re-baseline, do not attribute).

   **One caution that still stands unchanged.** `relevance.json`'s `_max_tier_note` and the
   entry under "Findings later tasks must not inherit": **`max_tier_to_score = 3` is an
   unconditional pass, not a wider gate**, and is not the fix. It would disable
   `title_include`, `title_exclude`, `company_exclude` and `description_exclude` at once.

1. **Task 29 — the labelling session.** 07's tooling is built and produced zero
   labels by design. The form is at `/v1/label` behind the existing Google SSO.
   What is missing is ~10 Builders and an afternoon. **Two specific questions are
   now waiting on it**, which is new: task 08 asked whether the ops shortfall is
   the title probe over-counting or the extractor under-applying; task 13 asks
   whether its four floor misses — postings at `ai_involvement = 'none'` whose
   employers are AI companies — are the weights being wrong or being right.

   **This is also the only thing that makes re-tuning 13 legitimate.** The weights
   are unfitted by construction and `tools/calibrate-match.py` can sweep them for
   free the moment there is anything to fit against.

2. ~~**`job_scores` has no version key at all.**~~ **DONE, `d18ea54`.** Four
   columns, three of them cache keys, and `persona_version` was built as a
   **content digest (`persona_sha`) rather than an integer** — see `DECISIONS.md`
   for why, and for why `criteria_version` is stored but deliberately excluded
   from the staleness predicate.

   **What a fresh session must not misread:** nothing is stale and nothing was
   re-scored. All 1,293 rows are unversioned, which is a *third state*, not a
   stale one. Re-scoring is opt-in and needs an explicit `--limit`.
   `score.py --stale-report` prices it without a credential.

   **The re-scoring budget question is answered but not spent.** Whoever raises
   `daily_narrative_budget` above 0, or reactivates `tech`, should run
   `--stale-report` first — and note that `profiles.load_one` ignores `active`,
   so `score.py --profile tech` can already reach those rows.

3. ~~**Fix `lib/text.strip_html()`, which task 35 gated but did not repair.**~~
   **DONE this session.** `lib/text.py`'s `_TAG` is now an alternation whose first
   branch treats a double-quoted attribute run as opaque and whose second is the exact
   old pattern — a **superset by construction**, so it can only match where `<[^>]+>`
   already matched and only match further. `HTMLParser` was rejected deliberately:
   `strip_html` must unescape *exactly once* (greenhouse is escaped a level deeper,
   `ingest/ats.py:559-581`) and `convert_charrefs` would decode `&amp;nbsp;` to `\xa0`,
   deleting the guard at `tests/test_ats_descriptions.py:62-70` rather than satisfying
   it. Single-quote and comment handling were implemented, swept over 21,350 markup
   strings from 13,066 live rows, found byte-identical on all of them, and dropped as
   cost without benefit.

   **The defect was worse than "markup leaked".** The old pattern ended a tag at the
   first `>` inside a quoted attribute, so on six greenhouse rows the *rest of the
   posting* was replaced by Tailwind class soup. `migrations/migrate_description_rehash.py`
   rebuilt them from `raw_json`; `tools/audit-description-markup.py` reports **0 rows
   above threshold, from 5**. Two `job_facts` rows extracted from the soup were
   remediated first, in that order, because the reverse leaves clean text with soup-derived
   facts under it. The migration proves its own hash reconstruction by reproducing the
   stored hash on **10,405/10,405 untouched rows** before writing anything.

   **Three tests changed, and one of the three HANDOFF predicted was the wrong one.**
   The stripper test was *inverted* rather than deleted (same cassette, asserting the
   markup is now gone). The two that actually broke were task 35's **gate** tests —
   fixing the source cleaned the fixture the gate is tested against. They were
   re-pointed at input still poisoned after the fix, plus a new
   `test_the_rows_already_written_by_the_old_stripper_are_still_rejected`, because the
   gate still guards 13,000 rows written by the old stripper. `test_row_identity.py`'s
   pinned sha256 **did not move**.

   The four things established before it landed, kept because they are the reasoning:

   - **A fix must be stdlib-only.** `requirements.txt` is `psycopg[binary]` alone,
     deliberately; no bs4/lxml/html5lib/selectolax is installed or vendored. The
     only precedent in-repo is `html.parser.HTMLParser`, used once, in
     `tools/jsonld-probe.py`.
   - **Three tests break BY DESIGN and need deliberate updating, not deletion.**
     `tests/test_row_identity.py:161-168` pins a sha256 of stripper output;
     `tests/test_extract.py:290-300` asserts the markup **is** present and its own
     docstring says it is meant to fail when this lands; and
     `tests/test_ats_descriptions.py:62-70` requires `strip_html` alone to still
     leave `&nbsp;` on double-escaped greenhouse input.
   - **It forces a re-hash.** `description_text` is in `HASH_FIELDS_ATS` and
     `HASH_FIELDS_SHORT`, and `lib/upsert.py` skips rewriting a row whose hash
     matches. `migrations/migrate_ats_descriptions.py` is the precedent — it
     rebuilds `description_text` from stored `raw_json` through the real
     normalizers.
   - **The regression fixture already exists**: replay the
     `ats-greenhouse-domsoup` cassette, which holds a poisoned posting and a clean
     control and refuses to re-record if either crosses the threshold.

   Its
   `<[^>]+>` ends a tag at the first `>`, and modern Tailwind class names contain
   one, so the tag remainder is emitted as prose. Task 35 rejects the result at
   extraction; it does not stop the bytes being stored. New contaminated rows will
   still be ingested. Deliberately scoped out on blast radius — `lib/text.py` is on
   every ingest path — so it needs a change made carefully with the cassettes task
   09 built. `tools/audit-description-markup.py` is the instrument: it swept 13,282
   rows and is the way to prove a stripper change fixes the leak without touching
   anything else.

4. **Task 21 has lost its premise.** It was scoped as "cheap because task 19's
   parser does most of the work." 19 is dropped. Either re-scope it as a
   standalone Idealist parser or measure first — and note that Idealist's
   per-listing expiration date was the good closure case, which survives.

5. **Tasks 15 and 20 need credentials**, and **their estimates come from the same
   table that has now been wrong four times out of four.** Measure before
   building. That is no longer a caution; it is the run's most reliable finding.

6. **Workday will not scale sequentially.** Task 18 costs ~14 min of nightly
   window at **four** tenants at 1.5s apart. `18-ingest-workday-cxs.md:97`
   anticipates ~50. Measured and recorded, not solved.

7. **Task 23, descoped** — but see the reprioritisation argument in
   `DECISIONS.md`: on the evidence **25 is where the 12x yield difference lives
   and it is a config edit**, and **24 is 7,500 searches/month against code
   already written and tested**.

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
the artifacts. That is the norm, not the exception. **Sixteen of sixteen across the run
now**, all five mock-acceptance agents included — and two of them sent idle
notifications *twice*, for work already verified and committed, while a sixth agent
(a planning one) went idle twice and never reported at all, even when asked directly.
Treat the notification as "go look", including the second time, and do not spend turns
chasing a report that may not exist. **Budget for the artifacts being the only output
you will get.**

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

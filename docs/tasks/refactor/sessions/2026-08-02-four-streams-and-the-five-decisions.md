---
kind: record
written: 2026-08-02
generator: none
---

# Session record — 2026-08-01 and 2026-08-02, four streams and the five decisions

**Frozen on write.** This is a `record`: it says what happened on a date, and per
[`../../../DOCS-POLICY.md`](../../../DOCS-POLICY.md) rule 4 it is corrected by a later record
rather than rewritten. That property is the whole reason it is a separate file — see
[task 47](../tranche_eight/47-split-the-entry-point.md), which split it out of `HANDOFF.md`
on 2026-08-02 after that file regrew 397 lines in thirty-six hours with six checks green.

**The text below is unchanged from `HANDOFF.md`;** `git log -p -- docs/tasks/refactor/HANDOFF.md`
reaches it at that path. Its cross-references to *"this file"* and to `§` sections mean
`HANDOFF.md` as it stood on 2026-08-02, and the sections it names are now in
[`../STANDING-GUIDANCE.md`](../STANDING-GUIDANCE.md) or
[`../../../archive/handoff-run-narrative-through-2026-08-01.md`](../../../archive/handoff-run-narrative-through-2026-08-01.md).

### ~~THE CURRENT SESSION IS PHASE 9~~ — **PHASE 9 IS CLOSED. Rolled forward 2026-08-01.**
### ~~**THE PRODUCT / API TRACK IS OPEN AND TASK 27 HAS LANDED.**~~ **27 AND 31 HAVE BOTH LANDED. Rolled forward 2026-08-01.**
### ~~**THE LABELLING NIGHT HAPPENED AND THE REPORT PRINTED** — and the answer is "not yet".~~ Rolled forward 2026-08-02.
### ~~**THE `role_track` GROUPING AXIS HAS THREE INDEPENDENT PROBLEMS, AND THE TREE IS UNCOMMITTED.**~~ Rolled forward 2026-08-02 — **the tree is committed; the three `role_track` problems all stand and are restated under task 30 below.**

### **THE PRODUCT/API TRACK HAS NO SESSION-DOABLE WORK LEFT. 2026-08-02, a THIRD parallel session — `role_track` to the read edge, then four streams.**

> **Everything is committed and all three suites are green.** No count is typed here;
> [`AUDIT.md`](../AUDIT.md) owns the figures and names the command for each. **Read all three
> `Ran N tests` lines** — they moved in three different directions this session.
>
> **What landed, in merge order.** One serial change first, because it moved a surface every
> stream would otherwise have collided on: **`role_track` reaches the read edge** (`DEC-94`)
> — it had been on `job_facts` since task 11 and `jobs_app` never selected it, so it was in
> no response body and every posting bucketed to `UNTRACKED`. Then four worktrees:
> **D18–D21** (per-unit isolation in four ingest scripts and the match stage), **the register
> reconciled** against the code with D69's third residue closed, **task 24's `submission_log`
> report plus D72 and D73**, and **the search screen** — which makes 32 five of six surfaces.
> One new defect, `D74`, ~~open and~~ cosmetic — **fixed 2026-08-02**, and its count had
> gone stale by then: 19 broken anchors when filed, 22 when fixed, because `e79448c` gave
> three more headings a ` — fixed` suffix the same day. `tests/test_defect_register.py`
> now watches it.
>
> **WHAT IS LEFT ON THIS TRACK IS NOTHING A SESSION CAN DO.** 24's deploy half, 33's machine
> half, 32's phone test and its live Google login all need a person, an account or a device.
> `Contribute` is the sixth surface and is blocked on `DEC-84`'s ownership question rather
> than on effort. **Do not open this track expecting to write code.**
>
> **THE PROCESS LESSON, AND IT IS A NEW ONE — the old one was fixed and a different seam
> opened.** Last session's failure was stale worktrees; this session branched all four from
> one printed SHA, handed every stream the floor rather than letting it measure its own, and
> gated in the primary tree after **each** merge. That held: three streams touched
> `docs/ingest/DEFECTS.md` and every rebase applied with zero conflicts.
>
> **What still got through was a duplicate index row.** Two streams were given disjoint
> regions of that file — one owned the index table, one owned `D73` and `D72`'s closure. Both
> obeyed. The merge still produced **two index rows for `D72`, one reading `open` and one
> reading `fixed`**, because "add the missing row" and "close this defect in the table" are
> the same line reached from two directions, and a blank line between them meant git saw no
> conflict. **`audit-docs.py` C5 did not catch it** — C5 forbids defining an identifier twice
> and reads `### D` headings, not index rows. **It was caught by reading the table.** The
> lesson is not "do not parallelise this file": it is that a register's *index* is a single
> shared surface even when its bodies are not, and one stream should own the whole table.
> Recorded under `D74`.
>
> **A second thing worth carrying: a stream's report is not evidence.** One stream's
> broken-anchor count was an overcount (~24 against a measured 19) because it read the list
> instead of computing the slugs; another never sent a report at all and its work was
> accepted only after reverting two of its fixes and watching **12 tests** go red. Both
> streams did good work. Neither claim would have been safe to quote.
>
> ~~**THE PRODUCT/API TRACK IS FOUR TASKS FURTHER ON. 2026-08-02, a second four-stream
> session — 24, 25, 33 and 26's screen, each in its own worktree.**~~ Rolled forward; what
> that session landed is below.

> **Everything is committed and both — now three — suites are green.** No count is typed
> here; [`AUDIT.md`](../AUDIT.md) owns the figures under rule 2 and names the command for each.
> **There is a third suite as of today**: `backend/api/` had zero tests and now has its own,
> run by its own venv, because that venv cannot import what the top level has
> (`DEC-81`). Read all three `Ran N tests` lines, and do not assume the number in front of
> you is the one you want.
>
> **What landed:** the pre-deploy half of **24**, all of **25**, the file half of **33**, and
> **26's onboarding screen**, which closes 26's last DoD item. Thirteen decisions,
> `DEC-81`–`DEC-93`. Two new defects, `D71` and `D72`, both open and both filed by the work
> that fixed their neighbours.
>
> **THE PROCESS LESSON, AND IT IS THE SAME ONE THIS RUN KEEPS RE-LEARNING.** Three of the
> four worktrees were branched twelve commits stale. The agents' own before/after readings
> were internally consistent and therefore looked fine — and meant nothing, because the
> instrument had moved: `audit-docs.py`'s widening to the two declared roots was not in
> those trees, so a "0 findings" there was the *old* check passing. One stream's central
> precedent (`cohort_signal`) did not exist in its tree at all. **Every figure in this
> section was re-measured in the primary tree after merge, and that is the only reason they
> can be quoted.** A reading is only as current as the tree it was taken in.


## A session's read on the five decisions — RECOMMENDATIONS, NOT DECISIONS TAKEN

*Written 2026-08-02 by an assistant session, at the owner's request, after reading the code
behind each row rather than the prose describing it. **Nothing here is a decision.** No
`DEC-` number is allocated and no code was changed on account of any of it; every row above
stays open until the owner closes it. It is here because the rows state what is open and not
what turns on it, and the owner said the implications were the missing part.*

*Figures are cited, not restated — rule 2. Where a recommendation disagrees with a document,
the document is named so the disagreement is checkable.*

### (2) The dedup key — this is a defect wearing a decision's clothes

**The row above, `27-event-schema.md`, `API-CONTRACT-v1.md` and `engagement-events.md` all
frame this as `(profile, job_id)` vs `(profile, job_id, request_id)`. Read the predicate and
that is not the live question.** `webapp/jobs.py:934-937` matches on `prior.profile` and
`prior.job_id` and nothing else. `profile` is the **cohort**. So the first Builder to load
the list writes impressions, and for `IMPRESSION_DEDUP_HOURS` (`jobs.py:95`) every other
Builder who sees the same postings is deduped away — most sharply at the top of the list,
where everyone sees the same rows.

`derive_skips()` reads impressions back out (`jobs.py:836-851`) and its own docstring calls
skips *"the strongest free negative signal available"*. No impression, no skip. **So the
consequence is not "skips are a first-render-per-day signal". It is that the cohort records
roughly one Builder's engagement per posting per day instead of thirty.**

**`jobs.py:891-895` already says this** — *"one Builder's render suppresses another
Builder's impression of the same job for the rest of the window"* — and it never reached
this table. The row was written from the task file, and the task file predates
`app_user_id` existing.

Three keys, not two:

| key | window survives? | cross-Builder | matches the documented sentence? |
|---|---|---|---|
| `(profile, job_id)` — today | yes | **broken** | **no — it suppresses more than the sentence claims** |
| `(profile, job_id, request_id)` | no — a new id per render means no window at all | fixed incidentally | no |
| **`(app_user_id, job_id)`** | yes, per person | fixed directly | **yes** |

**The recommendation is the third, and the argument is that it is not a change of meaning at
all.** The documented contract is *"a list re-render is not new information."* It does not
say *another person's* render is not new information. Today's code is stronger than the
sentence that licenses it, which makes this a defect against the contract rather than a
choice between two readings of it. **Suggested disposition: file it as `D75`** — the
register's next free number — **and fix it, rather than leave it owed as a decision.**

Why it is worth doing before the other open rows: `job_events` is append-only, so every day
it runs adds rows whose meaning has to be caveated permanently. This is the same shape as
task 27's own argument for landing `rank` and `request_id` before the frontend existed.

### (1) The contributor credential — the question is how long `backend/api/` lives

`DEC-84` states this outright and it is the whole decision; the three options are its
mechanics. The reading it offers — (2) if the service is genuinely being revived, (3) if it
is a stopgap for one cohort — is sound, and the population argues for **(3)**: a cohort of
~30 means the owner is the bottleneck for a couple of dozen credentials in total, against
(2)'s permanent cost of a second inter-process dependency and a second secret to rotate, in
a service the repo describes throughout as expected to be deprecated. **Take it with task
24's *"a Builder onboards without the author's involvement"* recorded as deliberately unmet**,
which is the same disposition `DEC-92` took for 33's stated goal.

**Option (1) is the one to avoid**, and not on general principle: it widens a webapp
session-hijack from reads-and-event-rows to minting a contributor credential, and makes two
roles writers of one table, which is the property role separation exists to buy.

### (8) Naming the tracks — ship the slugs, and the reason has changed

`pursuit-persona.json`'s `_no_buckets_comment` blocks naming on task 29's labels, to avoid
inventing a vocabulary before the evidence arrives. **The evidence has now partly arrived
and it argues against spending effort here at all**: the humans answered `no_track_fits` on
a large fraction of the labelled set ([`labelling-report-2026-08-02.md`](../../../labelling-report-2026-08-02.md)
owns the figure). Renaming a nine-value vocabulary that the labellers reject on a substantial
share of postings is polishing the wrong object — the open question the labels raise is
whether nine values are the right **shape**, which is task 30's gated half.

**Recommendation: ship `extract.ROLE_TRACK`'s nine slugs with the hand-written display copy
already in `js/tracks.mjs`, and fold naming into task 30 when its label half unblocks.** This
is the lowest-stakes row in the table and is being carried as though it were not.

### (5) `revenue_commercial` — already decided correctly, but it is hiding a cheap fix

`DEC-64`'s reasoning holds and nothing here disputes it: cost is not the objection, the
objection is that `job_facts` is keyed on `job_id` alone so re-extraction overwrites the
facts the labelled postings were labelled against.

**What is worth acting on is the second half of that argument rather than the first.**
`eval_labels` records `labeller_id`, `round_no` and `labelled_at` and **no `facts_version`**
(`evals/labels.py:365-379`), so nothing marks which extraction a label was formed against.
That absent column is what turns "wait for the labelling to finish" from an inconvenience
into a one-way door — with it, pre-bump and post-bump labels would at least be separable.

**Recommendation: add `facts_version` to `eval_labels` before round 2 (~2026-08-09), not
after.** It is additive, it is free, and it is the difference between this constraint binding
once and binding at every future bump. It does not change `DEC-64`'s answer for today.

### (6) `D31` — this is a chore that was filed as a decision

The register asks whether the retry split across the six ingest scripts is deliberate or an
incomplete migration, and `docs/ingest/weworkremotely.md` already records that nobody could
determine which. **Nothing turns on the answer.** Three scripts get `lib.http`'s retries and
three call `urlopen` directly; `lib/http.py:3-5` cites exactly this failure as the reason the
module exists, and the failures are **counted rather than silent**, which is what keeps it out
of the class the runbook is built around.

**Recommendation: stop calling it a decision.** Either migrate the three scripts to `lib.http`
— session work, no owner input, and the answer to "deliberate or incomplete?" becomes moot —
or mark it won't-fix with the completeness cost stated. It has stayed open because "needs a
decision" reads as blocked when what it needs is an afternoon.

---


**THE ONE FINDING TO CARRY FORWARD FROM THIS SESSION: three separate task files specified a
schema that could not be built as written, and all three failures were the same failure.**
`profile` is the **cohort** — thirty Builders share one — so any table keyed on it can hold
one row per cohort, not one per Builder. Task 28 hit it (`job_events` had no `app_user_id`),
task 31 hit it (one Builder's save read as everyone's), and task 25's sketch hit it again
with `search_query_watchers (query_id, profile, …)`, which makes its own Definition of done
*"one row with two watchers"* unsatisfiable by construction (`DEC-86`). **The next task file
that sketches a per-Builder table should be read with this in hand before it is implemented,
not after.**

**A SECOND PATTERN, ALSO THREE FOR THREE: a privacy control enforced in the value and
defeated by the key.** `DEC-80` (a sub-threshold `cohort_signal` row's *existence* is the
disclosure), `D67` (`visibility` stored correctly, reported cohort-wide by the join), and now
`DEC-87` — a `watcher_count` column on a table the service can `INSERT` into is a count the
service can write, however carefully the fold computes it. In each case the control was
correct one layer up and undone one layer down.

> **NOTHING BELOW IS COMMITTED.** 15 modified files and 6 new ones sit in the working tree.
> The natural split is four commits along stream lines. **Take a `git status` before
> anything else** — a session that starts by editing will merge two sessions' work into one
> unreviewable diff.
>
> **Suites, measured after all four landed: `backend` has exactly one failure; `webapp` is
> green.** No count is typed here — [`AUDIT.md`](../AUDIT.md) owns that figure under rule 2, and
> per rule 3 the reproducible answer is the `Ran N tests` line of
> `cd backend && python3 -m unittest discover -s tests`. Both suites grew; run them and
> compare, do not trust a number. *(This paragraph typed both counts on its first draft and
> check C4 caught it within the minute — which is the second time that check has caught a
> restatement in the hour after it landed.)*
> **The one failure is deliberate and owner-approved** —
> `test_docs_policy.TestPolicyBaseline.test_findings_are_a_subset_of_the_declared_baseline`,
> red because `audit-docs.py` was widened to scan `.claude/CLAUDE.md` and the root
> `README.md`. Tasks [45](../tranche_seven/45-declare-kind-on-the-roots.md) and
> [46](../tranche_seven/46-sentence-scope-the-c4-lookahead.md) clear it. **Do not silence it by
> declaring the four findings** — the baseline is *pruned, never grown*.
>
> **What landed:** `job_events.app_user_id`, closing **D66, D67 and D68**; the frozen
> contract fixtures in `frontend/`; the doc-policy widening; and an n=115 `role_track`
> selfcheck.

**THE ONE FINDING TO CARRY FORWARD: task 30's "group by `role_track`" display now has three
independent problems, none of which was known on 2026-08-01, and they were found by three
different streams that were not looking for each other's answers.**

1. **The axis is unstable at exactly the boundary that matters.** `role_track` `agree2`
   **88.7%** [81.6–93.3] at n=115 — but **13 of 115 (11.3%, [6.7–18.4]) changed whether the
   posting belongs to any track at all** between runs, against only 6.1% moving between two
   *named* tracks. Nearly two thirds of the instability is the classifiable/not boundary.
   [`../../ingestion_tests/selfcheck-n120-2026-08-02.md`](../../../ingestion_tests/selfcheck-n120-2026-08-02.md)
   owns those figures.
2. **The humans reject the vocabulary on about half the set** — `no_track_fits` on 15 of 36.
   [`../../labelling-report-2026-08-02.md`](../../../labelling-report-2026-08-02.md).
   **It is NOT the same quantity as (1)** and neither bounds the other: 42% is a
   *prevalence*, 11.3% an *instability*. A model answering `null` always would score 100%
   and 0%.
3. **The track vocabulary does not exist in code.** `API-CONTRACT-v1.md`'s only example,
   `ai_operations`, is a `role_archetype` value in `config/pursuit-criteria.json` — not a
   track. The only track vocabulary anywhere is `score.TRACKS`, Title Case. `frontend/`'s
   fixtures slugify it and flag the choice as task 32's, unresolved.

**A THING THAT WILL BITE THE FRONTEND AND IS NOT IN THE CONTRACT:** `match_reasons`,
`tech_stack`, `risk_factors` and `key_technologies` come back as **JSON strings, not arrays**
— TEXT columns holding `json.dumps(...)` (`match.py:526`, `extract.py:755`,
`score.py:851-853`), and the endpoint parses nothing. `why.risk_factors` is a real array in
the contract, so this is invisible there. `frontend/README.md` records it.

**The first `evals label report` is [`../../labelling-report-2026-08-02.md`](../../../labelling-report-2026-08-02.md),
and the one thing to carry out of it is that a measurement can arrive and change nothing.**
The ceiling — two people on the same posting — came back **below** the model's own floor on
all five fields, which means a model score has nothing to be read between. Do not tune on
it, do not quote a cell from it without its n, and do not treat task 30 as unblocked. Every
input is committed and the report is a pure function of three files, so re-run it rather
than trusting this paragraph.

**Tranche seven is complete: tasks 36–44, ending `b8c2943`.** ~~Nothing in `docs/` is the
next session's work.~~ **The owner chose the product/API track. Task 27 — the position
instrumentation — is done, and so is task 31.** 27 was the right first move for a reason
worth keeping: it is the only work in the plan that **cannot be backfilled**, because
`rank` and `request_id` describe a render that is over the moment it happens.

| track | tasks | what it needs |
|---|---|---|
| **the labelling night** | 30, then 13's weights and 12's next bump | ~~a second labeller for about twenty minutes; no session can do this~~ **DONE 2026-08-02 — and it did not unblock them.** The report prints ([`../../labelling-report-2026-08-02.md`](../../../labelling-report-2026-08-02.md)) and **the ceiling came back BELOW the floor on all five fields**, on 6–10 items each. What these tasks need is a *usable* ceiling: more labellers on the **same ten** overlap rows (more postings do nothing), round 2 ~2026-08-09, and an n=120 selfcheck covering `role_track`. Only the last is a session's to run |
| **the product / API surface** | ~~24, 25, 26, 27,~~ ~~24, 25, 26, 28, 31, 32, 33~~ ~~**24, 25, 26, 28, 32, 33**~~ **32's search screen, and the machine half of 33. Nothing else on this track is a session's work.** 27, 31, 28 and 26 are done; 24, 25 and 33 each landed the half a session can do and each named what remains. The search screen is now **unblocked** — task 25's tables and its six routes exist, and 26's stream left `frontend/js/app.mjs` with a `ROUTES` table a screen slots into with one row and one `<a>`, asserted against the tab list so adding one and not the other goes red | **27 and 31 are done.** The rest is unblocked apart from ordering, ~~**except 28 — see the D66/D67 note below, which is new and is a real blocker.**~~ **and 28 is now the LEAST blocked of them, not the most — its column landed in `3f4f88e`.** **Audit the premises first:** they were checked on 2026-07-31 and several were stale, and **~~two~~ FIVE dependency arrows have now been found wrong, and two of them are cycles** — 27 declared *"Depends on: 26"* while 26's own DoD needs 27's `visibility` column; 31's *"Depends on: 27, 26"* needed nothing 26 builds; **24 ↔ 33** each declared the other; **26 ↔ 32** each declared the other; and **25 → 24** is contradicted by 24's own file at `:92-94`. All five corrected in the task files 2026-08-02. Corrections are also in [`API-CONTRACT-v1.md`](../API-CONTRACT-v1.md), **which is a specification and not a description of the shipped API** |

**Three things a session picking up this track next must not re-derive.**

1. **`bucket` gates the rest of the list payload, and `bucket` is task 30, which is gated on
   the labelling night.** `API-CONTRACT-v1.md`'s *"No 0–100 score appears anywhere"* cannot
   be honoured until then — removing `match_score`/`fit_score`/`min_score` first would leave
   the API unable to express relevance at all. **It is a deferral with a named blocker, not
   an open question**, and it is recorded as such in the contract.
2. **One decision is genuinely open and it is the owner's**: the impression dedup is keyed
   `(profile, job_id)` and not `(profile, job_id, request_id)`, so a second render of the
   same list inside 24 hours writes no impressions — and skips derive from impressions.
   **Skips are a first-render-per-day signal.** The fix is one line; the cost is changing
   the documented meaning of *"a list re-render is not new information"*. Recorded in
   `27-event-schema.md` § *What the work turned up*, the contract, and
   `docs/ingest/engagement-events.md`.
3. ~~**`job_events` has no `app_user_id` column, and that now blocks task 28.**~~ **CLOSED
   2026-08-02 by `3f4f88e`, and this is the one blocker on the track that was REMOVED
   rather than argued away.** Found by task 31, 2026-08-01. The table was keyed
   `(profile, job_id)` and thirty Builders share `pursuit`, so **no query over it could
   count Builders** — only rows. *"4 Builders saved this"* is 28's entire deliverable and
   was unanswerable from that table. Two shipped defects came from the same cause: the list
   resolved `seen`, `dismissed`, `applied` and `saved` from `job_events` by profile, so one
   Builder's save read as everyone's. **Task 31 fixed `dismissed` and `saved`** by moving
   them to `builder_job_state`; **`seen` and `applied` were
   [D66 and D67](../../../ingest/DEFECTS.md)**. D67 was the sharp one — an application is
   `private` in the event row and was cohort-wide in the response body, so the control was
   enforced in the column and defeated in the join. **It was invisible at one Builder and
   wrong at two**, with no error and no code change on the day it turned.

   **`app_user_id TEXT` landed on `job_events`** (`../../../backend/schema.py:678`,
   nullable and unbackfilled, index at `:703`), and **D66, D67 and D68 are all closed**.
   Three things the column does *not* settle are now recorded in
   [`tranche_five/28-cohort-aggregation.md`](../tranche_five/28-cohort-aggregation.md) rather
   than here: `builder_job_state` is the webapp's and a nightly compute cannot read it;
   `save`/`unsave` are both events so a distinct count over `save` is wrong; and NULL rows
   must be excluded rather than counted as one phantom Builder.

   **The hole that survives is the write path, not the read path.** The impression dedup
   key is still `(profile, job_id)`, so one Builder's render can suppress another's
   impression of the same job for 24 hours — `seen` is per-Builder when read and
   cohort-wide when written. **That remains the owner's open decision**, and it is now
   *actionable* rather than hypothetical because the column exists. It was examined on
   2026-08-02 and deliberately not taken.

~~**Where a fresh session on this track should look first, and it is a suggestion rather
than a finding.** Task 31 …~~

> **Struck 2026-08-01: task 31 is done, and the suggestion's open question is answered.**
> It asked whether 31's declared dependency on 26 was real. **It was not** —
> `builder_job_state` is keyed `app_user_id`, `app_users.id` and `User.id` both already
> exist, and nothing 31 builds reads `builder_profiles`, `parent_profile`, config
> inheritance or onboarding. That is **two arrows now found wrong in this tranche and both
> pointed at 26**, which is worth carrying forward as a habit rather than a conclusion:
> check the arrow, and do not assume the rest are wrong either.

**Where a fresh session on this track should look first.** Tasks **24, 25, 26, 28, 32** and
**33** are what is left. **32 is the one everything user-facing is actually waiting on**,
and `frontend/` still holds one `.gitkeep` — it is also what task **26** is really blocked
on, per that file's own correction: 26 needs a screen, not a schema. **28 is the one to
check the premises on hardest**, for the reason in point 3 above.

**Read [`README.md`](../README.md)'s status column for what is done — do not trust a count,
including a count you just ran.** The instrument [`AUDIT.md`](../AUDIT.md) names for it was
itself wrong until 2026-08-01: `grep -c '| done |'` misses the two rows that spell it
`| **done** |`, so it reported 29 where the file holds 31. Corrected there.
~~Task 23 reads `todo` and its own row says descoped; that row is worth correcting before
anyone plans against it.~~ **Corrected 2026-08-02, and the two words were never in
conflict:** `descoped` is a decision about scope (`DECISIONS.md`), `todo` is the state of
the work, and `backend/serp/` does not exist. The row now says which is which.

~~**One rule 7 gap is open and is not a task.** `audit-docs.py` walks `docs/` only, so
`.claude/CLAUDE.md` and the root `README.md` are declared reachability roots for C2 and are
scanned by **no other check, C4 included** — and both carry figures. Widening `docs_files()`
to include the declared roots is the obvious next check and is unwritten. Until it is, **a
figure in `.claude/CLAUDE.md` is on the honour system**, and it is the first thing every
session reads.~~ [`AUDIT.md`](../AUDIT.md) § *What is open* has the argument.

> **CLOSED 2026-08-02, and it landed red on purpose — 4 findings.** The widening is done and
> the two roots are scanned by C1, C3 and C4. It became two tasks rather than none:
> [`tranche_seven/45`](../tranche_seven/45-declare-kind-on-the-roots.md) for the two real
> findings, [`tranche_seven/46`](../tranche_seven/46-sentence-scope-the-c4-lookahead.md) for the
> two where **C4 is wrong and the file is right** — its compliance lookahead is scoped to the
> physical line and `.claude/CLAUDE.md` is hard-wrapped, so a figure and the metric naming it
> land on different lines.
>
> **The `backend` suite is RED until both land**, on
> `test_findings_are_a_subset_of_the_declared_baseline`. That is the intended state and the
> baseline is still empty — it is *pruned, never grown*. Do not silence it by declaring these
> four; task 45 says so in its own text.
>
> One sentence above was already stale when written: the root `README.md` stopped typing an
> entry-point count in task 37. `AUDIT.md` § *What is open* records that.

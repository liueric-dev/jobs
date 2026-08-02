---
kind: rolling
written: 2026-07-31
generator: none
---

# Handoff — the `docs/tasks/refactor/` run

## START HERE — a fresh session's sixty seconds, ~~2026-07-31~~ ~~2026-08-01~~ **2026-08-02**

*This file had eight "READ THIS FIRST" sections and now has three — the four that
described finished work were archived on 2026-07-31 (task 34, § Orientation), and this
block is the entry point. Everything below is context. Verify anything here before acting
on it — the instrument is named in each case.*

**State, verified 2026-08-02 by `python3 backend/tools/label-findings.py`:**

| | |
|---|---|
| labels | ~~186 rows over 31~~ **271 rows over 36** of `pursuit-v1`'s 200 postings |
| labellers | ~~**ONE**~~ **TWO** (`u_090b0ad12e99` 35 postings, `u_919ad2c305c2` 11), round 1 only |
| `overlap` block | **all ten answered, by both** — which is the entire inter-annotator ceiling |
| `evals label report` | ~~**exits 2, correctly.** Zero of task 29's three quantities exist~~ **PRINTS, exit 0.** All three quantities exist: [`../../labelling-report-2026-08-02.md`](../../labelling-report-2026-08-02.md) |
| suites | ~~a number was typed here~~ **read [`AUDIT.md`](AUDIT.md), which owns the figure** — per `DOCS-POLICY.md` rule 2, and per rule 3 the reproducible answer is the `Ran N tests` line of `cd backend && python3 -m unittest discover -s tests` |

### ~~THE CURRENT SESSION IS PHASE 9~~ — **PHASE 9 IS CLOSED. Rolled forward 2026-08-01.**
### ~~**THE PRODUCT / API TRACK IS OPEN AND TASK 27 HAS LANDED.**~~ **27 AND 31 HAVE BOTH LANDED. Rolled forward 2026-08-01.**
### ~~**THE LABELLING NIGHT HAPPENED AND THE REPORT PRINTED** — and the answer is "not yet".~~ Rolled forward 2026-08-02.
### ~~**THE `role_track` GROUPING AXIS HAS THREE INDEPENDENT PROBLEMS, AND THE TREE IS UNCOMMITTED.**~~ Rolled forward 2026-08-02 — **the tree is committed; the three `role_track` problems all stand and are restated under task 30 below.**

### **THE PRODUCT/API TRACK HAS NO SESSION-DOABLE WORK LEFT. 2026-08-02, a THIRD parallel session — `role_track` to the read edge, then four streams.**

> **Everything is committed and all three suites are green.** No count is typed here;
> [`AUDIT.md`](AUDIT.md) owns the figures and names the command for each. **Read all three
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
> here; [`AUDIT.md`](AUDIT.md) owns the figures under rule 2 and names the command for each.
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

## THE OPEN QUESTIONS, IN ONE PLACE — every one is the owner's, none is a session's

*Assembled 2026-08-02 because they were scattered across this file and three others, and the
next session is going to work through them first. Each row names the document that owns the
full argument; this table is an index and deliberately does not restate the reasoning.*

| # | question | owns it | if you do nothing |
|---|---|---|---|
| 1 | **Who issues a contributor credential?** Grant `jobs_web` INSERT on `jobs_api`'s tables / a server-to-server mint / a request queue the owner services by hand | `DEC-84`, [`24`](tranche_four/24-revive-contributor-api.md) | 24's *"a Builder onboards without the author"* cannot be met, and the page stays unbuilt. **This is a product call about how long `backend/api/` is expected to live** |
| 2 | **Is the impression dedup key `(profile, job_id)` or `(profile, job_id, request_id)`?** One line of code; it changes the documented meaning of *"a list re-render is not new information"* | [`27`](tranche_five/27-event-schema.md), [`API-CONTRACT-v1.md`](API-CONTRACT-v1.md), [`engagement-events.md`](../../ingest/engagement-events.md) | **skips stay a first-render-per-day signal**, and every skip-derived figure quietly means that instead of what it says |
| 3 | **More labellers on the SAME ten overlap rows**, and round 2 (~2026-08-09) | [`AUDIT.md`](AUDIT.md) § *What is open*, [`labelling-report-2026-08-02.md`](../../labelling-report-2026-08-02.md) | tasks **30**, 13's weights and 12's next bump stay gated. More *postings* do nothing — 25 of 36 carry one labeller and add zero to the ceiling. **Task 30's data half is now unblocked and its label half is not**, so this row is the whole remaining blocker there |
| 7 | **The live database is missing task 25's five search objects and `cohort_signal`'s GRANT.** `verify_schema()` fails on exactly those; `manage_app_users.py init-schema` with `JOBS_ADMIN_DATABASE_URL` is the fix | [`33`](tranche_six/33-deployment.md), `backend/webapp/schema_web.py` | **the search screen cannot be exercised end to end at all** — it is proven against fixtures and three suites and against no running server. Nothing else on the webapp is affected today |
| 8 | **Name the tracks, or decide the grouping ships with the vocabulary it has** | `config/pursuit-persona.json`'s `_no_buckets_comment`, [`30`](tranche_six/30-within-track-ordering.md) | grouping works and its headings use `extract.ROLE_TRACK`'s nine slugs with hand-written plain-language copy. The persona config records that `score.TRACKS`' five names "do not describe this population" and makes naming task 30's — **building the mechanism was ungated; choosing the names is not** |
| 4 | **The machine half of 33** — Cloudflare account and `cloudflared login`, the OAuth redirect URI, `systemctl --user enable`, an off-machine backup destination, and **the one verified restore** | [`33`](tranche_six/33-deployment.md) § the command list, [`RUNBOOK.md`](../../RUNBOOK.md) | nothing is reachable by a Builder, and **there is no proven backup** — the script and its verify timer are written and have never run |
| 5 | **Apply the `revenue_commercial` archetype?** Proposed and deliberately unapplied | `DEC-64`/`DEC-65`, [`11`](tranche_two/11-archetype-superset-role-track.md) | `role_archetype = other` stays where it is. It is a `FACTS_VERSION` bump and `pursuit-v1` is mid-labelling, which is why it waits |
| 6 | **`D31`** needs a decision, not a fix | [`DEFECTS.md`](../../ingest/DEFECTS.md) | stays open, correctly |

**Two of these have moved since they were written and the movement is easy to miss.** (3) is
no longer *"get a second labeller"* — that happened, the report printed, and **the ceiling
came back below the model's floor on all five fields**, so what is needed now is *overlap*,
not volume. And (4) is no longer blocked on a decision — `DEC-91` took the Cloudflare-vs-
Tailscale call and `DEC-92` took the stays-on-the-home-box call; what is left is purely
account access and a person at a terminal.

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
> green.** No count is typed here — [`AUDIT.md`](AUDIT.md) owns that figure under rule 2, and
> per rule 3 the reproducible answer is the `Ran N tests` line of
> `cd backend && python3 -m unittest discover -s tests`. Both suites grew; run them and
> compare, do not trust a number. *(This paragraph typed both counts on its first draft and
> check C4 caught it within the minute — which is the second time that check has caught a
> restatement in the hour after it landed.)*
> **The one failure is deliberate and owner-approved** —
> `test_docs_policy.TestPolicyBaseline.test_findings_are_a_subset_of_the_declared_baseline`,
> red because `audit-docs.py` was widened to scan `.claude/CLAUDE.md` and the root
> `README.md`. Tasks [45](tranche_seven/45-declare-kind-on-the-roots.md) and
> [46](tranche_seven/46-sentence-scope-the-c4-lookahead.md) clear it. **Do not silence it by
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
   [`../../ingestion_tests/selfcheck-n120-2026-08-02.md`](../../ingestion_tests/selfcheck-n120-2026-08-02.md)
   owns those figures.
2. **The humans reject the vocabulary on about half the set** — `no_track_fits` on 15 of 36.
   [`../../labelling-report-2026-08-02.md`](../../labelling-report-2026-08-02.md).
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

**The first `evals label report` is [`../../labelling-report-2026-08-02.md`](../../labelling-report-2026-08-02.md),
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
| **the labelling night** | 30, then 13's weights and 12's next bump | ~~a second labeller for about twenty minutes; no session can do this~~ **DONE 2026-08-02 — and it did not unblock them.** The report prints ([`../../labelling-report-2026-08-02.md`](../../labelling-report-2026-08-02.md)) and **the ceiling came back BELOW the floor on all five fields**, on 6–10 items each. What these tasks need is a *usable* ceiling: more labellers on the **same ten** overlap rows (more postings do nothing), round 2 ~2026-08-09, and an n=120 selfcheck covering `role_track`. Only the last is a session's to run |
| **the product / API surface** | ~~24, 25, 26, 27,~~ ~~24, 25, 26, 28, 31, 32, 33~~ ~~**24, 25, 26, 28, 32, 33**~~ **32's search screen, and the machine half of 33. Nothing else on this track is a session's work.** 27, 31, 28 and 26 are done; 24, 25 and 33 each landed the half a session can do and each named what remains. The search screen is now **unblocked** — task 25's tables and its six routes exist, and 26's stream left `frontend/js/app.mjs` with a `ROUTES` table a screen slots into with one row and one `<a>`, asserted against the tab list so adding one and not the other goes red | **27 and 31 are done.** The rest is unblocked apart from ordering, ~~**except 28 — see the D66/D67 note below, which is new and is a real blocker.**~~ **and 28 is now the LEAST blocked of them, not the most — its column landed in `3f4f88e`.** **Audit the premises first:** they were checked on 2026-07-31 and several were stale, and **~~two~~ FIVE dependency arrows have now been found wrong, and two of them are cycles** — 27 declared *"Depends on: 26"* while 26's own DoD needs 27's `visibility` column; 31's *"Depends on: 27, 26"* needed nothing 26 builds; **24 ↔ 33** each declared the other; **26 ↔ 32** each declared the other; and **25 → 24** is contradicted by 24's own file at `:92-94`. All five corrected in the task files 2026-08-02. Corrections are also in [`API-CONTRACT-v1.md`](API-CONTRACT-v1.md), **which is a specification and not a description of the shipped API** |

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
   [D66 and D67](../../ingest/DEFECTS.md)**. D67 was the sharp one — an application is
   `private` in the event row and was cohort-wide in the response body, so the control was
   enforced in the column and defeated in the join. **It was invisible at one Builder and
   wrong at two**, with no error and no code change on the day it turned.

   **`app_user_id TEXT` landed on `job_events`** (`../../../backend/schema.py:678`,
   nullable and unbackfilled, index at `:703`), and **D66, D67 and D68 are all closed**.
   Three things the column does *not* settle are now recorded in
   [`tranche_five/28-cohort-aggregation.md`](tranche_five/28-cohort-aggregation.md) rather
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

**Read [`README.md`](README.md)'s status column for what is done — do not trust a count,
including a count you just ran.** The instrument [`AUDIT.md`](AUDIT.md) names for it was
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
session reads.~~ [`AUDIT.md`](AUDIT.md) § *What is open* has the argument.

> **CLOSED 2026-08-02, and it landed red on purpose — 4 findings.** The widening is done and
> the two roots are scanned by C1, C3 and C4. It became two tasks rather than none:
> [`tranche_seven/45`](tranche_seven/45-declare-kind-on-the-roots.md) for the two real
> findings, [`tranche_seven/46`](tranche_seven/46-sentence-scope-the-c4-lookahead.md) for the
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

> **Superseded, kept per rule 4 — what this block said while phase 9 ran:**

> ~~**THE NEXT SESSION IS CLEANUP, BUGFIXES AND DOCUMENTATION — decided 2026-07-31.**
> … **Task 34 is the next session's task**, and its file did not exist until this
> decision — `README.md` linked to `34-documentation-cleanup.md` and nothing was
> there. That broken link is itself a specimen of the debt the session is for.~~
>
> **Struck 2026-08-01 by task 40, kept per `DOCS-POLICY.md` rule 4 so a reader who
> acted on it can see what they had. Both halves were false, and the second was
> already false when it was written:**
>
> | claim | reality |
> |---|---|
> | task 34 is next | it is **done** — [`README.md`](README.md) row 34, checked off item by item |
> | its file did not exist | **it existed**, tracked since `28f1d0e`. [`34-documentation-cleanup.md`](34-documentation-cleanup.md)`:14` strikes this exact sentence as *"WRONG, AND CORRECTED"* |
>
> **This block is rule 4's specimen.** A `rolling` document with no retirement
> trigger went on sending every fresh session to a finished task, repeating as its
> justification a premise the linked file had itself retracted, and nothing was red
> for a day. `backend/tools/audit-docs.py` check C3 exists because of it, and it is the
> worked example in [`../../DOCS-POLICY.md`](../../DOCS-POLICY.md) rule 4 — *"the document
> was simply never given a reason to stop"*. **Rolling this block forward is what keeps C3
> at 0; retiring it on a trigger is what stops it recurring.**

~~**It is still not the labelling session, and still not the product/API phase.**~~ **It is
now one of those two — see the table above.** Phases 1–3 are built and measured. **Task 34
landed** (`99fbdb1`, `3c4cee0`, `46a5be4`, `3f42e2d`) and phase 9 — tranche seven, tasks
~~36–42~~ **36–44** — made the documentation rules it wrote *checkable* rather than merely
written. **That work is finished.**

| tranche seven | state, 2026-08-01 |
|---|---|
| **36** enforce the doc policy | **done** — `57c34a5` |
| **37** classify every document | **done** — `89f7a3f` |
| **39** split the `D` namespace | **done** — `0110473`, `b64d7a6` |
| **41a** the nightly-run bugfix that lived only in the working tree | **done** — `7d839f5` |
| **41b** `scripts/` ignored, the tranche-two launcher untracked | **done** — `183b4dc`, `9b7bb5e` |
| **42** close the UNBLOCKED defects | **done** — `2a94f3d` |
| **38** one figure, one owner | landing now |
| **40** roll this file, clear the archive | landing now (this edit) |
| **43** the `docs/scoring.md` split (DEC-70) | **done** — the measured half is [`docs/scoring-measured-2026-07-27.md`](../../scoring-measured-2026-07-27.md) |
| **44** archive `HANDOFF.md`'s frozen half | **done** — this file is `rolling` throughout now, and C4 enforces on it |
| **41c/41d** the three branch decisions | open — the owner's, not a session's |

**For the state of the run in one page with an instrument beside every number, read
[`AUDIT.md`](AUDIT.md)** — which now *owns* the run-level figures rather than
restating them, per `DOCS-POLICY.md` rule 2. For what phase 9 is doing and why, read
[`../../DOCS-POLICY.md`](../../DOCS-POLICY.md); for how to work on any of it, read
[`../../WORKING-METHOD.md`](../../WORKING-METHOD.md). ~~For this task's backlog, read
[`34-documentation-cleanup.md`](34-documentation-cleanup.md).~~ **That file is now
finished history — read it for what the cleanup found, not for what to do next.** It
still carries the lesson that produced this whole phase: this run's follow-ups go stale
silently, one had been marked *"still owed"* in two files for three days after it
landed, and re-checking it turned up a number nobody had (79 postings, not 88).

**TWO TRACKS, AND ONLY ONE OF THEM IS THE SESSION'S.**

> **ROLLED FORWARD 2026-08-01. Both rows below describe finished sessions.** Phase 9's
> hygiene tranche closed at `b8c2943`, and the session after it took task 27 off the
> product/API track (`2687bc0`). The live version of this table is the one in § *START
> HERE* at the top of this file; this one is kept because the labelling row in it has never
> changed and is the point.

| | who | state |
|---|---|---|
| ~~cleanup / bugfix / docs (**34**)~~ **doc and repo hygiene (36–42)** | ~~**the current session**~~ **a finished one** | the whole of its job; 34 itself is **done** |
| a second labeller, ten `overlap` rows (**29**) | **the owner** — no agent can do it | **open, unchanged**, ~16 min |

**The labelling ask has not gone away and nothing below supersedes it.** Every field of
`evals label report` is still refused for want of a *second* `labeller_id` on the same
item; the owner has already answered all ten `overlap` rows, so a second person's ten are
the **last** input `labels.inter_annotator()` needs and the report prints the moment they
land. The tenth row from a second person is still worth more than the hundredth from the
first, and **29 still gates 30, 13's weights and 12's next bump.** It is simply not
something a session can do, which is why it is no longer the entry point.

**[`LABELLING-NIGHT.md`](LABELLING-NIGHT.md) is task 29's operational annex, not a second
entry point.** It is the ordered command list for the night itself — § *Case A* is solo on
localhost, § *Case B* is ten Builders behind a tunnel — and it freezes once the night
happens, which is why task 37 classified it `kind: task` rather than `rolling`. **This file
stays the only `rolling` document.** Read the annex when you are running the sitting; read
this block to find out whether you should be.

```bash
# The owner's track, when a second person is available:
cd backend/webapp
.venv/bin/python manage_app_users.py add --email <real address> --profile pursuit \
                                         --prior-domain <see § task 29 is UNBLOCKED>
.venv/bin/python manage_app_users.py list        # verify BEFORE sending any link
.venv/bin/uvicorn app:app --port 8421            # then http://localhost:8421/v1/label
```

~~**A trap that is live right now: `app_users` contains a placeholder.**~~
**CLOSED 2026-07-31 — `them@gmail.com` is disabled and `list` now flags it `DISABLED`.**
It was profile `pursuit`, `prior_domain=healthcare`, `sessions=0`, created
2026-07-31T05:26:09 — the literal example address from `LABELLING-NIGHT.md` § 3, added by
following that command verbatim. It was never a person and never signed in, but `list`
showed two `pursuit` rows and read as though a second labeller existed. There is no
`remove` and no rename in `manage_app_users.py` — only `disable` (`cmd_disable` at `:252`
→ `_set_active` at `:238`, *"UPDATE app_users SET active = %s WHERE email = %s"*), so the
row **stays visible as the record of the mistake** and stops counting as turnout.
*(This was the same failure task 16 recorded — "reported success over a literal
placeholder" — one run later.)*

**Read `list` as: one active `pursuit` labeller, and it is the owner.**

**AND THE OWNER'S OWN `prior_domain` IS NULL — `domain=-` in `list`, verified 2026-07-31.**
That is not an oversight to correct casually, because **the vocabulary cannot express their
answer.** `schema_web.PRIOR_DOMAINS` (`:116-120`) is `healthcare, education, retail,
hospitality, logistics, administration, trades, military, other, none`, and the flag's own
help calls it *"industry they are changing career FROM … 'none' means genuinely
early-career, which is NOT the same as omitting it"* (`manage_app_users.py:322-324`). The
one labeller is a **working software engineer**, who is changing career from nothing and is
not early-career: `none` would be false and `other` says nothing. **So the confound this
column was added to decompose — § *THE RECALL QUESTION IS EARNED*, caveat 2, *"whether
these are pipeline recall misses or one person's own history"* — cannot be decomposed by
this column even at n=2.** Recorded, not fixed: widening `PRIOR_DOMAINS` moves a CHECK
constraint generated from it (`schema_web.py:122-129`) and is a decision, not a tidy-up.
It is the same shape as the `revenue_commercial` finding — a vocabulary derived from an
assumed population, failing on the member nobody looked at.

**What the second sitting's 26 extra postings did and did not buy.** They bought three
diagnostics and a better instrument; they bought **nothing** toward the Definition of done,
because that is gated on a second person rather than on volume — which this file predicted
in writing and is the clearest confirmation of that prediction available:

| | before (5 postings) | after (31) |
|---|---|---|
| per-posting rate | 154 s, n=4 | **93 s median, n=29** ([`AUDIT.md`](AUDIT.md) owns the rate) — and the n=4 sample sat entirely inside a warm-up curve |
| the recall question | unearned | **earned** — 3 non-surfaced postings the labeller would apply to |
| the vocabulary gap | n=1 anecdote, "commercial/sales" | **13 postings**, and a corpus re-derivation that inverted its own instrument |
| floor / ceiling / measured | none | **still none** |

**Three things a fresh session must not do**, each guarded by something other than this
paragraph: do not compute model-vs-human agreement and write it down (`evals label report`
exits 2 by design; there is no `--force` and none may be added); do not redraw `pursuit-v1`
(`redraw_refusal()` refuses, and the window closed with the first label); do not bump
`FACTS_VERSION` to apply `revenue_commercial` without reading **DEC-64** first — it would
overwrite the model answers the existing labels were formed beside, mid-collection.

**AND FIVE MORE THAT APPLY SPECIFICALLY TO A CLEANUP SESSION**, because the failure mode of
a documentation pass is different from the failure mode of an implementation pass — it
destroys the record rather than the code, and nothing goes red:

1. **Mark, do not delete.** Every superseded claim in this run is struck and kept, because
   a reader working from the old text has to be able to see what they had. A cleanup
   session that tidies by deleting removes the only evidence that a number was ever wrong.
   *(A check written this session — "expect `grep 'still owed'` to return zero" — was
   itself wrong for this reason: the correct outcome was one hit, struck.)*
2. **Do not sweep stale line numbers wholesale.** § *Verify before you trust* forbids it
   explicitly: rewriting them all is how a doc acquires numbers nobody checked. Symbol
   names plus `grep -n` are the durable citation.
3. **Do not edit `.claude/CLAUDE.md` without the owner's sign-off.** It is the owner's
   instruction file and it governs every future agent. **34's job is to propose the diff**
   — including the "263 tests" line, which is now nine times too small — not to apply it.
4. **Do not "fix" `job_scores`' NULL version columns**, and do not re-record the
   `workday-cxs` cassette without reading `record_workday_cxs()`'s refusal guard first.
   Both look like tidy-ups and both destroy evidence.
5. **A stale claim is a finding, not just a chore.** Re-checking the one that had been
   false for three days is what produced the 79-vs-88 correction. **Report what the
   re-check turns up, not merely that you fixed it.**

---

Written 2026-07-28, and rolling — last updated after **the sitting ran on to 31 postings,
the stopwatch reading was overturned by the re-check this file asked for, and the recall
question was earned.**

~~**LABELLING HAS STARTED. 30 rows, 5 postings, one labeller, 2026-07-30 evening
(`2026-07-31T02:56–03:06` UTC).**~~ **SUPERSEDED 2026-07-31 — the sitting kept going.
186 label rows / 31 distinct postings / one labeller (`u_090b0ad12e99`) / round 1 only,
window `2026-07-31T02:56:05`–`05:25:27` UTC.** By stratum: `surfaced` 19, `gate_rejected`
9, `below_floor` 3. **All ten `overlap` rows are complete** — `position` 0–30 is
contiguous and the overlap block is 0–9 — so **a second labeller's ten rows now produce
the inter-annotator ceiling immediately**, with nothing to label first. Instrument for
every figure in this update: `python3 backend/tools/label-findings.py`, new this session,
read-only, no API key.

**Four consequences, and two of them are new.** (1) **The redraw window is CLOSED** —
`redraw_refusal()` refuses every redraw of `pursuit-v1`, identical digest included, so the
drawn set is permanent. (2) **`consensus()` promoting a majority of size one is happening
now**, not hypothetically. (3) ~~**the per-posting rate is measured at ~154 s, so twenty
minutes is ~8 postings rather than ~20** and the "one second person, ten minutes" unblock
is **~26 minutes**~~ **— WRONG, and the correction goes the *cheap* way. At n=29 intervals
the median is 93 s** ([`AUDIT.md`](AUDIT.md)): twenty minutes is **13 postings**, the ten `overlap` rows are
**~16 minutes**, and the DoD's ≥100 postings is **~2.6 hours**. See § *the stopwatch
reading*. (4) **The recall question is earned.** Three postings the pipeline did *not*
surface are ones the labeller says they would apply to, two of them `gate_rejected` —
which is the exact trigger § *How many to label* wrote for itself.

~~last updated after **task 29 stopped being blocked.**~~
The OAuth credentials are in, `.env` is correct, the owner's account is on `pursuit`, and
the sign-in chain was verified end to end without a browser. ~~**The next session's job is
to label.**~~ See § *task 29 is UNBLOCKED* immediately below. Before that: **the
intra-annotator ceiling was made reachable at all, `role_track` went on the form, and a
paired bootstrap landed in `evals/metrics.py`** (the suite grew at each of those four
steps; the readings are in § *the tree is NOT clean* and the current figure is
[`AUDIT.md`](AUDIT.md)'s). Before that: **task 29 was unblocked: four
defects fixed in the sampler, the label tables created, and the 200-row set drawn, redrawn
and pinned** (`c65d34b`, `2f64e08`, `90170d1`). Before that: **step 0, the gate fix**, implemented and
written to the database (mock gate recall 48.3% → 89.7%, live tier ≤2 869 → 880); the
planning session that measured it; the **mock acceptance run and the `strip_html` fix**;
**`job_scores`' version keys** (`d18ea54`); and **13, 35 and D45** (`fa2d7a7`, `303f7b9`,
`e11fabf`). Read this first, then [`DECISIONS.md`](DECISIONS.md) (why each choice was
made) and [`CLAUDE_UPDATES.md`](CLAUDE_UPDATES.md) (what happened, per task).

> **`CLAUDE_UPDATES.md` IS CURRENT AGAIN AS OF 2026-07-31, AND IT HAD SILENTLY STOPPED
> BEING SO.** Its last entry was the 2026-07-29 gate session; `grep -c "2026-07-30\|
> 2026-07-31"` returned **0**. Four sessions were missing — the 2026-07-29 sampler
> session as well as the three this file describes at length — against this run's own
> stated convention (§ *how this run works*) that the four documents move in the same turn
> as every commit. **Nothing was red, because a document that stops being written looks
> exactly like a document with nothing to say.** Backfilled from `git log` and
> `DECISIONS.md` rather than from this file's prose, deliberately: this file is a rolling
> summary that has been measurably wrong about itself, and copying it forward is how a
> claim becomes a citation. **The suite figures in those four entries were derived
> statically** — `pytest` is installed in no interpreter in this checkout — by counting
> `^\s*def test_` per tree, a method that is exact here (zero `parametrize` decorators) and
> that reproduced twelve figures the commit messages state independently, with no
> disagreements.
[`README.md`](README.md)'s status column is the ordered index.

~~**If you are a fresh session, the whole of your job is task 29 and its first two commands
are mechanical.**~~ **That sentence was WRONG and it is the headline of this update.** The
first command was mechanical; the second would have drawn a set that measured the wrong
gate, starved its own key stratum, and could not have reached task 29's Definition of done
at any turnout. See § *task 29's "two mechanical minutes"*. ~~**Task 29 is still the whole
of a fresh session's job, and what is left of it is now genuinely only people**: Google
OAuth credentials and ten Builders, both the repo owner's.~~

**SUPERSEDED 2026-07-30, and this time in the cheap direction. The credentials are in.**
Task 29 is still the whole of a fresh session's job, but nothing is blocked: sign in and
label. § *task 29 is UNBLOCKED* is the operational entry point and `LABELLING-NIGHT.md`
§ *Case A* is the command list.

## Orientation — three "READ THIS FIRST" sections, in this order

> **SPLIT 2026-07-31 (task 34). There were seven, and this file had been calling that
> "six too many" about itself for a week while the count went up.** Four of the seven
> described work that had already landed — the stopwatch reading, the sampler defects, the
> ceiling and pre-flight, the gate fix. Finished work is history, and history was standing
> in front of the next reader. Those four are now stubs pointing at
> [`docs/archive/`](../../archive/); their text is intact and `git log --follow` reaches
> the original. **Two operational subsections did NOT move** — `FRONTEND_ORIGIN` and the
> `app_users` schema are how the service is configured, not the story of how it was fixed.
>
> The file went 3,481 → ~2,690 lines. The three that remain are all *standing*: one open
> track, and two prohibitions. **If a ~~fifth~~ *fourth* ever appears, check first whether
> it is describing something that already happened.** *(Off by one when written, corrected
> 2026-08-01 by task 40: three remain, so the next one added is the fourth. Nothing checks
> this — it is the rule the file states about itself and `audit-docs.py` has no check for,
> which is `DOCS-POLICY.md` rule 7's "documented as unenforced".)*

The three are: task 29's labelling surface (open, the owner's), the ranking DoD that is
unmet on purpose, and the cost lever in the profiles table. If you read nothing else:

0. **Labelling has started and the drawn set is now permanent.** ~~30 rows, 5 postings, one
   labeller.~~ **186 rows, 31 postings, one labeller, and the ten `overlap` rows are DONE**
   (2026-07-31). `redraw_refusal()` refuses every redraw of `pursuit-v1` from here on, so
   nothing can be added to or removed from it — including postings later found to be
   exactly the hard case worth labelling. ~~**And a sitting is ~8 postings, not ~20**~~
   **A sitting is ~13 postings per twenty minutes, not ~8 and not ~20** — the 154 s that
   figure came from was measured entirely inside a warm-up curve (§ *the stopwatch
   reading*).

   **THE SINGLE HIGHEST-VALUE ACTION IS ONE OTHER PERSON FOR ABOUT TWENTY MINUTES, and it
   got both cheaper and more valuable in the same update.** The overlap block being
   complete means the second labeller's ten rows are the *last* input the ceiling needs —
   they do not have to be preceded by anything, and `evals label report` prints the moment
   they land. At the re-derived rate that ask is **~16 minutes**, not the ~26 this file
   said yesterday and not the ten it said three times before that.

1. **Task 29 is the whole critical path** (§ *what is blocked*), and **its schema, its
   sampler and its 200-row set are now DONE** (§ *task 29's "two mechanical minutes"*).
   ~~Its first two steps are mechanical and unblocked — minutes, no credential.~~
   **SUPERSEDED 2026-07-29, and this file was wrong in the expensive direction:** the
   second of those two commands carried **four** defects, none of them red, and the set it
   would have drawn measured the wrong gate. Fixed, drawn, **redrawn once more after the
   set was already committed**, pinned at
   `backend/evals/fixtures/labelset-pursuit-v1.jsonl`. ~~**What is left really is only
   people** — Google OAuth credentials and ten Builders.~~ **The credentials landed
   2026-07-30 and the first labeller is the owner; see § *task 29 is UNBLOCKED*.** And
   **the 55 postings in `docs/tasks/refactor/mock/` are still not its data** — they are
   invented, and reduce its scope by zero postings.
2. **Do not re-tune task 13's weights** (§ *the ranking is a product now*). Its DoD is
   unmet on purpose. Nothing measured since — including the mock corpus's 5-of-5 on
   branding traps — licenses changing them. Only task 29 does.
3. **Do not reactivate `tech` or raise `daily_narrative_budget` casually**
   (§ *the cost lever hiding in the profiles table*). Either one restores a ~5,000-row
   re-extraction bill or a ~1,018-call re-scoring bill. Run `score.py --stale-report`
   first; it needs no API key.

4. ~~**The night's pre-flight has two values that are wrong and silent**
   (§ *the ceiling was unreachable, and the night's pre-flight*). `FRONTEND_ORIGIN`
   sends every successful sign-in to a dead origin, and the one `app_users` row is on the
   wrong profile. The executable list is `LABELLING-NIGHT.md`, ~15 minutes.~~
   **BOTH FIXED 2026-07-30 and verified.** `FRONTEND_ORIGIN` and `ALLOWED_ORIGINS` are
   `http://localhost:8421`; the owner's row is on `pursuit`. The diagnosis is kept in that
   section as the record of a failure mode that produced no error — it is the reason the
   values are now what they are.
5. **A solo sitting cannot produce a report, and that is correct behaviour, not a bug**
   (§ *task 29 is UNBLOCKED*). `evals label report` exits 2 for as long as there is one
   labeller. **Do not route around it** — no `--force` exists and none should be added.
   One second person on the ten `overlap` rows, ~10 minutes, unblocks every field.

**And one standing prohibition, now guarded by a test rather than a paragraph:** do not
add the four phrase families in § *the gate fix LANDED*. `tools/mock-acceptance.py` scores
all four as costing nothing and they admit ~136 live junk rows.

**The one sentence a fresh session most often gets wrong:** a completed task here is not
a validated one. 13 is committed and unmet; the mock acceptance run is a *specification*
test and does not reduce task 29 by one posting. **The corollary, asked out loud once
already: `docs/tasks/refactor/mock/` is not task 29's data.** Those 55 postings do not
exist — `source = 'mock'`, invented to a specification, and reducing 29's scope by zero.
~~Forbidden from `eval_labels` by `tests/test_labels.py:423`.~~ **That citation was wrong:
the containment is `backend/evals/mock_corpus.py:3-6`, pinned by
`backend/tests/test_mock_corpus.py:939`. The conclusion survives; the reason changed.**
See § *task 29's "two mechanical minutes"*.

**Verify before you trust — including this file.** It has been measurably wrong about
its own line numbers, about which three tests a change would break, about its own SQL,
about how many copies of `AI_VOCAB` existed, about which script owns a flag, and — this
update — **about whether `fastapi` is installed, about which test forbids what, and about
which of its own next steps were mechanical.** Cite `file:line`, then re-read the line: the
wrong-test claim died the moment someone opened `tests/test_labels.py:423`. **And it kept
dying differently** — that line resolved to three different pieces of code inside a single
day's editing, and none of the three had anything to do with mock rows. **A line number
is a pointer into a file that is still being written**; quote the line's *text* when the
claim depends on it.

**And it happened again on 2026-07-30, wholesale: every `evals/labels.py` line number
written before that date is now low by roughly 100–170.** The round-2 path and
`role_track` added ~470 lines to that file, so citations like `next_item()` at `:924`,
`tail_offset()` at `:869`, `WEB_PRIVILEGES` at `:240` and `verify_schema()` at `:353` —
all of them correct when written, all of them in this file above — now resolve to the
wrong code. Current anchors: `next_item()` **`:1064`**, `tail_offset()` **`:938`**,
`WEB_PRIVILEGES` **`:296`**, `verify_schema()` **`:409`**, `sample()` **`:644`**,
`pool()` **`:554`**. **The pre-2026-07-30 numbers have been left in place rather than
swept**, because rewriting them all is how a doc acquires numbers nobody checked; the
symbol names are the durable pointers and `grep -n` is the instrument.
`test_the_two_ceilings_are_different_quantities` moved from `:416` to `:464` in
`tests/test_labels.py` in the same window.

**The numbers in this update were re-derived twice within one hour and moved between the
two**, because `labels.py` was being edited while its citations were being written —
`next_item()` went `:1042` → `:1064` in that window. **So treat every line number in this
update the same way as the ones it corrects: a symbol name plus `grep -n` is the citation;
the digits are a convenience with a shelf life.** That is not a caveat added for form. It
is the fourth time this file has recorded the same failure. The `fastapi` claim needed a different instrument again —
**ask which interpreter the observation was made with**, because "it fails to import" is a
fact about an environment, not about a repo.

## ARCHIVED: the stopwatch reading, measured at n=4 and re-derived at n=29

> **MOVED 2026-07-31 → [`docs/archive/handoff-stopwatch-reading.md`](../../archive/handoff-stopwatch-reading.md).** Measured the per-posting labelling rate, 2026-07-31. The n=4 reading (154 s) and its same-day correction at n=29, which more than halved it. Superseded as a *narrative* by the single entry in HANDOFF.md's § Pending follow-ups; the rate itself is owned by [`AUDIT.md`](AUDIT.md).

## READ THIS FIRST: task 29 is UNBLOCKED ~~, and the next session labels~~

> **THE HEADING'S SECOND HALF IS SUPERSEDED, 2026-07-31.** Task 29 is still unblocked and
> everything in this section still holds — but **the next session is 34, not 29** (§ *THE
> NEXT SESSION IS CLEANUP*). What is left of 29 is a second person's twenty minutes, which
> is the owner's to arrange and not a session's to execute. Read this section for how the
> labelling surface works and what a solo sitting can and cannot produce; do not read it as
> this session's assignment.

**Done 2026-07-30. Nothing is committed — the working tree carries all of it.** Suite
**+6 main, +14 webapp** on that date — the deltas are what this sentence was saying, and
the absolute counts belong to [`AUDIT.md`](AUDIT.md) (rule 2). For the first time in this run **there is
no blocker on task 29 at all**: no credential, no code, no person. The remaining work is
someone reading postings and answering six questions.

### What changed

| | before | after |
|---|---|---|
| `GOOGLE_CLIENT_ID` / `_SECRET` | empty strings, `/v1/auth/login` → 503 | **set**, `config.oauth_configured()` → True |
| `FRONTEND_ORIGIN` | `http://localhost:5173` — nothing serves it | **`http://localhost:8421`** |
| `ALLOWED_ORIGINS` | `http://localhost:5173` | **`http://localhost:8421`** |
| owner's `app_users` row | profile `tech`, which task 12 paused | **`pursuit`** |
| moving a user between profiles | no supported path — `email` is UNIQUE and `add` refuses | **`manage_app_users.py set-profile`**, 14 tests |
| re-drawing a pinned label set | silently appended rows, desynced the fixture | **refused**, exit 2, 6 tests |

**The sign-in chain was verified end to end without a browser**, which is worth repeating
because it is cheap and it is the step that used to be assumed: `/v1/label` signed out
302s to `/v1/auth/login?next=/v1/label`; that 302s to
`https://accounts.google.com/o/oauth2/v2/auth` carrying
`redirect_uri=http://localhost:8421/v1/auth/callback`, `response_type=code`,
`code_challenge_method=S256`, `scope=openid email profile`. `/v1/health` returns
`{"ok":true}`. **What is NOT verified is the Google console entry**, which no local check
can reach — a mismatch there fails visibly with `redirect_uri_mismatch` before the browser
returns, so it is the friendly failure and not one to plan around.

### Start here

```bash
cd backend/webapp && .venv/bin/uvicorn app:app --port 8421
# then open http://localhost:8421/v1/label
```

`.venv` is the only interpreter with `fastapi`; system `python3` cannot import it, and that
has already been mistaken once for "fastapi is not installed". `LABELLING-NIGHT.md`
§ *Case A — solo, localhost* is the full list.

### The finding that changed the ORDER of the work

**Axis B answers are stamped with the SESSION's profile, and labels cannot be edited.**
`webapp/label.py:440` passes `profile=user.profile if q.axis == labels_mod.AXIS_B else
None`, under a comment reading *"profile comes from the SESSION, never from the form …
what keeps axis B rows attributable to a cohort"*, and `eval_labels` carries **no UPDATE
and no DELETE grant** (`schema_web.py:63`: *"A label is evidence"*). Labelling one posting
while still on `tech` would have recorded that `would_apply` answer as a `tech` preference
**permanently, with no correction path**. It was caught by checking what the form does with
`user.profile` before the first submit rather than after — the profile move is not tidying
and it is not reversible after the fact.

**Generalisation, and it is the same one this file keeps writing down:** the pre-flight
list said "move the row" and gave *"tech is inactive"* as the reason. That reason was true,
minor, and not the one that mattered. **A step can be right for a weak reason and the weak
reason is what gets it skipped when someone is in a hurry.**

### What a solo sitting produces, and what it cannot

**`evals label report` will exit 2 for as long as there is one labeller.** The ceiling
column is bound to `labels.inter_annotator()`, which needs **two distinct `labeller_id`s
on the same item**; `Interpretable` is the only thing `report.render_labels()` accepts, and
its `__post_init__` raises when a cell is missing. **There is deliberately no `--force`.**
This is a designed refusal — *"making the bad report unrepresentable rather than
discouraged is the whole design"* — and a session that finds a way around it has broken the
thing, not fixed it.

Everything else works at any count. Nothing requires 200: `status` and `export` are fine,
`next_item()` resumes exactly where a labeller stopped, indefinitely, and `tail_offset()`
computes each labeller's window at serve time from their own rank with **`k` appearing
nowhere in it** — so Builders arriving in a month sort after the owner, his rank stays 0,
and his queue never shifts under him. **His first ten items are already the `overlap`
block** (`band 0`), stratified 5 `surfaced` / 3 `below_floor` / 2 `gate_rejected`.

**The cheapest unblock in this task: one second person, ten minutes, ten rows.** They never
see the other 190. Arrange it *before* a long solo sitting rather than after — the labels
are not wasted either way, but nothing collected has a scale to be read against until that
person exists. **The DoD deviation is recorded in
`tranche_five/29-labelling-session.md` § *Deviation — the first sitting is SOLO***, line by
line, rather than tuned away; same treatment task 13's unmet lines got.

**And the owner's own fallback is the intra-annotator ceiling**, which needs no code: the
same ten `overlap` rows at `/v1/label?round=2`, no sooner than
`labels.ROUND_TWO_DELAY_DAYS = 7` days after the round-1 answers. It is the **weaker**
quantity and `interpretable()` was deliberately **not** changed to accept it as the
ceiling; it renders as a footnote.

> **ASKED AND SETTLED 2026-07-31: shortening the delay was proposed, examined, and NOT
> done.** Recorded here so the next session does not re-open it. **The reason is not DEC-59 —
> it is that the change buys nothing.** `_three_quantity_report()` passes
> `ceiling=inter["fields"]` into `interpretable()` (`evals/__main__.py:485-487`) and hands
> `intra` to `report.render_labels()` on a separate argument, where it prints as a footnote
> (`report.py:489-496`). **So round 2 cannot satisfy the report at any delay**, and
> shortening it would not have unblocked one field. Round 1 ran
> `2026-07-31T02:56:05`–`05:25:27` UTC and the gate is per row, so the second pass matures
> **2026-08-07** on its own.
>
> **The second finding is the one worth keeping.** Had it been shortened, the resulting
> number would have arrived **unmarked**: `intra_annotator()` (`labels.py:1584`) groups by
> `(job_id, field)` then by round and **never reads `labelled_at`**, `Interpretable` never
> sees a timestamp, and `report.py:489-496` prints the footnote unconditionally. **The
> queue is the only guard there is.** `round_one_answers()`' docstring already says this
> at `labels.py:1194-1199` — *"a round-2 row can then partner MINUTES LATER … because
> intra_annotator() never reads `labelled_at` at all"* — and it is worth reading as a
> general rule: a guard that lives only in the write path cannot defend a number that is
> computed in the read path.
>
> The four functions do take `delay_days=` (`round_two_ready`, `round_one_answers`,
> `_round_two_cutoff`, `next_item`), and `webapp/label.py` passes it at none of its four
> call sites — so an operator override is ~6 lines through `webapp/config.py` if it is ever
> genuinely wanted. It is not wanted for the report.

### Which axis carries the profile, and why a solo Axis B is NOT a proxy

Asked directly on 2026-07-30 and worth answering here, because a later session will
reasonably wonder whether one person's `would_apply` answers are worth anything.

**Only Axis B carries a profile, and the split is enforced with a raise rather than by
convention** (`labels.record()`, `evals/labels.py:958-962`):

| axis | fields | `profile` stored |
|---|---|---|
| **A** | `ai_involvement`, `seniority_level`, `role_archetype`, `remote_policy`, `role_track` | **NULL** — *"axis A is profile-independent -- see the CHECK constraint in ensure_schema()"* |
| **B** | `would_apply` | **`pursuit`**, from the session, never the form |

So the extraction questions are recorded as facts about the posting, true for every cohort
forever — which is the mechanical reason Axis A is *"the asset"* and survives a change of
vertical. Only *"would you apply"* is stamped.

**And the repo owner is a Builder, not staff.** `29-labelling-session.md` § *Logistics*
says so as its opening premise — no roster access, no instructor authority, *"asking ~10
classmates for twenty minutes."* **His Axis B answers are therefore genuine cohort
preference at n=1, not a stand-in for it.** The circularity Axis B exists to avoid is
specifically *a model* substituting for a human — the defect named in `claude-bench.py:417`.
A Builder answering for themselves is the intended instrument, and a future session should
not discount these labels as second-best.

**What n=1 does cost is different and sharper:** `consensus()` promotes a single labeller's
answer to "the majority human answer" with `tied` always empty and **nothing recording that
the majority was of size one.** With one labeller there is no way to separate *"the model
disagrees with Builders"* from *"the model disagrees with Eric."* That — not the missing
ceiling cell — is what the report's refusal is really protecting, and it is why a second
person's ten minutes buys more than a second hundred postings of the owner's own would.

### How many to label, and the number STILL nobody has measured

**Verified 2026-07-30: the strata are INTERLEAVED, not blocked.** Sorted by `position`,
every 50-row block is roughly the set's own 50 / 25 / 25:

| positions | surfaced | below_floor | gate_rejected |
|---|---:|---:|---:|
| 0–9 (the overlap block) | 5 | 3 | 2 |
| 10–59 | 30 | 6 | 14 |
| 60–109 | 27 | 13 | 10 |
| 110–159 | 21 | 19 | 10 |
| 160–199 | 25 | 9 | 16 |

**So any prefix is a proportional miniature of the whole set and there is no wrong place to
stop.** This is worth stating because the opposite arrangement — strata in blocks — would
have made "label 50" mean "label only `surfaced`", and nothing in the tooling would have
said so.

**What each stopping point buys**, computed with `metrics.wilson()` rather than by hand:

| labelled | Axis A: 95% CI at an observed 85% | `gate_rejected` seen | recall bound if the owner would apply to none |
|---:|---|---:|---:|
| 10 | [0.49, 0.94] | 2 | 66% |
| 60 | [0.71, 0.92] | 16 | 19% |
| 110 | [0.77, 0.91] | 26 | 13% |
| 200 | [0.79, 0.89] | 50 | **7%** |

**Read the middle column against task 06's floors — ~~76% on `seniority_level`, 94% on
`ai_involvement`~~ 85.2% and 94.8%, both `agree2` — because that is what makes it
legible:**

> **FIGURES CORRECTED 2026-07-31, and the pair that was here is the superseded one.**
> 76% / 94% are the **provisional n=17** figures from 2026-07-27.
> `docs/ingestion_tests/README.md` carries them under a heading that reads *"Superseded"*,
> and `DECISIONS.md` § *06 — Was 76% real?* answers its own question with **no**. The live
> measurements, both `agree2`, are **`seniority_level` 85.2% [77.6–90.6]** and
> **`ai_involvement` 94.8% [89.1–97.6]** (`agree2`, [`AUDIT.md`](AUDIT.md) § *The three
> self-consistency metrics*), n=115, `--repeat 3`, `deepseek-v4-flash` at
> temperature 0. **Naming the metric is not decoration** — `ai_involvement`
> self-consistency circulates here as three different percentages, all correct, because
> `agree2`, the pairwise two-run metric and a per-platform cell are three different
> questions; [`AUDIT.md`](AUDIT.md) § *The three self-consistency metrics* owns all three
> with the command that reproduces them. This file
> quoting the dead pair is the exact thing that README predicted would happen — *"retained
> because published text still cites them"* — and it is corrected rather than deleted so
> the next reader can see which number they may have been working from. **The bullets below
> are left as written**: at these floors the reading is directionally the same and the
> conclusion (110 is where Axis A becomes defensible) does not move.

- **At 60** an observed 85% cannot be told apart from `seniority_level`'s own ~15%
  instability. It *does* already exclude 0.94, so a real `ai_involvement` problem surfaces
  this early.
- **At 110** the interval clears 0.76 — this is where Axis A becomes a defensible claim for
  every field, and it is also the DoD's number.
- **200 barely improves Axis A** (width 0.14 → 0.10) and nearly halves the recall bound.
  **The back half is bought almost entirely for the recall question**, which is the one no
  other instrument in this repo can answer at all.

**Recommended: ~60 in the first sitting, 110 as the target across two or three, 200 only if
the recall question earns it** — it does the moment any `gate_rejected` row turns out to be
one the owner would genuinely apply to. The back half is also *cheaper per row*: about a
quarter of the set is `gate_rejected`, most of it unambiguous, and 26 of those 50 carry no
`job_facts` at all, so they only ever feed Axis B and the recall bound.

#### THE RECALL QUESTION IS EARNED — 2026-07-31, and the trigger was this section's own

The sentence above sets the bar: 200 is bought *"the moment any `gate_rejected` row turns
out to be one the owner would genuinely apply to."* **Two have.** Instrument:
`python3 backend/tools/label-findings.py`, `eval_labels.would_apply` × `eval_label_items.stratum`,
over the 31 postings labelled 2026-07-31 by one labeller, Wilson intervals from
`metrics.wilson()`.

| stratum | yes | no | n | rate | 95% CI |
|---|---:|---:|---:|---:|---|
| `surfaced` | 6 | 13 | 19 | 32% | [0.15, 0.54] |
| `below_floor` | 1 | 2 | 3 | 33% | [0.06, 0.79] |
| `gate_rejected` | 2 | 7 | 9 | 22% | [0.06, 0.55] |

**The three postings the pipeline did NOT surface and the labeller would apply to:**

- **Brex — *AI Engineer, Ecosystem*** (`below_floor`), extracted
  `ai_involvement = builds_llm_features`. Scored, and scored under the floor.
- **Ramp — *Software Engineer, Accounting*** (`gate_rejected`), **no `job_facts` row at
  all** — nothing in this repo has an opinion about it, by construction.
- **Twilio — *Frontend Software Engineer*** (`gate_rejected`), extracted
  `ai_involvement = none`.

**TWO CAVEATS THAT MUST TRAVEL WITH THIS TABLE, and neither is optional.**

1. **The three Wilson intervals overlap almost completely.** [0.15, 0.54], [0.06, 0.79] and
   [0.06, 0.55] cannot tell the strata apart at these n. **This is a trigger, not a rate** —
   the named postings above are what earns the back half of the set, not the 22%. Do not
   quote "22% of `gate_rejected` would be applied to"; at n=9 it means nothing.
2. **The single labeller is a software engineer by background, and two of the three
   postings are plain software-engineering roles.** That is exactly the confound
   `app_users.prior_domain` was added to decompose, and **it cannot be decomposed at
   n=1.** Whether these are pipeline recall misses or one person's own history is a
   question a second labeller with a different `--prior-domain` answers and nothing else
   does.

**What it changes:** 200 is now on the table on its own stated terms, at **5.2 h** for one
person at the re-derived rate (§ *the stopwatch reading*) rather than the ~8.5 h the 154 s
figure implied. It does **not** license touching the gate — see § *the first finding
arrived BEFORE the first label* for why n=1 is not a licence.

~~**THE DELIVERABLE THE NEXT SESSION SHOULD ACTUALLY BRING BACK IS A STOPWATCH READING.**~~
**DELIVERED 2026-07-31 — twice, and the second reading corrected the first.** 93 s median at n=29 ([`AUDIT.md`](AUDIT.md) owns it),
`tools/label-findings.py --timing`; § *the stopwatch reading*. The paragraph is kept
because it is the request that produced the number and because its warning against
inventing a correction factor is what made the re-derivation legible when it arrived.

**THE DELIVERABLE THE NEXT SESSION SHOULD ACTUALLY BRING BACK IS A STOPWATCH READING.**
Every budget figure in this run — *"~20 items each"*, *"~28 at five labellers"* — was
computed against a **five**-question form; the form asks **six**, and this file already
records that the per-posting time *"was never measured, only assumed"* and that inventing a
correction factor would repeat the 110-vs-84 error. **The first ten rows are the
instrument.** Time them, write the number down here, and every Builder-session estimate
afterwards stops being a guess. That is a smaller deliverable than the labels and a more
reusable one.

**And use the abstention.** *"I can't tell from this posting"* stores NULL and is
dropped-and-counted, never folded in — *"folding them in as a value would score two people
who both gave up as two people who concurred."* Forcing a guess to keep the count up is
worse than a lower count.

### The first finding arrived BEFORE the first label, and it is a vocabulary one

**Recorded 2026-07-30, from the repo owner reading postings in the form.** It is one
Builder's judgement at n=1 — authoritative for Axis B, and **not yet a licence to change
the gate.** Written down now because the repo's convention is rationale at decision time,
and because it is the exact finding task 12 predicted and could not name.

**The observation:** commercial / sales roles that *sell AI products* are strong Pursuit
targets — the employer explicitly wants people who are enthusiastic about AI and who use
it — and **the vocabulary cannot express them.**

> **AMENDED 2026-07-31 at n=31, and the amendment splits the finding in two. The vocabulary
> gap is real and larger than stated. The *commercial* framing of it was not the dominant
> shape in the labelled sample — it is corroborated at corpus scale instead, and the two
> populations disagree in emphasis.** Both must be quoted with their population attached;
> this is the file's own *"disaggregate, and look at what is actually in the bucket"* rule
> applied to its own headline finding.
>
> **Population A — the 31 labelled postings** (`tools/label-findings.py`, the humans' own
> answers, one labeller, 2026-07-31). `role_track = no_track_fits` on **13 of 31 = 42%**
> [0.26, 0.59]; `role_archetype = other` on **17 of 31 = 55%** [0.38, 0.71]. So more than
> half the postings a Builder actually read had no archetype that fits. **But only 2 of
> those 13 are commercial/sales** — both Notion *Commercial Solutions Consultant* (Japan,
> and San Francisco) — and **the owner answered `would_apply = no` on both.** Location is a
> plausible confound and is not controlled for; do not read the two `no`s as a retraction of
> the finding. The NYC variant of that same role, which *is* the code-verified instance this
> file records as side-list entry #1 (`8ba8616b7c91d2a1b5112cdc`), **is not in `pursuit-v1`
> and can never be added.** The rest of the 13 is a different population entirely:
> rotational and analyst programmes, ops specialists, non-software engineering (mechanical,
> laboratory, building), recruiting, and data annotation. § *Pending follow-ups* now carries
> all 17 with the model's answers beside them.
>
> **Population B — the cohort corpus** (`tools/derive-role-tracks.py --archetypes`,
> `facts_version = 3`, 294 `other` rows). **Strongly corroborated here.** A single proposed
> value, `revenue_commercial`, reclaims **68 of 294 = 23.1%** of the `other` bucket — more
> than the fourteen values task 11 actually adopted reclaim between them (47). Working,
> counts, and the reasons four other candidates were dropped: § *Pending follow-ups*.
>
> **The honest summary is therefore narrower than the 2026-07-30 headline and better
> evidenced than it:** `ARCHETYPE` has no commercial value, that gap is the single largest
> nameable slice of `other` at corpus scale, and **it is not what the first 31 human labels
> were mostly complaining about.** Both sentences are true of different populations.

**Verified against the code, and the gap is structural:**

- **`ARCHETYPE` has no sales value at all.** Its own first line is the admission —
  `extract.py:262-266`, *"The original twelve. All software engineering."* Across all 26
  there is no sales, account executive, business development or commercial. The nearest,
  `solutions` and `forward_deployed`, are **solutions *engineering*** — technical presales,
  still engineering. A commercial role lands in `other`, or is mislabelled `solutions`
  because the word matches.
- **`ROLE_TRACK` has no plain commercial track either.** `revenue_operations` is RevOps —
  the ops function *behind* selling, not selling — and `solutions_and_implementation` is
  again the technical side.
- **This was predicted in writing.** `ROLE_TRACK`'s own comment says the corpus is
  *"pre-Phase-3 and tech-heavy"* and that task 11 is *"explicit that a taxonomy derived
  from it 'will not describe the population's opportunity space' and expects revision."*
  Task 12 then measured the consequence: 12 → 26 archetypes made `other` **worse**, 31.1%
  of the cohort corpus and **44.0% of first-time extractions**, because *"the vocabulary
  fits the corpus it was derived from and fails on the part of the cohort corpus nobody had
  looked at."* **This is that part, being looked at.**

**The sharper half is `ai_involvement`, and it may overturn a design assumption.** Its four
values — `none`, `uses_ai_tools`, `builds_llm_features`, `core_ml_research` — all describe
what the *person does with* AI, so a commercial role selling an AI product can honestly
score **`none`**. That is precisely the shape of **task 13's four floor misses**
(*"carry `ai_involvement = 'none'` and read as AI-adjacent only because the employer is an
AI company"*), the pattern **task 05 measured at 6.7% precision**, and the one the gate was
deliberately tightened *against*. `DECISIONS.md` says only task 29's labels can settle
whether those are correct rejections or weight errors. **They are being settled, and the
first answer contradicts the assumption.**

**But the two claims are not the same claim, and the difference is the whole finding.**
Task 05's pattern was **broad** — *any* role at an AI employer, including facilities and
admin. This one is **narrow**: the *product* is AI and the posting selects for AI
enthusiasm. **`ai_involvement` conflates "does this person use AI" with "is this role
about AI", and for customer-facing commercial work those come apart.** That is a missing
distinction, not a wrong value, and no amount of re-tuning the existing four values
produces it.

**This is also the standing argument against dropping Axis A from the form.** A model
**cannot report that its own vocabulary is wrong** — it can only pick from the list or emit
`other`/NULL. *"None of these fit, and here is the shape that is missing"* is information no
LLM in this pipeline can generate, because the list is the only thing it is allowed to
return. **`role_archetype` and `role_track` are the two questions whose answers a model
structurally cannot substitute for**, which is the opposite of the intuition that says the
extraction fields are the skippable ones.

**How it is being captured, and the one thing that cannot be:**

- `role_track` → **`no_track_fits`**, a verdict, deliberately distinct from the *"I can't
  tell"* abstention that `validate()` would otherwise collapse it into.
- `role_archetype` → **`other`**, the same signal at the coarser grain.
- **There is no free-text field on the form** — checked. So it records *that* nothing fits
  and never *what* is missing. **A side list of the postings where the answer is
  "commercial/sales" is the only place the content can live**, and it is the input to
  re-running `backend/tools/derive-role-tracks.py`.

**Do not act on this yet.** n=1, and it would move the gate — the one artefact this run has
damaged the premise of (§ *GATE 2 is the one at risk*). What makes it actionable is other
Builders agreeing, which is another thing the second labeller buys.

### The redraw window is about to close, and now something guards it

`register_set()` used `ON CONFLICT DO NOTHING` on both tables, so re-running `evals label
sample --label-set pursuit-v1` with a different `--seed` did not error: existing items kept
their old `position` and `overlap`, new job_ids were **appended**, and
`eval_label_sets.n` and `job_id_sha256` went on describing the first draw while `--out`
overwrote the committed fixture. `labels.digest()` was computed and **never compared** to
the stored hash anywhere. `redraw_refusal()` now compares it and refuses; **verified live
on both the dry-run and the write path**, exit 2, fixture byte-identical, 200 items intact.

An identical re-draw is still allowed, on purpose — that is crash recovery. **But any
label at all refuses even an identical-digest redraw**, because the job ids are the
digest's only input, so a draw that keeps them and moves the `overlap` flags hashes the
same while changing what every labeller was shown.

## ARCHIVED: task 29's "two mechanical minutes" were four defects, and the set is drawn

> **MOVED 2026-07-31 → [`docs/archive/handoff-sampler-defects.md`](../../archive/handoff-sampler-defects.md).** Recorded 2026-07-29. Four defects in `labels.sample()` found before the 200-row set was drawn, plus a fifth found after it was pinned. All fixed; the set is drawn and permanent. Nothing here is outstanding.

## ARCHIVED: the ceiling was unreachable, and the night's pre-flight

> **MOVED 2026-07-31 → [`docs/archive/handoff-ceiling-and-preflight.md`](../../archive/handoff-ceiling-and-preflight.md).** Recorded 2026-07-30; the ceiling diagnosis and the pre-flight fixes, all landed and verified.

## Operational reference kept from the pre-flight section

*These two subsections did not move. They are how the labelling service is configured, not the story of how it was fixed.*

#### What `FRONTEND_ORIGIN` should actually be set to

**There is no single right value — it is "the origin a volunteer's browser is on", and that
depends on who is labelling.** `FRONTEND_ORIGIN` is only ever used as the base of the
post-login redirect (`config.py:105-106`, *"Where the OAuth callback sends the browser once
a session exists"*), so it has to be an origin that serves `/v1/label`.

**Case A — the owner testing alone, on the machine running the service:**

```
FRONTEND_ORIGIN=http://localhost:8421
ALLOWED_ORIGINS=http://localhost:8421
GOOGLE_REDIRECT_URI=http://localhost:8421/v1/auth/callback   # already this
SESSION_COOKIE_SECURE=false                                  # already this
```

**Case B — ten Builders on their own devices, which is what task 29 actually is:**
`localhost` is not reachable from anyone else's machine, so a public origin is required —
the **tunnel half of task 33**, which HANDOFF already records as splittable and needed
before 24. Then all four values change together:

```
FRONTEND_ORIGIN=https://<tunnel-host>
ALLOWED_ORIGINS=https://<tunnel-host>
GOOGLE_REDIRECT_URI=https://<tunnel-host>/v1/auth/callback
SESSION_COOKIE_SECURE=true
```

**Four things must agree and three of them fail silently:**

- `GOOGLE_REDIRECT_URI` must **also** be registered verbatim in the Google console.
  A mismatch is the one failure in this group that *does* produce a visible error — Google
  refuses with `redirect_uri_mismatch` before the user reaches this service.
- `FRONTEND_ORIGIN` wrong → sign-in succeeds and the browser lands nowhere. Silent.
- `ALLOWED_ORIGINS` wrong → the CORS allowlist rejects the origin. `config.py:108-110`
  records the failure mode: *"a wildcard is incompatible with credentialed requests per the
  CORS spec, and the browser's failure mode is to silently drop the session cookie rather
  than say so."* Not load-bearing for `/v1/label` itself, which is server-rendered HTML with
  no JavaScript, but it will be for task 32's frontend.
- **`SESSION_COOKIE_SECURE` is the trap in the other direction.** It defaults to `True`
  (`config.py:119`, *"so that the insecure setting has to be typed out on purpose"*) and is
  currently `false`, which is correct for `http://localhost`. Serve over plain HTTP with it
  `true` and the browser **discards the session cookie**: login appears to succeed and every
  subsequent request is signed out. Set it `true` for Case B, keep it `false` for Case A, and
  do not leave it `true` while testing on `localhost`.

#### The `app_users` schema, and where the example data is

**DDL: `backend/webapp/schema_web.py:107-117`** — nine columns, and this module owns them
(`backend/webapp/` owns the service's tables; `backend/schema.py` owns the pipeline's).

```sql
CREATE TABLE IF NOT EXISTS app_users (
    id            TEXT PRIMARY KEY,
    email         TEXT NOT NULL UNIQUE,
    google_sub    TEXT UNIQUE,
    display_name  TEXT,
    profile       TEXT NOT NULL,
    is_admin      BOOLEAN NOT NULL DEFAULT FALSE,
    active        BOOLEAN NOT NULL DEFAULT TRUE,
    created_at    TEXT NOT NULL,
    last_login_at TEXT
)
```

**Do not hand-write a row.** `manage_app_users.py add` is the path, and it supplies three
things you would otherwise have to know:

- **`id` is generated**: `f"u_{secrets.token_hex(6)}"` (`manage_app_users.py:88`), so
  `u_` plus 12 hex characters.
- **`google_sub` is NULL until their first successful login**, then bound. The row is
  matched by email until then and **by `sub` afterwards** — which is why an email change is
  harmless and a recycled address cannot inherit somebody's account. The CLI prints this
  when it adds a user (`:105-107`).
- **`profile` has deliberately NO foreign key** to `profiles(profile)`, matching
  `job_scores.profile` and `job_matches.profile` (`schema_web.py:119-125`): a real FK would
  make this service's DDL depend on a table it must not own. The CLI validates with
  `profiles.load_one()` instead — *"the right place for it, since that function deliberately
  returns paused profiles too"*, so it will happily seed a user against a profile nobody has
  activated yet. **That is exactly how the one existing row ended up on the inactive `tech`.**

**Example data — there is exactly one row, and it is a counter-example:**

```
email                profile   google_sub   active
ericliu93@gmail.com  tech      (bound)      true
```

Read it for the *shape* and not for the values: `tech` is inactive, so this user sees
nothing the cohort sees. What a Builder row must look like is the same shape with
`profile = 'pursuit'`:

```
cd backend/webapp
.venv/bin/python manage_app_users.py add --email them@gmail.com --profile pursuit
.venv/bin/python manage_app_users.py list      # verify before sending any links
```

`list` (`:109-118`) is the check to run before the night — it reports email, profile,
whether `google_sub` is bound, `created_at` and `last_login_at`, so it answers "did all ten
rows land, and has anyone actually signed in yet" in one command.

Both blockers named in § *what is blocked* still stand: the OAuth client id and secret are
**empty strings** (`/v1/auth/login` → 503, `webapp/auth.py:235-239`), and ten Builders need
ten `manage_app_users.py add` invocations plus ten Google console **Test users** entries —
**and only one of those two failures produces an error from this service**
(`backend/webapp/README.md:143-151`).

**Serving it needs no install and no code**, but **use `backend/webapp/.venv`** —
`fastapi` lives there and nowhere else, and system `python3` cannot import it. That
observation has already been mistaken once for "fastapi is not installed".

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

## ARCHIVED: the gate fix LANDED, and what it did not buy

> **MOVED 2026-07-31 → [`docs/archive/handoff-gate-fix.md`](../../archive/handoff-gate-fix.md).** Recorded 2026-07-29. Step 0's relevance-gate fix: mock gate recall 48.3% -> 89.7%, live tier <=2 869 -> 880. Its own first line says "What follows is the record, not a plan." The four forbidden phrase families it names are now guarded by a test, not by this prose.

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

## State at handoff — ARCHIVED

> **MOVED 2026-08-01 → [`docs/archive/handoff-state-2026-07-31.md`](../../archive/handoff-state-2026-07-31.md).** The run's state as
> of 2026-07-31: the dated suite readings, the drift table that is the evidence for
> `DOCS-POLICY.md` rule 3, and the commit table that `tranche_two/12`, `tranche_two/13` and
> `tranche_three/19` cite. **[`AUDIT.md`](AUDIT.md) owns both current suite counts and, per
> rule 3, states neither — it names the command that prints them.**

## What 08, 12 and 19 changed about the plan — ARCHIVED

> **MOVED 2026-08-01 → [`docs/archive/handoff-state-2026-07-31.md`](../../archive/handoff-state-2026-07-31.md).** The findings those
> three tasks landed on 2026-07-28: which number the product should display, the archetype
> vocabulary making `other` worse rather than better, and task 19 dropped on the evidence.

## The two decisions the repo owner made in conversation — LANDED

> **MOVED 2026-07-31 → [`docs/archive/handoff-owner-decisions.md`](../../archive/handoff-owner-decisions.md).** Recorded 2026-07-28, landed in `943d899`. Selective majority-of-3 extraction and the 40/day ceiling. Both shipped; the rationale is in DECISIONS.md under EXTRACT.

## Nothing is in flight — ARCHIVED

> **MOVED 2026-08-01 → [`docs/archive/handoff-tree-state.md`](../../archive/handoff-tree-state.md).** What was committed and
> what was only a database write, recorded 2026-07-29 through 2026-07-31, with the content
> digests that proved nothing else moved. **Its FAQ is the section immediately below and
> stayed here**; its four cross-stream lessons were promoted to
> [`docs/MEASUREMENT-TRAPS.md`](../../MEASUREMENT-TRAPS.md) under rule 5.

## The next session's likely first question, answered

**"Step 0 is done, the schema exists and the set is drawn. What is actually next?"**
**Nothing an agent can do on task 29.** ~~Its first two steps take minutes and need no
credential~~ — they are done, and they were not minutes; see § *task 29's "two mechanical
minutes"*. What remains is **two things, both the repo owner's**: Google OAuth credentials
in `backend/webapp/.env`, and ten Builders with an `app_users` row each. § *what is
blocked* has the specifics. Everything else in the plan is credentials (15, 20), a
re-scope (21), or a call for the repo owner (GATE 2).

**"The set is drawn. Can I start measuring against it?"** No. `eval_labels` is **empty**.
`pursuit-v1` is a pinned eval set of 200 `job_id`s and nothing else — no labels, no Axis B,
no consensus. It is the thing the labelling session labels, and CLAUDE.md's rule applies
from now: **never train on it, never recycle it.**

**"Isn't task 29's data already in `docs/tasks/refactor/mock/`?"** **No, and this is the
single easiest mistake to make in this repo — it was asked once already.** That directory
holds `mock-postings-v3.json`, its answer key and an addendum: **55 postings that do not
exist**, invented to a specification, with `source = 'mock'` on every one and
`generated_by ∈ {human, claude, gpt, glm}`. Nexora AI, Aurelian Intelligence and Vireo
Cognitive Systems are not companies.

They are a **specification test** (DEC-46). They measure agreement with an author's intent,
which is why an agent could produce them at all — and it is precisely why they are not
labels. Writing them into `eval_labels` would reproduce `claude-bench.py:417`'s defect
inside the tool built to detect it. ~~and `tests/test_labels.py:423` forbids it
structurally~~ — **CORRECTED 2026-07-29: that line does no such thing**, and it has not
held still long enough for a line number to describe it (see § *task 29's "two mechanical
minutes"* for what it actually says). The containment is `backend/evals/mock_corpus.py:3-6`,
pinned by `backend/tests/test_mock_corpus.py:939`, with `:919` and `:930` asserting that
nothing under `ingest/` and no step in `STEPS` references the module — and
**`pool_query()` has no platform filter at all**.
**Nothing from that corpus has ever reached the database**, and that remains true: the
`jobs` table has nine platforms and none of them is `mock`. The claim was right and the
citation was not.

**Task 29 needs ~200 REAL postings from the live table, labelled by ~10 human Builders on
two axes.** Axis B *is* Builder preference; there is no artifact that can stand in for it.
**The 200 are now drawn** — `pursuit-v1`, pinned at
`backend/evals/fixtures/labelset-pursuit-v1.jsonl` — and **`eval_labels` is empty**, which
is the state it should be in until people fill it.

**What the mock corpus legitimately did** is pre-answer one narrow slice: task 29's
`gate_rejected` stratum (this file used to call it the *fourth* of five; `classify()`
produces **three**, and `pursuit-v1` drew 50 of them) asks whether the gate rejects good
postings, and 25 constructed rejects
with known verdicts could bound that without people. It fired, at 48.3%, and step 0 acted
on it. **That is one question of one bucket, on invented postings.** It reduced task 29's
scope by zero postings.

**"The mock harness says the four rejected phrase families cost nothing. Why not add
them?"** Because the mock corpus cannot see their cost. They admit +17/+5/+5/+123 live
rows of senior engineering requisitions at AI employers, and `\ywe train\y` matches
OpenAI's *"we train models"*. This is the single most likely thing for a fresh session to
"fix", which is why `backend/tests/test_pursuit_gate.py` carries a sentinel asserting
their absence with the counts in its docstring. **The general form: a synthetic corpus can
bound recall but cannot price precision, because its negatives were written by whoever
wrote its positives.** See § *the gate fix LANDED*.

**"The gate config is in a file now. What breaks if I move it again?"**
`tools/mock-acceptance.py`'s `cohort_relevance()` and
`migrations/migrate_pursuit_profile.py`'s `COHORT_RELEVANCE`, both of which read
`backend/config/pursuit-relevance.json`. Move it without moving them and the harness
measures one gate while the pipeline runs another, reporting "no change" —
indistinguishable from the fix having done nothing. `tests/test_pursuit_gate.py` asserts
all three agree.

**"I edited the gate. What re-runs?"** Nothing automatically, and the gate is not a
`criteria_version` input — relevance gates *extraction*, not scoring, so `match.py`
recomputes nothing and existing `job_matches` are untouched. What does change is
`extract.remaining`: the widened gate took it 2 → 13, and that backlog drains on the next
nightly. **`migrate_profiles.py` warns you about a changed `criteria_json` and says
nothing at all about a changed gate** (`:242-249` has no relevance equivalent), so verify
a gate write with `tools/relevance-report.py` and an md5, not with the script's output.

**"The mock corpus measured gate recall at 48.3%. Does that mean task 29 is done, or
partly done?"** Neither. It measured task 29's `gate_rejected` stratum on **constructed**
postings, which is why it could be done at all without people. Nothing was written to
`eval_labels` — it is still empty — no Axis B exists, and the corpus was built to contain
the failure modes
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

**Live state, recorded 2026-07-29 — ARCHIVED.** Two dated snapshots and their
attribution reasoning moved 2026-08-01 → [`docs/archive/handoff-tree-state.md`](../../archive/handoff-tree-state.md).

## Cross-stream lessons — PROMOTED

> **Promoted 2026-08-01 to [`docs/MEASUREMENT-TRAPS.md`](../../MEASUREMENT-TRAPS.md)** §
> *Later additions*, which is the copy to read and to cite. Four paragraphs of method sat
> here, deep inside a rolling handoff about a labelling session: three agents on strictly
> disjoint *files* still interacted because the database is shared; the other agent in the
> room is the cron job; a pin on set membership buys nothing about the derived facts; take a
> content digest, because a row count cannot see an overwrite.
>
> **None of it is about Pursuit, Builders, job postings, one persona or one model**, which is
> [`DOCS-POLICY.md`](../../DOCS-POLICY.md) rule 5's test, and § *How this run works* below is
> the precedent — same move, same reason. The text is unchanged;
> `git log -p -- docs/tasks/refactor/HANDOFF.md` reaches it at this path.

## How this run works — PROMOTED

> **Promoted 2026-08-01 to [`docs/WORKING-METHOD.md`](../../WORKING-METHOD.md), which is
> the copy to read and to cite.** Roughly a hundred lines of method sat here, about 1,500
> lines into a rolling handoff about a labelling session: verify the plan against the code before
> implementing it, verify the plan's *arithmetic* against the artifact, a green suite does
> not mean the brief was met, a finished artifact is where the defects the checks cannot
> see live, a measurement's denominator needs an adversarial reader, and verify rather than
> trust the report.
>
> **None of it is about Pursuit, Builders, job postings, one persona or one model**, which
> is [`DOCS-POLICY.md`](../../DOCS-POLICY.md) rule 5's test, and
> [`docs/MEASUREMENT-TRAPS.md`](../../MEASUREMENT-TRAPS.md) is the precedent — same move,
> same reason. The text is unchanged; `git log -p -- docs/tasks/refactor/HANDOFF.md`
> reaches it at this path.
>
> **What it says about *this* run stays in this file** and is not repeated there: the two
> tracks above, what is blocked below, and the findings later tasks must not inherit.

## What is blocked, and on what

**Human judgement — cannot be substituted.** Task **07**'s golden set needs human labels:
`docs/ingestion_tests/03-metrics-and-golden-set.md:25` requires the human self-agreement
ceiling ("5-10 jobs labelled twice, a week apart") and tranche two's 07 adds
inter-annotator agreement, needing two people. Axis B *is* Builder preference — a model
standing in for it makes the measurement circular, the exact defect `03:13` names in
`claude-bench.py:417`, which treats `sonnet-batch-1` as ground truth. **07's tooling is
now built (`3a8b42c`) and produced zero labels, by design and by test.** The form is
server-rendered HTML at `/v1/label` behind the existing Google SSO. Task **29** is the
labelling session itself and stops entirely. **30** sits behind it. **12** needs Axis A
figures.

**Updated 2026-07-30 on the ceilings, because this paragraph names both and they are not
the same ask.** The **inter**-annotator ceiling comes free from the overlap block on the
night itself. The **intra**-annotator one ("5-10 jobs labelled twice, a week apart") was
**not collectable at all** until 2026-07-30 — `next_item()` had no `round_no` predicate,
so a posting a labeller had answered was never served again — and now costs a **second
sitting, seven days later**. `interpretable()` takes the inter-annotator cell as
`ceiling`, so nothing is blocked on round 2 ever happening. **Whether to spend it is the
repo owner's decision on the night.** See § *the ceiling was unreachable*.

**And note which task the ops question belongs to, because § *recommended next steps* got
it wrong:** *"**12** needs Axis A figures"* above is the correct statement of it. The ops
shortfall — 42 under the title-probe floor — is task 12's finding, at
`docs/facts-v3-diff.md:328-333`. **Task 08 is not waiting on labels**; it *"Blocks:
nothing, but should precede 30"* and its one open clause waits on `job_events` having
rows (`docs/ingestion_tests/04-score-validation.md:33-36`).

~~**"What is missing is people" was not the whole truth, and this matters because it makes
task 29 look more shovel-ready than it is.**~~ **SUPERSEDED 2026-07-29 — the schema, the
sampler and the set are all done, and "what is missing is people" is now the whole truth
after all.** The block below is kept because it is the record of what was believed, and
because one line of it turned out to be the expensive one. Struck through where it is now
false:

- ~~**The label tables do not exist in the live database.**~~ **They exist now.**
  `eval_label_sets`, `eval_label_items` and `eval_labels`, defined in `evals/labels.py` and
  created by `python3 -m evals label init-schema` run as `jobs_pipeline`, with `jobs_web`
  granted per `labels.WEB_PRIVILEGES` (`:240`) and `verify_schema()` (`:353`) passing. **The
  file was right that they did not exist** — a `LIKE '%label%'` query really did return
  nothing.
- **There is a second path that does not need the webapp**, and it is the one that was
  used: `python3 -m evals label init-schema` reaches the same function deliberately, so the
  two cannot drift (`schema_web.py:161-166` says so). `sample`, `export`, `status` and
  `report` are on the same CLI.
- ~~**No eval set has ever been drawn.**~~ **`pursuit-v1` is drawn and pinned** —
  n=200, seed 0, overlap 10, **surfaced 100 / below_floor 50 / gate_rejected 50**,
  `sha256(sorted job_id)` `afb2d58f…`, at
  `backend/evals/fixtures/labelset-pursuit-v1.jsonl`. **The strata are not the five this
  paragraph used to name** (50/60/40/30/20); `classify()` produces three, plus a `None` for
  rows the pipeline has not yet had an opinion about.
- ~~**The form itself does need `fastapi`.** Serving `/v1/label` to ten people is the step
  that requires installing it and standing the webapp up — which is also task 33's
  territory.~~ **WRONG on both halves.** `fastapi` is installed, in `backend/webapp/.venv`;
  the route exists at `backend/webapp/label.py:241/:296/:364` (was `:218/:256/:311` before the round-2 path), wired at
  `webapp/app.py:91`. **No install, no code, and it does not wait on task 33.**

~~**So the honest ordering for task 29 is: `init-schema`, then `sample`, then get the form
served, then find ten Builders.** The first two are minutes and need no credential.~~
**The first two were not minutes.** `sample` carried **four** defects — wrong gate, starved
window, one-labeller ceiling, and an unstratified overlap block that put the
inter-annotator ceiling on the easy cases — and none of them was red. The fourth was found
**after the set had been drawn, pinned and committed.** See § *task 29's "two mechanical
minutes"*. **And "draw the sample AFTER the gate fix" was correct and inoperative**: the
sampler was resolving `relevance.load()` rather than the profile's own gate, so the
constraint this file had recorded bought nothing until `relevance.for_profile()` made it
real. A real dependency that no artifact shows you is being violated is worse than one
nobody wrote down.

> **SUPERSEDED 2026-07-30 — task 29 is blocked on NOTHING.** The two items below were the
> last of it and both are closed: the OAuth credentials are in `backend/webapp/.env` and
> `config.oauth_configured()` returns True; `FRONTEND_ORIGIN` and `ALLOWED_ORIGINS` are
> `http://localhost:8421`; the owner's `app_users` row is on `pursuit`. **Ten Builders is
> no longer a blocker either, only a ceiling constraint** — one labeller can start now,
> and one *second* person on the ten `overlap` rows is what makes the report render. See
> § *task 29 is UNBLOCKED*. The text below is kept as the record of what was blocking.

**~~What task 29 is blocked on now, and it is only two things, both the repo owner's:~~**

1. **Google OAuth credentials.** `GOOGLE_CLIENT_ID` and `GOOGLE_CLIENT_SECRET` are empty
   strings in `backend/webapp/.env`, so `/v1/auth/login` returns **503**
   (`webapp/auth.py:235-239`). **There is no auth bypass anywhere in `webapp/`, and that
   is deliberate.** Do not add one to get a labelling session started.

   **And `FRONTEND_ORIGIN` is wrong today, confirmed 2026-07-30, in the silent
   direction.** It is `http://localhost:5173`, and the post-login redirect is built from
   it (`auth.py:359-360`). `/v1/label` is served by **this service on `:8421`** (per
   `GOOGLE_REDIRECT_URI`), and **`frontend/` is a lone `.gitkeep`** — nothing runs on
   `:5173` and there is no dev server to start. **With the secrets filled in and nothing
   else changed, sign-in SUCCEEDS and lands on a dead origin**: cookie set, no error, no
   log line. **One-line fix, made alongside the secrets** — set it (and
   `ALLOWED_ORIGINS`) to the origin volunteers actually reach.
2. **Ten Builders, each with a row**: `manage_app_users.py add --email ... --profile
   pursuit`. **Note the two-allowlist trap**: while the consent screen is unverified, an
   address must be in the Google console's **Test users** list *and* in `app_users`, and
   **only one of those two failures produces an error message from this service**
   (`backend/webapp/README.md:143-151` — the section is *"What a Builder actually does"*;
   this file previously cited `:149-151`, which is the middle of the same list item).
   Also note that the **single existing `app_users` row is `ericliu93@gmail.com` on
   profile `tech`**, which task 12 made inactive — **not a working example of a cohort
   labeller**, and copying its shape adds people to a dead profile.

**`docs/tasks/refactor/LABELLING-NIGHT.md` is the executable version of both of these**,
in order, at ~15 minutes — added 2026-07-30, including what NOT to do (no auth bypass; do
not redraw the set) and the optional round-2 follow-up with its seven-day delay.

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
  **AMENDED 2026-07-29 — the specific defect is fixed and the general warning stands.**
  `cohort_relevance()` now reads `config/pursuit-relevance.json`, the same file the
  pipeline is configured from, and `tests/test_pursuit_gate.py` asserts it. But it still
  never reads the `pursuit` **row**: it installs its own copy into a scratch schema
  (`:272-311`). **A green mock run does not mean production changed** — only the write in
  commit 4 does that. `--dry-run` is free re-measurement of whatever the harness is
  pointed at, which is a config file, not the database.
- **Candidate gate terms ranked on the mock corpus rank the OPPOSITE way on the live
  corpus, and the mock corpus scores the bad ones as free.** Measured 2026-07-29:
  `we provide … training` +17 live rows, `we (will) train` +5, `preferred but not required`
  +5, `experience … is a plus` +123 — all four admitting senior engineering requisitions at
  AI employers, and `\ywe train\y` matching OpenAI's *"we train models"*. On the mock corpus
  all four add **zero** false positives, because every intended-bad mock posting carrying
  that phrasing has no AI vocabulary at all. **That is a property of a corpus written to a
  specification.** Any vocabulary decision taken on `mock-acceptance.py` alone is untrusted;
  compile the candidate through `relevance.tier_sql` against the live table before shipping
  it. Asserted by `tests/test_pursuit_gate.py`; see § *the gate fix LANDED*.
- **Step 0's cost caution pointed at the wrong risk.** "Widening the gate widens the
  extraction queue — check the volume against `extract.py`'s drain" is answered and was
  never the constraint: the shipped fix is **+11 rows**, `extract.remaining` 2 → 13 (both
  confirmed after the write), under
  half of one `EXTRACT_BATCH_SIZE=40` batch. Extraction has ~15x headroom
  (`EXTRACT_DEADLINE_SECS=3600` × 3 workers ≈ 1,260 calls/hour against 43–80/day intake),
  and `drain_loop` (`extract.py:1125-1159`) lifted the old 40/day ceiling. **A widened gate
  is priced by the one-time backlog it creates, not by steady state**, and the real cost is
  precision.
- **Fixing the gate did not meaningfully change what task 29's labellers see.** +11
  postings on an 869-row pool is **+1.3%**. Doing it first was still right — the defect is
  real, the fix is cheap, and a labelling session run through a knowingly-broken gate is
  wasted — but step 0's ordering rationale implies a recovery it does not deliver, and it
  moves the GATE 2 "≥200/day" question not at all.
- **48.3% is a recall figure against a corpus built to contain the failure mode it
  measures, and so is 89.7%.** The best new term matches **18 rows anywhere** in 13,447
  open live postings. The fix is correct and shipped, but **"recall was 48.3% and is now
  89.7%" is a statement about the mock corpus and must be written that way wherever it is
  quoted.**
- ~~**"Task 29 is blocked on people" was incomplete, and it made the task look more
  shovel-ready than it is.** … **Two mechanical minutes were being described as "what is
  missing is people".**~~ **CORRECTED 2026-07-29, and the correction was itself wrong in
  the other direction.** The tables genuinely did not exist and no set had been drawn — that
  much held. But **the two commands were not two mechanical minutes**: `evals label sample`
  classified against the shared author gate rather than the profile's (**59 `surfaced`
  against 144**), truncated its pool to 400 rows per platform (**29 of 144 surfaced rows
  reachable**), served every labeller an identical queue (**distinct coverage capped at
  one person's throughput**), and marked an **unstratified** overlap block (**6 of 10 rows
  `gate_rejected` against an expected 2.5**). All four fixed in `c65d34b` / `2f64e08` /
  `90170d1`; see § *task 29's "two mechanical minutes"*. **Calling work mechanical is a
  claim about code, and it fails the same way every other claim about code in this file has
  failed — by not being checked against the code.**
- **A tool that takes a `profile` argument and resolves its config by default will read
  the wrong config, and nothing will look wrong.** `labels.pool()` / `pool_query()`
  defaulted `cfg` to `relevance.load()` — the shared `config/relevance.json` — while its
  first parameter was the profile naming the population. Fixed by
  `relevance.for_profile()` (`relevance.py:100-109`) and by having the caller load the
  profile row and pass the gate in explicitly (`evals/__main__.py:279-292`). **The general
  form: if a function takes the name of a thing, it must not independently default the
  thing's configuration.** `relevance.load()` is a legitimate default for a caller that has
  no profile; it is never a legitimate default for one that does.
- **`tools/derive-role-tracks.py` probed the `other` bucket across EVERY vocabulary the
  project has ever had, and the conclusion that inverts is task 12's.** Found and fixed
  2026-07-31. `load_other()` had no `facts_version` filter, so its `other` population was
  **696 rows — 402 of them at `facts_version = 2`, the TWELVE-value vocabulary, which never
  contained any of the values being probed.** 58% of what the tool called "postings the 26
  values failed to describe" were postings the 26 values were never offered for. The
  printed reclaim figures moved accordingly:

  | candidate | raw `other` matches, unfiltered | at `facts_version = 3` |
  |---|---:|---:|
  | `hardware_embedded` | 54 | **3** |
  | `infrastructure_compute` | 42 | **2** |
  | `engineering_management` | 32 | **0** |
  | `qa_test` | 22 | **0** |
  | `mobile` | 16 | **0** |
  | `business_systems` | 15 | **0** |
  | `developer_relations` | 11 | **0** |
  | `ai_operations` | 10 | **0** |

  **The conclusion this inverts: the 26 values ARE being used by the extractor.** Reading
  the unfiltered column, task 11's tech values look inert — 54 `hardware_embedded`-shaped
  postings still sitting in `other` says the vocabulary was added and ignored. At v3 there
  are three, and five of the eight are at zero, which says the opposite: **the extractor is
  applying them, and the v3 `other` bucket is a different gap.** Fixed by a
  `--facts-version` flag defaulting to `schema.FACTS_VERSION`; the population is now printed
  in the header of every run (`'other' population: facts_version 3, 294 rows`), and
  `--facts-version 0` reproduces the historical figure for anyone checking this entry.
  **Same family as the `labels.pool()` defect immediately above** — a tool that resolves a
  population by default resolves the wrong one, every marginal still adds up, and nothing
  looks wrong. **The general form: a tool that reports on "the current vocabulary" must say
  which version it read, in its own output, every time.**
- **A TOTAL IS NOT A COMPOSITION, and the sub-block that carries a whole measurement needs
  its own stratification.** `sample()` marked the first `overlap` rows of a `job_id` sort.
  The set's strata totals were exactly right — 100/50/50, checked and committed — while the
  ten-row overlap block inside them was **6 `gate_rejected` / 3 `surfaced` / 1
  `below_floor`** against an expected 2.5/5/2.5. **That block is the entire inter-annotator
  ceiling**, so six rows of discarded postings, on which every labeller says "no" and agrees
  for free, would have inflated it. Fixed by largest-remainder proportional allocation
  (`evals/labels.py:665-679`, rationale `:648-664`). **Three of this session's four defects
  were found by measuring an artifact that had already passed its own checks** — every
  marginal still summed correctly in all three cases. **Disaggregate, and look at what is in
  the bucket.**
- **A drawn eval set can be redrawn only while `eval_labels` is empty, and that must be
  CHECKED rather than assumed.** Redrawing after anyone has labelled silently reassigns
  what their answers were answers to. The defect-4 redraw checked and refused on it; **that
  window is now closed for `pursuit-v1` the moment the first Builder submits.** Note also
  that a redraw does not necessarily move the pin: `sha256(sorted job_id)` was unchanged,
  because membership did not change — **only the `overlap` flags did, and no digest in this
  file could see that.**
- **An idealised formula is not a measurement, and here the gap was 26 postings and a
  Definition of done.** `distinct = overlap + n * (budget - overlap)` assumes **disjoint**
  windows. Rotating labellers by `sha256(labeller_id)` gives *random* windows, which
  collide — the birthday problem. The formula predicted 110; **verifying against the drawn
  set gave 84.** Rank spacing by `2**64/phi` gives 110. Recorded with both numbers in
  `tail_offset()`'s docstring (`evals/labels.py:874-883`), and the constant `_PHI64`
  (`:866`) carries its own comment (`:859-865`) saying it is there for low discrepancy and
  not as a hash — so it cannot be simplified back to one. **Verify a plan's arithmetic
  against the artifact, not against the algebra.**
- **`sample()` under-fills a stratum in silence, and `PARTITION BY platform` does not fix
  the window underneath it.** These are two different traps and one was being read as a
  guard against the other: platform partitioning answers CLAUDE.md's "~85%
  greenhouse/ashby" composition complaint and says nothing about recency truncation.
  `cmd_label_sample` now exits 2 and names the shortfall (`evals/__main__.py:306-345`).
- **`pool_query()` has NO platform filter of any kind.** Nothing structurally prevents a
  `platform = 'mock'` row being drawn into an eval set. **Not live** — the `jobs` table
  carries nine platforms and none is `mock` — and the containment that does exist is
  upstream, at `backend/evals/mock_corpus.py:3-6` with
  `backend/tests/test_mock_corpus.py:919` and `:930`. Recorded rather than fixed, because the
  right guard is the one that stops such a row being *written*, not one that filters it at
  read time.
- **`docs/tasks/refactor/mock/` is NOT task 29's data**, and the question has been asked
  out loud, so it will be asked again. 55 invented postings at `source = 'mock'`, written
  to a specification, and reducing task 29's scope by **zero postings**. They legitimately
  pre-answered one question of one stratum — gate recall — and nothing more.
  ~~forbidden from `eval_labels` by `tests/test_labels.py:423`~~ **— WRONG CITATION,
  corrected 2026-07-29.** Today that line is a `role_archetype` fixture row inside
  `test_the_two_ceilings_are_different_quantities` (`:416`); it says nothing about
  `source = 'mock'` and never did. **The conclusion is still true and the reason is
  different**: `mock_corpus.py:3-6` binds the module, `test_mock_corpus.py:939` pins the
  caveat to it, and `:919` / `:930` assert no `ingest/` module and no `STEPS` entry
  references it. **A wrong citation survived two sessions inside a file whose own rule is
  to re-read the line** — and while it was being corrected, the line moved twice more.
  **Quote the line's text when a claim rests on it.**
- **`AI_VOCAB` had exactly ONE copy, not two.** Step 0 required a test asserting "the two
  copies are equal"; it was one list referenced twice (`:216`, `:229`), so the assertion
  could not fail. Moving the gate to JSON is what created two literals and gave the test
  teeth. **A test that cannot fail on the code it was written for is documentation.**
- **`relevance.load()` merges a profile's config over `DISABLED`, not over
  `config/relevance.json`** (`relevance.py:88-90`). **A per-profile gate must be complete,
  not a patch** — an omitted key does not inherit the shared file's value, it goes
  permissive. Pinned by `test_pursuit_gate.py`.
- **`profiles.upsert` stores NULL for a falsy `relevance_cfg`** (`profiles.py:207`), so an
  empty dict from a failed load silently reverts a profile to the shared author gate,
  with no error. The post-write `md5(relevance_json)` is the only thing that catches it.
- **`NULL !~* 'x'` is NULL, not TRUE**, so a NULL `company_name` or `platform` makes the
  whole `row_ok` conjunction NULL and the row falls silently to tier 3. **Not live** — 0
  of 14,049 rows carry a NULL in either — but a test fixture built with NULLs reports
  every row rejected, and every "expected rejected" assertion in it passes for the wrong
  reason. Found that way, then pinned by a test rather than worked around.
- **`--force-placeholders` is not a flag on `migrate_profiles.py`.** It is on
  `migrate_pursuit_profile.py:462-465`. Step 0's "Never `--force-placeholders`" warned
  about the wrong script.
- **`migrate_pursuit_profile.py`'s refusal fires BEFORE the `--apply` check**, so even a
  dry run exits 1 while stored `criteria_json.archetypes` is non-empty. It was already
  retired as a write path; that is what made moving the gate out of it coherent rather
  than merely tidy.
- **`migrate_profiles.py` warns when criteria change and says NOTHING when the gate
  changes.** `:242-249` fires on a criteria diff without `--bump`; there is no equivalent
  for `relevance_json`, even though changing it changes which rows are eligible for paid
  extraction. Verify a gate write with tier counts and an md5, not with the script's
  output.
- **`migrate_profiles.py` does NOT leave criteria and persona untouched.** It overwrites
  both wholesale from the files on every run (`:124-128`, `:256-261`), and `--persona-file`
  defaults to `config/persona.json`, **the author's tech persona** (`profiles.py:221-224`).
  Only `relevance_json`, `daily_narrative_budget` and `active` are preserve-on-absent
  (`resolve_preserved`, `:112-145`). Running it against `pursuit` without both file flags
  writes the wrong persona. Step 0's commit 4 was safe only because both files were
  confirmed dict-equal to the stored values first, and verified again afterwards by md5 —
  **that is a pre-flight check, not a property of the script.**
- ~~**`ENTRY_LEVEL` is a title vocabulary and the pursuit gate applies it to
  descriptions.**~~ **FIXED 2026-07-29 (`e8f3b72`).** The group is split by field:
  `title_include` keeps the eleven nouns, `description_include` is a strict superset of
  them plus three phrases. Mock recall 48.3% → 86.2% on that change alone. The vocabulary
  now lives in `config/pursuit-relevance.json`, not in the migration.
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
- ~~**`fastapi` is not installed in this environment**, so `backend/webapp/tests/` cannot
  run at all — five modules fail to import, four of which predate this run.~~ **WRONG,
  corrected 2026-07-29.** `fastapi` **is** installed — 0.140.0, with uvicorn, starlette,
  pydantic and httpx — in **`backend/webapp/.venv`**, a separate environment with a
  separate `backend/webapp/requirements.txt` listing exactly those five packages and
  `include-system-site-packages = false`. Under it, `backend/webapp/` reports **55 tests,
  OK**. **The original observation was made with system python**, and
  `backend/requirements.txt` being `psycopg[binary]` alone is what made it look confirmed.
  **The consequence: serving `/v1/label` needs no install and no code** — the route is at
  `backend/webapp/label.py:241/:296/:364` (was `:218/:256/:311` before the round-2 path), wired at `webapp/app.py:91`, server-rendered and
  already blind to `fit_score`. Every estimate here that priced it as an install plus task
  33's territory was pricing work already done. `backend/tests/` is still the suite that
  gates work here and still does not cover `webapp/`; **there are two interpreters, and a
  claim about an import is a claim about which one you ran.**
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

**Task 29 is the whole critical path and it is still the one thing in this plan that
cannot be done by an agent.** Step 0 — the gate fix — is done, and so is everything on 29
that an agent *could* do: the schema, the sampler and the drawn set. ~~**What is left of 29
is two asks of the repo owner** — OAuth credentials and ten Builders.~~ **Both closed
2026-07-30: the credentials are in and the owner's account is on `pursuit`. What is left
is the sitting itself.** Everything else in this list needs credentials (15, 20) or a
re-scope (21).

> ~~**AMENDED 2026-07-31. The sitting has started, and the single highest-value action is no
> longer "label more" — it is "get one more person for half an hour."** 30 labels exist
> from one labeller. … The ask is ~26 minutes at
> the measured rate, not the ten minutes this file says three times.~~
>
> **AMENDED AGAIN 2026-07-31, later the same day. The conclusion is unchanged and both of
> its numbers moved in the good direction.** 186 labels / 31 postings exist from one
> labeller, and **all ten `overlap` rows are among them.** Every field in the report is
> still refused for want of a *second* `labeller_id` on the same item, not for want of
> volume — so **the tenth row from a second person is worth more than the hundredth row
> from the first**, and it is now the *last* thing the ceiling needs rather than the first.
> The ask is **~16 minutes** at the re-derived rate (§ *the stopwatch reading*), not the
> ~26 written above and not the ten written three times before that.

0. ~~**Fix the relevance gate.**~~ **DONE 2026-07-29** — `4eefb7e`, `e8f3b72`, `9dab9e6`
   and a database write. Mock gate recall 48.3% → 89.7%, live tier ≤2 869 → 880,
   `extract.remaining` 2 → 13, and the suite grew — the before/after pair is in
   [`docs/archive/handoff-gate-fix.md`](../../archive/handoff-gate-fix.md), which owns it,
   and [`AUDIT.md`](AUDIT.md) owns the current count. See § *the gate fix LANDED*.

   **What a fresh session must not undo.** The four phrase families recorded there admit
   ~136 live junk rows and the mock harness scores every one of them as free.
   `backend/tests/test_pursuit_gate.py` asserts their absence; read it before widening the
   vocabulary. And the gate now lives in `backend/config/pursuit-relevance.json` — if it
   ever moves again, `tools/mock-acceptance.py`'s `cohort_relevance()` moves with it, or
   the harness measures one gate while the pipeline runs another.

   **What it did NOT buy: +1.3%.** Eleven postings on an 869-row pool. It does not
   meaningfully change what task 29 sees and it moves GATE 2 not at all.

1. **Task 29 — the labelling session, and it is now the only thing on the critical
   path.** 07's tooling is built and produced zero labels by design.

   ~~**Do these two first — they are mechanical, take minutes, need no credential and
   no `fastapi`:** `init-schema`, then `sample`.~~ **DONE 2026-07-29 — `c65d34b`,
   `2f64e08`, `90170d1`, plus a database write — and they were not mechanical.** The schema
   exists, the grants are issued, and **`pursuit-v1` is drawn and pinned**: n=200, seed 0,
   overlap 10, surfaced 100 / below_floor 50 / gate_rejected 50, `sha256(sorted job_id)`
   `afb2d58f…`, at `backend/evals/fixtures/labelset-pursuit-v1.jsonl`, with a stratified
   overlap block of 5/3/2. `sample` had **four** defects first — wrong gate, starved window,
   one-labeller ceiling, unstratified overlap — none of them red, and **the fourth was
   found after the set was committed**. § *task 29's "two mechanical minutes"* is the
   record.

   ~~**Do not redraw this set.** It can only be redrawn while `eval_labels` is empty, and
   the first submitted label closes that window.~~ **MOOT 2026-07-31: the window is closed.**
   ~~30 labels~~ **186 labels over 31 postings** exist, so `redraw_refusal()` refuses every
   redraw including an identical-digest
   one. This is no longer an instruction to follow — it is a property of the system, and
   the set is what it is. **The cost is already visible:** a mid-level bridge role that is
   exactly the hard case worth a label (Notion `8ba8616b7c91d2a1b5112cdc`,
   § *Pending follow-ups*) is not in the set and cannot be added.

   **What to do next, in order. REORDERED 2026-07-31 — the old list's steps 1 and 3 are
   done or cheaper, and a step has been added at the end that did not exist yesterday.**

   1. **Get the second labeller. Ask for about twenty minutes — not half an hour, and not
      ten minutes.** Ten `overlap` rows at the re-derived rate is **~16 min**
      (§ *the stopwatch reading*). This is not merely still the cheapest unblock in the
      task: **the owner has now finished all ten `overlap` rows**, so those ten rows are
      the last input `labels.inter_annotator()` needs and `evals label report` prints the
      moment they land. It is the difference between *"the model disagrees with Builders"*
      and *"the model disagrees with Eric"*, which `consensus()` cannot currently tell
      apart. **Set their `--prior-domain` when you add them.** That flag stopped being a
      nicety today: the recall finding's second caveat is a `prior_domain` confound that
      **cannot be decomposed at n=1** (§ *How many to label*), and a second labeller from a
      *different* background is the only instrument that touches it.
   2. **Then label to ~60**, which is **1.6 h** at the re-derived rate — not the 2.6 h this
      list said — and is where an observed 85% starts excluding 0.94. Stop wherever —
      § *How many to label* verified 2026-07-30 that the strata are interleaved, so **any
      prefix is a proportional miniature of the whole set** and there is no wrong place to
      stop. 31 of the 200 are done.
   3. ~~**Re-derive the timing number** from `labelled_at` once there are more rows, and
      overwrite § *the stopwatch reading*. n=4 intervals is not a rate.~~ **DONE
      2026-07-31 at n=29, and it overturned the section.** `tools/label-findings.py
      --timing` is now the instrument; re-run it, don't re-quote it.
   4. **NEW — decide whether the recall question buys the back half.** It is earned on this
      file's own stated trigger: two `gate_rejected` postings and one `below_floor` one
      turned out to be roles the labeller would apply to (Ramp, Twilio, Brex —
      § *How many to label*). 200 postings is **5.2 h** for one person at the measured
      rate. **The
      decision is the repo owner's and the evidence for it is a trigger, not a rate** — the
      three strata's Wilson intervals overlap almost completely at n=31.
   5. **NEW — do NOT apply the `revenue_commercial` archetype while labelling is open**,
      however good the corpus evidence looks (23.1% of the v3 `other` bucket from one
      value, against 47 rows from the fourteen task 11 adopted). It is a `FACTS_VERSION`
      bump, and a bump re-extracts the model answers these labels exist to be compared
      against, mid-collection, on a set that cannot be redrawn. Full proposal and its gate:
      § *Pending follow-ups*.

   **What NOT to do:** compute model-vs-human agreement and write it down. `evals label
   report` exits 2 at one labeller by design and there is deliberately no `--force`; a
   number computed around that refusal and pasted into a document has no exit code to
   protect the next reader. Get the second labeller and the report prints by itself.

   **29 blocks 30, and ONLY 30.** `29-labelling-session.md:3` said *"Blocks: 30, 31"*;
   corrected 2026-07-30. `tranche_six/31-dismiss-demotion.md:3` reads *"Depends on: 27,
   26. Blocks: nothing"* and **31's body never mentions labels** — it needs the event
   schema and profile creation, not human judgement. Worth knowing because it makes the
   critical path one task narrower than this file implied: **31 can proceed without the
   labelling night.**

   **~~What is left is two asks of the repo owner and nothing else:~~ BOTH CLOSED
   2026-07-30 — kept below as the record. What is left is the sitting.**

   - **Google OAuth credentials** in `backend/webapp/.env`. `GOOGLE_CLIENT_ID` and
     `GOOGLE_CLIENT_SECRET` are empty strings, so `/v1/auth/login` returns 503
     (`webapp/auth.py:235-239`), and `FRONTEND_ORIGIN` must point at the serving origin or
     sign-in succeeds and lands nowhere (`auth.py:359-360`). **There is no auth bypass in
     `webapp/` and none should be added.**
   - **Ten Builders**, each with `manage_app_users.py add --email ... --profile pursuit`.
     **Two allowlists have to agree** while the consent screen is unverified — Google
     console Test users *and* `app_users` — and only one of the two failures produces an
     error from this service (`backend/webapp/README.md:149-151`). The one existing
     `app_users` row is on `tech`, which is inactive.

   **Serving `/v1/label` needs no install and no code.** `fastapi` is in
   `backend/webapp/.venv` and the route exists at `backend/webapp/label.py:241/:296/:364` (was `:218/:256/:311` before the round-2 path),
   wired at `webapp/app.py:91`. This item used to say otherwise and used to route through
   task 33; it does not.

   **Budget, decided by the repo owner: overlap 10, ~20 items each.** That breaks one DoD
   line (20 overlapped → 10) and buys **110 distinct postings** at ten labellers in a
   twenty-minute sitting. **At the DoD's 5-labeller fallback, ≥100 distinct needs ~28 items
   each** — know that before the night, not during it.

   **AMENDED 2026-07-30: both figures were computed against a FIVE-question form, and the
   form now asks SIX.** `role_track` was added (DEC-61), so ~20 items and ~28 items are each a
   larger sitting than when those numbers were set. **No replacement number is asserted
   here** — the per-posting time was never measured, only assumed, and inventing a
   correction factor would be the same mistake as the 110-vs-84 formula. **Re-check the
   budget before the night.** And if the round-2 second sitting is spent, that is **~10 more
   minutes per labeller**, at least seven days later, on the ten-row overlap block only.

   **Two specific questions are waiting on it**:
   ~~task 08 asked whether the ops shortfall is the title probe over-counting or the
   extractor under-applying;~~ **CORRECTED 2026-07-30 — the question is real and the
   attribution was wrong, in both places this file made it** (here and § *what is
   blocked*). **Neither `tranche_two/08-score-validation.md` nor
   `docs/ingestion_tests/04-score-validation.md` contains the words "ops",
   "operations" or "shortfall"** — checked by grep over both files. **08 is not
   waiting on labels at all**: it is *"Blocks: nothing, but should precede 30"*, and
   its one open clause is `04:33-36` — *"Whether `fit_score` is good stays open until
   `job_events` has data"* — which waits on **`job_events` having rows**, i.e. on the
   webapp's event endpoint being used, not on a labelling session.

   **The ops question belongs to task 12 and lives at `docs/facts-v3-diff.md:328-333`**,
   which states it exactly: *"either the title probe over-counts ops … or the extractor
   under-applies the ops values because its `role_archetype` guidance was written for
   software roles"*, and — this is the part that made it look label-blocked —
   *"The second is checkable with task 07's Axis A labels and is the more useful thing to
   check first."* So it **is** waiting on the labelling session; it is task 12's finding,
   not task 08's. This file already records it correctly one section up, in § *what 08, 12
   and 19 changed about the plan* item 5, where the ops five come in **42 under** their
   title-probe floor. **Keep the question, fix the number on the door.**

   The second question is unaffected: **task 13** asks whether its four floor misses —
   postings at `ai_involvement = 'none'` whose employers are AI companies — are the
   weights being wrong or being right (`DECISIONS.md:962-965`: *"Task 29's labels settle
   that; nothing available now does."*).

   ~~**This is also the only thing that makes re-tuning 13 legitimate.** The weights
   are unfitted by construction and `tools/calibrate-match.py` can sweep them for
   free the moment there is anything to fit against.~~
   **CORRECTED 2026-07-30. The first sentence stands; the second names a tool that
   cannot do it.** The path is `backend/tools/calibrate-match.py`, not
   `tools/calibrate-match.py`, and **its ground truth is `job_scores` — the LLM.** Its
   own docstring section is headed **"THE LABELS ARE FREE"** (`:44`) and reads:
   *"`job_scores` already holds real LLM judgements for profile `tech`, produced by the
   pipeline this replaces … Using them as ground truth means calibration needs no new
   API calls at all."* Its next section, **"WHAT IT IS NOT"**, says *"The LLM is not
   right, it is just the incumbent."*

   **So it cannot consume human labels today.** Pointing it at L0 needs a loader that
   **does not exist** — the labels are rows in `eval_labels`, keyed by
   `(job_id, field, labeller_id, round_no)` with an axis, not a `fit_score` per
   `(job_id, profile)`. **This matters because this file named that script as what
   makes re-tuning legitimate**, and as written it would sweep the weights against the
   very model the labels exist to check — CLAUDE.md's *"never evaluate on the layer you
   trained on"*, with L1 standing in for L0. Re-tuning against labels is real work with
   a real deliverable (an L0 loader), not a flag on an existing tool.

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

> **MOVED 2026-07-31 → [`docs/archive/handoff-session-measurements.md`](../../archive/handoff-session-measurements.md).** Session narrative through 2026-07-31. Retained for the figures and their instruments; the live numbers are in HANDOFF.md § State at handoff and AUDIT.md.

## How these sessions ran it, and what worked

> **MOVED 2026-07-31 → [`docs/archive/handoff-session-method.md`](../../archive/handoff-session-method.md).** Method notes from the same sessions. The durable half was promoted to HANDOFF.md § How this run works, and **promoted again 2026-08-01 to [`docs/WORKING-METHOD.md`](../../WORKING-METHOD.md)**, which is now the copy to read.

## Pending follow-ups with no task of their own

- **The per-posting labelling time is MEASURED at 93 s, n=29 ([`AUDIT.md`](AUDIT.md) owns it; stated here with its method),
  and the twenty-minute budget is out by ~1.5x in the CHEAP direction.** Re-derived 2026-07-31 with
  `python3 backend/tools/label-findings.py --timing`, over all 31 postings labelled by
  `u_090b0ad12e99` in `2026-07-31T02:56:05`–`05:25:27` UTC, one 5,765 s break excluded at
  `--break-secs 600` ([`AUDIT.md`](AUDIT.md)). Median **93 s**, mean **110 s**; including the break, median 97 s /
  mean 299 s (n=30). First 7 intervals mean **137 s**, last 7 mean **83 s** — there is a
  warm-up curve, and the n=4 figure below is its first four intervals. Budgets: ten
  `overlap` rows **16 min**, twenty minutes **13 postings**, 60 postings **1.6 h**, 100
  postings **2.6 h**, 200 postings **5.2 h**. § *the stopwatch reading* carries the raw
  interval list and the irony.

  > ~~**The per-posting labelling time is MEASURED, and the twenty-minute budget is out by
  > ~2.5x.**~~ **SUPERSEDED 2026-07-31, kept because the run planned against it for a day.**
  > Added 2026-07-31; this is the *"stopwatch reading"* § *How many to label* asks
  the next session to bring back. Derived from `eval_labels.labelled_at` over the first five
  labelled postings — successive `min(labelled_at)` per `job_id` — giving submit-to-submit
  intervals of **87 / 170 / 247 / 110 s**: **median 170 s, mean 154 s**. So **twenty minutes
  is ~8 postings, not ~20**; the ten `overlap` rows a second labeller contributes are
  **~26 minutes, not ten**; and the DoD's ≥100 postings is ~4.3 hours for one person.
  n=4 intervals, one labeller, submit-to-submit includes reading, and the *first* posting's
  reading time is not in the figure at all — so the true rate is **higher** than 154 s,
  not lower. This is a measurement of the six-question form rather than a correction factor
  applied to a five-question one, which is what this file warned against inventing.
  Re-derive it as the count grows. `tranche_five/29-labelling-session.md`
  § *Findings, 2026-07-31*, E.

- **No archetype or track expresses a commercial / sales role, and the cohort wants them.**
  Added 2026-07-30 from the owner labelling. `ARCHETYPE`'s 26 values contain no sales,
  account executive, business development or commercial value — its own comment reads
  *"The original twelve. All software engineering."* (`extract.py:262-266`) — and
  `ROLE_TRACK`'s nearest is `revenue_operations`, which is RevOps rather than selling.
  Separately, **`ai_involvement` cannot distinguish "uses AI" from "sells AI"**, so a strong
  target scores `none` and reads as task 05's 6.7%-precision false positive. **Nothing is
  scheduled to act on either**, and acting needs more than one Builder saying so. Full
  write-up in § *the first finding arrived BEFORE the first label*;
  `backend/tools/derive-role-tracks.py` re-runs the derivation.

  > **First entry on the side list this asks for, added 2026-07-31.** Notion, *Commercial
  > Solutions Consultant, New York*, job `8ba8616b7c91d2a1b5112cdc`, `ashby`, NYC, open.
  > **It confirms the "mislabelled `solutions` because the word matches" prediction on a
  > real row:** the title contains the literal word *Solutions* and the extractor returned
  > `role_archetype: solutions`, `role_track: solutions_and_implementation`. It is a
  > code-verified instance of the class and **NOT a second Builder agreeing** — the
  > *"acting needs more than one Builder"* bar is untouched by it.
  >
  > It also puts a number on the `ai_involvement` half. The row is extracted
  > `uses_ai_tools` and scores **63**; flipping only `ai_involvement` to `none` takes it to
  > **13**, and flipping seniority to `junior` as well still leaves it at **38 — below
  > `MATCH_FLOOR`, where no `job_matches` row is written at all.** So the conflation is not
  > a ranking nuisance, it is a deletion. **The posting is not in `pursuit-v1` and can never
  > be added** now that the redraw window has closed, so this session cannot settle it.
  > `tranche_five/29-labelling-session.md` § *Findings, 2026-07-31*, A.

  > **THE SIDE LIST IS NO LONGER ONE ENTRY. All 17, added 2026-07-31**, reproducible with
  > `python3 backend/tools/label-findings.py --side-list`. Population: the 31 postings
  > labelled by one labeller on 2026-07-31; these are the ones where the human answered
  > `role_track = no_track_fits` **or** `role_archetype = other`. **The model's own answers
  > are shown beside each — this is a side-by-side for reading the SHAPE of the gap, and it
  > is NOT a scored comparison.** There is no free-text field on the form, so this table is
  > the only place the content of *"none of these fit"* can live.
  >
  > | stratum | employer / title | human `track` / `arch` / apply | model `track` / `arch` / `ai` |
  > |---|---|---|---|
  > | `below_floor` | DEPT OF YOUTH & COMM D — *Operations Analyst* | `business_operations` / `other` / no | `business_analysis` / `other` / `none` |
  > | `below_floor` | SynergisticIT — *Junior Level/Entry Level Software Engineer* | `no_track_fits` / `other` / no | `software_engineering` / `fullstack` / `none` |
  > | `gate_rejected` | Finix — *Senior Technical Recruiter* | `no_track_fits` / `other` / no | — (no `job_facts`) |
  > | `gate_rejected` | NewYork-Presbyterian — *Senior Technologist Laboratory – Microbiology* | `no_track_fits` / `other` / no | — (no `job_facts`) |
  > | `gate_rejected` | NewYork-Presbyterian — *Licensed Engineer – 1 License – Rotating Shift* | `no_track_fits` / `other` / no | — (no `job_facts`) |
  > | `gate_rejected` | Shield AI — *Senior Mechanical Engineer, Systems Integration* | `no_track_fits` / `other` / no | NULL / `other` / `none` |
  > | `gate_rejected` | Wells Fargo — *Branch Operations Coordinator, Borough Park* | `business_operations` / `other` / no | — (no `job_facts`) |
  > | `surfaced` | Carta — *Finance and Equity Analyst – Rotational Program* | `no_track_fits` / `other` / no | `data_and_analytics` / `data` / `uses_ai_tools` |
  > | `surfaced` | Cohere — *Data Annotation Specialist, Arabic* | `no_track_fits` / `other` / no | `data_and_analytics` / `other` / `uses_ai_tools` |
  > | `surfaced` | Coinbase — *Specialist, Market Operations* | `no_track_fits` / `other` / no | `technical_support` / `support_ops` / `uses_ai_tools` |
  > | `surfaced` | EliseAI — *Product Solutions Analyst \| Housing* | `product_and_marketing` / `other` / no | `technical_support` / `support_ops` / `uses_ai_tools` |
  > | `surfaced` | Gemini — *Predictions Partnerships Marketing Coordinator* | `no_track_fits` / `other` / no | `product_and_marketing` / `marketing_ops` / `none` |
  > | `surfaced` | Gusto — *Future Opportunities: Retirement Implementation* | `no_track_fits` / `other` / no | `solutions_and_implementation` / `implementation_analyst` / `uses_ai_tools` |
  > | `surfaced` | Notion — *People Analytics & Operations (Rotational Program)* | `no_track_fits` / `other` / **yes** | `data_and_analytics` / `data` / `uses_ai_tools` |
  > | `surfaced` | Notion — *Commercial Solutions Consultant, Japan* | `no_track_fits` / `other` / no | `solutions_and_implementation` / `solutions` / `uses_ai_tools` |
  > | `surfaced` | Notion — *Commercial Solutions Consultant, San Francisco* | `no_track_fits` / `other` / no | `solutions_and_implementation` / `solutions` / `uses_ai_tools` |
  > | `surfaced` | Vanta — *AI Optimization Specialist, Support* | `software_engineering` / `other` / **yes** | `technical_support` / `ai_operations` / `uses_ai_tools` |
  >
  > **What the table says that the 2026-07-30 entry did not.** Only **2 of the 17 are
  > commercial/sales**, they are the two non-NYC variants of the role the entry above
  > names, and the owner said `would_apply = no` to both — location is an uncontrolled
  > confound and the NYC variant is not in `pursuit-v1`. **The bulk of the list is
  > something else**: rotational and analyst programmes (Carta, Notion), ops specialists
  > (Coinbase, Wells Fargo, DEPT OF YOUTH & COMM D), non-software engineering (Shield AI
  > mechanical, NewYork-Presbyterian laboratory and building), recruiting (Finix), and data
  > annotation (Cohere). **Five of the 17 carry no `job_facts` row at all**, so for those
  > the gap is not the vocabulary — nothing was ever extracted. The commercial finding is
  > corroborated at *corpus* scale instead; see the next entry.

- **A vocabulary proposal: ONE new archetype, `revenue_commercial`. PROPOSED 2026-07-31 and
  deliberately NOT APPLIED.** Instrument: `python3 backend/tools/derive-role-tracks.py
  --archetypes`, population `facts_version = 3` (the header of every run now prints it —
  `'other' population: facts_version 3, 294 rows`; see § *findings later tasks must not
  inherit* for why that line exists).

  **Where the `other` mass actually is.** 294 of the 940 `facts_version = 3` rows are
  `role_archetype = other` — **31.3%**. Of those 294:

  - **182 (62%) also carry `role_track` NULL.** *Neither* vocabulary has a word for them, so
    a new archetype does not reach them and the gap there is extraction or coverage, not
    naming.
  - **112 (38%) DO get a coherent track** — 36 `business_operations`, **35
    `revenue_operations`**, 18 `product_and_marketing`, 11 `business_analysis`, and 12
    across four others. **These are the rows the proposal is about**: the coarse vocabulary
    has a word and the fine one does not.
  - **57 of the 294 are ONE employer** — Sailor Health, a telehealth clinical-psychologist
    role posted once per US state — which is **19.4% of the bucket** and is a hiring spree,
    not a role family. The raw 31.3% does not dedup it.

  **The comparison figure, with both populations attached, because it is routinely quoted
  without them:** `other` is **8.0%** at `facts_version = 2` (402 of 5,024 — the author's
  tech corpus under the TWELVE-value vocabulary) and **31.3%** at `facts_version = 3` (294
  of 940 — the pursuit-eligible corpus under twenty-six). **Those two rates differ by
  vocabulary AND by corpus, so "12 → 26 made `other` worse" conflates two changes** and
  cannot be read off this pair. Task 12's own 31.1% is the v3 figure and is the one that
  reproduces.

  **The candidate, measured** (`dedup` collapses one employer's repeated posting of one
  role; `emp` is distinct employers — read `emp` first):

  | candidate | cohort raw / dedup / emp | `other` raw / dedup / emp | verdict |
  |---|---|---|---|
  | **`revenue_commercial`** | 148 / **91** / **31** | 68 / **48** / **23** | **recommended** |
  | `finance_accounting` | 28 / 27 / 19 | 22 / 21 / 16 | dropped |
  | `strategy_bizops` | 31 / 25 / 19 | 26 / 22 / 17 | dropped |
  | `people_recruiting` | 13 / 12 / 10 | 8 / 7 / 7 | dropped |
  | `clinical_care` | 58 / **11** / **3** | 56 / **9** / **1** | dropped — *one employer* |

  `clinical_care` is the employer-spread rule doing its job: 56 raw `other` matches collapse
  to **9 dedup at 1 employer.** That is Sailor Health again, and a vocabulary value for it
  would name a hiring spree.

  **Union reclaim, distinct rows, not a column sum** (the patterns overlap and
  `role_archetype` is single-valued): `revenue_commercial` alone reclaims **68 of 294 =
  23.1%** of the v3 `other` bucket. **The fourteen values task 11 actually adopted reclaim
  47 between them** — ops 38 (12.9%) plus tech 9 (3.1%). **One value reclaims more than
  fourteen.**

  **The structural argument matters more than the count.** `ROLE_TRACK` already has
  `revenue_operations` — 35 of the 294 `other` rows are on it — while `ARCHETYPE` has no
  commercial value at all; its own first line is the admission, *"The original twelve. All
  software engineering."* (`extract.ARCHETYPE`, the comment immediately above the tuple). So
  a Deal Desk Analyst gets a coherent track and **can only be `other` at the finer grain.**
  Two vocabularies meant to be one space at two grains, and on commercial work they are not
  one space.

  **Why one value and not five.** The 12 → 26 expansion is the move that has already been
  tried and did not shrink `other`. Adding five at once repeats it, and the dropped four are
  kept above *with their evidence* precisely so that the next person does not re-derive them
  from scratch — the evidence AGAINST a value is the part a later reader cannot reconstruct.

  **Why it is NOT applied, and the objection is not cost.** Both constants are interpolated
  into `_INSTRUCTIONS`, the cache-keyed fixed prefix, whose own comment asks for exactly
  this: *"any change here invalidates the cache for the whole corpus and should come with a
  `schema.FACTS_VERSION` bump if it changes the meaning of an answer"* (`extract.py`,
  immediately above `_INSTRUCTIONS`). So adding a value is a `FACTS_VERSION` bump. **Task 12
  priced that bump: 863 calls, 28m31s, ~$0.33 — cost is not the objection.** The objection
  is that **`pursuit-v1` is being labelled right now.** Re-extraction changes the model
  answers the human labels exist to be compared against, mid-collection, on a set that can
  no longer be redrawn. It also needs a weight in **both** `config/criteria.json` and
  `config/pursuit-criteria.json` (`tests/test_match.py:484-485` asserts *"archetypes must
  price `extract.ARCHETYPE` exactly"*) and a count update at `tests/test_extract.py:720-721`,
  which pins `len(extract.ARCHETYPE) == 26`.

  **Follow the precedent already stated in the repo:** `config/extraction-policy.json`'s
  `_not_a_version_note` — *"task 12 owns the next bump and carries this change with it, so
  that one re-extraction pays for both."* **Land the vocabulary and the rationale, do not
  bump, and note that the next bump carries this too.**

- **There is no loader from `eval_labels` into anything that can re-tune the weights, and
  no task owns building one.** Added 2026-07-30. `backend/tools/calibrate-match.py` is what
  this file has been naming as the instrument, and **its ground truth is `job_scores` —
  the LLM** (its own *"THE LABELS ARE FREE"* section, `:44`). Sweeping the weights with it
  after the labelling night would fit them to the model the labels exist to check. What is
  missing is small but real: labels are rows keyed
  `(job_id, field, labeller_id, round_no)` with an axis, and a sweep wants a per-`job_id`
  target for a profile — so somebody has to decide **what an axis-B `would_apply`
  consensus means as a regression target**, including what to do with the ties
  `labels.consensus()` deliberately refuses to break. That decision is not an
  implementation detail and it is not made anywhere.
- **`role_track` is NULL on 261 of 917 `job_facts` rows at `facts_version = 3` (28.5%)**,
  and 82 of the 200 rows in `pursuit-v1` — including **all 50** `gate_rejected`. Measured
  2026-07-30 after the 04:09 nightly; the pre-run figures were 244/881 and 83/200. It is
  now a question on the labelling form so the night can say *which* fix
  it needs (extraction vs vocabulary), but **nothing is scheduled to act on either
  answer**, and the vocabulary conditions every per-track figure task 30 produces.
  `docs/role-track-derivation.md`, § *The validation this document asked for*.
- **26 of the 50 `gate_rejected` rows in `pursuit-v1` have no `job_facts` row at all**
  (24 carry facts; re-verified 2026-07-30 after the nightly and unchanged by it), so
  no axis-A field can be scored on them by any instrument. Added 2026-07-30. Not a defect —
  the stratum is defined by rejection and `pool_query()` LEFT JOINs on purpose — but it
  **bounds what the night can produce** and should be stated wherever a `gate_rejected`
  figure is quoted. That stratum yields a recall bound (k of 50, Wilson), never a
  precision rate, which the pinned fixture confirms independently: it carries `match_score`
  on 100/100 surfaced and `computed_score` on 50/50 below_floor and **neither column on any
  of the 50 gate_rejected**.
- ~~**`backend/evals/record_cassettes.py` owes a `workday-cxs` recipe**~~ — **IT DOES NOT,
  AND HAS NOT SINCE 2026-07-28. This entry was stale for three days and nobody checked.**
  `record_workday_cxs()` is at `record_cassettes.py:501`, `WORKDAY_CXS = ("msk", "wd108",
  "MSKCC_Careers_Primary")` at `:498`, and the recording is committed at
  `backend/evals/fixtures/cassettes/workday-cxs.json` with seven tests on it in
  `backend/tests/test_workday_cxs_cassette.py`. **This is the failure mode this file warns
  about, committed by this file**: a follow-up that decayed into a quotation because
  re-checking it needed one `ls`. *(The identical claim in `docs/ingest/workday.md` was
  struck in the same session.)*

  **And the re-check paid for itself**, which is the argument for doing it: the recipe
  delivered *half* of what this entry promised. The board was at **79 postings when
  recorded, not 88** — four pages, not ~5 — answering `total` 79, 0, 0, 0, so
  **`total`-on-the-first-page-only is now recorded rather than constructed**, guarded by a
  refusal-to-record in `record_workday_cxs()` if the tenant ever stops behaving that way.
  **The wrap — offsets past the end returning page one — is still constructed and
  deliberately so**, because provoking it means issuing a request past the end of a
  stranger's board that `collect_postings` never issues (the `fresh == 0` guard at
  `ingest/workday.py:490`). So `total_only_on_first_page()` is no longer the only evidence
  for failure 5, but it is still the only evidence for the wrap.
- ~~**Task 09's `workday_fixtures.prefix_assumed()` models the wrong failure shape.**~~
  **FIXED 2026-07-31, and the status code was the smaller of the two errors.** It modelled
  a wrong data centre as HTTP 404 with an HTML body; the recorded `nvidia.wd1` probe in
  `ats-validation.json` answers **422 with a JSON `errorCode` body**. It now encodes the
  recorded shape, transcribed into `WRONG_DC_STATUS`/`_REASON`/`_CONTENT_TYPE`/`_BODY` so
  the fixture still builds with no cassette on disk, with
  `TestTheRecordedRefusalIsWhatTheFixtureEncodes` diffing each constant against the bytes
  so drift fails loudly. The suite grew by seven; the before/after pair is in
  [`CLAUDE_UPDATES.md`](CLAUDE_UPDATES.md)'s 2026-07-31 entry and the current count is
  [`AUDIT.md`](AUDIT.md)'s, which per rule 3 is a command rather than a number.

  **The mechanism was wrong too, and that is the reusable part.** The old docstring argued
  the loss went through a `JSONDecodeError` on the HTML — *"which every ingest script in
  this repo catches"*. **No decode ever happens.** `lib/http.py:76-77` (*"raise # permanent
  -- surface immediately"*) re-raises before `ingest/workday.py:371`'s
  `json.loads(http.get_text(` is reached — `json.loads` sits *outside* `get_text`, so it is
  reached only if `get_text` returns, which it never does on a ≥400 whatever the body is.
  **The sharpest form of it: the stated mechanism could not have occurred under the
  fixture's OWN 404/HTML bytes either**, because the replayer raises at
  `evals/cassettes.py:448` before the body is touched. So this was never a fixture that
  drifted from reality — it described a route that had never existed, and it passed its
  tests for a year because the tests asserted the conclusion. **A fixture is a claim about
  a mechanism, not only about a status code, and a green test on the conclusion does not
  check the claim.** **No 404 case was
  kept**: no Workday host in any cassette here has answered 404, and 404 and 422 take a
  byte-identical path (permanent at `lib/http.py:76`, both absent from `BLOCKED_STATUSES`
  at `ingest/workday.py:237`) to the same `Shortfall` — so a second interaction would
  encode an unobserved status to buy no coverage.
- **NEW 2026-07-31, small and unowned: `record_workday_cxs()`'s own docstring is now stale
  against the cassette it recorded.** `record_cassettes.py:510` says *"msk is 88 postings:
  five pages, the last one short"* and the note built at `:546` says *"five pages ending in
  a short one"*; the committed recording holds **four** pages over a **79**-posting board
  (`total` 79, 0, 0, 0 — verified by reading the JSON). The board moved between task 16's
  validation and the 2026-07-28 recording, which is ordinary and is why nothing reconciles
  against a stored count. **Left unfixed on purpose:** it is a two-string edit but it is a
  judgement about whether to restate the docstring or re-record against today's board, and
  nobody owned that file this session. Do not "fix" it by re-recording without reading
  `record_workday_cxs()`'s refusal guard first — the guard is what protects failure 5's
  evidence.
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

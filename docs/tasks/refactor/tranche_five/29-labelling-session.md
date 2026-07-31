# 29 — Two-axis labelling session

**Status:** todo. **Depends on:** 07, 12, 26. **Blocks:** 30. ~~30, 31.~~
**Corrected 2026-07-30: this task does not block 31.**
`tranche_six/31-dismiss-demotion.md:3` reads *"**Depends on:** 27, 26. **Blocks:**
nothing"* — it does not name 29 — and **31's body never mentions labels at all**
(checked by grep for "label" over the whole file: zero hits). 31 turns a dismissal into
a persistent signal from `job_events`; it needs the event schema (27) and profile
creation (26), not human judgements. **30 is the only task file genuinely behind 29.**

> **Correction, 2026-07-29.** This file was written from the plan. Task 07 has since
> been built (`3a8b42c`) and the sample drawn, and five of its statements do not
> survive contact with the code. Read this block before "The sample" or "Logistics".
>
> **1. There are three strata, not five.** `backend/evals/labels.py:425` defines
> `STRATA = ("surfaced", "below_floor", "gate_rejected")`, with
> `DEFAULT_STRATA_QUOTA = {"surfaced": 0.5, "below_floor": 0.25, "gate_rejected": 0.25}`
> (`labels.py:433`). Four of the five buckets in the table below are not addressable as
> strata: top-20, ranks 20–50 and the tie block are all sub-slices of `surfaced`, which
> is one stratum with one quota. The DoD's *"all five strata represented"* is not
> satisfiable as written. Read it as **all three strata represented** — which the drawn
> set meets.
>
> **2. The `fit_score` tie block is empty by construction.** It needs `job_scores`, and
> `pool_query()` (`labels.py:440`) never joins that table — it reads `jobs`, `job_facts`
> and `job_matches` only (`labels.py:488-490`). Separately, `pursuit` has **0 rows in `job_scores`** at all,
> its `daily_narrative_budget` being 0. There is nothing to sample even if the query were
> widened. Dropping the bucket costs zero postings.
>
> **3. "ranks ~20–50, n=60" asks 60 postings out of ~31 rank slots.** `pursuit` holds 144
> rows in `job_matches` (measured 2026-07-29). The band cannot supply the count.
>
> **4. "tier-2/3, gate-rejected" is wrong: tier 2 is ADMITTED.** Both
> `backend/config/relevance.json:113` and `backend/config/pursuit-relevance.json:179` set
> `"max_tier_to_score": 2`, and `classify()` (`labels.py:542`) returns `gate_rejected`
> only for `tier > max_tier` (`labels.py:544-545`). **Only tier 3 is gate-rejected.**
>
> **5. The labeller arithmetic was impossible; it is now resolved.** "10 volunteers × 20
> postings = 200" and "overlap 20 postings across everyone" cannot both hold. Distinct
> coverage is `overlap + n_labellers × (budget − overlap)`, so a 20-row overlap block
> against a 20-posting sitting yields **20** distinct postings — not 200, and not the
> DoD's ≥100. **Decision, 2026-07-29, repo owner: overlap 10, budget ~20.** Ten labellers
> then reach 110 distinct in the twenty minutes this task specifies, and a 10-row block
> still gives 45 annotator pairs per field. **This changes one DoD line: "20 postings
> overlapped" becomes 10.** For the DoD's own five-labeller fallback: five labellers at
> 20 items reach 60 distinct, not 100 — reaching ≥100 at five labellers needs ~28 items
> each.
>
> **6. "Build that, not a CLI" is stale — it is built.** GET/POST `/v1/label` and
> `/v1/label/progress` exist ~~at `backend/webapp/label.py:218`, `:256` and `:311`~~, wired at
> `backend/webapp/app.py:91`. Server-rendered HTML, no JS, behind the existing Google SSO
> plus an `app_users` allowlist.
>
> > **Citations re-checked 2026-07-30 — all three had moved, and this is the third
> > generation of them.** The round-2 path pushed the routes down. Re-verified with
> > `grep -n` against the working tree today, quoting the text because the digits have a
> > shelf life in this file:
> >
> > | route | line | the text at it |
> > |---|---:|---|
> > | GET form | **`:266`** | `@router.get("/v1/label", response_class=HTMLResponse)` |
> > | POST submit | **`:354`** | `@router.post("/v1/label")` |
> > | progress | **`:466`** | `@router.get("/v1/label/progress")` |
> >
> > The decorated functions are `label_form()` (`:267`), `submit_label()` (`:355`) and
> > `label_progress()` (`:467`). **`app.py:91` was re-checked and has not moved.**
> > `:218`/`:256`/`:311` were correct when written; `HANDOFF.md` then recorded them as
> > `:241`/`:296`/`:364`, which were correct for about a day. **Three sets of numbers for
> > one unchanged set of routes** — the durable pointer is the route decorator, and
> > `grep -n '@router' backend/webapp/label.py` is the instrument.
>
> **7. "Blind to `fit_score`" is SATISFIED, not pending.** `backend/webapp/label.py`
> contains no reference to `fit_score` or `match_score` anywhere.
>
> **8. The sample is drawn and pinned.** Label set `pursuit-v1`, n=200, seed 0, overlap
> 10, profile `pursuit`, drawn 2026-07-29 against the cohort gate over the full pool
> window. Strata: surfaced 100 / below_floor 50 / gate_rejected 50, spread over nine
> platforms with no platform above 54. Pinned by `sha256(sorted job_id)` =
> `afb2d58f5d369dfd03ad9237a8b16396cea31b838a67343f51aceecf70cd1763`, committed at
> `backend/evals/fixtures/labelset-pursuit-v1.jsonl`, registered in `eval_label_sets` and
> `eval_label_items`. `eval_labels` is empty. **Never train on it.**
>
> **9. What remains is two things, neither of them code.** Google OAuth credentials —
> `GOOGLE_CLIENT_ID` and `GOOGLE_CLIENT_SECRET` are empty strings in
> `backend/webapp/.env`, and `FRONTEND_ORIGIN` needs pointing at the serving origin — and
> ten Builders with a `manage_app_users.py add` row each. Nothing is left to install:
> `backend/webapp/.venv` already carries fastapi 0.140.0 and the webapp suite passes
> ~~55/55~~ ~~**61, OK**~~ **75, OK** under it.
>
> > **Re-measured 2026-07-30**, `.venv/bin/python -m unittest discover -s tests -t .` from
> > `backend/webapp/`: **`Ran 75 tests`, `OK`**. 55 was correct when written on 2026-07-29;
> > the round-2 path and `role_track` on the form added the difference. **The suite grew
> > and nothing broke** — the safe direction.
> >
> > **`61` was written on this line earlier the same day and was stale before it was
> > saved**: `manage_app_users.py set-profile` landed 14 webapp tests from a parallel agent
> > while this correction was being written. That is the joke this sentence keeps making at
> > its own expense — **do not quote 75 either without re-running it.**

> **Added 2026-07-30: the first sitting is SOLO and does not meet this file's Definition
> of done.** That is a choice, it is recorded rather than tuned away, and the report at the
> end is **expected to refuse**. Read § *Deviation — the first sitting is SOLO* at the
> bottom of this file before running anything, and `LABELLING-NIGHT.md` § *Case A — solo,
> localhost* for the operations.

Collect the first human labels this system has ever had. Everything downstream of
`job_facts` is currently validated against an LLM's opinion of an LLM's output.

## The gap this closes

`docs/ingestion_tests/03` states it plainly: every existing tool substitutes a model
for a human — `claude-bench.py:417` treats sonnet-batch-1 as ground truth,
`calibrate-match.py:47` uses existing `job_scores`. That *"measures agreement, not
correctness, and is blind to any error two models share."*

And `tools/compare-extract.py` measures the model against **itself**, which catches
instability and is structurally blind to systematic error. A model can be perfectly
self-consistent and consistently wrong. Task 06 measured the self-consistency floor;
this task measures the thing above it.

## Two axes, and the split is the durable part

| axis | question | scope | survives a cohort ending? |
|---|---|---|---|
| **A** | Is the extraction correct? Does `seniority_level` match the posting? Is `ai_involvement` right? | objective | **yes — and survives a change of vertical** |
| **B** | Would you apply to this? | subjective | no |

**Axis A is the asset.** It validates `job_facts`, the tier computed once and shared
by every profile forever. It transfers to every future Builder, every future cohort,
and any future vertical. Collect it carefully and it never needs collecting again.

Axis B dies with the cohort. Collect it anyway — it is what task 30 is measured
against — but do not confuse its shelf life with Axis A's.

Label both on the same postings in the same sitting. The marginal cost of the second
axis is small once someone has read the posting.

## The sample

Drawn per task 07's design, stratified — **random sampling would spend labels where
the ranker never operates.**

| bucket | n | answers |
|---|---|---|
| top 20 by `match_score` | 50 | is the head correct |
| ranks ~20–50 | 60 | where does the cutoff belong |
| scored, below `MATCH_FLOOR` | 40 | false negatives from the floor |
| tier-2/3, gate-rejected | 30 | **false negatives from `relevance.py`** |
| the `fit_score` tie block | 20 | does the score have sub-band resolution |

That fourth bucket is the only way recall is estimable. Everything measured to date
was something the pipeline already chose to surface, so only precision has ever been
knowable. `labels.py` must accept rows with no `job_scores` entry at all (task 07).

Pin the sample by sorted `job_id` and never train on it.

## Logistics — you are a Builder, not staff

This shapes the design more than anything else.

There is no roster access and no instructor authority, so this is **asking ~10
classmates for twenty minutes**, not running a sanctioned exercise. Plan accordingly:

- **10 volunteers × 20 postings = 200 labels.** Five volunteers still gets 100, which
  beats zero. Design the analysis to work at either.
- **Overlap 20 postings across everyone.** That gives inter-annotator agreement — the
  ceiling measurement — for the cost of no extra postings. It is a better ceiling than
  one person labelling twice a week apart, and it is free.
- **Twenty minutes, in person, in one sitting.** Asynchronous labelling homework will
  not come back.
- **The interface must assume no terminal.** Task 07 specifies a web form behind the
  existing Google SSO. Build that, not a CLI.
- **Blind to `fit_score`.** Seeing the model's number first collapses a human's
  judgement onto it. This is the single easiest way to invalidate the whole exercise.

It doubles as a class activity with genuine content — evaluating whether a posting is a
realistic target is a skill this population needs, and doing it as a group surfaces
disagreements worth discussing. That is a legitimate reason to ask, not a
rationalisation.

## Analysis

Report three quantities per field, per task 07's design — model self-consistency (from
task 06), inter-annotator agreement, and model-vs-human. **Model-vs-human alone is
uninterpretable**; a model at 80% agreement with humans who agree with each other 78%
of the time is doing well, and the same 80% against humans agreeing 96% is not.

Break out by source platform. Task 06's reconciliation predicts extraction degrades on
messy sources, and Phase 3 just added several. A blended number would hide exactly
that effect.

## Gates

| finding | consequence |
|---|---|
| Axis A poor on `ai_involvement` | the cohort's targeting mechanism is unreliable. Return to task 11's mitigation — confidence field or majority-of-3 |
| Axis A poor on the new Phase 3 sources specifically | the extraction prompt needs source-aware handling before those sources are trusted |
| Axis B poor — `fit_score` does not track Builder preference | `persona.json`'s rubric is wrong. Fix it before task 30 does anything with the number |
| Gate-rejected bucket contains good roles | task 10's gate is too tight. Fix before anything else, because no ranking work recovers a posting that never entered |

## Definition of done

- ≥100 labelled postings across both axes, from ≥5 labellers.
- 20 postings overlapped across all labellers; inter-annotator agreement computed.
- All five strata represented, including gate-rejected rows.
- Labellers were blind to `fit_score`.
- Three quantities reported per field, broken out by source platform.
- The sample is pinned and marked never-train.
- The gate decision above is recorded, including which branch was taken.

## Deviation — the first sitting is SOLO, and it does not meet this DoD

**Recorded 2026-07-30, before the sitting rather than after it.**

The repo owner is going to label **alone, on localhost**, before any Builder is involved
(`LABELLING-NIGHT.md`, § *Case A — solo, localhost*). **That meets neither the first nor
the second line above, by choice.** This file's convention — and this repo's — is to
record a deviation rather than tune the DoD into being met; task 13's unmet DoD lines got
exactly that treatment, and `HANDOFF.md` § *the ranking is a product now, and the DoD it
did not meet* is the model this block is written against. **The rest gets collected once
Builders are using the app.** Nothing here is a change to the DoD; the lines stand as
written and are simply not all reachable yet.

Line by line, and the split is not where it looks:

| DoD line | a solo sitting | why |
|---|---|---|
| ≥100 postings, **from ≥5 labellers** | **NO** | the posting count is reachable in one long sitting; *"≥5 labellers"* is not reachable by one person at any effort |
| 20 overlapped, **inter-annotator agreement computed** | **NO** | already amended to 10 by correction 5 above. The agreement figure is **structurally uncomputable** — see below |
| all strata represented | **yes** | read as **three** strata per correction 1. The queue serves the overlap block first, stratified 5 `surfaced` / 3 `below_floor` / 2 `gate_rejected`, so all three are touched in the first ten answers |
| labellers blind to `fit_score` | **yes** | met structurally and independently of turnout — `backend/webapp/label.py` references neither `fit_score` nor `match_score` anywhere (correction 7) |
| three quantities per field, per platform | **NO** | the report refuses. See below |
| sample pinned, never-train | **already met** | `pursuit-v1`, `sha256(sorted job_id)` = `afb2d58f…0cd1763` |
| the gate decision recorded | **partial** | the `gate_rejected` rows can be *read* by one person and a branch *drafted*; it cannot be **settled**, because with no ceiling there is no scale to read a disagreement rate against |

**The report is EXPECTED to refuse, and that is not a defect to work around.**
`evals label report` exits 2 with `evals label report REFUSED:` for as long as there is one
labeller. The ceiling column is bound to `labels.inter_annotator()`, which requires **two
distinct `labeller_id`s on the same item** and skips every item where it does not find
them; `labels.interpretable()` then refuses per field, and `Interpretable` is the only
thing `report.render_labels()` accepts. **There is deliberately no `--force`** — the
mechanism and its current line numbers are in `LABELLING-NIGHT.md` § *A5. What a solo run
can and cannot produce*, cited by symbol because those two files were being edited while
this was written.

**What unblocks it is one second person and ten minutes.** Not a second full sitting — the
ten `overlap` rows only. They never see the other 190 postings, the queue serves the
overlap block first to everyone by construction, and that single contribution turns every
refused field into a printable one. **It is the cheapest unblock in this task and it should
be arranged before a long solo sitting, not after**, so the labels collected have a scale
to be read against.

**The intra-annotator ceiling is the owner's own fallback, and it is the weaker one.** The
owner re-answers **those same ten overlap rows** at `/v1/label?round=2`, no sooner than
`labels.ROUND_TWO_DELAY_DAYS = 7` days after their round-1 answers. Same postings by
design, so the two ceilings differ for one reason rather than two. Too soon and the form
names the date to come back on rather than showing an empty page.

**And the thing that is deliberately NOT being done: `interpretable()` is not being changed
to accept the intra cell as `ceiling`.** It would make the report print, and that is
precisely the objection. Intra measures whether one person repeats themselves; inter
measures whether two people agree. **They are different quantities**, pinned as such by
`tests/test_labels.py`'s `test_the_two_ceilings_are_different_quantities`, and a report
that silently substituted the weaker one would denominate every model score in a number
that does not mean what the column header says. A model at 80% against an intra ceiling of
95% and against an inter ceiling of 79% calls for opposite decisions — *fix the prompt*
versus *stop working on this*. **Rendering the bad report unrepresentable rather than
discouraged is the whole design.** If attrition ever leaves intra as the only ceiling with
any n, that is a decision to take explicitly and write down, not one to acquire by
loosening a keyword argument.

---
kind: task
written: 2026-07-28
generator: none
---

# 29 — Two-axis labelling session

**Status:** ~~todo~~ **in progress** — the report printed 2026-08-02
([`docs/labelling-report-2026-08-02.md`](../../../labelling-report-2026-08-02.md)) and no
DoD line is met; see § *Findings, 2026-08-02*.
**Depends on:** 07, 12, 26. **Blocks:** 30. ~~30, 31.~~
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
| the gate decision recorded | ~~**partial**~~ **evidence collected, decision still open** | the `gate_rejected` rows can be *read* by one person and a branch *drafted*; it cannot be **settled**, because with no ceiling there is no scale to read a disagreement rate against. **Updated 2026-07-31: the evidence now exists — see § *Findings, 2026-07-31 (second sitting)*, B** |

> **Re-checked against 31 labelled postings, 2026-07-31 (second sitting).** The table above
> was written before the sitting; the rows below are what it looks like after it, and the
> original wording is left standing because **none of the NOs became yeses**. Instrument:
> `tools/label-findings.py`, 186 label rows / 31 postings / 1 labeller / round 1. Lettered
> references below are to § *Findings, 2026-07-31 (second sitting)* at the end of this file,
> **not** to the section of the same letters above it.
>
> | DoD line | before the sitting | after 31 postings |
> |---|---|---|
> | ≥100 postings, from ≥5 labellers | **NO** | still **NO** — **31 postings from 1 labeller**. The posting count is now demonstrably reachable (§ A: 100 is ~2.6 h, not the ~4.3 h this file last recorded); the labeller count is not reachable alone at any effort |
> | 10 overlapped, agreement computed | **NO** | still **NO** — **all ten `overlap` rows are answered**, by one person. Agreement remains *structurally* uncomputable: `labels.inter_annotator()` needs two distinct `labeller_id`s on the same item |
> | all strata represented | **yes** | still **yes**, and now with counts rather than by construction: **surfaced 19, gate_rejected 9, below_floor 3** |
> | blind to `fit_score` | **yes** | unchanged — met structurally, independently of turnout |
> | three quantities per field, per platform | **NO** | still **NO**, and the report still refuses. `tools/label-findings.py` does not change this and deliberately prints no model-vs-human number |
> | sample pinned, never-train | **already met** | unchanged, and now **irreversibly**: `eval_labels` holds rows, so `redraw_refusal()` refuses every redraw |
> | the gate decision recorded | **partial** | **evidence collected, decision still open** — three non-surfaced postings the labeller would apply to (§ B). That is evidence for the *"gate too tight"* branch of § *Gates*; it is not that branch taken |
>
> **Nothing in the DoD was tuned.** The first sitting's deviation stands as written; this is
> the same deviation measured.

**The report is EXPECTED to refuse, and that is not a defect to work around.**
`evals label report` exits 2 with `evals label report REFUSED:` for as long as there is one
labeller. *(Written while that was the state. A second labeller arrived 2026-08-02 and it
prints — the mechanism below is unchanged and is why it printed only then; see § Findings,
2026-08-02.)* The ceiling column is bound to `labels.inter_annotator()`, which requires **two
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

## Findings, 2026-07-31 — a hard case, a blind corpus, a ceiling caveat, and the first timing number

**Recorded from a design session dated 2026-07-30.** That session ran against a **shallow
clone**, so nothing it produced was treated as a measurement. Every figure below was
re-derived against the working tree and the live database on **2026-07-31** before being
written here; each one names the instrument that produced it. **Three of its claims
reproduced exactly, one did not, and one of its premises was wrong** — the corrections are
stated with the original claim beside them, per correction 5's convention above.

Nothing here changes the gate, the form, the drawn sample, the DoD, or any weight.

### A. A mid-level bridge role, admitted by accident

**The posting is real, and its title is not what the session called it.** It is
`Commercial Solutions Consultant, New York` — **not** "Solutions Consultant, Commercial" —
Notion, `ashby`, `location_is_nyc`, status `open`, job `8ba8616b7c91d2a1b5112cdc`. The
title is the string `title_include` and `title_exclude` are matched against, so the name is
load-bearing rather than cosmetic.

**A1 — the gate. Reproduces exactly, and the consequence is worse than the session
stated.** Instrument: `relevance.tier_sql()` compiled from the **live**
`profiles.relevance_json` for `pursuit` — verified byte-identical to
`config/pursuit-relevance.json` on every key, comments included — with each term tested
standalone using Postgres `~*` against the stored `description_text`.

| group | terms hit |
|---|---|
| AI, description | `ai tool`, `\yai\y` — 2 of 21 |
| entry-level, description | **`\yspecialist\y` alone** — 1 of 14 |
| `title_include`, **both groups** | **nothing** |
| `title_exclude` | nothing |

Tier **1**, and `max_tier_to_score` is 2, so it is admitted and extracted. The single
entry-level hit is *"troubleshoot in front of a customer without a specialist in the
room"* — a clause whose subject is a person the team does **not** have.

**What the session missed: the title path contributes nothing in either group.** The
description path is the only way in, so that one incidental word is the *only* thing
standing between this posting and tier 3. Rewrite the clause as *"without a solutions
engineer in the room"* and the posting is never extracted, for no change in the job.

Added to `pursuit-relevance.json`'s `_entry_level_note` as a known weakness, **documentation
only**. It is a different shape from the `\yassociate\y` / `\yanalyst\y` weaknesses already
listed there: those match a *senior title* and `title_exclude`'s seniority block is designed
to catch them — a precision leak with a backstop. This is a **recall** leak with no backstop
in either direction, because nothing can exclude on a word that is doing its job in a
subordinate clause.

> **The comment edit diverges the file from the database, and that is recorded rather than
> repaired.** `config/pursuit-relevance.json` and `profiles.relevance_json` were byte-identical
> on every key before this change; they now differ in exactly one, `_entry_level_note`.
> **Provably inert:** `relevance.load()` merges with `if not k.startswith("_")`, so no
> comment key can reach `tier_sql`. Verified 2026-07-31 — no `_` key survives the load, and
> the SQL emitted from the edited file is identical to the SQL emitted from the DB row. No
> re-import was run; a `migrate_profiles.py` pass would sync it and is not worth a write to
> the live profile row for a comment.

**A2 — the score. The session's premise was wrong: this is a measurement, not a
simulation.** The instruction was to label the range SIMULATED because *"the extractor has
not been run on this posting; the fact vectors are hand-written."* **It has been run.**
There is a real `job_facts` row (`facts_version` 3, extracted 2026-07-28,
`deepseek-v4-flash`, `extraction_passes` 1) and a real `job_matches` row:

```
seniority_level  mid             role_archetype   solutions
ai_involvement   uses_ai_tools   customer_facing  true
match_score      63   base +50  seniority:mid -25  archetype:solutions +10
                      ai:uses_ai_tools +20  flag:customer_facing +8
```

63 is above `MATCH_FLOOR` (**40**, `schema.py:228`, re-checked 2026-07-31 — note
`pursuit-criteria.json`'s `_scale` still cites `:206`, which has drifted). It sits at rank
**42 of 152** `pursuit` `job_matches` rows.

So the two flips are recorded as a **counterfactual on a measured row**, run through the
pure `score_job()` with every other field held at its extracted value:

| | `ai_involvement = uses_ai_tools` | `ai_involvement = none` |
|---|---:|---:|
| `seniority_level = junior` | 88 | **38 — below the floor; no row is written at all** |
| `seniority_level = mid` *(as extracted)* | **63** | 13 |

**The claimed range of "roughly 13 to 98" does not reproduce. It is 13 to 88.** 13 is
exact. Reaching 98 requires a **third** flip — `gap_friendly_language` false→true — which is
the single most self-consistent field the extractor has, at **100% [96.8–100]**
(`docs/ingestion_tests/README.md`). Quoting 98 as the range of two flips silently borrows a
flip from the one field that never flips.

**The `ai_involvement` flip is the one that matters here, and it is not hypothetical.** The
posting carries a genuine requirement — *"You're obsessed with AI, constantly building with
the newest tools"*, under **Skills You'll Need to Bring** — and, separately, the exact
company boilerplate, its *"A Note on AI"* block. The figure to read this against is not the
94.8% headline but the decomposition beside it: **8 of 115 records (7.0%, [3.6–13.1])
changed whether the job is in the AI opportunity space at all** across three runs of the
same prompt on the same text. `seniority_level` is **85.2% [77.6–90.6]**. Both are
cross-referenced from `docs/ingestion_tests/README.md` rather than restated here.

**And the instruction that would discount the boilerplate never fires on this posting.**
`pursuit-persona.json`'s `scoring_instructions` does say to name *"an AI mention that turns
out to be company boilerplate rather than part of the job"* — but that is the **narrative**
prompt, consumed by `score.py` for `fit_score`, and `pursuit` has
`daily_narrative_budget = 0` and **zero rows in `job_scores`**. `ai_involvement` is decided
by `extract.py`, whose prompt has no persona in it by design. The instruction that would
catch this boilerplate is attached to the stage that never runs on it.

**A3 — the hole, and a competing reading that is probably the better one.**

The session's claim: the hole is not the archetype, because `solutions` is priced 10 and
`_archetypes_bridge_comment` already describes this posting; the hole is that
`seniority_level` conflates *distance-to-role* with *distance-in-a-transferable-domain*.
`pursuit-criteria.json`'s `_years_experience_no_prior_domain_comment` already records that
punt and its reason — *"there is no scalar in this file that can represent 'these fifteen
years transfer'"* — and this posting is the case where the demanded experience **is** in
the transferable domain, so the punt has a measured cost: **25 points**, the `seniority:mid`
delta, which is the entire difference between rank 42 and the head of the list.

**`HANDOFF.md` § *the first finding arrived BEFORE the first label* says something
different about the archetype half, and this row supports the handoff, not the session.**
That finding records that no archetype or track expresses a commercial/sales role and that
such a role *"lands in `other`, or is **mislabelled `solutions` because the word
matches**."* This posting's title contains the literal word *Solutions*, and the extractor
returned `role_archetype: solutions` and `role_track: solutions_and_implementation`. **Both
readings are recorded and neither is asserted**; settling it needs the labels this task
exists to collect.

The two conflations are different and they compose: the handoff's is `ai_involvement`
failing to separate *"uses AI"* from *"sells AI"*; this one is `seniority_level` failing to
separate the two kinds of distance. **This posting is a candidate entry for the
commercial/sales side list** the handoff calls *"the only place the content can live"*, and
which feeds `backend/tools/derive-role-tracks.py`. It is **not** a second Builder agreeing —
it is a code-verified instance of the class, and the handoff's *"acting needs more than one
Builder saying so"* still binds.

**One consequence for this task specifically: the posting is not in `pursuit-v1` and can
never be added.** `eval_labels` now holds rows, so `redraw_refusal()` refuses every redraw
of the set, identical digest included. Whatever this posting is evidence of, it is not
evidence this labelling session will produce.

### B. `mock-postings-v3` cannot detect this class

Measured 2026-07-31 from `docs/tasks/refactor/mock/mock-postings-v3-answer-key.json`; the
key's own `postings_sha256` re-verified against `mock-postings-v3.json` and matching.
**Neither file was edited.**

- **29 good / 25 bad / 1 undecided** — reproduces exactly.
- **All 29 good entries are `seniority_level: junior`. Zero good entries at mid or above** —
  reproduces exactly.
- `failure_modes`: `clean_reject` 5, `seniority` 7, `branding_trap` 5,
  `not_a_real_employer` 5, `out_of_scope_location` 5, `technical_bar` 4 — reproduces
  exactly, and all 31 are attached to `bad` entries with **none on a `good` one**. Every
  mode is a rejection mode.

**Correction to the session's phrasing.** `good <=> junior` is **not** a perfect
correlation: it is not a biconditional. `good ⇒ junior` holds perfectly at 29/29, but the
converse fails — 10 `bad` entries and the 1 `undecided` are junior too. The claim the
consequence actually rests on is the one that holds: **no good entry sits at mid or above**,
so `seniority.tolerate.mid = -25` cannot be falsified against this corpus in either
direction.

**Addition the session did not find, and it is the same defect one field over.** All 29
good entries are also `ai_involvement: uses_ai_tools`. **The `ai_involvement` weights are
unfalsifiable against v3 for exactly the same structural reason** — and A2 shows that
`ai_involvement`, not seniority, is the flip that decides whether a posting is written at
all.

So the corpus is precision-shaped in two dimensions, not one, and the *"reachable mid,
transferable domain"* false-negative class is structurally invisible to any measurement run
on it. **v3 is sha256-pinned; this is a note toward a successor corpus and a candidate
sixth failure mode, not a change to v3.**

### C. An interpretation caveat on the Axis B ceiling, and one time-sensitive action

`AXIS_B_FIELD` is `would_apply` (`evals/labels.py`). § *Which axis carries the profile* in
`HANDOFF.md` already establishes that Axis B rows are stamped with the session's profile
and Axis A rows carry none. **What is not recorded anywhere: that profile is the COHORT,
identical for every Builder, and no labeller attribute exists at all.**

On a posting like A, a Builder with prior commercial experience and one without give
**opposite answers that are both correct**. `labels.inter_annotator()` reads that as
disagreement and depresses the Axis B ceiling — and since every model score is denominated
in that ceiling, the effect is to make the model **read as better than it is**. This is the
neighbour of, and not the same as, the handoff's `consensus()` n=1 caveat: that one is about
a majority of size one, this one is about two people who genuinely disagree for a reason
nothing records.

**Axis A is unaffected**, as this file already says — and it is enforced rather than
conventional: `eval_labels_axis_shape` CHECKs that axis A carries `profile IS NULL`.

**ACTION TAKEN, and its deadline is the first Builder sitting rather than the solo one.**
A nullable `prior_domain` column on `app_users`, closed vocabulary, settable via
`manage_app_users.py add --prior-domain` and `set-profile --prior-domain`, shown in `list`.
`eval_labels.labeller_id` is `app_users.id`, so the decomposition is a plain equijoin: **no
change to the pinned item set, the form's questions, `labels.inter_annotator()` or
`labels.interpretable()`**, all of which stay exactly as they are.

Vocabulary — **derived, not invented.** The first eight are the industry list in
`pursuit-persona.json`'s `background_summary`, verbatim and in its order: `healthcare`,
`education`, `retail`, `hospitality`, `logistics`, `administration`, `trades`, `military`.
Plus `other` — a real domain the list does not name, priced as no-information the way
`_archetypes_other_comment` prices the archetype of the same name — and `none`, a genuinely
early-career Builder, which `background_summary` requires by describing the cohort as
*"early-career **and** career-changing"*. **NULL means nobody asked, and that is a different
statement from `none`**; collapsing them would score an unasked labeller as one with no
background, the same conflation `_seniority_unknown_comment` refuses for seniority and
`labels.py` refuses for the abstention.

**Nothing reads the column.** It does not commit the project to per-Builder scoring, and it
is one `ALTER TABLE` to drop if that decision goes the other way.

### D. Direction: per-Builder scoring is a derivation function

Recorded as a decision in `DECISIONS.md` § *29 — per-Builder scoring is a derivation
function, not N criteria files*, which carries the verified plumbing, task 11's reasoning
and which half of it survives, the `extract.py` / `score.py` cost reconciliation, and seven
risks. **Nothing is built.** The short form: per-`(posting, Builder)` scoring in the form of
**one derivation function** from a `user_facts` record to criteria deltas composed over
`pursuit-criteria.json` as the population prior — **not** thirty hand-authored criteria
files.

### E. The stopwatch reading, which is the number this file has been guessing at

`HANDOFF.md` asks for it by name: *"THE DELIVERABLE THE NEXT SESSION SHOULD ACTUALLY BRING
BACK IS A STOPWATCH READING … every budget figure in this run was computed against a
**five**-question form; the form asks **six**."* **It is now derivable, because labelling
has started.**

State, measured 2026-07-31: `eval_labels` holds **30 rows — 5 postings × 6 questions, one
labeller, round 1**, `labelled_at` spanning `2026-07-31T02:56:05` to `03:06:19` UTC. Those
are UTC stamps from `lib.timeparse.utc_now_str()`; in New York it was the evening of
2026-07-30, and it is **one sitting**, not two.

Instrument: successive `min(labelled_at)` per `job_id`. Submit-to-submit intervals:
**87 s, 170 s, 247 s, 110 s**. **Median 170 s, mean 154 s**, total span 614 s.

**What that does to the numbers this file plans against:**

| claim, and where it appears | at 154 s/posting |
|---|---|
| *"Twenty minutes, in person, in one sitting"* → ~20 postings (§ *Logistics*) | **~8 postings** |
| *"one second person and ten minutes"*, the ten `overlap` rows (§ *Deviation*) | **~26 minutes** |
| ≥100 postings, one person (Definition of done) | **~4.3 hours** |

**The twenty-minute budget is out by roughly 2.5x**, in the direction that matters, on the
one number every Builder-session estimate in this run is built from.

**Caveats, stated with it rather than after it:** n = 4 intervals from 5 postings and one
labeller; submit-to-submit includes reading time; the first posting's own reading time is
not measured at all, so the true per-posting figure is *higher* than 154 s, not lower; and
the fastest interval is the first, which is the opposite of a warm-up curve and is worth
re-checking as the count grows. `HANDOFF.md` warns against inventing a correction factor for
the sixth question — **this is a measurement of the six-question form, not a factor applied
to a five-question one**, and it should be re-derived rather than re-quoted once there are
more rows.

> **SUPERSEDED 2026-07-31 (second sitting): the figure is ~16 minutes, not ~26.** Left
> standing because it was right for n=4 and the drift is the lesson — see § *Findings,
> 2026-07-31 (second sitting)*, A and E.
>
> **Correction to § *Deviation — the first sitting is SOLO*, 2026-07-31.** That section
> calls the second labeller's contribution *"one second person and ten minutes"*, and
> `HANDOFF.md` says it twice more. **At the measured rate the ten `overlap` rows are ~26
> minutes, and ~15 minutes even at the fastest interval observed.** Everything else in that
> paragraph stands: it is still the cheapest unblock in this task, the ten rows still turn
> every refused field into a printable one, and it should still be arranged **before** a
> long solo sitting. It is not a ten-minute favour, and asking for it as one will fail on
> contact.

**Deliberately NOT recorded here: model-vs-human agreement.** Labels exist, `job_facts`
exists for these rows, and the comparison is two SQL statements away. `evals label report`
exits 2 for as long as there is one labeller, by design — *"rendering the bad report
unrepresentable rather than discouraged is the whole design"* — and a number computed around
that refusal and written into a document is the refusal defeated, with the added defect that
a document has no exit code. The state above is the whole of what is recorded.

### Suites, re-run 2026-07-31

`backend/`: **`Ran 1166 tests`, `OK`** before this change. `backend/webapp/` under its own
`.venv`: **75 → 93, `OK`** (18 added: `prior_domain`'s vocabulary, the generated CHECK, the
CLI-vs-database agreement, and the join). Neither went down.

**Note for task 34:** `CLAUDE.md` still says *"It was at 263 tests"*. The measured figure is
**1166**. That is stale by roughly 900 and is a documentation defect, not a regression.

## Findings, 2026-07-31 (second sitting) — the timing number reverses, the recall branch gets its evidence, and the vocabulary gap is not the shape finding A recorded

**Recorded 2026-07-31, from the sitting itself rather than from a design session.** The
section above was written when `eval_labels` held **30 rows over 5 postings**; the same
labeller kept going the same night. **This is a second sitting continuing the first, not a
second sitting a day later** — the window is contiguous apart from one break, and the file
above records only its first ten minutes.

Every figure below was re-derived on **2026-07-31** against the live database by
**`backend/tools/label-findings.py`**, a read-only tool added this session — no LLM, no API
key, no write of any kind. Read its module docstring before quoting anything from it; it
exists because *"an instruction to re-derive that requires someone to write four lines of
SQL first is an instruction that decays into a quotation,"* and this file is one of the two
documents that decayed. **Run the tool; do not re-quote this section.**

State at the time of writing, from `tools/label-findings.py`:

| quantity | value |
|---|---|
| label rows | **186** |
| distinct postings | **31** |
| labellers | **1** (`u_090b0ad12e99`) |
| rounds | **1** only |
| by stratum | surfaced **19**, gate_rejected **9**, below_floor **3** |
| window | `2026-07-31T02:56:05` – `05:25:27` UTC |
| queue positions answered | **0–30, contiguous** — so the ten-row `overlap` block (positions 0–9) is **complete** |

**That last row is the operationally important one.** The overlap block is answered in
full, so a second labeller's ten rows produce the inter-annotator ceiling **immediately**,
with no further work from the owner. See E.

Nothing here changes the gate, the form, the drawn sample, the DoD, or any weight.

### A. The stopwatch reading, re-derived at n=29 — and it moves the OTHER way

**Instrument:** successive `MIN(labelled_at)` per `job_id`, in submit order —
`tools/label-findings.py --timing`. The same instrument the first sitting used, at 7.25x
the n.

Raw intervals, seconds, in order (n=30):

```
 87  170  247  110 5765   81  178   83  133   93
125   74  113  131  119  171  116   80   69  251
 43  101   38   78   50   67   91   76   73  149
```

**The 5,765 s interval is a break in the sitting, not a posting that took 96 minutes**, and
it is excluded at the tool's default `--break-secs 600`. Both figures are printed so the
exclusion can be argued with:

| | median | mean | n |
|---|---:|---:|---:|
| including breaks | 97 s | **299 s** | 30 |
| **excluding breaks** | **93 s** | **110 s** | 29 |

**This overturns the caveat that finding E of the section above attached to its own
number.** E ends: *"the fastest interval is the first, which is the opposite of a warm-up
curve and is the thing to re-check as the count grows."* Re-checked at n=29:

| | mean |
|---|---:|
| first quartile (7 intervals) | **137 s** |
| last quartile (7 intervals) | **83 s** |

**The labeller speeds up.** There is a warm-up curve, and E's four intervals — 87, 170,
247, 110, mean **153.5 s** — sit **entirely inside it**. E asked for exactly this re-check
and the re-check reversed its note. A rate taken from the first few postings overstates the
cost of the rest by roughly 65%.

**Budgets at the 93 s median**, all of them replacing figures computed at 154 s:

| claim, and where it appears | at 154 s (superseded) | **at 93 s** |
|---|---|---|
| the ten `overlap` rows, a second labeller (§ *Deviation*) | ~26 min | **~16 min** |
| *"Twenty minutes, in person, in one sitting"* (§ *Logistics*) | ~8 postings | **13 postings** |
| ~60 in the first sitting (`LABELLING-NIGHT.md` § *A6*) | — | **1.6 h** |
| ≥100 postings, one person (Definition of done) | ~4.3 h | **2.6 h** |
| all 200 | — | **5.2 h** |

**The caveat that survives both derivations:** submit-to-submit includes reading time, and
the first posting's own reading time is not in the figure at all — so the true per-posting
rate is *higher* than 93 s, not lower. This remains a measurement of the **six**-question
form, not a factor applied to a five-question one.

> **Correction to § *Findings, 2026-07-31*, finding E — 2026-07-31 (second sitting).** E's
> **154 s** was correct arithmetic on the four intervals it had, and it is left standing
> above rather than edited. **At n=29 the figure is 93 s and every budget derived from 154 s
> is out by ~1.65x in the optimistic direction.** The lesson is not that E was careless — it
> is that **a rate measured over the first four postings of a first sitting is a measurement
> of a warm-up curve**, and this file had no way to know that until the count grew. E's own
> instruction, *"it should be re-derived rather than re-quoted once there are more rows,"*
> is the thing that produced this correction. Both numbers, and the n each was taken at,
> stay visible.

**Five tests pin this** — `backend/tests/test_label_findings.py` — including the
break-exclusion threshold and the curve's refusal to invent a trend when the sitting is too
short to show one.

### B. The recall question is now LIVE, and it is the DoD's open branch

**Instrument:** `eval_labels.would_apply` × `eval_label_items.stratum`, with Wilson
intervals — `tools/label-findings.py --recall`. **This is a human answer against a PIPELINE
decision, not against the model.** It is a recall bound; it needs no ceiling and it is not
an agreement rate.

| stratum | yes | no | n | rate | 95% CI |
|---|---:|---:|---:|---:|---|
| surfaced | 6 | 13 | 19 | 32% | [0.15, 0.54] |
| below_floor | 1 | 2 | 3 | 33% | [0.06, 0.79] |
| gate_rejected | 2 | 7 | 9 | 22% | [0.06, 0.55] |

**Three postings the pipeline did not surface, that the labeller would apply to:**

| posting | stratum | what the pipeline knew |
|---|---|---|
| **Brex — AI Engineer, Ecosystem** | below_floor | `ai_involvement = builds_llm_features` |
| **Ramp — Software Engineer, Accounting** | gate_rejected | **no `job_facts` row at all** |
| **Twilio — Frontend Software Engineer** | gate_rejected | `ai_involvement = none` |

§ *Gates* above carries the branch *"Gate-rejected bucket contains good roles → task 10's
gate is too tight"*, and the DoD carries *"The gate decision above is recorded, including
which branch was taken."* **This is evidence for that branch. It is recorded as evidence,
not as a decision taken**, and § *Deviation*'s line moves from *partial* to **evidence
collected, decision still open** accordingly.

**Two caveats, stated beside it rather than after it:**

1. **The three intervals overlap almost completely.** [0.15, 0.54], [0.06, 0.79] and
   [0.06, 0.55] cannot tell the strata apart at these n. Nothing here says gate_rejected is
   *worse* than surfaced; what it says is that the gate-rejected bucket is **not empty of
   roles the owner would apply to**, which is the branch's own trigger condition.
2. **n=1 labeller, and that labeller is a software engineer by background.** Two of the
   three are plain software-engineering roles. That is precisely the confound the
   `prior_domain` column of finding C above exists to decompose — and it is
   **undecomposable at one labeller**, whatever the column holds.

### C. The vocabulary gap, measured — and it is not the shape finding A recorded

**Instrument:** the humans' own `role_track` / `role_archetype` answers —
`tools/label-findings.py --vocabulary`. **Population: 31 labelled postings of a stratified
200-row eval set.** Not the cohort corpus; any comparison across the two is a comparison of
different populations and has to say so.

| answer | count | rate | 95% CI |
|---|---:|---:|---|
| `role_track = no_track_fits` | **13 of 31** | 42% | [0.26, 0.59] |
| `role_archetype = other` | **17 of 31** | 55% | [0.38, 0.71] |

**But the bucket is not the shape the section above predicts.** Only **2 of the 13** are
commercial/sales roles — both of them Notion *Commercial Solutions Consultant*, the Japan
and San Francisco variants — and **the owner answered `would_apply = no` to both**.
Location is a plausible confound on that answer and it is not controlled for, so **this does
not refute finding A**: the NYC posting A is about (`8ba8616b7c91d2a1b5112cdc`) is not in
`pursuit-v1` and, per A3's last paragraph, can never be added.

The rest of the 13 is a different list entirely: rotational and analyst programmes, ops
specialists, non-software engineering (mechanical, laboratory, building), recruiting, and
data annotation.

**At corpus scale the commercial finding is corroborated, and that measurement lives in
`docs/role-track-derivation.md`** — referenced by name deliberately, because restating its
numbers here is how a figure acquires two homes and one of them goes stale. **The point that
belongs to *this* file: the labelled sample and the corpus disagree in emphasis. They are
different populations, and the 31-posting figure above is the one this file owns.**

**No vocabulary change is proposed here.** Whether a value gets added is decided in
`docs/role-track-derivation.md`, against the corpus, and not against 31 postings from one
labeller.

### D. What 31 postings did and did not meet

Covered line by line, against the original wording, in the blockquote appended to §
*Deviation — the first sitting is SOLO* above. The short form: **no NO became a yes.** The
posting count is reachable and now demonstrably cheap (A); the labeller count is not; the
report still refuses; and the only line that moved is the gate decision, from *partial* to
*evidence collected, decision still open* (B). **The DoD lines are unchanged.**

### E. What is now the cheapest unblock, sharpened to a number

**All ten `overlap` rows are answered.** Positions 0–9 of `pursuit-v1` are complete, so the
second labeller's contribution is exactly ten rows at ~93 s — **~16 minutes** — and the
ceiling, hence the entire three-quantity report, lands the moment they finish. Not a second
sitting, not a share of the 200, and no further work from the owner to prepare it.

The figures this supersedes, both left visible where they appear: **"ten minutes"**
(§ *Deviation*, and `LABELLING-NIGHT.md` § *A5*) was a guess made before anything was
measured; **"~26 minutes"** (finding E's correction block above) was measured at n=4 inside
the warm-up curve. **~16 minutes is the current figure and it is the one to ask with.**

Everything else in § *Deviation*'s paragraph stands unchanged: it is still the cheapest
unblock in this task, it still turns every refused field into a printable one, and it should
still be arranged **before** a long solo sitting rather than after.

**Still deliberately NOT recorded: model-vs-human agreement.** The tool that produced every
figure above prints none, by design and in its own docstring — *"a number computed here and
pasted into a document would have no exit code to protect the next reader."* Every quantity
in A–C is either the humans' own answers (a marginal rate) or a human answer against a
**pipeline** decision (a recall bound). **Neither is a per-item agreement rate and neither
needs a ceiling.** `evals label report` still exits 2, still has no `--force`, and this tool
is not a route around it.

### Suites, re-run 2026-07-31 (second sitting)

`backend/`, `python3 -m unittest discover -s tests -t .`: **`Ran 1171 tests`, `OK`** —
**1166 → 1171**, five added in `backend/tests/test_label_findings.py`. `backend/webapp/`
under its own `.venv`: **`Ran 93 tests`, `OK`**, untouched by this change. Neither went
down.

## Findings, 2026-08-02 (third sitting — and the report printed)

**A second labeller arrived and the task's central deliverable exists.** The three-quantity
measurement is
[`docs/labelling-report-2026-08-02.md`](../../../labelling-report-2026-08-02.md), which
**owns those figures** under `DOCS-POLICY.md` rule 2. It is cited here and not restated;
every input is committed and the report re-runs from three files with no database, no
network and no LLM call.

**State, `python3 tools/label-findings.py`:** 271 label rows / 36 postings / **2** labellers
/ round 1. `u_919ad2c305c2` answered 11 postings including all ten `overlap` rows, 2026-08-02
`00:52`–`01:09` UTC; the owner added five more postings the same night.

**The one thing this file should carry forward, because it corrects its own § E.** E called
the second labeller *"the cheapest unblock,"* and it was — but it unblocked a **report**, not
an **answer**. The inter-annotator ceiling completed the moment those ten rows landed, and it
came back **below the model's own floor on every one of the five fields**, on 6–10 items each.
A model number with an inverted band has nothing to be read between. **E was right about the
mechanism and wrong about what it would buy**, and the correction is not that E was careless:
a ceiling cannot be predicted before it is measured, which is the entire reason the report
refuses to invent one.

**Effect on the Definition of done:** none of the lines move. Distinct postings are 36
against ≥100; labellers are 2 against 5–10; the gate decision stays *evidence collected,
decision still open*. **The one line that could have moved — a printable report — is now
printable and still not decisive**, so the task stays **in progress** rather than closing on
a technicality.

**What C's vocabulary figures look like at n=36**, re-derived rather than re-quoted, and the
population caveat above is unchanged — this is the stratified eval set, a quarter of it
`gate_rejected` by construction, and not the cohort corpus:

| answer | at n=31 (C, above) | **at n=36** |
|---|---|---|
| `role_track = no_track_fits` | 13 of 31 · 42% [0.26, 0.59] | **15 of 36 · 42% [0.27, 0.58]** |
| `role_archetype = other` | 17 of 31 · 55% [0.38, 0.71] | **19 of 36 · 53% [0.37, 0.68]** |

**The rate did not move.** C's conclusion is unchanged and no vocabulary change is proposed
here either.

**Next, and only the third is a session's to do:** more labellers on the *same ten* overlap
rows (more postings add nothing to the ceiling — 25 of the 36 carry one labeller); round 2
after the form's 7-day delay, ~2026-08-09, for the intra-annotator ceiling; and an
`evals selfcheck` at n=120 covering `role_track`, which the committed n=120 file predates
(`DEC-75`).

---
kind: record
written: 2026-08-02
generator: none
---

# ARCHIVED — `HANDOFF.md`'s run narrative through 2026-08-01

> **Written 2026-07-28 through 2026-08-01; archived 2026-08-02, superseded by
> [task 47](../tasks/refactor/tranche_eight/47-split-the-entry-point.md).**
>
> **What it measured:** the dated session narrative of the `docs/tasks/refactor/` run — the
> superseded entry-point blocks kept under rule 4, the two-track table, the
> recommended-next-steps list that is now almost entirely struck, and the stubs left behind
> by four earlier archivals and two rule-5 promotions.
>
> **Why it was superseded:** task 47 split `HANDOFF.md` by lifecycle, after it regrew 397
> lines in thirty-six hours — four fifths of what task 44's archival had removed — with all
> six doc checks green throughout.

**Where the rest of it went.** The live entry point is
[`../tasks/refactor/HANDOFF.md`](../tasks/refactor/HANDOFF.md); what still binds is
[`../tasks/refactor/STANDING-GUIDANCE.md`](../tasks/refactor/STANDING-GUIDANCE.md); the
open questions are [`../tasks/refactor/OPEN-QUESTIONS.md`](../tasks/refactor/OPEN-QUESTIONS.md);
the 2026-08-02 session is
[`../tasks/refactor/sessions/2026-08-02-four-streams-and-the-five-decisions.md`](../tasks/refactor/sessions/2026-08-02-four-streams-and-the-five-decisions.md).

**Retained for the record, not for instruction.** Several blocks below were *already* struck
where they stood, which is the point: a reader who acted on the old text has to be able to
see what they had. The text is unchanged; `git log -p -- docs/tasks/refactor/HANDOFF.md`
reaches it at that path.

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
> | its file did not exist | **it existed**, tracked since `28f1d0e`. [`34-documentation-cleanup.md`](../tasks/refactor/34-documentation-cleanup.md)`:14` strikes this exact sentence as *"WRONG, AND CORRECTED"* |
>
> **This block is rule 4's specimen.** A `rolling` document with no retirement
> trigger went on sending every fresh session to a finished task, repeating as its
> justification a premise the linked file had itself retracted, and nothing was red
> for a day. `backend/tools/audit-docs.py` check C3 exists because of it, and it is the
> worked example in [`../../DOCS-POLICY.md`](../DOCS-POLICY.md) rule 4 — *"the document
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
| **43** the `docs/scoring.md` split (DEC-70) | **done** — the measured half is [`docs/scoring-measured-2026-07-27.md`](../scoring-measured-2026-07-27.md) |
| **44** archive `HANDOFF.md`'s frozen half | **done** — this file is `rolling` throughout now, and C4 enforces on it |
| **41c/41d** the three branch decisions | open — the owner's, not a session's |

**For the state of the run in one page with an instrument beside every number, read
[`AUDIT.md`](../tasks/refactor/AUDIT.md)** — which now *owns* the run-level figures rather than
restating them, per `DOCS-POLICY.md` rule 2. For what phase 9 is doing and why, read
[`../../DOCS-POLICY.md`](../DOCS-POLICY.md); for how to work on any of it, read
[`../../WORKING-METHOD.md`](../WORKING-METHOD.md). ~~For this task's backlog, read
[`34-documentation-cleanup.md`](../tasks/refactor/34-documentation-cleanup.md).~~ **That file is now
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

**[`LABELLING-NIGHT.md`](../tasks/refactor/LABELLING-NIGHT.md) is task 29's operational annex, not a second
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
| per-posting rate | 154 s, n=4 | **93 s median, n=29** ([`AUDIT.md`](../tasks/refactor/AUDIT.md) owns the rate) — and the n=4 sample sat entirely inside a warm-up curve |
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
the median is 93 s** ([`AUDIT.md`](../tasks/refactor/AUDIT.md)): twenty minutes is **13 postings**, the ten `overlap` rows are
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
[`AUDIT.md`](../tasks/refactor/AUDIT.md)'s). Before that: **task 29 was unblocked: four
defects fixed in the sampler, the label tables created, and the 200-row set drawn, redrawn
and pinned** (`c65d34b`, `2f64e08`, `90170d1`). Before that: **step 0, the gate fix**, implemented and
written to the database (mock gate recall 48.3% → 89.7%, live tier ≤2 869 → 880); the
planning session that measured it; the **mock acceptance run and the `strip_html` fix**;
**`job_scores`' version keys** (`d18ea54`); and **13, 35 and D45** (`fa2d7a7`, `303f7b9`,
`e11fabf`). Read this first, then [`DECISIONS.md`](../tasks/refactor/DECISIONS.md) (why each choice was
made) and [`CLAUDE_UPDATES.md`](../tasks/refactor/CLAUDE_UPDATES.md) (what happened, per task).

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

## State at handoff — ARCHIVED

> **MOVED 2026-08-01 → [`docs/archive/handoff-state-2026-07-31.md`](handoff-state-2026-07-31.md).** The run's state as
> of 2026-07-31: the dated suite readings, the drift table that is the evidence for
> `DOCS-POLICY.md` rule 3, and the commit table that `tranche_two/12`, `tranche_two/13` and
> `tranche_three/19` cite. **[`AUDIT.md`](../tasks/refactor/AUDIT.md) owns both current suite counts and, per
> rule 3, states neither — it names the command that prints them.**

## What 08, 12 and 19 changed about the plan — ARCHIVED

> **MOVED 2026-08-01 → [`docs/archive/handoff-state-2026-07-31.md`](handoff-state-2026-07-31.md).** The findings those
> three tasks landed on 2026-07-28: which number the product should display, the archetype
> vocabulary making `other` worse rather than better, and task 19 dropped on the evidence.

## The two decisions the repo owner made in conversation — LANDED

> **MOVED 2026-07-31 → [`docs/archive/handoff-owner-decisions.md`](handoff-owner-decisions.md).** Recorded 2026-07-28, landed in `943d899`. Selective majority-of-3 extraction and the 40/day ceiling. Both shipped; the rationale is in DECISIONS.md under EXTRACT.

## Nothing is in flight — ARCHIVED

> **MOVED 2026-08-01 → [`docs/archive/handoff-tree-state.md`](handoff-tree-state.md).** What was committed and
> what was only a database write, recorded 2026-07-29 through 2026-07-31, with the content
> digests that proved nothing else moved. **Its FAQ is the section immediately below and
> stayed here**; its four cross-stream lessons were promoted to
> [`docs/MEASUREMENT-TRAPS.md`](../MEASUREMENT-TRAPS.md) under rule 5.


## Cross-stream lessons — PROMOTED

> **Promoted 2026-08-01 to [`docs/MEASUREMENT-TRAPS.md`](../MEASUREMENT-TRAPS.md)** §
> *Later additions*, which is the copy to read and to cite. Four paragraphs of method sat
> here, deep inside a rolling handoff about a labelling session: three agents on strictly
> disjoint *files* still interacted because the database is shared; the other agent in the
> room is the cron job; a pin on set membership buys nothing about the derived facts; take a
> content digest, because a row count cannot see an overwrite.
>
> **None of it is about Pursuit, Builders, job postings, one persona or one model**, which is
> [`DOCS-POLICY.md`](../DOCS-POLICY.md) rule 5's test, and § *How this run works* below is
> the precedent — same move, same reason. The text is unchanged;
> `git log -p -- docs/tasks/refactor/HANDOFF.md` reaches it at this path.

## How this run works — PROMOTED

> **Promoted 2026-08-01 to [`docs/WORKING-METHOD.md`](../WORKING-METHOD.md), which is
> the copy to read and to cite.** Roughly a hundred lines of method sat here, about 1,500
> lines into a rolling handoff about a labelling session: verify the plan against the code before
> implementing it, verify the plan's *arithmetic* against the artifact, a green suite does
> not mean the brief was met, a finished artifact is where the defects the checks cannot
> see live, a measurement's denominator needs an adversarial reader, and verify rather than
> trust the report.
>
> **None of it is about Pursuit, Builders, job postings, one persona or one model**, which
> is [`DOCS-POLICY.md`](../DOCS-POLICY.md) rule 5's test, and
> [`docs/MEASUREMENT-TRAPS.md`](../MEASUREMENT-TRAPS.md) is the precedent — same move,
> same reason. The text is unchanged; `git log -p -- docs/tasks/refactor/HANDOFF.md`
> reaches it at this path.
>
> **What it says about *this* run stays in this file** and is not repeated there: the two
> tracks above, what is blocked below, and the findings later tasks must not inherit.


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
   [`docs/archive/handoff-gate-fix.md`](handoff-gate-fix.md), which owns it,
   and [`AUDIT.md`](../tasks/refactor/AUDIT.md) owns the current count. See § *the gate fix LANDED*.

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

> **MOVED 2026-07-31 → [`docs/archive/handoff-session-measurements.md`](handoff-session-measurements.md).** Session narrative through 2026-07-31. Retained for the figures and their instruments; the live numbers are in HANDOFF.md § State at handoff and AUDIT.md.

## How these sessions ran it, and what worked

> **MOVED 2026-07-31 → [`docs/archive/handoff-session-method.md`](handoff-session-method.md).** Method notes from the same sessions. The durable half was promoted to HANDOFF.md § How this run works, and **promoted again 2026-08-01 to [`docs/WORKING-METHOD.md`](../WORKING-METHOD.md)**, which is now the copy to read.

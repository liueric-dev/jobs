# Handoff — the `docs/tasks/refactor/` run

## START HERE — a fresh session's sixty seconds, 2026-07-31

*This file had eight "READ THIS FIRST" sections and now has three — the four that
described finished work were archived on 2026-07-31 (task 34, § Orientation), and this
block is the entry point. Everything below is context. Verify anything here before acting
on it — the instrument is named in each case.*

**State, verified 2026-07-31 by `python3 backend/tools/label-findings.py`:**

| | |
|---|---|
| labels | **186 rows over 31 of `pursuit-v1`'s 200 postings** |
| labellers | **ONE** (`u_090b0ad12e99`), round 1 only |
| `overlap` block | **all ten answered** — positions 0–30 contiguous |
| `evals label report` | **exits 2, correctly.** Zero of task 29's three quantities exist |
| suites | main **1178**, webapp **93** (main was 1171 until the `prefix_assumed()` fix, 2026-07-31) |

### THE NEXT SESSION IS CLEANUP, BUGFIXES AND DOCUMENTATION — decided 2026-07-31

**It is not the labelling session, and it is not the product/API phase.** Phases 1–3 are
built and measured: 20 of 35 tasks are done or deliberately dropped. Before tasks 24–28 /
31 / 32 open a new surface, the run pays down what it has accumulated. **Task 34 is the
next session's task**, and its file did not exist until this decision — `README.md` linked
to `34-documentation-cleanup.md` and nothing was there. That broken link is itself a
specimen of the debt the session is for.

**For the state of the run in one page with an instrument beside every number, read
[`AUDIT.md`](AUDIT.md).** For this task's backlog, read
**[`34-documentation-cleanup.md`](34-documentation-cleanup.md).** It carries the
verified backlog, in priority order, with the evidence for each item. **Everything in it
was re-checked against the code on 2026-07-31** rather than inherited from a document —
because the single clearest lesson of the previous session is that this run's follow-ups go
stale silently: one had been marked *"still owed"* in two files for three days after it
landed, and re-checking it turned up a number nobody had (79 postings, not 88).

**TWO TRACKS, AND ONLY ONE OF THEM IS THE SESSION'S.**

| | who | state |
|---|---|---|
| cleanup / bugfix / docs (**34**) | **the next session** | the whole of its job |
| a second labeller, ten `overlap` rows (**29**) | **the owner** — no agent can do it | open, unchanged, ~16 min |

**The labelling ask has not gone away and nothing below supersedes it.** Every field of
`evals label report` is still refused for want of a *second* `labeller_id` on the same
item; the owner has already answered all ten `overlap` rows, so a second person's ten are
the **last** input `labels.inter_annotator()` needs and the report prints the moment they
land. The tenth row from a second person is still worth more than the hundredth from the
first, and **29 still gates 30, 13's weights and 12's next bump.** It is simply not
something a session can do, which is why it is no longer the entry point.

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
| per-posting rate | 154 s, n=4 | **93 s median, n=29** — and the n=4 sample sat entirely inside a warm-up curve |
| the recall question | unearned | **earned** — 3 non-surfaced postings the labeller would apply to |
| the vocabulary gap | n=1 anecdote, "commercial/sales" | **13 postings**, and a corpus re-derivation that inverted its own instrument |
| floor / ceiling / measured | none | **still none** |

**Three things a fresh session must not do**, each guarded by something other than this
paragraph: do not compute model-vs-human agreement and write it down (`evals label report`
exits 2 by design; there is no `--force` and none may be added); do not redraw `pursuit-v1`
(`redraw_refusal()` refuses, and the window closed with the first label); do not bump
`FACTS_VERSION` to apply `revenue_commercial` without reading **D64** first — it would
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
the median is 93 s**: twenty minutes is **13 postings**, the ten `overlap` rows are
**~16 minutes**, and the DoD's ≥100 postings is **~2.6 hours**. See § *the stopwatch
reading*. (4) **The recall question is earned.** Three postings the pipeline did *not*
surface are ones the labeller says they would apply to, two of them `gate_rejected` —
which is the exact trigger § *How many to label* wrote for itself.

~~last updated after **task 29 stopped being blocked.**~~
The OAuth credentials are in, `.env` is correct, the owner's account is on `pursuit`, and
the sign-in chain was verified end to end without a browser. ~~**The next session's job is
to label.**~~ See § *task 29 is UNBLOCKED* immediately below. Before that: **the
intra-annotator ceiling was made reachable at all, `role_track` went on the form, and a
paired bootstrap landed in `evals/metrics.py`** (suite 1070 → 1107 → 1166 → **1171**). Before that: **task 29 was unblocked: four
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
> track, and two prohibitions. **If a fifth ever appears, check first whether it is
> describing something that already happened.**

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
   they land. At the re-derived 93 s that ask is **~16 minutes**, not the ~26 this file
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

> **MOVED 2026-07-31 → [`docs/archive/handoff-stopwatch-reading.md`](../../archive/handoff-stopwatch-reading.md).** Measured the per-posting labelling rate, 2026-07-31. The n=4 reading (154 s) and its same-day correction at n=29 (93 s median). Superseded as a *narrative* by the single entry in HANDOFF.md's § Pending follow-ups, which carries the live number.

## READ THIS FIRST: task 29 is UNBLOCKED ~~, and the next session labels~~

> **THE HEADING'S SECOND HALF IS SUPERSEDED, 2026-07-31.** Task 29 is still unblocked and
> everything in this section still holds — but **the next session is 34, not 29** (§ *THE
> NEXT SESSION IS CLEANUP*). What is left of 29 is a second person's twenty minutes, which
> is the owner's to arrange and not a session's to execute. Read this section for how the
> labelling surface works and what a solo sitting can and cannot produce; do not read it as
> this session's assignment.

**Done 2026-07-30. Nothing is committed — the working tree carries all of it.** Suite
1160 → **1166** (main) and 61 → **75** (webapp). For the first time in this run **there is
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
> done.** Recorded here so the next session does not re-open it. **The reason is not D59 —
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
`ai_involvement`~~ 85.2% and 94.8% — because that is what makes it legible:**

> **FIGURES CORRECTED 2026-07-31, and the pair that was here is the superseded one.**
> 76% / 94% are the **provisional n=17** figures from 2026-07-27.
> `docs/ingestion_tests/README.md` carries them under a heading that reads *"Superseded"*,
> and `DECISIONS.md` § *06 — Was 76% real?* answers its own question with **no**. The live
> measurements are **`seniority_level` 85.2% [77.6–90.6]** and **`ai_involvement` 94.8%
> [89.1–97.6]**, n=115, `--repeat 3`, `deepseek-v4-flash` at temperature 0. This file
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
person at the re-derived 93 s (§ *the stopwatch reading*) rather than the ~8.5 h the 154 s
figure implied. It does **not** license touching the gate — see § *the first finding
arrived BEFORE the first label* for why n=1 is not a licence.

~~**THE DELIVERABLE THE NEXT SESSION SHOULD ACTUALLY BRING BACK IS A STOPWATCH READING.**~~
**DELIVERED 2026-07-31 — twice, and the second reading corrected the first.** 93 s median,
n=29, `tools/label-findings.py --timing`; § *the stopwatch reading*. The paragraph is kept
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

## State at handoff

**Branch `webapp-service`, suite green at ~~1107~~ ~~1160~~ ~~1166~~ ~~1171~~ **1178** tests (run, not statically counted, 2026-07-31)** (task
files say 263, earlier handoffs 782, 837, 878, 1030, 1058, 1070 and 1107; ~~**1166 is the
floor now**~~ **1171 is the floor now** — `Ran 1171 tests` … `OK`, re-run 2026-07-31; the
five are `backend/tests/test_label_findings.py`). **Webapp untouched this session, still
93.**
~~1107 is the floor now — the round-2 path, `role_track` on the form and the paired
bootstrap added 37 between them.~~
**The whole suite passes** — `python3 -m unittest discover -s backend/tests` from
the repo root. Working tree is clean apart from untracked `scripts/`, which
predates this run and is not ours.

**Two code artifacts landed 2026-07-31 and both are instruments rather than pipeline.**

- **`backend/tools/label-findings.py` — NEW.** Read-only, no LLM call, no API key. Every
  figure in this update's labelling sections comes from it: `--timing`, the recall table,
  the vocabulary marginals, `--side-list`. **It exists because *"re-derive, do not
  re-quote"* was issued three times and re-quoted three times** — re-deriving needed four
  lines of SQL first, and an instruction that costs four lines of SQL decays into a
  quotation. **It deliberately prints no model-vs-human agreement**, and it is not a route
  around `evals label report`'s exit 2: a number computed around that refusal and pasted
  into a document has no exit code to protect the next reader.
- **`backend/tools/derive-role-tracks.py` — FIXED.** `load_other()` gained a
  `--facts-version` flag defaulting to `schema.FACTS_VERSION`, and every run now prints the
  population it read in its header. Before the fix it probed rows extracted under every
  vocabulary the project has ever had. § *findings later tasks must not inherit* has the
  before/after table and the conclusion it inverts.

**On that number: it was 1067, then 1068, then 1070 across a single afternoon** — the
implementing session's report, a re-run an hour later, and a re-run after `90170d1` added
the overlap-stratification tests. All three were correct when taken. This file already
records that test counts drift under concurrent agents (§ *how this run works*); ~~**1070 is
what a re-run reported as this paragraph was written, and it is the floor because it is the
largest.**~~ Re-run before quoting it, and do not treat a number quoted in a handoff as a
number you have measured.

**And it happened again, exactly as that paragraph predicts. Both counts in this section
were re-measured on 2026-07-30 and both were low:**

| suite | command | this file said | re-measured 2026-07-30 | after the solo-labelling work | re-run 2026-07-31 | after `label-findings.py` |
|---|---|---:|---:|---:|---:|---:|
| main | `python3 -m unittest discover -s backend/tests` (repo root, system `python3`) | 1107 | 1160 | `Ran 1166 tests` … `OK` | 1166, `OK` | **`Ran 1171 tests` … `OK`** |
| webapp | `.venv/bin/python -m unittest discover -s tests -t .` (from `backend/webapp/`) | 55 | 61 | `Ran 75 tests` … `OK` | **93, `OK`** | 93, untouched |

**The fifth column is 2026-07-31 and is the first time one of these was quoted and then
held.** 1166 reproduced exactly; webapp went 75 → **93** because `prior_domain` added 18
(the vocabulary, the generated CHECK, the CLI-vs-database agreement, and the join). Same
direction as every other movement in this table: **the suites grew and nothing broke.**

**The sixth column is later on 2026-07-31.** 1166 → **1171**: five tests in
`backend/tests/test_label_findings.py`, covering the break-exclusion threshold, the
warm-up split, and the Wilson-interval formatting. The webapp suite was not touched by this
session and is still 93. **Ninth instance of the same drift, and the same direction again.**

**Task 34 should know that `CLAUDE.md` still says *"It was at 263 tests; it should not go
down."*** The measured figure is **1171**. That instruction is stale by roughly 900 and any
agent following it literally is checking against a number nine times too small to catch a
regression.

**Both moved in the safe direction: the suites GREW and nothing broke.** 1107 and 55 were
each correct when they were written — this is drift, not a regression, and it is now the
sixth and seventh instance of it recorded in this file. ~~**1166 and 75 are the floors
now.**~~ **1171 and 93 are the floors now** (2026-07-31).
Neither is a number you have measured until you re-run it; that is the whole point of the
paragraph above, which was written before this update and correctly anticipated it.

**And the fourth column is the eighth instance, acquired while writing the third.** The
1160/61 column was measured at the start of the 2026-07-30 solo-labelling session and was
correct then. Three agents were working in parallel: the pin guard added 6 to the main
suite and `manage_app_users.py set-profile` added 14 to the webapp suite **while the
documenting agent was writing 61 down**. Neither number was wrong when taken and both were
stale by the time the paragraph containing them was saved. **The instrument is
`| grep -E '^(Ran|OK|FAILED)'` at the moment you need the number**, not a column in this
file — the previous three sentences say so and the column still went stale, which is the
finding.

~~`backend/webapp/tests/` is a separate matter: **`fastapi` is not installed here**, so five
modules fail to import and always have.~~ **WRONG, corrected 2026-07-29.** `fastapi`
**is** installed, in **`backend/webapp/.venv`**, which is a separate environment with a
separate `requirements.txt`. Under it, `backend/webapp/` reports ~~**55 tests, OK**~~
~~**61 tests, OK**~~ **75 tests, OK** (re-measured 2026-07-30; see the table above). The
original observation was made with system python. `backend/tests/` is still the suite that
gates work here and still does not cover `webapp/`; the two are run with two interpreters.
See § *task 29's "two mechanical minutes"* for what this changes — chiefly that serving
`/v1/label` needs no install.

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
| — | step 0 planned and measured against the live corpus | `bb910c0` |
| — | **step 0 IMPLEMENTED — gate to JSON, proven no-op** | `4eefb7e` |
| — | **step 0 — entry-level vocabulary split, recall 48.3% → 86.2%** | `e8f3b72` |
| — | **step 0 — `title_exclude` narrowed, recall → 89.7%** | `9dab9e6` |
| — | **step 0 — the gate written to `profiles`** | no commit — a database write |
| 29 | **sampler — three defects: wrong gate, starved window, one-labeller ceiling** | `c65d34b` |
| 29 | **rank spacing (84 → 110 distinct) + `pursuit-v1` drawn and pinned** | `2f64e08` |
| 29 | **overlap block stratified — the ceiling was on the easy cases; set redrawn, pin unchanged** | `90170d1` |
| 29 | **the three label tables created and granted** | no commit — a database write |
| 29 | **round 2 made reachable at all — the intra-annotator ceiling had no code path** | this session |
| 29 | **`role_track` a 6th question, `NO_TRACK_FITS`; `FIELD_KINDS` drift found** | this session |
| 30 | **paired bootstrap into `evals/metrics.py` — degenerate resamples no longer scored 0.0** | this session |
| 29 | **OAuth credentials in, `.env` origins fixed, owner's account moved to `pursuit`** | ~~UNCOMMITTED~~ `4374ede` (`.env` gitignored) |
| 29 | **`manage_app_users.py set-profile` — moving a user between profiles had no path** | ~~UNCOMMITTED~~ `4374ede` |
| 29 | **`redraw_refusal()` — a pinned set could be silently re-drawn; now refused** | ~~UNCOMMITTED~~ `4374ede` |
| — | **doc sweep: 5 stale `Status:` lines, `label.py` citations, both suite counts** | ~~UNCOMMITTED~~ `4374ede` |
| 29 | **the first 30 labels — 5 postings, one labeller** | no commit — a database write |
| 29 | ~~**the per-posting rate MEASURED at ~154 s; the 20-minute budget is out by 2.5x**~~ | `127c7c0` |
| 29 | **`app_users.prior_domain` — Axis B disagreement was undecomposable by background** | `127c7c0` |
| 29 | **a design session's 4 findings verified: 1 did not reproduce, 1 premise was wrong** | `127c7c0` |
| — | **`extract.py` does NOT fan out per profile — `manage_app_users.py`'s header corrected** | `127c7c0` |
| 29 | **the sitting ran to 186 rows / 31 postings; ALL TEN `overlap` rows done** | no commit — a database write |
| 29 | **`tools/label-findings.py` — the re-derivation this file asked for three times, as a command** (+5 tests, suite → **1171**) | this session |
| 29 | **the per-posting rate RE-DERIVED at 93 s, n=29 — the 154 s reading was a warm-up curve, and the correction is CHEAPER** | this session |
| 29 | **the recall question EARNED — 3 postings the pipeline did not surface, 2 of them `gate_rejected`, that the labeller would apply to** | this session |
| 11 | **`derive-role-tracks.py` had NO `facts_version` filter — 58% of its `other` population was the twelve-value vocabulary; the "26 values are unused" reading inverts** | this session |
| 11 | **`revenue_commercial` proposed — 23.1% of the v3 `other` bucket from ONE value; deliberately NOT applied, no `FACTS_VERSION` bump while `pursuit-v1` is open** | this session |

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

> **MOVED 2026-07-31 → [`docs/archive/handoff-owner-decisions.md`](../../archive/handoff-owner-decisions.md).** Recorded 2026-07-28, landed in `943d899`. Selective majority-of-3 extraction and the 40/day ceiling. Both shipped; the rationale is in DECISIONS.md under EXTRACT.

## Nothing is in flight — but the tree is NOT clean

**Nothing is half-written and nothing is waiting on a reply.** Step 0 is implemented,
committed and written to the database, and so are task 29's four sampler fixes and its
drawn set; the docs were rolled forward in the same session each time. ~~The working tree
is clean apart from untracked `scripts/`, which predates this run and is not ours.~~

~~**AMENDED 2026-07-30: the working tree carries the whole solo-labelling change and NONE of
it is committed.** It is finished, not half-done — both suites are green at **1166** and
**75** — but a fresh session will find modifications, not a clean checkout:~~

```
 M backend/evals/__main__.py            M backend/webapp/manage_app_users.py
 M backend/evals/labels.py             ?? backend/webapp/tests/test_set_profile.py
 M backend/tests/test_labels.py         M docs/tasks/refactor/  (8 files)
```

~~plus `backend/webapp/.env`, which is **gitignored and will never appear in `git status`** —
and which now holds the OAuth secrets.~~ Untracked `scripts/` still predates this run and is
still not ours.

> **RE-AMENDED 2026-07-31: all of the above is COMMITTED, at `4374ede` — "Unblock task 29,
> and guard the pin before the first label closes it" — plus the four commits before it.**
> The file list above is now the *contents* of that commit rather than a description of a
> dirty tree. `git status` is clean apart from untracked `scripts/`, which still predates
> this run and is still not ours. `backend/webapp/.env` remains gitignored and still holds
> the OAuth secrets, so that half stands. Suite counts re-run 2026-07-31 and unchanged at
> the time of the commit: **1166** and **75**.

**Two database writes have no commit and cannot be inferred from the tree**, the same way
the gate write and the label tables could not: the owner's `app_users` row moved from
`tech` to `pursuit`, and ~~`eval_labels` is **still empty** — so the redraw window is open
until the first label is submitted, and~~ `redraw_refusal()` is what now closes it on
purpose rather than by memory.

> **THE REDRAW WINDOW IS CLOSED. Measured 2026-07-31: `eval_labels` holds 30 rows** — 5
> postings × 6 questions, one labeller (`u_090b0ad12e99`), round 1, `labelled_at`
> `2026-07-31T02:56:05`–`03:06:19` UTC, which is the evening of 2026-07-30 in New York and
> is **one sitting, not two**. So `pursuit-v1` is now permanently pinned: `redraw_refusal()`
> refuses every redraw, identical digest included, exactly as designed. **Nothing can be
> added to or removed from the drawn set from here on.** A third database write to add to
> the list above: the labels themselves.
>
> This also makes two things live that this file records as risks rather than facts.
> `consensus()` promoting a majority of size one is happening now, not hypothetically. And
> the per-posting timing is no longer unmeasured — see the pending follow-up below and
> `tranche_five/29-labelling-session.md` § *Findings, 2026-07-31*, E.

**The next session starts from a finished state**, and for task 29 it starts from one that
is waiting on nobody.

**What the task-29 session wrote to the database**, all of it new and none of it touching
anything that existed: the three label tables created by `evals label init-schema` as
`jobs_pipeline`, the `jobs_web` grants from `labels.WEB_PRIVILEGES`, and one registered
set — `pursuit-v1`, 200 rows in `eval_label_items`, **re-registered once when defect 4
forced a redraw**. **`eval_labels` is empty and must stay that way until people put labels
in it** — and it being empty is what made that redraw safe.

**Proof that nothing else moved.** Content digests byte-identical either side:

| table | rows | content digest |
|---|---:|---|
| `job_matches` | 3,521 | `383a9266c3b862716ff977e08491dd0e` |
| `job_scores` | 1,293 | `6960a9c3a1f39cdfbd8f8ecb838b645b` |
| `job_facts` | 5,923 | `df46e5ee2a1b63ab93d080fdbf6f5a7e` |

**These digests are computed over a DIFFERENT COLUMN SET from the ones quoted earlier in
this file** (`c98c4bbc…`, `90715a5f…`, `af8a273f…`). They are before-and-after pairs within
this session and prove nothing was overwritten *during it*; they are **not** comparable to
the older values and a difference against those means nothing. Say which columns went into
a digest, or it is a number that can only mislead the next reader.

**Six agents ran in the implementing session** — three read-only verification up front,
three writing documentation on disjoint files at the end. The orchestrator made every code edit, every measurement and
every commit itself, because the four commits were strictly sequential and each gated on
the previous one's numbers.

**One row of `profiles` was written** — `pursuit`'s `relevance_json`, by
`migrate_profiles.py --apply` with all three file flags and no `--bump`. Everything else
was a `SELECT`. Proof that nothing else moved: the `job_matches` content digest is
byte-identical before and after (`c98c4bbceed1b77d82979e83dfad70cc`, 3,521 rows), and
`md5(persona_json)` and `md5(criteria_json)` are unchanged. **Take the digest, not the
count** — a count cannot see an overwrite.

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
**1070, OK**. `backend/.env` is not exported by default — scripts that reach the
database need `cd backend && (set -a; . ./.env; set +a; python3 ...)`. **The webapp is a
second environment**: `cd backend/webapp && .venv/bin/python -m unittest discover -s tests
-t .` reports **55, OK**, reads `backend/webapp/.env`, and is not covered by the 1070.

**Then read this, because it is the one thing a fresh session will get wrong:** task 13
is committed and its Definition of done is *not* met. See the top of this file. A
completed task here is not a validated one.

### The next session's likely first question, answered

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

They are a **specification test** (D46). They measure agreement with an author's intent,
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

**Live state after the gate-fix session (2026-07-29T15:42Z, the nightly having run at
04:12).** `jobs` 14,049 (13,447 open / 602 closed), `job_facts` 5,923 (881 @v3 + 5,027
@v2 + 15 @v1), `job_matches` 3,521 (pursuit 144 / tech 3,084 / frontend 293), `job_scores`
1,293 (tech 1,110 / frontend 183, **pursuit 0**). `pursuit` is the only active profile,
`criteria_version` 2, `daily_narrative_budget` 0.

**The one write this session made** is `pursuit.relevance_json`:
`md5` `e4efd209789cbeeac201b2102fd6afb8` → **`73b110df7aea5937caabb553077632fd`**, 23 keys.
`persona_json` (`39dc8bdc…`) and `criteria_json` (`7b58380d…`) md5s are **unchanged**, and
the `job_matches` content digest is **byte-identical** either side
(`c98c4bbceed1b77d82979e83dfad70cc`, 3,521 rows). **Gate now admits 880 of 13,447 open**
— tier 1 456, tier 2 424, tier 3 12,567 — and `extract.remaining` is **13**, up from 2.
That backlog drains on the first nightly run, ~$0.004.

**Live state after the mock-acceptance / strip_html session (2026-07-29T05:40Z),
superseded by the paragraph above but kept for its attribution reasoning.**
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

**And it happened a THIRD time, on 2026-07-30, and this one nearly reached a document as a
bare fact.** The timer fired at **04:09** — `max(first_seen)` 2026-07-30T04:09:01,
`max(extracted_at)` 2026-07-30T04:11:47 — ingesting **388 new postings** and **36 new
`job_facts` rows**. `facts_version = 3` went **881 → 917** and `pursuit`'s `job_matches`
**144 → 152**. Attributed, not assumed: `job_scores` was byte-identical
(`daily_narrative_budget` is 0), `eval_labels` still 0 rows, `eval_label_items` still 200,
no new scratch schemas, and the session's own edits were confined to `evals/`,
`webapp/label.py`, `evals/tasks/extract.py` and two test files — none of which is in the
pipeline write path.

**What it moved is the instructive part: a statistic about a PINNED set.** `pursuit-v1` is
pinned by sorted `job_id`, its `sha256` is unchanged, and its membership *cannot* drift —
**but the facts underneath its rows can, and did.** One `below_floor` posting acquired a
`role_track` overnight, taking the set's NULL count 83 → 82 and the corpus rate 27.7% →
28.5%, inside a single working session and after the first figure had already been handed
to a writer.

**So the rule, and it is narrower and more useful than "take a baseline":** a pin on set
membership buys you nothing about the derived facts. **Any figure computed from `job_facts`
about a pinned set must carry the date it was taken, and a figure quoted without one is
unverified.** The two previous instances moved *counts of rows*; this one moved a *rate
about a frozen sample*, which is the version that looks safe to quote.

**A second-order trap this exposed.** The superseded corpus rate, **244 of 881**, is
**27.7%** — and `docs/facts-v3-diff.md:468` independently reports a `role_track` NULL rate
of **27.7%**, from **239 of 863**. Different denominator, different run, same rounded
number. **That is precisely the shape in which one measurement gets quoted as
corroborating another.** The current figure, 28.5%, breaks the coincidence. If you meet a
bare "27.7%", establish its population first.

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

**A sequential change is not a parallelisable one, and pretending otherwise costs more
than it saves.** The gate fix was four commits where each one's gate was the previous
one's measurement — a mock number, a live row count, a dead-term list. The orchestrator
did all four itself. Agents were used where the work genuinely forked: **three read-only
verification agents up front** on disjoint areas of the code, and **three documentation
agents at the end** on disjoint files. That is the shape to copy: fan out on *reading* and
on *writing prose*, not on a chain of edits that each need the last one's number.

**Verify the plan against the code before implementing it, not after.** Three agents spent
one round-trip checking step 0's claims and found ten errors, four of which changed the
work — including a required test that asserted something which could not fail, and a
script that refuses to run before it checks `--apply`. **Step 0 had itself been produced by
a careful session with live measurements.** Its numbers were all correct; its claims about
the code were not. Those are different things and they fail independently.

**And verify the plan's ARITHMETIC against the artifact, not against the algebra.** Task
29's plan asserted that rotating labellers by `sha256(labeller_id)` would give 110 distinct
postings, from `distinct = overlap + n * (budget - overlap)`. Counted against the drawn
200-row set: **84.** The formula assumes disjoint windows; hashing gives random ones, and
random windows collide. **The formula was not wrong — it was describing a different
mechanism from the one being built**, which is the failure a re-read of the code cannot
catch, because the code matched the plan. Rank spacing gives 110. **26 postings and a
Definition of done**, and the only thing that found it was computing the number the plan
had asserted.

**A finished artifact is where to look for the defects the checks cannot see. Three of task
29's four were found that way** — after the code was written, the tests were green and, for
the fourth, after the artifact had been committed. The gate misclassification surfaced from
counting `surfaced` two ways; the 84-vs-110 from counting distinct postings instead of
trusting the formula; the overlap skew from **reading the ten rows in the block rather than
the strata totals above them, which were correct.** In all three the marginals summed. **A
total is not a composition**, and a suite that is green tells you the code does what it was
written to do, not that what it was written to do is what was wanted. **Budget a pass that
looks at the output itself, after everything is green — it is where the expensive ones
were.**

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
> The ask is **~16 minutes** at the re-derived 93 s (§ *the stopwatch reading*), not the
> ~26 written above and not the ten written three times before that.

0. ~~**Fix the relevance gate.**~~ **DONE 2026-07-29** — `4eefb7e`, `e8f3b72`, `9dab9e6`
   and a database write. Mock gate recall 48.3% → 89.7%, live tier ≤2 869 → 880,
   `extract.remaining` 2 → 13, suite 1030 → 1058. See § *the gate fix LANDED*.

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
      ten minutes.** Ten `overlap` rows at the re-derived **93 s** is **~16 min**
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
      § *How many to label*). 200 postings is **5.2 h** for one person at 93 s. **The
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
   form now asks SIX.** `role_track` was added (D61), so ~20 items and ~28 items are each a
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

> **MOVED 2026-07-31 → [`docs/archive/handoff-session-method.md`](../../archive/handoff-session-method.md).** Method notes from the same sessions. The durable half is promoted to HANDOFF.md § How this run works.

## Pending follow-ups with no task of their own

- **The per-posting labelling time is MEASURED at 93 s (n=29), and the twenty-minute budget
  is out by ~1.5x in the CHEAP direction.** Re-derived 2026-07-31 with
  `python3 backend/tools/label-findings.py --timing`, over all 31 postings labelled by
  `u_090b0ad12e99` in `2026-07-31T02:56:05`–`05:25:27` UTC, one 5,765 s break excluded at
  `--break-secs 600`. Median **93 s**, mean **110 s**; including the break, median 97 s /
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
  so drift fails loudly. Suite 1171 → **1178**.

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

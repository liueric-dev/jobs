# The inter-annotator ceiling, and the labelling night's pre-flight

> **Archived from `docs/tasks/refactor/HANDOFF.md` on 2026-07-31**, when that file was split.
>
> **What it is:** Recorded 2026-07-30. Why the ceiling was unreachable, the three documents that disagreed about which ceiling gets measured, and the two pre-flight values that were wrong and silent. All fixed and verified. **The two operational subsections that were at the end of this section did NOT move** -- `FRONTEND_ORIGIN` and the `app_users` schema are live reference and stayed in HANDOFF.md.
>
> Moved, not deleted. `git log --follow` on this path reaches the original text, and a stub
> and link remain where this section was.

---

## READ THIS FIRST: the ceiling was unreachable, and the night's pre-flight

**Done 2026-07-30. Suite 1070 → 1107.** Three things landed and one of them was a defect
of the same family as the four above: **correct, tested, and with no path to it from
production.**

### What the inter-annotator ceiling IS, and what it is responsible for

Asked directly, and worth answering here because two different ceilings are discussed in
this section and the difference decides what the night has to collect.

**What it is: how often two different people give the same answer about the same posting,
per field.** `labels.inter_annotator()` (`evals/labels.py:1404` as of 2026-07-30 — **find it
by name**, this file's line numbers have moved three times in one session). Its own first
line is the definition — *"THE CEILING: how often two different people give the same
answer."*

**What it is responsible for: making every other number in the report readable.** The
docstring puts it better than a paraphrase can:

> Without it, "the model agrees with humans 80% of the time" cannot be read: if humans
> agree with each other 98% the model is bad, and if they agree 79% the model has already
> saturated the task and no prompt change will help.

So it is not a nice-to-have statistic beside the model score. **It is the scale the model
score is denominated in**, and the same 80% means "fix the prompt" or "stop working on this"
depending entirely on it.

**And it is responsible for that structurally, not by convention.** It is one of the three
fields of `labels.Interpretable` (`:1778`), whose `__post_init__` raises `Uninterpretable`
if `floor`, `ceiling` or `measured` is missing or has no `n` (`:1808-1815`) — and
`Interpretable` is *"the ONLY thing report.render_labels() accepts, so there is no code path
anywhere that prints a model-vs-human number alone. Making the bad report unrepresentable
rather than discouraged is the whole design; a `--force` flag would undo it and there
deliberately is not one."* **A labelling night that produces no ceiling produces no
report** — not a report with a caveat.

The three quantities it sits between:

| | quantity | source | what it bounds |
|---|---|---|---|
| floor | model self-consistency | `metrics.selfcheck` | below which disagreement is instability, not error |
| **ceiling** | **two people, same posting** | **`inter_annotator()`** | **above which there is nothing left to resolve** |
| measured | model vs the majority human answer | `model_vs_human()` | the question itself |

**Where it is measured, and why the overlap block's stratification mattered.** Only the
`overlap` rows are seen by more than one person, so the ceiling is computed on those and
nothing else — **10 rows in `pursuit-v1`, stratified 5 `surfaced` / 3 `below_floor` /
2 `gate_rejected`.** That stratification was defect 4 of the previous session: an
unstratified block came back 6 of 10 `gate_rejected`, i.e. postings the pipeline threw away,
on which agreement is near-unanimous **for free**. A ceiling measured on the easy cases is
too high, and every model score read against it then looks worse than it is.

**How to read the numbers it returns** (all `metrics.field_cell()`, so they mean exactly
what they mean in the self-consistency table — that is what lets floor and ceiling be
columns of one quantity rather than two statistics that merely look alike):

- **`agree2`** — the two lowest-sorted labeller ids. Arbitrary but stable, one Bernoulli
  trial per item, so it **carries a Wilson interval** and is the cell that goes in the table.
- **`pairwise`** — the mean over all C(N,2) pairs. The **better point estimate**, and it
  carries **no interval**, because pairs drawn from one item are not independent trials.
- **`unanimous`** — everyone agreed.
- **Abstentions are dropped and counted**, never folded in: a NULL is "I cannot tell from
  this posting", and *"folding them in as a value would score two people who both gave up as
  two people who concurred."*
- `by_platform` sits **beside** the blended figure and never replaces it — the per-platform
  cells are single-digit at any label count this session can realistically collect, which is
  what `is_thin()` exists to make visible.

**Versus the intra-annotator ceiling, which is the subject of the rest of this section:**
intra is *one* person answering the same posting twice, a week apart. It is a **different
quantity**, and a weaker one — `inter_annotator`'s docstring calls inter *"the better
ceiling"* and keeps intra *"because attrition may leave it as the only one with any n"*.
Inter comes free from overlapping a set; intra costs every volunteer a second sitting.
`tests/test_labels.py`'s `test_the_two_ceilings_are_different_quantities` is the pin
(`:465` today — cited by name for the reason above). `intra_annotator()` is at
`evals/labels.py:1477`.

**The practical consequence for the night: the inter-annotator ceiling is the one you
cannot skip.** Ten Builders each answering the ten overlap rows produces it at no extra
cost, and without it there is no report at all. The second sitting is optional.

### The intra-annotator ceiling could not be collected at all

`labels.intra_annotator()` has existed and been tested since task 07. **Nothing could
ever feed it.** `webapp/label.py` never passed `round_no` to `labels.record()`, and
`next_item()`'s queue filter had **no `round_no` predicate** — its docstring said *"the
next job this labeller has not answered anything about"*, which is exactly what it did, so
once a labeller answered a posting it was never served to them again. Every row that could
exist was `round_no = 1`, and the function that reads round 2 was unreachable.

**A tested function with no caller reads exactly like a working feature.** That is the
generalisation, and it is the same shape as defect 3 above: nothing was red, because
nothing asserted that the *path* existed.

**What landed.** `next_item(..., round_no=2)` serves the **overlap block only**,
restricted to rows that labeller answered in round 1 and has not answered in round 2
(`evals/labels.py:1112-1145`). `labels.round_two_ready()` (`:1010`) enforces
`ROUND_TWO_DELAY_DAYS = 7` (`:1007`) and returns a **date**, so the form says *"come back
on the 8th"* rather than showing an empty page. `progress()` counts round 2 against the
overlap block, not the 200-row set (`:903-925`) — *"3 / 200"* on a ten-row queue reads as
an eight-hour evening. The form takes `?round=2` and carries it through the POST and the
303 (`webapp/label.py:257`, `:320`, `:360`).

**Why the overlap block and not a fresh 5-10:** both ceilings are then measured on
**identical postings** and can be read against each other, instead of differing for two
reasons at once. **Why seven days:** served an hour later, round 2 measures whether the
labeller *remembers* their first answer — near 100%, and it would be quoted as a ceiling.
D58 and D59 in `DECISIONS.md`.

**And the decision this does NOT make:** whether to spend ten volunteers' second ten
minutes on the weaker of two ceilings. **That is the repo owner's call on the night, not
an implementer's.** Both paths are implemented; the round-2 link is simply not sent unless
someone chooses to send it.

### Three documents disagreed about which ceiling gets measured, and all three are now reconciled

Worth knowing because each was internally consistent, so nothing looked wrong:

**Line numbers below are given as they were BEFORE the corrections were written, because
writing them moved every one of them.** Current positions in parentheses. Quote the text.

- `tranche_two/07-metrics-and-golden-set.md:57-59` (now struck through at `:71-75`) said
  inter-annotator *"is a better ceiling and it costs nothing extra"* and read as
  **superseding** the intra-annotator one.
- `07:81`'s DoD asked for *"Inter-annotator agreement … not just intra-annotator"* — while
  **`07:77` (now `:143`) inherits `docs/ingestion_tests/03-metrics-and-golden-set.md`'s DoD
  wholesale**, and `03:142` (now `03:179`) requires *"the self-consistency floor and human
  self-agreement ceiling beside each number"*, where `03:25` defines that ceiling as the
  **intra**-annotator quantity. So 07 replaced a requirement and inherited it in the same
  breath.
- **`03:107-108` (now `03:127-128`) claimed the tool *"supports a second pass over
  already-labelled jobs"* — false from the day it was written until 2026-07-30.**

**The resolution, recorded in all three:** the capability question is closed — both
ceilings are collectable, over the same postings, and the "second pass" clause is true
again.
Inter-annotator is the better ceiling and comes **free** from the overlap block;
intra-annotator is the weaker one, kept because attrition may leave it as the only one
with any n, and it **costs a second sitting**. `interpretable()` accepts the
inter-annotator cell as `ceiling`, so a report is renderable without round 2 ever
happening. **The spending question is left open on purpose.** "Supersedes" was retracted
rather than deleted; see 07, § *Both ceilings are collectable now*.

### `role_track` is a sixth question, and the budget arithmetic was computed for five

On the form with a `labels.NO_TRACK_FITS` choice, because `extract.py:338` tells the model
null means *"no listed track describes this role"* — a **verdict** — while the form's *"I
can't tell from this posting"* is an **abstention**, and `validate()` collapses both to
None. Without the new value `model_vs_human` would score a verdict and a shrug as
agreement. The fold happens at comparison time only (`labels.as_model_domain()`, `:1492`);
storage keeps them distinct. D60 and D61.

**Measured 2026-07-30 after that morning's nightly run, and it is why the field is worth a
question:** `role_track` is NULL on **261 of 917** `job_facts` rows at `facts_version = 3`
(**28.5%**; non-null 656 of 917), and within `pursuit-v1` on **16 of 100 `surfaced`, 16 of
50 `below_floor`, 50 of 50 `gate_rejected` — 82 of 200**.

> **Superseded and correct when taken (2026-07-29, before the run):** 244 of 881 = 27.7%
> corpus-wide, 83 of 200 in the set, 17 of 50 `below_floor`. **One `below_floor` row
> acquired a `role_track` overnight** — that is the whole of the in-set delta — and 36 new
> v3 rows moved the denominator. **A pin on set membership buys nothing about the derived
> facts underneath it**; see § *nothing is in flight*, under *"the other agent in the room
> is the cron job"*, where this is written up as the third instance.

On those 82 `model_vs_human` is silent, which inverts the usual argument: **if
a human confidently assigns a track where the extractor abstained, the NULL rate is an
extraction problem; if the human cannot either, the vocabulary is wrong.** Different fixes,
and no other instrument tells them apart. Written up in `docs/role-track-derivation.md`,
whose `:324-325` asked for exactly this validation.

**Also measured, and it bounds what the night can produce — re-verified 2026-07-30 after
the nightly run and UNCHANGED by it:** **26 of the 50 `gate_rejected` rows have no
`job_facts` row at all** (24 carry facts), so `model_vs_human` can score no axis-A field on
them. `surfaced` is 100/100 and `below_floor` 50/50. And **the pinned
fixture carries the score axis itself** — `match_score` on 100/100 surfaced (range 40–92),
`computed_score` on 50/50 below_floor (range 0–34), and **neither column on any of the 50
gate_rejected** — so an axis-B precision figure needs no database read, and
**`gate_rejected` cannot enter a precision rate at all**: it yields a recall bound (k of
50, with a Wilson interval), never a rate.

**THE BUDGET FIGURE NOW COMPETES WITH A SIXTH QUESTION.** *"≥100 distinct needs ~28 items
each at 5 labellers"* (§ *recommended next steps*, and D57) was computed against a
five-question form in a twenty-minute sitting. The form asks six. **No new number is
asserted here — re-check the arithmetic before the night, not during it.** And if round 2
is spent, that is **~10 more minutes per labeller**, seven days later.

**A drift this found:** `role_track` was **missing from `evals/tasks/extract.py`'s
`FIELD_KINDS` entirely** — task 11 added the column and never registered it, exactly the
drift that file's own comment warns about. Caught by an **existing** test the moment the
field went on the form.

### A paired bootstrap, and the guard it refuses

`bootstrap_delta()` lifted into `evals/metrics.py:705` from
`tools/learned-ranker-probe.py`, **rejecting one line of the original on the way**: the
probe scores a degenerate resample (no positives) as average precision **0.0**
(`learned-ranker-probe.py:438`). Both sides of such a draw get 0.0, so its delta is exactly
0.0, and every one is another exact zero in the middle of the distribution the percentiles
read off — **the interval widens toward zero and manufactures "not distinguishable" out of
an arithmetic guard.** Rare at n in the hundreds; **routine at the per-`role_track` n of
about a dozen task 30 needs** (one positive in twelve rows makes ~35% of draws degenerate).
Degenerate draws are now skipped and counted, with `draws_used` carrying what the interval
rests on. D63 has the measured before/after. **The guard would have been silently deciding
the very comparison it was written to protect.**

### ~~The night's pre-flight — two values are wrong and neither errors~~ FIXED, and this is the diagnosis

> **Both values were corrected on 2026-07-30 and verified; the OAuth secrets are in.**
> Everything below is now the RECORD of why they are what they are, not a list of work.
> It is kept in full because the failure produced no error at all, and the diagnosis is
> the only thing that explains why `FRONTEND_ORIGIN=http://localhost:8421` is not an
> arbitrary value. **Do not act on this section — read § *task 29 is UNBLOCKED*.** The
> Case B parts (a tunnel host, `SESSION_COOKIE_SECURE=true`) become live again the day
> Builders label from their own devices.

**Verified 2026-07-30.** `LABELLING-NIGHT.md` is the executable version, ~15 minutes.

1. **`FRONTEND_ORIGIN` sends a successful sign-in to a dead origin.** It is
   `http://localhost:5173` in `backend/webapp/.env`, and the post-login redirect is built
   from it — `RedirectResponse(config.FRONTEND_ORIGIN + safe_next_path(next_path))`
   (`webapp/auth.py:359-360`). But `/v1/label` is served by **this service on `:8421`**
   (per `GOOGLE_REDIRECT_URI`, and `PORT` defaults to 8421), and **`frontend/` is a lone
   `.gitkeep`** — there is no dev server on `:5173` to start. **So with the OAuth secrets
   filled in and nothing else changed, sign-in SUCCEEDS, the session cookie is set, and the
   volunteer lands nowhere.** No error, no log line. **One-line `.env` fix, to be made
   alongside the secrets**, plus `ALLOWED_ORIGINS` in the same file. This file already
   warned that it *"must point at the origin the service is actually served from"*; what is
   new is that the current value is confirmed wrong and the failure is confirmed silent.
2. **The only `app_users` row is `ericliu93@gmail.com` on profile `tech`, which task 12
   made inactive.** It is **not a working example of a cohort labeller** — every Builder
   needs `--profile pursuit`. Copying the existing row's shape adds people to a dead
   profile.

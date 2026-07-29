# Handoff — the `docs/tasks/refactor/` run

Written 2026-07-28, and rolling — last updated after **task 29 was unblocked: four
defects fixed in the sampler, the label tables created, and the 200-row set drawn, redrawn
and pinned** (`c65d34b`, `2f64e08`, `90170d1`). Before that: **step 0, the gate fix**, implemented and
written to the database (mock gate recall 48.3% → 89.7%, live tier ≤2 869 → 880); the
planning session that measured it; the **mock acceptance run and the `strip_html` fix**;
**`job_scores`' version keys** (`d18ea54`); and **13, 35 and D45** (`fa2d7a7`, `303f7b9`,
`e11fabf`). Read this first, then [`DECISIONS.md`](DECISIONS.md) (why each choice was
made) and [`CLAUDE_UPDATES.md`](CLAUDE_UPDATES.md) (what happened, per task).
[`README.md`](README.md)'s status column is the ordered index.

~~**If you are a fresh session, the whole of your job is task 29 and its first two commands
are mechanical.**~~ **That sentence was WRONG and it is the headline of this update.** The
first command was mechanical; the second would have drawn a set that measured the wrong
gate, starved its own key stratum, and could not have reached task 29's Definition of done
at any turnout. See § *task 29's "two mechanical minutes"*. **Task 29 is still the whole of
a fresh session's job, and what is left of it is now genuinely only people**: Google OAuth
credentials and ten Builders, both the repo owner's.

## Orientation — there are four "READ THIS FIRST" sections, in this order

That is three too many, and the file has earned each one. If you read nothing else:

1. **Task 29 is the whole critical path** (§ *what is blocked*), and **its schema, its
   sampler and its 200-row set are now DONE** (§ *task 29's "two mechanical minutes"*).
   ~~Its first two steps are mechanical and unblocked — minutes, no credential.~~
   **SUPERSEDED 2026-07-29, and this file was wrong in the expensive direction:** the
   second of those two commands carried **four** defects, none of them red, and the set it
   would have drawn measured the wrong gate. Fixed, drawn, **redrawn once more after the
   set was already committed**, pinned at
   `backend/evals/fixtures/labelset-pursuit-v1.jsonl`. **What is left really is only
   people** — Google OAuth credentials and ten Builders. And **the 55 postings in
   `docs/tasks/refactor/mock/` are still not its data** — they are invented, and reduce
   its scope by zero postings.
2. **Do not re-tune task 13's weights** (§ *the ranking is a product now*). Its DoD is
   unmet on purpose. Nothing measured since — including the mock corpus's 5-of-5 on
   branding traps — licenses changing them. Only task 29 does.
3. **Do not reactivate `tech` or raise `daily_narrative_budget` casually**
   (§ *the cost lever hiding in the profiles table*). Either one restores a ~5,000-row
   re-extraction bill or a ~1,018-call re-scoring bill. Run `score.py --stale-report`
   first; it needs no API key.

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
claim depends on it. The `fastapi` claim needed a different instrument again —
**ask which interpreter the observation was made with**, because "it fails to import" is a
fact about an environment, not about a repo.

## READ THIS FIRST: task 29's "two mechanical minutes" were four defects, and the set is drawn

**Done 2026-07-29, three commits: `c65d34b` (three sampler fixes), `2f64e08` (rank spacing
and the drawn set) and `90170d1` (the stratified overlap block, and a redraw), plus the
label tables created in the live database.**

**This file said task 29's first two commands were "mechanical" and called them "two
mechanical minutes"** — in its own Orientation, in § *what is blocked*, and in
§ *recommended next steps*. **They were not.** `init-schema` was. `evals label sample`,
as it stood, would have drawn a 200-row set that

- **(a)** classified every row against a gate the pipeline does not run,
- **(b)** starved the one stratum the precision figure is quoted from,
- **(c)** could not have reached task 29's Definition of done at any turnout, and
- **(d)** put the inter-annotator ceiling on the easy cases.

**None of the four was red.** Nothing asserted coverage, `sample()` under-fills in silence,
a set drawn against the wrong gate looks exactly like a set drawn against the right one,
and **(d) was found only after the set had been drawn, pinned and committed** — by looking
at the ten rows the block actually contained rather than at the strata totals, which were
correct. All four are fixed and the set has been redrawn.

### The four defects, each measured against the live corpus

**1. The sampler classified against the AUTHOR's gate, not the cohort's.** `labels.pool()`
(`evals/labels.py:498`) and `pool_query()` (`:440`) defaulted `cfg` to `relevance.load()`
— the shared `config/relevance.json` — while taking a **profile** as the argument that
names the population. `classify()` tests `tier > max_tier` **before** it looks at
`match_score` (`evals/labels.py:544-546`, in `classify()` at `:542`), so the gate decides
the stratum first and everything else second. The rationale now lives in `pool_query()`'s
own docstring at `:444-453`, with these numbers in it — the argument is `cfg IS REQUIRED`
rather than a defaulted one, so the defect cannot be reintroduced by omission.

| classified `surfaced` | count |
|---|---:|
| under the shared author gate | 59 |
| under `pursuit`'s own gate | **144** |

**85 postings the pipeline actively surfaces would have been filed as `gate_rejected`** —
the one stratum whose entire value is being identified correctly. Fixed with
`relevance.for_profile()` (`relevance.py:100-109`); the CLI now loads the profile row and
hands its gate in explicitly rather than letting the default resolve
(`evals/__main__.py:279-292`).

**And this is what made this file's own ordering constraint real.** "Draw the sample AFTER
the gate fix" (§ *what is blocked*) bought **nothing** while the sampler was reading a
different gate from the one commit 4 wrote. The constraint was correct and inoperative,
which is the worst of both — it is a real dependency that no artifact would have shown you
was being violated.

**2. The recency window starved `surfaced`.** `--per-platform` defaulted to 400 rows per
platform, which held **29 of pursuit's 144** surfaced postings: greenhouse 6/65, ashby
13/52, google_jobs 9/26. `sample()` takes what a stratum has and moves on. `PARTITION BY
platform` answers CLAUDE.md's "~85% greenhouse/ashby" composition complaint and does
nothing at all about the recency truncation underneath it — **two different traps, one of
which was being mistaken for the other.** The default is now the whole table (`jobs` is
~14,000 rows; one `SELECT` over all of it is free), and `cmd_label_sample` **exits 2 and
names the shortfall** on any under-filled stratum (`evals/__main__.py:306-345`).

**3. Distinct coverage was capped at ONE labeller's throughput.** `next_item()`
(`evals/labels.py:924`, the defect written up at `:927-936`) served every labeller the
identical queue — `overlap DESC, position ASC` for everyone. Ten volunteers doing
twenty postings each therefore answered **the same twenty**, so

```
distinct = overlap + n_labellers * (budget - overlap)
```

had a structurally **zero second term**: distinct coverage could never exceed what one
person completed, and task 29's "≥100 labelled postings from ≥5 labellers" was unreachable
**regardless of turnout**. The tail is now rotated by the labeller's rank; overlap rows
still come first, because they are what makes the agreement ceiling measurable.

**4. The overlap block was not stratified, and it carries the ENTIRE inter-annotator
ceiling.** `sample()` marked the first `overlap` rows of a `job_id` sort — stratified by
nothing at all. The overlap block is the only part of the set more than one person sees, so
it is not a sample of the set: **it is the whole of one of the three quantities task 29
exists to produce.** The first draw of `pursuit-v1` came back

| overlap block | first draw | redrawn | set proportion |
|---|---:|---:|---:|
| `surfaced` | 3 | **5** | 5.0 |
| `below_floor` | 1 | **3** | 2.5 |
| `gate_rejected` | **6** | **2** | 2.5 |

against a set that is 50 / 25 / 25. That particular draw was ~2% likely — **but the
mechanism carried no guarantee against it**, which is the defect; the draw is only how it
was noticed. **Six of ten rows would have been postings the pipeline threw away** —
*"Senior Mechanical Engineer, Systems Integration"*, *"Branch Operations Coordinator
Borough Park"* — on which every labeller answers Axis B "no" and agreement is
near-unanimous **for free**. **That is a ceiling measured on the easy cases**, which is the
same failure as evaluating on the population the pipeline already chose, one level in.
CLAUDE.md names the outer version of it; this was the inner one.

Fixed by proportional allocation across strata, largest remainder, at
`evals/labels.py:665-679`, with the rationale and these numbers at `:648-664`. The redrawn
block reads as real judgement calls — **AI Engineer at Brex, Legal Engineer at Harvey,
Operations Analyst at NYC DYCD** — which is what an agreement ceiling has to be measured on
to mean anything.

**Two things about the redraw that are counterintuitive and must be stated precisely:**

- **The pin did NOT move.** `sha256(sorted job_id)` is still
  `afb2d58f5d369dfd03ad9237a8b16396cea31b838a67343f51aceecf70cd1763`. **Set membership is
  unchanged**; only which ten of the 200 rows are marked `overlap` moved. Every digest and
  every stratum count already written in this file is still correct — verified by
  recomputing both from the committed fixture.
- **The redraw was safe only because `eval_labels` was empty, and it CHECKED that rather
  than assuming it.** Redrawing a set somebody has already labelled silently reassigns what
  their answers were answers to. The check is the difference between a correction and a
  data loss, and it cost nothing to make.

### The methodological finding, and it is the reusable one

The first version of fix 3 rotated by `sha256(labeller_id)` — stateless, no rank to
derive, obviously adequate. The plan asserted it would give 110 distinct postings, from
the formula above.

**Verified against the drawn set rather than against the formula: 84.**

| rotation | distinct postings (190-row tail, ten labellers, twenty each) |
|---|---:|
| `sha256(labeller_id)` | **84** |
| rank-spaced by `2**64/phi` | **110** — the ideal |

Hashing spreads people at *random*, and random windows **collide**; the formula assumes
*disjoint* windows. It is the birthday problem, and here it cost **26 postings and the
Definition of done** — 84 misses "≥100", 110 meets it, at the same twenty-minute sitting.
The reasoning is recorded in the code that earned it — `tail_offset()` at
`evals/labels.py:869`, both numbers in its docstring at `:874-883`, and `_PHI64` at `:866`
under a comment (`:859-865`) explaining that the constant is there for its
low-discrepancy property and not as a hash. **That comment is the guard**: without it,
`2**64/phi` reads like an arbitrary magic number and the obvious "simplification" back to a
hash costs 26 postings silently.

**An idealised formula is not a measurement.** This file already says to verify a plan's
claims *about the code* before implementing them (§ *how this run works*). This is the
same rule one level up: **verify a plan's claims about its own arithmetic against the
artifact, not against the algebra.** The algebra was not wrong; it was describing a
different mechanism from the one being built.

**And the sharper version, which defect 4 paid for: A TOTAL IS NOT A COMPOSITION.** The
drawn set's strata totals were **exactly right** — 100 / 50 / 50, checked, committed,
reported. The ten-row block *inside* them was 6/3/1 against 2.5/5/2.5, and the totals could
not see it, because every marginal a check was being run against still summed correctly.
**Three of this session's four defects were found by measuring an artifact that had already
passed its own checks** — the gate misclassification by counting `surfaced` two ways, the
84-vs-110 by counting distinct postings instead of trusting the formula, and the overlap
skew by reading the ten rows rather than their totals. **The check that finds this class of
defect is always the same one: disaggregate, and look at what is actually in the bucket.**

### What landed

- **The three label tables now exist in the live database.** `eval_label_sets`,
  `eval_label_items`, `eval_labels`, created by `python3 -m evals label init-schema` run as
  `jobs_pipeline`, which holds CREATE on `public`. **This file was right that they did not
  exist.** `jobs_web` was then granted SELECT / SELECT+INSERT / sequence USAGE per
  `labels.WEB_PRIVILEGES` (`evals/labels.py:240`), and `labels.verify_schema()` (`:353`)
  passes.
- **The set is drawn, redrawn and pinned: `pursuit-v1`.** n=200, seed 0, overlap 10,
  profile `pursuit`, drawn against the cohort gate over the full window. **surfaced 100 /
  below_floor 50 / gate_rejected 50**, nine platforms with none above 54.
  `sha256(sorted job_id)` =
  `afb2d58f5d369dfd03ad9237a8b16396cea31b838a67343f51aceecf70cd1763`, committed at
  `backend/evals/fixtures/labelset-pursuit-v1.jsonl`. **The redraw for defect 4 did not
  change any of those numbers** — it changed which ten rows are marked `overlap`, from
  3/1/6 to **5 surfaced / 3 below_floor / 2 gate_rejected**. All of it re-verified from the
  committed fixture rather than from the tool that wrote it.
- **Six rows were excluded from `below_floor`, deliberately.** SQL called them below-floor
  because they have no `job_matches` row; `score_job()` recomputes them **at or above the
  floor**, which means `match.py` had not caught up with their facts. "No `job_matches`
  row" has two causes and they are indistinguishable in SQL. Keeping them would have
  contaminated a recall stratum with a measurement of the scheduler.
- **`eval_labels` is EMPTY, and `pursuit-v1` is an eval set.** CLAUDE.md: pinned by sorted
  `job_id`, **never train on it, never recycle it.** Its emptiness is also what made the
  defect-4 redraw safe, and **that window is now closed** — once a labeller has answered
  anything, the set cannot be redrawn without invalidating their answers.
- **The repo owner set overlap 10 and a budget of ~20 items per labeller.** That **breaks
  one line of task 29's Definition of done** — it asks for 20 postings overlapped and gets
  10 — and buys **110 distinct postings** in the twenty-minute sitting the task specifies.
  Recorded rather than quietly met. **At the DoD's 5-labeller fallback, ≥100 distinct needs
  ~28 items each.** That is the number a smaller turnout will need, and it is worth knowing
  before the session rather than at 7pm on the night. **Both figures were re-verified on the
  redrawn set**, not carried over from the first one.

### Two of this file's own facts were wrong, and both were load-bearing

**`fastapi` IS installed.** This file said it was not — at `:218-220` and `:927-930`
before this update shifted them, now struck through in § *state at handoff* and in
§ *findings later tasks must not inherit* (cited by section, because inserting this one
moved both, which is the drift this file already warns about) — and said that five webapp
modules therefore always fail to import. It is installed in
**`backend/webapp/.venv`** — fastapi 0.140.0, plus uvicorn, starlette, pydantic and httpx
— and `.venv/bin/python -m unittest discover -s tests -t .` under `backend/webapp/` reports
**55 tests, OK** (re-run 2026-07-29 while writing this). **`backend/webapp/requirements.txt`
is a SEPARATE file from `backend/requirements.txt`** and lists exactly those five packages;
its own header records that the venv sets `include-system-site-packages = false`, so
"anything missing here is missing at runtime and nowhere else". **The "five modules fail to
import" observation was made with system python** — a true statement about the wrong
interpreter, and `backend/requirements.txt` being `psycopg[binary]` alone is what made it
look confirmed.

**The consequence is the part that matters: serving `/v1/label` needs no install and no
code.** The route already exists — `backend/webapp/label.py:218` (the form), `:256`
(submit), `:311` (progress) — wired at `backend/webapp/app.py:91`, server-rendered HTML,
and already blind to `fit_score`. **Every estimate in this file that priced "get the form
served" as an install plus task 33's territory was pricing work that is done.**

**`tests/test_labels.py:423` does not forbid mock rows in `eval_labels`.** This file cites
it for that twice. Open the line. **Today it reads**

```
                _label(job, "role_archetype", "backend", "alice", round_no=1),
```

— a fixture row inside `test_the_two_ceilings_are_different_quantities` (`:416`), which is
about intra- versus inter-annotator agreement being different quantities. It says nothing
about `source = 'mock'`, and it never did: **checked twice within one day it resolved to
two different lines, neither of them a mock assertion**, because that file was being edited
underneath the citation. Quote the text, not just the number.

The real containment is **`backend/evals/mock_corpus.py:3-6`** — the module docstring, and
it is the binding statement: *"Nothing in this module may ever reach `eval_labels`."* It is
pinned by **`backend/tests/test_mock_corpus.py:939`**
(`test_the_module_says_plainly_that_it_is_not_a_label`), which asserts the caveat travels
with the module, and backed by two structural tests: **`:919`** — no module under `ingest/`
references it — and **`:930`** — no step in `run-daily.py`'s `STEPS` does either. Those two
are the ones that matter, because `ingest/` is the only path to the production `jobs`
table. **And `pool_query()` has no platform filter of any kind**, so nothing downstream
stops a `platform = 'mock'` row being sampled if one ever existed.

**This is not a live risk.** The `jobs` table carries nine platforms and none of them is
`mock`; nothing has ever written one. So the conclusion — *"nothing from that corpus has
ever reached the database"* — **stands, for a different reason than the one given.** The
citation was wrong and the containment is real and lives somewhere else. That is exactly
the failure mode the "cite `file:line`, then re-read the line" rule exists for, and it
survived two sessions inside the rule.

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

## READ THIS FIRST: the gate fix LANDED, and what it did not buy

**Done 2026-07-29, four commits: `4eefb7e`, `e8f3b72`, `9dab9e6`, plus a database write.**
Step 0 is closed. What follows is the record, not a plan.

| metric | before | after |
|---|---|---|
| mock gate recall | 14/29 = 48.3% [31.4–65.6] | **26/29 = 89.7% [73.6–96.4]** |
| mock gate precision | 58.3% | **72.2%** |
| mock false positives | 10 ids | **the same 10 ids, unchanged** |
| live tier ≤2, open | 869 (t1 450 / t2 419) | **880 (t1 456 / t2 424)** |
| `extract.remaining` | 2 | **13** |
| suite | 1030 | **1058** |

**Say it the long way wherever it is quoted: "48.3% → 89.7% *on the mock corpus*."** That
corpus was built to contain the failure mode it measures. It is not a claim about the
pipeline's recall on real postings, and nothing here reduces task 29 by one posting.

**What the defect was.** The gate is conjunctive — one AI term **and** one entry-level term
in the *same field* (`migrate_pursuit_profile.py:216,229`). Task 10 built a
description-first gate and handed it a **title** vocabulary: `associate, coordinator,
assistant, specialist, analyst`. A description does not restate its own title's seniority
noun, so the AI half matched and the entry half did not. 14 of the 15 lost postings failed
on that one group.

**What was done.** The gate moved out of a dict literal inside a migration that refuses to
run and into `backend/config/pursuit-relevance.json` (a no-op, proven by byte-identical
compiled SQL). `description_include`'s entry group became a **strict superset** of the
title group — the same eleven nouns byte-for-byte, plus three phrases — so the title path
*cannot* change and the description path *can only gain*. `\ycustomer success\y` was
narrowed to four manager-and-above terms rather than removed.

### The four phrase families that must stay out, and why the harness will tell you otherwise

Compiled through `relevance.tier_sql` against 13,447 live open rows:

| family | live rows admitted | mock cost |
|---|---:|---|
| `we provide/offer … training` | **+17** | zero |
| `we (will) train` | **+5** | zero |
| `preferred but not required` | **+5** | zero |
| `experience … preferred / is a plus` | **+123** | zero |

They admit `Software Engineer, RL Training Infra | OpenAI`, `Full-Stack Software Engineer,
Reinforcement Learning | Anthropic`, `Product Manager, Gen AI | Scale AI`. **`\ywe train\y`
matched OpenAI's *"we train models"*.**

**On the mock corpus all four measure as FREE**, because every intended-bad mock posting
carrying that phrasing has no AI vocabulary at all, so the conjunction rejects it on the
other half. That is a property of a corpus written to a specification. Adding them takes
mock recall to 100% at **~136 live junk rows**. Refused.
`backend/tests/test_pursuit_gate.py` carries a **sentinel** asserting their absence with
these counts in its docstring. **If the harness tells you they are free, that is the
harness's limitation, not a discovery.**

**The general rule this earned:** a synthetic corpus can bound *recall* but cannot price
*precision*, because its negatives were written by whoever wrote its positives.

### Read the size of it honestly

**+11 postings on an 869-row pool is +1.3%.** It does not meaningfully change what task
29's labellers see and it moves GATE 2's ≥200/day question **not at all**. Doing it first
was still right — the defect was real, the fix was cheap, and a labelling session run
through a knowingly-broken gate is wasted — but do not read a recovery into it that it
does not deliver.

The 11 new rows were hand-checked as a **census, not a sample**: ~7 on-target, 1 clear
false positive (`Research Engineer, Interpretability | Anthropic`, which really does say
"no research experience is required"), 3 ambiguous. **~64% strict against the incumbent
gate's 10.0%** (`migrate_pursuit_profile.py:166-167`) — the rows added are better than the
rows already in. The extraction backlog is 11 calls, ~$0.004, drained on the first nightly.

**Three mock false negatives remain — mock_016, mock_017, mock_018 — and they are
unreachable on purpose.** Only the rejected families recover them.

### What step 0 got wrong about the code, found by verifying it before implementing

- **`AI_VOCAB` had exactly ONE copy**, not two. Step 0 required a test that "the two copies
  are equal", which could not fail. It is now meaningful *because* the JSON move created
  two literals — the test is kept and its docstring says so.
- **`migrate_pursuit_profile.py` refuses to run before it checks `--apply`**, so even a dry
  run exits 1. It was already retired as a write path; that is what made the JSON move
  coherent. It still self-consumes `COHORT_RELEVANCE` at four sites, so the symbol was kept
  as a loader, not deleted.
- **`relevance.load()` merges over `DISABLED`, not over `config/relevance.json`**
  (`relevance.py:88-90`). **A per-profile gate must be complete, not a patch** — an omitted
  key goes permissive, it does not inherit.
- **`profiles.upsert` stores NULL for a falsy `relevance_cfg`** (`profiles.py:207`). An
  empty dict silently reverts `pursuit` to the shared author gate. The post-write md5 is
  what catches it.
- **`--force-placeholders` is not a flag on `migrate_profiles.py`** — it is on
  `migrate_pursuit_profile.py:462-465`. Step 0 warned about the wrong script.
- **The module docstring at `:71-78` pointed at nothing missing.** `migrate_profiles.py`,
  `config/pursuit-persona.json` and `config/pursuit-criteria.json` all exist, as do all six
  flags it names.
- Paths: **`relevance.py` is `backend/relevance.py`, not under `lib/`**; there is **no
  repo-root `config/`**; `extract._eligible_sql` is `:541-579`, not `:397`; tier assignment
  is `relevance.py:297-299` and `tier <= max_tier` is `:331`.

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

**Branch `webapp-service`, suite green at 1070 tests** (task files say 263, earlier
handoffs 782, 837, 878, 1030 and 1058; **1070 is the floor now**).
**The whole suite passes** — `python3 -m unittest discover -s backend/tests` from
the repo root. Working tree is clean apart from untracked `scripts/`, which
predates this run and is not ours.

**On that number: it was 1067, then 1068, then 1070 across a single afternoon** — the
implementing session's report, a re-run an hour later, and a re-run after `90170d1` added
the overlap-stratification tests. All three were correct when taken. This file already
records that test counts drift under concurrent agents (§ *how this run works*); **1070 is
what a re-run reported as this paragraph was written, and it is the floor because it is the
largest.** Re-run before quoting it, and do not treat a number quoted in a handoff as a
number you have measured.

~~`backend/webapp/tests/` is a separate matter: **`fastapi` is not installed here**, so five
modules fail to import and always have.~~ **WRONG, corrected 2026-07-29.** `fastapi`
**is** installed, in **`backend/webapp/.venv`**, which is a separate environment with a
separate `requirements.txt`. Under it, `backend/webapp/` reports **55 tests, OK**. The
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

**Nothing is half-written and nothing is waiting on a reply.** Step 0 is implemented,
committed and written to the database, and so are task 29's four sampler fixes and its
drawn set; the docs were rolled forward in the same session each time. The working tree is
clean apart from untracked `scripts/`, which predates this run and is not ours. **The next
session starts from a finished state**, not from a handover — and for task 29 it starts
from a finished state that is waiting on the repo owner, not on an implementer.

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
  the route exists at `backend/webapp/label.py:218/:256/:311`, wired at
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

**What task 29 is blocked on now, and it is only two things, both the repo owner's:**

1. **Google OAuth credentials.** `GOOGLE_CLIENT_ID` and `GOOGLE_CLIENT_SECRET` are empty
   strings in `backend/webapp/.env`, so `/v1/auth/login` returns **503**
   (`webapp/auth.py:235-239`). And `FRONTEND_ORIGIN` is `http://localhost:5173`: it must
   point at the origin the service is actually served from, or **sign-in succeeds and lands
   nowhere** — the post-login redirect is built from it (`auth.py:359-360`). **There is no
   auth bypass anywhere in `webapp/`, and that is deliberate.** Do not add one to get a
   labelling session started.
2. **Ten Builders, each with a row**: `manage_app_users.py add --email ... --profile
   pursuit`. **Note the two-allowlist trap**: while the consent screen is unverified, an
   address must be in the Google console's **Test users** list *and* in `app_users`, and
   **only one of those two failures produces an error message from this service**
   (`backend/webapp/README.md:149-151`). Also note that the **single existing `app_users`
   row is on profile `tech`**, which is inactive — it is not a working example of a cohort
   labeller.

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
  `backend/webapp/label.py:218/:256/:311`, wired at `webapp/app.py:91`, server-rendered and
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
that an agent *could* do: the schema, the sampler and the drawn set. **What is left of 29
is two asks of the repo owner** — OAuth credentials and ten Builders. Everything else in
this list needs credentials (15, 20) or a re-scope (21).

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

   **Do not redraw this set.** It can only be redrawn while `eval_labels` is empty, and
   the first submitted label closes that window.

   **What is left is two asks of the repo owner and nothing else:**

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
   `backend/webapp/.venv` and the route exists at `backend/webapp/label.py:218/:256/:311`,
   wired at `webapp/app.py:91`. This item used to say otherwise and used to route through
   task 33; it does not.

   **Budget, decided by the repo owner: overlap 10, ~20 items each.** That breaks one DoD
   line (20 overlapped → 10) and buys **110 distinct postings** at ten labellers in a
   twenty-minute sitting. **At the DoD's 5-labeller fallback, ≥100 distinct needs ~28 items
   each** — know that before the night, not during it.

   **Two specific questions are waiting on it**: task 08 asked whether the ops
   shortfall is the title probe over-counting or the extractor under-applying; task
   13 asks whether its four floor misses — postings at `ai_involvement = 'none'`
   whose employers are AI companies — are the weights being wrong or being right.

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

---
kind: record
written: 2026-07-31
generator: none
---

# Task 29's "two mechanical minutes" were four defects

> **Archived from `docs/tasks/refactor/HANDOFF.md` on 2026-07-31**, when that file was split.
>
> **What it is:** Recorded 2026-07-29. Four defects in `labels.sample()` found before the 200-row set was drawn, plus a fifth found after it was pinned. All fixed; the set is drawn and permanent. Nothing here is outstanding.
>
> Moved, not deleted. `git log --follow` on this path reaches the original text, and a stub
> and link remain where this section was.

---

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
code.** The route already exists — `backend/webapp/label.py:241` (the form), `:296`
(submit), `:364` (progress); these read `:218`/`:256`/`:311` until the round-2 path landed
on 2026-07-30 — wired at `backend/webapp/app.py:91`, server-rendered HTML,
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

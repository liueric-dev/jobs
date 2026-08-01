---
kind: record
written: 2026-08-01
generator: none
---

# State at handoff, and what tasks 08, 12 and 19 changed

> **Archived from `docs/tasks/refactor/HANDOFF.md` on 2026-08-01**, by task 44, which split
> that file's two lifecycles apart: a `rolling` entry point sitting on a frozen session
> narrative, which `DOCS-POLICY.md` rule 1 has no single name for.
>
> **What it is:** the run's state as of 2026-07-31 — dated suite readings, the drift table
> that is the evidence for `DOCS-POLICY.md` rule 3, the thirty-row commit table — and the
> findings tasks 08, 12 and 19 landed on 2026-07-28. **Every number here is a dated reading,
> not a current figure.** [`AUDIT.md`](../tasks/refactor/AUDIT.md) owns the current suite
> counts and, per rule 3, states neither: it names the command that prints them.
>
> Moved, not deleted, and moved verbatim — the struck-and-kept sequences *are* the record of
> the drift, so rewriting a cell would destroy the thing being demonstrated (rule 4).
> `git log --follow` on this path reaches the original text, and a stub and link remain
> where each section was.

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
| main | `python3 -m unittest discover -s backend/tests` (repo root, system `python3`) | 1107 | 1160 | `Ran 1166 tests` … `OK` | 1166, `OK` | **`Ran 1171 tests` … `OK`** — for the current figure see [`AUDIT.md`](../tasks/refactor/AUDIT.md) |
| webapp | `.venv/bin/python -m unittest discover -s tests -t .` (from `backend/webapp/`) | 55 | 61 | `Ran 75 tests` … `OK` | **93, `OK`** | untouched — for the current figure see [`AUDIT.md`](../tasks/refactor/AUDIT.md) |

> **Every number in this table is a DATED READING, not a current figure**, and that is the
> only reason they are still here: the table *is* the evidence of the drift the section
> argues about, so rewriting the cells would destroy the thing being demonstrated
> (`DOCS-POLICY.md` rule 4). **[`AUDIT.md`](../tasks/refactor/AUDIT.md) owns both current counts, and per rule
> 3 it does not state either — it names the command that prints them.** Marked 2026-08-01,
> task 40, at task 38's request.

**The fifth column is 2026-07-31 and is the first time one of these was quoted and then
held.** The main suite reproduced exactly; the webapp suite grew by 18 — `prior_domain`
added the vocabulary, the generated CHECK, the CLI-vs-database agreement, and the join.
Same direction as every other movement in this table: **the suites grew and nothing
broke.**

**The sixth column is later on 2026-07-31.** 1166 → **1171**: five tests in
`backend/tests/test_label_findings.py`, covering the break-exclusion threshold, the
warm-up split, and the Wilson-interval formatting. The webapp suite was not touched by this
session and is unchanged. **Ninth instance of the same drift, and the same direction
again.**

**Task 34 should know that `CLAUDE.md` still says *"It was at 263 tests; it should not go
down."*** The measured figure is **1171**. That instruction is stale by roughly 900 and any
agent following it literally is checking against a number nine times too small to catch a
regression.

**Both moved in the safe direction: the suites GREW and nothing broke.** 1107 and 55 were
each correct when they were written — this is drift, not a regression, and it is now the
sixth and seventh instance of it recorded in this file. ~~**1166 and 75 are the floors
now.**~~ ~~**1171 and 93 are the floors now** (2026-07-31).~~ **A floor typed into prose is
the drift this section is about, one level up — [`AUDIT.md`](../tasks/refactor/AUDIT.md) owns both, and the
floor is whatever the two commands print today.**
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
| 29 | **the per-posting rate RE-DERIVED at n=29 — the 154 s reading was a warm-up curve, and the correction is CHEAPER** | this session |
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

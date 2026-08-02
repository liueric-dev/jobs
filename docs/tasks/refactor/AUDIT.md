---
kind: contract
written: 2026-07-31
generator: none
---

# AUDIT — the state of the refactor, and where every claim comes from

**Written 2026-07-31 (task 34).** One page. It **indexes**; it does not restate. Anything
below that looks like a fact carries the instrument that produced it, and re-running that
instrument is the intended way to check this file rather than trusting it.

> **This file must not become an eighth "READ THIS FIRST".** `HANDOFF.md` grew to 3,481
> lines by answering that temptation seven times. If something here needs a paragraph, it
> belongs in the document that owns it and this file gets a link.

## What the system is

A job-discovery pipeline being retargeted from one software engineer's search to the
Pursuit AI-Native cohort — ~30 Builders, entry-level, AI-adjacent, all industries, NYC.

Four stages, `relevance.py` → `extract.py` → `match.py` → `score.py`. Relevance and match
are free arithmetic; extract and score cost LLM calls. `job_facts` is shared across
profiles and scores are per profile, which is the property that makes cost flat in users.
`match_score` orders the list and `fit_score` only annotates it — sorting by `fit_score`
would put an LLM call on the critical path for every posting.

The architecture invariants are in [`../../../.claude/CLAUDE.md`](../../../.claude/CLAUDE.md)
and are the thing to read before changing any of the above.

## The four documents, and what each is for

| document | question it answers | lifecycle |
|---|---|---|
| [`README.md`](README.md) | *what are the 35 tasks and which are done?* | the ordered index; one row per task |
| [`HANDOFF.md`](HANDOFF.md) | *what should I do next, and what must I not break?* | rolling; finished sections move to [`../../archive/`](../../archive/) |
| [`DECISIONS.md`](DECISIONS.md) | *why was this chosen, and what was rejected?* | append-only |
| [`CLAUDE_UPDATES.md`](CLAUDE_UPDATES.md) | *what happened, session by session?* | append-only run log |

The convention is that all four move in the same commit as the code. **It has failed
once**: `CLAUDE_UPDATES.md` silently stopped being written for four sessions, and nothing
was red, because a document that stops being written looks exactly like a document with
nothing to say.

**The lifecycle rules for these four, and for every other document in the tree, are now in
[`../../DOCS-POLICY.md`](../../DOCS-POLICY.md)** (`DEC-66`, 2026-08-01). Each of the four
is one of its five declared kinds — `README.md` and this file are `contract`, `HANDOFF.md`
is `rolling`, `DECISIONS.md` is `rationale`, `CLAUDE_UPDATES.md` is `record`. **This file
is the owner of the figures below under policy rule 2**: they appear here with their
instrument, and every other document cites this one rather than restating them.

## Current measured state, with the instrument for each

| | value | instrument |
|---|---|---|
| tasks done or dropped | ~~20 of 35~~ **read the status column** — the count moved five times on 2026-08-01 alone, and two tasks were added | `grep -cE '\| \*{0,2}done\*{0,2} \|' docs/tasks/refactor/README.md`, against the same for `todo` |
| test suite, main | ~~**green.**~~ ~~**RED, one failure, and it is deliberate**~~ **GREEN again 2026-08-02 — tasks 45 and 46 landed and cleared the deliberate failure (`2586bb2`).** The count is whatever `Ran N tests` prints — see the note under this table | `cd backend && python3 -m unittest discover -s tests` |
| test suite, webapp | **green.** Same: run it, read the line | `cd backend/webapp && .venv/bin/python -m unittest discover -s tests` |
| test suite, **api** | **green, and NEW 2026-08-02** — `backend/api/` had zero tests until task 24. It is a **third** suite, not part of the first, because `backend/api/.venv/pyvenv.cfg` sets `include-system-site-packages = false` and system `python3` cannot import `fastapi` at all (`DEC-81`) | `cd backend/api && .venv/bin/python -m unittest discover -s tests` |
| per-source volume floors | **wired, and firing correctly on no data** — it reports `no_history` as a *finding* rather than exiting clean, which is the disposition the whole check exists for. Exits 1 on findings; `jobs-volume-check.service` carries `OnFailure=` | `python3 backend/tools/volume-check.py`, and `--self-test` |
| broken doc links | **0** | `python3 backend/tools/audit-doc-links.py` |
| documentation policy | ~~**all six checks 0**~~ ~~**C1 2, C4 2 — 4 findings, red on purpose**~~ ~~**all six checks 0 again, exit 0, on the widened set**~~ **SEVEN checks as of 2026-08-02, all 0, exit 0.** Tasks [45](tranche_seven/45-declare-kind-on-the-roots.md) and [46](tranche_seven/46-sentence-scope-the-c4-lookahead.md) closed the four findings; [47](tranche_eight/47-split-the-entry-point.md) added **C7**, a size budget on `rolling` documents, and **it is the only check here that landed green** — the six before it measure consistency and none measured volume, which is how `HANDOFF.md` regrew four fifths of task 44's archival in thirty-six hours with all six reporting zero. **The baseline was never grown and is still empty** | `python3 backend/tools/audit-docs.py`; wired into `backend/tests/test_docs_policy.py` |
| defect register | ~~45 entries, `D01`–`D45`~~ ~~**48 entries — `D01`–`D45` and `D66`–`D68`**~~ ~~**`D01`–`D45` and `D66`–`D72`**~~ **`D01`–`D45` and `D66`–`D74`**; `D46`–`D65` are burnt, re-prefixed to `DEC-` by task 39. **No count is typed here** — the register owns it, per rule 2. Next free `D75` | [`../../ingest/DEFECTS.md`](../../ingest/DEFECTS.md) |
| decision register | `DEC-46`–~~`DEC-93`~~ **`DEC-94`**. Next free `DEC-95`; **thirteen were added on 2026-08-02** by four parallel streams, **and one more by the second such session the same day** | [`DECISIONS.md`](DECISIONS.md) |
| human labels | ~~186 rows / 31 postings / **one** labeller~~ **271 rows / 36 postings / two labellers**, round 1 (2026-08-02) | `python3 backend/tools/label-findings.py` |
| model vs human | **measured 2026-08-02, and the ceiling is below the floor on all five fields** — owned by [`../../labelling-report-2026-08-02.md`](../../labelling-report-2026-08-02.md), which carries the table and the reasons not to tune on it | the command in that document; every input is committed |
| labelling rate | 93 s median (n=29) | `python3 backend/tools/label-findings.py --timing` |
| model self-consistency | **three named metrics** — [§ *The three self-consistency metrics*](#the-three-self-consistency-metrics) below owns them | task 06; the command in that section |
| cohort corpus | 940 rows at `facts_version = 3`; `role_archetype = other` on 31.3% | `python3 backend/tools/derive-role-tracks.py --archetypes` |
| `role_track` at the read edge | **landed 2026-08-02 (`DEC-94`)** — it had been on `job_facts` since task 11 and in no response body. 134 of 166 visible `pursuit` rows carry a track, all nine values present. **Measure through the view, never the table**: `jobs_app` inner-joins `job_matches` and applies four completeness predicates, so what reaches a Builder is a strict subset of `job_facts`, and `docs/facts-v3-diff.md` gives a corpus statistic here a shelf life of one night | the query in [`tranche_six/30-within-track-ordering.md`](tranche_six/30-within-track-ordering.md); `SELECT v.profile, count(*), count(f.role_track), count(DISTINCT f.role_track) FROM jobs_app v JOIN job_facts f ON f.job_id = v.id GROUP BY 1` |

**No test count is written above, deliberately.** It was written as three different values in
three live documents on 2026-08-01 and none of them was what the runner printed; each was
correct on the day it was typed. `DOCS-POLICY.md` rule 3 — *a number a script can produce is
never typed into prose* — and this table records the command instead. **Your floor is the
suite's own reading before you changed anything**, not a number anybody wrote down.

**Two figures that circulate and are dead:** `seniority_level` 76% / `ai_involvement` 94%
are the provisional **n=17** measurements, superseded by the n=115 `agree2` figures below.
And the labelling budget was quoted at 154 s/posting for a day; that sample sat entirely
inside a warm-up curve.

## The three self-consistency metrics

`deepseek-v4-flash`'s agreement with itself at temperature 0 circulates in this repo as
**three different percentages, and every one of them is correct.** One *word* is overloaded,
which is what makes two correct numbers look like a contradiction. This section owns all
three under policy rule 2; `DOCS-POLICY.md` rule 3's corollary is the reason it names them:
*a number written without the metric beside it is not a measurement, it is a rumour with a
decimal point.*

The instrument is one committed file and no LLM call — nothing here needs re-measuring:

```bash
python3 -c "
import json; d=json.load(open('docs/ingestion_tests/selfcheck-n120-2026-07-28.json'))
o=d['fields']['ai_involvement']['overall']
print({k: round(v,4) for k,v in o.items() if k in ('agree2','pairwise','unanimous')})
print('hn:', {k: round(v,4) for k,v in
      d['fields']['ai_involvement']['by_platform']['hn_whoishiring'].items()
      if k in ('agree2','pairwise')})"
```

| metric | what it is | `ai_involvement`, n=115 | `hn_whoishiring`, n=21 |
|---|---|---|---|
| `agree2` | repeat 1 against repeat 2 — the two-run protocol, and the only one comparable to the superseded n=17 study | **94.8%** [89.1–97.6] | **85.7%** |
| `pairwise` | the mean over all three pairs of runs | **90.7%** | **77.8%** |
| `unanimous` | all three runs identical | **87.0%** [79.6–91.9] | — |

`seniority_level` on the same run, same n: `agree2` **85.2%** [77.6–90.6], `pairwise` 84.9%,
`unanimous` 77.4%. Intervals are 95% Wilson. The per-field table for all sixteen fields, and
the gate decision task 06 took on it, are in
[`../../ingestion_tests/README.md`](../../ingestion_tests/README.md), which holds the
instrument itself.

**Every other document cites this section *and names its metric*** — `94.8% (agree2)` — rather
than restating the number bare. `DECISIONS.md` is append-only and its three earlier entries are
left exactly as written: `DEC-71` records which metric each of them meant.

**The decomposition matters more than the headline.** 8 of 115 records (7.0%, [3.6–13.1])
changed whether the job is in the AI opportunity space *at all* between runs. That is the
number the product turns on, and 94.8% hides it —
[`../../ingestion_tests/README.md`](../../ingestion_tests/README.md) § *What the disagreements
are, which the rate does not tell you*.

## What is open

> ~~**Blocking everything downstream: a second labeller for about twenty minutes.** `evals
> label report` exits 2 by design while there is one labeller, because with one there is no
> inter-annotator ceiling to denominate a model score against — and `consensus()` promotes a
> majority of size one with nothing recording that it was of size one. The ten `overlap`
> rows are already answered on the owner's side, so a second person's ten are the *last*
> input needed. This is the owner's to arrange; no session can do it. It gates tasks 30, 13's
> weights, and 12's next bump.~~
>
> **Struck 2026-08-02: it happened.** A second labeller answered the overlap block, `evals
> label report` printed at exit 0, and the result is
> [`../../labelling-report-2026-08-02.md`](../../labelling-report-2026-08-02.md).

**What blocks now is not what that paragraph predicted.** The report exists and **still
cannot be tuned on** — the ceiling it produced is *below* the floor on all five fields and
rests on 6–10 items each. Tasks 30, 13's weights and 12's next bump are gated on a **usable**
ceiling, not on a report. Three things would produce one, and only the third is a session's
to do:

1. **More overlap — more labellers on the *same* ten rows.** Not more postings: 25 of the 36
   labelled postings carry one labeller and add nothing to the ceiling. The owner's to
   arrange.
2. **Round 2**, the same labeller re-answering the overlap block after the form's 7-day delay
   (~2026-08-09), for the intra-annotator ceiling. The owner's to arrange.
3. ~~**An `evals selfcheck` at n=120 that covers `role_track`.** The committed
   `docs/ingestion_tests/selfcheck-n120-2026-07-28.json` predates task 11 adding the field, so
   the report cannot be run against it at all and a per-corpus selfcheck was substituted
   (`DEC-75`). This one is a session's to run and costs LLM calls, not people.~~
   **DONE 2026-08-02 — [`../../ingestion_tests/selfcheck-n120-2026-08-02.md`](../../ingestion_tests/selfcheck-n120-2026-08-02.md),
   which owns `role_track`'s figures.** `agree2` **88.7%** [81.6–93.3] at n=115 — the artifact
   is named `n120` because that was the ask; 5 of 120 were skipped before any call.
   **It did not unblock task 30, and the decomposition is why.** 13 of 115 (**11.3%**,
   [6.7–18.4]) changed whether the posting belongs to *any* track between runs, against only
   6.1% moving between two named tracks: nearly two thirds of the instability sits on the
   classifiable/not boundary, which is the boundary a "group by `role_track`" display turns
   on. **It is NOT the same quantity as the humans' 15-of-36 `no_track_fits`** — 42% is a
   prevalence, 11.3% an instability, and neither bounds the other. A model answering `null`
   always would score 100% and 0%. So items 1 and 2 above are still what a usable ceiling
   needs, and both are the owner's.

~~**Not blocked, not started:** the product/API surface — tasks 24–28, 31, 32.~~
**STARTED 2026-08-01.** ~~**Task 27 is done** (`2687bc0`); 24, 25, 26, 28, 31, 32 remain.~~
**27, 31 and 28 are done, and 26 and 32 are each one screen short — 2026-08-02.** 28 is
`3ad38dd`, 26's backend half is `4c874e7`, 32's client is `681c2a1`. What remains on the
track is **24, 25, 33, and two screens** (26's onboarding, 32's search — and the search one
is blocked on 25, which does not exist in code at all). Its
**2026-08-02, second parallel session: the search screen shipped, so 32 is five of six
surfaces and `Contribute` is the last — and it is `DEC-84`'s ownership question, not
effort.** What remains a session's work on this track is now **nothing**: 24's deploy half,
33's machine half, 32's phone test and login round trip all need a person, an account or a
device. Its
premises were audited on 2026-07-31 and several were stale — **and 27's own dependency line
was one of them**, declaring `Depends on: 26` while 26's Definition of done needs 27's
`visibility` column. The corrections are in the task files themselves and in
[`API-CONTRACT-v1.md`](API-CONTRACT-v1.md), which is a **specification** and not a
description of the shipped API.

**Two things about that track a next session must not re-derive.**

- **The contract's list payload is gated on task 30, which is gated on the labelling
  night.** *"No 0–100 score appears anywhere; `bucket` carries the claim"* cannot be
  honoured while `bucket` does not exist — removing `match_score`, `fit_score` and
  `min_score` first would leave the API unable to express relevance at all. It is a
  **deferral with a named blocker**, recorded as such in the contract, not an open question.
- **`apply` vs `applied` is settled** (`DEC-73`), and `model_version` was replaced by
  `criteria_version` (`DEC-74`) because the former is one of three names
  `.claude/CLAUDE.md` records as planned and never built.

**One open decision from task 27, and it is the owner's.** The impression dedup is keyed
`(profile, job_id)` and not `(profile, job_id, request_id)`, so a second render of the same
list inside 24 hours writes no impression rows — and the `skip` derivation reads
impressions. **Skips are a first-render-per-day signal.** The change is one line; the cost
is changing the documented meaning of *"a list re-render is not new information"*. Recorded
in [`tranche_five/27-event-schema.md`](tranche_five/27-event-schema.md),
[`API-CONTRACT-v1.md`](API-CONTRACT-v1.md) and
[`../../ingest/engagement-events.md`](../../ingest/engagement-events.md).

**Deliberately not done, with reasons recorded:** applying the `revenue_commercial`
archetype (it is a `FACTS_VERSION` bump, and `pursuit-v1` is mid-labelling); re-tuning task
13's weights (only task 29 licenses that); three defects in `DEFECTS.md` (D31 needs a
decision rather than a fix, D33's consumer is task 25, D34 is a live-database DELETE).

**The two most-read files in this repo are not checked by anything, and that is a rule 7 gap
rather than an oversight.** `backend/tools/audit-docs.py` walks `docs/` only — task 36 scoped
it there and said widening was a later call. So `.claude/CLAUDE.md` and the root `README.md`
are **declared reachability roots for C2 and are scanned by no other check**, C4 included.
Both carry figures: `.claude/CLAUDE.md` has the self-consistency pair and the instruction
every session reads about the test suite, and the root `README.md` types a count of the
entry points under `docs/ingest/`. Task 38's Definition of done checks the first of those
with a **`grep` a person has to remember to run**, which `DOCS-POLICY.md` rule 7 says is
exactly one step better than prose — *"a script nobody runs automatically … decays the
moment the person who remembers it stops running it."* ~~Widening `docs_files()` to include
the declared roots is the obvious next check and is not written. Until it is, **a figure in
`.claude/CLAUDE.md` is on the honour system**, and it is the first thing every session reads.~~

> **THE WIDENING LANDED 2026-08-02, RED ON PURPOSE — 4 findings, and one sentence above is
> half-stale.** The scanned set now takes the two declared roots as well as `docs/`, derived
> from `ROOTS` rather than a second list. C2 is deliberately excluded: a root cannot be an
> orphan, since reachability is defined *from* those files.
>
> **The root `README.md` no longer types that count.** Task 37 replaced it with a link to
> `docs/README.md` and left the strike visible at `README.md:25-29`, citing rule 3 by name.
> C4 confirms it — zero findings there. So the live half of the gap was `.claude/CLAUDE.md`
> alone, and had been for a day before this paragraph was read as current.
>
> The 4 findings split cleanly and are [`tranche_seven/45`](tranche_seven/45-declare-kind-on-the-roots.md)
> and [`tranche_seven/46`](tranche_seven/46-sentence-scope-the-c4-lookahead.md):
> **2 real** (neither root declares `kind:`) and **2 false positives where the file is right
> both times** — C4's compliance lookahead is scoped to the physical line, and
> `.claude/CLAUDE.md` is hard-wrapped, so `94.8%` sits one line above the `` `agree2` `` that
> licenses it. The unit of the claim is the sentence; the unit of the check is the line.
> Task 38's design was correct against `docs/`, where no owned figure straddled a wrap.
>
> **Nothing was added to the declared baseline and it is still empty.** ~~The `backend` suite
> is red on `test_findings_are_a_subset_of_the_declared_baseline` until 45 and 46 land~~,
> which is the disposition task 36 took and the reason that test is written to be pruned,
> never grown.
>
> **CLOSED 2026-08-02 by `2586bb2`. All six checks are 0 on the widened set and the suite is
> green.** Both roots declare `kind: contract` (`DEC-76`); C4's compliance lookahead is
> evaluated against the enclosing **sentence**, with struck figures exempt under rule 4
> (`DEC-78`). **Task 46's diagnosis was right about one of its two findings, not both** — the
> second was licensed by the strike, because `main suite test count` is the one row in
> `doc-figures.json` carrying no compliance lookahead at all, so joining the paragraph still
> matched. Two independent fixes clearing disjoint sets. And the first implementation cleared
> a **real** restatement through greedy `[^\n]*` letting a later cell license an earlier one —
> the failure the task warns about, arriving through the fix rather than the bug.

> **THE STATUS-COUNT INSTRUMENT WAS UNDER-REPORTING, found 2026-08-01 by running it.**
> The command in that row was `grep -c '| done |'`, and two rows spell it `| **done** |` for
> emphasis — task 34 and task 27. So the documented instrument reported **29 done** where
> the file holds **31**, and it had been wrong since task 34 landed. Corrected to tolerate
> the emphasis rather than by flattening the two rows, because the rows are not the defect.
>
> **This is the failure this row already exists to prevent, one level up.** The number was
> replaced by a command precisely so it could not go stale — and then the command went
> stale, silently, because nobody ran it. *"Re-derive it"* without checking that the
> derivation still works is the same trust the typed figure asked for. `DOCS-POLICY.md`
> rule 3's *"a number a script can produce is never typed into prose"* does not say the
> script is exempt from being checked.

## How to audit this run in an hour

1. `python3 backend/tools/audit-doc-links.py` — every relative link resolves.
2. Run both suites. Read the `Ran N tests` line, not a static count of `def test_`; every
   test-count figure written before 2026-07-31 was derived by regex, not by a runner.
3. Pick any number in this table and re-run its instrument. **Do not re-quote it** — this
   run has gone stale on at least eight numbers it quoted, and the one instruction that
   reliably decayed into a quotation was *"re-derive it"* without a command attached.
4. Read [`DECISIONS.md`](DECISIONS.md) for anything that looks arbitrary. Most arbitrary-
   looking choices have a measured reason and a rejected alternative recorded beside them.
5. Read [`../../MEASUREMENT-TRAPS.md`](../../MEASUREMENT-TRAPS.md) before believing any
   quality figure, including the ones above. ~~Three of its seven entries~~ **Several of its
   entries — that file owns its own count, per rule 2** were found only *after* the
   conclusions they invalidated had been written down as fact.

## The known weaknesses, stated rather than discovered

- **n=1 on human labels.** Every Axis B figure is one person's preference, and that person
  is a software engineer by background, which is an uncontrolled confound in exactly the
  three postings the recall question turns on.
- **The vocabulary is derived from the wrong corpus.** `ARCHETYPE`'s own first line reads
  *"The original twelve. All software engineering."* Expanding 12 → 26 made `other` worse,
  not better, and the gap is a decision that is proposed and unapplied.
- **Silence is this system's failure mode.** Exhausted keys, blocked scrapers and changed
  endpoints all return zero rows rather than raising. Volume is the alarm; errors are not.
- **Documentation goes stale without going red.** This run's clearest single lesson, and
  the reason task 34 exists. See [`34-documentation-cleanup.md`](34-documentation-cleanup.md)
  for what a pass over it found — including that its own founding premise was false.
  **Task 34 paid this down by hand and it drifted again within a day** — the entry point in
  `HANDOFF.md` still sends every session to do task 34. Phase 9 (tasks 36–42) is the attempt
  to make it *checkable* rather than to pay it down a second time; see
  [`../../DOCS-POLICY.md`](../../DOCS-POLICY.md) rule 7 for the argument, which is that the
  only doc rule that has held here is the one with a script attached.

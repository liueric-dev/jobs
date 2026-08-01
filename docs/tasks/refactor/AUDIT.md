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
| tasks done or dropped | ~~20 of 35~~ **read the status column** — the count moved five times on 2026-08-01 alone, and two tasks were added | `grep -c '| done |' docs/tasks/refactor/README.md`, against `grep -c '| todo |'` |
| test suite, main | **green.** The count is whatever `Ran N tests` prints — see the note under this table | `cd backend && python3 -m unittest discover -s tests` |
| test suite, webapp | **green.** Same: run it, read the line | `cd backend/webapp && .venv/bin/python -m unittest discover -s tests` |
| broken doc links | **0** | `python3 backend/tools/audit-doc-links.py` |
| documentation policy | **all six checks 0**, and the baseline is empty — that emptiness is phase 9's exit gate | `python3 backend/tools/audit-docs.py`; wired into `backend/tests/test_docs_policy.py` |
| defect register | 45 entries, `D01`–`D45` | [`../../ingest/DEFECTS.md`](../../ingest/DEFECTS.md) |
| human labels | 186 rows / 31 postings / **one** labeller | `python3 backend/tools/label-findings.py` |
| labelling rate | 93 s median (n=29) | `python3 backend/tools/label-findings.py --timing` |
| model self-consistency | **three named metrics** — [§ *The three self-consistency metrics*](#the-three-self-consistency-metrics) below owns them | task 06; the command in that section |
| cohort corpus | 940 rows at `facts_version = 3`; `role_archetype = other` on 31.3% | `python3 backend/tools/derive-role-tracks.py --archetypes` |

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

**Blocking everything downstream: a second labeller for about twenty minutes.** `evals
label report` exits 2 by design while there is one labeller, because with one there is no
inter-annotator ceiling to denominate a model score against — and `consensus()` promotes a
majority of size one with nothing recording that it was of size one. The ten `overlap`
rows are already answered on the owner's side, so a second person's ten are the *last*
input needed. This is the owner's to arrange; no session can do it. It gates tasks 30, 13's
weights, and 12's next bump.

**Not blocked, not started:** the product/API surface — tasks 24–28, 31, 32. Its premises
were audited on 2026-07-31 and several were stale; the corrections are in the task files
themselves and in [`API-CONTRACT-v1.md`](API-CONTRACT-v1.md), which is a **specification**
and not a description of the shipped API.

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
moment the person who remembers it stops running it."* Widening `docs_files()` to include
the declared roots is the obvious next check and is not written. Until it is, **a figure in
`.claude/CLAUDE.md` is on the honour system**, and it is the first thing every session reads.

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
   quality figure, including the ones above. Three of its seven entries were found only
   *after* the conclusions they invalidated had been written down as fact.

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

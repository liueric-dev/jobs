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

## Current measured state, with the instrument for each

| | value | instrument |
|---|---|---|
| tasks done or dropped | 20 of 35 | [`README.md`](README.md) status column |
| test suite, main | **1182**, green | `cd backend && python3 -m unittest discover -s tests` |
| test suite, webapp | **93**, green | `cd backend/webapp && .venv/bin/python -m unittest discover -s tests` |
| broken doc links | **0** | `python3 backend/tools/audit-doc-links.py` |
| defect register | 45 entries, `D01`–`D45` | [`../../ingest/DEFECTS.md`](../../ingest/DEFECTS.md) |
| human labels | 186 rows / 31 postings / **one** labeller | `python3 backend/tools/label-findings.py` |
| labelling rate | 93 s median (n=29) | `python3 backend/tools/label-findings.py --timing` |
| model self-consistency | `seniority_level` **85.2%** [77.6–90.6], `ai_involvement` **94.8%** [89.1–97.6], n=115 | task 06; `DECISIONS.md` § *06 — Was 76% real?* |
| cohort corpus | 940 rows at `facts_version = 3`; `role_archetype = other` on 31.3% | `python3 backend/tools/derive-role-tracks.py --archetypes` |

**Two figures that circulate and are dead:** `seniority_level` 76% / `ai_involvement` 94%
are the provisional **n=17** measurements, superseded by the n=115 row above. And the
labelling budget was quoted at 154 s/posting for a day; that sample sat entirely inside a
warm-up curve.

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

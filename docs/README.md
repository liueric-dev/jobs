---
kind: contract
written: 2026-08-01
generator: none
---

# docs/

**Every document in this tree, grouped by what it is for rather than by where it
sits on disk.** One line each, saying the question that document answers.

The five kinds and their lifecycles are [`DOCS-POLICY.md`](DOCS-POLICY.md) rule 1.
The short version: a **contract** says what is true now and a stale line in it is a
defect; **rationale** is append-only and says why; a **record** is frozen at its date
and nobody should try to keep it current; **rolling** is the one document that says
what to do next; a **task** freezes when it reads DONE.

This file is also what `backend/tools/audit-docs.py` check C2 walks from. Reachability
needs a root, and `docs/` had none until this file existed — which is why nothing could
tell an unlinked document from a deliberate one. **Every entry below is a real relative
link, and that is load-bearing, not decoration.**

Per rule 3, nothing here counts anything. To count the documents, run
`find docs -name '*.md' | wc -l`; to see which are unreachable, run
`python3 backend/tools/audit-docs.py --check C2`.

---

## `contract` — what is true of the system now

### Cross-cutting

| document | the question it answers |
|---|---|
| [`DOCS-POLICY.md`](DOCS-POLICY.md) | What is each document for, how long does it stay true, and what retires it? |
| [`MEASUREMENT-TRAPS.md`](MEASUREMENT-TRAPS.md) | What has already invalidated a measurement in this repo, and how do I not repeat it? |
| [`RUNBOOK.md`](RUNBOOK.md) | How does a successor keep this running — restart a service, rotate a key, act on a source that has gone quiet, add an employer, onboard a contributor, and restore from a backup? |
| [`WORKING-METHOD.md`](WORKING-METHOD.md) | How is work verified here — who commits, what is checked before implementing, and what a green suite does not tell you? |
| [`scoring.md`](scoring.md) | What does a score mean, are two of them comparable, and where did every weight come from? ~~Part contract, part dated measurement~~ **split 2026-08-01 by task 43 (`DEC-70`); the measured half is [`scoring-measured-2026-07-27.md`](scoring-measured-2026-07-27.md), below.** |
| [`tasks/refactor/AUDIT.md`](tasks/refactor/AUDIT.md) | What is the state of the run, and which instrument produced each figure? |
| [`tasks/refactor/API-CONTRACT-v1.md`](tasks/refactor/API-CONTRACT-v1.md) | What must `/v1` return for a frontend to be built against it, and how far is the shipped service from that? |

### Per-script reference — what each ingestion and scoring entry point does

| document | the question it answers |
|---|---|
| [`ingest/DEFECTS.md`](ingest/DEFECTS.md) | Every defect found across every ingest path: what it is, how bad, and is it closed? The `D` register. |
| [`ingest/ats.md`](ingest/ats.md) | How does the Greenhouse/Lever/Ashby board pull work, and what does it do when a board changes? |
| [`ingest/builtin-nyc.md`](ingest/builtin-nyc.md) | How is Built In NYC scraped, and what does a card that parses badly do? |
| [`ingest/contributor-api.md`](ingest/contributor-api.md) | How does the contributor work queue claim, submit and store a query's results? |
| [`ingest/engagement-events.md`](ingest/engagement-events.md) | Who writes `job_events`, and what does a row in it mean? |
| [`ingest/extract.md`](ingest/extract.md) | How is one posting turned into `job_facts`, and what happens when the model answers unusably? |
| [`ingest/google-apify.md`](ingest/google-apify.md) | How does the Apify Google Jobs actor path work, and what does it cost per result? |
| [`ingest/google-serpapi.md`](ingest/google-serpapi.md) | How are SerpApi queries picked, claimed and paced against the quota? |
| [`ingest/hn-hiring.md`](ingest/hn-hiring.md) | How is an HN *Who is hiring* thread read into postings, and what is re-fetched after a crash? |
| [`ingest/match.md`](ingest/match.md) | How does `match_score` get computed, and what makes a row demoted or orphaned? |
| [`ingest/nyc-open-data.md`](ingest/nyc-open-data.md) | How does the NYC Open Data jobs feed map onto this schema? |
| [`ingest/score.md`](ingest/score.md) | How does `fit_score` get produced, and what distinguishes a deferral from a failure? |
| [`ingest/weworkremotely.md`](ingest/weworkremotely.md) | How are the WWR category feeds parsed, and what is dropped before the upsert? |
| [`ingest/workday.md`](ingest/workday.md) | How does the Workday CXS pull work, and why is its gate the fragile one? |

### Directory indexes

| document | the question it answers |
|---|---|
| [`tasks/README.md`](tasks/README.md) | What are the five tasks that built `backend/webapp/`? |
| [`tasks/refactor/README.md`](tasks/refactor/README.md) | What is the ordered task list for the Pursuit retarget, and what is done? The task-number register. |
| [`ingestion_tests/README.md`](ingestion_tests/README.md) | What is `backend/evals/` for, and which of its tasks moved into the refactor run? |
| [`archive/README.md`](archive/README.md) | What is in the archive, what superseded each file, and why is nothing deleted? |

## `rationale` — why this was chosen, and what was rejected

| document | the question it answers |
|---|---|
| [`tasks/refactor/DECISIONS.md`](tasks/refactor/DECISIONS.md) | Every choice a task file left open, decided with its rejected alternative beside it. Append-only. The `DEC` register. |

## `rolling` — what to do next

| document | the question it answers |
|---|---|
| [`tasks/refactor/HANDOFF.md`](tasks/refactor/HANDOFF.md) | What should a fresh session do first, and what must it not break? **The only `rolling` document in the tree**, by policy rule 1. |

## `record` — what was measured or what happened, on a date

Frozen. Each carries its date and its method. **None of these is maintained, and
none should be** — a half-updated measurement is worse than an honestly stale one,
because you cannot tell which is current.

### Measurements

| document | the question it answered |
|---|---|
| [`labelling-report-2026-08-02.md`](labelling-report-2026-08-02.md) | What did the first `evals label report` say — how does the model compare to human labels, and between what floor and what ceiling? Task 29's first three-quantity measurement. |
| [`scoring-measured-2026-07-27.md`](scoring-measured-2026-07-27.md) | What did the four stages actually do on 2026-07-27 — the funnel, the two profiles' scales, and what the `staff` fix deleted? The measured half of [`scoring.md`](scoring.md), split out by `DEC-70`. |
| [`pursuit-gate-volume.md`](pursuit-gate-volume.md) | How many postings a day would a widened Pursuit gate admit? |
| [`pursuit-description-gate.md`](pursuit-description-gate.md) | What does the description-first cohort gate keep and drop? |
| [`score-validation.md`](score-validation.md) | Does the scoring stage produce well-shaped output, and where does it fail? |
| [`facts-v3-diff.md`](facts-v3-diff.md) | What changed field by field between `job_facts` version 2 and version 3? |
| [`role-track-derivation.md`](role-track-derivation.md) | Where did the archetype superset and the `role_track` vocabulary come from? |
| [`mock-acceptance.md`](mock-acceptance.md) | Does the whole pipeline behave as specified against a quote-backed answer key? |
| [`jsonld-coverage.md`](jsonld-coverage.md) | How many employer careers sites actually publish a JSON-LD `JobPosting`? |
| [`ats-token-discovery.md`](ats-token-discovery.md) | Which ATS do NYC employers actually run, and can the token be discovered without scraping? |
| [`jobspy-spike.md`](jobspy-spike.md) | Does a self-hosted scraper work from a residential IP? |
| [`google-jobs-query-experiment.md`](google-jobs-query-experiment.md) | Does Google Jobs yield Pursuit-relevant postings when asked for them directly? |

### Plans and logs, frozen at their date

| document | the question it answered |
|---|---|
| [`tasks/refactor/MASTER-PLAN-pursuit.md`](tasks/refactor/MASTER-PLAN-pursuit.md) | What was the phased plan for retargeting the pipeline at the cohort? Its live descendant is the task list. |
| [`tasks/refactor/SOURCING-STRATEGY.md`](tasks/refactor/SOURCING-STRATEGY.md) | Which sourcing service was assigned to which target, and why? |
| [`tasks/refactor/ADDENDUM-google-jobs-providers.md`](tasks/refactor/ADDENDUM-google-jobs-providers.md) | Why are the Google Jobs providers one integration behind an abstraction rather than four? |
| [`tasks/refactor/CLAUDE_UPDATES.md`](tasks/refactor/CLAUDE_UPDATES.md) | What happened in each session of the run? The *what happened* log, beside `DECISIONS.md`'s *why*. |
| [`tasks/refactor/mock/mock-postings-v3-answer-key-addendum.md`](tasks/refactor/mock/mock-postings-v3-answer-key-addendum.md) | What are the expected answers for mock postings 041–055, and what was dropped from that batch? |

### Archive

Everything under [`archive/`](archive/README.md) was true when written and is not the
current state. Its README is the index, with what superseded each file; the files
themselves are linked from there and from `HANDOFF.md`, which is where their content
came from.

## `task` — a unit of work, frozen once it reads DONE

| document | the question it answers |
|---|---|
| [`tasks/refactor/34-documentation-cleanup.md`](tasks/refactor/34-documentation-cleanup.md) | What documentation debt did the run pay down before opening a new surface, and what did it find? |
| [`tasks/refactor/LABELLING-NIGHT.md`](tasks/refactor/LABELLING-NIGHT.md) | What operations have to happen, in what order, to run the labelling night? Task 29's operational annex. |
| [`tasks/refactor/tranche_six/34-documentation-cleanup.md`](tasks/refactor/tranche_six/34-documentation-cleanup.md) | Where did task 34 go? A deliberate stub so an old citation still lands somewhere. |

The numbered task files themselves are indexed by the tree they belong to, in order
and with their status:

- [`tasks/refactor/README.md`](tasks/refactor/README.md) — the Pursuit retarget, tranches one through seven.
- [`tasks/README.md`](tasks/README.md) — the five `job_ingest` tasks that built `backend/webapp/`.
- [`ingestion_tests/README.md`](ingestion_tests/README.md) — the `backend/evals/` work breakdown.

---

## Not in this tree

- **`backend/docs/`** — `DEVELOPER.md`, `OVERVIEW.md`, `SCORING.md` and two
  `HANDOFF-*.md` files, one of which (`HANDOFF-match-quality.md`) is now a stub
  pointing at [`archive/handoff-match-quality.md`](archive/handoff-match-quality.md).
  Out of scope for `audit-docs.py`, which starts at `docs/`; widening it is a later
  call (task 37, *Out of scope*). **`SCORING.md` stays where it is and is not a
  duplicate of [`scoring.md`](scoring.md)** — the two declare different jobs in their
  own opening paragraphs (`DEC-72`): design argument and cost, against contract.
- **`_comment` fields in `backend/config/*.json`** — rationale that lives in the
  config file rather than here, deliberately, and stays there.
- **The repo root [`README.md`](../README.md)** — what the project is and how to run it.

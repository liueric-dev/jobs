---
kind: record
written: 2026-08-02
generator: none
---

# The first three-quantity report

**Task:** [`tasks/refactor/tranche_five/29-labelling-session.md`](tasks/refactor/tranche_five/29-labelling-session.md),
against the harness [`tranche_two/07-metrics-and-golden-set.md`](tasks/refactor/tranche_two/07-metrics-and-golden-set.md) built.
**Measured:** 2026-08-02, from labels collected 2026-07-31 … 2026-08-02.
**Method:** `deepseek-v4-flash` over the 36 labelled postings — **144 live extraction
calls**: 36 for the run (0 replayed from cache, 674 s of summed model latency) and 108 for
the `--repeat 3` selfcheck that produced the floor. Read-only against the database; nothing
tuned, re-scored, or written back to `job_facts`.

This document **owns** the figures below under `DOCS-POLICY.md` rule 2. It is a `record`:
frozen at its date, and nobody should try to keep it current. When the numbers move, a new
dated record supersedes it and this one stays.

---

## Headline

**`evals label report` printed for the first time — exit 0.** The three quantities task 07
was built to produce all exist:

| field | floor | ceiling | model | 95% CI | n |
|---|---:|---:|---:|---|---:|
| `ai_involvement` | 86% | **50%** | 61% | [44–76] | 31 |
| `remote_policy` | 92% | 75% | 48% | [31–66] | 29 |
| `role_archetype` | 75% | 67% | **38%** | [23–55] | 32 |
| `role_track` | 89% | 67% | 47% | [31–64] | 32 |
| `seniority_level` | 89% | 67% | **83%** | [65–92] | 29 |

*floor* = model self-consistency (`agree2`, `evals selfcheck`, this corpus).
*ceiling* = two different people on the same posting (inter-annotator `agree2`).
*model* = the model against the majority human answer.

**The ceiling is below the floor on every field.** Two people agree with each other *less*
often than the model agrees with itself. That is the finding, and it is a finding about the
**measurement**, not about the model: a model score has nothing to be read between when the
band is inverted.

`seniority_level` is the only field where the model number looks healthy. On
`ai_involvement` the model sits *above* the human–human rate — the "saturated the task"
reading — on the field that is the cohort's entire targeting mechanism. The five
inter-annotator disagreements there are `none ↔ uses_ai_tools` ×3 and
`builds_llm_features ↔ uses_ai_tools` ×2, so three of five cross the `none` boundary the
product turns on.

## Do not tune on any of this

**The ceiling rests on 6–10 items per field** — `ai_involvement` 10, `role_archetype` and
`role_track` 9, `remote_policy` 8, `seniority_level` 6 — and every interval in the table
spans 20–30 points. This is the same class of provisional figure as the superseded n=17
self-consistency pair, and the same rule applies: it is not a result, it is a first
reading. See [`MEASUREMENT-TRAPS.md`](MEASUREMENT-TRAPS.md).

**More *overlap* is what moves these numbers. More labels is not.** 25 of the 36 postings
carry one labeller and contribute nothing to the ceiling at all.

## Three caveats that must travel with the table

**1. The floor column is this corpus, and supersedes nothing.** It was measured on the 36
labelled postings, not on the frozen n=115 fixture. The committed self-consistency figures
and the three metrics they are reported under are owned by
[`tasks/refactor/AUDIT.md`](tasks/refactor/AUDIT.md) § *The three self-consistency metrics*
— cite that, not this. `ai_involvement`'s floor reads lower here than the committed
`agree2` figure in AUDIT.md; same metric, different corpus, and neither restates the other.

**2. A fresh selfcheck had to be run, and an n=120 replacement is still owed.**
[`ingestion_tests/selfcheck-n120-2026-07-28.json`](ingestion_tests/selfcheck-n120-2026-07-28.json)
covers 16 fields and **`role_track` is not one of them** — task 11 added that field after
the measurement was taken. `evals label report` refuses per field for whichever of floor /
ceiling / measured is missing, and there is no `--force`, so the report is unrunnable
against the committed selfcheck. The n=36 selfcheck here is what unblocked it; a n=120
selfcheck covering `role_track` remains owed. `DEC-75`.

**3. The `n` column is not 36.** Abstentions are excluded from every rate
(`seniority_level` 8, `remote_policy` 6), and 15 items had no majority human answer and are
excluded — **a tie is not broken**.

## The per-platform reading points the other way from what was predicted

README § *Why evals moved to the front* argues that extraction quality is measured on the
easy sources and will degrade as Phase 3 adds messier ones. **In this sample it is the
clean sources the model does worst on, on all five fields:**

| field | clean (greenhouse + ashby) | messy (everything else) |
|---|---|---|
| `ai_involvement` | 50% [29–71] n=18 | 77% [50–92] n=13 |
| `remote_policy` | 29% [12–55] n=14 | 67% [42–85] n=15 |
| `role_archetype` | 19% [7–43] n=16 | 56% [33–77] n=16 |
| `role_track` | 24% [10–47] n=17 | 73% [48–89] n=15 |
| `seniority_level` | 76% [53–90] n=17 | 92% [65–99] n=12 |

**Read this as an observation, not a result, and the confounds are as large as the effect.**
Each cell holds 12–18 items and the intervals overlap on every field taken alone; what is
suggestive is only that the direction is the same on all five. `ashby` alone supplies 12 of
the clean side, so "clean" here is substantially one platform. And the comparison is
model-vs-*human*, where README's argument is about extraction fidelity — a posting whose
description is clean and long gives a human more to disagree with the model about.

**Nothing in README is corrected on this evidence.** It needs a real n, and the way to get
one is overlap, not another platform.

## The humans reject the vocabulary on about half the set

**Instrument:** `python3 backend/tools/label-findings.py`, the humans' own answers.

| answer | count | rate | 95% CI |
|---|---:|---:|---|
| `role_track = no_track_fits` | 15 of 36 | 42% | [0.27, 0.58] |
| `role_archetype = other` | 19 of 36 | 53% | [0.37, 0.68] |

**Population is the stratified 200-row eval set, not the cohort corpus.** A quarter of it is
`gate_rejected` by construction — postings the pipeline decided are not for this cohort at
all — so this is *not* comparable to task 12's `other` rate on the live corpus, and reading
one against the other is a comparison across two populations.

What it does bear on, and settles neither of: `DEC-64`'s `revenue_commercial`, which is
deliberately proposed and not applied while `pursuit-v1` is being labelled; and task 30's
"group by `role_track`" display, which needs a vocabulary a Builder's own posting lands in.

## Reproducing it

Every input is committed. The report is a pure function of the three files — no database,
no network, no LLM:

```
cd backend && python3 -m evals label report \
  --golden evals/fixtures/golden-v1.jsonl \
  --run evals/fixtures/run-labelled36-2026-08-02.jsonl \
  --selfcheck evals/fixtures/selfcheck-labelled36-2026-08-02.json \
  --label-set pursuit-v1
```

| file | what it is |
|---|---|
| `backend/evals/fixtures/golden-v1.jsonl` | the label export — 271 rows, 36 postings, 2 labellers, round 1 |
| `backend/evals/fixtures/corpus-labelled36-2026-08-02.jsonl` | the same 36 postings hydrated with `description_text` |
| `backend/evals/fixtures/run-labelled36-2026-08-02.jsonl` | the extract run, 36 records |
| `backend/evals/fixtures/selfcheck-labelled36-2026-08-02.json` | the floor, `--repeat 3`, whole-record identical 9 of 36 |

The chain that produced them, in order, since only the last step is discoverable from
`--help`:

```
python3 -m evals label export --out evals/fixtures/golden-v1.jsonl
python3 tools/hydrate-labelled-corpus.py evals/fixtures/corpus-labelled36-2026-08-02.jsonl
python3 -m evals run --task extract --corpus <that corpus> --model "$SPEC" --out <run>
python3 -m evals selfcheck --model "$SPEC" --corpus <that corpus> --repeat 3 --out <selfcheck>
python3 -m evals label report --golden <golden> --run <run> --selfcheck <selfcheck>
```

**Step 2 is the one that is not obvious.** `labelset-pursuit-v1.jsonl` pins *which* postings
were drawn and carries no `description_text`, so it cannot be fed to `evals run`;
`backend/tools/hydrate-labelled-corpus.py` reads the pinned ids back out of the database.
It was a scratch script on the night and is committed for that reason.

## Who labelled what

| | rows | postings | when |
|---|---:|---:|---|
| `u_090b0ad12e99` | 205 | 35 | 2026-07-31 02:56 – 2026-08-02 00:37 UTC, three sittings |
| `u_919ad2c305c2` | 66 | 11 | 2026-08-02 00:52 – 01:09 UTC, one sitting |

**10 postings carry both**, which is the `overlap` block and the whole of the ceiling.
All round 1; **no field has a second round**, so there is no intra-annotator ceiling yet.

## What this does not license

- **No weight change, no threshold, no vocabulary change.** Task 13's weights and task 11's
  proposed `revenue_commercial` are untouched, deliberately.
- **Task 30 is not unblocked.** It needs bucket thresholds set from labels, and a table
  whose ceiling rests on ≤10 items cannot set them.
- **No bucket appears in the API.** `API-CONTRACT-v1.md`'s deferral of `bucket` behind task
  30 stands.

## What would move it

1. **More overlap.** Additional labellers answering the *same* ten `overlap` rows, not new
   postings. Each one adds annotator pairs to every field at once.
2. **Round 2** — the same labeller re-answering the overlap block after the 7-day delay the
   form enforces (~2026-08-09), which yields the intra-annotator ceiling. It is the weaker
   of the two ceilings and is deliberately not wired to the report's ceiling column.
3. **An n=120 selfcheck covering `role_track`**, which retires caveat 2.

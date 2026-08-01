---
kind: task
written: 2026-08-01
generator: none
---

# 38 — One figure, one owner

**Status:** DONE, 2026-08-01. **Depends on:** 36 (check C4 is what keeps this from recurring).

> **Where the figures live now.** [`../AUDIT.md`](../AUDIT.md) § *The three self-consistency
> metrics* owns all three, with the command; `backend/config/doc-figures.json` carries the C4
> rows that keep them there. The tables below are the **derivation**, kept under rule 4 —
> they name every metric they quote, which is the form rule 3's corollary asks for. The two
> bare test counts this file used to restate are gone, because a bare integer is exactly what
> this task exists to remove.
**Blocks:** nothing, but every later measurement inherits the convention it lands.

Apply [`DOCS-POLICY.md`](../../../DOCS-POLICY.md) rules 2 and 3 to the figures that have
already drifted. **Nothing here needs re-measuring** — the resolution below was derived from
the committed raw data on 2026-08-01, offline, and is reproduced by the commands given.

## Finding, and it changes the shape of this task

**No self-consistency number in this repo is wrong.** Every one is correct. One *word* is
overloaded, and it makes two correct numbers look like a contradiction.

`docs/ingestion_tests/selfcheck-n120-2026-07-28.json` carries **three** distinct agreement
metrics per field. All three are in circulation and only one of them is ever named:

```bash
python3 -c "
import json; d=json.load(open('docs/ingestion_tests/selfcheck-n120-2026-07-28.json'))
o=d['fields']['ai_involvement']['overall']
print({k: round(v,4) for k,v in o.items() if k in ('agree2','pairwise','unanimous')})
print('hn:', {k: round(v,4) for k,v in
      d['fields']['ai_involvement']['by_platform']['hn_whoishiring'].items()
      if k in ('agree2','pairwise')})"
```

| metric | what it is | `ai_involvement`, n=115 | `hn_whoishiring` |
|---|---|---|---|
| `agree2` | repeat 1 vs repeat 2 — the two-run protocol, comparable to the n=17 study | **94.8%** | **85.7%** |
| `pairwise` | mean over all three pairs | **90.7%** | **77.8%** |
| `unanimous` | all three identical | **87.0%** | — |

Now every site in the tree resolves, and every one of them is right:

*(Cited by content, not by line: `13d4be5` and task 37's tree-wide frontmatter sweep moved
every line number this file was drafted against.)*

| site | figure | metric it is | labelled? |
|---|---|---|---|
| `.claude/CLAUDE.md` § *production model*, `../AUDIT.md` § *Current measured state* | 94.8% | `agree2` | said *"`--repeat 3`"*, which is the **run**, not the metric |
| `../DECISIONS.md` § *06 — Was 76% real?* table, `CLAUDE_UPDATES.md` § *06 — the gate* | 90.7% | `pairwise` | called *"the **pairwise** two-run metric"* in the line under that table |
| `../DECISIONS.md` § *06 — THE GATE* | 77.8% | `pairwise`, per platform | called *"pairwise agreement by platform"* |
| `docs/ingestion_tests/README.md` § *Gate decision* | 85.7% | `agree2`, per platform | table header says `agree2` |
| `../README.md`, task 06 row | 77.8% | `pairwise`, per platform | **not labelled at all** |

**The defect is `DECISIONS.md` using "pairwise" for both.** Under its *06 — Was 76% real?*
table it means `agree2` ("*because the n=17 study ran twice*"); in *06 — THE GATE* it means the
three-pair mean. One file, one word, two metrics — and the two most-quoted numbers in the run
sit on either side of it.

**And it is one turn worse than that, found while implementing this task.** That same
*"Was 76% real?"* table does not use one metric at all — its three field rows mix two, under a
caption naming one (its fourth row, whole-record-identical 21.7%, is a third thing again: all
three runs agreeing on all fifteen compared fields at once):

| row | value in the table | which metric that is | the other one, same run |
|---|---|---|---|
| `seniority_level` | 85.2% | **`agree2`** | `pairwise` 84.9% |
| `role_archetype` | 84.3% | **`agree2`** | `pairwise` 85.8% |
| `ai_involvement` | 90.7% | **`pairwise`** | `agree2` 94.8% |

Every cell is a real number and none of the entry's conclusions move — `role_archetype` is
"optimistic" on either metric — but the caption *"comparisons are drawn against the pairwise
two-run metric"* is true of exactly one of the three rows. `DECISIONS.md` is append-only, so
`DEC-71` records this rather than editing it.

This is `MEASUREMENT-TRAPS.md`'s territory and probably belongs in it: **a metric with no name
is a number that cannot be compared to itself.**

## The work

### 38a — name the three metrics, once

`AUDIT.md` owns the figure under rule 2. Give it the table above, with the command that
reproduces it. Every other site then **cites `AUDIT.md` and names its metric** — `94.8%
(agree2)` — rather than restating the number bare.

`DECISIONS.md` is append-only: **do not rewrite `:40`, `:57` or `:613`.** Append a new entry
that defines the three metric names and states which of them each earlier entry meant. That is
the append-only-safe repair and it preserves the evidence that the ambiguity existed.

### 38b — the one unlabelled site

`../README.md`'s **task 06 row** read *"`ai_involvement` 77.8% (`pairwise`) on hn_whoishiring"*
— without the parenthesis, which is the whole defect — in the file that calls itself the
ordered index. Add the metric name. It is a one-line fix and it is the site most likely to be
copied forward.

### 38c — the superseded pair, in the index that does not mark it

`../README.md` § *Why evals moved to the front* still read *"76% on `seniority_level`, 94% on
`ai_involvement`"* with no supersede marker. **Every other site in the repo marks it** —
`role-track-derivation.md` strikes it, `DEFECTS.md` scopes it, `AUDIT.md` § *Current measured
state* calls it dead by name, `.claude/CLAUDE.md` strikes it. This one file did not, and it is
the ordered index.

Mark, do not delete (rule 4). The n=17 figures stay visible with the n=115 pair beside them.

### 38d — the test count

Three live values, none of which is what the runner prints:

| site | value |
|---|---|
| `../HANDOFF.md` § *State* | one four-digit count |
| `../AUDIT.md` § *Current measured state*, `.claude/CLAUDE.md` § *Working on a task* | a different one |
| what `python3 -m unittest discover -s tests` prints today | **neither** |

*(The three integers themselves are deliberately not written here: this file is the one
arguing that a typed count decays, and C4 flagged it for quoting the copies it exists to
remove. `git show 13d4be5:docs/tasks/refactor/AUDIT.md` has them if the exact values matter.)*

Each was right when typed. Apply rule 3: **`AUDIT.md` keeps the instrument and drops the
number**, and every other site cites `AUDIT.md`. `AUDIT.md` already argues for exactly this —
*"Read the `Ran N tests` line, not a static count"* — one line above a static count.

`.claude/CLAUDE.md` is the sharp case: it tells every session *"it should not go down"*, which
needs a floor to compare against. Either it keeps a floor **with a date and a "verify before
trusting" note**, or it says "not smaller than the last commit's run". Decide and record in
`DECISIONS.md`; do not leave a bare integer.

### 38e — register the figures in `doc-figures.json`

Task 36's C4 reads a declared list. This task is where the list gets its first real rows: the
test counts, the three self-consistency metrics, the labelling rate, the gate volume. With
`_comment` and `_why` fields in the existing style.

**Eight rows landed, and the editorial rule they encode is `DOCS-POLICY.md` rule 1's lifecycle
column rather than anyone's taste.** C4 bites on `contract` and `rolling` — the two kinds that
may not be stale — and allows `record`, `task` and `rationale`, which are frozen by
construction and where rewriting a figure destroys the evidence rule 4 exists to keep. Each
allowance is enumerated to what the figure actually reaches, with a line saying why; see
`_allowance_rule` in the file.

**`HANDOFF.md` is allowed nowhere.** It is the tree's only `kind: rolling` document, which is
the one kind rule 1 forbids to be stale, and it is the entry point every session reads first.
The exemption argued for and rejected was the labelling rate, whose twelve uses there are
mostly budgets *derived* from the median rather than restatements of it. The reason it lost:
when a rate is re-measured the derived budgets go stale too, and they are the more dangerous
half, because *"ask for twenty minutes"* is the sentence that reaches a human. This figure has
already drifted exactly that way once, off a four-interval reading, and the correction had to
chase it through five documents in a day. C4 caught this very paragraph restating the number
while it was being written, which is the check doing the only thing it is for.

**One row is not owned by `AUDIT.md`.** The Pursuit gate volume belongs to
[`docs/pursuit-gate-volume.md`](../../../pursuit-gate-volume.md), which carries the SQL, the
date range and the junk-fraction adjustment; `AUDIT.md` carries no line of it. Rule 2 puts a
figure with its instrument, not with the index — a row naming `AUDIT.md` there would have been
the rule quoted rather than applied.

## Definition of done

| | item | how it is checked |
|---|---|---|
| ✅ | `AUDIT.md` carries the three named metrics and the command that reproduces them | `AUDIT.md` § *The three self-consistency metrics*. The command re-run 2026-08-01: `{'agree2': 0.9478, 'pairwise': 0.9072, 'unanimous': 0.8696}`, `hn: {'agree2': 0.8571, 'pairwise': 0.7778}` |
| ⚠️ | No document states a self-consistency figure without naming its metric | `grep -rn '94\.8\|90\.7\|87\.0\|85\.7\|77\.8' docs/ .claude/`. Clean in every `contract` and `rolling` document **except three lines outside this task's writable scope** — `.claude/CLAUDE.md`, `docs/ingest/nyc-open-data.md` (this task's own § *Out of scope*), and two prose cells in `docs/ingestion_tests/README.md` whose table headers name the metric. Frozen `record`/`task`/`rationale` hits are evidence under rule 4 and are left |
| ⏳ | `DECISIONS.md` gained an **appended** entry defining the metrics; the three earlier entries unmodified | `DEC-71`, drafted and handed to the orchestrator, which owns that file. `git diff docs/tasks/refactor/DECISIONS.md` is empty from this task |
| ✅ | `../README.md`'s 76%/94% is struck with the n=115 pair beside it | § *Why evals moved to the front*; struck, with an `agree2`-named replacement blockquote |
| ✅ | No test count is typed anywhere except `AUDIT.md`, and `AUDIT.md`'s is either absent or dated-with-a-caveat | **absent.** `AUDIT.md` carries the two commands and *"your floor is the suite's own reading before you changed anything"*. C4's only remaining finding is one `HANDOFF.md` line, already in the baseline and task 40's |
| ✅ | `backend/config/doc-figures.json` has rows for every figure named here | eight rows: both test counts, the three metrics, the per-platform pair, the labelling rate, the gate volume. Every pattern measured over `docs/` and the count recorded in its `_pattern_note` |
| ✅ | Both suites green and not smaller | `Ran 1233 tests` / `OK` (main) and `Ran 93 tests` / `OK` (webapp), **run 2026-08-01, unchanged from this wave's opening reading**. Those two integers are a dated observation of a run, not a floor anyone should compare against later — that is what the rest of this task is about, and `AUDIT.md` carries the commands |

## Out of scope

- **Re-running `evals selfcheck`.** Everything above came out of committed data for free. Task
  06's gate decision is untouched and is not reopened by naming its metrics.
- **Deciding which metric is the "right" one.** All three are real. The product question — which
  one `MATCH_FLOOR` and the cohort gate should be reasoned about with — is task 30's, and this
  task must not pre-empt it by blessing one and quietly retiring the others.
- **`docs/ingest/` figures.** They are per-script contracts; task 37 classifies them first.

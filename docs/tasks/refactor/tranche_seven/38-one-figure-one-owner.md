---
kind: task
written: 2026-08-01
generator: none
---

# 38 — One figure, one owner

**Status:** TODO. **Depends on:** 36 (check C4 is what keeps this from recurring).
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

| site | figure | metric it is | labelled? |
|---|---|---|---|
| `.claude/CLAUDE.md`, `../AUDIT.md:50` | 94.8% | `agree2` | says *"`--repeat 3`"*, which is the **run**, not the metric |
| `../DECISIONS.md:57`, `CLAUDE_UPDATES.md:606` | 90.7% | `pairwise` | called *"the **pairwise** two-run metric"* at `DECISIONS.md:613` |
| `../DECISIONS.md:40` | 77.8% | `pairwise`, per platform | called *"pairwise agreement by platform"* |
| `docs/ingestion_tests/README.md:253` | 85.7% | `agree2`, per platform | table header says `agree2` |
| `../README.md:31` | 77.8% | `pairwise`, per platform | **not labelled at all** |

**The defect is `DECISIONS.md` using "pairwise" for both.** At `:613` it means `agree2`
("*because the n=17 study ran twice*"); at `:40` it means the three-pair mean. Its own table at
`:57` uses the second. One file, one word, two metrics — and the two most-quoted numbers in the
run sit on either side of it.

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

`../README.md:31` reads *"`ai_involvement` 77.8% on hn_whoishiring"* in the file that calls
itself the ordered index. Add the metric name. It is a one-line fix and it is the site most
likely to be copied forward.

### 38c — the superseded pair, in the index that does not mark it

`../README.md:118` still reads *"76% on `seniority_level`, 94% on `ai_involvement`"* with no
supersede marker. **Every other site in the repo marks it** — `role-track-derivation.md:361`
strikes it, `DEFECTS.md:604` scopes it, `AUDIT.md:53` calls it dead by name, `.claude/CLAUDE.md`
strikes it. This one file does not, and it is the ordered index.

Mark, do not delete (rule 4). The n=17 figures stay visible with the n=115 pair beside them.

### 38d — the test count

Three live values, none of which is what the runner prints:

| site | value |
|---|---|
| `../HANDOFF.md:17` | 1178 |
| `../AUDIT.md:44`, `.claude/CLAUDE.md:177` | 1182 |
| what `python3 -m unittest discover -s tests` prints today | **neither** |

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

## Definition of done

| | item | how it is checked |
|---|---|---|
| | `AUDIT.md` carries the three named metrics and the command that reproduces them | the command in this file runs and prints the three numbers |
| | No document states a self-consistency figure without naming its metric | `grep -rn '94\.8\|90\.7\|87\.0\|85\.7\|77\.8' docs/ .claude/` — every hit names `agree2`, `pairwise` or `unanimous`, or cites `AUDIT.md` |
| | `DECISIONS.md` gained an **appended** entry defining the metrics; `:40`, `:57`, `:613` unmodified | `git diff` touches only lines after the last existing entry |
| | `../README.md:118`'s 76%/94% is struck with the n=115 pair beside it | read it |
| | No test count is typed anywhere except `AUDIT.md`, and `AUDIT.md`'s is either absent or dated-with-a-caveat | 36's C4 clean |
| | `backend/config/doc-figures.json` has rows for every figure named here | C4 runs against it |
| | Both suites green and not smaller | read `Ran N tests` from each |

## Out of scope

- **Re-running `evals selfcheck`.** Everything above came out of committed data for free. Task
  06's gate decision is untouched and is not reopened by naming its metrics.
- **Deciding which metric is the "right" one.** All three are real. The product question — which
  one `MATCH_FLOOR` and the cohort gate should be reasoned about with — is task 30's, and this
  task must not pre-empt it by blessing one and quietly retiring the others.
- **`docs/ingest/` figures.** They are per-script contracts; task 37 classifies them first.

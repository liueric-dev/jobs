# 06 — Re-run self-consistency at n=120

**Status:** DONE, `5092568`. **Depends on:** 01. **Blocks:** 07, 11, 12, 13.

Establish whether `deepseek-v4-flash` really disagrees with itself 24% of the time on
`seniority_level`, or whether that was an artifact of seventeen jobs.

`docs/ingestion_tests/README.md` already specifies this and says plainly: *"Nothing
should be re-tuned on it until it is re-run at n=120. The harness makes that cheap;
it has not been done."* This task is that sentence.

## What was measured, and why it is now urgent

2026-07-27, 17 jobs from `evals/fixtures/corpus-v1.jsonl`, extracted twice with
identical prompts and parameters at temperature 0:

| field | self-agreement | scored by `match.py`? |
|---|---|---|
| `seniority_level` | 76% | yes |
| `remote_policy` | 76% | yes |
| `tech_stack` | 90% (Jaccard) | yes |
| `role_archetype` | 94% | yes |
| **`ai_involvement`** | **94%** | **yes — and it is now the product** |
| whole record identical | **0 of 17** | |

Two things changed since that was written.

**The model is confirmed as production** (task 01). This is not a hypothetical.

**`ai_involvement` became the targeting mechanism.** `uses_ai_tools` is how the
Pursuit cohort's entire opportunity space is identified. A 6% flip rate between
identical runs — on *clean* ATS postings — is a product-level risk, not a data-quality
footnote. If the true figure is materially worse on the messy sources Phase 3 adds,
the app surfaces a different set of jobs each night for no reason a user could
understand.

## The competing explanation, which must be tested

The README's own reconciliation is corpus, not model: `tools/compare-extract.py`
selects `ORDER BY first_seen DESC`, which is ~85% greenhouse and ashby — clean ATS
postings — and reported 95% / 90%. The stratified fixture includes HN free-text and
reported 76%.

If that is right, **the 95% describes the easy sources and the calibration rests on
it** — and Phase 3 moves the corpus decisively toward the hard end: government
boilerplate, Workday free text, arbitrary JSON-LD, nonprofit boards.

So this task must report per-platform, not just per-field. A single blended number
would hide exactly the effect that matters.

## Work

### Extend the fixture

`corpus-v1.jsonl` needs to reach n=120 with per-platform stratification maintained.
`docs/ingestion_tests/README.md` records why the pool is per-platform: sampling the
globally-most-recent rows returned zero HN and zero weworkremotely records, because
greenhouse and ashby are ~9,800 of 11,517 rows. *The source with the messiest parsing
was the one a naive corpus structurally could not test.*

Freeze it as `corpus-v2.jsonl`. Do not mutate v1 — figures already cite it.

### Run

`runner.py --repeat 3` per `docs/ingestion_tests/03-metrics-and-golden-set.md`. Three
runs rather than two gives a majority and distinguishes "flips between two values"
from "unstable across three."

### Report

Per field **and per platform**, with confidence intervals:

| field | greenhouse/ashby | lever | google_jobs | hn_whoishiring | weworkremotely | all |
|---|---|---|---|---|---|---|

Intervals matter more than point estimates here — n=17 was 13-of-17 on the worst
field, which is consistent with anything from 55% to 90%.

Cost and latency must not be reported from cache; `report.py` already refuses this
and the rule holds.

## Gates

This task gates four others, with different thresholds:

| finding | consequence |
|---|---|
| `ai_involvement` ≥ 95% on all platforms | proceed; the targeting mechanism is sound |
| `ai_involvement` 90–95% | proceed, but task 11 adds a confidence field and task 13 weights unstable extractions down |
| `ai_involvement` < 90% on the messy platforms | **stop.** Tasks 10 and 13 need rethinking — possibly a second extraction pass or majority-of-3 for this field alone. The entire cohort targeting depends on it |
| clean-vs-messy gap > 10 points | Phase 3's sourcing plan needs a quality budget per source, and task 12's re-extraction should be measured before and after |

Whatever the outcome, task 12's `FACTS_VERSION` bump is gated on task 07 as well —
measure extraction quality on the new corpus before committing to a full
re-extraction, not after.

## Definition of done

- `corpus-v2.jsonl` frozen at n=120, stratified, committed.
- Per-field, per-platform agreement with CIs, reported and committed.
- `docs/ingestion_tests/README.md`'s provisional figures are replaced, with the n=17
  numbers retained and marked superseded rather than deleted.
- `config/criteria.json`'s `_hard_exclude_comment` — which currently justifies its
  penalty design with the 95% / 90% figures — is corrected or confirmed.
- The gate decision above is recorded explicitly, including which branch was taken.

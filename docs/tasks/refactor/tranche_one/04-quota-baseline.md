# 04 — Quota and wall-clock baseline

**Status:** todo. **Depends on:** 01. **Blocks:** 12 (the `FACTS_VERSION` bump), and
the sizing of all of Phase 3.

Replace a cost model denominated in dollars with one denominated in the things that
actually bind: requests per day, requests per minute, and seconds of nightly window.

## Why the existing figures do not answer the question

`backend/docs/SCORING.md` "What it costs" concludes: *"At roughly $0.05/user/month,
token cost has stopped being the interesting constraint. What binds is request rate
limits, wall-clock, and ranking quality."*

That conclusion is correct and the table underneath it does not measure any of the
three things it names. Everything is in dollars.

Three further reasons it cannot be reused as-is:

- **The projection assumes 250 eligible postings/day.** Task 05 measures what a
  Pursuit gate actually admits. If it is 2,000, every derived figure moves by 8×.
- **94% cache hit rate was measured, not guaranteed.** It depends on prompt stability
  and the provider's caching behaviour, and the prompt is about to change (task 11).
- **The free tier changes the units.** With a near-zero marginal token cost, the
  binding constraint is whatever the provider's rate limit is — a number that appears
  nowhere in the repo.

## Measure

Rewrite `backend/tools/cost-test.py` to report, per stage:

| quantity | why |
|---|---|
| **requests/day available** | the provider's daily ceiling on the production key |
| **requests/minute ceiling** | observed, by pushing until throttled — the burst limit decides whether a backfill is possible at all |
| **wall-clock per call**, p50 and p95 | extraction was 9.3s. At 2,000 postings that is 5 hours |
| **real cache hit rate** | on the current prompt, not the one measured months ago |
| **tokens in/out** | retained — still the input to any future paid tier |
| **failure and retry rate** | a throttled call that silently returns short is the pattern task 03 exists to catch |

Report against `deepseek-v4-flash` as pinned in task 01. If extraction and scoring
resolve to different models, report each separately.

### The number that matters

Produce one derived figure and put it at the top of the output:

> **At N eligible postings/day, the nightly extraction pass takes H hours and
> consumes Q% of the daily request quota.**

Everything else is supporting detail. `run-daily.py` runs nine steps under a systemd
timer; if extraction alone exceeds the window, the plan changes regardless of price.

## Then decide the throttle

`config/relevance.json`'s `max_tier_to_score` is currently 2, with the comment *"Set
to 3 to open the floodgates once throughput allows."* This task produces the number
that decides whether that is safe — and, if the widened gate from task 05 is large,
whether tier 2 itself needs subdividing.

Record the decision in `relevance.json`'s `_max_tier_note` rather than only in a
commit message. That file's `_comment` convention is the most durable documentation
in the repo; use it.

## Do not

**Do not re-tune anything on this run.** The purpose is a baseline against which the
post-refactor pipeline is compared. Tuning here means the comparison has no fixed
point — the trap `HANDOFF-match-quality.md` §4 documents three separate ways of
walking into.

**Do not measure against a live-selected corpus.** Use the frozen fixture from
`backend/evals/fixtures/corpus-v1.jsonl`. `docs/ingestion_tests/README.md` records
exactly why: every tool under `tools/` selects with `ORDER BY first_seen DESC LIMIT
n` against production, so the corpus changes nightly and no two runs are comparable.
That applies to cost as much as to quality.

## Definition of done

- `cost-test.py` reports quota, wall-clock and cache rate; dollars are secondary.
- The derived sentence above is printed and recorded in `SCORING.md`.
- The provider's actual rate limits are documented — in the repo, not in someone's
  memory.
- A decision on `max_tier_to_score` is recorded with its reasoning.
- Figures are reproducible: frozen fixture, pinned model, stated date.

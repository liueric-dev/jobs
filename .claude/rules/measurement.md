---
paths:
  - "backend/evals/**"
  - "backend/tools/*.py"
---

# Measurement discipline

**Never evaluate on the layer you trained on.** L0 is human labels (never train), L1 is
`fit_score`, L2 is `job_events`.

**Never select an eval corpus with `ORDER BY first_seen DESC`** — it measures the easy sources. Use
the frozen fixtures in `backend/evals/fixtures/`. (`tools/compare-models.py` and
`tools/claude-bench.py` still do this against production; figures from either are not
reproducible.)

**Report average precision as the measurement, precision@20 as the objective.** A count of twenty
cannot resolve the differences being decided on.

**Pin eval sets by sorted `job_id`.** Never train on them, never recycle them.

**Read the `Ran N tests` line, not a count written down anywhere** — including in `CLAUDE.md`.
Counts in prose go stale silently, and that is most of why `docs/` was deleted.

**`deepseek-v4-flash` is the production model and it does not agree with itself at temperature 0.**
**85.2% [77.6–90.6] on `seniority_level`, 94.8% [89.1–97.6] on `ai_involvement`**, n=115, both
**`agree2`**. **Name the metric whenever you quote one of these** — the same run yields `agree2`
94.8%, `pairwise` 90.7% and `unanimous` 87.0% for `ai_involvement`, all correct and all in
circulation; `--repeat 3` is the *run*, not the metric. A second n=115 run on the same frozen corpus
five days later disagrees by up to 9.6 points (`remote_policy`). **OQ-9 decided 2026-08-03: quote
both as a range and act on the lower bound** — neither run supersedes the other, each carries a
`_comment` saying so, and `docs/STATE-OF-THE-SYSTEM.md` § 6 has the per-field floors.

The rest of the landmines are path-scoped beside this file in `.claude/rules/`, so they load when
you touch what they bite; `docs/STATE-OF-THE-SYSTEM.md` § 5 keeps only the one that has no path.

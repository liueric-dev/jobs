---
paths:
  - "backend/config/*.json"
---

# Config conventions

**`_comment` fields are load-bearing documentation.** They record where numbers came from and —
more valuably — what was rejected and why. Every new config gets them, in the existing style. Read
the ones in `config/relevance.json` before writing new ones. **With `docs/` gone these are the
primary written rationale in the repo**; treat deleting one as deleting a decision record.

**After any `config/relevance.json` edit, run the dead-pattern report. Not optional** — see the
`\y` landmine in `.claude/rules/sql.md`.

```bash
cd backend && python3 tools/relevance-report.py --dead --profile pursuit
```

Pass `--profile`: the default resolves to `tech`, which is INACTIVE, so the default invocation
reports on a projection rather than on production (`backend/tools/relevance-report.py:146`, and the
tool says so itself at `:163-166`).

**Editing `config/criteria.json` changes nothing observable.** It is a template: it is imported once
by `migrations/migrate_profiles.py` and thereafter `jobs.profiles.criteria_json` is authoritative.
The `unknown_penalty` block (`backend/config/criteria.json:112`) is the live example — until someone
runs `migrate_profiles.py --apply --bump`, every profile's criteria carries no such block,
`match.py:198`'s lookups return 0, and `score_job()` returns byte-identical scores. The file says so
at `:124`, and the magnitudes are unfitted by design; `OQ-39` owns whether they are ever fitted and
applied. **So a criteria edit is a proposal, not a change**, and anything measuring its effect
against the live database is measuring the old numbers.

**`daily_budget` in `config/google-queries.json` is per request, not per day.** Each bucket's budget
caps how many stale queries one call to `pick_stale_queries_by_bucket()` takes
(`backend/api/query_claims.py:1332-1353`); nothing decrements it across calls. What actually stops a
slug being fetched twice in a day is `MIN_HOURS_BETWEEN_RUNS`, 20 by default
(`backend/api/query_claims.py:365`, applied at `:1347`). Two callers a day is two budgets spent.

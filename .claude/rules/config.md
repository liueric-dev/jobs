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
reports on a projection rather than on production.

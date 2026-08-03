---
kind: contract
written: 2026-08-02
generator: none
---

# jobs

Daily job-discovery automation for the Pursuit AI-Native cohort: ~30 Builders, entry-level,
AI-adjacent roles, all industries, NYC.

| | what | state |
|---|---|---|
| [`backend/`](backend/) | the pipeline that finds, dedupes and scores postings | live |
| [`backend/webapp/`](backend/webapp/) | Google SSO, ranked jobs, engagement events | live, port 8421 |
| [`backend/api/`](backend/api/) | the contributor work queue | expected to be deprecated; may not start against the deployed DB |
| [`frontend/`](frontend/) | the client | shipping — five screens, no build step |
| [`deploy/`](deploy/) | systemd units and cloudflared ingress | files tracked; not installed on any machine |

**Start with [`docs/STATE-OF-THE-SYSTEM.md`](docs/STATE-OF-THE-SYSTEM.md)** — what the pipeline
actually does, what is genuinely done, what is open, the landmines, and every figure with the
instrument that produced it. It is the only document in this repo. On 2026-08-02 the other 137
files under `docs/` were deleted after an audit found 168 places they contradicted the code; they
are all still in git behind the tag `refactor-freeze-2026-08-02`.

[`.claude/CLAUDE.md`](.claude/CLAUDE.md) holds the rules and invariants for working in this tree.

## backend/

Pulls postings from **eight** ingest scripts into one Postgres table, dedupes them, and has an LLM
extract facts and write a fit narrative. It **finds and judges** jobs; it does not apply to them,
track applications, or do outreach — those stay manual on purpose.

`ingest/ats.py` alone reaches six ATS vendors (Greenhouse, Lever, Ashby, Workable, Recruitee,
SmartRecruiters), reading its roster from the `company_ats` table rather than from a file.

```bash
cd backend
python3 -m unittest discover -s tests        # the whole suite
python3 -m unittest tests.test_row_identity  # the guard on row identity
python3 run-daily.py                         # the 14 steps the nightly timer runs
```

Scheduled by a **systemd user timer**, not cron — `jobs-ingest.timer`, midnight local. The last
run's outcome: `journalctl --user -u jobs-ingest.service`.

## frontend/

A shipping client: one HTML shell, one hand-written stylesheet, 13 ES modules, five routed screens
(Today, Job detail, Saved, Search, Onboarding). **No build step, no framework, no npm, no
`package.json`** — a constraint to keep, not an accident.

It must be served from the webapp's own origin, because it authenticates with
`credentials: "same-origin"` and a relative `BASE`. Served from anywhere else every request silently
loses the session cookie and renders as the sign-in screen.

```bash
cd backend/webapp && .venv/bin/python ../../frontend/serve.py   # then http://localhost:8421/
python3 frontend/verify_fixtures.py    # fixtures still describe the server
node frontend/check_client.mjs         # client still agrees with the fixtures
```

Not built: the Contribute surface, and the phone test.

## Layout note

Everything the backend needs resolves relative to `backend/`, never to this directory or to the
process's working directory — the `sys.path` inserts in `ingest/`, `tools/`, `migrations/`,
`scripts/`, `api/` and `webapp/` each reach exactly one level up, and the shell scripts `cd` to
their own parent. That is what made the original split a pure move, and the tree can be relocated
again as a unit.

`backend/` holds three deliberately separate processes, each with its own `.env`, venv and Postgres
role. `api/` and `webapp/` import nothing from each other, and no pipeline module imports either —
but `webapp/` does import the pipeline's `profiles`, `searchnorm` and `evals.labels`, and `api/`
imports `google_jobs`, so the shared surface is wider than `schema.py` and `lib/`.

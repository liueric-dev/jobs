# jobs

Daily job-discovery automation, split into two halves.

| | what | state |
|---|---|---|
| [`backend/`](backend/) | the pipeline that finds, dedupes and scores postings | live |
| [`backend/webapp/`](backend/webapp/) | the API the frontend will call: Google SSO, ranked jobs, engagement | built, unrendered |
| `frontend/` | the surfacing layer itself | not started |
| [`docs/tasks/`](docs/tasks/) | the work breakdown for closing that gap | — |

## backend/

Pulls tech/AI postings from seven independent sources into one Postgres table,
dedupes them, and has an LLM score each one against a candidate profile. It
**finds and judges** jobs; it does not apply to them, track applications, or do
outreach — those stay manual on purpose.

Start at [`backend/README.md`](backend/README.md) for setup and operation, or
[`backend/docs/`](backend/docs/) for architecture and design history.

```bash
cd backend
python3 -m unittest discover -s tests -t .   # the guard on row identity
python3 run-daily.py                         # what the nightly timer runs
```

Scheduled by a **systemd user timer**, not cron — `jobs-ingest.timer`, midnight
local. See `backend/README.md` for why, and `~/.hermes/scripts/jobs-ingest-status.sh`
for the last run's outcome.

## frontend/

Still empty — nothing renders a job to a human yet. What changed on 2026-07-26
is that the half below the UI now exists, so a frontend has something to call
rather than a database to reinvent access to.

**[`backend/webapp/`](backend/webapp/)** serves it. Google SSO against an email
allowlist, an opaque session cookie, `GET /v1/jobs` reading the `jobs_app`
view, and `POST /v1/events` writing `job_events` — the engagement table
`backend/docs/SCORING.md` has always attributed to "the surfacing layer" and
which nothing had ever written.

```bash
cd backend/webapp
.venv/bin/python -m unittest discover -s tests -t .
.venv/bin/uvicorn app:app --port 8421
```

It runs as its own restricted Postgres role that can read the corpus and append
engagement and rewrite nothing. See its README for setup, the Google Cloud
Console steps, and the grant table; [`docs/tasks/`](docs/tasks/) has the work
breakdown and the reasoning behind each decision.

## Layout note

Everything the backend needs resolves relative to `backend/`, never to this
directory or to the process's working directory — the `sys.path` inserts in
`ingest/`, `tools/`, `migrations/`, `scripts/`, `api/` and `webapp/` each reach
exactly one level up, and the shell scripts `cd` to their own parent. That is
what made this split a pure move: no import changed, and the tree can be
relocated again as a unit.

`backend/` holds three things that are deliberately separate processes: the
nightly pipeline, `api/` (the contributor work queue, expected to be
deprecated) and `webapp/` (the frontend's backend). Each has its own `.env`,
its own venv and its own Postgres role, and none imports another — they share
only `schema.py` and `lib/`.

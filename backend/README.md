# Backend ingestion

Python 3.14 and a dedicated Postgres database are required. This code only
creates ingestion-owned tables; it does not drop old product tables or rows.

## Local Development

```bash
cd backend
python3.14 -m venv .venv
.venv/bin/pip install -r requirements.txt
cp .env.example .env && chmod 600 .env
```

Set `DATABASE_URL` in `.env`; there is no default. Before connecting a new
database, verify the URL and run `.venv/bin/python tools/provision-database.py`.
That command changes schema. Never use the local development database for
investigation writes; use a throwaway database or reversible seed instead.

The full pipeline is `.venv/bin/python run-daily.py`. Each `ingest/*.py` source
can also run independently. Known ATS board tokens are checked about every 30
days. To investigate a new employer, run `.venv/bin/python
tools/ats-discover.py --help` and add/probe it explicitly. `config/companies.json`
is the initial board-token seed; `config/relevance.json` limits Workday detail
fetches and does not rank postings. Query `jobs` for the raw normalized rows.

Before verifying a local server, check `lsof -i :8000` and `lsof -i :3000` and
clear stale processes or choose another port. There is no server in this reset.
Use the matching component venv; never invoke the backend with system Python.

## Checks

```bash
.venv/bin/python -m unittest discover -s tests -t .
.venv-dev/bin/ruff check .
.venv-dev/bin/mypy
```

Set `JOBS_SCRATCH_DATABASE_URL` to a disposable Postgres database for DB-backed
tests. This Python project has no build step. Ruff has a pre-existing nonblocking
backlog; mypy checks the typed seams. The earlier app/docs remain available at
the recovery tag in the root README.

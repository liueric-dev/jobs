# Backend pipeline

The pipeline ingests job postings, extracts facts once per posting, matches them
to profiles, and generates narratives for the top matches. `run-daily.py` runs
the stages in order. The browser reads results through `webapp/`.

## Setup

Use Python 3.14 and a Postgres database dedicated to this project. The
pipeline has its own environment:

```bash
cd backend
python3.14 -m venv .venv
.venv/bin/pip install -r requirements.txt
cp .env.example .env && chmod 600 .env
```

Set `DATABASE_URL` in `.env`. It has no fallback. Add the source and scoring
keys you intend to use; `.env.example` lists them. For a fresh development
database, create all three components' schema with:

```bash
.venv/bin/python tools/provision-database.py
```

That command issues DDL against the configured database. Check the URL before
running it. The pipeline's configuration files are under `config/`.

## Run and inspect

```bash
.venv/bin/python run-daily.py
.venv/bin/python ingest/ats.py
.venv/bin/python match.py
```

Each ingest script can run independently. Scheduled runs use
`deploy/systemd/jobs-ingest.timer`. Query `jobs_app` for listings; `jobs` is
the unfiltered ingestion table. `docs/` and the older task plans are available
through the recovery tag named in the root README.

## Checks

```bash
.venv/bin/python -m unittest discover -s tests -t .
.venv-dev/bin/ruff check .
.venv-dev/bin/mypy
```

For the optional development tools, create `.venv-dev` with Python 3.14 and
install `ruff`, `mypy`, and `psycopg[binary]` into it.

The test suite uses temporary Postgres schemas when a scratch database is
available. Set `JOBS_SCRATCH_DATABASE_URL` to a disposable database for DB
tests. Ruff currently has an existing nonblocking backlog; mypy is a blocking
check in CI. `api/` and `webapp/` have separate environments and test suites.

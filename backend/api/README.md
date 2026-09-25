# Contributor API

This FastAPI service manages contributors, hands out Google Jobs query claims,
and accepts their results. The pipeline and webapp are separate processes.

## Setup

Use the API's own Python 3.14 environment:

```bash
cd backend/api
python3.14 -m venv .venv
.venv/bin/pip install -r requirements.txt
cp .env.example .env && chmod 600 .env
```

Set `DATABASE_URL` to this project's database. The long-running service should
use a restricted role; `.env.example` describes the owner credential used only
for schema setup. A fresh local database can be provisioned from `backend/`
with `tools/provision-database.py`. For an existing database, the API's additive
schema command is:

```bash
JOBS_ADMIN_DATABASE_URL=postgresql://OWNER:PASSWORD@localhost:5432/jobs \
  .venv/bin/python manage_users.py init-schema
```

The service checks its required tables and privileges at startup. The exact
grant requirements live in `query_claims.py`; provisioning does not grant a
restricted role access automatically.

## Run and administer

```bash
.venv/bin/uvicorn app:app --port 8420
.venv/bin/python manage_users.py create --name "Example" --label "laptop"
.venv/bin/python manage_users.py list
.venv/bin/python contribution_report.py
```

The raw contributor key is printed once. The webapp's Contribute flow is the
normal way to issue a key; `manage_users.py create` is an operator fallback.
The optional Apify worker is in `actor/`.

## Checks

```bash
.venv/bin/python -m unittest discover -s tests -t .
```

Database tests use temporary schemas. Set `JOBS_SCRATCH_DATABASE_URL` to a
disposable database owned by a non-superuser; privilege tests cannot work as
a Postgres superuser. The worker installer tests are written for Linux, the
platform used by CI.

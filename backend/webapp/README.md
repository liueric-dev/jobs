# Webapp

The webapp provides Google sign-in and the job API. `frontend/serve.py` mounts
the browser client on the same origin as this service.

## Local setup

Use the webapp's own Python 3.14 environment:

```bash
cd backend/webapp
python3.14 -m venv .venv
.venv/bin/pip install -r requirements.txt
cp .env.example .env && chmod 600 .env
```

Set `DATABASE_URL`, `GOOGLE_CLIENT_ID`, and `GOOGLE_CLIENT_SECRET`. For local
HTTP development, set `FRONTEND_ORIGIN` and `ALLOWED_ORIGINS` to
`http://localhost:8421` and `SESSION_COOKIE_SECURE=false`. Keep the cookie
secure in deployment. The root `./dev.sh` checks these values and starts the
local stack after the database has been provisioned.

A fresh local database can be provisioned from `backend/` with
`tools/provision-database.py`. For an existing database, the webapp's additive
schema command is:

```bash
JOBS_ADMIN_DATABASE_URL=postgresql://OWNER:PASSWORD@localhost:5432/jobs \
  .venv/bin/python manage_app_users.py init-schema
```

The service checks required grants at startup. For a restricted production
role, grant the privileges listed in `schema_web.py`; schema setup does not
grant them automatically.

## Google Cloud Console

Create a Web application OAuth client in Google Cloud Console. Register the
exact `GOOGLE_REDIRECT_URI` from `.env`, including whether it has a trailing slash.
While the consent screen is in testing, each user must be on Google's test-user
list and in this app's `app_users` table.

```bash
.venv/bin/python manage_app_users.py add --email you@example.com --profile tech --admin
.venv/bin/python manage_app_users.py list
```

## Database privileges

`manage_app_users.py init-schema` and `tools/provision-database.py` create
objects but do not grant access to a restricted service role. Issue the
required grants as the database owner before starting the service. The exact
table and privilege list is `schema_web.REQUIRED_TABLES`; startup verifies it
and reports missing grants. Do not use the owner credential in the long-running
service.

## Run and test

From the repository root, `./dev.sh` serves the webapp and client at
`http://localhost:8421/`. To run only the API from this directory:

```bash
.venv/bin/uvicorn app:app --port 8421
.venv/bin/python -m unittest discover -s tests -t .
```

Use `frontend/serve.py` or `./dev.sh` when testing the browser client; bare
uvicorn does not mount it. Deployment templates are in `deploy/`.

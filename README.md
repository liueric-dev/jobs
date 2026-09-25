# Jobs

A job discovery app. The backend collects postings, extracts shared facts, and
ranks matches for each profile. The webapp serves the API and the browser client.

| Directory | Purpose |
| --- | --- |
| `backend/` | Ingestion, extraction, matching, and scoring pipeline |
| `backend/webapp/` | User accounts and job API |
| `frontend/` | Browser client (plain HTML, CSS, and JavaScript) |
| `actor/` | Dormant Apify actor awaiting redesign |
| `deploy/` | Example systemd and Cloudflare deployment files |

## Local development

The backend uses Python 3.14 and Postgres. Its pipeline and webapp
have separate environments and requirements. See the README in each
directory for setup and environment variables. Copy the relevant `.env.example`
file to `.env`; never commit credentials.

For the webapp and client on one local origin, set up the webapp environment and
database, then run:

```bash
./dev.sh
```

Open `http://localhost:8421/`. `dev.sh` starts the development database with
Docker unless passed `--no-db`. It does not create the schema for you; follow
its error message if the database is empty.

## Checks

Run each Python suite with its own environment:

```bash
cd backend && .venv/bin/python -m unittest discover -s tests -t .
cd webapp && .venv/bin/python -m unittest discover -s tests -t .
```

From the repository root, check the browser client with
`backend/.venv/bin/python frontend/verify_fixtures.py` and
`node frontend/check_client.mjs`. The frontend has no build step.

The actor is retained as reference code for a future redesign. Its current
claim/submit flow requires the removed contributor API and should not be deployed.

## Recovery

The previously tracked documentation and `.claude` configuration are available
at Git tag `archive/pre-simplification-2026-09-24`.

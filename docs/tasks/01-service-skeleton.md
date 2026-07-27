# 01 — Service skeleton

Stand up `backend/webapp/` as a real, runnable service with nothing in it but
configuration, a database helper and a health check. Everything after this
task adds routes to a thing that already starts.

**Depends on:** nothing. **Blocks:** 02.

## Files

```
backend/webapp/
├── app.py              FastAPI app, CORS, lifespan, /v1/health
├── config.py           every env var read, in one place
├── db.py               per-request connection
├── requirements.txt
├── .env.example
└── README.md           (filled in over tasks 02–05)
```

## `config.py`

Read every environment variable here and nowhere else, so the README's
configuration table has a single source and no route can quietly invent a knob.

| Env var | Default | Meaning |
|---|---|---|
| `DATABASE_URL` | *(none — must be set)* | the restricted `jobs_web` role |
| `JOBS_ADMIN_DATABASE_URL` | falls back to `DATABASE_URL` | DDL only, used by the task-02 CLI |
| `GOOGLE_CLIENT_ID` | *(none)* | OAuth client |
| `GOOGLE_CLIENT_SECRET` | *(none)* | OAuth client |
| `GOOGLE_REDIRECT_URI` | `http://localhost:8421/v1/auth/callback` | must match the Cloud Console entry byte-for-byte |
| `FRONTEND_ORIGIN` | `http://localhost:5173` | where the callback sends the browser |
| `ALLOWED_ORIGINS` | `http://localhost:5173` | comma-separated CORS allowlist |
| `SESSION_COOKIE_NAME` | `jobs_session` | |
| `SESSION_COOKIE_SECURE` | `true` | set `false` only for local plain-HTTP dev |
| `SESSION_TTL_DAYS` | `30` | |
| `OAUTH_STATE_TTL_MINUTES` | `10` | |
| `PORT` | `8421` | documentation only; uvicorn takes `--port` |

`DATABASE_URL` has **no default**, matching `lib/dbconn.database_url()`, which
raises when it is unset. The reason is written up in `backend/README.md`
section 2 and is worth not undoing: applications on this Postgres instance are
told apart only by the database named in the URL, and every one of them uses
unqualified table names in `public`. A process that fell back to a plausible
default would not error — it would create its tables inside somebody else's
database.

The three OAuth settings are also defaulted to nothing and are **not** checked
at import time; task 03's routes fail with a legible error instead. That keeps
`/v1/health` and the test suite working on a machine with no Google credentials
at all.

`SESSION_COOKIE_SECURE` parses as a boolean but defaults to **true**: the
insecure setting has to be typed out deliberately, in a file that is already
gitignored.

## `db.py`

One `db()` context manager, lifted from `backend/api/app.py` **including its
docstring**. That comment records a bug that has already been paid for once:

> psycopg's own `with conn:` commits or rolls back but deliberately does NOT
> close — it is designed for reusing a long-lived connection. This service
> opens one per request, so every request was leaking a socket until GC got
> round to it.

`contextlib.closing` alone is not the fix either: it closes without committing.
The working shape is `with conn:` nested inside a `try/finally: conn.close()`.
Copy it; do not re-derive it.

Also `SET search_path TO public` on connect, as `api/app.py` does.

## `app.py`

- The `sys.path` insert that reaches `../schema.py` and `../lib/` together —
  one line, same as `backend/api/query_claims.py`. Put it in `config.py` so
  everything else imports `config` first and inherits the path.
- `CORSMiddleware` with `allow_credentials=True` and the explicit origin list
  from `ALLOWED_ORIGINS`. **Never `allow_origins=["*"]`** — a wildcard and
  credentials are mutually exclusive per the CORS spec, and browsers will drop
  the session cookie rather than tell you why.
  `allow_methods` and `allow_headers` should be the actual sets used, not `*`.
- A `lifespan` that calls task 02's `verify_schema()` before serving. Until
  that exists, an empty lifespan is fine.
- `docs_url=None, redoc_url=None`, as `api/app.py` sets — this is not a public
  API and the schema page is one more thing to think about.
- `GET /v1/health` → `{"ok": true}`. No database call: it answers "is this
  process up", and a database probe belongs in the startup check, which
  already refuses to serve without one.

## `requirements.txt`

```
fastapi>=0.115
uvicorn[standard]>=0.30
psycopg[binary]>=3.1
pydantic>=2.7
httpx>=0.27
```

Five, and the plan is that it stays five — `httpx` is the only addition over
`api/requirements.txt`, and it is there for exactly one call in task 03 (the
POST to Google's token endpoint). Task 03 explains why no JWT library is
needed. Note that `include-system-site-packages = false` in this venv, like
`api/`'s, so anything missing here is missing at runtime and nowhere else;
`api/README.md` has the story of the last time that bit someone.

## `.env.example`

Same conventions as the other two in this repo: a header explaining the format,
one `KEY=value` per line, comments on their own line only. Track the example,
never the `.env`. The root `.gitignore` already covers `.env` and `.env.*` with
a `!.env.example` exception, so no change is needed there.

## Verify

```bash
cd backend/webapp
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
cp .env.example .env && chmod 600 .env
.venv/bin/uvicorn app:app --port 8421 --reload
curl -s localhost:8421/v1/health          # {"ok":true}
```

With `DATABASE_URL` unset, the service must fail with a named error rather than
connecting to something plausible.

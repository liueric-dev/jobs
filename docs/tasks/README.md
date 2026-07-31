# docs/tasks/

Work breakdown for closing the gap named at the top of
[`backend/docs/DEVELOPER.md`](../../backend/docs/DEVELOPER.md): the pipeline
scores every job it ingests and delivers none of them.

These five tasks build `backend/webapp/` — the HTTP service `frontend/` will
talk to — and stop at the point where a browser can sign in with Google and
read that user's ranked jobs. They are ordered; each assumes the one before it
has landed.

| | Task | Lands | |
|---|---|---|---|
| 01 | [Service skeleton](job_ingest/01-service-skeleton.md) | a running FastAPI app with config, DB helper, CORS and `/v1/health` | done |
| 02 | [Auth schema and role](job_ingest/02-auth-schema-and-role.md) | `app_users` / `app_sessions` / `oauth_logins`, the `jobs_web` role, the admin CLI | done |
| 03 | [Google SSO](job_ingest/03-google-sso.md) | the OAuth redirect flow, session cookies, `require_user` | done |
| 04 | [Read endpoints](job_ingest/04-read-endpoints.md) | `GET /v1/jobs`, `GET /v1/jobs/{id}`, `POST /v1/events` | done |
| 05 | [Tests and docs](job_ingest/05-tests-and-docs.md) | unit tests, service README, doc updates | done |

All five landed 2026-07-26 in `backend/webapp/`. The one step no automated
check can cover is the live Google login — the Cloud Console client has to be
created by hand and the round trip driven in a browser. That checklist is in
task 05 and in `backend/webapp/README.md`.

## The three decisions these tasks encode

Taken 2026-07-26, before any code was written. Don't re-litigate them without
new facts.

**A new service, not an extension of `backend/api/`.** That directory is the
*contributor* API: a machine-to-machine work queue for volunteers who submit
SerpApi results, whose entire design assumes the caller is hostile and whose
`jobs_api` Postgres role is deliberately granted **nothing** on the seven
pipeline-owned tables (`backend/api/README.md`, "Database privileges" — three
sections of that README exist to defend this boundary, and it was tightened as
recently as the move off the shared superuser). A logged-in-user API needs
`SELECT` across all of those, so putting it there would mean relaxing the one
property that README is about. `backend/api/` is also expected to be
deprecated, so `backend/webapp/` imports nothing from it — only `../schema.py`
and `../lib/`.

**Server-side OAuth, opaque session cookie.** The backend owns the whole
redirect flow and hands the browser an `HttpOnly` cookie whose `sha256` is what
the database stores. No token ever reaches JavaScript, sessions are revocable,
and the frontend needs no Google SDK — which keeps the framework choice open,
since `frontend/` is still empty.

**Email allowlist.** Google authenticates; it does not authorise. An
`app_users` row must already exist or the login is refused. The alternative —
auto-provisioning a profile per Google account — is open signup, and every
active profile costs real money: `extract.py` and `score.py` both fan out per
active profile.

## What already exists, and must not be rebuilt

The pipeline did most of the data work already:

- **`jobs_app`** (`backend/schema.py`) — one row per (job × profile), already
  joining `jobs` + `job_facts` + `job_matches` + `job_scores`, already dropping
  rows with no company/title/url/description, already ordered
  match-score-then-recency. The list view is a `SELECT` from this view.
- **`job_events`** (`backend/schema.py`) — written by nothing today.
  `backend/docs/SCORING.md` lists its writer as "the surfacing layer", which is
  task 04. `score.py`'s nightly warm pass already reads it, so logging
  engagement feeds straight back into which profiles get narratives written.
- **`profiles`** — already one row per user. `profiles.load_one()` serves
  paused profiles deliberately, "because the login path needs to serve a
  profile". This is that login path.

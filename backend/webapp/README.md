# jobs-webapp

The application backend: what `frontend/` talks to.

The pipeline one directory up finds and scores jobs and delivers none of them —
the gap at the top of [`../docs/DEVELOPER.md`](../docs/DEVELOPER.md). This is
the delivery half. A person signs in with Google, reads their profile's ranked
jobs out of the `jobs_app` view, and their interactions land in `job_events`,
which nothing has ever written and which `../score.py` already reads.

```
browser ──Google SSO──▶ auth.py ──session cookie──▶ jobs.py ──▶ jobs_app  (read)
                                                          └──▶ job_events (append)
```

## Why this is not part of `../api/`

That directory is the **contributor** API: a machine-to-machine work queue for
volunteers who submit SerpApi results on their own quota. Its whole design
assumes the caller is hostile, and its `jobs_api` role is deliberately granted
*nothing* on the seven pipeline-owned tables — three sections of its README
exist to defend that boundary. Serving logged-in users needs SELECT across all
of them, so putting these routes there would mean relaxing the one property
that README is about.

So: a second process with a second database identity, sharing `../schema.py`
and `../lib/` and importing nothing from `api/`. The two do not talk.

## Setup

```bash
cd backend/webapp
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
cp .env.example .env && chmod 600 .env      # fill in DATABASE_URL + the Google client

# once, with an admin credential -- the only command that issues DDL
JOBS_ADMIN_DATABASE_URL=postgresql://jobs_pipeline:pass@localhost:5432/jobs \
  .venv/bin/python manage_app_users.py init-schema

# once, as the database owner -- see "Database privileges" below
psql -d jobs -f - <<'SQL'
CREATE ROLE jobs_web LOGIN PASSWORD 'CHANGEME';
GRANT CONNECT ON DATABASE jobs TO jobs_web;
GRANT USAGE ON SCHEMA public TO jobs_web;
GRANT SELECT ON public.jobs_app, public.jobs, public.job_matches,
                 public.job_scores, public.job_facts, public.profiles TO jobs_web;
GRANT SELECT, INSERT ON public.job_events TO jobs_web;
GRANT USAGE, SELECT ON SEQUENCE public.job_events_id_seq TO jobs_web;
GRANT SELECT, INSERT, UPDATE ON public.app_users TO jobs_web;
GRANT SELECT, INSERT, UPDATE, DELETE ON public.app_sessions TO jobs_web;
GRANT SELECT, INSERT, DELETE ON public.oauth_logins TO jobs_web;
SQL

.venv/bin/python manage_app_users.py add --email you@gmail.com --profile tech --admin
.venv/bin/uvicorn app:app --port 8421
```

Schema creation is a **deliberate, separate step**, not something the service
does at startup — the same split `api/` uses. `init-schema` is additive only
and never rewrites a column the pipeline owns. The service connects as a role
with no DDL rights and refuses to start if the schema or its grants are
missing, naming what is absent.

### Allowing someone in

```bash
.venv/bin/python manage_app_users.py add --email dave@gmail.com --profile tech
.venv/bin/python manage_app_users.py list
.venv/bin/python manage_app_users.py disable --email dave@gmail.com
.venv/bin/python manage_app_users.py revoke-sessions --email dave@gmail.com
```

`--profile` is which pipeline profile they see; it is validated against the
`profiles` table at insert time. `disable` takes effect on the user's **next
request**, not at their next login, because `require_user` re-reads `app_users`
every time.

## Google Cloud Console

None of this is code and all of it blocks the first login.

1. Create a project, then configure the **OAuth consent screen** (External
   unless you have a Workspace domain).
2. While the consent screen is unverified, add every allowlisted address to
   **Test users**. **There are two allowlists during development and they have
   to agree** — Google's test-user list and `app_users`. Only one of the two
   failures produces an error message from this service; the other is a Google
   error page you never see the cause of.
3. **Credentials → Create OAuth client ID → Web application.**
4. The **Authorized redirect URI** must equal `GOOGLE_REDIRECT_URI`
   byte-for-byte, trailing slash included. Add the localhost one and the
   deployed one.
5. Copy the client id and secret into `.env`.

## API

Everything except `/v1/health` and the two `/v1/auth` entry points requires the
session cookie.

| Endpoint | Purpose |
|---|---|
| `GET /v1/health` | liveness |
| `GET /v1/auth/login?next=/path` | 302 to Google |
| `GET /v1/auth/callback` | Google's redirect target; sets the session cookie |
| `POST /v1/auth/logout` | revoke the session, clear the cookie |
| `GET /v1/me` | `{email, display_name, profile, is_admin}` |
| `GET /v1/jobs` | this profile's ranked jobs, keyset-paginated |
| `GET /v1/jobs/{id}` | one job, with the full description |
| `POST /v1/events` | record interactions |

`GET /v1/jobs` takes `limit` (≤100), `cursor`, `q`, `remote`, `nyc`,
`min_score`, `since` and `exclude_dismissed`, and returns
`{jobs, next_cursor, profile}`. Field names are the `jobs_app` column names
unchanged, plus four booleans per row — `seen`, `saved`, `dismissed`,
`applied` — for this profile.

Pagination is **keyset, not offset**: the list is re-ranked nightly whenever
`match.py` rebuilds `job_matches`, and an offset taken before a re-rank and
used after silently skips or repeats rows. Pass the `next_cursor` back.

`POST /v1/events` takes `{"events": [{"job_id": ..., "event": ...}]}` and
returns `{recorded, deduped, skipped}`. `event` must be one of `impression`,
`open`, `save`, `unsave`, `dismiss`, `applied`.

## Security model

- **The allowlist is the access control.** Google authenticates; it does not
  authorise. A valid Google login for an address with no `app_users` row is
  **403**, and no row is created. This is not an oversight to fix by
  auto-provisioning: every active profile costs real money, because
  `extract.py` and `score.py` both fan out per active profile.
- **Sessions are opaque, hashed and revocable.** The cookie is 256 bits of
  `secrets.token_urlsafe`; the database stores only `sha256` of it, so a dump
  yields no working session. Revocation is one UPDATE — which is the reason
  these are database rows rather than signed tokens.
- **The cookie is `HttpOnly`, `SameSite=Lax`, `Secure` by default.** No token
  ever reaches JavaScript. `Lax` rather than `Strict` because the OAuth
  callback is a top-level cross-site navigation and `Strict` would drop the
  cookie on the one request that sets it.
- **PKCE state is single-use and server-side.** `oauth_logins` rows are
  redeemed with one `DELETE ... RETURNING`, so replay protection is a property
  of the primary key rather than of code someone has to keep correct.
- **`next` is validated to a local path.** The only place in this service where
  an open redirect could happen; `//evil.com` is the case it exists for.
- **The profile comes from the session, never from a parameter.** That is the
  whole tenancy model. A `?profile=` parameter would make one forgotten check a
  cross-user leak.
- **Event scores are derived server-side.** `match_score` and `fit_score` are
  looked up from `job_matches` / `job_scores` at write time and never accepted
  from the client — `../docs/SCORING.md` makes recording them *as of the
  impression* the load-bearing property of the whole table, and a
  client-supplied score is unverifiable training data.

### The one place a dependency was not added

`auth.py` validates the `id_token`'s claims without verifying its signature,
and that is safe **only** because the token is read from the direct,
TLS-authenticated response to this service's own client-secret-authenticated
POST to Google's token endpoint — the case Google's documentation exempts. It
is never read from a request body, header or query parameter.

**The exemption is void for the other shape of this flow.** A frontend
Google-Identity-Services button POSTing an `id_token` to the backend needs full
JWKS signature verification, and `_claims_from_id_token()` must not be reused
for it. If that day comes, add the library then.

## Database privileges

This service connects as `jobs_web`, which can read the corpus, append
engagement, and rewrite nothing.

| Object (database `jobs`, schema `public`) | Granted |
|---|---|
| `jobs_app`, `jobs`, `job_matches`, `job_scores`, `job_facts`, `profiles` | SELECT |
| `job_events` | SELECT, INSERT |
| `job_events_id_seq` | USAGE, SELECT |
| `app_users` | SELECT, INSERT, UPDATE |
| `app_sessions` | SELECT, INSERT, UPDATE, DELETE |
| `oauth_logins` | SELECT, INSERT, DELETE |

- **No UPDATE or DELETE on any pipeline table.** A session-hijacking bug or an
  injection here costs reads and event rows, not the corpus. Verified: as
  `jobs_web`, `UPDATE job_scores SET fit_score = 0` is denied.
- **`jobs` needs SELECT even though only `jobs_app` is queried.** A plain view
  runs with the caller's privileges — it is not a security barrier — so
  granting on the view alone fails at the first request, not at deploy time.
- **No CREATE.** DDL runs only through `manage_app_users.py init-schema` and
  its separate admin credential.
- **Nothing on `api/`'s tables** (`contributors`, `api_keys`,
  `submission_log`) and nothing on the events database.

The grants are re-creatable from `schema_web.REQUIRED_TABLES` and
`REQUIRED_SEQUENCES`, which are the source of truth for the startup check, the
table above, and `tests/test_grants.py`. That test asserts every table named in
this package's SQL appears in `REQUIRED_TABLES` — because a route that queries
an ungranted table produces a service that starts cleanly and 500s on that one
request, in production. `api/` closed the identical gap by adding
`REQUIRED_SEQUENCES` after a documented-but-unverified grant surfaced as a 500
on a contributor's first submit.

`job_events_id_seq` needs USAGE despite the table only being appended to:
`job_events.id` is BIGSERIAL, so `nextval()` is a separate privilege from
INSERT, and its absence is a runtime error rather than a startup one unless it
is checked.

## Configuration

| Env var | Default | Meaning |
|---|---|---|
| `DATABASE_URL` | *(none — required)* | the restricted `jobs_web` role |
| `JOBS_ADMIN_DATABASE_URL` | falls back to `DATABASE_URL` | DDL only, for `init-schema` |
| `GOOGLE_CLIENT_ID` | *(none)* | OAuth client; `/v1/auth/login` 503s without it |
| `GOOGLE_CLIENT_SECRET` | *(none)* | OAuth client |
| `GOOGLE_REDIRECT_URI` | `http://localhost:8421/v1/auth/callback` | must match the console entry byte-for-byte |
| `FRONTEND_ORIGIN` | `http://localhost:5173` | where the callback sends the browser |
| `ALLOWED_ORIGINS` | `http://localhost:5173` | comma-separated CORS allowlist |
| `SESSION_COOKIE_NAME` | `jobs_session` | |
| `SESSION_COOKIE_SECURE` | `true` | `false` only for local plain-HTTP dev |
| `SESSION_TTL_DAYS` | `30` | sliding, refreshed past half-life |
| `OAUTH_STATE_TTL_MINUTES` | `10` | how long a started login stays redeemable |
| `PORT` | `8421` | documentation only; uvicorn takes `--port` |

`DATABASE_URL` has no default anywhere in this repo. Applications on this
Postgres instance are told apart only by the database named in the URL and all
of them use unqualified table names in `public`, so a process that fell back to
a plausible default would not error — it would work, against someone else's
data.

## Tests

```bash
.venv/bin/python -m unittest discover -s tests -t .
```

Stdlib `unittest`, no live database and no Google client — deliberately. The
suite covers what is logic rather than I/O: the open-redirect guard, every
`id_token` rejection, session hashing, the event vocabulary, the cursor
encoding, and the grant/SQL parity check. The I/O halves are the manual
checklist below; a test suite that needs a client secret to run is a test suite
nobody runs.

## Deployment (manual — not automated by this repo)

**No credential is stored in this repo.** `DATABASE_URL` and the Google client
secret live in `.env` (mode 600, gitignored) — see `.env.example`.

### Phase 1 — localhost / tailnet

Works as-is. Set `SESSION_COOKIE_SECURE=false` **only** if you are serving over
plain HTTP on localhost, and change it back for anything else.

### Phase 2 — reachable from a browser you don't own

1. **Terminate TLS.** The session cookie is a bearer credential; over plaintext
   HTTP it leaks on every request. With TLS in place, `SESSION_COOKIE_SECURE`
   must be `true` — its whole job is to stop the browser sending the cookie in
   the clear.
2. **Add the deployed redirect URI to the Google console**, and set
   `GOOGLE_REDIRECT_URI` to match byte-for-byte. A mismatch is a Google error
   page, not an error from this service.
3. **Set `ALLOWED_ORIGINS`** to the real frontend origin. Once the frontend is
   served from the same origin as this service, CORS stops being involved at
   all and the list can be empty.
4. **Firewall Postgres** so it doesn't become reachable just because the host
   did.
5. Run under a supervisor (systemd unit or container) so it restarts.

### Known gaps

- **`oauth_logins` is pruned opportunistically**, on each callback. A burst of
  started-but-abandoned logins between callbacks leaves rows until the next
  one. Harmless — they are single-use and expiry-checked — but it is not a
  bounded table under an adversary who can hit `/v1/auth/login` in a loop, and
  that endpoint is unauthenticated by necessity. Rate-limit it at the proxy
  before exposing this publicly.
- **No CSRF token on `POST /v1/events`.** `SameSite=Lax` blocks the
  cross-site POST that would need, which is sufficient for current browsers;
  a token would be belt-and-braces.

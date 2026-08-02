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
                 public.job_scores, public.job_facts, public.profiles,
                 public.cohort_signal TO jobs_web;
GRANT SELECT, INSERT ON public.job_events TO jobs_web;
GRANT USAGE, SELECT ON SEQUENCE public.job_events_id_seq TO jobs_web;
GRANT SELECT, INSERT, UPDATE ON public.app_users TO jobs_web;
GRANT SELECT, INSERT, UPDATE, DELETE ON public.app_sessions TO jobs_web;
GRANT SELECT, INSERT, DELETE ON public.oauth_logins TO jobs_web;
GRANT SELECT, INSERT, UPDATE ON public.builder_job_state TO jobs_web;
GRANT SELECT, INSERT, UPDATE ON public.builder_profiles TO jobs_web;
-- Searches (task 25). Note what is NOT here: no UPDATE on search_queries (the
-- run statistics and the decay flag are the pipeline's), and nothing at all
-- beyond SELECT on search_query_signal, which carries the exposed watcher
-- bucket. The suppression rule lives in the nightly fold and this role must not
-- be able to write a bucket it did not compute.
GRANT SELECT, INSERT ON public.search_queries TO jobs_web;
GRANT USAGE, SELECT ON SEQUENCE public.search_queries_id_seq TO jobs_web;
GRANT SELECT, INSERT, UPDATE ON public.search_query_watchers TO jobs_web;
GRANT SELECT ON public.search_query_signal, public.search_query_results TO jobs_web;
GRANT SELECT ON public.eval_label_sets, public.eval_label_items TO jobs_web;
GRANT SELECT, INSERT ON public.eval_labels TO jobs_web;
GRANT USAGE, SELECT ON SEQUENCE public.eval_labels_id_seq TO jobs_web;
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
| `GET /v1/label` | the golden-set labelling form (HTML) |
| `POST /v1/label` | record one person's answers, then serve the next posting |
| `GET /v1/label/progress` | `{label_set, done, total}` for the signed-in labeller |

`GET /v1/jobs` takes `limit` (≤100), `cursor`, `q`, `remote`, `nyc`,
`min_score`, `since` and `include_dismissed`, and returns
`{request_id, jobs, next_cursor, profile}`. Field names are the `jobs_app`
column names unchanged, then five per-Builder state fields — `seen`, `applied`,
`dismissed`, `saved` and the nullable `dismiss_reason` — then `cohort_signal`,
then `rank`. **All of them are flat on the job object.** The nesting under
`comp{}` / `why{}` / `state{}` that `API-CONTRACT-v1.md` describes is the target
shape and is not what ships.

> **Corrected 2026-08-02; the struck version is below because a client written
> against it fails in ways that look like server bugs.** Six claims here were
> wrong:
>
> | said | is |
> |---|---|
> | ~~`exclude_dismissed`~~ | **`include_dismissed`**, default `False`. Task 31 renamed it: the old one defaulted to *showing* dismissed rows, so a dismissal meant nothing unless the client opted in. The old name is silently ignored by FastAPI |
> | ~~`{jobs, next_cursor, profile}`~~ | **four keys** — `request_id` rides beside them, and an event that does not echo it 400s with `missing_request_id` |
> | ~~"four booleans"~~ | **five fields, four of them boolean**; `dismiss_reason` is a nullable string |
> | ~~"for this profile"~~ | **per Builder.** Resolving these by profile *was* defects D66 and D67 — thirty Builders share `pursuit`, so one Builder's save read as everyone's. "For this profile" describes the defect, not the fix |
> | ~~`{recorded, deduped, skipped}`~~ | **four keys** — `derived_skips` too |
> | ~~event list~~ | missing **`undismiss`** |
>
> `cohort_signal` is new (task 28) and is `{"save_bucket": "3-5"\|"6-10"\|"10+"}`
> or `null`. **A null is a privacy suppression, not an absence of data** — the
> count is withheld below three Builders, because in a thirty-person cohort who
> see each other in a classroom a count of one is close to an identifier. Do not
> render it as "0 saves".

Pagination is **keyset, not offset**: the list is re-ranked nightly whenever
`match.py` rebuilds `job_matches`, and an offset taken before a re-rank and
used after silently skips or repeats rows. Pass the `next_cursor` back. `rank`
is 1-based and **continues across pages** — the render id and the next rank ride
inside the opaque cursor, so page two starts at 5, not 1.

`POST /v1/events` takes `{"events": [{"job_id": ..., "event": ...}]}` and
returns `{recorded, deduped, skipped, derived_skips}`. `event` must be one of
`impression`, `open`, `save`, `unsave`, `dismiss`, `undismiss`, `applied`.
`skip` is **server-derived** and sending it is a 400.

**This is the operator's summary, not the client author's contract.**
[`../../frontend/README.md`](../../frontend/README.md) § *Things a client author
will get wrong if nobody says them* owns that list — the two error envelopes, the
four fields that arrive as JSON strings rather than arrays, and the rest — and it
is derived from the code by `frontend/verify_fixtures.py`. Read it before writing
a client; do not restate it here, or there will be two of it.

## The labelling surface — `/v1/label`

The golden set (`../evals/labels.py`, task 07) needs judgements from ~10
Builder volunteers, not from whoever wrote the harness. This is where they make
them.

**It is server-rendered HTML with no JavaScript.** Not a JSON endpoint: a
volunteer cannot use one. ~~`frontend/` currently contains a single file called
`.gitkeep`, so there is nothing to render a form.~~ A `<form>`, a POST and
a 303 to the next posting works today and keeps working when `frontend/` is
eventually filled with something opinionated.

> **`frontend/` was filled 2026-08-02 (task 32), and the decision above is
> unchanged — now by choice rather than by absence.** That client has Today, Job
> detail and Saved and **no labelling screen**, and one is not planned there: the
> golden set is an operator-and-volunteer surface, not a Builder one. The last
> clause is now testable rather than hypothetical, and it holds — the client is
> plain HTML/CSS/ES-modules with no build step, so nothing about it makes a
> `<form>` and a 303 any harder to keep.

### What a Builder actually does

1. The operator adds them: `manage_app_users.py add --email them@gmail.com
   --profile pursuit`. The allowlist is still the access control — no row, no
   entry, and no row is ever auto-created.
2. While the OAuth consent screen is unverified, they also go in the Google
   console's **Test users** list. **Two allowlists that have to agree** — see
   "Google Cloud Console" above; only one of the two failures produces an error
   message from this service.
3. They are sent one link: `https://<this service>/v1/label`.
4. Signed out, that URL **302s to Google** rather than returning 401. A 401 is
   right for `/v1/jobs`, which a frontend calls and handles; this is a URL
   somebody pastes out of an email.
5. They see one posting's full text and five questions, answer, press **Save
   and next**, and repeat. Every question has an *I can't tell from this
   posting* option, and it is not the same thing as "no".
6. When the set is finished the page says so and stops.

No terminal, no checkout, no credential, nothing installed.

**`FRONTEND_ORIGIN` must point at the origin serving `/v1/label`.** The OAuth
callback redirects to `FRONTEND_ORIGIN + next_path` (`auth.py:359`), so with
the default `http://localhost:5173` a labeller completes the Google round trip
and lands on a frontend that does not exist yet. Set it to this service's own
origin for a labelling deployment. This is the one configuration step that is
easy to miss and produces a confusing failure — the sign-in *works*, and the
browser then shows nothing.

### What is recorded

`app_users.id`, never the email: an opaque id is all the inter-annotator
computation needs, and every JSONL this produces gets exported and quoted.
`profile` comes from the session, never from the form — the same tenancy rule
`jobs.py:5` states, and here it is also what makes axis-B rows attributable to
a cohort and droppable with it.

Answers are validated against `extract.py`'s own vocabularies, read at render
time rather than copied. A label recorded as `"Mid-Level"` could not be
compared against a `job_facts` row holding `"mid"` — it would score formatting.

`eval_labels` is **append-only to this service** (SELECT, INSERT; no UPDATE, no
DELETE). A revised judgement is round 2, which is exactly what the
intra-annotator measurement reads; quietly replacing round 1 would destroy it.
A repeat submission of the same round is a no-op, enforced by the partial
unique indexes rather than by code here.

### Upgrading an existing deployment

The startup check now covers three more tables, so **a service that has not run
`init-schema` since this landed will refuse to start**, naming them. That is
the intended behaviour (see "Database privileges"), and the fix is two steps:

```bash
JOBS_ADMIN_DATABASE_URL=... .venv/bin/python manage_app_users.py init-schema
psql -d jobs -c "
GRANT SELECT ON public.eval_label_sets, public.eval_label_items TO jobs_web;
GRANT SELECT, INSERT ON public.eval_labels TO jobs_web;
GRANT USAGE, SELECT ON SEQUENCE public.eval_labels_id_seq TO jobs_web;"
```

**2026-08-02 adds two more tables, and one of them is not created by this
service.** `builder_profiles` (task 26) is created by `init-schema` like the
rest. **`cohort_signal` (task 28) is pipeline-owned** — it is declared in
`backend/schema.py` and created by the pipeline's `ensure_schema()`, so
`init-schema` does not create it and the GRANT below will fail with *"relation
does not exist"* until a nightly run, or any pipeline script, has been through.
That ordering is the same one the column check exists for: the two processes
migrate on different schedules.

```bash
JOBS_ADMIN_DATABASE_URL=... .venv/bin/python manage_app_users.py init-schema
psql -d jobs -c "
GRANT SELECT, INSERT, UPDATE ON public.builder_profiles TO jobs_web;
GRANT SELECT ON public.cohort_signal TO jobs_web;"
```

No sequence grant for either. `builder_profiles` is keyed `PRIMARY KEY
(app_user_id)` on a TEXT column and `cohort_signal` on `(job_id,
cohort_profile)` — neither has a `BIGSERIAL`, which is why `REQUIRED_SEQUENCES`
is unchanged. `cohort_signal` is **SELECT-only on purpose**: the suppression
threshold is computed by the pipeline's nightly fold and this service must not
be able to write a bucket it did not compute.

Then draw a set, from the pipeline side:

```bash
cd backend && python3 -m evals label sample --n 60 --overlap 20
```

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
| `builder_job_state` | SELECT, INSERT, UPDATE |
| `eval_label_sets`, `eval_label_items` | SELECT |
| `eval_labels` | SELECT, INSERT |
| `eval_labels_id_seq` | USAGE, SELECT |

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

## Deployment

**~~Manual — not automated by this repo~~ — automated as of task 33.** The
systemd unit (`deploy/systemd/jobs-webapp.service`), the tunnel ingress rule
(`deploy/cloudflared/config.yml`) and the install sequence are tracked in
[`deploy/`](../../deploy/README.md). Operations — restarting this service,
rotating the Google client secret, what a `curl` that works on `localhost` and
fails through the tunnel means — are in
[`docs/RUNBOOK.md`](../../docs/RUNBOOK.md).

**No credential is stored in this repo.** `DATABASE_URL` and the Google client
secret live in `.env` (mode 600, gitignored) — see `.env.example`. Rotating
either is an edit plus `systemctl --user restart jobs-webapp.service`; nothing
is rebuilt and no tracked file changes. `backend/tests/test_secrets_rotation.py`
pins that property rather than trusting it.

### Phase 1 — localhost / tailnet

Works as-is. Set `SESSION_COOKIE_SECURE=false` **only** if you are serving over
plain HTTP on localhost, and change it back for anything else.

### Phase 2 — reachable from a browser you don't own

Task 33 chose **Cloudflare Tunnel** over Tailscale Funnel and over
Caddy/nginx-plus-a-forwarded-port; `../api/README.md` § *Deployment* carries the
argument, which applies identically here and is not restated. One hostname
serves this service, and the page, and the API the page calls.

1. **TLS is terminated by the tunnel**, so `SESSION_COOKIE_SECURE` stays `true`
   — its whole job is to stop the browser sending the session cookie in the
   clear, and the cookie is this client's only credential.
2. **Add the deployed redirect URI to the Google console**, and set
   `GOOGLE_REDIRECT_URI` to match byte-for-byte. A mismatch is a Google error
   page, not an error from this service — which means it looks like Google is
   broken rather than like a config line is wrong. **Only the owner can do
   this**; it is a console click, not a file.
3. **Set `FRONTEND_ORIGIN`** to the deployed origin. `ALLOWED_ORIGINS` can then
   be empty: `frontend/serve.py` mounts the page on this service's *own* origin
   deliberately, so CORS stops being involved at all. A third origin that
   neither variable names gets its cookie dropped by the browser **silently**,
   which is why the client is not served from a second dev server.
4. **Bind to `127.0.0.1`, not `0.0.0.0`.** `cloudflared` connects from this same
   host; binding wider only widens the LAN surface.
   `deploy/systemd/jobs-webapp.service` does this.
5. **Firewall Postgres** so it doesn't become reachable just because the host
   did.
6. Run under a supervisor — `deploy/systemd/jobs-webapp.service`, with
   `Restart=always` and systemd's start-limit removed so a flapping restart
   cannot disable the unit and lock the cohort out.

**The tunnel is not an authorization layer.** Anyone on the internet can reach
the hostname; the Google OAuth session is the only thing keeping strangers out
of the app, and the *Known gaps* below are the places that matters.

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

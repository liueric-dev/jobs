---
kind: task
written: 2026-07-27
generator: none
---

# 05 — Tests and docs

**Depends on:** 04.

## Tests

`backend/webapp/tests/`, stdlib `unittest` like `backend/tests/`, run with the
service's own venv:

```bash
cd backend/webapp && .venv/bin/python -m unittest discover -s tests -t .
```

These cover the parts that are **logic rather than I/O** — no live Postgres, no
live Google. That is a deliberate limit, not laziness: the flow's I/O halves are
covered by the manual checklist below, and a test suite that needs an OAuth
client secret to run is a test suite nobody runs.

| File | Pins |
|---|---|
| `test_next_path.py` | `//evil.com`, `https://evil.com`, `\\evil.com` and a bare `evil.com` all fall back to `/`; ordinary paths and query strings survive intact |
| `test_id_token.py` | claim validation rejects wrong `aud`, wrong `iss`, expired `exp`, mismatched `nonce`, `email_verified: false`, and a missing `email` — one test per rejection, built from handcrafted payloads |
| `test_sessions.py` | the cookie value never appears in what is stored; `sha256` round-trips; an expired or revoked row does not authenticate |
| `test_events.py` | the event-name allowlist rejects anything outside the closed set, and the impression-dedup window is 24h |
| `test_grants.py` | every table named in the service's SQL appears in `REQUIRED_TABLES` |

`test_grants.py` is the one worth explaining. `REQUIRED_TABLES` drives both the
startup check and the README's grant table, so a route that starts querying a
new table without adding it there produces a service that starts cleanly and
500s on that one request in production. Grepping the modules' SQL for table
names and asserting the set is covered turns that into a test failure. It is the
same class of gap `api/` closed by adding `REQUIRED_SEQUENCES` — a documented
grant that nothing verified.

Also confirm the pipeline's own guard is untouched:

```bash
cd backend && python3 -m unittest discover -s tests -t .
```

The added index from task 02 is the only pipeline change and should disturb
nothing.

## `backend/webapp/README.md`

Written across tasks 01–04, finished here. Sections:

- **What this is** — the frontend's backend, and one line on why it is not
  `api/` (that service is the contributor work queue, assumes a hostile caller,
  and is expected to be deprecated).
- **Setup** — venv, `.env`, `init-schema`, the `jobs_web` role SQL, `add` a
  user, run uvicorn. In runnable order, like `api/README.md`.
- **Google Cloud Console** — the checklist from task 03, including the
  test-users trap while the app is unverified.
- **API** — one table of endpoints.
- **Security model** — allowlist not signup; sessions are opaque, hashed and
  revocable; scores derived server-side; profile from the session only; the
  grant table.
- **Configuration** — the env table from task 01.
- **Deployment** — same two-phase shape as `api/README.md`: local/tailnet
  first, then TLS. Flag the two settings that must change for a public
  deployment (`SESSION_COOKIE_SECURE=true`, real `ALLOWED_ORIGINS`) and the one
  that must not be reused (`GOOGLE_REDIRECT_URI` must match the console entry).

## Doc updates elsewhere

**`backend/docs/DEVELOPER.md`** — the "No surfacing layer yet" bullet is the
first line of the Open Questions section and has been the headline gap for
months. It becomes "in progress", naming `backend/webapp/` and what now exists
(auth + read API) versus what does not (the frontend itself). Do not delete it;
the gap is not closed until something renders.

**Root `README.md`** — the table says `frontend/` is "not started" and the
prose says "Deliberately empty". Both are still true of `frontend/`, but the
backend half now exists. Add `backend/webapp/` to the layout and note that the
API it needs is live.

**`docs/tasks/README.md`** — mark the tasks done.

## Manual end-to-end checklist

The half no unit test covers. Run it once, in order, against a live database
and a real Google client — it is the acceptance criterion for the whole
sequence.

1. `curl -s localhost:8421/v1/health` → `{"ok": true}`.
2. `REVOKE SELECT ON job_matches FROM jobs_web` → the service **refuses to
   start**, naming the missing privilege. Restore it.
3. Browser → `/v1/auth/login` → consent → back at `FRONTEND_ORIGIN` with an
   `HttpOnly` cookie. `/v1/me` returns your email and profile.
4. A Google account not on the allowlist → 403, no row created.
5. `/v1/jobs?limit=5` matches the equivalent `SELECT` from `jobs_app`.
6. A `save` lands in `job_events` **with `match_score` snapshotted**; a repeated
   `impression` does not.
7. Logout → the previous cookie 401s.
8. As `jobs_web`, `UPDATE job_scores SET fit_score = 0` → permission denied.

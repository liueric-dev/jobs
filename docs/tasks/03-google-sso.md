# 03 — Google SSO and sessions

The only way into this application. Google authenticates; the `app_users`
allowlist from task 02 authorises.

**Depends on:** 02. **Blocks:** 04.

## Files

```
backend/webapp/auth.py     the flow, the session helpers, require_user
backend/webapp/README.md   + the Cloud Console checklist
```

## The flow

Authorization Code with PKCE, driven entirely by the backend. The browser gets
an opaque cookie; no token ever reaches JavaScript.

### `GET /v1/auth/login?next=/some/path`

1. Generate `state`, `nonce`, and a PKCE `code_verifier` — all
   `secrets.token_urlsafe(32)`.
2. Validate `next` and store the row in `oauth_logins` with an
   `OAUTH_STATE_TTL_MINUTES` expiry.
3. 302 to `https://accounts.google.com/o/oauth2/v2/auth` with
   `response_type=code`, `scope=openid email profile`,
   `code_challenge_method=S256`, `code_challenge=BASE64URL(SHA256(verifier))`,
   `state`, `nonce`, `prompt=select_account`, and `redirect_uri` taken from
   config.

**`next` must be validated as a local path**, and this is the only place in the
service where an open redirect can happen. Accept it only if it starts with a
single `/` and not `//` (`//evil.com` is a protocol-relative URL that browsers
follow off-site), and reject anything containing a scheme or a backslash.
Anything that fails validation becomes `/`, silently — a failed redirect target
is not worth a 400 in the middle of a login.

### `GET /v1/auth/callback?code=&state=`

1. Redeem the `oauth_logins` row with a single `DELETE ... RETURNING`. A
   replayed or forged `state` finds no row → 400. Check `expires_at` on what
   comes back.
2. `POST https://oauth2.googleapis.com/token` over `httpx` with the client id,
   client secret, code, verifier and redirect URI.
3. Validate the returned `id_token`'s claims:
   - `aud` == `GOOGLE_CLIENT_ID`
   - `iss` in `{"accounts.google.com", "https://accounts.google.com"}`
   - `exp` in the future (with a small leeway for clock skew)
   - `nonce` == the nonce from the redeemed row
   - `email_verified` is true, and `email` is present

   Any failure → 401, with the reason in the log and *not* in the response.
4. Resolve the user (below).
5. Mint the session and 302 to `FRONTEND_ORIGIN + next_path`.

### User resolution — `sub` before email

Look up `google_sub` first; only if that misses, look up `lower(email)` and
bind the `sub` onto that row as part of the first successful login.

The order matters. Google's `sub` is the stable identifier for an account;
an email address is not — inside a Workspace domain it can be reassigned to a
different person. Matching on email alone would hand the new holder of a
recycled address the previous holder's session history and job profile. Once
`sub` is bound, email changes are harmless.

**No row, or `active = false` → 403, and no row is created.** Not 401: the
caller authenticated successfully, they are simply not allowed in, and a 401
would invite the frontend to retry the login loop forever. The allowlist is the
entire access-control model — see `docs/tasks/README.md` for why it isn't open
signup.

Update `last_login_at` on success.

## Sessions

- Cookie value: `secrets.token_urlsafe(32)`. The database stores
  `sha256(value)` in `app_sessions.token_hash` and never the value itself.
- Cookie attributes: `HttpOnly`, `SameSite=Lax`, `Path=/`,
  `Max-Age=SESSION_TTL_DAYS`, and `Secure` unless `SESSION_COOKIE_SECURE` is
  explicitly false. `Lax` rather than `Strict` because the OAuth callback is a
  top-level cross-site navigation — `Strict` would drop the cookie on the one
  request that sets it.
- Record `user_agent` and `ip` at creation. Diagnostics only; nothing
  authorises on them, because both are trivially forged and a real user's IP
  moves.

### `require_user`

A FastAPI dependency: read cookie → `sha256` → join `app_sessions` to
`app_users` in one query → reject if the session is missing, revoked, expired,
or the user is inactive. Returns a small frozen dataclass (`user_id`, `email`,
`display_name`, `profile`, `is_admin`) that every route in task 04 takes its
`profile` from.

**Sliding expiry, written at most once per half-TTL.** Push `expires_at`
forward only when the session is past half its life; an `UPDATE` on every
request would turn each read into a write and make `last_seen_at` a hot row for
no benefit.

## `POST /v1/auth/logout`

Set `revoked_at`, clear the cookie with the same attributes it was set with
(browsers ignore a `Set-Cookie` deletion whose `Path`/`Secure` don't match).
Idempotent — no session is still a 200, because a logout that 401s is a
confusing dead end.

## `GET /v1/me`

Behind `require_user`. Returns `{email, display_name, profile, is_admin}`. This
is what the frontend calls on load to decide between "show the app" and "show
the sign-in button", so it must be fast and must not touch the jobs tables.

## Why there is no JWT library

Dependencies stay at the five from task 01. The `id_token` is consumed **only**
from the direct, TLS-authenticated response to our own POST to Google's token
endpoint — never from a request body, a header or a query parameter. That is
precisely the case Google's own documentation exempts from signature
verification: the channel already authenticates the issuer, so decoding the
payload and checking `aud` / `iss` / `exp` / `nonce` is sufficient.

This is worth a comment in the code at the decode site, because the exemption
evaporates the moment anyone accepts an `id_token` over HTTP — the
frontend-GIS variant of this flow does exactly that, and it needs full JWKS
signature verification. If that day comes, add the library then; do not assume
the existing decode is doing something it isn't. Task 05 pins the property with
a test.

## Google Cloud Console checklist

None of this is code, and all of it blocks the first login. It belongs in
`backend/webapp/README.md`:

1. Create a project; configure the OAuth consent screen (External unless
   there's a Workspace domain).
2. While the app is unverified, add each allowlisted address to **Test users** —
   otherwise Google refuses the account before this service ever sees it. Two
   allowlists have to agree during development; that surprise is worth writing
   down.
3. Credentials → Create OAuth client ID → **Web application**.
4. Authorized redirect URI must equal `GOOGLE_REDIRECT_URI` **byte-for-byte**,
   trailing slash included. Add both the localhost and the deployed URI.
5. Copy the client id and secret into `.env` (mode 600, gitignored).

## Verify

```bash
.venv/bin/uvicorn app:app --port 8421 --reload
```

1. Open `http://localhost:8421/v1/auth/login` → Google consent → back at
   `FRONTEND_ORIGIN`. A `jobs_session` cookie is set, `HttpOnly` and without a
   readable value.
2. `curl -b 'jobs_session=<value>' localhost:8421/v1/me` → your email and
   profile. Without the cookie → 401.
3. Sign in with a Google account **not** on the allowlist → 403, and
   `manage_app_users.py list` shows no new row.
4. Replay a used callback URL → 400, not a second session.
5. `http://localhost:8421/v1/auth/login?next=//evil.com` → the redirect after
   login lands on `FRONTEND_ORIGIN/`, never on `evil.com`.
6. `POST /v1/auth/logout`, then re-issue step 2 → 401. Confirm
   `app_sessions.revoked_at` is set rather than the row being gone.
7. `manage_app_users.py disable --email you@gmail.com`, then call `/v1/me`
   with a still-valid cookie → 403. Disabling must take effect on the next
   request, not at the next login.

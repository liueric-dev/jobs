# 02 — Auth schema, the `jobs_web` role, and the admin CLI

Three new tables, a Postgres role that can touch almost nothing, a startup
check that proves it, and the CLI that seeds the allowlist.

**Depends on:** 01. **Blocks:** 03.

## Files

```
backend/webapp/schema_web.py         DDL + REQUIRED_TABLES + verify_schema()
backend/webapp/manage_app_users.py   admin CLI
backend/schema.py                    (one added index — see below)
```

`schema_web.py` is structured like `backend/api/query_claims.py`'s schema half:
it declares **only** the tables this service owns, delegates anything
pipeline-owned to `schema.ensure_schema()`, and never drops or rewrites a
column it does not own. That ownership line is what keeps this service's DDL
from becoming a second, drifting definition of the jobs table — the exact
failure `api/query_claims.py`'s docstring documents at length.

## Tables

```
app_users
    id             TEXT PRIMARY KEY          u_<hex>
    email          TEXT NOT NULL UNIQUE      stored lowercased
    google_sub     TEXT UNIQUE               NULL until first login
    display_name   TEXT
    profile        TEXT NOT NULL             -> profiles.profile, by convention
    is_admin       BOOLEAN NOT NULL DEFAULT FALSE
    active         BOOLEAN NOT NULL DEFAULT TRUE
    created_at     TEXT NOT NULL
    last_login_at  TEXT

app_sessions
    token_hash     TEXT PRIMARY KEY          sha256 of the cookie value
    user_id        TEXT NOT NULL REFERENCES app_users(id) ON DELETE CASCADE
    created_at     TEXT NOT NULL
    expires_at     TEXT NOT NULL
    last_seen_at   TEXT
    revoked_at     TEXT
    user_agent     TEXT
    ip             TEXT

oauth_logins
    state          TEXT PRIMARY KEY
    code_verifier  TEXT NOT NULL             PKCE
    nonce          TEXT NOT NULL
    next_path      TEXT
    created_at     TEXT NOT NULL
    expires_at     TEXT NOT NULL
```

Timestamps are `TEXT` in the pipeline's `%Y-%m-%dT%H:%M:%S` UTC form, via
`lib.timeparse.utc_now_str()`. Not because TEXT is better — because every other
table in this database does it, and one table with `TIMESTAMPTZ` would make
every join and every hand-written diagnostic query a special case.

### Three decisions worth their comments

**`app_users.profile` has no foreign key to `profiles`.** It is a bare `TEXT`
column, exactly like `job_scores.profile` and `job_matches.profile` in
`backend/schema.py`. A real FK would mean this service's DDL depended on a
pipeline-owned table, which is the coupling the ownership rule above exists to
prevent. The CLI validates the profile at insert time with
`profiles.load_one()` instead — which is the right place, because that function
deliberately returns paused profiles too.

**`app_sessions` stores `sha256(token)`, never the token.** Same reasoning and
the same three lines as `api/manage_users.py`: a database dump then yields no
working credential. The cookie value is `secrets.token_urlsafe(32)` — ~256 bits,
so the only attack left is stealing the cookie, not guessing it.

**`oauth_logins` keeps PKCE state server-side** rather than in a signed cookie.
Rows are single-use — redeemed with one `DELETE ... RETURNING`, so a replayed
`state` finds nothing and the CSRF property falls out of the primary key rather
than out of code anyone has to keep correct. It also means no signing secret to
generate, store, rotate or leave at a default.

`oauth_logins` needs pruning, or an abandoned login leaves a row forever.
Delete expired rows opportunistically inside the callback rather than adding a
timer: the table is only ever touched by logins, so a login is exactly when it
is worth a cheap `DELETE WHERE expires_at < now`.

## `verify_schema()`

Port `verify_schema()` from `backend/api/app.py` wholesale — the docstring as
much as the code. It checks **privileges, not just existence**, through
`has_table_privilege()` and `has_sequence_privilege()`, because a table can
exist and still be unusable if a `GRANT` was missed, and that failure surfaces
at *runtime* as a 500 rather than at deploy time. The specific example in that
docstring (INSERT without SELECT looks fine until the first `ON CONFLICT`)
applies here identically, and the sequence case applies to `job_events.id`,
which is `BIGSERIAL`.

Two dicts drive both the check and the README's grant table:

```python
REQUIRED_TABLES = {
    "jobs_app":     ("SELECT",),
    "jobs":         ("SELECT",),
    "job_matches":  ("SELECT",),
    "job_scores":   ("SELECT",),
    "job_facts":    ("SELECT",),
    "profiles":     ("SELECT",),
    "job_events":   ("SELECT", "INSERT"),
    "app_users":    ("SELECT", "INSERT", "UPDATE"),
    "app_sessions": ("SELECT", "INSERT", "UPDATE", "DELETE"),
    "oauth_logins": ("SELECT", "INSERT", "DELETE"),
}
REQUIRED_SEQUENCES = {"job_events_id_seq": ("USAGE", "SELECT")}
```

The service refuses to start if any of that is missing, naming what is absent
and pointing at `manage_app_users.py init-schema`.

## The `jobs_web` role

Created by hand, once, with an admin credential. The SQL belongs in the service
README so it is re-creatable, and it must match `REQUIRED_TABLES` above — those
dicts are the source of truth for both.

| Object | Granted |
|---|---|
| `jobs_app`, `jobs`, `job_matches`, `job_scores`, `job_facts`, `profiles` | SELECT |
| `job_events` | SELECT, INSERT |
| `job_events_id_seq` | USAGE, SELECT |
| `app_users` | SELECT, INSERT, UPDATE |
| `app_sessions` | SELECT, INSERT, UPDATE, DELETE |
| `oauth_logins` | SELECT, INSERT, DELETE |

- **No `UPDATE` or `DELETE` on any pipeline table.** This service cannot rewrite
  a score, a posting or a match. A session-hijacking bug or an injection here
  costs reads and event rows, not the corpus.
- **`jobs` needs SELECT even though only `jobs_app` is queried.** A plain view
  runs with the caller's privileges; it is not a security barrier. Granting on
  the view alone fails at the first request.
- **No `CREATE`.** DDL runs only through the CLI's separate admin credential,
  which is the same split `api/` uses and for the same reason: the
  internet-facing long-running process should not be able to alter the schema.
- **No `DELETE` on `job_events`.** Engagement data is append-only; a "dismiss"
  is a row, not a deletion.

## One pipeline-side change

Add to `ensure_schema()` in `backend/schema.py`:

```sql
CREATE INDEX IF NOT EXISTS idx_job_events_profile_job ON job_events(profile, job_id)
```

The existing index is `(profile, occurred_at DESC)`, which serves "this
profile's recent activity" but not "has this user saved or dismissed *this
job*" — the lookup task 04 does on every list render. It goes in `schema.py`
rather than here because the pipeline owns `job_events`; adding an index is
additive, idempotent and safe on the existing table.

## `manage_app_users.py`

argparse CLI shaped like `backend/api/manage_users.py`, run locally only, never
exposed over HTTP. `init-schema` is the only command that issues DDL and the
only one that uses `JOBS_ADMIN_DATABASE_URL`; everything else runs on the
restricted URL, because add/list/disable need nothing beyond grants the service
role already holds.

```
init-schema
add             --email you@example.com --profile tech [--name "Eric"] [--admin]
list
disable         --email ...
enable          --email ...
sessions        [--email ...]
revoke-sessions --email ...
```

- `add` lowercases the email, and **refuses an unknown profile** — checked with
  `profiles.load_one()`, which is the substitute for the foreign key that
  deliberately is not there.
- `revoke-sessions` is the break-glass path for a stolen cookie, and the reason
  sessions are opaque database rows rather than signed tokens: revocation is an
  `UPDATE`, not a key rotation.

## Verify

```bash
cd backend/webapp
JOBS_ADMIN_DATABASE_URL=postgresql://jobs_pipeline:...@localhost:5432/jobs \
  .venv/bin/python manage_app_users.py init-schema
.venv/bin/python manage_app_users.py add --email you@gmail.com --profile tech --admin
.venv/bin/python manage_app_users.py list
```

Then prove the startup gate works — this is the point of the whole task:

```sql
REVOKE SELECT ON job_matches FROM jobs_web;
```

The service must now **refuse to start**, naming `public.job_matches: no
SELECT`. Restore the grant and it starts. Also confirm the boundary itself:
connecting as `jobs_web`, `UPDATE job_scores SET fit_score = 0` must be denied,
and `python3 -m unittest discover -s tests -t .` in `backend/` must still pass —
the added index is the only pipeline change and it should disturb nothing.

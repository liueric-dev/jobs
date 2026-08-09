# jobs-api

Coordination service that lets other people contribute job-posting search
results without ever touching the database.

Contributors run [`contributor-worker/google-serpapi-worker.py`](contributor-worker/google-serpapi-worker.py)
on their own machines with their own SerpApi accounts. They ask this server
what to search, run the search, and post the raw results back. This server is
the only thing that talks to Postgres.

```
contributor machine                    this server        Postgres db `jobs`
  worker script  ──claim + check-in───▶  app.py    ──────────▶  public.jobs
       │                                   │                    job_ingest_state
       ├─ SerpApi (their own key)          │                    submission_log
       │                                   │                    contributor_status
       └──submit raw results─────────────▶ │ normalizes
                                             server-side
```

## Relationship to the pipeline in the parent directory

Until slice D of `~/apps/REORG.md` this was a separate repo with **no shared
imports**, deliberately reimplementing the claim algorithm rather than
importing it, on the grounds that `~/.hermes` was the harness's private
directory and had no business being a library dependency of a public-facing
server. That reasoning was sound and its conclusion was still wrong, because
what got duplicated went well beyond the claim: nine functions and the DDL for
three tables, which had drifted six ways by the time anyone measured. Two of
those drifts changed `content_hash`, which is row identity — so the same
posting written by the pipeline and then through this API produced two
different digests and the two systems rewrote each other's rows on alternating
runs. It stayed latent only because this service has never been deployed.

The fix was to move the pipeline out of `~/.hermes` too and put both halves in
one repo. This directory now imports `../schema.py`, `../google_jobs.py` and
`../lib/` directly — one `sys.path` insert in `query_claims.py` reaches all
three.

**What is still deliberately not shared: the claim SQL.** `try_claim_query`,
`holds_claim`, `mark_success` and `release_claim` are a superset of
`lib.state`'s — they add `claimed_by` and `claim_granted_at`, because this
service must answer "does this contributor still own the claim they are
submitting against?", which the pipeline never asks. The two still coordinate
through the **same Postgres row** (`job_ingest_state`, keyed
`google_jobs:query:<slug>`) with the same atomic
`INSERT ... ON CONFLICT ... WHERE claimed_at IS NULL OR expired`, so row-level
locking keeps "two claimants never get the same query" true across both.

`config/google-queries.json` is now the pipeline's copy, one level up, read by
both. It used to be a separate file here, free to diverge to a curated public
subset; the two were byte-identical in practice, and nothing was keeping them
that way. Set `GOOGLE_QUERIES_FILE` if you do want to serve a different bank.

## Setup

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
cp .env.example .env && chmod 600 .env    # fill in DATABASE_URL
set -a; . .env; set +a

# once, with an admin credential — the only command that issues DDL
JOBS_ADMIN_DATABASE_URL=postgresql://jobs_pipeline:pass@localhost:5432/jobs \
  python3 manage_users.py init-schema

uvicorn app:app --port 8420
```

**There used to be a third install line here, and its absence is the point.**
This venv sets `include-system-site-packages = false`, so while the mechanism
layer was a shared pip-installed package it was invisible in here and needed
its own `pip install -e ~/apps/pipelib`. Forgetting it produced an
`ImportError` **only under uvicorn** and nowhere else — not in the pipeline,
not in the tests, not in a bare `python3` here. Slice G vendored that code to
`../lib/`, which `query_claims.py` reaches with the same `sys.path` insert it
already needed for `../schema.py`. `requirements.txt` is now the complete
dependency list.

Schema creation is a **deliberate, separate step**, not something the service
does at startup. `init-schema` is additive only — it never drops or rewrites
columns the ingest pipeline owns. The service itself connects as a role with no
DDL rights and refuses to start if the schema or its grants are missing, naming
what's absent. See "Database privileges" below.

### Issuing a key

```bash
python3 manage_users.py create --name "Dave" --label "dave-laptop"
python3 manage_users.py list
python3 manage_users.py revoke --key-hash <prefix>
```

The raw key prints **once** and is never stored — only `sha256(key)`. If a key
is lost, revoke it and mint a new one; there is no recovery command by design.

**`create` is the manual fallback, not the normal path** (`docs/adr/0006`,
`docs/adr/0007` decision 1). A Builder gets a credential by opting in through
`../webapp/`, which POSTs `/v1/internal/contributors` here — see "Minting for
another process" under **API** below. Both go through one implementation,
`query_claims.mint_credential()`, so there is a single place that decides a key
is `token_urlsafe(32)` and that only its sha256 is stored.

### Who is contributing, and whose worker is broken

```bash
.venv/bin/python contribution_report.py                  # per contributor
.venv/bin/python contribution_report.py --by-dataset     # per query slug
.venv/bin/python contribution_report.py --empty-workers  # only the findings
.venv/bin/python contribution_report.py --since 2026-08-01 --json
```

Counts over `submission_log`, bucketed by `action`. Two findings, and they are
different failures: `empty-submits` is a worker whose submissions come back with
nothing in them, and `no-submits` is a worker that claims queries and never
submits at all — the second writes no submit row of any kind, so no empty rate
can see it, and every one of its claims held a query out of the pool for
`CLAIM_TTL_MINUTES`.

`--by-dataset` is the control, not a convenience. If every contributor's submits
on one slug come back empty, the **query** is dead and the workers are fine;
telling a Builder their worker is broken when the query is stale is the mistake
that view exists to prevent.

**A NULL `action` is a fourth value, not a zero.** It means *"written before the
column existed"* (see `query_claims.py`), it gets its own `null` column, and it
is excluded from every rate and from both findings — a contributor whose rows
cannot be classified is reported as unmeasurable rather than as broken. A sixth
column, `other`, catches an `action` outside the vocabulary; the column is free
TEXT by design, so that state is representable and is worth naming when it
appears.

`--min-submits` and `--empty-rate` are a reading lens: they decide what gets a
label printed beside it and nothing else. Nothing in the service reads them, no
request is refused because of them, and no row is written.

**Since `T-35` it also shows four facts per contributor**, and they answer a
different question from the counts beside them: `check-in`, `worker`, `quota`,
and — under the table, because an error is a sentence and not a cell — the last
error. `submission_log` says what somebody has *done*; these say whether their
machine is *still there*.

```
contributor     name             check-in             worker                       quota  claims  submits  finding
c_1297ba1faca5  Alex Yu          2026-08-09T15:21:20  jobs-contributor-worker/1.0  0      3       0        no-submits
c_16eceda10e2e  Dana Okonkwo     2026-08-09T15:21:20  jobs-contributor-worker/1.1  173    4       4
c_56bcfcc98bfc  Never Installed  -                    -                            -      0       0
c_e6ace310750a  Sam Reyes        2026-08-09T15:21:20  jobs-contributor-worker/1.1  250    0       0

reported by the contributors' own machines, not observed here:
  c_1297ba1faca5  last error 2026-08-09T15:21:20 -- search failed: SerpApi rejected this key (HTTP 401)
```

Read the last two rows together, because they are the reason this exists.
**Sam and "Never Installed" have identical counts** — zero of everything — and
before `T-35` they were the same row in this report and in every other record
this service kept. Sam is a healthy machine polling hourly on a bank that has
nothing stale; the other is somebody who opted in and never ran the worker. The
check-in column is the only thing that tells them apart, and `claim` writes no
`submission_log` row when it grants nothing, so nothing else ever could.

**A contributor now appears here whether or not they have ever written a log
row.** The key set is the union of `contributors` and the ids in
`submission_log` — the second half kept because `contributor_id` has no foreign
key, so a log row with no contributor row (a leaked or hand-crafted key) is
representable and is the last row that should be dropped.

**`--since` bounds the log and not the status.** The buckets are counts of
events in a window; the four facts are current state. A reader asking "who has
done nothing since Monday" needs the check-in that answers "because they
stopped polling on Tuesday".

**The quota and the error came off a contributor's machine and are never
presented as this service's own observations.** Nothing here can see a
Builder's SerpApi plan or verify that an error happened, so each is stored with
the time it arrived and printed under a heading that says so.

This runs on the same restricted `DATABASE_URL` the service uses — it needs
`SELECT` on `submission_log`, `contributors` and `contributor_status` and
nothing more. That is also why it lives here rather than in `backend/tools/`,
which runs as `jobs_pipeline` and holds nothing on `submission_log`.

## Tests

```bash
cd backend/api
.venv/bin/python -m unittest discover -s tests
```

**A third suite, not part of `backend/tests/`, and that is a constraint rather
than a preference.** This venv sets `include-system-site-packages = false`, so
the system `python3` the pipeline suite runs under cannot import `app.py` at all
— it needs `fastapi`, which the top level does not have and (per
`.claude/CLAUDE.md`) is not getting. `backend/tests/test_upsert_checked.py` names
`api/app.py` and `api/query_claims.py` as *paths* and says in its own docstring
that importing them would buy nothing there; it parametrises over
`schema.google_spec()`. So until 2026-08-02 nothing anywhere imported this
service. These are its first tests.

Most of it needs no database and no network: `tests/fakedb.py` is a fake
connection that dispatches on SQL text, the same line `backend/webapp/tests/`
draws between its unit files and `test_event_replay.py`.

~~What that cannot falsify — the claim-protocol SQL in `try_claim_query` and
`holds_claim` — is not covered and is called out as such.~~ **Covered since
2026-08-02 (defect `D72`)** by `tests/test_claim_protocol.py`, which runs against
a scratch schema and **skips** where no database is reachable rather than passing
vacuously. `tests/test_contribution_report.py` splits the same way: the bucket
arithmetic is pure and always runs, and the five `COUNT(*) FILTER` expressions
run against Postgres.

The scratch schema is created on the **pipeline's** credential, read out of
`backend/.env` and published only as `JOBS_SCRATCH_DATABASE_URL`. It has to be:
`scratchdb.create()` issues `CREATE SCHEMA`, and `jobs_api` holds no DDL at all
by design — which is the property `verify_schema()` exists to preserve, so
borrowing a stronger credential for the fixture is better than weakening the
role. Set that variable yourself to point the fixture somewhere else.

**Read the `Ran N tests` line, not a number written down anywhere.** A skip is
not a failure, and this suite has modules that skip.

## API

All endpoints require `Authorization: Bearer <key>`. **Two different kinds of
key** — a contributor's, for everything in the first table, and the operator's
own server-to-server secret, for the one route in the second.

| Endpoint | Purpose |
|---|---|
| `POST /v1/queries/claim` | `{"max": N}` → stalest unclaimed queries, each with a `date_chip`. One `submission_log` row per query granted |
| `POST /v1/queries/{dataset}/submit` | `{"jobs": [...raw SerpApi objects...]}` → stores results. Advances the watermark **only if the payload was non-empty** — see below |
| `POST /v1/queries/{dataset}/release` | give a claim back after a failed fetch, watermark untouched |
| `GET /v1/health` | liveness |

Only SerpApi-backed buckets are offered. The Apify source bills the operator's
own account per result, so it stays in the private pipeline — contributors
spend their own SerpApi quota, which is the point.

### Contributor settings — the server holds desired state

`docs/adr/0007` decision 3. Three columns on `contributors`, read by `claim` on
every poll and written only by `manage_users.py settings`:

| Setting | Unset means | What it does |
|---|---|---|
| `paused` | not paused | `claim` grants nothing and answers `{"paused": true, "queries": [], "poll_interval_seconds": N}` |
| `daily_cap` | `MAX_CLAIMS_PER_CONTRIBUTOR_PER_DAY` | this contributor's claims-per-day ceiling, replacing the service default rather than capping it |
| `reserve_floor` | `0` | SerpApi credits the Builder keeps unspent — a **level**, read against the balance their worker last reported, not a slice of the cap |

```bash
python3 manage_users.py settings --contributor c_ab12 --paused
python3 manage_users.py settings --contributor c_ab12 --active --daily-cap 8 --reserve-floor 2
python3 manage_users.py settings --contributor c_ab12 --daily-cap clear
```

**`settings` runs on `JOBS_ADMIN_DATABASE_URL`, and it is the second command
that does** — `jobs_api` holds SELECT and INSERT on `contributors`, not UPDATE,
so the internet-facing role cannot rewrite the policy that governs it. That is
why the grant table below is unchanged by this feature.

**A pause is a `200`, never a `4xx`.** The worker exits 1 on any HTTP error from
`claim`, so refusing a paused contributor would make a deliberately quiet
machine report itself broken; `0007`'s dormancy consequence is that pausing
stops *spending*, not *reporting*. The reply still carries
`poll_interval_seconds`, because that poll is the only channel a resume can
arrive on.

**The two numbers are spent server-side and never sent.** The worker is told
`paused` — so a Builder can tell a paused machine from an idle one — and nothing
else. A number the worker could act on is a number it could disagree about, and
`0007` decision 3 gives it no policy beyond its poll-interval floor.

**The floor binds against a balance, and the balance is the Builder's own
report** (`T-54`). `allowance` has two readings and which one applies depends on
whether `contributor_status.quota_remaining` holds something recent:

| The last reported balance is | `allowance` is | Why |
|---|---|---|
| present, and no older than `QUOTA_STALE_AFTER_POLLS` × the poll interval | `min(cap, used + max(0, balance − floor))` | the floor is a level the credits must not drop below; the cap is still the operator's ceiling |
| absent, or older than that | `max(0, cap − floor)` | `T-34`'s reading, kept as the fallback — a machine that has never finished a run has reported nothing, and refusing it on the strength of a number that never came is worse than reserving conservatively |

`used` is added back because `allowance` is a **day total** that `claim` then
subtracts `used` from again, while a balance is a level already net of what was
spent before it was reported. A key that has stopped working reports an *error*,
never a balance of `0`, so the dead-credential case lands in the second row and
not in a refusal. A balance at or below the floor is a `429` — see `T-57` for
what that `429` currently says.

### Contributor status — the poll is also the check-in

`T-35`. The same request carries three optional fields *up*, and
`contributor_status` keeps one row per contributor with what they said and when:

| Field | Where it comes from |
|---|---|
| `last_check_in_at` | this server's clock, on **every** authenticated poll — granted, granted-nothing, paused, and refused at the cap |
| `worker_version` | the worker's own `USER_AGENT`, so the string here and the one in a proxy's access log cannot disagree |
| `quota_remaining` / `quota_reported_at` | SerpApi's unmetered account endpoint, read by the worker at the end of a run and reported on the next poll |
| `last_error` / `last_error_at` | whatever failed on that machine since its last poll, reported **once** and then forgotten |

**Every fact has its own timestamp, and that is not symmetry.** A check-in moves
hourly; a quota and an error move only when there is one to report. Reading the
check-in time as the time a balance was reported would make a week-old balance
look freshly confirmed once an hour — and `T-54` built the reserve floor on
exactly that number's age, so the separate column is now load-bearing rather
than merely tidy: a worker whose SerpApi key has died keeps checking in every
hour and reports a balance never, and it is `quota_reported_at` alone that stops
the floor binding against a number nothing has confirmed since.

**A check-in is not a claim.** No `submission_log` row, nothing `claims_today()`
counts. An honest idle poll would otherwise exhaust a daily cron's allowance on
precisely the days there was no work — which is the same argument `claim`'s
granted-nothing case already rests on.

**It is committed before anything can refuse the poll.** `claim` refuses a
contributor over their cap by raising, and the request's transaction rolls back
on the way out; a check-in inside it would be erased for exactly the
contributors an operator is trying to see.

**A reported field can never fail the poll it rides on.** All three are
optional (an older worker sends none and keeps working), and an over-long or
control-character-laden string is trimmed and cleaned rather than refused — a
machine must not be denied the queries it called for because its traceback had
a newline in it. Wrong *types* are still a `422`: that is broken code, not a
broken machine.

**Why `contributor_status` is its own table and not three more columns on
`contributors`.** This is written by the request path, and `contributors` holds
the policy that governs the request path. Sharing a table would mean granting
`jobs_api` UPDATE on the row that says whether it may grant anything at all —
table-wide, which the section above refuses outright, or column-wise, which
`has_table_privilege()` cannot tell apart from the wide form, so the safety
property would rest on a GRANT nothing checks. A separate table keeps
`contributors` at SELECT/INSERT, which a startup check *can* hold.

**`submit` with an empty `jobs` array does not advance the watermark**
(defect D08, fixed 2026-08-02). It releases the claim, logs the submission and
returns `watermark_advanced: false`. The pipeline's own
`ingest/google-serpapi.py` *does* advance on zero results and is right to: it
made the SerpApi call itself, so it knows the fetch succeeded. This service only
ever sees an array, and an empty one is what an exhausted key, a blocked worker,
a wrong chip and a genuinely quiet query all look like from here. A worker whose
search legitimately returned nothing loses nothing — the query is simply handed
out again.

**`submit` against a slug the server's query bank does not contain returns
409**, and one whose bank cannot be read returns **500** (defect D09). Neither
stores anything. `mode` drives `location_is_remote`, so guessing it is a wrong
stored fact that nothing downstream can distinguish from a right one.

### Minting for another process

| Endpoint | Purpose |
|---|---|
| `POST /v1/internal/contributors` | `{"name", "label", "contributor_id"}` → `{"contributor_id", "api_key", "key_hash", "created_at"}`, `201` |

**Authenticated by `JOBS_MINT_SHARED_SECRET`, not by a contributor key** —
`app.authenticate_service()`, a separate function from `authenticate()` on
purpose. If the two mechanisms were one, any leaked contributor key would mint
more keys. Unset secret means the route **503s**; it never means "allow
anything".

**Its only caller is `../webapp/`'s `POST /v1/contribute/opt-in`.** That
service authenticates the Builder and this one owns `api_keys`; they hold
different Postgres roles and `docs/adr/0006`'s consequences reject granting
`jobs_web` INSERT here. `0006` named "the server-to-server shared secret" as
the unscoped follow-up — this is it, and `T-27` is where it landed.

**Passing `contributor_id` is a RE-KEY**: every live key that contributor holds
is revoked and one new key is issued, in one statement, sharing one timestamp.
Omit it and a new contributor row is created. An id this service has never seen
is a **409**, never a silent create — a re-key that quietly became a first mint
would leave the caller's stored id pointing at nothing.

**`internal` in the path is intent, not a control.** The shared secret is the
control; the reverse proxy refusing `/v1/internal/` from outside is the belt —
see **Deployment** below.

## Security model

Every caller is untrusted: contributors run code on machines the operator
doesn't control, and keys can leak.

- **Postgres is never reachable by contributors.** Only this process talks to
  it. Keep the database bound to localhost/Tailscale; expose only this service.
- **All stored fields are derived server-side** by `query_claims.normalize_job()`.
  Client-supplied ids and hashes are ignored entirely. This is what stops a
  hostile payload from clobbering rows owned by other sources — `make_id()`
  derives the dedup key from `platform:company_token:source_id`, so accepting
  those from a client would let anyone overwrite arbitrary postings.
- **Claim ownership is enforced on submit** (`holds_claim`): you may only
  submit against a live, unexpired claim you hold. Returns 409 otherwise.
- **Caps**: request body size (`MAX_BODY_BYTES`, on every route), jobs per
  submit (`MAX_JOBS_PER_SUBMIT`), queries per claim (`MAX_QUERIES_PER_CLAIM`),
  and per-contributor daily volume (`MAX_CLAIMS_PER_CONTRIBUTOR_PER_DAY`,
  counted from `submission_log`).
- **The body ceiling is a middleware, and it was not always** (`T-56`, closed
  2026-08-09). Until then `MAX_BODY_BYTES` was enforced only inside `submit`,
  which reads its body by hand; `claim`, `release` and the mint route take a
  Pydantic body, so Starlette buffered the whole request before any code in
  `app.py` ran and uvicorn set no ceiling below it. `BodySizeLimit` now refuses
  an oversized `Content-Length` before the app is entered at all, and counts
  chunks for a request that declares nothing or declares less than it sends —
  without which `Transfer-Encoding: chunked` is a one-header bypass. The
  refusal is a **413 before authentication**: an unauthenticated caller must
  not be able to make this service buffer an arbitrary body.
- **What that middleware does not do**: stop the bytes *arriving*. It bounds
  what this process holds, not what crosses the network. A body limit at
  whatever terminates TLS is the other half and is a deployment decision —
  see **Deployment** below, where the same argument already applies to
  request rate and to `/v1/internal/`.
- **Keys are stored hashed**, and revoked rows are kept rather than deleted.
- **The mint route holds a different credential from every other route.**
  `JOBS_MINT_SHARED_SECRET` identifies another of the operator's own processes,
  compared with `secrets.compare_digest` — the contributor path can afford a
  plain compare because it compares hashes of a 256-bit secret, but this one
  compares the secret itself. Unset disables the route.
- **The raw key exists in exactly one response and is never readable again.**
  No route returns an existing credential, `manage_users.py list` prints a hash
  prefix, and losing one means re-keying. `tests/test_mint.py` asserts this by
  trying to read the key back out of everything that was written.

## Database privileges

This service connects as `jobs_api`, a role granted a short, enumerated list
and nothing else. **Read the table, not a count in this sentence** — it said
"exactly six things" while the list below held seven, and `T-35` made it
eight. It is **not** the database owner, and deliberately not a
superuser — before 2026-07-26 it shared the instance's only role, `nyc_events`,
which is a superuser, so a leaked bearer token or an injection bug would have
yielded `COPY ... FROM PROGRAM` and full access to the unrelated
`public.events` data.

Since slice E that data is not merely ungranted but **unreachable**: it lives
in the separate `nyc_events` database, and `jobs_api` has no CONNECT there at
all. Verified by connecting as the role and being refused at the door.

| Table (database `jobs`, schema `public`) | Granted |
|---|---|
| `jobs` | SELECT, INSERT, UPDATE |
| `job_ingest_state` | SELECT, INSERT, UPDATE |
| `google_jobs_query_stats` | SELECT, INSERT |
| `contributors` | SELECT, INSERT |
| `contributor_status` | SELECT, INSERT, UPDATE |
| `api_keys` | SELECT, INSERT, UPDATE |
| `submission_log` | SELECT, INSERT |
| `submission_log_id_seq` | USAGE, SELECT |

No `DELETE` on anything — the code never issues one. No `CREATE`, so the
running service cannot alter the schema the ingest pipeline owns. No grant at
all on the seven pipeline-owned tables (`job_scores`, `job_facts`,
`job_matches`, `profiles`, `hn_seen_comments`, `ingest_progress`, `job_events`)
or on the `jobs_app` view, and no CONNECT to the events database.

`google_jobs_query_stats` needs SELECT despite being write-only from this
service's perspective: `log_query_stats()` uses `INSERT ... ON CONFLICT
(slug, run_at) DO NOTHING`, and Postgres requires SELECT on the arbiter index.
Granting INSERT alone fails at *runtime*, not at deploy time — which is why
`verify_schema()` checks privileges with `has_table_privilege()` rather than
just checking that tables exist.

The grants are re-creatable from `query_claims.REQUIRED_TABLES` and
`REQUIRED_SEQUENCES`, which are the source of truth for both the startup check
and this table. The sequence row used to appear here and nowhere in the code,
which made it the one documented grant whose absence surfaced as a 500 on a
contributor's first submit rather than as a refusal to start; slice D added
`REQUIRED_SEQUENCES` and a `has_sequence_privilege()` check to close that.

`tests/test_grants.py` now keeps this table honest in both directions: it parses
every SQL literal out of `app.py`, `query_claims.py` and `manage_users.py` and
asserts that no table is queried without being declared, **and** that no table is
declared without being queried. A privilege held for no reason is a hole in a
security posture whose whole claim is that this role can do a short, listed set
of things.

`contributors` keeps SELECT/INSERT and gains no UPDATE despite growing three
mutable settings columns, because the only writer is `manage_users.py settings`
on the admin credential — see "Contributor settings" above. **`T-35` is what
tested that line rather than restating it**: the four status facts are written
by the request path on every poll, so putting them on `contributors` would have
required the UPDATE this paragraph refuses. They went to `contributor_status`
instead, which is why that row is the only new grant in the table above.

### Required columns

`query_claims.REQUIRED_COLUMNS` is a third map, checked at startup by the same
`verify_schema()`, and it exists for the third instance of the same argument. A
table can exist, be granted correctly, and still be missing a column every
`INSERT` names — `init-schema` is a deliberately separate admin command this
service holds no rights to run, so shipping the code ahead of it is one `git
pull` away.

**Read the map, not a count written here.** It held one entry when this section
was written (`submission_log.action`, added 2026-08-02 so `claims_today()` could
count claims rather than log rows — defect D41); `T-45` widened it to seven
across three tables, and `T-34` added `contributors`' three settings. What
qualifies an entry is not how the column is accessed but whether it can go
missing on its own: every one arrives via `dbconn.add_missing_columns` on a table
that already exists, rather than in a `CREATE TABLE`. **`T-35` added a table and
no entry here, and that is the same rule rather than an exception** —
`contributor_status`' columns are in its `CREATE TABLE`, so they exist if it
does, and `REQUIRED_TABLES` already covers the only thing that can be absent. `T-34`'s three are the
first this service only ever **reads** — losing one is a 500 on every claim from
a service that started cleanly, which is the same failure the written case gives.

`action` is one of `claim`, `submit`, `release` — free `TEXT` with the closed set
in `query_claims.SUBMISSION_ACTIONS`, because a `CHECK` constraint would need DDL
rights this service does not have and a migration to widen. It is nullable with
no default: this service has never been deployed, so there is no existing row
whose action anyone could infer, and a NULL honestly reads as "written before
this column existed" — which `action = 'claim'` never counts.

## Deployment (manual — not automated by this repo)

**No credential is stored in this repo.** `DATABASE_URL`'s default is
passwordless; the real connection string lives in `.env` (mode 600, gitignored)
— see `.env.example`. The old shared default password was rotated out on
2026-07-24, and on 2026-07-26 this service moved off the superuser onto the
restricted `jobs_api` role described above.

**`/v1/internal/` must be refused at the edge.** Nothing in this repo can do
that — it is a line in the deployed reverse proxy's config, on a machine no
session touches — so it is `DEV_TASKS.md`'s `OQ-30`, together with generating
`JOBS_MINT_SHARED_SECRET` and putting the same value in this service's `.env`
and `../webapp/.env`. Until that secret exists the route 503s, which is the
safe direction: the mint is off, not open.

**~~Not automated by this repo~~ — automated as of task 33.** The systemd unit,
the tunnel config and the install sequence are tracked in
[`deploy/`](../../deploy/README.md), and day-to-day operations were in
`git show refactor-freeze-2026-08-02:docs/RUNBOOK.md`, deleted 2026-08-02.
What remains manual is the part no
repository can hold: a Cloudflare account, a domain, and one `cloudflared
tunnel create`.

### ~~Phase 1 — tailnet only~~ — superseded by Cloudflare Tunnel, task 33

~~Serving only machines their owner controls, over Tailscale: no TLS, reverse
proxy or domain needed, bind to the tailnet interface, run under a
supervisor.~~

**Struck, not deleted, and the reasoning is worth the next reader's time
because it was correct.** Tailscale is WireGuard — transport is already
encrypted and device-authenticated, so bearer tokens over plain HTTP *inside*
a tailnet genuinely are fine, and adding a proxy there genuinely does buy
nothing. Nothing below contradicts that.

What changed is the population, not the argument. Phase 1 was written for one
person's own devices. This service now has to serve ~30 Builders who are not on
anyone's tailnet and must never be put on one — putting them there would grant
network-level access to a home network, which the phase-2 note below already
said. Once every real caller is outside the tailnet, "phase 1" describes a
configuration with no users, and keeping two transports alive to reach that
state is more surface, not less.

So there is one transport: **Cloudflare Tunnel**, from day one, for this service
and for the webapp. Free tier; no static IP, no inbound port open, TLS
terminated at the edge, and it works from behind a residential ISP that blocks
inbound servers.

### Phase 2 — public contributors, and what it takes

1. **TLS is terminated by the tunnel.** Bearer tokens over plaintext HTTP on the
   open internet leak on every request; this is the requirement Tailscale Funnel
   was going to satisfy and Cloudflare now does. Caddy/nginx would also work and
   would each need a port opened, which is the thing being avoided.
2. **Bind to `127.0.0.1`, not `0.0.0.0`.** `cloudflared` connects from this same
   host, so binding wider buys nothing and makes the service reachable from the
   LAN the moment someone opens a firewall for an unrelated reason.
   `deploy/systemd/jobs-api.service` does this.
3. **Never put contributors on the tailnet.** Unchanged from the original text
   and now the only thing the tailnet is mentioned for. They reach the HTTPS
   hostname and nothing else.
4. **Firewall Postgres** so it doesn't become reachable just because the host
   did.
5. Set `MAX_CLAIMS_PER_CONTRIBUTOR_PER_DAY` to match how much of the query bank
   external contributors should cover per day.
6. **The tunnel is not an authorization layer.** Anyone on the internet can
   reach the hostname; the bearer key is the only thing keeping them out. Close
   the two gaps below before minting a key for anyone you do not know.

### Before opening this up — known gaps

~~**Claiming is unmetered.**~~ **Closed 2026-08-02, task 24 (defect D41).**
`POST /v1/queries/claim` now writes one `submission_log` row per query it
grants, and `claims_today()` counts rows with `action = 'claim'` and nothing
else — so the daily cap means *queries claimed today*, which is what
`MAX_CLAIMS_PER_CONTRIBUTOR_PER_DAY` always said. Counting every row instead
would have charged an honest submit and an honest release against the same cap.
A request granted nothing writes nothing: it locked no query, and metering it
would spend an honest daily cron's allowance on the days the bank is fresh.

Two of these are still open, and both are real once strangers can call it:

- **Concurrency is uncapped.** The fix above bounds claims *per day*, not how
  many a contributor may hold *at once*. Fifty outstanding claims is inside the
  daily cap and is most of a 32-slug bank, each locked for `CLAIM_TTL_MINUTES`.
  `job_ingest_state.claimed_by` makes the check one query; it is not built. See
  `git show refactor-freeze-2026-08-02:docs/tasks/refactor/tranche_four/24-revive-contributor-api.md`.
- **No provenance.** Rows submitted through this API are indistinguishable
  from locally-ingested ones, and `submission_log` records counts, not job
  ids. There is no way to trace or purge one contributor's rows if they turn
  out to be submitting junk. **`contribution_report.py` does not close this**
  and should not be read as closing it: it can tell you a contributor's
  submissions are empty or that their accepted count is implausible, which is
  the *detection* half. Acting on the finding still means having no way to say
  which stored rows were theirs.

## Configuration

| Env var | Default | Meaning |
|---|---|---|
| `DATABASE_URL` | `postgresql://jobs_api@localhost:5432/jobs` | Postgres connection |
| `GOOGLE_QUERIES_FILE` | `config/google-queries.json` | query bank path |
| `CLAIM_TTL_MINUTES` | `15` | how long a crashed contributor blocks a query |
| `GOOGLE_JOBS_MIN_HOURS_BETWEEN_RUNS` | `20` | don't re-hand-out a query that succeeded this recently |
| `MAX_JOBS_PER_SUBMIT` | `50` | per-submit posting cap |
| `MAX_QUERIES_PER_CLAIM` | `5` | per-request query cap |
| `MAX_CLAIMS_PER_CONTRIBUTOR_PER_DAY` | `50` | daily per-contributor cap |
| `MAX_BODY_BYTES` | `2097152` | request body ceiling, on every route (`BodySizeLimit`), and pre-parse again inside `submit` |
| `JOBS_MINT_SHARED_SECRET` | *(none — `/v1/internal/contributors` 503s without it)* | server-to-server secret; **the same value and the same name in `../webapp/.env`** |

# jobs-api

Coordination service that lets other people contribute job-posting search
results without ever touching the database.

Contributors run [`contributor-worker/google-serpapi-worker.py`](contributor-worker/google-serpapi-worker.py)
on their own machines with their own SerpApi accounts. They ask this server
what to search, run the search, and post the raw results back. This server is
the only thing that talks to Postgres.

```
contributor machine                    this server        Postgres db `jobs`
  worker script  ──claim──────────────▶  app.py    ──────────▶  public.jobs
       │                                   │                    job_ingest_state
       ├─ SerpApi (their own key)          │                    submission_log
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

No database and no network: `tests/fakedb.py` is a fake connection that dispatches
on SQL text, the same line `backend/webapp/tests/` draws between its unit files
and `test_event_replay.py`. What that cannot falsify — the claim-protocol SQL in
`try_claim_query` and `holds_claim` — is not covered and is called out as such.

## API

All endpoints require `Authorization: Bearer <key>`.

| Endpoint | Purpose |
|---|---|
| `POST /v1/queries/claim` | `{"max": N}` → stalest unclaimed queries, each with a `date_chip`. One `submission_log` row per query granted |
| `POST /v1/queries/{dataset}/submit` | `{"jobs": [...raw SerpApi objects...]}` → stores results. Advances the watermark **only if the payload was non-empty** — see below |
| `POST /v1/queries/{dataset}/release` | give a claim back after a failed fetch, watermark untouched |
| `GET /v1/health` | liveness |

Only SerpApi-backed buckets are offered. The Apify source bills the operator's
own account per result, so it stays in the private pipeline — contributors
spend their own SerpApi quota, which is the point.

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
- **Caps**: request body size (`MAX_BODY_BYTES`, pre-parse), jobs per submit
  (`MAX_JOBS_PER_SUBMIT`), queries per claim (`MAX_QUERIES_PER_CLAIM`), and
  per-contributor daily volume (`MAX_CLAIMS_PER_CONTRIBUTOR_PER_DAY`, counted
  from `submission_log`).
- **Keys are stored hashed**, and revoked rows are kept rather than deleted.

## Database privileges

This service connects as `jobs_api`, a role that can do exactly six things and
nothing else. It is **not** the database owner, and deliberately not a
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
security posture whose whole claim is "this role can do exactly six things."

### Required columns

`query_claims.REQUIRED_COLUMNS` is a third map, checked at startup by the same
`verify_schema()`, and it exists for the third instance of the same argument. A
table can exist, be granted correctly, and still be missing a column every
`INSERT` names — `init-schema` is a deliberately separate admin command this
service holds no rights to run, so shipping the code ahead of it is one `git
pull` away. Today it holds one entry: `submission_log.action`, added 2026-08-02
so `claims_today()` can count claims rather than log rows (defect D41).

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

**~~Not automated by this repo~~ — automated as of task 33.** The systemd unit,
the tunnel config and the install sequence are tracked in
[`deploy/`](../../deploy/README.md), and day-to-day operations are in
[`docs/RUNBOOK.md`](../../docs/RUNBOOK.md). What remains manual is the part no
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
  `docs/tasks/refactor/tranche_four/24-revive-contributor-api.md`.
- **No provenance.** Rows submitted through this API are indistinguishable
  from locally-ingested ones, and `submission_log` records counts, not job
  ids. There is no way to trace or purge one contributor's rows if they turn
  out to be submitting junk.

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
| `MAX_BODY_BYTES` | `2097152` | request body ceiling, enforced pre-parse |

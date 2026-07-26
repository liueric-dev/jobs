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
`pipelib` directly.

**What is still deliberately not shared: the claim SQL.** `try_claim_query`,
`holds_claim`, `mark_success` and `release_claim` are a superset of
`pipelib.state`'s — they add `claimed_by` and `claim_granted_at`, because this
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
.venv/bin/pip install -e ~/apps/pipelib   # REQUIRED: this venv has
                                          # include-system-site-packages=false,
                                          # so the user-site pipelib the
                                          # pipeline uses is invisible here
cp .env.example .env && chmod 600 .env    # fill in DATABASE_URL
set -a; . .env; set +a

# once, with an admin credential — the only command that issues DDL
JOBS_ADMIN_DATABASE_URL=postgresql://jobs_pipeline:pass@localhost:5432/jobs \
  python3 manage_users.py init-schema

uvicorn app:app --port 8420
```

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

## API

All endpoints require `Authorization: Bearer <key>`.

| Endpoint | Purpose |
|---|---|
| `POST /v1/queries/claim` | `{"max": N}` → stalest unclaimed queries, each with a `date_chip` |
| `POST /v1/queries/{dataset}/submit` | `{"jobs": [...raw SerpApi objects...]}` → stores results, advances watermark |
| `POST /v1/queries/{dataset}/release` | give a claim back after a failed fetch, watermark untouched |
| `GET /v1/health` | liveness |

Only SerpApi-backed buckets are offered. The Apify source bills the operator's
own account per result, so it stays in the private pipeline — contributors
spend their own SerpApi quota, which is the point.

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

## Deployment (manual — not automated by this repo)

**No credential is stored in this repo.** `DATABASE_URL`'s default is
passwordless; the real connection string lives in `.env` (mode 600, gitignored)
— see `.env.example`. The old shared default password was rotated out on
2026-07-24, and on 2026-07-26 this service moved off the superuser onto the
restricted `jobs_api` role described above.

### Phase 1 — tailnet only (current plan)

Serving only machines their owner controls, over Tailscale:

1. **No TLS / reverse proxy / domain needed.** Tailscale is WireGuard —
   transport is already encrypted and device-authenticated, so bearer tokens
   over plain HTTP *inside the tailnet* are fine. Do not "fix" this by adding
   a proxy; it buys nothing here.
2. Bind to the tailnet interface rather than `0.0.0.0`.
3. Run under a supervisor (systemd unit or container) so it restarts.

Note that for one person's own devices this service is optional — those
machines can point `DATABASE_URL` straight at Postgres over the tailnet and
use the existing ingest scripts. Running them through this API is worth it
mainly to shake it out before external contributors exist.

### Phase 2 — public contributors

1. **Terminate TLS.** Tailscale Funnel can expose this service publicly over
   HTTPS with a valid cert, no port-forwarding and no domain purchase;
   Caddy/nginx works too. Bearer tokens over plaintext HTTP on the open
   internet would leak on every request.
2. **Never put contributors on the tailnet** — that grants network-level
   access to the home network. They hit the HTTPS endpoint only.
3. **Firewall Postgres** so it doesn't become reachable just because the host
   did.
4. Set `MAX_CLAIMS_PER_CONTRIBUTOR_PER_DAY` to match how much of the query
   bank external contributors should cover per day.
5. **Close the two gaps below first.**

### Before opening this up — known gaps

Both are harmless among trusted devices and real once strangers can call it:

- **Claiming is unmetered.** `claims_today()` counts `submission_log` rows,
  but `POST /v1/queries/claim` writes none. A caller who claims and never
  submits is never metered, and each claim locks its row for
  `CLAIM_TTL_MINUTES` — so a claim-loop could hold the whole query bank
  locked, starving other contributors *and* the owner's own nightly pipeline.
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

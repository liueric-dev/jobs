# jobs-api

Coordination service that lets other people contribute job-posting search
results without ever touching the database.

Contributors run [`contributor-worker/google-serpapi-worker.py`](contributor-worker/google-serpapi-worker.py)
on their own machines with their own SerpApi accounts. They ask this server
what to search, run the search, and post the raw results back. This server is
the only thing that talks to Postgres.

```
contributor machine                    this server              Postgres
  worker script  ──claim──────────────▶  app.py    ──────────▶  jobs.jobs
       │                                   │                    job_ingest_state
       ├─ SerpApi (their own key)          │                    submission_log
       └──submit raw results─────────────▶ │ normalizes
                                             server-side
```

## Relationship to `~/.hermes/scripts/jobs/`

That directory holds the operator's private daily ingest pipeline, run as a
Hermes cron job. It is a **separate codebase with no shared imports** — this
repo deliberately reimplements the claim algorithm rather than importing it,
because `~/.hermes` is the Hermes harness's private directory and shouldn't be
a library dependency of a public-facing server.

They coordinate anyway, safely, because they serialize through the **same
Postgres row**: `job_ingest_state`, keyed `google_jobs:query:<slug>`, updated
with the same atomic `INSERT ... ON CONFLICT ... WHERE claimed_at IS NULL OR
expired`. Postgres row-level locking makes "two claimants never get the same
query" hold across both systems automatically. The operator's own machines and
external contributors can run simultaneously without coordination.

`config/google-queries.json` is this service's **own copy** of the query bank.
It's allowed to diverge from the pipeline's copy — e.g. to expose only a
curated public subset. Sync by hand if you want parity.

## Setup

```bash
pip install -r requirements.txt
export DATABASE_URL=postgresql://user:pass@localhost:5432/nyc_events
uvicorn app:app --port 8420
```

Schema is created/extended automatically on startup (additive only — it never
drops or rewrites columns the ingest pipeline owns).

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

## Deployment (manual — not automated by this repo)

**No credential is stored in this repo.** `DATABASE_URL`'s default is
passwordless; the real connection string lives in `~/.hermes/.env` (mode 600)
and is loaded into the environment there. The old shared default password was
rotated out on 2026-07-24.

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
| `DATABASE_URL` | `postgresql://nyc_events@localhost:5432/nyc_events` | Postgres connection |
| `GOOGLE_QUERIES_FILE` | `config/google-queries.json` | query bank path |
| `CLAIM_TTL_MINUTES` | `15` | how long a crashed contributor blocks a query |
| `GOOGLE_JOBS_MIN_HOURS_BETWEEN_RUNS` | `20` | don't re-hand-out a query that succeeded this recently |
| `MAX_JOBS_PER_SUBMIT` | `50` | per-submit posting cap |
| `MAX_QUERIES_PER_CLAIM` | `5` | per-request query cap |
| `MAX_CLAIMS_PER_CONTRIBUTOR_PER_DAY` | `50` | daily per-contributor cap |
| `MAX_BODY_BYTES` | `2097152` | request body ceiling, enforced pre-parse |

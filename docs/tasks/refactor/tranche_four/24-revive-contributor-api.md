# 24 — Revive the contributor API

**Status:** todo. **Depends on:** 23, 33 (tunnel). **Blocks:** 25.

Deploy `backend/api/`. It is written, tested and has never run.

## Reversing a decision

`backend/api/README.md:32` records that the service has never been deployed, and
`docs/tasks/README.md` records that it is **expected to be deprecated**. That was a
reasonable call for a single-user tool. It is wrong for this one.

The contributor model is the community feature the whole product is organised around,
and — this is the part that changed my earlier advice — it is *architecturally* the
right way to pool Google Jobs access:

> A contributor's worker claims stale queries from `POST /v1/queries/claim`, runs them
> against SerpApi **with its own key**, and posts the raw results back to
> `POST /v1/queries/{dataset}/submit`

Thirty Builders each running their own worker against their own free 250 searches is
thirty people staying inside their own allocation. That is a different thing from one
application pooling thirty keys to exceed one allocation, and it is defensible in a
way key-pooling is not. It also degrades gracefully: a Builder graduates, their worker
stops, nothing breaks.

Capacity: **30 × 250 = 7,500 searches/month**, the largest renewable pool in the plan
by an order of magnitude.

## What already works

Read `docs/ingest/contributor-api.md` before touching anything — it is a generated
audit of this exact service.

- FastAPI app object at `backend/api/app.py:152`; `uvicorn app:app --port 8420`
- **Startup is gated**: a `lifespan` context manager runs `verify_schema()` before
  serving (`:146-149`) and raises `RuntimeError`, refusing to start, if any required
  table, privilege or sequence is missing (`:82-143`)
- `docs_url` and `redoc_url` are both `None` — interactive docs deliberately disabled
- Everything stored is **recomputed server-side from the raw payload** (`:325-334`),
  so a contributor cannot inject arbitrary rows — they submit a SerpApi response and
  the server decides what it means
- Rows land in the same `jobs` table tagged `platform='google_jobs'` through the same
  `lib.upsert` path the pipeline uses (`query_claims.py:425-446`)
- It coordinates with `ingest/google-serpapi.py` and `ingest/google-apify.py` through
  the **same `job_ingest_state` rows** (`query_claims.py:216-241`), so the three paths
  do not duplicate work

That server-side recomputation is the security property that makes this safe to open
to thirty people, and it should be stated in the operator docs rather than left to be
rediscovered.

## Work

### Deploy

The docstring is explicit that domain, TLS and reverse proxy are undone. Task 33's
Cloudflare Tunnel solves all three without opening a port or needing a static IP.

The API and the nightly pipeline have different requirements — the API needs inbound
connectivity and uptime, the pipeline needs neither. Deploy accordingly; see task 33.

### Builder onboarding

The missing half. A Builder needs to go from "I have a SerpApi account" to "my worker
is contributing" without a terminal session with the author.

- A page, behind the existing Google SSO, that issues a contributor credential
- A single-file worker script they can run — and, better, a scheduled option that
  does not require leaving a laptop on. A GitHub Actions cron in their own repo is a
  plausible zero-install path and doubles as something they built
- Plain-language setup instructions. Assume no prior terminal experience; this is the
  population the whole app exists for, and the onboarding is itself a teaching
  artifact

### Query source

Contributors claim from a queue. Task 25 fills that queue from `search_queries`, seeded
by `role_track`. Until then, seed manually from task 05's vocabulary so the service has
something to serve.

### Fairness and abuse

- Rate-limit claims per contributor so one worker cannot drain the queue
- Expire unclaimed-but-checked-out queries so a worker that dies does not block a
  query forever
- Cap submissions per contributor per day — a contributor with 250/month should not
  spend it in an hour
- Track contribution counts per Builder. Anonymously in the UI (per the visibility
  decision), but attributably in the database, because a contributor whose submissions
  are consistently empty is a broken worker, not a lazy person

### Register it in the router

`serp/providers/contributor.py` (task 23) dispatches into this queue. Note that it is
**asynchronous** — a query goes in, results arrive when some Builder's worker picks it
up. The router must treat it as a deferred provider, not a synchronous one, and fall
through to a synchronous provider when a result is needed now.

## Documentation

`backend/api/README.md:32` and `docs/tasks/README.md` both say this is expected to be
deprecated. Both are now wrong. Correct them as part of this task rather than leaving
it to task 34 — a doc that actively contradicts a running service is worse than a
stale one.

## Definition of done

- Service running behind the tunnel; `verify_schema()` passes at startup.
- A Builder can onboard end-to-end without the author's involvement.
- At least three contributors submitting successfully.
- Rate limits, claim expiry and per-contributor caps in place.
- Registered in task 23's router as a deferred provider.
- Contribution counts tracked; empty-submission workers detectable.
- The two deprecation notices corrected.
- `docs/ingest/contributor-api.md` regenerated.

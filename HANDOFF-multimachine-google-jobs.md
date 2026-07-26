# Handoff — multi-machine Google Jobs ingest

**Date:** 2026-07-25 · **Status:** Steps 1–2 done and verified. Step 3 written, **not applied**. Steps 4–7 not started.
**Full plan:** `~/.claude/plans/read-hermes-scripts-jobs-and-create-ancient-badger.md`

---

## The ask

Run `ingest/google-serpapi.py` from several machines, each with its own SerpApi key,
all writing to the Postgres on `fedora` over Tailscale, coordinating so no credit is spent
twice. Later: an external app where users supply their own job titles and their own SerpApi
key.

## What turned out to be true

**The coordination layer already existed and was correct.** `pipelib.state.try_claim()` does an
atomic `INSERT … ON CONFLICT … WHERE claimed_at IS NULL OR expired RETURNING`; Postgres
row-locking makes "two machines never get the same query" a real guarantee. `~/apps/jobs-api/`
already implements the contributor-worker model the future app needs. **Neither needed
redesigning.** The original ask was mostly already built.

What was actually broken was **measurement**. Three findings, all verified against live data:

### 1. The Google Jobs dedup key was unstable — duplicates were being paid for

`source_id` was Google's `job_id` verbatim. It is not a posting identifier: it is a base64
JSON blob carrying the search context, including an `fc` token that rotates on every *fresh*
fetch and `hl`/`gl` keys that come and go. `schema.make_job_id()` hashed it, so every fetch
of an already-stored posting minted a new primary key.

- **837 google_jobs rows held 632 distinct postings — 32% inflation.** One 15Five listing was
  stored 4×.
- It stayed invisible because **SerpApi caches responses for 1h and serves them free**. Repeat
  runs inside the window replayed a byte-identical payload and reported "0 new". The first run
  past expiry reported "10 new / 10 fetched" for the same query. Check the timestamps in the
  old `google_jobs_query_stats`: 18:45 → 18:46 → 18:49 → 19:13 all report 0 new; 19:47 (just
  past 1h from 18:46) reports 10 new. Textbook.
- Therefore `google_jobs_query_stats.new_count` — the data collected specifically to drive the
  planned adaptive-cadence feature — was measuring **cache expiry, not job novelty**. Any
  yield-based scheduler built on it would have been fitting noise.
- The stable id is **`htidocid`**, inside the same blob. It is *better* than a
  (company, title, location) tuple: all 37 apparent `htidocid` collisions were Google reporting
  one remote posting as `United States` on one search and `Anywhere` on another. The tuple
  splits those; `htidocid` correctly unifies them.

### 2. `chips=date_posted:` is deprecated in the docs but STILL WORKS

SerpApi's [Google Jobs docs](https://serpapi.com/google-jobs-api) mark both `chips` and `ltype`
"deprecated by Google", with `uds` as successor. The entire catch-up ladder in
`choose_date_chip()` rests on `chips`. **Tested live 2026-07-25, 3 credits** — it works:

| variant | posted_at ages returned |
|---|---|
| unfiltered | 9h, 4d, 8d, 9d, 10d, 11d, 17d |
| `date_posted:today` | 8h–23h — **10/10 under 24 hours** |
| `date_posted:month` | 9h – 28d — **capped at 28 days** |

**No change needed to `choose_date_chip()`.** If it ever does break, the successor is `uds`,
read from the `filters` array of an unfiltered response (never hardcoded), and note
[serpapi/public-roadmap#2280](https://github.com/serpapi/public-roadmap/issues/2280): `uds` is
dropped when combined with `next_page_token`, so paginated pages are always unfiltered.

Repeatable via `tools/verify-date-filter.py` (`--dry-run` spends nothing).

### 3. Google Jobs is by far the best source — worth spending more on

| platform | scored | avg fit | ≥70 |
|---|---|---|---|
| google_jobs | 35 | **52.6** | **7** |
| greenhouse | 4 | 16.3 | 0 |
| builtin | 9 | 13.9 | 0 |
| ashby | 14 | 0.7 | 0 |

But 14.5% of its volume is three spam reposters (`remote zest jobs` 53, `vmysmartpros` 42,
`remote click jobs` 26), and a spam-filled page costs a full credit.

### Other facts worth keeping

- `/account` is **free** (doesn't consume quota) and returns `total_searches_left`,
  `plan_renewal_date`, `account_rate_limit_per_hour`.
- **Cycles are per-account anniversaries, not calendar months.** This key renews 2026-08-24.
- **Cached (1h), errored, and failed searches are all unbilled** — so failure handling can be
  aggressive, and a retry costs nothing.
- Current key state at handoff: Free Plan, **159 of 250 left**, 91 used, renews 2026-08-24.
  At `daily_budget`=8 that's ~240/month — no headroom for even a manual test run. Pacing would
  want `floor(159/30) = 5/day`. This is the Phase 2 problem.
- The README's claim that *"the daily budget is shared across all your machines, not multiplied
  by them"* **is wrong** for any bucket larger than its `daily_budget`. Machine A claims 2 of
  `core_swe`'s 8; machine B sorts stalest-first, sees those 2 are now freshest, and claims the
  *next* 2. Two machines cover 16/day, up to 32/day (the bank size) at 4 machines. Needs
  correcting in Step 7.

---

## What is done

### Step 1 — date filter verified ✅
- **New:** `tools/verify-date-filter.py`
- Result above. 3 credits spent. Verdict logic reads the **posted_at age ceiling**, not set
  overlap — three 10-result samples of a large relevance-ranked pool never nest even when the
  filter works, which is why the first version reported "INCONCLUSIVE" against a clear positive.

### Step 2 — stable posting identity ✅
- **`pipelib/ids.py`** — added `decode_google_job_id()`, `normalize_apply_url()`,
  `google_source_id()`. `htidocid` when available, else `fp:<sha256>` over
  (company_token, normalized title, apply URL with `utm_*`/`gclid`/`fbclid` stripped).
  **Location is deliberately excluded from the fingerprint** — it's the field Google reports
  inconsistently for the same posting.
- **`ingest/google-serpapi.py`**, **`ingest/google-apify.py`** — `normalize_job()`
  now calls `ids.google_source_id()`. Both sources return the same `job_id` for the same
  posting, so they must derive the key identically or one posting becomes two rows.
- **`~/apps/jobs-api/query_claims.py`** — same three functions **reimplemented** (that repo
  deliberately shares no code with `~/.hermes`). Marked in-file as the one place the two
  codebases must agree.
- **`pipelib/tests/test_pipelib.py`** — `TestGoogleJobIdentity`, 8 tests, pinned against two
  **verbatim real blobs** from the live table (the 15Five posting at 18:17:53 and 19:47:41 —
  same `htidocid`, different `fc`, one has `hl` and one doesn't).

**Verified:** 92/92 tests pass. Both implementations produce **identical ids on all 837 real
postings** plus fallback cases — cross-checked directly, 0 mismatches.

### Step 3 — migration written, **NOT APPLIED** ⚠️
- **New:** `migrate_google_ids.py` — dry-run default, `--apply`, idempotent.
- **Dry run output (verified):** 837 rows → 632 postings, 174 merge groups removing 205 rows,
  458 re-key-only, 0 score-profile collisions.
- **Backup taken:** `~/.hermes/backups/pre-googleid-20260725-055508.sql.gz` (21M, verified
  complete — "PostgreSQL database dump complete", 11,279 job rows).

---

## STOP — read before running `--apply`

**`score.py` was running concurrently and kept relaunching.** Observed PIDs 1656517 then
1657351. It writes `job_scores` continuously; the scored-google_jobs count drifted 21 → 34 →
35 → 36 across a few minutes of observation. That drift is live activity, **not a bug in the
migration**.

This matters because `apply_merge()` moves scores off the losing rows and then deletes them
(FK is `ON DELETE CASCADE`). If `score.py` inserts a score for a losing row *after* the read
and *before* the delete, that score is silently destroyed.

**Before `--apply`:**
1. Confirm nothing is running: `pgrep -af "score.py"` returns nothing.
2. Find out *what* is relaunching it. `hermes cron` has `daily-jobs-ingest` at `0 0 * * *`
   (`run-daily.py`, enabled) — that does not explain a 05:55 start. Suspect a manual run,
   another agent session, or a loop.
3. Re-take the backup if significant time has passed.
4. Then: `python3 migrate_google_ids.py` (confirm ~837→632), then `--apply`.
5. Verify: `SELECT count(*), count(DISTINCT source_id) FROM jobs.jobs WHERE platform='google_jobs'`
   — **the two numbers must be equal.**

**Also:** `pipelib/llm.py` was modified at 05:54, during this session, by something other than
this work. **Another session or agent is active in this repo.** Coordinate before committing.

---

## What remains

### Step 3 (finish) — apply the migration
Above. Also truncates `google_jobs_query_stats` (not data loss — every `new_count` in it was
computed from the broken key; use `--keep-stats` to override).

### Step 4 — `jobs.job_sources` provenance
The table that makes marginal yield measurable and closes jobs-api's documented "no provenance"
gap.

```sql
CREATE TABLE IF NOT EXISTS job_sources (
    job_id      TEXT NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
    query_slug  TEXT NOT NULL,
    key_id      TEXT,          -- sha256(serpapi_key)[:16], NEVER the key
    machine_id  TEXT,          -- hostname; NULL for jobs-api submissions
    page        INTEGER NOT NULL DEFAULT 1,
    outcome     TEXT NOT NULL, -- 'new' | 'updated' | 'unchanged'
    fetched_at  TEXT NOT NULL,
    PRIMARY KEY (job_id, query_slug, fetched_at)
);
CREATE INDEX IF NOT EXISTS idx_job_sources_query ON job_sources(query_slug, fetched_at);
```

- DDL in `schema.py:ensure_schema()`, next to `google_jobs_query_stats`.
- `pipelib.upsert.upsert()` returns only counts today. Add `UpsertResult.records:
  list[(id, outcome)]`, appended in the three existing branches. Purely additive —
  `__iter__`/`__add__` keep the `n, u, unc = upsert(...)` shape working in all six ingest
  scripts. **Don't break that; every ingest script uses it.**
- Rewrite `log_query_stats()` to derive `new_count` from `job_sources`, not from `upsert`'s
  raw `new`.
- `hashlib` is still imported in `google-serpapi.py` and currently unused — it's there for
  `key_id`.

### Step 5 — Postgres on Tailscale only ⚠️ security
**The running container publishes `0.0.0.0:5432`.** `ss -ltnp` confirms. `docker-compose.yml`
was edited to `127.0.0.1` on 2026-07-24 but the container predates it (up 2 days). Postgres is
reachable right now from the whole LAN at `192.168.1.111:5432`. **Docker's published ports
bypass firewalld** by writing straight into the DOCKER iptables chain, so a firewalld rule
will not cover this.

1. Rotate `POSTGRES_PASSWORD` **and** the password inside `DATABASE_URL` in `~/.hermes/.env`
   (they must match or compose fails fast). Also update `~/apps/jobs-api`'s environment.
2. `docker-compose.yml`:
   ```yaml
   ports:
     - "100.107.134.96:5432:5432"   # tailscale0 — fedora
     - "127.0.0.1:5432:5432"
   ```
3. `docker compose --env-file ~/.hermes/.env up -d --force-recreate postgres`, then confirm
   `ss -ltnp | grep 5432` shows **no** `0.0.0.0` line.
4. `ALTER SYSTEM SET idle_in_transaction_session_timeout = '15min'; SELECT pg_reload_conf();`

No TLS/proxy needed inside the tailnet — Tailscale is WireGuard, already encrypted and
device-authenticated. `jobs-api`'s README makes the same call.

### Step 6 — second worker on `erics-mac-mini`
`100.112.178.70`, online. (`erics-macbook-pro` has been offline 36 days — add later, the claim
TTL handles intermittent workers fine.)

```bash
git clone https://github.com/hermes-toes/jobs-script.git ~/hermes-scripts
cd ~/hermes-scripts && pip3 install 'psycopg[binary]'
```
`~/.hermes/.env` there (mode 600), **its own** SerpApi key:
```
DATABASE_URL=postgresql://nyc_events:<new-password>@fedora:5432/nyc_events
SERPAPI_API_KEY=<mac mini's own key>
```
Cron — **SerpApi step only** (the other five sources are free HTTP with no per-machine quota;
`score.py` is metered on a different key and belongs on the server):
```cron
30 2 * * * cd ~/hermes-scripts && git pull --ff-only && \
  /usr/bin/python3 ingest/google-serpapi.py >> ~/hermes-jobs.log 2>&1
```

### Step 7 — docs
- `README.md` — fix the wrong "shared not multiplied" claim (see above).
- `DATABASE.md` — "Multi-device access" still says it doesn't work and the port is
  localhost-bound. Rewrite for the tailnet bind.
- `DEVELOPER.md` — record the identity bug + fix, the date-filter result, move "multi-machine
  networking" out of TODO. Note the `google_jobs_query_stats` truncation.

---

## Files touched by this work

| File | State |
|---|---|
| `tools/verify-date-filter.py` | **new**, run, verified |
| `pipelib/ids.py` | modified — identity helpers |
| `pipelib/tests/test_pipelib.py` | modified — `TestGoogleJobIdentity` (92/92 pass) |
| `ingest/google-serpapi.py` | modified — `normalize_job()` |
| `ingest/google-apify.py` | modified — `normalize_job()`, dropped unused `hashlib` |
| `migrate_google_ids.py` | **new**, dry-run verified, **not applied** |
| `~/apps/jobs-api/query_claims.py` | modified — mirrored identity rule |

**Nothing has been committed.** Both repos have uncommitted changes.

**Pre-existing uncommitted changes NOT from this work** — don't attribute or bundle them:
`events/nyc-events-ingest.py`, `events/nyc-library-events-ingest.py`, `README.md`,
`ingest/builtin-nyc.py`, `score.py`, `tools/compare-models.py`,
`pipelib/geocode.py`, `pipelib/llm.py`, `backfill-scores.py`, `tools/cost-test.py`,
`pipelib/tests/test_builtin_description.py`.

---

## Decisions already made (don't re-litigate without new facts)

- **Identity migration:** migrate now with dry-run first, rather than new-rows-only or wipe.
  837 rows is the cheapest this will ever be — same reasoning `schema.py` used for doing
  `job_scores` at 44 rows.
- **App key custody:** the user's SerpApi key **never leaves their machine**. Extend the
  existing `~/apps/jobs-api` contributor-worker model; do not build hosted key storage. No
  encryption-at-rest, no breach surface, no liability.
- **Scope:** foundation first. The credit-market scheduler is deliberately deferred until
  there's ~2 weeks of *clean* yield data to tune against — which is only possible after
  Steps 3–4.

## Direction for later phases (designed, not built)

- **Phase 2 — keys as funded resources, decoupled from machines.** `serpapi_keys` registry
  keyed on `sha256(key)[:16]` (never the key): owner, plan, `searches_left`,
  `plan_renewal_date`, `account_rate_limit_per_hour`, `last_seen_at`. Whichever worker holds a
  key refreshes it from the free `/account` endpoint at run start. Per-key pacing is
  `floor((searches_left − reserve) / days_until_that_key's_renewal)` — anniversary-based.
  Global capacity = sum over keys seen recently, so an offline laptop contributes 0 with no
  manual step. Replaces `daily_budget` as the ceiling.
- **Phase 3 — value per credit instead of fixed bucket budgets.** Unit of work becomes
  `(query, page)`. One global ranked list:
  `value = strategic_weight × E[new distinct postings] × quality`, where `E[new]` comes from
  each query's arrival rate estimated from `job_sources` scaled by days-since-last-run
  (saturating at 10/page), and `quality` is the rolling share of that query's postings that
  aren't spam-reposter and score above threshold — which demotes the `remote zest jobs`
  queries automatically. Buckets become weights, not quotas, so surplus quota flows to
  whatever is next-best with no hardcoded leftovers valve. `try_claim()` and
  `MIN_HOURS_BETWEEN_RUNS` stay exactly as they are.
- **Phase 4 — multi-tenant.** Query bank moves to Postgres, **content-addressed**:
  `slug = hash(canonical(query, location, mode))`, so two users who both want
  "LLM engineer / NYC" land on the *same row* and cost one credit between them. That is the
  property that makes the app not waste queries as it grows.
  `query_subscriptions(slug, tenant_id, priority)` supplies `strategic_weight` as the sum of
  subscriber priorities. Per-user relevance needs nothing new — `job_scores(job_id, profile)`
  already exists for exactly this. Natural anti-freeloading rule: weight a tenant's queries by
  the quota their key contributes.

**One risk to flag:** keys belonging to *different people* (the app, other household machines)
is unambiguously fine. Several free accounts registered by one person to multiply a free tier
is a grey area — SerpApi's ToS doesn't address it explicitly, but their Team Management
positioning ("so searches don't end up scattered across separate personal accounts") suggests
they'd prefer consolidation. The design is agnostic either way.

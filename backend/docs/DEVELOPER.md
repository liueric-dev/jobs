# Jobs Pipeline — Developer Reference

Internal documentation for the job-discovery automation pipeline. If you're looking for the plain-language overview with diagrams and the build story, see `OVERVIEW.md` instead. This doc is for anyone (including future-you) who needs to actually modify or debug these scripts.

---

## Open Questions / TODOs

**Highest priority:**
- **Surfacing layer: backend built 2026-07-26, no frontend yet.** `score.py` scores every ingested job and nothing yet *presents* the results to a human — that is still true and the gap is not closed. What now exists is the half below the UI: `backend/webapp/`, a FastAPI service with Google SSO (email allowlist, opaque session cookies), `GET /v1/jobs` reading the `jobs_app` view, and `POST /v1/events` finally writing `job_events` — the table `SCORING.md` has always listed as "written by the surfacing layer" and which nothing had ever written. It connects as a new `jobs_web` role that can read the corpus and append engagement and rewrite nothing. See `backend/webapp/README.md`, and `docs/tasks/` at the repo root for the work breakdown and the decisions behind it. **What remains is `frontend/`**, still empty: nothing renders any of this.

**Needs infrastructure work, not code:**
- Multi-machine networking isn't set up yet — the claim-based scheduler (see below) is built and tested, but running it from a second physical machine requires: (1) making the home-PC Postgres instance reachable over a private network (Tailscale recommended over exposing it to the open internet), and (2) replacing the checked-in default DB password (`nyc_events_password`) once the instance is reachable beyond localhost — that default was only ever reasonable under a "this is genuinely localhost-only" assumption.
- Each additional machine just needs its own `SERPAPI_API_KEY` in its own `./.env` and a synced copy of `config/google-queries.json`.
- **Script distribution (decided 2026-07-24, not yet done): git, pull-before-run.** The plan for running from the laptops: make `~/apps/jobs` a git repo (bare repo hosted on the server over Tailscale/SSH, or a private GitHub repo — either works), and each worker machine runs `git pull --ff-only && python3 run-daily.py` as its entry point. This beats ad-hoc copying/`scp`-ing from the server because every machine states exactly which version it ran, updates are atomic, and a broken edit on one machine can't silently propagate. Phones: technically runnable (Termux on Android can do Python+psycopg over Tailscale) but not worth the upkeep — the min-interval guard means extra machines add resilience and quota, not coverage, so two laptops + server is already plenty.

**Quota management (designed 2026-07-24, not yet built):**
- **Pace to the monthly cycle instead of a fixed 8/day.** SerpApi's account endpoint (`GET https://serpapi.com/account?api_key=…`) returns searches used/remaining for the current cycle. Planned logic: at the start of a run, compute `daily_allowance = floor(remaining_quota / days_left_in_cycle)` and use that (scaled across the buckets in their existing ratios) instead of the static `daily_budget` sum. This one formula solves both directions: overspending early in the month automatically lowers the allowance for the rest of the cycle (a *hard* daily cap, but self-correcting rather than a hard monthly stop that would go dark for a week), and a surplus near refresh automatically gets spent down (allowance grows as `days_left` shrinks) — no separate "burn it before it expires" mechanism needed. Multi-user note if this ever grows users: hard-cap per day at the formula, warn (don't block) when someone's trajectory would exhaust early, and hold back ~10% of quota as reserve.

**Scoring model (decided 2026-07-24):**
- **Default stays a cloud model** — workers must run on machines with no GPU, so cloud is the only universal default; `glm-4.5-flash` (free) remains it until it demonstrably falls short. Evaluation plan before spending money: build a golden set of ~20-30 already-scored jobs with hand-checked expected `primary_track`/rough score, then run candidate backends (paid cloud, other free tiers like Groq/OpenRouter, and Ollama on the server as a local option) against it comparing JSON validity rate and score agreement. The server-local-model experiment is worthwhile purely for token savings *on the server's own runs* — laptops would still use cloud.

**Known bug, unfixed (found 2026-07-26, slice D):**
- **`posted_at` slides forward for the Google sources.** They report publication as a relative string ("23 days ago"), and `parse_relative_posted_at` resolves it as `now - delta` on *every* ingest — so the stored date is anchored to when the row was last written, not to when the posting went up. Re-ingest the same payload a week later and `posted_at` moves a week later. Two effects: the date is wrong and drifts, and since `posted_at` is in `HASH_FIELDS_SHORT`, a re-seen Google posting can never be counted "unchanged" (a serpapi run reports `0 unchanged` where `ats.py` reports thousands). Measured: 706 of 835 `google_jobs` rows are derived this way but only 6 have actually drifted, because Google's ranking rotates and most postings are written once — a slow leak rather than present damage. The fix is to pin `posted_at` on first write (or anchor to `first_seen`), not to round it; existing rows are backfillable from `raw_json` + `first_seen`. Row identity is safe — `make_job_id` excludes `posted_at`. Full write-up in `~/apps/REORG.md`, "The sliding `posted_at`".

**Real open questions:**
- **Scoring model reliability across backends is untested.** `score.py` calls a plain OpenAI-compatible endpoint directly now (no Hermes dependency — see its section below), but has only actually been run against `glm-4.5-flash` via Z.ai. Genuinely different backends (local Ollama, Groq, OpenRouter's free models) haven't been tried — not yet stress-tested for JSON-output reliability.
- **Adaptive query cadence isn't built.** `google_jobs_query_stats` logs `(new_count, days_since_last_run)` per query per run, but nothing yet computes "this query only fills a page every ~4 days, so revisit it every 2-3 days instead of daily." The data exists; the logic doesn't.
- **Google Jobs noise isn't filtered.** Spammy aggregator reposts (e.g. "remote zest jobs") and geo-mismatched remote listings (e.g. "Remote - India" surfacing on a US-scoped search) currently just sit in the table untagged. Not urgent at current volume.

**Considered and ruled out (2026-07-24) — don't re-litigate without new facts:**
- **"Paginate until we see the last job we already saw" as a completeness strategy.** Doesn't work on Google Jobs: results are *relevance*-ranked, not chronological, so "last seen posting" is not a frontier — it can sit on page 1 while genuinely new postings sit on page 5, or drop out of the ranking entirely (loop never terminates or terminates instantly-and-wrong). There are no sponsored/stickied slots in SerpApi's `google_jobs` results to worry about; ordering alone breaks the invariant. The equivalent guarantee we *can* get is already implemented: the `date_posted` chip scoped to the gap since last success. If deeper coverage per query is ever wanted, the correct upgrade is date-chip **plus** paginating through that filtered result set (SerpApi `next_page_token`, 10 results and 1 credit per page, hard `MAX_PAGES` cap) — that set *is* bounded and fully enumerable. Not enabled now because at 8 queries/day the extra credits aren't there; revisit if quota grows. (The chronological sources — WWR RSS, HN thread — already fetch their full feed each run, so this question doesn't apply to them.)

**Multi-user crowdsourcing — BUILT, and since slice D it lives in `api/`:**

It was a standalone repo at `~/apps/jobs-api` until 2026-07-26, on the reasoning that `~/.hermes` was the harness's private directory and had no business being a dependency of a persistent, eventually internet-facing server. That reasoning was sound; its conclusion stopped being right once the pipeline itself moved to `~/apps/jobs`. See `api/README.md` for API details, security model, and deployment steps.

- **Shape:** contributors get an admin-issued API key (`api/manage_users.py`), pull claimed queries from `POST /v1/queries/claim`, run them against SerpApi with **their own** key, and `POST .../submit` the raw results. Only this service talks to Postgres — no contributor ever gets DB credentials. Apify is deliberately *not* exposed (it bills Eric's account per result).
- **The two now share code, and the reason is a scar.** `api/` had copied nine functions and the DDL for three tables out of this pipeline, and the copies had drifted six ways — including `strip_html` truncating at 5000 instead of 20000 and `parse_relative_posted_at` not understanding "yesterday". Both feed `content_hash`, which is row identity, so the same posting written by each side produced two different digests and they rewrote each other's rows on alternating runs. `normalize_job` now lives once, in `google_jobs.py`, imported by `ingest/google-serpapi.py`, `ingest/google-apify.py` and `api/query_claims.py` alike. `api/` also imports `schema.py` for the DDL it does not own.
- **The claim SQL is still deliberately separate**, and that part of the original reasoning holds: the two coordinate through the *same Postgres row* (`job_ingest_state`, `google_jobs:query:<slug>`) using the same atomic conditional update, so row-level locking extends the "two claimants never get the same query" guarantee across both automatically. Verified live: 18 concurrent claims across two contributors, zero overlap. `api/`'s version is a superset — it adds `claimed_by` and `claim_granted_at`, which this pipeline has no need to ask about.
- **A real bug this surfaced, worth knowing if you touch the claim SQL here:** `try_claim_query()` in `ingest/google-serpapi.py` sets `claimed_at` but has no knowledge of the `claimed_by` column the API added — so when this local pipeline legitimately takes over an expired claim, `claimed_by` is left stale. A naive `claimed_by == caller` ownership check on the API side therefore passed for a contributor whose claim had *already been taken over by this pipeline*, letting them submit results and advance the watermark mid-fetch. Fixed entirely on the API side (a `claim_granted_at` column pinned to the exact grant; any takeover rewrites `claimed_at` and invalidates it), so **no change was needed here** — but if you ever add ownership semantics to these scripts, that asymmetry is the thing to remember.
- **Schema impact on this pipeline: additive only.** That service adds `job_ingest_state.claimed_by` / `.claim_granted_at` and the `contributors` / `api_keys` / `submission_log` tables. These scripts never read or write any of them, and nothing they own was altered.
- **Still Eric's to do before it's live:** domain/TLS/reverse proxy, firewalling Postgres, and rotating the default DB password (same prerequisite already listed above for multi-machine).

**Long-standing, still deferred:**
- Indeed ingestion — no verified-working Apify actor found yet (unlike Google Jobs, where `johnvc/google-jobs-scraper---pay-per-result` was confirmed live). SerpApi has no Indeed product at all.
- `ai-jobs.net` scraper (confirmed feasible, not yet built).
- Widening `config/companies.json` beyond its current 68 companies; resolving its `checked_but_not_found` list via JSON-LD.
- Entirely separate, deliberately non-automated tracks: resume/tailoring, application tracker (Teal/Huntr/Simplify), networking cadence.

---

## What this is

A daily cron pipeline that discovers tech/AI job postings from 7 independent sources, writes them into a shared Postgres table, and scores them against a specific candidate persona using an LLM. It does NOT apply to jobs, track applications, or handle networking — those are deliberately manual.

## Directory layout

Reorganized 2026-07-24 (was a flat directory of `*-ingest.py` files; old→new mapping in the git-less backup at the bottom of this doc's changelog): code at the top level is "the pipeline" (orchestrator + scoring), `ingest/` is one file per source, `config/` is everything meant to be hand-edited without touching code.

Tidied again 2026-07-26. The root had accumulated four unrelated kinds of thing — the live pipeline, five one-off migrations, four backfill drivers, and six large docs — so the three that are not the pipeline moved into `migrations/`, `scripts/` and `docs/`. **Nothing was renamed and no module's import name changed**; the moved files each gained the same one-line parent insert `ingest/` and `tools/` already use.

Split into `backend/` and `frontend/` on 2026-07-26. `frontend/` is empty; the
surfacing layer named at the top of this document is what will go in it. The
split was a pure move — every path below resolves relative to `backend/`, so no
import, no `sys.path` insert and no shell `cd` changed.

`backend/webapp/` was added the same day: the service `frontend/` will call.
It is a sibling of `api/`, not an extension of it — `api/` is the contributor
work queue whose role is deliberately granted nothing on the pipeline tables,
and is expected to be deprecated. `webapp/` imports nothing from it, reaching
`schema.py` and `lib/` through the same one-line parent insert every
subdirectory here uses.

```
~/apps/jobs/backend
├── run-daily.py                # single cron entry point, runs everything below in order
├── extract.py                  # per-posting LLM facts, shared by every profile
├── match.py                    # free per-profile ranking over those facts
├── score.py                    # LLM fit-scoring layer, runs last
├── schema.py llm.py relevance.py profiles.py ratelimit.py google_jobs.py
├── README.md                   # operating the pipeline
├── requirements.txt            # psycopg[binary] — the only third-party dependency
├── config/                     # hand-edited, no code changes needed
│   ├── companies.json          # 68 companies with verified ATS board tokens
│   ├── google-queries.json     # shared query bank (4 buckets) for both Google scripts
│   ├── criteria.json           # match.py's weights
│   ├── relevance.json          # the shared title filter
│   └── persona.json            # candidate background + bucket definitions, LLM-editable
├── ingest/                     # one script per source, all independently runnable
│   ├── ats.py                  # Tier 1: direct Greenhouse/Lever/Ashby API pulls
│   ├── builtin-nyc.py          # Built In NYC scrape
│   ├── weworkremotely.py       # We Work Remotely RSS feeds
│   ├── hn-hiring.py            # HN "Who is hiring?" monthly thread
│   ├── google-serpapi.py       # Google Jobs via SerpApi (primary)
│   └── google-apify.py         # Google Jobs via Apify (supplemental)
├── lib/                        # vendored mechanism layer — see lib/__init__.py
├── migrations/                 # one-off, dry-run by default, idempotent
├── scripts/                    # backlog drivers: run them by hand, not on a timer
├── tools/                      # measurement and comparison, never part of a run
├── tests/                      # stdlib unittest; test_row_identity.py is the guard
├── api/                        # the contributor-facing service (its own README)
├── webapp/                     # the frontend-facing service: SSO + read API
└── docs/
    ├── DEVELOPER.md            # this file
    ├── OVERVIEW.md             # public-facing overview + diagrams + build retrospective
    ├── SCORING.md              # how a posting becomes a recommendation, and its cost
    └── HANDOFF-*.md            # open-question write-ups
```

Old→new names, for reading older notes/commits: `daily-jobs-ingest.py`→`run-daily.py`, `jobs-ingest.py`→`ingest/ats.py`, `builtin-nyc-ingest.py`→`ingest/builtin-nyc.py`, `weworkremotely-ingest.py`→`ingest/weworkremotely.py`, `hn-hiring-ingest.py`→`ingest/hn-hiring.py`, `google-jobs-serpapi-ingest.py`→`ingest/google-serpapi.py`, `google-jobs-apify-ingest.py`→`ingest/google-apify.py`, `job-score.py`→`score.py`, `job-sources.json`→`config/companies.json`, `google-jobs-queries.json`→`config/google-queries.json`, `job-scoring-persona.json`→`config/persona.json`.

All scripts resolve sibling files relative to their own location (`ingest/` scripts go one level up to reach `config/`), not the process's working directory — so the whole folder can still be moved as a unit. That property is what made slice D's move cheap. Run ingest scripts from the repo root as `python3 ingest/<name>.py` (or from anywhere — CWD doesn't matter).

**`sys.path` (rewritten in slice D, simplified again in slice G).** Root-level scripts do nothing at all: Python already puts a script's own directory on `sys.path[0]`, and that is now also how `lib/` is found — it is a package inside this repo, not something installed. Only `ingest/`, `tools/`, `migrations/` and `scripts/` need help, because they sit one level below the modules they import, and each adds its parent in one line; that single insert reaches `schema`, `relevance`, `llm` **and** `lib` together. `api/query_claims.py` does the same, and `api/app.py` imports `query_claims` *before* `lib` for exactly that reason — keep that ordering. `migrations/migrate_ats_descriptions.py` additionally adds `ingest/`, which is not a package — four of its filenames are hyphenated.

The subdirectories that read `config/` resolve it against the repo root, not their own directory — `migrations/migrate_profiles.py` and `migrate_scores.py` both do, and `scripts/backfill-scores.py` runs its `score.py` subprocess with the root as `cwd` for the same reason. The three shell scripts in `scripts/` `cd` to the root before doing anything, so `. ./.env` and every relative path below it keep working unchanged. Before slice D all 24 walked up the tree hunting for a `pipelib/` directory and inserted two paths; the second insert was the load-bearing one, and it is why moving `pipelib` used to break `import schema`. Don't reintroduce that pattern.

## Pipeline order (`run-daily.py`)

```
ingest/ats.py → ingest/builtin-nyc.py → ingest/weworkremotely.py → ingest/hn-hiring.py
              → ingest/google-serpapi.py → ingest/google-apify.py → score.py
```

All steps always run even if an earlier one fails (independent sources — one being down isn't a reason to skip the rest). Exit code is non-zero if any step failed. `ingest/google-apify.py` must run after the SerpApi step (see its own docstring), and `score.py` runs last since it scores whatever the other six just ingested.

Scheduled: the `jobs-ingest.timer` systemd user unit, daily at midnight local. Slice D moved this off `hermes cron` — the scheduler requires any script it runs to resolve inside `~/.hermes/scripts` and explicitly blocks symlink escape, so moving the code out forced the scheduling change.

The old hermes entry (`daily-jobs-ingest`, `43f2e0330e75`) is still present but **paused, and it is not a rollback** — it points at `jobs/run-daily.py` inside `~/.hermes/scripts`, a path that no longer exists, so resuming it would fail rather than restore anything. Its last real run (2026-07-25) had already failed all 7 steps with `fe_sendauth: no password supplied`, because the hermes scheduler strips secrets out of the subprocess environment via `_sanitize_subprocess_env`. Delete it; do not plan around it. A real rollback means putting the code back, not un-pausing the entry.

## Per-script reference

| Script | Source | Volume/day | Close semantics |
|---|---|---|---|
| `ingest/ats.py` | 68 companies' own Greenhouse/Lever/Ashby APIs | full current listing per company | exact-diff (missing = closed) |
| `ingest/builtin-nyc.py` | builtinnyc.com/jobs, pages 1-3 | ~60 sampled listings | staleness (14 days) |
| `ingest/weworkremotely.py` | 4 WWR category RSS feeds | ~250 items | staleness (21 days) |
| `ingest/hn-hiring.py` | current month's HN "Who is hiring?" thread | ~250-350 parsed comments | staleness (40 days) |
| `ingest/google-serpapi.py` | SerpApi `google_jobs` engine | 8 queries/day (free tier) | staleness (30 days) |
| `ingest/google-apify.py` | Apify `johnvc/google-jobs-scraper---pay-per-result` | 1 query/day | staleness (30 days) |
| `score.py` | scores rows from ALL the above | 30 jobs/day (default cap) | n/a (additive columns) |

Every ingest script is independently runnable and testable:
```
python3 <script>.py
DEBUG_PRINT_KEYS=1 python3 <script>.py
```
`DEBUG_PRINT_KEYS=1` is the consistent convention across every script in this pipeline for verbose per-item stderr logging.

### Why staleness-based closing, not exact-diff, for most sources

Only `ingest/ats.py` gets exact-diff closing (a company's ATS API always returns its *full* current listing, so anything missing from a fresh pull really did close). Every other source returns a bounded, sampled slice (Built In's ~60 most-recent NYC listings, WWR's per-category feed, Google Jobs' per-query top-10, HN's one monthly thread) — a job absent from one run's sample may just have scrolled past the sample window, not actually closed. Marking it closed on that basis would be wrong, so these sources instead close a row only after it hasn't been *re-seen* for N days (14/21/40/30 depending on the source's own typical refresh cadence).

## Google Jobs — the more involved subsystem

### Query bank (`config/google-queries.json`)

4 buckets, weighted to the candidate's actual positioning (5 YOE full-stack SWE, 2.5yr career break, currently 5 months into a prompt/agent engineering program — see `config/persona.json` for the full profile):

| Bucket | daily_budget (free tier) | Paid-tier target | Focus |
|---|---|---|---|
| `core_swe` | 2 | 6 | full-stack/backend/data/devops — safety net, broadest pool |
| `ai_integration` | 3 | 10 | LLM/agent/prompt/applied-AI engineer — highest strategic alignment |
| `bridge_solutions` | 2 | 8 | forward-deployed/AI-solutions/technical-solutions engineer — strongest-fit niche |
| `reentry_growth` | 1 | 4 | returnship/career-break/return-to-work phrasing |

Bucket `daily_budget`s sum to `SERPAPI` free-tier capacity (8/day = 250/mo ÷ ~30). To upgrade: bump each bucket's `daily_budget` directly in the JSON — no code change.

### Scheduling: per-bucket least-recently-run + atomic claiming

`pick_stale_queries_by_bucket()` (SerpApi) and `pick_stale_queries()` (Apify, scoped to `ai_integration`+`bridge_solutions` only) both:
1. Sort each bucket's queries by `last_success_at` (never-run sorts first, via empty-string sentinel).
2. Walk the sorted list attempting an **atomic claim** on each candidate via `try_claim_query()`, until `daily_budget` claims succeed or the bucket is exhausted.

The claim is what makes this safe to run from **multiple machines simultaneously**, each with its own SerpApi account:
```sql
INSERT INTO job_ingest_state (dataset, last_success_at, claimed_at)
VALUES (%(dataset)s, '', %(now)s)
ON CONFLICT (dataset) DO UPDATE
    SET claimed_at = %(now)s
    WHERE job_ingest_state.claimed_at IS NULL OR job_ingest_state.claimed_at < %(ttl_cutoff)s
RETURNING dataset
```
Postgres's row-level locking makes this a real guarantee, not best-effort — verified with an actual concurrency test (two instances launched simultaneously, zero overlap in what they picked, graceful degradation when a bucket ran out of unclaimed candidates). `CLAIM_TTL_MINUTES=15` bounds how long a crashed machine blocks a query; a genuine fetch failure calls `release_claim()` to free it immediately instead of waiting out the TTL (a different machine's account might not share the same transient error).

No static per-machine query partitioning is used or needed — the claim system gives automatic load-balancing/failover across however many machines are running.

**Min-interval guard (added 2026-07-24):** claims clear on success, so before this guard a second machine running `run-daily.py` later the same day would happily re-claim and re-run queries the first machine already ran — burning its quota re-fetching a `chips=date_posted:today` window that's nearly all overlap. Both pick functions now skip any candidate whose `last_success_at` is within `MIN_HOURS_BETWEEN_RUNS` (default 20h, env `GOOGLE_JOBS_MIN_HOURS_BETWEEN_RUNS`), and because candidates are walked stalest-first, hitting one too-recent candidate ends the whole bucket — everything after it is even fresher. Net effect: `daily_budget` is now a true *per-query-bank-per-day* budget across all machines combined, not per-machine. 20h rather than 24h so a daily cron whose start time drifts a few minutes doesn't skip a legitimate next-day run. A machine with nothing stale to do exits cleanly having claimed nothing.

**Failure recovery / resume semantics (verified in code, not just intended):** `mark_success()` is the *only* thing that advances `last_success_at`, and it only runs after a successful fetch+upsert. A failed query releases its claim immediately (`release_claim()`) and leaves the watermark untouched — so the next run (any machine, any day) sees the true gap-since-last-success and `choose_date_chip()` widens the date filter to cover it (`today`→`3days`→`week`→`month`). A query that fails for a week self-heals with one `week`-chip run. Per-query failures don't abort the script (only all-queries-failed exits non-zero), and per-script failures don't abort `run-daily.py` (all steps always run; exit code reflects failures afterward).

**IP addresses are a non-issue for this multi-machine setup.** SerpApi's own infrastructure is what talks to Google — the calling machine's IP/identity is irrelevant to Google's bot defenses, since Google never sees it. This is unrelated to the Apify CAPTCHA-blocking risk discussed below, which was specifically about direct browser automation against Google.

### Date filtering

`choose_date_chip()` picks SerpApi's `chips=date_posted:X` bucket (`today`/`3days`/`week`/`month`) based on how long it's actually been since *that specific query* last succeeded — not always "today". A query's first-ever run gets no filter at all (deliberate backfill). `hl=en&gl=us` are pinned on every call — without them, Google intermittently returns non-English relative timestamps that the parser's English-only regex silently fails on.

The Apify actor (`johnvc/google-jobs-scraper---pay-per-result`) has no equivalent date-filter parameter (confirmed by inspecting its full input schema) — it always returns current top-ranked results regardless of when it last ran.

### Why SerpApi + this specific Apify actor, not DIY scraping

Google shipped anti-scraping tech ("SearchGuard") in Jan 2025 and is actively suing SerpApi (Dec 2025) over circumvention. Live-tested the cheaper, more obvious Apify actor choice (`khadinakbar/google-jobs-scraper`, $0.003/result, Playwright browser automation) — it got Google's actual CAPTCHA page on 2/2 test queries, real confirmation this is a live, current risk, not theoretical. `johnvc/google-jobs-scraper---pay-per-result` ($0.015/result, 5x pricier) uses a different approach and returned clean, correct results in the same test session (confirmed via identical `job_id` values to SerpApi's own output for the same posting).

**Cost discipline, non-optional**: this Apify actor's `num_results` defaults to 100 and `max_pagination` to 0 (unlimited) if left unset — an early uncapped test call cost $1.50, 30% of the entire monthly $5 free-tier credit, in one shot. Every call in `ingest/google-apify.py` hardcodes explicit `num_results`/`max_pagination` — never rely on this actor's defaults if modifying that script.

## The scoring layer (`score.py`)

Adds `fit_score` (0-100), `primary_track`, `gap_friendly_signal`, `key_technologies`, `gap_bridging_angle`, `risk_factors`, `scored_at`, `scoring_model` columns to the `jobs` table via `ALTER TABLE ADD COLUMN IF NOT EXISTS` (the table already exists from the ingest scripts — `CREATE TABLE IF NOT EXISTS` is a no-op there and won't add columns).

**Swappable LLM backend, zero Hermes dependency (revised 2026-07-24).** This originally shelled out to `hermes -z`. Changed because this script needs to run standalone on other (SerpApi/Apify worker) machines that shouldn't need a full Hermes install just to score jobs — and Hermes was never actually necessary for swappability, only convenient. It now calls a plain OpenAI-compatible `/chat/completions` endpoint directly via stdlib `urllib` — that wire format is a de facto standard across OpenAI itself, most free-tier providers (Groq, OpenRouter), and local model servers (Ollama, LM Studio). Swapping backends is `JOB_SCORING_BASE_URL`/`JOB_SCORING_MODEL`/`JOB_SCORING_API_KEY` env vars — no code change, no Hermes required anywhere.

**A real dead end worth knowing about, in case it comes up again**: the default model is `glm-4.5-flash`, not the more capable `glm-4.7` that Hermes itself was successfully using all session. Direct calls to `api.z.ai/api/paas/v4/chat/completions` with the same `GLM_API_KEY` and model `"glm-4.7"` return `"Insufficient balance or no resource package"` — yet `hermes -z -m glm-4.7 --provider zai` kept working the whole time, using (per `hermes auth`'s credential pool listing) that same env var. Never fully root-caused the discrepancy — possibly Hermes routes it through Nous Portal's own infrastructure rather than a raw pay-per-token Z.ai account, but that's a guess, not a confirmed answer. What IS confirmed: testing several model-ID strings against the same endpoint/key found `glm-4.5-flash` works cleanly, including with `response_format=json_object`. Swap `JOB_SCORING_MODEL` back to `glm-4.7` if that balance question ever gets resolved directly on Z.ai's side — that's a billing matter, not something this script can fix.

`parse_llm_json()` is intentionally tolerant — strips markdown fences and pulls the `{...}` substring rather than requiring the entire response to be valid JSON, even though `response_format=json_object` is now requested explicitly on every call (some OpenAI-compatible servers, especially smaller local ones, ignore or loosely honor that field). A job whose scoring attempt fails or returns unparseable JSON still gets `scored_at` set (with `scoring_model="FAILED:..."`) so it isn't retried forever — same tombstone lesson as `hn_seen_comments` in `ingest/hn-hiring.py`.

`config/persona.json` is meant to be hand-edited directly (background summary, strengths, honest gaps, the 4 bucket descriptions, scoring instructions) without touching code.

**Known open question**: JSON-output reliability has only been validated against `glm-4.5-flash` — genuinely different (especially smaller/local) models haven't been stress-tested.

## Data model

Single shared table: `jobs` in the `jobs` database's `public` schema. Shares a Postgres instance with the unrelated `nyc-events-ingest.py` pipeline and nothing else — slice E gave each application its own database and its own role, replacing the earlier arrangement where a `jobs` schema sat inside the events database and only a per-connection `search_path` kept them apart.

Key columns:
- `id` — `sha256(platform:company_token:source_id)[:24]`, the dedup key across every source
- `platform` — `greenhouse`/`lever`/`ashby`/`builtin`/`weworkremotely`/`hn_whoishiring`/`google_jobs`
- `status` — `open`/`closed`, never deleted (except `ingest/ats.py`'s `prune_old_closed`, 30 days)
- `seniority_guess`, `location_is_nyc`, `location_is_remote` — heuristic-tagged, not filtered at ingest; query them yourself rather than trusting rows were already dropped
- `fit_score`, `primary_track`, `gap_friendly_signal`, `key_technologies`, `gap_bridging_angle`, `risk_factors`, `scored_at`, `scoring_model` — added by `score.py`, NULL until scored

Bookkeeping tables:
- `job_ingest_state` — `(dataset, last_success_at, claimed_at)`, watermarks for every source AND the Google Jobs claim mechanism, keyed by dataset strings like `google_jobs:query:<slug>` or `builtin:nyc`
- `google_jobs_query_stats` — `(slug, run_at, new_count, total_fetched, days_since_last_run)`, per-run history for the not-yet-built adaptive-cadence feature
- `hn_seen_comments` — `(comment_id)`, tombstone so unparseable HN comments aren't re-fetched forever

## Secrets

`SERPAPI_API_KEY`, `APIFY_API_TOKEN` live in `./.env` (mode 600, gitignored, template in `.env.example`), same convention as this file's other API keys (`GLM_API_KEY`, `TAVILY_API_KEY`, etc.) — NOT hardcoded in script source, since (unlike the low-stakes localhost-only `DATABASE_URL` default that IS hardcoded as a fallback in every script) these are real billing-linked secrets. `score.py`'s `JOB_SCORING_API_KEY` falls back to the already-present `GLM_API_KEY` if unset — set it explicitly (to whatever the target `JOB_SCORING_BASE_URL` actually needs) on any machine using a different LLM backend.

## Reference

Eric had another LLM independently draft a competing architecture plan (`~/Downloads/job_ingestion_architecture_plan.pdf`), reviewed 2026-07-24. Converged on the core mechanics (SerpApi + ATS, 8/day free-tier budget, page-1-only extraction). Useful ideas adopted from it: the AI-scoring-layer concept (became `score.py`) and the 4-bucket taxonomy concept. A real flaw it had that got caught: it appended recency phrases directly into query text instead of using SerpApi's documented `chips` parameter — reviewing that also surfaced the locale bug described above.

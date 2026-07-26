# jobs-pipeline

Daily job-discovery automation. Pulls tech/AI postings from seven independent
sources into one Postgres table, dedupes them, and has an LLM score each one
against a specific candidate profile.

It **finds and judges** jobs. It does not apply to them, track applications, or
do outreach — those stay manual on purpose.

- `OVERVIEW.md` — plain-language tour, diagrams, and the build story
- `DEVELOPER.md` — architecture, design decisions, open questions

## Sources

| Script | Source | Volume/day |
|---|---|---|
| `ingest/ats.py` | 68 companies' Greenhouse / Lever / Ashby APIs | full listing per company |
| `ingest/builtin-nyc.py` | builtinnyc.com/jobs, pages 1–3 | ~60 |
| `ingest/weworkremotely.py` | 4 WWR category RSS feeds | ~250 |
| `ingest/hn-hiring.py` | HN "Who is hiring?" monthly thread | ~250–350 |
| `ingest/google-serpapi.py` | Google Jobs via SerpApi | 8 queries (free tier) |
| `ingest/google-apify.py` | Google Jobs via Apify | 1 query |
| `score.py` | LLM fit-scoring over everything above | 30 jobs |

Everything lands in `jobs.jobs`, deduped on `sha256(platform:company_token:source_id)`.

## Requirements

- Python 3.9+
- `psycopg[binary]` — the only third-party dependency
- Postgres reachable via `DATABASE_URL`
- API keys for the sources you want (see [Configuration](#configuration))

```bash
pip install 'psycopg[binary]'
```

## Setup

### 1. Get the code

```bash
git clone <this repo> ~/hermes-scripts
cd ~/hermes-scripts
```

> **Layout note:** the jobs pipeline lives under `jobs/` in this repo,
> alongside the shared `pipelib/` library it imports. The events pipeline
> used to live here too; it moved to `~/apps/events` in slice C of
> `~/apps/REORG.md`. Run the jobs scripts from the repository root, as the
> commands below do -- `pipelib` is located by walking up from each
> script, so running them from elsewhere still works, but the paths shown
> assume the root.
>
> `pipelib` is now also installable (`pip install --user -e .`), which is how
> out-of-tree consumers import it. The walk-up stays for these scripts
> because in 22 of them the same block supplies `jobs/`'s own `sys.path`
> entry, not just pipelib's -- slice D rewrites them.

### 2. Point it at the database

The pipeline needs a `DATABASE_URL`. **No credential is stored in this repo** —
the default is passwordless and will fail against a password-protected server,
which is intentional.

On the machine hosting Postgres, this pipeline reads it from `~/.hermes/.env`
(loaded automatically by `hermes cron`). On any other machine, export it:

```bash
export DATABASE_URL="postgresql://nyc_events:PASSWORD@SERVER:5432/nyc_events"
```

Where `SERVER` is the database host — over Tailscale, its MagicDNS name
(`homeserver.tailXXXX.ts.net`). **Don't expose Postgres to the public
internet.** Tailscale gives you an encrypted, device-authenticated link with
no port-forwarding.

### 3. Verify the connection

```bash
python3 -c "
import os, psycopg
c = psycopg.connect(os.environ['DATABASE_URL'], connect_timeout=5)
print('rows:', c.execute('SELECT count(*) FROM jobs.jobs').fetchone()[0])"
```

Schema is created automatically on first run — no migration step for a fresh
database.

### 4. Upgrading an existing database

One migration exists, for databases that predate `jobs.job_scores` (scores used
to be eight columns on `jobs.jobs`). It's a no-op on a fresh install and safe to
run twice:

```bash
python3 jobs/migrate_scores.py                       # dry run — reports, changes nothing
python3 jobs/migrate_scores.py --apply               # copy scores into job_scores
python3 jobs/migrate_scores.py --apply --drop-columns  # ...and remove the old columns
```

Copying is idempotent and never overwrites a newer score. `--drop-columns` is
separate and opt-in because it's the only destructive step here; it refuses to
run while any scored row hasn't been copied.

## Running

### On the server (scheduled)

`run-daily.py` runs all nine steps in order, in one process, and loads
`~/.hermes/.env` itself. **`hermes cron` does not load it for you** — this
README used to claim it did, and the 2026-07-25 scheduled run failed all seven
steps at once on a missing `DATABASE_URL` and missing API keys because of it.
Anything already exported wins over the file, so a one-off run can override a
single key.

```bash
hermes cron list                      # confirm it's registered
hermes cron run daily-jobs-ingest     # trigger a run now
```

To register it fresh:

```bash
hermes cron create "0 0 * * *" "" --script jobs/run-daily.py --no-agent \
    --name daily-jobs-ingest --deliver origin
```

Every step runs even if an earlier one fails — the sources are independent, so
one being down is no reason to skip the rest. Exit code is non-zero if any
step failed.

Plain cron works too:

```cron
0 0 * * * cd ~/hermes-scripts && DATABASE_URL="postgresql://..." /usr/bin/python3 jobs/run-daily.py
```

### On other devices (ad hoc)

**Run only the SerpApi step.** That's the one place a second machine actually
helps — it uses *that machine's own* SerpApi quota, multiplying total coverage:

```bash
export DATABASE_URL="postgresql://nyc_events:PASSWORD@homeserver.tailXXXX.ts.net:5432/nyc_events"
export SERPAPI_API_KEY="<this machine's own key>"
python3 jobs/ingest/google-serpapi.py
```

The other six sources are free HTTP fetches with no per-machine quota, so
running them from a laptop just re-fetches what the server already has. You
*can* run the full `run-daily.py` from anywhere — it's safe, just redundant.

**Multiple machines can run at the same time.** Coordination is automatic; see
below.

### Individual scripts

Every script is independently runnable and testable:

```bash
python3 jobs/ingest/builtin-nyc.py
DEBUG_PRINT_KEYS=1 python3 jobs/ingest/google-serpapi.py   # verbose per-item logging
```

`DEBUG_PRINT_KEYS=1` is the convention across every script here.

## Reading the results: `jobs.jobs_app`

**Query the `jobs.jobs_app` view, not `jobs.jobs`.** The base table is
deliberately unfiltered — `ingest/ats.py` pulls entire company job boards, so
roughly two thirds of it is roles this pipeline exists to ignore (enterprise
sales, tax directors, clinical staff). The view is the supported read surface:

```sql
SELECT title, company_name, job_url, posted_at_ts, match_score, fit_score
FROM jobs.jobs_app
WHERE profile = 'tech'
ORDER BY match_score DESC, posted_at_ts DESC NULLS LAST
LIMIT 50;
```

It guarantees the four fields a listing cannot render without — `company_name`,
`title`, `job_url`, `description_text` are all non-empty — plus `status='open'`,
and joins in facts, match scores and narratives. One row per (job, profile).

Those are **not** `NOT NULL` constraints on the columns, on purpose:
`ingest/builtin-nyc.py` legitimately writes a listing row first and fills
`description_text` on a later pass, because Built In rate-limits detail-page
fetches. A column constraint would break that two-phase write. Enforcing
completeness at the read edge keeps both properties — partial rows may exist,
but nothing downstream can see one.

Two columns worth knowing about:

| Column | Notes |
|---|---|
| `posted_at_ts` | `TIMESTAMPTZ`, and the only date you can sort on. `jobs.posted_at` is TEXT, is part of `content_hash` (so its format is frozen), and holds three incompatible formats — ISO from most sources, `NULL` from Google when the posting gave no date, and relative English from Built In (`"Reposted 8 Hours Ago"`). For Greenhouse it prefers `first_published` over `updated_at`, so "posted" means posted. |
| `salary` | `builtin`'s parsed `salary_text` when present, else the LLM-extracted `comp_min`/`comp_max`. Sparse — most postings disclose nothing. |

## How multiple machines stay out of each other's way

There are 32 Google Jobs queries but only ~8 SerpApi credits/day on the free
tier. If two machines each independently picked "the stalest query," they'd
pick the *same* one and waste two credits on identical results.

A lock in the database prevents that. Before running a query, a machine writes
a claim into `job_ingest_state`. Postgres guarantees exactly one machine wins,
even under simultaneous writes; the loser moves to the next-stalest query.

| Column | Meaning |
|---|---|
| `dataset` | which query, e.g. `google_jobs:query:core-backend-nyc` |
| `last_success_at` | when it last succeeded — drives "what's stalest" |
| `claimed_at` | who's working on it now; expires after 15 min if a machine dies |

Two consequences worth knowing:

- **A query that succeeded in the last 20 hours won't be handed out again**
  (`GOOGLE_JOBS_MIN_HOURS_BETWEEN_RUNS`). So the daily budget is shared across
  *all* your machines, not multiplied by them. A machine that finds nothing
  stale exits cleanly having spent nothing.
- **Failures are safe.** `last_success_at` only advances on success, so a
  failed or interrupted run loses nothing — the next run sees the true gap and
  automatically widens its "posted since" filter (`today` → `3days` → `week` →
  `month`) to cover it.

## Configuration

All configuration is environment variables. Nothing needs editing in code.

| Variable | Default | Notes |
|---|---|---|
| `DATABASE_URL` | passwordless localhost | **Required** in practice |
| `SERPAPI_API_KEY` | — | Required by `ingest/google-serpapi.py`; per-machine |
| `APIFY_API_TOKEN` | — | Required by `ingest/google-apify.py` |
| `JOB_SCORING_BASE_URL` | `https://api.z.ai/api/paas/v4` | Any OpenAI-compatible endpoint |
| `JOB_SCORING_MODEL` | `glm-4.5-flash` | Model id sent in the request |
| `JOB_SCORING_API_KEY` | falls back to `GLM_API_KEY` | Key for the endpoint above |
| `SCORE_BATCH_SIZE` | `30` | Jobs scored per run |
| `SCORE_MAX_WORKERS` | `5` | Concurrent scoring requests |
| `LLM_MAX_RPM` | unset (unlimited) | Client-side requests/minute; per-model |
| `LLM_MAX_RPD` | unset (unlimited) | Client-side requests/day; per-model |
| `LLM_QUOTA_STATE` | `~/.cache/hermes/llm-quota.json` | Where the daily count persists |
| `LLM_QUOTA_TZ` | `UTC` | When the daily budget rolls over |
| `JOBS_PROFILE` | `config/persona.json`'s `profile` | Which score set to read/write |
| `JOBS_RELEVANCE_FILE` | `config/relevance.json` | Tier rules; missing file = score everything |
| `BUILTIN_DETAIL_LIMIT` | `60` | Detail-page fetches per run (descriptions) |
| `BUILTIN_DETAIL_DELAY` | `2.0` | Seconds between detail-page fetches |
| `GOOGLE_JOBS_MIN_HOURS_BETWEEN_RUNS` | `20` | Don't re-run a query this recent |
| `CLAIM_TTL_MINUTES` | `15` | How long a crashed machine blocks a query |
| `DEBUG_PRINT_KEYS` | unset | `1` for verbose stderr logging |

### Hand-edited config files

- `config/companies.json` — 68 companies with verified ATS board tokens
- `config/google-queries.json` — the query bank, 4 weighted buckets
- `config/persona.json` — candidate background, scoring instructions, profile name
- `config/relevance.json` — which jobs are worth a scoring call (tier rules)

Adding a query to a bucket needs no migration; it simply has no watermark yet
and sorts first as "never run."

### Swapping the scoring model

`score.py` calls a plain OpenAI-compatible `/chat/completions` endpoint, so
switching backends is three env vars and no code change:

```bash
# Google Gemini free tier
export JOB_SCORING_BASE_URL="https://generativelanguage.googleapis.com/v1beta/openai"
export JOB_SCORING_MODEL="gemini-3.6-flash"
export JOB_SCORING_API_KEY="<gemini key>"

# Local Ollama
export JOB_SCORING_BASE_URL="http://localhost:11434/v1"
export JOB_SCORING_MODEL="llama3.1"
export JOB_SCORING_API_KEY="unused"
```

### Backfilling the whole backlog

`score.py` scores `SCORE_BATCH_SIZE` jobs and exits, which is right for a
nightly cron and useless for a one-time backlog. `backfill-scores.py` drives
it in a loop until the backlog is empty:

```bash
python3 jobs/backfill-scores.py --dry-run              # plan only
nohup python3 jobs/backfill-scores.py --workers 3 > backfill.log 2>&1 &
```

Resumable by construction — each round is an independent short transaction,
and "what is still unscored" *is* the progress, asked fresh from the database
every round. Interrupt it whenever; rerun to continue. Ctrl-C finishes the
round in flight and exits cleanly.

It pins the model for the whole run and re-checks it every round, because a
fit_score is only comparable to one produced the same way. `--rescore-stale`
deletes scores from other models so they get redone in the current one (off
by default; it deletes rows).

Measured throughput on `glm-4.5-flash`, which is slow and intermittently
drops calls even sequentially:

| workers | rate | 5,100 jobs |
|---|---|---|
| 1 | ~40/hr | ~5 days |
| 2 | ~94/hr | ~2.3 days |
| 3 | ~81-111/hr | ~2-2.5 days |

Deferred calls are not failures — nothing is written and the row is retried
next round. Only genuinely unparseable responses get tombstoned.

### Staying inside a free tier

Free tiers meter **per model, not per project** — the quota id Google returns
is literally `GenerateRequestsPerDayPerProjectPerModel-FreeTier`. Two separate
limits bite, and they fail differently: RPM is burst (429s, clears in ~60s),
RPD is a daily budget (429s for the rest of the day, retrying never helps).

`jobs/ratelimit.py` enforces both client-side, so the pipeline stops before
the provider does. Unset means unlimited, so this is a no-op for local and
paid endpoints. Budgets are per model, with an override that wins over the
bare name — non-alphanumerics become underscores:

```bash
export LLM_MAX_RPD__gemini_3_6_flash=20     # measured, not a guess
export LLM_MAX_RPM__gemini_3_6_flash=10
export LLM_QUOTA_TZ="America/Los_Angeles"   # Google resets midnight Pacific
```

Verify a model's real ceiling rather than trusting a blog post — exhaust it
once and read the violation:

```bash
curl -s .../chat/completions -d '...' | python3 -c \
  "import json,sys; d=json.load(sys.stdin); d=d[0] if isinstance(d,list) else d; \
   print(json.dumps(d['error'].get('details'), indent=2))"
```

Published free-tier numbers are frequently wrong. `gemini-3.6-flash` is
documented in several places as 1,500 requests/day; the quota violation on
this project reports **20**.

When the daily cap is hit, `llm.call()` raises `TransientError`, which
`score.py` **defers** — nothing is written and the row is retried next run.
That is deliberate: recording "we ran out of budget" as a verdict on a posting
would tombstone jobs nobody ever evaluated.

### What gets scored, and in what order

Scoring is expensive; ingest is not. `ingest/ats.py` pulls **entire company
job boards**, so most of the table is roles you'd never apply to — the run log
shows `tiers[t1=30]` for what a batch actually spent its calls on.

`config/relevance.json` assigns every job a tier, and `score.py` works through
them in order:

| tier | meaning | share of current backlog |
|---|---|---|
| 1 | title matches **and** location is acceptable | 26% |
| 2 | title matches, location unknown/elsewhere | 21% |
| 3 | everything else | 53% |

`max_tier_to_score` (default `2`) caps how deep the budget reaches. **Nothing is
ever deleted** — raise it to `3` and previously-skipped rows become eligible
with no re-ingest.

All the domain knowledge is in that one JSON file; `relevance.py` contains no
engineering terms at all. Retargeting the pipeline at a different field means
rewriting `relevance.json` and `persona.json`, not touching code.

```bash
python3 jobs/tools/relevance-report.py --dead   # tier counts, samples, dead patterns
```

**Run that after every edit.** A relevance filter fails silently in the
direction that hurts: a pattern matching nothing doesn't error, it just quietly
buries good postings in tier 3. Two things to know:

- These are **Postgres** regexes. Word boundary is `\y` — in Postgres `\b`
  means *backspace*. The first version of this config used `\b` throughout and
  silently demoted "ML / LLM Engineer" to tier 3.
- Read the **tier 3 samples**. Anything there you'd actually apply to is a
  false negative, and false negatives are invisible in production.

### When scoring fails

Two different outcomes, deliberately:

- **Unparseable** — the model answered but the answer was unusable. Gets a
  `job_scores` row with `scoring_model="FAILED:..."` and a NULL `fit_score`,
  so it isn't retried forever.
- **Deferred** — the endpoint never answered (HTTP 429, timeout, 5xx). Nothing
  is written and the job is retried next run.

That split matters: a rate limit says nothing about the posting. Recording one
as a failure would permanently discard a job that was never evaluated. If you
see a large `deferred` count, lower `SCORE_MAX_WORKERS` — the endpoint is
throttling you.

### Scores are per profile

Scores live in `jobs.job_scores`, keyed `(job_id, profile)` — not as columns on
`jobs.jobs`. A score isn't a property of a posting; it's one persona's opinion
of it, and `jobs` is shared across every persona.

The profile name comes from `config/persona.json`'s `profile` key (`tech`),
overridable per-run with `JOBS_PROFILE`. Two consequences:

- **Editing the persona without renaming the profile re-scores in place.**
  That's usually what you want when refining wording.
- **Renaming the profile starts a fresh, empty score set** and leaves the old
  one intact — so you can score the same postings against a second persona, or
  A/B two versions of your own, without either destroying the other.

`select_unscored_jobs` anti-joins on `(job_id, profile)`, so "unscored" always
means "unscored *for this profile*."

**Test a model before making it the default.** `tools/compare-models.py` scores
real postings with each candidate and reports JSON reliability, latency, score
spread, and agreement with your current model. It's read-only — it never writes
to `jobs.jobs`, so run it as often as you like:

```bash
python3 jobs/tools/compare-models.py \
    --model "glm-4.5-flash@https://api.z.ai/api/paas/v4@$GLM_API_KEY" \
    --model "gemini-3.6-flash@https://generativelanguage.googleapis.com/v1beta/openai@$GEMINI_API_KEY" \
    --n 15
```

`json_ok` is the hard gate: a model that can't reliably return parseable JSON
is unusable here regardless of how good its judgment is. Watch latency too —
multiply by `SCORE_BATCH_SIZE / SCORE_MAX_WORKERS` for real nightly runtime.

## Troubleshooting

**`could not connect to Postgres`** — `DATABASE_URL` is unset or wrong. The
default is deliberately passwordless and won't work against a real server.
Error messages print only the host/database, never the password.

**`SERPAPI_API_KEY not set`** — expected on machines that don't run Google
Jobs queries. Other steps still run; `run-daily.py` exits non-zero but the
rest of the pipeline completed.

**A run claimed nothing** — normal. Every query already ran within the last 20
hours. Nothing to do.

**Scoring returns unparseable JSON** — the parser tolerates markdown fences and
extra prose, but smaller models still fail sometimes. Check `scoring_model` for
`FAILED:` values:

```sql
SELECT scoring_model, count(*) FROM jobs.job_scores
GROUP BY 1 ORDER BY 2 DESC;
```

## Querying results

```sql
-- Best-fit open jobs
SELECT s.fit_score, j.title, j.company_name, j.location_raw, j.job_url
FROM jobs.jobs j
JOIN jobs.job_scores s ON s.job_id = j.id AND s.profile = 'tech'
WHERE j.status = 'open' AND s.fit_score IS NOT NULL
ORDER BY s.fit_score DESC LIMIT 20;

-- What came in today, by source
SELECT platform, count(*) FROM jobs.jobs
WHERE first_seen >= to_char(now() - interval '1 day', 'YYYY-MM-DD"T"HH24:MI:SS')
GROUP BY 1 ORDER BY 2 DESC;

-- How two profiles rate the same posting
SELECT j.title, a.fit_score AS tech, b.fit_score AS other
FROM jobs.jobs j
JOIN jobs.job_scores a ON a.job_id = j.id AND a.profile = 'tech'
JOIN jobs.job_scores b ON b.job_id = j.id AND b.profile = 'other'
ORDER BY abs(a.fit_score - b.fit_score) DESC LIMIT 20;
```

Heuristic columns (`seniority_guess`, `location_is_nyc`, `location_is_remote`)
are tags, not filters — rows are never dropped at ingest, so query them
yourself rather than assuming filtering already happened.

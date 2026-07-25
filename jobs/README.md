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
> alongside the shared `pipelib/` library it imports and the separate
> `events/` pipeline. Run its scripts from the repository root, as the
> commands below do -- `pipelib` is located by walking up from each
> script, so running them from elsewhere still works, but the paths shown
> assume the root.

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

`run-daily.py` runs all seven steps in order, in one process. It's wired to
`hermes cron`, which loads `~/.hermes/.env` for you:

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
| `JOBS_PROFILE` | `config/persona.json`'s `profile` | Which score set to read/write |
| `GOOGLE_JOBS_MIN_HOURS_BETWEEN_RUNS` | `20` | Don't re-run a query this recent |
| `CLAIM_TTL_MINUTES` | `15` | How long a crashed machine blocks a query |
| `DEBUG_PRINT_KEYS` | unset | `1` for verbose stderr logging |

### Hand-edited config files

- `config/companies.json` — 68 companies with verified ATS board tokens
- `config/google-queries.json` — the query bank, 4 weighted buckets
- `config/persona.json` — candidate background and scoring instructions

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

A job whose scoring fails still gets a `job_scores` row (with
`scoring_model="FAILED:..."` and a NULL `fit_score`) so it isn't retried
forever.

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

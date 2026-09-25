# Pursuit jobs: Google Jobs contributor (Apify actor)

This actor fetches Google Jobs postings for the Pursuit cohort's job list. Each classmate runs it on a
schedule in **their own** Apify account. Each run does three things:

1. **Claims** the searches that are due from the jobs server (`POST /v1/queries/claim`).
2. **Scrapes** each one with the Apify Store's Google Jobs actor, inside your account.
3. **Submits** the raw results back (`POST /v1/queries/{dataset}/submit`). The server normalises and
   stores them.

For why it works this way, see [`docs/adr/0012`](../docs/adr/0012-contributor-scrape-runs-as-apify-actor.md).

## For classmates: setup (5 minutes)

1. **Get your token.** Sign in to the jobs site with your **@pursuit.org** Google account, open
   **Contribute**, and tap **Get actor token** twice. The token is shown only once, so copy it. If you
   get a new token later, the old one stops working.
2. **Open the actor.** In [Apify Console](https://console.apify.com), open the actor shared with you,
   **Pursuit jobs: Google Jobs contributor**. A free Apify account is enough.
3. **Paste the token** into **Jobs API token**. Leave the other inputs at their defaults.
4. **Test it.** Click **Save & Start** once. A good run ends with a message like
   `1/1 queries submitted, 9 postings accepted by the server`.
5. **Schedule it.** Go to **Schedules**, create a schedule, set it to daily, and add this actor with
   the saved input.

### What it costs you

The scrape runs the Store actor `johnvc/google-jobs-scraper---pay-per-result` in your account, at
about **$0.015 per result**. The defaults are 1 search per run and 10 results per search, so a run
costs about **$0.15** and a daily schedule costs about $4.50 a month. That fits inside the Apify
free plan's monthly credit.

The actor also passes `maxItems`, so Apify never charges for more results than you asked for.

### What a "green but did nothing" run means

These runs all succeed without scraping or spending anything:

| Run message | Meaning |
|---|---|
| `Paused by the server operator` | The operator paused contributors. Keep the schedule; it resumes on its own. |
| `Daily limit reached on the server` | Your per-day cap on the server was used up. |
| `Nothing to do: every query was fetched recently` | Every search was run within the last day. |

A **red** run means something is actually wrong:
- The token was rejected. Get a new one.
- The server couldn't be reached.
- Every search failed.

## Inputs

| Input | Default | Notes |
|---|---|---|
| `apiKey` | none, required | Secret. Your token from the Contribute screen. |
| `serverUrl` | `https://jobs-api.etotheric.com` | The jobs API (`backend/api/`). |
| `maxQueries` | 1 | 1–5 searches per run. |
| `resultsPerQuery` | 10 | 1–50. The server accepts at most 50 per search. |

## For the operator: developing and deploying

```bash
cd actor
npm install
npm run lint     # tsc --noEmit
npm test         # builds, then node --test over dist/**/*.test.js
npm run build
```

`src/run.ts` holds the claim → scrape → submit loop. It has no Apify or network imports, so the tests
drive it with fakes. `src/scrape.ts` is the only part that talks to Apify. To replace the delegated
scraper, write a new `Scraper` there.

**Deploy** with `npx apify-cli login`, then `npx apify-cli push` from this directory. Then share the
actor with each classmate with *run* permission (Actor → Share). It never needs to be public. The
remaining owner-side steps are tracked in `DEV_TASKS.md` `OQ-40`.

**Against a local server:** start `backend/api` on `:8420` and mint a key with
`backend/api/manage_users.py create`. Then run
`npx apify-cli run --input '{"apiKey":"…","serverUrl":"http://localhost:8420"}'`. That run still
calls the real Google Jobs actor, and bills the Apify account you're logged in as.

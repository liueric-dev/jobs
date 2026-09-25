# Google Jobs contributor actor

This optional Apify actor claims due Google Jobs queries from the contributor
API, scrapes them in the runner's Apify account, and submits results back.

## Contributor setup

Sign in to the jobs site, open Contribute, and generate an actor token. Copy it
when shown; it cannot be displayed again. In Apify Console, open the actor
shared by the operator, paste the token into `apiKey`, and run it once before
adding a daily schedule. The delegated scrape uses the runner's Apify account
and may incur charges. A green run with no queries means there was nothing due
or the server paused contributors.

Inputs are `apiKey` (required), `serverUrl` (the contributor API),
`maxQueries` (default 1), and `resultsPerQuery` (default 10).

## Develop

```bash
cd actor
npm ci
npm run lint
npm test
npm run build
```

`src/run.ts` owns the claim, scrape, submit loop; `src/scrape.ts` calls Apify.
Deploying or sharing the actor requires an Apify account and is separate from
building this repository.

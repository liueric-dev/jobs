# Google Jobs contributor actor

This actor is dormant pending redesign. Its current claim/submit flow requires
the contributor API removed during cleanup. Do not deploy or schedule it.

The old inputs are `apiKey`, `serverUrl`, `maxQueries`, and `resultsPerQuery`.
They describe the retired contributor protocol, not a supported setup.

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

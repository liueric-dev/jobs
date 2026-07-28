# 23 — SERP abstraction

**Status:** todo. **Depends on:** 22, 09. **Blocks:** 24, 25.

One interface over every Google Jobs provider, with a quota-aware router behind it.

## Why an abstraction rather than one integration

Google for Jobs aggregates Indeed, LinkedIn, Glassdoor, ZipRecruiter and company ATS
pages, so it is the only no-API target worth integrating. But no single provider gives
enough free capacity to depend on, and each has different auth, response shape, credit
unit and failure mode.

Eight providers wired directly into an ingest script is unmaintainable. Eight adapters
behind one call is fine.

**You already have the pattern.** `llm.py`'s `call_detailed()` takes per-call model,
base URL and key overrides and returns a `Completion` carrying usage. This is that,
for SERP.

## Shape

```
backend/serp/
  __init__.py       # call(query, location, *, provider=None) -> SerpResult
  providers/
    jobspy.py       # local, no creds        (default if task 22 passed)
    contributor.py  # dispatch into backend/api/'s queue
    scrappa.py      # 500/mo
    serpapi.py      # 250/mo, engine=google_jobs
    jsearch.py      # ~200/mo
    apify.py        # $5/mo credits, actor-denominated
    scrapingbee.py  # 1,000 one-time
    scrapingdog.py  # 200 credits, 5/request
  normalize.py      # raw -> the frozen record shape
  router.py         # quota-aware selection
  quota.py          # per-provider ledger
```

Adapters expose one function: `fetch(query, location, creds) -> raw`. Nothing else.
Normalisation, routing, accounting and caching live outside them, so adding a
provider is one small file.

## Three properties to design in

Each mirrors a decision already made elsewhere in this repo. Restate them rather than
rediscover them.

**`SerpResult` carries provenance and cost.** Provider, credits consumed, and whether
it came from cache — the same way `Completion` carries usage. And apply the evals
harness's rule: `report.py` already refuses to print cost or latency for a run
containing a replayed result, *enforced where the number would be printed rather than
by asking each caller to remember*. Do the same here.

**Normalisation is an adapter, never a copy.** The Google Jobs record shape is already
frozen in `lib/` — commit `0c3ae51`, "De-vendor the API: one copy of the Google Jobs
record shape". Every provider normalises *into* that shape. A second definition
appearing here would undo work that was deliberately done once.

**The API key is not part of the cache key.** The evals harness already enforces this:
rotating a credential must not discard a corpus of paid-for answers, and a key must
never reach disk. It matters more here — eight providers with rotating free-tier keys.

## Router policy

Fall through on exhaustion or error:

1. **Cache** — `(normalized_query, location, date)`, 24h TTL
2. **JobSpy** — free and unlimited, *if passing its health check*
3. **Contributor API** — largest renewable pool, and the community feature
4. **Scrappa → SerpApi → JSearch** — renewable, cheapest first
5. **Apify** — job-denominated; good for a deep pull on one query
6. **One-time trials** — only on explicit backfill, never automatically

Task 22's outcome sets whether step 2 exists at all.

### Two operational rules that matter more than the ordering

**Alert on volume, not errors.** Every failure mode here is *silence*: an exhausted
key returns zero rows, a revoked key returns zero rows, a blocked scraper returns zero
rows. None raise. This is the same class as task 03's discarded upsert errors and task
18's Workday traps — and it is why task 03 lands first, so this code is not built on a
pipeline that already swallows failures.

Concretely: record expected result counts per query, and alert when a provider's
nightly yield drops below a floor. Not when it throws.

**Health-check JobSpy separately from using it.** Self-hosted scrapers degrade
gradually. Run a canary query on a known-good term nightly, and have the router demote
JobSpy automatically when its result count falls. Do not wait for a human to notice a
thinner list.

## Quota ledger

`quota.py` tracks, per provider: allowance, unit (searches / credits / jobs / dollars),
renewal date or one-time flag, consumed this period, and credit multipliers where they
apply.

Multipliers are not a detail. ScraperAPI bills 25 credits for premium domains
including Google, so a 5,000-credit tier may be ~200 real requests. Scrapingdog bills
5 credits per Google Jobs request, so 200 credits is 40 requests. A ledger counting
raw requests would be wrong by an order of magnitude for both.

Seed it from `ADDENDUM-google-jobs-providers.md` §2, and **verify each number against
the provider on first integration** — several in that table are reported secondhand
and flagged as such.

## Definition of done

- `serp.call()` works against at least three providers with identical output shape.
- All output normalises into `lib/`'s existing Google Jobs record shape; no second
  definition exists.
- Router falls through on exhaustion and records which provider served each result.
- Quota ledger reflects real allowances, verified per provider, with multipliers.
- Cache implemented; cache hits are visible in `SerpResult` and excluded from cost
  and latency reporting.
- Volume-based alerting in place; a provider silently returning zero is detected
  within one night.
- JobSpy canary running, with automatic demotion.
- Cassettes per provider (task 09), proving the adapters agree on one input.

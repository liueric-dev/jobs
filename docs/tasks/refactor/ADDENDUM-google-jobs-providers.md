# ADDENDUM — Google Jobs providers and the SERP abstraction

**Written** 2026-07-28. Extends `SOURCING-STRATEGY.md` §3.
Slots into `MASTER-PLAN-pursuit.md` Phase 2 as tasks 13a/13b.

---

## 1. Why this is one integration, not four

Google for Jobs aggregates Indeed, LinkedIn, Glassdoor, ZipRecruiter and company
ATS pages into a single result set, and the response carries the source domain and
per-network apply links. One Google Jobs query therefore covers every no-API target
you care about.

Google has never offered a public jobs API — Cloud Talent Solution is a separate
enterprise product for embedding search into your own site, not a way to read
`google.com/jobs`. Every provider below is scraping the public SERP.

---

## 2. Providers with a free tier and a Google Jobs vertical

"Vertical" means a dedicated jobs endpoint returning parsed job objects, not a
generic SERP you'd have to parse yourself.

| provider | free tier | renews | vertical | endpoint / notes |
|---|---|---|---|---|
| **SerpApi** | 250 searches | **monthly** | yes ✓ | `serpapi.com/search?engine=google_jobs`. Documented, playground, cached searches don't count against quota |
| **Scrappa** | 500 credits | **monthly** | yes (reported) | Advertises a Google Jobs engine |
| **JSearch** (RapidAPI) | ~200 requests | **monthly** | yes | Wraps Google for Jobs; returns Indeed/ZipRecruiter/Glassdoor/LinkedIn rows |
| **Apify** | $5 platform credits | **monthly** | yes, many actors | $0.008–$0.015/job typical; one at $15/1k. Actor fees stack on compute units |
| **ScrapingBee** | 1,000 credits | one-time | yes ✓ | Dedicated Google Jobs Scraper API |
| **ScraperAPI** | 5,000 credits | one-time | yes ✓ | Structured-data endpoint. **Caveat: generic pricing bills 25 credits for "premium domains" incl. Google — 5,000 credits may be ~200 real requests.** Verify before relying on it |
| **Scrapingdog** | 200 credits | one-time | yes ✓ | `api.scrapingdog.com/google_jobs`. **5 credits per request** → 200 credits = 40 requests. Paid: $10 = 25,000 credits = 5,000 requests |
| **Bright Data** | 1,000 requests | one-time | yes ✓ | Pay-per-success; unlimited rate. Requires KYC |
| **Decodo** (ex-Smartproxy) | "free plan" | unverified | yes ✓ | Google Jobs Scraper API; check the actual allowance |
| **SearchApi.io** | 100 requests | one-time | reported | Verify the `google_jobs` engine exists before integrating |
| **Serper** | 2,500 credits | one-time | **unverified** | Generic Google SERP; jobs vertical not confirmed |
| **DataForSEO** | $1 trial | — | unverified | $50 minimum deposit rules it out anyway |
| **JobSpy** | unlimited | — | yes | **Self-hosted, free, no quota.** Scrapes Google Jobs, Indeed, LinkedIn, Glassdoor, ZipRecruiter |
| **Contributor API** (`backend/api/`) | 30 × 250 | **monthly** | yes | Already built. Builders' own SerpApi keys |

Verified against primary sources: SerpApi, ScrapingBee, ScraperAPI, Scrapingdog,
Bright Data, Decodo. Others reported secondhand — confirm before integrating.

---

## 3. Effective capacity

**Renewing monthly:**

| source | searches/mo |
|---|---|
| Contributor API (30 Builders × 250) | 7,500 |
| Scrappa | 500 |
| SerpApi (yours) | 250 |
| JSearch | 200 |
| Apify ($5 ÷ ~$0.01/job ÷ 10 jobs) | ~50 equivalent |
| **total** | **~8,500/mo ≈ 280/day** |

**One-time trials, held in reserve:** ScrapingBee 1,000, Bright Data 1,000,
ScraperAPI ~200 effective, Scrapingdog 40, SearchApi 100 → **~2,300 requests** of
burst capacity for backfills or a bad month.

**Demand:** 30 Builders × 3 saved searches × daily = 90/day. Against 280/day
renewable, that's 3× headroom before caching.

**With query caching it's more like 10×.** Cache on `(normalized_query, location,
date)` — thirty Builders in one cohort searching one city will collide constantly,
and SerpApi explicitly doesn't bill cached searches. This is the pooling feature
paying for itself: not pooled credits, pooled *results*.

**Test JobSpy first.** If it holds up on your residential IP, the whole table above
becomes backup rather than backbone.

---

## 4. The abstraction layer

Eight providers with different auth, response shapes, credit units and failure modes
is unmanageable without one interface. You already have the pattern — `llm.py`'s
`call_detailed()` with per-call model, base URL and key overrides returning a
`Completion` that carries usage. Build the SERP equivalent.

```
serp/
  __init__.py       # call(query, location, *, provider=None) -> SerpResult
  providers/
    serpapi.py      # each exposes fetch(query, location, creds) -> raw
    scrappa.py
    scrapingbee.py
    scrapingdog.py
    jsearch.py
    apify.py
    jobspy.py       # local, no creds
    contributor.py  # dispatch to the queue in backend/api/
  normalize.py      # raw -> the Google Jobs record shape lib/ already freezes
  router.py         # quota-aware selection
  quota.py          # per-provider ledger
```

Three properties worth designing in deliberately, all mirroring decisions already
made elsewhere in the repo:

- **`SerpResult` carries provider, credits consumed, and whether it was served from
  cache** — the same way `Completion` carries usage. `report.py` already refuses to
  print cost or latency for replayed results; apply the identical rule here.
- **Normalization is an adapter, never a copy.** The Google Jobs record shape is
  already frozen in `lib/` (commit `0c3ae51`, "one copy of the Google Jobs record
  shape"). Every provider normalizes *into* that shape. Do not let a second
  definition appear.
- **The API key is not part of the cache key.** Same rule the evals harness already
  enforces — rotating a credential must not discard a corpus of paid-for answers.

---

## 5. Router policy

Spend in this order, falling through on quota exhaustion or error:

1. **Cache** — `(normalized_query, location, date)`, TTL 24h
2. **JobSpy** — free and unlimited, if it's passing its health check
3. **Contributor API** — the largest renewable pool, and the community feature
4. **Scrappa → SerpApi → JSearch** — renewable, cheapest first
5. **Apify** — job-denominated, good for deep pulls on one query
6. **One-time trials** — only on explicit backfill, never automatically

Two operational rules that matter more than the ordering:

**Alert on volume, not errors.** A revoked or exhausted key returns zero rows, not
an exception. The failure mode across every provider here is silence. This is the
same class of bug as the `UpsertResult.errors` defect the ingest audit found in four
scripts — worth fixing that first so the new code isn't built on it.

**Health-check JobSpy separately from using it.** A self-hosted scraper degrades
gradually as sites change. Run a canary query on a known-good term nightly and
demote it in the router automatically when the result count drops.

---

## 6. Where this lands

Everything on this path routes through the existing pipeline — `jobs` →
`relevance.py` → `extract.py` → `match.py`. No shortcuts to display. Google Jobs is
precisely where the relister junk originates; `config/relevance.json` already
carries six excluded relist sites and the `'reputed company'` placeholder filter
because of it.

Queries become first-class objects so they can be deduped, cached, and shown
socially:

```sql
search_queries (
    id, normalized_text, location, chips,
    first_requested_at, last_run_at, run_count,
    requested_by TEXT[],        -- for "3 Builders are watching this"
    provider_last_used, result_count_last_run
)
```

Seed the query list from the `role_track` clusters. Builders who don't yet know what
role they want cannot write a good search term — that's the same problem `role_track`
exists to solve, and search should be the refinement tool rather than the entry
point.

---

## 7. Task mapping

Replaces task 13 in the master plan:

- `13a-serp-abstraction.md` — the `serp/` package, provider adapters, normalization
  into the frozen record shape, quota ledger, router, cache
- `13b-jobspy-evaluation.md` — spike: does JobSpy work from the home IP, what's the
  result quality vs SerpApi on identical queries, what's the block rate over two
  weeks. **Run this before 13a** — the answer changes the router's default
- `13c-revive-contributor-api.md` — deploy `backend/api/` behind the tunnel,
  onboarding flow for Builders to contribute a key
- `13d-search-queries.md` — the query object, dedup, caching, social signal, seeded
  suggestions from `role_track`

13b is a spike, not a build. Timebox it.

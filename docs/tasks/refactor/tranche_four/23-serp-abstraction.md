---
kind: task
written: 2026-07-28
generator: none
---

# 23 — SERP abstraction

**Status:** ~~todo.~~ **DONE 2026-08-02, sharply descoped, with two Definition-of-done
lines reported UNMET rather than tuned into being met — see § *Outcome* at the bottom.**
**Depends on:** 22, 09. **Blocks:** 24, 25 — **and it was blocking 25 in exactly one place,
which is now closed**: `searchqueries.run_due(conn, provider=None)` had taken a callable
since task 25 landed and every caller passed None.

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

---

## Outcome — 2026-08-02

**Built: `backend/serp/`** — `__init__.py` (the interface, `SerpResult`, the failure
classes), `providers/serpapi.py`, `providers/apify.py`, `normalize.py`, `dispatch.py`,
`datechip.py`, `cache.py`, `quota.py`, plus `config/serp-quota.json` and a
`searchqueries` entry in `config/volume-floors.json`, and `backend/tests/test_serp.py`,
which replays committed cassettes and never reaches the network. The suite's size is
[`AUDIT.md`](../AUDIT.md)'s figure under policy rule 2 — read the `Ran N tests` line, and
no count is typed here. **No live search was spent building any of it.** The two account endpoints were read, because they are free and are
the instrument the ledger needed.

### The shape the file sketched, against what landed

| sketched | landed |
|---|---|
| eight adapters | **two** — the descope (`DEC`, *"Build task 23, sharply descoped"*). Six are cut by not appearing in `serp.PROVIDERS`, which is data, not an if-chain |
| `jobspy.py`, `router.py` step 2, the canary | **not built.** Task 22 dropped JobSpy |
| `contributor.py` as one adapter among eight | **not built**, and `DEC` already says why it is misfiled: at 30 Builders × 250 searches it is ~8x every free tier combined. It is task 24, not an adapter |
| `fetch(query, location, creds) -> raw` | as written, plus `date_chip` — the one parameter the router genuinely has to pass down |
| `normalize.py` | as written, and it defines nothing: it calls `google_jobs.normalize_job` and a test asserts no adapter has a symbol with "normalize" in its name |
| `quota.py` seeded from ADDENDUM §2 | seeded, **and demoted**: the config's own `_comment` says those numbers are a description and the vendor is the authority. See below |

### Two Definition-of-done lines are UNMET, deliberately

- **"`serp.call()` works against at least three providers."** It works against **two**.
  Three was the pre-descope number; the descope cut six of eight and the arithmetic was
  never restated here. Reported rather than met, the way 13's DoD lines are.
- **"Quota ledger reflects real allowances, verified per provider."** The allowances in
  `config/serp-quota.json` are **not verified** and each says so on its own row. What is
  verified is better and is what the DoD was reaching for: the ledger asks the provider.

Two more are met in a different shape than written. **"Volume-based alerting"** is a row in
`config/volume-floors.json` rather than new machinery, because that check already exists,
already runs on its own timer and already treats no-history as a finding. **"Cassettes per
provider, proving the adapters agree on one input"** — the two recordings hold no posting
in common, so what is asserted is stronger and cheaper: both produce exactly
`schema.COLUMNS`, from one normalizer, and a per-provider normalizer breaks the test.

### What the work found

**The ledger defect was never given a number, so nothing scanned it.** `DEC` records it as
*"not reversible; it is a defect"* and no `D` entry existed. It is now **D76**, and
re-measuring it on the way in put `google_jobs_query_stats` at 18 rows this month against
SerpApi's own 193 used of 250 — which is **not** a ratio and D76 explains why not.

**`choose_date_chip` had to move before anything could use it.** It lived in
`ingest/google-serpapi.py`, a file whose name has a hyphen in it and which therefore cannot
be imported. So run_due() had no date policy available at any price, and would have
re-asked Google the same unfiltered question every night. It is now `serp/datechip.py`,
re-exported under its old name; `api/query_claims.py`'s copy stays, because `backend/api/`
may import only `schema.py` and `lib/`.

**`due_queries()` selected `last_run_at` and dropped it on the floor.** One key, and
without it the chip above has nothing to compute from.

**Two falsy-or bugs, both found by tests that would otherwise have passed for the wrong
reason.** `now or time.time()` in the cache made an epoch of 0 read as the wall clock, so
the TTL test aged nothing; `env or os.environ` in `credentials_for` made an empty
environment fall back to the real one, so a "no key configured" test would have passed or
failed depending on whose `.env` was on disk.

**Apify differs from SerpApi in two ways that are now declared as data rather than
absorbed.** `SUPPORTS_DATE_CHIP = False` — the actor has no equivalent of Google's
`chips=date_posted:`, so the whole DATE FILTER design does not apply to it. `RECONCILABLE
= False` — it bills dollars where this pipeline counts results, so its ledger line reads
`NOT RECONCILED` with the reason attached instead of a zero delta.

### Deliberately NOT done, and the reason

**`ingest/google-serpapi.py` and `ingest/google-apify.py` still talk to their providers
directly.** Routing them through `serp/` is what finally removes the duplication, and it is
a live nightly path carrying claim and watermark semantics — `try_claim_query`,
`CLAIM_TTL_MINUTES`, the multi-machine safety its own docstring is explicit about — that
this interface does not model yet. Doing it in the same pass as building the interface
would have made the first failure ambiguous between the two. **This is the follow-up**, and
it is the one that closes *"no second definition exists"* for the fetch path as well as for
the record shape.

**Nothing alerts on a large reconciliation delta.** The number is printed every run;
choosing the threshold that turns it into an alert is a policy call nobody has made, and
inventing one here is `D71`'s mistake.

---
kind: record
written: 2026-07-28
generator: none
---

# SOURCING STRATEGY — service-to-target assignment

**Written** 2026-07-28. Companion to `MASTER-PLAN-pursuit.md` §5.
Drives the Phase 2 task files.

---

## 0. The principle that decides most of this

**Most of your targets need no scraping service at all.** Every major ATS exposes
public JSON with no auth, and the two highest-value NYC sources are government
APIs. A paid or free-tier scraping service earns its place only on JavaScript-heavy
or anti-bot-protected targets — which, for job postings, is a much smaller set than
it looks.

The corollary that matters for planning: **your scarce resource is not scraping
credits, it is wall-clock time and politeness delay on a nightly batch.** Spend the
free tiers on the handful of targets that genuinely need them, and use plain
`requests` everywhere else.

---

## 1. Service capability table

Verified where noted; otherwise reported from secondary comparisons. Credit
multipliers are the thing that silently destroys free tiers — a "1,000 credit"
plan can be 40 real requests against a protected site.

| service | free tier | renews | card | multipliers | notes |
|---|---|---|---|---|---|
| **Apify** | $5 platform credits | monthly, permanent | no | Actor fees stack **on top** of compute units — a pay-per-result Actor at $1.50/1k bills separately | 25k+ prebuilt Actors. **Creator Plan: $500 over 6 months for publishing an Actor.** Credits do not roll over |
| **Firecrawl** | 1,000 credits | monthly | no | — | Markdown-first, good for LLM ingestion. ~60% success on protected targets, fastest (3.9s). **Hard-blocks LinkedIn, Instagram, Reddit at the gateway on every tier** |
| **Scrapfly** | 1,000 credits | one-time trial | no | ASP/residential cost more | Best benchmarked success on protected sites (98–99%) |
| **Scrape.do** | 1,000 credits | one-time | no | — | Bills only successful requests. Good default for unknown difficulty |
| **ScrapingBee** | 1,000 calls | one-time | no | JS render + premium proxy multiply | Owned by Oxylabs since mid-2025 |
| **ScraperAPI** | ~5,000 credit trial | then small monthly | no | **1 basic / 5–10 JS / 25 "premium domains"** (incl. Google) | The 25× multiplier makes it a poor fit for SERP work |
| **ZenRows** | 1,000 credits | monthly | — | **25 credits/request** once JS + premium proxy engage on Cloudflare sites | Benchmarks poorly (54–58% protected). Avoid |
| **Crawlbase** | ~1,000 requests | one-time | no | token types differ | Minimal setup |
| **Zyte** | free credits, new users | one-time | — | — | Leads protected-site benchmarks (~93%). Natural if you use Scrapy |
| **Bright Data** | 1,000-request trial | one-time | yes/KYC | — | Highest measured success (98.44%). Gated behind KYC; overkill |
| **JobsPipe** | 100 credits | monthly, "free forever" | — | 1 credit per request regardless of page size | **The only free route to normalized iCIMS/Workday.** 100/month is tiny — use for spot-checks, not bulk |
| **SerpApi** | 250 searches | monthly | no | cached searches free | Only provider with a documented `google_jobs` engine |
| **Serper** | 2,500 credits | one-time | no | >10 results = 2 credits | Generic Google SERP |
| **Scrappa** | 500 credits | monthly | no | — | Advertises a Google Jobs engine |
| **Adzuna** | ~1,000 calls | monthly | no | — | Not a scraper — a real job API. Descriptions + salary |
| **USAJobs** | unlimited | — | no | — | Free federal API, email + auth key headers |
| **NYC Open Data** | unlimited | — | no | — | SODA API; free app token lifts throttling |

**Worth an email regardless:** Apify and Scrapfly both list student/nonprofit
discounts. You are a student building for a nonprofit's students — that is the
strongest version of that request.

---

## 2. Target difficulty

| target | protection | needs a service? |
|---|---|---|
| **Greenhouse** `boards-api.greenhouse.io/v1/boards/{token}/jobs?content=true` | none | **no** |
| **Lever** `api.lever.co/v0/postings/{slug}?mode=json` | none | **no** |
| **Ashby** (public GraphQL, `includeCompensation=true`) | none | **no** |
| **Workable / Recruitee / SmartRecruiters / Personio** | none | **no** |
| **Workday** `POST /wday/cxs/{tenant}/{site}/jobs` | Akamai on some tenants; throttles fast paging | **no** at low rate — see §4 |
| **NYC Open Data** (SODA) | none | **no** |
| **USAJobs / Adzuna** | none | **no** |
| **Career pages with JSON-LD** | none to light | mostly **no** |
| **iCIMS portals** | moderate + JS | sometimes |
| **Taleo / Oracle Cloud** | moderate + JS | usually |
| **Idealist** | light | rarely |
| **StateJobsNY, NYC DOE, CUNY** | light | rarely |
| **Indeed** | Cloudflare, aggressive | **yes** |
| **Glassdoor** | anti-bot | **yes** |
| **ZipRecruiter** | anti-bot | **yes** |
| **Google for Jobs SERP** | anti-bot + active litigation | **yes** |
| **LinkedIn Jobs** | hostile + litigation | **do not** |

---

## 3. The assignment table

| target | use | why | fallback |
|---|---|---|---|
| Greenhouse, Lever, Ashby, Workable, Recruitee, SmartRecruiters | **plain `requests`** (extend `ingest/ats.py`) | Public JSON, full descriptions, no auth. Closure detection is free — a job missing from the list response is closed | Apify ATS actors if you want zero maintenance |
| **Workday tenants** | **plain `requests`**, politely | The single highest-value unlock. POST for list, GET per job for description | Scrapfly's 1,000 credits for tenants that block; JobsPipe's 100/mo for spot verification |
| NYC Open Data `kpav-sd4t` | **plain `requests`** + free app token | Full descriptions, salary, **explicit `post_until`** | none needed |
| USAJobs, Adzuna, The Muse | **plain `requests`** + free keys | Documented APIs | none needed |
| Employer career pages w/ JSON-LD | **plain `requests` + `extruct`**; **Firecrawl** for JS-rendered ones | `validThrough` gives closure for free | Scrape.do's 1,000 |
| iCIMS portals | **Firecrawl** (1,000/mo) | JSON-LD is usually present on detail pages | JobsPipe for normalized iCIMS |
| Taleo / Oracle Cloud | **Scrapfly** (1,000, highest success) | Heavier JS | skip — low yield per effort |
| Idealist, nonprofit boards | **plain `requests`**; Firecrawl if JS | Mission-aligned; per-listing expiration | — |
| StateJobsNY, NYC DOE, CUNY | **plain `requests`** | Light protection, high relevance | Firecrawl |
| **Indeed** | **Apify actor** only | Cloudflare. Do not hand-roll | skip |
| **Glassdoor** | **Apify actor** only | anti-bot | skip |
| **Google for Jobs** | **contributor API** (`backend/api/`, already built) + your 250 SerpApi | Distributed across Builders' own keys | Scrappa 500/mo |
| **ATS token discovery** | **Apify** discovery actors, one-time | See §5 | DIY regex crawl |
| **LinkedIn** | — | **Excluded.** Reddit sued SerpApi and Oxylabs Oct 2025; Google sued SerpApi Dec 2025; Firecrawl refuses it | — |

---

## 4. Workday — the important one, and its traps

This is the gateway to Mount Sinai, NewYork-Presbyterian, Northwell, NYC Health +
Hospitals, the insurers, the universities. It is free HTTP, and it is where your
"all industries" promise actually lives.

```python
POST https://{tenant}.wd{N}.myworkdayjobs.com/wday/cxs/{tenant}/{site}/jobs
{"appliedFacets": {}, "limit": 20, "offset": 0, "searchText": ""}
```

Four traps, all of which cause **silent** data loss:

1. **`limit` cannot exceed 20.** Ask for 100 and Workday returns an empty
   `jobPostings` array with no error — indistinguishable from "no more results."
2. **It throttles fast paging.** A failed page mid-loop looks like the end of the
   list. One writeup lost 1,960 of NVIDIA's 2,000 jobs to exactly this. Pause
   between pages; retry a failed page rather than breaking.
3. **Data centre varies** — `wd1`, `wd3`, `wd5`. Read it off the company's actual
   careers URL; never assume.
4. **Descriptions need a second request** per job:
   `GET /wday/cxs/{tenant}/{site}/job/{externalPath}`.

Trap 4 is the architectural one. If a hospital has 2,000 open roles and you fetch a
detail page for each, that is 2,000 requests per tenant per night — the detail
fetches dominate everything else in the pipeline.

**So the relevance gate has to move upstream into the ingest layer for
detail-fetch sources.** Your current pipeline gates *after* ingest
(`relevance.py` runs against rows already in `jobs`). For Workday, filter on the
list response — which carries title and location — and only fetch detail for
postings that survive. That turns 2,000 requests into perhaps 150.

This is a real change to the ingest contract and should be its own task.

One tension worth noting: vendors selling Workday access claim Akamai blocks naive
scraping within minutes, while independent writeups report plain `requests` working
fine. Both are probably true at different rates. **Your home server's residential
IP is an advantage here** — it is the traffic profile Akamai is least suspicious
of. Start with plain requests, 1–2s delays, ~50 tenants, and measure. Escalate to
Scrapfly only for tenants that actually block.

---

## 5. Token discovery — the genuinely unsolved part

There is no public directory of ATS board tokens. This is the real work; the
endpoints are trivial once you have the list.

**Signatures to match on any careers page:**

| ATS | URL pattern |
|---|---|
| Greenhouse | `boards.greenhouse.io/{token}` · `job-boards.greenhouse.io/{token}` |
| Lever | `jobs.lever.co/{slug}` |
| Ashby | `jobs.ashbyhq.com/{slug}` |
| Workable | `apply.workable.com/{slug}` |
| Recruitee | `{slug}.recruitee.com` |
| SmartRecruiters | `careers.smartrecruiters.com/{slug}` |
| Workday | `{tenant}.wd{N}.myworkdayjobs.com/{site}` |
| iCIMS | `careers-{slug}.icims.com` · `{slug}.icims.com` |

**Recommended approach — seed then probe:**

1. Build a seed list of **NYC non-tech employers**: hospital systems, insurers,
   universities, city agencies, large nonprofits, banks, media, retail HQs. A few
   hundred names, assembled by hand or from public NYC employer lists. This is the
   part only you can do, and it is where the app's differentiation comes from.
2. Fetch each employer's `/careers` page and regex for the signatures above.
3. Validate the token returns 200 with a non-empty job list.
4. Persist to a `company_ats` table with `last_validated_at`.
5. Re-probe monthly — companies migrate ATS constantly, and the old feed keeps
   serving stale jobs after they do.

**Shortcut for the first pass:** Apify has discovery actors
(`igolaizola/greenhouse-companies`, `wickfeed/ats-company-discovery`) that return
ranked board-URL directories filterable by keyword. One run against health, finance
and education keywords will seed the list faster than crawling, and $5/month covers
it. Then maintain it yourself.

---

## 6. Quota arithmetic

Nightly, at steady state:

| source | requests/night | against |
|---|---|---|
| ATS feeds (300 tokens) | ~300 | nothing — plain HTTP |
| Workday (50 tenants, gated detail) | ~500 list + ~150 detail | nothing — plain HTTP |
| NYC Open Data | ~5 paginated | nothing |
| USAJobs | ~10 | nothing |
| Adzuna | ~30 | 1,000/mo → **fits** |
| JSON-LD career pages | ~100 | Firecrawl 1,000/mo → **tight**, use for iCIMS only |
| Indeed/Glassdoor | ~20 actor runs | Apify $5/mo → **fits if actors are cheap** |
| Google Jobs | ~8 | contributor keys + your 250/mo |

Roughly **1,100 requests/night, of which ~950 cost nothing.** The free tiers are
comfortable. The binding constraint is wall-clock: 1,100 requests at a 1–2s
politeness delay is 20–35 minutes of ingest, before extraction. That is fine, but
it means the nightly window is dominated by `extract.py` (9.3s/call), not by
fetching — which is what Phase 0 needs to measure.

**Where it breaks first:** Firecrawl at 1,000/month is 33/night. Reserve it
strictly for iCIMS and JS-rendered career pages. Do not point it at anything plain
`requests` can handle.

**Closure detection is nearly free** if you pick sources well. ATS list endpoints
return the complete current set in one request — disappearance means closed, no
re-crawl needed. NYC Open Data gives `post_until`. JSON-LD gives `validThrough`.
Only ad-hoc scraped pages require re-crawling, which is another reason to weight
toward ATS and government sources.

---

## 7. Self-hosted

Since compute is free on your box, these avoid free tiers entirely:

- **`curl_cffi`** — TLS fingerprint impersonation. Cheapest possible upgrade over
  `requests` and often enough for lightly-protected sites. Try this before spending
  any credit.
- **Playwright** (already in your toolkit from the Pursuit bot work) — handles
  JS-rendered career pages. Slow, but you have all night.
- **Crawl4AI** — self-hosted, LLM-oriented extraction, no per-request cost.
- **Scrapy** — if the crawl grows beyond scripts.

The honest boundary: self-hosting handles everything except sites with commercial
anti-bot (Indeed, Glassdoor, Google SERP) where you genuinely need rotating
residential IPs you cannot get free. That is a short list, and it maps exactly onto
the three rows where the table above says "Apify actor."

---

## 8. Implementation order

Sorted by relevant NYC postings per unit of effort:

| # | integration | effort | est. relevant/day |
|---|---|---|---|
| 1 | NYC Open Data | XS | 20–60 |
| 2 | USAJobs | XS | 5–15 |
| 3 | Adzuna | XS | 30–80 |
| 4 | ATS token discovery (Apify, one-time) | S | — (unblocks 5) |
| 5 | Retarget `ats.py` at NYC non-tech tokens | S | 50–150 |
| 6 | Workday CXS ingest + upstream gating | **M** | **80–200** |
| 7 | JSON-LD parser (`extruct`) | M | 30–60 |
| 8 | Revive contributor API | S (built) | 10–30 |
| 9 | iCIMS via Firecrawl | M | 20–40 |
| 10 | Idealist + nonprofit boards | S | 10–25 |

Items 1–3 are an afternoon each and roughly triple your relevant corpus. Item 6 is
the biggest single unlock and the only one with real engineering risk.

---

## 9. Avoid

- **ZenRows** — 25-credit multiplier on protected sites and the worst benchmarked
  success rate. A 1,000-credit tier is 40 real requests.
- **ScraperAPI for anything Google** — 25 credits per premium-domain request.
- **Firecrawl for LinkedIn** — refused at the gateway on every tier, including
  stealth modes. Not a config problem.
- **Pointing Firecrawl at plain-HTTP targets.** Its 1,000/month is your scarcest
  renewable credit; ATS feeds cost nothing.
- **`limit > 20` on Workday.** Silent empty response, not an error.
- **Treating a failed Workday page as end-of-list.** Silent 95% data loss.
- **Bulk aggregator feeds as canonical.** JSearch and similar triplicate the same
  posting across Indeed/ZipRecruiter/LinkedIn. Prefer the employer-direct ATS record
  and dedupe on apply URL.
- **LinkedIn, entirely.**
- **Retiring the tech sources yet.** `builtin-nyc`, `weworkremotely` and `hn-hiring`
  still serve your second profile. Drop them from the cohort gate, not from the repo.

---

## 10. Task file mapping

Phase 2 of the master plan becomes:

- `07-ingest-nyc-open-data.md`
- `08-ingest-usajobs-adzuna.md`
- `09-ats-token-discovery.md` — seed list, regex probe, `company_ats` table
- `10-retarget-ats-ingest.md`
- `11-ingest-workday-cxs.md` — including upstream relevance gating
- `12-jsonld-parser.md`
- `13-revive-contributor-api.md`
- `14-ingest-icims-firecrawl.md`
- `15-ingest-nonprofit-boards.md`

Task 11 carries the four silent-failure traps in §4 as explicit acceptance criteria
— each one should have a test that fails loudly rather than returning short.

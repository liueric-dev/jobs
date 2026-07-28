# 20 — iCIMS via Firecrawl

**Status:** todo. **Depends on:** 16, 19. **Blocks:** nothing.
**Estimated yield:** 20–40 relevant postings/day.

The second-largest non-tech employer platform after Workday, and the first task in
the plan constrained by a hard renewable credit budget.

## Why it needs a service

iCIMS career portals are JavaScript-rendered with moderate anti-bot, and unlike
Workday there is no undocumented-but-callable JSON endpoint to reach for. Customer
API access is gated behind partner agreements.

What makes it tractable: **iCIMS detail pages usually carry `schema.org/JobPosting`
JSON-LD**, because customers want Google for Jobs indexing. So task 19's parser does
the extraction; this task only solves *fetching*.

## Budget, stated up front

Firecrawl's free tier is **1,000 credits per month — 33 per night**, shared with task
19's JavaScript-rendered career pages.

That is the entire budget, and it is the tightest constraint in Phase 3. Design
around it rather than discovering it:

- **Index pages, not detail pages.** Fetch the listing page through Firecrawl, then
  attempt detail pages with plain `requests` or `curl_cffi` first. Many iCIMS detail
  pages are static enough to fetch directly once you have the URL.
- **Try `curl_cffi` before spending a credit,** every time. TLS-fingerprint
  impersonation is free and works more often than expected.
- **Cap per-employer spend.** Ten iCIMS employers at 3 credits each is the nightly
  budget. Rotate: not every employer every night.
- **Never retry through Firecrawl.** A failed credit is spent. Retry with the free
  path or defer to tomorrow.

Record credits consumed per night in the quota ledger from task 15. When task 23
builds the router, this ledger is what it reads.

## Alternative worth measuring

**JobsPipe** offers 100 credits/month free forever and returns normalized iCIMS *and*
Workday postings in one schema. That is 3/night — too few to ingest with, but enough
to **verify** with.

Use it as a correctness check rather than a source: pull the same employer through
both paths and diff. If your Firecrawl-plus-JSON-LD pipeline is dropping fields or
postings that JobsPipe returns, you have found a parser bug for the cost of one
credit.

## Fallback if the budget does not stretch

If iCIMS coverage of the seed list turns out large and 33 credits/night cannot cover
it, the honest options in order:

1. Reduce scope — ingest only the highest-value iCIMS employers, chosen by open-job
   count from `company_ats`.
2. Rotate on a weekly cycle rather than nightly. Entry-level postings do not usually
   fill in 24 hours.
3. Spend $10 on Scrapingdog credits, which is the cheapest paid escape in the plan.

Do **not** solve it by signing up for more free accounts. That is the pattern the
plan already rejected for SerpApi.

## Definition of done

- iCIMS employers from `company_ats` ingesting on a rotation that fits the budget.
- `curl_cffi` attempted before every Firecrawl call, with the fallback rate logged.
- Credits consumed recorded nightly in the quota ledger.
- Detail extraction reuses task 19's parser — no second JSON-LD implementation.
- A JobsPipe diff run against at least two employers, with any discrepancies
  filed as defects.
- Cassettes committed.
- A documented answer to "what happens when the budget runs out mid-month" — degrade,
  do not fail the nightly run.

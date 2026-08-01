---
kind: task
written: 2026-07-28
generator: none
---

# 19 — JSON-LD parser

**Status:** ~~todo.~~ **DROPPED on the evidence, `2fecec5`.** **Depends on:** 09, 16.
**Blocks:** 20.
**Estimated yield:** ~~30–60 relevant postings/day.~~ **≤1.1–2.3/day, and that is a
ceiling rather than a measurement.**

**Corrected 2026-07-30:** this line still read `todo` after the spike ran and the task was
dropped. [`README.md`](../README.md)'s Phase 3 row for 19 says *"measured before building —
**2 of 55 employers publish `JobPosting`, 1 of 35 in the target population. DROPPED**"*,
`HANDOFF.md`'s *State at handoff* table carries `19 | JSON-LD coverage spike — dropped on
the evidence | 2fecec5`, and `git log -1 2fecec5` reads *"JSON-LD coverage spike: drop task
19 (tranche_three/19)"*. The evidence is in [`docs/jsonld-coverage.md`](../../../jsonld-coverage.md).

**Nothing below this block was rewritten**, because the design it describes is what was
priced and rejected — the record of what was believed is the point. Read the rest of this
file as the case that was made, not as work to do. **One consequence to carry forward:**
`Blocks: 20` is now a broken edge. Task 20 (iCIMS via Firecrawl) still names 19 in its own
`Depends on:` line and task 21's premise was *"cheap because 19's parser does most of the
work"* — README already records 21 as needing a re-scope for exactly this reason. Neither
was re-scoped here.

Read `schema.org/JobPosting` structured data from employer career pages that have no
public feed. The most durable and least adversarial way to reach the long tail.

## Why this is the right instrument

Employers embed JSON-LD *so that* Google for Jobs can index them. It is published for
machines to read, it is stable across site redesigns in a way CSS selectors are not,
and reading it requires no anti-bot circumvention.

It is also the fallback for every employer in `company_ats` with
`status = 'never_found'` — the ones running Taleo, Oracle, ADP, Paylocity or a
bespoke careers page.

## Fields

`schema.org/JobPosting` gives, at best:

| field | maps to |
|---|---|
| `title` | `title` |
| `description` | `description_text` (HTML — strip) |
| `datePosted` | `posted_at` |
| **`validThrough`** | **closure date** |
| `employmentType` | `employment_type` |
| `hiringOrganization.name` | `company_name` |
| `jobLocation.address` | `location_raw` |
| `baseSalary` | comp fields — **stated, not predicted** |

Completeness varies wildly. Treat every field except `title` as optional and record a
per-employer completeness score; an employer publishing three fields is barely worth
re-crawling.

## Discovery

Two paths, in order:

**Job sitemaps.** Many career sites publish `sitemap.xml` with job URLs and
`<lastmod>`. Crawl the sitemap, fetch only URLs whose `lastmod` changed since last
run. This is the efficient path and it solves re-crawl cost — see below.

**Index-page crawl.** Where there is no sitemap, fetch the careers listing page,
extract job-detail links, follow. Cap depth and per-employer page count hard; an
unbounded crawler pointed at a large careers site is how a nightly job becomes a
six-hour job.

## Extraction

Use `extruct` rather than hand-rolled regex — it handles JSON-LD, microdata and RDFa,
and JobPosting appears in all three in the wild. Prefer JSON-LD; fall back to
microdata.

Expect `@graph` wrappers, arrays of postings on index pages, and `JobPosting` nested
inside `ItemList`. Handle all three or you will silently ingest one posting from a
page carrying twenty.

## Re-crawl is the cost problem

Unlike ATS feeds, there is no list endpoint returning the current set. Closure must
be inferred, and naive re-crawling of every known URL grows linearly with the corpus
until it dominates everything.

Three mitigations, in priority order:

1. **`validThrough`** where present — set `closed_at` directly, no re-crawl at all.
2. **Sitemap `lastmod`** — re-fetch only changed URLs.
3. **Decaying re-crawl** for the remainder — daily for the first week, then weekly,
   then monthly. A posting still open after 90 days is either a ghost job or a
   perpetual req, and either way it does not need daily checking.

Record the re-crawl request count separately in the nightly summary. It is the number
most likely to grow silently past its budget.

## Politeness

Respect `robots.txt` — it is both correct and useful evidence of good faith. Rate-limit
per host, not globally; one employer with 400 postings should not starve the other
fifty.

Set an honest `User-Agent` identifying the project with a contact address. For a
student project serving a nonprofit's students, being trivially identifiable and
easily contactable is the right posture.

## Where a service helps

Plain `requests` handles static career pages. For JavaScript-rendered ones, use
Firecrawl's 1,000 credits/month — but reserve them. Task 20 needs the same pool for
iCIMS, and 1,000/month is 33/night across both.

Try `curl_cffi` first for anything that returns a challenge; TLS-fingerprint
impersonation is free and often sufficient, and it costs an hour to find out.

## Definition of done

- `extruct`-based parser handling JSON-LD, microdata, `@graph`, and `ItemList`
  nesting, with a fixture for each.
- Sitemap-driven incremental crawl where sitemaps exist.
- `closed_at` from `validThrough` where present; decaying re-crawl otherwise.
- Per-employer completeness score stored, so low-value employers can be dropped.
- Per-host rate limiting, honest UA, `robots.txt` respected.
- Re-crawl request count reported separately in the nightly summary.
- Cassettes committed for a rich posting, a three-field posting, and an `ItemList`
  page.

---
kind: task
written: 2026-07-28
generator: none
---

# 21 — Nonprofit and civic boards

**Status:** todo. **Depends on:** ~~19~~ **nothing — 19 is DROPPED**. **Blocks:** nothing.
**Estimated yield:** ~~10–25 relevant postings/day~~ **10–25, unverified**.

> **PREMISE BROKEN, flagged in `README.md` since task 34 and in this file 2026-08-02.**
> [`../README.md`](../README.md)'s Phase 3 row has carried the flag; the file it points at
> did not, so anyone who followed the link read the original premise as current. Task 20 had
> the same defect and was flagged the same day.
>
> Task **19 is dropped** — 2 of 55 employers publish `JobPosting`, 1 of 35 in the target
> population ([`../../../jsonld-coverage.md`](../../../jsonld-coverage.md) owns that figure).
> So "cheap because task 19's parser does most of the work" is false, and the cost of this
> task is unestimated rather than small. **Re-scope or measure first.** What survives
> untouched is everything that is not parsing: board selection, the employer-discovery side
> effect, and the mission-alignment argument below.

~~The smallest yield in Phase 3 and arguably the best-fitting. Cheap because task 19's
parser does most of the work.~~

## Why these belong in the plan

Three reasons beyond volume.

**Mission alignment is real, not rhetorical.** Pursuit's own Mizuho "AI Nonprofit
Build Corps" places graduates into nonprofits as embedded AI talent, and its Goldman
Sachs pilot ran AI literacy training for the social sector. Nonprofits are
demonstrably a destination for this population, and they are chronically under-served
by job boards built for tech hiring.

**Nonprofits hire the profile.** Small technical teams, few formal credential
barriers, and a genuine appetite for someone who can make AI tools useful in
operations. That is close to a description of a Pursuit Builder.

**Almost nobody aggregates them well.** Idealist is the incumbent and its search is
weak. This is a coverage gap, not a redundant source.

## Sources

| board | notes |
|---|---|
| **Idealist** | Largest. NYC-heavy. **Every listing carries a predetermined expiration date** — excellent closure signal |
| **Work for Good** | Smaller, curated |
| **Foundation List** | Foundation and grantmaker roles |
| **Nonprofit New York** | Member org job board; local |
| **NYCON** | NY Council of Nonprofits, statewide |

Start with Idealist. Add the others only if the yield justifies the maintenance —
each is a separate parser and a separate thing that breaks.

## Approach

These are lightly protected and mostly static, so plain `requests` should suffice.
Try `curl_cffi` if any returns a challenge. **Do not spend Firecrawl credits here** —
task 20 needs them and these sites do not require rendering.

Check for JSON-LD before writing any selectors. If a board publishes `JobPosting`
markup, task 19's parser handles it and this task reduces to discovery plus a
sitemap crawl.

Where JSON-LD is absent, the parsers are per-board and brittle by nature. Keep them
small, cassette them thoroughly, and accept that they will break periodically — the
yield does not justify heroics.

## Closure

Idealist's per-listing expiration date is the good case: set `closed_at` directly,
same as NYC Open Data's `post_until` and JSON-LD's `validThrough`.

For boards without one, ~~fall back to task 19's decaying re-crawl~~ **there is no
fallback to inherit — 19 is dropped and its decaying re-crawl was never built.** Reuse
`ingest/nyc-open-data.py`'s `post_until` closure or state that closure is unsolved for
these boards; do not build a third closure mechanism, and do not cite a second one that
does not exist.

## Employer discovery, as a side effect

Nonprofit boards name employers that will not appear in any tech-stack directory.
Feed every distinct employer seen here back into task 16's seed list — a nonprofit
posting on Idealist may also run a Greenhouse or Workable board you would otherwise
never find.

This is the general pattern worth making explicit: **every source is also a discovery
channel for `company_ats`.** Wire that once, here, and reuse it.

## Definition of done

- Idealist ingesting nightly with closure from the listing expiration date.
- JSON-LD checked for before any bespoke selector is written.
- Employers seen are fed back into `company_ats` as candidate seeds.
- Cassettes committed; parser failures degrade the source, not the nightly run.
- A yield measurement after two weeks, with a documented decision on whether to add
  the remaining four boards.

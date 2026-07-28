# 22 — JobSpy spike

**Status:** todo. **Depends on:** nothing. **Blocks:** 23.
**This is a spike, not a build. Timebox it to two days plus a two-week observation.**

Find out whether a self-hosted scraper works well enough from a residential IP to be
the default path for Google Jobs. The answer changes task 23's router and, if
favourable, makes every paid provider a fallback rather than a backbone.

## Why it is worth two days

JobSpy is an open-source Python library that scrapes Google Jobs, Indeed, LinkedIn,
Glassdoor and ZipRecruiter behind one interface. It is the only option in the plan
with **no quota at all** — free, unlimited, running on hardware you already own.

And the deployment target is unusually favourable. Commercial anti-bot systems are
tuned to distrust datacentre IP ranges; a home connection making a few dozen requests
a night with human-scale delays is the traffic profile they are least suspicious of.
That is the opposite of the situation a paid scraping API is solving for, which is
why this is worth testing before spending anything.

The risk is equally real: a self-hosted scraper degrades as sites change, and you own
the maintenance. This spike is about finding out which reality you are in.

## What to measure

Run against **the same query set** through JobSpy and through SerpApi's free 250, so
the comparison is like-for-like.

| question | method | decides |
|---|---|---|
| **Does it work at all from this IP?** | 20 queries, Google Jobs source | whether to continue |
| **Result parity vs SerpApi** | same 20 queries both ways; compare result counts and overlap by apply URL | whether it can be primary or only supplementary |
| **Field completeness** | do descriptions arrive, or only cards? | whether a second detail fetch is needed |
| **Block rate over 14 days** | 30 queries/night, log every failure | the only number that matters for a nightly job |
| **Failure mode** | does a block raise, or silently return zero rows? | how the router must health-check it |
| **Wall-clock** | p50/p95 per query | fit against task 04's window |

That last-but-one is the important one. **A scraper that returns zero rows on a block
is indistinguishable from a genuinely empty search**, which is the same silent-failure
class as task 03's upsert defect and task 18's Workday traps. If JobSpy fails
silently, the router needs a canary rather than an exception handler.

## Decision thresholds

Write these down before running, so the result is not rationalised afterwards.

| finding | consequence |
|---|---|
| block rate < 5% over 14 days, parity ≥ 80% | **JobSpy is the router default.** Paid providers become fallback and overflow |
| block rate 5–25%, or parity 50–80% | supplementary only. Contributor API stays primary; JobSpy fills gaps and absorbs bursts |
| block rate > 25%, or it fails silently and cannot be health-checked reliably | **drop it.** Do not build a router branch around something that lies about its own state |

## Rules for the spike

**Do not integrate anything.** No ingest script, no `run-daily.py` entry, no schema.
A scratch script and a log file. The deliverable is a decision, not code.

**Google Jobs only.** JobSpy also scrapes Indeed, LinkedIn and Glassdoor directly, and
testing those muddies the result — Google Jobs already aggregates them, and LinkedIn
is excluded from this plan on legal grounds regardless of technical feasibility.

**Residential IP, human-scale rate.** 1–3s between queries, a few dozen a night. The
point is to test the deployment you would actually run, not to find the breaking
point.

**Two weeks, not two runs.** Blocking is often gradual — reputation accrues. A clean
first night proves nothing.

## If it works

Note the consequence for the plan's shape: the entire provider table in
[`ADDENDUM-google-jobs-providers.md`](../../../ADDENDUM-google-jobs-providers.md) §2
becomes backup capacity rather than the primary path, and task 23's router gets a
much simpler default. The contributor API (task 24) stays regardless — it is the
community feature, not just a quota source.

## Definition of done

- The six measurements above, recorded with dates.
- A written decision against the thresholds, including which branch was taken.
- The query set committed, so it can be re-run when JobSpy or Google changes.
- No production code merged.

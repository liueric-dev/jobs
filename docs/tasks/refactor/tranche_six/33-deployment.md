---
kind: task
written: 2026-07-28
generator: none
---

# 33 — Deployment

**Status:** todo. **Depends on:** 24, 32. **Blocks:** nothing.

Get this running on a home server for thirty people, without opening a port or paying
for anything.

## Split the pipeline from the app

The two halves have opposite requirements and should not share a failure domain.

| | inbound? | uptime? | if it stops |
|---|---|---|---|
| **nightly pipeline** — ingest, extract, match, score | no | no | one night of ingest lost |
| **webapp + contributor API** | yes | yes | thirty people locked out |

Run the pipeline at home under the existing systemd timer — it already works
(`19ccd1b`, `run-daily.py:68`). If the app can live somewhere with better uptime, put
it there; a power cut should cost a night of ingest, not access.

If everything must stay at home, that is workable — but know which half is fragile and
say so in the operator docs.

## Cloudflare Tunnel, not port forwarding

Free tier, and it solves four problems at once: no static IP needed, no open inbound
ports, TLS terminated, and it sidesteps residential-ISP restrictions on inbound
servers.

`backend/api/app.py`'s docstring is explicit that domain, TLS and reverse proxy are
undone. This closes all three.

Two services behind the tunnel: the webapp and the contributor API (port 8420 per
`backend/api/README.md`).

## Secrets

Non-trivial here because of how many free-tier keys accumulate: the LLM key, SerpApi,
Scrappa, JSearch, Apify, Firecrawl, ScrapingBee, Adzuna, USAJobs, Socrata, plus
Google OAuth.

- `.env` per `backend/.env` (`19ccd1b`), never committed. Verify `.gitignore` covers
  it — **especially if the repo is public**, which it plausibly is as a portfolio
  piece.
- Contributor SerpApi keys stay on contributors' own machines. The API only ever
  receives results, never keys. Confirm nothing in `backend/api/` logs a submitted
  payload in a way that could capture one.
- Rotation should not require a redeploy. Task 23's abstraction already keeps keys out
  of cache keys; keep them out of code too.

## Monitoring, and the one rule that matters

**Alert on volume, not errors.**

Every failure mode in this system is silent. An exhausted API key returns zero rows. A
revoked key returns zero rows. A blocked scraper returns zero rows. A Workday tenant
that changed its site path returns zero rows. None of them raise.

This is the through-line from task 03's discarded upsert errors, task 18's Workday
traps, and task 23's provider router. The deployment-level expression is:

- Record expected nightly volume per source; alert when any source drops below a
  floor.
- Alert when the nightly run does not complete at all — absence of a run is the
  easiest failure to miss.
- Surface per-source counts somewhere a human sees them weekly without going looking.

`jobs-failure@.service` already exists (`run-daily.py:68`) for hard failures. This is
the soft-failure counterpart, and it is the one that will actually fire.

## Backups

`pg_dump` nightly, off the machine. The corpus is the asset — 11,517 rows and growing,
each carrying an LLM extraction that cost real time to produce. Re-extraction is
possible but slow, and task 12's snapshot discipline is worthless if the whole database
is on one disk.

Verify a restore once. An unverified backup is a belief, not a backup.

## Runbook

Write it, and write it for someone who is not you. You are a Builder in a programme
that ends; if this outlives your cohort, someone else needs to be able to run it.

Cover: restarting each service, rotating a key, what to do when a source goes quiet,
how to add an employer to `company_ats`, how to onboard a contributor, and where the
backups are.

## Definition of done

- Webapp and contributor API reachable over TLS through the tunnel; no inbound ports
  open.
- Pipeline and app in separate failure domains, or the coupling documented.
- All keys in `.env`, confirmed gitignored, rotatable without redeploy.
- Volume-based alerting live; a source silently returning zero is caught within a day.
- Nightly `pg_dump` off-machine, with one verified restore.
- A runbook written for a successor.

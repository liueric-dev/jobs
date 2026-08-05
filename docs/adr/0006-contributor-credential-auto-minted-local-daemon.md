---
kind: decision
written: 2026-08-05
generator: none
---

# 0006 — Contributor credentials are auto-minted; the worker stays local and long-running

**Status:** accepted. Direction only — no implementation exists yet.

## Context

`OQ-1`'s parent question (does `api/` stay) was answered 2026-08-03: it stays. The child question —
how a contributor gets a credential — was left open, because `DEC-84`
(`git show refactor-freeze-2026-08-02:docs/tasks/refactor/DECISIONS.md:2903-2933`) named three
mechanisms but all three assumed the existing shape: a script a volunteer remembers to run, using
their own SerpApi account, against a credential someone hands them.

Before picking one, this session checked whether the crowdsourcing model was worth building at all.
Live database numbers: `google_jobs` is 1,643 of 18,235 total jobs (~9%); of those, only 251 came
through the per-query dispatch a credential system would scale (`search_query_results`) — the rest
from the existing nightly bucketed sweep (`ingest/google-serpapi.py`), which needs no credential
work. A paid SerpApi Starter tier ($25/mo, ~1,000 searches/month) would quadruple today's free-tier
ceiling for zero engineering and zero contributor-onboarding risk.

**Rejected anyway.** A paid tier is a fixed ceiling the operator pays for; crowdsourcing scales with
cohort headcount at near-zero marginal cost, compounding across future Pursuit cohorts. Given `OQ-12`
found zero contributors ever onboarded, the blocker was never the model — it was the friction of a
script nobody actually ran.

## Decision

1. **Auto-mint, not a request queue.** `webapp` mints a contributor credential server-to-server
   (`DEC-84` option 2) the moment a Builder acts — login or a "Contribute" affordance — not
   `manage_users.py create` run by hand per request (`DEC-84` option 3).
2. **The worker becomes a long-running local daemon**, started once, polling `api/`'s claim endpoint
   on an interval — not a script re-invoked daily.
3. **SerpApi is called from the contributor's own machine, on their own key, from their own natural
   IP — never proxied through the operator's server.** Two reasons, both checked live this session
   rather than assumed: SerpApi's own CORS policy blocks browser-origin calls outright, so a browser
   could never make the call directly regardless of trigger; and there is no confirmed SerpApi policy
   on many distinct accounts calling from one shared IP, which is a common fraud-detection signal
   industry-wide and one SerpApi has extra reason to enforce (they are being sued by Google over
   anti-scraping circumvention). Centralizing ~30 real people's accounts on that unconfirmed footing
   risks getting them banned — worse than the current zero-contributor status quo.
4. **No webapp control layer over the running daemon, for now.** Technically possible via a local
   companion HTTP server the daemon binds and the webapp's JS calls at `127.0.0.1` — but Safari
   deliberately blocks this as mixed content (unlike Chrome) and Chrome's own Local/Private Network
   Access rules are mid-rollout toward a permission prompt. Deferred as speculative build against a
   feature with no realized usage yet.

## Consequences

- `DEC-84`'s option 1 (grant `jobs_web` INSERT on `jobs_api`'s tables) is rejected outright — same
  blast-radius argument that closed it originally.
- `manage_users.py create` stays as the manual fallback, not the primary path.
- Nothing here is scoped into buildable steps yet: the mint endpoint, the daemon script, its
  packaging, and the server-to-server shared secret are follow-up `T-`/`OQ-` rows for a future
  session, per `TASKS.md`'s own ceiling against turning a decision into an unbounded sub-project.
- Separate, unactioned finding surfaced while reading the sweep for context: `config/
  google-queries.json`'s bucket comments ("weighted to Eric's actual positioning") still read as the
  pre-Pursuit single-operator persona, not the current cohort.

---
kind: decision
written: 2026-08-07
generator: none
---

# 0007 — Contributor credentials mint at opt-in; the worker is scheduled, not resident

**Status:** accepted. Supersedes [0006](0006-contributor-credential-auto-minted-local-daemon.md)
decisions 1, 2 and 4. Decision 3 there — local execution, contributor's own key, own IP, never
proxied — is retained unchanged and is load-bearing for everything below.

## Context

0006 read `OQ-12`'s zero contributors as friction and removed a step from the credential request.
That misreads which step failed: nobody was ever blocked waiting on a credential, so auto-minting at
login optimises the cheapest part of onboarding while leaving the expensive part — installing and
running software on a personal machine — untouched. It also mints submit-capable credentials for
Builders who never opted in.

Two further constraints surfaced that 0006 did not weigh. `searchnorm.RERUN_HOURS` against a SerpApi
free tier allows far fewer watched queries per contributor than `searchnorm.MAX_QUERIES_PER_BUILDER`
promises, so the ceiling binds before any sharing does. And the free tier does not roll over, so a
fixed cadence both fails a contributor whose machine was closed for a week and abandons credits that
expire at cycle end.

## Decision

1. **Mint at opt-in, not at login.** The mint endpoint is the installer: opting in mints the
   credential and returns it inside a `config.json` the Builder drops beside the worker. One paste,
   one secret entered by hand — their SerpApi key, which never reaches the server.
2. **Scheduled invocation, not a resident daemon.** `--install` writes a launchd `StartInterval`
   agent and `--uninstall` removes it. The OS owns the schedule, so it survives reboot and sleep
   without a process to keep alive.
3. **The server dictates the interval and holds desired state.** Each poll response carries the next
   interval and a paused/active flag; the worker clamps the interval against a local floor and holds
   no other policy. This replaces 0006's deferral of a control layer: pause, resume and interval
   changes need no local listener, so Safari mixed content and Chrome's Private Network Access rules
   never enter it. Uninstall stays local and manual.
4. **Budget pacing replaces cadence as the spending primitive.** Allowance is credits remaining
   divided by days left in the cycle, recomputed per run from the contributor's own plan data.
   `RERUN_HOURS` demotes to a minimum-freshness guard and stops deciding whether a query runs.
5. **The keyword list is a discovery surface; contribution is a switch over it.** A watch row is a
   Builder's saved keyword. Without contribution the list filters and pins the existing corpus; with
   it, the same list is also dispatched. Nothing in the UI names claims, cadence or watchers.
6. **The leech path is deferred until measured.** A worker may claim only rows its Builder watches,
   plus seeded and track sources. Spare capacity is asserted by nobody until the empty-claim rate
   shows it exists.
7. **Windows is manual-run only.** The cohort is overwhelmingly Mac. A Windows Builder runs the
   worker by hand; packaging an installer is out of scope, not forgotten.

## Consequences

- `api/query_claims.py` claims a dataset row; per-query dispatch needs a second claim mode over
  `search_queries` with the same conditional-update and takeover protection.
- `MAX_QUERIES_PER_BUILDER` is a promise the free tier cannot keep. The cap becomes derived from the
  contributor's reported plan and surfaced as a soft warning rather than a block.
- Under decision 6 a keyword watched only by non-contributors never runs. Its empty state stays
  plain; the case for contributing lives in onboarding, not in an empty result.
- Dormancy is account-level and pauses spending, not check-in, so status still reports and nothing
  needs re-enabling on return.
- `config/google-queries.json`'s persona comments, flagged unactioned in 0006, now shape what every
  contributor's credits are spent on and stop being cosmetic.

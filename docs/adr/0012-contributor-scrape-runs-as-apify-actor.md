---
kind: decision
written: 2026-09-24
generator: none
---

# 0012 — The contributor scrape runs as an Apify actor in each classmate's own account; SerpApi is disabled pending review

**Status:** accepted. It supersedes three earlier decisions:
- [0006](0006-contributor-credential-auto-minted-local-daemon.md) decision 3: the contributor ran SerpApi from their own machine.
- [0007](0007-contributor-credential-opt-in-scheduled-worker.md) decision 2: the launchd worker.
- 0007 decision 4: SerpApi budget pacing.

It keeps 0007 decision 1, minting at opt-in. It also keeps decision 3, the server dictating pause and cap, which the actor honours.

## Context

**The ask was never adopted.** The contributor path from 0006 and 0007 asks a Builder to do three things: install a Python worker on their laptop, give it a SerpApi key, and keep the laptop awake on a launchd schedule. No contributor key was ever minted (`OQ-12`). The step that costs is still the install.

**Google Jobs was the operator's bill.** Beside that path, the operator's own nightly run fetched Google Jobs twice:
- through SerpApi's free tier, shared across machines;
- through a third-party Apify actor billed per result to the operator.

**Apify fits the ask.** It runs code on a schedule in the user's own account. A private actor can be shared to named users, and runs in *their* account, billed to *their* credit. Its free plan includes monthly credit without a card. So "install and schedule software" shrinks to "accept a share and click Schedule". The scrape stops being the operator's cost.

**Apify does not make Google Jobs easy to scrape.** Its Google SERP proxy covers Google Search and Shopping, not Google Jobs. Scraping Jobs ourselves means a headless browser on residential proxies. That is the configuration in which a cheaper third-party actor was already CAPTCHA-blocked (`backend/ingest/google-apify.py` docstring).

## Decision

1. **The actor is ours, and so is the orchestration.** It lives in `actor/` at the repo root. It speaks `api/`'s existing claim, submit and release protocol unchanged. `submit` already recomputes every derived field server-side, so the actor can't choose a row's identity.
2. **The scrape is delegated for now.** Our actor calls the same third-party Google Jobs actor the operator used, from inside the classmate's account. Its output is the shape `google_jobs.normalize_job` already reads. The scrape sits behind one function so a scraper of our own can replace it later; the protocol stays the same when it does.
3. **Identity is Google sign-in, restricted to one Workspace domain.** A scheduled actor can't complete an interactive login, so Google gates who gets a key and the actor carries the key.
   - The webapp admits a verified account from `ALLOWED_SIGNUP_DOMAIN` on first login, attached to the existing profile `SIGNUP_PROFILE` names.
   - Opt-in returns the key as `actor_token`. It is the same single credential as before, readable in the same single response.
   - The allowlist stays the only way in for anyone outside that domain. The domain rule never creates a profile.
4. **SerpApi is disabled, not deleted.** Three steps leave `run-daily.py`'s step list pending the owner's review: the SerpApi ingest, the operator-billed Apify ingest, and `searchqueries.py` (whose provider defaults to SerpApi). Their files are kept.
5. **Every query bucket is offered to contributors.** `api/` withheld Apify only because it billed the operator. That reason is gone.

## Consequences

- **Cost:** the contributor pays per result and the operator pays nothing for Google Jobs. The actor's default is one query per run, so a free-plan classmate running it daily stays inside the monthly credit. `api/`'s daily cap and pause still apply.
- **Volume check:** Google Jobs volume is no longer visible to `run-daily.py` or `config/volume-floors.json`. It is measured from `submission_log`. Nothing alarms on it yet.
- **No date filter:** the delegated actor has none, so `date_chip` is returned and ignored. Every query re-fetches its top results. `GOOGLE_STICKY` keeps the first-seen `posted_at` as before.
- **Supply-chain dependency:** the scrape depends on the third-party actor's pricing and output shape. A change there breaks every classmate at once, and it surfaces as submit rejections in `submission_log`.
- **Open ADR 0007 work:** the rows about the SerpApi worker's install and pacing no longer describe the live path. They stay open until the SerpApi review decides whether that worker returns.

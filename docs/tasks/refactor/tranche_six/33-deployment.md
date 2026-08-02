---
kind: task
written: 2026-07-28
generator: none
---

# 33 — Deployment

**Status:** todo. **Depends on:** ~~24, 32~~ **nothing hard — see below**. **Blocks:** nothing.

> **BOTH ARROWS ARE SOFT, AND ONE OF THEM IS HALF OF A CYCLE. Corrected 2026-08-02.**
>
> **`24` is a cycle.** [`../tranche_four/24-revive-contributor-api.md`](../tranche_four/24-revive-contributor-api.md)`:9`
> declares *"Depends on: 23, **33** (tunnel)"* while this file declared 24. One of the two
> has to be soft and it is this one: the tunnel, the secrets, the backups, the alerting and
> the runbook do not read a line of the contributor API. Only the *"contributor API
> reachable over TLS"* clause of the first Definition-of-done bullet does, and that is one
> clause of one bullet. **24 genuinely needs the tunnel; the tunnel does not need 24.**
>
> **`32` is not real at all.** No bullet in the Definition of done reads frontend code.
> `backend/webapp/` runs standalone and the tunnel fronts a FastAPI app whether or not a
> client exists.
>
> **So the deployable half is deployable now**, and the half with no prerequisite at all is
> the one that would have caught the most: `pg_dump` off-machine with one verified restore,
> and volume-based alerting. `.claude/CLAUDE.md` § *Landmines* — *"Silence is this system's
> failure mode … alert on volume, not errors"* — is an argument for doing that half first
> rather than last.
>
> This is the **third** wrong arrow found in this tranche and the second cycle. The first
> two both pointed at 26.

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

---

## What the work turned up

Written by the implementing session. The `DECISIONS.md` entries below are **full text
with no number allocated** — the orchestrator numbers and lands them.

### Where the task file was wrong

**"`jobs-failure@.service` already exists (`run-daily.py:68`)".** The unit exists, but
that citation is off: `run-daily.py:68` is the `INSTALL:` line of the docstring, and
the unit is named at `run-daily.py:75-76`. More usefully, the unit **was not in the
repository at all** — see the finding below. Corrected by bringing it in-tree; the
citation is now `deploy/systemd/jobs-failure@.service`.

**"`19ccd1b`, `run-daily.py:68`" for the existing systemd timer.** Same line drift;
the schedule is documented at `run-daily.py:71-86`.

**"11,517 rows and growing."** Not re-measured, and deliberately not restated anywhere
this task wrote. Rule 3 — a number a script can produce is never typed into prose.

### D — `backend/scripts/` was gitignored and nobody could have known

`.gitignore:60` read `scripts/`, unanchored, so it matched **at every depth** — including
`backend/scripts/`. The four files already tracked there were unaffected, because
tracking beats `.gitignore`, so `git status` was clean and nothing was ever red. What
broke was the *next* file added: `backend/scripts/backup-jobs.sh` did not appear in
`git status` at all.

The comment above the pattern describes only `scripts/tranche-two-launcher.sh` at the
repo root, so the breadth was never intended. Fixed by anchoring to `/scripts/`, with
both halves verified (`git check-ignore -v` on each) and pinned by
`backend/tests/test_secrets_rotation.py::test_backend_scripts_is_not_ignored`.

This is the deployment-shaped version of the same failure the whole task is about: a
backup script silently not in the repo is indistinguishable from a backup script that
is there, exactly as a source silently returning zero is indistinguishable from a slow
week.

### DECISIONS.md entry — Cloudflare Tunnel supersedes the Tailscale plan

> **33 — Tailscale or Cloudflare Tunnel?**
>
> `backend/api/README.md:182-204` documented a two-phase Tailscale plan: phase 1
> tailnet-only with no TLS, phase 2 Tailscale Funnel for public contributors. Task 33
> specifies Cloudflare Tunnel. These are not the same plan and the difference is a
> decision, not a typo.
>
> **Decided: Cloudflare Tunnel, one transport, from day one, for both services.**
>
> The Tailscale argument was *correct* and is struck rather than deleted. Tailscale is
> WireGuard: transport is already encrypted and device-authenticated, so bearer tokens
> over plain HTTP inside a tailnet genuinely are fine, and the README is right that
> adding a proxy there buys nothing. Nothing about that reasoning is wrong.
>
> What changed is the population. Phase 1 was written when the only callers were one
> person's own devices. The service now has to serve ~30 Builders who are not on
> anyone's tailnet and **must never be put on one** — the same README already says why,
> because that would grant network-level access to a home network. Once every real
> caller is outside the tailnet, phase 1 describes a configuration with no users, and
> maintaining two transports to reach a state nobody uses is more surface, not less.
>
> Between Funnel and Cloudflare for phase 2 the margin is genuinely thin, and Funnel
> was a defensible answer. Cloudflare wins on three narrow points: it serves the
> **webapp** on the same mechanism, so there is one thing to understand rather than two;
> it takes an ingress config as a **tracked file** (`deploy/cloudflared/config.yml`),
> where Funnel's state lives in the tailnet's control plane and would have been the
> second piece of this deployment living only on a machine; and its hostname does not
> encode the tailnet's node name, so moving the app off this box later does not change
> the URL thirty people have bookmarked.
>
> **Rejected: Caddy or nginx with a forwarded port.** Both need port 443 open on a
> residential connection, a certificate to renew, and a dynamic IP to track — four
> failure modes where the tunnel has one.
>
> **Rejected: keeping phase 1 as a documented fallback.** A fallback nobody exercises
> is not a fallback. If the tunnel is down, the fix is to fix the tunnel; `ssh -L` to
> `127.0.0.1:8421` covers the operator's own emergency access without a second
> supported configuration.
>
> **What this decision does not buy, and it is worth stating because it is easy to
> assume otherwise:** the tunnel authenticates the *origin* to Cloudflare, not the
> *user* to the app. Both hostnames are reachable by anyone on the internet. The
> webapp's Google OAuth session and the contributor API's bearer key are the only
> things keeping strangers out, and `backend/api/README.md`'s two open gaps —
> unmetered claiming, no per-contributor provenance — are the places that matters.

### DECISIONS.md entry — the app stays on the home box, and the coupling is named

> **33 — Does the app move off the home server?**
>
> The task's § *Split the pipeline from the app* asks for the two halves to be in
> separate failure domains, and allows "if everything must stay at home, that is
> workable — but know which half is fragile and say so".
>
> **Decided: both halves stay on the home box for now. The coupling is documented
> rather than removed, in `docs/RUNBOOK.md` § *Failure domains*, which names the three
> things they actually share.**
>
> They are now separate systemd **units** — each restarts alone, each fails alone,
> `Restart=always` on the two services with systemd's start-limit removed so a flapping
> restart cannot disable the unit and lock the cohort out. That is a real improvement
> over one process tree and it is as far as unit boundaries can take it.
>
> **What is honestly still shared**, and the runbook says so rather than implying
> otherwise:
>
> 1. **One Postgres instance.** The single point of failure in the design. Splitting it
>    means either a managed database (recurring cost, which the task rules out) or
>    replication (an operational burden well beyond thirty users).
> 2. **One host.** So a power cut costs a night of ingest **and** locks thirty people
>    out. **The task's stated goal — "a power cut should cost a night of ingest, not
>    access" — is therefore NOT met**, and that is recorded as an open gap rather than
>    reported as done.
> 3. **One `job_ingest_state` claim row**, shared between the pipeline and the
>    contributor API. The least obvious coupling and the most likely to bite: a
>    contributor holding a claim blocks the nightly pipeline from that query for
>    `CLAIM_TTL_MINUTES`, and claiming is currently unmetered.
>
> **Rejected: moving the app to a free-tier PaaS now.** It would fix (2) and worsen (1)
> — the app would reach Postgres over the internet, so the database would need to be
> exposed or tunnelled outward, converting a power-cut risk into a permanent attack
> surface. Not a trade worth making before there is evidence that home uptime is
> actually the binding constraint.
>
> **The trigger to revisit**, so this is a decision with an expiry rather than a
> default: the first time a Builder reports being unable to reach the app for a reason
> that was not a deploy. The app is stateless apart from Postgres and moves easily; the
> pipeline is the half that wants to be near the database and does not care about being
> reachable.

### DECISIONS.md entry — a volume floor is a window, not a nightly number

> **33 — What shape is a per-source volume floor?**
>
> The task asks to "record expected nightly volume per source; alert when any source
> drops below a floor". Implemented literally, that check fires constantly.
>
> **Decided: a floor is a minimum total over a trailing window of runs, and the window
> is a property of the source.** `backend/config/volume-floors.json` carries both per
> source, with the journal command that produced every number.
>
> The evidence is the five nightly runs the journal held on 2026-08-02. A nightly floor
> would have fired on **four of the nine sources while nothing was wrong**: `hn-hiring`
> is one monthly thread and wrote zero on every night measured; `nyc-open-data` wrote
> zero on four of five, because it re-reads a full slice and unchanged rows are
> deliberately excluded from the written count; `weworkremotely` ran 0/0/3/2/2. Zero is
> those sources' ordinary Tuesday, and an alarm that cries wolf teaches the reflex that
> retires all the others.
>
> Two further shape decisions fall out of the same data:
>
> **Floors are set to catch zero, not to catch a dip.** `ats` wrote 1143 one night and
> 105 another with nothing wrong either time. Any floor tight enough to see that swing
> fires most weeks, so the shipped floors sit roughly an order of magnitude below the
> observed window minimum. The quantity being defended is "the boards still answer",
> not "the boards are as busy as last week".
>
> **Rejected: a percentage of the trailing median.** The obvious design, and it fails on
> exactly the case that matters — a source returning zero for a week has a median of
> zero, so its floor becomes zero and the check agrees that nothing is wrong. A floor
> that adapts to the outage it is meant to detect is not a floor.
>
> **Rejected: one global floor over the run total.** `ats` outweighs everything else by
> an order of magnitude, so it alone holds any global total above any global floor while
> every other source is dead.
>
> **Also decided: the check runs outside `run-daily.py`.** The hardest failure to notice
> is the run that never happened, and a check inside the run is structurally incapable
> of reporting the run's absence. `run-daily.py` appends per-source counts to
> `backend/.run-volumes.jsonl`; `jobs-volume-check.service` reads them back on its own
> timer, so staleness of the newest entry is a finding like any other. It also keeps a
> quiet night off `jobs-ingest.service`'s exit code — "a step crashed" and "a source
> went quiet" need different responses, and one alert channel meaning both very quickly
> means neither.
>
> **The floors are provisional and say so.** Five nightly runs is the whole history the
> journal held. The config's `_n` field records that and names re-derivation from a
> longer `.run-volumes.jsonl` as the next step.

### Open gaps, for whoever picks this up

- **The two halves still share a host.** See the second decision above. This is the one
  DoD bullet that is *documented rather than met*.
- **The restore rehearsal verifies data, not ACLs.** `pg_restore --no-owner` means
  grants are not exercised, and `jobs_api`'s six grants are a security boundary. The
  roles-only dump is taken nightly and **nothing rehearses it**. `docs/RUNBOOK.md`
  § *Restoring for real* works around this by starting `jobs-api.service`, which
  refuses to start when a grant is missing — but that is a manual step in a procedure,
  not a check.
- ~~**`backend/api/app.py:292`** returns `detail=f"malformed body: {e}"`, and a pydantic
  `ValidationError` string can carry the offending input. It is a response body to the
  sender and nothing persists it, so it leaks nothing today; it becomes an exposure the
  moment anything in front of the service logs response bodies. Recorded in
  `docs/RUNBOOK.md` § *The audit behind the "no payload is logged" claim*. Not changed
  here — another stream owns that file.~~
  **Numbered `D73` and fixed 2026-08-02 by task 24**, the stream that owns `app.py`.
  **The cite above was wrong by 58 lines**: the site was `app.py:350`, inside `submit()`,
  and `:292` lands on the daily-cap `HTTPException` in `claim()` — a different handler
  raising a different status, so the citation resolved to plausible-looking code rather
  than to nothing. Struck rather than corrected in place, because a stale line number is
  worth keeping visible next to the entry that shows what it costs. The severity was also
  understated here: for the `json_invalid` case, which is every syntactically broken body,
  pydantic's `input_value` is the **whole request body**, not one field of it. See
  [`DEFECTS.md` § D73](../../../ingest/DEFECTS.md#d73).
- **`config/volume-floors.json` has no floor for `workday`'s real shape.** Two runs of
  history, both after the step landed. It is the least-evidenced number in the file and
  the first to re-derive.

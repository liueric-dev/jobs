---
kind: rolling
written: 2026-08-03
generator: none
subject: .
budget: 450
---

<!--
BUDGET NOTE. Task 53 specified 250, assuming each row could link to the document owning the
argument and stay one sentence. Those documents were deleted on 2026-08-02 -- DECISIONS.md,
AUDIT.md, OPEN-QUESTIONS.md and the task files are all behind refactor-freeze-2026-08-02 now --
so the "How to do it" column absorbed them. Raised once, deliberately, with the reason recorded.
The spec's rule applies from here: past 450, move narrative out rather than raise the number.
-->


# Dev tasks — everything that is on the owner

**This file owns the prefix `OQ-`.** One allocator. **The next free number is `OQ-17`.**
Numbers are never reused and never renumbered; `OQ-7` is closed and stays in the table so that
citations to it keep resolving.

**Every row here needs you.** A session cannot start any of them: each needs a machine, an
account, a device, other people, or a decision only you can take. That is what makes this the
critical path and the least visible thing in the repo.

It is Part A of `git show refactor-freeze-2026-08-02:docs/tasks/refactor/tranche_nine/53-owner-queue-and-changelog.md`,
which specified it under `docs/` as OWNER-QUEUE.md — same six columns, same `OQ-` namespace, at
the root under the name you asked for. Part B was never built; it is `T-9` now.

**How to use it.** The *Why it is yours* column is the one to sort on, because it says whether
waiting helps. `decision` rows are free and unblock work immediately — nothing is stopping them
but you. `account` and `device` rows cost money or a signup. `people` rows have a lead time you
cannot compress, so start them first even though they finish last.

**Do not restate these rows elsewhere** — link here. When a row closes, strike it and keep it.

---

## The one-minute version

| if you have | do this |
|---|---|
| **5 minutes** | `OQ-9` — pick the floor of record. Every model figure you or anyone quotes is provisional until you do |
| **30 minutes** | `OQ-4a` — install the systemd units. The volume alarm is the only thing watching for silent ingest failure and it is not running |
| **an evening** | `OQ-4b` — Cloudflare account, tunnel, one verified restore. Unblocks everything a Builder can reach |
| **a week of lead time** | `OQ-3` — line up labellers for round 2. This is the gate the whole scoring redesign is waiting on |

**If you do only one thing: `OQ-3`.** The scoring redesign completed 2026-07-28 and has never
been validated, because GATE 4 of the master plan needs labels that do not exist yet. Everything
else on this list improves a system nobody has confirmed works.

---

## Open

### OQ-3 — More labellers on the same ten overlap rows, and round 2

**Why it is yours:** people. Longest lead time on the list; start it today even though it
finishes last.

**What:** Round 2 is due around 2026-08-09 and needs ≥100 distinct postings from ≥5 labellers.
Today there are 2 labellers, 36 postings, and **10 rows of overlap**.

**How to do it.** More *postings* do nothing — 25 of the 36 carry a single labeller and add
exactly zero to the ceiling. What is needed is **more people labelling the same ten rows**.
Recruit from the cohort, point each at the labelling flow, and check progress with:

```bash
cd backend && python3 -m evals label status
```

**What it unblocks:** task 30, task 13's weights, task 12's next `FACTS_VERSION` bump, and
GATE 4 of the master plan — which is the gate that says whether the scoring redesign worked.
It also un-denominates every model-vs-human figure in the repo, all of which are currently
computed against a ceiling derived from those 10 rows.

**Done when:** `evals label status` shows ≥5 labellers on the overlap set, and the recomputed
human ceiling sits **above** the model floor on at least the fields it currently sits below.

---

### OQ-9 — Which of the two n=115 selfchecks is the floor of record?

**Why it is yours:** decision. Costs nothing, unblocks immediately, and is the cheapest row here.

**What:** Two committed self-consistency runs on the same frozen corpus, five days apart,
disagree by up to 9.6 points. Neither carries a supersession marker, so both are "current" and
both are quoted.

**How to do it.** Read both, pick one, and write the reason into the loser:

```bash
ls backend/evals/fixtures/results/
#   selfcheck-n120-2026-07-28.json     <- the original
#   selfcheck-n120-2026-08-02.json     <- the re-run
```

Three defensible answers, and my recommendation is the third:

1. **The later run.** Newer, same corpus, same model. But "newer" is not a reason on its own.
2. **The lower of the two, per field.** Conservative; you can never be accused of overstating.
3. **Both, as a range, with the lower bound as the number you act on.** *Recommended* — the
   spread is the finding. A model that moves 9.6 points at temperature 0 across five days has a
   stability problem, and collapsing that to one number deletes the most important thing you
   learned. Quote it as a range, tune against the floor.

Whichever you pick, add a `_comment` to the superseded file saying so and dating it — that is
the house convention and the reason `config/*.json` survived the purge.

**What it unblocks:** every figure quoted from either run, including the ones in
`.claude/CLAUDE.md` and `docs/STATE-OF-THE-SYSTEM.md`.

**Done when:** one file carries a supersession marker naming the other, and § 6 of
`docs/STATE-OF-THE-SYSTEM.md` states the decision rather than presenting both.

---

### OQ-1 — Is `backend/api/` being retired or kept warm, and who issues a contributor credential?

**Why it is yours:** decision, and it is a product call rather than a technical one.

**What:** Two signals point opposite ways. `deploy/systemd/jobs-api.service` says the service is
deprecated and says to delete the unit and its cloudflared ingress rule **together** — an ingress
hostname with nothing behind it is a 502 that reads as an outage. Meanwhile tranche work landed
in `api/` on 2026-08-02.

**How to do it.** Answer the parent question first — *is there a contributor work queue in this
product a year from now?* Then the credential question resolves itself. If yes, pick one of
`DEC-84`'s three options for issuing a credential:

1. Grant `jobs_web` INSERT on `jobs_api`'s tables — simplest, weakest isolation.
2. A server-to-server mint — most work, cleanest boundary.
3. A request queue you service by hand — no code, does not scale, fine for ~30 Builders.

If no: delete the unit and the ingress rule together, drop `api/`, and close task 24.

```bash
# what exists today
backend/api/manage_users.py list          # contributors and keys
backend/api/manage_users.py create        # mint a contributor + API key
```

**What it unblocks:** task 24, the Contribute surface (currently unbuilt), and `OQ-12`.

**Done when:** either `api/` is gone from the tree and the unit list, or task 24 has a chosen
credential path written into `DEC-84`.

---

### OQ-2 — The 24h impression dedup key

**Why it is yours:** decision. One line of code; the code will not choose for you because the
choice is about what an impression *means*.

**What:** The dedup key is `(profile, job_id)` and holds no `app_user_id`. Thirty Builders share
the `pursuit` profile, so **the first Builder to load the list suppresses every other Builder's
impression of those postings for the window** — and skips are derived from impressions, so they
inherit it. `backend/webapp/jobs.py:897` states in capitals that this is yours and not an
oversight; `941cd94` deliberately left it alone.

**How to do it.** The original framing asked `(profile, job_id)` vs `(profile, job_id,
request_id)` and **that was the wrong question** — the binding axis is `app_user_id`. The real
options:

1. `(app_user_id, job_id)` — *recommended*. One Builder's render no longer speaks for another's.
   This is almost certainly what "a list re-render is not new information" was meant to say.
2. `(app_user_id, job_id, request_id)` — every render counts. Truer to the event stream, noisier.
3. Leave it. Only defensible if you decide the cohort is the unit of analysis and no per-Builder
   figure will ever be computed. Say so in the `_comment` if you pick it.

**What it unblocks:** every per-Builder engagement figure, and the L2 layer generally. Note that
existing `job_events` rows were written under the current key and **must not be backfilled** —
a guessed rank is worse than a missing one.

**Done when:** the key is chosen, `webapp/jobs.py`'s comment records the decision and its date,
and the replay tests cover a second Builder seeing the same posting.

---

### OQ-8 — Name the tracks, or ship the grouping with the vocabulary it has

**Why it is yours:** decision. Building the mechanism was ungated; choosing the names is not.

**What:** `backend/score.py:280` defines `TRACKS` as the author's five-value enum — Core SWE /
AI Integration / Bridge & Solutions / Re-Entry & Growth / Poor Fit. `config/pursuit-persona.json`
records that these **"do not describe this population"** and assigns naming to task 30.

**How to do it.** Harmless today — `daily_narrative_budget` is 0, so nothing is written for this
profile — but it blocks the display half of task 30 independently of the labelling experiment.
Either write five names that describe Pursuit Builders, or decide the grouping ships using
`extract.ROLE_TRACK`'s nine slugs with the hand-written plain-language copy it already has.
The second is a real answer, not a punt.

**What it unblocks:** task 30's display half.

**Done when:** `score.TRACKS` and the persona `_comment` agree, and neither says the names are
wrong.

---

### OQ-5 — Apply the `revenue_commercial` archetype?

**Why it is yours:** decision, and it is partly a one-way door.

**What:** Proposed in `DEC-64`/`DEC-65` and deliberately unapplied. It is a `FACTS_VERSION` bump
and `pursuit-v1` is mid-labelling.

**How to do it.** Cheaper to answer than it was: labels written from 2026-08-02 carry the
`facts_version` they were formed against (`DEC-95`), so a bump no longer silently re-denominates
the agreement figures — it shows up as a version split in `python3 -m evals label status`. Rows
labelled *before* that date are unrecorded and always will be, so the bump is one-way for those
and only those. Weigh how many that is before deciding.

**What it unblocks:** `role_archetype = other` stops being a catch-all.

**Done when:** either applied with the bump recorded, or the row is struck with the reason.

---

### OQ-15 — Is the `ingest/google-*.py` ↔ `serp/providers/*` duplication temporary or permanent?

**Why it is yours:** decision. The code supports both readings and they imply opposite fixes.

**What:** Two SerpApi implementations coexist and **disagree**:
`backend/ingest/google-serpapi.py` raises on any `error` key, so "no results" is recorded as a
query failure; `backend/serp/providers/serpapi.py` treats it as empty. Held back on purpose by
`DEC-99`. Router fallthrough is unimplemented and unflagged.

**How to do it.** If **temporary**, the fix is to finish the seam: make `serp/providers/` the
one implementation, delete the duplicate, implement router fallthrough. If **permanent**, the fix
is the opposite — document the split, and reconcile the two error dispositions so they at least
agree on what "no results" means, because today one of them is silently recording failures that
are not failures.

**What it unblocks:** task 23's remaining half.

**Done when:** one disposition for an `error` key exists in the tree, or two exist with a
`_comment` at each saying why.

---

### OQ-16 — Does the `kind: record` handoff carve-out stay?

**Why it is yours:** decision, and it sets policy for every future document.

**What:** `backend/docs/HANDOFF-multimachine-google-jobs.md` is the last handoff document — 362
lines, `kind: record`, frozen 2026-07-25, self-labelled "history rather than state." The purge
deleted every other one.

**How to do it.** The emergent rule after the purge is *no document may claim current state
except the three `kind: contract` files*, with `kind: record` as a carve-out for frozen history.
Either:

1. **Keep the carve-out** — it is honest, the header is explicit, and nobody has been misled by
   it. Cost: one more document that a future session has to classify before trusting.
2. **Close it** — lift the two or three still-live facts into `backend/README.md` and read the
   rest from `git show refactor-freeze-2026-08-02:backend/docs/HANDOFF-multimachine-google-jobs.md`.
   Cost: half an hour. Benefit: the rule becomes "three contracts and READMEs", with no
   exceptions to explain.

**Done when:** either the file is gone, or `.claude/CLAUDE.md` states the carve-out as policy.

---

### OQ-4a — Install the eleven absent systemd units

**Why it is yours:** machine. No account needed — this one is just a terminal.

**What:** `deploy/systemd/` holds 14 units and **3 are installed**. The three that are live are
**user** units at `~/.config/systemd/user/`, dated 2026-07-26, and they **differ from the repo
copies today** — so editing `deploy/systemd/` changes nothing that runs.

**The one with a live consequence:** `jobs-volume-check.timer` is not installed. History is now
accruing (`backend/.run-volumes.jsonl` exists and `tools/volume-check.py` exits 0), but nothing
runs the check, so **the only alarm watching for silent ingest failure is not watching.** This
repo's stated failure mode is silence — exhausted keys, revoked keys, blocked scrapers and
changed endpoints all return zero rows rather than raising.

**How to do it.**

```bash
systemctl --user list-unit-files | grep jobs     # what is live now: 3
ls deploy/systemd/                               # what exists: 14

# diff each live unit against its repo copy BEFORE overwriting -- they have drifted
diff ~/.config/systemd/user/jobs-ingest.service deploy/systemd/jobs-ingest.service

cp deploy/systemd/jobs-volume-check.{service,timer} ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now jobs-volume-check.timer
```

**Done when:** `systemctl --user list-timers` lists `jobs-volume-check.timer`, and after a few
nightly runs `python3 tools/volume-check.py` reports a comparison rather than
`insufficient history` on every source.

---

### OQ-4b — The account half of deployment, and one verified restore

**Why it is yours:** account. `DEC-91` already took the Cloudflare-vs-Tailscale call and `DEC-92`
took the stays-on-the-home-box call, so nothing here is a decision any more — it is purely
account access and a person at a terminal.

**What:** A Cloudflare account, a domain, one `cloudflared tunnel create` to fill
`deploy/cloudflared/config.yml`'s placeholders, and the `cloudflared` binary
(`/usr/local/bin/cloudflared` does not exist). Plus `~/.config/jobs-backup.env`, which does not
exist — so backups would run local-disk-only, tolerated silently by the `-` prefix in the unit.

**No verified restore has ever been performed.** The backup script and its verify timer are
written and have never run.

**How to do it.** In order:

```bash
# 1. binary, account, tunnel
cloudflared tunnel login
cloudflared tunnel create jobs
#    then fill the placeholders in deploy/cloudflared/config.yml

# 2. backups: create ~/.config/jobs-backup.env with an OFF-MACHINE destination
# 3. the part everyone skips -- restore into a scratch database and diff row counts
```

**Do the restore.** A backup that has never been restored is a belief, not a backup.

**What it unblocks:** everything a Builder can reach, `OQ-14`, and `OQ-11`.

**Done when:** the tunnel resolves from off-network, and you have restored a dump into a scratch
database and compared row counts against production.

---

### OQ-11 — Is `SESSION_COOKIE_SECURE` true in the deployed `.env`?

**Why it is yours:** machine. Nobody but you can read that file.

**What:** The session cookie is the client's **only** credential (`backend/webapp/auth.py:420`).
If `SESSION_COOKIE_SECURE` is false anywhere but local plain HTTP, it travels in the clear.

**How to do it.** Read `backend/webapp/.env` on the deployed box. If it is false and the box is
reachable over anything but localhost, set it true and restart the webapp. Check it again after
`OQ-4b`, because that is the moment it starts mattering.

**Done when:** confirmed true in the deployed environment, or confirmed the deployment is
localhost-only and written down as such.

---

### OQ-12 — Has any contributor API key ever been minted and handed to a person?

**Why it is yours:** you are the only one who would know. `api_keys` is empty in this database;
a key minted elsewhere would not show up here.

**How to do it.**

```bash
cd backend/api && .venv/bin/python manage_users.py list
```

If one was ever issued off this machine, revoke it unless you know who holds it:

```bash
.venv/bin/python manage_users.py revoke <key_hash_prefix>
```

**What it unblocks:** `OQ-1` — if the answer is "yes, and people are using it", retiring `api/`
is a migration rather than a deletion.

**Done when:** answered yes or no, and written into `OQ-1`.

---

### OQ-13 — Registrations that block work: Adzuna, USAJobs, Firecrawl

**Why it is yours:** account. Each is a signup you have to do.

**What:** Task 15 has **no commit and no code at all** — it is blocked on an Adzuna
`app_id`/`app_key`. `backend/tools/ats-discover.py:55-60` documents the seam and says so:
`adzuna_top_companies()` is stubbed, and filling it in flows employers into `ats_seed` with no
other change. Firecrawl blocks task 20.

**How to do it.** Register for each, put the credentials in `backend/.env`, and hand tasks 15
and 20 to a session. Adzuna is free for low volume; check USAJobs' terms before relying on it.

**Done when:** the keys are in `backend/.env` and the stub is no longer a stub.

---

### OQ-14 — The phone test

**Why it is yours:** device, plus a registration that is not in this repo.

**What:** A physical phone, plus a Google Cloud Console redirect-URI registration. The frontend
has never been exercised on a phone.

**How to do it.** Needs `OQ-4b` first — the client uses `credentials: "same-origin"` with
`BASE = ""`, so it must be served from the webapp's own origin or every request silently loses
the session cookie and renders as the sign-in screen with no error anywhere. Add the tunnel
hostname as an authorised redirect URI in Google Cloud Console, then load it on the phone.

**Done when:** sign-in completes on a phone and the Today screen renders.

---

### OQ-6 — `D31` needs a decision, not a fix

**Why it is yours:** decision. **Likely already answered — verify before working it.** `4d6f7aa`
(2026-08-02) is titled *"D31 decided"* and reads as closed; this row survives only because the
register tracking it was deleted before the row was struck. Confirm and close it.

---

## Closed — kept so citations resolve

| # | what it was | outcome |
|---|---|---|
| ~~OQ-7~~ | The live database was missing task 25's five search objects and `cohort_signal`'s GRANT | **Closed 2026-08-02.** `init-schema` created them; the seven GRANTs were issued by hand. The lesson worth keeping: this row read as a nicety for a day **while the whole webapp was down** — `verify_schema()` raised in the lifespan and the process exited. Nobody had started it |

---

## What is not on this list, and why

**Session-doable work is not here. It is in [`TASKS.md`](TASKS.md)**, which owns `T-` the way this
file owns `OQ-` — the toolchain rows, the harness, and the § 4a defects. Do not move them here;
this file is what only you can do. Between the two, that is meant to be the whole list.

**Tranche nine is 4½ of 7 done.** The gap is why this file did not exist until now:

| task | what | state |
|---|---|---|
| 48 | stop the refactor at a known-green state | done (`5cca001`) |
| 49 | orientation from code | done — produced `docs/STATE-OF-THE-SYSTEM.md` |
| 50 | extract the durable core | done (`5046f98`) |
| 51 | archive the rest | done, **but not the way its spec said** — see below |
| 52 | build the harness | **not started.** `~/.claude/skills/` does not exist. Rewritten as [`TASK-52-harness.md`](TASK-52-harness.md) |
| 53 | owner queue and changelog | **Part A only — this file.** Part B, the `whatsnew` check, is `T-9` |
| 54 | replan the product | **superseded.** It was a task to write a plan; [`TASKS.md`](TASKS.md) is the plan |

**51 deviated from its spec and nobody wrote it down.** Its tranche README — `git show
refactor-freeze-2026-08-02:docs/tasks/refactor/tranche_nine/README.md` — said *"Not delete
anything. 51 is `git mv` and stubs."* `5046f98` deleted 137 and left none; `c052f23`, `20ee7d0`
and `47dd212` are the bill. Now recorded — `docs/adr/0002-task-51-deleted-instead-of-git-mv.md`.

**`OQ-3` is still the one to do first, and `TASKS.md` does not change that.** The scoring
redesign completed 2026-07-28 and has never been validated — GATE 1 came in at 16/20 and 10/20
against a definition of done asking 20/20, and GATE 4 has never been attempted. `OQ-3` is that
gate. Every row in `TASKS.md` improves a system nobody has confirmed works.

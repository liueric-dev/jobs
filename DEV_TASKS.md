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

**This file owns the prefix `OQ-`.** One allocator. **The next free number is `OQ-18`.**
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
| **30 minutes** | `OQ-4a` — three systemd timers left (`jobs-backup`, `jobs-backup-verify`, `jobs-volume-digest`); the tunnel and webapp/API units are live |
| **an evening** | `OQ-4b` — the tunnel is live; what's left is an off-machine backup destination and one verified restore |
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

---

### OQ-1 — `backend/api/` stays; who issues a contributor credential is still open

**Why it is yours:** decision, and it is a product call rather than a technical one. **The parent
question is answered as of 2026-08-03: the crowdsourcing service stays.** `deploy/systemd/
jobs-api.service`'s deprecation marking is therefore stale and should not be acted on as written.
The credential-issuance sub-question is deliberately still open — owner's words: "I don't know
what the current plan for implementation is. It may change" — so this row is not closeable by
picking one of `DEC-84`'s three options today; it would be answering a question that is not yet
stable enough to answer.

**What:** `api/` is the crowdsourcing service — volunteers run a worker script on their own
machine with their own SerpApi account, claim queries from this server's priority queue, and
submit raw results back, so nobody but the operator ever touches Postgres (`backend/api/
app.py`'s module docstring, `backend/api/README.md`). It is unrelated to labelling. `OQ-12`
(closed 2026-08-03) found zero contributors have ever been onboarded, so there is no live
credential to migrate — whatever mechanism gets picked, it is greenfield, not a cutover.

**How to do it, once the implementation plan firms up.** Pick one of `DEC-84`'s three options for
issuing a credential:

1. Grant `jobs_web` INSERT on `jobs_api`'s tables — simplest, weakest isolation.
2. A server-to-server mint — most work, cleanest boundary.
3. A request queue you service by hand — no code, does not scale, fine for ~30 Builders.

```bash
# what exists today
backend/api/manage_users.py list          # contributors and keys
backend/api/manage_users.py create        # mint a contributor + API key
```

**`OQ-12`, closed 2026-08-03: no contributor API key has ever been minted or handed to anyone.**
Whatever mechanism eventually gets picked here has zero existing users to migrate.

**Done when:** the implementation plan for `api/` firms up and task 24 has a chosen credential
path written into `DEC-84`. Not blocked on anything except that plan existing.

---

---

---

### OQ-5 — Apply the `revenue_commercial` archetype, once round 2 closes

**Why it is yours:** decision, and it is partly a one-way door. **Decided 2026-08-03, staged
rather than applied** — this is now a timing row, not an open question.

**What:** Proposed in `DEC-64`/`DEC-65`, apply it. Checked before touching anything, per this
row's own "weigh how many that is before deciding": `python3 -m evals label status` shows **all
271 labels collected so far (2 labellers) are unrecorded provenance** — every one predates
`DEC-95`'s facts_version-stamping fix, so none of them would survive a re-extraction. `job_facts`
is keyed on `job_id` alone (`backend/schema.py`), with no version history, so a bump now would
silently overwrite the exact facts every current label was formed against, on the corpus round
`OQ-3` calls the single highest-priority item in this whole file (due ~2026-08-09).

**How to do it, once round 2 closes:**

1. Add `"revenue_commercial"` to `extract.ARCHETYPE` (27th value).
2. Bump `schema.FACTS_VERSION` 3 → 4 (both vocabularies interpolate into `extract._INSTRUCTIONS`,
   whose own comment asks for a bump on exactly this kind of change).
3. Price it in both criteria files — **already decided and staged as a `_comment` in each,
   so this step is transcription, not re-deriving**: `config/criteria.json` → **-30** (the
   `marketing_ops`/`pm` tier — non-technical commercial/GTM work, off the author's SWE target);
   `config/pursuit-criteria.json` → **10** (the `solutions`/`it_internal`/`business_systems`
   bridge tier — 63% of the pursuit `other` rows that got a `role_track` at all landed on
   `business_operations` or `revenue_operations`, so this is a plausible entry-level reach).
4. Bump the count at `tests/test_extract.py`'s ARCHETYPE-length assertion, 26 → 27.
5. Consider adding one disambiguating clause to `_INSTRUCTIONS` for the `revenue_commercial` vs
   `solutions` overlap (pre-sales solutions architecture reads as either) — the same tension
   `implementation_analyst` already carries against `forward_deployed`/`solutions`.
6. Let the next nightly run re-extract, or run `extract.py` by hand. Not a cost question —
   task 12 measured a full re-extraction at 863 calls / ~28 min / ~\$0.33.

**What it unblocks:** `role_archetype = other` stops being a catch-all for commercial/GTM work.

**Done when:** round 2 closes, the five steps above land together in one change, and the two
staged `_comment`s are replaced by real `archetypes` entries.

---

### OQ-17 — The archetype/track vocabularies read tech-leaning; review after round 2

**Why it is yours:** decision, and a genuinely bigger one than OQ-5 — this is a request to
re-examine the whole superset, not just add one value.

**What:** Flagged 2026-08-03 alongside OQ-5. Both vocabularies say this about themselves
already: `extract.ROLE_TRACK`'s own comment calls its nine values "PROVISIONAL" and derived
from "a pre-Phase-3 corpus" that is "overwhelmingly software companies and ATS-clean postings,"
and `config/pursuit-criteria.json`'s `_archetypes_other_comment` says the 26-value `ARCHETYPE`
superset was "derived from a tech-heavy corpus" and that 44% of the actual cohort corpus —
entry-level, all-industry, NYC — goes unnamed by it. So the "options lean toward tech" read is
not a misimpression; it is a documented, load-bearing caveat in the code, not yet acted on.

**How to do it.** `backend/tools/derive-role-tracks.py` exists precisely to re-run this
derivation, and its own task file (deleted, behind `refactor-freeze-2026-08-02`) sequenced the
re-run for **after Phase 3** adds non-tech sourcing — which has not landed yet. Re-running it
today would re-derive a vocabulary from the same tech-heavy corpus that produced the one being
questioned. Before spending a session on this: (1) check whether Phase 3 sourcing has landed
enough non-tech employers to change the corpus mix meaningfully, (2) if not, this is a
re-derivation to schedule after that lands, not before; (3) if it has, re-run
`derive-role-tracks.py --archetypes --tracks` and read the result against the same
employer-spread discipline `git show refactor-freeze-2026-08-02:docs/role-track-derivation.md`
used (read `emp` first — a
candidate whose mass sits at one employer is that employer's hiring spree, not a vocabulary
gap).

**What it unblocks:** a vocabulary that describes the all-industry NYC cohort this pipeline
now serves, rather than the original SWE-focused, tech-heavy corpus it was derived from.

**Done when:** either Phase 3 sourcing is confirmed to have landed and the re-derivation is
run and reviewed, or this row is struck with the reason it is still premature.

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

---

### OQ-4a — Install the eleven absent systemd units

**Why it is yours:** machine. No account needed — this one is just a terminal. **Ten of the
fourteen units are now live as of 2026-08-04** — three remain, below.

**`jobs-volume-check.timer` is installed and enabled** (since 2026-08-03), and **`cloudflared.service`,
`jobs-api.service` and `jobs-webapp.service` are now installed, enabled, and `active (running)`**
(confirmed 2026-08-04 — `systemctl --user status` on all three, tunnel accepting real traffic
since 01:49 EDT). `python3 tools/volume-check.py` still runs clean at exit 0. **Still open, and
not closeable today:** the "Done when" below needs a few days of nightly history to accrue before
the check reports a real comparison instead of `insufficient history` on every source — that part
is a clock, not a task.

**Three of the fourteen `deploy/systemd/` units remain uninstalled**: `jobs-backup.timer`,
`jobs-backup-verify.timer`, `jobs-volume-digest.timer` (confirmed absent from
`systemctl --user list-timers --all` 2026-08-04). `jobs-backup.service` also has no off-machine
destination yet (see `OQ-4b`), so installing its timer now would only ever produce a local-disk
copy. Diff each against its repo copy before installing if this row is picked up again:

```bash
systemctl --user list-unit-files | grep jobs     # what is live now: 10 of 14
ls deploy/systemd/                               # what exists: 14
diff ~/.config/systemd/user/jobs-ingest.service deploy/systemd/jobs-ingest.service
```

**Done when:** after a few nightly runs, `python3 tools/volume-check.py` reports a comparison
rather than `insufficient history` on every source, and the three remaining timers are installed.

---

### OQ-4b — The account half of deployment, and one verified restore

**Why it is yours:** account. `DEC-91` already took the Cloudflare-vs-Tailscale call and `DEC-92`
took the stays-on-the-home-box call, so nothing here is a decision any more — it is purely
account access and a person at a terminal. **The tunnel half is done; the backup half is not.**

**Done, confirmed 2026-08-04:** the Cloudflare account, domain, tunnel (`726fa841-8945-4e06-bb06-
f241cbbe30dc`), and `cloudflared` binary (`/usr/local/bin/cloudflared` now a symlink to
`/usr/bin/cloudflared`) all exist. `deploy/cloudflared/config.yml`'s placeholders are filled in.
`curl https://jobs.etotheric.com/v1/health` returns `{"ok":true}` from off-network, and a real
Google sign-in was completed through the public URL the same day (see `OQ-11`, closed).

**Still open:** `~/.config/jobs-backup.env` still does not exist, so `jobs-backup.timer` /
`jobs-backup-verify.timer` are not installed (`OQ-4a`) and backups, if run manually, would be
local-disk-only, tolerated silently by the `-` prefix in the unit. **No verified restore has ever
been performed** — the backup script and its verify timer are written and have never run.

**How to do it.** What's left, in order:

```bash
# 1. backups: create ~/.config/jobs-backup.env with an OFF-MACHINE destination
# 2. install jobs-backup.timer and jobs-backup-verify.timer (OQ-4a)
# 3. the part everyone skips -- restore into a scratch database and diff row counts
```

**Do the restore.** A backup that has never been restored is a belief, not a backup.

**What it unblocks:** `OQ-14` (the tunnel half it needed is already done).

**Done when:** you have restored a dump into a scratch database and compared row counts against
production.

---

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

## Closed — kept so citations resolve

| # | what it was | outcome |
|---|---|---|
| ~~OQ-7~~ | The live database was missing task 25's five search objects and `cohort_signal`'s GRANT | **Closed 2026-08-02.** `init-schema` created them; the seven GRANTs were issued by hand. The lesson worth keeping: this row read as a nicety for a day **while the whole webapp was down** — `verify_schema()` raised in the lifespan and the process exited. Nobody had started it |
| ~~OQ-6~~ | `D31` (urlopen call sites bypassing `lib.http`'s retries) needed an owner decision, not a fix | **Closed 2026-08-03 — confirmed already decided.** `4d6f7aa` (2026-08-02), *"D31 decided — three of four urlopen sites reach lib.http, and one must not"*, resolved it: `fetch_feed`, `fetch_page` and `serpapi_search` now go through `lib.http`; `builtin-nyc.fetch_description` stays on raw `urllib.request.urlopen` deliberately, because `lib.http`'s retry-on-429 schedule would spend four extra requests before `RateLimited` could abandon the detail pass. This row only survived because the register tracking `D31` was deleted in the 2026-08-02 purge before the row was struck there too |
| ~~OQ-9~~ | Two n=115 selfchecks, five days apart, disagreed by up to 9.6 points with no supersession marker on either | **Closed 2026-08-03.** Owner picked option 3: both as a range, act on the lower bound. Both `evals/fixtures/results/selfcheck-n120-*.json` files now carry a `_comment` recording this; `docs/STATE-OF-THE-SYSTEM.md` § 6 and `.claude/CLAUDE.md`'s landmine paragraph state the decision and the per-field floors instead of presenting both as open |
| ~~OQ-2~~ | The 24h impression dedup was keyed `(profile, job_id)`, so one Builder's render suppressed thirty Builders' impressions of the same jobs | **Closed 2026-08-03.** Owner picked option 1: `(app_user_id, job_id)`. `backend/webapp/jobs.py`'s `record_events` NOT EXISTS predicate now binds `prior.app_user_id` instead of `prior.profile`; the existing `idx_job_events_user_job` partial index already served it, so no schema change was needed. Existing rows are not backfilled. Two new replay tests in `tests/test_event_replay.py` (`TestSkipReplay`) cover both directions — a second Builder's impression is no longer deduped by the first, and the same Builder's re-render still is. Full webapp suite (354 tests) green |
| ~~OQ-8~~ | `score.TRACKS`'s five-value enum "does not describe this population" (persona `_comment`); task 30's display half needed a browsable vocabulary | **Closed 2026-08-03.** These are two different "track" concepts, not one. `score.TRACKS` is the narrative LLM call's per-profile vocabulary, two of whose five values ("Re-Entry & Growth", "Poor Fit") are fit judgments rather than job families — renaming it for Pursuit would be exactly the invented narrowness the persona `_comment` warns against, and it's dead code for this profile anyway (`daily_narrative_budget` is 0). `extract.ROLE_TRACK` is the separate, per-job, already-live nine-slug vocabulary task 11 built for this purpose, with hand-written plain-language copy already in `config/search-queries.json`. Decision: task 30's display half ships with `ROLE_TRACK`; `score.TRACKS` is left as-is. Recorded in `score.py`'s `TRACKS` comment and the persona's `_no_buckets_comment` |
| ~~OQ-16~~ | Whether the `kind: record` carve-out (one document allowed to claim frozen history rather than current state) stays | **Closed 2026-08-03 — carve-out removed, option 2.** The last `kind: record` handoff document is deleted, recoverable at `git show refactor-freeze-2026-08-02:backend/docs/HANDOFF-multimachine-google-jobs.md`. Its still-live facts moved before deletion rather than being lost with it: the multi-machine shared-budget bug it found moved to `backend/README.md`'s locking section, and its Step 3 (a dry-run-verified id migration for `google_jobs` rows, checked today and confirmed **still unapplied 9 days later**) became `TASKS.md`'s `T-20` — a genuinely live finding this closure surfaced, not mere history. The rest was already duplicated in code comments (`lib/ids.py`). Rule is now unqualified: only the three `kind: contract` files may claim current state, no exceptions |
| ~~OQ-12~~ | Whether any contributor API key has ever been minted and handed to a person | **Closed 2026-08-03. No.** Owner confirmed none were generated; `cd backend/api && .venv/bin/python manage_users.py list` (with `api/.env` exported into the shell) returns `no contributors yet` — `api_keys` is empty. Written into `OQ-1`: retiring `api/` would be a deletion, not a migration, if that is the direction chosen |
| ~~OQ-11~~ | Is `SESSION_COOKIE_SECURE` true in the deployed `.env`? | **Closed 2026-08-04. Yes.** `backend/webapp/.env` has `SESSION_COOKIE_SECURE=true`, and the deployment is no longer localhost-only — the Cloudflare tunnel (`OQ-4b`) went live the same day, with a real Google sign-in completed through the public URL |

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

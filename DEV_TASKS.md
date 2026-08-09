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

T-47 tried that on 2026-08-08 and could not: 711 pruned to 534, and filing the finding as OQ-34
put it at 565. The shortfall is the row's own finding, not an unfinished job. Nothing could be
moved out -- an open row is an unsettled question by definition, so docs/adr/ cannot hold one,
T-43's freeze question was unanswered then, and .claude/CLAUDE.md rules out a third file -- so only
prose could go, and it did. No row, no open question, no option in a decision, no date and no
file:line was dropped; the citation set was diffed before and after to prove it. What is left is
options and "why a session cannot answer this", which is what the budget exists to protect rather
than trim. OQ-34 carries the three ways out. Everything cut is in git at 9a05925.
-->


# Dev tasks — everything that is on the owner

**This file owns the prefix `OQ-`.** One allocator. **The next free number is `OQ-38`.** Numbers are
never reused and never renumbered; `OQ-7` is closed and stays in the table so citations resolve.

**Every row here needs you.** A session cannot start any of them: each needs a machine, an account,
a device, other people, or a decision only you can take — the critical path, and the least visible
thing in the repo. Session-doable work is not here; it is in [`TASKS.md`](TASKS.md), which owns
`T-`. Do not move rows between the two; between them, that is meant to be the whole list. This is
Part A of `git show
refactor-freeze-2026-08-02:docs/tasks/refactor/tranche_nine/53-owner-queue-and-changelog.md`, which
specified it under `docs/` as OWNER-QUEUE.md; Part B was never built and is `T-9` now.

**How to use it.** Sort on *Why it is yours*: `decision` rows are free and unblock work immediately,
`account` and `device` rows cost money or a signup, and `people` rows have a lead time you cannot
compress — so start those first even though they finish last. **Do not restate these rows
elsewhere**; link here. When a row closes, strike it and keep it.

**Start `OQ-3` today**, for the lead time alone. **It does not gate shipping:** the 2026-07-28
scoring redesign has never been validated — GATE 1 came in at 16/20 and 10/20 against a definition
of done asking 20/20, GATE 4 has never been attempted — but `score_job()` is pure, reads no label
table, and the frontend has been showing its output throughout. Every row in both files improves a
system that already works, not one waiting to be unblocked.

---

## Open

### OQ-37 — `jobs-api` will not restart until `init-schema` runs, and it is running now

**WIDENED 2026-08-09 BY `T-35`, AND THE SECOND HALF IS NOT THE SAME KIND OF THING AS THE FIRST.**
`T-34` added three columns; `T-35` added a whole table, `public.contributor_status`, and put it in
`qc.REQUIRED_TABLES` — so the next restart now checks for a table as well as for three columns, and
`verify_schema()` checks **privileges** on a table, not just its existence. `init-schema` creates it
and **issues no GRANT** — that is
[`0004`](docs/adr/0004-provision-database-issues-no-grants.md), stated in
`tools/provision-database.py`'s own "WHAT IT DOES NOT DO: GRANTS". So route (a) alone leaves the
service refusing to start with `public.contributor_status: no SELECT, INSERT, UPDATE`, which reads
like a bug and is the documented behaviour. **The GRANT is a separate statement somebody has to
run**, and it is the first new one this service has needed since `search_queries`.

**Why it is yours:** a DDL run against the live database while `jobs-api` is serving it, not a
missing credential. **The first version of this row said the credential was missing and that was
under-checked:** `JOBS_ADMIN_DATABASE_URL` is indeed absent from `backend/api/.env`, so
`manage_users.py` falls back to the restricted `jobs_api` URL and the ALTER fails with permission
denied — but `public.contributors` is owned by **`jobs_pipeline`**, which is the role in
`backend/.env`'s own `DATABASE_URL`. The exact `ADD COLUMN` was dry-run on that credential against
the live database on 2026-08-09 and rolled back; it succeeds. So what is yours is the decision, not
the access.

**What:** `T-34` added three columns to `contributors` and to
`query_claims.REQUIRED_COLUMNS`, and `verify_schema()` runs in the FastAPI lifespan. The live
`public.contributors` has `id`/`name`/`created_at`/`notes` and nothing else (read off the deployed
`jobs` database on the pipeline credential, 2026-08-09; the table is empty, 0 rows). So the
**currently running** `jobs-api.service` — active on `127.0.0.1:8420`, `/v1/health` answering, and
started before this change — keeps working, and **the next restart of it fails to start**.

**THE UNIT IS USER-SCOPED AND THIS ROW SAID `sudo`, CORRECTED 2026-08-09 WHILE CLOSING `T-35`.**
There is no system-level `jobs-api.service` at all — `systemctl cat jobs-api.service` answers "No
files found", while `systemctl --user show` gives
`/home/eric/.config/systemd/user/jobs-api.service`, active since **2026-08-04 01:49:51 EDT** and
serving `127.0.0.1:8420` from `backend/api/.venv/bin/uvicorn`. `deploy/README.md:92` had it right
(`systemctl --user enable --now`); this row was the one place in the tree that did not, and
`sudo systemctl restart jobs-api` fails with "Unit jobs-api.service not found" — at the one moment
the service is refusing to start, which is the worst moment to be debugging the wrong command.

**The live schema was re-read on the pipeline credential 2026-08-09, and both halves still hold:**
`public.contributors` has `id`/`name`/`created_at`/`notes` and **0 rows**;
`public.contributor_status` **does not exist**; `jobs_api` holds `SELECT, INSERT` on `contributors`
and no UPDATE. So nothing has drifted since `T-34` wrote this, and the restart is still blocked.

**This is `OQ-7` again, and that row is the reason to file this rather than mention it.** There, the
whole webapp was down for a day because `verify_schema()` raised in the lifespan, the process
exited, and nobody had started it. The refusal is the designed behaviour — the alternative is a
service that starts cleanly and 500s on every claim — but it is a deploy step, and a deploy step
nobody performed is what `OQ-7` cost.

**Two routes, and they are not equivalent — pick deliberately.** `init-schema` runs
`qc.ensure_schema()`, which calls `schema.ensure_schema()` and therefore also brings the app view
and the foreign-key cascade repair (`backend/api/query_claims.py:354-358` says so outright). That is
the documented, idempotent path and the one the docstring intends; it is also more than three
columns, against a database a live webapp reads, and `.claude/CLAUDE.md`'s standing warning about
view-DROP-and-GRANT-loss is next door to it ([`docs/adr/0004`](docs/adr/0004-provision-database-issues-no-grants.md)).
The narrow route issues only what `T-34` added and touches nothing else.

```bash
# route (a) -- the documented one, and more than these three columns
cd backend/api
JOBS_ADMIN_DATABASE_URL="$(grep ^DATABASE_URL= ../.env | cut -d= -f2-)" \
  .venv/bin/python manage_users.py init-schema

# route (b) -- only what T-34 added; same statements add_missing_columns issues
#   ALTER TABLE contributors ADD COLUMN IF NOT EXISTS paused BOOLEAN;
#   ALTER TABLE contributors ADD COLUMN IF NOT EXISTS daily_cap INTEGER;
#   ALTER TABLE contributors ADD COLUMN IF NOT EXISTS reserve_floor INTEGER;
#   -- and T-35's table, which `ensure_schema` creates on either route:
#   CREATE TABLE IF NOT EXISTS contributor_status (
#       contributor_id TEXT PRIMARY KEY REFERENCES contributors(id),
#       last_check_in_at TEXT NOT NULL, worker_version TEXT,
#       quota_remaining INTEGER, quota_reported_at TEXT,
#       last_error TEXT, last_error_at TEXT);

# EITHER ROUTE THEN NEEDS THIS, and neither issues it (docs/adr/0004).
# On the owner role, not on jobs_api -- a role cannot grant itself anything.
#   GRANT SELECT, INSERT, UPDATE ON contributor_status TO jobs_api;

# Read back what the service will check, BEFORE restarting it. This is the
# same list verify_schema() reads, run against the live database from a
# process that is not the service:
cd backend/api && .venv/bin/python -c "
import psycopg, query_claims as qc
with psycopg.connect(qc.DATABASE_URL) as c:
    c.execute('SET search_path TO public'); qc.verify_schema(c); print('ready')"

systemctl --user restart jobs-api && curl -s localhost:8420/v1/health
```

**Done when:** `paused`, `daily_cap` and `reserve_floor` exist on `public.contributors`,
`public.contributor_status` exists **and `jobs_api` holds SELECT/INSERT/UPDATE on it**, the
`verify_schema()` read-back above prints `ready` **before** anything is restarted,
`jobs-api.service` has been restarted deliberately rather than discovered down, and `/v1/health`
answers after it. **One GRANT changes, and only one** — `contributors` still gains no UPDATE, which
is the property `T-34` refused to give up and the reason `T-35` built a second table rather than
three more columns.

---

### OQ-3 — More labellers on the same ten overlap rows, and round 2

**Why it is yours:** people. Longest lead time here; start it today even though it finishes last.
**Deferred past the MVP deliberately, 2026-08-04** — easier to recruit once people see the app work.

**What:** Round 2 is due around 2026-08-09 and needs ≥100 distinct postings from ≥5 labellers.
Today: 2 labellers, 36 postings, **10 rows of overlap**. More *postings* do nothing — 25 of the 36
carry a single labeller and add exactly zero to the ceiling; what is needed is **more people
labelling the same ten rows**. Recruiting can widen past the cohort: the access gate
(`backend/webapp/manage_app_users.py add`) is an allowlist by email, not a cohort check. Progress:
`cd backend && python3 -m evals label status`. It unblocks task 13's weights, task 12's next
`FACTS_VERSION` bump, `OQ-5` and GATE 4, and un-denominates every model-vs-human figure in the repo.

**Done when:** `evals label status` shows ≥5 labellers on the overlap set, and the recomputed human
ceiling sits **above** the model floor on at least the fields it currently sits below.

### OQ-5 — Apply the `revenue_commercial` archetype, once round 2 closes

**Why it is yours:** decision, partly a one-way door. **Decided 2026-08-03, staged rather than
applied** — a timing row now, not an open question.

**What:** Proposed in `DEC-64`/`DEC-65`. `evals label status` shows **all 271 labels collected so far
(2 labellers) are unrecorded provenance**, every one predating `DEC-95`'s facts_version-stamping fix,
so none would survive a re-extraction; `job_facts` is keyed on `job_id` alone (`backend/schema.py`)
with no version history, so bumping now silently overwrites the exact facts every current label was
formed against, on the corpus `OQ-3` relabels ~2026-08-09.

**How to do it, once round 2 closes** — six steps, landing together in one change:

1. Add `"revenue_commercial"` to `extract.ARCHETYPE` (27th value); `role_archetype = other` stops
   being a catch-all for commercial/GTM work.
2. Bump `schema.FACTS_VERSION` 3 → 4 — both vocabularies interpolate into `extract._INSTRUCTIONS`,
   whose comment asks for a bump on exactly this change.
3. Price it in both files — **staged as a `_comment` in each, so this is transcription**:
   `config/criteria.json` → **-30** (the `marketing_ops`/`pm` tier, off the author's SWE target);
   `config/pursuit-criteria.json` → **10** (the `solutions`/`it_internal`/`business_systems` bridge
   tier — 63% of pursuit `other` rows with a `role_track` landed on `business_operations` or
   `revenue_operations`).
4. Bump `tests/test_extract.py`'s ARCHETYPE-length assertion, 26 → 27.
5. Consider a disambiguating clause in `_INSTRUCTIONS` for `revenue_commercial` vs `solutions`
   (pre-sales solutions architecture reads as either).
6. Re-extract nightly or by hand — task 12 measured a full re-extraction at 863 calls / ~28 min /
   ~\$0.33, so this is not a cost question.

**Done when:** round 2 closes, the six steps land together, and the two staged `_comment`s become
real `archetypes` entries.

### OQ-17 — The archetype/track vocabularies read tech-leaning; review after round 2

**Why it is yours:** decision, and bigger than `OQ-5` — it asks to re-examine the whole superset, not
to add one value. Flagged 2026-08-03 alongside it.

**What:** Both vocabularies say it about themselves already. `extract.ROLE_TRACK`'s comment calls its
nine values "PROVISIONAL" and derived from "a pre-Phase-3 corpus" that is "overwhelmingly software
companies and ATS-clean postings"; `config/pursuit-criteria.json`'s `_archetypes_other_comment` says
the 26-value `ARCHETYPE` superset was "derived from a tech-heavy corpus" and that 44% of the actual
cohort corpus goes unnamed by it. A documented, load-bearing caveat in the code, not a misimpression.

**How to do it.** `backend/tools/derive-role-tracks.py` re-runs the derivation, but its own task file
(deleted, behind `refactor-freeze-2026-08-02`) sequenced that for **after Phase 3** adds non-tech
sourcing, which has not landed — re-running today re-derives the vocabulary from the same corpus that
produced the one being questioned. So: check whether Phase 3 has moved the corpus mix; if not,
schedule this after it lands; if it has, run `derive-role-tracks.py --archetypes --tracks` and read
the result against the employer-spread discipline `git show
refactor-freeze-2026-08-02:docs/role-track-derivation.md` used — read `emp` first, because a
candidate whose mass sits at one employer is that employer's hiring spree, not a vocabulary gap.

**Done when:** either Phase 3 sourcing is confirmed landed and the re-derivation is run and reviewed,
or this row is struck with the reason it is still premature.

### OQ-4a — One clock left, nothing to do but wait

**Why it is yours:** machine — but as of 2026-08-04 there is nothing left to type. All 13 tracked
units are installed and enabled, `systemctl --user list-unit-files 'jobs-*'` shows no `bad` entries,
and `jobs-backup.timer`/`jobs-backup-verify.timer` joined once `OQ-4b`'s off-machine destination
existed to make them meaningful.

**`jobs-volume-digest.timer`/`.service` were deleted and are fully un-installed.** Decided
2026-08-04: a weekly Telegram report nobody reads is the kind of alert that trains a channel to be
ignored — the failure mode that unit's own comment warned about for its sibling alarm, one level up.
`backend/tools/volume-check.py --digest` remains for a manual check-in; only the automation is gone.

**Not closeable today, and not yours to fix:** `volume-check.py` needs a few days of nightly history
before it reports a real comparison. That is a clock, not a task.

**Done when:** `python3 tools/volume-check.py` reports a comparison rather than
`insufficient history` on every source.

### OQ-13 — Registrations that block work: Adzuna, USAJobs, Firecrawl

**Why it is yours:** account. Each is a signup you have to do. **Re-checked 2026-08-04: Firecrawl is
already registered**, so only Adzuna and USAJobs remain open.

**What:** Task 15 has **no commit and no code at all** — it is blocked on an Adzuna
`app_id`/`app_key`. `backend/tools/ats-discover.py:55-60` documents the seam and says so:
`adzuna_top_companies()` is stubbed, and filling it in flows employers into `ats_seed` with no other
change. Firecrawl blocks task 20 — but **`FIRECRAWL_API_KEY` is already set in
`backend/webapp/.env`** (populated, `fc-…` prefix, present since 2026-08-04's deploy). Nothing reads
it yet, and it sits in `webapp/.env` rather than `backend/.env`, so whoever picks up task 20 should
confirm that is the right process for it before writing code.

**Done when:** the Adzuna and USAJobs keys are registered and in `backend/.env` — Adzuna is free for
low volume, and check USAJobs' terms before relying on it — and the stubs are no longer stubs.

### OQ-18 — The personal scoring layer's own validation plan is blocked by a rule this repo chose on purpose

**Why it is yours:** decision. Both available answers are defensible and the code cannot pick.

**What:** The plan was to score the same postings with a hand-authored personal persona and with the
cohort's, and compare both against your own Axis B labels. **That comparison cannot be printed today,
and the refusal is deliberate rather than a missing feature.** `evals label report`
(`backend/evals/__main__.py:653-655`) is the only model-vs-human command and it exits 2 while there
is one labeller, because *"model-vs-human is uninterpretable without a floor and a ceiling beside
it"* (`backend/evals/labels.py:39-45`). There is deliberately no `--force`, and
`backend/tools/label-findings.py:25-35` says it is not a way around that. The ceiling needs a second
labeller — `OQ-3`. `n=1` is a property of the situation, not a flaw in the plan.

**How to do it.** Name one of three. (1) **A paired comparison rather than an agreement rate** — not
the per-item accuracy the guard is about, and `labels.ordering()` (`backend/evals/labels.py:2479`)
and `labels.recall_bound()` (`backend/evals/labels.py:2418`) are both axis-B aware and neither is an
agreement rate. (2) **Wait for `OQ-3`** — correct and slow. (3) **Build it unvalidated and say so** —
it annotates and never orders, so a bad narrative costs a Builder words, not a ranking. `T-22` is
independent either way.

**Done when:** one of the three is chosen and written into an ADR under `docs/adr/`, since it either
reverses or ratifies a documented position.

### OQ-19 — Cohort narratives went live on 2026-08-05; does a personal one replace them or sit beside them?

**Why it is yours:** decision. Its funding half answered itself while these rows were being written.

**What:** This row was drafted claiming the `pursuit` cohort's `daily_narrative_budget` was zero, so
no Builder had ever seen a `gap_bridging_angle`. **That was false within hours of being written, and
the code still says it.** The live `profiles` row carries a budget of **200**, changed 2026-08-05,
and `job_scores` holds 178 `pursuit` rows with a populated `gap_bridging_angle`, scored that night
against `deepseek-v4-flash`. So the display question is the whole question: show both, labelled — one
is what the cohort sees, one is yours, and the two disagreeing is honest — or replace the cohort one
in place. The first is more honest and busier; the second is cleaner and hides a disagreement the
Builder might want to see. One constraint either way: `frontend/js/ui.mjs:13` — *"NO SCORE, ANYWHERE.
Not match_score, not fit_score."* A personal **narrative** is in scope; a personal **score** is not.
**Look at one on a phone first** — nobody has seen a real `gap_bridging_angle` render, and its length
decides whether two fit on one screen.

**Done when:** replace-in-place or side-by-side is chosen, having looked at a real rendered narrative
first, and `TASKS.md`'s `T-24` has corrected the three places in the code that still say this budget
is zero.

### OQ-20 — `localStorage` is plaintext, and this cohort may be sharing devices

**Why it is yours:** decision, about people you know and this codebase does not.

**What:** The personal layer runs in the Builder's browser on the Builder's own API key, which has to
be stored somewhere. `localStorage` is the only real option in a client with no build step, and
anything else running in that browser profile can read it — including the next person to use that
computer. The earlier framing had the Builder's exposure running to their LLM provider rather than to
the operator, which is true and incomplete: **the third party that matters here is whoever else uses
that browser.** The client stores **nothing** in web storage today — that grep is empty, and all
state rides the session cookie on the webapp's own origin (`frontend/js/api.mjs:27`).

**How to do it.** Answer one question: do Builders in this cohort share machines — a lab, a library,
a family computer? If yes, the options are session-only storage (re-paste each visit: annoying, safe)
or no stored key at all. If no, `localStorage` plus a plain warning is proportionate. Does not block
`T-22`.

**Done when:** the answer is known from the cohort rather than assumed, and the chosen storage is
written into the row that builds the client.

### OQ-21 — Is the class-issued Groq key real, still valid, and one key or thirty?

**Why it is yours:** account. Nobody but you can check it.

**What:** The cost argument assumes each Builder brings their own key, and the draft says the cohort
was issued Groq keys as part of the class. If that is stale, or if it is one key shared across thirty
people, both the economics and the rate-limit behaviour change — a shared key means one Builder's
burst throttles everyone else's narratives. Confirm with Pursuit whether the keys were issued, are
still valid and are per-person. Do not design around Groq either way: `backend/llm.py:7-13` already
speaks to four providers over one wire format and `backend/llm.py:206-208` takes per-call `model` and
`base_url` overrides — parameters, not UI copy. It unblocks nothing structural, only how the client
asks.

**Done when:** you know whether the keys exist, are current and are per-Builder, and it is written
into this row.

### OQ-24 — The cohort OS census, before `0007` decision 7 is final

**Why it is yours:** people. Nobody can count thirty laptops from a terminal.

**What:** [`docs/adr/0007`](docs/adr/0007-contributor-credential-opt-in-scheduled-worker.md) decision
7 makes Windows manual-run-only, on the ground that "the cohort is overwhelmingly Mac" — the one
claim in `0007` resting on an unmeasured fact, and `TASKS.md`'s `T-29` (a launchd agent, so
macOS-only) is built entirely on top of it. If the Windows share is a third rather than a handful,
`T-29` covers a minority and Scheduled Tasks stops being out of scope. Ask: one question in the
cohort channel. **Count Linux separately** rather than folding it into "not Mac" — a Linux Builder
can be handed a `systemd --user` timer for the cost of one file, a different answer from Windows.

**Done when:** the Mac / Windows / Linux split is known from the cohort rather than assumed and is
written into this row. A changed answer is a new ADR, not an edit to `0007`.

### OQ-25 — Watch one Builder install the worker end to end, and record where they stall

**Why it is yours:** people, and a room. This cannot be simulated by whoever wrote the installer.

**What:** `0007`'s premise is that the expensive part of onboarding was never the credential — it was
installing software on a personal machine, which `OQ-12` measured at zero contributors. `T-27` …
`T-30` are four guesses about where that friction lives. One watched install says which of the four
mattered and which was invented, including whether `--check`'s output means anything to a reader —
the criterion `T-30` explicitly declines to invent, because plain language is a human judgement.

**How to do it.** One Builder, one machine that is not yours, the real opt-in flow, no shell access
for you, fifteen minutes, before writing installer documentation rather than after. **Sit with them
and say nothing** — the instinct to help destroys the measurement. Write down where they hesitate,
what they read, and what they typed instead of what the instructions said.

**Done when:** one non-author install has been watched start to finish and the stall points are
written into this row — including "none", if that is the honest answer.

### OQ-26 — The metric that replaces `OQ-12`'s zero, and the signal that reopens decision 6

**Why it is yours:** decision. Picking the number you will be judged by is not delegable.

**What:** `OQ-12` closed on a count of zero minted credentials — a metric that could only go up and
said nothing about whether the system works. Two things need naming. **(1) The replacement metric**,
where none is obviously right: *contributors with a check-in in the last 7 days* measures liveness
and ignores value; *queries dispatched per week* measures throughput and flatters a contributor
spending credits on nothing anyone watches; *postings reaching `search_query_results` that no other
source produced* measures the only thing that justifies the arrangement and is the hardest to
attribute. Pick one, and say what number would mean this was not worth building. **(2) The
empty-claim rate that reopens `0007` decision 6**, which defers the leech path until the rate shows
spare capacity exists — measurable once `T-35` reports check-ins, but "shows it exists" is not a
number. **Pick both before the data arrives:** nothing today records a poll that was granted nothing,
and choosing the metric afterwards is choosing the flattering one.

**Done when:** one metric and one threshold are named, and the decision 6 half is written into an
ADR, since it either ratifies or reverses a documented position.

### OQ-27 — Offboarding at cohort end

**Why it is yours:** decision, and it involves other people's machines and other people's money.

**What:** `0007` scopes onboarding completely and offboarding not at all. A cohort ends. Three
questions the code cannot answer:

- **Credential revocation.** `manage_users.py revoke` exists (`backend/api/manage_users.py:190`), so
  the mechanism is there and the policy is not. An alumnus spending their own credits on the next
  cohort's search is a gift — and also an account you no longer have a relationship with.
- **Keyword retention.** `search_queries` deliberately carries no per-Builder identity
  (`backend/schema.py:1045`), so a keyword survives its Builder by construction. That was a privacy
  decision, and it makes this question harder rather than easier.
- **The config file on a returned machine.** `T-28` puts a credential in a plaintext `config.json`.
  If the laptop is Pursuit-issued and passed on, that file goes with it.

**The third had a deadline the others do not, and it has passed.** `T-28` and `T-29` both closed
2026-08-08 and the shipped `--uninstall` **does not remove the credential** — a declining answer the
row made deliberately, pinned by `api/tests/test_worker_install.py`'s
`test_it_removes_the_schedule_and_leaves_the_credential`, so reversing it is a deliberate edit to a
named test. The question is now "decide, then change one function and one test". What did get more
expensive is the machines already installed: every Builder who opts in from here has a plaintext
credential on disk that nothing this repo ships will remove, and a later decision to remove it does
not reach a laptop that already ran `--uninstall`.

**Done when:** all three are answered, and the third is either written into a new `T-` row that
changes `uninstall_agent()` and its test, or recorded here as deliberately unchanged.

### OQ-28 — Is the operator's own SerpApi key contributor zero, or a separate pool?

**Why it is yours:** decision, and it is your account and your credits.

**What:** `0007` paces every contributor against their own plan (`T-32`) behind a reserve floor
(`T-34`). The operator's key is not in that system at all: the nightly bucketed sweep
(`ingest/google-serpapi.py`) spends `SERPAPI_DAILY_QUERY_BUDGET` outside the claim mechanism, and
`OQ-15` closed on keeping that split permanent. Does the operator's key **also** enroll — one
mechanism governing everything, the nightly sweep one participant among thirty — or stay separate,
making the crowdsourced path purely additive? Enrolling means one mechanism, one place spending is
visible, and the same reserve-floor protection for your own key. Staying separate means the path
producing most of what this pipeline ingests cannot be starved by a claim storm — `OQ-15`'s argument
one level up. **Check the arithmetic against whichever you pick:** 250 searches/month against a sweep
already spending 8/day leaves very little reserve to allocate, which may settle it.

**Done when:** one of the two is chosen and written into an ADR, since it constrains `T-32` and
`T-34` and touches `OQ-15`'s documented split.

### OQ-29 — Two GRANTs on `search_queries`, or the contributor API stops starting

**Why it is yours:** machine — a statement issued as the database owner against the deployed
database, which no session may touch.

**What:** `T-26` gave `api/query_claims.py` a claim mode over `search_queries`, so that table is now
the seventh entry in `REQUIRED_TABLES` (`backend/api/query_claims.py:105`) and `verify_schema()`
checks it at startup like the other six. Until these run, the service refuses to start and names the
missing grant:

```sql
GRANT SELECT ON search_queries TO jobs_api;
GRANT UPDATE (claimed_at, claimed_by, claim_granted_at) ON search_queries TO jobs_api;
```

**The second is column-scoped and must stay that way.** A table-wide `GRANT UPDATE` would hand
`jobs_api` the run statistics too, and a contributor's submit could then forge a run history —
writing a future `last_run_at` silences that query for every Builder. `has_table_privilege(...,
'UPDATE')` answers TRUE for either form, so `verify_schema()` cannot tell them apart and this row is
the only place the distinction is enforced. **Refusing to start is designed, not a regression**;
`OQ-7` is the precedent for how that reads when nobody notices. **Neither `provision-database.py` nor
`init-schema` will do this for you** — no tool here issues GRANTs, per
[`docs/adr/0004`](docs/adr/0004-provision-database-issues-no-grants.md).

**Done when:** both statements have run as owner against the deployed database, `jobs-api` starts
clean (`systemctl status`, not inference), and `backend/api/README.md`'s privilege table names
`search_queries` with the column list rather than a bare UPDATE.

### OQ-31 — Run `--check`'s credential branch against the deployed api, once

**Why it is yours:** account and machine. It needs a credential the mint has not issued yet, on a
host no session can reach — `OQ-30` first, and that is the only reason for the order.

**What:** `T-30` shipped `--check`, and one of its three checks is unverified against anything real.
The credential check asks the deployed `api/` to release a claim nobody holds and reads the **409** as
"your key is good" and the **401** as "your key is not" — an ordering inside `release`
(`backend/api/app.py:635`, `:513`) that `api/tests/test_worker_check.py` pins with a fake connection.
**The 401 branch has been run against a real HTTP server; the 409 branch never has.** A fake that
agrees with the code it stands in for cannot tell you the deployed service agrees too.

**How to do it.** After `OQ-30`: opt in through the webapp as yourself, drop the `config.json` beside
the worker on any machine, run `python3 google-serpapi-worker.py --check`, then run it once more with
one character of `JOBS_API_KEY` changed. Two runs, thirty seconds, no SerpApi account needed. **Also
worth reading while you are there:** `T-30` verified against the pipeline's own key that the account
endpoint charges nothing, but that account is at **250/250 with 0 searches left**, so "the remaining
count does not move" was checked on a count that could not move.

**Done when:** a good credential prints the accepted line and a wrong one prints the rejected line,
both against the deployed host, and if either says something else it is written into this row rather
than fixed silently — `T-30` chose the 409 reading deliberately, and this is the check on it.

### OQ-30 — The mint secret, and refusing `/v1/internal/` at the edge

**Why it is yours:** machine and account — a secret generated and placed in two `.env` files on the
deployed host, plus a line in the reverse proxy's config. No session touches either.

**What:** `T-27` shipped the mint. `../webapp/`'s `POST /v1/contribute/opt-in` calls `api/`'s
`POST /v1/internal/contributors` with a shared secret, because the two hold different Postgres roles
and [`docs/adr/0006`](docs/adr/0006-contributor-credential-auto-minted-local-daemon.md) rejects
granting `jobs_web` INSERT on `api_keys`. Three things must be true on the host, and none is code:

1. **One secret, one name, two files.** Generate it (`python3 -c 'import secrets;
   print(secrets.token_urlsafe(32))'`) and set `JOBS_MINT_SHARED_SECRET` to the **same value** in
   `backend/api/.env` and `backend/webapp/.env` — the same variable name in both deliberately.
2. **`CONTRIBUTOR_API_PUBLIC_URL` in `backend/webapp/.env`**, the address a **Builder's laptop**
   reaches `api/` on — not `127.0.0.1`, which is what `CONTRIBUTOR_API_INTERNAL_URL` is for. It has
   no default precisely because the wrong value is silent: the mint succeeds and the `config.json`
   fails on every contributor's machine.
3. **The reverse proxy must refuse `/v1/internal/` from outside.** The secret is the control, this is
   the belt: `api/` is internet-facing behind the Cloudflare Tunnel, so without it the mint route is
   reachable by anyone who finds it.

**Nothing is open until this runs, which is the safe direction.** With no secret set the route returns
**503** and `webapp`'s opt-in returns 503 too; an unset credential-issuing endpoint must never mean
"allow anything", and `api/tests/test_mint.py` asserts that it does not.

**Found while closing `T-27`, left alone because it is also yours.** `backend/webapp/.env`'s
`JOBS_ADMIN_DATABASE_URL` is set but its role is **not the owner of `app_users`** — the `T-27` column
migration failed as that role and was applied as `jobs_pipeline`, which `pg_tables` confirms is the
owner. So `manage_app_users.py init-schema`, whose whole reason for a separate credential is DDL,
cannot issue DDL on this service's own table. Point that URL at the owning role, or record why not.

**Done when:** the secret is set in both `.env` files, `CONTRIBUTOR_API_PUBLIC_URL` is a public
address, `curl` against `/v1/internal/contributors` from outside is refused by the proxy (checked,
not inferred), one real opt-in returns a `config.json` whose `JOBS_API_BASE_URL` a contributor's
machine can reach, and the `JOBS_ADMIN_DATABASE_URL` question has an answer either way.

### OQ-32 — Pick `T-41`'s route: `--install` asks the server, or a run rewrites its own plist

**Why it is yours:** a decision only you can take, **and a Mac.** The second half is why the first
cannot be delegated to a session that would otherwise just pick one.

**What:** `install_agent` takes its interval from `MIN_POLL_INTERVAL_SECONDS` and from nowhere else
(`backend/api/contributor-worker/google-serpapi-worker.py:589`), so an operator who sets
`POLL_INTERVAL_SECONDS` to six hours gets thirty machines that report the ask and keep polling
hourly. `TASKS.md`'s `T-41` is the implementation and is **blocked on this row**. The two routes
differ on one property, and it is the one no test in this tree can observe:

- **(a) `--install` asks the server once.** Costs no SerpApi credit — only a claimed *search* does —
  but `claim` is the only route returning `poll_interval_seconds` (`backend/api/app.py:476`), and
  claiming leases queries the installing process will not run, so (a) is either a leak of live claims
  at install time or a server change to carry the interval somewhere cheaper. It also reverses
  `T-30`'s split, which specified `--install` to talk to nothing and `--check` to be the thing that
  talks to the server — that split is *why* an unreachable server cannot break an install today.
- **(b) A run rewrites the plist when the ask changed.** No new network call. But `install_agent`
  goes unload → write → load (`:464-472`), and under (b) the job being unloaded is the job making the
  call. If launchd stops the process at `unload`, `load` never runs: a plist on disk and **nothing
  scheduled**, with no further run to report it. Strictly worse than the failure `T-31` spent a row
  preventing — a paused worker was at least still a worker.

**Whether launchd does that is unknowable here, and the harness hides it.** The only `launchctl` any
test sees is `test_worker_install.py`'s `Recorder`, whose docstring says answering 0 to everything
"is not a claim that launchctl would" (`:76-78`), and whose `test_what_it_asks_launchctl_to_do` says
no test on this machine can assert launchd accepts anything (`:250-252`). Route (b) built here would
be **green by construction** — the fake returns from `unload` instantly and never stops its caller,
the precise opposite of the hazard. `cli()` refuses `--install` off Darwin (`:799-808`) besides.

**How to do it.** Ten minutes on a Mac: install with a short `StartInterval`, and from inside a
scheduled run call `launchctl unload -w` on its own plist, then write a file immediately after. If
the file appears, (b) survives its own unload and is the cheaper route. If not, (b) needs a detached
helper — machinery whose failure mode is a silently unscheduled fleet — and (a) is the answer.

**A third option neither route names, worth deciding at the same time:** whether a cadence change may
need one `--install` per machine. If it may, a run can persist the last-seen interval beside
`config.json` and `--install` can read it — spending nothing, talking to nothing, the cheapest thing
on the table. `T-41` does not name it because it does not meet that row's "without a hand on each
machine"; `0007` decision 3 says the server "holds desired state", not that machines converge on it
unattended, so whether that clause is a requirement or an aspiration is yours.

**Done when:** one route is chosen, the reason is written into `docs/adr/` as a decision — this is
`0007` decision 3's missing half — and `T-41` is edited to name it and drop the other.

### OQ-33 — A closed row's `file:line` citations go stale on the next commit; is rewriting them right?

Filed by `T-40`, 2026-08-08, which spent its session rewriting fourteen and expects to be back.
**A convention question, so a session cannot settle it.**

**The evidence is not a projection.** `T-28`/`T-29`/`T-30` closed with correct citations into
`google-serpapi-worker.py` and `T-30`/`T-31` broke all twelve; `T-42` corrected six into `api/app.py`
and `T-39` broke them the next commit (`T-46` has both lists). Every one still resolves, so nothing
reported it. `api/app.py:704-711` already carries a mitigation — two constants parked at the bottom
so nothing is inserted above `submit()` — and `T-39` inserted above `submit()` anyway.

**Three options, not equivalent.** (1) Keep rewriting: every row pays forever and a row that forgets
is silently wrong — the status quo, and the only one with a per-session cost. (2) Pin a **closed**
row's citations to the commit that closed it, `git show <sha>:<path>:NNN` — permanently true, and
already blessed for the deleted `docs/`, **but the checker skips line-range validation behind that
form entirely** (`backend/tools/audit-citations.py:17-25`, the `T-18` blindspot), so it trades a
citation that goes wrong loudly for one nothing can check, and points a reader at history rather than
at the code they are about to edit. (3) Drop line numbers from closed rows and cite the symbol —
nothing to drift, nothing to check, and `.claude/CLAUDE.md`'s cite-`file:line` rule would need an
explicit carve-out. **Open rows are out of scope**: a session stands on those.

**`T-46` found a case none of the three covers, and it is the one that decides this.** A closed row's
narrative contains numbers that are *quoted history* — `T-42`'s "→ `:209`" list and `T-30`'s "had
drifted to `:269`" record what those rows wrote at their own commit. Option (1) rewrites them, which
falsifies the record rather than maintaining it; (2) and (3) do not reach them at all. So a closed row
holds two kinds of number and only one is a pointer. `T-46` left the historical ones and marked the
one ambiguous case; `T-47` held the same line on 2026-08-08 while renumbering this file.

**Done when:** the answer is a decision in [`docs/adr/`](docs/adr/), since it changes what
`.claude/CLAUDE.md`'s citation rule means, and `T-46` is edited to match. **If the answer is (1), say
so explicitly** — an unrecorded status quo is what let this run for five days.

### OQ-36 — The cycle reset date is guessed, and two mechanisms now pace one SerpApi account

Filed by `T-32`, 2026-08-09, which built `0007` decision 4's pacing and could not settle either half.

**`T-33` widened the first half the same day.** The guessed anchor now has a second consumer —
`searchnorm.watch_cap()` divides the plan's full allowance by the cycle's full *length* where pacing
divides what is left by what is left of it. Both read the same `cycle_reset_day`, so one right
number still fixes both; a wrong one is now wrong twice, and the second is **visible to a Builder**
as a sentence about how many keywords their plan can keep fresh. Untested on both paths, for the
reason below.

**Why it is yours:** the first half is a fact about an account only you can log into; the second is a
decision about which of two schedulers is the authority.

**What, first half.** Decision 4 divides credits remaining by *days left in the cycle*, and **the
vendor never says when the cycle ends**. `serp/providers/serpapi.py:150`'s `account()` returns
`used`, `left` and `allowance` and no reset date — so `searchnorm.days_left_in_cycle()`
(`backend/searchnorm.py:223`) derives the boundary, defaulting to the **1st of the calendar month**
because that is the vendor's own framing (`this_month_usage`, `searches_per_month`). SerpApi bills
from the **signup date**, so an account opened on the 12th turns over on the 12th and the default is
wrong for it by up to a month — pacing too slow for three weeks, then stranding the remainder. The
anchor is already a parameter (`reset_day`, read from a `cycle_reset_day` key in the provider's
`config/serp-quota.json` entry, absent today), so the fix is a number, not a change: **log in, read
the renewal date, and write it.** A wrong guess here is not visible in any test — every case in the
suite passes under any anchor, because they all pass the anchor in.

**What, second half, and this one is a decision.** `config/serp-quota.json`'s own REJECTED note
forbids a `daily_budget` in that file, on the grounds that `config/google-queries.json` already
carries per-bucket daily budgets and "a second daily number in a second file would be two schedulers
disagreeing". `T-32` did not add one — the allowance is computed per run from the vendor, never
configured — but the collision the note predicts now exists anyway: those buckets sum to
`SERPAPI_DAILY_QUERY_BUDGET = 8`, which is `250/31`, **decision 4's own arithmetic computed once by
hand and frozen**, and it paces `ingest/google-serpapi.py` while `searchqueries.py` paces itself
dynamically against the same account. `reserve` is `0`, so neither holds anything back from the
other, and a month that goes dark early is what "they disagreed" looks like.

**Three ways out, and they are not equivalent.** (1) **Set `reserve`** and leave both — cheapest,
and it makes the nightly bank's fixed 8 a floor the contributor path cannot eat; it is also the
option `serp-quota.json`'s own `_reserve_comment` already describes ("set it if the month starts
going dark early"). (2) **Derive the bank's budget too**, retiring `SERPAPI_DAILY_QUERY_BUDGET` in
favour of `run_allowance()` — one scheduler, and it changes the nightly bank's behaviour, which is a
second live-pipeline row. (3) **Declare them separate accounts** — the contributor's key is the
Builder's own, and if the pipeline's key is never a contributor's then there is no collision to
resolve, only a comment to write saying so. **Which of these is right depends on whether any
contributor ever runs against the pipeline's own key**, which is a fact about deployment.

**Done when:** the reset date is written into `config/serp-quota.json` (or the calendar-month
default is confirmed correct for this account and said so in writing), and one of the three is
chosen — in an ADR if it changes which file owns pacing, in a comment if it only sets a number.

### OQ-35 — A citation into a sibling repo is unrepresentable, and it is red in your working tree now

Filed by `T-51`, 2026-08-09, from your own uncommitted change — untouched, because it is yours.

**Why it is yours:** decision, and the evidence is a repo a session cannot see.

**What:** `deploy/cloudflared/config.yml:87` cites a systemd unit under a sibling `bankan` checkout
for the port the new `bankan.etotheric.com` ingress points at. (The path is not repeated here: it
would make this row unresolvable too, which is the defect.) That file is in a *different* repo on
the same machine, so `tools/audit-citations.py` — which resolves every path against this repo root —
reports it unresolvable, and `tests/test_citations.py`'s
`test_no_citation_broke_that_was_not_already_broken` is a **red test in the working tree right
now**. `T-51`'s own numbers were verified against a copy with this file restored to `HEAD`: `0 new`,
suite `1462` OK. Commit it as-is and CI's `suites` job goes red on `main`.

**Three ways out, and they are not equivalent.** (1) **Drop the `file:line`** and name the port in
prose — cheapest, and it loses the one pointer that says where 3011 comes from. (2) **Add the
sibling-repo form to `audit-citations.py`**, the way `git show <ref>:<path>` was added for the
2026-08-02 deletions — it makes cross-repo cites checkable-looking while validating nothing, which
is the blindspot [`audit-citations.py`'s tag-line form](.claude/CLAUDE.md) already has once. (3)
**Accept it in `config/citation-baseline.json`** — which `.claude/CLAUDE.md` forbids ("never add to
that file to silence a finding"), so taking it is an exception only you can grant.

**Done when:** one is chosen, the suite is green with `config.yml` as committed, and if the answer
is (2) or (3) it is written down where the citation rule is — an ADR, since it changes what that
rule covers.

### OQ-34 — This file cannot reach its own 450-line budget, and the three ways out are all yours

Filed by `T-47`, 2026-08-08, which cut 711 → 534 and could not close the rest without taking
content the same row's "Done when" forbids taking.

**Why it is yours:** decision. Every route out changes a rule you wrote, and a session picking one
would be granting itself the exception.

**What:** The BUDGET NOTE says "past 450, move narrative out rather than raise the number", but
there is nowhere to move it. An open `OQ-` row is an unsettled question by definition, so
[`docs/adr/`](docs/adr/) — which takes decisions, one per file, frozen on write — cannot hold one;
`T-43`'s freeze question was unanswered on top of that; and `.claude/CLAUDE.md` puts what is left to
do in exactly two files, so a third is not available. So the rule's own prescribed remedy is
unavailable and only pruning is left. `T-47` pruned everything that was restatement, drafting
history or elaboration — 25% of the file — and stopped at 534 because what remains is options,
dates, `file:line`s and the "why a session cannot answer this" that makes each row an owner row.
**Cutting further means cutting open questions, which is what the budget exists to protect.**

**Three ways out, and they are not equivalent.** (1) **Raise the number again**, as it was raised
once before, and record why — honest, and it concedes the budget does not bind. (2) **Allow a third
file** for the analysis behind a row, leaving `OQ-` rows as one-paragraph pointers — this is what
task 53 originally assumed, and `TASK-52-harness.md` is the precedent for a root-level file that is
neither of the two; it costs an edit to `.claude/CLAUDE.md`. (3) **Let `docs/adr/` take the
settled halves** — several rows carry decisions already taken (`OQ-5` staged 2026-08-03, `OQ-4a`'s
digest deletion 2026-08-04), which by `.claude/CLAUDE.md`'s own rule belong in an ADR rather than in
prose here. **`T-43` was answered 2026-08-09 by [`0008`](docs/adr/0008-the-freeze-covers-the-argument-not-the-citations.md), so this route is now open** — which does not decide it.

**Done when:** one is chosen and written down — in an ADR if it changes what `.claude/CLAUDE.md`
means, in the BUDGET NOTE if it only moves the number — and this file is inside whatever the
answer makes its budget.

---

## Closed — kept so citations resolve

| # | what it was | outcome |
|---|---|---|
| ~~OQ-1~~ | `backend/api/` stays; who issues a contributor credential was still open | **Closed 2026-08-05 — direction chosen, not yet built.** Auto-mint a credential server-to-server (`DEC-84` option 2) the moment a Builder logs in or hits a "Contribute" affordance, rather than `manage_users.py create` run by hand. The worker itself becomes a long-running local daemon (start once, poll on an interval) instead of a script re-invoked daily — the thing that actually kept `OQ-12`'s contributor count at zero. SerpApi stays called from the contributor's own machine on their own key, never proxied server-side: SerpApi blocks browser-origin calls outright (confirmed), and there is no confirmed SerpApi policy on many accounts sharing one server IP, a pattern that risks real accounts getting banned. A paid SerpApi tier was checked and set aside on purpose — cheaper today, but a fixed ceiling, where crowdsourcing scales with cohort headcount at near-zero marginal cost. Full reasoning in `docs/adr/0006-contributor-credential-auto-minted-local-daemon.md`. Implementation (mint endpoint, daemon script, packaging) is unscoped — follow-up `T-`/`OQ-` rows, next session |
| ~~OQ-15~~ | Is the `ingest/google-*.py` ↔ `serp/providers/*` SerpApi duplication temporary or permanent? | **Closed 2026-08-05, option A: permanent, documented, not merged.** Checked against the live database before deciding — the row's own premise ("an on-demand search path that is dead code in production") was stale: `serp.dispatch.SearchQueryProvider` has been dispatched nightly from `searchqueries.py` since `tranche_four/23` (2026-08-02), one day before the row calling it dead code was written, and `search_query_results` held 253 dispatched rows as of this closure, most recently that same morning. Both implementations spend real SerpApi credit every night — the risk calculus the row was written against (merge a live path into a dead one) no longer holds, since a merge now would mean changing two live nightly paths at once. `_comment`s recording why the split stays permanent are at `ingest/google-serpapi.py:348-363` and `serp/providers/serpapi.py`'s module docstring; the two files were not otherwise touched |
| ~~OQ-22~~ | `score.TRACKS` values are now live in `job_scores.primary_track`; does `derive_tracks()` need to exclude `Re-Entry & Growth` too, or should `score.TRACKS` be replaced for `pursuit` outright? | **Closed 2026-08-05.** Owner picked option 1, after option 3 (revisit the enum outright) was researched and rejected: `primary_track` is never rendered to Builders — `frontend/js/tracks.mjs` explicitly rejects it in favor of `extract.ROLE_TRACK`, the nine-slug vocabulary that *is* displayed (`frontend/fixtures/shipped/MANIFEST.json`). Its only live consequence was the one this row named. A full replacement would drop `primary_track` from the narrative prompt schema, bumping `SCORE_PROMPT_VERSION` — one of the three `_STALE_ANY` arms — and stale the entire `job_scores` backlog (1,231+ rows) for re-scoring, for no additional visible benefit. `webapp/onboarding.py`'s `derive_tracks()` now excludes `'Re-Entry & Growth'` alongside `'Poor Fit'` (`onboarding.py:409-410`), its docstring updated to match, and `webapp/tests/test_builder_profiles.py`'s `test_re_entry_and_growth_is_never_subscribed_to` covers it. Full webapp suite (368 tests) green |
| ~~OQ-23~~ | Cloudflare rewrote `app.css`'s `Cache-Control` to `max-age=14400` regardless of what the origin sent | **Closed 2026-08-05.** Owner set Browser Cache TTL to "Respect Existing Headers" in the Cloudflare dashboard for the zone fronting `jobs.etotheric.com` (option A was available on the current plan). Verified on a guaranteed-fresh edge `MISS`: `curl -sI "https://jobs.etotheric.com/app.css?cachetest=$RANDOM"` now reads `cache-control: no-cache` / `cf-cache-status: MISS` — the origin's header, not a rewritten `max-age`. The `?v=` cache-bust in `frontend/index.html`, left in place since `T-21`/`OQ-14` specifically to cover this gap, is removed. Both frontend checkers still pass: `verify_fixtures.py` matches, `check_client.mjs` reports 57 checks, 0 failed |
| ~~OQ-7~~ | The live database was missing task 25's five search objects and `cohort_signal`'s GRANT | **Closed 2026-08-02.** `init-schema` created them; the seven GRANTs were issued by hand. The lesson worth keeping: this row read as a nicety for a day **while the whole webapp was down** — `verify_schema()` raised in the lifespan and the process exited. Nobody had started it |
| ~~OQ-6~~ | `D31` (urlopen call sites bypassing `lib.http`'s retries) needed an owner decision, not a fix | **Closed 2026-08-03 — confirmed already decided.** `4d6f7aa` (2026-08-02), *"D31 decided — three of four urlopen sites reach lib.http, and one must not"*, resolved it: `fetch_feed`, `fetch_page` and `serpapi_search` now go through `lib.http`; `builtin-nyc.fetch_description` stays on raw `urllib.request.urlopen` deliberately, because `lib.http`'s retry-on-429 schedule would spend four extra requests before `RateLimited` could abandon the detail pass. This row only survived because the register tracking `D31` was deleted in the 2026-08-02 purge before the row was struck there too |
| ~~OQ-9~~ | Two n=115 selfchecks, five days apart, disagreed by up to 9.6 points with no supersession marker on either | **Closed 2026-08-03.** Owner picked option 3: both as a range, act on the lower bound. Both `evals/fixtures/results/selfcheck-n120-*.json` files now carry a `_comment` recording this; `docs/STATE-OF-THE-SYSTEM.md` § 6 and `.claude/CLAUDE.md`'s landmine paragraph state the decision and the per-field floors instead of presenting both as open |
| ~~OQ-2~~ | The 24h impression dedup was keyed `(profile, job_id)`, so one Builder's render suppressed thirty Builders' impressions of the same jobs | **Closed 2026-08-03.** Owner picked option 1: `(app_user_id, job_id)`. `backend/webapp/jobs.py`'s `record_events` NOT EXISTS predicate now binds `prior.app_user_id` instead of `prior.profile`; the existing `idx_job_events_user_job` partial index already served it, so no schema change was needed. Existing rows are not backfilled. Two new replay tests in `tests/test_event_replay.py` (`TestSkipReplay`) cover both directions — a second Builder's impression is no longer deduped by the first, and the same Builder's re-render still is. Full webapp suite (354 tests) green |
| ~~OQ-8~~ | `score.TRACKS`'s five-value enum "does not describe this population" (persona `_comment`); task 30's display half needed a browsable vocabulary | **Closed 2026-08-03.** These are two different "track" concepts, not one. `score.TRACKS` is the narrative LLM call's per-profile vocabulary, two of whose five values ("Re-Entry & Growth", "Poor Fit") are fit judgments rather than job families — renaming it for Pursuit would be exactly the invented narrowness the persona `_comment` warns against, and it's dead code for this profile anyway (`daily_narrative_budget` is 0). `extract.ROLE_TRACK` is the separate, per-job, already-live nine-slug vocabulary task 11 built for this purpose, with hand-written plain-language copy already in `config/search-queries.json`. Decision: task 30's display half ships with `ROLE_TRACK`; `score.TRACKS` is left as-is. Recorded in `score.py`'s `TRACKS` comment and the persona's `_no_buckets_comment`. **The "dead code anyway" half stopped being true 2026-08-05** (`T-24`) — the enum decision itself stands, and the live consequence for `onboarding.derive_tracks()` was resolved the same day as `OQ-22` |
| ~~OQ-16~~ | Whether the `kind: record` carve-out (one document allowed to claim frozen history rather than current state) stays | **Closed 2026-08-03 — carve-out removed, option 2.** The last `kind: record` handoff document is deleted, recoverable at `git show refactor-freeze-2026-08-02:backend/docs/HANDOFF-multimachine-google-jobs.md`. Its still-live facts moved before deletion rather than being lost with it: the multi-machine shared-budget bug it found moved to `backend/README.md`'s locking section, and its Step 3 (a dry-run-verified id migration for `google_jobs` rows, checked today and confirmed **still unapplied 9 days later**) became `TASKS.md`'s `T-20` — a genuinely live finding this closure surfaced, not mere history. The rest was already duplicated in code comments (`lib/ids.py`). Rule is now unqualified: only the three `kind: contract` files may claim current state, no exceptions |
| ~~OQ-12~~ | Whether any contributor API key has ever been minted and handed to a person | **Closed 2026-08-03. No.** Owner confirmed none were generated; `cd backend/api && .venv/bin/python manage_users.py list` (with `api/.env` exported into the shell) returns `no contributors yet` — `api_keys` is empty. Written into `OQ-1`: retiring `api/` would be a deletion, not a migration, if that is the direction chosen |
| ~~OQ-11~~ | Is `SESSION_COOKIE_SECURE` true in the deployed `.env`? | **Closed 2026-08-04. Yes.** `backend/webapp/.env` has `SESSION_COOKIE_SECURE=true`, and the deployment is no longer localhost-only — the Cloudflare tunnel (`OQ-4b`) went live the same day, with a real Google sign-in completed through the public URL |
| ~~OQ-4b~~ | The account half of deployment, and one verified restore | **Closed 2026-08-04.** Cloudflare account, domain, tunnel, and `cloudflared` binary all confirmed live (`OQ-11`). Off-machine backup: `~/.config/jobs-backup.env` points `JOBS_BACKUP_REMOTE` at a Backblaze B2 bucket via a new `rclone` remote (`b2jobs:`); `backup-jobs.sh` run by hand landed a real dump, checksum, and roles-only dump in the bucket. `verify-jobs-backup.sh` then restored that dump into a scratch database and matched all 29 tables' row counts against production, and `--self-test` (truncating `job_facts` in the restored copy) correctly failed the comparison — the check can fail, so passing means something. Both timers installed via `OQ-4a` |
| ~~OQ-14~~ | The phone test — sign-in and the Today screen, on a real device | **Closed 2026-08-04. Sign-in completes and onboarding is reachable, confirmed on a real phone.** The row's own prerequisite (a Google Console redirect URI matching the tunnel hostname) was already done as part of `OQ-11`. What actually blocked it was three bugs nobody had hit, because **the client had never been loaded end to end through the deployed tunnel, on any device, before this row** — the phone was the first thing to try. (1) `deploy/systemd/jobs-webapp.service` ran bare `uvicorn app:app`, never `frontend/serve.py` — so `/` 404'd for everyone since the tunnel went live, not just phones; fixed by pointing `ExecStart` at `frontend/serve.py`, which mounts the client after every API route. (2) `frontend/app.css` had zero `[hidden]` rules, and `.topbar`/`.sheet-backdrop`/`.toast` each set their own unconditional `display: flex` — an author `display` rule always beats the browser's built-in `[hidden] { display: none }` regardless of specificity, so all three had been rendering on top of the page this whole time; the dismiss-reason sheet ("Why isn't this one for you?") sat directly over the sign-in button. Fixed with one global `[hidden] { display: none !important; }` rule rather than three per-class patches. (3) Cloudflare's edge was caching `app.css` for 4 hours by default (`frontend/serve.py`'s `StaticFiles` mount sends no `Cache-Control`, so Cloudflare's own heuristic — cache known static extensions — filled the gap), which meant fix (2) didn't visibly land until `index.html`'s stylesheet link was cache-busted (`index.html` itself is `cf-cache-status: DYNAMIC`, never cached, so that edit propagated immediately). **Separately, a VPN on the host machine caused the "page cannot be reached" symptom seen mid-diagnosis** — `cloudflared` holds QUIC-over-UDP connections to Cloudflare's edge, which the VPN degraded while leaving ordinary HTTPS/TCP untouched; turning the VPN off fixed it immediately and was unrelated to the three bugs above. The caching gap in (3) is real and recurring — every future static-asset edit will get stuck behind the same 4-hour window without a fresh cache-bust — tracked separately as `TASKS.md`'s `T-21` |

---

## Tranche nine, and where it ended up

**4½ of 7 done**, which is why this file exists.

| task | what | state |
|---|---|---|
| 48 | stop the refactor at a known-green state | done (`5cca001`) |
| 49 | orientation from code | done — produced `docs/STATE-OF-THE-SYSTEM.md` |
| 50 | extract the durable core | done (`5046f98`) |
| 51 | archive the rest | done, **but not the way its spec said** — `git show refactor-freeze-2026-08-02:docs/tasks/refactor/tranche_nine/README.md` said *"Not delete anything. 51 is `git mv` and stubs."* `5046f98` deleted 137 and left none; `c052f23`, `20ee7d0` and `47dd212` are the bill. Recorded in `docs/adr/0002-task-51-deleted-instead-of-git-mv.md` |
| 52 | build the harness | **not started.** `~/.claude/skills/` does not exist. Rewritten as [`TASK-52-harness.md`](TASK-52-harness.md) |
| 53 | owner queue and changelog | **Part A only — this file.** Part B, the `whatsnew` check, is `T-9` |
| 54 | replan the product | **superseded.** It was a task to write a plan; [`TASKS.md`](TASKS.md) is the plan |

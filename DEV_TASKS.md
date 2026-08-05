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

**This file owns the prefix `OQ-`.** One allocator. **The next free number is `OQ-22`.**
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
| **10 minutes, and it costs money** | `OQ-19` — the cohort's nightly narrative budget is zero, so no Builder has ever seen a `gap_bridging_angle`. Fund it or decide not to; the personal scoring layer's whole display design turns on the answer |
| **a week of lead time, once the MVP has shipped** | `OQ-3` — line up labellers for round 2. This is the gate the scoring redesign's *validation* is waiting on, not the MVP itself |

**`OQ-3` validates whether the scoring redesign worked; it does not gate shipping.** The redesign
completed 2026-07-28 and has never been validated — GATE 4 of the master plan needs labels that
do not exist yet — but `score_job()` already runs and the frontend already displays its output
independent of any label. Owner decision 2026-08-04: `OQ-3` is deliberately sequenced after the
MVP ships (see the row itself). Everything else on this list improves or validates a system that
already works for users, it does not unblock it.

---

## Open

### OQ-3 — More labellers on the same ten overlap rows, and round 2

**Why it is yours:** people. Longest lead time on the list; start it today even though it
finishes last. **Deliberately deferred past the MVP, 2026-08-04** — see below.

**What:** Round 2 is due around 2026-08-09 and needs ≥100 distinct postings from ≥5 labellers.
Today there are 2 labellers, 36 postings, and **10 rows of overlap**.

**This does not block the MVP or anything a user sees.** `match_score`/`fit_score` are computed
by `score_job()`, which is pure and reads no label table — the frontend already displays scores
today with zero dependency on this row. Owner decision 2026-08-04: recruiting more labellers is
easier once people can see the app working, so this is sequenced **after** the MVP ships, not
before. Recruiting can still widen past the cohort when it resumes — the access gate
(`backend/webapp/manage_app_users.py add`) is an allowlist by email, not a cohort-membership
check.

**How to do it, once resumed.** More *postings* do nothing — 25 of the 36 carry a single
labeller and add exactly zero to the ceiling. What is needed is **more people labelling the same
ten rows**. Point each at the labelling flow, and check progress with:

```bash
cd backend && python3 -m evals label status
```

**What it unblocks:** task 13's weights, task 12's next `FACTS_VERSION` bump, `OQ-5`'s staged
`revenue_commercial` archetype, and GATE 4 of the master plan — which is the gate that says
whether the 2026-07-28 scoring redesign worked. (Previously this line also named task 30; that
was closed independently via `OQ-8` on 2026-08-03 using `extract.ROLE_TRACK`, without needing
these labels — struck here since it no longer depends on this row.) It also un-denominates every
model-vs-human figure in the repo, all of which are currently computed against a ceiling derived
from those 10 rows.

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
**The error-disposition bug this row originally described is already fixed** — re-verified
2026-08-04, see below. What remains is the structural question only.

**What:** Two SerpApi implementations still coexist. They used to **disagree** on what an `error`
key in a 200 response means: `backend/ingest/google-serpapi.py` raised on any `error` key, so
"no results" was recorded as a query failure, while `backend/serp/providers/serpapi.py` treated
it as empty. **That disagreement was fixed in `a80f254` (2026-08-03)** — the live script now
imports `EMPTY_ERROR_MARKERS` from `serp/providers/serpapi.py` and only raises for the
non-empty-result error cases (`ingest/google-serpapi.py:335-356`); one new test covers it. The
commit's own message explains why the two implementations were **not** merged at the same time:
they serve different, currently-unrelated call sites (the live nightly batch script vs. an
on-demand search path that is dead code in production), and merging now would repeat the exact
risk `DEC-99` held back on. Router fallthrough is still unimplemented and unflagged.

**How to do it.** If **temporary**, the fix is to finish the seam: make `serp/providers/` the
one implementation, delete the duplicate, implement router fallthrough. If **permanent**, the fix
is to document the split — the two now already agree on what "no results" means, so this half of
the original "How to do it" is done regardless of which way the temporary/permanent question
lands.

**What it unblocks:** task 23's remaining half.

**Done when:** one implementation exists in the tree, or two exist with a `_comment` at each
saying why the split is permanent.

---

---

### OQ-4a — One clock left, nothing to do but wait

**Why it is yours:** machine. No account needed — this one is just a terminal, and as of
2026-08-04 there is nothing left to type. All 13 tracked units are installed and enabled, and
`systemctl --user list-unit-files 'jobs-*'` shows a clean list — no `bad` entries. `jobs-backup.
timer` and `jobs-backup-verify.timer` joined the rest today, once `OQ-4b`'s off-machine
destination existed to make them meaningful.

**`jobs-volume-digest.timer`/`.service` were deleted from the repo, and are now fully
un-installed.** Decided 2026-08-04: a weekly Telegram report nobody reads is exactly the kind of
alert that trains a channel to be ignored — same failure mode `jobs-volume-digest.service`'s own
comment warned about for its sibling alarm ("an alert about a failed report is how a channel
stops being read"), just applied one level up. `backend/tools/volume-check.py --digest` still
exists for a manual check-in; only the automation is gone. The initial deletion left two dangling
symlinks behind at `~/.config/systemd/user/jobs-volume-digest.{service,timer}` (`systemctl --user
list-unit-files` reported both `bad`) — found and removed 2026-08-04, `daemon-reload` run, list
is clean.

**Not closeable today, and it is not yours to fix:** `python3 tools/volume-check.py` needs a few
days of nightly history before it reports a real comparison instead of `insufficient history` on
every source. That part is a clock, not a task — check back after a few more `jobs-ingest.timer`
runs.

**Done when:** `python3 tools/volume-check.py` reports a comparison rather than
`insufficient history` on every source.

---

---

---

---

### OQ-13 — Registrations that block work: Adzuna, USAJobs, Firecrawl

**Why it is yours:** account. Each is a signup you have to do. **Re-checked 2026-08-04: Firecrawl
is already registered**, so only Adzuna and USAJobs remain open.

**What:** Task 15 has **no commit and no code at all** — it is blocked on an Adzuna
`app_id`/`app_key`. `backend/tools/ats-discover.py:55-60` documents the seam and says so:
`adzuna_top_companies()` is stubbed, and filling it in flows employers into `ats_seed` with no
other change. Firecrawl blocks task 20 — but **`FIRECRAWL_API_KEY` is already set in
`backend/webapp/.env`** (populated, `fc-…` prefix, present since 2026-08-04's deploy). Nothing in
the tree reads it yet (`grep -rn FIRECRAWL_API_KEY **/*.py` is empty — task 20 has no code
either), and it is filed in `webapp/.env`, not `backend/.env`, so whoever picks up task 20 should
confirm that's the right process for it to live in before writing code against it.

**How to do it.** Register for Adzuna and USAJobs, put the credentials in `backend/.env`, and
hand tasks 15 and 20 to a session. Adzuna is free for low volume; check USAJobs' terms before
relying on it.

**Done when:** the Adzuna and USAJobs keys are in `backend/.env` and the stubs are no longer
stubs.

---

### OQ-18 — The personal scoring layer's own validation plan is blocked by a rule this repo chose on purpose

**Why it is yours:** decision. Both available answers are defensible and the code cannot pick.

**What:** The draft's plan was to validate the premise cheaply and server-side: score the same
postings with a hand-authored personal persona and with the cohort's, and compare both against your
own Axis B labels. **That comparison cannot be printed today, and the
refusal is deliberate rather than a missing feature.** `evals label report`
(`backend/evals/__main__.py:653-655`) is the only model-vs-human command and it exits 2 while there
is one labeller, because *"model-vs-human is uninterpretable without a floor and a ceiling beside
it"* (`backend/evals/labels.py:39-45`). There is deliberately no `--force`, and
`backend/tools/label-findings.py:25-35` says it is not a way around that. The ceiling needs a second
labeller — `OQ-3`, which you sequenced *after* the MVP on 2026-08-04.

**How to do it.** Name one of three:

1. **A paired comparison rather than an agreement rate.** "Which of two personas agrees better
   against the same labels" is not the per-item accuracy the guard is about, and `labels.ordering()`
   (`backend/evals/labels.py:2479`) and `labels.recall_bound()` (`backend/evals/labels.py:2418`) are
   both axis-B aware and neither is an agreement rate.
2. **Wait for `OQ-3`.** Correct and slow: the personal layer ships unvalidated or waits.
3. **Build it unvalidated and say so** — it annotates and never orders, so a bad narrative costs a
   Builder some words, not a ranking.

`n=1` is a property of the situation, not a flaw in the plan: you are the only person who can label
for themselves. **What it unblocks:** the sequencing of the feature — `T-22` is independent either
way.

**Done when:** one of the three is chosen and written into an ADR under `docs/adr/`, since it either
reverses or ratifies a documented position.

---

### OQ-19 — Cohort narratives went live on 2026-08-05; does a personal one replace them or sit beside them?

**Why it is yours:** decision. Its funding half answered itself while these rows were being written.

**What:** This row was drafted claiming the `pursuit` cohort's `daily_narrative_budget` was zero, so
no Builder had ever seen a `gap_bridging_angle` and a personal narrative would be the only one on
screen. **That was false within hours of being written, and the code still says it.** The live
`profiles` row carries a budget of **200**, changed 2026-08-05, and `job_scores` holds 178 `pursuit`
rows with a populated `gap_bridging_angle`, scored the same night against
`deepseek-v4-flash`. Cohort narratives are real, and the cards have been rendering them since.

**So the display question is the whole question now.** The detail screen can show both, labelled —
one is what the cohort sees, one is yours, and the two disagreeing is honest — or the personal one
can replace the cohort one in place. The first is more honest and busier; the second is cleaner and
hides a disagreement the Builder might want to see. One constraint either way:
`frontend/js/ui.mjs:13` — *"NO SCORE, ANYWHERE. Not match_score, not fit_score."* A personal
**narrative** is in scope; a visible personal **score** is not.

**Look at one on a phone first.** Nobody has seen a real `gap_bridging_angle` render — `OQ-14`'s
phone test predates the scoring pass by a day — and its length and tone decide whether two of them
fit on one screen at all.

**Done when:** replace-in-place or side-by-side is chosen, having looked at a real rendered
narrative first, and `TASKS.md`'s `T-24` has corrected the three places in the code that still say
this budget is zero.

---

### OQ-20 — `localStorage` is plaintext, and this cohort may be sharing devices

**Why it is yours:** decision, about people you know and this codebase does not.

**What:** The personal layer runs in the Builder's browser on the Builder's own API key, which has
to be stored somewhere. `localStorage` is the only real option in a client with no build step, and
anything else running in that browser profile can read it — including the next person to use that
computer. The superseded draft framed the Builder's exposure as being to their chosen LLM provider
rather than to the operator, which is true and incomplete: **the third party that matters here is
whoever else uses that browser.**

Worth knowing first: the client stores **nothing** in web storage today — that grep is empty and all
state rides the session cookie on the webapp's own origin (`frontend/js/api.mjs:27`).

**How to do it.** Answer one question: do Builders in this cohort share machines — a lab, a library,
a family computer? If yes, the options are session-only storage (re-paste each visit: annoying,
safe) or no stored key at all. If no, `localStorage` plus a plain warning is proportionate. It
unblocks the storage half of the client feature and does not block `T-22`.

**Done when:** the answer is known from the cohort rather than assumed, and the chosen storage is
written into the row that builds the client.

---

### OQ-21 — Is the class-issued Groq key real, still valid, and one key or thirty?

**Why it is yours:** account. Nobody but you can check it.

**What:** The cost argument assumes each Builder brings their own key, and the draft says the cohort
was issued Groq keys as part of the class. If that is stale, or if it is one key shared across
thirty people, both the economics and the rate-limit behaviour change — a shared key means one
Builder's burst throttles everyone else's narratives.

**How to do it.** Confirm with Pursuit whether the keys were issued, are still valid and are
per-person. Do not design around Groq either way: `backend/llm.py:7-13` already speaks to four
providers over one wire format and `backend/llm.py:206-208` takes per-call `model` and `base_url`
overrides — parameters, not UI copy. It unblocks nothing structural, only how the client asks.

**Done when:** you know whether the keys exist, are current and are per-Builder, and it is written
into this row.

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
| ~~OQ-4b~~ | The account half of deployment, and one verified restore | **Closed 2026-08-04.** Cloudflare account, domain, tunnel, and `cloudflared` binary all confirmed live (`OQ-11`). Off-machine backup: `~/.config/jobs-backup.env` points `JOBS_BACKUP_REMOTE` at a Backblaze B2 bucket via a new `rclone` remote (`b2jobs:`); `backup-jobs.sh` run by hand landed a real dump, checksum, and roles-only dump in the bucket. `verify-jobs-backup.sh` then restored that dump into a scratch database and matched all 29 tables' row counts against production, and `--self-test` (truncating `job_facts` in the restored copy) correctly failed the comparison — the check can fail, so passing means something. Both timers installed via `OQ-4a` |
| ~~OQ-14~~ | The phone test — sign-in and the Today screen, on a real device | **Closed 2026-08-04. Sign-in completes and onboarding is reachable, confirmed on a real phone.** The row's own prerequisite (a Google Console redirect URI matching the tunnel hostname) was already done as part of `OQ-11`. What actually blocked it was three bugs nobody had hit, because **the client had never been loaded end to end through the deployed tunnel, on any device, before this row** — the phone was the first thing to try. (1) `deploy/systemd/jobs-webapp.service` ran bare `uvicorn app:app`, never `frontend/serve.py` — so `/` 404'd for everyone since the tunnel went live, not just phones; fixed by pointing `ExecStart` at `frontend/serve.py`, which mounts the client after every API route. (2) `frontend/app.css` had zero `[hidden]` rules, and `.topbar`/`.sheet-backdrop`/`.toast` each set their own unconditional `display: flex` — an author `display` rule always beats the browser's built-in `[hidden] { display: none }` regardless of specificity, so all three had been rendering on top of the page this whole time; the dismiss-reason sheet ("Why isn't this one for you?") sat directly over the sign-in button. Fixed with one global `[hidden] { display: none !important; }` rule rather than three per-class patches. (3) Cloudflare's edge was caching `app.css` for 4 hours by default (`frontend/serve.py`'s `StaticFiles` mount sends no `Cache-Control`, so Cloudflare's own heuristic — cache known static extensions — filled the gap), which meant fix (2) didn't visibly land until `index.html`'s stylesheet link was cache-busted (`index.html` itself is `cf-cache-status: DYNAMIC`, never cached, so that edit propagated immediately). **Separately, a VPN on the host machine caused the "page cannot be reached" symptom seen mid-diagnosis** — `cloudflared` holds QUIC-over-UDP connections to Cloudflare's edge, which the VPN degraded while leaving ordinary HTTPS/TCP untouched; turning the VPN off fixed it immediately and was unrelated to the three bugs above. The caching gap in (3) is real and recurring — every future static-asset edit will get stuck behind the same 4-hour window without a fresh cache-bust — tracked separately as `TASKS.md`'s `T-21` |

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

**`OQ-3` is still the one to line up recruiting for, once the MVP ships — see the row itself for
the 2026-08-04 sequencing decision.** The scoring redesign completed 2026-07-28 and has never
been validated — GATE 1 came in at 16/20 and 10/20 against a definition of done asking 20/20, and
GATE 4 has never been attempted. `OQ-3` is that gate, but the system it would validate is already
running and displaying scores to users regardless. Every row in `TASKS.md` improves or validates
a system that already works, not one still waiting to be unblocked.

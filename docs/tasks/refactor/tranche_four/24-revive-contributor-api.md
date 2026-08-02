---
kind: task
written: 2026-07-28
generator: none
---

# 24 — Revive the contributor API

**Status:** the pre-deploy half landed 2026-08-02; the deploy half is still
todo. **Depends on:** 23, 33 (tunnel). **Blocks:** 25.

Deploy `backend/api/`. It is written, ~~tested~~ **tested as of 2026-08-02** and
has never run.

> **CORRECTED 2026-07-31 (task 34): there are ZERO tests for `backend/api/`.**
> No file in `backend/tests/` imports `api/app.py` or `api/query_claims.py`; the two
> that mention the directory test `lib/`, not the service. "Never run" is right and is
> confirmed by `backend/api/README.md`. **"Tested" was not**, and the difference matters
> for this task's shape: deploying code with no tests is a bigger job than deploying
> tested code, and three defects (D08, D09, D41) are dispositioned *fix before deploy*
> against it with nothing to catch a regression in the fix.
>
> **CLOSED 2026-08-02.** `backend/api/tests/` now exists — 35 tests, the service's
> first, run by api's own venv:
>
> ```bash
> cd backend/api && .venv/bin/python -m unittest discover -s tests
> ```
>
> A **third suite**, not an addition to `backend/tests/`, and that was forced rather
> than chosen: `backend/api/.venv/pyvenv.cfg` sets
> `include-system-site-packages = false`, so the system `python3` the pipeline suite
> runs under cannot import `app.py` at all — it needs `fastapi`. Verified, not assumed:
> `python3 -c "import fastapi"` raises `ModuleNotFoundError` at the top level.
> The command is recorded in `.claude/CLAUDE.md` beside the other two.

## Reversing a decision

`backend/api/README.md:32` records that the service has never been deployed, and
`docs/tasks/README.md` records that it is **expected to be deprecated**. That was a
reasonable call for a single-user tool. It is wrong for this one.

The contributor model is the community feature the whole product is organised around,
and — this is the part that changed my earlier advice — it is *architecturally* the
right way to pool Google Jobs access:

> A contributor's worker claims stale queries from `POST /v1/queries/claim`, runs them
> against SerpApi **with its own key**, and posts the raw results back to
> `POST /v1/queries/{dataset}/submit`

Thirty Builders each running their own worker against their own free 250 searches is
thirty people staying inside their own allocation. That is a different thing from one
application pooling thirty keys to exceed one allocation, and it is defensible in a
way key-pooling is not. It also degrades gracefully: a Builder graduates, their worker
stops, nothing breaks.

Capacity: **30 × 250 = 7,500 searches/month**, the largest renewable pool in the plan
by an order of magnitude.

## What already works

Read `docs/ingest/contributor-api.md` before touching anything — it is a
~~generated~~ **hand-written and hand-maintained** audit of this exact service.
Its frontmatter says `generator: none` and always meant it
(`docs/ingest/contributor-api.md:1-15`); `.claude/CLAUDE.md` records that
"never hand-edit" applies only to a generator that exists, which for this repo is
none of them.

- FastAPI app object at `backend/api/app.py:152`; `uvicorn app:app --port 8420`
- **Startup is gated**: a `lifespan` context manager runs `verify_schema()` before
  serving (`:146-149`) and raises `RuntimeError`, refusing to start, if any required
  table, privilege or sequence is missing (`:82-143`)
- `docs_url` and `redoc_url` are both `None` — interactive docs deliberately disabled
- Everything stored is **recomputed server-side from the raw payload** (`:325-334`),
  so a contributor cannot inject arbitrary rows — they submit a SerpApi response and
  the server decides what it means
- Rows land in the same `jobs` table tagged `platform='google_jobs'` through the same
  `lib.upsert` path the pipeline uses (`query_claims.py:425-446`)
- It coordinates with `ingest/google-serpapi.py` and `ingest/google-apify.py` through
  the **same `job_ingest_state` rows** (`query_claims.py:216-241`), so the three paths
  do not duplicate work

That server-side recomputation is the security property that makes this safe to open
to thirty people, and it should be stated in the operator docs rather than left to be
rediscovered.

## Work

### Deploy

The docstring is explicit that domain, TLS and reverse proxy are undone. Task 33's
Cloudflare Tunnel solves all three without opening a port or needing a static IP.

The API and the nightly pipeline have different requirements — the API needs inbound
connectivity and uptime, the pipeline needs neither. Deploy accordingly; see task 33.

### Builder onboarding

The missing half. A Builder needs to go from "I have a SerpApi account" to "my worker
is contributing" without a terminal session with the author.

- A page, behind the existing Google SSO, that issues a contributor credential
- A single-file worker script they can run — and, better, a scheduled option that
  does not require leaving a laptop on. A GitHub Actions cron in their own repo is a
  plausible zero-install path and doubles as something they built
- Plain-language setup instructions. Assume no prior terminal experience; this is the
  population the whole app exists for, and the onboarding is itself a teaching
  artifact

### Query source

Contributors claim from a queue. Task 25 fills that queue from `search_queries`, seeded
by `role_track`. ~~Until then, seed manually from task 05's vocabulary so the service has
something to serve.~~

**CORRECTED 2026-08-02: there is nothing to seed.** `backend/config/google-queries.json`
already holds **4 buckets and 32 slugs**, with `daily_budget` per bucket (2, 3, 2, 1) and
a `mode` of `nyc` or `remote` on every query. `query_claims.load_query_buckets()` reads it
(`backend/api/query_claims.py:401-403`) and `pick_stale_queries_by_bucket()` serves from it
(`:406-453`). It is the same file `ingest/google-serpapi.py` uses — deliberately one file
since slice D, because the API's private copy had been free to diverge and nothing was
keeping the two identical. `GOOGLE_QUERIES_FILE` overrides the path if a curated public
subset is ever wanted.

The queue is therefore not empty and never was. What task 25 changes is where the bank
comes *from* — a static committed file becomes rows in `search_queries` keyed by
`role_track` — not whether one exists.

### Fairness and abuse

- ~~Rate-limit claims per contributor so one worker cannot drain the queue~~ **Done
  2026-08-02 (defect D41)**, per day. `claim` writes one `submission_log` row per query
  granted and `claims_today()` counts `action = 'claim'`. **Per-day only** — nothing caps
  how many a contributor holds *concurrently*, and 50 outstanding claims is inside the
  daily cap and most of a 32-slug bank. See "What the work turned up".
- ~~Expire unclaimed-but-checked-out queries so a worker that dies does not block a
  query forever~~ **Already true and was when this was written**:
  `try_claim_query`'s `WHERE claimed_at IS NULL OR claimed_at < ttl_cutoff`
  (`backend/api/query_claims.py:256-281`) makes expiry a property of the claim statement
  rather than a sweeper that has to run. `CLAIM_TTL_MINUTES` defaults to 15.
- ~~Cap submissions per contributor per day~~ **Already true**:
  `MAX_CLAIMS_PER_CONTRIBUTOR_PER_DAY` (`backend/api/app.py:52-54`, enforced `:296-301`).
  It was the *claim* side that was uncapped, which is what D41 was about.
- Track contribution counts per Builder. Anonymously in the UI (per the visibility
  decision), but attributably in the database, because a contributor whose submissions
  are consistently empty is a broken worker, not a lazy person. **Partly done**: an empty
  submit now writes a `submission_log` row saying so (`backend/api/app.py:405-407`)
  instead of being indistinguishable from a successful one, so "consistently empty" is a
  query. Nothing surfaces it — there is no report and no UI.

### Register it in the router

`serp/providers/contributor.py` (task 23) dispatches into this queue. Note that it is
**asynchronous** — a query goes in, results arrive when some Builder's worker picks it
up. The router must treat it as a deferred provider, not a synchronous one, and fall
through to a synchronous provider when a result is needed now.

## Documentation

~~`backend/api/README.md:32` and `docs/tasks/README.md` both say this is expected to be
deprecated.~~ **Half right, corrected 2026-07-31: `backend/api/README.md` does not
contain the word "deprecat" anywhere.** Its `:32` says the service has *never been
deployed*, which is a different claim and is still true. The deprecation sentence is in
`docs/tasks/README.md` only. That one is now marked; this task still owns un-marking it
when the service actually deploys. ~~Both are now wrong. Correct them as part of this
task~~ — **there is one notice, not two**, and un-striking it belongs to deploy day, not
to the pre-deploy work: a doc that says "expected to be deprecated" about a service that
is still not running is stale, and a doc that says the opposite about the same service
would be false.

## Definition of done

Status as of 2026-08-02, after the pre-deploy half. The deploy half is gated on
task 33's tunnel and on a running service, and is untouched.

- **Service running behind the tunnel; `verify_schema()` passes at startup.**
  Split. The tunnel half is task 33's and is not done. `verify_schema()` is
  *stronger* than when this was written — it now checks required **columns** as
  well as tables, privileges and sequences (`backend/api/app.py:143-154`), which
  it needed to, because `submission_log.action` is new and `init-schema` is a
  separate admin command. Not verified against a live database; no database this
  service can reach has been initialised.
- **A Builder can onboard end-to-end without the author's involvement.** Not
  done, and the blocking piece is a decision rather than code — see
  *A credential-issuing page needs an ownership decision* below.
- **At least three contributors submitting successfully.** Not done; needs the
  service to run.
- **Rate limits, claim expiry and per-contributor caps in place.** Claim expiry
  and the per-contributor daily cap were already in place before this task and
  are now pinned by tests; the claim rate limit landed with D41. **Concurrency is
  still uncapped** — see below.
- **Registered in task 23's router as a deferred provider.** Not possible.
  `backend/serp/` does not exist; task 23 is descoped.
- ~~**Contribution counts tracked; empty-submission workers detectable.**
  Detectable, not surfaced. `submission_log` now records an empty submit as an
  empty submit with `action` on every row, so the query exists. No report reads
  it.~~ **Done 2026-08-02.** `backend/api/contribution_report.py` reads it —
  per contributor and, with `--by-dataset`, per query slug. Both halves of "an
  empty-submission worker" are answerable from the output: a worker whose
  submits come back empty (`action = 'submit' AND fetched_count = 0`), and a
  worker that claims and never submits at all, which writes no submit row of
  any kind and so cannot appear in an empty rate. The second view is the
  control — every contributor submitting empty on one slug is a dead query, not
  a room full of broken workers, and reporting the latter for the former was the
  failure worth designing against. See *Where the report lives* below.
- **The ~~two~~ one deprecation notice corrected.** Deferred to deploy day on
  purpose — see the Documentation section above.
- **`docs/ingest/contributor-api.md` regenerated.** Done, where "regenerated"
  means **hand-edited**: that file is `generator: none` and always was
  (`docs/ingest/contributor-api.md:1-15`), and `.claude/CLAUDE.md` records that
  "never hand-edit" applies only to a generator that exists, which for this repo
  is none of them. Rewritten for the three fixes and re-cited throughout: the
  D01 fix had shifted `app.py` by eight lines and roughly thirty citations in
  that document had gone stale, including the two this task's own defects were
  filed against.

---

## What the work turned up

Everything below is from the pre-deploy half, 2026-08-02. **Decision text is
written out in full with no number allocated** — four agents were running in
parallel and `DECISIONS.md` cannot take four appends. The owner numbers and
lands these.

### Proposed decision — `backend/api/` gets its own test suite, run by its own venv

**Context.** `backend/api/` had zero tests. The two files in `backend/tests/`
that mention it name `api/app.py` and `api/query_claims.py` as *paths* in a
parametrised list over `schema.google_spec()`
(`backend/tests/test_upsert_checked.py:133-134`) and in a comment
(`backend/tests/test_lib_contract.py:331`); neither imports the service, and the
first says so in its own docstring at `:20-28`. Three defects dispositioned *fix
before deploy* were pointed at it with nothing to catch a regression in the fix.

**Decision.** Tests live in `backend/api/tests/` and are run by api's own venv:

```bash
cd backend/api && .venv/bin/python -m unittest discover -s tests
```

That is a **third suite** the repo now has, alongside `backend/tests/` and
`backend/webapp/tests/`, and the discovery command is recorded in
`.claude/CLAUDE.md`.

**Why this and not `backend/tests/`.** It is not a preference.
`backend/api/.venv/pyvenv.cfg` sets `include-system-site-packages = false`, and
`app.py` imports `fastapi`; the top level runs on system `python3` with no venv
at all, where `import fastapi` raises `ModuleNotFoundError`. Verified directly
rather than inferred. Putting these tests in `backend/tests/` would mean either
adding `fastapi` to the pipeline's dependency set — which `.claude/CLAUDE.md`
states as a constraint to keep, `psycopg[binary]` being the only third-party
dependency — or a suite that skips everywhere, which is worse than no suite
because it reports a number.

**What was rejected.** Importing `app.py` by path with `importlib` the way
`evals/ingest_modules.py` imports the hyphenated ingest scripts. That solves the
filename problem, which `api/` does not have, and not the dependency problem,
which is the actual one.

**Consequence to accept.** Three suites means three `Ran N tests` lines and
three chances to read the wrong one. The three are independent by construction —
separate processes, separate venvs, separate Postgres roles — so this is the
cost of that separation showing up in the test story, not a new problem.

### Proposed decision — an empty submission does not advance the watermark, and the pipeline's opposite rule stays

**Context.** Defect D08. `submit` called `mark_success` unconditionally, so
`{"jobs": []}` marked a query covered for `GOOGLE_JOBS_MIN_HOURS_BETWEEN_RUNS`
with nothing stored.

**Decision.** An empty payload short-circuits: no `mark_success`, no
`google_jobs_query_stats` row, the claim is **released**, a `submission_log` row
is written anyway, and the response carries `watermark_advanced: false`. The
pipeline's `ingest/google-serpapi.py:335-351` keeps doing the opposite —
advancing on zero results — and the asymmetry is deliberate.

**Why the two differ.** The pipeline made the SerpApi call itself, so an empty
array there is evidence: the fetch succeeded and the window is genuinely quiet.
This endpoint sees only an array, from a caller its own module docstring calls
untrusted. An empty one is what an exhausted key, a blocked worker, a wrong chip
and a quiet query all look like from here. "Silence is this system's failure
mode" is a named invariant, and this was its instance.

**What was rejected.**

- **A `fetch_ok: true` flag in the payload.** It moves the assertion to the side
  that has the bug, and a buggy worker sends it by default.
- **400 on an empty submit.** The honest "my search returned nothing" worker then
  retries forever, reports failures to its owner, and leaves the claim locked for
  the full TTL.
- **Holding the claim rather than releasing it.** Holding throttles a broken
  worker, which is a real benefit, but it also blocks the contributor with a
  *different* SerpApi account who could succeed on it right now.

**The cost, stated rather than hidden.** A genuinely-empty query is handed out
and fetched again — one SerpApi credit, bounded by the per-contributor daily cap
and the per-bucket budgets. The other direction is a posting nobody ever sees
and no counter records, which is unbounded and undetectable.

### Proposed decision — `submission_log.action`, and a daily cap that counts what its name says

**Context.** Defect D41. `MAX_CLAIMS_PER_CONTRIBUTOR_PER_DAY` was enforced by
`claims_today()`, which counted `submission_log` rows — and `claim`, the only
endpoint that takes a query out of the pool, wrote none.

**Decision.** `claim` writes one `submission_log` row **per query granted**, and
`claims_today()` counts rows with `action = 'claim'` and nothing else. That
needed a new nullable `submission_log.action` column, created by
`query_claims.ensure_schema()` through `dbconn.add_missing_columns` and declared
in a new `query_claims.REQUIRED_COLUMNS` that `verify_schema()` checks at
startup. `SUBMISSION_ACTIONS` is the closed set; `log_submission()` is the only
writer of the table.

**Why both halves.** Writing the rows without filtering the count would charge an
honest submit and an honest release against a cap whose name is about claims —
doing the work would reduce how much work you were allowed, which is a worse
defect than the one being fixed and would have looked like the fix working.

**Why per query and not per request.** The endpoint already computed
`remaining = MAX - used` and passed it to `max_queries`, so the number had always
been read as a count of queries. It now is one.

**Why a request granted nothing writes nothing.** It locked no query and cost
nothing. Metering it would make "the bank is fully fresh today" indistinguishable
from abuse and would spend an honest daily cron's allowance on exactly the days
there is no work — the worker prints "nothing to do" and exits 0 on those.

**Why a column and not a `reason` prefix or a second table.** `reason` is free
text a caller partially controls; a quota that parses it is a quota an input can
influence. A second table doubles the grants this role holds. The column costs
nothing to add because the service has never been deployed, so there is no
migration and no backfill — a NULL `action` honestly means "written before this
column existed" and is never counted as a claim.

**Why `CHECK` was rejected.** It would need DDL rights this service deliberately
does not hold, plus a migration to widen the set. The closed tuple in code is the
same shape `webapp/jobs.py`'s `EVENT_NAMES` uses for `job_events.event`, for the
same reason.

### Proposed defect — concurrent claims per contributor are still uncapped

*(Described, not numbered. `docs/ingest/DEFECTS.md` owns the `D` prefix.)*

D41's fix caps claims **per day**. Nothing caps how many a contributor may hold
**at once**. `MAX_CLAIMS_PER_CONTRIBUTOR_PER_DAY` defaults to 50 and the
committed query bank has 32 slugs, so one worker can be inside its daily
allowance and holding the entire bank, each row locked for `CLAIM_TTL_MINUTES`
(default 15). That is the second half of the original claim-loop threat and it
survives the fix.

It is cheap to close: `job_ingest_state.claimed_by` is already set by
`try_claim_query`, so "how many does this contributor hold right now" is one
`SELECT COUNT(*) WHERE claimed_by = %s AND claimed_at >= ttl_cutoff`. It was left
out of this tranche because the right ceiling is a policy number nobody has
picked — it interacts with `MAX_QUERIES_PER_CLAIM` (5), with the per-bucket
budgets, and with how many Builders are actually running workers, and picking it
before any of the three is observable would be inventing a constant.

Class: **cosmetic** while the service is undeployed, on the same reasoning D41
carried. Disposition: **fix before opening to more than a handful of
contributors** — not before deploy, since a tailnet-only phase 1 has no
adversary.

### Where the report lives, and why that was not a style choice

*(2026-08-02, the session that closed the bullet above.)*

`backend/api/contribution_report.py`, run on this package's venv beside
`manage_users.py`, which is the CLI precedent here:

```bash
cd backend/api
.venv/bin/python contribution_report.py                  # per contributor
.venv/bin/python contribution_report.py --by-dataset     # per query slug
.venv/bin/python contribution_report.py --empty-workers  # only the findings
```

**Not `backend/tools/`, and the reason is a GRANT.** `submission_log` is granted
to `jobs_api` and to nothing else (`query_claims.REQUIRED_TABLES`, and README's
privilege table). Everything under `backend/tools/` runs as `jobs_pipeline`,
which holds nothing on it, so putting the report there would have meant issuing
a new grant to produce a report — widening a role's reach for a read, which is
the opposite of what the three-role split buys. Here it needs no new privilege
at all, which `backend/api/tests/test_grants.py` now checks: the module was
added to `SERVICE_MODULES`, so its SQL is scanned against `REQUIRED_TABLES` like
the request path's.

**`action` has four values, not three, and the fourth is NULL.**
`SUBMISSION_ACTIONS` is `('claim', 'submit', 'release')`; the column is nullable
with no default and `query_claims.py` says what a NULL means — *"written before
this column existed"*. The report gives it its own column headed `null`, prints
a word rather than a blank there (a blank in a column of integers reads as
zero), excludes it from every rate, and — the assertion that matters — never
lets it earn a contributor a finding. *"This worker submits nothing"* about a
worker whose rows merely predate the column is a false accusation that reads
exactly like a true one. Same rule the pipeline applies to an unversioned
`job_scores` row and to `job_events.rank`.

There is a **fifth** bucket, `other`, for an action that is neither NULL nor in
the vocabulary. `action` is free TEXT — `DEC-83` rejected a `CHECK` because it
would need DDL rights this service deliberately does not hold — so a value
outside the set is a state the database can represent and the code cannot
prevent. The five buckets partition the rows exactly and `summarize()` asserts
they add up to `COUNT(*)`, which is the *"reconcile collected counts against the
total"* rule applied to a log instead of a paginated API: a row in no bucket
would be a row the report silently drops from somebody's totals.

**An empty submit is keyed on `fetched_count = 0`, not on `reason`.** That is
the server-computed `len(payload.jobs)` from the D08 short-circuit. `reason` is
free text the caller partially controls on the release path, and a diagnosis
that parses caller-supplied text is one an input can influence — the same
argument `DEC-83` used to reject a `reason` prefix in favour of a column.

**The two thresholds are a reading lens, not a policy.** `--min-submits` and
`--empty-rate` decide what gets a label printed beside it; nothing acts on them
and no row is written. That is why they are flags rather than constants: there
is no distribution of real worker behaviour to derive a ceiling from yet, and
picking an enforced number before one is observable is the mistake `D71`'s
concurrency cap was left open to avoid.

### ~~Proposed defect~~ **`D72`, fixed** — the claim protocol has no test

`try_claim_query`'s conditional update and `holds_claim`'s three conditions are
this service's subtlest reasoning — particularly the `claim_granted_at` takeover
guard, which exists because the pipeline's own claim statement sets `claimed_at`
without knowing about `claimed_by` and therefore leaves it stale
(`backend/api/query_claims.py:287-308`). All of it is SQL semantics, and
`backend/api/tests/fakedb.py` dispatches on SQL text and cannot falsify a `WHERE`
clause.

`backend/webapp/tests/test_event_replay.py` is the worked pattern for closing
this: a scratch schema from `evals/scratchdb`, skipped where no database is
available. It is not built here because `scratchdb.create()` calls
`schema.ensure_schema()`, which needs CREATE — and `api/`'s `.env` holds
`jobs_api`, which by design has none, so the fixture would need the same
`JOBS_SCRATCH_DATABASE_URL` indirection `test_event_replay.py:48-77` documents at
length. That is a real piece of work, not a line.

Class: **cosmetic** (a testing gap, not a defect in the code). Disposition: fix
with the scratch-schema fixture, before the service is exposed beyond the
tailnet.

**Numbered `D72` and fixed 2026-08-02**, with exactly that fixture:
`backend/api/tests/test_claim_protocol.py`. The takeover is performed by
`lib.state.try_claim` — the function `ingest/google-serpapi.py` actually calls —
rather than by a hand-written `UPDATE`, because this entry's own premise is that
the guard was *"found by testing against the pipeline's real SQL, not
theorized"*, and a test that restates the pipeline's SQL from memory stops being
that the first time the pipeline changes.
[`DEFECTS.md` § D72](../../../ingest/DEFECTS.md#d72) has the full list of what it
pins.

### `D73` — the 400 on a malformed body echoed the body

*(Allocated and closed 2026-08-02, in this task's stream because it owns
`app.py`.)*

`submit`'s parse handler returned `detail=f"malformed body: {e}"`, and a pydantic
`ValidationError` embeds `input_value=` in its string form. For `json_invalid` —
every syntactically broken body — that is the **whole request body**, which for
this endpoint is a SerpApi response fetched with a contributor's own key.

Found by task 33, which recorded it and declined to fix it because another stream
owned this file. **That entry's cite was wrong by 58 lines**: it said
`app.py:292` and the site was `:350`, with `:292` landing on the daily-cap
`HTTPException` in `claim()` — a citation that resolves to plausible-looking
other code, which is worse than one that resolves to nothing. Corrected in
`tranche_six/33-deployment.md` and in `docs/RUNBOOK.md`, struck rather than
overwritten in both.

The fix is `app._validation_detail()`, which builds the detail from the error's
`loc` and `type` alone and passes both through a whitelist. **It is placed at the
bottom of `app.py` on purpose**: about forty-five `backend/api/app.py:NNN`
citations live in `docs/ingest/contributor-api.md`, `docs/RUNBOOK.md` and three
task files, and anything inserted above `submit()` invalidates all of them at
once — which is precisely what this task's Definition of done records happening
after the D01 fix shifted the file by eight lines. The diff is one changed line
at `:350` and an append after `:527`, so no existing citation moved.
[`DEFECTS.md` § D73](../../../ingest/DEFECTS.md#d73) carries the rest.

### A credential-issuing page needs an ownership decision — proposed decision, NOT built

The task's "Builder onboarding" section asks for "a page, behind the existing
Google SSO, that issues a contributor credential". **This was deliberately not
built**, and the reason is an ownership boundary rather than effort.

That page would live in `backend/webapp/`, which runs as `jobs_web`. Issuing a
credential means `INSERT` on `contributors` and `api_keys` — two of the six
tables `jobs_api` owns, and two that `jobs_web` is granted nothing on.
`docs/tasks/README.md:40-52` states the boundary and states that task 24 reverses
the *deprecation* half and explicitly **not** the import half: "the two services
hold different Postgres roles... so `webapp/` importing from `api/` would relax
the property this section exists to defend, whatever happens to the deprecation
plan."

Three ways to satisfy the requirement without breaking that, for the owner to
choose between:

1. **Grant `jobs_web` INSERT on `contributors` and `api_keys`.** Simplest, and it
   widens the blast radius of a webapp session-hijacking bug from "reads and
   event rows" to "mint yourself a contributor credential". It also makes two
   roles writers of one table, which is the thing role separation buys.
2. **A server-to-server call: webapp asks api to mint a key**, over the tailnet,
   with a shared secret. Keeps every table single-writer. Adds a synchronous
   dependency between two processes that currently cannot reach each other at
   all, and a second credential to rotate.
3. **Keep issuance in `manage_users.py` and make the page a request queue** — the
   Builder asks, the owner runs one command, the key is delivered out of band.
   Does not meet the DoD's "without the author's involvement", and is the only
   option that changes no grant and no boundary.

The honest reading is that (2) is right if this service is really being revived
and (3) is right if it is a stopgap for one cohort. That is a product call about
how long `backend/api/` is expected to live, which is exactly what "expected to
be deprecated" was about, and it is the owner's.

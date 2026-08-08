---
kind: rolling
written: 2026-08-03
generator: none
subject: .
budget: 500
---

# Session tasks — everything a session can do without the owner

**This file owns the prefix `T-`.** One allocator. **The next free number is `T-41`.** Numbers are
never reused and never renumbered, so a citation to a closed row keeps resolving.

**It is the other half of [`DEV_TASKS.md`](DEV_TASKS.md)**, which owns `OQ-` and holds everything
that needs a machine, an account, a device, other people, or a decision only the owner can take.
Nothing here needs any of those. **Between the two files, that is meant to be the whole list** —
if work exists in neither, it is not tracked, and that is the condition this file exists to end.

This replaces `git show refactor-freeze-2026-08-02:docs/tasks/refactor/tranche_nine/54-replan-the-product.md`.
54 was a task to *write* a plan against `docs/STATE-OF-THE-SYSTEM.md`; this is the plan. Its
central requirement survives verbatim: **every row carries machine-checkable acceptance criteria —
the exact command and what it should print.** Its second requirement survives too, and matters
more here: *if this list turns out to be short, that is a finding and not a failure.*

## The ceiling

**Work discovered while executing a row becomes a row here, an `OQ-` row, or an ADR. It never
becomes a sub-tranche or a new document.** The failure mode this whole effort exists to correct is
a meta-project that grows: tasks 36–47 were twelve consecutive tasks of documentation
infrastructure, every one green, and they produced no product movement. The ceiling only works
when it is enforced at the inconvenient moment.

## The goal these rows serve

Standard tooling instead of hand-rolled convention. **The bound:** `ruff`, CI and type checking
are development tools. **No new runtime dependency enters `backend/requirements.txt`,
`backend/api/requirements.txt` or `backend/webapp/requirements.txt`.** The pipeline runs unattended
on several machines and every added package is another thing that can be missing on one of them;
that reasoning is unchanged and `T-1` has a grep proving it holds.

## Order

**Everything before `T-30` is closed** — the toolchain rows, the five harness layers, the
§ 4a defects, `0007`'s two server-side rows and the two worker rows under them — and each is one
line in the table at the foot of this file. `T-1` and `T-2` were the
reason for the original ordering: they are the enforcement layer every later row leaned on, and what
makes a session's claims checkable without hand-transcription. Everything since runs against CI
rather than against a transcribed count.

**The eleven open rows are one project, not a queue.** They cut
[`docs/adr/0007`](docs/adr/0007-contributor-credential-opt-in-scheduled-worker.md) into buildable
steps and are listed in dependency order, not priority order: the server side is done and the
worker can now be installed, so `T-30` … `T-31` — the rest of the worker — is what nothing on a
contributor's machine works without now; `T-32`
… `T-37` are policy that needs both halves in place. `T-32` and `T-33` are the two that change live
pipeline behaviour rather than adding to it. `T-38`, `T-39` and `T-40` are the exceptions to the dependency
order: none is a cut of `0007`, each is a gap a closed row opened or found and could not itself
close (`T-26`, `T-27` and `T-29` respectively), and they belong at the front rather than at the end.

**The worker's settings block is pinned from outside its own suite, and that outlives `T-28`.**
`T-27` shipped the payload as `webapp/contribute.CONFIG_FIELDS`, and
`webapp/tests/test_contribute.py`'s `TestTheWorkerContract` pins it against
`google-serpapi-worker.py`'s **own source** rather than against a fixture — by regex over
`os.environ.get("X")` and over everything after `def main`. So renaming a setting, or replacing
those three spelled-out lookups with a loop over a tuple, turns the **webapp** suite red rather
than the api one, and `T-29` … `T-31` all touch that block. Read that test before editing it, and
run both suites.

**None of these rows is the critical path.** [`DEV_TASKS.md`](DEV_TASKS.md)'s `OQ-3` is — the
scoring redesign completed 2026-07-28 and has never been validated, and every row here improves a
system nobody has confirmed works. It needs people, so no session can start it. `OQ-24` … `OQ-28`
are the owner-side half of `0007` specifically, and `OQ-25` — watching one Builder install the
worker — is the one that decides whether `T-27` … `T-30` were worth building. `OQ-30` is new and
blocks the row that just closed: the mint 503s until the operator generates
`JOBS_MINT_SHARED_SECRET` and puts it in both `.env` files.

---

## Contributor pipeline — [`docs/adr/0007`](docs/adr/0007-contributor-credential-opt-in-scheduled-worker.md)

Eleven open rows, eight of them cutting `0007` into buildable steps and `T-38`, `T-39` and `T-40`
consequences of three that closed. `0007` supersedes
[`0006`](docs/adr/0006-contributor-credential-auto-minted-local-daemon.md) decisions 1, 2 and 4;
`0006` decision 3 — local execution, contributor's own key, own IP, never proxied — stands and is
load-bearing for every row here. The owner-side half is `DEV_TASKS.md`'s `OQ-24` … `OQ-28`.

**Baseline: all three suites are green — `1449` / `397` / `212`, all `OK`, measured 2026-08-08.**
The api figure has moved four times since these rows were written and the rows below still
quote the old ones: it was `117`, then `145` after `T-26`'s 28 cases in
`api/tests/test_search_query_claims.py`, then `160` after `T-27`'s 15 in `api/tests/
test_mint.py`, then `179` after `T-28`'s 19 in `api/tests/test_contributor_worker.py`, and is now
`212` after `T-29`'s 33 in `api/tests/test_worker_install.py`; the
webapp suite was `368` and is now `397` after `T-27`'s 22 in
`webapp/tests/test_contribute.py` and 7 added to `webapp/tests/test_grants.py`. **Re-measure rather
than trusting a row's own number** — that is what these two paragraphs exist to say.
Commands below are still scoped to a module or a grep rather than a whole-suite `OK`, which is the
cheaper check and localizes a regression to the row that caused it.

**Two rotting tests were found and fixed getting to that green, and the shape is worth knowing
before writing a test for any row here.** Both mixed a real-clock timestamp with a hardcoded one and
so passed only inside a window: `tests/test_serp.py` paired a `now - 5 days` `last_run_at` with a
literal `now="2026-08-02T12:00:00"`, which stopped satisfying `searchnorm.is_due()` on
2026-08-06T16:00Z; `frontend/check_client.mjs`'s cohort-signal check ran a `/\bago\b/` ban over the
whole detail page, catching the posting's own `ageLabel()` and passing only while the shipped
fixture's fixed `posted_at_ts` sat in that function's seven-day `"last week"` window. **Derive every
timestamp in a test from one clock, or freeze all of them — never one of each.** `T-31` and `T-32`
are the rows most exposed to this, since both turn on elapsed time.

---

### T-40 — One citation into the worker names the wrong block, and the checker cannot see it

`api/tests/test_claim_metering.py:29` cites `contributor-worker/google-serpapi-worker.py:121-126`
for the worker printing "nothing to do" and exiting 0 on a granted-nothing poll. Those lines say
nothing of the kind. **It was already wrong before `T-29` touched the file** — at `1a0b0c3` they
were the settings block, `SERPAPI_API_KEY` through `DEBUG` — so this is drift the closing session
found rather than drift it caused. The behaviour the comment means is at
`google-serpapi-worker.py:247-252`.

**This is the one live instance in the tree of the blindspot `config/citation-baseline.json`'s
`_what_this_cannot_catch` describes**: the line number resolves, so `tools/audit-citations.py`
reports it green, and only reading the target shows the claim is about something else. Found by
`T-29` and deliberately not folded into it.

```bash
cd backend
python3 tools/audit-citations.py     # today: "citations ok: 3 known-drifted, 0 new" -- it cannot see this
sed -n '121,126p' api/contributor-worker/google-serpapi-worker.py         # not the claim
git show 1a0b0c3:backend/api/contributor-worker/google-serpapi-worker.py | sed -n '121,126p'
#   the settings block -- what it pointed at before this row's file moved, and already not the claim
```

**Done when:** the citation names the lines that carry the behaviour it describes, the checker still
prints `0 new`, and the other citation into that file (`TASKS.md`, `T-28`'s closed row) has been
read against its target rather than assumed. **Do not generalise this into a content checker** —
the tool's own docstring already says it cannot be one, and a second hand-rolled auditor is the
failure mode this repo deleted 137 files to end.

---

### T-30 — `--check`, validating credential, base URL and SerpApi key

One command a Builder runs when something is wrong, printing a pass/fail line per check: the base URL
resolves and `/v1/health` answers (`backend/api/app.py:255`), the credential authenticates, and the
SerpApi key is accepted by SerpApi. Exit non-zero if any fails.

**Spend no SerpApi credit to prove the key works.** SerpApi's account endpoint reports plan state
without running a search; a validating search would charge the Builder for asking whether they are
set up, which is the wrong first impression. That endpoint is also where `T-31`'s plan data comes
from, so the two rows read the same response.

```bash
cd backend/api/contributor-worker
python3 google-serpapi-worker.py --check    # today: exits 1, "worker FAILED: set JOBS_API_BASE_URL, ..."
#   (the flag is unparsed; the env check fires first)
```

**Done when:** `--check` prints one line per check and exits non-zero on any failure, a wrong
credential is distinguishable in the output from an unreachable base URL, and no SerpApi search
credit is spent — verify against the account endpoint's own reported remaining count, before and
after.

**One criterion here is not machine-checkable and is not being invented:** "plain language" is a human
judgement. `OQ-25` — watching one Builder install this end to end — is where that gets tested.

---

### T-31 — A server-dictated poll interval, clamped locally

`0007` decision 3. The claim response (`backend/api/app.py:260`) gains the next interval; the worker
clamps it against a local floor and holds no other policy. That is what makes pause, resume and
cadence changes need no local listener — the reason `0006` decision 4 could be superseded without
reintroducing Safari mixed content or Chrome's Private Network Access rules.

**The clamp is a floor, not a range.** A server that says "poll in 10 seconds" must not be able to
make thirty machines hammer an endpoint; a server that says "poll in six hours" is allowed to.
`T-29`'s `StartInterval` is the same number, so a changed interval only takes effect when the worker
rewrites the plist — say so in the row's implementation, because a Builder will otherwise read a
paused worker as a broken one.

```bash
cd backend
grep -n "poll_interval\|next_interval" api/app.py api/contributor-worker/google-serpapi-worker.py
# today: prints nothing
cd api && .venv/bin/python -m unittest discover -s tests
```

**Done when:** the claim response carries the interval, a below-floor value from the server is raised
to the floor with a test pinning that direction specifically, and the api suite prints `OK`.

---

### T-32 — Budget pacing from reported plan data; `RERUN_HOURS` demoted to a freshness guard

`0007` decision 4. Allowance is credits remaining divided by days left in the cycle, recomputed per
run from the contributor's own plan data (the same endpoint `T-30` reads). `searchnorm.RERUN_HOURS`
(`backend/searchnorm.py:183`) stops deciding *whether* a query runs and becomes only a
minimum-freshness floor inside `is_due()` (`backend/searchnorm.py:213`).

**The free tier does not roll over.** A fixed cadence both fails a contributor whose machine was shut
for a week and abandons credits that expire at cycle end — that is the whole argument, and it is in
`0007`, not to be restated in code comments.

`is_due()` is pure and swept, and `searchqueries.py:327` is its live caller. Keep it pure.

```bash
cd backend
python3 -m unittest tests.test_search_queries    # today: Ran 64 tests, OK
```

**Note the existing assertion this row must confront rather than edit around:**
`tests/test_search_queries.py:271` pins `searchnorm.RERUN_HOURS == 20`. Demoting the constant does
not make that test wrong — it makes it insufficient. Replace it with one asserting the freshness
floor still binds and that pacing, not cadence, picks the query.

**Done when:** `tests.test_search_queries` still prints `OK` at 64 plus the new cases, `is_due()` still
does no I/O (it takes the pacing allowance as an argument, it does not fetch it), and a contributor
with a week-idle machine is shown to catch up rather than being rate-limited to one run per
`RERUN_HOURS`.

---

### T-33 — A cap derived from the reported plan, replacing `MAX_QUERIES_PER_BUILDER`

`0007`'s first consequence: `MAX_QUERIES_PER_BUILDER = 20` (`backend/searchnorm.py:78`) is a promise
the free tier cannot keep, because `RERUN_HOURS` binds long before 20 watched queries do. The cap
becomes derived from the contributor's reported plan and surfaced as a **soft warning, not a block**.

Both enforcement sites raise today rather than warn — `backend/webapp/search.py:200` and
`backend/webapp/search.py:272`, each returning "stop watching one first". A watch row is a saved
keyword and a discovery surface (`0007` decision 5); refusing to save one because of a SerpApi plan
is the wrong coupling, which is what "soft" is doing here.

```bash
cd backend
grep -rn MAX_QUERIES_PER_BUILDER --include=*.py . | grep -v __pycache__
# today: 8 lines -- searchnorm.py:78, searchnorm.py:338 (a comment), webapp/search.py:200,204,272,276,
#   and webapp/tests/test_search_signal.py:184,195
cd webapp && .venv/bin/python -m unittest discover -s tests
```

**Done when:** watching past the derived cap succeeds and returns a warning rather than a 4xx, the
two `search.py` sites no longer raise, `webapp/tests/test_search_signal.py:184` (which loops to the
constant) is rewritten against the derived value, and the webapp suite prints `OK`.

---

### T-34 — Server-side contributor settings, against the credential

`0007` decision 3's other half: the server holds desired state. Three settings, keyed on the
contributor, read by the worker on every poll — **paused**, a **daily cap**, and a **reserve floor**
(credits the worker will not spend, so a Builder keeps some of their own quota).

The worker holds no policy of its own beyond `T-31`'s clamp. Anything else it decides locally is a
second source of truth that a paused contributor's machine will disagree with.

The settings need a home: `contributors` exists (`backend/api/manage_users.py:74` inserts it) and
carries `name`/`created_at`/`notes` only. Adding columns there is the cheap answer; say in the commit
why it is or is not the right one.

```bash
cd backend
grep -rn "reserve_floor\|daily_cap\|\"paused\"" api/*.py    # today: prints nothing
cd api && .venv/bin/python -m unittest discover -s tests
```

**Done when:** a paused contributor's poll returns zero queries and still records the check-in
(`T-35`), the reserve floor is shown to stop a claim at the boundary rather than one query past it,
and the api suite prints `OK`.

---

### T-35 — Contributor status reporting

Four facts per contributor, so the operator can tell a stalled worker from an idle one: **last
check-in**, **worker version**, **remaining quota**, **last error**. Without these, `OQ-26`'s
empty-claim-rate signal has nothing to read.

`api/contribution_report.py` already aggregates contributors (`fetch_contributors`,
`backend/api/contribution_report.py:189`) and is where this surfaces. **Last check-in is not last
submission** — a paused or fully-fresh worker submits nothing and is healthy, and `0007`'s dormancy
consequence turns on exactly that distinction. `claim` deliberately writes no `submission_log` row
when it grants nothing (`backend/api/app.py:260`), so check-in needs its own record; do not meter it
as a claim, or an honest idle poll starts consuming the daily allowance
(`backend/api/app.py:204`).

Remaining quota is contributor-reported, not server-observed. Store it as reported, with the time it
was reported, and never present it as authoritative.

```bash
cd backend/api
grep -n "last_check_in\|worker_version\|last_error" contribution_report.py app.py   # today: prints nothing
.venv/bin/python -m unittest discover -s tests
```

**Done when:** the report shows all four per contributor, a worker that polls and is given nothing
still moves its last check-in forward, that poll writes no `submission_log` row, and the api suite
prints `OK`.

---

### T-36 — Account-level dormancy pauses spending, not check-in

`0007`'s fourth consequence. A dormant account spends no SerpApi credit and claims no queries, but
keeps checking in — so status still reports, and nothing needs re-enabling when the Builder returns.

**Account-level, not per-query.** This is the same shape `score.py:1082` already uses on the scoring
side ("a dormant account costs nothing"); reuse the reasoning, not the code — that is a different
process with a different notion of account.

Dormancy is a server-side state under `T-34`, not a local flag. A worker that decides for itself that
it is dormant is invisible to the operator, which is the failure this row exists to avoid.

```bash
cd backend
grep -rn "dormant" --include=*.py . | grep -v __pycache__
# today: 2 lines, both score.py comments (1082, 1241) -- nothing in api/ or webapp/
cd api && .venv/bin/python -m unittest discover -s tests
```

**Done when:** a dormant contributor's poll returns zero queries, advances last check-in, and spends
nothing; reactivating requires no action on the Builder's machine; and the api suite prints `OK`.

---

### T-37 — Rewrite `config/google-queries.json`'s bucket comments for the cohort persona

`0007`'s last consequence, and `0006`'s unactioned finding. The top-level `_comment`
(`backend/config/google-queries.json:2`) says the four buckets are "weighted to Eric's actual
positioning: 5 YOE full-stack SWE, 2.5yr career break, currently 5mo into a prompt/agent engineering
program." Every per-bucket `_comment` reads the same way. Under `0007` these comments decide what
~30 Builders' own SerpApi credits get spent on, so they stop being cosmetic.

**Comments only, in this row.** `_comment` fields in `config/*.json` are decision records that live
beside the number they explain (`docs/adr/README.md`), so rewriting the rationale is in scope and
changing a `daily_budget`, a bucket, or a query string is not — that is a re-weighting, and it needs
`OQ-24`'s census and `OQ-26`'s metric before anyone can say the new weights are better.

```bash
cd backend
grep -c "Eric's actual positioning\|5 YOE\|career break" config/google-queries.json   # today: 5
python3 -c "import json; json.load(open('config/google-queries.json')); print('parses')"
python3 -m unittest tests.test_search_queries    # today: Ran 64 tests, OK
```

**Done when:** that grep prints `0`, the file still parses, every bucket's `daily_budget` and query
list is byte-identical to before (`git diff` touches `_comment` values only), and each rewritten
comment says what the bucket is for in terms of the cohort — entry-level, AI-adjacent, all
industries, NYC — rather than one person's résumé.

---

### T-39 — `contributors` and `api_keys` are unreachable from the one stand-up-from-nothing command

**Found while closing `T-27`, and filed rather than folded in.** This is `T-19` still open along one
edge, and `T-27` made it load-bearing for a second service without widening it.

`tools/provision-database.py` runs five `STEPS` (`backend/tools/provision-database.py:70-76`) and
none of them reaches `api/query_claims.ensure_schema()`, where the DDL for `contributors` and
`api_keys` lives (`backend/api/query_claims.py:245-261`). Only `manage_users.py init-schema`
(`backend/api/manage_users.py:55`) does. So on a database stood up by the one command that claims to
create everything, those two tables do not exist — and since `T-27` a **webapp** route depends on
them, one process away from the command that would have created them.

`T-26` hit the same trap from the other side and escaped it by putting its DDL in `schema.py`
instead. That option is not available here: these are `api/`'s own tables, owned by the service
whose README's whole argument is that the pipeline holds nothing on them, so moving the DDL would
trade a provisioning gap for an ownership lie.

**Two shapes, and the second is not obviously worse** — (1) add `qc.ensure_schema` as a sixth step,
which means `provision-database.py` importing `api/` and so acquiring a third venv's worth of
import path; (2) leave the DDL where it is and make the gap loud — `--verify-only` reports the two
tables as missing rather than not looking, so a fresh database says so before a Builder's first
opt-in does. Say in the commit which and why.

Note the asymmetry that makes this less urgent than it reads: CI provisions a fresh `postgres:16`
and the api suite is green there, because every test in it uses a fake connection rather than the
schema. That is exactly why the gap survived — nothing that runs proves the tables exist.

```bash
cd backend
grep -n "STEPS = \[" -A 8 tools/provision-database.py     # today: five, none of them api/'s
python3 tools/provision-database.py --verify-only          # today: says nothing about api_keys
```

**Done when:** a database provisioned only by `tools/provision-database.py` either has
`contributors` and `api_keys`, or is reported by `--verify-only` as not having them, with a test
that fails if a future table is added to `api/`'s DDL and to neither; and all three suites stay
green.

---

### T-38 — Nothing advances a `search_queries` row's run statistics after a contributor submits

**Found while closing `T-26`, and filed rather than folded in.** That row built the claim half of
per-query dispatch and stopped exactly where the claim stops. The other half has no owner.

On `job_ingest_state` the two halves are columns of one row, so `mark_success`
(`backend/api/query_claims.py:356`) advances the watermark and clears the claim in one statement.
`search_queries` splits them: the run statistics are `last_run_at`, `run_count`,
`provider_last_used`, `result_count_last_run` and `last_result_at`, and
`searchqueries.record_run()` (`backend/searchqueries.py:348`) says in its own docstring that it is
**the only writer** of them. It is also the only thing that *can* be — `T-26` grants the `jobs_api`
role UPDATE on the three claim columns and nothing else, deliberately, because a table-wide grant
would let a contributor's submit forge a run history and silence a query for every Builder by
writing a future `last_run_at`.

**The consequence, concretely:** a contributor claims a `search_queries` row, spends their SerpApi
credit, submits, and `release_search_query_claim` (`backend/api/query_claims.py:484`) frees the row
with `last_run_at` untouched. `due_queries()` (`backend/searchqueries.py:303`) therefore returns it
on the next cycle, and the next, and the credit is spent again each time. `0007` decision 4 paces
spending against a contributor's own plan, which makes a query that is never satisfiable the most
expensive kind of row there is.

**Three shapes, and this row is where one gets picked** — do not treat the first as the default
because it is the shortest: (1) widen the grant to `last_run_at` and friends and let `api/` write
them, which reopens the forging argument above; (2) a narrow server-side writer in `api/` that
calls nothing the contributor controls, taking provider and result count from the same server-side
normalization `/submit` already applies; (3) the pipeline reconciles from `search_query_results`,
which it already owns — no new grant at all, at the cost of the run statistics lagging by a nightly
cycle. Say in the commit which and why; if it is a real decision rather than a mechanism, it is an
ADR and not this row.

```bash
cd backend
grep -n "record_run" searchqueries.py api/*.py    # today: only searchqueries.py
cd api && .venv/bin/python -m unittest discover -s tests
```

**Done when:** a contributor's submit against a `search_queries` row leaves that row not due on the
next `due_queries()` call, with a test that fails if the run statistics are left untouched;
`record_run`'s "only writer" docstring is either still true or amended to say what else writes;
and the api suite prints `OK` at `145` plus the new cases.

---

## Closed — kept so citations resolve

**Compacted 2026-08-07, and this is a compaction, not a deletion.** These twenty-five rows were
~940 of this file's ~1300 lines: closure narrative that had already done its job. What each one is
still *for* is that its number resolves, which a table line does as well as an essay.

**To read any row in full, in the state it was closed:**

```bash
git log --oneline -S 'T-13' -- TASKS.md     # the commit that closed it
git show <that-commit>:TASKS.md             # the row, verbatim, as written
```

**Three findings were relocated rather than left to go down with the prose**, because each is a
landmine a future session would otherwise re-trip: `T-16`'s SQL-identifier convention and its
`# noqa`-inside-an-f-string gotcha are in [`.claude/rules/sql.md`](.claude/rules/sql.md); `T-18`'s
tag-form blindspot is in `backend/tools/audit-citations.py`'s own docstring, beside the code that
has it and correcting a claim that docstring used to make. Every other row's durable reasoning was
already in the code, an ADR, or a rules file before this compaction — that was checked row by row,
not assumed.

| # | what it was | outcome |
|---|---|---|
| ~~T-29~~ | The worker parsed no arguments at all, so `0007` decision 2's "the OS owns the schedule" had nothing to install it with | **Closed 2026-08-08.** `--install` writes `~/Library/LaunchAgents/com.github.liueric-dev.jobs.contributor-worker.plist` via `plistlib` and loads it; `--uninstall` unloads and removes it (`backend/api/contributor-worker/google-serpapi-worker.py:327`, `:367`, `:401`). Idempotence is **structural, not checked**: one label gives one path, so a second `--install` overwrites rather than adds — but it unloads first, because launchd holds the copy of the plist it read at load time and rewriting underneath a loaded job leaves the *old* schedule running and reports success. **The row's "`StartInterval` matches the local floor `T-31` defines" could not be met as written and was not faked**: `T-31` is unbuilt and no floor existed anywhere in the tree, so the constant is defined here as `MIN_POLL_INTERVAL_SECONDS = 3600` (`:169`) with `T-31` named as its inheritor — two floors that drift apart is a worker polling on one number and scheduled on another, which nothing would report. One hour for `T-31`'s own stated reason, and a granted-nothing poll spends no SerpApi credit, so what this bounds is the endpoint's cost and not the Builder's. **No `WorkingDirectory` key, deliberately** — pinning one would supply the very thing `T-28`'s suite exists to prove the agent does without; both `ProgramArguments` are absolute, `sys.executable` so the agent keeps the interpreter that was proved to work. `RunAtLoad` is false so `--install` never spends a credit; `T-30`'s `--check` is the specified way to confirm one. **The platform gate is in `cli()`, not in `install_agent()`** — that is what lets the file half be tested on this Linux box at all, and `--install` refusing here is asserted for real rather than skipped. **Nothing simulates `launchctl`**: the two cases that reach it record the argv this worker *would* send; whether a real launchd accepts the plist is `OQ-25`'s watched install and no test here reports on it. 33 cases in `api/tests/test_worker_install.py`, and **five deliberate breakages confirmed they bite** — a pinned `WorkingDirectory`, a rewrite without the unload, an `--uninstall` that deletes the credential, a second `main`-prefixed definition, and a parser that prints on the bare run — each turning exactly the expected test red, and the fourth turning the **webapp** suite red rather than the api one, which is the hazard the file now carries a comment about (that comment was itself written with the anchor string in it, twice, and the webapp suite caught it). The bare-run path was checked by diffing this build's stdout and stderr against `HEAD`'s, not by reading the parser. **`OQ-27`'s third bullet is NOT resolved here**: `--uninstall` removes the schedule, names the `config.json` still holding the credential, and deletes nothing — whether it should is an owner decision about other people's machines, and a test pins the declining answer so reversing it is a deliberate edit. One finding filed rather than folded in: `T-40` |
| ~~T-28~~ | The worker took its settings only from the environment, so `0007`'s "paste one file" install had nothing on the other end to read it | **Closed 2026-08-08.** `load_config()` resolves `config.json` from `os.path.dirname(os.path.abspath(__file__))` (`backend/api/contributor-worker/google-serpapi-worker.py:91`) and the three required settings fall back to it, environment first. **The row's own premise was wrong in one detail and `plan-verifier` caught it**: the worker reads **six** settings, not "all four", and requires three — `git show 3f76b3e` shows it was never four, so this was never-true rather than drift, and the same phrasing had been copied into `webapp/tests/test_contribute.py`'s docstring. The three it does not require stay environment-only, per `0007` decision 3: per-run policy is `T-31`'s poll response, not a file written once at install. **The cwd bug this row exists to prevent is invisible to any test that imports the module**, so all 19 cases in `api/tests/test_contributor_worker.py` are subprocess runs and `_run` asserts its `cwd` is outside the script's directory — including one that puts a *decoy* `config.json` in the working directory and requires the one beside the script to win. The unchanged-message clause was checked by diffing this build's output against `git stash`ed `HEAD`'s, not by reading the f-string. A malformed file gets its own message naming the file, because the unset-variable message would send its author to look at their shell. Three settings named at both ends rather than looped, deliberately: `TestTheWorkerContract` regexes this source and a loop would leave it nothing to read. No `config.json` is committed, and a test asserts that — it would be a committed credential and would mask the bare-environment clause. Nothing filed; `OQ-27`'s third bullet noted as overtaken |
| ~~T-27~~ | `0007` decision 1's mint-at-opt-in endpoint: the credential shape existed in `manage_users.py create`, but `webapp` and `api` share no code and no database role, so how `webapp` got a row into `api_keys` was unanswered | **Closed 2026-08-08.** **The answer is that it does not.** Three candidates: grant `jobs_web` INSERT on `api_keys` (rejected outright by `0006`'s consequences, DEC-84 option 1), a request queue for `manage_users.py create` to drain (rejected by `0006` decision 1), and a server-to-server call — the only survivor, and the one `0006`'s consequences already assumed by naming "the server-to-server shared secret" as the unscoped follow-up. So `webapp` authenticates the Builder, POSTs `api/`'s new `/v1/internal/contributors`, and **no grant crosses the two roles**: `jobs_api` already held INSERT on `contributors` and `api_keys`, `jobs_web` gains nothing, and `webapp/README.md`'s "The two do not talk" is amended rather than quietly falsified. The mint itself moved to `qc.mint_credential()` with `manage_users.py create` as a caller — one implementation, per `.claude/CLAUDE.md`. **Both key properties were asserted by trying to break them, not by reading the code**: the raw key is fetched back out of everything written and out of a second mint, and the `config.json` field list is pinned against the T-28 worker's own source rather than a fixture, so a rename on either side is red. Two findings filed rather than folded in: `T-39` (`api_keys` is unreachable from `provision-database.py`) and `OQ-30` (the shared secret, and refusing `/v1/internal/` at the edge). One thing found and left alone: `webapp/.env`'s `JOBS_ADMIN_DATABASE_URL` is not the owner of `app_users`, so the migration ran as `jobs_pipeline` — `OQ-30` carries it |
| ~~T-26~~ | `api/query_claims.py` could lease a **dataset string** in `job_ingest_state` and nothing else; `0007`'s per-query dispatch needs to lease a `search_queries` row, which had no claim columns at all | **Closed 2026-08-07.** Three columns added to `search_queries` via `add_missing_columns` inside `schema.ensure_search_query_schema()` — **in `schema.py`, deliberately not beside the precedent it mirrors.** A `plan-verifier` pass found the row's two halves in tension: `job_ingest_state`'s three claim columns have no single owner (`claimed_at` in `lib/state.py`, reachable from `provision-database.py`; `claimed_by` and `claim_granted_at` in `api/query_claims.ensure_schema()`, which is **not** one of its five steps), so mirroring the precedent literally would have shipped a column nobody provisions — `T-19` straight back. `try_claim_search_query` is a plain conditional `UPDATE`, not an upsert: a `search_queries` row exists because a Builder saved the keyword, so a claim must never conjure one. **Both protections were asserted by breaking them**, not by reading the predicate: dropping `claim_granted_at` from `holds_search_query_claim` turns exactly one test red, and removing the parentheses around the `OR` turns exactly one other red — the second matters because without them a claim aimed at one row takes over every expired claim in the table and still reports a win. Two findings filed rather than folded in: `T-38` (nothing advances a claimed row's run statistics after a submit) and `OQ-29` (the two column-scoped GRANTs the new `REQUIRED_TABLES` entry now demands at startup) |
| ~~T-1~~ | There was no linter and no formatter, and a tranche README said wiring one in was wrong for this repo | **Closed 2026-08-03**, `56ce823`. `ruff` adopted as a **dev-and-CI tool only**, reversing an outright ban by owner decision. `backend/pyproject.toml` carries `[tool.ruff]` and nothing else — no build backend, no packaging, because nothing here is installed as a package. Landed against a recorded baseline rather than a mass reformat: a large unreviewable diff is the exact move that produced the documents this repo deleted. In none of the three `requirements.txt`, and CI greps to prove it. Reasoning is [`docs/adr/0001`](docs/adr/0001-ruff-as-a-dev-only-linter.md) |
| ~~T-2~~ | A live remote, no CI, no git hooks — every result verified by hand and transcribed into a commit message | **Closed 2026-08-03.** Green run: `https://github.com/liueric-dev/jobs/actions/runs/30818425894`, its three `Ran N tests` lines matching a local run exactly — the clause that mattered, because a CI job reporting green on *less* was the failure this row existed to catch. **It was red first, and that is what it bought:** a database entry point that did not exist (`T-19`), a test-isolation defect, and confirmation that the DB gating and no-skip guard both work |
| ~~T-3~~ | The three `requirements.txt` specified floors, not pins | **Closed 2026-08-03.** All three pin `==` at the version already installed in the interpreter each file governs — the pipeline's system `python3`, `api/.venv`, `webapp/.venv`. CI installs fresh on a clean runner with no lockfile and no cache, so pinning to locally-validated versions is the same environment, not a departure from it. Every comment header untouched |
| ~~T-4~~ | `DECISIONS.md` — "the single most valuable file in the repo" — was deleted with the other 136 and nothing took its slot | **Closed 2026-08-03.** `docs/adr/` is the successor, seeded with the decisions recorded nowhere else. Two decisions were deliberately **left where they are** (the isort `known-first-party` entry, the non-blocking CI lint step): an ADR that only restates a config comment creates a second copy to keep in sync, which is the failure the directory exists to avoid. The rule that decides whether it survives — *an ADR records why, not what the code does today* — is in [`docs/adr/README.md`](docs/adr/README.md), not here |
| ~~T-5~~ ~~T-6~~ ~~T-7~~ ~~T-8~~ ~~T-9~~ | The five layers of [`TASK-52-harness.md`](TASK-52-harness.md), which held the argument and the ordering constraint | **Closed 2026-08-03/04.** L1: `.claude/CLAUDE.md` under 150 lines with five path-scoped files under `.claude/rules/`. L2: `plan-verifier` and `artifact-reviewer`, read-only. L4: a `PostToolUse` hook running `tools/audit-citations.py`. L5: `~/.claude/CLAUDE.md`, and `~/.claude/skills/whatsnew/` — task 53's Part B, never built until then. **One clause could not be met in-session and was recorded rather than skipped:** a running session does not detect a newly created `.claude/agents/` directory, so "each invoked once on real work" needed the *next* session. It resolved there exactly as predicted, hook included |
| ~~T-10~~ | Ten migration scripts, no runner, no record of which had been applied | **Closed 2026-08-03.** `backend/migrations/runner.py`, stdlib only, ten scripts registered by filename. It never parses a script's own report text to guess real-world state — that would be a second, drifting copy of logic each script already owns. **Deliberately no `--apply-all`:** four of the ten have a real effect on a bare re-run, each an operator decision by its own docstring, and a blanket apply-all would make ten of those decisions on a shrug. `--status` reports honestly rather than optimistically on a box with no history. That reasoning is in the runner's own docstring |
| ~~T-11~~ | Seven silent `except Exception` sites | **Closed 2026-08-03.** One logs, six narrow. The one that mattered is `evals/scratchdb.available()` — twelve modules gate on it via `skipUnless`, so "no Postgres here" and "the driver is broken" had been indistinguishable. The routine case stays exactly as silent as before; a genuine driver bug now prints one stderr line. `ruff` fell 1085 → 1078: narrowing removes `BLE001` |
| ~~T-12~~ | The pipeline stages printed their failures | **Closed 2026-08-03.** `backend/lib/pipelinelog.py`, one `get_logger(name)`. **A format change, not a visibility change** — every call site kept the `DEBUG_PRINT_KEYS` guard it had. The `_StderrProxy` that looks `sys.stderr` up fresh on every write is what makes this compatible with every pre-existing `redirect_stderr`/`mock.patch` test, with zero test rewrites; that reasoning is in the module. Four forced failures were checked directly, one per file, not just via the suite |
| ~~T-13~~ | `ensure_app_view`'s DROP fallback destroyed every GRANT on the view | **Closed 2026-08-03.** The fallback now captures grants via `pg_class.relacl` + `aclexplode` and re-issues them. **Not `information_schema.role_table_grants`** — that is restricted to rows where the connecting role is grantor or grantee and would silently miss a grant a separate admin role issued, confirmed by live experiment. Re-grant, never a new privilege decision, so it does not conflict with [`docs/adr/0004`](docs/adr/0004-provision-database-issues-no-grants.md) — which names this row as the accepted fix |
| ~~T-14~~ | Two tools selected their corpus from production by recency | **Closed 2026-08-03.** Checked first whether `evals run` already covered them: it does not, quite — a frozen fixture carries `job_facts` and `match_score`, never `job_scores.fit_score`, so neither tool's *other* job (comparing a candidate against today's live score) has an evals equivalent. Neither of the row's two literal options fit, so the fix is what they share: both now sample `evals/fixtures/corpus-v1.jsonl`. The live-comparison half is inherently live and stays |
| ~~T-15~~ | `learned-ranker-probe.py` trained and evaluated on the same layer | **Closed 2026-08-03, third option — stated rather than fixed.** Building a real L0 evaluation was ruled out rather than attempted: `OQ-3`'s overlap set is 10 rows, below the threshold this repo's own rule forbids tuning on, so a cross-validated number today would be the confident wrong answer the file's other guards exist to prevent. Instead a **WHAT THE VERDICT IS NOT EVIDENCE OF** section, printed at the top of every run. The script cannot run on a clean checkout (numpy/sklearn absent by design), so `py_compile` is what verified it |
| ~~T-16~~ | f-string SQL identifiers | **Closed 2026-08-03.** The row's own count was wrong and re-deriving it was the first finding: **113 sites, not "roughly 25"**, and every one was read rather than assumed. None builds identifier or clause text from a request parameter, a config value, or ATS/employer/labeller data. No site used `psycopg.sql.Identifier` because every constant is a Python name, never a runtime string. The convention and the `# noqa`-placement gotcha are now in [`.claude/rules/sql.md`](.claude/rules/sql.md) |
| ~~T-17~~ | No type checking anywhere | **Closed 2026-08-03.** `mypy` in `.venv-dev`, scoped by config to `lib/`, `schema.py`, `match.py` with `follow_imports = "silent"` — "do not type the tree" as a checkable config rather than a sentence. Private helpers deliberately unannotated, since mypy skips an unannotated body entirely; that default is restated explicitly so a future release cannot silently widen the claim. Two real findings, both fixed rather than suppressed. The CI job is **blocking**, unlike `ruff`'s baseline step |
| ~~T-18~~ | 305 drifted citations in the baseline | **Closed 2026-08-03.** 305 → 3, across six commits. The last 3 are **false positives the checker's design cannot avoid**, each confirmed individually rather than left as an unexplained floor. **One correctness bug found along the way, in citations this row had already "fixed":** the checker skips a `git show <ref>:<path>` citation before the line-range check, so a tag-wrapped citation to a line past the end of the file resolves as cleanly as a correct one — caught by reading content, not by the tool. Now recorded in `backend/tools/audit-citations.py`'s docstring |
| ~~T-19~~ | This project had never been stood up from nothing, and CI proved it | **Closed 2026-08-03.** The DDL was spread across five functions in four modules and nothing invoked all five; every green webapp suite until then had depended on a `public` schema provisioned by hand on one machine over months. `backend/tools/provision-database.py` now invokes all five in the one order that works, and CI runs it before the suites. **No GRANTs, deliberately** — [`docs/adr/0004`](docs/adr/0004-provision-database-issues-no-grants.md). It carries one hazard, stated at the top of the file: step 3 DROPs the view on a column reorder (`T-13`) |
| ~~T-20~~ | A Google Jobs id migration, dry-run-verified 2026-07-25 and never run | **Closed 2026-08-03.** Preconditions checked immediately before `--apply`: `pgrep -af score.py` empty, fresh backup taken. The dry run matched the row's own 9-day-old numbers exactly — no drift. `SELECT count(*), count(DISTINCT source_id)` returned `(1320, 1320)`; a re-run reported `nothing to do`, confirming idempotency. `--keep-stats` was deliberately not passed: the truncated table measured SerpApi cache expiry under the broken key, not real novelty |
| ~~T-21~~ | Static assets carried no `Cache-Control`, so Cloudflare could serve a stale `app.css` for 4 hours after every deploy | **Closed 2026-08-05, origin-side.** `frontend/serve.py` wraps the `StaticFiles` mount at the ASGI `send` layer rather than going through `file_response`, which would have missed the header on a conditional-GET 304. The CDN half — Cloudflare rewriting `app.css`'s header regardless of origin — needed dashboard access no session has, and split to `DEV_TASKS.md`'s `OQ-23`, closed the same day |
| ~~T-22~~ | Turn a Builder's background paragraph into a persona | **Closed 2026-08-05.** `backend/tools/persona-from-background`, one LLM call, validated against `profiles.validate` and `score.build_prompt` with three real postings. **Stops deliberately short of any UI, any storage and any database write** — in particular it must not create a `personal` row in `profiles`, which would put a new profile in front of `extract.py` and `match.py` every night. Model and base URL are parameters, not hardcoded: hardcoding one is how this codebase lost a model it relied on before. Its six sibling decisions are [`docs/adr/0005`](docs/adr/0005-personal-scoring-layer-annotates-only.md) |
| ~~T-23~~ | Six onboarding fields collected from every Builder and read by nothing | **Closed 2026-08-05, scoped to the four the row said would resolve.** The shape chosen: a **read-time `WHERE`, never a `match_score` adjustment** — mirroring the file's own existing pattern, so `job_matches` still holds exactly what `match.py` wrote. Each filter is **permissive on absence**: `comp_floor` excludes only a posting with a known `comp_max` below it, never an unpriced one. A Builder who answered nothing still sees everything |
| ~~T-24~~ | Three places in the code said the cohort narrative budget was zero, and it was 200 | **Closed 2026-08-05.** A `plan-verifier` pass found the row undercounted: **seven sites, not three**, two of which spelled it differently than the row's own grep. Each now points at the `profiles` table for the live number rather than transcribing `200` into a comment that would drift the same way. It also expired `OQ-8`'s "dead code anyway" premise and surfaced a live consequence as `OQ-22` rather than folding a decision in silently |
| ~~T-25~~ | `tools/ats-discover.py`'s circuit breaker tripped on most nightly runs, against the same WAF-protected employers | **Closed 2026-08-05.** All 30 blocked rows had been reprobed at least once; none of the 96-row unresolved pool held a never-probed row. **Decision: retire, not reroute** — a host still blocked after 3 probes leaves the nightly selection pool, because it never answered differently across three separate due-cycles. The rejected alternative kept probing hosts confirmed to refuse every request forever, which is the politeness mistake the file's own rules already forbid. **Nothing is silently dropped:** the row stays in the table and the report breaks the count out explicitly |

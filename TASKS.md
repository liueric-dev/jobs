---
kind: rolling
written: 2026-08-03
generator: none
subject: .
budget: 500
---

# Session tasks — everything a session can do without the owner

**This file owns the prefix `T-`.** One allocator. **The next free number is `T-44`.** Numbers are
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

**Everything before `T-31` is closed** — the toolchain rows, the five harness layers, the
§ 4a defects, `0007`'s two server-side rows and the three worker rows under them — and each is one
line in the table at the foot of this file. `T-1` and `T-2` were the
reason for the original ordering: they are the enforcement layer every later row leaned on, and what
makes a session's claims checkable without hand-transcription. Everything since runs against CI
rather than against a transcribed count.

**The ten open rows are one project, not a queue.** They cut
[`docs/adr/0007`](docs/adr/0007-contributor-credential-opt-in-scheduled-worker.md) into buildable
steps and are listed in dependency order, not priority order: the server side is done, the worker
can be installed and it can now report on itself, so `T-31` — the poll interval, and the last of
the worker — is what nothing on a contributor's machine works without now; `T-32`
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
worker — is the one that decides whether `T-27` … `T-30` were worth building. `OQ-30` blocks
`T-27`'s mint, which 503s until the operator generates `JOBS_MINT_SHARED_SECRET` and puts it in
both `.env` files — and `OQ-31`, filed by `T-30`, is blocked behind it in turn: the one branch of
`--check` no session can exercise needs a credential that mint has not issued yet.

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

### T-41 — The dictated interval reaches the worker and stops there; nothing can move the schedule

**BLOCKED on `DEV_TASKS.md`'s `OQ-32`, 2026-08-08 — the route is an owner decision, and the
evidence that would settle it does not exist on any machine a session can reach.** The two routes
below differ on one property: whether a scheduled run survives unloading the agent that is running
it. No test in this tree can observe that. The only `launchctl` any test sees is
`api/tests/test_worker_install.py`'s `Recorder`, whose docstring says answering 0 to everything "is
not a claim that launchctl would" (`:76-78`) and whose `test_what_it_asks_launchctl_to_do` says no
test on this machine can assert launchd accepts anything (`:250-252`); `cli()` refuses `--install`
off Darwin (`backend/api/contributor-worker/google-serpapi-worker.py:806`) besides. **Route (b)
built here would be green by construction** — the fake returns from `unload` instantly and never
stops its caller, the precise opposite of the hazard — and its failure mode is thirty volunteers'
machines silently unscheduled with no run left to report it. `OQ-32` carries the analysis, the
ten-minute experiment on a Mac that answers it, and a third option neither route names. **Do not
pick a route from this row.**

`T-31` closed with the server's interval read, floored and reported, and with the honest limit
printed rather than hidden: the OS owns the schedule (`0007` decision 2), so the cadence that
actually fires is the `StartInterval` written into the plist at `--install`
(`backend/api/contributor-worker/google-serpapi-worker.py:427`). **What `T-31` could not do, and
said so instead of faking, is make a changed interval take effect.** `install_agent` takes its
interval from `MIN_POLL_INTERVAL_SECONDS` and from nowhere else
(`backend/api/contributor-worker/google-serpapi-worker.py:450`), so an operator who sets
`POLL_INTERVAL_SECONDS` to six hours gets thirty machines that *report* the ask and keep polling
hourly — and re-running `--install`, which is what a Builder would try, writes the floor again.

**So the control layer `0007` decision 3 describes is half-built, and the half that is missing is
the half that changes anything.** Pause, resume and cadence changes still need a hand on each
machine, which is the property the decision exists to remove.

**Two ways to close it, and they are not equivalent.** Either `--install` learns the server's
interval (one claim call at install time — but `T-30` specified `--install` to spend nothing and
`--check` to be the thing that talks to the server, and an unreachable server would then break an
install that has no need of one), or a run rewrites the plist when the ask has changed (no new
network call, but a scheduled run unloading and reloading the agent that is running it, which is
the launchd hazard `report_poll_interval`'s docstring already describes,
`backend/api/contributor-worker/google-serpapi-worker.py:272`). **Pick deliberately; do
not build both.**

**That attribution was wrong as written and is corrected above, 2026-08-08.** The row credited the
hazard to `T-29`'s `install_agent` docstring; that docstring (`:452`) describes a *different* one —
replacing the plist underneath a **loaded** job leaves the old schedule running, which is why
`install_agent` unloads first. The self-referential hazard, a run unloading the agent running it,
was written by `T-31` in `report_poll_interval` and is a claim about the route this row declines to
pick, not about the code that exists.

**Done when:** an operator can change `POLL_INTERVAL_SECONDS` on the server and have a machine
actually fire on the new cadence, with the launchd hazard the chosen route carries either avoided
or pinned by a test, and with the worker's report updated so it no longer describes a schedule
nothing can move.

---

### T-42 — Six citations into `api/app.py` point at lines that no longer carry the claim

`T-40`'s blindspot, found again in five more places while closing `T-31` and **not swept into it**.
Each resolves, so `tools/audit-citations.py` prints `0 new` and cannot see any of them; each was
checked by reading the target, and each was already wrong at `5638ad3` — none is `T-31`'s drift,
which was corrected in the same commit that caused it.

| citation | what it claims | what `:N` is today | where the claim actually lives |
|---|---|---|---|
| `backend/webapp/label.py:25` → `api/app.py:159` | bearer tokens hashed in `api_keys` | a blank line | `authenticate()`'s hash, `:209` |
| `backend/webapp/label.py:84` → `api/app.py:284` | a hostile body rejected before parsing | a blank line | `:460`, the `MAX_BODY_BYTES` test |
| `backend/evals/labels.py:374` → `api/app.py:82` | the service holds no CREATE rights | `db()`'s docstring | `verify_schema()`, `:99` |
| `docs/STATE-OF-THE-SYSTEM.md:221` → `backend/api/app.py:82` | `verify_schema()` | the same docstring | `:99` |
| `DEV_TASKS.md:497` → `backend/api/app.py:549`, `:551` | `release` authenticates before testing ownership | a comment and a blank line | `:580`, `:582` |
| `TASKS.md:259` (`T-35`) → `backend/api/app.py:204` | the endpoint `T-35` is about | `authenticate()`'s Bearer test | read the row before deciding |

**The right-hand column is today's file, and `T-31` moved it.** `T-31` added 16 lines above
`db()`, so every number here points 16 lines further from its claim than it did at `5638ad3` —
but each was **already** wrong there, checked line by line against that commit, so none is `T-31`'s
drift and none was corrected by it. `T-31`'s own four drifted citations were fixed in the commit
that caused them.

**`T-35`'s other citation is worse and is the reason this row is not just tidying**: it cites
`backend/api/app.py:260` for "`claim` deliberately writes no `submission_log` row when it grants
nothing", and `:260` is a docstring line inside `MintRequest`. `T-31`'s row carried the identical
wrong citation, so the number was copied between rows rather than read — a session starting `T-35`
from it would be reading the mint endpoint while implementing against the claim one. `plan-verifier`
caught it on `T-31`; nothing would have caught it on `T-35`.

**Done when:** each citation names the line that carries the behaviour it describes, the checker
still prints `0 new`, and nothing new is added to `config/citation-baseline.json` to achieve it.
**Do not generalise this into a content checker** — same reasoning as `T-40`.

**Closed 2026-08-08.** All six corrected, each target read before writing the number rather than
computed by adding `T-31`'s 16-line offset: `webapp/label.py:25` → `:209` (`authenticate()`'s
`sha256`), `webapp/label.py:84` → `:460` (the `MAX_BODY_BYTES` test), `evals/labels.py:374` → `:99`
(`verify_schema()`), `docs/STATE-OF-THE-SYSTEM.md:221` → `:99`, `DEV_TASKS.md:497` → `:580`/`:582`
(`authenticate()` then `holds_claim`), and `T-35`'s pair → `:380`/`:383`. **The offset was a
coincidence, not a method** — three of the six moved by other amounts, which is why each was
resolved by reading.

**Two things the row did not predict.** First, `docs/STATE-OF-THE-SYSTEM.md:221` carries **three
more** `app.py` numbers in the same sentence (`:143`, the column loop `:143-154`, the raise
`:156-161`); a sentence whose parenthetical exists to correct one number cannot be left half
renumbered, so all four moved together — `:99`, `:160`, `:160-171`, `:173-179`. Second, **`T-35`'s
claim is true but its reason had changed underneath it**: `claim` writes one `submission_log` row
**per query it hands out** (defect D41, `backend/api/app.py:371`), so "no row when it grants
nothing" now holds because zero granted is zero rows, not because `claim` never writes — which is
what the pre-D41 code did, and what `claims_today`'s docstring (`:221`) exists to explain. A `T-35`
session reading only the old citation would have inherited the pre-D41 model of the endpoint. Both
are written into the `T-35` row itself, where the next session will be standing.

**One finding filed rather than swept: `T-43`.** Two citations to
`docs/STATE-OF-THE-SYSTEM.md:443-448` point at the annotator-ceiling paragraph, not the claim they
name; both live in `docs/adr/`, which is frozen on write, so neither is this row's to edit.

---

### T-43 — Two `docs/adr/` citations name the wrong paragraph, and the files are frozen

Found while closing `T-42`, in the one place `T-42` could not fix. `docs/adr/README.md:20` and
`docs/adr/0002-task-51-deleted-instead-of-git-mv.md:54` both cite
`../STATE-OF-THE-SYSTEM.md:443-448` for "every high-severity finding was a document describing a
state of the world that had since changed — not one had ever been false when written". **That
paragraph is at `:459-464` today**, and `:443-448` is the inter-annotator ceiling — a different
subject entirely.

**It was already wrong before this session and is not `T-42`'s drift.** At `f185642` the claim sat
at `:457-462` and the citation still read `:443-448`, so it was 14 lines out on arrival; `T-42`'s
own edit to `:221` added two lines above it and made that 16. Neither number was ever right.
`tools/audit-citations.py` cannot see it — the range resolves, and the tool checks only that, which
is `T-40`'s blindspot for the third row running.

**Why this is its own row: `docs/adr/` is frozen on write** (`.claude/CLAUDE.md`, "one file per
decision, frozen on write"). A citation is not a decision, so correcting one is arguably outside
what the freeze protects — but the freeze has no stated exception, and inventing one in passing
while closing an unrelated row is how a convention stops meaning anything. **Decide what the freeze
covers first, then edit.** If the answer is that it covers the argument and not the bookkeeping,
say so in the commit and fix both lines; if it covers the bytes, the correction belongs in a new
ADR that supersedes, or nowhere.

**Done when:** the freeze question has an answer written down, the two citations are consistent with
it, and `tools/audit-citations.py` still prints `0 new`. **Do not add either line to
`config/citation-baseline.json`** — both resolve today, so the baseline cannot express the problem
and adding them would record the opposite of what is wrong.

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
when it grants nothing (`backend/api/app.py:380`), so check-in needs its own record; do not meter it
as a claim, or an honest idle poll starts consuming the daily allowance
(`backend/api/app.py:383`).

**Both citations were corrected 2026-08-08 by `T-42`, and the first pointed somewhere actively
misleading.** They read `:260` and `:204`: `:260` was a comment line inside `MintRequest`, so a
session starting this row from it would have been reading the **mint** endpoint while implementing
against the **claim** one, and `:204` was `authenticate()`'s `Bearer ` test. The claim itself holds,
and the real target argues it better than the row does — `claim`'s docstring makes the
grants-nothing case explicitly ("A request that is granted NOTHING writes nothing, deliberately",
`:380`) and gives the reason this row's check-in must not be metered as one: charging for an empty
poll "would make 'the bank is fully fresh today' indistinguishable from abuse and would exhaust an
honest cron's daily allowance on the (common) days there is no work" (`:383`). **Read the
neighbouring paragraph before building**: `claim` writes one `submission_log` row **per query it
hands out** (defect D41, `:371`), so zero granted means zero rows — it is not that `claim` never
writes, which is what the pre-D41 code did and what `claims_today`'s docstring (`:221`) exists to
explain.

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
| ~~T-31~~ | `0007` decision 3 had no wire: the server held a cadence it could not say, so pause, resume and every interval change meant a hand on each of thirty machines **Closed 2026-08-08.** The claim reply carries `poll_interval_seconds` (`backend/api/app.py:428`, from `POLL_INTERVAL_SECONDS` at `:71`) and the worker floors it with `clamp_poll_interval` (`backend/api/contributor-worker/google-serpapi-worker.py:231`). **It is carried on the granted-nothing reply too, which is the case that matters**: the bank is fresh most days, so that is the ordinary answer, and a machine with no work is exactly the one an operator wants to slow down — attached to the queries it would reach quiet contributors never. The worker reads it *before* the nothing-to-do exit for the same reason, and a deliberate breakage moving that line below the exit turned the real-socket case red. **The clamp inherits `T-29`'s constant rather than declaring a second floor**, as that row's comment asked: `clamp_poll_interval` floors against `MIN_POLL_INTERVAL_SECONDS` (`:181`) and `build_launch_agent` schedules on it (`:427`), and a test asserts they are one constant and not two that agree — two floors that drift apart is a worker polling on one number and scheduled on another, which nothing would report. **The direction is pinned in both directions, separately**, because either case alone passes a `min()`: 10 seconds is raised to the floor, six hours is returned unchanged, and rewriting the clamp as a ceiling turns eight cases red. Absence, a string, a negative, `NaN`, infinity and `True` all land on the floor — absence silently, since a server predating `0007` sends nothing and must behave exactly like an install that never heard of an interval, which is what lets the two ends deploy in either order. **`True` is excluded by hand** because `bool` is an `int` in Python and `max(True, 1)` is `1`. **The row's "say so" clause is the printed line, and it is printed only on the disagreement** — the ordinary machine, where ask and schedule agree, stays silent, because a line per run about a cadence that did not change is noise in the one log a Builder reads for failures. It names the schedule as a schedule and not a fault, which is the failure the row named: a paused worker read as a broken one. **21 cases in `api/tests/test_poll_interval.py`, and four deliberate breakages confirmed they bite** — the clamp as `min()`, the server renaming the key, the read moved below the early exit, and the worker ignoring the reply — each turning exactly the expected test red. **The real-socket case was written wrong first and the mutation found it**: the stand-in spelled `poll_interval_seconds` itself, so a rename on the server end sailed straight past the one test whose whole premise was catching that. It now serves `app.claim()`'s own dict, and the rename turns it red. **Also run against the real FastAPI app under uvicorn on a real socket** with the real worker as a subprocess: `10` came back over the wire and was silently floored, `21600` came back and was reported as `every 360 minutes`. **`--check` was not touched**, so `T-30`'s exactly-three-requests assertion needed no edit — the interval rides on a reply `--check` never asks for. **What this row could not do is make the interval take effect**: the OS owns the schedule and nothing here rewrites the plist, so the report is honest about a cadence it cannot move — filed as `T-41` rather than half-built. Citations this row's own edits drifted were corrected in the same commit (three into `app.py` from the worker, one from `test_worker_check.py`); six that were already wrong at `5638ad3` were filed as `T-42`, not swept. Two findings filed: `T-41`, `T-42` |
| ~~T-30~~ | `0007`'s fourth guess at where onboarding friction lives: a Builder whose worker does nothing had no way to find out which of three things was wrong, and no way to ask that did not cost them a search credit | **Closed 2026-08-08.** `--check` prints one line per check and exits non-zero on any failure (`backend/api/contributor-worker/google-serpapi-worker.py:651`, flag at `:706`): the base URL answers at `/v1/health` (`:504`), the credential is accepted (`:540`), the SerpApi key is accepted (`:602`). **The credential is checked by offering to release a claim nobody can hold, and the 409 is the pass** — every authenticated route on that server *does* something, and `/v1/queries/claim` locks rows out of the pool and meters the caller against a daily cap (`backend/api/app.py:345`), so checking a credential with it would spend the allowance being checked and, on a stale day, lock real queries for a worker that was only asking a question. `release` authenticates first and tests claim ownership second (`backend/api/app.py:549`, `:551`), so a dataset the query bank cannot name reaches the credential check, writes nothing and commits nothing. **That ordering is now pinned from the server's side** in `api/tests/test_worker_check.py`'s `TestTheServerSideOfTheProbe`, because reversed it would tell a Builder with a good credential to go and ask for a new one. **An unreachable base URL reports the credential as `not checked`, never as bad** — the row's distinguishability clause, and the failure that would send a Builder to replace a key that was fine. **`--check` is deliberately NOT in `T-29`'s mutually-exclusive scheduling group**: it changes nothing, it works off a Mac, and it is what you run when one of those two went wrong; combining it with either is refused in a sentence rather than by argparse's grammar. `T-29`'s `test_an_unknown_flag_is_refused_rather_than_ignored` was rewritten, not deleted — its example moved from `--check` to a flag nothing intends to build, since what it pins is the parser refusing what it does not know. **Two halves, and only one of them is ours to verify.** Ours, asserted for real: no request `--check` makes is a SerpApi *search*, checked as an assertion over every URL it sends, plus the account endpoint pinned as a literal rather than as the constant (written from the constant first, it stayed green under exactly the edit it forbids). Not ours: the far ends. **One clause was met against the live endpoint and one was not.** SerpApi's account endpoint was called with the pipeline's own key before and after a real `--check` run: `this_month_usage` and `total_searches_left` were identical across it, so the check cost no credit — but the account is at 250/250 with 0 left, so the strong form of the row's before-and-after (a positive count that does not move) needs an account with credit and is `OQ-25`'s. The `409` pass path was never exercised against a running server: that needs a minted credential, which needs `OQ-30`'s secret — filed as `OQ-31`. **The live run is what found the one real bug**: `probe` truncated every body to 400 characters *before* parsing, SerpApi's account answer is longer than that, and a perfectly good key came back as "answered 200 with something that is not JSON" — invisible to all 38 scripted cases, whose fixtures were short. The body now comes back whole and truncation happens where it is printed (`:477`), with a case whose fixture is deliberately over 400 characters. Nothing prints a credential: bodies pass through `redacted()` (`:461`), the SerpApi URL — which carries the key as a query parameter — is never printed, and a test asserts both. 39 cases, and **seven deliberate breakages confirmed they bite** — the account endpoint swapped for `/search.json`, a 401 read as a pass, redaction removed, the probe pointed at `/claim`, the server's two checks reversed, `--check` moved into the scheduling group, and an unreachable server reported as a bad credential — each turning exactly the expected test red. Also run against a real socket, not only against a scripted stand-in. **The row's own worked example was stale and `plan-verifier` caught it**: it claimed `--check` exits 1 with the unset-settings message, but `T-29` landed a parser under it after the row was written, so it had been exiting 2 from argparse; its `app.py:255` citation for `/v1/health` had drifted to `:269` the same way. **The criterion this row declined to invent is still not invented**: whether the output means anything to a reader is `OQ-25`'s. One finding filed: `OQ-31` |
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

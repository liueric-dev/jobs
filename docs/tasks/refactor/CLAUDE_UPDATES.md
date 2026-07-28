# Run log — `docs/tasks/refactor/`

Progress updates from the agent run through tasks 03–34, appended as work lands.

This is the *what happened* log. The *why this choice* log is
[`DECISIONS.md`](DECISIONS.md) beside it, and the two are deliberately separate: a
decision outlives the run, a status update does not. The ordered index of tasks and
their `todo`/`done` state stays in [`README.md`](README.md).

Newest entries at the bottom. **Session handed off 2026-07-28 at `5092568` — see
[`HANDOFF.md`](HANDOFF.md) for where to pick up.**

---

## 2026-07-28 — run started

**Base:** `36d83f5`, branch `webapp-service`. Suite green at **267 tests** (the task
files say 263; it has grown since they were written, and the floor for this run is
267, not 263).

**Already committed before this run:** 01 (`28f1d0e`, production model pinned),
02 (`36d83f5`, `docs/ingest/DEFECTS.md`, 41 entries).

**Scope:** tasks 03–34, in dependency order, going as far as the graph allows.

### How this run is structured

One task per subagent, started cold, so no task inherits another's context. The
orchestrator verifies each Definition of done against the files, commits, and appends
here. Nothing is committed by a subagent.

Durable state, because the orchestrator's context is compacted several times across 32
tasks: this file, `DECISIONS.md`, `README.md`'s status column, and one commit per task
prefixed with its number. Those four reconstruct the run state exactly if context is
lost.

### Two walls this run is expected to hit

Neither stops the run — the work routes around them and reports at the end.

**Credentials that need an account:** 15 (USAJobs authorization key, Adzuna
`app_id`/`app_key`), 20 (Firecrawl), 24 (Builder key onboarding), 33 (Cloudflare
domain), and 14's optional Socrata app token — 14 can run anonymously and throttled
in the meantime.

**Human judgement that cannot be substituted:** 07's golden set, 29's labelling
session, and 30 behind them. This is load-bearing rather than procedural — Axis B *is*
Builder preference, so a model standing in for it makes the measurement circular. That
is the exact defect `docs/ingestion_tests/03-metrics-and-golden-set.md:13` names in
`claude-bench.py:417`, which treats `sonnet-batch-1` as ground truth. 07's *tooling*
gets built; only the labelling stops.

### Amendment carried into task 04

Task 04 asks for a requests/minute ceiling "observed, by pushing until throttled."
Dropped, on the repo owner's instruction: the DeepSeek limit is a known 2,500-concurrent
ceiling rather than a daily cap to be discovered, and probing it would risk the nightly
`run-daily.py` window for a number already in hand. It is recorded as a documented
figure with its date and source instead, which still satisfies the task's requirement
that the limit live in the repo rather than in someone's memory.

### Started, both now landed

| task | state |
|---|---|
| 03 — stop discarding upsert errors | **done** |
| 05 — corpus volume under a widened gate | **done** |

Started in parallel: their file sets are disjoint (03 is `backend/lib/`, `ingest/`,
`api/`, `run-daily.py` and tests; 05 adds one document and reads the database).

Two things are being proven rather than asserted, because both fail silently:

- **03** — whether `lib/`'s byte-parity constraint is still live at all.
  `tools/lib-parity.sh` does not exist in the repo and
  `backend/tests/test_lib_contract.py:5` records that `lib/` "used to be a shared
  package and is now this repo's own code." CLAUDE.md appears stale here. It decides
  whether `upsert_checked` lands in `lib/upsert.py` or in the task file's awkward
  `backend/ingest/_common.py` fallback — and two of the eight call sites are in
  `backend/api/`, which cannot import from that fallback cleanly.
- **05** — a positive control on the `\y`-not-`\b` landmine: run one pattern both ways
  and confirm the `\b` form returns zero. Without it, "we used `\y`" is an assertion
  rather than evidence, and a `\b` pattern's silent zero is indistinguishable from a
  genuinely small number.

Also worth noting from the planning pass: task 03's own file names four call sites and
tells the implementer to audit for more. Task 02 already did that audit — `DEFECTS.md`
D01 lists **eight**. The subagent was given the list rather than left to rediscover it.

---

## 2026-07-28 — 05 landed: **N = 43/day**, and the task's premise was wrong

Deliverable: [`docs/pursuit-gate-volume.md`](../../pursuit-gate-volume.md). Read-only,
SQL only, no LLM calls, nothing tuned.

| quantity | value |
|---|---|
| tier-3 rows matching AI vocabulary | 2,975 (of 6,489 tier-3) |
| …also entry-level signalled | 659 |
| …also NYC or remote | 407 |
| **new per day, 30-day mean** | **43** (2026-06-28 … 2026-07-27) |
| by platform | greenhouse 2,019 · ashby 657 · google_jobs 142 · builtin 94 · wwr 50 · hn 13 · lever 0 |
| hand-checked precision, n=30 | 6.7% (2 genuine) |

**Verified independently before committing**, not taken on trust: tier distribution
(2,975 / 2,360 / 6,489), the tier-3∩AI count, and the 30-day total re-run from the
orchestrator against the same database. The one-row difference (1,285 vs the report's
1,284) is the table moving between the two runs. `N` = 43 either way.

The `\y` positive control passed: `\yllm\y` → 1,127 rows, `\bllm\b` → **0**, no error.
A second trap in the same family turned up — unescaped `make.com` matches 116 rows
against 2 for `make\.com`, a 58× inflation from the wildcard dot, in the opposite
direction to the `\b` silence.

### Three findings that change later tasks

**1. The bottleneck is sourcing, not gating.** The task file is scoped on a premise
that no longer holds — see the `05` entry in `DECISIONS.md`. `title_include` has 34
terms now, not the 12 the task lists, and already includes `\yai\y` and `\yllm\y`. Of
43 titles carrying both entry-level and AI signals, 34 are *already* at tier 1/2 and
only 9 are at tier 3. The target population is not parked behind the gate; there is
barely any of it in the corpus. **Task 10 should not be expected to unlock a hidden
corpus, and task 04 must not size against one.**

**2. The junk is company boilerplate, not the failure mode anyone predicted.** 93% of
matches are wrong, but not because `automation` and `machine learning` pull in
manufacturing and ML research — that barely appeared. Pinterest ships "At Pinterest, AI
isn't just a feature…" in the header of *every* posting, so every Pinterest req matches,
including *Sr. Client Account Manager*. Brex, Braze, Notion, Wiz, ElevenLabs, Anthropic
and OpenAI all do the same. **The pattern selects for the employer being AI-ish, not
the role** — which inverts its intent. Corroborated at population scale: only 4.3% of
the 2,975 have any AI signal in the *title*, against 6.7% hand-checked. The two agree.
This is the baseline task 10 starts from, and a description-only gate on this
vocabulary must not ship as-is.

**3. Tier 3 is where the spam was deliberately parked.** 133 of the 2,975 come from the
six relisters in `company_exclude` and 104 contain the literal `reputed company` from
`description_exclude`. They are at tier 3 *because* those lists demoted them. **Raising
`max_tier_to_score` to 3 re-admits everything the exclusions were written to
suppress** — so task 04's throttle decision and task 10 both need those exclusions kept
as a separate gate rather than folded into tier.

Also: the platform value is `builtin`, not `builtin-nyc` as the task files write it;
`gemini` matches Gemini the crypto exchange (26 of 90 rows); Google Jobs is only 4.8%
of this population, so it is not currently a meaningful source of it either — 90% is
greenhouse + ashby alone.

`N` is now referenced from `04-quota-baseline.md`, closing that task's last Definition
of done item.

---

## 2026-07-28 — 03 landed: all eight call sites, 267 → 280 tests

`upsert_checked()` in `backend/lib/upsert.py`, and every one of the eight sites from
`DEFECTS.md` D01 converted — including the two the task file did not name
(`api/app.py`, `api/query_claims.py`) and the two that were not three-tuple unpacks at
all (`hn-hiring.py` read `.new` only; `query_claims.py` also omitted `debug=`).

**Verified by the orchestrator before commit**, not taken on trust:
`grep -rn "= upsert(" backend/` leaves only comments, docstrings and
`upsert_checked`'s own internal call; suite 280 passing, up from the 267 floor.

Three things worth knowing beyond the diff:

**The `lib/` parity constraint is dead, and CLAUDE.md is stale about it.** The task
file offered `ingest/_common.py` as a fallback "if `lib/` must stay byte-identical",
and CLAUDE.md asserts that constraint with `tools/lib-parity.sh` reporting drift. That
script does not exist in the repo, and `lib/__init__.py` and
`tests/test_lib_contract.py:5` both record that `lib/` is now this repo's own code. The
helper therefore went where it belongs. **CLAUDE.md's parity rule needs correcting in
task 34.**

**The threshold is applied at two scopes.** Loop-based scripts check per batch — where
one bad source is survivable and is now counted rather than ignored — and again over
the run total, where it is not. `UpsertErrorRate` carries `.result` because `upsert()`
commits before raising, so the records that succeeded are written and can still be
tallied.

**The nightly summary can now tell the two failures apart.** `run-daily.py` parses the
`upsert-summary:` line every call emits. Steps that never upsert report `-` rather than
`0`, and `unchanged` is deliberately excluded from "written" so a quiet day cannot
disguise a day that dropped everything.

### One change that is visible outside the repo

`POST /submit` now returns `accepted` = records actually **written** rather than
records that merely parsed, adds a `dropped` field, and populates
`submission_log.reason`. Not strictly demanded by the task. Kept because the
alternative leaves the exact defect intact at the API boundary, and the two values
differ only when records were dropped — the case where the old answer was a lie.
`API-CONTRACT-v1.md` freezes the frontend read endpoints only, so nothing frozen
breaks. Called out here because it is the one part of task 03 a client could notice.

### Follow-up left for task 34

`docs/ingest/contributor-api.md:378` documents the `submission_log` row and cites line
numbers that this commit moved. It carries `generated:` frontmatter, and per CLAUDE.md
generated docs are regenerated rather than hand-edited — but no generator script exists
for it. Left alone deliberately; task 34 owns the resolution.

---

## Running backlog for task 34 (documentation cleanup)

Collected as encountered, so 34 does not have to rediscover them. Each is a documented
claim that is wrong about the code as it now stands.

- **CLAUDE.md's `lib/` parity rule is stale.** It states `lib/` is "vendored
  byte-identical to another repo" with drift reported by `tools/lib-parity.sh`. That
  script does not exist anywhere in the repo, and both `backend/lib/__init__.py` and
  `backend/tests/test_lib_contract.py:5` record that `lib/` is now this repo's own
  code. The rule sent task 03 toward an `ingest/_common.py` fallback that two of its
  eight call sites could not have used. **This is the highest-value item here** — it is
  in the file every session reads first.
- **`docs/ingest/DEFECTS.md` undercounted itself.** Prose said "Total: 41 entries"; the
  register contains `D01`–`D42`, verified unique and gapless. Corrected in this run.
  The README's "42" was right all along.
- **`docs/ingest/contributor-api.md:378` cites line numbers that task 03 moved**, and
  documents a `submission_log` row whose `reason` column is now populated. The file
  carries `generated:` frontmatter, so per CLAUDE.md it should be regenerated rather
  than hand-edited — but **no generator script exists for it**. 34 needs to decide
  whether these files get a real generator or lose the frontmatter that claims they
  have one.
- **Task files describe a `relevance.json` that no longer exists.**
  `05-widened-gate-volume.md:13-20` lists 12 `title_include` terms; there are 34. Any
  later task scoped on that description inherits the error — 10 and 13 are the ones at
  risk.
- **The platform value is `builtin`, not `builtin-nyc`**, as several task files write
  it.
- **`docs/ingestion_tests/05-fetcher-harness.md` has no Definition of done**, but
  `09-fetcher-harness.md` inherits from it by reference. Being resolved inside task 09.

---

## 2026-07-28 — 04 landed, and the answer was not a quota

The sentence the task asked for:

> **At 43 eligible postings/day, the nightly extraction pass takes 0.03 hours and
> consumes 0.1% of what actually binds — 3 of the provider's 2,500 concurrent
> requests. There is no daily request ceiling to consume.**

It is not the headline. The headline is what the measurement turned up underneath:

> **The pipeline cannot process 43/day.** `EXTRACT_BATCH_SIZE = 40`
> (`extract.py:70`) and `run-daily.py` invokes `extract.py` exactly once, so the
> ceiling is **40 postings a night** regardless of how fast a call is. At 43/day the
> backlog grows 3/day. At 80/day — what the last seven complete days actually ran —
> it grows 40/day, forever.

**Verified independently:** `EXTRACT_BATCH_SIZE=40` with nothing overriding it in
`.env`, and `extract.py` appears exactly once in `run-daily.py`'s `STEPS`.

The pipeline is throttled by a constant three orders of magnitude below anything the
provider or the clock imposes. Task 04 was scoped to find out whether quota or
wall-clock binds. Neither does.

| measured | value |
|---|---|
| extract wall-clock | 7.7s p50 / 13.1s p95 per call; 2.85s/call effective at `EXTRACT_MAX_WORKERS=3` |
| provider concurrency | 2,500 — **operator-stated, not measured**, dated in `SCORING.md` |
| daily request ceiling | none published |
| calls made | 84 for the table (60 extract + 24 narrative); 173 billable on the day |
| corpus | frozen `corpus-v1.jsonl`, 120 records, pinned model, temperature 0 |

Two defects fell out of doing the measurement properly. The old `cost-test.py` **built
its own HTTP request instead of going through `llm.call_detailed()`**, so
`ratelimit.acquire()` never applied — it was measuring a system the pipeline does not
run. And it defaulted to one worker, so its latency figures were never comparable to
the nightly window.

### `max_tier_to_score` stays at 2 — and the reason is not throughput

The config's old note said "set to 3 to open the floodgates once throughput allows."
Throughput now allows. It is still wrong, and the decisive reason is structural rather
than economic:

**`max_tier_to_score = 3` is an unconditional pass, not a wider gate.**
`relevance.py:189` computes `CASE WHEN row_ok AND loc_ok THEN 1 WHEN row_ok THEN 2 ELSE
3 END`, and `:223` admits rows on `tier <= max_tier`. Every row satisfies `<= 3`.
Because `row_ok` folds in `title_include`, `title_exclude`, `company_exclude` **and**
`description_exclude`, that one-character change disables four exclusion lists
simultaneously — 1,906 rows return on `title_exclude` alone (account executive,
recruiter, nurse, controller, VP), plus 182 unique relist-spam rows.

And they return *at the top*: 19 of them already reach `match_score >= 90`, one hits 99
against an LLM fit of 15, because keyword-stuffed titles are precisely what
`title_include` rewards. `MATCH_FLOOR` cannot save this — the junk scores highest, so
the floor filters the wrong end.

Recorded across four `_comment` fields in `relevance.json` in the file's existing
style, including the rejected alternatives and what *would* change the decision (task
10 making the provenance exclusions a predicate no tier number can switch off).

### Consequence: a new blocker nobody had written down

The 40/day ceiling is not any task's responsibility in the current tree, and it
invalidates the sizing in several. Raised as a follow-up rather than fixed here —
task 04 is a measurement task and CLAUDE.md forbids tuning during one.

---

## 2026-07-28 — 09 landed: cassettes for all six sources, 400 tests

Phase 3 is now unblocked. `backend/evals/` gains `cassettes.py` (record/replay),
`scratchdb.py`, `ingest_modules.py`, `workday_fixtures.py` and `record_cassettes.py`;
`fixtures/cassettes/` holds nine cassettes with a README. **Suite 400 passing**,
verified by the orchestrator, +73 from this task.

All six existing sources have cassettes — greenhouse (with and without `?content=true`),
lever, ashby, hn-hiring, weworkremotely, builtin-nyc, google-serpapi, google-apify.
**Apify billed nothing**: rather than paying ~$0.15 to start a run, the agent recorded a
historical `SUCCEEDED` one through the free read endpoints. SerpApi cost a single
search. LinkedIn was never touched.

### The task file was wrong about where to intercept

It assumes the ingest scripts fetch through `lib/http.py`. **Four of the six call
`urllib` directly**, so a `lib/http.py` seam would have recorded nothing for them while
appearing to work — a silent-failure shape, in a harness built to catch silent
failures. The seam is `urllib.request.urlopen`.

### The open question, settled with evidence

`05-fetcher-harness.md` asks whether the harness should test concurrency. Answer: yes
for `state.try_claim`, which is *defined* by the concurrent case and guards metered
SerpApi/Apify budgets — if it is wrong, the symptom is a silent double-spend. No for
`lib/upsert.py`, which has no cross-process contract, since `run-daily.py` runs ingest
sequentially as subprocesses.

Settling it turned up something better. What motivated the question was really
transaction isolation, testable without concurrency — and testing it produced **the
first evidence in this repo that the per-record SAVEPOINT actually works**. A
five-record batch with one NOT NULL violation: with the SAVEPOINT, `new=4`, `errors=1`,
four rows stored. Without it, `new=2`, `errors=3`, **zero rows stored** — one bad
record takes all five. That mechanism has been load-bearing and unverified.

### The Workday fixtures are honest about being constructed

All four failure modes are reproduced — `limit` above 20 returning an empty array with
a 200; a 429 at offset 40 of 2,000 (the test asserts the full 1,960-row loss); wd1
versus wd5 host confusion returning 404 HTML; and the 10,000-row cap with a faceted
slice to enumerate past it. They are **built by a module rather than recorded**, because
no Workday tenant is known until task 16, and both the module and its tests say so
rather than passing themselves off as captures.

### Two follow-ups it surfaced

`match.py` still has no per-record isolation (register entry **D20**) and is now
testable for the first time. **D17** is pinned as still-broken with an assertion ready
to flip when it is fixed — a good pattern: the register entry and the test agree by
construction rather than by someone remembering.

Also corrected a comment task 03 wrote in `tests/test_upsert_checked.py`, which said the
ingest scripts "cannot be imported". They can now — `evals/ingest_modules.py` imports
them by path. The conclusion it supported still holds on its own, so the reason was
removed and the conclusion kept.

### One cross-task edit worth flagging

09 added a Definition-of-done bullet to **task 16's file** — requiring a cassette that
covers a token which does *not* resolve, "otherwise the validator is only ever exercised
against the live endpoints it is meant to stop trusting." That is the right bullet, but
16's agent started before it existed, so 16 will be checked against it on landing.

---

## 2026-07-28 — 22 landed: drop JobSpy, and task 23 is now in question

Findings: [`docs/jobspy-spike.md`](../../jobspy-spike.md). **No code merged** — verified,
zero `jobspy` references anywhere outside that document. LinkedIn never queried; every
call passed `site_name=["google"]` explicitly rather than trusting a default.

**Decision: drop JobSpy.** It returns zero rows from this machine — 0/20 queries, zero
exceptions, every request HTTP 200, p50 0.18s. That combination is the tell: it is not
a block. No captcha, no `sorry/index`, no "unusual traffic" interstitial. Google
requires JavaScript for search results, announced 2025-01-17 explicitly to stop
scrapers, and JobSpy parses HTML.

The probe that settles it: a plain web search with no `udm` parameter —
`q=weather new york` — returned the identical JS bootstrap shell. **No query could have
worked**, which kills the "wrong query syntax" explanation upstream offers for this
symptom. JobSpy issue #302 reports the same warning string, open since 2025-09-06.

This is a negative with a documented global cause rather than a "didn't work today"
observation, so confidence is high and no proxy or IP change addresses it. The SerpApi
control was clean — 10/10 results, 30/30 apply URLs — so the vertical is alive and only
the free path into it is dead.

**The spike's own premise went untested and remains open.** The question was whether a
residential IP fares better than a datacentre one. JobSpy never gets far enough for IP
reputation to be consulted.

### This puts task 23 in question, and 05's platform finding needs re-reading

JobSpy was the reason the SERP abstraction looked affordable
(`ADDENDUM-google-jobs-providers.md:73-74`). Without it, every remaining provider is
metered and the router reduces to squeezing eight small free tiers — to grow a source
measured at 4.8%.

**But that 4.8% is not settled, and this is the more important finding.**
`backend/config/google-queries.json` holds 32 queries across `core_swe`,
`ai_integration`, `bridge_solutions` and `reentry_growth`, and **every one is a
software-engineering title** — verified directly: "full stack engineer", "backend
engineer", "LLM engineer", "forward deployed engineer", "software engineer returnship".

Google Jobs contributed few Pursuit-shaped rows because **it was never asked for any**.
The honest statement is "Google Jobs *as currently queried* is 4.8%". Task 05's
conclusion that it is not a meaningful source does not survive that distinction
unexamined — and the spike's own control run returned 10 results with 4,508-character
median descriptions for "barista" in NYC.

**Consequence:** task 23 should not be built or dropped on the current evidence. The
deciding experiment is cheap — re-point the query bank at Pursuit-shaped terms, run
task 05's SQL against the result, compare. Hours, not a package. Raised as a follow-up.

### Minor

The agent reported it could not run the test suite because "pytest isn't installed".
The suite is `python3 -m unittest discover -s backend/tests` and runs fine; its only
change was one markdown file, so nothing was at risk either way.

---

## 2026-07-28 — 16 landed, on the second pass: the first non-tech NYC employers

Report: [`docs/ats-token-discovery.md`](../../ats-token-discovery.md). New:
`backend/ats_discovery.py` (pure, no I/O), `data/nyc-employer-seed.json` (376
employers), `migrations/migrate_company_ats.py`, `tools/ats-discover.py`, and a nightly
`--due-only` step at the head of `run-daily.py`. **Suite 413 → 426.**

`company_ats` is the table tasks 17, 18 and 20 read instead of `config/companies.json`.

### It was sent back once, and the check that caught it

The agent reported itself finished. It was not: the report contained a literal
`## RESULTS_PLACEHOLDER`, and **`company_ats` had zero rows** while 33 employers were
marked `found`. Committing that would have left three downstream tasks reading an empty
table — and "no NYC employer uses an ATS" is exactly the plausible-looking zero this
codebase keeps generating. Verifying against the database rather than the report is
what caught it. Second pass filled both, plus the cassette bullet task 09 had added to
16's file after 16 started.

### 7 validated tokens, 1,513 open jobs, every one non-tech

| employer | sector | ATS | open jobs |
|---|---|---|---|
| NewYork-Presbyterian | health | workday `nyp` **wd1** | 367 |
| Nordstrom | retail | workday `nordstrom` **wd501** | 862 |
| Memorial Sloan Kettering | health | workday `msk` **wd108** | 87 |
| Moelis & Company | finance | workday `moelis` **wd1** | 43 |
| National Football League | media | greenhouse | 66 |
| Per Scholas | nonprofit | greenhouse | 38 |
| PepsiCo | retail | icims | 50 |

This is the direct answer to task 05's finding that the target population is absent from
every configured source. It is also small — 1.9% of the seeded roster — and the reason
it is small is the next section.

**The data-centre column earns itself immediately.** `wd1`, `wd108`, `wd501` — nobody
would guess the last two, and `18-ingest-workday-cxs.md:54` is right that a wrong one
returns a 404 indistinguishable from a tenant with no openings. Task 18 can treat that
as confirmed rather than anticipated.

### The best thing this pass produced is a negative result about itself

The roster carried ten tech employers with tokens **already verified** in
`config/companies.json`, as a positive control. Four were conclusively probed. **The
method found zero of the four.**

`careers.datadoghq.com` returns 139,063 bytes of HTML containing `greenhouse.io`
nowhere. MongoDB's is 564,983 bytes, same result. Their boards render client-side, so
there is no ATS URL in the document a plain fetch receives.

**So `not_found` — 139 employers, the largest bucket — does not mean "this employer has
no ATS".** It means "no ATS URL in the HTML we were served", and on this evidence it is
wrong more often than right. Every coverage figure is a floor. Critically,
`company_ats.validation_note` records that **on the row itself**, so tasks 17, 18 and 20
cannot read those rows as settled fact about the New York labour market.

A discovery pass that had not carried a control would have reported "139 NYC employers
have no ATS" as a finding.

### Silence is not a result — the part that was right the first time

`last_probe_outcome` is one of seven values partitioned into conclusive (`found`,
`not_found`) and inconclusive (`blocked`, `unreachable`, `missing_page`, `no_url`,
`skipped`), with a test asserting the partition is disjoint and complete. **Only a
conclusive outcome may write `never_found`.** Under a boolean, the 30 `blocked`
employers would have become "no ATS here", silently and permanently.

Coverage is quoted over **both** denominators — 1.9% of 366 seeded, 3.6% of 193 probed —
and the tool refuses to print one without the other. The probed-subset figure alone
overstates by 1.9x.

Probing stopped deliberately at 280 of 376: `blocked` climbed 16 → 30 as coverage grew,
and this host also runs the nightly ATS pulls and `google-serpapi.py`. The 96 unprobed
are first in line for the nightly backfill.

---

## 2026-07-28 — the query-bank experiment: Google Jobs works when asked properly

Deliverable: [`docs/google-jobs-query-experiment.md`](../../google-jobs-query-experiment.md).
16 SerpApi searches, exactly at the authorised budget. **No production writes** —
verified: still 11,824 rows, no leftover scratch schemas, `google-queries.json`
untouched.

**Recommendation: build task 23, sharply descoped.** Task 22's challenge to the 4.8%
figure was right.

| | Pursuit-shaped bank | current SWE bank (control) |
|---|---|---|
| hand-checked genuine | **9 / 130 = 6.9%** (CI 3.7–12.7) | **0 / 39** |
| non-tech or government employers | 45.4% | — |
| new to the corpus | 129 of 130 | — |

The control is what makes it credible, and the agent **refused the comparison it was
sent to make**: 4.8% is a share-of-corpus figure and this is a yield, so it built a real
control instead — 30 pinned production `google_jobs` rows plus every one of the 9 rows
in the whole 901-row population carrying both AI and entry-level title signals, same
judge, same criteria. Zero genuine of 39. It also reports the weaker of its own two
statistics: the hand-check contrast is p=0.088, underpowered on the control arm.

**Weakest number, flagged by the agent itself:** 0.56 genuine/search is a *first-run*
rate — none of the 16 queries used a date chip, and no Google Jobs query on either bank
has ever run more than twice, so steady-state daily yield is unmeasured.

### The experiment found a defect in its own authorisation

I approved 16 searches after reading `google_jobs_query_stats`: **41 used this month**,
209 remaining. The SerpApi account read **137 used** — and 153 after. **97 left, not
209.** The repo's ledger undercounts real spend by 3.3x, in the dangerous direction.

Nobody gets an error from this; the ledger simply disagrees with the vendor, and the
first symptom is a month going dark early. It matters directly because task 23's descope
**keeps the quota ledger** — which must reconcile against the provider's counter, not
against rows this pipeline remembered to write.

### Four defects found outside scope, recorded not fixed

1. **Task 05's AI regex is missing bare `\yai\y`, `ai-driven` and `ai-enabled`** — it
   drops 3 of the 9 genuine rows. **Task 10 must not lift it as-is**, which is exactly
   what task 05's document invites.
2. The entry-level regex has no `\yintern\y`, which also affects task 05's own two
   genuine rows.
3. **`google_jobs.py:98-99` discards `detected_extensions.work_from_home`.** Verified:
   the field is read into a local and `work_from_home` appears nowhere else in the
   codebase; `is_remote` comes only from a regex on the location string. All 7 genuinely
   remote postings get both location flags FALSE and sit at tier 2.
4. 45% of rows arrive via aggregators carrying a median **530-character paraphrase**
   against 4,838 elsewhere. That is what `extract.py` is being fed, and it bears on
   task 06's clean-versus-messy split.

### A reprioritisation worth your attention

23 currently blocks 24 and 25. The evidence inverts that: **25 is where the entire 12x
difference lives and it is a config edit**, and **24 is 7,500 searches/month** (30
Builders × 250) against code already written and tested — roughly 8x every free tier in
`SOURCING-STRATEGY.md` combined. 23 lists `contributor.py` as one adapter among eight.
On these numbers it is not one adapter, it is the product. Recorded, not acted on.

Also useful: the **production tier gate is already the best filter for this source**
(74 kept, 8/9 recall, 10.8% precision). Task 05's widened AI-vocabulary gate is worse on
both axes here, and its AI+entry+location composite discards two-thirds of the genuine
rows.

---

## 2026-07-28 — 06 landed: **the gate says stop**

`python3 -m evals selfcheck --repeat 3` now exists, `corpus-v2.jsonl` is frozen at n=120
(115 comparable, all seven platforms), and `corpus-v1.jsonl` is untouched — task 04's
figures cite it. **Suite 426 → 429.** Full results in
`docs/ingestion_tests/selfcheck-n120-2026-07-28.json`.

### The gate: two branches fire at once

`ai_involvement`, pairwise agreement by platform:

| platform | | |
|---|---|---|
| lever | 100% | n=9 |
| weworkremotely | 95.8% | |
| google_jobs | 93.3% | |
| greenhouse / ashby | 92.2% | the clean sources |
| builtin | 91.1% | |
| **hn_whoishiring** | **77.8%** | the messy source |

Below 90% on the messy platform — the row of task 06's own gate table that reads **"stop.
Tasks 10 and 13 need rethinking."** And the clean-versus-messy gap is **14.4 points**,
over the 10-point threshold, so Phase 3 also needs a per-source quality budget and task
12's re-extraction must be measured before *and* after.

**Tasks 10, 11 and 13 are held.** The remediation is a design decision, not an
implementation one.

### Was 76% real? No — and n=17 was wrong in both directions

| | n=17 | n=115 | |
|---|---|---|---|
| `seniority_level` | 76% | **85.2%** | pessimistic |
| `role_archetype` | 90% | **84.3%** | optimistic |
| `ai_involvement` | 94% | **90.7%** | optimistic |
| whole record identical | 0 of 17 | **21.7%** | pessimistic |

The lesson is not that the old numbers were wrong; it is that at n=17 they could not have
been right in either direction. What survives — and sharpens — is the structural finding:
the clean/messy gap is real and large.

Comparisons use the **pairwise** two-run metric, because the n=17 study ran twice. The
report also carries unanimous-of-3, which is stricter by construction; quoting that
against the old figures would have manufactured a decline that is an artifact of the
metric rather than a property of the model.

### The trap was real, and is now guarded by a test

The eval cache is content-addressed, so without a repeat index in the key, repeat 2 reads
back repeat 1's stored answer and the run reports **perfect agreement** — a total silent
false pass on the exact quantity being measured, presenting as excellent news. A test now
asserts the digests differ per repeat. One refinement worth keeping: `repeat_index=0`
yields the *same* digest as an ordinary run, so adding `--repeat` does not invalidate a
cache someone already paid for.

### `criteria.json` was calibrated against figures that do not reproduce

`_hard_exclude_comment` justified its penalty design with "seniority_level 95%,
role_archetype 90%". Measured: **85.2%** [77.6–90.6] and **84.3%** [76.6–89.9] — both old
figures fall outside the new intervals. The slip rate a `-100` penalty amplifies is
nearer 1-in-7 than the 1-in-10 and 1-in-20 quoted there and in `docs/scoring.md:374`.

The design is unchanged and the correction strengthens it; only the numbers were wrong.
The comment records what it *used to say* rather than quietly replacing it, and
`docs/ingestion_tests/README.md` keeps the n=17 figures under a "Superseded" heading with
a per-field verdict rather than deleting them.

---

## 2026-07-28 — the two extraction decisions landed (`943d899`), 429 → 470 tests

Neither of these is a task file. They are the two decisions the repo owner made in
conversation, which existed nowhere but [`HANDOFF.md`](HANDOFF.md) — and the two agents
that were mid-flight on them when the previous session ended left **nothing in the
tree**. Both were re-run from scratch. Nothing downstream had depended on them, so the
loss cost time and not correctness.

New: `backend/config/extraction-policy.json`,
`backend/migrations/migrate_extraction_passes.py`, `backend/tests/test_extract.py` (41
tests, which is the whole of the increase). Changed: `backend/extract.py`,
`backend/schema.py`, `backend/docs/SCORING.md`.

### Selective majority-of-3 — one platform qualifies, and that is the point

The threshold is **0.90**, and it is not a new number: it is the line in task 06's own
gate table, the row that fired. At that threshold exactly one platform is below —
`hn_whoishiring` at 77.8% — and the six others sit at 91.1% or better, so the threshold
is not perched on a cliff. 0.92 would additionally pull in `builtin`; 0.93 would pull in
greenhouse and ashby, which is 9,659 of 11,824 rows and no longer a targeted remedy.

**It costs +4.2% of calls, not 3x.** `hn_whoishiring` is 247 of 11,824 rows (2.1%), and
each qualifying row pays two extra calls. Over a full re-extraction that is 494 extra
calls, ~23 minutes of wall clock at task 04's measured 2.85 s/call effective. Nightly it
is less than that and *bursty* rather than steady — hn is a single monthly thread, so its
rows arrive on one night a month and the other 29 nights pay nothing.

The pass count is **derived** from the measured agreement rather than stored as a second
list of platform names, so the config cannot come to say "hn_whoishiring: 3 passes" next
to a measurement that no longer justifies it. An unmeasured platform gets one pass: an
unmeasured source is not a bad source, and tripling it would be paying for a number
nobody has. That also makes a renamed platform string degrade to today's behaviour rather
than to a 3x bill.

### `vote_facts()` is pure, and the prose is not voted on

Enums and booleans take a plain majority, integers take a median, and `summary` and
`tech_stack` are carried **whole** from a single pass — the one whose enum vector agrees
most with the vote. Three summaries of one posting are three different sentences: a
per-field majority finds no majority, and any merge produces prose no pass wrote and no
posting supports. A union of `tech_stack` would accumulate every hallucinated library
across three passes; an intersection would delete a technology two passes named because
the third did not.

It votes on the **normalized** dicts, not raw model JSON, so "Mid-Level" and "mid" are one
vote rather than two. Voting before normalization would count formatting differences as
disagreement and manufacture instability that is not there.

`None` votes, deliberately, in both the enum and the integer rule: two passes answering
"the posting does not say" outrank one that names a level, because that is the honest
reading of that evidence. And the integer rule takes the lower of two middle values rather
than their mean — averaging 3 and 5 into 4 would invent a `years_experience_min` no model
ever said and no posting contains.

### The stability signal records what happened, not what was asked for

`job_facts.extraction_passes` and `.vote_unanimity`. A three-pass platform whose second
and third calls were rate-limited records **1**, not 3 — otherwise the column would be a
restatement of the config rather than a measurement. `vote_unanimity` is **NULL** for a
single pass rather than 1.0: one pass agrees with itself trivially, and 1.0 would make an
unmeasured row indistinguishable from a genuinely unanimous three-pass row in exactly the
query the column exists to answer. Task 11 consumes both.

The migration backfills `extraction_passes = 1` on all 5,328 existing rows and leaves
`vote_unanimity` NULL. The backfill is a fact rather than a guess — until this change the
script could not make a second call. Verified after applying: 5,328 rows at 1, zero
non-NULL unanimity.

### The 40/day ceiling, both halves, because it was two defects

`EXTRACT_BATCH_SIZE = 40` against one `extract.py` entry in `run-daily.py` was a hard
40/day ceiling against 43/day intake and 80/day recently. `main()` now drains batches
until the backlog is empty or `EXTRACT_DEADLINE_SECS` (3600) passes. At 2.85 s/call
effective that hour is ~1,260 calls — roughly 15x headroom on a normal night, and it
closes the ~6,000-row burn-down after a `FACTS_VERSION` bump in about five nights instead
of the 150 the old ceiling needed.

**The zero-progress break is the load-bearing part.** A `DEFERRED` row is written nowhere
and stays eligible — that is what makes a 429 retryable rather than a discarded posting.
It also means a rate-limited endpoint re-selects the *same* batch every iteration, so
without the break the loop would spin until the deadline against an endpoint already
asking it to stop. That is the one way this change could have made things worse than the
single batch it replaces, and it is pinned by a test.

The summary line reports `stopped=drained|deadline|no-progress` on every run, including a
clean one. Silence is this system's failure mode, and "the backlog is growing" is
precisely the condition that otherwise looks like a normal quiet night.

### The selection order was making CLAUDE.md's forbidden selection in production

`ORDER BY first_seen DESC` is what CLAUDE.md forbids for eval corpora — it is ~85%
greenhouse/ashby, so it measures the easy sources. `extract.py:191` was making the same
selection in **production**, where it decides which postings are never looked at at all.

Now: never-extracted rows first, then FIFO within each group. Plain FIFO was rejected —
after a `FACTS_VERSION` bump it would queue tonight's postings behind ~5,000
re-extractions, so the freshest postings would be the last served. This ordering keeps new
postings in front while FIFO within each group guarantees nothing starves.

`select_unextracted_jobs` and `remaining()` are now both built from one `_eligible_sql()`.
Their docstrings used to *promise* they matched ("if one changes the other must"); it is
structural now.

### `FACTS_VERSION` deliberately not bumped

Extraction semantics moved, and under "Versions are cache keys" the number should have
moved with them. It does not, because **task 12 owns the next bump and must carry this
change** — one re-extraction paying for both instead of two burn-downs a week apart. The
debt is recorded at the constant itself (`schema.py:158`) with a warning not to bump it
"to tidy up" without doing task 12's measurement, since the bump re-extracts ~5,300 rows.

---

## 2026-07-28 — 10 landed (`7d94bb1`): the gate reads descriptions, and it is still mostly noise

Report: [`docs/pursuit-description-gate.md`](../../pursuit-description-gate.md). New:
`backend/migrations/migrate_pursuit_profile.py`. Changed: `backend/relevance.py`,
`backend/tools/relevance-report.py`, `backend/tests/test_relevance.py` (+20).

Harvey's **User Operations Specialist** — *"working fluency with AI tools (e.g. ChatGPT,
Claude, Gemini); you use them, not just know of them"* — sits at tier 3 under the shared
config and **tier 1** under the cohort gate. That is the task's Definition-of-done example
and it was found in the live table rather than constructed.

**876 rows eligible for the cohort (tier ≤ 2), 573 of them newly, 13.2/day.**

### The honest number: 10.0% strict, against task 05's 6.7%

Hand-checked n=30, sample pinned by `md5(id)`. The conjunctive gate is **better** than the
vocabulary alone that task 05 measured — and it is still 90% junk. The report says so in
its own headline rather than in a footnote: *"the gate is better than the one task 05
measured and it is still mostly noise… the bottleneck is sourcing, not gating."*

That is the second time this run has produced a truthful low number where a flattering one
was available (task 05's 6.7% was the first). It matters because task 12's extraction
volume projection consumes this figure directly.

### The invariant was verified two ways, not asserted

With `description_include` absent, null or empty, `tier_sql` emits the **identical string
and identical params**. The agent loaded the pre-change module side by side with the new
one and diffed the emitted SQL across seven config shapes — production config, `DISABLED`,
include-only, include+exclude, excludes-without-include, locations-configured, and
`union_sql` — then pinned it in the suite as a golden string.

Deliberately brittle, and correctly so: anything that changes that string changes which
postings get extracted, and that should require somebody to look at the string.

**`frontend` and `tech` tier counts are unchanged on every platform**, confirmed against
the baseline taken before any agent ran.

### Include groups: the mechanism that bought the precision

An include list is now either a flat list of strings — one OR group, the historical shape,
still what every list in `config/relevance.json` uses — or a **list of lists**, meaning a
row must match at least one term from every group. That is how the cohort gate expresses
"AI vocabulary AND an entry-level signal".

A single group keeps the un-suffixed parameter name (`rel_include`, not `rel_include1`),
which is what makes the byte-identity above possible at all.

### The cohort profile is inactive, and that is the safety mechanism

`profiles.load_active` filters on `active`, so an inactive profile is invisible to
`union_sql`, `extract.py` and `match.py`. Production extraction volume **provably** cannot
move until a human activates it. `persona_json` and `criteria_json` are placeholders that
say so in their own text — task 13 owns the real cohort criteria and it is a product call,
not an implementation one.

### Four defects found outside scope, recorded not fixed

1. `title_exclude` has `\yauditor\y` but not `\yaudit\y` — an *IT Audit Analyst* clears the
   gate. Same class: `\yclinician\y`/`\ytherapist\y`/`\yphysician\y` but not
   `\ypsychologist\y`.
2. "Hybrid Development Representative" evades both `sales development` and `\ysdr\y`,
   despite the posting saying outright it is the entry point into the sales org. Three
   near-duplicates landed in one 30-row sample.
3. A Singapore posting is tagged `location_is_remote = TRUE` and reaches tier 1 for an NYC
   cohort. Ingest-side location tagging, not relevance.
4. **One `description_text` contains scraped ChatGPT web-UI markup** — job
   `ff9f9d9f9643e185af0f48ca` begins with `data-testid="conversation-turn-136"`. Something
   in that ingest path captured a browser DOM rather than a posting body. Worth a task of
   its own; it is silently poisoning extraction input.

---

## 2026-07-28 — 07 landed (`3a8b42c`): the tooling is built, and it produced zero labels

New: `backend/evals/labels.py`, `backend/webapp/label.py`, `backend/tests/test_labels.py`
(+44), `backend/webapp/tests/test_label_form.py`. Changed: `backend/evals/README.md`,
`__main__.py`, `report.py`, `backend/webapp/app.py`, `schema_web.py`,
`docs/ingestion_tests/README.md`.

**`backend/schema.py` was not touched.** The golden-set DDL is owned by
`evals/labels.py` and merged into `webapp/schema_web.py` by reading
`labels.WEB_PRIVILEGES`, so there is one definition rather than two.

### The uninterpretable report is unrepresentable, not discouraged

Task 16 set the precedent — a tool that *refuses to print one denominator alone*. This
does the same for the three quantities: a model-vs-human number will not render without
the floor (task 06's `selfcheck`) and the ceiling (human agreement) beside it. The
renderer takes the triple; a partial triple is **refused, not silently dropped**; an empty
cell is as absent as a missing one. There is no code path that prints one number alone.

### The two axes are keyed so that axis A survives the cohort

| axis | key |
|---|---|
| A — "is the extraction correct?" | `(job_id, field, labeller_id, round_no)`, **no profile** |
| B — "would you apply to this?" | `(job_id, field, profile, labeller_id, round_no)` |

A `CHECK` enforces the asymmetry in both directions: axis A **may not** carry a profile,
axis B **must**. `DELETE FROM eval_labels WHERE axis = 'B'` when the Pursuit cohort ends
leaves every axis-A row intact and fully interpretable — which is the point, because axis A
validates `job_facts`, the tier shared by every profile that will ever exist and the one
that **has never been measured against a human**.

### `tech_stack` is off the form, and the reason is recorded rather than the field dropped

At **70.4%** exact self-agreement (task 06, n=115), most of `tech_stack`'s instability is
granularity — "Postgres" vs "PostgreSQL", whether nice-to-haves count — so a human label
would be settling a question about the field's *definition*. That is a spec change, not
evidence, and it would spend scarce volunteer hours on a figure nobody can act on.

`remote_policy` at **81.7%** is **kept**, and that is the judgement call in the list: it is
a five-value enum where a disagreement is a disagreement a human can settle from the
posting. The two fields are unstable in different ways and the distinction is the reason
one is asked and one is not.

`ai_involvement` and `seniority_level` are asked **first** — task 06 measured
`ai_involvement` at 77.8% on `hn_whoishiring`, and a field that cannot agree with itself is
where a human label buys the most.

### The surface is HTML behind the SSO that already exists

Server-rendered at `/v1/label`, not a CLI. It is for ~10 Builder volunteers and
`frontend/` currently holds one file called `.gitkeep`. Labels are **append-only to the
service** — no `UPDATE` and no `DELETE` grant — because a label is evidence; a revision is
a second round and both survive.

### Zero labels, and a test that enforces it

`test_the_tables_ship_empty` and `test_no_module_in_the_package_calls_a_model_to_label`.
Verified independently: no `%label%` table exists in the live database yet, since
`ensure_schema` runs on webapp startup. Axis B *is* Builder preference, so a model standing
in for it makes the measurement circular — the exact defect `claude-bench.py:417` has in
treating `sonnet-batch-1` as ground truth. **Task 29 is the labelling session and it needs
people.**

### An environment limitation, not a regression

`backend/webapp/tests/` cannot run here: **`fastapi` is not installed**, which fails
`test_label_form.py` and the four pre-existing webapp test modules identically. The
`backend/tests/` suite, including all 44 label tests, is green.

---

## 2026-07-28 — 14 landed (`7221620`): it works, and it is ~1.8/day against an estimate of 20–60

Report: [`docs/ingest/nyc-open-data.md`](../../ingest/nyc-open-data.md). New:
`backend/ingest/nyc-open-data.py`, `backend/tests/test_nyc_open_data.py` (+36),
`backend/evals/fixtures/cassettes/nyc-open-data.json`. Wired into `run-daily.py`'s `STEPS`
by the orchestrator.

**1,030 rows are in the live table** as `platform='nyc_open_data'` — 79 at tier 1 under
the author's gate, 951 at tier 3.

### The estimate was out by an order of magnitude, and this is the second time

The task file estimated **20–60 relevant/day**. Measured: **~1.8/day**. The report says so
in its own *Purpose* section — *"Read the yield section before investing further in this
source"* — not in a footnote at the bottom.

That matters beyond this one source. Phase 3's remaining sourcing decisions (15, 19, 20,
21) are sized against estimates from the same table, and this is now the **second**
measurement to come in far below its estimate — after task 05's 43/day gate volume
resolving to ≈3/day usable. **Treat the remaining Phase 3 estimates as unvalidated.**

### It earns its place on grounds other than volume

One documented JSON API, one crawl, no HTML parsing, no token discovery. And two
properties nothing else in the pipeline has:

- **An explicit close date per posting** (`post_until`). Every other source infers closure
  from absence, or cannot infer it at all — tasks 19–21 will have neither.
- **NYC by construction rather than by regex.** The location filter that every other source
  needs does not apply here.

### Pagination reconciled against a count, not a short page

Anonymous SODA throttles, and a throttled page is byte-identical to the end of a list —
the landmine that cost one published account 1,960 of 2,000 jobs. The ingest reconciles
against `$select=count(*)`.

### One file deliberately left out of the commit

`backend/evals/record_cassettes.py` carries this task's cassette registration **and task
17's in-flight changes**, so it was excluded rather than committed with another agent's
half-finished work in it. Task 17's commit brings both.

---

## 2026-07-28 — 17 landed (`597662b`): the roster is a table, and the task file was wrong about the starting point

Report: [`docs/ingest/ats.md`](../../ingest/ats.md), rewritten by hand. New:
`backend/ingest/ats_sources.py`, `backend/tests/test_ats_new_platforms.py` (+38), three
recorded cassettes. Changed: `backend/ingest/ats.py`, `backend/config/companies.json`,
`backend/evals/record_cassettes.py`.

`ats.py` was already in `run-daily.py`'s `STEPS`, so nothing needed wiring.

### Three new platforms, not four — the task file mis-stated the baseline

It says *"current coverage is Greenhouse and Lever"* and asks for Ashby, Workable,
Recruitee and SmartRecruiters. **Ashby was already supported.** Three are new, and the
Greenhouse/Lever/Ashby mappings are unchanged from the 2026-07-27 version. Six vendors
now.

This is the fourth task file in this run found to be wrong about the code it describes,
after 05's premise, 10's regex instruction and 18's frontmatter claim. The pattern is
consistent: **the task files were written from the plan, not from the code.**

### Adding an employer is a row insert, not a deploy

`ingest/ats_sources.py` is the single place that knows where the roster comes from —
`company_ats`, task 16's table. `config/companies.json` no longer competes as a second
source of truth.

### Closure is now conditional on reconciliation

Previously a posting absent from a run was closed. Now a run that comes back **short of
the total the API just reported** does not get to close anything. That is the landmine
CLAUDE.md names — *a throttled page is not the end of a list* — applied to the one
operation where it does permanent damage: closure driven by a truncated page is how a
source silently marks its own live corpus dead.

### The `generated:` frontmatter is dropped, not preserved

`docs/ingest/ats.md` carried `generated: 2026-07-27`. **No generator exists** —
`grep -rn "docs/ingest" --include='*.py'` finds no writer anywhere in the repo. The file is
now hand-written and says so, and says what it supersedes. Task 34 still owns the decision
for the rest of the directory.

---

## 2026-07-28 — 18 landed (`fabe381`): the plumbing is sound, the premise is not

Report: [`docs/ingest/workday.md`](../../ingest/workday.md). New:
`backend/ingest/workday.py`, `backend/tests/test_workday_ingest.py` (+77). Changed:
`backend/evals/workday_fixtures.py`, `backend/tests/test_workday_fixtures.py`. Wired into
`run-daily.py`'s `STEPS` by the orchestrator, after `ats-discover.py`.

**Measured (run 3, the committed code): ~400 requests, 861s, 329 rows, 0 dropped, 0
blocked, 1 closure detected.** Full suite green at **663**.

**Correction, 2026-07-28:** the run log and commit `fabe381` first quoted **run 1** — 220
requests, 462s, 149 rows. The committed code already carried two later fixes; only the
report lagged. Corrected in `162845b`. The deltas are the evidence and are worth keeping:

| run | detail-fetched | gate-surviving | wall-clock | what changed |
|---|---|---|---|---|
| 1 | 149 (11%) | 4 | 462s | first end-to-end run |
| 2 | 122, 3 tenants | 4 | 420s | Nordstrom shortfall: `total` 867, collected 865 — ordinary churn, fatal under a strict check |
| 3 | **329 (24%)** | **14** | **861s** | `locationsText` facility fix; one-page reconciliation threshold |

### The best thing this task produced is a bug in its own first run

**Run 1 was silently dropping 161 of NewYork-Presbyterian's postings** — real NYC hospital
jobs, exactly the population the cohort exists for — while printing `4/4 tenants ok`.

That is CLAUDE.md's *"silence is this system's failure mode"* caught in this task's own
output, by the task itself, after it had already reported success once. It is also why the
reconciliation threshold is **one page** rather than zero: run 2 showed that an exact-match
check fails on ordinary mid-walk churn (`total` 867, collected 865), so a strict check
would have turned a healthy board into a permanent alert while the real 161-row loss went
unnoticed.

### A scaling constraint this task did not solve, and says so

**~14 minutes of nightly window at four tenants**, sequential at 1.5s apart. At the ~50
tenants `18-ingest-workday-cxs.md:97` anticipates, that does not fit a nightly window. The
delay, the concurrency or the per-tenant cadence has to change. Recorded as a real
constraint rather than deferred silently.

### The `limit` landmine is an exception, not a clamp

`_check_page_limit()` **raises** rather than doing `min(limit, 20)`. Above 20 the CXS
endpoint returns an empty `jobPostings` array with HTTP 200 and no error — byte-identical
to "no more results" — so silently correcting the caller would preserve the bug in the
caller's head while the run reported success and ingested nothing. That is the right
reading of a landmine whose entire danger is that it looks like success.

### A shortfall writes nothing at all

Collected rows are reconciled against the `total` the API itself reported, and a run that
comes back short does not get to write, let alone close.

### The upstream gate, quantified

**~1,360 postings reachable per night from four tenants.** The gate takes detail fetching
down to **24%** of that — ~14 minutes of nightly window. Without it the same run is 1,366
detail requests and **34 minutes**, for four tenants, growing linearly with the tenant
count task 16's backlog will produce. That is the whole reason this source is gated
upstream rather than pulled whole and filtered after.

### It did eventually report a yield, and it is ~1/day against 80–200

**Correction to an earlier version of this entry**, which said the task declined to report
one. It declined at first, correctly, and then measured the right thing instead. Of **329**
detail-fetched postings from four tenants:

| | |
|---|---|
| AI vocabulary in the **title** | **0** |
| entry-level AND AI-signalled | **1** (`seniority_guess`) · **3** (title regex) |

Verified independently by the orchestrator against the live table; the two methods disagree
on the margin and agree on the order. **The zero does not depend on the method.**
Extrapolated to the ~50 tenants the task file anticipates: **~12/day against 80–200**, and
generously so — `company_ats` holds four tenants, not fifty.

The plumbing is sound and separable from that: ~1,360 postings/night reachable, 24%
detail-fetch cost, 0 blocks, 0 records dropped, closure detection working live.

### Why the first number it reported was not the answer either

Only **4 of 149** postings survive the full gate. The report says, correctly, that this is
not a yield: the gate is today's SWE-shaped `config/relevance.json`, whose two active
profiles are built from "engineer", "developer", "SRE". Four hospital, bank and retail
postings matching it *is exactly right and exactly useless* — those profiles are not who
this source exists for.

The task file's 80–200/day assumes the Pursuit retarget. **The number must be re-measured
after task 13, and it is not evidence about the source until it is.** Contrast task 14,
which could measure honestly because its estimate did not depend on the retarget.

### It carried task 16's finding instead of re-learning it

`test_never_found_does_not_mean_no_ats`, and `test_upsert_is_never_unpacked_as_a_bare_three_tuple`.

### The defect it found: task files' `Status:` headers are stale, and they mislead

Task 18 reported task 04 as "still `todo`" because
`tranche_one/04-quota-baseline.md` says `**Status:** todo`. **04 landed in `c3275be`.**
Every landed task file still carried a `todo` header; `README.md`'s status column was the
only correct index, and nothing said so.

**Fixed in this commit:** all fourteen landed task files now read `**Status:** DONE,
<commit>`. This is exactly the drift `docs/` is supposed to prevent, and it cost one agent
a wrong conclusion in a shipped report.

Half-right, though, and worth recording: **task 04 has no standalone `docs/` report.** Its
findings went into `backend/docs/SCORING.md`. So an agent told to check its work against
"task 04's budget" finds no such document. Task 34 should decide whether 04's numbers get
promoted to `docs/`.

## 11 — Archetype superset, `role_track`, missingness

Three changes designed together because they ship in one `FACTS_VERSION` bump, which task
12 still owns. **Nothing was re-extracted and nothing was tuned.** Suite 663 → **717**.

**The archetype vocabulary went from 12 values to 26.** Derived, not invented:
`backend/tools/derive-role-tracks.py` (new, stdlib-only) against 863 cohort-eligible
postings and the 427 rows sitting at `other`, with the evidence in
`docs/role-track-derivation.md`. Five ops values, nine tech. Two of the task file's seven
proposed candidates were dropped on evidence.

**`role_track` exists as a nullable `job_facts` column and an extracted field**, with a
provisional nine-value vocabulary from title clustering. It is NULL on all 5,328 rows and
stays NULL until task 12 re-extracts — nothing has been extracted for it, so there is
nothing to backfill, and a guessed value would be worse than a missing one.

**Missingness is now representable at both layers.** `normalize()` no longer substitutes
`"other"` / `"none"` / `"unknown"` / `false` for an absent answer, and the four scored
booleans are tri-state. `score_job()` prices each nullable feature via a top-level
`unknown_penalty` map and emits a `{feature}:missing` entry into `match_reasons`, so "why
is this ranked 8th" is answerable when the answer is "we could not tell".

### The defect it found: the task file described a bug that was not there

Section 3 is written against NULLs that do not exist — `normalize()` had already laundered
every absence into a real-looking value, so 0 of 5,321 rows carried a NULL in any of the
fields it names. The bias was real and one layer up. **That is now five task files
confirmed wrong about the code**, and the correction changed the work: the fix had to land
in extraction, not only in scoring.

### What is deliberately still outstanding

- **No `FACTS_VERSION` bump.** Task 11 adds three items to the unpaid bill already recorded
  at `schema.py:159-168`; one re-extraction under task 12 settles all of it.
- **No `criteria_version` bump.** The new weights and penalties are inert until someone
  runs `migrate_profiles.py --apply --bump`. Verified inert: `match.py --dry-run` reports
  0 matched for both active profiles.
- **The `role_track` vocabulary is provisional.** Derived pre-Phase-3 from a tech-heavy
  corpus; the task file expects revision and the tool exists to re-run it.

---

## 2026-07-28 — tasks 08, 12 and 19, three agents in one round

Three subagents in parallel with disjoint file ownership; the orchestrator took
the baseline, verified every claim against the code and the database, and
committed. Nothing was committed by a subagent. Zero collisions across
eleven files.

### The finding that reframes the run: the cost was configuration, not corpus

Task 12's bump was costed at 5,317 rows / 5,659 calls / ~5 nights. It cost **863
rows and 28m31s** because `extract._eligible_sql` gates the queue on the
relevance union of the *active* profiles, and both of the owner's
software-engineer job-search profiles were still on. The re-extraction that had
been described as expensive was mostly re-extracting a corpus the repo is being
retargeted away from.

### The negative result: widening the vocabulary made `other` worse

Task 11 went from 12 archetypes to 26 to shrink the unclassifiable bucket. After
re-extraction `other` is **31.1%** of the cohort corpus against 8.0% before —
**4.6%** on rows that already had facts, **44.0%** on the 579 first-time
extractions. The vocabulary fits the corpus it was derived from and fails on the
part of the cohort corpus nobody had examined. Task 13 should price the weights
knowing that.

The ops five also came in **42 under** their title-probe floor. That direction is
falsifiable where an overshoot is not: the extractor read whole postings and the
probe read titles, so it had strictly more information and still applied those
values to fewer postings.

### What task 08 settled

`primary_track` reproduces at **89%**, `fit_score` at **24%** with a maximum
self-disagreement of 33 points, `fit_score` as an ordering at **ρ 0.915**. The
bucket is stable, the number is not, the ordering is fine — which is task 30's
argument, now measured. It also found two defects nobody was looking for: **D43**
(a tombstone left the previous score in place; 3 `FAILED:` rows carry a real
`fit_score`) and **D44** (`evals run` raised `UnboundLocalError` for *every*
task, from a branch-local import that made a name function-local at compile time).

### What task 19 settled, and the defect it found on the way

2 of 55 employers publish parseable `JobPosting`; **1 of the 35 in the actual
target population**, and that one publishes no `validThrough`. Dropped. On the way
it found **D45**: `company_ats.status = 'never_found'` holds 35 rows against a
true population of 139, and the 35 are a contiguous alphabetical block
(`M=8 N=20 O=2 P=5`) — a partial write-back. Task 19's brief was written against
25% of the set it meant to describe, and tasks 16 and 17 read the same column.

### The defect that got worse rather than better

The browser-DOM poisoning found by task 10 survived the re-extraction and was
**laundered into version-3 facts**: `ff9f9d9f9643e185af0f48ca` produced
`role_archetype = 'data'` and `role_track = 'data_and_analytics'` from scraped
ChatGPT web-UI markup. Three postings carry DOM markers. Extraction has no
input-sanity gate, so any ingest path that captures the wrong bytes gets
structured facts written from it, confidently.

### What is deliberately still outstanding

- **The majority-of-3 vote has still never fired.** `hn_whoishiring` contributes
  0 of the 863, so `extraction_passes = 1` and `vote_unanimity IS NULL` on all
  5,907 rows. The `FACTS_VERSION` debt is paid on paper; the mechanism is
  unexercised and its first real run is still ahead.
- **Task 11's 203/54 `other` prediction is untested, not falsified.** Only 25 of
  those 427 rows survive the pursuit union. Testing it means reactivating `tech`.
- **No `criteria_version` bump.** `pursuit` is active with `archetypes = {}`, so
  every value prices through `match.py:191`'s `:unpriced` path. Ranking is live
  and not yet a product; task 13 owns it.
- **`job_scores` still has no version key.** Task 08 documented it and did not add
  one, because `schema.py` was another agent's file that round. Task 13 edits the
  persona, so this bites next.

### Verification that earned its keep this round

Ranked by what actually caught something:

1. **Recomputing a headline number independently.** Caught that only 25 of task
   11's 427 `other` rows were reachable, which changed what the deliverable could
   claim, and confirmed all seven of task 08's production figures.
2. **Re-running an agent's own tool and reconciling its sub-counts.** Task 19's
   summary reported 2 employers over sub-lines summing to 1 — the second was found
   by a discovery path with no line in the output. A correct headline with an
   unreconcilable breakdown.
3. **Checking whether a known defect survived the change.** Nobody asked; the
   browser-DOM row turned out to have been re-extracted into confident facts.
4. **Asking where an artifact is.** Task 08's selfcheck table was quoted from a
   run whose `--out` file was never committed, making the session's best
   measurement cost 165 live calls to re-verify. Now committed.

---

## 2026-07-28 — 13, 35 and D45 (three parallel agents)

Three subagents in one round on strictly disjoint file sets; the orchestrator took
the baseline first, verified every claim against the code and the database, and
committed each stream under its own number. Nothing was committed by a subagent.

| stream | commit | suite delta |
|---|---|---|
| D45 — `company_ats` durability cadence | `e11fabf` | +8 |
| 35 — extraction input-sanity gate | `303f7b9` | +16 |
| 13 — cohort criteria profile | `fa2d7a7` | +31 |

**782 → 837, OK.**

### What each landed

**13.** `pursuit` went from a documented placeholder — `base 50`, `archetypes {}` —
to real weights at `criteria_version` 2, and from 863 uniformly-scored matches to
144 ranked ones. The weight set was chosen by the repo owner from three variants
simulated over the live corpus with `score_job()`, which is pure and therefore
sweepable without writing anything.

**Its DoD is partially unmet and was reported as such rather than tuned into
passing** — 16 of 20 above floor, 10 of 20 in the top 20, against 10 of 10 on the
senior-exclusion list. See `DECISIONS.md`.

**35.** Extraction had no opinion about what it was reading. Eight rows were not job
postings; one had been extracted at `facts_version 3` into confident facts from a
scraped ChatGPT web UI, and another — 2,700 characters of a staffing firm's
navigation menu — reached a `job_scores` row. The gate returns `REJECTED` before
`build_prompt`, so zero LLM calls is structural rather than asserted.

**D45.** `company_ats` held 35 `never_found` rows against 139 because two tables
committed on cadences measured on different axes. Fixed, 104 rows backfilled with
no network, and the fix is verified by killing a pass at every one of 60 indices.

### What this round taught about running agents

**File ownership does not isolate database state.** All three agents were given
explicit, disjoint file lists and none collided on a file. They collided on the
*database*: 35's remediation deleted 4 rows from the pursuit corpus while 13 was
scoring it, which moved 13's frozen eval fixture (863 → 859), its matched count
(145 → 144) and `tech`'s `job_matches` md5. Every one of those looked like a
regression in 13 and was not. **Only the pre-flight baseline made them
attributable** — the same lesson task 10 recorded, arriving by a different route.

**The falsifiable prediction is what made verification cheap.** 13 was handed
"expect 145 matched, 19 of the top 20 on the shared floor, 51 of 55" and told to
stop and report rather than adjust the weights if its run disagreed. Two of the
three reproduced exactly and the third reconciled to a known cause, which took
minutes rather than a re-derivation.

**Send an agent back to its own file.** 13's fixture staleness was fixed by 13, not
by the orchestrator, and it came back with an exhaustive `_what_moved` record — no
pinned score changed, 15 ranks moved, none in the top 20 — that was better than
what was asked for.

**All three went idle without reporting.** Nine of nine across four sessions now.
Treat the idle notification as "go look".

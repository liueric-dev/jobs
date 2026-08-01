---
kind: record
written: 2026-07-28
generator: none
---

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

---

## 2026-07-29 — `job_scores` version keys (HANDOFF step 2)

**Not a numbered task.** It is recommended next step 2 in `HANDOFF.md`, deferred out
of the task 13 session because its invalidation path fires on exactly the
`criteria_version` bump 13 made. Base `d5897d8`, suite green at **837**.

**What landed.** `job_scores` gained four nullable columns — `facts_version`,
`persona_sha`, `prompt_version`, `criteria_version` — and `select_shortlist`'s
anti-join became version-aware. `schema.SCORE_PROMPT_VERSION = 1`.
`persona_sha()` moved from `evals/tasks/score.py` into `score.py`; the harness
re-exports it. New `migrations/migrate_score_versions.py` and
`tests/test_score_versions.py`.

**Suite 837 → 875.** No existing test was deleted or reordered; two were extended
and one 17-tuple fixture became 18 when `f.facts_version` joined the shortlist.

### The measurement that should shape how this is read

**Nothing is stale, and nothing was re-scored.** `--stale-report` reads **0 stale**
on every profile and **1,018 unversioned** (tech 835 + frontend 183). The database
snapshot before and after is byte-identical on the narrative content digest,
`max(scored_at)` and the per-model tombstone census. `SELECT count(*) FROM job_scores
WHERE <any version> IS NOT NULL` reads **0**.

**The bill is 1,018 calls, not 1,293, and the difference is a real finding.**
`select_shortlist` reaches a posting only through `job_matches` and only while
`status = open`, so 275 rows are closed or never cleared `MATCH_FLOOR` and **no flag
routed through that path can ever reach them**. Quoting the row count overstates the
cost by 27%. The migration report prints both, labelled — the fix task 11 used for
the 54-vs-55 ambiguity.

**The 57 tombstones are a separate and much cheaper decision**, and 40 of them were
written by `FAILED:glm-4.5-flash@api.z.ai`, which is not the production pin and was
failing for a credential reason rather than anything about the posting.

### Proposed amendment to `.claude/CLAUDE.md:28-31` — NOT APPLIED

The instruction file names four columns being added: `persona_version`,
`prompt_version`, `features_version`, `model_version`. Two are now wrong about the
code:

- **`persona_version` shipped as `persona_sha`**, a content digest rather than an
  integer with a bump discipline. See `DECISIONS.md`.
- **`model_version` was not added and should not be.** `job_scores.scoring_model`
  already records it, and a model swap is an operator decision with a known price —
  `scripts/backfill-scores.py` already deletes-by-model as the deliberate act.

`features_version` remains unbuilt and correctly listed. **Not edited — it is the
owner's instruction file, the same rule the stale `lib/` parity note is held to.
Propose it in task 34.**

### Two defects found on the way, both closed in the same change

- **`--limit 0` spent 20 calls.** `limit = limit or budget` evaluates `0 or 20` → 20,
  and `--limit 0` is exactly what someone types to mean "don't spend". `pursuit` was
  safe only by the accident of `None or 0` being `0`.
- **A nested `_comment` inside `persona.buckets` does not leak, it crashes** — and it
  takes the whole batch. `build_prompt` does `(b or {}).get('description')`; a string
  raises `AttributeError` into `score_one_job`'s blanket handler, so every job in the
  batch returns `ERRORED`. That is D16 with a different key.

### Corrections to claims in the plan and the code

- `score.py`'s `run_for_profile` docstring said "the login path calls it directly".
  **Nothing under `webapp/` imports the module**; `main()` is the only caller. The
  cost model is documented and unbuilt. Docstring corrected, reasoning kept.
- The exposure was framed as 1,293 rows and is 1,018 (above).
- `strip_comments()` is not merely top-level-only for the persona — **the persona is
  never passed through it at all** (`migrate_profiles.py:180`).

### Mechanics

Three agents, two rounds, all on disjoint files, **nothing committed by a subagent**.
The orchestrator owned the two shared files — `schema.py` (both agents' input) and
`run-daily.py` — which is the `STEPS` rule generalised, and it removed the race
task 11 had to solve by pasting values into a prompt.

**Both agents went idle without reporting. Eleven of eleven now.**

Verification that earned its keep, in order of value: the **before/after database
snapshot** (a count cannot see an overwrite; an md5 over the narrative columns can),
running `--stale-report` with **both API keys unset** to prove the report cannot
reach the code that spends, and **re-running the agent's own tool and reconciling
every number against an independently-taken baseline**. One required test —
`test_run_daily_score_step_passes_no_rescore_flag` — was missing from an otherwise
complete 37-test file, and was caught by checking the list against the brief rather
than by the suite, which was green without it.

---

# Session — mock acceptance run, `strip_html`, task-07 gaps (2026-07-29)

Five agents in parallel on disjoint files, orchestrator verifying and committing.
Suite **878 → 1030**, green. 90 live LLM calls, all in a scratch schema.

## What landed

- **`backend/evals/mock_corpus.py`** + `tests/test_mock_corpus.py` — loads the 55
  synthetic postings, maps them to all 18 `schema.COLUMNS` keys, validates the answer
  key. `job_url` is deliberately empty so a mock row can never satisfy `jobs_app`
  (`schema.py:711`) even if one leaked.
- **`docs/tasks/refactor/mock/mock-postings-v3-answer-key.json`** — quote-backed ground
  truth for all 55. 605/605 quotes verified byte-exact substrings. 5 disagreements with
  the pre-existing addendum recorded unresolved.
- **`backend/tools/mock-acceptance.py`** — the scratch-schema driver. Refuses to write
  unless `schema.SCHEMA` matches `scratchdb.SCRATCH_NAME`.
- **`average_precision` / `precision_at_k` in `evals/metrics.py`** — stdlib, not
  sklearn (which is not in `requirements.txt`, so `learned-ranker-probe.py` does not run
  on a clean checkout). Ties handled by the McSherry & Najork closed form.
- **`lib/text.strip_html()` fixed** + `migrations/migrate_description_rehash.py`.
- **Per-platform breakout** in `labels.inter_annotator` / `intra_annotator` /
  `model_vs_human` / `report.render_labels`, closing task 29 DoD:106.
- **`fit_score` blindness pinned** — task 29 DoD:105 — in `backend/tests/`, which runs
  here, as well as `webapp/tests/`, which cannot (`fastapi` is not installed).

## The finding

**Gate recall 48.3%.** See `docs/mock-acceptance.md` and the new section at the top of
`HANDOFF.md`.

## Verification that caught things, in order of value

1. **An independent validator on the same contract.** The loader agent's `load_key`
   refused the answer-key agent's file over `location_is_nyc`. Two of eleven extraction
   fields would otherwise have been the loader's own mapping scored against itself.
   Neither agent could see the other's work; review by one reader would not have caught
   it. **D47.**
2. **Brute-force enumeration against a closed form.** `average_precision`'s tie handling
   was checked against the mean over *every* tie-break permutation — 8 cases, max delta
   1.1e-16. Then the orchestrator's own correction changed the function's signature, so
   it was **re-verified after the change**: a verified-then-modified function is
   unverified.
3. **A migration that proves its own method before writing.** `migrate_description_rehash`
   reproduces the stored `content_hash` on 10,405/10,405 untouched rows. A hash rebuild
   that could not reproduce existing hashes would be caught before it touched anything.
4. **Content digests, not row counts.** `job_matches` and `job_scores` digests were
   byte-identical before and after, which is what proves nothing was overwritten. The
   only delta was the intended −2 `job_facts`.
5. **Reading the failing test list rather than the pass count.** Three tests broke on the
   `strip_html` fix and HANDOFF had predicted the wrong ones — two were task 35's *gate*
   tests, red because fixing the source cleaned the fixture the gate is tested against.

## Method notes worth keeping

- **The orchestrator fixed the shared module surface before either dependent agent
  started.** `mock_corpus.py`'s signatures went into both briefs verbatim, so the
  harness agent could code against a module that did not exist yet. No race, no pasting
  values between prompts.
- **Fixing a defect can silently disarm the alarm built for it.** Task 35's gate tests
  went red because their poisoned fixture became clean. Deleting them would have retired
  a live alarm as a side effect of an upstream fix. They were re-pointed at input still
  poisoned after the fix, and a test was added for the 13,000 rows the old stripper
  already wrote.
- **Five of five agents went idle without sending a report.** Sixteen of sixteen across
  the run now. Treat the notification as "go look".

---

# Session — the `pursuit` relevance gate (2026-07-29)

**Not a numbered task.** Step 0 in `HANDOFF.md`, and it fixes a defect in what task 10
built. Four commits: three in git, plus one database write.

| | | suite |
|---|---|---|
| `4eefb7e` | move the gate to `config/pursuit-relevance.json` (proven no-op) | 1030 → 1033 |
| `e8f3b72` | split the entry-level vocabulary: title nouns, description phrases | 1033 → 1054 |
| `9dab9e6` | narrow `customer success`; keep `executive assistant` on a census | 1054 → 1058 |
| — | the database write: `migrate_profiles.py --apply`, **no `--bump`** | — |

**Mock gate recall 48.3% → 89.7% [73.6–96.4], precision 58.3% → 72.2%. Live tier ≤ 2
869 → 880.** The false positives are the **same ten ids** at every step.

### The defect

The gate is conjunctive — one AI term **and** one entry-level term in the *same field*
(pre-move `migrate_pursuit_profile.py:216,229`; now `config/pursuit-relevance.json:14,55`).
Task 10 built a description-first gate and handed it a **title** vocabulary: associate,
coordinator, assistant, specialist, analyst — title nouns. A description does not restate
its own title's seniority noun, so on the description path the AI half matched and the
entry half did not.

Measured on the 55-posting mock corpus: **gate recall 48.3%, 15 of 29 intended-good
postings rejected, 14 of the 15 on that single group.** mock_022's *"No retail or
e-commerce experience required; training provided"* matched neither `\yno experience\y`
nor `\ywill train\y`.

### `4eefb7e` — the gate was living in a script that refuses to run

`COHORT_RELEVANCE` was a dict literal inside `migrate_pursuit_profile.py:147-386` — a
script that **refuses to run** whenever stored `criteria_json.archetypes` is non-empty
(it holds 26), and the refusal fires *before* the `--apply` check (now `:289-306`, ahead
of `:308`), so even a dry run exits 1. Three other things read that gate. It is now
`backend/config/pursuit-relevance.json`.

Proven a no-op three ways rather than asserted: the dict is equal to the stored
`profiles.relevance_json` key-for-key **and in key order**; `relevance.tier_sql` compiles
a **byte-identical 799-character SQL string** with identical params; the mock `--dry-run`
still reads 14/15/10/15.

`tools/mock-acceptance.py`'s `cohort_relevance()` (`:314-329`) used to `importlib` the
dict out of the migration **by file path**, and was repointed in the same commit. Missing
that would have left the harness compiling the old literal while the pipeline ran the new
file — and reporting **"no change"**, which reads as the fix having done nothing rather
than as the instrument pointing at the wrong object.

### `e8f3b72` — a strict superset, which is what makes the title path safe

`description_include`'s entry group opens with the **same eleven nouns byte for byte** and
adds three phrases. The title path therefore *cannot* change and the description path can
only gain rows. Three terms, raw live description matches **18 / 0 / 11**:

```
\yno\y[^.;:]{0,40}\y(?:experience|background|license)\y[^.;:]{0,25}\y(?:required|needed|necessary)\y
\ydoes not require\y[^.;:]{0,40}\y(?:experience|background)\y
\ytraining (?:is |will be )?provided\y
```

| | before | after |
|---|---|---|
| live gate (tier ≤ 2) | 869 | **873** (t1 450→453, t2 419→420) |
| mock good_admitted | 14 | **25** |
| mock recall | 48.3% | **86.2%** |
| mock bad_admitted | 10 | **10** — the same ten ids |

Term 2 is the one new dead term and is **kept deliberately**, on the same standing as
`\yattorney\y` under `_dead_patterns_note`: a working pattern verified against mock_012,
waiting for its first live posting.

**Three rejections, all measured.** Putting the phrases *instead of* the nouns takes the
live gate from 869 to **39** — the conjunction needs both signals in one field, and
descriptions restate their own title. One shared widened list for both fields gives
**873, identical to the split**, so it buys nothing and gives up a provable invariant.
`degree` in the noun set: rejected.

New `backend/tests/test_pursuit_gate.py`, +21 tests. **Its defect class fails 8 subtests
against the previous gate** — the test and the defect agree by construction rather than
by someone remembering. It also carries a **sentinel** asserting four rejected phrase
families stay absent, with their live costs (+17 / +5 / +5 / +123) in the docstring.

### `9dab9e6` — a census, not a paragraph

`title_exclude` gates **both** paths (`relevance.py:232-234`, deliberate, pinned by
`test_relevance.py:203-211`), so six terms inherited from the author's software-engineer
profile were exclusions on the cohort's own target population. Rows each was blocking
alone: `\ycustomer success\y` **12**, `\yexecutive assistant\y` **9**, `\yfacilities\y`
**1**, `\yoffice manager\y` / `\ywarehouse\y` / `\ydriver\y` **0** each.

`\ycustomer success\y` became four manager-and-above terms. Measured, they admit exactly
**7** rows (Customer Success Associate at Datadog ×4 and AlphaSense, Customer Success
Specialist at EliseAI, Applied AI Specialist at Samsara) and block exactly the **5**
Manager rows. Raw title matches 120 / 7 / 4 / 1, all non-dead. Gate 873 → **880**.

`\yexecutive assistant\y` is **kept**, on a census of all 12 open EA postings at the
blocked employers: required experience 3+, 5+, 5+, 5+, 6+, 6+, 7+, 7+, 10+ years, one
unstated; most are not NYC. That is a read of every row the term touches rather than an
argument about the term.

### The database write, verified after rather than reported

`migrate_profiles.py --apply --profile pursuit` with the three config files and **no
`--bump`**. No code change.

| | |
|---|---|
| live tier ≤ 2 | **880** (t1 456 / t2 424 / t3 12,567 of 13,447 open) |
| `extract.remaining` | **2 → 13** |
| `job_matches` content digest | byte-identical, `c98c4bbceed1b77d82979e83dfad70cc`, 3,521 rows |
| `md5(persona_json)`, `md5(criteria_json)` | unchanged |
| `criteria_version` | still 2 |
| `daily_narrative_budget` | still 0 |

### Two limitations, stated rather than buried

**1. "Recall 48.3% → 89.7%" is a statement about the mock corpus, which was built to
contain the failure mode it measures.** It is a specification test. It is not evidence
about the live corpus, and the live corpus has no recall figure.

**2. The fix adds 11 postings to an 869-row pool — +1.3%.** It does not meaningfully
change what task 29's labellers will see, and it moves GATE 2's ">= 200/day" question
**not at all**.

It was still right to do first: the defect is real, the fix is cheap, and a labelling
session run through a knowingly-broken gate is wasted.

The three remaining mock false negatives (mock_016/017/018) are reachable **only** through
the four rejected phrase families, at **+145 live junk rows**. Recall stops at 89.7% on
purpose.

---

# Session — the task 29 sampler: four defects, and the set drawn (2026-07-29)

Eight commits, the last two of them documentation. Suite **1058 → 1070**, webapp **55**,
green throughout. The session's product is a pinned 200-row label set; its finding is that
none of the four defects it fixed was red.

| | | suite |
|---|---|---|
| `23b1a42` | roll the docs forward for the gate fix, and recheck the +145 | 1058 |
| `99f4347` | "task 29 is blocked on people" was incomplete: the tables did not exist | 1058 |
| `c65d34b` | three defects that would have wasted the labelling session | 1058 → 1065 |
| `2f64e08` | space labellers by rank, not by name, and draw the set | 1065 → 1067 |
| `62ebf4e` | correct what the `gate_rejected` stratum promised about `job_facts` | 1067 → 1068 |
| `1d665f5` | D54–D57, and reconcile task 29's spec with the code | 1068 |
| `90170d1` | stratify the overlap block, which carries the whole ceiling | 1068 → 1070 |
| `f5a93a4` | roll the handoff forward, and retract its own "two mechanical minutes" | 1070 |

### A correction to the entry above, recorded rather than edited into it

`23b1a42` is the commit that *wrote* the preceding entry, and it also recomputed the
number that entry quotes. The four rejected phrase families were recorded at
**+17 / +5 / +5 / +123 = +145**; recompiled through `relevance.tier_sql` against the live
table they are **+0 / +3 / +5 / +128**, deduplicated union **136 rows, zero overlap**. The
entry above still reads "+145 live junk rows" at its last paragraph and "(+17 / +5 / +5 /
+123)" in its `9dab9e6` section. Both are superseded.

**The per-family counts are not reproducible constants**, which is the durable part. They
were measured against the planning session's own regex spellings and those spellings were
never written down, so a reconstruction measures different patterns and legitimately gets
different numbers. The documents now say **quote the union, not the addends**. The
conclusion is robust to the spelling either way: the families are expensive, they
concentrate in senior engineering requisitions at AI employers, and the mock corpus prices
all four at zero.

### The defects — four, none of them red

`evals label sample` was described in HANDOFF as one of "two mechanical minutes". Verified
against the code and the live database, it would have drawn a set with four separate
things wrong with it, all of them green, and all of them only expensive after ten
volunteers had spent twenty minutes each.

**1. The sampler classified against the wrong gate.** `pool()` / `pool_query()` defaulted
to `relevance.load()` — the shared `config/relevance.json` — while taking a *profile* as
the argument that names the population. Not a near miss, because `classify()` tests tier
before `match_score`: `backend/evals/labels.py:598`, `def classify(row, max_tier):`.
Measured live, **59 rows came back `surfaced` under the author's gate against 144 under
pursuit's own** — 85 postings the pipeline actively surfaces filed as gate-rejected, which
is the one stratum whose entire value is being identified correctly. Resolved with
`relevance.for_profile()`, the helper `extract.py` and `score.py` already use, and `cfg` is
now required: `backend/evals/labels.py:496`, `def pool_query(profile, cfg):`. There is no
default left that can be wrong. This also restored the point of HANDOFF's ordering
constraint — "draw the sample after the gate fix" bought nothing while the sampler read a
different gate.

**2. The recency window starved `surfaced`.** `--per-platform` defaulted to 400, which held
**29 of pursuit's 144** surfaced postings (greenhouse 6/65, ashby 13/52, google_jobs 9/26),
and `sample()` takes what a stratum has and moves on, so the set would have looked fine.
`PARTITION BY platform` answers CLAUDE.md's "~85% greenhouse/ashby" complaint and does
nothing about the truncation underneath it. Default raised to the whole table;
`cmd_label_sample` now exits 2 when a stratum under-fills.

**3. Distinct coverage was capped at one labeller's throughput.** `next_item()` ordered
every labeller's queue `overlap DESC, position ASC` — identically — so ten volunteers doing
twenty postings each answered the same twenty. In

```
distinct = overlap + n_labellers * (budget - overlap)
```

the second term was structurally zero and task 29's ">=100 postings from >=5 labellers" was
unreachable **at any turnout**.

**4. The overlap block was stratified by nothing.** Found by inspecting the ten shared rows
rather than trusting the strata totals: **6 gate_rejected / 3 surfaced / 1 below_floor**
against a set that is 25/50/25, about a 2% draw, and `sample()` had no mechanism to prevent
it. It matters far beyond its size because the overlap block is the only part of the set
more than one person sees, so it carries the **entire** inter-annotator ceiling. Six of ten
rows would have been postings the pipeline threw away — *"Senior Mechanical Engineer,
Systems Integration"*, *"Branch Operations Coordinator Borough Park"* — on which every
labeller answers Axis B "no" and agreement is free. That is evaluating on the population
the pipeline already chose, one level in. The mechanism and the measured first draw are now
in the source: `backend/evals/labels.py:704`, `# THE OVERLAP BLOCK IS STRATIFIED, NOT THE
FIRST n BY job_id. It carries`. Allocated proportionally by largest remainder, the redraw is
**5 surfaced / 3 below_floor / 2 gate_rejected** against an expected 5/2.5/2.5, and the rows
read as real judgement calls — AI Engineer at Brex, Legal Engineer at Harvey, Operations
Analyst at NYC DYCD.

## The finding: hashing spreads people at random, and random windows collide

Defect 3's first fix rotated each labeller's tail by `sha256(labeller_id)`. Verifying the
coverage claim **against the drawn set rather than against the formula** showed the formula
was optimistic — it assumes disjoint windows, and hashing does not give them. Over the real
190-row tail, ten labellers at twenty postings each:

| | distinct postings | task 29 DoD (>=100) |
|---|---:|---|
| hashed offsets | **84** | misses |
| rank-spaced | **110** | meets |

Same sitting, same set, **26 postings of difference**. `tail_offset()` now takes a rank and
spaces it by `2**64/phi` — `backend/evals/labels.py:1042`, `_PHI64 = 11400714819323198485`
— which tiles the tail into k near-equal windows for any k without any labeller knowing
what k is. The rank is *derived*, not stored: `backend/evals/labels.py:1066`,
`def labeller_rank(conn, label_set, labeller_id):`. `labelled_at` is written at insert time,
so nobody can acquire an earlier first label than someone already ranked and no rank moves
once assigned — which keeps the walk resumable, the property the hash was chosen for.
Re-verified on the redrawn set: 10 labellers × 20 → **110 distinct**; 5 × 28 → **100**.
Both meet the DoD. **D56.**

## What landed

- **The set is drawn and pinned.** `pursuit-v1`, n=200, seed 0, overlap 10, against the
  cohort gate and the full window: **surfaced 100 / below_floor 50 / gate_rejected 50**,
  nine platforms, none above 54, `sha256(sorted job_id)`
  `afb2d58f5d369dfd03ad9237a8b16396cea31b838a67343f51aceecf70cd1763`. Six rows recomputed at
  or above the floor and were excluded from `below_floor`. Fixture:
  `backend/evals/fixtures/labelset-pursuit-v1.jsonl`.
- **The pin did not move across the overlap redraw.** Same digest, because set *membership*
  is unchanged and only which ten rows are marked shared moved. The redraw was safe because
  `eval_labels` was empty, **which the redraw checked and refused on rather than assumed**.
- **`eval_label_sets`, `eval_label_items`, `eval_labels` exist in the live database**, with
  `jobs_web` holding SELECT / SELECT+INSERT / sequence USAGE. `eval_labels` empty.
- **`--dry-run` no longer overwrites the fixture on disk** while printing "nothing
  registered in the database", and `sample()`'s unread `max_tier` parameter — a second,
  disagreeing knob for the gate boundary — is gone.
- **D54–D57** in DECISIONS, and a nine-item correction block at the head of
  `29-labelling-session.md`.

## Verification that caught things, in order of value

1. **Auditing the drawn set structurally instead of reading the totals.** It produced
   defect 4, and separately found **24 of the 50 gate-rejected rows carrying `job_facts`**
   against a comment saying there is no facts row either (`62ebf4e`). The comment was false
   *when written*: extraction is shared and its queue is the union over active profiles, so
   everything `tech` and `frontend` pulled in before task 12 flipped the active set still has
   facts under a gate that now rejects it. The stratum is unaffected — rejection by the
   profile's gate is what defines it — and the 24 are a bonus, since Axis A on them can be
   read against an extraction the cohort gate never asked for. What *would* have mattered was
   checked and holds: **0 of the 50 carry a `pursuit` `job_matches` row**, and corpus-wide
   **0 of 144 pursuit matches are tier > max_tier**.
2. **Checking a claim against the drawn set rather than against the arithmetic.** The
   84-vs-110 finding exists only because the formula was re-run on real data.
3. **Reading the task's own arithmetic for consistency.** "10 volunteers × 20 postings" and
   "overlap 20 across everyone" cannot both hold — a 20-row block against a 20-posting
   sitting yields 20 distinct postings. The task was impossible as written; resolved at
   overlap 10, which reaches 110 and knowingly changes one DoD line. **D57.**
4. **Re-resolving every code citation against the committed source.** The first pass
   drifted, because `labels.py` moved under the writers while they wrote. One of the
   session's own code comments had drifted the same way and was fixed with the docs
   (`__main__.py:284`).

## Method notes worth keeping

- **HANDOFF's own credibility repairs are worth more than its content.** `f5a93a4` retracts
  two of its claims: **`fastapi` IS installed**, in `backend/webapp/.venv`, and the webapp
  suite passes 55/55 under it — the "five modules fail to import" claim was made with system
  python, and the consequence is that serving `/v1/label` needs no install and no code. And
  `tests/test_labels.py:423` **does not** forbid mock rows in `eval_labels`; it is a
  platform-pooling assertion. The containment is real but lives elsewhere, so the conclusion
  survived its citation being wrong — which is the only reason it was safe to correct in
  place.
- **"Mock data may already answer this" is the easiest mistake this repo affords.** It was
  made out loud once and is now answered in three places: `docs/tasks/refactor/mock/` holds
  55 postings that **do not exist**, invented to a specification. They pre-answered exactly
  one question of task 29's strata — gate recall, which step 0 acted on — and reduced its
  scope by **zero postings**.
- **Never train on this set.** Pinned by sorted `job_id`, per CLAUDE.md. Nothing else moved:
  `job_matches` (3,521), `job_scores` (1,293) and `job_facts` (5,923) content digests
  byte-identical either side of the session.

---

# Session — task 29 unblocked (2026-07-30)

Six commits. Suite **1070 → 1166**, webapp **55 → 75**, green. At the end of it there is no
blocker left on the labelling session that is not a person.

| | | suite | webapp |
|---|---|---|---|
| `38a3435` | lift the paired bootstrap out of the sklearn probe | 1070 → 1109 | 55 |
| `1088c7f` | print the number task 29's DoD is actually about | 1109 | 55 |
| `6adb542` | make the intra-annotator ceiling collectable; `role_track` on the form | 1109 → 1160 | 55 → 61 |
| `a666694` | roll the docs forward; settle which human ceiling task 29 measures | 1160 | 61 |
| `5fb2b72` | answer three questions the handoff had left implicit | 1160 | 61 |
| `4374ede` | unblock task 29, and guard the pin before the first label closes it | 1160 → 1166 | 61 → 75 |

### The defect — the fifth, and the same shape as the four before it

**No round-2 label was reachable.** The storage was right all along: both partial unique
indexes key on `round_no`, and `record()`'s docstring says *"A revision is round_no 2, which
is the intra-annotator measurement"*. But `webapp/label.py` never passed `round_no`, and
`next_item()`'s queue filter had no `round_no` predicate, so once a labeller answered a
posting it was never served to them again. **`intra_annotator()` was correct, tested, and
unreachable from production** — nothing red, tests green, expensive only after ten
volunteers have spent their twenty minutes.

Round 2 now re-serves the **overlap block** and nothing else
(`backend/evals/labels.py:1229`, `def next_item(conn, label_set, labeller_id, *,
round_no=1, now=None,`), so both ceilings are measured on identical postings and can be read
against each other rather than differing for two reasons at once. It re-asks only what that
person actually answered: not blanks, not abstentions, and not rows younger than
`ROUND_TWO_DELAY_DAYS` (`backend/evals/labels.py:1114`, `ROUND_TWO_DELAY_DAYS = 7`), checked
**per field** at both render and write.

**Each exclusion was a defect first.** The blank case, filed as round 1, created a fresh
round-1 row that a round-2 row could partner minutes later — because eligibility was judged
per posting on the *other* fields' timestamps, and `intra_annotator()` never reads
`labelled_at` at all. The seven days are the measurement, not politeness: served an hour
later it measures memory. **D58, D59.**

## What landed

- **`role_track` is a sixth question on the form**, for a different reason from its four
  neighbours. They are there because task 06 measured the model unstable on them; `role_track`
  has **no task 06 figure at all**, and is there because task 30 groups its precision figures
  by a vocabulary nothing has ever validated. The rows where the label buys most are the rows
  where the model is **silent**: NULL on **261 of 917** `job_facts` at v3 (2026-07-30) and on
  **82 of pursuit-v1's 200**. If a human confidently assigns a track where the extractor
  abstained, the NULL rate is an extraction problem; if they cannot either, the vocabulary is
  wrong. **D61.**
- **`NO_TRACK_FITS`**, because the vocabulary lacked the value the question needs.
  `extract.py` tells the model null means *"no listed track clearly describes the role"* — a
  verdict — while the form's *"I can't tell from this posting"* is an abstention, and
  `validate()` collapsed both to NULL. `backend/evals/labels.py:184`,
  `NO_TRACK_FITS = "no_track_fits"`, kept distinct in storage and folded only at comparison,
  in `as_model_domain()`. `role_track` was also missing from `FIELD_KINDS` entirely — the
  drift that file's own comment warns about. **D60.**
- **Four volunteer-facing pages, not two**, because "come back Tuesday", "you have no round-1
  answers", "that is all for now" and "you are finished" are four states, and telling a
  volunteer the wrong one ends their part in a measurement that has no second sitting. Three
  of the four bugs reviewed out of this path lived in the page while the queue was correct
  throughout.
- **`evals label status` prints set-wide `COUNT(DISTINCT job_id)`.** Nothing computed it
  before — `progress()` gives each person their own and `/v1/label/progress` reports only the
  caller's. The gap matters most on the night it is needed: the label count now runs about
  **six times ahead of coverage**, because `role_track` made it six questions per posting, so
  *"120 labels from 6 labellers"* is twenty postings and reads like progress toward 100. The
  per-labeller distinct counts beside it are what distinguish a **turnout** shortfall from a
  **throughput** one — two different remedies, and only one is fixed by sending another email.
  Round-2 rows are named separately as adding no coverage. `--label-set` now scopes **before**
  anything is counted; it did not, so with more than one set the label count spanned every set
  while the posting count beside it did not.
- **`manage_app_users.py set-profile`** (`backend/webapp/manage_app_users.py:136`,
  `def cmd_set_profile(args):`). `app_users.email` is UNIQUE and `add` refuses an existing
  address, so a user could not be moved between profiles by any supported path — only a
  hand-written UPDATE, which README tells operators not to do because it skips the
  `profiles.load_one()` check standing in for the absent foreign key. Sessions are
  deliberately **not** revoked: `require_user` re-joins `app_users` on every request, so the
  next request already sees the new value.
- **`labels.redraw_refusal()` / `SetAlreadyDrawn`** (`backend/evals/labels.py:802`,
  `def redraw_refusal(conn, label_set, rows):`; `:784`, `class SetAlreadyDrawn(ValueError):`).
- **The credentials landed.** OAuth in; `FRONTEND_ORIGIN` and `ALLOWED_ORIGINS` point at
  `:8421` rather than the `:5173` nothing serves; the owner's `app_users` row moved from the
  paused `tech` profile to `pursuit`. The sign-in chain was verified end to end **without a
  browser** — `/v1/label` 302s to `/v1/auth/login`, which 302s to Google carrying the right
  `redirect_uri` and PKCE S256.
- **`LABELLING-NIGHT.md`** is new, and gains a Case A (solo, localhost) variant alongside
  Case B for when Builders arrive.

## The finding: `set-profile` was not tidying, and the redraw guard was not either

Both were filed as conveniences and both turned out to be the last chance to prevent an
irreversible write.

**Labelling one posting while still on the paused `tech` profile would have recorded that
`would_apply` answer as a tech preference permanently.** Axis B labels are stamped with the
**session's** profile — `backend/webapp/label.py:440`,
`profile=user.profile if q.axis == labels_mod.AXIS_B` — and `eval_labels` carries no UPDATE
and no DELETE grant, because *a label is evidence*. There is no correction path.

**`register_set()` used `ON CONFLICT DO NOTHING` on both tables**, so re-running
`evals label sample` with a different `--seed` did not error: existing items kept their old
position and overlap flags, new `job_id`s were appended, `eval_label_sets.n` and
`job_id_sha256` went on describing the first draw, and `--out` overwrote the committed
fixture. `digest()` was computed and never compared to the stored hash anywhere. An
identical re-draw stays allowed — that is crash recovery — but **any label at all refuses
even an identical-digest redraw**, because the job ids are the digest's only input, so a
draw that keeps them and moves the overlap flags hashes the same while changing what every
labeller was shown. Verified live on both the dry-run and write paths: **exit 2, fixture
byte-identical, 200 items intact.**

## The bootstrap, and why it was moved rather than imported

Task 30 needs a paired bootstrap over **human** labels to compare two orderings. The only
one in the repo was inside `tools/learned-ranker-probe.py`, fitted against
`job_scores.fit_score` — CLAUDE.md's L1 layer, which *"never evaluate on the layer you
trained on"* puts off limits for exactly that comparison. It is also numpy, which is not in
`requirements.txt`, so it does not run on a clean checkout. Lifted to
`backend/evals/metrics.py:705`, `def bootstrap_delta(scores_a, scores_b, labels,
metric=None, *,`, as stdlib, and fixed on the way:

- **A degenerate resample — one containing no positives — was scored 0.0.** Its true average
  precision is undefined, and 0.0 on **both** arms makes that draw's delta exactly zero,
  which drags the mean toward zero and narrows the interval. It manufactures *"not
  distinguishable"* out of an arithmetic guard. Rare at n=200; **routine at the per-`role_track`
  n of about a dozen task 30 needs** — one positive in twelve rows makes (11/12)^12 ≈ 35% of
  draws degenerate. Measured, on twelve rows with one positive, a perfect ordering against its
  own reverse: **+0.917 [+0.823, +0.917]** here against **+0.917 [+0.000, +0.917]** with the
  substitution — *"better"* versus *"not distinguishable"* on the same data, 400 draws, seed 11.
  Skipped draws are counted; `backend/evals/metrics.py:625`, `def draws_used(self):`. Below
  `MIN_USABLE_FRACTION` the value is None rather than a number computed on a biased subset.
- **The point estimate is the observed delta on the full paired sample**, not
  `np.mean(deltas)` — the probe returned the bootstrap's estimate of the mean, which differs
  by the bootstrap bias and is a headline number no reader can recompute from the corpus.
- **Deterministic by default**, and the seed travels in the return value.
- `Delta` is a **10-tuple** for the reason `Ranked` is a 5-tuple: `d, lo, hi = ...` raises
  rather than quietly discarding the drop counts (`backend/evals/metrics.py:548`,
  `class Delta(NamedTuple):`).

The probe keeps its own copy; repointing it is a rewrite of its call sites, not an import.
**D63.**

## Verification that caught things, in order of value

1. **Reading three documents against each other instead of each on its own.** Which human
   ceiling task 29 measures was disputed by 07:54-59 ("inter-annotator *becomes* the ceiling",
   "costs nothing extra"), 07:81 ("inter, not just intra"), 07:77 (inherits 03's DoD wholesale)
   and 03:142 (self-agreement beside every number) — **each internally consistent, which is why
   nobody had to resolve it**. Recorded: "becomes" is retracted, they are different quantities,
   both are collectable on identical postings, and the **spending** question is explicitly left
   open. Asking ten volunteers for a second ten minutes is a judgement about people donating
   their time; it belongs to the repo owner on the night, and no document here decides it.
   Meanwhile 03:107 claimed the tool *"supports a second pass over already-labelled jobs"* —
   false from the day it was written until this week, and true again now.
2. **Testing field MEMBERSHIP rather than `.get()`.** On `role_track` a present null is a
   verdict and an absent key is silence, and `pursuit-criteria-corpus.jsonl` carries
   `role_track` on **0 of 859 rows** — so every real human answer would have scored as
   agreement with a model that never spoke.
3. **Checking HANDOFF's dependency graph against the task files it describes.** Three
   corrections: task 08 is **not** waiting on labels (neither of its files mentions "ops" or
   "shortfall"; its open clause waits on `job_events`, and the label-blocked ops question is
   task 13's); task 29 does **not** block task 31, whose own header depends on 27 and 26 and
   whose body never mentions labels; and `calibrate-match.py` **cannot consume human labels at
   all** — its ground truth is `job_scores`, the LLM, which is precisely the circularity
   CLAUDE.md's L0/L1/L2 rule forbids. HANDOFF had named it as what makes re-tuning legitimate.
4. **Dating every `role_track` measurement.** `docs/facts-v3-diff.md` reported a NULL rate of
   **27.7% from 239 of 863**, and the 2026-07-29 measurement was **244 of 881, also 27.7%** —
   two different populations, one rounded number, and anyone finding both would read them as
   confirming each other. The 2026-07-30 figure, **28.5%**, breaks the coincidence. Superseded
   figures are marked, not deleted; the nightly ran mid-session and moved one of them.
5. **Verifying five "Status: todo" task files against git.** All five had landed, and 13's
   made task 26 look blocked on unstarted work. Both suite counts were low and went stale
   **again** mid-session under parallel agents — recorded as the **eighth** instance rather than
   quietly overwritten.

## Method notes worth keeping

- **Four values have to agree for sign-in and only one of them errors.** A
  `GOOGLE_REDIRECT_URI` not registered in the Google console fails with
  `redirect_uri_mismatch` before the request reaches this service. `FRONTEND_ORIGIN` wrong
  lands sign-in **nowhere**; `ALLOWED_ORIGINS` wrong makes the browser drop the session cookie
  **silently**; and `SESSION_COOKIE_SECURE` is a trap in the *other* direction — it defaults to
  true, `.env` sets it false which is correct for plain HTTP, and leaving it true over HTTP
  makes login look successful with every subsequent request signed out. This is
  CLAUDE.md's "silence is this system's failure mode" wearing a deployment costume.
- **The inter-annotator ceiling is the scale every other number is denominated in.** The same
  "model agrees 80%" means *fix the prompt* at a 98% ceiling and *stop working on this* at 79%.
  It is responsible for that **structurally** rather than by convention: it is one of the three
  fields `Interpretable` refuses to be constructed without, and `Interpretable` is the only
  thing `render_labels()` accepts — so a night that produces no ceiling produces **no report**,
  rather than a report with a caveat.
- **A guard test widened deliberately is not a guard test loosened, if the trade is written
  down beside it.** `_render_form`'s parameter allowlist admits `round_no` and `blank` (neither
  carries a pipeline verdict; `stratum` still does not), and the FROM-count in `label.py` became
  an assertion on table names plus a JOIN scan. `seniority_guess` joins stay **forbidden** — it
  is `guess_seniority(title)` and the form asks what seniority the *posting* asks for. **D62.**
- **The one existing `app_users` row is documented as a counter-example**: read it for shape,
  not values. `profile` has no foreign key, which is why `add` will happily seed a user against
  a paused profile, and exactly how that row ended up on the inactive `tech`.
- **The first finding of the labelling session arrived before the first label.** No `ARCHETYPE`
  or `ROLE_TRACK` value expresses a commercial role selling AI products, though the cohort wants
  them — the gap task 12 predicted and could not name. `ai_involvement` separately conflates
  "uses AI" with "sells AI", so a strong target scores `none` and reads as task 05's
  6.7%-precision false positive. **n=1, recorded, not acted on.**

---

# Session — the first labels (2026-07-31)

Two commits. Suite **1166 unchanged**, webapp **75 → 93**, green. A design session's four
findings were re-verified against the real repo, and the number this whole run has been
planning against became measurable for the first time.

| | | suite | webapp |
|---|---|---|---|
| `127c7c0` | verify a design session's four findings, and measure the labelling rate | 1166 | 75 → 93 |
| `820351d` | roll the handoff forward: labelling started, and the budget was wrong | 1166 | 93 |

The design session ran against a **shallow clone**, so its numbers were treated as claims to
reproduce rather than measurements to quote. Three reproduced, one did not, and one premise
was wrong.

### Does not reproduce

**The score range for the worked example is 13–88, not 13–98.** 13 is exact. Reaching 98
needs a **third** flip — `gap_friendly_language`, which self-agrees **100% [96.8–100]** — so
quoting 98 as the range of *two* flips borrows a flip from the one field that never flips.

### Wrong premise, and it makes the finding stronger

The posting had **already been extracted and matched**. Notion's *"Commercial Solutions
Consultant, New York"* (`8ba8616b7c91d2a1b5112cdc`) is `job_facts` `mid` × `uses_ai_tools`
at `match_score` 63, **rank 42 of 152**. So the two flips are recorded as a counterfactual on
a **measured row** rather than a simulation over hand-written fact vectors. Flipping only
`ai_involvement` to `none` takes a junior version to **38 — below `MATCH_FLOOR`, where no
`job_matches` row is written at all**. The conflation is a **deletion, not a re-ranking**.

### Reproduces, and worse than stated

The entry-level gate group hits on `\yspecialist\y` **alone**, from *"troubleshoot in front of
a customer without a specialist in the room"* — a clause whose subject is a person the team
does **not** have. Neither `title_include` group matches the title, so one incidental word is
the only thing between this posting and tier 3; rewrite the clause and the posting is never
extracted, for no change in the job. Recorded in `backend/config/pursuit-relevance.json:10`,
`"_entry_level_note"`, **documentation only** — `relevance.load()` strips `_` keys, verified,
and the emitted SQL is byte-identical to the live profile row's. It is a different shape from
the known `\yassociate\y` / `\yanalyst\y` weaknesses: those are precision leaks with
`title_exclude`'s seniority block as a backstop, this is a **recall leak with no backstop in
either direction**, because nothing can exclude on a word that is doing its job in a
subordinate clause.

### Reproduces, with a correction

`mock-postings-v3` is **29/25/1** with all 29 good entries junior. But `good <=> junior` is
**not** a biconditional — 10 bad entries are junior too. The claim the consequence rests on is
`good => junior`, which holds at **29/29**. All 29 good entries are also `uses_ai_tools`, so
`ai_involvement` is **unfalsifiable** against that corpus for the same reason.

## The finding: the twenty-minute budget was out by ~2.5x

Labelling started, so the per-posting rate is measurable from `eval_labels.labelled_at`
rather than from a stopwatch. **Median 170 s, mean 154 s over 5 postings.** Twenty minutes is
therefore **~8 postings, not ~20**, and the "one second person, ten minutes" unblock is
**~26 minutes**. Corrected in all three places that claimed it.

HANDOFF had asked three separate times for this number and warned each time against inventing
a correction factor for it. The consequence is a change to how people are **asked**, not just
a number: asking for a ten-minute favour and then keeping somebody for half an hour is how
the second labeller does not become a third.

**The standing recommendation changed with it.** "Label more" is no longer the highest-value
action — every field in the report is refused for want of a **second `labeller_id` on the
same item**, not for want of volume, so the tenth row from a second person beats the
hundredth from the first.

**And the redraw instruction became moot rather than live.** 30 labels closed the window, so
"do not redraw" is now a property of the system instead of a rule to follow. Recorded with
its cost, which is already visible: a mid-level bridge role that is exactly the hard case
worth labelling cannot be added to the set.

## What else landed

- **`app_users.prior_domain`** — nullable, closed vocabulary derived from
  `pursuit-persona.json`'s `background_summary`. `eval_labels.labeller_id` is `app_users.id`,
  so decomposing Axis B disagreement by background is a **join**; `inter_annotator()` and
  `interpretable()` are untouched and nothing reads it yet.
- **A correction to `manage_app_users.py`'s own header**: `extract.py` does **not** fan out per
  profile. It hands one `cfgs` list to `relevance.union_sql`, an OR across gates, so N profiles
  sharing one gate cost **zero** extra extraction. `score.py` is the one that fans out.

## Method notes worth keeping

- **Deliberately not computed: model-vs-human agreement.** `evals label report` exits 2 at one
  labeller **by design**, and a document has no exit code. That asymmetry is the whole reason
  the refusal has to be restated in prose every time.
- **A superseded number outlives its correction if it is quoted in an instruction file.** The
  "76% / 94%" self-consistency floors are the **n=17** pair; live they are **85.2%** and
  **94.8% at n=115**. They were amended in HANDOFF here. `.claude/CLAUDE.md:56-58` still reads
  *"76% on `seniority_level`, 94% on `ai_involvement`"* — the superseded pair, in the file every
  session is told to read first. Recorded, not acted on: that file is not this run's to edit.

---

# Session — the rate re-derived at n=29 (2026-07-31)

Two commits. Suite **1166 → 1171**, webapp **93**, green. The sitting kept going, and the
number the previous entry had just published reversed.

| | | suite | webapp |
|---|---|---|---|
| `d368825` | re-derive the labelling rate at n=29, and find the gap is commercial | 1166 → 1171 | 93 |
| `3baa746` | give the handoff a sixty-second entry point, and name the placeholder trap | 1171 | 93 |

**30 rows over 5 postings became 186 over 31**, one labeller, one night. **All ten `overlap`
rows are answered**, which changes the ask: a second labeller's ten rows now complete the
inter-annotator ceiling immediately, with no further work from the owner.

## The finding: the stopwatch reading reverses

**154 s was correct arithmetic over four intervals. At n=29 the median is 93 s.** The four
sat entirely inside a warm-up curve — **first quartile 137 s, last 83 s** — and the caveat
printed beside them asserted the *opposite*, that "the fastest interval is the first, which is
the opposite of a warm-up curve".

Both numbers and the n each was taken at stay visible. The consequences:

| | at n=4 | at n=29 |
|---|---|---|
| per posting | 154 s | **93 s** |
| ten overlap rows (the second labeller's ask) | ~26 min | **~16 min** |
| the DoD's 100 postings | 4.3 h | **2.6 h** |

**The re-check that overturned it is the one the previous note asked for**, which is the
durable part: an instruction to re-derive that requires someone to write four lines of SQL
first is an instruction that decays into a quotation. It decayed twice.

## What landed

- **`backend/tools/label-findings.py`** — so the next session runs a command instead of
  writing the SQL. **Read-only, no LLM, no API key**, and it deliberately prints **no
  model-vs-human agreement**: `evals label report` still exits 2 at one labeller and nothing
  here routes around it. Five tests pin the break threshold and the curve's refusal to invent a
  trend on too little data.
  - `backend/tools/label-findings.py:157`, `def interval_stats(intervals, break_secs):` — pure,
    separated from the printing, because *"this is the number that has already been published
    wrong once, off a sample of four"*.
  - Intervals print **raw, in order, before any statistic**: a sitting contains breaks, and a
    median over a list containing a 96-minute gap is a statistic about dinner. Both the
    including-breaks and excluding-breaks figures print, so the exclusion can be argued with.
  - The quartile curve refuses below twelve kept intervals — `backend/tools/label-findings.py:180`,
    `if q >= 3:` — the n below which the comparison would be two points against two points.
- **`derive-role-tracks.py` gains `--facts-version`**, defaulting to `schema.FACTS_VERSION`
  (`backend/tools/derive-role-tracks.py:210`, `def load_other(conn, facts_version):`). The
  family list had been hardcoded in two places, which is why a third family was probed, counted
  and never printed.
- **HANDOFF gets a `START HERE`**: state, the one thing on the critical path, three commands,
  three prohibitions. The file had **eight** "READ THIS FIRST" sections — a defect it had been
  recording about itself for a week without fixing.

## The finding: the vocabulary probe was reading two populations at once

`load_other()` had **no `facts_version` filter**. Its docstring said it returned every
`job_facts` row *the current vocabulary* could only call `other`; it returned rows from **every
vocabulary the project has ever had**. Correct on the day it was written — 2026-07-28, when
the current version *was* 2 — and silently wrong from task 12's bump onward, which is exactly
the interval in which the tool exists to be re-run.

**402 of the 696 `other` rows (58%) are `facts_version = 2`** — the twelve-value vocabulary,
which never contained the fourteen values the tool exists to evaluate. At v3 the population is
**294 of 940**, and the nine recommended tech values reclaim **9 of 294 (3.1%)**, not
**202 of 696 (29.0%)**.

**The conclusion this inverts is the point, not the flag.** Those 202 rows are `other` under
the *twelve*-value vocabulary on the author's *tech* corpus. The v3 population is a different
corpus as well as a different vocabulary — task 12 retargeted the extraction gate to `pursuit`
— and it contains almost none of that hardware and data-centre work, which is why the same
probes match 3 and 2 rows there. So the remaining v3 `other` bucket is **not** evidence that
the 26 values sit unused; **the 26 values are being used**, and what is left is a different,
smaller gap. `--facts-version 0` reproduces the historical figures exactly, and the population
prints in the header of every run, so no figure from this tool can be quoted without it.
**D65.**

## The finding: that bucket is commercial

One proposed value, **`revenue_commercial`, reclaims 68 of 294** where all fourteen task-11
values reclaim **at most 47**, at the widest employer spread this tool has ever probed. **The
argument that carries it is structural rather than a count**: `ROLE_TRACK` has
`revenue_operations`, `ARCHETYPE` has **no commercial value at all**, so a Deal Desk Analyst
gets a coherent track and can only be `other` at the finer grain.

**Proposed and not applied.** `pursuit-v1` is being labelled now; `job_facts`' primary key is
`job_id` **alone**, so re-extraction *overwrites* the answers the first 31 postings were
labelled beside rather than keeping them at the old version; and `eval_labels` records
`labelled_at`, `round_no` and `labeller_id` but **no `facts_version`**, so nothing would mark
which extraction a label was formed against. Cost is not the objection — task 12 measured the
whole re-extraction at 863 calls / 28m31s / ~$0.33. **D64.**

## The finding: the recall question is earned

Three postings the pipeline did **not** surface are ones the labeller would apply to
(`29-labelling-session.md:691-693`):

| | stratum | why the pipeline missed it |
|---|---|---|
| **Brex — AI Engineer, Ecosystem** | `below_floor` | `ai_involvement = builds_llm_features` |
| **Ramp — Software Engineer, Accounting** | `gate_rejected` | **no `job_facts` row at all** |
| **Twilio — Frontend Software Engineer** | `gate_rejected` | `ai_involvement = none` |

Recorded as **evidence for task 29's "gate too tight" branch, not as the branch taken**: the
three Wilson intervals overlap almost completely, and the one labeller is a software engineer
by background against two plain software-engineering roles. That is the `prior_domain`
confound, and it is **undecomposable at n=1** — which is what `prior_domain` was added for one
commit earlier.

## Method notes worth keeping

- **A trap that is live in the database rather than in the code.** Adding the second labeller by
  following `LABELLING-NIGHT.md` § 3 **verbatim** puts `them@gmail.com` into `app_users` — the
  example address, on `pursuit`, with `prior_domain` set. It will never sign in, but `list`
  shows two pursuit rows and **reads as turnout**. There is no remove and no rename, only
  disable. Same shape as task 16 reporting success over a literal placeholder, one run later.
- **State plainly what a sitting bought, because the honest answer is the useful one.** The
  second sitting bought **three diagnostics and a better instrument, and nothing toward the
  Definition of done**. Floor, ceiling and measured are all still absent. That is not a
  disappointment — it is HANDOFF's own prediction confirmed, that the report is gated on a
  **second labeller** rather than on volume.
- **How this entry's suite numbers were derived, since the numbers in this file have gone stale
  eight times.** `pytest` is not installed in any interpreter in this checkout — not system
  python, not `backend/webapp/.venv` — so no count here was re-run. They were derived
  statically, per commit, by counting `^\s*def test_` across `backend/tests/` and
  `backend/webapp/tests/` at each tree. The method is exact for this suite: there are **zero**
  `parametrize` decorators in either directory, so collection is one test per definition, and
  the count reproduces **every** figure the commit messages state independently — 1058, 1065,
  1067, 1068, 1070, 1160 → 1166, 1166, 1171 and webapp 55 / 61 / 75 / 93, twelve agreements,
  no disagreements. `subTest` appears in 10 files and does not change the collected count.
- **1171 is the count at `3baa746`, and the working tree already disagrees with it.** Measured
  the same day, `backend/tests/` in the working tree counts **1178** — `+7`, all of them in
  `tests/test_workday_fixtures.py` (41 → 48), which is **uncommitted**: `HEAD` is still
  `3baa746` and its tree still counts 1171. The delta belongs to a later session than anything
  in this entry and must not be attributed to `d368825` or `3baa746`. Recorded because the
  ninth staleness in this file would otherwise be somebody reading 1178 off a terminal and
  concluding the entry above is wrong.
- **Every figure in this entry was re-derived on 2026-07-31, not quoted from the commit
  message.** `python3 tools/label-findings.py` prints `186 label rows / 31 postings / 1
  labeller(s) / 1 round(s)`, below_floor 3 / gate_rejected 9 / surfaced 19; median **93 s**
  excluding breaks at **n=29**, 97 s including them at n=30; first 7 mean **137 s**, last 7
  mean **83 s**; 10 overlap rows **16 min**, the DoD's 100 postings **155 min (2.6 h)**. The
  one excluded interval is **5,765 s** — the dinner the raw-intervals rule exists for. This is
  the tool doing the job it was built for one session earlier: the re-derivation cost one
  command, which is the only reason it happened at all.

---

# Session — the fixture described a route that had never existed (2026-07-31)

**No commits.** `HEAD` is still `3baa746` and every change below is in the working tree.
That is unusual for this file — it records landings — and is stated first so no reader
attributes any of it to a commit that does not contain it. Suite **1171 → 1178** (+7,
every one of them in `tests/test_workday_fixtures.py`), webapp **93**, both green and both
*run* rather than derived.

| | | suite | webapp |
|---|---|---|---|
| `evals/workday_fixtures.py`, `tests/test_workday_fixtures.py` | failure 3's fixture: the status was 422, and the status was the smaller error | 1171 → 1178 | 93 |
| `docs/ingest/workday.md` | two follow-ups retired, one of them by re-reading a recording nobody had opened | — | — |
| `app_users` (a row, not code) | the placeholder labeller disabled | — | 93 |

Nothing here moved task 29 forward. It closed three claims that were being carried as
true, and two of the three were being carried in files a new session is told to read
first.

## The finding: a fixture can hold a correct conclusion and a route that never existed

`workday_fixtures.prefix_assumed()` modelled a wrong Workday data centre as **404 with an
HTML body**, and rested the argument on the caller json-decoding that HTML. Its old
docstring, verbatim: *"the wrong host answers with an HTML error page, so a caller that
json-decodes it gets a JSONDecodeError, which every ingest script in this repo catches"*.

**The status was wrong, and that was the smaller error.** The recorded `nvidia.wd1` probe
in `ats-validation.json` answers **HTTP 422**, `application/json;charset=ISO-8859-1`,
body `{"errorCode":"HTTP_422","errorCaseId":"38B497MS4CIBJB","httpStatus":422,…}` — a body
that *parses*. So no `JSONDecodeError` was available from the real bytes.

**No decode happens at all, at any status.** `json.loads` sits *outside* the fetch:
`ingest/workday.py:371` is `return json.loads(http.get_text(`, and `lib/http.py:76-77` —
`if e.code != 429 and not (500 <= e.code < 600):` / `raise  # permanent -- surface
immediately` — re-raises first. 422 is neither 429 nor 5xx, so it surfaces on attempt one
and `json.loads` is never reached.

**The sharpest form, and the reason this is a finding rather than a typo: that mechanism
could not have occurred under the fixture's own 404/HTML bytes either.** The replayer
raises before the body is touched — `evals/cassettes.py:448`, `if interaction.status >=
400:` — so under replay *and* under live urllib the HTML the fixture supplied was never
going to be decoded by anything. The docstring described a route through the code that
does not exist and never did, in either direction of the seam.

**Its tests stayed green because they asserted the conclusion, not the claim.** The three
old tests asserted `caught.exception.code == 404` (against the fixture's own literal — an
assertion of a constant against itself), that the naive shape collects nothing, and that
the real loop raises `Shortfall`. **The `Shortfall` test would have passed unchanged
against the correct status**, because 404 and 422 take a byte-identical path: both
permanent at `lib/http.py:76`, both absent from `ingest/workday.py:237`'s
`BLOCKED_STATUSES = (401, 403, 406, 429, 451)`. Nothing anywhere tested the sentence that
was false, so nothing could go red.

The fix keeps the conclusion — a wrong prefix is one more failed tenant in a fifty-tenant
loop — and replaces the route with a traced one, five hops with a `file:line` each
(`evals/workday_fixtures.py:222-240`). **No 404 case was kept**, deliberately and with the
reason recorded: no Workday host in any cassette in this repo has ever answered 404 (the
other recorded 404s are the greenhouse, icims, recruitee and workable no-such-tenant
probes), and a second interaction would discriminate nothing given the identical path.

## The finding: `prior_domain` cannot decompose the confound it was added for

The placeholder disable made this visible, which is the only reason it was found. The
owner's `app_users` row has `prior_domain` **NULL** — `manage_app_users.py list` prints
`domain=-` — and it cannot simply be filled.

`schema_web.PRIOR_DOMAINS` (`backend/webapp/schema_web.py:116-120`) is a **career-changer**
vocabulary: `healthcare, education, retail, hospitality, logistics, administration,
trades, military, other, none`. The first eight are `pursuit-persona.json`'s
`background_summary` verbatim. The one labeller is a **working software engineer**, and
the list has no value for that: `none` would be false — the field's own comment is
explicit that *"a Builder with no prior domain is a real answer about a real person"* —
and `other` is priced as no-information, so it says nothing.

**So the recall question's second caveat stays undecomposable even at n=2.** The previous
entry recorded it as undecomposable *at n=1*, with `prior_domain` as the instrument that
would fix it once a second labeller existed. It will not: a second labeller's domain
against a NULL is not a decomposition, and the value that would make it one is not in the
vocabulary.

**Recorded, not fixed.** Widening the tuple is not a one-line edit —
`schema_web.py:122-129` generates `_PRIOR_DOMAIN_CHECK` *from* `PRIOR_DOMAINS`, on purpose,
so the vocabulary and the database constraint move together. That is the right design and
it is exactly why the change is not a working-tree afterthought.

## The finding: shortening the round-two delay buys nothing

Shortening `ROUND_TWO_DELAY_DAYS` (7, at `evals/labels.py:1114`) was proposed as a way to
get a ceiling out of one labeller sooner. It was examined and **deliberately not changed**,
on a structural finding rather than a preference.

`evals/__main__.py:485-487` passes **`ceiling=inter["fields"]`** — `inter_annotator()`'s
block only. `intra` is computed on the line above and rendered beside the table, but it
never enters a triple. **The intra ceiling cannot satisfy the report at any delay**, so the
delay is not what is standing between this run and an interpretable number; a second
`labeller_id` is, exactly as the previous entry concluded from the other direction.

**The durable half is about where guards live.** `intra_annotator()`
(`evals/labels.py:1584`) never reads `labelled_at` — it groups on `labeller_id` and
`round_no` and computes over whatever rows it is handed. The seven days are enforced in the
**queue** (`labelled_at <= %(cutoff)s` at `:1303`, and `round_two_ready` at `:1118`), which
is the write path. So the delay is real only as long as every round-2 row arrives through
`next_item()`; a row inserted any other way is indistinguishable to the metric. **A guard
in the write path cannot defend a number computed in the read path** — it can only make the
usual route produce good inputs.

## What landed

- **The `app_users` placeholder is disabled.** `them@gmail.com` — the literal example
  address from `LABELLING-NIGHT.md:349` — was on profile `pursuit` with `sessions=0`, and
  made `list` read as two labellers. That trap is the last method note of the entry above;
  this is it firing, in this database, one session after it was named. `disable` is the
  only path (the subcommands are `add`, `set-profile`, `list`, `disable`, `enable`,
  `sessions`, `revoke-sessions` — no remove, no rename), so **the row stays visible as the
  record of the mistake**: `list` now prints it `DISABLED`, `sessions=0`, beside the one
  real labeller.
- **Two stale follow-ups retired in `docs/ingest/workday.md`.** Failure 3's "real status
  code is 422" note is struck and folded into the fixture; the "**a recording recipe is
  still owed**" claim is struck as delivered. It had stood in two files for **three days**
  after it stopped being true — `record_workday_cxs()` is at
  `backend/evals/record_cassettes.py:501` and the cassette was committed 2026-07-28 in
  `05b7fa2`, "Record the workday-cxs cassette, closing a pending follow-up".
- **`CLAUDE_UPDATES.md` was found two sessions stale and backfilled — four entries, not
  three.** The one immediately above is the last of them.

## Re-checking the retired follow-up paid, which is the argument for re-checking them

Striking the recipe claim required opening the recording, and the recording does not say
what the recipe predicted. `record_cassettes.py:510` promises *"msk is 88 postings: five
pages, the last one short"* and `:502` *"~6 requests"*. The committed bytes hold **four**
list pages over a **79**-posting board — 20, 20, 20, 19 — plus one detail document, five
interactions. Boards move; that is not a defect, and nothing reconciles against a stored
count.

**The half it did deliver is the half that mattered.** The four pages answer `total` **79,
0, 0, 0**. Failure 5's first half — `total` on the offset=0 page only — is now **RECORDED**
rather than constructed, and `record_workday_cxs()` refuses to record unless
`totals[0] and not any(totals[1:])`, so a tenant that quietly starts reporting `total` on
every page cannot silently retire the evidence for the latch at `ingest/workday.py:463-475`.

**The wrap is still constructed, deliberately.** Offsets past the end returning page one —
failure 5's second half — is not in the recording, because provoking it means issuing one
request past the end of a stranger's board purely to record a pathology, and
`collect_postings` never makes that request (the `fresh == 0` guard at
`ingest/workday.py:490`). So `total_only_on_first_page()` is no longer the only evidence for
failure 5, but it is still the only evidence for the wrap, and stays in
`FIXTURES_FOUND_LIVE` for that reason alone.

## Method notes worth keeping

- **A prediction written before the measurement, inside the artefact that disproves it.**
  "Five pages" is not only in the recipe docstring — `record_cassettes.py:546` builds it
  into the cassette's `note`, so `workday-cxs.json:7` describes itself as *"five pages
  ending in a short one"* while carrying four. The recipe was written from an estimate, the
  note was written from the recipe, and the recording was never read back against either.
  It is **not corrected here**: the note is data inside a recording, and fixing it honestly
  means re-recording, which is a network call this session was not making. The docstring at
  `:510` and `:546` is still wrong in the working tree, recorded rather than patched.
- **The suite counts in this entry were run, not derived — and the derivation was right.**
  The entry above derived 1178 statically, by counting `^\s*def test_`, because `pytest` is
  not installed in any interpreter here. It is not, and that remains true; but
  `python3 -m unittest discover -s tests` and `.venv/bin/python -m unittest discover -s
  tests` both work and were used here. They print **`Ran 1178 tests` / OK** and **`Ran 93
  tests` / OK**, confirming the static count exactly. Two consequences: the method the entry
  above documented is now validated against a real run at a non-trivial n, and the missing
  tool was `pytest`, never a test runner — that is the sentence worth carrying forward, since
  the earlier note is easy to read as "counts here cannot be re-run".
- **Assert the claim, not the conclusion.** The three tests replaced here all passed for
  three days against a docstring that named a code path that did not exist, because each
  asserted an outcome that both the true and the false mechanism produce. The replacement
  `TestTheRecordedRefusalIsWhatTheFixtureEncodes`
  (`backend/tests/test_workday_fixtures.py:582`) diffs each transcribed constant against the
  recorded bytes, and `test_the_error_body_is_valid_json_and_that_changes_nothing`
  (`:283`) asserts the *negative* the old prose got wrong — the body parses, and it is not
  parsed. A test that can only go red if the constant drifts from a recording is worth more
  than three that restate the fixture's own literals back at it.
- **`LABELLING-NIGHT.md` § 3 still creates the row that was just disabled**, and it is worse
  than the copy-paste address. `:349` is still `--email them@gmail.com --profile pursuit`
  verbatim, and `:353-354` still says *"The only row that exists today is
  `ericliu93@gmail.com` on profile `tech`"* — now false twice over: `list` shows that row
  on **`pursuit`**, and it is no longer the only row, because of this session. The same
  stale sentence appears a second time at `:71`, *"The one existing row is
  `ericliu93@gmail.com` on profile `tech`"*, so a reader who corrects one still meets the
  other. Disabling the placeholder cleaned up the instance and left the generator running.
  Not this session's file to edit; recorded because the § exists to be followed verbatim by
  someone in a hurry.
- **Nothing here was a measurement, and no model-vs-human agreement number was computed.**
  `evals label report` still exits 2 at one labeller, that is still by design, and no
  document produced in this session routes around it.

---

## 2026-07-31 — 34 landed: cleanup, bugfixes and documentation, in six commits

`3383f9a` `3f42e2d` `3c4cee0` `46a5be4` `bcf5fc6` `99fbdb1`. Suite 1178 → **1182**
(main) and 93 (webapp), both run rather than statically counted. 0 broken doc links.

**This entry exists because the last thing this file recorded about itself is that it had
silently stopped being written for four sessions.** The convention is that all four
documents move in the same turn as the commits; that failed once and would have failed
again here — six commits landed before this entry was written.

### The task file written to fix stale documentation was itself stale in five places

Task 34's own §§A1–A5 were re-verified against the code before any of them was acted on,
which is what §*The rule this task runs under* asks for. Five did not survive contact:

- **Its founding premise was false.** *"This file did not exist until 2026-07-31 … it is
  specimen #1 of what this task is for."* It existed — `tranche_six/34-…`, tracked since
  `28f1d0e`. `README.md:102` linked to it **without the `tranche_six/` prefix**, the
  identical defect §A1's own table records three rows above it for the six `tranche_one/`
  links. A broken link was read as a missing file, and the remedy wrote a *second* task 34
  at the un-prefixed path — which then went on asserting the very `docs/ingest/` claim §A2
  exists to retire. It is still specimen #1, of something sharper.
- **§A1's count was wrong in both directions.** Sixteen was a pre-fix number; fourteen
  remained. But the audit was scoped to the directory already under suspicion, which hid
  **five more of the identical class** in `docs/tasks/README.md`. Nineteen total.
  §A1's *"same depth error"* grouping also prescribed the wrong fix for three of them.
- **§A2 says "ten" and lists eleven.** Eleven files carried `generated:`. The three
  "converted" files used **three different formats**, so "the established pattern" it
  points at did not exist.
- **§A5 named two stale docstring sites; there are three** — and the same false sentence
  is inside the committed cassette's own `note`, which the prescribed fix ("restate the
  docstring; do not re-record") structurally cannot reach. It also misquotes the refusal
  guard and misses a second one.

### The defect register was advertising finished work

**D45's body has said `### D45 — fixed` since task 16's follow-up landed, while its index
row said "open — needs a task".** The index is the part anyone scans. **D27's five unused
imports are all absent from `ats.py`**, verified name by name, and it too was listed as
owed to this task.

**Nine defects were dispositioned *"fix with harness — task 09"*, and task 09 landed three
tranches ago.** Nothing rescheduled them, so they were neither open-with-an-owner nor
closed. Three are now fixed, six re-marked **open, UNBLOCKED**.

**D17 was the cheapest confirmed bug in the repo and had been waiting on two lines.** A
paid Apify actor run that came back `SUCCEEDED` immediately skipped the poll loop and read
a name that was never bound — the results were never collected and it reported as one
failed query. The reproduction was already committed, asserting the `UnboundLocalError` on
purpose, with a note saying whoever fixes it flips the assertion. Flipped.

**Three recorded counts understated the defect** (D28 is 5 unused imports, not 4; D30's
`timezone` IS used and a sweep would have removed it; §A5's two sites are three). Counted
by AST binding-vs-use, because grep cannot tell an import from the word in a comment —
which is how they were miscounted originally.

### Three CLAUDE.md paths did not exist, and one rule was stale

Applied rather than proposed, on the owner's instruction — the standing rule is
propose-only, and it was wrong for a file whose instructions could not be followed at all.
`tools/relevance-report.py` → `backend/tools/`; **`tools/lib-parity.sh` has never
existed** and `lib/` is this repo's own code now; `76%/94%` → `85.2%/94.8%` at n=115;
`263 tests` → 1178/93 **with the caveat to read `Ran N tests` rather than count `def
test_`**; and the version-keys line promised three column names (`persona_version`,
`features_version`, `model_version`) that exist nowhere.

**`docs/MEASUREMENT-TRAPS.md` did not exist**, while `.claude/CLAUDE.md` ordered every
session to read it. Nor did `docs/archive/`. Both were dispositions recorded as though
already done. Both now exist.

### One environment claim was wrong, and it is the recurring shape

A survey concluded ~80 DB-gated tests silently skip here, from `env | grep DATABASE_URL`
returning nothing. **They run.** Each such module calls `envfile.load(backend/.env)` at
import *before* evaluating `scratchdb.available()`. `test_scratchdb` alone runs 12 and
passes. This is the same shape as the `fastapi` claim this run already recorded: *"it
fails to import" is a fact about an environment, not about a repo* — and the fix is to ask
which interpreter, and which loader, the observation was made with.

### The split, and the trap in it

HANDOFF.md 3,481 → 2,690 lines; seven "READ THIS FIRST" sections → three. The file
disagreed with itself about the count (`:5` said eight, `:200` said seven). Cutting on
`^## ` **outside fenced blocks** was load-bearing: two lines in that file are bash
comments inside the owner's runnable command blocks, and a naive `^#` splitter slices both
in half. Two operational subsections were deliberately kept out of the archive —
`FRONTEND_ORIGIN` and the `app_users` schema are configuration, not narrative.

`AUDIT.md` is new: one page, every figure with the command that produced it. The named
risk is that it becomes an eighth "READ THIS FIRST", so it indexes and does not restate.

---

## 2026-08-01 — Phase 9, tranche seven: tasks 36–44

**Nine commits. The tranche's own thesis got demonstrated on it three times while it was
being written.**

`9b7bb5e` **41b** — `scripts/` ignored with a why-comment, making `183b4dc`'s decision
durable instead of dependent on nobody typing `git add -A`. **And `.claude/CLAUDE.md`
stopped being ignored**, by the owner's decision: it is the brief every session reads
first, and while it was ignored a correction to it could be made and could not be
committed. Landing it early is what let tasks 38 and 40 commit their edits to that file
at all.

`0110473`, `b64d7a6` **39** — `D` is defects, `DEC` is decisions, one allocator declared in
each register's header. The twenty `D46`–`D65` entries became `DEC-46`–`DEC-65` with
numbers preserved and `<a id="dNN">` anchors left behind. **`D46`–`D65` are burnt in the
defect register and next free is `D66`**, because those numbers still circulate as decision
IDs in the two `kind: record` histories that were deliberately left unswept. The trap was
that the identifier to change and the identifier to leave alone are the same string:
`ats-discover.py`'s dozen `D45` citations all mean the defect, were read one by one, and
`git diff` on it is empty. `sed` would have corrupted them and the suite would have stayed
green while it did.

`57c34a5` **36** — `backend/tools/audit-docs.py`, six checks, wired into the suite as the
repo's first doc test. It lands **red in the CLI and green in the suite** against a declared
baseline, which `DEC-68` records with `expectedFailure` and exact-match both rejected. C5
went 22 → 0 when 39 landed. C3's threshold is derived from this repo's commit-per-day
distribution, not picked. C4's first row cost the most care: a naive `\b11[0-9]{2}\b`
matches 86 lines under `docs/` and **34 of them are line-number citations**.

`2a94f3d` **42** — the six UNBLOCKED defects closed, 21 tests, each verified by deleting the
fix and watching it fail. **Every count the register quoted for them was wrong**: D03's
"135 of 351" is 421 of 678 and none are malformed; D05 had five `continue` sites, not four;
D13's cite was 138 lines off. **Three of the six were never blocked** — a disposition
written for a batch, applied to members that did not need it, which is D17's shape again.
`DEFECTS.md` now requires `BLOCKED-BY: <thing>` so the question is one grep.

`89f7a3f` **37** — every document declares a `kind:`, and `docs/README.md` exists, which is
what made orphan detection possible at all. The label was the smaller half: **six per-script
contracts still said upsert errors were discarded four days after `e353e3e` fixed all eight
sites**, in the *"Logged vs. swallowed"* table. That exposed a defect in the policy itself —
`DOCS-POLICY.md` claimed `audit-docs.py` enforced the same-commit rule and **nothing did**;
the row now reads unenforced.

`6b74e0b`, `8e9e343`, `6b6ae71` **40** — the entry point stopped sending every session to a
finished task, struck and kept. § *How this run works* promoted to `docs/WORKING-METHOD.md`.
The archive backlog cleared, and **one of its two dispositions reversed**: `DEC-72` keeps
`backend/docs/SCORING.md`, because § D read "two scoring documents" as drift from the file
list while the two files declare different jobs in their own opening paragraphs.

`d323546` **38** — no self-consistency number here was wrong; one **word** was overloaded.
`agree2` 94.8%, `pairwise` 90.7%, `unanimous` 87.0%, all n=115, now named and owned by
`AUDIT.md` with the command that reproduces them from committed data. No test count is typed
anywhere: **the floor is the reading you take before you change anything.**

### What the run learned about its own instruments

**C4 fired three times on the people building this tranche** — on `DEFECTS.md`, on task 38's
own file, and on `DEC-71` as it was being written. Each time the document was fixed and the
check left alone. A checker that catches its authors within the hour is the strongest
evidence available that it reads the tree rather than a fixture.

**Two agents of five never sent a report**, and one edited a file its brief fenced off. No
work was lost — the fence had already been vacated — but the orchestrator verified every
Definition of done against the files rather than against a report, which is the only reason
that was survivable. `WORKING-METHOD.md` § *verify, do not trust the report* now says this
where the next run will read it.

**One allowance reverses a subagent's decision on evidence it did not have.** Task 38 allowed
`HANDOFF.md` nowhere. C4 then found nineteen restatements there, **all below line 380 and none
in the entry point**. They are struck-and-kept sequences that *are* the record of the drift.
The real finding is that `HANDOFF.md` is two documents — a `rolling` entry point on a frozen
narrative — and rule 1 has no name for that. **Task 44** archives the frozen half and removes
the allowance rather than widening it.

**Tasks 43 and 44 are open and are this tranche's output, not its leftovers.** 43 executes
`DEC-70`'s already-taken decision to split `docs/scoring.md`; 44 is above. Both exist because
a check found something a reading had not.

### Left to the owner, and not decided by silence

`main` has 24 unpushed commits; `origin/HEAD` points at `origin/jobs-app-readiness`, which is
100 behind; local `webapp-service` is contained in `main` and safe to delete. Every remote
branch is ahead 0, so nothing anywhere holds work `main` does not. **Task 41 surfaced all
three and took none of them** — pushing publishes and moving a default branch changes what a
fresh clone gets. The commands are in `41-git-and-repo-hygiene.md` § *Outcome*.

**A second labeller for about twenty minutes still gates tasks 30, 13's weights and 12's next
bump.** Unchanged by anything in this tranche.

---

## 2026-08-01 — tasks 43 and 44, and tranche seven closes

**Two commits: `29a7d99` (44) and `b8c2943` (43), in that order.** 44 first, deliberately:
it removed a `doc-figures.json` allowance that existed only until it landed, so leaving it
open kept a known hole open. 43 was independent — `DEC-70` had already taken the decision.

**Suite floor read before either task: `Ran 1233 tests` OK and `Ran 93 tests` OK.**
Unchanged at the end. Neither task touches code; both suites are the regression gate for
`test_docs_policy.py`, which is what makes a doc change capable of going red at all.

### 44 — `HANDOFF.md` was two documents

Moved verbatim to the archive: § *State at handoff* and § *What 08, 12 and 19 changed about
the plan* → `docs/archive/handoff-state-2026-07-31.md`; § *Nothing is in flight* →
`docs/archive/handoff-tree-state.md`. Stub and link left where each was.

**Two parts of the last section did not move**, and deciding that was most of the task. Its
FAQ is standing guidance — *"the single easiest mistake to make in this repo"* — and was
promoted to a `##` in place. Its four cross-stream lessons went to
`docs/MEASUREMENT-TRAPS.md` under rule 5: a shared database defeats file-level agent
isolation, and a pin on set membership buys nothing about the derived facts. Neither is
about this cohort, model or product, which is rule 5's test. They went into that file's
**"Later additions"** block rather than as new `§4.8/4.9`, because `MEASUREMENT-TRAPS.md:19`
pins its numbering at 4.1–4.7 so existing citations resolve.

**THE PREMISE WAS WRONG ON TWO OF THE NINETEEN, AND THE CORRECTION IS THE TRANSFERABLE
PART.** Task 44 assumed every restatement sat in the history region, so that a red C4 after
the move would mean *"something that should have been archived was not."* Seventeen behaved
that way. The other two — a `suite 1030 → 1058` delta in the next-steps list and a
`Suite 1171 → 1178` delta in an open follow-up — sat inside **live rolling sections**, where
archiving them would have archived current content. Both became citations of a document that
already carried the pair (`docs/archive/handoff-gate-fix.md` and this file), which is rule
2's fix rather than rule 4's move, and no figure was lost. **A figure inside a rolling
document is not evidence that the section around it is history.** Recorded in
`doc-figures.json`'s `_allowed_note`, where the next reader meets it.

The allowance is removed and the struck paragraph kept beside it. **C4 now enforces on the
file every session reads first**, which it could not do for the day the exemption stood.

### 43 — `docs/scoring.md` splits

The contract **kept the path**, because all eight live citations of it mean the contract
half — read one by one. The measured half is `docs/scoring-measured-2026-07-27.md`,
`kind: record`, frozen, maintained by nobody.

**The task describes "the contract half" and "the record half" as though the file had two
halves. It does not.** The 2026-07-27 figures are interleaved into almost every section —
the funnel, the per-profile scale tables, the tier block, the tombstone counts,
`fit_score`'s observed range, the `staff` demotion — so there was no line to cut at. What
moved is every figure the file **owned**. Figures it already cited to another document
(`SCORING.md`'s Spearman, the 59-row tie block, the learned-ranker avg-precision pair)
stayed: a cited figure is already rule 2 being followed, and moving it would have been
tidying rather than fixing.

Two findings, both about citations rather than about scoring:

- **`backend/config/criteria.json:43` cited `docs/scoring.md:374` and was already off by
  seven lines before this task ran** — the 1-in-20 sentence is at `:381` — and the split
  moved it again. Repointed to a section anchor, which cannot drift, with the correction
  marked in place. The same drift had hit `docs/archive/README.md`'s `:15-21`. **A line
  number into a live `contract` is a citation with an expiry date.**
- **The contract quoted the learned-ranker probe's 12.7/20 in three places with none of the
  caveat its owner attaches.** `docs/archive/README.md` relabels it as *imitation fidelity
  against a non-target persona*, not a quality score, and says *"do not quote them
  forward."* The record half carries the relabel beside the figure.

### What closes, and what does not

**Tranche seven is complete — tasks 36–44.** `audit-docs.py` reports 0 on all six checks,
`audit-doc-links.py` reports 0, and `doc-policy-baseline.json` is still empty everywhere,
which was phase 9's stated exit gate. **No row was added to that baseline by either task**;
44's only tolerance is a struck-and-kept note explaining a tolerance it removed.

**The refactor is not complete.** The status column reads 29 done, 10 todo. Ten of those are
the product/API surface (24–28, 31, 32, 33) plus 30 and a mislabelled 23, and **the premises
of the product tasks were audited on 2026-07-31 and several were stale** — read the task
files and `API-CONTRACT-v1.md`, which is a specification and not a description of the
shipped API.

**A second labeller for about twenty minutes still gates tasks 30, 13's weights and 12's
next bump**, and no session can arrange it. Unchanged by anything in this tranche.

**One rule 7 gap is open and owns no task.** `audit-docs.py` walks `docs/` only, so
`.claude/CLAUDE.md` and the root `README.md` are declared reachability roots for C2 and are
scanned by no other check, C4 included — and both carry figures. Widening `docs_files()` to
include the declared roots is the obvious next check and is unwritten. Phase 9 made the
documentation checkable; it did not make **all** of it checkable, and saying so is what rule
7 asks for.

## 2026-08-01 — task 27, the event schema: the product/API track opens

**The owner chose the product/API track over the labelling night, and 27 is where it
starts** — not by preference but because it is the only work in the plan that cannot be
backfilled. `rank` and `request_id` describe the state of a list at the moment it was
rendered, and the render is over as soon as it happens; every other task on the track can
be redone later.

**Suite before: main 1233, webapp 93, both OK.** That reading is the floor, taken before
anything changed, per `.claude/CLAUDE.md`. **After: main 1233, webapp 129.** The main suite
is unmoved by design — nothing here is pipeline code except six `add_missing_columns`
entries and an index.

### What landed

| | |
|---|---|
| `backend/schema.py` | six nullable columns on `job_events` — `request_id`, `rank`, `dwell_ms`, `reason`, `visibility DEFAULT 'private'`, `criteria_version` — plus a partial `idx_job_events_request` for the derivation's only query |
| `backend/webapp/jobs.py` | `GET /v1/jobs` issues a `request_id` and a per-row `rank`; `POST /v1/events` validates and stores the new fields; `derive_skips()`; `ContractError` and the contract's error envelope; the `CLIENT_EVENT_NAMES` / `SERVER_EVENT_NAMES` split |
| `backend/webapp/schema_web.py` | `REQUIRED_COLUMNS`, checked at startup |
| `backend/webapp/app.py` | the exception handler, registered for `ContractError` alone |
| tests | `test_event_replay.py` (new, 11 tests, real Postgres), plus `test_events.py`, `test_sessions.py`, `test_grants.py` |

### Four findings, and the first one changed what the session did

**1. Task 27's declared dependency was backwards, and it had the expensive orientation.**
`27-event-schema.md:9` read *"Depends on: 26"*. Nothing in 27 touches anything 26 builds;
**26's own Definition of done needs 27's `visibility` column**. And 26 needs onboarding
screens, which is task 32, which needs a `frontend/` that holds one `.gitkeep`. So the
declared order put the one un-backfillable task in this plan behind the one that most
obviously can be redone later. Corrected in both files.

**2. `model_version` was a name this repo had already decided against.** The task file
sketched it; `.claude/CLAUDE.md` lists it as one of three names *"planned and never built"*.
`criteria_version` is the provenance that actually exists, and **`schema.py`'s `job_scores`
block had already written the argument for it** — that column is stored there *"because L2
analysis of `job_events` must know which weight generation ordered the list a user saw."*
That sentence is about this table. `DEC-74`.

**3. `apply` vs `applied` could not be deferred any further.** It had to be settled to write
the validator at all. The code wins and the contract moves, and the tiebreak is that
`job_events` is granted `SELECT, INSERT` and nothing else — the existing rows say `applied`
and are the only part of the disagreement that cannot be edited. `DEC-73`.

**4. The webapp could have started against a database missing the columns it writes.**
`verify_schema()` checked tables and privileges, not columns. The two processes migrate on
different schedules — `ensure_schema()` is the pipeline's, and this service holds no DDL
rights by design — so a deploy ahead of a nightly run would have produced a 500 on a real
user's first click. That is the precise failure `verify_schema()`'s own docstring exists to
convert into a refusal to start, and the sequence grant beside it is annotated with `api/`
having learned it the expensive way. `REQUIRED_COLUMNS` closes it.

### One limit, recorded rather than fixed, and it is the owner's call

**Skips are a first-render-per-day signal.** `IMPRESSION_DEDUP_HOURS` is keyed
`(profile, job_id)`, not `(profile, job_id, request_id)`, so a second render of the same
list inside 24 hours writes no impression rows — and `derive_skips()` reads impressions.
The fix is one line. The cost is changing the documented meaning of *"a list re-render is
not new information"*, which is an existing behaviour with its own reasoning, for a
different task's benefit. **Left alone and written down in three places** rather than
changed in passing.

### Method notes worth keeping

**A test caught its own premise.** `test_the_declared_columns_are_the_ones_the_writers_name`
was first written to read the first `INSERT INTO job_events` in the file and assert every
declared column appeared in it. It failed on `dwell_ms` — because there are now **two**
writers, and a `skip` legitimately has no dwell and no reason. The assertion is over the
union, and the episode is left in the test's comment: the failure was the test working.

**The replay test needed a credential the service does not have.** `scratchdb` calls
`schema.ensure_schema()`, which issues `CREATE SCHEMA`; `webapp/config.py` has already
loaded `webapp/.env` by then, so `DATABASE_URL` is `jobs_web`, which holds CREATE on
nothing. Every test in the file died with *"permission denied for database jobs"* rather
than skipping — **a gate that cannot tell "no database" from "wrong role" reports the wrong
one.** Resolved by publishing `backend/.env`'s pipeline URL as `JOBS_SCRATCH_DATABASE_URL`,
the escape hatch `scratchdb.scratch_url()` already documents, and deliberately **not** by
merging `backend/.env` over this service's own credential inside its own test suite.

**Two orphaned scratch schemas are sitting in the `jobs` database** — `scratch_5ce56323`
and `scratch_cafb8b05`, both with the pre-27 seven-column `job_events`, so both predate
this session. Noted, not dropped: `scratchdb` will only ever drop a name it could have
created and it checks that immediately before the DROP, so removing them is a deliberate
act rather than a tidy-up, and it is the owner's.

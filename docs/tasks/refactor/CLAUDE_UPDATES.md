# Run log — `docs/tasks/refactor/`

Progress updates from the agent run through tasks 03–34, appended as work lands.

This is the *what happened* log. The *why this choice* log is
[`DECISIONS.md`](DECISIONS.md) beside it, and the two are deliberately separate: a
decision outlives the run, a status update does not. The ordered index of tasks and
their `todo`/`done` state stays in [`README.md`](README.md).

Newest entries at the bottom.

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

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

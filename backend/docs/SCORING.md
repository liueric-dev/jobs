# Scoring: how a posting becomes a recommendation

How the jobs pipeline decides which postings a person sees, what each stage
costs, and why the work is split the way it is.

Companion to `README.md` (operating the pipeline), `DEVELOPER.md`
(architecture and TODOs) and `OVERVIEW.md` (how it got built).

**This document is the design argument — why the work is split this way and
what it costs.** For the contract the split produces — what a score means,
whether two are comparable, the provenance of every weight, and what happens
when a stage fails — see [`docs/scoring.md`](../../docs/scoring.md). For
running an individual stage, see [`docs/ingest/`](../../docs/ingest/).

---

## The problem this design solves

The original `score.py` made one LLM call per `(job, profile)` pair. Correct,
simple, and it does not scale: cost, latency and rate-limit consumption all
grow as **jobs x profiles**.

At one profile that is invisible. Measured on this corpus at 100 profiles:

| | one call per (job, profile) | split into tiers |
|---|---|---|
| LLM calls/day | ~11,500 | ~850 |
| Scoring wall-clock/day | ~9 hrs | ~20 min |
| Backfill of the existing corpus | 511k calls | 11.3k calls |
| **New profile sees a ranked list after** | **~5,100 calls, ~4 hrs** | **0 calls, seconds** |

The last row is the one that mattered most. A signup could not see anything
until its entire eligible corpus had been scored. At ten signups a day that is
forty machine-hours a day of pure onboarding.

Separately, 11,500 requests/day is impossible on any free tier —
`./.env` caps `gemini-3.6-flash` at 20 requests/day, and the real free
quota is 20, not the documented 1,500 (`README.md`).

---

## The pipeline

```
ingest  ->  eligibility  ->  extract  ->  match  ->  narrative
 (free)      (free, SQL)      (LLM)      (free)      (LLM)
                            once/job    per user   top-N/user
                              EVER      per job    active only
```

The rule the split follows: **anything true about a posting regardless of who
is looking is computed once and shared. Anything persona-relative is either
free, or bounded by what a person actually sees.**

### Stage 1 — Eligibility (`relevance.py`, free)

`relevance.union_sql()` ORs together every active profile's `title_include`
regex. A posting earns an LLM look if **any** profile's filter admits it.

This is a union rather than one profile's filter because extraction is shared:
a posting profile A would never look at still deserves the call if profile B
would. Using one profile's filter would let whoever happens to be first quietly
shape the corpus for everyone.

An empty profile list returns FALSE, not TRUE — nobody is waiting on the work.

### Stage 2 — Extract (`extract.py`, one LLM call per posting, ever)

Turns a posting into a `job_facts` row: seniority, years required, role
archetype, tech stack, remote policy, comp band, degree and visa requirements,
whether it welcomes career breaks, and a neutral two-sentence summary.

Two properties do the work:

- **The prompt contains no persona.** Not only because facts should not be
  persona-shaped, but because the instruction block is then byte-identical for
  every posting *and every profile* — one cache prefix across the whole corpus.
  Measured 2026-07-28 on the current prompt: **95% of input once warm, 80% on
  a cold prefix** — see "What it actually spends" for why that is a range. The
  posting goes last for the same reason; anything variable earlier would
  truncate the prefix.
- **It never re-runs.** `facts_version` records which generation of the schema
  produced a row, so adding a field is a resumable backlog burn-down rather
  than a TRUNCATE, and tombstoned rows get one more attempt under the new
  prompt.

Enumerated answers are coerced onto closed vocabularies on the way in
(`extract._enum`). A model answering `"Mid-Level"` instead of `"mid"` does not
error — it would silently score as unknown for every profile forever. Anything
unrecognised becomes NULL, which the matcher can reason about; `"Mid-Level"` is
a landmine.

### Stage 3 — Match (`match.py`, free)

For each profile, walk its `criteria_json` against each posting's facts and sum
the deltas:

```
job_facts:  seniority=senior, yoe_min=5, archetype=forward_deployed,
            stack=[python, typescript, kubernetes], remote_policy=hybrid

base                            +35
archetype: forward_deployed     +28
tech (python 6 + typescript 5)  +11
seniority: senior                -8
                                ----
match_score                       66
```

Every line lands in `match_reasons`, so "why is this ranked 8th" is answerable
from the row. A hard exclude (`archetype: ml_research`, `ml_research_required`)
short-circuits to 0 with the reason kept, and — critically — stops later rules
being credited, so a research role that happens to name Python cannot climb
back over the floor.

It is free because it is roughly forty integer operations per pair with no
network. 100 profiles x 11,300 postings is ~1.1M evaluations in seconds. **A
brand-new profile is 11,300 evaluations against facts that already exist: a
full ranked list in seconds, zero LLM calls.** That is the property the whole
design exists for.

Only rows at or above `MATCH_FLOOR` are stored. Recomputation is incremental:
a row is stale when its `facts_version` or `criteria_version` no longer
matches, so re-extracting a posting re-ranks it for everyone and editing one
profile's weights re-ranks only that profile.

### Stage 4 — Narrative (`score.py`, LLM, bounded)

For one profile, the top `daily_narrative_budget` (default 20) matches with no
`job_scores` row yet. The prompt is the persona plus the *facts and summary* —
not the 3,000-char description — so the variable part is small and the persona
prefix caches across the profile's whole batch. That is why `run_for_profile`
handles one profile at a time instead of interleaving.

**Triggered on login, plus a nightly warm pass for profiles active in the last
7 days** (`score.py --active-within-days 7`). Because ranking is already
computed, a login can render a fully ranked list instantly and fill narratives
in behind it. Cost then tracks engagement rather than registration: dormant
accounts cost nothing, where eager nightly generation pays full freight for
users who never return.

---

## The ordering rule

> **`match_score` ranks. `fit_score` annotates.**

`job_scores.fit_score` is displayed as a refinement and must never order a
list. The moment ordering depends on it, every posting a user might see needs
an LLM call before it can be placed — which is exactly the property this split
removes. It would also forfeit both the login optimisation and the learned
ranker below.

The cost of this rule is giving up the LLM's re-ordering *within* the 20 items
a user sees anyway. That matters far less than choosing the right 20.

---

## Data model

| Table | Grain | Written by | Cost to fill |
|---|---|---|---|
| `jobs` | one posting | ingest | free |
| `profiles` | one user | signup / `migrate_profiles.py` | free |
| `job_facts` | one posting | `extract.py` | **one LLM call, shared** |
| `job_matches` | posting x profile, above floor | `match.py` | free |
| `job_scores` | posting x profile, shortlist only | `score.py` | one LLM call per shown job |
| `job_events` | one interaction | the surfacing layer | free |

Every `job_id` foreign key is `ON DELETE CASCADE ON UPDATE CASCADE`. The update
half is not decorative: the primary key is a content hash, so re-keying happens
(`migrate_google_ids.py`), and without it that migration fails on every posting
that already had a score.

`job_events` is written by nothing in the pipeline today. It exists because
engagement cannot be collected retroactively — every day without it is training
data for the learned ranker that can never be recovered. Recording
`match_score` and `fit_score` *as of the impression* is the load-bearing part:
without them you cannot reconstruct what the user was reacting to once weights
change.

---

## What it actually spends

> **At 43 eligible postings/day, the nightly extraction pass takes 0.03 hours
> and consumes 0.1% of what actually binds — 3 of the provider's 2,500
> concurrent requests. There is no daily request ceiling to consume.**

That sentence is the deliverable of task 04 and it is not the headline. The
headline is the line under it:

> **The pipeline cannot process 43/day. `EXTRACT_BATCH_SIZE` is 40
> (`extract.py:70`) and `run-daily.py` invokes `extract.py` exactly once
> (`run-daily.py:120`), so the ceiling is 40 postings a night regardless of
> how fast a call is. At 43/day the backlog grows 3/day; at 80/day — what the
> last seven complete days actually ran — it grows 40/day, forever.**

**Superseded 2026-07-28 as a statement about the code; kept because it is
task 04's finding and the reason the code changed.** `extract.py` no longer
runs one batch per invocation. `main()` loops batches until the backlog is
empty or `EXTRACT_DEADLINE_SECS` (3600, `extract.py:119`) passes, so
`EXTRACT_BATCH_SIZE` is now the size of a batch and not a daily ceiling. The
measurement above is what sets the deadline: at 2.85 s/call effective, one
hour is ~1,260 calls against 43–80 eligible postings a night. The summary
line reports `stopped=drained` or `stopped=deadline`, and the second on two
consecutive nights is the condition this paragraph used to describe.

Nothing about that is a rate limit, a token budget or a wall-clock problem.
40 calls take 114 seconds — 1.1% of the systemd window. The pipeline is
throttled by a constant, three orders of magnitude below anything the
provider or the clock imposes.

### Method

Reproducible, and every part of it pinned:

| | |
|---|---|
| measured | **2026-07-28**, at commit `e353e3e` |
| model | `deepseek-v4-flash` at `api.deepseek.com` — `JOB_SCORING_MODEL`, the production pin (`llm.py:45`). Extraction and scoring resolve to the same model, so one row each rather than two tables. |
| corpus | `evals/fixtures/corpus-v1.jsonl` — **frozen**, 120 records, stratified across all seven platforms. Extract: 115 eligible, first 60 by sorted `job_id`. Score: 55 eligible (those carrying a facts block), first 24. |
| concurrency | the pipeline's own — `EXTRACT_MAX_WORKERS=3`, `SCORE_MAX_WORKERS=5`. Latency at `workers=1`, which the old tool defaulted to, is not latency the pipeline ever sees. |
| temperature | 0, as production pins it (`llm.DEFAULT_TEMPERATURE`) |
| calls | **84 produced the table below** (60 extract + 24 narrative); 173 billable in total on the day, the remainder being the cold-vs-warm cache comparison and smoke runs. All through `llm.call_detailed()`, so `ratelimit.acquire()` applied — the old tool built the HTTP request itself and silently bypassed it. |

```bash
cd backend
python3 tools/cost-test.py --stage extract --n 60
python3 tools/cost-test.py --stage score   --n 24
```

**Not a live corpus, deliberately.** Every tool under `tools/` used to select
with `ORDER BY first_seen DESC LIMIT n` against production, so the sample
changed nightly and a slower p95 was equally well explained by a busier
endpoint or by a batch of longer postings. That applies to cost exactly as it
applies to quality — see `evals/corpus.py`'s *WHY FREEZE*.

### The measurement

| | extract | narrative |
|---|---|---|
| wall-clock p50 | **7.7 s** | 7.8 s |
| wall-clock p95 | **13.1 s** | 9.5 s |
| min / max | 4.0 / 16.9 s | 4.1 / 9.8 s |
| effective, at the stage's own workers | 2.85 s/call (3) | 1.62 s/call (5) |
| input tokens/call | 1,286 | 1,042 |
| output tokens/call | 971 (757 reasoning) | 729 (546 reasoning) |
| prefix cache hit | **80% cold, 95% warm** | **74% cold, 95% warm** |
| usable JSON | 60/60 | 24/24 (23/24 on the first run) |
| deferred (transient) | 0 | 0 |
| tombstoned (permanent) | 0 | 0 |
| $/call | $0.000284 | $0.000215 |

**The cache figure is a range, not a number, and the old 94% was the top of
it.** DeepSeek's prefix cache survives *between* runs. The same 24 narrative
prompts read 74% of input cached on a cold prefix and 95% on an immediate
re-run; extraction read 80% then 95%. Both stages converge on 95% once warm,
which is what the 94% in the dollar table below was measuring — but a
measurement taken after a `FACTS_VERSION` bump, a prompt edit (task 11), or a
quiet day will see the cold end. Quote the range.

**Failure and retry rate were zero over 84 calls, which is a floor and not a
guarantee.** `n=84` cannot resolve a 1% failure rate. What it does establish
is that neither stage has a *systematic* failure against this corpus,
including its `long_title`, `no_description` and `tombstoned` pathology rows.
One narrative response on the first run parsed but omitted a required field
and would have been tombstoned; the same prompt succeeded on re-run, which is
the temperature-0 non-determinism `deepseek-v4-flash` is already known for
(~~76% self-agreement on `seniority_level`~~).

> **SUPERSEDED 2026-08-01 by task 06 — the struck figure is the provisional
> `n=17` reading and must not be re-quoted.** Task 06 re-ran it with
> `python3 -m evals selfcheck --repeat 3` at `n=115` and the current pair,
> with its confidence intervals, is owned by
> [`docs/tasks/refactor/AUDIT.md`](../../docs/tasks/refactor/AUDIT.md) — cited
> here rather than restated, per `docs/DOCS-POLICY.md` rule 2, so that this
> file cannot be the place a fourth copy goes stale.
> `docs/tasks/refactor/DECISIONS.md` § *06 — Was 76% real?* is why the answer
> is no. **Check the `n` before reusing either pair**; the direction of the
> point below is unaffected — the model still does not agree with itself at
> temperature 0, which is the only property this paragraph relies on.

### The provider's limits, in the repo rather than in someone's memory

Recorded in `PROVIDER_LIMITS` in `tools/cost-test.py`, which is where the
tool reads them from.

| limit | value | provenance |
|---|---|---|
| concurrent requests | **2,500** | repo owner, 2026-07-28 — **operator-stated, not measured** |
| requests/day | none published | DeepSeek does not publish a daily ceiling |
| requests/minute | none published | ditto; the documented posture is degradation under load, not refusal |
| client-side RPM/RPD | unset for this model | `ratelimit.py`; `.env` caps only `gemini-3.6-flash` |

**The throttle probe the task asked for was not run, and that is a decision
rather than an omission.** Finding the ceiling by pushing until 429 would
have spent an unknown share of the nightly `run-daily.py` window to rediscover
a number already in hand. The figure above is therefore a *claim to check*,
not a measurement to reuse — but it is a claim that now lives in the repo with
its date and its source attached, which is what the task actually needed.

At 3 concurrent calls the pipeline uses 0.12% of that ceiling. Concurrency is
not close to binding and will not be until the batch cap is raised by three
orders of magnitude.

### Does it fit the nightly window?

`jobs-ingest.service` sets `TimeoutStartSec=10800` — systemd kills the unit at
three hours, mid-run, and the nine steps are sequential.

| | calls | wall-clock | share of the 3 h window |
|---|---|---|---|
| extraction, one nightly batch (40) | 40 | 114 s | 1.1% |
| narrative, 2 active profiles × budget 20 | 40 | 65 s | 0.6% |
| extraction at N=43, if the cap were lifted | 43 | 123 s | 1.1% |
| extraction at N=80, if the cap were lifted | 80 | 228 s | 2.1% |
| one-time tier-3 backfill (6,075 rows) | 6,075 | 4.8 h at 3 workers | needs `scripts/backfill-facts.sh`, not the nightly path |

**It fits, at both N figures, with three orders of magnitude of headroom.**
Lifting `EXTRACT_BATCH_SIZE` to 100 would still be 2.6% of the window. The
constant is doing no useful work at these volumes; it was sized when scoring
was the filter and 200–400 rows/day arrived unfiltered.

Note the narrative stage is **not** a function of postings/day at all:
`run_for_profile()` takes `profile_obj.daily_narrative_budget`
(`score.py:479`), so nightly narrative volume is `active_profiles × budget`
regardless of how many postings arrived. `SCORE_BATCH_SIZE` (`score.py:195`)
is documented in two docstrings as the cap and is read by nothing on the
nightly path.

### `max_tier_to_score` stays at 2

The full reasoning is in `config/relevance.json`'s `_max_tier_*` fields, which
is where a person editing the number will actually look. In one line:
**affordable, and not worth it.**

Tier 3 is a 6,183-row, $1.73, 4.8-hour backfill — throughput is not the
objection and the old note here ("set to 3 once throughput allows") is
answered. The objections are that tier 3 is 93% employer boilerplate
(`docs/pursuit-gate-volume.md`, hand-checked n=30 at 6.7% precision), that 34
of the 43 on-target titles are *already* at tier 1/2 so widening buys nine
postings, and — decisively — that `tier_sql` folds `company_exclude` and
`description_exclude` into the same predicate that assigns the tier
(`relevance.py:163`, `:168`, `:189`). `max_tier_to_score = 3` is therefore an
unconditional pass, not a wider gate: it re-admits 182 provenance-excluded
rows and 1,906 `title_exclude` rows, and those are the ones that rank
*highest*, because their titles are keyword-stuffed in the way `title_include`
rewards.

---

## What it costs in dollars (secondary)

Kept because it is still the input to any future paid tier, and demoted
because the section above is what actually binds. ~~**The `latency` and
`% cached` columns in this table are superseded by the 2026-07-28
measurement above**~~ — they were taken at `workers=1` against a live corpus.

> **SUPERSEDED IN FULL 2026-08-01, not in two columns — corrected by task 40.**
> The note above named `latency` and `% cached`, which understates it: task 04
> re-measured this table's stage on a **frozen** corpus at the pipeline's own
> concurrency, and **every cell of the extraction row moved.** § *The
> measurement* above is the live pair, and it is the one to quote:
>
> | | this table (2026-07-26, live corpus, `workers=1`) | § *The measurement* (2026-07-28, `corpus-v1`, task 04) |
> |---|---|---|
> | extraction $/call | ~~$0.000385~~ | see § *The measurement* |
> | extraction input tok | ~~1,363 (94% cached)~~ | see § *The measurement* — and the cache figure is a **range**, not a number; 94% was the top of it |
> | extraction latency | ~~9.3s~~ | see § *The measurement*, at `EXTRACT_MAX_WORKERS=3` |
>
> Kept, not deleted, because the **dollar-comparison table below depends on it**
> and because a superseded cost is the only evidence of how the cost was once
> read. **The three `$/month` rows below are unaffected in their ordering**,
> which is the only thing that table was ever used for — see the `250/day`
> note under it, which was separately 6x high.

Measured with `tools/cost-test.py` against `deepseek-v4-flash` on real
postings, at the production `temperature=0`. Prices `0.14 / 0.0028 / 0.28` per
Mtok (input miss / input cache hit / output).

`deepseek-v4-flash` is the production model — `llm.DEFAULT_MODEL`, and what
`backend/.env`'s `JOB_SCORING_MODEL` pins both `extract.py` and `score.py`
to as of 2026-07-28. This table describes what actually runs, not a
candidate under evaluation.

| | input tok | output tok | $/call | latency |
|---|---|---|---|---|
| Extraction | 1,363 (94% cached) | 1,071 | **$0.000385** | 9.3s |
| Narrative (old, full description) | 1,605 | 602 | $0.000288 | 6.5s |

Output dominates the bill and scales with postings scored regardless of prompt
design, so **prompt-shrinking is not the lever — scoring fewer postings per
user is.**

At 100 profiles, 250 new eligible postings/day, 30% daily-active:

| | $/month | one-time backfill |
|---|---|---|
| One call per (job, profile) | ~$64 | ~$94 |
| Split tiers, narrative eager nightly | ~$12 | ~$2 |
| **Split tiers, narrative on login** | **~$5** | **~$2** |

Extraction is the flat term: 250 calls/day whether there is one profile or a
thousand. Narrative is `active_profiles x budget`.

**The 250/day in that table is an assumption and it was 6x high.** Measured
2026-07-28 over 2026-06-28…2026-07-27, the current gate admits 66/day
(`docs/pursuit-gate-volume.md` reports 43/day for the narrower AI-vocabulary
population), and the widest possible gate — every open, described row —
admits 152/day. So every dollar figure above is a ceiling, not an estimate.
The relative ordering of the three rows is unaffected, which is the only thing
the table was ever used for.

At roughly $0.05/user/month, **token cost has stopped being the interesting
constraint.** What binds is request rate limits, wall-clock, and ranking
quality — and, measured, none of those three either: what binds is
`EXTRACT_BATCH_SIZE`. Spend the effort on `criteria.json` calibration, not on
tokens.

*(Superseded 2026-07-28 in its last clause only, and by acting on it: the
batch cap is no longer a daily ceiling — see the drain-loop note under "What
it actually spends". The conclusion it supports is unchanged.)*

### Reasoning tokens: measured, and deliberately left ON

Disabling reasoning on the extraction prompt is 4.9x cheaper
($0.000078/posting) and 3.9x faster. It was still rejected. `tools/compare-extract.py`
extracts the same postings twice and compares field by field:

| field | self-consistency floor | reasoning on vs off | true effect |
|---|---|---|---|
| `ai_involvement` | 100% | 82.5% | **−17.5** |
| `remote_policy` | 97.5% | 80.0% | **−17.5** |
| `role_archetype` | 100% | 90.0% | **−10.0** |
| `seniority_level` | 95.0% | 87.5% | −7.5 |
| `tech_stack` (jaccard) | 98.3% | 78.8% | −19.5 |

The floor column is the point. An absolute agreement number means nothing on
its own — the first version of that tool called 90.7% "good enough to disable
reasoning" when the same fields disagreed *with themselves* at 93.9%, i.e. it
was reading sampling noise as signal. (That noise was itself an artefact of the
measurement tools not sending `temperature`, while production pins it to 0.)

Against a proper 98.6% floor, reasoning genuinely changes the four
highest-weight matching fields. Disabling it saves ~$2.30/month and risks
systematically mis-typing the one artifact every profile reads, recoverable
only by a `FACTS_VERSION` bump and a full re-extraction. Bad trade.

---

## Calibration

`tools/calibrate-match.py` is the gate. The 900+ `job_scores` rows for profile
`tech` were produced by the LLM this design replaces — real judgements, already
paid for. They are free labels, so calibration makes **zero** API calls.

Two numbers, and recall is the one that matters:

- **spearman** — rank correlation across everything scored both ways. A broad
  sanity check that the orderings are related at all. Ship threshold `>= 0.6`.
- **recall@k** — of the LLM's top 50, how many land in the rules' top 150. This
  is the gating question stated directly: a rules score 15 points low on a
  posting nobody scrolls to costs nothing; dropping a genuine 85 out of the top
  150 costs a user their best lead. Ship threshold `>= 0.8`.

`--disagreements` prints the postings the rules rank far *lower* than the LLM
did, with their `match_reasons`, because that is the expensive direction of
error and the reasons say which weight caused it.

The LLM is not right, it is the incumbent. Tuning until Spearman hits 1.0 would
be fitting to the thing being replaced, mistakes included.

### Judge against the baseline, not against the LLM

The thresholds below were set during design, before any measurement, and the
recall one turned out to be aspirational rather than informative. The question
that matters is not "does the rules ranking match the LLM's" — the LLM never
ranked anything. It scored postings in arrival order and nothing sorted them,
because there is no surfacing layer. The real baseline is **recency**, which is
what the old pipeline effectively surfaced.

Measured over the 917 LLM-scored postings that have facts:

| ordering | mean fit of top 20 | top 20 that are fit>=80 | recall@150 |
|---|---|---|---|
| **rules (`match_score`)** | **69.3** | **40%** (8/20) | **0.433** |
| recency (newest first, old behaviour) | 48.9 | 25% (5/20) | 0.179 |
| random (mean of 500 draws) | 46.6 | 15% (3.0/20) | 0.164 |

1.4x the mean fit of the old behaviour, 1.6x the hit rate, 2.5x the recall.
Real, and worth having, but not a transformation.

**These two rows were wrong until 2026-07-26 and the error flattered the
result.** The baseline block sorted `first_seen` *ascending*, so the row
labelled "recency" was the 20 **oldest** postings — it scored 1/20 and made the
rules look 8x better than the status quo. The `random` row used a single seed
that happened to draw 5/20 against a 500-seed mean of 3.1. Together those
produced the conclusion that recency was *worse than random*, which was
entirely an artifact of the reversed sort: newest-first is in fact modestly
better than random, not worse. A baseline is only worth measuring against if it
is the thing you actually replaced.

Set quality bars relative to what a change replaces. A bar invented before the
baseline is measured tells you nothing about whether to ship.

### Result as of 2026-07-27 — one threshold met, one not

```
spearman                 +0.673   (need >= 0.6)   PASS
recall fit>=80 in top150  0.354   (need >= 0.8)   FAIL  [56/158]

TOP 20 QUALITY vs BASELINE (what actually reaches a user):
  rules (match_score)     mean fit 75.5    12.0/20 at fit>=80
  recency (newest first)  mean fit 73.8     9.0/20 at fit>=80
  random (mean of 500)    mean fit 49.5     3.4/20 at fit>=80
```

**These are not comparable to the 2026-07-26 figures below, and the
difference is not evidence of anything.** Three things changed at once on
2026-07-27, and the run was not controlled for any of them:

1. `calibrate-match.py` could not execute at all between the relevance union
   moving into `match.load_facts` and being repaired — so it now applies a
   relevance filter it never applied before, over a different sample.
2. `criteria.json` gained `seniority.tolerate.staff` and
   `penalty_per_level`, which re-ranked 3,077 rows and demoted 250.
3. The corpus grew: the `fit>=80` label set went 134 → 158.

Point 3 alone explains the recall drop, per the window-relative warning
below — "top 150" is a narrower slice of a bigger pool. Attributing any of
this to the weight change would be exactly the kind of uncontrolled reading
this document's measurement-traps section exists to prevent. **Re-measure
deliberately before drawing a conclusion.**

The previous figures, for the record — measured against 917 LLM-scored
postings over a 4,977-row `job_facts` corpus (1 tombstoned):

```
spearman                 +0.619   (need >= 0.6)   PASS
recall fit>=80 in top150  0.433   (need >= 0.8)   FAIL  [58/134]
```

Spearman is stable across sample sizes (+0.605 / +0.613 / +0.619 at 756 / 806
/ 917 postings), which is what a real measurement looks like.

These figures are reproducible to the digit only since `load_pairs` started
sorting by `job_id`. Before that, two runs against an unchanged database
returned recall 0.440 and 0.433: a seeded sample over an unordered SELECT is
not a pinned experiment, and the wobble was the same size as the effects this
tool exists to detect.

**Recall is window-relative — do not compare it across corpus sizes.** The same
ranking scored 0.476 when 806 postings were ranked and 0.444 when 3,214 were,
because "top 150" is a far narrower slice of the larger pool. When the corpus
grows, either the window grows with it or the number falls for reasons that
have nothing to do with the weights.

**This is a tuning gap, not a capacity ceiling — the opposite of what this
document said until the probe was run.** A sweep across the entire plausible
weight space — base 22–55, location penalty 0 to −55, tech cap 18–34, match
floor 0–40 — moves recall only between 0.468 and 0.484, and the conclusion
drawn from that was that seventeen coarse fields simply could not reproduce a
judgement made from reading full prose.

That inference does not hold. A weight *sweep* only explores the shapes
`criteria.json` can express: a base, a per-level penalty, a capped additive
boost. It cannot find an interaction, and exhausting it says nothing about
what the features contain. `tools/learned-ranker-probe.py` asks the question
properly — fit a model on **exactly the inputs `score_job()` reads** and
cross-validate it against the same 917 labels:

| ranking over the same 917 postings | precision@20 | avg precision |
|---|---|---|
| rules (`match_score`), hand-tuned | 8.0 | 0.347 |
| **learned, identical features** | **12.7 ± 1.0** | **0.498 ± 0.015** |
| learned, + the unused `job_facts` columns | 11.6 ± 1.4 | 0.480 ± 0.025 |
| learned, + tf-idf over the full description | 14.7 ± 1.3 | 0.520 ± 0.031 |

Out-of-fold, 10× 5-fold, paired bootstrap on the difference: +0.167 average
precision [+0.099, +0.240]. The features were never the problem. The same 17
fields, weighted by fitting instead of by hand, close most of the gap.

Two riders, both of which cut against spending on extraction:

- **The unused columns are worthless here.** `employment_type`,
  `visa_sponsorship`, `comp_*` and `years_experience_max` are already
  extracted and cost nothing to adopt — and adding them makes the model
  slightly *worse*. `visa_sponsorship` is 96% `unknown` and `comp_*` is 13%
  populated, so they are mostly noise with a missingness indicator attached.
- **Full prose adds little once its boilerplate is stripped.** The text arm
  first scored 0.534, and its strongest positive terms were `18808` and
  `18808 ljbffr` — a republisher's footer tag, present on 41 `google_jobs`
  postings that happen to be 34% `fit>=80` against a 13.9% base rate. It was
  learning which board scraped the page. Stripped, the arm falls to 0.520,
  inside one standard deviation of the structured-only model.

So the ranking ceiling is the weighting function, and the answer is the
learned ranker below — not richer extraction.

Three things were learned getting to that number, all of which were
measurement errors first:

- **Spearman was being computed on a truncated sample.** The first version
  joined `job_matches`, which only holds rows above `MATCH_FLOOR`. That
  discards the low end, where rules and LLM agree most, and reported +0.326
  for a ranking function that actually scores +0.613. The tool now scores
  from `job_facts` in-process. A storage policy must not be able to move a
  quality metric.
- **"Top 50" was not well defined.** `fit_score` is heavily tied — 59 postings
  share the value 85 — and the top-50 boundary falls inside that block, so
  ~24 of any "top 50" were an arbitrary draw. Recall is now defined by score
  threshold (`fit >= 80`), which is stable and is also the set a user would
  care about not losing.
- **Hard excludes amplify extraction errors.** `role_archetype` agrees with
  itself only 90% of the time, so a −100 on it turned a 1-in-10 extraction
  slip into a deleted posting — "Java Full Stack with AI Integration" read as
  `new_grad`, "Senior Software Engineer" read as `ml_research`, both
  annihilated. Hard excludes are now reserved for fields that are both
  reliably extracted and genuinely disqualifying.
- **The recency baseline was sorted backwards.** See the table above: the row
  labelled "the old behaviour" was the 20 *oldest* postings, and the random
  row was a single lucky seed. Together they overstated the improvement as 8x
  and made recency look worse than random.
- **An exhausted weight sweep was read as an exhausted feature set.** The
  sweep only ever explored the shapes `criteria.json` can express. Concluding
  from it that the features were at capacity took four days of planned
  extraction work off the critical path in the wrong direction, and the
  experiment that disproved it cost zero API calls and twenty minutes.

**What this costs in practice**, given the baseline comparison above:

- **~60% of narrative spend goes to mediocre matches.** 40% precision@20 means
  roughly 12 of each profile's 20 daily narratives are written for postings the
  LLM would not rate highly. At 100 profiles that is ~$3 of the ~$5/month —
  negligible in money. The cost is that the list is strong at the top and thins
  out below.
- **Good postings are delayed, not lost.** Nothing is dropped; a posting ranked
  400th surfaces on day 20 rather than day 1. Whether that matters depends on
  how quickly postings close, which cannot be measured yet — the corpus is days
  old and there is almost no `closed_at` history. Worth revisiting once there
  is a month of lifecycle data.
- **It caps how far the daily budget can be trimmed.** At 80% precision the
  budget could drop from 20 to 10 and halve narrative cost. At 40% the wider
  net is earning its keep, because the good postings are scattered further
  down.

Closing it needs better weights, not more signal — a learned ranker over the
features that already exist, which the probe measures at 12.7/20 against the
hand-tuned 8/20. `job_events` is still worth logging now, because engagement
labels are what let that model improve past the LLM's own judgement rather
than merely imitating it. precision@20 is the objective it should be trained
against; average precision is what to *measure* it with, since p@20 is a count
of twenty things and its confidence interval is correspondingly useless.

---

## Where this goes next

`job_facts` is a feature store. Once every posting is a structured feature
vector, recommendation stops being an LLM problem and becomes a ranking
problem.

1. **Now** — rules over facts. Works at zero users with zero behavioural data,
   fully explainable, free at inference.
2. **Now** — log engagement (`job_events`). No payoff this quarter, total
   blocker for everything below if skipped.
3. **Next, and now measured rather than assumed** — learned ranker. Features
   from `job_facts`, logistic regression, labels from `job_events` once there
   are any and from `job_scores.fit_score` until then. Zero inference cost,
   beats hand-tuned weights because it learns preferences users cannot
   articulate, and improves with use instead of decaying. A global model plus a
   per-user residual handles cold start.

   `tools/learned-ranker-probe.py` already fits this model out-of-fold on the
   existing 917 labels: **12.7/20 precision@20 against the rules' 8.0**, +0.167
   average precision [+0.099, +0.240] paired. That is the whole business case,
   and it needs no new extraction, no new labels and no engagement history to
   start — the cold-start model can be trained on `fit_score` today and swapped
   to engagement labels as they accumulate.
4. **Later** — embeddings for "more like the ones you saved" (~$0.10 one-time
   for the corpus). Also fixes the fuzzy-title weakness `relevance.py`
   acknowledges, and enables cross-source dedup.
5. **Throughout** — LLM as explainer, never ranker. An LLM ranking is
   expensive, non-deterministic, and cannot learn from feedback. An LLM
   extracting features once and explaining the top 20 is cheap and durable.

At one user with no history a learned ranker has nothing to learn from, and the
LLM's judgement genuinely is the best signal available. Do not skip step 1.

---

## Operating it

```bash
# nightly, all nine steps
python3 run-daily.py

# individually
python3 extract.py                       # facts for new postings
python3 match.py                         # re-rank stale rows only
python3 match.py --rebuild --dry-run     # what a full re-rank would do
python3 score.py --profile tech --limit 20

# burn down an extraction backlog
EXTRACT_MAX_WORKERS=16 ./scripts/backfill-facts.sh

# add or update a profile
$EDITOR config/criteria.json
python3 migrations/migrate_profiles.py --apply --bump   # --bump invalidates matches
python3 match.py

# is the ranking good enough?
python3 tools/calibrate-match.py --disagreements 15
```

**`--bump` matters.** `match.py` keys its incremental rebuild on
`criteria_version`. Editing weights without bumping leaves stale `match_score`s
that look current — the one genuinely wrong combination, which
`migrate_profiles.py` warns about.

| env var | default | what it does |
|---|---|---|
| `EXTRACT_BATCH_SIZE` | 40 | postings per **batch**. Was the daily ceiling, measured 2026-07-28 as the binding constraint on the whole pipeline; `extract.py` now drains batches until empty or out of time, so it no longer is. See "What it actually spends". |
| `EXTRACT_DEADLINE_SECS` | 3600 | how long `extract.py` may keep starting batches, on a monotonic clock. Checked between batches only, never before the first — one batch per invocation stays the floor. Justified against 2.85 s/call effective at `EXTRACT_MAX_WORKERS=3`. |
| `EXTRACT_MAX_WORKERS` | 3 | concurrent extraction calls |
| `JOBS_EXTRACTION_POLICY_FILE` | `config/extraction-policy.json` | per-platform extraction pass counts and the measured self-agreement they derive from |
| `SCORE_MAX_WORKERS` | 5 | concurrent narrative calls |
| `JOBS_MATCH_FLOOR` | 40 | below this, no `job_matches` row is written |
| `JOBS_PROFILE` | — | one-off profile override |
| `JOBS_RELEVANCE_FILE` | `config/relevance.json` | shared eligibility rules |

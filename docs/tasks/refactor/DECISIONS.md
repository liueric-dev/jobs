# Decisions taken while running `docs/tasks/refactor/`

Hand-written, not generated — there is no `script:` frontmatter here and this file is
never regenerated. It is appended to as tasks land, one entry per decision that a
reader of the diff would otherwise have to reverse-engineer.

**What counts as an entry.** A choice the task file left open, a place where the task
file was wrong about the code, or a deviation from what it asked for. Not routine
implementation detail — the commit shows that.

**Format.** Claim, the alternative rejected, one line of why, and whether it is
reversible. The reversibility field is there so this can be skimmed for the entries
that actually constrain later work.

Run started 2026-07-28, from `36d83f5`, on branch `webapp-service`. Tasks 01 and 02
were already committed (`28f1d0e`, `36d83f5`).

---

### 00 — Scope of this run, and where it stops

Tasks 03–34 attempted in dependency order. Two classes of wall are expected and are
routed around rather than stopped at: credentials that require registering an account
(15 USAJobs/Adzuna, 20 Firecrawl, 24 Builder keys, 33 Cloudflare, 14's Socrata token),
and human judgement that cannot be substituted (07's golden set, 29's labelling
session, and 30 behind them).

The human wall is load-bearing rather than procedural: Axis B *is* Builder preference,
so a model standing in for it makes the measurement circular — the defect
`docs/ingestion_tests/03-metrics-and-golden-set.md:13` names in `claude-bench.py:417`,
which treats `sonnet-batch-1` as ground truth. Reversible only in the sense that the
labels can be collected later.

### 06 — THE GATE: the stop branch, and the >10-point gap branch, both fire

Measured 2026-07-28, n=120 (115 comparable), `--repeat 3`, `deepseek-v4-flash` at
temperature 0, on frozen `corpus-v2.jsonl`. All seven platforms represented.

`ai_involvement` pairwise agreement by platform: lever 100% (n=9), weworkremotely 95.8%,
google_jobs 93.3%, greenhouse and ashby 92.2%, builtin 91.1%, **hn_whoishiring 77.8%**.

Against task 06's own gate table: `ai_involvement` is **below 90% on the messy
platform**, which is the row that reads *"stop. Tasks 10 and 13 need rethinking."* And
the clean-versus-messy gap is **14.4 points**, over the 10-point threshold, which
additionally requires Phase 3 to carry a per-source quality budget and task 12's
re-extraction to be measured before *and* after.

Both branches fire. Tasks 10, 11 and 13 are held pending a design decision that belongs
to the repo owner, not to this run.

### 06 — Was 76% real? No, and the n=17 sample erred in both directions

| | n=17 | n=115 | |
|---|---|---|---|
| `seniority_level` | 76% | **85.2%** | pessimistic |
| `role_archetype` | 90% | **84.3%** | optimistic |
| `ai_involvement` | 94% | **90.7%** | optimistic |
| whole record identical | 0 of 17 | **21.7%** | pessimistic |

The useful lesson is not that the old numbers were wrong but that at n=17 they could not
have been right in either direction. The structural finding — a large clean-versus-messy
gap — is what survives, and it sharpened.

Comparisons are drawn against the *pairwise* two-run metric, since the n=17 study ran
twice. The report also carries unanimous-of-3, which is stricter by construction;
quoting it against the old figures would have manufactured a decline that is an artifact
of the metric.

### 06 — `criteria.json`'s calibration figures were corrected, and the design was not

`_hard_exclude_comment` justified its penalty design with "seniority_level agreeing with
itself 95% and role_archetype 90%". Neither reproduces: 85.2% [77.6–90.6] and 84.3%
[76.6–89.9], with 95% and 90% falling outside the respective intervals. The slip rate a
-100 penalty amplifies is nearer 1-in-7 than the quoted 1-in-10 and 1-in-20. **The design
is unchanged and the correction strengthens it** — only the numbers were wrong. The
comment records what it used to say rather than quietly replacing it. Not reversible; it
is a correction of fact.

### 06 — `repeat_index=0` shares cache keys with an ordinary run

The cache is content-addressed, so a repeat index had to enter the key or repeat 2 would
read back repeat 1's answer and report perfect agreement — a silent total false pass on
the quantity being measured. A test asserts the digests differ per repeat. The refinement
worth recording: `repeat_index=0` produces the *same* digest as a non-repeat run, so
adding `--repeat` does not invalidate a cache someone already paid for. Reversible.

### EXP — Build task 23, sharply descoped. Google Jobs yields when it is asked properly

16 SerpApi searches on Pursuit-shaped queries: 131 results, 74 passing the production
gate, **9 genuine by hand-check — 6.9%, 95% CI 3.7–12.7%**. 45.4% of employers returned
are non-tech or government, the category task 05 found absent from every configured
source. 129 of 130 rows are new to the corpus.

The control is what makes this credible. **The 4.8% figure was not used, because it is
not comparable** — it is a share-of-corpus number against a yield, and `google_jobs` has
901 rows to greenhouse's 7,370 largely because the ATS pull takes whole boards while the
Google bank runs eight queries a night. Instead: 30 pinned production `google_jobs` rows
plus every one of the 9 rows in the entire 901-row population whose title carries both
AI and entry-level signals, judged by the same person against the same criteria —
**0 genuine of 39**. Population proxy 1.0% versus 31.5%, p<1e-12. The hand-check
contrast alone is p=0.088, underpowered on the control arm, and the document says so.

Descope: keep the single interface and the normalizer into `lib/`'s frozen shape,
`SerpResult` provenance, the quota ledger, the cache and volume alerting. Cut the JobSpy
adapter, canary and router step 2 (task 22 settled those), and six of eight provider
adapters — ScraperAPI and ZenRows bill 25 credits per Google request, so a 1,000-credit
tier is 40 real searches. Reversible.

**Weakest number, and it is stated as such:** 0.56 genuine/search is a *first-run* rate
with no date chip on any of the 16 queries. Nobody has measured steady-state daily yield
for a Google Jobs query on either bank — `google_jobs_query_stats` holds 32 slugs and
none has run more than twice. The follow-up is rerunning the same 16 in two weeks with
`chips=date_posted:week`.

### EXP — The repo's own SerpApi ledger undercounts real spend by 3.3x

Before authorising this experiment the orchestrator read `google_jobs_query_stats` and
found **41** searches used this month, implying 209 remaining. The SerpApi account
itself read **137 used**, and 153 after the experiment — **97 left, not 209**.

The repo's view of its own metered spend is wrong by a factor of 3.3, in the dangerous
direction. This is CLAUDE.md's "silence" failure mode wearing a different hat: nobody
gets an error, the ledger simply disagrees with the vendor and the first symptom is a
month that goes dark early. It bears directly on task 23, whose descope **keeps the
quota ledger** — that ledger needs to reconcile against the provider's own counter, not
against rows this pipeline remembered to write. Not reversible; it is a defect.

### EXP — Task 23 should not block 24 and 25; the evidence inverts it

`23-serp-abstraction.md` lists itself as blocking both. But **task 25 is where the whole
12x difference lives, and it is a config edit**; and **task 24 is 30 Builders × 250
searches/month = 7,500 searches**, roughly 8x every free tier in `SOURCING-STRATEGY.md`
combined, against code that is already written and tested. 23 lists `contributor.py` as
one adapter among eight. On these numbers it is not one adapter — it is the product.
Recorded rather than acted on: reordering a phase is the repo owner's call.

### 16 — `not_found` does not mean "no ATS", and the positive control is why we know

The seed roster carried ten tech employers with tokens already verified in
`config/companies.json`, as a control. Four were conclusively probed. **The regex method
found zero of the four.** Checked by hand: `careers.datadoghq.com` returns 139,063 bytes
of HTML containing the string `greenhouse.io` nowhere; MongoDB's is 564,983 bytes, same
result. Their boards render client-side, so no ATS URL exists in the document a plain
fetch receives.

`not_found` is the largest bucket at 139 employers, and on this evidence it is wrong far
more often than it is right. Every coverage number in `docs/ats-token-discovery.md` is
therefore a **floor**, and `company_ats.validation_note` carries that caveat *on the row
itself* so tasks 17, 18 and 20 cannot read those rows as settled fact. Not reversible —
it is a property of the method, and it is the most useful thing the pass produced.

### 16 — Seven outcome values, partitioned, instead of a boolean

`ats_seed.last_probe_outcome` is one of seven (`ats_discovery.py:57-70`), split into
CONCLUSIVE (`found`, `not_found`) and INCONCLUSIVE (`blocked`, `unreachable`,
`missing_page`, `no_url`, `skipped`), with a test asserting the partition is disjoint and
complete. **Only a conclusive outcome may write `status='never_found'`** — a 403 never
produces one. Rejected: a found/not-found boolean, under which the 30 `blocked`
employers would have become "no ATS here", silently and permanently. Not reversible in
intent; this is the defence against CLAUDE.md's named failure mode.

`skipped` is a per-host cascade: many NYC agencies share `www.nyc.gov`, so one 403 there
suppresses all of them at once, and they are recorded as inconclusive rather than absent.

### 16 — An `unvalidated` status the task's schema did not have

`16-ats-token-discovery.md:69` offers `valid | dead | never_found`, with no value for
"we found a token but the ATS did not answer". Both available choices are wrong: `valid`
asserts something unverified, `dead` discards a real finding. Added `unvalidated`.
ADP, Jobvite and Oracle Cloud are detected-only — they publish no feed this tool can
call — and are recorded because "which large NYC employers are on Oracle/ADP" is exactly
the skew the task asks to be reported. Reversible.

### 16 — Both denominators, always, and the tool refuses to print one alone

Coverage is quoted over all 366 seeded non-tech employers **and** over the 193
conclusively probed: 1.9% versus 3.6%. Quoting the probed subset alone would overstate
by 1.9x. Rejected: reporting the flattering figure, or reporting one with a footnote.
The tool will not emit one without the other. Reversible, but should not be.

### 16 — The probe was stopped at 280 of 376, deliberately

`blocked` climbed from 16 to 30 as coverage grew — the pipeline's documented failure
mode arriving in real time — and this host's IP also runs the nightly ATS pulls and
`google-serpapi.py`. Stopping was a decision to protect that, not a run that finished.
The 96 unprobed carry `last_probe_outcome IS NULL` and are first in line for the nightly
backfill, which walks least-recently-probed first. Reversible.

### 16 — The Workday data-centre column earns itself immediately

The four Workday tenants found use `wd1`, `wd108` and `wd501`. Nobody would guess
`wd108` or `wd501`, and `18-ingest-workday-cxs.md:54` is right that a wrong data centre
returns a 404 indistinguishable from a tenant with no openings. Task 18 should treat
this as confirmed rather than anticipated.

### 22 — Drop JobSpy. The cause is global, not this IP

JobSpy returns zero rows from this machine — 0/20 queries, no exceptions, every request
HTTP 200. Not a block: no captcha, no `sorry/index`, no "unusual traffic". Google
requires JavaScript for search results (announced 2025-01-17, explicitly to stop
scrapers) and JobSpy parses HTML. The decisive probe was a plain web search with no
`udm` parameter — `q=weather new york` returned the identical JS bootstrap shell, which
rules out the "wrong query syntax" explanation upstream offers for this symptom. JobSpy
issue #302 reports the same string, open since 2025-09-06.

Confidence is high and unusually so: this is a negative with a documented global cause
rather than a "works today" observation. No proxy or IP change fixes it. Invalidated
only by JobSpy shipping a JS-executing backend, Google reversing the requirement, or a
fork parsing the rendered payload — and on the first, `ingest/google-serpapi.py:10-18`
already records Playwright automation against Google Jobs being CAPTCHA-walled twice.
Reversible in principle; nothing to reverse today.

The SerpApi control was clean — 10/10 results per search, 30/30 apply URLs. The
vertical is alive; only the free path into it is dead.

**The spike's own premise went untested**, and this is worth keeping: the question was
whether a residential IP fares better than a datacentre one. JobSpy never gets far
enough for IP reputation to be consulted, so that question is still open — it simply
cannot be answered with this tool.

### 22 — The 14-day observation was deliberately not run

The task's design assumes a scraper that works on night one and degrades as reputation
accrues. This one fails 100% from a deterministic, non-reputational cause, so 420
further requests would re-observe the same zero — and would be the one part of the spike
that could plausibly harm the home IP that `google-serpapi.py` and the ATS pulls run
from nightly. Reversible.

### 22 — The 4.8% Google Jobs figure is not settled, and task 05 should be read accordingly

Task 05 reported Google Jobs at 4.8% of the target population and concluded it is not a
meaningful source. **That figure is conditioned on a query bank that has never been
asked for this population.** `backend/config/google-queries.json` holds 32 pre-retarget
queries in four buckets — `core_swe`, `ai_integration`, `bridge_solutions`,
`reentry_growth` — and **every one is a software-engineering title** (verified: "full
stack engineer", "backend engineer", "LLM engineer", "forward deployed engineer",
"software engineer returnship"). Google Jobs contributed few Pursuit-shaped rows because
it was never asked for any.

Mild evidence the other way from the spike's own SerpApi control: "barista" in NYC
returned 10 results with 4,508-character median descriptions.

So the honest statement is "Google Jobs *as currently queried* is 4.8%", not "Google
Jobs is 4.8%". Not reversible as a fact; it changes the reading of an already-committed
document, which is why it is recorded here.

### 09 — The open question: concurrency-test the claim SQL, not `lib/upsert.py`

`05-fetcher-harness.md`'s "open question worth settling first". Settled: **yes for
`state.try_claim`, no for `lib/upsert.py`.** `try_claim` is *defined* by the concurrent
case — `lib/state.py:96-99` guards metered SerpApi and Apify budgets, and if it is
wrong the symptom is a silent double-spend. `lib/upsert.py` has no cross-process
contract: `run-daily.py` runs the ingest scripts sequentially as subprocesses
(`ingest/ats.py:97-102`), so two upserts racing on one row is unreachable. Reversible
if the pipeline ever parallelises ingest.

What actually motivated the question turned out to be transaction isolation, which is
testable *without* concurrency — and doing so produced the first evidence in the repo
that the per-record SAVEPOINT works. A five-record batch with one NOT NULL violation:
with the SAVEPOINT, `new=4`, `errors=1`, four rows stored. Without it, `new=2`,
`errors=3`, and **zero rows stored** — one bad record takes the whole batch.

### 09 — The missing Definition of done, derived rather than invented

`09-fetcher-harness.md` inherits "everything in `05-fetcher-harness.md`'s definition of
done", and that section did not exist. Derived twelve bullets from that file's
"Suggested shape" and "The defects this would catch", and wrote them into it.
Deliberately does **not** require fixing the seven defects the harness would catch —
task 02 produces a register, not fixes — and separates "input pinned" from "defect
closed" so a cassette cannot be mistaken for a repair. Reversible.

### 09 — The interception seam is `urllib.request.urlopen`, not `lib/http.py`

The task file assumes the scripts fetch through `lib/http.py`. **Four of the six do
not** — they call `urllib` directly, so a `lib/http.py` seam would have recorded
nothing for them while appearing to work. Rejected: refactoring the four to route
through `lib/http.py`, which is a caller-side change to shared code in the middle of a
harness task. Reversible, and worth revisiting if `lib/http.py` ever becomes universal.

### 09 — A scratch *schema*, not a scratch database

The role `jobs_pipeline` has no `CREATEDB`, so the throwaway target is a schema created
through the real `ensure_schema()` rather than a separate database. Rejected: granting
`CREATEDB`, which widens production credentials to suit a test harness. Reversible.

### 09 — The Workday fixtures are constructed, not recorded, and say so

No Workday tenant is known until task 16 completes, so the four failure modes are built
by a module rather than captured from a live tenant, and both the module and its tests
state that plainly. Failure mode 4 (the 10,000-row cap) needs 500 pages, which is
another reason not to store it as committed JSON. Reversible — re-record against a real
tenant once one exists, which is the point of leaving it labelled.

### 09 — Apify cost nothing, deliberately

Recorded a *historical* `SUCCEEDED` run through Apify's free read endpoints rather than
paying roughly $0.15 to start a fresh one. The cassette is equivalent for replay
purposes. SerpApi cost one search. Reversible.

### 04 — `max_tier_to_score` stays at 2, and throughput was never the objection

The old `_max_tier_note` said "set to 3 to open the floodgates once throughput allows."
Throughput now allows — 4.8 hours and $1.73 for the one-time backfill, 0.1% of the
provider's concurrency ceiling — and it is still the wrong move. Three findings, in
increasing order of decisiveness:

1. **Quality.** The tier-3 AI-vocabulary population is 93% junk (task 05), and widening
   buys 9 on-target postings for 6,183 rows of noise.
2. **Throughput does not actually allow it either, for a different reason.**
   `EXTRACT_BATCH_SIZE=40` against one nightly `extract.py` invocation already binds at
   tier 1+2 — 66 eligible/day into a 40/day pipe. Tier 3 makes it 152/day into the same
   pipe. The effect is not "more postings get looked at" but "the backlog never closes
   and `ORDER BY first_seen DESC` decides which ones do."
3. **Decisive: `max_tier_to_score = 3` is an unconditional pass, not a wider gate.**
   `relevance.py:189` builds `CASE WHEN row_ok AND loc_ok THEN 1 WHEN row_ok THEN 2
   ELSE 3 END`, and `:223` admits on `tier <= max_tier`. Every row is `<= 3`. Since
   `row_ok` folds in `title_include`, `title_exclude`, `company_exclude` and
   `description_exclude`, the one-character change silently disables **four** exclusion
   lists at once: 1,906 rows return on `title_exclude` alone (account executive,
   recruiter, nurse, controller, VP), plus 182 unique relist-spam rows. And they return
   **at the top** — 19 of them already reach `match_score >= 90`, one hits 99 against an
   LLM fit of 15, because keyword-stuffed titles are exactly what `title_include`
   rewards.

Rejected, both measured before rejecting: relying on `MATCH_FLOOR` to suppress the junk
(the relist rows score *highest*, so the floor filters the wrong end), and subdividing
tier 2 as the task file suggested (tier 2 is already fully extracted — 2,313 of 2,313 —
so it solves nothing). Reversible, and task 10 is what would change it: making the
provenance exclusions a separate predicate that no tier number can switch off.

### 04 — Latency measured at the pipeline's own concurrency, not at `workers=1`

7.7s p50 / 13.1s p95 per call, 2.85s/call effective at `EXTRACT_MAX_WORKERS=3`. The
previous tool defaulted to one worker; latency at one worker is not latency the
pipeline ever experiences, so it could not be compared against the nightly window.
Rejected: reporting both, which invites quoting the wrong one. Reversible.

### 04 — The old `cost-test.py` bypassed the rate limiter, and now does not

It built its own HTTP request rather than going through `llm.call_detailed()`, so
`ratelimit.acquire()` never applied to it. A measurement tool that does not obey the
pipeline's own throttle is measuring a different system. Now routed through
`call_detailed()`. Not reversible in intent — it was a defect.

### 04 — The throttle probe was dropped, on instruction

The task asks for a requests/minute ceiling "observed, by pushing until throttled."
Not done: the limit is a known 2,500-concurrent ceiling, and probing it would risk the
nightly window for a number already in hand. Recorded in `SCORING.md` as
**operator-stated, not measured**, with its date, so a later reader knows its
provenance. Reversible — measure it properly if the provider ever becomes the binding
constraint, which today it is not by three orders of magnitude.

### 03 — `upsert_checked` went into `lib/upsert.py`, not the `ingest/_common.py` fallback

The task file offers `backend/ingest/_common.py` as a fallback "if `lib/` must stay
byte-identical" to another repo, and CLAUDE.md states that constraint as live with
drift reported by `tools/lib-parity.sh`. **That script does not exist anywhere in the
repo**, and `backend/lib/__init__.py` plus `backend/tests/test_lib_contract.py:5`
both record that `lib/` "used to be a shared package and is now this repo's own code."
The constraint is dead. Put the helper beside `upsert` where it belongs. Rejected: the
fallback location, which two of the eight call sites (`api/app.py`, `api/query_claims.py`)
could not have imported from cleanly anyway. Reversible, but there is no longer a
reason to. **CLAUDE.md's `lib/` parity rule is stale and should be corrected in task 34.**

### 03 — `UpsertResult.__iter__` left exactly as it was

The task said not to change it and that is right: the three-tuple unpack is the
documented shape, and rewriting it would move the surprise rather than remove it. The
fix is a wrapper that cannot be called without logging the error count, so the correct
call is also the shorter one. Not reversible in intent — it is the design.

### 03 — The failure rate is checked at two scopes, not one

Scripts that upsert inside a per-source loop (`ats.py`, both Google scripts) apply the
threshold twice: per batch, where one bad source is survivable and is recorded the way
an unreachable source already was, and again over the accumulated total at the end of
the run, where it is not. Hence `check_error_rate()` exists separately from
`upsert_checked()`, and `UpsertErrorRate` carries `.result` — `upsert()` commits before
raising, so the records that succeeded *are* written and a caller that catches it can
still count them. Single-batch scripts (`hn-hiring`, `builtin-nyc`, `weworkremotely`)
need only the one scope. Reversible.

### 03 — The 5% threshold is a guess, and is labelled as one

`DEFAULT_THRESHOLD = 0.05` per the task file. There has never been a run with the error
count recorded, so there is no distribution to choose from — the constant says so in
its own comment rather than presenting itself as calibrated. Reversible, and should be
revisited once real error counts exist.

### 03 — The contributor API's `accepted` now means "written", and a `dropped` field appears

`POST /submit` previously returned `accepted: len(records)` — the count that *normalized*
cleanly, which said nothing about whether they reached the table. It now returns the
count actually written, adds `dropped`, and populates `submission_log.reason`. Not
literally required by the task, which only demanded the error count stop being
discarded; kept because the alternative preserves the exact defect at the API boundary,
and a contributor whose rows vanished has no other channel to learn it. The two values
differ **only when records were dropped** — that is, only in the case where the old
answer was wrong. `docs/tasks/refactor/API-CONTRACT-v1.md` freezes the frontend read
endpoints and does not cover this one, so no frozen contract is broken.

**Reversible in code, but it is a deployed surface** — a client that treats `accepted`
as "how many I sent that parsed" would now see a smaller number on a partial failure,
which is the intended correction. Flagged rather than buried because it is the one
change in task 03 that is visible outside the repo.

### 05 — The rate came from `posted_at_ts`, not `first_seen`

The task specifies grouping by `first_seen::date` over 30 days. That cannot work here:
the database was re-seeded on 2026-07-24, so `first_seen` spans five days and 11,000 of
11,824 rows carry the same date. Following the task literally would have returned a
four-day window and a meaningless mean. Used `posted_at_ts` (populated on
2,974/2,975 of the matching set). Rejected: waiting for 30 days of organic history.
Reversible — re-run against `first_seen` once the table has the history, and expect a
different, better number.

### 05 — Tier computed by importing `relevance.tier_sql()`

There is no `relevance_tier` column on `jobs`; tier is derived per query. Imported
`backend/relevance.py:112`'s `tier_sql()` rather than hand-writing the predicate in the
measurement, per CLAUDE.md's "one implementation, two callers". Rejected: a standalone
SQL transcription, which would have been a second definition of the gate and would
drift from it silently. Not reversible in any meaningful sense — it is the correct
dependency direction.

### 05 — Hand-check sample pinned by `md5(id)`

Drew the n=30 false-positive sample with `ORDER BY md5(id) LIMIT 30` and recorded the
ids. Rejected: `ORDER BY first_seen DESC` (forbidden by CLAUDE.md's measurement
discipline — it selects the easy sources) and unpinned `random()` (not reproducible).
The set is L0: never train on it, never recycle it. Reversible only by drawing a new
sample under a new name.

### 05 — Precision reported strictly at 6.7%, with the generous reading beside it

Two of thirty postings genuinely describe AI work reachable by an entry-level Builder.
A third — an OpenAI B2B marketing leadership hire that mentions "AI-powered workflows"
— was counted as junk, since the role is neither entry-level nor AI work. Counting it
gives 10%. Reported the strict figure as the headline with the generous one stated, so
the later comparison in task 10 has a fixed definition rather than a flattering one.
Reversible: the ids are pinned, so anyone can re-judge them.

### 05 — The task file's premise does not hold, and this changes tasks 04 and 10

`05-widened-gate-volume.md:13-20` says `title_include` is twelve software-engineering
terms and that AI-titled roles "all fall to tier 3 … never scored, never extracted,
never seen." That describes an earlier config. `backend/config/relevance.json:12-47`
now has **34** terms including `\yai\y`, `\yllm\y`, `\yml\y` and `machine learning`, so
any title with a standalone "AI" token already reaches tier 1 or 2. Measured: of 43
titles carrying both entry-level and AI signals, **34 are already admitted and 9 sit at
tier 3**.

Consequence, recorded here because two later tasks are scoped on the false premise:
the target population is not waiting untouched behind the gate — there is almost none
of it in the corpus at all. **The bottleneck is sourcing, not gating.** Task 04's
projection must not assume a widened gate unlocks a hidden corpus, and task 10 should
expect to recover ~9 on-target postings while admitting ~2,975 that are 93%
boilerplate. Not reversible — it is a fact about the config, not a choice.

### 00 — A real cycle in the task graph

`24-revive-contributor-api.md:3` depends on 33 for the tunnel; `33-deployment.md:3`
depends on 24 and 32. Circular as written. Recorded here rather than silently
resolved: 33 has to split, with the tunnel standing up before 24 and the
pipeline/app split landing after 32. Both halves sit behind a Cloudflare account
regardless, so the cycle is not on the critical path of this run. Reversible.

### EXTRACT — The majority-of-3 threshold is 0.90, and the pass count is derived not listed

0.90 is task 06's own gate line, not a number invented here. Exactly one platform is
below it and the rest sit at 91.1%+, so it is not perched on a cliff: 0.92 pulls in
`builtin`, 0.93 pulls in greenhouse and ashby — 9,659 of 11,824 rows, no longer targeted.
`passes_for()` derives the count from `measured_agreement` rather than reading a second
list of platform names, so the config cannot say "3 passes" beside a measurement that no
longer justifies it. Rejected: a threshold of 0.95 "to be safe", which is uniform
majority-of-3 under another name. Reversible — it is one number in a config file.

### EXTRACT — Uniform majority-of-3 rejected on arithmetic, not on taste

3x across 11,824 rows is 23,648 extra calls, ~19 hours at task 04's 2.85 s/call, to fix
an instability that measurement locates in 247 of them. On the six platforms at 91.1%+
the second and third calls buy a third opinion that agrees with the first nine times in
ten. It is also the wrong *shape*: it makes the fix invisible to whoever next asks which
sources we are least sure about, where a per-platform table answers that by being read.
Reversible.

### EXTRACT — A self-reported confidence field rejected as circular

It labels the instability without fixing it — the row written is still one unstable draw
— and it asks the model that cannot reproduce its own `ai_involvement` answer to reliably
rate how sure it is about that answer. Same quantity, no more trustworthy.
`vote_unanimity` is a confidence signal derived from observed behaviour instead, and
costs nothing once the passes are being paid for. Reversible.

### EXTRACT — An unmeasured platform gets ONE pass

An unmeasured source is not a bad source; tripling its cost pays for a number nobody has.
This also decides the failure mode when a platform string is renamed out from under the
config: it degrades to today's behaviour rather than to a 3x bill. The consequence is
that a new Phase 3 source costs exactly what it costs today until someone measures it —
which is the intended prompt to measure it. Reversible.

### EXTRACT — Prose is carried whole from one pass, never merged

`summary` and `tech_stack` are not votable. Three summaries of one posting are three
different sentences, so a per-field majority finds no majority and any merge produces
prose no pass wrote and no posting supports. A `tech_stack` union accumulates every
hallucinated library across three passes; an intersection deletes a technology two passes
named because the third did not. The pass chosen is the one whose enum vector agrees most
with the vote, so the prose describes the reading the row actually stores rather than one
that was outvoted. Rejected: voting per token, and unioning `tech_stack`. Reversible.

### EXTRACT — `None` votes, and the integer rule is a median that never invents a value

Two passes answering "the posting does not say" outrank one that names a level: that is
the honest reading of the evidence, not a missing answer. For integers the median takes
the lower of the two middle values rather than their mean, so the stored number is always
one an extraction pass actually produced — averaging 3 and 5 into 4 would invent a
`years_experience_min` no model said and no posting contains. A three-way enum tie falls
back to the first pass, which is exactly what the script wrote before voting existed, so
the fallback is never worse than the behaviour it replaces. Reversible.

### EXTRACT — `vote_unanimity` is NULL for a single pass, not 1.0

One pass agrees with itself trivially. Storing 1.0 would make an unmeasured row
indistinguishable from a genuinely unanimous three-pass row in exactly the query the
column exists to answer. Same reasoning as task 16's refusal to print one denominator
alone. **Irreversible in practice** — once 1.0 is written for single-pass rows the
distinction cannot be recovered.

### EXTRACT — `extraction_passes` records what happened, not what the policy asked for

A three-pass platform whose extra calls were rate-limited stores 1. Writing the intended
number would make the column a restatement of `config/extraction-policy.json` rather than
a measurement, and "was this row actually voted on" would be unanswerable after the fact.
Irreversible for rows already written.

### EXTRACT — The drain loop stops on a zero-progress batch, and this is the load-bearing part

A `DEFERRED` row is written nowhere and stays eligible — that is what makes a 429
retryable rather than a discarded posting — so a rate-limited endpoint re-selects the same
batch every iteration. Without the break, the loop spins until the deadline hammering an
endpoint already asking it to stop, which is strictly worse than the single batch it
replaces. A batch that extracts nothing and rejects nothing has learned nothing. Pinned
by a test. Reversible, and should not be.

### EXTRACT — The deadline is checked between batches only, and never before the first

One batch per invocation is the old behaviour and the floor this must not fall below, so
a deadline of zero still does one batch. Checking mid-batch would abandon calls already
paid for. The real ceiling is therefore one batch of overshoot, which at 40 postings is
~114 seconds. Reversible.

### EXTRACT — A connection per batch, not one held across the drain

These connections are not autocommit, so one `execute()` opens a transaction that stays
open until the next commit — holding one across an hour of LLM calls is the "idle in
transaction" zombie that once blocked a run behind an `ACCESS EXCLUSIVE` lock. A handful
of connects a night costs nothing next to that. Reversible.

### EXTRACT — Never-extracted first, then FIFO; plain FIFO rejected

`ORDER BY first_seen DESC` is what CLAUDE.md forbids for eval corpora (~85%
greenhouse/ashby) and it was making that selection in production, where it decides which
postings are never looked at. Plain FIFO was rejected because after a `FACTS_VERSION` bump
it queues tonight's postings behind ~5,000 re-extractions — the freshest postings served
last. Never-extracted-first keeps new postings in front; FIFO within each group guarantees
nothing starves, since everything ahead of a row leaves the queue once extracted.
Reversible.

### EXTRACT — `FACTS_VERSION` deliberately NOT bumped, and the debt is recorded at the constant

Extraction semantics changed and "Versions are cache keys" says the number should move.
It does not, because task 12 owns the next bump and must carry this change — one
re-extraction paying for both rather than two burn-downs a week apart. Until then
`job_facts.extraction_passes` is what tells the two generations apart. The warning lives
at `schema.py:158` rather than only here, because that is where someone would be standing
when tempted to tidy it up. **Task 12 must not be run without it.**

### EXTRACT — `backend/docs/SCORING.md` marked superseded rather than rewritten

Its 40/day paragraph is task 04's finding and the reason the code changed, so it is kept
and annotated rather than replaced. CLAUDE.md's rule for hand-written docs: write at
decision time, mark stale, fix at phase boundaries. Reversible.

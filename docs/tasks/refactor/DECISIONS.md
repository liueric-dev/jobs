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

### 10 — Include lists accept a list of lists, and that is what bought the precision

Task 05's AI vocabulary alone is 93% junk over 2,975 rows, so lifting it verbatim — which
the task file asks for — would have shipped a gate at 6.7% precision. Include lists now
accept either a flat list (one OR group, the historical shape, unchanged for every list in
`config/relevance.json`) or a list of lists meaning "at least one term from every group",
which is how the cohort gate says "AI vocabulary AND an entry-level signal". Precision
10.0% strict rather than 6.7%. A single group keeps the un-suffixed parameter name, which
is what preserves byte-identity of the emitted SQL. Reversible.

### 10 — Task 05's regex was extended, not lifted verbatim, against the task file's instruction

The task file says lift it directly. It is incomplete: no bare `\yai\y`, no `ai-driven`,
no `ai-enabled`, and the entry-level list lacks `\yintern\y`. The task file's instruction
was written before anyone had hand-checked the pattern. Reversible.

### 10 — The invariant is verified by byte-diff against HEAD, not by inspection

The pre-change module was loaded side by side with the new one and both were asked for SQL
across seven config shapes; all seven identical, `union_sql` included. Then pinned in the
suite as a golden string. Rejected: asserting the tier counts match, which would have
proved only that this corpus does not distinguish them. The golden string is deliberately
brittle — anything that changes it changes which postings get extracted, and that should
require somebody to look at it. Reversible, and should not be.

### 10 — The cohort profile ships `active=False`, and that is load-bearing

`profiles.load_active` filters on `active`, so the profile is invisible to `union_sql`,
`extract.py` and `match.py`. This is what makes "production extraction volume does not
move" provable rather than argued, and it is why the gate could land before task 13 exists.
`persona_json` and `criteria_json` are placeholders labelled as such in their own text
rather than plausible-looking invented weights — an invented weight would be indavertently
inherited by task 13. **Activating this profile is a deliberate act with a volume
consequence: +573 rows, 13.2/day.** Reversible by one column.

### 10 — Both tier arms repeat the whole `row_ok`

Otherwise an excluded title merely drops from tier 1 to tier 2 rather than to tier 3, and
`max_tier_to_score = 2` would still admit it. The exclusion lists encode judgement that has
to hold on both include paths, not just the located one. Irreversible in the sense that
getting it wrong is silent. Reversible as code.

### 10 — A `COALESCE(description_text, '')` guard on the include path

37 rows have no description, and `NULL ~* pattern` is `NULL`, not `FALSE` — so an
unguarded include path makes the whole tier expression `NULL` for those rows. Same guard
`description_exclude` already carries, for the same reason. Reversible.

### 10 — The precision figure is reported strictly, with the generous reading beside it

10.0% strict / 23.3% generous, n=30, sample pinned by `md5(id)`. Same convention task 05
set. The headline says the gate "is better than the one task 05 measured and it is still
mostly noise" rather than leading with the improvement — task 12's extraction volume
projection consumes this number and a flattering one would mis-size it. Not reversible:
it is a measurement.

### 07 — The golden-set DDL is owned by `evals/labels.py`, not `schema.py`

`webapp/schema_web.py` reads `labels.WEB_PRIVILEGES` and `labels.WEB_SEQUENCES` and calls
`labels.ensure_schema`, so the tables are declared once. The alternative — putting them in
`schema.py` beside `job_events` — would have made the pipeline schema depend on the evals
package's vocabulary. It also would have collided with a concurrent agent, but that is not
why: labels are evidence about the pipeline rather than part of it. Reversible.

### 07 — A `CHECK` enforces that axis A carries no profile and axis B must

Not a convention, a constraint, in both directions. It is what makes
`DELETE FROM eval_labels WHERE axis = 'B'` a safe cohort teardown: nothing objective can
have been keyed to a profile by accident, so nothing objective is lost with it. Axis A
validates `job_facts`, which outlives every cohort. **Effectively irreversible** — relaxing
it later cannot recover rows already written under the wrong key.

### 07 — `tech_stack` is excluded from the form; `remote_policy` at 81.7% is kept

`03-metrics-and-golden-set.md:116` instructs that the selfcheck narrow the field set and
that the remainder be recorded as known-unstable rather than dropped silently. `tech_stack`
self-agrees 70.4% exact, and most of that instability is granularity, so a label settles a
question about the field's definition — a spec change, not evidence. `remote_policy` is a
five-value enum where a disagreement is a real disagreement a human can settle from the
posting. Rejected: dropping both, and keeping both. Reversible — the list can grow without
rework, since metrics scores only what is labelled.

### 07 — Axis B is two answers with no middle, and abstention is NULL

"Would you apply" is the decision the product actually asks a Builder to make. A 1-5 scale
invites a middle that means nothing and cannot be turned into a precision figure. "I cannot
tell" is an abstention stored as NULL, which is a different statement from "no" — and
abstentions are excluded from agreement and **counted**, never folded in. Reversible.

### 07 — Labels are append-only to the service, and a revision is a second round

No `UPDATE` and no `DELETE` grant for the web role. A label is evidence; a labeller who
changes their mind produces a second round and both rows survive, which is also precisely
what makes intra-annotator agreement computable at all. Rejected: an editable label, which
would have destroyed the ceiling measurement as a side effect of a UI convenience.
Irreversible by design.

### 07 — A tie between labellers is not broken into a consensus

Two people disagreeing is the measurement, not an obstacle to it. Ties are reported and
excluded from model-vs-human, and the count of what was dropped is reported with it.
Rejected: majority-of-three-humans, which would launder the ceiling into a false certainty
in exactly the way majority-of-3 is *appropriate* for a model and is not for people.
Reversible.

### 07 — The surface is server-rendered HTML behind the existing SSO, not a CLI

The task file says "usable by someone who has never opened a terminal" and the labellers
are ~10 Builder volunteers. `frontend/` holds one file called `.gitkeep`, so a JSON
endpoint would have had no client. Google SSO and sessions already exist in
`backend/webapp/`, so `/v1/label` costs one router. Reversible.

### 07 — Zero labels produced, and a test asserts no module calls a model to label

The boundary of the task, enforced rather than promised. Axis B is Builder preference, so
a model standing in for it makes the measurement circular — `claude-bench.py:417` treating
`sonnet-batch-1` as ground truth is the defect being avoided. Task 29 is the labelling
session and it stops until there are people. Not reversible, and that is the point.

### 14 — Kept despite ~1.8/day, and the reason is not volume

The task file sized this at 20–60 relevant/day; it measures at ~1.8. Kept anyway: it is
one documented JSON API with no HTML parsing and no token discovery, it is the only source
that publishes an **explicit close date** per posting, and it is the only one that is NYC
by construction rather than by regex. Those are properties tasks 19–21 will not have.
Rejected: dropping it as under-yielding, which would have discarded the pipeline's only
non-inferred closure signal to save a step that costs one crawl. Reversible — it is one
`STEPS` entry.

### 14 — The estimate miss is recorded as a finding about the estimates, not about the source

Second measurement this run to land far below its task file's estimate, after task 05's
43/day resolving to ≈3/day usable. The remaining Phase 3 estimates (15, 19, 20, 21) come
from the same table and should be treated as unvalidated until measured. Not reversible:
it is a measurement.

### 14 — `record_cassettes.py` excluded from the commit

It carried this task's registration and task 17's in-flight changes simultaneously.
Committing it would have shipped another agent's half-finished work under this task's
number. Task 17's commit brings both registrations. Reversible, and a consequence of
running agents in parallel over one shared file — the general fix is that shared files get
one owner, which is what `run-daily.py`'s `STEPS` already has.

### 17 — Three platforms, not the task file's four: Ashby already existed

The task file's "current coverage is Greenhouse and Lever" is wrong about the code.
Workable, Recruitee and SmartRecruiters are new; Ashby's mapping is unchanged. Recorded
because the count appears in the task file's Definition of done and a later reader
comparing four-asked against three-delivered would otherwise read it as incomplete work.
Not reversible: it is a fact about the starting point.

### 17 — Closure is conditional on reconciliation, not on absence alone

A run that collects fewer rows than the `total` the API reported does not close anything.
Absence-based closure is free and correct only when the list is complete, and a throttled
page is byte-identical to a complete one. The failure it prevents is permanent: closing a
live corpus because one page was throttled. Rejected: closing on absence and relying on
the next run to reopen, which writes a `closed` status the app has already shown a user.
Reversible as code; the data damage it prevents is not.

### 17 — `config/companies.json` retired as a roster, not deleted

`company_ats` is the single source of truth and `ingest/ats_sources.py` is the only place
that knows it. Two competing rosters is the condition the task file asked to end.
Reversible.

### 17 — `docs/ingest/ats.md` drops its `generated:` frontmatter

It claimed `generated: 2026-07-27` and no generator exists anywhere in the repo. Rather
than preserving a provenance claim nothing can back, the file is hand-written, says so,
and names what it supersedes. Task 34 still owns the directory-wide decision — this is one
file declining to keep asserting something false in the meantime. Reversible.

### 18 — `limit > 20` raises instead of clamping

`min(limit, 20)` would preserve the bug in the caller's head and produce a run that quietly
disagrees with the code that asked for it. The landmine's danger is precisely that
exceeding the cap *looks like success* — HTTP 200, empty array, no error — so it earns an
exception at the request site. Rejected: silent clamping, and clamping with a warning
(warnings in this pipeline are read the morning after, if at all). Reversible.

### 18 — A run short of the API's own `total` writes nothing, rather than writing what it got

Partial writes would be defensible for an append-only source; they are not here, because
this ingest also drives closure. Rejected: write the rows and skip only closure, which
splits one reconciliation decision into two places that can disagree. Reversible.

### 18 — No yield figure reported, deliberately

4 of 149 postings survive today's gate, and the report refuses to call that a yield: the
gate is SWE-shaped, and the task file's 80–200/day estimate assumes the Pursuit retarget
that task 13 has not done. Publishing 4/149 would have put a number in `docs/` that
measures `config/relevance.json`, not Workday. Rejected: quoting it with a caveat, which is
how a number survives its caveat and gets cited bare. **Must be re-measured after task 13.**
Not reversible: it is a refusal to measure, correctly reasoned.

### 18 — The upstream gate is justified by a measured ratio, not by principle

1,366 postings reachable per night from four tenants; detail fetching at 11% of that, ~8
minutes against 34 unguarded. The ratio is what makes the gate worth its complexity, and it
grows with the tenant count. Reversible, and should not be.

### 00 — Task files' `**Status:**` headers were stale and misled a task

Every landed task file still read `**Status:** todo`; `README.md`'s column was the only
correct index and nothing said so. Task 18 consequently reported task 04 as undone in a
shipped report. All fourteen landed files now read `**Status:** DONE, <commit>`.
Reversible, and the standing instruction is that the header moves in the same commit as
the task's own docs entry.

### 00 — Task 04 has no standalone `docs/` report

Its findings went into `backend/docs/SCORING.md` instead, so an agent asked to check
against "task 04's budget" finds no such document — which is half of why task 18 concluded
04 was undone. Recorded for task 34 to decide whether to promote them. Reversible.

### 11 — `normalize()` stopped defaulting, because the task file's premise was wrong

Task 11 section 3 says a NULL `role_archetype` "reads as a perfect archetype match" and a
NULL `advanced_degree_required` "is indistinguishable from `false`". **Neither field was
ever NULL.** `normalize()` substituted sentinels — `"other"`, `"none"`, `"unknown"`,
`bool()` — so 0 of 5,321 non-tombstoned rows held a NULL in any of them. The bias was real
but lived one layer up, in extraction, not in scoring: "the extractor could not tell" and
"the posting says none" were the same stored value, so an `unknown_penalty` would have had
nothing to fire on.

Both halves therefore shipped: `normalize()` preserves `None`, and `score_job()` prices it.
`employment_type` and `visa_sponsorship` keep their defaults — `unknown` is a real value in
those two vocabularies and nothing scores them. Not reversible without re-extraction.

### 11 — The `other` bucket was mostly a TECH vocabulary gap, not an ops one

The task file's motivating example is "an AI operations role at an insurance company". The
corpus disagrees about proportion: of 427 `other` rows, the seven proposed ops candidates
reclaim **54**; nine tech values the original twelve simply lacked reclaim **203**. 240
occurrences of "engineer" across those titles. So nine tech values were added that the task
file never proposed, and they benefit the author's own profile rather than the cohort's.
Reversible.

### 11 — Two of the seven proposed archetypes were dropped on evidence

`automation_specialist` (5 cohort postings, 1 `other` row) and `data_coordination` (8 of 9
hits are one employer's "Data Annotation Specialist"). Together they reclaim **1 row of
427**. The task file asks for values "grounded in what the corpus actually contains, not in
imagination"; these are the ones that standard excludes. Reversible, and
`derive-role-tracks.py` still probes and prints them — the evidence *against* a value is
the part a later reader cannot reconstruct.

### 11 — `ai_operations` is carried at 5 postings across 3 employers, and that is recorded

The value the whole task is motivated by is the thinnest of the fourteen. Carried because
its absence is precisely the failure being fixed, and because `other` priced at 0 is what
makes the hole invisible. But it is the weakest recommendation in the set and the first to
re-check after Phase 3. This is the same shape as the run's existing headline finding —
of 329 Workday postings from four NYC employers, zero carry AI vocabulary in the title.
**These employers are not posting these roles**, and a vocabulary cannot fix that.

### 11 — `_enum` now splits on `/`, which is scope the task did not ask for

`extract.py:33` has always named `"Senior/Mid"` as a shape that must not "silently score as
unknown for every profile forever". The code never delivered it: `/` survived the two
`replace()` calls, so `"QA/Test"` matched nothing. Fixed, because `qa_test` is one of the
new values and the docstring documents the intent. **It is a semantics change to fields
task 11 does not own** — a compound answer now resolves to the value named first rather
than to NULL, on every enum. Recorded rather than smuggled; it rides task 12's
re-extraction with everything else. Reversible.

### 11 — The tombstone guard's `== "other"` was a proxy, and it would have failed silently

`normalize()`'s "nothing usable came back" guard tested `archetype == "other"`, which was
only ever correct because `"other"` was *also* the default for an absent answer. Removing
the default would have silently stopped it firing on exactly the responses it exists to
catch, storing junk instead of tombstoning it. Rewritten as `archetype in (None, "other")`,
which is the old predicate exactly, and verified over a 192-case cross product rather than
by argument. The gain is downstream: a model that explicitly answers `"other"` is now
distinguishable from one that answered nothing.

### 11 — No `criteria_version` bump, so the whole change is inert in production

`config/criteria.json` is a template; `jobs.profiles.criteria_json` is authoritative. The
new `unknown_penalty` block and the fourteen archetype weights take effect only on
`migrate_profiles.py --apply --bump`, deliberately not run here. Two reasons: the
magnitudes are unfitted, and `years_experience_min` alone is NULL on 52.9% of the corpus,
so bumping would re-rank the live profile on a guess. Verified inert — `match.py --dry-run`
reports **0 matched** for both active profiles after every change in this commit.

### 12 — Retarget the extraction gate instead of optimising the re-extraction

The bump was costed at 5,317 rows, 5,659 calls and ~5 nights. The instinct was to
make bumps cheaper — a lazy or tiered staleness policy, so a version change did
not invalidate the whole corpus at once. **Rejected, because it was solving the
wrong problem.** `extract._eligible_sql` gates on `relevance.union_sql(ACTIVE
profiles)`, and both software-engineer job-search profiles were still active. The
5,317 rows were not the cohort's corpus; they were the repo owner's.

Deactivating `tech`/`frontend` and activating `pursuit` took the same bump to 863
rows and 28m31s. **The version-comparison predicate is good design that was
pointed at the wrong corpus**, and a second notion of staleness alongside it would
have added a mechanism to work around a configuration mistake. Rejected also:
pruning `jobs` — 190 MB total and ingest costs no LLM calls, so storage was never
where the money was.

Reversible by construction: `prune_orphans` runs inside the loop over *active*
profiles, so nothing was deleted and flipping back resumes the old behaviour at
the old price.

### 12 — Snapshot the table rather than build `--dry-run --limit` into `extract.py`

Task 12 step 3 asks for a 100-row dry run diffed field by field. `extract.py`
takes no arguments at all — no argparse — so that meant new CLI surface, and
`update_job_facts` is `ON CONFLICT DO UPDATE`, so the old values are destroyed as
it goes. Under the owner's staging-data stance the cheaper answer was
`CREATE TABLE job_facts_v2_snapshot AS SELECT *`: 6 MB, seconds, dropped after
the diff. It also produced a **better** artifact than the task asked for — a
284-row exhaustive comparison rather than a 100-row sample — with no code to
maintain afterwards.

The cost is real and recorded: once the snapshot was dropped, the per-field table
and the 427-row reachability figure became non-reproducible without re-extracting.

### 12 — The Axis A gate was waived, not satisfied

`12-facts-version-bump.md` gates the bump on task 07's Axis A labels, before and
after. Those tables are empty by design and filling them is task 29, which needs
~10 people. **Waived on the staging-data stance**: at 28 minutes the re-extraction
is cheap enough to redo, which is the property that made the gate skippable. Under
the old 5-night cost it would not have been. Recorded so that nobody reads the
completed task as evidence the gate was met.

### 19 — Measure before building, and drop on the evidence

Task 19 was scoped as a build. It was run as a spike instead, on the grounds that
three Phase 3 estimates had already come back 3x–30x high. The measurement — 2 of
55 employers publishing `JobPosting`, 1 of 35 in the actual target population,
and that one lacking `validThrough` — makes the 30–60/day estimate 13x–53x a
ceiling that is not reachable. **Dropped, not descoped.**

`extruct` was deliberately not installed. `requirements.txt` records psycopg as
the pipeline's only third-party dependency, and a spike whose job is to decide
whether to build a thing must not install that thing's dependency as a side
effect of deciding. Stdlib only, 333 requests, no LLM calls.

### 08 — `score.normalize()` gets its own vocabulary, not `extract._enum()`

The two coercers look interchangeable and are not. Extraction's vocabulary is
snake_case and `_enum()` lowercases; scoring's is Title Case with spaces
(`Core SWE`, `Bridge & Solutions`). Reusing it would have **silently rewritten
every stored value** rather than failing. D15 names this trap specifically, and it
is the reason the task exists rather than being a two-line fix.

### 08 — D16 fixed in `build_prompt`, not by requiring `buckets` in `profiles.py`

The obvious fix — add `buckets` to `profiles.validate`'s required keys — would
have rejected the `pursuit` profile, which has no buckets and which task 12 had
just made the only active one. It would also have converted a scoring-time
KeyError into a save-time failure rather than removing it. The section is omitted
when the key is absent instead. A persona with no positioning buckets is
legitimate under the Pursuit scope.

### 13 — The Definition of done was reported unmet rather than tuned into being met

Lines 122-123 ask for 20 hand-picked target roles all above `MATCH_FLOOR` and all
in the top 20. Measured: **16 of 20 above the floor, 10 of 20 in the top 20.** Line
124 is met in full at 10 of 10.

The list was picked on **title, company and location** — the three fields
`score_job()` cannot see (`match.py:276-287` selects `job_facts` plus two location
booleans and never reads the title). That is what makes it the one available
non-circular test of the weights, and it is also why tuning against it was
refused: adjusting `ai_involvement` until the fixture passed would have converted
the only independent test into a circular one, which is CLAUDE.md's "never
evaluate on the layer you trained on" at a smaller scale. Picking the top 20 of
the ranking and asserting it is the top 20 measures nothing.

Three of the four floor misses carry `ai_involvement = 'none'` and read as
AI-adjacent only because the employer is an AI company — the exact failure mode
task 05 measured at 6.7% precision. They may be correct rejections rather than
weight errors. **Task 29's labels settle that; nothing available now does.**

### 13 — Two silent defects in the authoring path, found because the DoD named it

The DoD's "created through code that task 26 will generalise, not hand-inserted
SQL" pointed at `migrate_profiles.py`, and reading it before running it is what
surfaced both:

- It passed `relevance_cfg` from a flag that defaults to absent, so a run against
  `pursuit` would have written NULL over the cohort gate task 10 built — silently,
  and the next `match.py` would have scored the whole corpus through the shared
  title filter. `daily_narrative_budget` and `active` had the same shape, and
  either would have switched on paid LLM scoring for the cohort profile. All three
  now preserve what they are not given.
- `strip_comments()` drops only **top-level** underscore keys, so nested `_comment`
  documentation reaches the database while top-level documentation does not.

Both behaviours are now pinned by test. `migrate_profiles.py` had no tests at all
before this.

### 13 — `entry` was not added to the seniority vocabulary

`13-*.md:39` asks for `target: ["entry","junior","new_grad"]`. `entry` is in
neither `extract.SENIORITY` (`extract.py:205-206`) nor `match.SENIORITY_ORDER`
(`match.py:65-66`), and `match.py:152-154` filters the target list through
`if t in SENIORITY_ORDER`, so it would have been dropped **silently** and no
extracted value could ever have matched it. Adding it costs a `FACTS_VERSION` bump
and a full re-extraction, to buy a synonym for two values already present.
Shipped as `["new_grad","junior"]`. Seventh task file confirmed wrong about the
code.

### 13 — DoD line 125 replaced with a stronger assertion than it asks for

It asks for a top-50 diff of the author's rankings before and after. `tech` and
`frontend` are inactive as of task 12 and their `job_matches` sit at
`facts_version 2`, while `job_facts` v3 exists only for the pursuit corpus — so
`match.py` cannot recompute `tech` without first re-extracting ~5,000 postings,
which is the bill task 12 was run to avoid.

Asserted instead: `tech`'s `criteria_json` md5 and `criteria_version` byte-identical
before and after. That is unchanged rankings proved by unchanged stored scores,
which is stronger than a top-50 diff and costs nothing. Its `job_matches` lost
exactly one row — to task 35's remediation, not to this change, verified by
recomputing the set md5 excluding the remediated ids.

### 35 — The gate belongs to extraction, because the leak is in the stripper

Every contaminated row is one mechanism: `lib/text.strip_html()`'s `<[^>]+>` ends
a tag at the first `>`, and modern Tailwind class names contain one
(`[&:has([data-writing-block])>*]:pointer-events-auto`), so the tag's remainder is
emitted as text. It fires source-independently — on greenhouse, where an employer
pasted a rendered page into their own JD editor and the markup is in the API's
`content` field, and on google_jobs, where a careers page was scraped. A fix in
any one ingest script would have addressed one symptom of a shared cause.

**The stripper itself was NOT fixed**, on blast-radius grounds: `lib/text.py` is
called by every ingest path. So new contaminated rows will still be ingested and
will now be rejected rather than laundered. That is a deliberate limit of what
landed and wants its own follow-up.

### 35 — The threshold was measured, and two alternatives were rejected on measurement

`MARKUP_REJECT_RATIO = 0.01` is the **geometric midpoint** of an empirical gap:
over 13,282 described postings the signature scores exactly 0.0 on all but eight,
and the worst clean row (0.0040) and the mildest poisoned one (0.0247) sit either
side of `sqrt(0.0040 * 0.0247) = 0.0099`. False positives over the full table: 0.

Rejected, with the numbers, so neither is proposed again:
- a marker blocklist (`data-testid=`, `pointer-events-auto`) — the query
  `HANDOFF.md:410-413` used. It finds **3 of the 8**, missing both `google_jobs`
  rows and both Tailwind-only greenhouse rows, which leaked class names and no
  `data-` attribute.
- repeated-content density, aimed at the navigation-menu case. It scores 0.000 on
  **all eight** contaminated rows and its six highest scorers are legitimate
  postings: six false positives, zero true ones. It measures boilerplate, which
  real postings also have.

The gate deliberately does not reject `cc7d1b61574ffdac2d112a8d`, twelve stray
Tailwind characters in an otherwise complete description. The threshold is set
where a prompt stops being a posting, not where it stops being clean.

### 35 — Remediation clears `content_hash`, and omitting it would strand the row forever

`description_text` is in `HASH_FIELDS_ATS` and `HASH_FIELDS_SHORT`
(`schema.py:131-135`), and `lib/upsert.py:219` compares the **stored**
`content_hash` against one recomputed from the **incoming** record. A row whose
`description_text` is NULL but whose hash still matches upstream takes the
`touch_sql` branch on every subsequent run: `last_seen` bumped, description never
rewritten, posting permanently invisible while the night reports success. That is
this pipeline's signature failure mode, reintroduced by the cleanup meant to fix
it.

Deleting the `jobs` row was rejected — five of the eight are real jobs at real
companies with soup spliced through them, and losing Databricks' req over twelve
class names is worse than the defect. Tombstoning the facts alone was rejected
because the poisoned bytes would survive to be re-extracted at the next
`FACTS_VERSION`.

### D45 — One durability boundary, on the iteration axis

The two tables were committed on cadences measured on **different axes** —
`ats_seed` every 20 iterations, `company_ats` every 50 records — so no choice of
constants could align them, and a run that died between boundaries kept the seed
outcome while discarding the buffer. "Partial success is the honest outcome" is
only true if both tables are partial by the same amount.

The loop moved out of `main()` into `probe_pass()` **so the cadence could be
tested rather than argued**: the test kills a pass at every one of 60 indices and
asserts set equality between the tables. Reading the loop is what let the original
defect through review, so the test does not read it.

### D45 — `company_ats` holds every negative, and the column now falsifies itself

The design question D45 declined to decide, answered yes: `tools/jsonld-probe.py`
and tasks 16/17 read the column as their **population**, and a partial column
understates every figure derived from it silently.

But `never_found` means "no ATS URL in the served HTML", not "no ATS". All four
positive controls with a verified live board — Datadog, MongoDB, Justworks, Ramp —
returned `not_found` because their careers pages are client-rendered, and all four
now carry a `never_found` row **beside** a valid token row. So **≥4 of 139 rows are
provably wrong**, in the table itself rather than in a footnote. Backfilling 104
rows did not make the column more correct; it made it complete.

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

## Allocator — this register owns the `DEC` prefix

Per [`DOCS-POLICY.md`](../../DOCS-POLICY.md) rule 6, one allocator per register and no
register issues an identifier in another's space. **This file owns `DEC-<n>` and nothing
else does.** Defects are `D<n>` and live in
[`docs/ingest/DEFECTS.md`](../../ingest/DEFECTS.md); task numbers live in
[`README.md`](README.md).

**Next free: `DEC-70`.** Allocated `DEC-46`–`DEC-69`. The count starts at 46 rather than at
1 because these entries were first issued as `D46`–`D65`, continuing the defect register's
count while it stood at `D45`. Task 39 re-prefixed them and **preserved every number** — a
citation that says 52 still means this entry — and `DEFECTS.md` records `D46`–`D65` as burnt
so the two registers can never collide on them. Each re-prefixed heading carries an
`<a id="dNN"></a>` anchor so an inbound `#d46` still lands (rule 4), and `CLAUDE_UPDATES.md`
and `docs/archive/` are `kind: record`, frozen at write time, and keep the old spelling on
purpose.

**Cross-register references are written out** — *"defect D45"*, *"decision DEC-52"* — because
a bare identifier in a code comment cannot be resolved by a reader who does not already know
which file it came from. `backend/tools/label-findings.py:82` is the worked example on this
side; `backend/tools/ats-discover.py` is the one on the defect side.

**The entries before `DEC-46` are not identifiers and do not become any.** `### 00 — Scope of
this run`, `### 06 — THE GATE`, `### SCORE-VERSIONS — …` and the two `### Defect D45 — …`
entries are **topic** headings: they name the task or the defect a decision was taken under,
not the decision. Allocation starts where it actually started, at 46.

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

### Defect D45 — one durability boundary, on the iteration axis

The two tables were committed on cadences measured on **different axes** —
`ats_seed` every 20 iterations, `company_ats` every 50 records — so no choice of
constants could align them, and a run that died between boundaries kept the seed
outcome while discarding the buffer. "Partial success is the honest outcome" is
only true if both tables are partial by the same amount.

The loop moved out of `main()` into `probe_pass()` **so the cadence could be
tested rather than argued**: the test kills a pass at every one of 60 indices and
asserts set equality between the tables. Reading the loop is what let the original
defect through review, so the test does not read it.

### Defect D45 — `company_ats` holds every negative, and the column now falsifies itself

The design question D45 declined to decide, answered yes: `tools/jsonld-probe.py`
and tasks 16/17 read the column as their **population**, and a partial column
understates every figure derived from it silently.

But `never_found` means "no ATS URL in the served HTML", not "no ATS". All four
positive controls with a verified live board — Datadog, MongoDB, Justworks, Ramp —
returned `not_found` because their careers pages are client-rendered, and all four
now carry a `never_found` row **beside** a valid token row. So **≥4 of 139 rows are
provably wrong**, in the table itself rather than in a footnote. Backfilling 104
rows did not make the column more correct; it made it complete.

### SCORE-VERSIONS — `criteria_version` is stored and deliberately NOT a cache key

`job_matches` keys its incremental rebuild on `(facts_version, criteria_version)`,
so the symmetric-looking move was to do the same for `job_scores`. It would have
been wrong, and it is the reason this work was held back out of the task 13 session.

`select_shortlist` selects `m.match_score, m.match_reasons` (`score.py:456-457`),
but `build_prompt` and `_facts_block` never read either — the prompt is five persona
keys, three `jobs` fields and ten `job_facts` fields. **Criteria decide which jobs
are asked about and in what order; they never change what is asked.** Making
`criteria_version` a cache key would therefore have marked every stored narrative
stale on task 13's bump — 1,018 reachable rows of paid re-scoring bought by a change
that could not alter a single answer.

It is stored anyway, because L2 analysis of `job_events` has to know which weight
generation ordered the list a user saw, and that is unrecoverable after the fact.
The hazard is real and named: a column that looks like a cache key and is not.
**The mitigation is `test_a_criteria_bump_alone_does_not_make_a_score_stale`, not
the comment beside it.**

This is a deviation from a literal reading of CLAUDE.md's "a row is stale iff any
recorded version differs from current", and it agrees with
`MASTER-PLAN-pursuit.md`'s C4, which names only `persona_version` and
`prompt_version`.

### SCORE-VERSIONS — a persona DIGEST, not an invented `persona_version` integer

CLAUDE.md names `persona_version`. It was built as `persona_sha` instead.

The repo's own precedent argues the other way: `profiles.upsert(bump_criteria=False)`
(`profiles.py:180-184`) makes bumping explicit because `upsert()` also writes
`display_name`, `relevance_json`, `budget` and `active`, so bump-on-write would fire
on cosmetic edits. **That premise is absent here.** `persona_sha()` already existed
(`evals/tasks/score.py`), already digested exactly the five keys that reach a prompt,
and already excluded `_comment` / `display_name` / `profile` — it is not
bump-on-write, it is bump-on-change-of-what-the-model-actually-sees, which is what
the manual flag exists to approximate by hand.

Decisive against the integer: **a manual bump can be forgotten, and this run has
already caught the profile authoring path writing wrong values silently** (task 13,
`fa2d7a7`, where `migrate_profiles.py` would have nulled the cohort gate). A missed
persona bump costs no money — it leaves a stale narrative that looks current, which
`profiles.py:33-36` itself calls worse than either a rebuild or no change.

Decisive against a whole-blob hash: `config/persona.json` carries `_comment` and
`_profile_comment`, and the persona is **never** passed through `strip_comments()` at
all — `migrate_profiles.py:180` hands `load_persona_file()` straight to `upsert` and
strips only criteria. A blob digest would move on a typo fix in a comment.

Honest cost, recorded: a digest is not orderable, so there is no oldest-first backlog
burn-down the way `extract._eligible_sql` gets from `facts_version < N`. Acceptable
because the shortlist is ordered by `match_score`, not by version. The function moved
into `score.py` beside `build_prompt`, which defines its field set; the harness
re-exports it, because the pipeline must not import the eval harness.

### SCORE-VERSIONS — unversioned is a THIRD STATE, and `IS DISTINCT FROM` is the wrong operator

The natural predicate is `s.persona_sha IS DISTINCT FROM %(current)s`. It would have
marked **all 1,018 reachable pre-existing rows stale the instant the column landed**,
because `IS DISTINCT FROM` treats NULL as "differs".

CLAUDE.md says a row is stale iff any **recorded** version differs from current. A
NULL is not a recorded version — the rule is silent on rows that record nothing, and
the honest completion of it is a third state rather than a coerced second one. So the
predicate is `IS NOT NULL AND <>`, and unversioned rows are counted in their own
census bucket and reachable only through their own flag.

The separation is not academic: today `--rescore-stale` selects **0** rows and
`--rescore-unversioned` selects **835** on `tech`. Collapsing them makes those two
numbers the same number.

The same reasoning is why the migration backfills nothing. `facts_version` is the
tempting one — `job_facts` has the column, so copying it across is one statement that
runs — and it **destroys information**: task 12 re-extracted 859 rows *after* most
scores were written, so copying today's value onto a v2-era narrative stamps it
v3-current and permanently hides a genuinely stale row. A NULL that says "unknown"
is recoverable; a confident wrong version is not.

### SCORE-VERSIONS — invalidation is inert, and that is what makes over-sensitivity affordable

No version change spends an LLM call. The default `select_shortlist` is
byte-equivalent to the old existence-only anti-join, `run-daily.py`'s step is
unchanged and passes no flag, and `--rescore-stale` / `--rescore-unversioned` each
**require an explicit `--limit`** — `daily_narrative_budget` is a nightly warm-pass
quantity, and reusing it as a backfill quantity is how an operator signs up for 51
nights of re-scoring on `tech` without typing a number.

That property is what pays for two otherwise-uncomfortable choices: an absolute
prompt-version bump rule with no carve-out for whitespace, and a persona digest that
notices edits a human would call cosmetic. **Over-sensitive invalidation costs
nothing until someone opts in.** If re-scoring ever becomes automatic, both rules
have to be renegotiated first — that dependency is recorded at
`schema.SCORE_PROMPT_VERSION` rather than left to be rediscovered.

Two spend traps were found and closed on the way. `limit = limit or budget`
(`score.py`) meant **`--limit 0` evaluated to `0 or 20` → 20 and spent 20 calls** —
and `--limit 0` is exactly what someone types to mean "don't spend"; `pursuit` was
safe only by the accident of `None or 0` being 0. And `--stale-report` is handled
*before* `main()`'s `llm.api_key()` check, so it runs on a machine with no credential
— proved by running it that way, not by reading it.

---

<a id="d46"></a>

## DEC-46 — the mock corpus is a specification test, and is never a label

**2026-07-29.** 55 synthetic postings arrived for "task 29". Task 29 is the human
labelling session and `HANDOFF.md` calls it the one thing in the plan an agent cannot
do. Writing synthetic values into `eval_labels` would reproduce `claude-bench.py:417`'s
defect inside the tool built to detect it, and `tests/test_labels.py:433` already
forbids it structurally.

**Decided:** run the corpus through the real pipeline as an *acceptance* measurement,
in a scratch schema, against a quote-backed answer key — and record it as a
specification test, in those words, in `docs/mock-acceptance.md`. It does not reduce
task 29's scope by one posting. Nothing from it reached `eval_labels`.

**Rejected:** treating the answer key as Axis A labels (circular provenance, and it
would contaminate the one asset task 29 exists to build); measuring only the 15
postings with a pre-existing addendum key (n=15, and CLAUDE.md's own line is that
n=17 is not a result).

**The quote rule is what makes the derived key legitimate.** Every expected value
carries the byte-exact substring of the posting that determines it, mechanically
verified — 605/605 — by a validator written by a different agent than the key. That
turns 40 derived entries from an agent's opinion into evidence a human can audit in
twenty minutes. It does not make them independent, and the doc says so.

<a id="d47"></a>

## DEC-47 — location flags are loader output, not extraction output

**2026-07-29.** The answer key initially scored `location_is_nyc` / `location_is_remote`
as extraction fields. They are not `job_facts` columns: `match.py:281` reads them as
`j.location_is_nyc, j.location_is_remote` from the `jobs` table. The model never
produces them — the ingest loader does.

**Caught by an independent validator, not by review.** Two agents were given the same
contract and no sight of each other's work; the loader's validator refused the key.
Had it not, two of eleven "extraction accuracy" fields would have been the loader's
mapping compared against the key's reading of the same `location` string — both from
the same twenty characters, agreeing almost always, silently inflating the headline
with a field the model was never asked.

**Decided:** a separate `loader_fields` block with a two-directional check, so an
extraction field can never appear there and vice versa. They are kept, because
`score_job` prices them (−15 / −25) and this is the only thing positioned to catch a
wrong `_location_flags()`. They are just in a different denominator.

**The general rule this session earned:** a measurement's denominator deserves an
adversarial reader who cannot see how the numerator was built.

<a id="d48"></a>

## DEC-48 — `strip_html` fixed by a superset regex, not by a parser

**2026-07-29.** `lib/text.py` is on every ingest path, which is why HANDOFF scoped this
out once already on blast radius.

**Decided:** an alternation whose first branch treats a double-quoted attribute run as
opaque and whose second is the exact previous pattern. It can only match where
`<[^>]+>` already matched, and only match further — the blast radius is bounded by
construction rather than by testing.

**Rejected: `html.parser.HTMLParser`**, the only in-repo precedent
(`tools/jsonld-probe.py`). `strip_html` must unescape exactly once — greenhouse is
escaped a level deeper (`ingest/ats.py:559-581`) — and `convert_charrefs` decodes
`&amp;nbsp;` to `\xa0`, which would delete the regression guard at
`tests/test_ats_descriptions.py:62-70` rather than satisfy it. Turning charrefs off and
re-emitting by hand reproduces the function as a state machine with a far larger set of
behaviour changes, every one reaching a stored `content_hash`.

**Rejected on measurement, not taste:** single-quoted attribute values and comment
handling were both implemented, swept over 21,350 markup strings from 13,066 live rows
at every level of escaping, and produced byte-identical output on all of them. Cost
without benefit — and single quotes carry a real risk this does not, since an
apostrophe in an unquoted value opens a run that prose then closes.

**The defect was worse than recorded.** Six greenhouse rows had the remainder of the
posting replaced by Tailwind class soup, not appended to. Remediation ran before the
rewrite, deliberately: the reverse order leaves clean text with soup-derived facts
under it.

<a id="d49"></a>

## DEC-49 — the pursuit gate lives in a file, and the harness reads that file

**2026-07-29.** The gate was a Python dict literal, `COHORT_RELEVANCE`, at
`migrations/migrate_pursuit_profile.py:147-386` — inside a script that **cannot run**.
Its guard (`:442-453`, refusal at `:526-543`) exits 1 whenever the stored
`criteria_json.archetypes` is non-empty; it holds 26, and the refusal fires *before* the
`--apply` check, so even a dry run exits 1. The source of truth for a gate three things
read lived inside the one path that could not execute.

**Decided:** `config/pursuit-relevance.json`, beside `config/relevance.json`,
`config/pursuit-criteria.json` and `config/pursuit-persona.json`, written through
`migrate_profiles.py --relevance-file` (`:159-163`) — an option that had existed all
along and had never been exercised with a real file, because none existed.

**The no-op was proven three ways rather than asserted:** the loaded dict equal to the
stored `profiles.relevance_json` key-for-key *and in key order*; `relevance.tier_sql`
compiling byte-identical SQL (799 chars) and identical params from file, migration and
stored row; `tools/mock-acceptance.py --dry-run` still 14/15/10/15.

**The load-bearing part is the harness.** `mock-acceptance.py`'s `cohort_relevance()`
(`:314-329`) pulled the dict out of the migration **by file path**, via
`importlib.util.spec_from_file_location`. It was repointed at the JSON in the same
commit. Had it not been, the harness would have kept compiling the old literal while the
pipeline ran the new file, and reported the gate unchanged — which reads as *the fix did
nothing*, not as *the instrument is pointed at the wrong object*. The invariant was
already written down, in prose, in `install_profiles`'s own docstring (`:286-289`), and
nothing enforced it: `tests/test_profiles_migration.py:52` imports the migration and
touches only `is_placeholder`, never `COHORT_RELEVANCE`. It is now asserted
(`tests/test_pursuit_gate.py`).

`relevance_json` is deliberately **not** comment-stripped
(`migrate_profiles.py:130-135`), because `relevance.load()` drops `_`-prefixed keys at
read time (`relevance.py:88-97`) — so the rationale for every list survives into the
database. That asymmetry with `criteria_json` is now pinned by test rather than by
convention.

<a id="d50"></a>

## DEC-50 — the entry-level vocabulary is split by field, and the description list is a superset by construction

**2026-07-29.** The gate is conjunctive: one AI term **and** one entry-level term, in
the *same* field (`migrate_pursuit_profile.py:216,229`). Task 10 built the
description-first path and handed it the **title** vocabulary — eleven seniority nouns,
`\yentry.?level\y` through `\yintern(ship)?s?\y`. A description does not restate its own
title's seniority noun, so on the description path the AI half matched and the entry
half did not; it was discarding 51.7% of the postings the cohort exists to find.
mock_022's "No retail or e-commerce experience required; training provided" matched
neither `\yno experience\y` nor `\ywill train\y`.

**Decided:** `description_include`'s entry group opens with the same eleven nouns byte
for byte, then adds three phrases. The title path therefore *cannot* change and the
description path can only gain rows — the same superset-by-construction argument DEC-48
used. Live over 13,447 open rows: gate 869 → 873 (tier 1 450 → 453, tier 2 419 → 420).
Mock: good_admitted 14 → 25, recall 48.3% → 86.2%, bad_admitted **unchanged at 10 — the
same ten ids**, not merely the same count. Raw live description matches for the three
added terms: 18 / 0 / 11.

**Rejected, and this is the one that matters: the phrases *instead of* the nouns.**
Measured, that takes the live gate from 869 rows to **39**, because the conjunction
needs both signals in one field and descriptions restate their own title 81% of the time
(`migrate_pursuit_profile.py:222`).

**Rejected: one widened list shared by both fields.** 873 — identical to the split,
because titles do not contain sentences. It buys nothing and gives up a provable
invariant.

**Rejected: `degree` in the noun set.** "No engineering degree required" pulled in a
Scale AI consultant role and recovers nothing; the persona treats no-degree as a
**constraint**, not a seniority signal.

Two dialect details, both measured. The window is `[^.;:]{0,40}` because `{0,30}` loses
mock_025's "No insurance license or prior claims experience required", and the negated
class stops it crossing a sentence or a bullet colon. Alternations are wrapped in
`(?:...)` because `relevance._alternation` (`:112-120`) joins terms with a bare `|` and
`--dead` tests each term standalone — a term carrying a top-level `|` is two terms
wearing a trenchcoat.

`\ydoes not require\y…` matches **0** live rows and is kept on purpose, with the same
standing as `\yattorney\y` under `config/relevance.json`'s `_dead_patterns_note`:
verified against mock_012, a working pattern waiting for its first live posting.

<a id="d51"></a>

## DEC-51 — a synthetic corpus can measure recall but cannot price precision

**2026-07-29.** Four further phrase families were compiled through `relevance.tier_sql`
against 13,447 open postings before being rejected. Live rows each admits:
"we provide/offer … training" **+17**; "we (will) train" **+5**; "preferred but not
required" **+5**; "experience … preferred / is a plus" **+123**. What they admit:
`Software Engineer, RL Training Infra | OpenAI`, `Full-Stack Software Engineer,
Reinforcement Learning | Anthropic`, `Product Manager, Gen AI | Scale AI`. **`\ywe
train\y` matched OpenAI's "we train models"** — a false friend that cannot exist on a
synthetic corpus.

On the mock corpus all four add **zero** false positives, because every intended-bad
mock posting carrying that phrasing has no AI vocabulary at all, so the conjunction
rejects it on the other half. That is a property of a corpus written to a specification,
not of the world — CLAUDE.md's "fixtures written from a specification test the
specification" firing on the very deliverable that introduced the rule (DEC-46).

**Decided:** refused, at mock recall 89.7% rather than 100%, to avoid ~136 live junk
rows — and the refusal is *recorded* rather than silently omitted, in
`_rejected_phrase_families_note` and in a sentinel test in `tests/test_pursuit_gate.py`
that asserts their absence and carries the live counts in its docstring. The harness will
keep saying they are free.

**The general rule:** a synthetic corpus's negatives were written by the same person who
wrote its positives, so it can bound recall and cannot price precision. Any vocabulary
decision taken on the mock harness alone is untrusted; compile the candidate through
`relevance.tier_sql` against the live table before shipping it.

<a id="d52"></a>

## DEC-52 — `title_exclude` narrowed to manager-and-above, and `executive assistant` kept on a census

**2026-07-29.** `title_exclude` gates **both** paths — a title-only regex ANDed onto an
already-OR'd `row_ok` (`relevance.py:232-234`), deliberate and documented at `:227-231`,
pinned by `test_relevance.py:203-211`. Six of its terms were inherited from the
*author's* software-engineer profile, and several were exclusions on the *cohort's* own
target population. Rows each was blocking alone, live: `\ycustomer success\y` 12,
`\yexecutive assistant\y` 9, `\yfacilities\y` 1, `\yoffice manager\y` 0,
`\ywarehouse\y` 0, `\ydriver\y` 0.

**Decided: narrowed, not removed.** `\ycustomer success\y` became four
manager-and-above terms (`\ycustomer success manager\y`, `\ymanager, customer
success\y`, `\yhead of customer success\y`, `\ydirector of customer success\y`), raw
title matches 120/7/4/1, none dead. Removing it outright would import 5 "Manager,
Customer Success" rows that the seniority block deliberately does not catch — bare
`\ymanager\y` was rejected at `:299-307` as genuinely ambiguous. Measured: admits
exactly 7 rows (Customer Success Associate at Datadog ×4 and AlphaSense, Customer
Success Specialist at EliseAI, Applied AI Specialist at Samsara), blocks exactly the 5
manager rows, removes none. Gate 873 → 880.

**`\yexecutive assistant\y` kept, decided on a census rather than a sample** — step 0
left this the one genuinely open question, so all 12 open EA postings at the blocked
employers were read rather than sampled. Required experience: 3+, 5+, 5+, 5+, 6+, 6+,
7+, 7+, 10+ years of executive support, one unstated. The lowest (Ramp, the only NYC
one) wants "Legal, Finance, Investment Banking, Private Equity"; most are not NYC at all
— Singapore, São Paulo, Seoul, Costa Rica, DC. The persona's `honest_gaps` says prior
seniority does not transfer.

The three zero-row terms stay, with their zeros written into `_title_exclude_note`. **No
measurement can decide a term that admits nothing** — deciding them is a persona
question, not a data one — so the counts are recorded so the next person decides with
them instead of re-deriving them.

The database write carried all three files with no `--bump`, and the blast radius was
checked afterwards rather than argued: live tier ≤ 2 880 (t1 456 / t2 424),
`extract.remaining` 2 → 13, `job_matches` content digest byte-identical across the write
(`c98c4bbceed1b77d82979e83dfad70cc`, 3,521 rows), `md5(persona_json)` and
`md5(criteria_json)` unchanged, `criteria_version` still 2.

<a id="d53"></a>

## DEC-53 — the gate is data, and the suite only tested code

**2026-07-29.** At 1,030 tests, **nothing** asserted on the AI vocabulary, the
entry-level vocabulary, or the pursuit `title_exclude`. That is exactly how a defect
costing half the gate's recall (DEC-50) sat green: every test was about the code that
compiles the gate, and the gate is a JSON document.

**Decided:** `backend/tests/test_pursuit_gate.py`, suite 1,030 → 1,058, structured
around the defect classes rather than the current values — the superset invariant, the
Postgres dialect, the recovered postings, the rejected families, the narrowed excludes,
and the harness-reads-the-same-file check from DEC-49. Its defect-class tests fail 8
subtests against the previous gate. **A test that cannot fail on the code it was written
for is documentation, not a test**, so that was checked by running it against the old
gate rather than reasoned about.

**Found while writing its Postgres-backed class:** `NULL !~* 'x'` is NULL, not TRUE, so
a NULL `company_name` or `platform` makes the whole `row_ok` conjunction NULL and the
row falls silently to tier 3. Not live — 0 of 14,049 rows have a NULL in either column —
but a fixture built with NULLs reports every row rejected, and every "expected rejected"
assertion then passes for the wrong reason. Pinned by a test rather than worked around,
because the failure mode is a green suite.

<a id="d54"></a>

## DEC-54 — the eval sampler resolves the gate per profile, and has no default that can be wrong

**2026-07-29.** `pool_query()` and `pool()` (`labels.py:440`, `:498`) took a **profile**
as the argument naming their population and defaulted `cfg` to `relevance.load()` — the
shared `config/relevance.json`, which is the *repo author's software-engineer job-search
gate*. The two are different gates, and `classify()` tests tier **before** it tests
`match_score` (`labels.py:544-547`), so this was not a near miss. Measured over the live
corpus for `pursuit`: **59 rows classified `surfaced` under the shared gate against 144
under the profile's own** — 85 postings the pipeline is actively surfacing were being
filed as `gate_rejected`, which is the one stratum whose entire value is being identified
correctly (`labels.py:461-465`).

**Decided:** resolve through `relevance.for_profile()` (`relevance.py:100-109`), the same
helper `extract.py` and `score.py` already use — one implementation, per CLAUDE.md. `cfg`
is now **required** on `pool_query()`; `pool()` resolves it from the profile row when the
caller does not already hold one, and `cmd_label_sample` passes it explicitly because it
loads the row for `criteria` anyway (`__main__.py:279-288`).

**Rejected: passing the right `cfg` at the one call site and leaving the default in
place.** There was exactly one caller, so this would have measured the same. A plausible
fallback re-arms itself the first time someone adds a second caller, and the failure is
silent by construction — a wrong gate returns rows, not an error.

**Rejected: a second relevance implementation inside `labels.py`.** Named in
`pool_query()`'s own docstring as the thing not to do; it would drift from the config and
misclassify precisely the stratum the query exists to populate.

**Worth recording:** this restores the point of `HANDOFF.md:956`'s own ordering
constraint — "draw the sample **AFTER** the gate fix" — which bought nothing at all while
the sampler was reading a different gate than the one that had been fixed.

<a id="d55"></a>

## DEC-55 — the pool window is the whole table, and a starved stratum is a refusal

**2026-07-29.** `--per-platform` defaulted to 400 newest-per-platform. Measured: that
window held **29 of `pursuit`'s 144 surfaced postings** (greenhouse 6/65, ashby 13/52,
google_jobs 9/26). `sample()` takes what a stratum has and moves on
(`labels.py:636-642`), so the drawn set would have looked entirely healthy while quietly
measuring a fifth of its own population — CLAUDE.md's "never select an eval corpus with
`ORDER BY first_seen DESC`" firing on the tool built to escape that trap.

`PARTITION BY platform` (`labels.py:486-487`) answers the *composition* complaint — the
"~85% greenhouse/ashby" one — and does nothing whatever about the recency truncation
underneath it. **They are two separate defects, and fixing one reads like fixing both.**

**Decided:** the default window is the whole table (`__main__.py:543-546`); `jobs` is
~14,000 rows and one SELECT over all of it is free. And under-fill is a **non-zero exit**:
`cmd_label_sample` compares taken against want per stratum and returns 2, naming the
shortfall (`__main__.py:306-346`). The comparison lives in the caller because `sample()`
cannot distinguish a starved pool from a deliberately small draw.

**Rejected: leaving the default and passing a large `--per-platform` at draw time.** The
set drawn today would have been correct and the next person draws with the default.

**Rejected: a warning rather than a refusal.** This repo's stated failure mode is
silence, and a warning printed above a successful `wrote …` line is silence with extra
steps.

<a id="d56"></a>

## DEC-56 — labellers are spaced by rank, not by name, and the number came from a measurement not from the formula

**2026-07-29.** `next_item()` served **every** labeller the identical order — `overlap
DESC, position ASC` — so distinct coverage could never exceed what *one* labeller
completed. The second term of `distinct = overlap + n_labellers × (budget − overlap)` was
structurally zero: adding people bought redundancy only, and task 29's "≥100 postings
from ≥5 labellers" was unreachable regardless of turnout (`labels.py:886-898`). The suite
was green because nothing asserted coverage.

**The first fix was wrong by 26 postings.** It rotated each labeller's tail by
`sha256(labeller_id)` — stateless, stable, no new state, and defensible on every axis
except the one that mattered. Verifying the coverage claim **against the drawn set rather
than against the arithmetic** showed why: the formula assumes *disjoint* windows, and
hashing does not give a partition, it gives the birthday problem. Over the real 190-row
tail, ten labellers at twenty postings each:

    hashed offsets      84 distinct postings   (misses the DoD)
    rank-spaced        110 distinct postings   (the ideal, meets it)

**Shipped:** `tail_offset(rank, tail_size)` (`labels.py:831-849`), spacing by `2**64/φ`
(`labels.py:821-828`) — Fibonacci hashing's constant, used for its low-discrepancy
property and **not** as a hash: successive multiples land maximally far apart, so k
labellers tile the tail into k near-equal windows for any k without any labeller knowing
k. `labeller_rank()` (`labels.py:852-883`) *derives* the rank from the order people started
on the set rather than storing it. `labelled_at` is written at insert time, so nobody can
acquire an earlier first label than someone already ranked and no rank moves once
assigned — which is what keeps the walk resumable for a volunteer who closes the tab.

**Rejected: storing an assigned index.** New state on a table that has to be right, and
the derived version cannot drift from the thing it describes.

**Rejected: Postgres `hashtext()`.** Stability across versions is undocumented, and it is
not testable without a database, which this package's DoD forbids.

**Rejected: `hash()`.** `PYTHONHASHSEED` randomises `str` hashing per process, so two
workers would seat the same labeller differently.

**The general lesson, and it is the reusable part: an idealised formula is not a
measurement.** The plan's 110 and the shipped code's 84 differed by an assumption nobody
had written down.

<a id="d57"></a>

## DEC-57 — task 29's five strata were reconciled to three rather than built

**2026-07-29.** The task file specified five buckets. Three of them are sub-slices of
`surfaced`, which is one stratum with one quota (`labels.py:425`, `:433`), and two of
those cannot be filled at all:

- **The `fit_score` tie block is empty by construction.** `pool_query()` never joins
  `job_scores` — it reads `jobs`, `job_facts` and `job_matches` only
  (`labels.py:488-490`) — and `pursuit` has **0 rows** in that table regardless, its
  `daily_narrative_budget` being 0 — a column on the `profiles` table (`profiles.py:75`),
  not a persona key, and so read from the live database rather than from a config file.
  Dropping the bucket costs zero postings.
- **"ranks ~20–50, n=60" asks 60 postings of ~31 rank slots**, against the 144 rows
  `pursuit` holds in `job_matches`.

**Decided:** reconcile the task file to the three strata that exist, in a correction block
at its head (`tranche_five/29-labelling-session.md:9-40`), rather than build machinery for
buckets the corpus cannot supply. The DoD's *"all five strata represented"* is read as
**all three**, which the drawn set meets.

**Rejected: widening `pool_query()` to join `job_scores`.** It would put an LLM-derived
number into the *selection* of the set built to validate that number, and CLAUDE.md is
explicit that `fit_score` only annotates — it may not reach an ordering, and a sampling
frame is an ordering.

**Also decided by the repo owner: overlap 10 rather than 20.** Distinct coverage spends
each labeller's twenty-minute budget on the shared block first, so a 20-row overlap
against a 20-posting sitting yields 20 distinct postings no matter how many people turn
up. At 10, ten labellers reach 110. **This knowingly breaks one DoD line — "20 postings
overlapped" becomes 10** (`29-labelling-session.md:164`) — and 10 rows still gives 45
annotator pairs per field. Recorded here rather than quietly satisfied: at the DoD's own
five-labeller fallback, ≥100 distinct needs ~28 items each, not 20.

<a id="d58"></a>

## DEC-58 — round 2 is the overlap block, and nothing else

**2026-07-30.** The intra-annotator ceiling was **unreachable from production**, and had
been since task 07 shipped. `webapp/label.py` never passed `round_no` to
`labels.record()`, and `next_item()`'s queue filter had **no `round_no` predicate at
all** — its docstring said *"the next job this labeller has not answered anything
about"*, which is exactly what it did, so a posting a labeller had answered was never
served to them again. `labels.intra_annotator()` was correct, tested, and had no
reachable caller. **A tested function with no caller reads exactly like a working
feature**, which is why this survived a task marked DONE and a handoff that listed the
ceiling as collectable.

**Decided:** round 2 re-serves the **overlap block only**, restricted to rows that
labeller answered in round 1 and has not answered in round 2 — the exact inverse of
round 1's predicate (`labels.py:1112-1145`).

**Why the overlap block specifically.** It is the only part of the set more than one
person sees, so it is already where the *inter*-annotator ceiling is measured. Re-serving
those same rows means **both ceilings are computed over identical postings** and can be
read against each other. Measured on two different subsets they would differ for two
reasons at once — the quantity and the postings — and
`test_the_two_ceilings_are_different_quantities` exists precisely because that
distinction is the point. It is also 10 rows, which is what
`docs/ingestion_tests/03-metrics-and-golden-set.md:25` asks for (*"5-10 jobs labelled
twice"*), at ~10 minutes of a volunteer's time.

**Rejected: a fresh 5-10 postings drawn for round 2.** Literally what `03:25` describes,
and it forfeits the comparability above for nothing. It would also draw from the tail,
where each labeller's window is their own, so the two ceilings would be measured on
disjoint populations.

**Rejected: rotating round 2's queue by labeller rank, as round 1 does.** Round 2 is ten
rows and every labeller answers all of them, so there is no coverage to spread; rotating
would only make two people's queues differ for no gain.

**Rejected: enforcing the delay inside `next_item()`.** It is enforced by
`round_two_ready()` instead, so a caller can explain a refusal. *"Come back Tuesday"* and
*"you have finished"* are different states, and a queue function that returns None
collapses them. Reversible; both functions are pure of each other.

**Also decided:** `progress()`'s round-2 denominator is the overlap block, not the
200-row set (`labels.py:903-925`). Showing a volunteer *"3 / 200"* on a queue that is ten
rows long reads as an eight-hour evening and is the single most likely reason someone
closes the tab. The queue and the denominator have to be the same population.

<a id="d59"></a>

## DEC-59 — the seven-day delay is the measurement, not a politeness setting

**2026-07-30.** `labels.ROUND_TWO_DELAY_DAYS = 7` (`labels.py:1007`), and it is recorded
here because it looks exactly like a tunable and is not one.

Round 2 exists to measure whether one person gives the same answer twice. **Served an
hour later, it measures whether they REMEMBER their first answer** — a fact about human
memory, not about the field's difficulty. It would come back near 100% and then be quoted
as a ceiling, which is worse than not collecting it: a fabricated ceiling makes every
model-vs-human figure beneath it look bad by comparison.

**Decided:** seven days, taken from
`docs/ingestion_tests/03-metrics-and-golden-set.md:25`'s *"5-10 jobs labelled twice, **a
week apart**"*. The constant is that phrase in code and the docstring says so.

**Rejected: shortening it to fit a single evening.** It does not buy a faster
measurement, it buys a different and weaker one.

**Rejected: showing an empty page when it is too soon.** `round_two_ready()` returns a
**date** and the form names it (`_TOO_SOON` in `webapp/label.py`). A volunteer told *"not
yet"* with no date either gives up or retries daily, and either way the operator hears
nothing about it.

**Not decided here, deliberately: whether to spend the second sitting at all.** It costs
~10 minutes per volunteer, seven days later, for the *weaker* of the two ceilings. That is
a judgement about people donating their time and it belongs to the repo owner on the
night. Both paths are implemented; the round-2 link is simply not sent unless someone
chooses to send it. See `LABELLING-NIGHT.md`.

<a id="d60"></a>

## DEC-60 — `NO_TRACK_FITS` is a stored value, not a `validate()`-time fold

**2026-07-30.** `extract.py:338` tells the model *"Use null if none of the listed tracks
clearly describes the role. Do not force a value"* — so **the model's NULL on
`role_track` is a substantive verdict**, unlike `role_archetype`, whose prompt says
`"other"` *"is a real answer and is not the same as omitting the field"*. `ROLE_TRACK` has
nine values and no `other`.

The form's *"I can't tell from this posting"* is an **abstention**, and
`labels.validate()` collapses `''` and `'unsure'` to None. **Without a distinct value,
both would store NULL and `model_vs_human()` would score a considered verdict and a shrug
as agreement.**

**Decided:** `labels.NO_TRACK_FITS = "no_track_fits"` (`labels.py:184`), offered as a
tenth choice on that one question and rendered *"none of these describes this role"*
(`webapp/label.py:_CHOICE_LABELS`). **Storage keeps the two apart; the fold to the
model's domain happens at comparison time only**, in `labels.as_model_domain()`
(`:1492`), where `NO_TRACK_FITS` against a model NULL reads as **agreement** — both
saying no listed track fits.

**Rejected: folding it in `validate()`.** That writes None to `eval_labels` and makes
"no track fits" indistinguishable from "I can't tell" **forever** — a one-way loss, in
the one table this module exists to keep uncontaminated. It is the same conflation
`AXIS_B_VALUES` already refuses for "no" versus abstention, one field over.

**Rejected: growing `as_model_domain()` into a general normalisation layer.**
`questions()` reads its vocabularies from `extract.py` precisely so no such layer is
needed; a second place where values get rewritten is a second place they can drift. One
field needs this and the function says so.

**Why the fold loses nothing:** a human abstention never reaches a comparison —
`consensus()` drops None values and `vs_each` skips them — so the only thing
`NO_TRACK_FITS` can ever match is a model null. Reversible: storage is faithful, so a
different comparison rule can be written later against the same rows.

<a id="d61"></a>

## DEC-61 — `role_track` is on the form despite having NO task 06 self-consistency floor

**2026-07-30.** This is the entry that most looks like an inconsistency, so it is
recorded rather than left to be rediscovered. The other four axis-A fields are on the
form because **task 06 measured them and found the model unstable**; a human label buys a
ceiling to read that instability against. **`role_track` has no task 06 figure at all** —
it postdates that measurement (task 11 added the column) and its nine-value vocabulary is
explicitly provisional, derived pre-Phase-3 from a tech-heavy corpus
(`docs/role-track-derivation.md`).

**Decided: include it anyway.** Task 30 groups its precision figures **by** this
vocabulary, so an unvalidated vocabulary would silently condition every per-track number
that task produces. And the validation is only available now — **nobody can label a set
after the labelling session is over.**

**The argument that settles it is that the label buys most where the model is silent**,
which inverts the usual reasoning. Measured **2026-07-30, after that morning's 04:09
nightly run**, over `job_facts` at `facts_version = 3`: `role_track` is NULL on **261 of
917 rows (28.5%)** — non-null 656 of 917 — and within `pursuit-v1` on **16 of 100
`surfaced`, 16 of 50 `below_floor` and 50 of 50 `gate_rejected` — 82 of 200**. On those 82
`model_vs_human()` is silent, and that is the interesting half: **if a human confidently
assigns a track where the extractor abstained, the NULL rate is an EXTRACTION problem; if
the human cannot either, the VOCABULARY is wrong.** Those are different fixes and no other
instrument distinguishes them.

**Superseded figures, correct when taken (2026-07-29, before the run): 244 of 881 = 27.7%
corpus-wide, 83 of 200 in the set, 17 of 50 `below_floor`.** Recorded rather than replaced
silently, because **the delta is a finding in its own right**: the nightly took v3 from 881
to 917 rows and **one `below_floor` posting in the pinned set acquired a `role_track`
overnight**. `pursuit-v1`'s membership is pinned by sorted `job_id` and its digest did not
move — **but the facts underneath its rows are not pinned by anything.** Any figure
computed from `job_facts` about this set carries the date it was taken; one quoted without
a date is unverified. Third instance of *"the other agent in the room is the cron job"*
(`HANDOFF.md`, § *nothing is in flight*), and the first of the three to move a *rate about
a frozen sample* rather than a row count.

**Also worth recording, because it is the shape of a false corroboration:** the superseded
27.7% and the 27.7% at `docs/facts-v3-diff.md:468` are **different measurements** — 244 of
881 against 239 of 863, different runs and different denominators — that happened to round
alike. The current 28.5% breaks the coincidence.

**Rejected: swapping it in for `role_archetype` to keep the form at five questions.**
`role_archetype` is the field task 12 measured at 31.1% `other` (44.0% on first-time
extractions), so it is the one with a *known* quality problem; dropping it would forfeit
the label that diagnoses it.

**Cost, recorded rather than hidden: the form is now six questions per posting, not
five.** Every budget figure computed against five — including the "≥100 distinct needs
~28 items each at 5 labellers" in DEC-57 and `HANDOFF.md` — was computed for a shorter form.
Re-check the arithmetic before the night. Reversible: removing a question is a one-line
change to `AXIS_A_FIELDS`, and it costs nothing already collected.

**And a drift this found:** `role_track` was **missing from `evals/tasks/extract.py`'s
`FIELD_KINDS` entirely**. Task 11 added the column and never registered it — exactly the
drift that file's own comment warns about. It was caught by an **existing** test the
moment the field went on the form, which is the test earning its keep rather than a new
one being needed.

<a id="d62"></a>

## DEC-62 — an existing guard test was deliberately widened to admit `round_no`

**2026-07-30.** `test_the_stratum_is_never_handed_to_the_renderer`
(`backend/tests/test_labels.py:1036`) asserts `_render_form`'s parameter list **exactly**,
as an allowlist, and the round-2 work had to add `round_no` to that signature. Changing a
guard test to make a change pass is normally the thing not to do, so the reasoning is
recorded here.

**Decided:** widen the allowlist to `["job", "question_list", "label_set", "done",
"total", "overlap", "round_no"]`, and write the *rule* the list encodes into the test
body so the next reader does not have to infer it from the membership.

**The rule is: nothing that tells the labeller what the PIPELINE thinks of this
posting.** A stratum name is the pipeline's verdict in one word — `surfaced` tells a
labeller the ranker already liked this posting, `gate_rejected` tells them it never made
it in — and either one contaminates the judgement the form exists to collect. Against
that rule:

- **`overlap` is admissible.** It says only that other people also see this posting.
- **`round_no` is admissible.** It says only that *this person* saw it before — and the
  form must say so out loud, or a volunteer reads the repeat as a bug and "corrects" it to
  whatever they said last time, which is the one answer that makes the measurement
  worthless.
- **`stratum` stays off**, and `next_item()` still returns it while the route still
  declines to pass it on. `assertNotIn("stratum", _code_only(...))` is unchanged.

**Rejected: relaxing the assertion to a `assertNotIn("stratum", args)` check alone.** The
exact-list form is what makes an *addition* visible; a membership test would let a future
`match_score` or `tier` argument through silently, and those carry verdicts too.

<a id="d63"></a>

## DEC-63 — the paired bootstrap refuses to score a degenerate resample as 0.0

**2026-07-30.** `bootstrap_delta()` was lifted into `backend/evals/metrics.py:705` from
`tools/learned-ranker-probe.py`, and **rejecting one line of the original is the
substantive reason it was moved rather than copied.**

The probe's metric reads
`average_precision_score(yy, s) if 0 < yy.sum() < len(yy) else 0.0`
(`learned-ranker-probe.py:438`). A resample drawn with replacement can contain no
positives, where average precision does not exist. Substituting 0.0 gives **both** sides
of a degenerate draw 0.0, so its delta is exactly 0.0 — and every such draw is one more
exact zero in the middle of the distribution the percentiles are read off. **The interval
widens toward zero at the near end, manufacturing "not distinguishable" out of an
arithmetic guard.**

**At n in the hundreds this is rare. At the per-`role_track` n of about a dozen that task
30 needs it is routine** — one positive in twelve rows makes (11/12)^12 ≈ 35% of draws
degenerate. The function's docstring records the measured consequence: on twelve rows
with one positive, a perfect ordering against its own reverse is **+0.917 [+0.823,
+0.917]** here and **+0.917 [+0.000, +0.917]** with the substitution — *"better"* against
*"not distinguishable"* on the same data (400 draws, seed 11, pinned in
`tests/test_metrics_ranking.py`). **The guard would be silently deciding the very
comparison it was written to protect.**

**Decided:** a degenerate resample is **skipped and counted**, never scored. Skipped
draws land in `n_undefined`; `draws_used` is what the interval rests on and travels in
the return value. Below `MIN_USABLE_FRACTION` of `draws`, `value` is None and no interval
is reported — past that point the surviving draws are a minority subset selected by
something correlated with the statistic, which is trap 4.1 of
`backend/docs/HANDOFF-match-quality.md:147` in a third costume.

**Worth recording precisely, because the guard is wrong twice and biasing once:**
`yy.sum() == 0` is genuinely undefined and 0.0 is an invented value — that is the biasing
case. `yy.sum() == len(yy)` is **not** undefined: every ordering of an all-positive set
has average precision 1.0, and this module returns it, so there the substitution is
merely a wrong value whose error cancels in the difference.

**Also decided: `value` is the observed delta on the full paired sample, not the mean of
the resamples.** The probe returns `np.mean(deltas)` (`:428`), which is the bootstrap's
estimate of the mean and differs from the statistic on the actual sample by the bootstrap
bias — a headline number no reader can recompute from the corpus. Here the resamples only
ever set `(lo, hi)`.

**Rejected: a tighter usable-draws floor than `MIN_USABLE_FRACTION`.** See that
constant's own note for the 1/e bound. **Rejected: reproducing the probe's endpoints
digit-for-digit** — `random.Random` and `numpy.random.default_rng` draw different index
lists from the same seed, so the two agree only to resampling error, and nothing should
be built on comparing their digits. The shared seed (11) is the same *discipline*, not the
same stream.

### 29 — per-Builder scoring is ONE derivation function, not N criteria files

Recorded 2026-07-31 from a design session dated 2026-07-30. **Nothing is built**; this
entry exists so the reframe is not re-litigated from scratch, and so the reasons it is
*not* what task 11 already rejected are on the record.

DECIDED: per-`(posting, Builder)` scoring is the destination, in the form of **one
derivation function from a `user_facts` record to criteria deltas, composed over
`config/pursuit-criteria.json` as the population prior**. Rejected: thirty hand-authored
per-Builder criteria files.

**Why this is not the thing task 11 already rejected.**
`tranche_two/11-archetype-superset-role-track.md` §2 rejects eight track profiles because
*"eight configs nobody can validate is worse than one"* and because
*"`learned-ranker-probe.py` already identified hand-tuned weights as the bottleneck."*
Thirty authored files is that first objection four times worse. The split:

- **The artifact-count argument does not survive the reframe.** One generator is one
  artifact to validate, and the per-Builder configs stop being authored at all — they
  become regenerable outputs. Task 11's own section heading two paragraphs later is
  **"Derive it, do not author it"**, and its closing line is *"If a track later proves to
  need its own weights, promote it to a profile. `profiles` already supports that; nothing
  is foreclosed."* The reframe is what that file asks for, applied one level up.
- **The hand-tuned-weights argument survives intact**, and lands on the derivation
  function's own coefficients. It is concentrated in one place, not removed. That is risk 3.
- **Task 11's cost argument supports the reframe:** *"Compute is not the constraint —
  `job_matches` is arithmetic."*

**Plumbing that already exists.** Each verified 2026-07-31 rather than cited from memory;
by symbol where the line is likely to move.

| | |
|---|---|
| `job_matches` PK `(job_id, profile)` | `schema.py`, `MATCHES_TABLE` DDL |
| `job_scores` PK `(job_id, profile)` | `schema.py`, `SCORES_TABLE` DDL |
| the N-profile cross product | `MATCH_FLOOR`'s own comment, *"at N profiles the full cross product is N x 11k rows"* |
| *"flat in the number of users"* | `extract.py` module docstring |
| *"a brand-new profile gets a full ranked list in seconds"* | `schema.py`'s two-tier note |
| moving a user between profiles | `app_users.profile`, `manage_app_users.cmd_set_profile` |
| the frozen response contract | `API-CONTRACT-v1.md`'s top-level `profile` field — a per-Builder profile name is a different string in a field that already exists, **so the freeze is not broken** |

**The one claim that needed reconciling, and it resolves in the reframe's favour.**
`manage_app_users.py`'s header said *"extract.py and score.py both fan out per active
profile."* True of `score.py`, which loops `for prof in targets` with LLM calls inside it.
**False of `extract.py`**, which loops over profiles nowhere: it builds one `cfgs` list and
hands it to `_eligible_sql` → `relevance.union_sql`, an **OR** across every active gate
(*"does this row clear the bar for ANY profile?"*). Facts are extracted once per **posting**
and shared. So an added profile cannot multiply extraction calls — it can only add the
postings its own gate admits that no other active gate does, and **for N profiles sharing
one derived gate that delta is exactly zero.** The header comment was corrected in the same
change. Extraction cost is genuinely flat across profiles sharing a gate; the real
per-profile cost is `score.py`, and `pursuit` runs at `daily_narrative_budget = 0`.

**Risks, unranked, none dropped.**

1. **Ground truth gets scarcer per stratum exactly as parameters are added.** ~30 Builders,
   and the measured rate is ~154 s/posting — so twenty minutes is ~8 postings, not 20
   (`29-labelling-session.md` § *Findings, 2026-07-31*, E). Current turnout is one.
2. **`inter_annotator()` and `interpretable()` stay correct for Axis A and become the wrong
   instrument for Axis B.** Do not change either function; the fix is a labeller attribute
   to decompose by, which is why `app_users.prior_domain` landed.
3. **Two unfitted layers compose.** `pursuit-criteria.json`'s `_unfitted` plus the
   derivation function's own numbers, and error cannot be attributed between them.
4. **n=1 validation.** Validating a per-Builder function against its author is structurally
   the `claude-bench.py:417` "single run as ground truth" defect with a person substituted.
   Live rather than hypothetical: `eval_labels` has one labeller today.
5. **Resume parsing moves onto the critical path** as the source of `user_facts`.
6. **PII posture changes in a public repo that is also a portfolio piece.** The decision
   wants making **before the first resume lands**, not after.
7. **There is no loader from `eval_labels` into anything that can re-tune weights, and
   nobody owns building one** (`HANDOFF.md` § *Pending follow-ups*). `calibrate-match.py`'s
   ground truth is `job_scores` — the LLM — so sweeping with it fits the weights to the
   model the labels exist to check. And *"what an axis-B `would_apply` consensus means as a
   regression target"*, including the ties `consensus()` deliberately refuses to break, is
   decided nowhere. **This is a hard dependency, not a caveat.**

**Explicitly not done:** the derivation function, per-Builder profiles, a `user_facts`
table, and any change to a number in `pursuit-criteria.json`.

Reversible — it is a direction with no code behind it. The one thing that is not free to
reverse is risk 6, which is why it is called out with a deadline.

<a id="d64"></a>

## DEC-64 — the commercial gap in `ARCHETYPE` is recorded as a proposal, not applied

**2026-07-31.** `derive-role-tracks.py --archetypes` was re-run against the population it
is now correct about (DEC-65) and re-derives the archetype vocabulary at `facts_version = 3`
for the first time since task 12 made 3 current. It recommends **one** new value,
`revenue_commercial`. **Nothing was applied**: `extract.ARCHETYPE` is still 26 values and
`schema.FACTS_VERSION` is still 3. The evidence, the four candidates dropped and the
counter-evidence for each are in `docs/role-track-derivation.md` § *The commercial gap in
`ARCHETYPE`, and the one value proposed for it*.

**Decided: land the vocabulary and the rationale, and do not bump.** This follows
`config/extraction-policy.json`'s `_not_a_version_note` exactly — a change that ought to
move `FACTS_VERSION` deliberately does not, yet, so that the next bump carries it and one
re-extraction pays for both.

**The objection is that `pursuit-v1` is being labelled right now. Cost is not the
objection.** Both vocabularies are interpolated into `_INSTRUCTIONS` (`extract.py:322`),
the cache-keyed fixed prefix whose own comment asks for a `FACTS_VERSION` bump on exactly
this kind of change — so applying the value means re-extracting the corpus, which rewrites
the model answers the human labels exist to be read against, **mid-collection, on a set
whose redraw window has closed.** 31 of 200 items are labelled and the overlap block is
complete.

**And the two halves could not be reconciled afterwards, which is what makes it
irreversible rather than merely awkward.** `job_facts`' primary key is `job_id` **alone**
(`schema.py`, `FACTS_TABLE` DDL) — one row per posting — so re-extraction *overwrites* the
answers the first 31 postings were labelled beside; they are not kept at the old version.
And `eval_labels` records `labelled_at`, `round_no` and `labeller_id` but **no
`facts_version`** (`evals/labels.py`, `eval_labels` DDL), so nothing marks which extraction
a label was formed against. This is DEC-61's *"membership is pinned; the extraction under it
is not"* done deliberately, across every axis-A field at once, instead of one row at a
time by the cron job.

**Cost, recorded so it is not re-derived as an objection:** task 12 measured the whole
re-extraction at **863 calls / 28m31s / ~\$0.33**; `docs/facts-v3-diff.md` has the sizing.
The bill is not what is being avoided.

**What applying it will need, so the next bump is not surprised:** a weight in **both**
`config/criteria.json` and `config/pursuit-criteria.json` — `tests/test_match.py:484`
asserts `set(extract.ARCHETYPE)` equals the priced set *exactly*, so a new value fails the
suite until both are edited — and the count at `tests/test_extract.py:720`, 26 → 27.

**Rejected: bumping `FACTS_VERSION` now and treating the labels already collected as a
separate round.** `round_no` means *this labeller saw this posting before* (DEC-58, DEC-62); it
does not and cannot mean *these labels sit beside a different extraction*. With the old
facts overwritten and nothing recording which version a label met, the pre-bump rows would
be neither comparable to the post-bump rows nor separable from them. The vocabulary gain
will still be there in a week; the reconcilability would not be.

**Rejected: adding all five probed commercial values** — `finance_accounting`,
`strategy_bizops`, `people_recruiting` and `clinical_care` alongside `revenue_commercial`.
**12 → 26 is the move that has already been tried and was not followed by a fall in
`other`** — task 12 reported it *rising*, though that comparison conflates a vocabulary
change with a corpus change and is corrected in
`docs/role-track-derivation.md`. What survives the correction is that fourteen new values
bought no visible shrinkage, which is the part that matters
here. Adding five at once repeats that, and at 26 hand-maintained values
the stated alternative to growing the list is SOC, not a longer list
(`docs/role-track-derivation.md` § *The O\*NET/SOC escape hatch*). One value carried by a
structural argument is a different bet from five carried by counts. The four are **deferred
with their evidence printed, not refuted** — `clinical_care` alone is refuted, by employer
spread: 56 of its 56 `other` matches are one employer.

**Rejected: reading the corpus `other` rate as a finding about Builder preference.**
`other` is **31.3%** over the 940 `job_facts` rows at v3; the humans answered
`role_archetype = other` on **17 of 31 = 55%** of labelled postings drawn from a stratified
200-row eval set. **Two different populations, and neither is an agreement figure.**
`tools/label-findings.py` prints them side by side and deliberately prints no
model-vs-human comparison, for the reason DEC-57 and DEC-61 give: one labeller, no
inter-annotator ceiling. The two also disagree in *emphasis* — only **2 of the 13** human
`no_track_fits` rows are commercial (both Notion *Commercial Solutions Consultant*), while
the corpus is where the commercial mass is. Treating either as corroboration of the other
would be the false-corroboration shape DEC-61 already records at 27.7%.

Reversible: completely — two documents changed and no code. The bump is the part that
would not have been.

<a id="d65"></a>

## DEC-65 — `load_other()` probes the CURRENT `facts_version` by default

**2026-07-31.** `tools/derive-role-tracks.py`'s `load_other()` had **no `facts_version`
filter**. Its docstring said it returned every `job_facts` row *the current vocabulary*
could only call `other`; it returned rows from **every vocabulary the project has ever
had**. Correct on the day it was written — 2026-07-28, when the current version *was* 2 —
and silently wrong from task 12's bump onward, which is the interval in which the tool
exists to be re-run.

**Measured.** Unfiltered, `other` is **696** rows, of which **402 (58%) are
`facts_version = 2`** — the twelve-value vocabulary, which never contained the fourteen
values the tool exists to evaluate. At v3 the population is **294 of 940**. The effect on
the printed reclaim, raw `other` matches unfiltered → at v3:

| candidate | unfiltered | v3 |
|---|---:|---:|
| `hardware_embedded` | 54 | **3** |
| `infrastructure_compute` | 42 | **2** |
| `engineering_management` | 32 | **0** |
| `qa_test` | 22 | **0** |
| `mobile` | 16 | **0** |
| `business_systems` | 15 | **0** |
| `developer_relations` | 11 | **0** |
| `ai_operations` | 10 | **0** |
| tech values, distinct-row union | 202 (29.0% of 696) | **9 (3.1% of 294)** |

**Decided:** `--facts-version`, defaulting to `schema.FACTS_VERSION`. `--facts-version 0`
means *all versions* and reproduces the historical figures exactly; the population is
printed in the header of every run, so no figure from this tool can be quoted without it.

**The conclusion this inverts is the point, not the flag.** Those 202 tech rows are
`other` **under the twelve-value vocabulary**, on the author's tech corpus. Counting them
as reclaim credits fourteen new values with rows the extractor is not being asked to
re-judge: the v3 population is a different corpus as well as a different vocabulary — task
12 retargeted the extraction gate to `pursuit` — and it contains almost none of that
hardware and data-centre work, which is why the same probes match 3 and 2 rows there. So
the remaining v3 `other` bucket is **not** evidence that the 26 values sit unused; it is a
different and smaller gap. `docs/role-track-derivation.md`'s original headline — *"mostly
a tech vocabulary gap"* — is true of the population it was measured on and does not
describe the current one; it is corrected beside itself there, not swept.

**Rejected: leaving the historical population as the default.** The default is what gets
run, and what gets run is what gets quoted; a tool whose headline number silently answers a
question about a vocabulary two versions old is the *"silence is this system's failure
mode"* rule (CLAUDE.md) in documentation form.

**Rejected: deleting the pre-bump rows, or filtering them out of the query permanently.**
The v2 rows are the evidence for what task 11 actually decided, and a later reader who
cannot reproduce the 427/696-row figures cannot audit that decision. Making the version an
**explicit argument** keeps both populations reachable and forces whoever quotes a number
to name which one it is over.

**Two smaller fixes in the same file, recorded because each had hidden a whole family.**
`_families()` derived its family list from two hardcoded `("ops", "tech")` tuples while
`CANDIDATES` had grown a third — so the commercial family was probed, counted, and **never
printed**. It now derives the list from `CANDIDATES`, as does the union-reclaim table's
per-family rows. A hardcoded list beside a data structure that already knows the answer is
the same defect twice.

Reversible: yes, and cheaply — the flag makes every prior figure re-derivable.

---

## DEC-66 — documentation kinds are declared in the file, and every rule gets a script

**2026-08-01.** A review of the whole tree found four documents that had drifted out from
under task 34 § D's disposition rule — which is *correct*, and which nothing could be checked
against because it lived inside one task file. The entry point in `HANDOFF.md` was still
sending every fresh session to do task 34, justified by a premise task 34's own file had
struck as **WRONG**; `D45` had come to mean three different things, one of them inside
`backend/tools/ats-discover.py`; and the main suite's test count was written three ways in
three live documents, none of them what the runner prints.

**Decided:** [`docs/DOCS-POLICY.md`](../../DOCS-POLICY.md), seven rules. The two that carry
the weight:

**Every document declares its `kind:` in frontmatter** — one of `contract`, `rationale`,
`record`, `rolling`, `task`, each with exactly one lifecycle. This is not a new taxonomy. It
is a *name* for what the tree already does: `DECISIONS.md` is append-only rationale and its
header says so, `CLAUDE_UPDATES.md` is a dated record, `HANDOFF.md` is rolling. The kinds
were always there. Nothing could check them because nothing declared them.

**A rule with no check is a suggestion.** Stated as an empirical claim about this repository
rather than a principle, because the evidence is here: two documentation rules were written
by careful people in the same task, `audit-doc-links.py` got a script and holds at zero
today, § D did not and four documents drifted. The claim is not that prose rules are useless
— § D's rule is the one this whole tranche is built on — but that **a correct rule with no
check decays at the speed of the surrounding work**, and this run has now measured that
speed twice.

**Rejected: a schedule.** "Review the docs at each phase boundary" is what § D already
implies and it is the thing that did not happen. A calendar cannot tell you *which*
document went wrong, and the failure mode being fixed is precisely that a stale document
looks exactly like a current one.

**Rejected: deleting the stale material.** Rule 4 keeps *mark, do not delete*. What is added
is the missing trigger — a `rolling` document whose subject has landed is archived **in the
same commit that lands it**, because the reason `HANDOFF.md`'s entry point survived task 34
is that nothing ever gave it a reason to stop.

**Rejected: checking prose accuracy.** Named in the policy as explicitly unenforced. No
script can check whether a sentence is true, and a green tick that implies otherwise is
worse than no tick — `AUDIT.md` § *How to audit this run in an hour* exists for that reason
and is not replaced by any of this.

**This entry uses the `DEC-` prefix that rule 6 establishes**; ~~entries D46–D65 above still
carry the old bare `D`, and task 39 brings them into line~~ — **task 39 landed 2026-08-01;
they now read `DEC-46`–`DEC-65`, numbers preserved, each with an `<a id="dNN"></a>` anchor so
an inbound `#d46` still lands.** Using the target form from the
commit that lands the policy is deliberate — a convention whose own founding entry does not
follow it is a convention with a footnote.

Reversible: yes. The frontmatter is additive, and `audit-docs.py` is a new script that
nothing else imports.

---

<a id="dec-67"></a>

## DEC-67 — the `D` namespace is split by prefix, and the two record histories are left unswept

**2026-08-01, task 39.** `D45` resolved three ways — one defect and two decision entries —
and the ambiguity had already reached `backend/tools/ats-discover.py`. `DOCS-POLICY.md`
rule 6 gives each register one allocator; this applies it.

**Decided:** `D46`–`D65` become `DEC-46`–`DEC-65`, **numbers preserved**, each heading
carrying an `<a id="dNN"></a>` anchor so an inbound `#d46` still lands. The two `### D45`
entries are retitled `### Defect D45 — …`: they were never identifiers. They are topic
headings and the topic is the defect, exactly as `### 06 —` means "decisions taken while
doing task 06" — and the second entry's own first sentence says so.

**Rejected: renumbering to `DEC-01`–`DEC-20`.** Starting the register's count where the
register starts is tidier, and it would have invalidated every inbound citation *silently* —
the precise failure mode this tranche exists to close. Twenty integers burnt in `DEFECTS.md`
is the cheaper price, and that register now says so in its header.

**Rejected: a regex sweep.** The identifier to be changed and the identifier to be left
alone are the same string; only the surrounding sentence separates them. Every `D45` in the
tree was resolved by reading it, and the dozen in `ats-discover.py` and
`test_ats_discovery.py` all mean the defect and were not touched. `sed` would have corrupted
them and the suite would have stayed green while it did.

**Rejected: sweeping the historical logs.** `CLAUDE_UPDATES.md` and `docs/archive/` are
`kind: record`, frozen by rule 1, and keep the old spelling. This is only safe because of the
anchors above and because `DEFECTS.md`'s allocator names the exemption — a surviving `D58` in
a session log can never be re-read as a defect if no defect can ever be issued at 58.

**The anchor sits on its own line with a blank line under it**, not immediately above the
heading. An anchor pressed against an ATX heading is the kind of markdown that renders
correctly in most parsers and not in all of them, and the anchor being added here exists
precisely so that a citation does not depend on a renderer's goodwill.

Reversible: yes, mechanically. The prefix carries no information the number does not, and the
anchors mean the old citation form never stopped working.

---

<a id="dec-68"></a>

## DEC-68 — the doc checker lands red in the CLI and green in the suite, against a declared baseline

**2026-08-01, task 36.** The task asks for two things that conflict once the checker is
wired into `unittest discover`, which is the whole point of wiring it in: **it must land
red** — *"a checker whose first run is green has been tested against nothing"*, and C5 had
22 real failures — **and both suites must stay green**, because that is the gate every
later wave of this tranche runs against.

**Decided:** `backend/tools/audit-docs.py` exits non-zero on the tree as it stands, which
is what the Definition of done actually checks. `backend/tests/test_docs_policy.py` gates
on **regression** instead of on zero: the current finding set must be a **subset** of
`backend/config/doc-policy-baseline.json`. Clearing a finding keeps the suite green; a
**new** finding turns it red. The baseline was written by the checker's own first run —
93 C1, 95 C2, 5 C4, 22 C5 — so it is evidence the checks fired against real input rather
than a hand-written list of things somebody tolerated. Every check in it names **the task
that clears it**, and a test asserts that naming, so a tolerated finding cannot become
anonymous. Tasks 37–40 prune it; phase 9 exits when it is empty.

**Rejected: `@unittest.expectedFailure`.** It would have satisfied both sentences literally
and hidden the findings behind a passing dot. The suite would then have gone red when the
documents were *fixed*, which is precisely backwards.

**Rejected: leaving the suite red through waves 1–3.** Honest, and it would have destroyed
the wave gate — *"both suites green and not smaller"* cannot detect a regression in tasks 37,
38 or 42 if it is already failing for a reason everyone has agreed to ignore. That is rule
7's own warning about a check that cries wolf, applied to the check being built.

**Rejected: an exact-match assertion rather than a subset.** It catches a stale allowance,
which the subset form does not, but it turns every single frontmatter line task 37 adds into
a red suite until the baseline is regenerated — which trains exactly the reflex of
regenerating the baseline to make the suite quiet. The stale-allowance hole is real and is
closed by hand in wave 4, where the baseline is pruned to empty and the emptiness is the
phase-exit gate.

**A non-empty baseline is a temporary state with an owner, and this is the risk to watch.**
If tranche seven closes and that file still has findings in it, the mechanism has become the
thing it was built to prevent. The module docstring says so in those words.

Reversible: yes. Delete the baseline file and change the assertion to `assertEqual([], found)`
once the tree is clean; nothing else depends on it.

---

<a id="dec-69"></a>

## DEC-69 — deleted match rows are logged as ids on stderr, behind `DEBUG_PRINT_KEYS`

**2026-08-01, task 42, closing defect D11.**

**Decided:** `match.py` reads `DEBUG_PRINT_KEYS` — which it read **nowhere** — and prints
the `job_id` of every demoted and every orphaned row to **stderr**, prefixed `[debug]`,
off by default. `prune_orphans` obtains them from `DELETE … RETURNING job_id`; the
demotion path already held the exact list.

**Rejected: writing them to a table** (`job_match_deletions`, or an event row).

**Why a deleted row's id is worth keeping at all.** `job_id` is derived and stable
(`schema.make_job_id`), so it still resolves against `jobs`, `job_facts` and `job_events`
long after the match row is gone. It is the only part of a deleted row that retains
value, and it is what turns *"that weight edit demoted 412 rows"* from an observation
into something reviewable. The rows were already gone by the time anyone read the count,
so there was no answer to *"which ones"* from anywhere.

**Why stderr and not a table.** A table is the better artifact and the wrong trade here:
it needs a schema migration, a retention policy and a pruner, on a stage that runs nightly
over every profile and whose whole design property is that it is free arithmetic.
`job_events` is L2 in the measurement hierarchy (`docs/MEASUREMENT-TRAPS.md`) and writing
pipeline bookkeeping into it would put machine-generated rows in a layer that means *"a
user did something"*. Stderr is where this pipeline already puts log output —
`check_criteria_sections()` and the D10 corrupt-`tech_stack` warning are two functions
away — and it keeps the summary line the watchdog reads on stdout unchanged.

**Why behind the flag.** This is a new output surface on a nightly stage, and a
`--rebuild` can demote thousands of rows; printing them unconditionally would bury the
line anyone actually reads. `.claude/CLAUDE.md` documents `DEBUG_PRINT_KEYS` as the
verbose convention *everywhere*, and `match.py` was simply not part of "everywhere" —
which is why the ids were unrecoverable at **every** verbosity rather than merely off by
default. Verified: `python3 match.py --dry-run` prints byte-identically before and after.

Reversible: yes. Nothing persists and no schema changed; deleting the two call sites
restores the previous behaviour exactly. The table remains available later if the ids ever
need to outlive a terminal — this decision does not foreclose it, it declines to pay for
it now.

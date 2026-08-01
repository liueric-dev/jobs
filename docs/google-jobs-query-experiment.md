---
kind: record
written: 2026-07-28
generator: none
---

# Does Google Jobs yield Pursuit-relevant postings when it is actually asked for them?

**Run:** 2026-07-28, at commit `66c9d18`, from the home connection.
**Budget:** 16 SerpApi searches. **Spent: exactly 16** (`this_month_usage` 137 → 153).
**Writes:** none to production. The sample was loaded into a throwaway
`scratch_*` schema via `backend/evals/scratchdb.py` and dropped.
**Config:** `backend/config/google-queries.json` was **not modified.** The candidate
bank below is a proposal; re-pointing the production bank is task 25's job.

This is a decision-support experiment, not a numbered task. It exists to decide
`docs/tasks/refactor/tranche_four/23-serp-abstraction.md`.

---

## 1. Decision

**Build task 23, sharply descoped.** Google Jobs yields on-target postings at
**6.9% hand-checked precision (9/130)** when asked Pursuit-shaped questions,
against **0% (0/30, and 0/9 on the most favourable slice)** for the same source
under the current software-engineering bank. Nearly half the employers returned
(45.4%) are non-tech or government — the category `docs/pursuit-gate-volume.md:126-129`
found "essentially absent from every configured source." 129 of the 130 rows are
new to the corpus.

What to descope, and why, is §9. The short version: the yield justifies buying more
Google Jobs *capacity*, but the cheapest large capacity is the contributor API
(task 24 — 30 Builders × 250/month), not eight provider adapters, and task 22
already deleted the free unlimited one.

**The single highest-value action this experiment implies is not task 23 at all.**
It is re-pointing the query bank, which is a config edit (task 25) and produced the
entire 12× difference measured here.

---

## 2. The question, and why task 05 could not answer it

`docs/pursuit-gate-volume.md:115` measured `google_jobs` at 142 of 2,975
gate-matching rows — 4.8% — and concluded Google Jobs "is not currently a
meaningful source of this population."

`docs/jobspy-spike.md:186-191` challenged the inference rather than the number:
`backend/config/google-queries.json` holds 32 queries in four buckets (`core_swe`,
`ai_integration`, `bridge_solutions`, `reentry_growth`) and **every one is a
software-engineering title** — `full stack engineer`, `LLM engineer`, `forward
deployed engineer`, `software engineer returnship`. The bank's own `_comment`
(`google-queries.json:2`) says so outright: it is "weighted to Eric's actual
positioning: 5 YOE full-stack SWE."

So 4.8% measured what Google Jobs returns when asked for senior software engineers.
It says nothing about what it returns when asked for an AI Operations Coordinator at
a hospital.

---

## 3. What was run

16 searches, all `location = "New York, NY"`, all `mode = "nyc"`, **no date chip**
— which is `choose_date_chip()`'s never-run-before backfill branch
(`backend/ingest/google-serpapi.py:243-262`), the correct setting for a yield
measurement.

The search itself was issued by importing `serpapi_search()` out of
`backend/ingest/google-serpapi.py:265-284` rather than writing a second one, so
`hl=en`/`gl=us` locale pinning and the `"error" in data` check are identical to the
nightly run. Results were normalised by `google_jobs.normalize_job()`
(`backend/google_jobs.py:45`) and written with `upsert_checked()` — the real ingest
path, so `location_is_nyc`, dedup by `ids.google_source_id()` and description
handling are exactly what a production run would produce.

| bucket | query | results |
|---|---|---|
| archetypes | `AI operations coordinator` | 10 |
| archetypes | `AI implementation analyst` | 10 |
| archetypes | `prompt specialist` | 10 |
| archetypes | `automation associate` | 10 |
| entry_level_ai | `entry level AI specialist` | 10 |
| entry_level_ai | `junior automation specialist` | 10 |
| entry_level_ai | `workflow automation coordinator` | 10 |
| entry_level_ai | `AI operations associate` | 10 |
| industry_anchored | `AI specialist hospital` | **0** |
| industry_anchored | `automation analyst insurance` | 10 |
| industry_anchored | `AI coordinator nonprofit` | 10 |
| industry_anchored | `logistics automation coordinator` | 10 |
| industry_anchored | `AI analyst city government` | **1** |
| industry_anchored | `AI specialist school district` | **0** |
| ops_with_ai | `business process automation analyst` | 10 |
| ops_with_ai | `AI content specialist marketing agency` | 10 |

131 results, 130 unique after dedup (one posting was returned by two queries:
New York Life's *Senior Associate - Workload Automation Engineer*, once as
`New York, NY` and once as `Anywhere`).

**Note for anyone re-running this: SerpApi bills a search that returns nothing.**
`AI specialist hospital` raised `RuntimeError("Google hasn't returned any results
for this query.")` from `google-serpapi.py:283` and the account counter still moved.
An immediate re-issue of the same query was *not* billed — SerpApi serves a cached
repeat free — which is how 16 queries plus one retry came to exactly 16 searches.

---

## 4. The yield

| quantity | value |
|---|---|
| searches | **16** |
| results returned | **131** (130 unique) |
| tier 1 / 2 / 3 under `config/relevance.json` | 27 / 47 / 56 |
| **passing the production gate** (`tier <= max_tier_to_score = 2`) | **74 (56.9%)** |
| matching task 05's AI vocabulary in `description_text` | 98 (75.4%) |
| …also entry-level signalled | 71 (54.6%) |
| …also NYC or remote | 22 (16.9%) |
| AI signal **in the title** | 57 (43.8%) |
| title carrying **both** AI and entry-level signals | 41 (31.5%) |
| `location_is_nyc` TRUE | 47 (36.2%) |
| **hand-checked genuine** | **9 (6.9%)** |
| non-tech employers | 57 (43.8%) |
| government employers | 2 (1.5%) |
| tech / AI product companies | 45 (34.6%) |
| staffing, IT consulting or relist sites | 26 (20.0%) |
| already in the production corpus (same `job_id`) | **1 of 130** |

Tier was not re-derived. `relevance.tier_sql()` (`backend/relevance.py:112-192`) was
imported and run against the scratch table, per CLAUDE.md's "one implementation, two
callers." The AI-vocabulary and entry-level regexes are copied verbatim from
`docs/pursuit-gate-volume.md:42` and `:48`, `\y` throughout.

**Genuine per search: 9/16 = 0.56.** At the free tier's 8 searches/day that projects
to ~4.5 on-target postings/day from this one source — against the ≈3/day that
`docs/pursuit-gate-volume.md:16` calls the whole pipeline's *usable* rate today.
§10 explains why that projection is the most fragile number in this document.

---

## 5. The hand-check

**Criterion**, three parts, all required — the first two are task 05's
(`docs/pursuit-gate-volume.md:182-183`), the third is added because these are live
SERP results rather than corpus rows:

1. The AI/automation vocabulary describes **the work of the role** — not company
   boilerplate, not the employer's name, not a homonym.
2. The role is **plausibly reachable by an entry-level Builder** — no CS degree
   gate, no 5+ YOE, not senior/lead/principal/AVP/director/manager, not a licensed
   profession.
3. It is **takeable from NYC** — five boroughs, PATH-commutable Hudson County, or
   genuinely remote.

**Judged genuine: 9 of 130. Precision 6.9%.**

| id | employer | title | class | location |
|---|---|---|---|---|
| `38d9a64d` | Talon Air | Entry-Level AI Solutions Builder — On-Site | non-tech (aviation) | New York |
| `0a2249e6` | Penn Mutual Life Insurance | IT Analyst — AI & Data Automation for Investments | non-tech (insurer) | New York, NY |
| `e339ae7d` | Genius Agency AI | Content Writer / AI Editor | non-tech (agency) | New York, NY |
| `05ec1966` | Genius Agency AI | Remote AI-Driven Content Writer & Editor | non-tech (agency) | New York, NY |
| `812d4a33` | Meta Viable Solutions | Digital Marketing AI Content Creator Intern | non-tech (marketing) | New York, NY, remote |
| `d8c04183` | Voice AI Space (EliseAI) | People Ops Coordinator — Onboarding & Automation | tech | New York, NY |
| `514dcea4` | Moab | Data & AI Analyst (Operations) | tech | New York, NY |
| `9df77b2b` | Loop | AI Operations Associate | tech | NYC one of three offices |
| `344f5622` | Lucem Health | Remote Clinical AI Implementation Specialist | tech (health AI) | remote |

Talon Air is the bullseye and is worth quoting, because it is the posting the whole
retarget is aimed at and it does not exist anywhere in the current 11,824-row corpus:

> "You don't need years of software engineering experience or a computer science
> degree. If you've built projects using ChatGPT, Codex, Cursor, GitHub Copilot,
> Claude, Replit, Bolt, Lovable, or similar AI tools, we want to hear from you…
> You'll spend most of your time using modern AI development tools to build
> solutions — not writing thousands of lines of code from scratch."

That is a private aviation company — an employer class with no ATS token in
`companies.json` and no presence in any configured source.

### A second, looser count

Eleven further rows are **AI-training gig work** on freelance platforms —
DataAnnotation (×3), Alignerr, Mercor (×2), Prolific, Invisible Agency (×2),
Meridial, Welocalize, plus one Upwork contract literally titled *"AI Implementation
Specialist – Ongoing Help Putting AI to Work Across My Business."* Six of the eleven
gate on domain expertise a Builder will not have (Dutch fluency, a chemistry degree,
financial-institution or politics expertise). The other five are genuinely open to
anyone.

Counting those five, precision is **14/130 = 10.8%**. They are excluded from the
headline because they are contract micro-task work, not employment, and the cohort's
objective is a job. Whether they belong in the product is a real question and not
this experiment's to answer.

### What is *not* in the count, and why

Four postings match all three criteria except geography, and they matter because they
show the role type exists at volume — just not here:

- **Dormont Manufacturing** — *Hybrid AI Operations Associate (Production & Trust)*,
  Atlanta. A manufacturer hiring an AI ops associate to "monitor and support AI-driven
  workflows in production."
- **Olympia Moving and Storage** — *Junior Business Technology & Automation
  Specialist*, Watertown MA. "An early career role for someone who loves helping
  people use technology and wants to grow into automation and workflow improvement."
- **Jasper** — *AI Operations Associate*, Austin. "Run and improve AI-powered
  workflows: evaluate model outputs, refine prompts, and document what works. Pattern
  recognition and judgment matter more than a technical degree."
- **MJH Life Sciences** — *AI-Driven Sales Operations Coordinator*, Cranbury NJ. "Use
  AI tools to draft communications, summarize notes, and automate CRM tasks."

The archetypes in `MASTER-PLAN-pursuit.md` are not hypothetical. They are being
hired for. The constraint is NYC supply, not existence — which is an argument for
task 16's ATS token discovery aimed at NYC non-tech employers, not against it.

---

## 6. The control, and whether the 4.8% comparison is fair

**It is not fair, and it should not be used.** 4.8% is a *share of corpus* — Google
Jobs' slice of the 2,975 rows matching an AI-vocabulary regex, competing against a
greenhouse/ashby pull that ingests entire company boards. This experiment measures a
*yield* — on-target postings per SERP result. A source can have a low share and a
high yield simultaneously, and that is exactly what is happening: `google_jobs` is
901 rows against greenhouse's 7,370 because the ATS pull takes everything and the
Google bank runs 8 queries a night, not because its per-result quality is worse.

So a like-for-like control was measured instead: **the same judge, the same three
criteria, applied to what the current bank actually produced.**

A pinned sample of 30 production `google_jobs` rows, `ORDER BY md5(id) LIMIT 30`,
read-only (ids at the end):

**Genuine: 0 of 30. Precision 0.0%.**

The 30 are **22 software-engineering roles** (DevOps, backend, full-stack, ML,
forward deployed, solutions engineer — including a Senior Principal Engineer at Bank
of America and a Senior Engineering Manager at Asana), **7 relist-spam rows** from
`remote zest jobs`, `remote click jobs` and `vmysmartpros` — three of the six names
already in `company_exclude` (`config/relevance.json:88-95`) — and **1** *AI
Implementation Lead* at an investment bank in Omaha. Nothing entry-level, nothing
NYC non-tech. This is the bank working exactly as designed; it was designed for a
different person.

A second, more generous production slice: **all 9 rows in the entire 901-row
`google_jobs` population whose title carries both an AI signal and an entry-level
signal.** Four are relist spam (`vmysmartpros` ×3, `vacancy global pro`), one is
SynergisticIT (a bootcamp relister), one is DataAnnotation.tech gig work, one is a
Northwell Health *Associate Software Engineer — AI/LLM*, one an agency contract
requiring Azure OpenAI development, one a *Clinical Prompt Engineer* wanting a
clinical background. **Genuine: 0 of 9**, by the same criteria that passed 9 of 130
in the new sample.

| | current bank | Pursuit bank |
|---|---|---|
| rows examined by hand | 39 (30 random + 9 best-case) | 130 (all of them) |
| genuine | **0** | **9** |
| population with title AI+entry signal | 9 / 901 = **1.0%** | 41 / 130 = **31.5%** |
| non-tech / government employers | — | 45.4% |

**On significance, stated honestly.** The hand-check contrast (9/130 vs 0/39) gives
a one-sided Fisher exact **p = 0.088**. That is suggestive, not conclusive at the 5%
level, and it is limited by the control's size, not the treatment's. The
population-level proxy — titles carrying both signals, 41/130 vs 9/901 — is
**p < 10⁻¹²**, and the proxy is measured on 901 control rows rather than 39. The two
disagree about certainty and agree about direction. Note also that the proxy
*overstates* on both sides (31.5% proxy vs 6.9% hand-checked here; 1.0% proxy vs 0%
hand-checked there) — the same ~4-5× inflation task 05 warned about — so it is safe
as a comparison and unsafe as an absolute.

---

## 7. What generated the junk — and it is a different failure mode from task 05's

Task 05's dominant junk generator was **company boilerplate**: an employer with an AI
blurb in its "About us" matching on every requisition it has
(`docs/pursuit-gate-volume.md:201-209`). That mechanism appears here, but it is small
— Gong's *Director, Content Marketing* and IBM's *Process Analyst SubK Conversion*
are the clear cases, and both are excluded on seniority anyway. Live SERP results are
title-ranked by Google, so the boilerplate path barely fires.

Four different mechanisms dominate instead.

**1. "Automation" without AI — 43 rows, a third of the sample.** Their titles carry
`automat*` and no AI token at all: test automation (QA/Tosca/UAT), industrial
control systems, warehouse and materials-handling automation, and RPA/SAP process
automation. All legitimately "automation"; none is AI-adjacent work in the
`ai_involvement = uses_ai_tools` sense. Three further rows match on the employer's
**name** rather than the title: **`Robotics Prcocess Automation, LLC`** is a New
Jersey logistics company posting *Logistics & Supply Chain Coordinator* twice, and
**`Podium Automation`** is an industrial control-panel manufacturer posting a
*Supply Chain Operations Lead*.

**2. Federal "Office Automation" — 2 rows, and it is a trap worth naming.** *Legal
Assistant (Office Automation)* at the U.S. Attorneys' Offices and *Court IT
Automation Specialist* at United States Courts. "Office automation" is US federal
HR vocabulary meaning *can operate a word processor*. Both are entry-level government
postings in the NYC metro — precisely the profile the cohort wants — and both are
false positives. Any government-source ingest (task 15, USAJobs) will meet this at
scale.

**3. The company is called "Prompt."** `Prompt` is a healthcare revenue-cycle
company; the query `prompt specialist` returned its *AR Specialist* posting. Same
class as task 05's `gemini`-the-crypto-exchange finding
(`docs/pursuit-gate-volume.md:211-213`).

**4. Titles that say "Specialist" and bodies that say "Architect."** The clearest
case: Bright Vision Technologies' **`LLM Prompt Specialist`** — the title is a
perfect archetype match and passes every entry-level title signal. The body reads
"Prompt Engineering *Architect*… Six or more years of software engineering
experience… Bachelor's or Master's in Computer Science… $100,000–$150,000." This is
the strongest single argument for task 10's description-first gate: **the entry-level
signal is in the title and the disqualifier is in the body**, and no title regex can
see it.

Two further hygiene findings:

**Google will report a fabricated location.** `Braun Management — Junior Automation
Specialist` is returned as `New York, NY`; the description's first line reads
"Junior Automation Specialist Jobs in Johannesburg, Gauteng, South Africa."
`Hollybank Trustees` is returned as `Belfast, ME` for a role in Belfast, Northern
Ireland; `Jobgether` as `Finland, MN` and `Belgium, WI` for roles in Finland and
Belgium. All four are `location_is_nyc`-eligible or -adjacent on metadata that the
body contradicts. Four in 130 is a 3% location-lie rate on a field the gate trusts.

**`location` is a ranking hint, not a filter.** Every query asked for `New York, NY`;
**47 of 130 results (36.2%) are actually NYC.** The rest span Ohio, Arizona,
Oklahoma, California and Northern Ireland. Any capacity planning that assumes one
search yields ten NYC postings is wrong by 2.8×.

---

## 8. Four defects this experiment found in code outside its own scope

Recorded here because each is cheap, each is load-bearing for a task already queued,
and none was fixed (this is a measurement).

**8.1 — Task 05's AI vocabulary has no bare `ai` token, and it costs a third of the
recall.** The regex at `docs/pursuit-gate-volume.md:42` matches `ai tool`,
`ai-powered`, `generative ai` and `\ygen ai\y`, but **not** `\yai\y`, `ai-driven`,
`ai-enabled` or `ai-assisted`. Three of the nine genuine postings fail it outright:
Lucem Health ("clinical AI"), Penn Mutual ("AI-driven efficiency improvements") and
Meta Viable ("AI generation for content creation"). Task 10 should not lift that
regex as-is.

**8.2 — The entry-level regex has no `\yintern\y`.** `docs/pursuit-gate-volume.md:48`
lists ten signals; `intern`/`internship` is not among them, and it drops Meta Viable
Solutions' *Digital Marketing AI Content Creator Intern*. Both Databricks postings
that task 05 judged genuine were internships, so this is a live gap in that
measurement too.

**8.3 — `normalize_job()` ignores `detected_extensions.work_from_home`.**
`backend/google_jobs.py:98-99` derives `location_is_remote` from
`text.REMOTE_PATTERN` over the location string. SerpApi does not put remoteness in
that string — it sets `location = "Anywhere"` and `detected_extensions.work_from_home
= true`. `REMOTE_PATTERN` is `\bremote\b`, so **`"Anywhere"` matches neither
`location_is_nyc` nor `location_is_remote`**, and all 7 genuinely remote postings in
this sample land at tier 2 with both flags FALSE. Every one of them would be a tier-1
row if the field were read. One line, in the one place that owns the Google Jobs
record shape.

**8.4 — 45% of results arrive as a paraphrase, not a posting.** Google's `via` field
credits an aggregator on 59 of 130 rows (BeBee 29, JobLeads 11, Talents By Vaia 8,
Jobilize 4, Learn4Good 2, Jobrapido 2, and one each from Recruit.net, ZA Hired and
JobTarget). Those rows carry a **median 530-character third-person summary**
("Arch Insurance Group Inc. is seeking an Accounting Professional in Jersey City, NJ.
This role supports…"), against a **median 4,838 characters** for everything else — a
9× difference. `config/relevance.json:99` deliberately does *not* exclude BeBee and
that call is correct: `company_name` holds the real employer. But `extract.py` is
being handed a paraphrase for nearly half of this source, and `job_facts` extracted
from 530 characters of summary is not comparable to facts extracted from a 5,000-character
posting. This is a `FACTS_VERSION`/task 11 concern and a candidate `_comment` in
whatever config records description-quality thresholds.

---

## 9. What this means for task 23

### The existing gate is the wrong filter for this source

Measured on the 130-row sample, with the 9 hand-checked rows as ground truth:

| gate | rows kept | genuine kept | precision | recall |
|---|---|---|---|---|
| no gate | 130 | 9 | 6.9% | 100% |
| **production tier gate (`tier <= 2`)** | **74** | **8** | **10.8%** | **88.9%** |
| task 05 AI vocabulary (description) | 98 | 6 | 6.1% | 66.7% |
| …+ entry-level signal | 71 | 4 | 5.6% | 44.4% |
| …+ NYC or remote | 22 | 3 | 13.6% | **33.3%** |
| title carries AI + entry-level | 41 | 2 | 4.9% | 22.2% |

**The production tier gate is already the best filter available for this source** —
it keeps 8 of 9 and nearly doubles precision. The widened AI-vocabulary gate that
task 05 measured is *worse on both axes* here, and the "AI + entry + location"
composite throws away two-thirds of the genuine postings (two on the `work_from_home`
defect in §8.3, one on the missing `\yai\y` token in §8.1). The one genuine row the
production gate drops is *People Ops Coordinator — Onboarding & Automation*, which
falls to tier 3 because no `title_include` term matches — which is exactly the case
task 10 exists to catch.

Practical consequence for 23: **the router does not need a smarter filter bolted onto
it.** Ship the results into the existing pipeline.

### Descope

Task 23's Definition of done (`23-serp-abstraction.md:108-121`) is a `serp/` package,
eight provider adapters, a normalizer, a quota ledger with credit multipliers, a
router, a cache, volume alerting and a JobSpy canary.

**Keep:**

- **One interface + `normalize.py` into `lib/`'s frozen record shape.** Non-negotiable
  regardless of provider count — `0c3ae51` de-duplicated that shape deliberately and
  CLAUDE.md forbids a second definition.
- **`SerpResult` carrying provider, credits and cache-hit**, with the evals harness's
  rule enforced where the number is printed (`23-serp-abstraction.md:52-53`).
- **The quota ledger.** It earns itself on SerpApi alone: this run proved a
  zero-result search is billed, which a request counter would miss.
- **The cache.** Task 25's argument (`25-search-queries.md:12-20`) is independent of
  provider count and is the strongest single lever on effective capacity.
- **Volume-based alerting.** `docs/jobspy-spike.md:206-208` already argues this and
  the argument is unchanged. Note the specific shape needed here: *zero results is a
  legitimate outcome* — `AI specialist hospital` and `AI specialist school district`
  both returned zero for real. Alert on aggregate nightly volume, never per query.

**Cut:**

- **The JobSpy adapter, the JobSpy canary, and router step 2.** Task 22 settled it.
- **Six of the eight adapters.** Apify, ScrapingBee, Scrapingdog, JSearch and the
  one-time trial tier. `SOURCING-STRATEGY.md:256-262` already says ScraperAPI bills 25
  credits per Google request and ZenRows the same; a 1,000-credit tier is 40 real
  searches. Building an adapter for 40 searches is not worth a file.
- **Three-provider parity as the acceptance criterion**, if it forces a third
  integration for its own sake. Scrappa (500/month, renewable, advertises a
  `google_jobs` engine) is the only remaining candidate worth its adapter.

**Reprioritise.** `23-serp-abstraction.md:3` has 23 blocking 24 and 25. The evidence
inverts that ordering in value terms:

- **Task 25 (query bank) is where the entire result of this experiment lives.** It is
  a config edit, it produced a 12× density difference, and it depends on 23 only for
  the cache. Do it first, standalone, against the existing SerpApi integration.
- **Task 24 (contributor API) is the real capacity unlock.** Thirty Builders × 250
  searches/month is 7,500/month. Multiplexing every free tier in
  `SOURCING-STRATEGY.md:26-47` reaches perhaps 950. The contributor path is ~8× all
  eight providers combined, it is already written and tested
  (`24-revive-contributor-api.md:5`), and at 0.56 genuine postings per search it is
  worth ~4,200 on-target postings a month. Task 23 lists `contributor.py` as one
  adapter among eight; it is the product.

---

## 10. Confidence, and what would change the answer

**High confidence** that the current bank yields ~nothing for this cohort. That rests
on 901 production rows, not on 16 searches: 9 of 901 titles carry both signals and
none of the 9 survives a hand-check.

**Moderate confidence** in 6.9% as the Pursuit bank's precision. n=130 gives a 95%
interval of roughly **3.7%–12.7%**, and the low end still beats the control. One
judge, one sitting; no second rater, so there is no inter-rater floor beside this
number — the same objection CLAUDE.md raises about `deepseek-v4-flash` at 76%
self-agreement applies to a human judge and is not answered here.

**Low confidence in 0.56 genuine/search as a *sustained* rate, and this is the
weakest link in the argument.** All 16 queries were first runs with no date chip —
`choose_date_chip()`'s deliberate backfill branch. Google's default ranking is
relevance-based, so re-running the same query tomorrow with `chips=date_posted:today`
returns the *new* slice of a list that has already been harvested, which is much
smaller. The production stats table agrees in shape: `google_jobs_query_stats` shows
41 runs producing 272 new rows (2026-07-26 → 2026-07-28), but it holds only 32
distinct slugs and **no slug has run more than twice**, so it too is measuring
first-run yield. **Nobody has measured the steady-state daily rate
for any Google Jobs query, on either bank.** A 16-query bank rerun nightly will not
deliver 4.5 genuine/day indefinitely; the bank has to keep growing, which is precisely
what task 25's `search_queries` table is for.

**What would change the decision:**

1. **A steady-state re-measurement.** Re-run these same 16 queries in two weeks with
   `chips=date_posted:week` and count new rows. If first-run yield collapses by more
   than ~5×, Google Jobs is a backfill source rather than a nightly one, and task 23's
   capacity argument weakens accordingly. This costs 16 searches and is the single
   highest-value follow-up.
2. **A second hand-rater on the same 130 rows.** The `location_raw` lies (§7) and the
   title/body seniority mismatch (§7.4) mean two careful raters could plausibly differ
   by ±3 rows, which spans 4.6%–9.2%.
3. **Task 16 landing NYC non-tech ATS tokens.** If a hospital-system and insurer ATS
   pull delivers the same archetypes at higher volume and full description quality,
   Google Jobs becomes a discovery channel for employers rather than a posting source
   — and the right build is smaller still.
4. **Scrappa's `google_jobs` engine failing verification.** Then SerpApi + contributor
   is the whole provider set and the "abstraction" is one interface over two callers,
   which may not warrant a package at all.

---

## 11. The proposed query set

**A proposal. `backend/config/google-queries.json` was not modified.** Structured to
drop into the existing file's shape (`daily_budget` per bucket, `slug`/`query`/
`location`/`mode` per query) so task 25 can take it directly, with `_comment` fields
in the existing style per CLAUDE.md.

```json
{
  "_comment": "Pursuit-shaped candidate bank, drafted 2026-07-28 by docs/google-jobs-query-experiment.md. All 16 were run once against SerpApi with no date chip; per-query yield is recorded below. Aimed at the cohort's actual floor -- entry-level, AI-adjacent, all industries, NYC -- not at software engineering titles. daily_budgets are UNSET here on purpose: they depend on whether the contributor API (task 24) is live, and setting them is task 25's decision, not this experiment's.",
  "buckets": {
    "archetypes": {
      "_comment": "The four archetypes named across the task tree. Asked as bare titles here and industry-anchored separately, so the two effects can be told apart. Result: bare titles outperformed industry anchoring 4:1.",
      "queries": [
        {"slug": "arch-ai-ops-coordinator",   "query": "AI operations coordinator",  "location": "New York, NY", "mode": "nyc"},
        {"slug": "arch-ai-impl-analyst",      "query": "AI implementation analyst",  "location": "New York, NY", "mode": "nyc"},
        {"slug": "arch-prompt-specialist",    "query": "prompt specialist",          "location": "New York, NY", "mode": "nyc"},
        {"slug": "arch-automation-associate", "query": "automation associate",       "location": "New York, NY", "mode": "nyc"}
      ]
    },
    "entry_level_ai": {
      "_comment": "Entry-level framing carried in the query text, industry-agnostic. Tests whether Google's ranking surfaces junior AI-adjacent work without an industry hint. It does, but 'specialist' and 'junior' in a title do not survive contact with the body -- see section 7.4.",
      "queries": [
        {"slug": "entry-ai-specialist",             "query": "entry level AI specialist",     "location": "New York, NY", "mode": "nyc"},
        {"slug": "entry-junior-automation",         "query": "junior automation specialist",  "location": "New York, NY", "mode": "nyc"},
        {"slug": "entry-workflow-automation-coord", "query": "workflow automation coordinator","location": "New York, NY", "mode": "nyc"},
        {"slug": "entry-ai-operations-associate",   "query": "AI operations associate",       "location": "New York, NY", "mode": "nyc"}
      ]
    },
    "industry_anchored": {
      "_comment": "REJECTED AS A BUCKET, kept here as the record of why. Appending an industry to a title collapses the result set rather than retargeting it: 'AI specialist hospital' and 'AI specialist school district' returned ZERO (and SerpApi bills a zero-result search), 'AI analyst city government' returned ONE. The three that did return ten produced one genuine posting between them. Google Jobs matches on the posting's own title text, so an industry word that does not appear in job titles simply eliminates matches. Anchor on industry via the ATS token list (task 16), not via the query.",
      "queries": [
        {"slug": "ind-ai-hospital",          "query": "AI specialist hospital",           "location": "New York, NY", "mode": "nyc"},
        {"slug": "ind-automation-insurance", "query": "automation analyst insurance",     "location": "New York, NY", "mode": "nyc"},
        {"slug": "ind-ai-nonprofit",         "query": "AI coordinator nonprofit",         "location": "New York, NY", "mode": "nyc"},
        {"slug": "ind-logistics-automation", "query": "logistics automation coordinator", "location": "New York, NY", "mode": "nyc"},
        {"slug": "ind-ai-government",        "query": "AI analyst city government",       "location": "New York, NY", "mode": "nyc"},
        {"slug": "ind-ai-education",         "query": "AI specialist school district",    "location": "New York, NY", "mode": "nyc"}
      ]
    },
    "ops_with_ai": {
      "_comment": "Ordinary operations and content titles where AI is the tool rather than the head noun. Best bucket in the experiment: 'AI content specialist marketing agency' alone produced 3 of the 9 genuine postings, all at NYC agencies. This is the bucket to expand -- the cohort's reachable roles are AI-using ops and content jobs, not jobs with AI in the title.",
      "queries": [
        {"slug": "ops-bpa-analyst",       "query": "business process automation analyst",   "location": "New York, NY", "mode": "nyc"},
        {"slug": "ops-ai-content-agency", "query": "AI content specialist marketing agency","location": "New York, NY", "mode": "nyc"}
      ]
    }
  }
}
```

### Which queries earned their search, and which did not

| query | results | gate | genuine | gig |
|---|---|---|---|---|
| `AI content specialist marketing agency` | 10 | 8 | **3** | 1 |
| `AI implementation analyst` | 10 | 9 | **2** | 1 |
| `AI operations coordinator` | 10 | 6 | **1** | 0 |
| `entry level AI specialist` | 10 | 9 | **1** | 1 |
| `AI operations associate` | 10 | 7 | **1** | 0 |
| `automation analyst insurance` | 10 | 6 | **1** | 0 |
| `prompt specialist` | 10 | 9 | 0 | 2 |
| `automation associate` | 10 | 4 | 0 | 0 |
| `junior automation specialist` | 10 | 1 | 0 | 0 |
| `workflow automation coordinator` | 10 | 2 | 0 | 0 |
| `AI coordinator nonprofit` | 10 | 8 | 0 | 0 |
| `logistics automation coordinator` | 10 | 1 | 0 | 0 |
| `business process automation analyst` | 10 | 4 | 0 | 0 |
| `AI analyst city government` | 1 | 1 | 0 | 0 |
| `AI specialist hospital` | **0** | — | 0 | 0 |
| `AI specialist school district` | **0** | — | 0 | 0 |

Six of sixteen queries produced every genuine posting. Three lessons for task 25:

**Keep AI as the head noun of the title, not the industry.** The three highest-yield
queries all name an AI-shaped *role*. The three lowest-yield all name an *industry*.

**`automation` alone is a dead term for this cohort.** `automation associate`,
`junior automation specialist`, `workflow automation coordinator`,
`logistics automation coordinator` and `business process automation analyst` —
five searches, 50 results, **zero genuine**, and the lowest gate-pass rates in the
set (1, 1, 2, 4, 4 of 10). They return QA test automation, industrial controls and
warehouse robotics. This is the same term that carries 1,200 of task 05's 2,975
matches (`docs/pursuit-gate-volume.md:79`) and it is doing the same damage from the
other end of the pipeline.

**Do not anchor on industry in the query text.** `hospital` and `school district`
returned literally nothing and were billed for it. Google matches the posting's own
title; hospitals do not put "hospital" in job titles. Industry targeting belongs in
the ATS token list (task 16), which is where the archetype postings found in Atlanta,
Watertown and Cranbury would have come from.

---

## 12. Every decision made, and whether it is reversible

| decision | chose | rejected | why | reversible |
|---|---|---|---|---|
| Query count | 16 distinct, one run each | 8 queries × 2 runs for a repeat-rate estimate | Breadth answers the yield question; repeat-rate is a separate follow-up (§10.1) | yes |
| Date chip | none (backfill branch) | `chips=date_posted:week` | Measures the query's whole reachable pool, not one day of it. Costs comparability with steady state — stated as the weakest number in §10 | yes |
| Location | `New York, NY` on all 16 | mixing in `United States` remote queries | Cohort is NYC; remote arrives anyway (7 rows) | yes |
| Persistence | scratch schema via `scratchdb.py` | in-memory only | `tier_sql()` returns SQL; evaluating it needs Postgres. Scratch schema is dropped on exit | n/a |
| Tier predicate | imported `relevance.tier_sql()` | re-deriving in Python | CLAUDE.md: one implementation, two callers | n/a |
| Search call | imported `serpapi_search()` from the ingest script | writing a new client | Brief said do not rewrite it; also inherits `hl`/`gl` pinning | n/a |
| Hand-check scope | all 130 | task 05's `ORDER BY md5(id) LIMIT 30` | 130 is small enough to check exhaustively, and removes sampling error from the treatment arm | n/a |
| Gig work | excluded from headline, counted separately at 10.8% | folding it in silently | Contract micro-task work is not the cohort's objective; the judgment is contestable so both numbers are given | yes |
| Location judgment | five boroughs + PATH-commutable NJ + genuine remote | strict `location_is_nyc` | The gate's own flags are wrong for this source (§8.3); using them would have scored the defect as a yield result | yes |
| Control | 30 pinned production rows + all 9 best-case rows | reusing task 05's n=30 | Task 05's sample is 68% greenhouse; it is not a Google Jobs control | n/a |
| Zero-result query | recorded as a real zero, counted against budget | retrying with a reworded query | The zero is the finding, and it was billed either way | n/a |
| The four §8 defects | recorded, not fixed | fixing them | This is a measurement. CLAUDE.md: do not tune anything | yes |

---

## 13. Conduct

- **16 SerpApi searches. Budget was 16.** Account moved 137 → 153 (`this_month_usage`),
  verified before and after against `serpapi.com/account.json`. 97 searches remain on
  the 250/month free tier.
- **No writes to production.** Every production query was a `SELECT`. The sample lives
  in a `scratch_<8 hex>` schema created and dropped by `backend/evals/scratchdb.py`,
  whose `drop()` refuses any name not matching `^scratch_[0-9a-f]{8}$`
  (`scratchdb.py:106-118`).
- **`backend/config/google-queries.json` unmodified.** `git status` shows it untracked
  by this work. The bank in §11 is a proposal inside this document.
- **LinkedIn was never queried.** Every call went to SerpApi's `google_jobs` engine.
  Google's `via` field credits LinkedIn as the origin of 25 postings — that is Google
  reporting where it found them, not this experiment fetching from LinkedIn.
- **No JobSpy.** Task 22 established it returns nothing.
- **No production code changed, no dependency added, no test touched.** The scripts
  live in the session scratchpad; this document is the only artifact in the repo.
- Files owned by concurrent agents were not touched. `backend/evals/scratchdb.py` was
  read and imported, never modified.

---

## 14. Pinned samples

**The Pursuit sample** is reproducible from §11 plus §3's parameters, but Google's
ranking rotates, so it will not reproduce byte-for-byte. The 9 genuine `job_id`s, as
computed by `schema.make_job_id()` — an L0 set under CLAUDE.md; never train on it,
never recycle it:

```
0a2249e6…  05ec1966…  344f5622…  38d9a64d…  514dcea4…
812d4a33…  9df77b2b…  d8c04183…  e339ae7d…
```

**The production control**, `ORDER BY md5(id) LIMIT 30` over `platform='google_jobs'`,
sorted for the record:

```
0ada61a6  1bd30dca  24b37a66  29a631b5  33784adb
386f0ddf  4021d701  52068d8d  5e3d03b1  63e1cc22
795b9e79  7c79a2ca  80416ef0  90b01998  90fe729b
910a4fa8  9a587fa6  9fe1ec6d  a46b152a  a8089652
b8c91519  baa17f40  caa8b22f  d9761615  e0222877
e7cb63d8  ea03fb65  ee6216ca  f3651347  feed098a
```

---
kind: record
written: 2026-07-28
generator: none
---

# Deriving the archetype superset and the `role_track` vocabulary

**Task:** `docs/tasks/refactor/tranche_two/11-archetype-superset-role-track.md`, sections 1 and 2.
**Derived:** 2026-07-28, at commit `37af79e`, against the live database.
**Method:** read-only SQL plus pure-Python TF-IDF. No LLM calls, nothing extracted, nothing tuned.
**Tool:** `backend/tools/derive-role-tracks.py`. Every count, percentage and vocabulary
decision below is printed by it; re-derive with `python3 backend/tools/derive-role-tracks.py`
(clusters need `--tracks`, which is on by default). The reclaim totals and the token
frequencies are in its **TOTAL EFFECT** section. What is *not* machine-derived, and is
editorial judgement: the names given to the clusters, which clusters are grouped into which
`role_track`, and the recommend/drop calls — the last of these is at least recorded in the
tool, as the third element of `CANDIDATES`.

This is a hand-written rationale document. It is not generated and carries no
`script:`/`commit:`/`generated:` frontmatter; see CLAUDE.md's two-kinds-of-docs rule.

---

## Headline

**The `other` bucket is mostly a *tech* vocabulary gap, not an ops one.** The task file's
framing — "an AI operations role at an insurance company extracts as `other`" — describes a
real hole, but not the one the data is full of. Of the 427 `other` rows, **all seven** ops
candidates the task proposes reclaim **55 (12.9%)** — the five of them worth keeping reclaim
**54 (12.6%)** — while nine tech values the current twelve simply lack reclaim **203
(47.5%)**. The token `engineer` occurs **240** times across the 427 `other` titles.

All reclaim figures in this document are **distinct-row unions, not sums of the
per-candidate table**: the probe patterns overlap and `role_archetype` is single-valued, so
adding the columns would double-count the postings hardest to classify. The tool prints
both, and labels the unions as such.

> **Superseded as a description of the CURRENT vocabulary, 2026-07-31 — and correct
> when taken.** Every figure in this Headline, and in *(a) The archetype superset* below,
> is over the **427 `other` rows at `facts_version = 2`**, which was the current version
> on 2026-07-28. The tool that produced them had **no version filter at all** (DEC-65), so
> re-running it after task 12's bump kept answering a question about the twelve-value
> vocabulary. At `facts_version = 3` the nine tech values reclaim **9 of 294**, not 203 of
> 427. The tech gap was real and is largely closed; what is left is a different bucket.
> See § *The commercial gap in `ARCHETYPE`, and the one value proposed for it*.

**Two of the seven proposed candidates are not supported and are dropped**
(`automation_specialist`, `data_coordination`). Together they would reclaim **1** row of 427.

**`ai_operations` — the value the whole task is motivated by — has almost no mass in this
corpus: 5 cohort postings across 3 employers.** It is recommended anyway, for reasons given
below, but it is the value most at risk of being aspirational rather than derived, and
re-running this tool after Phase 3 is the check that decides it.

---

## The corpus, and exactly how it was selected

| | |
|---|---|
| **cohort** | **863** open postings at relevance tier ≤ 2 under the `pursuit` profile, across **142** employers |
| **other** | **427** `job_facts` rows with `role_archetype = 'other'` (8.0% of 5,328 extracted rows) |

The cohort is selected by `pursuit`'s *own* `relevance_json` via
`relevance.for_profile()` (`relevance.py:100`), not by the shared `config/relevance.json`.
Not `ORDER BY first_seen DESC` — CLAUDE.md forbids it, and it would have skewed the
selection to clean ATS postings.

**`pursuit` is `active=False`.** `extract.py` and `match.py` only see active profiles
(`profiles.load_active`), so only 284 of the 863 have a `job_facts` row at all. The cohort
analysis therefore runs off `title` and `description_text` and **not** off extracted facts.
That is a constraint, not a choice.

The two populations are analysed separately because the superset serves both. `job_facts` is
shared and extraction runs once per posting ever, so per-vertical archetype vocabularies
would break one of those two properties (task file lines 19–26). One vocabulary, and
`criteria.json` decides what each value is worth per profile.

---

## Method, and the two things that were wrong before they were right

### Near-duplicate blocks: collapse on `(company, normalized title)`, never on the description

One employer posting one role many times is not a cluster. This corpus contains a
**54-posting block from Sailor Health** — one telehealth clinician role, duplicated once per
US state — which is easily large enough to manufacture a whole track by itself.

The first fix attempted was a description fingerprint, and it was badly wrong. **The
employer boilerplate lives at the head of the description**, so fingerprinting it collapsed
Harvey's 40 postings — spanning **25 distinct titles**: Applied Legal Researcher, IT
Operations Analyst, Strategy Associate, Deal Operations Analyst, Innovation Product Manager
— into a single "duplicate" block. Hashing the *full* description does not work either:
Sailor Health's 54 postings are all byte-distinct, because the state name appears in the
body too.

What works is `(company_name, normalized title)` with geography and seniority stripped
(`derive-role-tracks.py`, `normalized_title`). It collapses **213 of 863 postings (24.7%)
across 78 blocks**, leaving **650 representatives** for clustering. The largest blocks:

| n | employer | role |
|---|---|---|
| 40 | Sailor Health | Remote Clinical Psychologist – Older Adults |
| 17 | Databricks | Lakebase Sales Specialist |
| 12 | Toast | Bilingual Hybrid Development Representative |
| 11 | Databricks | Solutions Architect (Pre-sales) |
| 10 | Samsara | Specialist Seller, Mid-Market |
| 7 | MongoDB | Technical Services Engineer |

### Clustering reads titles only, because descriptions recover employers

Clustering title + description at **any** description weight rebuilds the *company list*
rather than a role taxonomy. The largest clusters came back with top terms
`interpretable, steerable, beneficial` (Anthropic's mission page), `gdp, economy, staggering`
(Stripe's), `harmony, work-life` (Datadog's). A job description is mostly employer copy with
a little role in it, and TF-IDF faithfully finds the majority signal.

Scored by the fraction of clusters spanning ≥ 4 distinct employers — an employer-specific
cluster is an artifact; a role family is not:

| vectoriser | clusters n≥5 | span ≥4 employers | postings covered |
|---|---|---|---|
| **title only** | 36 | **34 (94%)** | 614 |
| title ×4 + description | 56 | 17 (30%) | 160 |
| description-heavy | 45 | 16 (36%) | 188 |

These three arms were swept with the vocabulary floor at 3 employers and the cluster-spread
criterion held at 4. The tool couples those into one `--min-employers`, so **a default run
does not print these numbers**: at the shipped default of 4, title-only reports 41 clusters,
25 at n≥5, 24 spanning ≥4 employers, 620 representatives. `--min-employers 3` reproduces the
46 / 36 of the sweep. Recorded rather than quietly restated, because the comparison is the
whole justification for excluding descriptions and it was run before the default was chosen.

So descriptions are dropped from the vector entirely. A cross-employer document-frequency
floor (a term must appear under ≥ 4 distinct employers) removes what remains — product names
like `lakebase`, and the residue of the Sailor Health block (`psychologist`, `psyd`,
`older`, `adults`). 16 terms dropped; 88 survive.

Clustering is average-link agglomerative over sparse cosine similarity, stopping at 0.10.
Stdlib only — `backend/requirements.txt` keeps `psycopg` as the sole third-party dependency.

**Limit worth stating: the cluster tail is not trustworthy.** Titles are ~5 tokens, so below
roughly n=8 clusters form on incidental shared words — a Site Reliability Engineer and a
Pharmacy Technician sharing `technician, site`. The head was named; the tail was not.

---

## (a) The archetype superset

The existing tuple is twelve all-software values at `backend/extract.py:191`.
`config/criteria.json` prices `other` at **0** — the task file's claim that it is "worth
exactly 0, identical to a missing value" is **correct as written**, verified against the
`archetypes` map.

One thing has changed under the task file since it was written: `match.py:183-191` now
charges an archetype the extractor named but the profile does not price at the *unknown*
rate rather than a silent zero. So adding values here without adding weights to a profile's
`archetypes` map is now visible in `match_reasons` as `archetype:<value>:unpriced`, not
silently free.

Counts below are **upper bounds** — the probe patterns overlap and `role_archetype` is
single-valued, so a posting matching three candidates is counted by all three. `dedup` is
after near-duplicate collapsing; `emp` is distinct employers. **Read `emp` first**: a
candidate whose mass sits at one employer is that employer's hiring spree.

### Recommended — the ops values (5 of the 7 proposed)

| value | cohort raw/dedup/emp | other raw/dedup/emp | evidence |
|---|---|---|---|
| `support_ops` | 60 / 44 / **22** | 17 / 14 / 10 | Strongest of the seven. IT Support Specialist, Technical Support Engineer, Product Support Specialist, Partner Support Specialist, Billing Support Specialist. |
| `marketing_ops` | 52 / 44 / **29** | 24 / 24 / 15 | Widest employer spread of any candidate. Field/Growth/Product Marketing Manager, Brand Partnership Specialist, Digital Media Associate. |
| `implementation_analyst` | 49 / 37 / **22** | 5 / 4 / 4 | Coherent family on inspection: AI Implementation Specialist, Implementation Analyst, Solutions Consultant (Mid-Market/Commercial/Enterprise), Technical Account Manager, Provider Onboarding Specialist. |
| `admin_ops` | 19 / 18 / **15** | 0 / 0 / 0 | Modest but genuinely distributed — 15 employers for 19 postings, no concentration. People Operations Coordinator, Administrative Business Partner, Early Talent Program Coordinator, Personal Assistant. |
| `ai_operations` | 5 / 5 / **3** | 10 / 10 / 8 | **Thin. See the caveat below.** AI Enablement Manager, AI Operations Specialist, AI Deployment Manager ×3; in `other`, Product Operations Manager AI & Systems, Program Manager Talent & AI Enablement, Sales & AI Enablement Lead. |

**The `ai_operations` caveat, stated plainly.** **15 distinct postings across 9 distinct
employers**, taking both populations together — fewer employers than the 3 + 8 in the table
suggests, because two employers appear in both. And a few of the `other` matches are
coincidental co-occurrence of "AI" and "operations" rather than the role
(`Datacenter Networking Technician, AI Compute`), so 15 is itself an upper bound. This
corpus does not contain the role the task file opens with. That is consistent with the run's
existing headline finding — `HANDOFF.md`: of 329 Workday postings from four NYC employers,
*zero* have any AI vocabulary in the title; "these employers are not posting these roles."

It is recommended regardless, on one ground rather than two: it is the value whose *absence*
would be actively misleading, since `other` priced at 0 is exactly the failure the task
exists to fix. The second ground originally given here — that its employer spread was
respectable — **does not survive checking**. 9 employers is middling, not good: `admin_ops`
reaches 15 on 19 postings and `marketing_ops` 29 on 52. This is the weakest of the 14 by
some margin, and the first thing to re-check after Phase 3.

### Dropped — the 2 of 7 the corpus does not support

| value | cohort raw/dedup/emp | other | why dropped |
|---|---|---|---|
| `data_coordination` | 9 / 9 / **2** | 0 | **8 of the 9 are Cohere** "Data Annotation Specialist". One employer, one role — precisely the near-duplicate trap this analysis is built to catch. Two employers is not a vocabulary value. |
| `automation_specialist` | 5 / 5 / 5 | 1 / 1 / 1 | Spread is fine, mass is not: 5 cohort postings, 1 `other` row. Nothing here to name. The genuine automation work in this corpus already lands in `implementation_analyst` and `business_systems`. |

Together they reclaim **1** row of the 427. Per the task file's own standard — values must be
"grounded in what the corpus actually contains, not in imagination" — they are not carried.

### Recommended — the tech values, which the task file does not propose

The superset serves both populations (task file lines 19–26), and this is where the `other`
mass actually is. `other` breaks down by title token as **engineer 240, systems 42,
infrastructure 29, architect 17, quality 16, mechanical 15**.

Those are occurrence counts under the tool's own tokenizer — `words()`, built on `_WORD` at
`derive-role-tracks.py:139`, lowercased, stopwords and ≤2-character tokens removed — printed
by the TOTAL EFFECT section. Worth stating because it is the kind of number two people
measure differently and both believe: these figures are identical under a naive `\bword\b`
regex, so the tokenizer is not doing anything surprising here. What it *does* do is drop
`ai` (**52** occurrences) along with `ml` (11) and `qa` (8) via the length rule — the single
most important token in this project. The tool now counts and prints those separately rather
than letting the floor hide them.

| value | other raw/dedup/emp | cohort | evidence |
|---|---|---|---|
| `hardware_embedded` | 55 / 50 / **11** | 6 / 6 / 6 | Largest single reclaim. Data Center Design Engineer (Electrical), Mechanical Engineer Systems Integration, RF Hardware Systems Engineer, Electrical Engineer Robotics. |
| `infrastructure_compute` | 42 / 41 / **14** | 8 / 8 / 8 | Network Engineer II, Data Center Infrastructure Electrical Engineer, Site Reliability Engineer, AI Compute roles. Distinct from `devops`, which is a delivery-pipeline value. |
| `engineering_management` | 31 / 29 / **22** | 6 / 6 / 5 | Best employer spread of the tech set. Director/Manager, Engineering. `pm` covers *product* management; nothing covers engineering management, so all of it lands in `other`. |
| `qa_test` | 24 / 22 / **16** | 2 / 2 / 2 | Senior Quality Engineer, QA Test Engineer, Mobile QA Engineer, Staff Software Engineer QE. |
| `program_management` | 17 / 17 / **13** | 13 / 12 / 10 | Technical Program Manager, Project Manager, Delivery Manager. Has mass in *both* populations. |
| `mobile` | 16 / 16 / **13** | 2 / 2 / 2 | iOS/Android/React Native. A clean gap: `frontend` exists, mobile does not. |
| `business_systems` | 16 / 13 / **9** | 16 / 11 / 7 | Salesforce, Workday, NetSuite, ERP, CPQ, Business Systems Analyst. Mass in both populations, and the closest thing in this corpus to the cohort's AI-adjacent internal-tooling work. |
| `it_internal` | 8 / 7 / 6 | 17 / 15 / **11** | Internal IT rather than customer-facing support. Mass sits in the *cohort*, which is why it is carried despite a thin `other` count. Distinguish from `support_ops` by who is served. |
| `developer_relations` | 11 / 9 / **7** | 0 / 0 / 0 | Weakest of the tech set and the one to drop first if the vocabulary must shrink. Developer Advocate, Developer Relations, technical writing. |

### Total effect

Distinct-row unions, printed by the tool's TOTAL EFFECT section:

| set | `other` / 427 | cohort / 863 |
|---|---|---|
| ops, recommended (5) | 54 (12.6%) | 179 (20.7%) |
| ops, all proposed by task 11 (7) | 55 (12.9%) | 191 (22.1%) |
| tech, recommended (9) | 203 (47.5%) | 69 (8.0%) |
| **all 14 recommended** | **242 (56.7%)** | **237 (27.5%)** |
| the 2 dropped candidates alone | 1 (0.2%) | 14 (1.6%) |

> **Read the whole of this table as `facts_version = 2`.** Reproduce it with
> `--facts-version 2`, or `--facts-version 0` for the historical all-versions population
> (696 rows) the tool used to return by default. The v3 equivalents are in § *The
> commercial gap in `ARCHETYPE`, and the one value proposed for it*.

**14 recommended values reclaim 242 of 427 `other` rows (56.7%), leaving 185.** Adding the
two dropped candidates back would reclaim **1** further row. In the cohort, the same 14
values name 237 of 863 (27.5%) by title probe alone — a floor, since the probe reads titles
and the extractor reads the whole posting.

The residual 185 is mostly senior IC engineering that the existing values arguably *should*
already catch (`Senior Machine Learning Engineer`, `Senior Foundry Integration Engineer`,
`Staff Engineer QE`). That is an extraction-quality question, not a vocabulary one, and it
is out of scope here — but worth noting that a straight ML engineer has no home in a
vocabulary whose only ML value is `ml_research`, defined as research-level work
(`extract.py` `_INSTRUCTIONS`, `role_archetype` guidance).

---

## (b) The `role_track` vocabulary — **PROVISIONAL**

**Marked provisional, with the reason, per task file lines 56–64.** This corpus is
pre-Phase-3 and tech-heavy: 142 employers, overwhelmingly software companies and ATS-clean
postings, plus one NYC-government block. The task file asks for the clustering to be run
*after* Phase 3 adds sources and says a taxonomy from today's corpus "will not describe the
population's opportunity space". It does not. This vocabulary is the provisional one the
task file explicitly sequences for now, and `derive-role-tracks.py` exists to be re-run.

Nine values. Each is a name given to one or more clusters; the cluster sizes are counts of
**representatives** (post-collapse, of 650), and are reproducible with
`python3 backend/tools/derive-role-tracks.py --tracks`.

| `role_track` | clusters (n, employers) | one-line definition for the extraction prompt |
|---|---|---|
| `software_engineering` | c1 (74, 46), c20 (7, 4) | Building the product itself — backend, frontend, full-stack, mobile, or infrastructure code. |
| `technical_support` | c0 (89, 37) | Resolving problems for users or staff after a product ships — support, service desk, internal IT. |
| `business_analysis` | c2 (73, 29), c24 (5, 5) | Analysing commercial, financial, risk or compliance data to inform decisions, rather than building systems. |
| `product_and_marketing` | c3 (70, 37) | Deciding what gets built or how it is positioned — product management, marketing, growth, developer relations. |
| `solutions_and_implementation` | c4 (35, 14), c15 (9, 8), c16 (9, 4) | Customer-facing technical work that configures or deploys an existing product — pre-sales, solutions architecture, implementation, onboarding. |
| `data_and_analytics` | c5 (32, 20) | Working with data as the primary material — analysis, science, pipelines, annotation. |
| `revenue_operations` | c6 (29, 17), c17 (9, 8), c18 (8, 8), c21 (6, 6) | Running the commercial machine — GTM and sales operations, enablement, accounts, billing. |
| `business_systems` | c8 (23, 16), c22 (5, 5) | Configuring and integrating internal business software — Salesforce, Workday, ERP, and the automation between them. |
| `business_operations` | c7 (23, 16), c13 (14, 8), c14 (14, 10), c19 (7, 6) | Coordination and administration that keeps an organisation running — program coordination, legal, finance, people, facilities. |

`security` (c11, n=21, 13 employers) and AI/agent engineering (c12, n=14, 9 employers) both
surfaced as clean clusters but are **not** given tracks: both already exist as archetype
values (`security`, `ai_integration`, `ml_research`). Tracks are the browsable families the
UI groups by; duplicating an archetype at a coarser grain would give the UI two controls
that do the same thing.

Two clusters were read and deliberately not named:

- **c10 (n=22, 14 employers) — "intern, fall".** A real cluster, but it groups on *seniority*,
  not role family. `seniority_level` already carries it (`extract.py:189`).
- **c9 (n=22, 15 employers) — "remote, engineer, prompt, devops".** Groups on the word
  "remote" in the title. `remote_policy` already carries it, and this is the cluster the
  Sailor Health block's survivors landed in.

One cluster is flagged by the tool as an employer artifact and excluded: **c23 (n=5, 3
employers)**, Toast's "Bilingual Hybrid Development Representative".

**Coverage:** the nine tracks account for **20 of the 25 clusters at n≥5, covering 541 of the
650 representatives (83.2%)** — 541 being the sum of the cluster sizes listed in the table
above, each of which the tool prints, since the grouping itself is editorial. Of the five unassigned, two map to existing archetype values
(c11 security, c12 AI/agent), two group on an axis other than role family (c9 remote, c10
intern), and one is the flagged employer artifact (c23). The remaining 109 representatives
are singletons and sub-5 clusters, which is expected — `role_track` is nullable by design,
and the tail is the part of the clustering the module docstring warns not to trust.

---

## The O\*NET/SOC escape hatch

Recorded here so `backend/extract.py` can cite it from a code comment, per task file
lines 32–36, verbatim in substance:

> **If a third vertical ever appears, stop hand-growing this vocabulary and adopt O\*NET/SOC
> codes.** Hand-maintained taxonomies that lag reality are the documented failure mode — it
> is why LinkedIn abandoned theirs. **Two verticals does not justify SOC's complexity; four
> would.**

Where this stands today: the corpus is two verticals — software/tech and NYC government —
and this document hand-grows the vocabulary accordingly. The 14 values recommended above
push the hand-maintained list from 12 to 26, which is most of the way to the point where the
trade flips. Phase 3 is what will decide it. **If re-running `derive-role-tracks.py` after
Phase 3 produces a third and fourth distinct vertical, the correct move is not to add
another eight values — it is SOC.**

### Where the line sits after the 2026-07-31 re-derivation

**The proposal below is 26 → 27, and it is one value rather than five partly because of
this section.** Five would be 26 → 31, which is another eight-values-shaped move made
without the fourth vertical that was supposed to trigger the SOC decision — the escape
hatch would be being stepped over rather than argued with.

Two things keep 27 on the hand-maintained side of the line. **`revenue_commercial` is not
a new vertical; it is a grain mismatch inside an existing one.** `ROLE_TRACK` already names
this work (`revenue_operations`) and `ARCHETYPE` cannot, so the value closes a gap between
two vocabularies the system already maintains rather than extending the taxonomy outward.
And **the corpus is still the same two verticals** — 886 postings across 158 employers,
overwhelmingly software companies plus the NYC-government block, and the one non-tech mass
large enough to notice is a single telehealth employer's hiring spree. Nothing in it is a
third vertical.

**The four deferred families are the thing to watch, and they are deferred rather than
refuted.** `finance_accounting`, `strategy_bizops`, `people_recruiting` and `clinical_care`
all have real mass and, for three of them, real employer spread. If Phase 3's non-tech
sources bring them back with the spread they currently lack — a hospital system, a bank, a
university — **that is the fourth-vertical signal this section is waiting for, and the
answer then is SOC, not 26 → 31.** Recording them here in evidence shape is what makes
that call checkable rather than a fresh argument each time.

---

## What I could not do, and what I did not do

- **No `role_track` values were assigned to any row.** This document derives a vocabulary;
  populating the column is task 11's implementation work and re-extraction is task 12.
- **Nothing was measured against extracted facts for the cohort**, because `pursuit` is
  inactive and 579 of the 863 have no `job_facts` row. Every cohort figure is a title probe,
  which is a floor rather than an estimate.
- **The archetype counts are upper bounds and are not a precision measurement.** Confirming
  that the extractor actually assigns these values, and how consistently, needs an eval
  against frozen fixtures — `backend/evals/fixtures/`, never `ORDER BY first_seen DESC` —
  and a self-agreement floor beside it, since `deepseek-v4-flash` agrees with itself only
  ~~76%~~ **85.2%** on `seniority_level` (**superseded 2026-07-28** by task 06 at n=115;
  the 76% was n=17 and pessimistic — DECISIONS.md § *06 — Was 76% real?*). Not done here;
  it belongs with task 12's re-extraction.
- **The provisional vocabulary has not been validated against Builder preference.** It cannot
  be until task 29 produces labels. **UPDATE 2026-07-30: it now will be.** `role_track` is
  a question on the labelling form — see § *The validation this document asked for* below.
  **UPDATE 2026-07-31: it now partially has been** — 31 of 200 postings, one labeller. The
  answer, and the reasons it is a partial one, are in § *The commercial gap in `ARCHETYPE`,
  and the one value proposed for it*.

---

## The validation this document asked for — 2026-07-30

**`role_track` is the sixth question on task 29's labelling form**, alongside
`ai_involvement`, `seniority_level`, `role_archetype`, `remote_policy` (axis A) and
`would_apply` (axis B). It is on the list for a **different reason from the other
four**, and the difference is worth stating because it looks like an inconsistency.

The other four are there because **task 06 measured them and found the model unstable**;
a human label buys a ceiling to read that instability against. **`role_track` has no
task 06 figure at all** — it postdates that measurement (task 11 added the column) and
the nine-value vocabulary this document derives is explicitly provisional, drawn
pre-Phase-3 from a tech-heavy corpus. It is on the form because **task 30 groups its
precision figures BY this vocabulary**, so an unvalidated vocabulary would silently
condition every per-track number that task produces — and because the validation is only
available now. Nobody can label a set after the labelling session is over.

### The rows where the label buys most are the rows where the model said nothing

**Measured 2026-07-30, over `job_facts` at `facts_version = 3`, AFTER that morning's
nightly run.** The date is not decoration — see § *A corpus statistic here has a shelf
life of one night* below, which is the reason these figures are the second set taken.

| population | `role_track` NULL | of | % |
|---|---:|---:|---:|
| all `job_facts` at v3 | **261** | 917 | **28.5%** |
| `pursuit-v1` — `surfaced` | 16 | 100 | |
| `pursuit-v1` — `below_floor` | 16 | 50 | |
| `pursuit-v1` — `gate_rejected` | **50** | 50 | |
| **`pursuit-v1` total** | **82** | **200** | |

Non-null is **656 of 917**.

> **Superseded, and correct when taken — measured 2026-07-29, before the run:** NULL on
> **244 of 881 (27.7%)** corpus-wide, and **83 of 200** in the set, with **17 of 50**
> `below_floor`. Kept rather than deleted because the delta is the point: **one
> `below_floor` row acquired a `role_track` overnight**, which is the whole of the
> difference inside the set, and 36 new `job_facts` rows at v3 moved the corpus
> denominator 881 → 917.

**This inverts the usual argument about where a label is worth collecting.** On those 82
rows there is no model answer to agree or disagree with, so `model_vs_human()` is
**silent on them** — and that is the interesting half:

- **If a human confidently assigns a track where the extractor left NULL, the NULL rate
  is an EXTRACTION problem.** The vocabulary contains the right answer and the extractor
  is not reaching it — a prompt or a model issue, fixable without touching this
  document's nine values.
- **If the human cannot assign one either, the VOCABULARY is wrong.** The role genuinely
  belongs to no listed track, which is this document's own hypothesis about its coverage
  finally being tested rather than asserted.

**Those are different fixes, and nothing else in the system distinguishes them.** A NULL
rate on its own is compatible with both, which is why this number has been quotable for
two tasks without being actionable.

### A corpus statistic here has a shelf life of one night

**Recorded 2026-07-30, because it moved a figure that was about to be written down as a
bare fact.** The nightly `run-daily.py` fired at **04:09** — `max(first_seen)`
2026-07-30T04:09:01, `max(extracted_at)` 2026-07-30T04:11:47 — ingesting 388 new postings
and 36 new `job_facts` rows. `facts_version = 3` went **881 → 917** and `pursuit`'s
`job_matches` **144 → 152**. The first set of figures above was taken before it; the
second after; both were correct when taken.

**The pinned set did not drift, and could not have.** `pursuit-v1` is pinned by sorted
`job_id` and its `sha256` is still
`afb2d58f5d369dfd03ad9237a8b16396cea31b838a67343f51aceecf70cd1763`;
`eval_label_items` is still 200 rows and `eval_labels` still 0. **But the facts underneath
those 200 rows changed** — one `below_floor` posting acquired a `role_track` overnight.
**Membership is pinned; the extraction under it is not.**

So: **any figure derived from `job_facts` about a pinned set must carry the date it was
taken, and a figure quoted without one should be treated as unverified.** This is the same
class as `HANDOFF.md`'s *"the other agent in the room is the cron job"* — that instance was
a `tech` count moving 835 → 834 when the timer fired at 04:08 — and it now has a second
instance, one night later and one minute earlier in the hour.

**The near-miss worth knowing about.** The **corpus-wide** rate this document reported on
2026-07-29 was **244 of 881 = 27.7%**, and `docs/facts-v3-diff.md:468` independently
reports a `role_track` NULL rate of **27.7%** — from **239 of 863**, a different
denominator and a different run. **Two unrelated measurements that round to the same
number are exactly what gets quoted as one confirming the other.** The 2026-07-30 figure
is 28.5%, which breaks the coincidence; if you find a bare "27.7%" anywhere, establish
which population it is over before using it.

### Why the form needed a tenth value to make that readable

`extract.py:338` tells the model that null means *"no listed track clearly describes the
role"* — a **verdict**, not an absence. `ROLE_TRACK` has nine values and no `other`,
unlike `ARCHETYPE`. Meanwhile the form's *"I can't tell from this posting"* is an
**abstention**, and `labels.validate()` collapses `''` and `'unsure'` to None.

Without a distinct value, a human meaning *"no track fits"* and a human meaning *"I
can't tell"* would both store NULL, and the comparison would score **a considered verdict
and a shrug as agreement**. So the form carries `labels.NO_TRACK_FITS`
(`backend/evals/labels.py:184`) as a tenth choice, rendered as *"none of these describes
this role"*. **Storage keeps the two apart; the fold to the model's domain happens at
comparison time only**, in `labels.as_model_domain()` (`:1492`), where `NO_TRACK_FITS`
against a model NULL reads as agreement — both saying no listed track fits.

**Read the two numbers together when the labels land.** The 50-of-50 NULL rate on
`gate_rejected` is the row to be most careful with: 26 of those 50 postings have **no
`job_facts` row at all**, so no axis-A field can be scored on them by any instrument.
`gate_rejected` yields a recall bound, never a per-field agreement rate.

### One thing this does not settle

The vocabulary question this document flags in § *The O\*NET/SOC escape hatch* — whether a third and fourth
distinct vertical after Phase 3 means SOC rather than eight more hand-maintained values —
is **not** what task 29 answers. Task 29 asks whether the nine values fit the postings
the cohort actually sees. Whether a hand-maintained list is the right *mechanism* at 26
values is a separate decision and still open.

> **Partly settled 2026-07-31**, and in the direction of *not yet*: see § *Where the line
> sits after the 2026-07-31 re-derivation* above. The mechanism question is still open;
> what is now on the record is why 26 → 27 does not decide it and 26 → 31 would.

---

## The commercial gap in `ARCHETYPE`, and the one value proposed for it — 2026-07-31

**One value is proposed — `revenue_commercial` — and it is NOT applied.** The vocabulary
and this rationale land; `extract.ARCHETYPE` is untouched at 26 values and
`schema.FACTS_VERSION` is untouched at 3. The reason is DECISIONS.md **DEC-64**: `pursuit-v1`
is being labelled right now, and re-extraction rewrites the model answers those labels
exist to be read against, mid-collection, on a set whose redraw window has closed.

**Measured 2026-07-31, after that morning's nightly** — `max(first_seen)`
2026-07-31T04:08:06, `max(extracted_at)` 2026-07-31T04:10:45. The date is not decoration;
see § *A corpus statistic here has a shelf life of one night*. Two read-only tools, no LLM
calls and no API key: `tools/derive-role-tracks.py --archetypes` and the new
`tools/label-findings.py --vocabulary --side-list`.

### The instrument was wrong first, and fixing it inverts this document's headline

`derive-role-tracks.py`'s `load_other()` had **no `facts_version` filter**. Its docstring
claimed it returned every `job_facts` row *the current vocabulary* could only call `other`;
it returned rows from **every vocabulary the project has ever had**. That was true on
2026-07-28, when the current version *was* 2. It stopped being true at task 12's bump —
which is precisely the moment this tool exists to be re-run.

Unfiltered, `other` is **696** rows, of which **402 (58%) are `facts_version = 2`** — the
twelve-value vocabulary, which never contained the fourteen values the tool exists to
evaluate. Raw `other` matches, unfiltered → at v3:

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
| **tech values, distinct-row union** | **202 (29.0% of 696)** | **9 (3.1% of 294)** |

**What this inverts is the conclusion, not just the arithmetic.** Those 202 rows are
`other` *under the twelve-value vocabulary*, on the author's tech corpus. Counting them as
reclaim credits fourteen new values with rows nobody is asking the extractor to re-judge —
and the v3 population is a different **corpus** as well as a different vocabulary, since
task 12 retargeted the extraction gate to `pursuit`, so it contains almost none of that
data-centre and hardware work. **The remaining `other` bucket is therefore not evidence
that the 26 values sit unused. It is a different, smaller gap**, and the whole of this
section is about what is in it.

A `--facts-version` flag now defaults to `schema.FACTS_VERSION`; `--facts-version 0` means
all versions and reproduces every historical figure above. The population is printed in the
header of every run. Two smaller fixes travelled with it: `_families()` derived its family
list from two hardcoded `("ops", "tech")` tuples while `CANDIDATES` had grown a third, so
**the commercial family was probed, counted and never printed** — it and the union-reclaim
table now both derive the list from `CANDIDATES`. DEC-65 has the reasoning.

### The corpus, restated at `facts_version = 3`

| | |
|---|---|
| **cohort** | **886** open postings at relevance tier ≤ 2 under `pursuit`, across **158** employers |
| **other** | **294** `job_facts` rows at v3 with `role_archetype = 'other'` — **31.3%** of the 940 rows at v3 |
| **near-duplicate blocks** | 79 blocks, **212 postings collapsed (23.9%)**, 674 representatives into the clustering |

**Two rates that are not comparable, written together because they are being compared.**
`other` is **8.0% at `facts_version = 2`** (402 of 5,024 — the author's tech corpus, twelve
values) and **31.3% at v3** (294 of 940 — pursuit-eligible, twenty-six values). **Those
differ by vocabulary AND by corpus.** So *"12 → 26 made `other` worse"* — a claim currently
circulating as settled, and traceable to task 12's own headline — **conflates two changes
and cannot be read as a verdict on the vocabulary.** What survives is weaker and still
worth acting on: fourteen new values were not followed by any visible shrinkage.

### What the 294 actually are

| | rows | of 294 | |
|---|---:|---:|---|
| `role_track` **also NULL** | **182** | **62%** | neither vocabulary has a word for the role |
| `role_track` assigned | 112 | 38% | the coarse vocabulary copes; the fine one cannot |

The 112, by track: `business_operations` **36**, `revenue_operations` **35**,
`product_and_marketing` 18, `business_analysis` 11, `data_and_analytics` 5,
`solutions_and_implementation` 4, `software_engineering` 3.

**The 112 are the finding, not the 182.** Seventy-one of them — 63% — are
`business_operations` or `revenue_operations`: rows where the extractor knew what kind of
work it was looking at and had no archetype to say it with. That is a vocabulary defect
with a specific shape, and it is the shape `revenue_commercial` is cut to.

**Employer spread of the bucket itself, because the raw rate does not dedup it:**

| employer | rows of 294 | |
|---|---:|---|
| Sailor Health | **57** | **19.4% of the whole bucket** — one telehealth clinical-psychologist role posted once per US state |
| AlphaSense | 17 | |
| Toast | 15 | |
| Datadog | 13 | |
| Anthropic | 11 | |

**One employer is a fifth of the `other` problem.** Any headline rate over this bucket that
has not collapsed near-duplicates is measuring Sailor Health's hiring spree, which is the
same trap § *Near-duplicate blocks* was built for one level up.

> **Use 57, not 59.** A figure of **59** circulated for a few hours on 2026-07-31 and is
> the count of Sailor Health's rows at v3 **regardless of archetype** — the wrong
> denominator for a claim about the `other` bucket. The two rows it adds are not `other` at
> all: *Credentialing Specialist* (`admin_ops`) and *Revenue Cycle Management (RCM)
> Associate* (`support_ops`), both already named by task 11's ops values. Recorded rather
> than silently corrected because 59 and 57 are both true statements about the same
> employer and only one of them answers this question.

### The validation asked for in § *What I could not do, and what I did not do*

**Human labels, 2026-07-31: 186 label rows over 31 of `pursuit-v1`'s 200 postings, by ONE
labeller** — 19 `surfaced`, 9 `gate_rejected`, 3 `below_floor`.

| the humans' own answer | rate | 95% CI |
|---|---|---|
| `role_archetype = other` | **17 of 31 — 55%** | [0.38, 0.71] |
| `role_track = no_track_fits` | **13 of 31 — 42%** | [0.26, 0.59] |

**This is not an agreement figure and must not be written as one.** It is what the humans
said, on its own; `label-findings.py` deliberately prints no model-vs-human comparison,
because with one labeller there is no inter-annotator ceiling to denominate a model score
against (DEC-57, DEC-61). **And the population is different from every corpus figure above** — a
stratified 200-row eval set, not the cohort corpus. The 55% and the 31.3% are two
populations, not a confirmation.

**The labelled sample and the corpus disagree in emphasis, and the corpus is where the
commercial mass is.** Only **2 of the 13** `no_track_fits` rows are commercial — both
Notion *Commercial Solutions Consultant* (Japan and San Francisco), both `would_apply =
no`. The other eleven span rotational and analyst programmes (Carta *Finance and Equity
Analyst — Rotational*, Notion *People Analytics & Operations — Rotational*), ops
specialists (Coinbase *Specialist, Market Operations*), non-software engineering (Shield AI
*Senior Mechanical Engineer*, NewYork-Presbyterian *Licensed Engineer*), recruiting (Finix
*Senior Technical Recruiter*) and data annotation (Cohere).

**So the labels support the *existence* of the gap and not this particular value.** They
are 31 rows by one person, and they are read here as corroboration that `other` is a live
problem in the postings a Builder actually sees — not as the derivation. The derivation is
the corpus evidence below. Stated plainly because the temptation to read a 55% as a mandate
for whatever value one already wanted is exactly what the two-populations warning exists to
stop.

### `revenue_commercial` — the evidence

Counts are **upper bounds** on the same terms as § *(a)*: the probe patterns overlap,
`role_archetype` is single-valued, `dedup` is post-collapse and `emp` is distinct
employers. **Read `emp` first.**

| value | cohort raw/dedup/emp | other raw/dedup/emp |
|---|---|---|
| `revenue_commercial` | 148 / 91 / **31** | 68 / 48 / **23** |

Thirty-one employers in the cohort and twenty-three in `other` is the **widest employer
spread of any candidate in this run, in both populations at once**; the runner-up is
`marketing_ops` at 25 and 16, then `implementation_analyst` and `support_ops` at 23 in the
cohort and almost nothing in `other`. (§ *(a)* called `marketing_ops` the widest of the
original seven at **29** — a v2 figure, not comparable to these, which is what the two
blockquotes above are for.) The mass is not
one employer's spree: Databricks ×34, Datadog ×12 and Braze ×11 lead the cohort, Toast
×14, Datadog ×9 and MongoDB ×6 lead `other`. Deal Desk Analyst, GTM Strategy and Operations
Associate, Commercial Associate, Enterprise Security Sales Specialist, Solutions Architect
(pre-sales), Specialist Seller.

**Distinct-row union reclaim** — unions, not column sums, printed by the tool's TOTAL
EFFECT section:

| set | `other` / 294 | cohort / 886 |
|---|---|---|
| **`revenue_commercial` alone** | **68 (23.1%)** | **148 (16.7%)** |
| ops, recommended (5) | 38 (12.9%) | 184 (20.8%) |
| tech, recommended (9) | 9 (3.1%) | 67 (7.6%) |
| all 15 recommended | 108 (36.7%) | 361 (40.7%) |

**One value reclaims more of the current `other` bucket than the fourteen this project
actually adopted.** Those fourteen reclaim 38 + 9 — **at most 47** together, and fewer as a
union wherever the two families overlap — against **68** for `revenue_commercial` on its
own. Residual `other` after all fifteen: **186**.

### The structural argument, which matters more than the count

**`ROLE_TRACK` has `revenue_operations`. `ARCHETYPE` has no commercial value at all.**
`extract.ARCHETYPE`'s own first line is the admission — `# The original twelve. All
software engineering.` — and the fourteen added by task 11 are five ops and nine tech.
Nothing in the tuple names commercial work.

So a **Deal Desk Analyst gets a coherent `role_track` and can only be `other` at the finer
grain.** That is not a missing value in a list; it is **two vocabularies meant to be one
space at two grains, and on commercial work they are not.** The 35 `other` rows carrying
`revenue_operations` measured above are that asymmetry, row by row.

**This is why the recommendation is one value and not five.** Four other families were
probed and have mass; none of them has this argument behind them. A count says *"here are
some rows"*; the asymmetry says *"the system already believes this category exists and
cannot express it."* And 12 → 26 is the move that has already been tried without a visible
fall in `other` — adding five at once repeats it, at the exact point where § *The
O\*NET/SOC escape hatch* says the alternative to a longer list is SOC.

### Four families probed and deferred, with their counter-evidence

Kept visible rather than dropped, on this document's own standard: the evidence *against* a
value is the part a later reader cannot reconstruct. All four are still probed and still
printed by the tool.

| value | cohort raw/dedup/emp | other raw/dedup/emp | why deferred |
|---|---|---|---|
| `finance_accounting` | 28 / 27 / **19** | 22 / 21 / **16** | Real mass and real spread — the strongest of the four. Deferred, not refuted: FP&A Analyst, Billing Analyst, Order Operations Analyst, Treasury Associate. Adding it is a second value on count alone, which is the thing 12 → 26 already tested. |
| `strategy_bizops` | 31 / 25 / **19** | 26 / 22 / **17** | Same shape, and worse defined: *Strategy Associate*, *Competitive Intelligence Lead*, *Strategic Partnerships Manager* and *GTM Strategy and Operations Associate* are not one family, and the last of them is already `revenue_commercial`'s. A value that overlaps the proposed one is the wrong second value. |
| `people_recruiting` | 13 / 12 / **10** | 8 / 7 / **7** | Distributed but thin — 12 dedup postings. `admin_ops` already catches People Operations Coordinator; what it misses is recruiting proper, and the corpus has a handful. |
| `clinical_care` | 58 / **11** / **3** | 56 / **9** / **1** | **Refuted, not deferred.** 56 raw `other` matches collapse to **one employer** — Sailor Health. This is the employer-spread rule doing exactly the job it was written for, and the reason `emp` is read first. |

The six dropped candidates together would reclaim **113 of 294 (38.4%)** — a figure that
looks decisive until it is read through the `emp` column: **56 of those rows are Sailor
Health.** Net of the fifteen recommended values, the six add **92** rows.

### What applying it will need

Recorded so the next `FACTS_VERSION` bump is not surprised. Per
`config/extraction-policy.json`'s `_not_a_version_note`, the vocabulary lands and the bump
does not, so that one re-extraction pays for both.

- A weight in **both** `config/criteria.json` and `config/pursuit-criteria.json`.
  `tests/test_match.py:484` asserts `set(extract.ARCHETYPE)` equals the priced set
  *exactly*, so a new value fails the suite until both are edited — by design, per
  `match.py`'s `archetype:<value>:unpriced` path.
- The count at `tests/test_extract.py:720`, 26 → 27.
- A `FACTS_VERSION` bump, because both vocabularies are interpolated into `_INSTRUCTIONS`
  (`extract.py:322`), whose own comment asks for one on exactly this kind of change.
- **Not a cost decision.** Task 12 measured the full re-extraction at 863 calls / 28m31s /
  ~\$0.33 (`docs/facts-v3-diff.md`). The objection is the labelling session, and it expires
  when the session does.

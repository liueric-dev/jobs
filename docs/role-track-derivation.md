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
  76% on `seniority_level`. Not done here; it belongs with task 12's re-extraction.
- **The provisional vocabulary has not been validated against Builder preference.** It cannot
  be until task 29 produces labels.

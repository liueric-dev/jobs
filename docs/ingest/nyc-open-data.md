---
script: backend/ingest/nyc-open-data.py
written: 2026-07-28
generator: none
---

> **Provenance.** `generator: none` is literal: nothing in this repo produces
> `docs/ingest/*.md`. Earlier versions carried `generated:` frontmatter naming a
> tool that was never written, which made `.claude/CLAUDE.md`'s *"never hand-edit"*
> instruction unfollowable — the only way to fix a wrong line was to break the rule.
> The claim was dropped across all fourteen files on 2026-07-31; see
> [`34-documentation-cleanup.md`](../tasks/refactor/34-documentation-cleanup.md) §A2.
> These files are hand-written and are maintained by hand.

> **Hand-written, and deliberately carries no `generated:` line.** The other
> files in this directory claim `script:`/`commit:`/`generated:` frontmatter
> and CLAUDE.md describes them as regenerated rather than edited — but **no
> generator exists**. Task 34 owns the decision to either write one or drop
> the claim. Until then this file does not assert a provenance it cannot
> back. Everything below was written at decision time, against the code and
> against a live crawl on 2026-07-28.

## Purpose

Ingests DCAS's **"Jobs NYC Postings"** dataset (`kpav-sd4t`) from the City of
New York's Socrata (SODA) endpoint and upserts it into `jobs` tagged
`platform='nyc_open_data'` (`backend/ingest/nyc-open-data.py:125`).

One documented JSON API, one crawl, no HTML parsing and no token discovery.
It is the only source in the pipeline that publishes an **explicit close
date** per posting, and the only one that is NYC by construction rather than
by regex.

**Read the yield section before investing further in this source.** It works,
it is cheap, and it returns roughly **1.8 relevant postings per day** against
a task-file estimate of 20–60.

---

## Invocation

**Not yet scheduled.** The intended `run-daily.py` `STEPS` entry is
`"ingest/nyc-open-data.py"`, placed after `"ingest/builtin-nyc.py"` and before
`"ingest/weworkremotely.py"` — with the other NYC-scoped source, and before
`extract.py`, which is the only ordering constraint that matters
(`backend/run-daily.py:147-148`).

**Manual.** `python3 ingest/nyc-open-data.py`, or with `DEBUG_PRINT_KEYS=1`
for per-page counts.

### Environment variables

| Variable | Required | Default | Read at |
|---|---|---|---|
| `DATABASE_URL` | yes | none — raises | `backend/lib/dbconn.py:77-91` |
| `SOCRATA_APP_TOKEN` | **no** | unset — runs anonymously | `nyc-open-data.py:154` |
| `NYC_OPEN_DATA_DELAY` | no | `1.0`s anonymous, `0.25`s with a token | `nyc-open-data.py:159-162` |
| `DEBUG_PRINT_KEYS` | no | unset | `nyc-open-data.py:163` |

### The app token, and what it would buy

Nothing but rate limit. Socrata serves anonymous callers from a **shared**
throttling pool and token-holders from their own bucket; the token is not
authentication, and it changes neither the rows returned nor the fields on
them. This crawl is **five requests a night** (two counts, three pages)
against a 2,376-row dataset, which the anonymous pool serves without
complaint — measured 2026-07-28, 17.8s wall clock end to end including the
database write, of which 2s is the script's own inter-page sleep.

If one is ever registered (free, at `data.cityofnewyork.us/profile/edit/developer_settings`),
set `SOCRATA_APP_TOKEN` and it is sent as the **`X-APP-TOKEN` header** by
`_headers()` (`nyc-open-data.py:275-279`). That is the only place it plugs in.

It goes in a header and never in the `$$app_token` query parameter, on
purpose: `evals/cassettes.py` records the request URL and drops request
headers (`cassettes.py:540`), and `$$app_token` is **not** in its
`SECRET_PARAMS` (`cassettes.py:90-93`) — so the query-parameter form would
write the credential into a committed fixture and the header form cannot.

### Expected runtime

~18s. Three pages at `$limit=1000` plus two count queries, plus
`REQUEST_DELAY_SECONDS` between pages.

---

## Data flow

```
fetch_count()  ─────────────────────────────┐   count BEFORE
fetch_all()    $limit/$offset/$order=job_id │   2,376 rows over 3 pages
fetch_count()  ─────────────────────────────┘   count AFTER
        │
        ├── reconcile(collected, before, after)      pure; gates everything below
        │
        ├── filter posting_type == 'External'        1,230 kept, 1,146 dropped
        ├── normalize()                              → jobs columns
        ├── dedupe()                                 1,230 → 1,219 (job_id is not unique)
        ├── split on is_expired(post_until)          1,030 live / 189 expired
        │
        ├── upsert_checked(live)                     errors logged, never discarded
        │
        └── if reconciled:
              close_expired(expired)                 closed_at := post_until
              schema.close_stale(PLATFORM, 7)        closed_at := now
              state.set_watermark(PLATFORM)
```

---

## Field mapping

| SODA field | `jobs` column | note |
|---|---|---|
| `job_id` | `source_id` | **not unique** — see Dedupe |
| `business_title` | `title` | falls back to `civil_service_title` |
| `agency` | `company_name` | as published, upper case |
| `agency` (slugified) | `company_token` | `text.slugify` |
| `job_category` | `department` | e.g. "Technology, Data & Innovation" |
| `preferred_skills` + `minimum_qual_requirements` + `job_description` | `description_text` | all three, **in that order** — see below |
| `salary_range_from`/`_to`/`_frequency` | `salary_text` | stated, never predicted; `$60,000-$65,000 Annual` |
| `posting_date` | `posted_at`, `posted_at_ts` | ISO already |
| `work_location` | `location_raw` | a bare street address on most rows |
| — | `location_is_nyc` | **constant `True`** — see below |
| — | `job_url` | `https://cityjobs.nyc.gov/job/<job_id>` |
| `post_until` | *not a column* | drives `closed_at` — see Closure |
| `career_level` | *not a column* | deliberately unmapped — see below |
| `posting_type` | *filter* | `External` only; the drop count is logged |
| whole record | `raw_json` | capped by `text.bounded_json` |

### Three fields, and the order is not the one task 14 asked for

`docs/tasks/refactor/tranche_three/14-ingest-nyc-open-data.md:44` asks for
`job_description + minimum_qual_requirements + preferred_skills`, and
justifies concatenating all three with *"the AI/automation vocabulary usually
appears in `preferred_skills`, not the description"*.

Both halves of that sentence cannot hold at once. `extract.py:180` caps the
prompt at `MAX_DESCRIPTION_CHARS = 3000` and applies it at `extract.py:257`;
`score.py:312` does the same. Measured over 400 External postings on
2026-07-28:

| field | mean | median | p90 |
|---|---|---|---|
| `job_description` | 4,047 | 3,946 | 6,327 |
| `minimum_qual_requirements` | 1,065 | 932 | 1,933 |
| `preferred_skills` | 306 | 55 | 881 |

`preferred_skills` is present on 202 of 400 postings, and under the task
file's stated order **168 of those 202 (83.2%) sit entirely past character
3,000** — so the field the concatenation exists to capture would never reach
the model on five postings in six.

So `DESCRIPTION_PARTS` (`nyc-open-data.py:246-250`) puts the two short dense
fields first. `relevance.py` is unaffected either way — it matches over the
full stored text, capped at 20,000. Reordering rather than raising
`extract.py`'s cap, because that cap is shared with `score.py`, applies to
all seven platforms, and costs tokens on every row in the table; this is one
source's field order and costs nothing.

`residency_requirement` is deliberately **not** concatenated: identical
civil-service boilerplate on essentially every row, ~500 chars, a sixth of
the prompt budget, and it says nothing about the job. It stays in `raw_json`.

### `location_is_nyc` is a constant, and that is the honest value

`work_location` is a bare street address on most rows — `100 Gold Street`,
`City Hall`, `Rikers Island`, `30-30 Thomson Ave L I City Qns`.
`text.NYC_PATTERN` matched **340 of 1,230** (27.6%). Deriving the flag from
it would file 72% of the City of New York's own job postings as
not-in-New-York, and `config/relevance.json`'s `location_columns` is exactly
`["location_is_nyc", "location_is_remote"]` — so those rows would drop out of
tier 1 for no reason but a regex missing a street address.

Every row here is a City agency requisition, so the constant is true. The
handful of City facilities just over the line (Valhalla, Hawthorne) are
accepted as NYC employers rather than special-cased.

`company_is_nyc_hq=True` and `company_is_ai_focused=False` for the same
reason: both are *known* here, so both are booleans rather than the `None`
the sources that cannot tell use.

### `career_level` is carried and never mapped

The dataset labels every posting `Entry-Level` / `Experienced (non-manager)` /
`Manager` / `Executive` / `Student`. That is a **free, independent label on a
field task 06 measured as unstable**, and task 14 is explicit that it must not
be written into `job_facts.seniority_level`. It rides on the normalized record
(`nyc-open-data.py:533-539`) and lives in `raw_json`, where task 07 can use it
as a check on the extractor rather than as a shortcut around it.

Distribution over the 1,030 live postings, 2026-07-28:

| `career_level` | rows | of which relevant (tier ≤ 2) |
|---|---|---|
| Experienced (non-manager) | 752 | 67 |
| Entry-Level | 130 | 6 |
| Manager | 120 | 5 |
| Executive | 16 | 0 |
| Student | 12 | 1 |

---

## Closure

Two signals, whichever fires first.

**`post_until` — the explicit deadline.** The City's own published close
date, so a posting past it is closed as a fact rather than as a guess.
`close_expired()` (`nyc-open-data.py:601-629`) writes `closed_at` **from the
deadline**, not from the clock: the City said when applications stopped, and
recording the night we noticed would throw that away.

It arrives as `12-SEP-2026` — a text field, not one of the ISO timestamps the
rest of the record uses. 1,206 of 1,206 non-null External values matched that
one shape. Anything unreadable parses to `None` and falls through to
disappearance, which is the safe direction: a deadline we cannot read must
never close a posting early.

**Disappearance — `schema.close_stale(PLATFORM, 7)`.** `post_until` is *not*
sufficient alone, and this is where the source is worse than the ATS feeds: a
requisition can be filled weeks before its deadline, and when that happens
DCAS drops the row while `post_until` still reads months out. Disappearance
is therefore the *earlier and more accurate* signal for a filled req, and
`post_until` is the backstop for one that lingers.

Seven days rather than one, because DCAS republishes in batches — on
2026-07-28 every one of `max(process_date)`, `max(posting_updated)` and
`max(posting_date)` read **2026-07-20**, an eight-day-old snapshot. A row
briefly missing from one batch must not be closed and then reopened. It does
not need to be tight: `post_until` does the precise work for the 98% of
postings that carry one (24 of 1,230 External rows carry none).

**Expired postings are never written.** A deadline that has already passed is
not a job a Builder can apply to, and inserting one would create a row no
consumer can see (`schema.py`'s `jobs_app` view is scoped to `status='open'`)
purely so `prune_old_closed` could delete it later. Writing and then closing
in the same run would additionally report every expired posting as `updated`
every night forever, because `schema.spec()` recomputes `status='open'` on
every INSERT and UPDATE.

---

## Dedupe & idempotency

**`job_id` is not unique in this dataset.** Measured 2026-07-28: 1,230
External rows carry **1,219 distinct `job_id`s** — ten ids appear twice and
one three times. The twins are the same requisition published at more than
one `level`, and they do not always agree:

```
job_id 781780  Scientist (Water Ecology), I   post_until 25-JUL-2026
job_id 781780  Scientist (Water Ecology), I   post_until 13-SEP-2026
```

`schema.make_job_id()` is `sha256("platform:token:source_id")`, so both land
on one primary key and `upsert()` writes whichever comes last — the "two
records share a primary key, so one silently overwrites the other" failure
`tests/test_ingest_cassettes.py:84-88` exists to catch.

Worse than the overwrite: **the first live run of this script, on 2026-07-28,
wrote the live twin of two such pairs and then closed it from the expired
twin's deadline.** A posting open until September, closed in July, with
nothing in the output saying so. `dedupe()` (`nyc-open-data.py:543-577`) now
collapses them before the live/expired split, keeping the most permissive
deadline — a row with no `post_until` beats one with a date, and among dates
the latest wins, because the rule decides what may *close* a posting. The
collapse count is in every run's summary line.

Otherwise idempotent in the ordinary way: `content_hash` over
`HASH_FIELDS` (`nyc-open-data.py:215`), which is `HASH_FIELDS_ATS` plus
`salary_text`. Salary here is *stated* by the employer rather than parsed out
of prose, so a change to it is a real upstream edit; without it in the hash, a
posting whose band was corrected and whose description was not would be
counted `unchanged` and the stored band would stay wrong forever.

---

## Failure modes

**A short page is not the end of the list.** SODA answers a throttled request
and a last page with the same shape — fewer rows than were asked for. Every
run therefore asks the dataset how many rows it has
(`$select=count(*)`) **before and after** the crawl, and `reconcile()`
(`nyc-open-data.py:373-402`, pure, no I/O) compares that against what was
collected. **Closure and the watermark are gated on the answer**; the upsert
is not, because rows that did arrive are still good rows.

Two counts rather than one because the dataset genuinely moves between the
count and the last page; the pair brackets the crawl. The allowance is 2% or
5 rows, whichever is larger (`RECONCILE_TOLERANCE`, `RECONCILE_FLOOR`) — not
a measurement, and stated as such in the source.

`$order=job_id` is not decoration. Socrata does not promise a stable row order
across `$offset` requests without an explicit `$order`, and an unstable order
silently both skips and duplicates rows across page boundaries — which
`reconcile()` cannot see, because the count still matches.

**Silence.** Four things break it, all on stdout:

| condition | line |
|---|---|
| crawl did not reconcile | `ALERT: closure skipped — TRUNCATED: collected N of M …` |
| `MAX_PAGES` reached instead of a short page | `ALERT: pagination stopped at the 25-page cap …` |
| fewer than `MIN_EXTERNAL_ROWS` (400) External rows | `ALERT: only N External postings …` |
| `posting_type='External'` matched nothing | `ALERT: closure skipped — the filter or the column has changed shape` |

The summary line is printed on **every** run, unlike `ingest/ats.py`'s
quiet-day rule (`ingest/ats.py:1169`): this source writes every row it has every
night, so "wrote nothing" is never normal here, and the counts are the only
way to see a filter that stopped matching. Exit is non-zero on a failed
fetch, a failed reconciliation, a zero-External run, or an upsert error rate
over threshold.

**`upsert_checked` throughout** (`nyc-open-data.py:684`). No bare three-tuple
unpack; `errors` is logged on every run including when it is zero.

---

## External dependencies

- `https://data.cityofnewyork.us/resource/kpav-sd4t.json` — public Socrata
  SODA endpoint, unauthenticated, no quota worth budgeting.
- A **NY State mirror** exists at `https://data.ny.gov/resource/vntw-tq6b.json`
  with slightly fewer fields. Not ingested. If it ever is, it is a **different
  publisher and a different `platform` string**, not more rows under this one.

---

## Measured yield, 2026-07-28

Full live crawl, real database, `config/relevance.json` as committed.

| | |
|---|---|
| rows in the dataset | 2,376 |
| `posting_type='External'` | 1,230 (51.8%) |
| `Internal` dropped | 1,146 |
| distinct after `dedupe()` | 1,219 |
| past `post_until`, not written | 189 |
| **written and open** | **1,030** |
| in NYC | 1,030 (100% — every row, by construction) |
| with a description | 1,030 (100%) |
| with a stated salary | 1,030 (100%) |
| **relevant (tier ≤ 2)** | **79 (7.7%)** |
| new External postings per posting-day | ~26 |
| **relevant per posting-day** | **1.8** |

**Against the task file's estimate of 20–60 relevant postings/day: this is
10–30× lower.** Stated plainly because a truthful low number is the result.

The 79 relevant rows are also not the roles the cohort targets:

- **44 of 79** are built-environment engineering and architecture — Civil,
  Mechanical, Marine, Design, Resident, Parking, Geotechnical Engineer,
  Engineer-In-Charge. `title_include` matches on "engineer"; the City employs
  a great many of them and none of them writes software.
- **23 of 79** are software/data (Data Scientist, Data Engineer, Salesforce
  Developer, `COMPUTER ASSOCIATE (SOFTWARE)`, Senior Software Engineer).
- **6 relevant rows are `career_level='Entry-Level'` and every one of them is
  a civil-engineering intern or junior design engineer.** Zero entry-level
  software or AI roles across the whole dataset.

And on the AI vocabulary the task file expects:

> "increasingly with AI and automation language in the `preferred_skills`
> field" — task 14

**2 of 1,030** postings mention machine learning, artificial intelligence,
LLMs or generative AI in `preferred_skills` (Senior Director of Strategic
Initiatives; Lead Data Scientist, Justice Processes). **6 of 1,030** mention
them anywhere in the three description fields. That premise does not hold
today.

**Hand check, 30 rows.** Pinned by sorted `source_id`, every 34th row of the
1,030 (`540190, 721337, 756978, …, 786537`). Judged against the cohort:
entry-level-accessible, AI- or tech-adjacent, NYC.

**1 of 30 (3.3%) is plausibly Pursuit-relevant** — `763515 Cell Site
Analyst`, $75,000, a forensic data-analysis role, and even that is labelled
`Experienced`. The other 29 are Assistant District Attorneys (JD + bar),
Public Health Nurses (RN), Construction Laborers, Plasterers, Sergeants,
Records Clerks, Deputy Directors and Chiefs of Staff. One (`783402 Senior
.NET Developer`) is genuine software work at the wrong seniority.

### What this means

The source is worth keeping. It is nearly free, it is 100% NYC, it has real
salaries and real close dates on every row, and it is the cleanest test data
in the pipeline. It is **not** the "single best free NYC source" for this
cohort that task 14 opens by calling it, and nothing downstream should be
tuned on the assumption that it delivers 20–60 relevant postings a day.

Two things could change the number, neither of them this task's:

1. **The relevance retarget.** These figures are against `config/relevance.json`
   as committed, which is still the software-engineer configuration. A
   Pursuit-shaped config that reaches "Coordinator", "Specialist" and
   "Analyst" titles would score this source very differently — the raw
   material is 1,030 City analyst/coordinator/specialist postings — and would
   also stop counting 44 civil engineers as hits. **Re-run this measurement
   after that lands; do not carry these numbers forward.**
2. **Per-platform extraction quality**, which task 07 owns. See below.

---

## Open questions

- **Per-platform self-consistency is unmeasured here.** Task 06 found the
  model agrees with itself 77.8% on `hn_whoishiring` versus 92.2% on clean
  ATS postings, and these descriptions are heavy civil-service boilerplate —
  residency requirements, examination language, "TO APPLY: ALL APPLICATIONS
  MUST BE SUBMITTED THROUGH THE NYC JOBS WEBSITE". Expect this platform at
  the messy end. Task 07 should key its measurement on
  **`platform = 'nyc_open_data'`**, and if it lands below
  `config/extraction-policy.json`'s 0.90 threshold, that file gets a new row
  — the string must match exactly or the lookup silently falls through to
  `default_passes` (`extraction-policy.json` `_measured_agreement_caveats`).
- **`career_level` versus extracted `seniority_level`.** 1,030 free
  independent labels are sitting in `raw_json` waiting for someone to
  cross-tabulate them against what `extract.py` produced. That is the
  cheapest available check on a field task 06 measured as unstable, and
  nothing has run it.
- **The dataset's own freshness.** Every date field topped out at 2026-07-20
  on 2026-07-28 — an eight-day-old snapshot. Whether DCAS republishes
  weekly, or that week was an outage, is not established by one observation.
  If it is weekly, the nightly schedule is six wasted crawls a week (cheap,
  but worth knowing) and `STALE_AFTER_DAYS = 7` is sitting exactly on the
  republish period, which is closer than it should be.
- **`number_of_positions`** is on every record and is ignored. A posting
  hiring 40 Construction Laborers and one hiring a single Data Scientist are
  the same one row here.

---
kind: contract
script: backend/ingest/ats.py
written: 2026-07-28
generator: none
supersedes: the generated 2026-07-27 version at commit dd49a27
---

> **Provenance, stated plainly.** The previous version of this file carried
> `generated: 2026-07-27` frontmatter, and CLAUDE.md describes `docs/ingest/*.md`
> as "generated with `script:`/`commit:`/`generated:` frontmatter — regenerate,
> never hand-edit." **No generator exists.** Nothing in this repository produces
> these files; `grep -rn "docs/ingest" --include='*.py'` finds no writer. Task 34
> has to decide whether to write generators or drop the claim. This file is
> therefore **hand-written**, says so, and does not carry a `generated:` line it
> cannot back. Line citations were correct at the time of writing and are the
> thing most likely to rot — treat a mismatch as this file being stale, not as
> the code being wrong.
>
> Rewritten for task 17 (`docs/tasks/refactor/tranche_three/17-retarget-ats-ingest.md`),
> which replaced the config-file roster with `company_ats`, added three
> platforms, and made closure conditional on reconciliation.

## Purpose

Pulls open job postings from the public job-board API of every employer in the
`company_ats` table, across **six** ATS vendors — Greenhouse, Lever, Ashby,
Workable, Recruitee and SmartRecruiters (`backend/ingest/ats.py:536-545`). Each
posting is normalized into the 18 columns of `schema.COLUMNS`
(`backend/schema.py:121-128`) and written to the `jobs` table
(`backend/schema.py:270-294`).

An employer's **entire** board is pulled, deliberately. `config/relevance.json`
records that this is why "~87% of the table is roles this persona will never
apply to"; since the retarget to the Pursuit cohort that is the feature rather
than the cost — pulling a hospital system's whole board is how the
AI-operations coordinator buried in it gets found. Filtering by profile happens
at the relevance gate, never by dropping rows here.

Postings open but absent from this run are set to `status='closed'`
(`backend/ingest/ats.py:1128`), subject to three guards; rows closed more than
30 days ago are deleted (`:242`, `:1146`). A per-company row is written to
`job_ingest_state` (`:1137`), which this script never reads back.

---

## What changed in task 17

| | before | after |
|---|---|---|
| roster | `config/companies.json`, 68 entries, read every run | `company_ats` table, 70 rows today (`backend/ingest/ats_sources.py:95-134`) |
| platforms | greenhouse, lever, ashby | + workable, recruitee, smartrecruiters |
| closure | any non-empty fetch closes | non-empty **and** reconciled **and** not a delta run (`:1125-1135`) |
| pagination | none anywhere | lever (`limit`/`skip`), smartrecruiters (`limit`/`offset`) |
| salary | always `None` | ashby `compensation`, recruitee `salary` |
| request count | not recorded | `ats-requests:` on stderr every run (`:273-278`, `:1150`) |
| `is_nyc_hq` / `is_ai_focused` | from config | **retired**, always `None` |

`config/companies.json` is **retired as a runtime input**. It survives as the
one-time seed corpus behind `python3 ingest/ats.py --seed-from-json`, in the
same relationship `data/nyc-employer-seed.json` has to `ats_seed`. Its
`_comment` says so in the file. Editing it changes nothing until that command
is re-run, and re-running it will never overwrite a row
`tools/ats-discover.py` wrote (`backend/ingest/ats_sources.py:181-202`).

---

## The roster

```sql
SELECT ats, token, employer_name, status
  FROM company_ats
 WHERE ats = ANY(:platforms) AND status = ANY(:statuses) AND token <> ''
 ORDER BY ats, token
```

`backend/ingest/ats_sources.py:107-115`. Deduplicated on
`(lower(ats), lower(token))` afterwards (`:117-126`): two employers can share
one board — a health system and its physician group — and pulling it twice
would double the requests and run `close_missing` twice over the same rows.

### Which statuses admit a token

`company_ats.status` is a **four-value vocabulary, not a boolean**
(`backend/ats_discovery.py:77-80`):

| status | admitted? | why |
|---|---|---|
| `valid` | yes | the ATS answered and listed jobs |
| `unvalidated` | **yes** | a token was found and the ATS did **not** answer — 403, 429, 5xx, a network failure, or a 200 whose body was not a recognisable feed (`backend/ats_discovery.py:353-384`). Excluding it would mean a board blocked once at validation time is never pulled again, which is the same silence one layer up. Trying costs one request that either works or lands in the per-company error list |
| `dead` | no | a conclusive 404 or empty list from the vendor's own API (`backend/ats_discovery.py:369`, `:383`) |
| `never_found` | no | an employer with no token at all — `ats=''`, `token=''` (`backend/ats_discovery.py:490-491`). Excluded by the platform filter before status is considered |

The set is data, not a literal in a query
(`ats_sources.ADMITTING_STATUSES`, `backend/ingest/ats_sources.py:80-82`), and
a test asserts `dead` and `never_found` stay out of it.

### `not_found` is not "no ATS"

`docs/ats-token-discovery.md:35-60`: task 16's positive control found **0 of 4**
known-good tokens, because those boards render client-side and the board URL is
not in the served HTML at all. Every coverage figure derived from this table is
a **floor**. Nothing in this script treats absence from `company_ats` as
evidence about the world.

### What the roster actually holds today (2026-07-28)

| platform | rows admitted |
|---|---|
| greenhouse | 46 |
| ashby | 23 |
| lever | 1 |
| workable | **0** |
| recruitee | **0** |
| smartrecruiters | **0** (the one row present is `dead`) |

The three new platforms are wired, cassette-tested and contribute **nothing
until discovery finds tokens for them**. That is a discovery gap, not an
ingest gap, and task 16's own report predicts it: public-feed coverage of the
non-tech roster measured 0.5% of seeded employers, and 45 of 60 `found`
employers were lost to a batch-flush defect
(`docs/ats-token-discovery.md:139-143`, `:434-440`). The nightly
`tools/ats-discover.py --apply --nightly` backfill is what closes it.

---

## Invocation

**Scheduled.** `run-daily.py` is the only automated caller; `ingest/ats.py` is
one of its `STEPS` (`backend/run-daily.py:146`), invoked as a subprocess with
`cwd=SCRIPT_DIR` and `env=os.environ.copy()`, output captured.

`run-daily.py` runs under a systemd user timer, `OnCalendar=*-*-* 00:00:00`
local, `Persistent=true`. The service is `Type=oneshot`,
`WorkingDirectory=/home/eric/apps/jobs/backend`, `TimeoutStartSec=10800`.

**Manual.** Guarded by `if __name__ == "__main__"` (`backend/ingest/ats.py:1192`).

### CLI arguments

The script now takes arguments (`backend/ingest/ats.py:1023-1040`); the
previous version had none.

| flag | effect |
|---|---|
| *(none)* | the nightly full pull |
| `--seed-from-json` | insert absent tokens from `JOB_SOURCES_FILE` into `company_ats` and exit. Idempotent, insert-only |
| `--delta ISO8601` | only postings released after this timestamp, on the platforms that support it. **Disables closure** for those platforms. Not for the nightly run |

`run-daily.py` passes no arguments, so the scheduled behaviour is unchanged.

### Environment variables

| Variable | Required | Default | Read at |
|---|---|---|---|
| `DATABASE_URL` | yes | none — `database_url()` raises if unset | `backend/lib/dbconn.py:77-91` |
| `JOB_SOURCES_FILE` | no | `<repo>/backend/config/companies.json` | `backend/ingest/ats.py:237-240` |
| `DEBUG_PRINT_KEYS` | no | unset; `"1"` enables stderr diagnostics | `backend/ingest/ats.py:241` |
| `ATS_SR_DETAIL_BUDGET` | no | `200` | `backend/ingest/ats.py:494-495` |

No API keys. Every endpoint here is unauthenticated. "Token" in this script
means an ATS board slug, never a credential.

### Measured runtime and request count

**Measured 2026-07-28**, one full run against the live boards:

```
ats-requests: total=70 companies=70 ashby=23 greenhouse=46 lever=1
jobs-ingest: 135 new, 465 updated, 9157 unchanged, 45 closed,
             0 old-closed pruned, 0 record(s) dropped,
             across 70/70 sources (0 failed, 0 unvalidated,
             0 unreconciled), 70 request(s).
```

70 requests for 70 companies: one each, because every admitted token today is
on a platform that answers in a single call. The per-platform cost, for
projecting what the roster will cost as it grows:

| platform | requests per company per run |
|---|---|
| greenhouse | 1 |
| ashby | 1 |
| recruitee | 1 |
| lever | `ceil(postings / 100)`, capped at 10 |
| workable | 2 (one v3 for `total`, one widget for descriptions) |
| smartrecruiters | `ceil(postings / 100)` + up to `ATS_SR_DETAIL_BUDGET` |

`REQUEST_DELAY_SECONDS = 0.5` (`backend/ingest/ats.py:247`) between calls
inside a paginating fetch and between SmartRecruiters detail calls; there is
still **no delay between companies**, which is unchanged and is fine because
consecutive companies are usually different hosts.

The count is of requests **this script issues**. `lib/http.py` retries a 429 or
5xx underneath (up to 5 attempts, `backend/lib/http.py:29`) and those retries
are invisible here, so the number is a floor on wire traffic and an exact count
of intended calls.

---

## Endpoints, and what each one does and does not report

Probed live on 2026-07-28. Every row in the last two columns is a measurement,
not a reading of vendor documentation.

| platform | endpoint | pagination | server-side total | descriptions in the list? |
|---|---|---|---|---|
| greenhouse | `GET api.greenhouse.io/v1/boards/{token}/jobs?content=true` | none | **`meta.total`** | yes, via `content=true` |
| lever | `GET api.lever.co/v0/postings/{token}?mode=json&limit=100&skip=N` | `limit`+`skip` | no | yes |
| ashby | `GET api.ashbyhq.com/posting-api/job-board/{token}?includeCompensation=true` | none | no | yes |
| workable | `POST apply.workable.com/api/v3/accounts/{token}/jobs` **and** `GET apply.workable.com/api/v1/widget/accounts/{token}?details=true` | v3 pages by `nextPage` (10/page); the widget does not page | **v3 `total`** | only in the widget |
| recruitee | `GET {token}.recruitee.com/api/offers/` | none | no | yes |
| smartrecruiters | `GET api.smartrecruiters.com/v1/companies/{token}/postings?limit=100&offset=N` | `limit`+`offset` | **`totalFound`** | **no** — one `GET .../postings/{id}` per posting |

### Greenhouse

`content=true` is what returns descriptions. Without it every posting arrives
with no `content` key and every description silently becomes NULL while the run
reports success — the exact shape the `ats-greenhouse-no-content` cassette
holds. `meta.total` is this platform's reconciliation anchor.

### Lever

`limit`/`skip` verified working (`limit=3` then `skip=3` returns a disjoint set
of ids). No total. **The task file's note that pagination truncates at 250 is
honoured by refusing closure rather than by slicing**: past
`LEVER_SKIP_CEILING = 250` (`backend/ingest/ats.py:364`) a short page and the
API's own truncation are the same bytes, so absence stops being evidence. A
board that large needs slicing by team or location, which this script does not
do; recording that it could not see the whole board is strictly better than
closing on a guess.

### Ashby

`includeCompensation=true` adds a `compensation` object whose
`compensationTierSummary` is the rendered range the employer chose to publish
(`"$213K – $251K • Offers Equity • …"`). It is the cleanest salary of any
public feed here — a string the employer wrote, not a number inferred from
prose. Boards that publish nothing return the key with empty tiers and null
summaries, which `ashby_salary()` answers `None` to
(`backend/ingest/ats.py:640-660`).

**Caveat, and it is not small.** `salary_text` is **not** in `HASH_FIELDS_ATS`
(`backend/schema.py:131-132`, documented FROZEN), so an existing row whose
content hash has not moved takes the `unchanged` branch and its `salary_text`
is never written. Salary therefore appears only on rows that are new or
otherwise changed, and fills in as boards turn over rather than all at once.
Verified after the 2026-07-28 run: 0 of 2,515 open ashby rows carry a salary,
while `fetch_ashby('vanta')` yields 63 of 102 postings with one. Backfilling
needs either an extension of `HASH_FIELDS_ATS` — which rewrites the stored
digest of every ATS row, once — or a one-off UPDATE. Neither is in task 17's
scope and neither has been done.

### Workable — two endpoints, on purpose

The task file names `/api/v3/accounts/{slug}/jobs`. That endpoint is
authoritative about the **set** (it reports `total`) and carries **no
descriptions at all**, and it pages ten at a time. The v1 widget with
`details=true` returns every posting with its full description in one request,
reports no total, and **expands one entry per location**.

Measured against `braven` on 2026-07-28: the widget returned **66 entries for
20 distinct `shortcode`s**. Ingested naively that is a 3.3× over-count whose
extra rows collide on the primary key (`make_job_id` hashes per-posting
identity) and silently overwrite each other.

So: one v3 call for the truth about the size, one widget call for the content,
dedupe by `shortcode`, reconcile the two (`backend/ingest/ats.py:435-454`). Two
requests per account regardless of board size, and the over-count cannot
survive. The v3 call goes **first**: if it fails the whole company fetch fails,
which means no records, which means no closure — rather than closing postings
on the strength of an unreconciled list.

### Recruitee

One request, whole board, descriptions and a structured `salary` object
(`{min, max, currency, period}`) which `recruitee_salary()` renders
(`backend/ingest/ats.py:620-637`). No pagination and no total.

### SmartRecruiters

`limit` **clamps to 100 and reports the clamp back** — asked for 200 it answers
`"limit":100` with 100 items. That is the honest behaviour Workday does not
have: CLAUDE.md's landmine is that Workday answers `limit>20` with an *empty
array and no error*, byte-identical to the end of the list. Both were probed
rather than assumed, because the trap generalises even where this vendor avoids
it.

The list carries **no description**. The job ad is one `GET /postings/{id}` per
posting and there is no bulk form (`?expand=jobAd` is accepted and ignored). A
4,755-posting board is 4,755 requests to describe fully, which is not a nightly
budget. So descriptions are **backfilled**: each run spends at most
`ATS_SR_DETAIL_BUDGET` (default 200) detail calls per company, on postings that
do **not** already have a stored description, newest `releasedDate` first
(`backend/ingest/ats.py:953-987`). In steady state that is the day's new
postings. A board bigger than the budget fills in over successive nights and
the shortfall is reported rather than left to be inferred from a quietly NULL
column.

---

## Delta sync — what the platforms actually support

`17-retarget-ats-ingest.md:46` says "Both Greenhouse and Lever expose update
timestamps. Poll with `updated_at` filtering rather than full re-pulls."
**Probed against the live APIs on 2026-07-28, that is not true of either.**

| platform | server-side delta filter | evidence |
|---|---|---|
| greenhouse | **none** | `?updated_after=2030-01-01T00:00:00Z` returns the same 5 postings as no filter at all (`kickstarter`). The parameter is accepted and silently ignored — CLAUDE.md's silence landmine in its purest form. `updated_after` belongs to the authenticated **Harvest** API, not to this public board API |
| lever | **none** | there is no update timestamp in the payload at all. A posting carries `createdAt` and no `updatedAt` key, so there is nothing to filter on server-side or client-side |
| ashby | none | no filter parameter; postings carry `publishedAt` only |
| workable | none | no filter parameter |
| recruitee | none | postings **do** carry `updated_at`; the endpoint accepts no filter for it |
| smartrecruiters | **`releasedAfter=<ISO8601>`** | real and server-side: with `releasedAfter=2030-01-01T00:00:00Z`, `totalFound` drops from 4,755 to 0. It filters on `releasedDate` — **publication, not last update** — so it will not surface an edit to an older posting |

Each posting's own `updated_at` **field** (greenhouse) is a different thing from
a query filter and is already hashed into `posted_at`.

So `--delta` exists, applies to SmartRecruiters only
(`DELTA_CAPABLE`, `backend/ingest/ats.py:548`), and **disables closure** for the
platforms it applies to. That is not a limitation to work around, it is
arithmetic: closure is derived from absence from the complete set, and a delta
response is by construction not the complete set. **A nightly run must be a
full pull.** `--delta` is for an intra-day catch-up.

A test asserts `DELTA_CAPABLE` is non-empty, so the flag cannot quietly become
a no-op.

---

## Closure — free here, and not free in tasks 19–21

Every endpoint above returns the **complete current set** of open postings for
a company. So a posting present yesterday and absent today is closed: no
re-crawl, no `validThrough` parsing, no inference.

**This is worth stating because it is not true of the sources in tasks 19–21.**
JSON-LD scraping, Firecrawl and the aggregators see a *page* of a result set,
not an employer's whole board, so absence there is not evidence of closure.
When someone is deciding which source to trust for a staleness signal, that is
the difference.

### One call, not six

There is **exactly one** call to `schema.close_missing()` in
`backend/ingest/ats.py` (`:1128`), and it is not inside a per-platform branch.
Everything platform-specific ends in `fetch_company()` (`:989-1020`); the loop
that closes, upserts and watermarks is identical for all six. A test asserts
the count over the file's AST, because "shared rather than copy-pasted per
platform" is a property of the file rather than of any one function — a seventh
platform that grew its own closure call would also grow its own idea of when
closing is safe, and would have to remember the three guards rather than
inherit them.

### The three guards

```python
closing = bool(records) and fetched.complete and not (
    args.delta and platform in DELTA_CAPABLE)
```

`backend/ingest/ats.py:1125-1127`.

1. **An empty fetch never closes anything.** `schema.close_missing()` itself
   raises on empty `seen_ids` (`backend/schema.py:674-683`) rather than trusting
   the caller, so the guard is doubled. A genuine zero-postings company is rare
   and not urgent; silently closing an employer's whole board on a transient
   empty response is much worse.
2. **An incomplete fetch never closes anything.** `Fetched.complete`
   (`backend/ingest/ats.py:307-322`) is False when the collected count falls
   short of the total the API itself reported, or when the fetch stopped at a
   page cap or the Lever ceiling. A throttled page is not the end of a list;
   one published account lost 1,960 of 2,000 jobs to exactly that, and here it
   would additionally have *closed* the 1,960.
3. **A delta run never closes anything on the platform it filtered.**

Boards that skipped closure are named on stderr
(`jobs-ingest: N board(s) not reconciled …`, `:1152-1158`) and counted on the
stdout summary line. Keeping the rows open is the safe choice, but it also
means that employer's closure signal is stale and somebody should know.

### `reported_total is None` resolves to complete

Four of six platforms publish no total. Refusing closure for them would
silently retire a working feature for two thirds of the roster, and their
endpoints return the whole board in one response, so a short answer *is* the
answer. Where a total is published, it wins. This is a deliberate and slightly
uncomfortable choice and is commented as such at
`backend/ingest/ats.py:307-317`.

---

## Field mapping

Canonical column nullability is from the `jobs` DDL
(`backend/schema.py:270-294`) plus `posted_at_ts TIMESTAMPTZ` and
`salary_text TEXT` added afterward (`backend/schema.py:436-439`).

Greenhouse, Lever and Ashby mappings are **unchanged from the 2026-07-27
version of this file** except where noted below; that version enumerated the
dropped fields from a live `raw_json` sample and those lists remain accurate.

### Changes to the three existing platforms

| platform | field | before | after |
|---|---|---|---|
| ashby | `salary_text` | hardcoded `None` | `ashby_salary(job)` (`:783`) |
| all three | `company_is_nyc_hq`, `company_is_ai_focused` | `bool(company.get(...))` | `_company_flags()` (`:674-685`) — `None` when the roster has no opinion, which it never does now |

`bool(company.get(...))` was wrong even before the roster changed: it turned
"no opinion" into a confident `False`. Unknown is `None`.

### Why the two company-level flags were retired

They were company-level (headquarters, not where any individual req is based),
`company_ats` has no column for them, and adding one is a schema change out of
scope for task 17. **Nothing reads them** — verified 2026-07-28: the only
references anywhere in the repo are the writes in the six ingest scripts and
the DDL at `backend/schema.py:295-296`. Four of the other five sources already
hardcode `None` (`builtin-nyc.py:364-365`, `hn-hiring.py:322-323`,
`weworkremotely.py:178-179`, `google_jobs.py:116-117`), so this makes the
column uniformly "unknown from this source" rather than half-populated from
one. They are not in `HASH_FIELDS_ATS`, so no existing row's content hash
moves — which also means existing rows keep their old `True`/`False` values
until they change for another reason. After the 2026-07-28 run: 595 greenhouse
and 5 ashby rows carry `NULL`, the rest carry their historical values.

### Workable — `normalize_workable`, `backend/ingest/ats.py:801-836`

| raw field | canonical field | transformation | notes |
|---|---|---|---|
| `shortcode` | `source_id` | `str()` | **not `id`** — the widget carries no numeric id, and `shortcode` is what the public URL and the v3 endpoint both agree on |
| `title` | `title` | none | |
| `city`, `state`, `country` | `location_raw` | joined with `", "`, falling back to `locations[0]` (`:790-798`) | |
| `department` | `department` | none | |
| `url` / `shortlink` | `job_url` | first non-empty | |
| `published_on` / `created_at` | `posted_at`, `posted_at_ts` | first non-empty | |
| `description` | `description_text` | `strip_html()` — real HTML, one unescape | only present because the widget is called with `details=true` |
| `telecommuting` | `location_is_remote` | forces `True` over the regex result | |
| — | `salary_text` | `None` | the widget publishes no salary |
| `education`, `experience`, `function`, `industry`, `employment_type`, `code` | — | dropped | |

### Recruitee — `normalize_recruitee`, `backend/ingest/ats.py:839-866`

| raw field | canonical field | transformation | notes |
|---|---|---|---|
| `id` | `source_id` | `str()` | |
| `title` | `title` | none | |
| `location` | `location_raw` | none | already `"City, Region, Country"` |
| `department` | `department` | none | |
| `careers_url` | `job_url` | none | the employer's own careers domain, not a recruitee.com URL |
| `published_at` / `created_at` | `posted_at`, `posted_at_ts` | first non-empty | |
| `description` + `requirements` | `description_text` | both `strip_html`'d and joined (`:611-617`) | `requirements` is a separate HTML field and is often where the qualifications live |
| `salary` | `salary_text` | `recruitee_salary()` (`:620-637`) → `"EUR 50000-65000 / year"` | one-sided ranges are still rendered |
| `remote` | `location_is_remote` | forces `True` | |
| `updated_at`, `close_at`, `tags`, `open_questions`, `translations`, the ~30 `options_*`/`locations_*` form-config keys | — | dropped | |

### SmartRecruiters — `normalize_smartrecruiters`, `backend/ingest/ats.py:878-917`

| raw field | canonical field | transformation | notes |
|---|---|---|---|
| `id` | `source_id` | `str()` | |
| `name` | `title` | none | **not `title`** |
| `location.fullLocation` | `location_raw` | falls back to `city, region, COUNTRY` (`:869-875`) | |
| `department.label` | `department` | none | the list returns `{}` for employers who do not use departments |
| `postingUrl` | `job_url` | falls back to `jobs.smartrecruiters.com/{token}/{id}` | the list's own `ref` is an **API** URL and must never reach `job_url`; `postingUrl` exists only on the detail response |
| `releasedDate` | `posted_at`, `posted_at_ts` | none | publication date; the only date this API exposes |
| `jobAd.sections.*` | `description_text` | `companyDescription`, `jobDescription`, `qualifications`, `additionalInformation` joined; `videos` skipped (`:589-608`) | **`None` until a detail call has been spent.** That is a real reported state, not a parse failure |
| `location.remote` | `location_is_remote` | forces `True` | |
| — | `salary_text` | `None` | not published on either endpoint |
| `uuid`, `refNumber`, `jobAdId`, `customField`, `industry`, `function`, `experienceLevel`, `typeOfEmployment`, `visibility` | — | dropped | |

### Two mapping details that still bite

**`None` hashes as the string `"None"`, not `""`.** `content_hash` uses
`str(rec[f])` for every field except those in `blank_if_falsy`
(`backend/lib/ids.py:66-72`), and `schema.spec()` passes only
`("description_text",)`.

**`strip_html` truncates at 20,000 characters** (`backend/lib/text.py`), so
`description_text` is capped while `raw_json` is not.

---

## Dedupe & idempotency

Unchanged. The key is still

```
id = sha256(f"{platform}:{company_token}:{source_id}").hexdigest()[:24]
```

(`backend/schema.py:250-262`), and all three components come from somewhere the
remote API cannot move: `platform` is a literal in the normalizer,
`company_token` is now the roster row's token rather than the config file's,
and only `source_id` is the API's. Content-hash branching
(`insert` / `update` / `touch`) is `backend/lib/upsert.py:216-226` and
`HASH_FIELDS_ATS` is unchanged and still FROZEN.

One new duplicate source is handled before the key is computed: **Workable's
per-location expansion**, deduped on `shortcode` in `fetch_workable()`. Without
it, 46 of `braven`'s 66 widget entries would upsert onto rows already written
in the same batch and be reported as `updated`.

### Partial re-run after a crash

Unchanged in shape: `upsert()` commits once per company
(`backend/lib/upsert.py:235`), so companies before the crash persist, the
crashing company's batch rolls back whole, and later companies are never
attempted. The next run re-fetches everything; there is no resume pointer.

New wrinkle: a crash during a SmartRecruiters detail backfill leaves that
company's already-fetched details unwritten, and the next run re-selects the
same undescribed postings — so the budget is spent again on the same rows. That
is correct but not free, and it is the reason the budget is per company per run
rather than global.

---

## Failure modes

### Retry policy

Unchanged — every call goes through `lib/http.py`: 5 attempts, 30s timeout,
`min(60, 2**attempt + jitter)` backoff, `Retry-After` honoured when larger,
`429` and `5xx` retried and every other `HTTPError` re-raised immediately
(`backend/lib/http.py:29`, `:37-44`, `:62`, `:75-81`).

### Malformed or empty payloads

| Input | Behavior |
|---|---|
| any response missing its list key | `.get(key) or []` → empty list; the company contributes nothing and closes nothing |
| Lever response that is not a list | `data if isinstance(data, list) else []` (`:383`) |
| body that is not JSON | `json.loads` raises inside `get_json`; caught per company (`:1100-1104`) |
| Workable v3 unreachable | the whole company fetch fails → no records → no closure, by design (`:437-441`) |
| one SmartRecruiters detail unreachable | that posting keeps its NULL description and is retried tomorrow; the rest of the board proceeds (`:966-975`) |

### The new failure: an empty roster

**`company_ats` holding no admitted rows exits 1** (`:1067-1078`), naming both
remedies. Silence is this system's failure mode, and the previous version could
not hit this case — a 68-entry JSON file cannot be empty, a table can.

### Does a single bad record fail the batch?

- **During `normalize`** — the normalizers now run inside `fetch_company()`,
  which is called inside the `try` at `:1097`. An exception there is caught by
  the `OSError`/`URLError`/`TimeoutError`/`JSONDecodeError` handler **only if it
  is one of those types**; a genuine normalizer bug (`TypeError`, `KeyError`)
  still propagates and kills the run. That is deliberate and matches the
  previous behaviour: a normalizer bug is a code defect, not weather.
- **During `upsert`** — no. Per-record `SAVEPOINT`
  (`backend/lib/upsert.py:198`), errors collected, loop continues.

### Logged vs. swallowed

| Event | Where it goes |
|---|---|
| request count | `ats-requests:` on **stderr, every run** (`:1150`), including a clean one |
| per-record upsert failure | **no longer discarded.** `upsert_checked` (`:1108`) logs `upsert-summary: … errors=N` on every call and raises above the threshold; `run-daily.py` parses that line into its nightly written/dropped record |
| unreconciled board | named on stderr (`:1152-1158`) and counted on the stdout summary |
| tokens admitted as `unvalidated` | counted on the stdout summary (`:1179`) |
| per-company fetch failure | `company_errors`; count on the stdout summary, detail only under `DEBUG_PRINT_KEYS` |
| successful run with zero changes | no **stdout** — the summary is still guarded (`:1172-1173`). `ats-requests:` and `upsert-summary:` still appear on stderr |

### Exit codes

| Condition | Exit | Line |
|---|---|---|
| `DATABASE_URL` unset or Postgres unreachable | 1 | `backend/lib/dbconn.py:203` |
| `company_ats` holds no admitted rows | 1 | `backend/ingest/ats.py:1067-1078` |
| `company_ats` unreadable | 1 | `backend/ingest/ats.py:1060-1065` |
| seed file unreadable, under `--seed-from-json` | 1 | `backend/ingest/ats.py:1043-1050` |
| every company failed **and** at least one error | 1 | `backend/ingest/ats.py:1160-1163` |
| run-level upsert error rate above threshold | 1 | `backend/ingest/ats.py:1185-1189` |
| some companies failed, at least one succeeded | 0 | falls through |

---

## Cassettes

`backend/evals/fixtures/cassettes/`, recorded by
`python3 evals/record_cassettes.py <name>`. All free — public unauthenticated
endpoints.

| cassette | board | what it is for |
|---|---|---|
| `ats-greenhouse` | `kickstarter` | the double-escaped `content` field |
| `ats-greenhouse-no-content` | `kickstarter` | the payload with no `content` key at all |
| `ats-lever` | `finix` | **re-recorded** for the `&limit=&skip=` URL |
| `ats-ashby` | `runway` | **re-recorded** for `?includeCompensation=true`; holds the empty-compensation shape |
| `ats-workable` | `braven` | both endpoints, and the 66-entries-for-20-shortcodes expansion |
| `ats-recruitee` | `jobs` (Tellent) | whole board in one call, with structured salary |
| `ats-smartrecruiters` | `Visa` | list + one detail per posting; `totalFound` to reconcile against |

Two shapes are pinned by **synthetic** cassettes in
`backend/tests/test_ats_new_platforms.py` rather than recorded, because no live
board offers them cheaply: multi-page SmartRecruiters pagination, and a page
that comes back short of the total the API just reported. Ashby's *populated*
compensation string is pinned as a literal copied verbatim from
`vanta` on 2026-07-28 — the smallest Ashby board that publishes compensation is
`writer` at 859 KB, more bytes than one field is worth committing.

---

## External dependencies

`psycopg` is the only third-party import, reached via `lib/dbconn.py`.
Repo-local: `schema`, `ats_sources`, and from `lib` — `dbconn`, `http`,
`state`, `text`, `timeparse.utc_now_str`, `upsert.{upsert_checked,
check_error_rate, UpsertResult, UpsertErrorRate}`.

`backend/ingest/ats_sources.py` imports `ats_discovery` for the status
vocabulary, the `company_ats` column list, its hash fields and its
`make_row_id` — deliberately **the same** definitions `tools/ats-discover.py`
writes through, because two writers with different hash fields would report
each other's rows as changed on every run.

`ingest/ats.py` adds **its own directory** to `sys.path`
(`backend/ingest/ats.py:222-228`) as well as its parent, so `import ats_sources`
resolves when the module is loaded by path rather than run as a script — which
is exactly what `evals/ingest_modules.py` does for every cassette test.

---

## Open questions

**The three new platforms have no tokens.** See "What the roster actually holds
today". Nothing about the ingest path is untested — the cassettes exercise
every fetcher and normalizer against real bytes — but the yield from
workable/recruitee/smartrecruiters is zero until `tools/ats-discover.py` finds
employers on them. Whether to hand-seed a few verified tokens is a discovery
decision with its own provenance discipline (`docs/ats-token-discovery.md:283-292`)
and was deliberately not taken here.

**Ashby salary will not backfill.** See the caveat under Ashby. Existing rows
keep `salary_text = NULL` until they change for some other reason.

**`--delta` has never been run against a real board.** SmartRecruiters is the
only delta-capable platform and the roster admits no SmartRecruiters token, so
the flag is exercised only by tests. The `releasedAfter` filter itself was
verified live against `BoschGroup`.

**Per-company runtime is still not measured.** `run-daily.py` captures each
step's stdout and re-emits it after the step completes, so all steps share one
journal timestamp. The 2026-07-28 standalone run of this script alone is the
only isolated measurement, and its wall clock was not recorded — only its
request count, which is the number task 04 needs.

**Whether `close_missing`'s completeness assumption holds for the three new
platforms is now checked for two of them and not the third.** Workable and
SmartRecruiters reconcile against a published total; Recruitee publishes none,
so its closure rests on the endpoint returning the whole board in one response
— asserted by a test that fails if a second request ever appears, but not
verifiable against the vendor.

**Concurrent `ingest/ats.py` processes** remain undefined behaviour, unchanged:
the `INSERT` has no `ON CONFLICT` clause (`backend/lib/upsert.py:118-126`) and
the `SELECT`/`INSERT` pair is not atomic. Serialization is imposed by `flock`
around `run-daily.py`, not around this script.

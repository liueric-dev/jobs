---
script: backend/ingest/workday.py
written: 2026-07-28
generator: none
---

# Workday CXS ingest

**Hand-written, not generated.** Every other file in `docs/ingest/` carries
`script:`/`commit:`/`generated:` frontmatter and `.claude/CLAUDE.md` says they are
"generated — regenerate, never hand-edit". **No generator exists.** Nothing in the repo
produces those files; the frontmatter is a claim about a tool that was never written,
and task 34 owns the decision to either write the generators or drop the claim. This
file therefore carries no `generated:` line, because it would be false. Everything
below was written by hand at decision time and cites `file:line`.

**Script:** `backend/ingest/workday.py`
**Task:** `docs/tasks/refactor/tranche_three/18-ingest-workday-cxs.md`
**Measured:** 2026-07-28, on branch `webapp-service`, against the four live tenants in
`company_ats`.

---

## Purpose

Pulls open requisitions from the public Workday CXS endpoint of each employer that
`company_ats` records as a valid Workday tenant (`backend/ingest/workday.py:load_workday_tenants`),
and writes them to `jobs` tagged `platform='workday'`.

It is the source `docs/ats-token-discovery.md` says carries the plan: Workday
contributed 4 of the 7 validated tokens and **1,359 of the 1,513 open jobs — 90%** —
of everything task 16 found, and public-feed (greenhouse/lever/ashby) coverage of the
non-tech NYC roster came in at 0.5% of seeded employers.

It differs from every other ingest in this repo in one way, and that difference is the
whole task: **the relevance gate runs upstream, inside ingest**, before the expensive
request. See [The upstream gate](#the-upstream-gate).

---

## Invocation

**Not scheduled yet.** This script is deliberately not in `run-daily.py`'s `STEPS`;
several agents were editing that list concurrently. The line to add, and where:

```python
    "ingest/ats.py",
    "ingest/workday.py",          # <- here: after ats.py, before builtin-nyc.py
    "ingest/builtin-nyc.py",
```

After `tools/ats-discover.py` (`backend/run-daily.py:145`), because a tenant discovered
this morning should be pulled the same night, and after `ingest/ats.py` so the two
board-shaped sources sit together. Before `extract.py`, which is what turns the rows
this writes into facts.

By hand:

```
cd backend && set -a && . ./.env && set +a
python3 ingest/workday.py
DEBUG_PRINT_KEYS=1 WORKDAY_MAX_TENANTS=1 python3 ingest/workday.py
```

### Environment variables

| variable | default | what it does |
|---|---|---|
| `DATABASE_URL` | — | required; `lib/dbconn.py:77-91` refuses to guess |
| `WORKDAY_REQUEST_DELAY` | `1.5` | seconds between outward requests (18-…md:97 asks for 1–2s) |
| `WORKDAY_MAX_DETAIL_PER_TENANT` | `400` | fuse, not a filter — see [The upstream gate](#the-upstream-gate) |
| `WORKDAY_MAX_TENANTS` | all | stop after N tenants; for testing |
| `DEBUG_PRINT_KEYS` | off | per-tenant tracing on stderr |

### Measured runtime, 2026-07-28

A real end-to-end run, four tenants, sequential, 1.5s apart, from this host's
residential IP:

```
workday-ingest: 4/4 tenants ok (0 blocked, 0 shortfall, 0 failed), seen 1359,
                detail-fetched 329 (24% of seen)
workday-ingest: gate-surviving 14, 181 new, 0 updated, 148 unchanged, 1 closed,
                0 old-closed pruned, 0 record(s) dropped, 861.0s wall-clock,
                profiles=frontend,tech
workday-ingest:   Memorial Sloan Kettering (workday:msk@wd108):     88/88,   59 (67%), drift +0, 118.2s
workday-ingest:   Moelis & Company (workday:moelis@wd1):            42/42,   30 (71%), drift +0,  79.9s
workday-ingest:   NewYork-Presbyterian (workday:nyp@wd1):         363/366,  210 (58%), drift +3, 465.2s
workday-ingest:   Nordstrom (workday:nordstrom@wd501):            866/866,   30 ( 3%), drift +0, 197.6s
workday-ingest: ALERT NewYork-Presbyterian: `total` said 366 and 363 distinct postings
                were collected (+3) -- under one page, so the board moved mid-walk
                rather than a page being lost
```

**~400 requests, 861s, 329 rows in the table, 0 dropped, 0 blocked, 1 closure detected.**

This is the third run of the day and the first with both live-found location and
reconciliation fixes in. The two earlier runs are worth recording because the deltas
are the evidence:

| run | detail-fetched | gate-surviving | wall-clock | what changed |
|---|---|---|---|---|
| 1 | 149 (11%) | 4 | 462s | first end-to-end run |
| 2 | 122 of 3 tenants | 4 | 420s | Nordstrom **shortfall**: `total` 867, collected 865 — ordinary mid-walk churn, fatal under a strict check |
| 3 | **329 (24%)** | **14** | **861s** | `locationsText` facility-name fix; one-page reconciliation threshold |

**Run 1 was silently dropping 161 of NewYork-Presbyterian's postings** — real NYC
hospital jobs — and reporting `4/4 tenants ok` while doing it. See
[Field mapping](#field-mapping).

**Against task 04's budget:** there is no budget to check against. Task 04
(`docs/tasks/refactor/tranche_one/04-quota-baseline.md`) **landed in `c3275be`** — this
file originally said it was `todo`, because every task file's `**Status:**` header was
stale until 2026-07-28. What is true is the narrower point: 04 produced no standalone
`docs/` report. Its findings went into `backend/docs/SCORING.md`, so the wall-clock
baseline document this task was asked to report against does not exist where one would
look for it. What does exist is task 05's figure quoted inside 04's own
file: the pipeline currently admits **43 eligible postings/day** (80/day over the last
seven complete days). This source adds **~14 minutes** of nightly window at four
tenants, and that scales with tenant count — at the ~50 tenants 18-…md:97 anticipates
it would not fit a nightly window sequentially at 1.5s, and the delay, the concurrency
or the per-tenant cadence will have to change. That is a real constraint and it is not
solved here.

**Read `gate-surviving 14` carefully — it is the most important number here and it is
not a yield.** The full gate is the *current* `config/relevance.json`, which is
SWE-shaped: two active profiles named `frontend` and `tech`, `title_include` built from
"engineer", "developer", "SRE", "machine learning". Fourteen of 329 hospital, bank and
retail postings match it, which is exactly right and exactly useless — those profiles
are not who this source exists for. The task file's 80–200 relevant postings/day
assumes the Pursuit retarget (`config/relevance.json` and `config/persona.json`
rewritten for entry-level, AI-adjacent, all-industry, NYC). **This number must be
re-measured after that retarget, and it is not evidence about the source until it is.**

### The yield against the population this source exists for

The `14` above is not the answer, and neither is a deferral. Measured on the final run,
against the population task 18 exists to find — entry-level, AI-adjacent, NYC, any
industry:

| | of 329 detail-fetched |
|---|---|
| AI vocabulary in the **title** | **0** |
| entry-level signalled | 30 (by `seniority_guess`) · 71 (by title regex) |
| AI vocabulary in title **or** description | 21 |
| **entry-level AND AI-signalled** | **1** (by `seniority_guess`) · **3** (by title regex) |

Two methods are shown because they disagree on the margin and neither is a gate result: a
Pursuit-shaped `config/relevance.json` does not exist yet (task 13), and inventing one to
measure against would be a fabricated measurement. The first row does not depend on the
method at all — **zero of 329 postings from four Workday tenants have any AI vocabulary in
the title.**

**Extrapolated to the ~50 tenants `18-ingest-workday-cxs.md:97` anticipates: ~12/day,
against an estimate of 80–200.** That extrapolation is generous — it assumes 46 more
tenants exist and behave like these four, and `company_ats` currently holds four.

Caveats, so this is not over-read in either direction: **n = 4 tenants**, health/finance/
retail, one night. Task 05 measured company-level false positives as the dominant failure
mode, so a looser Pursuit gate would raise this count and lower its precision — 6.7%
hand-checked is the relevant prior.

**What the run does establish, independent of any persona:** ~1,360 postings/night
reachable, 24% detail-fetch cost, 0 blocks, 0 records dropped, closure detection working.
The plumbing is sound. What did not survive contact is the premise that Workday carries the
plan's volume — and the shape of that finding is not "the boards are hard to reach" but
**these employers are not posting these roles.**
What the run does establish is the part that does not depend on the persona: ~1,360
postings reachable per night from four tenants, at 24% detail-fetch cost, with no
blocks.

**Without the upstream gate the same run would be 1,359 detail requests — 34 minutes of
detail fetching for four tenants, against the 8 it actually spent.** That is the cost profile the gate exists to avoid,
and it grows linearly with the tenant count that task 16's backlog is expected to
produce.

---

## The endpoint

```
POST https://{tenant}.{dc}.myworkdayjobs.com/wday/cxs/{tenant}/{site}/jobs
Content-Type: application/json

{"appliedFacets": {}, "limit": 20, "offset": 0, "searchText": ""}
```

`tenant`, `dc` and `site` are three separate columns in `company_ats`
(`backend/migrations/migrate_company_ats.py:121-126`) and all three are read, never
guessed. The bodies are serialized with `sort_keys=True`
(`backend/ingest/workday.py:list_body`) because `evals/cassettes.py:374` keys a POST
interaction on the sha256 of its body — a different key order is a different request.

Detail, one per surviving posting:

```
GET https://{tenant}.{dc}.myworkdayjobs.com/wday/cxs/{tenant}/{site}{externalPath}
```

### What the list response actually carries — the task file is wrong here

`18-ingest-workday-cxs.md:27-30` says each list posting has "`title`, `locationsText`,
`externalPath`, `startDate` (native ISO — no 'posted 3 days ago' parsing), and
`jobRequisitionLocation` with structured fields."

Measured against `msk.wd108` live and against the recorded `nvidia.wd5` page in
`backend/evals/fixtures/cassettes/ats-validation.json`, the **list** carries:

```json
{"title": "Research Scholar",
 "externalPath": "/job/New-York-NY/Research-Scholar_98479",
 "locationsText": "New York, NY",
 "postedOn": "Posted Yesterday",
 "remoteType": "Hybrid",
 "bulletFields": ["98479"]}
```

No `startDate`. No `jobRequisitionLocation`. `postedOn` is exactly the relative string
the task file says this source avoids. Both of the missing fields are on the **detail**
document, alongside `location`, `externalUrl`, `timeType` and `jobDescription`.

This is not cosmetic. It means:

- `posted_at` — which is in `HASH_FIELDS_ATS` (`backend/schema.py:131`) and therefore
  frozen — can only be filled for a posting we detail-fetched. `normalize_listing`
  leaves it `None` and `apply_detail` sets it from `startDate`
  (`backend/ingest/workday.py:normalize_listing`, `:apply_detail`).
- the relative `postedOn` goes to the **unhashed** `posted_at_ts` instead, which
  `backend/schema.py:188-214` documents as the correct home for a value re-derived on
  every run.

`backend/tests/test_workday_fixtures.py::TestTheRecordingContradictsTheTaskFile`
asserts both fields are absent, so if Workday ever adds them the test says so.

---

## Failure modes

Seven, of which **four** are documented in the task file and **three** were found by
running the code against live tenants. **Every one returns HTTP 200 and loses data.**
Each has a replayable fixture and a test that fails loudly.

That ratio is the lesson worth keeping from this task: the four constructed fixtures
encode the shapes the task file *describes*, so they could not have caught any of the
last three. Fixtures written from a specification test the specification.

| # | failure | what it looks like | detector | fixture |
|---|---|---|---|---|
| 1 | `limit` > 20 | empty `jobPostings`, HTTP 200, no error — byte-identical to "no more results" | `_check_page_limit`, called from `list_body`, so every request path passes through it | `workday_fixtures.limit_over_20()` |
| 2 | a throttled page read as the end | walk stops early, exit 0; one published account lost 1,960 of NVIDIA's 2,000 | `lib/http.py:75-81` retries 429/5xx, then `collect_postings` reconciles against `total` and raises `Shortfall` | `throttled_page()` |
| 3 | wrong data-centre prefix | **HTTP 422** with a JSON error body (recorded); reads as one unreachable tenant among fifty | `dc` is read from `company_ats`; there is no `wd`-literal in the module and a test greps for one | `prefix_assumed()` |
| 4 | the 10,000-result cap | walk ends at 10,000 looking finished, `total` says more | reconciliation detects; `facet_slices()` + merge fixes, or `ResultCapUnsliceable` is raised | `result_cap()` |
| 5 | **`total` on the first page only, and offsets past the end wrap** | a *complete* walk reconciles against 0 and is reported as a shortfall; a loop waiting for an empty page never terminates | first `total` is latched permanently; a page adding no new `externalPath` ends the walk | `total_only_on_first_page()` |
| 6 | **`locationsText` is not always a location** | a hospital system's whole board dropped upstream, run reports `4/4 tenants ok` | `location_flags()` answers *unknown* for anything not recognisably a place | live only — see [Field mapping](#field-mapping) |
| 7 | **the board moves while it is being walked** | strict reconciliation turns ordinary churn into a shortfall, and a shortfall skips the tenant entirely | the threshold is one **page**, the unit of the failure being caught; smaller disagreements are reported as `drift` | `test_a_board_that_moves_mid_walk_is_drift_not_a_shortfall` |

### Failure 5, in detail — it is not in the task file and it bit first

Measured 2026-07-28 against all four live tenants. `msk.wd108`:

| offset | `total` | postings |
|---|---|---|
| 0 | **88** | 20 |
| 20 | **0** | 20 |
| 40 | **0** | 20 |
| 60 | **0** | 20 |
| 80 | **0** | 8 |
| 100 | **88** | 20 ← *the wrap: page 0 again* |

`total = payload.get("total", total)` — the obvious spelling, and the first one written
here — therefore does two things at once: it ends the walk at page two (because
`offset >= total` with `total == 0`) and then reconciles the truncated result against
zero. All four tenants failed with `collected 40 of 0`.

Neither half was catchable from the fixtures. The four constructed cassettes repeat
`total` on every page because the task file's documented shape says it does, and
NVIDIA's real recording is a single page, which has no later page to disagree with.
**Only a live run could have found this**, which is the general lesson worth keeping:
a fixture written from a specification tests the specification.

The wrap matters independently. Textbook pagination ("loop until a page comes back
empty") does not terminate against this endpoint — it cycles, forever, at one request
per delay, against a stranger's server. `collect_postings` breaks when a page
contributes no new `externalPath`, and additionally when a page is shorter than
`limit`; the reconciliation still runs afterwards, so a short page that was in fact a
truncated one raises rather than passing.

### Failure 3's real status code is 422, not 404 — **fixed 2026-07-31**

~~`prefix_assumed()` models a wrong data centre as a 404 with an HTML body.~~ It now
models the recorded 422. What this section said before the fix, kept because it is
half of what was wrong:

> The recorded live probe (`ats-validation.json`, `nvidia.wd1`) shows Workday
> answering **HTTP 422** with a JSON `{"errorCode":"HTTP_422", …}` body. The
> consequence is identical — both are permanent for `lib/http.py:76`, so neither is
> retried and both surface — and the fixture's point (a wrong prefix is one more failed
> tenant in a fifty-tenant loop) stands. Recorded here rather than silently corrected in
> the fixture, because the fixture is task 09's and its own docstring is explicit that
> it encodes the documented shape rather than the observed one.

**The status code was the smaller error.** The old docstring also named the wrong
*mechanism*: it said the HTML body would be json-decoded into a `JSONDecodeError`,
"which every ingest script in this repo catches". No decode ever happens. Traced:

- `evals/cassettes.py:448` — `if interaction.status >= 400:` — raises `_ReplayHTTPError`
  at the urlopen seam, as live urllib does for any 4xx. The body is still unread.
- `lib/http.py:76-77` — `if e.code != 429 and not (500 <= e.code < 600): raise
  # permanent -- surface immediately`. 422 is neither, so it surfaces on attempt one.
- `ingest/workday.py:371` — `return json.loads(http.get_text(` — `json.loads` is never
  reached. **The body is never decoded**, so no `JSONDecodeError` is reachable here for
  *any* ≥400 response, HTML or JSON. The recorded body happens to parse cleanly anyway.
- `ingest/workday.py:406` against `:237` (`BLOCKED_STATUSES = (401, 403, 406, 429,
  451)`) — 422 is absent, so `:409` raises `Shortfall`, not `TenantBlocked`.
- `ingest/workday.py:998` isolates it as `status='shortfall'`; `:1184` counts it and
  `:1194` exits 1.

So under the real loop a wrong prefix is **loud**. The silence is a property of the
naive shape only — catch `HTTPError`, `break`, zero postings and `total=None`, which is
`ingest/workday.py:872`'s "indistinguishable from a tenant with no open roles". The
fixture's conclusion always held; only its stated route did not.

**No 404 case was kept.** `ingest/workday.py:101` and `:872` both say "404 or 422", but
no Workday host in any cassette in this repo has answered 404 — the four other recorded
404s in `ats-validation.json` are the greenhouse, icims, recruitee and workable
no-such-tenant probes. A 404 interaction would also discriminate nothing: both statuses
are permanent at `lib/http.py:76` and both absent from `BLOCKED_STATUSES`, so they take
a byte-identical path to the same `Shortfall`. The 422 constants are *transcribed* from
the recording rather than lifted at call time, so the fixture still builds with no
cassette on disk; `TestTheRecordedRefusalIsWhatTheFixtureEncodes` in
`backend/tests/test_workday_fixtures.py` diffs each constant against the bytes, so drift
fails loudly.

### Exit codes and what is loud

- `0` — normal, **including a night that wrote nothing**. The summary line prints
  unconditionally (`workday-ingest: …`), unlike `ingest/ats.py:383-390` which stays
  quiet on a clean night. For this source a clean night and a blocked night produce the
  same zero, and CLAUDE.md's rule is to alert on volume, not errors.
- `1` — every tenant failed, or the run-level upsert error rate exceeded
  `lib/upsert.py:288`'s threshold.
- `workday-ingest: ALERT …` lines, one per condition: a `valid` tenant that returned
  zero postings, a blocked tenant, a shortfall, a capped detail budget, a
  detail-fetched/seen ratio at or above `RATIO_ALARM` (0.80), and any `company_ats`
  Workday row with no dc/site.

A **shortfall writes nothing at all** for that tenant — no upsert and no
`close_missing`. A partial list plus closure detection would mark every posting on the
missing pages as closed, turning one lost page into hundreds of wrong closures. Same
reasoning as the safety valve at `backend/ingest/ats.py:91-95`.

---

## The upstream gate

The architectural half of this task, and the reason it is affordable.

A hospital system runs 2,000 open requisitions. One detail request per posting is 2,000
requests per tenant per night; across the tenants task 16's backlog will produce, the
detail fetches dominate the nightly window. So the **list** response — title and
location and nothing else — decides who gets a detail request.

### Measured, 2026-07-28, against the current `config/relevance.json`

| tenant | listed | detail-fetched | ratio |
|---|---|---|---|
| Nordstrom | 866 | 30 | 3% |
| NewYork-Presbyterian | 363 | 210 | 58% |
| Memorial Sloan Kettering | 88 | 59 | 67% |
| Moelis & Company | 42 | 30 | 71% |
| **total** | **1,359** | **329** | **24%** |

The task file predicted "two thousand requests becomes perhaps a hundred and fifty".
1,359 → 329 — the right order of magnitude, and higher than the first run's 149 because
that run was wrong (see the location finding below), not because the filter loosened by
choice.

The ratio splits cleanly by employer geography. Nordstrom is national, so the location
half does nearly all the work (3%). MSK, Moelis and NYP are single-city NYC employers,
so location cuts nothing and only the exclusion lists apply — 58-71%, which is the
expected shape for a one-city employer and the reason `RATIO_ALARM` sits at 0.80 rather
than something tighter.

Of those 329, **14** clear the full gate under the current SWE-shaped profiles — see the
warning under [Measured runtime](#measured-runtime-2026-07-28). The upstream filter and
the full gate are answering different questions and both numbers are logged nightly for
that reason.

A tenant creeping toward 1.0 means the filter has stopped working, and the alert says
so (18-…md:86-88).

### One implementation, two callers — and why not the one the task file asked for

`18-ingest-workday-cxs.md:77-79` says to "add a function that evaluates a
title/location pair in **Python** against the same config `tier_sql` compiles to SQL."
That was not done, deliberately, for two reasons:

1. **It would be a second implementation, not a second caller.** `relevance.py`
   compiles config to **Postgres** regexes. In Postgres `\y` is a word boundary and
   `\b` is BACKSPACE; in Python's `re` it is the exact opposite — `\y` does not compile
   at all and `\b` is a word boundary. A Python evaluator of `config/relevance.json`
   would not merely duplicate the matcher, it would **disagree with it**, silently, on
   precisely the patterns CLAUDE.md names a landmine. `config/relevance.json`'s
   `_regex_dialect` note records that the first version of that file used `\b`
   throughout and buried "ML / LLM Engineer" in tier 3.
2. `relevance.py` was owned by another agent for the duration of this task and could
   not be edited in any case.

What was done instead: `relevance.tier_sql` is a **SQL compiler**, and its
`table_alias` parameter (`backend/relevance.py:189`) exists so the compiled predicate
can point at something other than `jobs`. So the gate builds the list rows into a
derived table and runs the real predicate against them **in Postgres, before they are a
table at all** (`backend/ingest/workday.py:_tiers`):

```sql
SELECT (<tier_sql for profile 0>), (<tier_sql for profile 1>)
FROM unnest(%(c_title)s::text[], %(c_company_name)s::text[], …)
     WITH ORDINALITY AS c(title, company_name, description_text,
                          location_is_nyc, location_is_remote, n)
ORDER BY c.n
```

`unnest` of typed arrays rather than a `VALUES` list, because a `VALUES` list of
literals types an all-NULL boolean column as `text` and the predicate fails to parse —
and `description_text` is NULL for every row here by construction.

One matcher, one dialect, one engine, two callers. Cost: one query per tenant.

### Why the filter is loose, and exactly how loose

Task 10's gate is description-first, and at list time there is no description. So
filtering tightly here "would discard exactly the postings this refactor exists to
find, since their titles are the uninformative part" (18-…md:80-85). "Operations
Coordinator" at a hospital is the Pursuit target population and no `title_include`
regex will ever match it.

The filter therefore **never requires `title_include` to match**. It drops a posting
only on evidence that survives having no description:

- an **exclusion** fired — `title_exclude` or `company_exclude`.
  `config/relevance.json`'s `_title_exclude_note` says that list is "narrow and
  specific on purpose … Exclude only what is unambiguous", which is what makes it safe
  against a bare title.
- the location is **known** and is not one this deployment accepts.

Mechanically (`backend/ingest/workday.py:_loose_cfg`, `:upstream_survivors`): substitute
a title pattern matching everything for `title_include`, so `tier_sql` compiles the
exclusion half of its `row_ok` predicate on its own — emptying the include list will
not do, because `relevance.py:210-215` nests the exclusion inside `if include:`. Then,
per profile:

| tier under the loose config | meaning | decision |
|---|---|---|
| 3 | an exclusion fired | drop |
| 1 | kept, location accepted | **fetch** |
| 2 | kept, location not accepted | **fetch only if the list could not say where the job is** |

A posting survives if **any** active profile would keep it — `relevance.py:276-292`'s
argument (a shared asset must not be shaped by whoever happens to be profile #1),
applied one step earlier to a shared detail fetch.

### "Neither-but-unknown" is a real value, not a missing one

Workday writes `"2 Locations"` instead of a place when a requisition spans several, and
`locationsText` is sometimes absent. `text.classify_location` — the function every
other source uses — returns `(False, False)` for those, which **states that the job is
known not to be in New York**. `location_flags()` returns `(None, None)` instead
(`backend/ingest/workday.py:location_flags`), and the gate keeps a tier-2 posting only
when the location is `None`. Without this, a placeholder string would be enough to drop
a posting.

### `MAX_DETAIL_PER_TENANT` is a fuse, not a filter

400 detail fetches at 1.5s is already ten minutes for one tenant. Hitting the cap is
reported as an `ALERT`, never as a normal night, because reaching it means the gate has
broken rather than that the board is large.

---

## What is stored, and what is only counted

**Only detail-fetched postings are written to `jobs`.** 18-…md:110-113 settles it: "a
posting you never detail-fetched is still a posting you *saw*, so track seen-set
membership from the list response, not from what you stored." So `close_missing`
(`backend/schema.py:674`) is fed the **full** seen set — every `externalPath` the list
returned — while the upsert carries only the survivors.

The alternative, storing every listing row and filling descriptions on a later night,
was rejected for a concrete reason: a listing-only record has `description_text=None`
and `posted_at=None`, both of which are in `HASH_FIELDS_ATS`, so re-writing one over a
row detail-fetched on an earlier night would blank both and churn the row between two
shapes forever.

### Field mapping

| `jobs` column | from | note |
|---|---|---|
| `platform` | literal `workday` | |
| `company_token` | `company_ats.token` | the tenant |
| `company_name` | `company_ats.employer_name` | |
| `source_id` | list `externalPath` | **not** `bulletFields[0]` — see below |
| `title` | list `title` | |
| `location_raw` | list `locationsText`; detail `location` only when the list gave a placeholder | see below — the list wins, and that is not the obvious choice |
| `department` | — | Workday's list carries none |
| `job_url` | detail `externalUrl`, else `{host}/en-US/{site}{externalPath}` | Workday's own spelling omits the locale segment; preferring it avoids storing an invented value in a hashed column |
| `posted_at` | detail `startDate` (ISO) | `None` if never detail-fetched |
| `posted_at_ts` | detail `startDate`, else the parsed list `postedOn` | unhashed, safe to recompute (`schema.py:188-214`) |
| `salary_text` | — | not published |
| `seniority_guess` | `text.guess_seniority(title)` | |
| `location_is_nyc` / `location_is_remote` | `location_flags()` | **nullable** — see above |
| `company_is_nyc_hq` / `company_is_ai_focused` | `False` | `company_ats` records employers, not their HQs or their industry, and a guess would land in a hashed column |
| `description_text` | `text.strip_html(detail.jobPostingInfo.jobDescription)` | Workday serves real HTML, so one unescape — same as Lever/Ashby (`ats.py:261`), not Greenhouse's double |
| `raw_json` | `{listing, jobPostingInfo}` via `text.bounded_json` | 20,000-char ceiling; descriptions run 30–60 KB |

**`locationsText` is not always a location, and this was the most consequential thing
the live runs found.** NewYork-Presbyterian's location vocabulary is a **facility
hierarchy**, not a geography:

```
'NYP/Columbia University Irving Medical Center' | Clinical Nurse I - RN - Operating Room
'NYP/Brooklyn Methodist Hospital'               | Registered Nurse (RN) - Interventional Radiology
'NYP/Weill Cornell Medical Center'              | Physicist – Radiation Oncology
```

Two of those three name a New York hospital without naming New York, so
`text.classify_location` returns `(False, False)` — and the first version of the
upstream gate read that as **"known not to be in New York"** and dropped them. That is
precisely the failure 18-…md:80-85 exists to prevent, arriving through the location
half of the filter instead of the title half, and it was invisible: the run reported
`4/4 tenants ok`.

`location_flags` now answers **unknown** for any string that is not recognisably a
place. The discriminator is the comma, which is the shape every real place in this data
has — `New York, NY`, `Boise, ID`, `US, CA, Santa Clara`, `Israel, Yokneam`. A bare
`Seattle` is therefore treated as unknown and costs one detail fetch rather than a lost
posting; that asymmetry is deliberate. `apply_detail` additionally combines the list's
and the detail's answers so knowledge can only be **added** — true beats false beats
unknown — and prefers the list's `locationsText` unless the list gave a placeholder.

**`source_id` is `externalPath`, not the requisition id.** The recorded NVIDIA page
carries `…/System-Speed-and-Reliability-Co-Design-Engineer_JR2018911-1` whose
`bulletFields` is `["JR2018911"]` — a second posting of one requisition. Keying on the
req id would collapse the two onto one row through `schema.make_job_id`.

### Writes

Every write goes through `upsert_checked` (`backend/lib/upsert.py:303`), never
`upsert()`, so per-record failures are counted and the `upsert-summary:` line lands in
`run-daily.py`'s nightly written/dropped record. `UpsertResult.__iter__` yields three
values and not `.errors`; CLAUDE.md names that a landmine and a test in
`backend/tests/test_workday_ingest.py` greps this module for the bare-tuple shape.

---

## Politeness, and the block rate

18-…md:90-98. Plain HTTP from this host's residential IP, sequential, one request per
`WORKDAY_REQUEST_DELAY` (1.5s), no scraping service, an honest `User-Agent`
(`lib/http.py:27`). Tenants answering 401/403/406/429/451 are recorded as `blocked` and
**not retried** — retrying into a refusal is how a probe becomes an incident, the rule
`docs/ats-token-discovery.md` adopted for the discovery pass. Tenants requiring a login
are inaccessible; they are counted, not retried (18-…md:104-106).

**Block rate: not measured.** 18-…md:128 requires "block rate measured over one week …
before any escalation". Three runs exist, all on 2026-07-28: **0 of 4 tenants blocked, 0
shortfalls, 0 detail-fetch errors, ~1,000 requests across three runs**. That is a single day's observation
from one IP and explicitly not a rate.
The script prints a block-rate line on any run with a refusal or a failure, and it says
so in the line itself. **No escalation to Scrapfly or any other scraping service is
authorized until a week of runs exists**, and when it does the escalation is per-tenant,
not global.

---

## Fixtures and tests

| file | what it holds |
|---|---|
| `backend/evals/workday_fixtures.py` | the four constructed failure cassettes (task 09), plus `recorded_list_page()` and `total_only_on_first_page()` added by task 18 |
| `backend/tests/test_workday_fixtures.py` | drives the real `collect_postings` / `collect_tenant` through all five failures, plus the recorded page |
| `backend/tests/test_workday_ingest.py` | the upstream gate (needs a scratch database), normalization, tenant selection, the ratio accounting |

`recorded_list_page()` is **real bytes** and is not a new recording: task 16's
`ats-validation` cassette already probes `nvidia.wd5` with exactly this request body
(verified — the sha256 of `list_body(0)` equals the recorded
`request_body_sha256`), so the interaction is lifted from it rather than recording a
second one against a stranger's board. It is the only fixture here that can falsify the
documented shape, and it does; see the endpoint section.

`total_only_on_first_page()` is registered in `FIXTURES_FOUND_LIVE`, apart from the
task file's four in `FIXTURES`. The provenance difference is the point: four are a
specification of documented traps, the fifth is an observation of an undocumented one.

~~**A recording recipe is still owed.**~~ **Delivered — verified 2026-07-31.** The
claim above stood for three days after it stopped being true; it is struck rather than
deleted so a reader working from the old text can see what changed.

`record_workday_cxs()` exists at `backend/evals/record_cassettes.py:501`, with
`WORKDAY_CXS = ("msk", "wd108", "MSKCC_Careers_Primary")` at `:498` — all three
coordinates, because `18-ingest-workday-cxs.md:54` forbids guessing the data centre.
The recording is committed at `backend/evals/fixtures/cassettes/workday-cxs.json`
(recorded `2026-07-28T18:48:09Z`) and is asserted on by
`backend/tests/test_workday_cxs_cassette.py`, seven tests.

**It delivered half of what the claim promised, and the half it delivered is the one
that mattered.** The recording holds **four** list pages, not the ~5 predicted: the
board was at **79** postings when recorded, not the 88 the claim quotes — three full
pages and a short one of 19. Boards move, which is why nothing here reconciles against
a stored count.

- **`total`-on-the-first-page-only is now RECORDED.** The four pages answer
  `total` 79, 0, 0, 0. That is failure 5's first half in live bytes, and
  `record_workday_cxs()` guards it: it refuses to record unless
  `totals[0] and not any(totals[1:])`, so a tenant that quietly starts reporting `total`
  on every page cannot silently retire the evidence for the latch at
  `ingest/workday.py:463-475` (`if total is None:` … `total = payload.get("total")` —
  "First page wins, permanently").
- **The wrap is still constructed, deliberately.** Offsets past the end returning page
  one again — failure 5's *second* half — is not in the recording, and
  `workday_fixtures.total_only_on_first_page()` remains the only fixture for it. The
  recipe's own docstring gives the reason: provoking it means issuing one request past
  the end of a stranger's board purely to record a pathology, and `collect_postings`
  never issues that request (the `fresh == 0` guard at `ingest/workday.py:490` stops the
  walk first). Recording a request the pipeline does not make is the one thing
  `record_cassettes.py`'s own docstring forbids.

So `total_only_on_first_page()` is no longer the only evidence for failure 5, but it is
still the only evidence for the wrap, and it stays in `FIXTURES_FOUND_LIVE` for that
reason.

---

## Open questions

- **The 10,000-result cap has never been exercised against a real board.** The largest
  live tenant is Nordstrom at 868. `facet_slices()` is tested against the *facets block*
  of the recorded NVIDIA page — real advertised facet parameters, values and counts —
  but the slice-and-merge path has only ever run against constructed pages. The first
  tenant over 10,000 will be the first real test, and it will either work or raise;
  it will not silently under-report.
- **Whether the exclusion lists are the right upstream filter for a Pursuit-shaped
  config.** They are measured here against the current SWE-shaped
  `config/relevance.json`. `docs/pursuit-gate-volume.md` found company-level false
  positives to be the dominant failure mode; when the config is retargeted, the
  detail-fetched/seen ratios in this document should be re-measured, not assumed.
- **Whether `postedOn` should feed `posted_at` for listing-only rows.** It cannot today
  because those rows are not stored. If that decision is ever revisited, the relative
  string must go through the `sticky` mechanism (`backend/schema.py:228-247`), never
  straight into the hashed column.

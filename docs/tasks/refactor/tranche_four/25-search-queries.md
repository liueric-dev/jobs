---
kind: task
written: 2026-07-28
generator: none
---

# 25 — Search queries

**Status:** todo. **Depends on:** ~~23, 24,~~ **11**; 23 for two bullets only. **Blocks:** 28, 32.

> **THE ARROW TO 24 IS FALSE, AND TASK 24'S OWN FILE SAYS SO. Corrected 2026-08-02.**
> [`24-revive-contributor-api.md`](24-revive-contributor-api.md)`:92-94` reads *"Task 25
> fills that queue … Until then, seed manually from task 05's vocabulary."* — 24 expects to
> be seeded **by** 25, not to precede it. Nothing here reads the contributor API: the
> `search_queries` and `search_query_watchers` tables, the normaliser, the watcher counts,
> the per-`role_track` seeding and the decay all stand alone. Only *"a query submitted twice
> costs one provider call"* needs **a** provider, and any of the two shipped adapters is one.
>
> **23 is real for two bullets and no more** — *"one provider call"* and *"results route
> through the full gate"*. It is `todo` and `backend/serp/` does not exist, so those two
> wait; the rest does not.
>
> **11 is real and is satisfied** (`da4942c`). `role_track` is a column
> (~~`../../../../backend/schema.py:542`~~ **`:649`, and it is on `job_facts`, not
> `jobs` — corrected 2026-08-02**) with a nine-value vocabulary
> (`../../../../backend/extract.py:305-308`), so *"seed one query per `role_track`"* has
> something to seed from today. **It is NULL on every pre-task-11 row**, which the seeding
> has to expect rather than treat as an empty vocabulary.
>
> The column is added by `dbconn.add_missing_columns(conn, FACTS_TABLE, …)`
> (`../../../../backend/schema.py:646-650`), so it is `job_facts.role_track`. Two things
> follow that a reader of the old citation would get wrong: it is a per-POSTING extracted
> fact rather than a column on the listing row, and it is **not in the `jobs_app` view**
> (`../../../../backend/schema.py:1056-1104` selects `f.role_archetype` and never
> `f.role_track`), so nothing reaches a response body through it today. Neither matters
> for the seeding bullet — the vocabulary is what is seeded from, not the column — and
> widening the view is task 30's, not this one's.
>
> `../../../../frontend/js/tracks.mjs:5` carries the same wrong citation
> (*"stored on `jobs.role_track` (backend/schema.py:542)"*). Reported, not edited:
> `frontend/` is another stream's.

Make the query a first-class object. It is what turns a quota problem and a community
feature into the same thing.

## The insight this task exists to exploit

Thirty Builders, one cohort, one city, overlapping target roles. Their queries will
collide constantly.

Cache on `(normalized_text, location, date)` and the fifth Builder to search "AI
operations NYC" costs nothing — SerpApi explicitly does not bill cached searches.
Against ~280 renewable searches/day and ~90/day of demand, caching plausibly turns 3×
headroom into 10×.

**That is the pooling feature paying for itself.** Not pooled credits — pooled
*results*. Worth stating plainly because the earlier framing of this project was
credit-pooling, and this is the version that is both more defensible and more
valuable.

## Schema

```sql
search_queries (
    id                    BIGSERIAL PRIMARY KEY,
    normalized_text       TEXT NOT NULL,
    location              TEXT NOT NULL,
    chips                 JSONB,          -- Google Jobs filter chips
    first_requested_at    TEXT NOT NULL,
    last_run_at           TEXT,
    run_count             INTEGER NOT NULL DEFAULT 0,
    watcher_count         INTEGER NOT NULL DEFAULT 0,
    provider_last_used    TEXT,
    result_count_last_run INTEGER,
    source                TEXT NOT NULL,  -- 'builder' | 'seeded' | 'track'
    UNIQUE (normalized_text, location)
)

search_query_watchers (
    query_id, profile, created_at,
    UNIQUE (query_id, profile)
)
```

Watchers are a separate table so the count is derived, and so `search_queries` carries
no per-Builder identity. That matters for the visibility decision below.

### Normalisation

Lowercase, collapse whitespace, strip punctuation, sort nothing (word order carries
meaning in job search). Keep it boring and deterministic — a normaliser that is too
clever produces cache hits between queries that mean different things, which is worse
than a cache miss.

Store the raw text a Builder typed alongside the normalised form, for display.

## Anonymous by design

Per the visibility decision: postings are pooled, **nobody knows who is looking for
what**.

So the UI shows "4 Builders are watching this search" and never who. `watcher_count`
is exposed; `search_query_watchers` is not. Applications stay private entirely — in a
cohort competing for entry-level roles, seeing who else applied is discouraging at
best.

This is the same `visibility` distinction task 27 encodes on `job_events`. Keep the
two consistent; two different answers to "what is shared" is how a privacy promise
gets broken by accident.

## Asynchronous

Do not block a Builder on a scrape. A query is submitted, queued, run on the nightly
cycle or by a short-interval worker, and results appear when they land.

Three reasons, in order of importance:

1. The contributor API (task 24) is inherently deferred — results arrive when some
   Builder's worker claims the query.
2. Batching across users is what makes the cache work. Collect queries, dedupe, then
   spend quota once.
3. A user waiting 20 seconds on a scrape is a worse experience than one who submits a
   search and finds results next time they open the app.

## Everything routes through the pipeline

Search results go `jobs` → `relevance.py` → `extract.py` → `match.py`, exactly like
any ingest source. **No shortcut to display.**

Google Jobs is precisely where the relister junk originates. `config/relevance.json`
already carries six excluded relist sites and a `description_exclude` for the
`'reputed company'` placeholder text that appears when relisters scrub the employer
name — those entries exist because this source fed them in. A user-initiated search
that bypassed the gate would surface the exact postings the curated pipeline was built
to suppress, and it would do it to people with no industry pattern-matching to catch
it.

## Seeding

Builders who do not yet know what role they want cannot write a good search term. That
is the same problem `role_track` (task 11) exists to solve.

- Seed `search_queries` with one query per `role_track`, marked `source = 'track'`
- Surface those as suggestions in the UI, not as an empty search box
- Let a Builder's own searches refine from there

Search is the refinement tool, not the entry point. A blank input is the wrong first
experience for this population.

## Scheduling and decay

- New queries run soon after submission.
- Watched queries re-run daily.
- A query with zero watchers and no results in 14 days stops running. Do not spend
  quota on abandoned searches.
- Cap total queries per Builder so one enthusiastic person cannot consume the pool.

## Definition of done

- `search_queries` and `search_query_watchers` exist; normalisation is deterministic
  and tested.
- A query submitted by two Builders creates one row with two watchers and costs one
  provider call.
- Cache hit rate measured after two weeks and reported — this is the number that
  justifies the design.
- Watcher counts exposed; identities never are.
- Seeded queries exist for every `role_track`.
- Results route through the full gate; a relister posting entering via search is
  suppressed exactly as it would be via ingest.
- Decay implemented; abandoned queries stop consuming quota.

## What the work turned up

Landed 2026-08-02. Four tables, one nightly step, five routes, 100 new tests
(63 pipeline, 37 webapp). What follows are proposed `DECISIONS.md` entries in
full text, **unnumbered** — several agents were running in parallel and could
not all append to that file, so the numbering is the owner's to allocate.

### Proposed decision — the watcher floor is 4, where the cohort floor is 3

`schema.SEARCH_MIN_WATCHERS = 4`, against `schema.COHORT_MIN_SAVERS = 3` two
constants above it (`backend/schema.py:146-162`). The obvious move is to copy
the neighbour, and it is wrong here for two reasons that do not apply to a save
count.

**The observed object is attacker-chosen.** The set of postings a save badge can
be watched on is fixed by the pipeline: an observer can watch a badge but cannot
conjure the posting it sits on. A search query is created by submitting it,
which is free. An observer who suspects a specific Builder is looking for
"bilingual healthcare operations Brooklyn" can type exactly that, create the
row, and then watch its bucket. That is a chosen-plaintext capability
`cohort_signal` does not have.

**The planter is always a watcher.** `POST /v1/searches` registers its caller
(`backend/webapp/search.py`, `create_search`), so at a floor of 3 the badge
appears when *two other people* arrive — an anonymity set of two, in a
thirty-person cohort who sit in a room together. 4 restores the set of three
that `COHORT_MIN_SAVERS` was chosen to give.

**Why not higher.** At N=30 a floor of 5 or 6 means most real searches never
show a badge, and a signal nobody sees is not a privacy win — it is the feature
removed, on a guess rather than a measurement. 4 is the smallest number that
survives both asymmetries.

What it does not defend against, stated so it is not read as more than it is: a
planter who gets no badge still learns "fewer than four". The mitigation is the
same one `COHORT_MIN_SAVERS` relies on — 0, 1, 2 and 3 are rendered identically,
because `search_watcher_bucket()` returns `None` for all of them and
`search_query_signal` holds no row at all.

The buckets are `4-6` / `7-10` / `11+` and **do not overlap**, which is the one
place this deviates from `COHORT_BUCKETS` (`3-5` / `6-10` / `10+`, where 10
satisfies two of three and `10+` means eleven or more). That constant's own
comment says its labels are the task file's verbatim and already shipped in
`frontend/fixtures/contract/`, so they are not its to tidy. This vocabulary is
new, this task file specifies no labels, and nothing has shipped against it.

### Proposed decision — the watcher table is keyed on `app_user_id`, not `profile`

This task file's schema sketch reads `search_query_watchers (query_id, profile,
created_at)`. `profile` in this system is the **cohort** — thirty Builders share
one, which `backend/webapp/schema_web.py:297-301` gives as the whole reason
`builder_job_state` exists. A profile-keyed watcher table can hold at most one
row per query per cohort, which makes the DoD's own *"one row with two
watchers"* unsatisfiable by construction.

It is the same defect that blocked task 28 before `app_user_id` landed on
`job_events`. `profile` is still stored, as the cohort the watch belongs to,
because the fold is deliberately within-cohort.

`app_user_id` is bare `TEXT` with **no** foreign key to `app_users(id)`: that
table is `schema_web.py`'s, and a real FK would make the pipeline's DDL depend
on a table it must not own. `schema_web.py:303-309` makes the identical call in
the other direction for `builder_job_state.job_id`.

### Proposed decision — the exposed count is a separate table, not a column

The task file sketches `watcher_count INTEGER NOT NULL DEFAULT 0` on
`search_queries`. It cannot go there. The service needs `INSERT` on that row to
register a query, and an `INSERT` names whatever columns it likes — so a count
column on a table the service can insert into is a count the service can write,
which is exactly what `cohort_signal`'s entry in `REQUIRED_TABLES` forbids for
the neighbouring aggregate.

So: `search_query_signal (query_id, cohort_profile, watcher_bucket NOT NULL,
computed_at)`, service-`SELECT`-only, written by `searchqueries.refresh()` and
nothing else. `search_queries` gets `SELECT, INSERT` and **no `UPDATE`** — the
run statistics and the decay flag are the pipeline's. Find-or-create still works
without `UPDATE` because `searchnorm.REGISTER_QUERY_SQL`'s `ON CONFLICT` branch
assigns a column to itself.

`watcher_bucket` is `NOT NULL` and a sub-threshold query has **no row**, which
is `cohort_signal`'s deviation from its own task file's sketch, taken here for
the same reason: a NULL-bucket row would be present for 1, 2 or 3 watchers and
absent for none, and that presence is the count leaking back out one indirection
later.

### Proposed decision — `search_query_results` exists, and takes no gate decision

A fourth table, `(query_id, job_id, first_seen_at, provider)`, service-
`SELECT`-only. It is what makes *"results route through the full gate"* a
structural property rather than a promise: `GET /v1/searches/{id}/results` joins
`jobs_app`, which requires a `job_matches` row, which `match.py` writes only for
postings passing `relevance.union_sql`. A relister posting a provider returned
therefore cannot be selected however it got into the table, and
`webapp/search.py` contains no relevance logic at all.

`attach_results()` links **every** job id a provider returned, including ones
the gate will reject. Deliberate: baking today's relevance config into a stored
link would mean raising `max_tier` or fixing a `\y` pattern did not
retroactively surface postings the pipeline had already paid to fetch.

### Proposed decision — seeded queries never decay

`searchnorm.UNDECAYABLE_SOURCES = ("seeded", "track")`. Nobody can watch a
suggestion that has already been retired for having no watchers, so decaying the
catalogue would switch the seeding feature off after two weeks. Nine track
queries a day against ~280 renewable searches/day is a fixed ~3% of the pool,
which is what the catalogue costs.

### Findings that are not decisions

- **`role_track`'s citation was wrong in two files.** Corrected in this file's
  header; `frontend/js/tracks.mjs:5` still carries it and was left alone.
- **`jobs_app` was deliberately not widened.** `role_track` is not in the view
  and adding it is task 30's; `frontend/check_client.mjs` asserts nothing has a
  track today, so it would go red by design. Seeding does not need the view —
  the vocabulary is what is seeded from.
- **`unwatch` is a `POST`, not a `DELETE`.** `app.py`'s CORS middleware allows
  `GET`, `POST` and `OPTIONS` only, so a browser `DELETE` would be refused at
  the preflight with no error anyone would see.
- **`_SIGNAL_JOIN` takes two parameters where `_COHORT_SIGNAL_JOIN` takes
  none.** That fragment can write `cs.cohort_profile = v.profile` because
  `jobs_app` carries a profile column; `search_queries` deliberately carries no
  identity at all, cohort included, so the cohort must be bound. Both parameters
  lead the params list and `_select_queries()` is the single place that binds
  them.

### Definition of done, item by item

| Item | State |
|---|---|
| Tables exist; normalisation deterministic and tested | **Done.** Four tables (`schema.ensure_search_query_schema`). `searchnorm.normalize()` is pure and swept by two tables of cases — the pairs that must collapse and the pairs that must not. |
| Two Builders → one row, two watchers, one provider call | **Done.** `tests/test_search_queries.py` `TestTwoBuildersOneRow` against the shipped SQL; `webapp/tests/test_search_signal.py` repeats it through the route. |
| Cache hit rate after two weeks | **Needs elapsed time.** Blocked twice over: nothing has run, and nothing *can* run until 23 lands a provider. `run_count` / `result_count_last_run` / `last_result_at` are recorded so the measurement is a query when the time comes. |
| Watcher counts exposed, identities never | **Done.** Bucket only, from the materialised table; `search_query_watchers` reaches no response. |
| A seeded query for every `role_track` | **Done.** `config/search-queries.json`, nine entries; the test asserts set equality against `extract.ROLE_TRACK` rather than a subset. |
| Results route through the full gate | **Done for the read path, deferred for the write path.** The join is the gate and is tested both ways. Nothing populates `search_query_results` in production until 23. |
| Decay implemented | **Done.** `searchnorm.should_retire()` is pure and swept; `searchqueries.apply_decay()` is the I/O around it. |

**Deferred on 23, precisely two bullets:** *"costs one provider call"* (the
dedup that makes it true is built and tested; the call itself has nowhere to
go) and the write half of *"results route through the full gate"*. The smallest
thing that unblocks both is a callable taking a due-query dict and returning
`jobs.id` values it wrote — `run_due(conn, provider=…)` already takes exactly
that and is tested against a stub. `ingest/google-serpapi.py:273`'s
`serpapi_search()` is that function with its query source hard-wired to
`config/google-queries.json`; lifting it behind an interface is 23's job. The
record shape needs nothing: `google_jobs.py` owns it and must not be
re-defined.

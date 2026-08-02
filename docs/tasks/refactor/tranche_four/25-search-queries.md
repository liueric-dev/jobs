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
> (`../../../../backend/schema.py:542`) with a nine-value vocabulary
> (`../../../../backend/extract.py:305-308`), so *"seed one query per `role_track`"* has
> something to seed from today. **It is NULL on every pre-task-11 row**, which the seeding
> has to expect rather than treat as an empty vocabulary.

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

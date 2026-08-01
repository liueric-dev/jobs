---
kind: task
written: 2026-07-27
generator: none
---

# 04 — Read endpoints

The minimum surface a frontend needs: a ranked list, one job in full, and a
place to record what the user did.

**Depends on:** 03. **Blocks:** 05.

## Files

```
backend/webapp/jobs.py
```

Every route is behind `require_user`, and **every query is scoped to
`user.profile` taken from the session** — never from a query parameter. That is
the whole tenancy model. A `?profile=` parameter would make one forgotten check
into a cross-user data leak, and there is no reason for the client to name a
profile it does not choose.

## `GET /v1/jobs`

Reads `jobs_app` (`backend/schema.py`), which already joins jobs + facts +
matches + scores and already drops rows missing a company, title, URL or
description. Do not reimplement that join here; the view exists so that
"incomplete rows may exist but nothing downstream can see one" holds at the
read edge.

Ordering is the view's documented one: `match_score DESC, posted_at_ts DESC
NULLS LAST`. `posted_at_ts` is the sortable column — `posted_at` is TEXT and
holds three incompatible formats including Built In's relative English
("Reposted 8 Hours Ago"), which no database can order. Never sort on it.

Parameters, all optional:

| Param | Meaning |
|---|---|
| `limit` | default 25, hard cap 100 |
| `cursor` | opaque `(match_score, posted_at_ts, id)` keyset, not an offset |
| `q` | case-insensitive substring over title and company |
| `remote` | `location_is_remote` |
| `nyc` | `location_is_nyc` |
| `min_score` | floor on `match_score` |
| `since` | `posted_at_ts >= ` |
| `exclude_dismissed` | drop jobs this profile has dismissed |

Keyset rather than `OFFSET`: the list is re-ranked nightly, so an offset
silently skips or repeats rows between pages. The cursor is the sort tuple, so
it stays correct under re-ranking.

Each row carries the user's own interaction state — `seen`, `saved`,
`dismissed`, `applied` — via a `LEFT JOIN LATERAL` over `job_events` filtered
to `user.profile`. That lookup is what `idx_job_events_profile_job` from task
02 exists for; without it this is a sequential scan on every page render.

## `GET /v1/jobs/{job_id}`

One row for this profile, including the full `description_text` that the list
endpoint truncates or omits. 404 if the job is not in this profile's matches —
**404, not 403**, because "exists but not yours" and "does not exist" should be
indistinguishable to a caller enumerating ids.

## `POST /v1/events`

Accepts a list, so a page of impressions is one request rather than twenty.

```json
{"events": [{"job_id": "...", "event": "impression"}]}
```

`event` must be in a closed set — `impression`, `open`, `save`, `unsave`,
`dismiss`, `applied` — and anything else is a 400. The column is free TEXT, so
the allowlist is the only thing keeping this table analysable a year from now,
when the learned ranker described in `backend/docs/SCORING.md` wants to read
it.

**`match_score` and `fit_score` are looked up server-side** from `job_matches`
and `job_scores` at write time, and are never accepted from the client.
`backend/docs/SCORING.md` makes this the load-bearing property of the whole
table:

> Recording `match_score` and `fit_score` *as of the impression* is the load-bearing
> part: without them you cannot reconstruct what the user was reacting to once
> weights change.

A client-supplied score would be unverifiable training data, which is worse
than none. This is the same rule `backend/api/` applies to postings — every
stored field derived server-side — arrived at independently.

Repeated `impression` rows for the same `(profile, job_id)` within 24 hours are
dropped with a `NOT EXISTS` guard. A list re-render is not new information, and
without the guard the table's most common row becomes its least meaningful one.
The other event types are always recorded: a second `open` genuinely is a
second open.

Unknown `job_id`s are skipped rather than failing the batch — the FK would
reject them anyway, and one stale id in a page of twenty should not lose the
other nineteen. Return counts (`recorded`, `skipped`) so a client bug is
visible instead of silent.

## Response shape

Keep field names identical to the `jobs_app` column names. The view already
chose them, the frontend does not exist yet to have an opinion, and a
translation layer between two things that agree is pure maintenance.

Return `null` for absent values rather than omitting keys — `fit_score` is
`NULL` for most rows, since `score.py` only narrates the top slice, and a
missing key would make the frontend's optional-chaining the difference between
"unscored" and "bug".

## Verify

```bash
curl -b "$C" 'localhost:8421/v1/jobs?limit=5'
curl -b "$C" 'localhost:8421/v1/jobs?remote=true&min_score=60&limit=5'
curl -b "$C" "localhost:8421/v1/jobs/$JOB_ID"
curl -b "$C" -X POST localhost:8421/v1/events \
     -H 'content-type: application/json' \
     -d '{"events":[{"job_id":"'"$JOB_ID"'","event":"save"}]}'
```

1. The list matches
   `SELECT id, title, match_score FROM jobs_app WHERE profile='tech'
    ORDER BY match_score DESC, posted_at_ts DESC NULLS LAST LIMIT 5`.
2. Page through with the cursor: no row appears twice, none is skipped.
3. `SELECT * FROM job_events ORDER BY id DESC LIMIT 1` shows the `save` **with
   `match_score` populated** from the database, not from the request.
4. POST the same `impression` twice → one row. POST `open` twice → two rows.
5. A `job_id` belonging to another profile's matches → 404 from
   `/v1/jobs/{id}`, and `skipped` from `/v1/events`.
6. Without a cookie, every route here → 401.

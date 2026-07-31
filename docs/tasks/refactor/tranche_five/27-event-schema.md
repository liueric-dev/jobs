# 27 — Event schema

**Status:** todo. **Depends on:** 26. **Blocks:** 28, 30, 31.
**Do not wait for the frontend.** This is the only work in the plan that cannot be
backfilled.

## Why it comes before the UI exists

`rank` and `request_id` describe the *state of the list at the moment it was shown*.
Once that render is over, the information is gone. Every day of impressions logged
without them is a day that can never be debiased, and position bias is the
best-documented failure mode in implicit-feedback ranking — users click higher
positions regardless of relevance, and a model trained on uncorrected logs learns the
previous ranker's ordering back.

Everything else in the plan can be redone later. This cannot.

## What exists

`POST /v1/events` landed with `docs/tasks/job_ingest/04-read-endpoints.md`, and
`docs/ingest/engagement-events.md` audits it. It already does the important thing:

> impressions, opens, saves, dismissals, applications — recorded together with the
> `match_score` and `fit_score` **as of that moment**, both read server-side

Reading the scores server-side rather than trusting the client is exactly right and
should not change. This task extends the same endpoint; it does not build a new one.

## The extension

```sql
job_events (
    id, profile, job_id, event,
    request_id    TEXT NOT NULL,   -- NEW: groups one rendered list
    rank          INTEGER,         -- NEW: 1-based position in that list
    dwell_ms      INTEGER,         -- NEW: 'open' only
    reason        TEXT,            -- NEW: dismiss enum
    visibility    TEXT NOT NULL,   -- NEW: 'private' | 'cohort_anon'
    model_version TEXT,            -- NEW: which ranker produced the order
    match_score, fit_score, occurred_at
)
```

> **VERIFIED 2026-07-31 (task 34): this task is 100% greenfield, and that is the cheapest
> position it could be in.** All six new columns are absent from `backend/schema.py`'s
> `job_events` DDL, and the table has **exactly one writer** — the `INSERT` in
> `webapp/jobs.py`'s `record_events`. One writer means the `NOT NULL` columns can be added
> without a compatibility window. Readers are `score.py`'s `_recently_active` (which only
> counts rows) and `webapp/jobs.py`'s state join; neither reads a column this task adds.
>
> **The one real conflict, which must be resolved before the DDL is written.**
> `request_id TEXT NOT NULL` above is incompatible with this task's own *"Do not backfill
> anything"* rule and with `.claude/CLAUDE.md`'s *"Do not backfill `rank` … a guessed rank
> is worse than a missing one."* Existing rows have no `request_id` and by rule never will,
> so `NOT NULL` cannot be added without either a sentinel — which is a guessed value
> wearing a different name — or a partial constraint.
>
> **Recommendation: add both `request_id` and `visibility` as nullable, and enforce
> `NOT NULL` in the writer rather than the schema**, exactly as the task already
> specifies for the API (*"reject a batch missing `request_id`/`rank` → 400"*). NULL then
> means "written before instrumentation existed", which is true and legible, and the
> analysis exclusion the task already requires for `rank` covers `request_id` for free
> with no second rule. `visibility` gets a `DEFAULT 'private'` because the safe value is
> knowable for old rows, which is not true of the other two.

### `request_id` and `rank`

Issued server-side when the list is rendered, returned with it, and echoed back on
every event from that render. Reject an impression batch that omits either — fail
loudly rather than accumulate rows that can never be used.

### `skip`, derived server-side

Add one member to `EVENT_NAMES`, written by the server and **never accepted from a
client**: when an `open` arrives at rank *k*, every un-actioned impression at rank
< *k* in the same `request_id` is a skip. The item was examined and passed over.

This is the strongest free negative signal available and it is derivable only because
`request_id` and `rank` exist.

### `dwell_ms`

Log it; do not treat it as a label. A short dwell can mean disinterest or prior
familiarity; a long one can mean an abandoned tab. Use >10s as a weak positive gate on
`open`, nothing more. News recommenders use roughly that threshold for "quick close"
negatives, and the ambiguity is well documented.

### `reason`

A small enum on dismiss, not free text: `wrong_level`, `wrong_role`, `wrong_location`,
`bad_company`, `stale_posting`, `other`.

The values map onto existing features deliberately. A `wrong_level` dismiss is
evidence about the seniority weight, not about one posting — which is what task 31
consumes.

### `visibility`

`private` or `cohort_anon`, set server-side by event type, never by the client:

| event | visibility |
|---|---|
| impression, skip, open, dwell | `private` |
| save | `cohort_anon` |
| apply | **`private`** |
| dismiss + reason | `private` |

Applications stay private. In a cohort competing for entry-level roles, seeing who
else applied is discouraging at best. Keep this consistent with task 25's watcher
model — two different answers to "what is shared" is how a privacy promise gets broken
by accident.

## Testing without a frontend

The frontend does not exist, so verify by replay: a script that posts a synthetic
impression batch for a 20-row list, then an `open` at rank 7, and asserts six `skip`
rows appear with correct ranks and a shared `request_id`.

**Verify by hand once, too.** Silent event-logging bugs are undetectable later because
there is nothing to compare against — the same reasoning behind task 03 and task 18.

## Do not

**Do not read these events for ranking yet.** At one active profile the volume is
~600 impressions/month; a per-Builder residual needs far more. Phase 5's trigger is a
volume threshold, not a date. Instrument now, consume later.

**Do not backfill anything.** Existing `job_events` rows have no `rank` and never
will. Leave them null and exclude them from any analysis that needs position — a
guessed rank is worse than a missing one.

## Definition of done

- Migration applied; endpoint accepts and validates the new fields.
- Impression batches without `rank` or `request_id` are rejected.
- `skip` derived server-side; client-sent `skip` rejected.
- `visibility` set server-side by event type, per the table above.
- Replay test: 20 impressions + open at rank 7 → 6 skips, correct ranks, shared
  `request_id`.
- One hand-verified end-to-end render.
- `docs/ingest/engagement-events.md` regenerated.

---
kind: task
written: 2026-07-28
generator: none
---

# 27 — Event schema

**Status:** DONE 2026-08-01. ~~**Depends on:** 26.~~ **Depends on: nothing.**
**Blocks:** 28, 30, 31 — **and 26**, which is the correction below.
**Do not wait for the frontend.** This is the only work in the plan that cannot be
backfilled.

> **THE DEPENDENCY ARROW POINTED THE WRONG WAY, and it is why this task sat behind a
> blocked one.** Nothing here reads `builder_profiles`, `parent_profile`, onboarding, or
> anything else task 26 builds — `request_id`, `rank`, `dwell_ms`, `reason`, `visibility`
> and the `skip` derivation are all properties of a render and an event. **26 depends on
> 27:** `26-profile-creation.md`'s own Definition of done says *"Seed judgements write real
> `job_events` rows with the correct `visibility`"*, and `visibility` is this task's column.
>
> Task 34 verified in 2026-07-31 that this task was 100% greenfield; what nobody checked
> was whether it was blocked, and it never was. **26 in turn needs onboarding screens, so
> it is behind task 32 and `frontend/` still holds one `.gitkeep`** — had the declared order
> been followed, the one piece of work in this plan that cannot be backfilled would have
> waited on the one that most obviously can.
>
> **Landed:** `backend/schema.py` (six columns + `idx_job_events_request`),
> `backend/webapp/jobs.py`, `backend/webapp/schema_web.py`, `backend/webapp/app.py`,
> and three test files. Decisions taken: `DEC-73` (the event name), `DEC-74`
> (`criteria_version` instead of `model_version`).

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

### Outcome, checked item by item — 2026-08-01

| item | result |
|---|---|
| migration applied; endpoint validates | **done.** Six columns via `add_missing_columns` on `EVENTS_TABLE`, the pattern the `job_scores` block above it established. `validate_batch()` owns the checks |
| rank/request_id rejection | **done, and narrower than asked.** `rank` is required on `impression` and `open` only — see § *One deviation* below |
| `skip` derived; client-sent `skip` rejected | **done.** `derive_skips()`; a client `skip` gets code `server_derived_event`, deliberately not `unknown_event` |
| `visibility` server-side | **done.** `save` → `cohort_anon`, everything else including `applied` → `private`. Not a field on the request model at all |
| replay test | **done, and it runs.** `webapp/tests/test_event_replay.py`, real Postgres via `evals/scratchdb.py`, 11 tests |
| one hand-verified render | **done** — see § *The hand check* |
| `engagement-events.md` regenerated | **hand-edited, and "regenerated" is wrong for this repo.** That file's own provenance header says `generator: none` is literal and that nothing produces `docs/ingest/*.md`; the claim otherwise was removed across all fourteen files by task 34 §A2. Amended by hand, with the stale line citations marked rather than swept |

### One deviation, and it is the contract's own reasoning

`API-CONTRACT-v1.md` says *"reject a batch missing `request_id` or any `rank`"*.
Implemented: `request_id` always; `rank` on `impression` and `open`. **The same document
says a detail-page request "is not an impression"** — so a `save` or `applied` raised from
`GET /v1/jobs/{id}` has no position in any render, and requiring one would force the client
to invent a value. That is the sentinel this task refused in the schema, wearing different
clothes. Pinned by `test_a_rankless_save_is_allowed`.

### What the work turned up that the task file did not predict

**1. The dependency arrow was backwards** — see the header block.

**2. `model_version` was a name the repo had already decided against.** `DEC-74`.

**3. `apply` vs `applied` had to be settled to write the validator at all.** `DEC-73`.

**4. The skip derivation is capped by the impression dedup, which is not this task's
code.** `IMPRESSION_DEDUP_HOURS` is keyed `(profile, job_id)`, not
`(profile, job_id, request_id)`, so a second render of the same list inside 24 hours writes
no impressions — and skips derive from impressions. **Skips are therefore a
first-render-per-day signal.** Narrowing the dedup key is a one-line change and a real
decision: it would change the documented meaning of *"a list re-render is not new
information"*. **Left alone, recorded in three places, and it is the owner's call.**

**5. The webapp could start against a database missing these columns.** `verify_schema()`
checked tables and grants, not columns, and the two processes migrate on different
schedules — the pipeline owns `ensure_schema()` and this service holds no DDL rights. A
deploy ahead of a nightly run would have produced a 500 on a real user's first click, which
is the exact failure that function's docstring exists to prevent. `REQUIRED_COLUMNS` added.

### The hand check

The task asks for this explicitly and gives the reason: silent event-logging bugs are
undetectable later because there is nothing to compare against.

**What was checked, 2026-08-01, against the live database as the `jobs_web` role:**

| | result |
|---|---|
| migration on `public` | six columns present, `idx_job_events_request` created, `job_events` still **0 rows** |
| three pages of a real render | one `request_id` throughout, ranks **1–3, 4–6, 7–9** — continuous across pages, not restarted |
| a second call with no cursor | new `request_id`, ranks back to 1 |
| service boots | yes, which now also exercises the `REQUIRED_COLUMNS` check |
| `GET /v1/jobs` signed out | 401 |
| the error envelope | `{"error": {"code": "missing_rank", "message": "…", "request_id": "req_abc"}}`, status 400 — the contract's shape exactly |
| the column guard fires | yes: injecting an absent column name makes `verify_schema()` raise, so the branch is not decorative |

**The write path was NOT exercised against production, deliberately.** `job_events` holds
0 rows, that figure is quoted in `docs/ingest/engagement-events.md`, and the table is
append-only with no DELETE grant — so synthetic rows could not be removed afterwards and
would corrupt the first real reading. The write path is covered against a **real Postgres**
by `webapp/tests/test_event_replay.py` instead, which is the same instrument in a schema
that gets dropped.

```bash
cd backend/webapp && .venv/bin/uvicorn app:app --port 8421
# sign in, then:
curl -s -b cookies.txt localhost:8421/v1/jobs?limit=3 | python3 -m json.tool | head
# -> top-level request_id, and rank 1,2,3 on the rows
```

> **A trap for whoever repeats this without a browser.** Calling `jobs.list_jobs()` directly
> rather than through FastAPI leaves the parameters that default to `Query(...)` holding a
> `Query` **object**, and `Query(None)` is **truthy** — so `if since:` passes and psycopg
> fails with *"cannot adapt type 'Query'"*. Pass `since=None` explicitly. It is not a defect
> in the served path, where FastAPI resolves the defaults, and it is exactly the kind of
> thing that costs twenty minutes when it is not written down.

Then post an impression batch and an `open`, and read the rows back. What to look at, in
order: `request_id` matches the one the list issued; `rank` matches what the row was shown
at; `visibility` is `private` on everything but a save; `criteria_version` is non-NULL and
equals `job_matches.criteria_version`; and the `skip` rows exist with the right ranks.

---
kind: task
written: 2026-07-28
generator: none
---

# 28 — Anonymous cohort aggregation

**Status:** todo. **Depends on:** 27, **which is DONE**. **Blocks:** 32.

> **UNBLOCKED 2026-08-02, and this is the one blocker on this track that was REMOVED rather
> than argued away.** `HANDOFF.md` carried this task as *"a real blocker"*: `job_events` was
> keyed `(profile, job_id)`, thirty Builders share `pursuit`, so *"4 **Builders** saved
> this"* — the entire deliverable — was not a question the table could answer. **`app_user_id
> TEXT` landed on `job_events` in `3f4f88e`** (`../../../../backend/schema.py:678`, index at
> `:703`), written from `user.id` by `POST /v1/events`
> (`../../../../backend/webapp/jobs.py:837`). `COUNT(DISTINCT app_user_id)` is now answerable.
>
> **Three things that column does not settle, and each changes the implementation below.**
>
> 1. **`builder_job_state` is NOT usable as the source, despite being the obvious one.** It
>    carries `saved_at` per Builder already — but it is declared in
>    `../../../../backend/webapp/schema_web.py:281-288`, on the **webapp's** side of the
>    ownership line, and § *Implementation* below puts this compute on the **nightly
>    cycle**. `.claude/CLAUDE.md` § *Layout*: the three processes have their own roles and
>    **none imports another**. A pipeline table must not require the surfacing service's
>    schema. So aggregate from `job_events`, which is what this file already says — the
>    reason is stronger than it looks.
> 2. **`save` and `unsave` are both events, so a distinct count over `event='save'` is
>    wrong.** `_STATE_WRITES` (`../../../../backend/webapp/jobs.py:573-574`) maps both, and
>    `job_events` is append-only. Someone who saved and then unsaved still has a `save` row
>    forever. Take the **latest** of `{save, unsave}` per `(app_user_id, job_id)`; the
>    current answer is a fold over the log, not a filter on it.
> 3. **`app_user_id IS NULL` rows must be excluded, not counted.** Pre-column rows are NULL
>    by design and unbackfilled (`../../../../backend/schema.py:662-671`). Counting them
>    collapses every pre-2026-08-01 saver into one phantom Builder — which would push
>    postings **over** the suppression threshold on the strength of a row that names nobody.
>    That is the privacy control failing open.
>
> **What the column does NOT unblock is the small-N problem below.** *"4 Builders saved
> this"* becoming an identifier in a thirty-person classroom is not something a column
> answers, and the suppression rule is load-bearing arithmetic today rather than a
> precaution. [`../../../labelling-report-2026-08-02.md`](../../../labelling-report-2026-08-02.md)
> records **two** labellers on `pursuit`; at that headcount a threshold of 3 suppresses
> everything by construction. **Do not tune it down to see output** — an empty badge is the
> correct rendering of a two-person cohort, and the first thing a test here should pin is
> that `2` produces no badge rather than a small one. (Instrument for the live count is
> `manage_app_users.py list`, which needs the database; the report is committed data and
> does not.)

Surface "4 Builders saved this" without ever revealing which four — and without the
count itself becoming an identifier.

## Why it earns its place

Two reasons, and the second is the one that matters technically.

**It is the community feature.** Pooled postings with visible collective interest is
the draw — Builders helping each other find things, which is the social contract the
whole app is organised around.

**Collaborative signal works at N=30 precisely because the cohort is homogeneous.**
"Four Builders saved this" is usable information immediately, in a way "four strangers
saved this" would not be. Thirty people with a shared floor — entry-level, AI-adjacent,
NYC — produce a signal that would need thousands of unrelated users to match.

## The small-N problem

This is the part that needs care, and it is easy to get wrong.

In a thirty-person cohort who see each other in a classroom, **a count of 1 is close
to an identifier.** "1 Builder saved this" plus knowing who was on their laptop, plus
a posting for a role someone mentioned, is enough. Aggregate counts are not
automatically anonymous at this scale.

### Rules

**Suppress below a threshold.** Show nothing until at least 3 Builders have saved a
posting. Below that, no badge — not "1 Builder", not a greyed-out zero. Absence of a
badge must not be readable as "exactly one or two."

**Bucket rather than count exactly.** `3–5`, `6–10`, `10+`. An exact count that
increments visibly lets an observer infer *when* someone saved something, which
combined with who was present narrows it further.

**Never expose ordering or recency.** No "recently saved by a Builder." Timing is the
strongest deanonymiser available in a room where people can see each other.

**Aggregate only `cohort_anon` events.** Task 27 sets `visibility` server-side.
Applications are `private` and must never reach this path — enforce it in the query,
not by convention.

## Implementation

A materialised count per `(job_id, cohort)`, refreshed on the nightly cycle rather
than computed live. Live computation invites a timing side channel and costs more.

```sql
cohort_signal (
    job_id, cohort_profile,
    save_bucket TEXT,        -- '3-5' | '6-10' | '10+' | null
    computed_at TEXT,
    PRIMARY KEY (job_id, cohort_profile)
)
```

The read endpoint joins this; it never touches `job_events` directly. One join, one
place where the suppression rule lives, no chance of a future endpoint forgetting it.

## Where it does not go

**Not into ranking, yet.** It is tempting to boost saved postings, and it would work
— but it creates a feedback loop with nothing to correct it: a posting that surfaces
early accumulates saves, ranks higher, accumulates more. At N=30 with no position-bias
correction (task 27's `rank` is logged but not yet used), the loop would be
unmitigated.

Log it, display it, and revisit after there is enough data to correct for exposure.
The events are being collected either way.

**Not across cohorts,** initially. A rolling programme means multiple cohorts exist
simultaneously with different profiles. Cross-cohort aggregation would raise the
counts and improve the signal, but it also means a Builder's save is visible to people
they have never met, which is a different privacy promise than the one made. Keep it
within cohort until there is a reason not to.

## Definition of done

- `cohort_signal` computed nightly from `cohort_anon` events only.
- Counts suppressed below 3 and bucketed above it.
- No recency, no ordering, no exact counts exposed.
- Application events provably cannot reach the aggregation — enforced in the query,
  with a test.
- The read endpoint joins the materialised table, never `job_events`.
- A written note in the endpoint docstring explaining the suppression threshold, so
  someone tuning it later knows it is a privacy control and not a display preference.

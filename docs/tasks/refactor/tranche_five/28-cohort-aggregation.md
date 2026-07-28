# 28 — Anonymous cohort aggregation

**Status:** todo. **Depends on:** 27. **Blocks:** 32.

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

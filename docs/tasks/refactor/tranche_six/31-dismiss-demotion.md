---
kind: task
written: 2026-07-28
generator: none
---

# 31 — Dismiss demotion

**Status:** todo. **Depends on:** 27, 26. **Blocks:** nothing.

Make a dismissal mean something. Today it is a query filter; it should be a signal.

## What happens now

`webapp/jobs.py` supports `exclude_dismissed` as an optional list parameter. So a
Builder dismisses a posting, and it is hidden only while that flag is set — it can
rank third again tomorrow, and nothing about the dismissal informs anything.

`job_events` records it. `score.py:_recently_active` is the only reader of that table
in the entire pipeline, and it only counts rows.

## The scoping problem — read this before designing

**This is the one thing about the cohort-profile decision that needs care.**

`job_matches` is keyed `(job_id, profile)`, and thirty Builders share one cohort
profile. So a demotion written into `match_score` would apply to **all thirty**. One
Builder dismissing a posting would suppress it for everyone.

That is clearly wrong, and it is a direct consequence of the shared-profile decision.
The fix is not to abandon shared profiles — the reasoning in task 11 still holds — but
to put per-Builder state where it belongs:

```sql
builder_job_state (
    app_user_id, job_id,
    dismissed_at TEXT,
    dismiss_reason TEXT,
    saved_at TEXT,
    PRIMARY KEY (app_user_id, job_id)
)
```

Ranking stays cohort-level and cheap. Per-Builder adjustments are a **join at read
time**, not a rewrite of `job_matches`. That keeps the flat-cost property — one match
row per posting, not thirty — while making dismissal personal.

This is the same fixed-effect/random-effect decomposition as task 26's config
inheritance and as the ranker's eventual shape. Three places now where the same split
appears; that consistency is worth preserving deliberately.

## Two kinds of demotion

**Item-level.** The dismissed posting drops out of that Builder's list permanently.
Simple, obvious, and what a user expects when they dismiss something.

**Feature-level, from `reason`.** This is the interesting one. Task 27's enum maps
onto existing features on purpose:

| reason | evidence about |
|---|---|
| `wrong_level` | the seniority weights |
| `wrong_role` | the archetype weights, or the `role_track` assignment |
| `wrong_location` | location acceptance |
| `bad_company` | a company-level signal the pipeline does not yet have |
| `stale_posting` | `posting_age_days` weighting |
| `other` | nothing — expect this to dominate initially |

A `wrong_level` dismiss on a staff-engineer posting is evidence about the seniority
weight, not about that one job.

**But do not implement feature-level demotion as a learned adjustment yet.** At ~600
impressions per Builder per month and no position-bias correction in use, a per-Builder
weight adjustment would be fitting noise, and it would do so invisibly.

Instead: **aggregate reasons and report them.** If twelve Builders dismiss postings as
`wrong_level` in a week, that is a signal `criteria.json` is mistuned — and it is
information for a human to act on, not a loop to close automatically. Task 13's config
is hand-authored; this is how it gets better.

## Undo

A dismissal that cannot be undone will be regretted. Provide it, and record the undo
as its own event rather than deleting the original — the fact that someone reversed a
dismissal is itself signal, and deletion loses it.

## Interaction with cohort signal

Task 28 aggregates saves. Do **not** aggregate dismissals into a visible counter. "18
Builders dismissed this" is discouraging, deanonymising at small N, and reflects a
cohort-wide config problem more often than a bad posting.

Keep dismissals private, per task 27's `visibility` assignment. Aggregate them for
your own tuning, not for display.

## Definition of done

- `builder_job_state` exists; dismissal is per-Builder, not per-profile.
- Ranking remains cohort-level; per-Builder state applies as a read-time join.
- A dismissed posting never reappears in that Builder's list, and appears normally for
  everyone else — verify with two accounts.
- `reason` is captured and aggregated into a report, not into automatic weight changes.
- Undo exists and is recorded as an event.
- Dismissal counts are never displayed.
- `exclude_dismissed` as a query parameter is removed or reduced to a debugging flag —
  the behaviour is now the default.

---
kind: task
written: 2026-07-28
generator: none
---

# 31 — Dismiss demotion

**Status:** **done, 2026-08-01.** **Depends on:** 27, ~~26~~. **Blocks:** nothing.

> **THE 26 DEPENDENCY WAS SPURIOUS AND IS STRUCK, 2026-08-01 — the second one in this
> tranche.** Checked rather than assumed, because `HANDOFF.md` flagged it as unverified
> after 27's own arrow turned out to be backwards.
>
> `builder_job_state` is keyed `app_user_id`. `app_users.id` already exists
> (`backend/webapp/schema_web.py`, `ensure_schema`) and `require_user` puts it on every
> request as `User.id` (`backend/webapp/auth.py`, the `User` dataclass). Nothing this task
> builds reads `builder_profiles`, `parent_profile`, config inheritance or onboarding —
> the four things 26 is. 27 was the half that mattered, and it supplied the `reason` enum
> this task consumes.
>
> **Two arrows in this tranche have now been found wrong in the same direction.** Both
> declared a dependency on 26, and in both cases the real relationship ran the other way or
> not at all. That is a pattern worth carrying into 28, 31's neighbours and anything else
> whose brief was written in the same sitting: **check the arrow before planning on it.**

> **WHAT THE WORK TURNED UP — read this before the design below, which is unamended.**
>
> **The leak this file predicts was already shipped, one layer lower than it looks.** The
> § *scoping problem* below is about `match_score`, and it is right — but the field it
> warns about was never the one that had gone wrong. `_EVENT_STATE_JOIN` in
> `backend/webapp/jobs.py` resolved `seen`, `dismissed`, `applied` and `saved` with
> `WHERE e.profile = v.profile`, and a cohort shares one profile. The dismissal did not
> need to reach the ranker to apply to all thirty; the **read** already did.
>
> **Two of the four are fixed and two are registered.** `dismissed` and `saved` now come
> from `builder_job_state`. `seen` and `applied` cannot follow — they derive from
> impressions, which live only in `job_events`, which has **no `app_user_id` column at
> all**. They are **defects D66 and D67** in [`../../../ingest/DEFECTS.md`](../../../ingest/DEFECTS.md),
> both `BLOCKED-BY: job_events has no app_user_id`. D67 is the sharper one: an application
> is `private` in the event row and cohort-wide in the response body.
>
> **`builder_job_state` is what makes task 28 possible.** *"4 Builders saved this"* needs
> distinct users and `job_events` cannot express one. 28 reads `saved_at` from this table,
> or adds the column D66/D67 want first.
>
> **The undo is `undismiss`, an eighth client event**, shaped on the `unsave` that had
> already answered the same question. It clears the state column and leaves the dismissal
> in the log, which is what this file asks for.
>
> **`exclude_dismissed` is gone, replaced by `include_dismissed` (default false).** The old
> parameter defaulted to *showing* dismissed rows, so a dismissal meant nothing unless a
> client opted in — a name that described the opposite of the behaviour anyone wanted.

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

*Checked item by item, 2026-08-01. The instrument is named for each.*

- ~~`builder_job_state` exists; dismissal is per-Builder, not per-profile.~~ **Done.**
  Declared in `backend/webapp/schema_web.py` — that side of the ownership line, because it
  references `app_users(id)`, which that module owns. `job_id` is bare TEXT with **no** FK
  to `jobs`, for the reason `app_users.profile` carries none: a real FK would make this
  service's DDL depend on a table it must not own. A stranded row is invisible rather than
  harmful, because state is only ever read joined to `jobs_app`.
- ~~Ranking remains cohort-level; per-Builder state applies as a read-time join.~~
  **Done.** `job_matches` is untouched; `_BUILDER_STATE_JOIN` is a `LEFT JOIN` in
  `jobs.py`. One match row per posting, not thirty — the flat-cost property is intact.
- ~~A dismissed posting never reappears in that Builder's list, and appears normally for
  everyone else — verify with two accounts.~~ **Done, and verified with two accounts in
  code rather than by hand:** `TestListState` in `webapp/tests/test_event_replay.py` runs
  `USER` and `USER_B` on the same `pursuit` profile against a real scratch schema. It is
  also the test that catches the join's parameter landing in the wrong position —
  mutation-checked: binding `user.id` after `user.profile` fails five cases.
- ~~`reason` is captured and aggregated into a report, not into automatic weight
  changes.~~ **Done.** `backend/tools/dismiss-reasons.py`, read-only, no writes and nothing
  in the pipeline reads its output. It reads `builder_job_state` and **not** `job_events`,
  because only the former carries `app_user_id` — and *"twelve Builders dismissed one
  posting"* versus *"one Builder dismissed twelve"* are the same row count and opposite
  conclusions. It prints **zero** against the live database today; `frontend/` holds one
  `.gitkeep`, so nothing has ever posted a dismiss from a screen. That is a reading, not a
  failure, and the tool says so in its own output rather than leaving it to be inferred.
- ~~Undo exists and is recorded as an event.~~ **Done.** `undismiss`, in
  `CLIENT_EVENT_NAMES`. It clears `dismissed_at` and `dismiss_reason` and leaves the
  original `dismiss` row in `job_events`, which holds `SELECT, INSERT` and nothing else —
  so "record rather than delete" is enforced by privilege, not by care.
- ~~Dismissal counts are never displayed.~~ **Done.** `COHORT_VISIBLE_EVENTS` is still
  `("save",)` and both `dismiss` and `undismiss` are `private`; a test asserts it by name.
  The aggregation is operator-only and prints no per-Builder breakdown, per this file's
  § *Interaction with cohort signal*.
- ~~`exclude_dismissed` as a query parameter is removed or reduced to a debugging flag —
  the behaviour is now the default.~~ **Removed**, and replaced by `include_dismissed`
  (default false). `GET /v1/jobs/{id}` is deliberately **not** filtered: undo has to be
  reachable from a detail page.

**Suites after the work:** backend `Ran 1233 tests` (unchanged — this task touches
`webapp/` only), webapp `Ran 147 tests`, both OK, up from 129. Read the `Ran N` line; the
fourteen new cases gate on `scratchdb.available()` and a skip is not a pass.

**One deliberate omission.** The feature-level demotion this file describes is **not**
implemented as an adjustment, per its own instruction — the tool reports and stops. The
reasoning is quoted in the tool's docstring so that whoever is tempted later finds it
without coming back here.

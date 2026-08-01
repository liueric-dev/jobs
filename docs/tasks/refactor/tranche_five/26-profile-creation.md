---
kind: task
written: 2026-07-28
generator: none
---

# 26 — Profile creation

**Status:** todo. **Depends on:** 13. **Blocks:** 28, 29, 32.

Close the last gap between "a Builder can sign in" and "a Builder has a ranked list."

## The gap is narrower than it looks

Authentication is done. `docs/tasks/job_ingest/` landed `app_users`, `app_sessions`,
`oauth_logins`, the `jobs_web` role, Google SSO, session cookies and `require_user`
on 2026-07-26. A Builder can already sign in.

What they cannot do is *exist* as a scored entity. `profiles` rows — carrying
`persona_json`, `criteria_json`, `relevance_json`, `criteria_version` and
`daily_narrative_budget` — can only be created by `migrations/migrate_profiles.py`,
a CLI reading a hand-written file. That is fine for two profiles and impossible for
thirty.

**First thing to establish:** how `app_users` currently maps to `profiles`. `job_events`
keys on a `profile` TEXT and `webapp/jobs.py` serves a profile's list, so some linkage
exists or is assumed. Read it before designing on top of it; if there is no explicit
mapping, that is the first thing this task adds.

> **ANSWERED 2026-07-31 (task 34), so this task does not start by re-deriving it.**
> There is deliberately **no foreign key**. `app_users.profile` is bare `TEXT NOT NULL`,
> and `webapp/schema_web.py` says so in a comment beside the column: the profile is
> validated by `manage_app_users.py` calling `profiles.load_one()` instead. So the
> linkage is **CLI-enforced, not database-enforced** — which is exactly the gap this
> task exists to close, and it is a design to replace rather than an unknown to discover.
>
> **Also already landed for an unrelated reason: `app_users.prior_domain`**, with its
> CHECK constraint and a migration. That is one of this task's onboarding fields already
> in the schema. Note `HANDOFF.md` records that its vocabulary already fails on the one
> real user — do not treat the column as settled just because it exists.

## Inheritance, not authoring

Per the master plan: **one cohort profile.** A Builder does not get their own
`criteria_json` — nobody is hand-authoring thirty weight files, and eight unvalidatable
configs is worse than one validated one.

Instead:

```
cohort profile  ──  criteria_json, relevance_json, persona_json  (task 13)
      │
      └── builder ──  location, remote preference, comp floor, track subscriptions
```

The Builder-level record carries only what genuinely varies. Everything else resolves
through the parent.

Note this is the same decomposition as the ranker's eventual global-plus-residual
shape — cohort is the fixed effect, Builder is the random effect. Building the config
inheritance to agree with that means the per-Builder residual has an obvious place to
live later.

### Schema

```sql
builder_profiles (
    app_user_id      REFERENCES app_users(id),
    parent_profile   REFERENCES profiles(profile),
    location_pref    TEXT,
    remote_pref      TEXT,
    comp_floor       INTEGER,
    tracks           TEXT[],        -- role_track subscriptions
    created_at, updated_at,
    PRIMARY KEY (app_user_id)
)
```

Resolution order at match time: Builder override, else cohort, else shared default.
The same merge `relevance.load(path=None, cfg=None)` already does at `:66-88` — reuse
that pattern rather than inventing a second one.

## Onboarding

Three steps, in order of what they produce.

**1. A structured form, not a résumé upload.** Prior domain, years of prior
experience, current situation, location, schedule constraints, track interests.
Fifteen fields, no file upload.

This is deliberate. Résumé upload would mean storing personal documents for thirty
low-income adults on a residential home connection. A form gives you the same
matching-relevant fields without holding the document. If résumé parsing is added
later, extract fields and discard the source — and do it when there is somewhere
better to put it than a home server.

**2. Seed judgements.** Show 15–20 deliberately diverse postings drawn across
`role_track`s; collect like/dislike. This does three things at once: it produces the
Builder's first `job_events` rows *on day one*, it seeds their track subscriptions
from behaviour rather than a checkbox, and it teaches — a Builder who does not know
what they want learns more from reacting to twenty real postings than from a
dropdown.

**3. Nothing else.** Resist adding steps. The population includes people for whom
this is a first technical product; every additional screen loses someone.

## Cohort lifecycle

Classes are rolling. Decide now, in code, rather than discovering it when the first
cohort ends:

- A cohort profile persists after its cohort graduates.
- Builder profiles persist; a graduated Builder keeps access unless they ask
  otherwise. They are still job-seeking, and the marginal cost is a narrative budget.
- A new cohort gets a new cohort profile seeded from the previous one's
  `criteria_json`, with its own `criteria_version`. That way tuning learned from
  cohort N carries forward and cohort N+1's changes do not retroactively re-rank
  cohort N.

## Deprecate the migration path

Once creation works through the API, `migrate_profiles.py` should create the *cohort*
profile only, and say so in its docstring. Two ways to create a profile is how the
two diverge.

## Definition of done

- A Builder signs in with Google and reaches a ranked list without any manual DB work.
- `builder_profiles` resolves overrides against the cohort profile using the existing
  merge pattern.
- Onboarding is ≤3 screens and involves no file upload.
- Seed judgements write real `job_events` rows with the correct `visibility`.
- Cohort lifecycle behaviour is implemented and documented, not left implicit.
- `migrate_profiles.py`'s scope is narrowed and its docstring updated.
- The `app_users` → `profiles` mapping is explicit in the schema.

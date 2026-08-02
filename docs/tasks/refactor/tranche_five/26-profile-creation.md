---
kind: task
written: 2026-07-28
generator: none
---

# 26 — Profile creation

**Status:** ~~todo~~ ~~**backend half DONE 2026-08-02; the screen half is task 32's and is
not started.**~~ **DONE 2026-08-02 — the screen landed the same day, as
`frontend/js/onboarding.mjs`.** **Depends on:** 13, ~~and 27 declared itself dependent on
this~~ **and 27, which is DONE.** **Blocks:** 28, 29, 32.

> **THE SCREEN CAME BACK TO THIS TASK RATHER THAN GOING TO 32.** The struck line above
> handed it to task 32, and 32's own definition-of-done table handed it back — *"onboarding
> completes without manual DB work: **not done** — out of scope for this stream;
> `POST /v1/onboarding` is another stream's"*. Both were reasonable and together they were
> a hole, which is what a bullet owned by two tasks and neither always is. It is built and
> it is recorded here, in the task whose endpoint it posts to; 32's table now points at
> this file.

> **THE 26/27 ARROW WAS BACKWARDS AND IS CORRECTED, 2026-08-01.**
> `27-event-schema.md` declared *"Depends on: 26"*. Nothing in 27 read anything 26 builds,
> and this file's own Definition of done — *"Seed judgements write real `job_events` rows
> with the correct `visibility`"* — names **27's** column. So the real order is 27 then 26,
> and 27 has landed: `visibility`, `request_id`, `rank` and the `skip` derivation all
> exist, so the seed-judgement step has somewhere correct to write.
>
> ~~**What this task still needs and does not have is a screen**, which is task 32, and
> `frontend/` holds one `.gitkeep`. That is the real blocker on 26 and it always was.~~
>
> > **OVERSTATED, AND IT IS THE OTHER HALF OF A CYCLE. Corrected 2026-08-02.**
> > [`../tranche_six/32-frontend.md`](../tranche_six/32-frontend.md)`:9` declares
> > *"Depends on: **26**, 27, 28, 30, 31"* while this block declared 32. **26 → 32 → 26.**
> >
> > Exactly two Definition-of-done bullets need a screen — *"a Builder signs in and reaches
> > a ranked list"* and *"onboarding is ≤3 screens"*. **The rest is schema and does not:**
> > the `builder_profiles` DDL, resolving overrides against the cohort profile,
> > `POST /v1/onboarding` (no route today), narrowing `migrate_profiles.py`, and making the
> > `app_users` → `profiles` mapping explicit — today `app_users.profile` is bare TEXT with
> > its no-FK rationale at `../../../../backend/webapp/schema_web.py:231, 241-247`.
> >
> > **So the backend half is unblocked and is on 32's critical path**, which is the
> > opposite of what this block said. The arrow to invert is this one, because a screen
> > cannot be built against an endpoint that does not exist and an endpoint can be built
> > against no screen.
> >
> > **And `frontend/` no longer holds one `.gitkeep`** — it carries `README.md`,
> > `verify_fixtures.py` and 39 frozen fixtures as of `fe3df28`. That sentence is stale in
> > three files; see [`../API-CONTRACT-v1.md`](../API-CONTRACT-v1.md) and
> > [`../tranche_six/32-frontend.md`](../tranche_six/32-frontend.md).

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

---

## What the work turned up, 2026-08-02

**Two streams, one day, and this section is both of them.** The backend half is
everything down to § *Still open*; the screen is § *The screen* at the end. They were
written hours apart and against each other, so the second one names where the first was
right and where it left a gap.

~~Five of the seven done bullets are met. The two that are not are the two that need a
screen, and they are **task 32's, not a remainder of this one** — see the correction at
the top of this file. Nothing below builds UI and `frontend/` was not touched.~~
**All seven are met.** The struck sentence was true when written and stopped being true
the same day; the screen is § *The screen* below.

Built, backend half: `builder_profiles` in `backend/webapp/schema_web.py`, resolution in a
new `backend/webapp/onboarding.py` (`resolve`, `resolved_for`), `POST`/`GET /v1/onboarding`
in the same file, and the narrowing in `backend/migrations/migrate_profiles.py`. Webapp
suite `Ran 159` → `Ran 300`, OK.

Built, screen half: `frontend/js/onboarding.mjs`, a route in `frontend/js/app.mjs`, a tab
in `frontend/index.html`, styles in `frontend/app.css`, four fixtures moved or added under
`frontend/fixtures/shipped/`, and coverage in both `frontend/verify_fixtures.py` and
`frontend/check_client.mjs`. `check_client.mjs` `28 checks` → `43 checks`, 0 failed.

### The foreign key this file sketched cannot be written, and a better one can

§ *Schema* asks for `parent_profile REFERENCES profiles(profile)`. The obstacle is not
the referenced side — `profiles.profile` is `TEXT PRIMARY KEY` (`backend/schema.py:391`)
and `schema_web.ensure_schema` already calls `schema.ensure_schema` first, on the same
connection and the same admin credential, so shape, ordering and privilege all permit it.

What forbids it is that **a foreign key is DDL on both tables**: Postgres implements
referential integrity with system triggers, and the `ON DELETE`/`ON UPDATE` half is
installed on the *referenced* table. So the constraint would put `pg_trigger` rows on a
pipeline-owned table and make every `DELETE FROM profiles` this service's business —
against the rule at the top of `schema_web.py`, which is that this module "never drops,
alters or restates anything on the other side of that line."

What was written instead is a **composite** FK entirely inside this service's ownership:

```
builder_profiles (app_user_id, parent_profile) REFERENCES app_users (id, profile)
    ON DELETE CASCADE ON UPDATE CASCADE
```

with a redundant-looking `UNIQUE (id, profile)` on `app_users` to make it legal. It is
the stronger constraint on the thing that can actually go wrong: a Builder's profile is
now stored in two places — `app_users.profile`, which the session carries and every
query in `jobs.py` scopes by, and `parent_profile`, which decides whose criteria resolve
— and **they cannot disagree**. Two answers to "which cohort is this Builder in" is D66
and D67 one level up.

`ON UPDATE CASCADE` is also the cohort lifecycle, implemented rather than left implicit:
`manage_app_users.py set-profile` is one `UPDATE app_users.profile`, and every override
row follows it. A graduated Builder who is not moved keeps their old cohort profile and
keeps working, which is what § *Cohort lifecycle* asks for.

`app_users.profile → profiles.profile` therefore still has **no** FK, and that is now a
recorded decision rather than an open one. It is enforced in three places instead: at
write time by `manage_app_users.py`'s `profiles.load_one()` check (unchanged), at deploy
time by a new `schema_web.profile_mapping_problems()` folded into `verify_schema()`, and
at request time by `POST /v1/onboarding` refusing a session whose profile has no row.
The deploy-time check is the one that closes the real hole — the hand-typed `UPDATE` the
README tells operators not to do, which skips the CLI check.

### Track subscriptions are derived, and derive nothing today

§ *Onboarding* step 2 asks that seed judgements seed track subscriptions "from behaviour
rather than a checkbox", so `derive_tracks()` reads `job_scores.primary_track` for the
postings a Builder liked. **It returns an empty set for `pursuit` and will keep doing so
until something changes.** `pursuit` has `daily_narrative_budget = 0`, so `score.py`
writes no rows for it at all: `job_scores` held **zero** `pursuit` rows on 2026-08-02
(`migrate_profiles.py` dry run: `existing job_scores : 0`). `config/pursuit-persona.json`'s
`_no_buckets_comment` already records that `score.TRACKS`' five names "do not describe
this population" and that fixing it is task 30's. The derivation is written now because
the alternative was shipping the checkbox this file rejects; `tracks` stays NULL rather
than `{}`, because "subscribed to no tracks" is not an answer anybody gave.

### Two contract questions this file left open, now decided

- **`interested`/`not_interested` → which event.** `frontend/fixtures/contract/MANIFEST.json`
  recorded this as undecided. Decided: `interested` → `save` (the only cohort-visible
  event, and it leaves the posting where the Builder can act on it), `not_interested` →
  `dismiss`, with its permanence accepted and no invented `dismiss_reason`. Seed
  judgements go through `jobs.record_events()` rather than a second INSERT, so
  `visibility`, `match_score`, `criteria_version` and `app_user_id` are all the server's,
  and `jobs.py` was not edited.
- **Where the fifteen form fields live.** `prior_domain` stays on `app_users` — it exists
  to decompose Axis B disagreement by background through `eval_labels.labeller_id`, which
  is a fact about a labeller, not a matching input. `prior_years`, `situation` and
  `schedule_constraints` are matching inputs and went on `builder_profiles`.

### Still open, and deliberately not decided here

- **`PRIOR_DOMAINS` still fails on the real user.** Unchanged, as instructed: widening it
  moves a generated CHECK and is a decision. The field is optional in the request, so
  that Builder can leave it NULL, which is the column's honest value.
- **`SITUATIONS` and `SCHEDULE_CONSTRAINTS` are new vocabularies with thin derivations.**
  `SCHEDULE_CONSTRAINTS` ships with the single value attested anywhere in the repo
  (`no_overnight`); `SITUATIONS` has one attested value plus its implied negation. Both
  are as unvalidated against real Builders as `PRIOR_DOMAINS` was on the day it shipped.
- **Nothing filters on the resolved config yet.** `resolved_for()` is written and tested;
  wiring it into `GET /v1/jobs` belongs with the screen that lets a Builder change these
  values, because turning on a filter nobody can see would silently shrink thirty lists.

### The screen — what building it against the endpoint found

Written 2026-08-02, on landing the onboarding **screen** — the last outstanding
bullet. `4c874e7` landed the entire server side and touched `frontend/` not at all;
six of the seven bullets were met in code and the third had no screen. This section
is what building the screen against the shipped endpoint found.

**Two screens, not three, and the third bullet is honoured by not spending it.**
`SCREENS` in `frontend/js/onboarding.mjs` is `["form", "seed"]`. § *Onboarding*'s
third step is literally *"Nothing else. Resist adding steps"*, so a confirmation
screen would have spent the budget on the one thing this task asked not to add.
The outcome goes in a toast and the Builder lands on Today.
`frontend/check_client.mjs` asserts the length against the ceiling, because a
definition-of-done bullet nothing checks is a bullet that drifts.

**The form asks seven questions, and § *Onboarding* asks for fifteen fields.** The
endpoint accepts exactly seven (`OnboardingRequest`, `backend/webapp/onboarding.py`),
and pydantic **ignores** keys a model does not declare — so an eighth question would
have been answered by a Builder, discarded silently, and reported as a 200. Building
the missing eight would be a schema change with eight new CHECK constraints, which is
a decision and not a screen. The screen asks what can be stored.

**That silent-discard is the sharpest thing this stream found, and it now has a
check.** Both checkers derive `OnboardingRequest`'s field list out of Python:
`frontend/verify_fixtures.py` compares it to the frozen request fixture, and
`check_client.mjs` compares it to the `name=` attributes in the **rendered** form,
so it fails in both directions — a field the endpoint accepts with no question on
the screen, and a question whose answer the server throws away. Nothing else in the
repo can see that failure: it produces no 400, no log line and no wrong row.

**The two "aspirational" onboarding fixtures were moved to `shipped/`, and the
fixture was the thing that was wrong.** They now derive from the code, and one
deviation fell out:

> `completed_at` carried a trailing **`Z`** that this endpoint never sends.
> `builder_profiles.onboarded_at` is `TEXT` (`backend/webapp/schema_web.py`, the
> `CREATE TABLE`) written by `lib.timeparse.utc_now_str()`, whose docstring says
> the `'%Y-%m-%dT%H:%M:%S'` shape is load-bearing and **"must not gain an offset
> or microseconds"** because both pipelines compare these as *strings*. The `Z`
> came from `API-CONTRACT-v1.md`, which invented this response shape against no
> code. A client doing `new Date(completed_at)` on the real value reads it as
> **local time** — the same trap `first_seen` sets, which `js/format.mjs` already
> handles by appending the `Z` itself. Both checkers now assert the zone's absence.

`GET /v1/onboarding` had **no fixture in either directory** and now has two, the
completed state and the first-run state. The first-run one pins that `prior_domain`
is `null` and **not** the domain literally named `none` — the distinction
`schema_web.py` spends a paragraph on, and the one a first-run client is most likely
to collapse.

**The onboarding block of `verify_fixtures.py` has no `rank`-shaped residue, and
that is luck rather than virtue.** Both route returns and `_state()` are single
dict literals and the request is a pydantic model, so every expectation is derived
and a new key appears on its own. The list endpoint is not in that position because
`jobs.py` assembles `item["rank"]` inside a handler, where there is no constant for
`ast` to read — the seam `D70` documents. Worth stating because the difference is
that `onboarding.py` happens not to build any response key inside a function body,
not that anybody designed for it.

**The seed draw asks for diversity across `role_track` and there is no `role_track`
to draw across.** § *Onboarding* step 2 wants "15–20 deliberately diverse postings
drawn across `role_track`s". That column is on `job_facts` and the `jobs_app` view
does not select it, so it is in no response body — task 32's finding 1, unchanged.
`pickSeed()` is written round-robin over `tracks.trackOf()` anyway: today that
degenerates to the first eighteen in `match_score` order, and it becomes the diverse
draw the day the field lands, with no edit. Same shape as the grouping in
`js/tracks.mjs`, and for the same reason.

**A judgement is never sent as an event.** The verdicts ride inside the POST body
and the **server** mints their `request_id` (`record_seed_judgements()`), because a
seed set genuinely is its own render. `js/onboarding.mjs` therefore imports nothing
from `js/events.mjs` and `check_client.mjs` asserts that it does not — sending them
under the *list's* `request_id` would claim they were part of a render they were
not, and would arm `derive_skips` against rows nobody was shown.

**The four preferences are stored and filter nothing, so the screen does not say
they do.** `resolved_for()`'s own docstring records that nothing calls it on the list
path, deliberately, because turning on a filter nobody can see or change would
silently shrink thirty people's lists. The copy on the screen says the answers are
saved, and stops there. This is the same class of care as never rendering a
suppressed `cohort_signal` as a zero: a true-sounding sentence the system does not
support is worse than a plainer one that it does.

**The first-run redirect is a nudge and not a gate**, on two counts. It fires only
when the Builder did not ask for something specific, so a deep link into a posting
still resolves; and a failed `GET /v1/onboarding` logs and routes to the list rather
than blocking it. Every onboarding field is optional server-side, so a Builder who
skips is a Builder with NULLs — the honest state, and exactly what the nullable
columns mean. Gating the list on a form would lose people at screen zero in a
population where this task's own § *Onboarding* says "every additional screen loses
someone".

#### Proposed `DECISIONS.md` entry — FULL TEXT, no number allocated

> **26 — Why onboarding is two screens and the form asks seven questions**
>
> `26-profile-creation.md` § *Onboarding* asks for three steps, "fifteen fields", and
> 15–20 seed postings drawn across `role_track`s. The screen that shipped on
> 2026-08-02 has **two** screens, **seven** fields and an eighteen-posting draw that
> cannot yet be diverse. All three departures are deliberate and none of them is a
> shortcut.
>
> **Two screens, because the task's own third step is "nothing else".** The budget in
> the definition of done is ≤3 and the third step in the body is *"Resist adding
> steps. The population includes people for whom this is a first technical product;
> every additional screen loses someone."* A confirmation screen would have spent the
> remaining budget on the single thing the task named as the failure mode. The
> outcome — including the one case the endpoint reports without failing on, a
> `seed_judgements_recorded` lower than what was sent — goes in a toast, and the
> Builder lands on the list. `frontend/check_client.mjs` asserts `SCREENS.length` so
> the ceiling is enforced rather than remembered.
>
> **Seven fields, because pydantic ignores the eighth.** `OnboardingRequest`
> (`backend/webapp/onboarding.py`) declares seven, and an undeclared key is not a
> 400: it is a **200 that stores nothing**, with no log line anywhere. An eighth
> question on the screen would have been answered by a Builder, discarded silently,
> and confirmed as saved. Widening to fifteen means eight new columns with eight
> generated CHECK constraints — a schema decision, taken with real answers in hand,
> which is the treatment `PRIOR_DOMAINS` and `SCHEDULE_CONSTRAINTS` already document
> for themselves. The screen asks what can be stored, and both checkers now derive
> the field list from the model so the two cannot drift apart in silence.
>
> **An eighteen-posting draw that is round-robin over a field that is always null.**
> `role_track` is on `job_facts` and the `jobs_app` view does not select it, so it
> reaches no response body. `pickSeed()` spreads across `tracks.trackOf()` regardless:
> with one bucket that is the payload order unchanged, and it becomes the diverse draw
> the task asked for on the day the field lands, with no edit. Rejected: picking the
> top eighteen and adding a comment promising diversity later.
>
> **And one fixture was wrong rather than one endpoint.** The frozen
> `POST /v1/onboarding` response carried `completed_at` with a trailing `Z`.
> `builder_profiles.onboarded_at` is `TEXT` written by `lib.timeparse.utc_now_str()`,
> whose docstring forbids an offset because both pipelines compare these as strings.
> The `Z` was inherited from `API-CONTRACT-v1.md`, which invented the shape against no
> code — which is the general hazard of a contract fixture nothing checks, and the
> reason those two files moved into `shipped/` rather than staying prefixed
> `ASPIRATIONAL_`.

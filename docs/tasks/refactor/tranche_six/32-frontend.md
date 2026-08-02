---
kind: task
written: 2026-07-28
generator: none
---

# 32 — Frontend

**Status:** ~~todo~~ **Today, Job detail and Saved are built (2026-08-02). Search,
Onboarding and Contribute are not, and two of the three have no backing table.**
**Depends on:** 26, 27, 28, 30, 31. **Blocks:** nothing.

Build `frontend/`. ~~It is currently a single `.gitkeep`.~~

> **STALE as of `fe3df28`, 2026-08-02.** `frontend/` carries
> [`README.md`](../../../../frontend/README.md), `verify_fixtures.py` and 39 frozen
> fixtures under `fixtures/shipped/` and `fixtures/contract/`. There is still **no
> application code** — that part of the sentence stands — but the contract mocking this
> task's own § *Mocking* asked for exists, and `README.md` there is the list of everything
> a client author gets wrong if nobody says it. **Read it before writing a line of client
> code.** The same stale sentence was in `26-profile-creation.md` and
> `API-CONTRACT-v1.md`; all three are corrected.

## The backend is further along than the empty directory suggests

Already landed: Google SSO, session cookies, `require_user`, `GET /v1/jobs`,
`GET /v1/jobs/{id}`, `POST /v1/events`. `docs/tasks/job_ingest/` records all five
tasks done, and `backend/webapp/README.md` carries the one manual step no automated
check covers — the live Google login round trip.

~~So this is a client against a working API, not a full-stack build.~~

> **THIS IS THE STALEST SENTENCE IN THE TRANCHE, corrected 2026-07-31 (task 34).**
> The API is working; it is not the API this task's own surface table needs. Today
> `GET /v1/jobs` returns a **flat list with ~~no `rank`,~~ no `bucket`, no `tracks[]`
> grouping ~~and no `request_id`~~** — and it returns raw `match_score`/`fit_score`, which
> `API-CONTRACT-v1.md` explicitly forbids. Every surface in the table below needs
> backend work that does not exist: Today-grouped-by-track needs task 30, the cohort
> save signal needs 27 **and** 28, Search needs 25's `search_queries` table, and
> Onboarding needs 26's `builder_profiles`. **Read the dependency line, not this
> sentence.** The auth, session and read plumbing genuinely is done and genuinely is
> reusable; the response shape is the work.
>
> **Half of that list landed 2026-08-01, in task 27** — struck above, kept per
> `DOCS-POLICY.md` rule 4. `GET /v1/jobs` now sets a 1-based `rank` on every row and
> returns a top-level `request_id` (`backend/webapp/jobs.py:370`, `:424`, `:432`
> — re-derived 2026-08-02; the old `:396-406` predated two rounds of insertions
> above it), and the pair
> rides in the opaque cursor, so ranks **resume across pages** instead of restarting
> at 1 — which is what makes the next section's requirement satisfiable at all rather
> than merely stated. **`bucket` and `tracks[]` are still absent** and are still task
> 30's, and raw `match_score`/`fit_score` are still in the payload for the reason
> `AUDIT.md` § *What is open* records: removing them before `bucket` exists would
> leave the API unable to express relevance at all. So the correction narrows this
> paragraph; it does not retire it.

## Non-negotiable: emit `rank` and `request_id`

Task 27 issues a `request_id` and per-row `rank` when a list is rendered, and the API
**rejects impression batches that omit either**. The client must echo both on every
event from that render.

This is the one requirement that cannot be added later. Everything else in this task
can be redesigned; impressions logged without position are permanently unusable.

Emit impressions for rows that were actually visible, not for every row in the
payload. A row below the fold was not examined, and recording it as an impression
poisons the skip derivation.

## Design constraints from the population

These matter more than the framework choice.

**Mobile first, genuinely.** Many Builders will be phone-primary. This is not a
responsive-design afterthought — the daily list, the dismiss action and the reason
picker all need to work with a thumb on a small screen. If desktop is easier to build,
build mobile anyway and let desktop be the adaptation.

**Plain language throughout.** No "match score," no "relevance," no jargon inherited
from the schema. A bucket label should read like something a person would say. This is
the first technical product some Builders will use closely.

**Never an empty search box.** Task 25 seeds `search_queries` from `role_track`
precisely because someone who does not know what role they want cannot write a good
query. Open on suggested tracks and seeded searches, not a blank input.

**Show the reasoning, not the number.** Per task 30, `gap_bridging_angle` is the
primary content — the transferable-skills story is what makes a posting legible to a
career changer. The bucket is a label on it, not the point.

## Surfaces

| screen | contents |
|---|---|
| **Today** | the daily list, grouped by `role_track`, bucketed, freshness-ordered within bucket |
| **Job detail** | full description, `gap_bridging_angle`, `risk_factors`, apply link, posting age, cohort save signal if ≥3 |
| **Saved** | the Builder's saved postings |
| **Search** | seeded suggestions, then their own queries; watcher counts |
| **Onboarding** | task 26's structured form and seed judgements |
| **Contribute** | task 24's contributor onboarding, if they choose to |

Dismiss needs a reason picker — task 27's enum — presented as a short list, not free
text, and skippable. A dismiss with `other` is still worth more than a dismiss the
Builder abandoned because the form was tedious.

## Honest about the market

The population is applying to entry-level roles that receive very high applicant
volume, in a market where surveys put the share of job seekers who have hit a ghost
job above 90%. Two consequences for the UI:

- **Show posting age prominently.** It is the most reliable staleness signal available
  and it is actionable.
- **Do not imply a match is a likelihood of being hired.** Bucket labels should read as
  fit, not as odds. This is the same discipline as refusing a cardinal score, applied
  to wording.

## What the work turned up

Written 2026-08-02, on landing Today / Job detail / Saved.
`frontend/README.md` § *What building against these fixtures turned up* carries
the same list with the `file:line` for each; this is the short version and what
each one blocks.

**The track vocabulary is decided and unusable.** `DEC-77` groups by
`extract.ROLE_TRACK` — nine snake_case values, the ones actually stored on
`jobs.role_track`. `frontend/README.md`'s claim that *"the only track vocabulary
in the code is `score.TRACKS`"* was wrong; there are two, and it named the
wrong one. But **`role_track` is not selected by the `jobs_app` view**, so it is
in no response body and there is nothing to group by. Today therefore renders as
one ungrouped list, which is also what `schema.py` predicts on its own: the
column is NULL on every pre-task-11 row. The client groups by the field the
moment it appears and has the assertion that goes red on that day. **Two lines
in two files this task does not own.**

**Three contract fields have no column and one has no parameter.**
`comp.is_estimated` exists nowhere in `schema.py` — and `jobs_app` coalesces
`salary_text` together with a derived currency+band into one `salary` field, so
the stated/derived distinction the flag exists to preserve is destroyed before a
client sees it. `GET /v1/jobs` has no state filter, so **Saved is a full crawl
of the list** — two requests at 166 rows, and not a design.

**A client that has not rendered a list can record nothing.** Every event batch
needs a `request_id` and the only source of one is a list render. A detail page
reached cold has to fetch a list purely to obtain an id. That collides with this
tranche's own rule that `GET /v1/jobs/{id}` still serves a dismissed posting so
the undo is reachable — the list that would supply the id is the one that hides it.

**Every live posting is unscored.** `gap_bridging_angle` and its four
neighbours were null on every row the API returned for `pursuit`. The fixtures
show that as one row in four, which reads as an edge case; it is currently the
only case, and it is what the card has to look good in.

**Both fixture checkers are now wired into the suite**
(`backend/tests/test_frontend_fixtures.py`). Neither was, which is the rule 7
decay `DOCS-POLICY.md` names. `frontend/verify_fixtures.py` checks that the
fixtures still describe the server; the new `frontend/check_client.mjs` checks
the other direction and re-derives `ROLE_TRACK`, `DISMISS_REASONS` and
`CLIENT_EVENT_NAMES` out of Python so the client cannot drift from them
silently. **The first one had a hole and it is defect `D70`:** it composed the
expected row from `LIST_COLUMNS + STATE_FIELDS + ("rank",)` and hardcoded the
tail, so task 28's `COHORT_FIELDS` — which lands between them — was invisible
to it. The fixtures omitted `cohort_signal`, the expectation omitted it too,
the two agreed with each other, both disagreed with the source, and the check
exited 0. Now fixed: the composition derives `COHORT_FIELDS`, the fixtures are
re-frozen with the key in the position the endpoint produces, and a guard fails
on any tuple in `jobs.py` the verifier does not recognise, so a fourth group
cannot arrive the same way. `rank` remains a literal — there is no constant for
`ast` to read — and that residue is documented at the seam rather than left to
be rediscovered, which is how `D70` happened.

**Two of `frontend/README.md`'s three "BLOCKED" entries were falsified within
the day.** Task 26 gave `builder_profiles` storage and `POST /v1/onboarding` a
route (plus a `GET /v1/onboarding` that document never listed and no fixture
covers); task 28 built `cohort_signal`. `search_queries` is the one still
correct. That document's own line — *"the blocked/unblocked status of a field is
the fastest-rotting sentence in this file"* — was right and understated, and the
measurement is now recorded beside it. A side effect worth naming: the
`ASPIRATIONAL_` prefix on the two onboarding fixtures is now false, and those
two were **built against**, so the deviation list between contract and shipped
is an artifact somebody has to produce.

**The no-build-step constraint held.** Plain HTML, one stylesheet, ES modules,
no framework, no npm, no `package.json`. The modules are `.mjs` so the same
files load in a browser and under `node` with nothing installed.

## What the search screen turned up

Written 2026-08-02, on landing the last code row of the table above.
`frontend/README.md` § *What building against these fixtures turned up* items
7–10 carries the same list with the `file:line` for each, and its new section
§ *Where the search contract and the shipped API differ* owns the deviation
list. This is the short version.

**The surfaces table's "watcher counts" is the one line in it that had to be
rewritten rather than implemented.** This file says Search shows *"seeded
suggestions, then their own queries; watcher counts"*, and
`API-CONTRACT-v1.md`'s fixture spells that as `watcher_count: 7` and
`watcher_count: 1`. A raw count is not what shipped and must not be: the
exposed field is `watcher_bucket`, a label or `null`, suppressed below
`schema.SEARCH_MIN_WATCHERS = 4`. **The contract's own fixture contains the
thing the suppression exists to prevent** — a count of one, in a thirty-person
cohort who sit in a room together, on a query anyone can create by typing it.
`DEC-85` is why the floor is 4 where `cohort_signal`'s is 3. So the phrase in
the table stands as a description of the surface and is wrong as a description
of the payload, and the client renders **no badge at all** for the suppressed
case, which is every case at today's cohort size.

**`role_track` now means two different things, and this feature is the first
place both appear.** On a job row it is `job_facts.role_track`, the posting's
family — landed at the read edge earlier the same day, which is what made this
task's *Today grouped by track* row work at all. On a query object it is
`search_queries.role_track`, the track a seeded suggestion was generated from.
Same closed vocabulary, two different subjects, and **they never share a JSON
object**, so nothing structural stops them being conflated — only the copy
does. A suggestion says *"For roles like: …"*; nothing groups search **results**
by track.

**The results list needed no new client code, which was the test of a claim
made a day earlier.** `backend/webapp/search.py` imports `LIST_COLUMNS`, the
three joins and the cursor codec from `jobs.py` rather than restating them, so
`GET /v1/searches/{id}/results` is `/v1/jobs`' shape field for field.
`parseJobRow`, `jobCard`, `askReason`, `observe` and `remember` were reused
unchanged, and the checker asserts the stronger property: `jobCard` produces
**byte-identical output** from a search-result row and from the `/v1/jobs` row
for the same posting. It also needed no `js/crawl.mjs` workaround — a search
results page is a real render, so its rows get real impressions, where the
Saved crawl deliberately emits none.

**`D70` would have re-opened in a new file, and then again one directory up.**
`verify_fixtures.py`'s `_KNOWN_JOBS_TUPLES` closed the class for `jobs.py`;
`search.py` arrived with two module-level tuples and no guard, so a new
response-key group there would have landed exactly the way `cohort_signal` did,
in a checker that had already learned the lesson next door. *A guard that
protects one file is a guard against one instance.* And
`backend/tests/test_frontend_fixtures.py` derived its module list from a
pattern that was derived in the filename and **hardcoded in the directory**, so
the two top-level modules the verifier now reads matched nothing — which would
have made its mutation test pass for the wrong reason, the exact failure its own
docstring already records once. Both are fixed. Third instance of one shape in
three days.

**End-to-end verification was not available and nothing here claims it.** The
live database is missing task 25's five search objects entirely — the four
tables and the id sequence — and `cohort_signal`'s `GRANT`; `verify_schema()`
fails on exactly those and creating them needs an admin credential this stream
does not hold. Every claim above is checked against the source and against the
frozen fixtures, which is a weaker instrument than the round trip items 1–6 of
`frontend/README.md`'s list got.

## Definition of done

- Signs in, lists, opens, saves, dismisses with reason, applies, searches.
- Every render issues a `request_id`; every event echoes it with the correct `rank`.
- Impressions fire on visibility, not on payload receipt.
- Works on a phone, tested on a real one.
- No 0–100 score displayed (task 30).
- Empty states are seeded, never blank.
- Onboarding completes without any manual DB work.
- The live Google login round trip is verified by hand, per `backend/webapp/README.md`.

### Where each of those stands, 2026-08-02

| item | state |
|---|---|
| signs in, lists, opens, saves, dismisses with reason, applies | **done** |
| searches | ~~**not done** — no route and no `search_queries` table (task 25)~~ **done 2026-08-02.** Task 25 landed four tables and **six** routes; `frontend/js/search.mjs` is the screen — seeded catalogue, watch/unwatch, submit, and one query's results as a real render. One `ROUTES` row covers both views. |
| every render issues a `request_id`; every event echoes it with the correct `rank` | **done** — one render across pages, `js/events.mjs` groups by render id and never merges two |
| impressions fire on visibility, not on payload receipt | **done** — IntersectionObserver, 50% for 500ms |
| no 0–100 score displayed | **done** — and asserted, including that the `match_reasons` deltas never reach a chip, since they sum to `match_score` |
| empty states are seeded, never blank | **done** for Today, Saved **and Search** — and Search is the one this bullet was written about (§ *Design constraints*, "never an empty search box"). The screen opens on `GET /v1/searches?scope=suggested` with the form **below** the suggestions, and `check_client.mjs` asserts the document order rather than the presence, because a catalogue underneath the box is a blank box. |
| works on a phone, **tested on a real one** | **not done.** Built mobile-first — 44px targets, bottom sheet, sticky action bar, safe-area insets — and rendered against live payloads, but no phone was in the loop. This one needs a person. |
| onboarding completes without manual DB work | ~~**not done** — out of scope for this stream; `POST /v1/onboarding` is another stream's~~ **done 2026-08-02, by task 26's stream** — `frontend/js/onboarding.mjs`, two screens, routed at `#/onboarding` and reached automatically on first run. See `tranche_five/26-profile-creation.md` § *What the work turned up*. |
| live Google login round trip verified by hand | **not done** — needs an interactive browser session |

Verified against the running API instead: both response shapes key-for-key
against `frontend/fixtures/shipped/`, `rank` resuming at 4 on page two of one
render, all seven `ContractError` codes reproducing their fixtures byte for
byte, and a `save` → read-back → `unsave` → read-back round trip. The list
endpoint was served from `HEAD`, because the working tree's copy joins a
`cohort_signal` table whose GRANT has not been issued yet.

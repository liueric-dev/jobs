# frontend/

~~Frozen API fixtures. No application code yet — task 32 builds against these.~~

> **The client landed 2026-08-02 (task 32).** Plain HTML/CSS/ES-modules, no build
> step, no framework, no npm, served from the same origin as the API. `index.html`,
> `app.css`, `js/*.mjs`, `serve.py`, `check_client.mjs`. The fixtures are unchanged
> and are now checked from **both** ends — see § *Running it* and § *What building
> against these fixtures turned up*, which is the part worth reading first if you
> are about to touch the API.

`API-CONTRACT-v1.md` § *Mocking* asks for one realistic
response per endpoint, frozen as JSON, so the client can be built before the
backend lands and so the fixtures become contract tests both sides run
afterwards. This is that, split in two, because the frozen contract and the
shipped API genuinely differ and **that difference is the frontend's whole
problem**.

> **Where the contract is.** `API-CONTRACT-v1.md` is cited by name throughout
> this file, `backend/webapp/` and `js/`. It lived at
> `git show refactor-freeze-2026-08-02:docs/tasks/refactor/API-CONTRACT-v1.md`
> and was deleted 2026-08-02 with the
> rest of `docs/`. It is the one deleted document still governing live code, so
> read it before changing a response shape.
> `fixtures/contract/` is that document rendered as JSON and is the part of it
> that did survive in the tree.

```
index.html app.css   the client. One page, hash routes, no build step.
js/*.mjs             api, events, tracks, format, ui, today, saved, detail,
                     search, onboarding, app.
serve.py             dev launcher: this directory + the API on one origin.
fixtures/shipped/    what the API returns TODAY. Derived from the code.
fixtures/contract/   the target shape in API-CONTRACT-v1.md. Derived from the doc.
verify_fixtures.py   re-derives every shape claim in shipped/ from the source.
check_client.mjs     the other direction: the client, against shipped/.
```

**Adding a screen is two lines and one module.** `js/app.mjs`'s `ROUTES` table
takes one row — `{name, pattern, show}`, where `show(root)` returns the
screen's teardown — and `index.html` takes one `<a data-tab="…">` whose value
is that same `name`, because `markTab()` matches on it. `check_client.mjs`
asserts the two lists agree, so a screen added to one and not the other goes
red. ~~Search (task 25) is the next row; it has no route and no table yet.~~

> **Search landed 2026-08-02** and the recipe was exact: one row, one `<a>`, one
> module, and nothing else in `app.mjs` or the shell changed. It takes **one row
> for two views** — `/^\/search/` matches both `#/search` (the seeded catalogue)
> and `#/search/<id>` (one query's results), and `js/search.mjs` reads the id out
> of the hash itself rather than claiming a second row for a distinction only it
> cares about. **Contribute (task 24) is the next row**, and is the last of the
> six surfaces in `git show refactor-freeze-2026-08-02:docs/tasks/refactor/tranche_six/32-frontend.md`.

Build the client's types against `contract/`. Build the client's **parser**
against `shipped/`, because that is what the server sends.

## Real vs aspirational

| endpoint | route today | fixture set |
|---|---|---|
| `GET /v1/jobs` | yes, `jobs.py:409` | both — shapes differ |
| `GET /v1/jobs/{id}` | yes, `jobs.py:581` | both — shapes differ |
| `POST /v1/events` | yes, `jobs.py:916` | both — **request shapes agree** |
| `GET /v1/me` | yes, `auth.py:465` | both — contract adds an onboarding block |
| `GET /v1/searches` | ~~**no route, no table**~~ **yes, `search.py`** | **both — shapes differ** |
| `POST /v1/searches` | ~~**no route, no table**~~ **yes, `search.py`** | **both — shapes differ** |
| `GET /v1/searches/{id}` | **yes, `search.py`** | `shipped/` only — not in the contract |
| `POST /v1/searches/{id}/watch` | **yes, `search.py`** | `shipped/` only — not in the contract |
| `POST /v1/searches/{id}/unwatch` | **yes, `search.py`** | `shipped/` only — not in the contract |
| `GET /v1/searches/{id}/results` | **yes, `search.py`** | `shipped/` only — not in the contract |
| `POST /v1/onboarding` | ~~**no route, no table**~~ **yes, `onboarding.py:540`** | ~~`contract/` only — **and nothing checks it**~~ **`shipped/`, 2026-08-02** |
| `GET /v1/onboarding` | **yes, `onboarding.py:523`** | ~~**no fixture at all**~~ **`shipped/`, two of them** |

~~Every aspirational file is named `ASPIRATIONAL_*`. `search_queries` and
`builder_profiles` exist nowhere in `schema.py` or `schema_web.py` — these three
are not "unimplemented endpoints", they are a feature with no storage.~~

> **HALF OF THAT WENT STALE ON THE DAY IT WAS WRITTEN, 2026-08-02.** Task 26
> landed, and the sentence has to be split rather than corrected, because the
> three endpoints it grouped no longer share a state.
>
> ~~**`search_queries` still exists nowhere** — grepped 2026-08-02, zero hits
> across `backend/`. `GET /v1/searches` and `POST /v1/searches` are unchanged
> and the two rows above are still right: a feature with no storage, waiting on
> task 25.~~
>
> **FALSIFIED THE SAME DAY IT WAS GREPPED, by `e3abd6e` (task 25).** All four
> tables exist in `backend/schema.py` — `search_queries`,
> `search_query_watchers`, `search_query_signal`, `search_query_results` — and
> `backend/webapp/search.py` carries **six** routes, four more than the contract
> ever described. So all three of this document's "BLOCKED" entries and all
> three of its "no storage" claims were falsified inside forty-eight hours, and
> the sentence further down that calls this "the fastest-rotting sentence in this
> file" is now measured twice rather than once.
>
> **`builder_profiles` has storage.** It is a real table in
> `backend/webapp/schema_web.py`, declared `("SELECT", "INSERT", "UPDATE")` in
> `REQUIRED_TABLES` (`schema_web.py:100`), with a composite foreign key to
> `app_users(id, profile)` — which is what `_ensure_app_users_profile_key`
> (`schema_web.py:428`) exists to make possible.
>
> **And `POST /v1/onboarding` has a route**, in a new
> `backend/webapp/onboarding.py`, included at `app.py:106`. **There is also a
> `GET /v1/onboarding`, which this document never listed and for which no
> fixture exists in either directory.**
>
> Two consequences worth stating rather than leaving to be discovered:
>
> * ~~**The `ASPIRATIONAL_*` prefix is now load-bearing in the wrong direction.**
>   `fixtures/contract/ASPIRATIONAL_POST_v1_onboarding.{request,response}.json`
>   describe an endpoint that ships. The prefix says "no route", the route
>   exists, and **nothing checks the two against each other** —
>   `verify_fixtures.py` reads `shipped/` only, by design, because there was no
>   code to check `contract/` against. Now there is, for one endpoint. Whoever
>   owns task 26 should either move those two into `shipped/` and teach the
>   verifier about them, or record where the shipped shape deviates. They were
>   built against, so the deviation list is the artifact that matters.~~
>   **DONE 2026-08-02, task 26.** Both are now
>   `shipped/POST_v1_onboarding.{request,response}.json`, plus
>   `shipped/GET_v1_onboarding.json` and `.first_run.json`, which existed in
>   neither directory. `verify_fixtures.py` derives all four shapes out of
>   `onboarding.py` — the two route returns and `_state()` are single dict
>   literals and the request is a pydantic model, so unlike the list endpoint
>   there is **no `rank`-shaped hardcoded residue** in that block. **The
>   deviation list is one item and the fixture was the thing that was wrong:**
>   `completed_at` carried a trailing `Z`, inherited from a contract that
>   invented the response shape against no code. `onboarded_at` is TEXT written
>   by `lib.timeparse.utc_now_str()`, whose docstring says
>   `'%Y-%m-%dT%H:%M:%S'` must not gain an offset because both pipelines
>   compare these as *strings*. Same trap `first_seen` sets. Both checkers now
>   assert the absence of the zone.
> * ~~**This client calls neither onboarding route.** The onboarding *screen* is
>   out of task 32's scope, so the route is live and unexercised by anything in
>   `frontend/`.~~ **It calls both, as of 2026-08-02** — `js/onboarding.mjs`,
>   routed at `#/onboarding`, reached automatically on first run from
>   `js/app.mjs`.

Everything in `shipped/` is real, has a route today, and is checked by
`verify_fixtures.py`. Nothing in `contract/` is checked by anything, because
there is no code to check it against — ~~and for the two search files that is
still literally true~~ **and that is now false for five of its files.** Three
describe `/v1/searches`, which ships, and two describe onboarding, which moved.
The three that stayed **stay deliberately**, because they describe a shape that
was never built and the difference is the artifact; see the next section.

## Where the search contract and the shipped API differ

Task 25's six routes landed on 2026-08-02 and this client was built against
them. The contract's three `ASPIRATIONAL_*searches*` fixtures were **not**
moved into `shipped/` and the shipped API was **not** changed to match them.
`fixtures/contract/MANIFEST.json` § `_searches_deviations` carries the full
list; these are the three that change what a client does.

**1. `watcher_count: 7` vs `watcher_bucket: "4-6"` or null — and the contract's
version is not merely unbuilt, it is wrong.** The shipped field is a label or
`null`, and `null` covers 0, 1, 2 **and** 3 watchers indistinguishably, because
`search_query_signal` holds no row below `schema.SEARCH_MIN_WATCHERS = 4`. The
contract fixture contains the exact thing the suppression exists to prevent:
`watcher_count: 1` on one query, which is one identifiable person in a
thirty-person cohort who sit in a room together, on a query **anyone can create
by typing it**. `DEC-85` sets out why the floor is 4 where `cohort_signal`'s is
3 — the observed object is attacker-chosen and the planter is always a watcher —
and `DEC-87` why the count is a separate table rather than a column the service
could write. Do not "fix" the API towards this fixture.

**2. One nested `{suggested, mine}` vs two scoped requests.** The shipped route
returns `{searches, scope}` and takes a `scope` parameter, so `js/search.mjs`
issues both with `Promise.all`. Two things the nested shape would have hidden:
the scopes **overlap** — a seeded query the caller watches is in both, byte for
byte — and there is deliberately **no third scope**, because the text of a
builder-created query is often self-identifying and a browsable list of
everyone's would hand an observer the whole population to plant against.

**3. 202 with `queue_position` vs 200 with the query object.** Nothing computes
a queue depth: the nightly cycle picks up whatever is due, so there is no
position to report. The shipped answer to "when will this run" is `last_run_at`
being `null`, which the client renders as *"This one hasn't run yet."*

Two smaller ones, recorded without ceremony: the contract's request carries a
`watching` flag that cannot exist — the submitter is registered as a watcher
unconditionally, which is what makes *"one row, two watchers"* true — and the
contract covers **two of the six** routes, missing the one that actually returns
postings.

## Verifying and regenerating `shipped/`

```bash
python3 frontend/verify_fixtures.py      # exit 0 if the fixtures still match the code
```

Stdlib only, no venv — it reads the constants out of
`backend/webapp/{jobs,auth,schema_web}.py` with `ast` rather than importing
them, because those modules import `fastapi` and `pydantic`, which live only in
`webapp/.venv`.

It checks **shape**, not values: the exact key set and order of every job
object, the top-level keys of every response, the event vocabulary, the dismiss
vocabulary, that `rank` runs 1..N across the two pages, that `next_cursor`
really decodes to the last row of page one, and that every error `code` is one
`jobs.py` can actually raise. It does not check that Mount Sinai is hiring.

There is no generator. Regenerating means editing the JSON by hand and running
the verifier — which is the honest arrangement, and the one
`.claude/CLAUDE.md` describes for `docs/ingest/*.md`: treat "never hand-edit" as
applying to a generator that exists, and here there is none.

`fixtures/shipped/MANIFEST.json` records the `file:line` every shape was derived
from, one entry per fixture. It is a sidecar rather than a `_comment` key inside
each fixture on purpose: those bodies are byte-faithful, and an extra key would
be a lie in the shape of documentation.

## Three contract fields are BLOCKED, not merely unimplemented

The gap between the two directories is mostly work nobody has done yet. Three
items are different — they are waiting on something, and no amount of frontend
work moves them. **One of the three had its blocker removed on 2026-08-01,
while these fixtures were being written**; it is recorded below as it now
stands, not as it was.

**`bucket` — blocked on task 30, which is itself gated on task 29's labels.**
Task 30 contains the within-band experiment that decides whether a numeric
score is ever justified; until it runs there is no defensible way to draw the
`strong` / `worth_a_look` / `stretch` boundaries. Task 29 needs a second
labeller before 30 has anything to run on. Guessing thresholds here would
produce a field that looks authoritative and is arbitrary. **Still blocked.**

**Removing raw `match_score` / `fit_score` — blocked on `bucket` existing
first.** The contract says *"no 0–100 score appears anywhere; `bucket` carries
the claim"*. `bucket` does not exist, so removing the raw scores now would leave
the API unable to express relevance at all — strictly worse than the
divergence. This is a deferral with a named blocker, not a decision, and it is
decided by task 30 landing. `min_score` is a public query parameter today for
the same reason. **Still blocked**, transitively on the one above.

**`cohort_signal` — the blocker was `job_events` having no `app_user_id`
column, and that column landed 2026-08-01. ~~Now unblocked and unbuilt.~~
BUILT 2026-08-02, task 28 — see the correction below.** The
contract requires suppression below three saves, and "three *Builders*" was not
a question `job_events` could answer: it had a `profile` and no user id, and
thirty Builders share the one `pursuit` profile, so counting distinct rows
counted one person's three saves as three people's — a privacy control
returning a wrong answer, which is worse than returning `null`. Defects **D66**
and **D67** in `git show refactor-freeze-2026-08-02:docs/ingest/DEFECTS.md` were the same missing column surfacing
in `state.seen` and `state.applied`, and both are now **fixed**: the join
resolves by `app_user_id` (`jobs.py:305-310`), `POST /v1/events` writes it, and
pre-column rows carry NULL and resolve to `false` for everyone rather than
`true` for everyone. ~~**Task 28 itself is still unbuilt** — nothing computes the
`3-5` / `6-10` buckets or enforces the below-three suppression, so
`cohort_signal` is `null` in every `shipped/` fixture because the field does not
exist at all, not because the count was low.~~

> **TASK 28 LANDED 2026-08-02 and the struck sentence is wrong in both halves.**
> Something computes the buckets and the field exists. `cohort_signal` is a real
> table (`backend/schema.py:147`, `COHORT_SIGNAL_TABLE`, with a
> `cohort_signal_bucket` CHECK at `:657`), and `backend/webapp/jobs.py` sets
> `item["cohort_signal"]` on **both** the list rows (`jobs.py:558`) and the
> detail row (`jobs.py:622`), via `COHORT_FIELDS` (`jobs.py:386`) and a
> `cohort_signal(save_bucket)` helper that returns `{"save_bucket": …}` or
> `null`. Read from the working tree at this commit and reported as such; the
> cohort stream owns whether that is its final shape.
>
> **`null` still means two different things and the endpoint cannot tell them
> apart either** — "nobody saved this" and "one or two Builders did" both
> produce no row. That is the suppression requirement, not a limitation, and it
> is why this client renders nothing at all rather than any "fewer than three"
> copy. Absence must never be readable as *exactly* one or two.
>
> **The `shipped/` fixtures were stale on this field and `verify_fixtures.py`
> did not notice — defect `D70`. Both are now fixed.** Every job object in
> `shipped/` carries `cohort_signal`, between `dismiss_reason` and `rank` on a
> list row and last on a detail row, which is the order the endpoint produces.
> Mount Sinai carries `{"save_bucket": "3-5"}` so a client author sees the
> populated shape once; it appears in two fixtures and reads the same in both,
> because one posting cannot have two answers. Everything else is null. The
> verifier now derives `COHORT_FIELDS` and refuses to pass on a tuple it does
> not recognise — see § *What building against these fixtures turned up*, item 5.

If you are reading this well after 2026-08-01, check
`git show refactor-freeze-2026-08-02:docs/ingest/DEFECTS.md`
and `git show refactor-freeze-2026-08-02:docs/tasks/refactor/HANDOFF.md` rather than trusting this section. The
blocked/unblocked status of a field is the fastest-rotting sentence in this
file.

> **Measured, not hedged: it rotted inside twenty-four hours.** Two of the three
> entries above were falsified the day after they were written — `cohort_signal`
> by task 28, and `builder_profiles` and `POST /v1/onboarding` in § *Real vs
> aspirational* by task 26. The sentence above was right and understated.

Everything else the contract adds — `tracks[]`, `posting_age_days`,
`apply_url`, `description_html`, `closes_at`, `source{}`, and the nesting of
`comp{}` / `why{}` / `state{}` / `facts{}` — is task 32's, and is unblocked.

## Things a client author will get wrong if nobody says them

- **The event for an application is `applied`, not `apply`** (`DEC-73`).
  `job_events` is append-only with `SELECT, INSERT` and nothing else; the
  existing rows already say `applied` and are the only part of the disagreement
  that cannot be edited, so the code won and the contract moved. A client
  sending `apply` gets a 400 — see
  `shipped/errors/400_unknown_event.json`, which is that exact response.
- **`skip` is server-derived.** Sending it is a 400 with code
  `server_derived_event`, deliberately not `unknown_event`: the mistake is a
  category error, not a typo.
- **`request_id` and `rank` already ship.** Several documents say they do not;
  they landed with task 27 (`jobs.py:464`, `:565`, `:571`). `rank` is 1-based and global
  across the render, and it *continues across pages* — the render id and the
  next rank ride inside the opaque cursor, so page two starts at 5, not 1.
  A cursor issued before task 27 is a 400, not an upgrade.
- **Four fields arrive as JSON strings, not arrays.** `match_reasons`,
  `tech_stack`, `risk_factors` and `key_technologies` are TEXT columns holding
  `json.dumps(...)` output and the endpoint does not parse them. `JSON.parse`
  each one. The contract's `why.risk_factors` is a real array; the shipped
  `risk_factors` is `"[\"…\"]"`.
- **Two error shapes, not one.** The contract's `{"error": {code, message,
  request_id}}` envelope is registered for `ContractError` alone (`app.py:101`).
  A 401, a 403, a 404 and a malformed cursor come back as FastAPI's
  `{"detail": "…"}`. Both are in `shipped/errors/`; the second group is
  prefixed `NOT-ENVELOPED-`.
- **The shipped `state` has five fields, not three.** `seen` and
  `dismiss_reason` are there too, and all five are per-Builder as of
  2026-08-01. The detail endpoint deliberately does *not* hide a dismissed
  posting — undo has to be reachable — so
  `GET_v1_jobs_by_id.dismissed.json` is the state the undo flow renders from.
- **The profile is `pursuit`**, not the contract's `pursuit-cohort-2026a`, and
  job ids are 24-char sha256 prefixes (`lib/ids.py:35,45`), not the contract's
  illustrative `gh_acme_4821`.
- **An unscored posting is normal.** `jobs_app` LEFT JOINs `job_scores` and
  scoring is budget-limited, so `fit_score`, `primary_track`,
  `gap_bridging_angle`, `risk_factors` and `key_technologies` are all null
  together on a posting the nightly run has not reached. Render the row anyway.
- **A null `cohort_signal` is a privacy suppression, not "no data".** The count
  is withheld below three Builders, so `null` is the answer for *both* "nobody
  saved this" and "one or two did" — the row does not exist and the endpoint
  cannot tell them apart either (`jobs.py:389`, and `backend/schema.py` explains
  why a NULL-bucket row would publish the fact the threshold exists to
  withhold). In a thirty-person cohort who see each other in a classroom, a
  count of one is close to an identifier. **Never render it as "0 saves", a
  greyed zero, or "fewer than three"** — absence must not be readable as
  *exactly* one or two. At today's cohort size every value is null, so null is
  the case the UI has to handle well, not the edge case.
- **A `watcher_bucket` is a label or nothing, and it is nothing far more often
  than the save badge is.** Same shape of rule as `cohort_signal` and a
  **higher** floor: `search_query_signal.watcher_bucket` is `NOT NULL` and the
  row is *absent* below `schema.SEARCH_MIN_WATCHERS = 4`, so `null` is the
  answer for zero, one, two and three watchers alike. Render it as **no badge**
  — never a zero, never a greyed dash, never "fewer than four", never "be the
  first to watch this". The labels are `4-6` / `7-10` / `11+` and, unlike
  `COHORT_BUCKETS`, they do not overlap. At today's cohort size every value is
  null.
- **`role_track` means two different things and this feature is where both
  appear.** On a **job row** it is `job_facts.role_track` — the posting's
  family, the axis `js/tracks.mjs` groups Today by. On a **query object** it is
  `search_queries.role_track` — the track a *seeded suggestion* was generated
  from, i.e. why that row exists. Same closed vocabulary out of
  `backend/extract.py`, two different subjects, and they never share a JSON
  object. Nothing structural stops them being conflated; only the copy does,
  which is why a suggestion reads *"For roles like: Working with data"* and
  nothing groups search **results** by track at all.
- **And the bucket counts the reader.** The fold is
  `COUNT(DISTINCT app_user_id)` over the whole profile (`backend/cohort.py:114`),
  which includes whoever is looking at the page. So the copy is "3-5 Builders
  saved this posting", never "3-5 *other* Builders" — that would be wrong by one
  exactly when the reader is one of them, and wrong in the flattering direction.
- **`comp.is_estimated` must be honoured.** Adzuna predicts salary; showing a
  prediction as though the employer stated it is a trust problem, not a
  formatting one.
- ~~**The track vocabulary is undecided.** The contract's one example,
  `ai_operations`, is a `role_archetype` value in `config/pursuit-criteria.json`,
  not a track. The only track vocabulary in the code is `score.TRACKS`
  (`score.py:301-302`). The `contract/` fixtures slugify those and put the
  stored Title Case in `label`; whoever implements task 32 has to actually
  decide this.~~

  > **DECIDED 2026-08-02, `DEC-77`, and the struck sentence was WRONG on its
  > facts.** *"The only track vocabulary in the code is `score.TRACKS`"* — there
  > are **two**, and the one this paragraph missed is the one that matters:
  > **`extract.ROLE_TRACK` (`backend/extract.py:307-310`)**, nine snake_case
  > values, which is what is actually stored on `job_facts.role_track`
  > (~~`jobs.role_track`, `backend/schema.py:542`~~ — **`backend/schema.py:745`**;
  > `:542` is the `profiles` DDL, so that cite was wrong about the table as well
  > as the line) and what `extract._enum` validates against
  > (`backend/extract.py:637`). `score.TRACKS` is five Title Case values written
  > by the LLM scorer into `job_scores.primary_track`.
  >
  > The client groups by **`ROLE_TRACK`**: it is the stored value, it is already
  > slug-shaped, so no mapping layer and no third vocabulary. `js/tracks.mjs`
  > holds it, and `check_client.mjs` re-derives the tuple out of `extract.py` so
  > the two cannot drift.
  >
  > ~~**And it does not appear in any response body — see the next section.**~~
  > **It does now.** See finding 1 below, which this change closes.

## What building against these fixtures turned up

The fixtures had never been used. ~~Six~~ **Ten** things were found by using
them, in descending order of how much they cost. Items 1–6 were **re-checked
against the running API on 2026-08-02**, not inferred from the JSON. **Items
7–10 were not, and could not be**: they came from building the search screen,
and the live database is missing task 25's five search objects entirely — the
four tables and the id sequence — plus `cohort_signal`'s `GRANT`, so
`verify_schema()` fails on exactly those and creating them needs an admin
credential. They were checked against the source and against the frozen
fixtures, which is a weaker instrument, and it is named here rather than left
to be assumed.

**1. ~~`role_track` is in no response body, so DEC-77's grouping has nothing to
group by.~~ CLOSED — the field landed.** It is a column on `job_facts`
(~~`backend/schema.py:542`~~ **`:745`**) that the `jobs_app` view did not
select, therefore not in `LIST_COLUMNS`, therefore not in `GET /v1/jobs` or
`GET /v1/jobs/{id}`. *"The two lines that would fix it are in two files this
stream does not own"* — those two lines are now written: `f.role_track` is the
last entry of `_APP_VIEW_SQL` and `"role_track"` the last of `LIST_COLUMNS`.

**Both had to be last, and one of them for a reason worth carrying.**
`CREATE OR REPLACE VIEW` can only append columns, so putting it where it reads
naturally — beside `f.role_archetype` — is a reorder, which sends
`ensure_app_view` down its `DROP VIEW` fallback, and **`DROP VIEW` takes every
GRANT on `jobs_app` with it.** Nothing in the repo re-grants. That failure
surfaces as the webapp refusing to start on the next nightly run.

**What it cost the client: nothing, which was the bet.** `js/tracks.mjs` and
`pickSeed()` were both written round-robin over a field that was always null,
so that they would start working on their own. Neither changed. What changed is
the two tests that *pinned the old behaviour* — and one of them,
*"the seed draw … is rank order while it cannot"*, **went on passing after the
field landed**: the top three shipped rows sit in three different buckets, so
spread order and payload order coincide on exactly that fixture. It now asserts
the property rather than the sequence. A green test whose stated premise is
false is worth less than a red one.

The struck sentence *"which is also what `backend/schema.py:534` predicts
independently, since `role_track` is NULL on every pre-task-11 row anyway"* was
**wrong twice**: `:534` is the `profiles` DDL, and the comment it meant (now
`:730-731`) had itself gone stale when task 12 re-extracted. Measured through the
view on 2026-08-02: **134 of 166 visible `pursuit` rows carry a track, all nine
values present.** Re-measure before quoting — `git show refactor-freeze-2026-08-02:docs/facts-v3-diff.md` records
that a corpus statistic here has a shelf life of one night.

**2. There is no way to ask for saved postings.** `GET /v1/jobs` takes eight
query parameters (`jobs.py:412-420`) and not one filters on state, so Saved is
implemented as a crawl: read every page of one render and filter `saved` client
side (`js/crawl.mjs`). It is two requests at today's 166 rows for `pursuit` and
it does not scale. A `saved=true` parameter beside `include_dismissed` is the fix.

**3. A client that has not rendered a list can record nothing at all.**
`POST /v1/events` refuses a batch with no `request_id` (`missing_request_id`,
`jobs.py:682-685`), and the only source of one is a list render (`jobs.py:464`).
So a detail page reached cold — a reload on `#/job/<id>`, a pasted link — cannot
send a `save`, an `applied` or an `undismiss` until it has fetched a list purely
to obtain an id. `js/renders.mjs` does exactly that and it is a workaround, not
a design. This bites hardest on the **undo of a dismissal**: `GET /v1/jobs/{id}`
deliberately still serves a dismissed posting so the undo is reachable, but the
list that would supply the `request_id` hides it, so the cold-reload undo path
is the one place the two rules pull against each other.

**4. `comp.is_estimated` is required by the contract and exists nowhere.** Not
in `job_facts` (`backend/schema.py:564-566` has `comp_min`, `comp_max`,
`comp_currency` and no provenance flag), not in the view, not in `LIST_COLUMNS`.
The only occurrence in the tree is `comp_is_estimated` in
`backend/evals/mock_corpus.py:104`, a fixture key. Adzuna — the source the
contract names as predicting salary — is a stub (`backend/tools/ats-discover.py:57`,
task 15). Worse, `jobs_app` **coalesces away the distinction that would let a
client infer it**: `salary` is `coalesce(j.salary_text, currency || ' ' || min-max)`
(`backend/schema.py:1212-1213`), so the employer's own string and a figure the
extractor derived arrive in the same field under the same name. `js/format.mjs`
reads the flag under either spelling and qualifies the figure when it is set;
with the flag absent it shows the figure plainly, which is right today and
becomes wrong the day a predicting source lands without the column.

**5. `verify_fixtures.py` could not see a third key group — defect `D70`, now
fixed.** It built the expected row as `LIST_COLUMNS + STATE_FIELDS + ("rank",)`
and hardcoded the tail. Task 28 inserted `cohort_signal` between the state
fields and `rank` via its own `COHORT_FIELDS` tuple (`jobs.py:386`, applied at
`:558` and `:622`), which that line did not read — so the fixtures omitted the
key, the verifier's expectation omitted it too, **the two agreed with each
other and both disagreed with the source**, and the check exited 0. That is
precisely the confidently-wrong fixture the verifier's own docstring exists to
prevent, arriving through the one seam it did not look at. A verifier stops
being a derivation exactly where its hardcoding starts, and that is where the
next field always lands.

Fixed in two parts. The composition now derives `COHORT_FIELDS`; and a guard
compares every module-level tuple in `jobs.py` against `_KNOWN_JOBS_TUPLES`
and fails on a name it does not recognise, so a **fourth** group cannot arrive
the same way. Verified by adding a fake tuple to a throwaway copy of `jobs.py`
and watching it go red. **`rank` is still a literal** and that residue is
documented at the seam: the endpoint assigns `item["rank"] = …` inside the
handler, so there is no constant for `ast` to read, and pattern-matching a
subscript assignment would break on a rename of `item` and pass on a rename of
`rank`. The one case still uncovered is a new response key added with no
module-level constant at all.

**6. Every live posting is unscored, so the "unscored is normal" path is the
only path.** `fit_score`, `primary_track`, `gap_bridging_angle`, `risk_factors`
and `key_technologies` were null on every row the API returned for `pursuit` —
the fixtures show it as one row in four, which reads as an edge case. It is
currently 100%. The card falls back to `summary`, at full strength and marked
`From the posting —` rather than as a fit story; it was styled as a faint
italic footnote until it was rendered against real data, where it was the only
prose on every card.

Two smaller ones, recorded without ceremony: `GET /v1/jobs/{id}` returns no
`rank` and cannot, so a detail page has no position of its own; and the `open`
event needs one (`RANK_REQUIRED_EVENTS`, `jobs.py:91`), which is why the client
skips `open` rather than inventing a position when it has none.

### And four more, from building the search screen (2026-08-02)

**7. The search results list needed no new client code at all, which was the
test of item 5's claim.** `backend/webapp/search.py` imports `LIST_COLUMNS`,
`STATE_FIELDS`, `COHORT_FIELDS`, all three joins and the cursor codec from
`jobs.py` rather than restating them, so `GET /v1/searches/{id}/results` returns
`/v1/jobs`' shape field for field with its own `request_id` and `rank`.
`api.parseJobRow`, `ui.jobCard`, `ui.askReason`, `events.observe` and
`renders.remember` were reused unchanged, and `check_client.mjs` asserts the
stronger property directly: `ui.jobCard` produces **identical output** from a
search-result row and from the `/v1/jobs` row for the same posting. The day
those key sets diverge is the day this client needs two renderers, and that is
the assertion that will say so.

**8. It also needed no `js/crawl.mjs` workaround, and the contrast is the
point.** Saved crawls the whole list because there is no state filter (item 2)
and a cold detail page crawls it to obtain a `request_id` (item 3). A search
results page is a **real render**: the server mints the id and the ranks, the
rows were genuinely put in front of a person in that order, so they get real
impressions. That is why `crawl.mjs` deliberately emits none and this screen
deliberately does.

**9. `verify_fixtures.py` would have re-opened `D70` in a new file.**
`_KNOWN_JOBS_TUPLES` closed the class for `jobs.py`; `search.py` then landed
with `QUERY_COLUMNS` and `RESPONSE_NAMES` and **no guard at all**, so a new
response-key group there would have arrived exactly the way `cohort_signal`
did — into a checker that had already learned the lesson in the file next door.
*A guard that protects one file is a guard against one instance.* `search.py`
now has the same treatment. One thing is better here than on the list endpoint:
the query object has **no `rank`-shaped residue**, because `_row_to_query()`
composes it as `RESPONSE_NAMES + _SIGNAL_FIELDS` and assigns no key inside a
handler. The *results* row inherits `jobs.py`'s residue verbatim, since
`search_results()` does its own `item["rank"] = …`.

**10. And the same seam sat one directory up, in the test that wires the
verifier in.** `backend/tests/test_frontend_fixtures.py` derived its module list
from the literal pattern `REPO / "backend" / "webapp" / "<file>"` — derived in
the filename and **hardcoded in the directory**. Reading two top-level modules
matched nothing, so the synthetic tree in the mutation test would have been
missing them and the "it goes red" assertion would have passed for the wrong
reason again, which is the failure that file's own docstring already describes
once. The pattern now reads any depth under `backend/`. Third instance of the
same shape in three days, in three different files.

## Running it

```bash
cd backend/webapp && .venv/bin/python ../../frontend/serve.py
# then open http://localhost:8421/

# From a phone on the same network, for task 32's "works on a phone" bullet.
# Prints the address the phone should use, and what will not work yet.
cd backend/webapp && .venv/bin/python ../../frontend/serve.py --host 0.0.0.0
```

### Looking at the card without a server

`preview.html` renders `js/ui.mjs` against `fixtures/shipped/` plus the states that
file cannot express — the stale age, the missing date, an estimated comp, a title
long enough to wrap, a posting with no angle and no summary, and hostile strings.
It calls no endpoint and needs no venv, no database and no node:

```bash
python3 -m http.server 8000 --directory frontend
# then open preview.html on http://localhost:8000
```

It imports the real render functions rather than copying them, so a card that
looks right there looks right in the app or the harness is broken and says so.
Every specimen is a shipped row with one or two named overrides; nothing in it
invents a row shape. **It is a design harness, not a route** — `app.mjs` does not
know it exists and `check_client.mjs` does not read it.

**`--host` defaults to `127.0.0.1` and that default does not move.** It binds this
machine only unless you ask otherwise, because opening a listener on an app running
with no TLS and `SESSION_COOKIE_SECURE=false` should be typed rather than inherited.
`backend/tests/test_frontend_fixtures.py` asserts the default, for the same reason.

**A LAN bind buys the layout half of the phone test and not the sign-in half.** The
page renders and the API answers against live payloads — viewport, tap targets, the
bottom sheet, safe-area insets. Signing in additionally needs the LAN origin
registered as an authorised redirect URI in the Google Cloud Console, which is not a
change this repo can make; `FRONTEND_ORIGIN` also holds exactly one value, so pointing
it at the phone is what stops localhost sign-in working while it is set. `serve.py`
prints both of those on a non-loopback bind rather than leaving them to a browser that
reports neither.

`serve.py` imports `backend/webapp/app.py` unchanged and mounts this directory
at `/` **after** every router, so `/v1/*` still resolves to the API and only
unmatched paths fall through to a file. One origin, because
`backend/webapp/.env` sets `FRONTEND_ORIGIN` and `ALLOWED_ORIGINS` to
`http://localhost:8421` and the session cookie is the client's only credential;
a static server on another port is a third origin neither variable names, and
the browser's failure mode for that is to drop the cookie without saying why.
It is a development launcher — behind a real deployment the reverse proxy in
`backend/webapp/README.md` should serve these files.

Sign-in is the existing server-driven Google flow. There is no Google SDK on the
page and there must not be: `backend/webapp/auth.py`'s docstring is explicit that
the frontend-GIS variant needs JWKS signature verification this backend does not do.

### The two checkers

```bash
python3 frontend/verify_fixtures.py     # server half: fixtures still describe the code
node frontend/check_client.mjs          # client half: the code still agrees with the fixtures
```

Both are wired into `backend/tests/test_frontend_fixtures.py`, so
`cd backend && python3 -m unittest discover -s tests` runs them. That is
the actual bar — *"fails a suite someone is already running"* — and neither had
met it. (The bar was rule 7 of
`git show refactor-freeze-2026-08-02:docs/DOCS-POLICY.md`, deleted 2026-08-02.) The node one skips where node is absent; it
is not a dependency of this repo.

`verify_fixtures.py` reads **seven** modules, and two of them are **not** under
`backend/webapp/`. `backend/searchnorm.py` owns the `InvalidQuery` codes a
client can receive from `POST /v1/searches` — `search.py` re-raises them as
`ContractError(bad.code, str(bad))`, so four of the five search error codes
appear as a literal nowhere in `webapp/` — and `backend/schema.py` owns
`SEARCH_MIN_WATCHERS` and `SEARCH_WATCHER_BUCKETS`, because it generates the
`CHECK` constraint from the same tuple the writer reads. Both are read rather
than restated.

`check_client.mjs` re-derives ~~three vocabularies~~ **nine names** out of
Python and fails when they drift: `ROLE_TRACK` from `backend/extract.py`;
`DISMISS_REASONS`, `PRIOR_DOMAINS`, `SITUATIONS`, `LOCATION_PREFS`,
`REMOTE_PREFS` and `SCHEDULE_CONSTRAINTS` from
`backend/webapp/schema_web.py`; `CLIENT_EVENT_NAMES` from
`backend/webapp/jobs.py` — the last checked against every `event: "..."`
literal in `js/`, which is what would catch a client sending `apply` (`DEC-73`)
or `skip`; and `VERDICT_EVENTS`, `MAX_SEED_JUDGEMENTS` and
`OnboardingRequest`'s field list from `backend/webapp/onboarding.py`.

**The last of those is the one that catches a failure nothing else can.**
Pydantic ignores keys a model does not declare, so a client sending
`prior_domains` for `prior_domain` gets a **200** and stores nothing — no 400,
no log line, and a Builder told their answer was saved. Deriving the field set
on both sides is the only check in the repo that sees it.

### Why the modules are `.mjs`

So the same files load in a browser and under `node` with **no `package.json`
and nothing installed**. A browser dispatches on the MIME type, and `.mjs`
resolves to `text/javascript` (Python's `mimetypes`, which is what serves them);
node dispatches on the extension and reads `.mjs` as an ES module. A `.js` file
with no manifest is CommonJS to node, which would have meant adding a
`package.json` to a repo that deliberately has no npm.

## Not covered here

`POST /v1/auth/logout` and the whole `/v1/label*` surface are implemented and
outside API-CONTRACT-v1.md. The eight `GET /v1/jobs` query parameters — `limit`,
`cursor`, `q`, `remote`, `nyc`, `min_score`, `since`, `include_dismissed` — are
implemented and undocumented in the contract; `include_dismissed` is for
debugging and is not part of the client contract (`jobs.py:419-420`, `:456-457`).
`Accept: application/vnd.jobs.v1+json` is in the contract and is not read
anywhere in `webapp/`.

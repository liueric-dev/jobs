---
kind: contract
written: 2026-07-28
generator: none
---

# API CONTRACT v1 — frozen for frontend development

**Written** 2026-07-28. **Status:** target contract, not current implementation.

`GET /v1/jobs`, `GET /v1/jobs/{id}` and `POST /v1/events` already exist from
`docs/tasks/job_ingest/04-read-endpoints.md`. **Diff this against what they return
today before implementing** — this is where they need to land, not where they are.

The point of freezing it now is that `frontend/` and tasks 26–31 can proceed in
parallel. Build the client against a mock of this; fill in the backend behind it.

---

## THE DIFF THIS FILE ASKS FOR — done 2026-07-31, task 34

*"Diff this against what they return today before implementing"* was the right
instruction and nobody had followed it. Here is the diff. **Nothing was built against
this contract** — `frontend/` contains one `.gitkeep`, and the mock fixtures § *Mocking*
describes were never created.

**Three of six endpoints exist, by path only.** `GET /v1/searches`, `POST /v1/searches`
and `POST /v1/onboarding` have no route and no backing table (`search_queries`,
`builder_profiles` exist nowhere).

**Two divergences are contract *breaks*, not gaps — a conformant client fails today:**

| | contract | shipped | where |
|---|---|---|---|
| event name for an application | ~~`apply`~~ **`applied`** — RESOLVED, see below | **`applied`** | `webapp/jobs.py`, `CLIENT_EVENT_NAMES` |
| raw scores | *"**No 0–100 score appears anywhere.** `bucket` carries the claim."* | **`match_score` and `fit_score` in every row**, and `min_score` is a public query parameter | `webapp/jobs.py`, `LIST_COLUMNS` |

~~A client sending the contract's `apply` gets a **400**. Whoever implements 27/32 must
pick one; this is an undecided divergence between a frozen contract and shipped code,
and it has been sitting in both for three days.~~

> **ONE OF THE TWO IS RESOLVED, 2026-08-01, TASK 27. The other is not, and is blocked.**
>
> **`apply` → `applied`: the code wins and this document moves (`DEC-73`).** `job_events`
> is append-only evidence granted `SELECT, INSERT` and nothing else, and the existing rows
> already say `applied` — they are the only part of the disagreement that cannot be edited.
> Every `apply` in this file is struck and corrected in place; a client may send `applied`
> and nothing else.
>
> **The raw scores stay, and this is a deferral with a named blocker rather than a
> decision.** The contract's rule is *"`bucket` carries the claim"* — but `bucket` is
> **task 30's** output, and 30 is gated on task 29's labels, which need a second labeller.
> Removing `match_score`, `fit_score` and `min_score` before `bucket` exists would leave
> the API with no way to express relevance at all, which is worse than the divergence.
> **Nothing in task 27 touches the list payload's fields**, so this is unchanged and still
> open. It is decided by task 30 landing, not by whoever next reads this paragraph.

**Everything the contract adds is absent, and all of it is task 27's:** `request_id`,
`rank`, `bucket`, the `tracks[]` grouping, `posting_age_days`, `cohort_signal`,
`visibility`, `dwell_ms`, `reason`, the derived `skip`, the `{"error": {...}}` envelope
and the `Accept: application/vnd.jobs.v1+json` header. `comp{}`, `why{}`, `state{}` and
`facts{}` exist as **flat** columns rather than nested objects; `apply_url` is `job_url`;
`description_html` is `description_text`, which is a different thing; `closes_at` has no
column anywhere.

**Implemented and undocumented here:** eight query parameters (`limit`, `cursor`, `q`,
`remote`, `nyc`, `min_score`, `since`, `exclude_dismissed`), the `seen` state, `unsave`,
24-hour impression dedup, the `{recorded, deduped, skipped}` response, the `profile`
echo, `GET /v1/me`, `POST /v1/auth/logout` and the whole `/v1/label*` surface.

**Read this file as the specification for tasks 26–28 and 32 — not as a description of
the API.** The accurate description of what `/v1/jobs` returns today is
`docs/tasks/job_ingest/04-read-endpoints.md`, which is append-only and verified correct.

---

## `GET /v1/jobs`

The daily list. Grouped by track, bucketed, freshness-ordered within bucket.

```jsonc
{
  "request_id": "req_01J8XQ...",     // REQUIRED — echo on every event
  "generated_at": "2026-07-28T06:12:00Z",
  "profile": "pursuit-cohort-2026a",
  "tracks": [
    {
      "track": "ai_operations",
      "label": "AI Operations",
      "blurb": "Roles where you'd run AI tools inside an existing team.",
      "jobs": [
        {
          "job_id": "gh_acme_4821",
          "rank": 1,                  // REQUIRED — 1-based, global across the render
          "bucket": "strong",         // strong | worth_a_look | stretch
          "title": "AI Operations Coordinator",
          "company_name": "Mount Sinai Health System",
          "location": "New York, NY",
          "remote_policy": "hybrid",
          "posted_at": "2026-07-25",
          "posting_age_days": 3,
          "comp": {
            "min": 62000, "max": 78000,
            "currency": "USD", "period": "yearly",
            "is_estimated": false     // task 35 — never show estimated as stated
          },
          "why": {
            "gap_bridging_angle": "Nine years coordinating restaurant operations…",
            "risk_factors": ["Asks for one year of Salesforce…"]
          },
          "cohort_signal": { "save_bucket": "3-5" },  // null if <3 — task 28
          "state": { "saved": false, "dismissed": false, "applied": false },
          "apply_url": "https://…"
        }
      ]
    }
  ],
  "next_cursor": null
}
```

### Contract rules

**`request_id` and `rank` are mandatory.** The events endpoint rejects batches missing
either, and impressions logged without position are permanently un-debiasable. `rank`
is global across the render, not per-track — the ordering the user actually saw.

> **SHIPPED 2026-08-01, task 27, and it is the only part of this response that has.**
> `GET /v1/jobs` returns a top-level `request_id` and a `rank` on every row. **A render
> spans pages, so the pair rides in the opaque cursor** — a call without a cursor starts a
> render, a call with one continues the render the cursor names, and ranks resume rather
> than restarting at 1 on page two. There is no server-side render state; the alternative
> is a table of open renders, which is a session store with a different name. A cursor
> issued before this change is a **400**, not an upgrade: it has no rank origin, so
> continuing it would write rows that look valid and are not.
>
> Everything else in this response object — `tracks[]`, `bucket`, `comp{}`, `why{}`,
> `state{}`, `cohort_signal`, `posting_age_days` — is **unchanged and still task 32's**,
> with `bucket` additionally gated on task 30. `/v1/jobs` today returns the flat column
> shape described at the top of this file, plus these two fields.

**No 0–100 score appears anywhere.** `bucket` carries the claim. Task 30's within-band
experiment decides whether a number is ever justified; until then the field does not
exist, so nobody can render it "just for debugging."

**`cohort_signal` is null below three saves** and bucketed above it. Never an exact
count, never a recency, never an identity — task 28's suppression is a privacy control,
enforced server-side.

**`state` is per-Builder**, resolved from `builder_job_state` (task 31), not from the
cohort profile.

**`comp.is_estimated`** must be honoured in the UI. Adzuna predicts salary; showing a
prediction as though the employer stated it is a trust problem, not a formatting one.

**`why` is the primary content.** `gap_bridging_angle` is what makes a posting legible
to a career changer. The bucket is a label on it.

---

## `GET /v1/jobs/{id}`

Same job object, plus:

```jsonc
{
  "description_html": "…",
  "source": { "platform": "greenhouse", "first_seen": "2026-07-25" },
  "closes_at": "2026-08-15",     // null where unknown
  "facts": {                      // display sparingly; mostly for debugging
    "seniority_level": "entry",
    "ai_involvement": "uses_ai_tools",
    "role_archetype": "ai_operations"
  }
}
```

Requesting a detail page is **not** an impression. Emit `open` with `dwell_ms` on exit.

---

## `POST /v1/events`

```jsonc
{
  "request_id": "req_01J8XQ...",   // REQUIRED
  "events": [
    { "event": "impression", "job_id": "gh_acme_4821", "rank": 1 },
    { "event": "open",       "job_id": "gh_acme_4821", "rank": 1, "dwell_ms": 14200 },
    { "event": "save",       "job_id": "gh_acme_4821", "rank": 1 },
    { "event": "dismiss",    "job_id": "gh_beta_991",  "rank": 4,
      "reason": "wrong_level" },
    { "event": "applied",    "job_id": "gh_acme_4821", "rank": 1 }
  ]
}
```

**Client rules:**

- Emit `impression` on **visibility**, not on payload receipt. A row below the fold was
  not examined, and recording it poisons the skip derivation.
- Never send `skip` — the server derives it from an `open` at rank *k*. Sending one is a
  400 with code `server_derived_event`, which is deliberately not `unknown_event`: the
  mistake is a category error, not a typo.
- Never send `match_score`, `fit_score`, `visibility` or ~~`model_version`~~
  **`criteria_version`** — all read or set server-side. *(Renamed 2026-08-01 by `DEC-74`:
  `model_version` is one of three names `.claude/CLAUDE.md` records as planned and never
  built. `criteria_version` is what actually names the weight generation that produced the
  order, and it already exists on `job_matches`.)*
- Batch impressions; send actions immediately.

**Server rules:** reject a batch missing `request_id` or any `rank`. Set `visibility`
by event type — `save` is `cohort_anon`, everything else including ~~`apply`~~ **`applied`**
is `private`.

> **IMPLEMENTED 2026-08-01, task 27, with one deviation on `rank` — recorded rather than
> silently narrowed.** *"Any `rank`"* is enforced for `impression` and `open` only; a
> `save`, `applied`, `dismiss` or `unsave` without one is accepted and stores NULL.
> **The reason is this document's own:** § `GET /v1/jobs/{id}` says a detail-page request
> *"is not an impression"*, so an action raised from the detail page has no position in any
> render. Requiring a rank there would force the client to invent one — which is exactly
> the sentinel task 27 refused in the schema, wearing different clothes. `rank` is stored
> whenever it is supplied. Pinned by `webapp/tests/test_events.py`
> `test_a_rankless_save_is_allowed`.
>
> **Errors use the envelope below.** Codes in circulation: `missing_request_id`,
> `missing_rank`, `unknown_event`, `server_derived_event`, `unknown_reason`,
> `reason_not_allowed`, `dwell_not_allowed`. Every one fails the **whole batch** — a
> partially-accepted impression batch leaves the render's rank sequence with holes that are
> indistinguishable from items the user never scrolled to.
>
> **One limit that is an interaction, not a bug.** The 24-hour impression dedup is keyed
> `(profile, job_id)`, not `(profile, job_id, request_id)`, so a second render of the same
> list inside that window writes no impression rows — and the skip derivation, which reads
> impressions, finds nothing to skip in it. **Skips are a first-render-per-day signal.**
> Narrowing the dedup key would change an existing documented behaviour (*"a list re-render
> is not new information"*) for a different task's benefit, so it is recorded here and in
> [`../../ingest/engagement-events.md`](../../ingest/engagement-events.md) rather than
> changed in passing. It is the owner's call whether it should be.

---

## `GET /v1/searches` · `POST /v1/searches`

```jsonc
{
  "suggested": [
    { "id": 12, "text": "AI operations coordinator", "location": "New York, NY",
      "source": "track", "watcher_count": 7 }
  ],
  "mine": [
    { "id": 44, "text": "prompt specialist nonprofit", "location": "New York, NY",
      "last_run_at": "2026-07-28T04:00:00Z", "result_count_last_run": 12,
      "watcher_count": 3, "watching": true }
  ]
}
```

`POST` returns `202` with a queue position. **Searches are asynchronous** — task 25.
Never block a Builder on a scrape; results appear on the next list.

`watcher_count` is exposed; watcher identities never are.

---

## `POST /v1/onboarding`

```jsonc
{
  "prior_domain": "food service",
  "prior_years": 9,
  "situation": "employed_seeking",
  "location_pref": "nyc",
  "remote_pref": "hybrid_ok",
  "comp_floor": 55000,
  "schedule_constraints": ["no_overnight"],
  "seed_judgements": [ { "job_id": "gh_acme_4821", "verdict": "interested" } ]
}
```

No file upload — task 26. Seed judgements write real `job_events` with correct
`visibility`.

---

## Versioning

`Accept: application/vnd.jobs.v1+json`. Additive changes only within v1; a field is
never repurposed. If `bucket` ever becomes a number, that is v2.

## Errors

```jsonc
{ "error": { "code": "missing_rank", "message": "…", "request_id": "req_…" } }
```

`400` for contract violations — including a rank-less impression batch. Fail loudly;
silence is this system's default failure mode and the API should not add to it.

---

## Mocking

Freeze one realistic response per endpoint as JSON fixtures in `frontend/`. Build
against them. When the backend lands, the fixtures become contract tests both sides
run — which is the same discipline as task 09's cassettes, applied at the API boundary
instead of the HTTP client.

Include a fixture for each edge case, because these are the states most likely to be
skipped: a track with zero jobs, a job with null comp, a job with `is_estimated: true`,
`cohort_signal: null`, an empty `mine` search list, and a first-run user with no
onboarding.

# API CONTRACT v1 — frozen for frontend development

**Written** 2026-07-28. **Status:** target contract, not current implementation.

`GET /v1/jobs`, `GET /v1/jobs/{id}` and `POST /v1/events` already exist from
`docs/tasks/job_ingest/04-read-endpoints.md`. **Diff this against what they return
today before implementing** — this is where they need to land, not where they are.

The point of freezing it now is that `frontend/` and tasks 26–31 can proceed in
parallel. Build the client against a mock of this; fill in the backend behind it.

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
    { "event": "apply",      "job_id": "gh_acme_4821", "rank": 1 }
  ]
}
```

**Client rules:**

- Emit `impression` on **visibility**, not on payload receipt. A row below the fold was
  not examined, and recording it poisons the skip derivation.
- Never send `skip` — the server derives it from an `open` at rank *k*.
- Never send `match_score`, `fit_score`, `visibility` or `model_version` — all read or
  set server-side.
- Batch impressions; send actions immediately.

**Server rules:** reject a batch missing `request_id` or any `rank`. Set `visibility`
by event type — `save` is `cohort_anon`, everything else including `apply` is
`private`.

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

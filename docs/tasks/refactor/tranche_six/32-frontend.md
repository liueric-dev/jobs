# 32 — Frontend

**Status:** todo. **Depends on:** 26, 27, 28, 30, 31. **Blocks:** nothing.

Build `frontend/`. It is currently a single `.gitkeep`.

## The backend is further along than the empty directory suggests

Already landed: Google SSO, session cookies, `require_user`, `GET /v1/jobs`,
`GET /v1/jobs/{id}`, `POST /v1/events`. `docs/tasks/job_ingest/` records all five
tasks done, and `backend/webapp/README.md` carries the one manual step no automated
check covers — the live Google login round trip.

~~So this is a client against a working API, not a full-stack build.~~

> **THIS IS THE STALEST SENTENCE IN THE TRANCHE, corrected 2026-07-31 (task 34).**
> The API is working; it is not the API this task's own surface table needs. Today
> `GET /v1/jobs` returns a **flat list with no `rank`, no `bucket`, no `tracks[]`
> grouping and no `request_id`** — and it returns raw `match_score`/`fit_score`, which
> `API-CONTRACT-v1.md` explicitly forbids. Every surface in the table below needs
> backend work that does not exist: Today-grouped-by-track needs task 30, the cohort
> save signal needs 27 **and** 28, Search needs 25's `search_queries` table, and
> Onboarding needs 26's `builder_profiles`. **Read the dependency line, not this
> sentence.** The auth, session and read plumbing genuinely is done and genuinely is
> reusable; the response shape is the work.

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

## Definition of done

- Signs in, lists, opens, saves, dismisses with reason, applies, searches.
- Every render issues a `request_id`; every event echoes it with the correct `rank`.
- Impressions fire on visibility, not on payload receipt.
- Works on a phone, tested on a real one.
- No 0–100 score displayed (task 30).
- Empty states are seeded, never blank.
- Onboarding completes without any manual DB work.
- The live Google login round trip is verified by hand, per `backend/webapp/README.md`.

# 17 — Retarget `ats.py`

**Status:** DONE, `597662b`. **Depends on:** 16. **Blocks:** nothing.
**Estimated yield:** 50–150 relevant postings/day.

The code is fine. The company list is wrong. This task changes the list and adds the
three ATS platforms the current script does not cover.

## What exists

`backend/ingest/ats.py` already pulls entire company job boards — `relevance.json:_why`
notes that this is why *"~87% of the table is roles this persona will never apply
to"*. That property, previously a cost problem, is now the feature: pulling a
hospital system's entire board is exactly how you find the AI-operations coordinator
buried in it.

## Work

### Source the company list from `company_ats`

Replace whatever hardcoded or config-file list `ats.py` uses today with a query
against task 16's table, filtered to `status = 'valid'` and the platforms this script
handles. Adding an employer becomes a row insert, not a deploy.

### Add the missing platforms

Current coverage is Greenhouse and Lever. Add:

| ATS | endpoint | note |
|---|---|---|
| **Ashby** | public GraphQL, `includeCompensation=true` | cleanest salary support of any public feed |
| **Workable** | `apply.workable.com/api/v3/accounts/{slug}/jobs` | |
| **Recruitee** | `{slug}.recruitee.com/api/offers/` | |
| **SmartRecruiters** | `api.smartrecruiters.com/v1/companies/{slug}/postings` | |

Existing endpoints for reference:

- Greenhouse: `boards-api.greenhouse.io/v1/boards/{token}/jobs?content=true` —
  `content=true` is what returns descriptions; without it you get titles only
- Lever: `api.lever.co/v0/postings/{slug}?mode=json` — use `descriptionPlain` rather
  than the HTML variant; pagination truncates at 250, so a company with more roles
  needs slicing by team or location

### Delta sync

Both Greenhouse and Lever expose update timestamps. Poll with `updated_at` filtering
rather than full re-pulls — it cuts request volume substantially on a mature token
list and keeps the nightly window inside task 04's budget.

### Closure detection is free here

The list endpoint returns the complete current set. A job present yesterday and
absent today is closed. No re-crawl, no `validThrough` parsing, no inference.

This is worth stating in the generated doc because it is *not* true of the sources in
tasks 19–21, and the difference should be visible when someone is deciding which
source to trust for a staleness signal.

### Keep the tech tokens

The author's profile still uses them. Filter by profile at the gate (task 10), not by
removing rows at ingest. Same principle as the geographic filter.

## Definition of done

- Company list read from `company_ats`; no hardcoded tokens remain.
- Four new platforms ingesting, each with a cassette committed (task 09;
  `python3 evals/record_cassettes.py --list` shows the three that already exist).
- Delta sync via `updated_at` where the platform supports it.
- `upsert_checked` throughout; error counts logged.
- Closure set from absence, with the logic shared rather than copy-pasted per
  platform.
- Request count per nightly run recorded, so task 04's budget can be checked against
  reality.
- `docs/ingest/ats.md` regenerated.

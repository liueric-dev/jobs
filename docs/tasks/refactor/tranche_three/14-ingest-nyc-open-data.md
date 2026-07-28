# 14 — NYC Open Data ingest

**Status:** DONE, `7221620`. **Depends on:** 09, 10. **Blocks:** nothing.
**Estimated yield:** 20–60 relevant postings/day.

The single best free NYC source: full descriptions, salary, and an explicit closure
date, from a government API with no rate ceiling worth worrying about.

## Why this one first

Everything else in Phase 3 requires either token discovery or a parser that copes
with arbitrary employer HTML. This is a documented JSON API with a stable schema,
and it lands an afternoon's work.

It also happens to be dense in exactly the roles the cohort targets — City agency
analyst, coordinator and specialist positions, increasingly with AI and automation
language in the `preferred_skills` field.

## The source

Dataset `kpav-sd4t`, "Jobs NYC Postings," published by DCAS. Socrata SODA endpoint:

```
https://data.cityofnewyork.us/resource/kpav-sd4t.json?$limit=1000&$offset=0
```

Register a free Socrata **app token** and send it as `X-App-Token`. Anonymous
requests are throttled from a shared pool; the token moves you to your own bucket and
costs nothing.

A NY State mirror exists at `https://data.ny.gov/resource/vntw-tq6b.json` with
slightly fewer fields. Ingest the City one; note the mirror for a future state-wide
expansion.

## Fields worth mapping

The record is unusually rich. Map at minimum:

| SODA field | `jobs` column | note |
|---|---|---|
| `job_id` | `source_id` | stable |
| `business_title` | `title` | prefer over `civil_service_title`, which is bureaucratic |
| `agency` | `company_name` | |
| `job_description` + `minimum_qual_requirements` + `preferred_skills` | `description_text` | **concatenate all three** — the AI/automation vocabulary usually appears in `preferred_skills`, not the description |
| `salary_range_from` / `salary_range_to` / `salary_frequency` | comp fields | stated, not predicted |
| `posting_date` | `posted_at` | |
| `post_until` | closure | **explicit close date — see below** |
| `work_location` | `location_raw` | |
| `career_level` | — | a useful independent check on extracted `seniority_level` |
| `posting_type` | — | **filter: keep `External` only** |

`posting_type` distinguishes Internal from External. Internal postings are open only
to existing City employees and are useless to Builders — filter them out at ingest,
and record the count you dropped so a schema change that breaks the filter is
visible.

## Closure detection

`post_until` is an explicit date. This is the only source in the plan that hands you
closure for free with no re-crawl at all — set `closed_at` from it directly and skip
the disappearance-inference logic entirely.

Watch for nulls: not every posting carries one. Fall back to disappearance from the
feed for those.

## Traps

- **Pagination is `$limit`/`$offset`**, default page 1,000. Loop until a short page.
  The same silent-truncation risk as everywhere else applies — a short page that is
  not the last page reads as the end.
- **`career_level` is not `seniority_level`.** Do not map it into `job_facts`
  directly; let `extract.py` do its job and use this as a validation signal in task 07
  instead. A free independent label on a field task 06 found unstable is worth more as
  a check than as a shortcut.
- **Descriptions carry heavy civil-service boilerplate** — residency requirements,
  examination language. This is exactly the "messy source" the self-consistency
  finding warns about. Expect extraction quality here to be worse than on Greenhouse,
  and measure it per-platform in task 07.

## Work

- `backend/ingest/nyc-open-data.py`, following the existing ingest script shape.
- Use `upsert_checked` from task 03. No bare three-tuple unpacks.
- Add to `run-daily.py`'s `STEPS`.
- Cassette per task 09, including a fixture with a null `post_until` and one with an
  Internal `posting_type`.
- Generated doc at `docs/ingest/nyc-open-data.md` — the frontmatter convention, so it
  regenerates.

## Definition of done

- Nightly run ingests External postings only, with the Internal drop count logged.
- `closed_at` is set from `post_until` where present.
- All three description fields are concatenated.
- Cassette committed, including the two edge fixtures.
- 30 rows hand-checked: are these plausibly Pursuit-relevant? Record the fraction.

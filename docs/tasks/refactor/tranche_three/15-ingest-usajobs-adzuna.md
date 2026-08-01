---
kind: task
written: 2026-07-28
generator: none
---

# 15 — USAJobs and Adzuna ingest

**Status:** todo. **Depends on:** 09, 10. **Blocks:** nothing.
**Estimated yield:** 5–15/day federal, 30–80/day Adzuna.

Two free documented APIs, shipped together because neither is a day's work alone.

## USAJobs

Federal postings, free, well documented. Federal roles are a genuine path for this
population — degree requirements are often explicit rather than assumed, hiring is
rules-based rather than network-based, and NYC has substantial federal presence.

### Mechanics

Register at `developer.usajobs.gov` for an authorization key. Authentication is via
headers, which is unusual and easy to get wrong:

```
User-Agent: <your registered email>
Authorization-Key: <your key>
```

The `User-Agent` **is** the credential half. A default `python-requests` UA gets
rejected with an unhelpful error.

Filter to the NYC locality. Occupational series codes give a structured role taxonomy
for free — worth storing raw for later comparison against task 11's `role_track`,
though not for mapping into it directly.

### Closure

Announcements carry explicit open and close dates. But **closed announcements leave
the index entirely**, so a job that disappears is either closed or was never seen.
Snapshot on first sight and set `closed_at` from the announcement's own close date
rather than inferring from disappearance.

## Adzuna

Broad multi-industry US coverage with descriptions and salary. The widest net in the
plan for non-tech employers, and the only aggregator here with real institutional
credibility — the UK Office for National Statistics uses it for labour-market
statistics.

### Mechanics

Register for `app_id` + `app_key`. Country-scoped path:

```
https://api.adzuna.com/v1/api/jobs/us/search/1?app_id=…&app_key=…&where=new+york&what=…
```

Free tier is roughly 1,000 calls/month — reported figures vary between a monthly cap
and a ~250/day cap, so **measure your actual limit on day one** and record it in the
quota ledger rather than trusting either number.

At ~30 calls/night this fits comfortably. Budget deliberately: use `what` queries
drawn from task 05's AI vocabulary rather than pulling everything and filtering
locally, since the call budget is the constraint and the filtering is free.

### Quality caveat

Adzuna **predicts** salary where it is not stated. Do not write a predicted salary
into `comp_min`/`comp_max` as though it were stated — that pollutes a field
`score_job()` reads. Store it separately or drop it, and record which you chose.

Descriptions are sometimes truncated relative to the employer's original. Where
Adzuna gives a redirect URL to an ATS you already ingest, prefer the ATS record as
canonical and treat the Adzuna row as a discovery signal.

### Analytics endpoints, worth knowing about

`histogram`, `top_companies` and `geodata` are free and return aggregate labour-market
data. Not needed for ingest, but `top_companies` for AI-adjacent NYC queries is a
plausible seed source for task 16's employer list. Note it there.

## Shared work

- `backend/ingest/usajobs.py` and `backend/ingest/adzuna.py`.
- `upsert_checked` per task 03.
- Both added to `run-daily.py` `STEPS`.
- Cassettes per task 09 — for USAJobs include a fixture with the header auth failing,
  since that failure mode is silent-ish and confusing.
- Quota ledger entries for both, since Adzuna is the first hard monthly cap in the
  pipeline and task 23's router will want the same ledger.
- Generated docs at `docs/ingest/usajobs.md` and `docs/ingest/adzuna.md`.

## Definition of done

- Both ingest nightly with error counts logged.
- Adzuna's real rate limit is measured and recorded, not assumed.
- Predicted salaries are not written into stated-salary fields.
- USAJobs `closed_at` comes from the announcement, not from disappearance.
- Cassettes committed.
- 30 rows from each hand-checked for Pursuit relevance; fractions recorded.

# 18 — Workday CXS ingest, and upstream gating

**Status:** todo. **Depends on:** 09, 16, 10. **Blocks:** nothing.
**Estimated yield:** 80–200 relevant postings/day.

The highest-value source in the plan and the only one with real engineering risk.
Four documented ways to lose data **silently**, and one change to the ingest contract.

## Why this carries the plan

Mount Sinai, NewYork-Presbyterian, Northwell, NYC Health + Hospitals, the insurers,
the universities — the large non-tech NYC employers almost all run Workday. Task 16
will confirm the exact fraction, but if public-feed ATS coverage of the non-tech seed
list comes in low, this task *is* the "all industries" promise.

And it is free plain HTTP. No auth, no scraping service, no credits.

## The endpoint

```python
POST https://{tenant}.wd{N}.myworkdayjobs.com/wday/cxs/{tenant}/{site}/jobs
Content-Type: application/json

{"appliedFacets": {}, "limit": 20, "offset": 0, "searchText": ""}
```

Response carries `total` and `jobPostings[]`. Each posting has `title`,
`locationsText`, `externalPath`, `startDate` (native ISO — no "posted 3 days ago"
parsing), and `jobRequisitionLocation` with structured fields.

Descriptions need a second call:

```
GET /wday/cxs/{tenant}/{site}/job/{externalPath}
```

Public job URL for `job_url`: `{host}/en-US/{site}{externalPath}`.

## The four silent failures

Every one of these returns success and loses data. Each needs a cassette fixture from
task 09 that reproduces it, and a test that fails loudly.

**1. `limit` cannot exceed 20.** Ask for 100 and Workday returns an empty
`jobPostings` array with **no error** — byte-identical to "no more results." Hardcode
20 and assert it.

**2. A throttled page reads as the end of the list.** Loop without pausing and a page
eventually fails; if the loop treats a failed page as termination, you silently
collect a fraction. One published account lost 1,960 of NVIDIA's 2,000 jobs this way.
Pause between pages, retry a failed page, and **compare the collected count against
the `total` the API returned** — a mismatch is an error, not a shrug.

**3. Data-centre prefix varies.** `wd1`, `wd3`, `wd5`. Read it from `company_ats`
(task 16 stores it separately for this reason). Never assume, never default.

**4. The 10,000-result cap.** A single query cannot enumerate beyond it. For any
tenant whose `total` approaches that, slice by `appliedFacets` — location or category
— and merge. Relevant for the largest hospital systems.

## The ingest-contract change

This is the architectural part.

If a hospital has 2,000 open roles and you fetch a detail page for each, that is
2,000 requests per tenant per night. Across 50 tenants the detail fetches dominate the
entire pipeline and blow the nightly window.

**So the relevance gate moves upstream, into ingest, for this source.**

Today `relevance.py` runs against rows already in `jobs`. Here, filter on the *list*
response — which carries title and location — and fetch detail only for postings that
survive. Two thousand requests becomes perhaps a hundred and fifty.

Implementation notes:

- Reuse `relevance.py`, do not reimplement. Add a function that evaluates a
  title/location pair in Python against the same config `tier_sql` compiles to SQL.
  Two copies of the matching logic is the trap; one implementation with two callers is
  the fix.
- Task 10's gate is **description-first**, and at list time there is no description.
  So the upstream filter must be deliberately *loose* — title match, location match,
  or neither-but-unknown — and let the full gate run after detail fetch. Filtering
  tightly here would discard exactly the postings this refactor exists to find, since
  their titles are the uninformative part.
- Log the ratio: postings seen, postings detail-fetched, postings surviving the full
  gate. If detail-fetched/seen creeps toward 1.0, the upstream filter has stopped
  working and the window is about to blow.

## Politeness and blocking

Vendors selling Workday access claim Akamai bot management blocks naive scraping
within minutes; independent accounts report plain `requests` working fine. Both are
probably true at different rates.

**Your residential home IP is an advantage here** — it is the traffic profile Akamai
is least suspicious of. Start plain: 1–2s between requests, ~50 tenants, sequential.
Measure the block rate over a week before reaching for anything else.

If specific tenants block, escalate *those tenants only* to Scrapfly's free 1,000
credits. Do not route everything through a scraping service because one tenant
misbehaved.

Some tenants require login for certain listings. Those are inaccessible; skip and
count them rather than retrying.

## Closure detection

The list endpoint returns the current set per tenant, so absence means closed — same
free mechanism as task 17. But note the interaction with the upstream filter: a
posting you never detail-fetched is still a posting you *saw*, so track seen-set
membership from the list response, not from what you stored.

## Definition of done

- Ingests from `company_ats` Workday rows, using stored tenant/dc/site.
- All four silent failures have a reproducing fixture and a failing-loudly test.
  The fixtures already exist, built by task 09: `backend/evals/workday_fixtures.py`,
  with `backend/tests/test_workday_fixtures.py` proving each one still reproduces
  the failure it names. Drive the real ingest loop through them and delete that
  file's stand-in `_collect_naively`/`_collect_reconciled`.
- Cassette committed: a recording of the real happy path against a live tenant
  from `company_ats`, once task 16 has produced one. The four fixtures above are
  constructed, not recorded, and say so.
- Collected count is reconciled against `total`; mismatch raises.
- Upstream gating implemented via shared `relevance.py` logic, not a second copy.
- The seen/fetched/surviving ratio is logged nightly.
- Block rate measured over one week and recorded before any escalation.
- Wall-clock per tenant and in total recorded against task 04's budget.
- `docs/ingest/workday.md` generated, with the four traps documented in the failure
  table so the next audit finds them already known.

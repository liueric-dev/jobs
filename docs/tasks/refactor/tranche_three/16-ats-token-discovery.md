# 16 — ATS token discovery

**Status:** todo. **Depends on:** nothing. **Blocks:** 17, 18, 20.
**Estimated yield:** none directly — unblocks ~150–350/day.

Find which NYC employers run which ATS. The endpoints are trivial; **this** is the
actual work, and there is no public directory of board tokens.

## The shape of the problem

Every public ATS feed needs a token or slug you cannot enumerate. You can read
Greenhouse's API for `stripe` only if you already know the token is `stripe`.

The good news is that probing is cheap and self-validating: a company with no
Greenhouse board returns a 404 for one HTTP request. So a **big, dumb list works
fine** — precision comes from validation, not from curation. That means the seed list
does not need expert judgement to start, which is the opposite of what an earlier
draft of this plan assumed.

## Seed list

Assemble a few hundred NYC employers, weighted toward non-tech. Public sources, no
curation required:

- **Crain's New York** largest-employers lists
- **Hospital systems** — Mount Sinai, NewYork-Presbyterian, Northwell, NYC Health +
  Hospitals, Montefiore, Maimonides, and their subsidiaries
- **Universities** — CUNY campuses, NYU, Columbia, The New School, Fordham
- **City and state agencies** — from the `agency` column already populated by task 14
- **Insurers, banks, media, retail HQs** with NYC presence
- **Large nonprofits** — Nonprofit New York's member directory, NYCON
- **Adzuna `top_companies`** (task 15) for AI-adjacent NYC queries

Store as a simple seeded table, not a config file — it will grow continuously.

## Probe

For each employer: fetch the careers page, follow one redirect, regex for signatures.

| ATS | URL signature |
|---|---|
| Greenhouse | `boards\.greenhouse\.io/([\w-]+)` · `job-boards\.greenhouse\.io/([\w-]+)` |
| Lever | `jobs\.lever\.co/([\w-]+)` |
| Ashby | `jobs\.ashbyhq\.com/([\w-]+)` |
| Workable | `apply\.workable\.com/([\w-]+)` |
| Recruitee | `([\w-]+)\.recruitee\.com` |
| SmartRecruiters | `careers\.smartrecruiters\.com/([\w-]+)` |
| Workday | `([\w-]+)\.wd(\d+)\.myworkdayjobs\.com/([\w-]+)` |
| iCIMS | `careers-([\w-]+)\.icims\.com` · `([\w-]+)\.icims\.com` |

Then **validate**: call the ATS's own endpoint and confirm a 200 with a non-empty job
list. A signature found in a stale footer link is common; an unvalidated token
silently contributes zero rows forever.

Workday needs all three captures — tenant, data-centre number, and site path. Getting
`wd1` vs `wd5` wrong is a 404, and task 18 depends on this being right.

## Schema

```sql
company_ats (
    id, employer_name, careers_url,
    ats TEXT,                    -- greenhouse | lever | ashby | workday | icims | …
    token TEXT,                  -- board token / slug / tenant
    workday_site TEXT,           -- null except workday
    workday_dc TEXT,             -- 'wd1' | 'wd5' | …
    open_jobs_at_validation INTEGER,
    first_validated_at, last_validated_at,
    status TEXT                  -- valid | dead | never_found
)
```

## Re-probe monthly

Companies migrate ATS constantly, **and the old feed keeps serving stale jobs after
they do.** That is the failure mode to design against: not a 404, but a feed that
returns plausible-looking postings that were filled six months ago. Re-validate
monthly and flag any token whose `open_jobs_at_validation` has not changed in 60 days
for manual review.

## Shortcut for the first pass

Apify has discovery actors — `igolaizola/greenhouse-companies` and
`wickfeed/ats-company-discovery` — that return ranked board-URL directories
filterable by keyword and minimum open-job count. One run against health, finance,
education and government keywords will seed the table faster than crawling, and fits
inside the $5/month free credits.

Use it to bootstrap, then own the maintenance yourself. Do not build a dependency on
it.

## Expect a skew, and record it

Public-feed ATS platforms skew tech and startup. Most large non-tech NYC employers run
**Workday, iCIMS, Taleo or Oracle** — which is why tasks 18 and 20 exist and why they
are the harder half of Phase 3.

Report the breakdown when the probe completes. If Greenhouse/Lever/Ashby coverage of
your non-tech seed list comes in under ~20%, that is the signal that task 18 carries
most of the plan's weight and should be resourced accordingly.

## Definition of done

- `company_ats` populated from a seed list of ≥300 NYC employers.
- Every row validated against the live endpoint, not just regex-matched.
- Workday rows carry tenant, data centre and site separately.
- Breakdown by ATS reported, with the non-tech coverage fraction stated explicitly.
- Cassette committed (task 09) covering one validation probe per ATS, including a
  token that does not resolve — otherwise the validator is only ever exercised
  against the live endpoints it is meant to stop trusting.
- A monthly re-probe job exists and is in `run-daily.py` or its own timer.
- The seed list is stored as data, extensible without a code change.

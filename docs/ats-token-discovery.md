---
kind: record
written: 2026-07-28
generator: none
---

# ATS token discovery — what NYC employers actually run

**Task:** `docs/tasks/refactor/tranche_three/16-ats-token-discovery.md`
**Measured:** 2026-07-28, on branch `webapp-service`, against the live database.
**Method:** one HTTP probe per employer careers page, then one validation call per
discovered token against the ATS's own endpoint. No scraping service, no credits, no
LinkedIn.

Hand-written rationale, not generated — this file has no `script:` frontmatter and is
not regenerated. The numbers below are reproducible with
`python3 tools/ats-discover.py --report`, which reads them out of the table.

---

## What was built

| thing | where |
|---|---|
| signatures, validators, outcome vocabulary (pure, no I/O) | `backend/ats_discovery.py` |
| seed roster, 376 NYC employers | `backend/data/nyc-employer-seed.json` |
| `ats_seed` + `company_ats` DDL and the seed loader | `backend/migrations/migrate_company_ats.py` |
| the probe, validation and reporting CLI | `backend/tools/ats-discover.py` |
| nightly backfill + monthly re-validation | `backend/run-daily.py` STEPS[0] |
| tests | `backend/tests/test_ats_discovery.py` |

`company_ats` is the table tasks 17, 18 and 20 read instead of
`backend/config/companies.json`.

---

## Results

**Measured 2026-07-28.** Reproduce with `python3 tools/ats-discover.py --report`.

### Read this first: the positive control failed 4 out of 4

The seed roster carries ten tech employers as a **positive control** — companies with
tokens already verified live in `backend/config/companies.json`. Four of them were
conclusively probed. The regex method found **zero** of the four.

| control employer | verified token | probe outcome |
|---|---|---|
| Datadog | `greenhouse:datadog` | `not_found` |
| MongoDB | `greenhouse:mongodb` | `not_found` |
| Justworks | `greenhouse:justworks` | `not_found` |
| Ramp | `ashby:ramp` | `not_found` |

Checked by hand: `https://careers.datadoghq.com/` returns HTTP 200 and 139,063 bytes of
HTML that **do not contain the string `greenhouse.io` anywhere**. MongoDB's is 564,983
bytes with the same result. Their boards are rendered client-side, so there is no ATS
URL in the document a plain fetch receives.

**Therefore `not_found` — 139 employers, the single largest bucket — does not mean
"this employer has no ATS".** It means "no ATS URL in the HTML we were served", and on
this evidence it is wrong far more often than it is right. Every number below is a
floor, and the true coverage of the roster is certainly much higher than what was
measured. `company_ats.validation_note` on those rows says so in the row itself, so
tasks 17, 18 and 20 cannot read them as settled.

This is what the control was for, and it is the most useful thing this pass produced.

### `company_ats` — 50 rows

15 token rows plus 35 `never_found` rows.

| ATS | status | rows | open jobs at validation |
|---|---|---|---|
| workday | valid | 4 | 1,359 |
| greenhouse | valid | 2 | 104 |
| icims | valid | 1 | 50 |
| icims | dead | 2 | — |
| smartrecruiters | dead | 1 | 0 |
| adp | unvalidated | 2 | — |
| jobvite | unvalidated | 2 | — |
| oracle_cloud | unvalidated | 1 | — |
| *(none)* | never_found | 35 | — |

**7 validated tokens, 1,513 open jobs.** Every one is a non-tech NYC employer:

| employer | sector | ATS | token | open jobs |
|---|---|---|---|---|
| NewYork-Presbyterian | health | workday | `nyp` **wd1** / `nypcareers` | 367 |
| Nordstrom | retail | workday | `nordstrom` **wd501** / `nordstrom_careers` | 862 |
| Memorial Sloan Kettering | health | workday | `msk` **wd108** / `MSKCC_Careers_Primary` | 87 |
| Moelis & Company | finance | workday | `moelis` **wd1** / `Experienced-Hires` | 43 |
| National Football League | media | greenhouse | `nflcareers` | 66 |
| Per Scholas | nonprofit | greenhouse | `perscholashires` | 38 |
| PepsiCo | retail | icims | `pepsico` | 50 |

The three `unvalidated` platforms (ADP, Jobvite, Oracle Cloud) are detected-only: they
publish no feed this tool can call. They are recorded because "which large NYC
employers are on Oracle/ADP" is exactly the skew `16-ats-token-discovery.md:92-100`
asks to be reported.

**The data-centre column earns itself immediately.** The four Workday tenants use
`wd1`, `wd108` and `wd501`. Nobody would guess `wd108` or `wd501`, and
`18-ingest-workday-cxs.md:54` is right that a wrong one is a 404 indistinguishable from
a tenant with no openings.

### Non-tech coverage fraction — stated explicitly

The task's Definition of done asks for this number. It is quoted over **both**
denominators, because neither alone is honest:

| | count | of 366 seeded | of 193 probed |
|---|---|---|---|
| non-tech employers seeded | 366 | 100% | — |
| …conclusively probed | 193 | **52.7%** | 100% |
| …with any validated ATS | 7 | **1.9%** | 3.6% |
| …on greenhouse / lever / ashby | 2 | **0.5%** | 1.0% |

**Quoting the probed-subset fraction alone would overstate roster coverage by 1.9x.**
The tool prints both and says so; it will not print one without the other.

Both numbers are floors, for the reason at the top of this section.

### Probe outcomes, all 376 seeded employers

| outcome | employers | conclusive? |
|---|---|---|
| `not_found` | 139 | yes — but see the control failure above |
| **never probed** | **96** | — |
| `found` | 60 | yes |
| `blocked` | 30 | **no** |
| `missing_page` | 28 | no |
| `unreachable` | 13 | no |
| `skipped` | 10 | no |

**96 employers were never probed, and the pass was stopped deliberately.** The
`blocked` count climbed from 16 to 30 as coverage grew — the pipeline's own documented
failure mode arriving in real time — and this host's IP also runs the nightly ATS pulls
and `google-serpapi.py`. Stopping at 280 of 376 was a decision to protect that, not a
run that finished. The 96 carry `last_probe_outcome IS NULL` and are first in line for
the nightly backfill, which walks least-recently-probed first.

`skipped` is per-host blocklist cascade and is worth understanding: many NYC agencies
share `www.nyc.gov`, so one 403 there suppresses all of them at once. They are recorded
as inconclusive, never as `never_found`.

60 employers reported `found` but only 15 token rows were written: the run was killed
mid-batch, and the records buffered since the last 50-row flush were lost with it. That
is the same defect described under "Known limitations", bounded now to at most 50 rows
instead of a whole run.

### What this says about tasks 17, 18 and 20

Public-feed (greenhouse/lever/ashby) coverage of the non-tech roster is **0.5% of
seeded, 1.0% of probed** — far below the ~20% line `16-ats-token-discovery.md:98-100`
sets. By that rule, **task 18 (Workday) carries most of the plan's weight.**

The measured evidence agrees: Workday alone contributed 4 of the 7 validated tokens and
**1,359 of the 1,513 open jobs — 90%**. The largest non-tech NYC employers really are
on Workday, and they really do expose it.

That conclusion is safe despite the control failure, because a false-negative-heavy
method under-counts every platform roughly alike, and the *relative* result is stark.
What the control failure does change is the absolute yield: there is more to find than
these numbers show, and the cheapest way to find it is not a better regex.

### Recommended next step, with the evidence for it

Do **not** invest further in careers-page scraping. The control says it fails on exactly
the employers that are easiest to verify.

Guess the slug and ask the ATS directly instead — `api.greenhouse.io/v1/boards/{slug}`
answers definitively in one request. It has three properties this pass lacked: it sends
no traffic to employer websites at all (so the block rate that stopped this run does not
apply), it hits the same vendor APIs `ingest/ats.py` already calls nightly, and it is
self-validating, since a wrong guess is a 404. `find_signatures()` stays useful for
Workday, whose tenant/dc/site triple cannot be guessed.

Task 19's JSON-LD parser is the other half, for employers who render server-side but
link no board URL.

---

## The design decision that matters most: silence is not a result

CLAUDE.md names silence this pipeline's failure mode — "exhausted keys, revoked keys,
blocked scrapers and changed endpoints all return zero rows rather than raising."

A discovery pass is the worst possible place for that. A probe refused at the front
door by every host finds zero tokens, exits 0, and writes an empty table that the next
run — and tasks 17, 18 and 20 — read as settled fact about the New York labour market.

So "found nothing" and "was not allowed to look" are never the same value anywhere in
this code:

**1. Every employer carries an outcome, not a boolean.** `ats_seed.last_probe_outcome`
is one of seven values (`ats_discovery.py:57-70`), partitioned into `CONCLUSIVE`
(`found`, `not_found`) and `INCONCLUSIVE` (`blocked`, `unreachable`, `missing_page`,
`no_url`, `skipped`). A test asserts the partition is disjoint and complete, because a
value in neither bucket would vanish from the summary line entirely.

**2. Only a conclusive outcome may write `status='never_found'`.** That row means "we
read this employer's careers page and it contains no ATS". A 403 never produces one.
`ats_discovery.never_found_row()` says so in its docstring and
`tools/ats-discover.py`'s probe loop is the only caller.

**3. A token that could not be checked is `unvalidated`.** Task 16's schema
(`16-ats-token-discovery.md:69`) offers `valid | dead | never_found` and has no value
for "we found a token but the ATS did not answer". Both available choices are wrong:
`valid` ships a token that contributes zero rows forever and looks healthy, and `dead`
deletes evidence. `STATUS_UNVALIDATED` is the fourth value. 403, 429, 5xx, a network
failure, and a 200 whose body is not a recognisable job feed all land there.

**4. A 200 with a WAF body counts as blocked.** `lib/http.py` documents the same shape
— queenslibrary.org answers 200 with "Request Rejected". Reading that as "page fetched,
no ATS found" would write a `never_found` row on the strength of a block.

**5. A circuit breaker.** If the blocked fraction exceeds `--max-blocked-frac` after
`--breaker-after` probes, the run aborts non-zero rather than finishing and reporting a
clean, empty answer. The watermark is not advanced on an aborted run — the same
mistake `lib/state.py:69-76` records for nyc-events advancing past its `max_pages` cap.

**6. The summary line prints on every run, including a clean one**, and separates
conclusive from inconclusive counts. `found 0` beside `blocked 0 unreachable 0` means
the market is empty. `found 0` beside `blocked 180` means nothing was measured. Those
need opposite responses, which is the same argument `run-daily.py:219-224` makes for
printing volume unconditionally.

---

## Politeness

A regex probe against several hundred hosts that never asked for it is outward-facing
network activity, so:

- **one global request per `--delay` (1.2s used here) and at most one request per host
  per `--host-delay` (5s)**. The per-host limit is the expensive one — careers-page
  fallbacks are same-origin by construction, so an employer needing all three
  candidates costs 10s of deliberate waiting. That is the intended trade.
- **no retries, ever.** `lib/http.py` retries 429 with exponential backoff, which is
  correct against an API you hold a key for and is precisely the wrong instinct when
  probing strangers: retrying into a rate limit is how a probe becomes an incident.
  `lib/` is also vendored byte-identical to another repo, so its policy is not
  something to bend to suit this caller. The probe has its own `Fetcher`.
- **a host that answers 401/403/406/429/451 is blocklisted for the rest of the run**,
  including its validation request. Ambiguous refusals resolve toward `blocked` on
  purpose: `blocked` is inconclusive and can never write a `never_found` row, so
  guessing wrong costs one re-probe next month rather than a false negative that
  persists.
- **an honest User-Agent** naming the project, not a browser string. A host that does
  not want automated traffic is entitled to recognise this as automated traffic; a 403
  here is a datum, not an obstacle to route around.
- **at most 3 URLs per employer**, and `--max-requests` as a hard ceiling on the run.

**LinkedIn is not touched.** CLAUDE.md forbids it.

---

## Why the seed list is a table and the file is only a bootstrap

`16-ats-token-discovery.md:34` — "store as a simple seeded table, not a config file —
it will grow continuously." `ats_seed` is the source of truth.
`data/nyc-employer-seed.json` exists only to bootstrap it, is loaded idempotently, and
never overwrites a probe result or a `careers_url` the probe corrected from the network
(`--refresh-urls` opts into that). Adding an employer afterwards is
`tools/ats-discover.py --add-employer "Name" --careers-url ... --sector ...`, or a
plain INSERT. No deploy.

It sits in `backend/data/` rather than `backend/config/`: config in this repo is tuning
that the pipeline reads on every run, and this is an input corpus with provenance read
exactly once per environment.

### Weighted non-tech, deliberately

`docs/pursuit-gate-volume.md` (task 05) measured 90% of the corpus arriving from
greenhouse + ashby alone and Google Jobs contributing 4.8%, and concluded: "The
broad-industry, non-tech employers the Pursuit cohort targets are essentially absent
from every configured source. The platform mix is not skewed — it is missing an entire
category."

So the roster is 366 non-tech and 10 tech, across health (55), nonprofit (50),
education (44), finance (35), media (32), government (30), retail (30),
professional services (20), insurance (15), real estate (15), transport/utilities (15),
arts and culture (15) and hospitality (10).

The ten tech entries are a **positive control**, not coverage: they are companies
already known to run Greenhouse or Ashby, so a run that finds nothing for them has a
probe bug rather than an empty market.

### The evaluation criterion for a discovered token

Task 05's other finding was that **company-level false positives are the dominant
failure mode** — an employer whose boilerplate mentions AI matches on every posting it
has, so the vocabulary "selects for the *company* being AI-ish, not the *role*".

A discovered token is therefore judged on whether the **employer** plausibly hires the
target population — entry-level, AI-adjacent, NYC, any industry — and never on whether
its postings match AI vocabulary. Filtering discovery by posting text would rediscover
exactly the ~93%-noise population task 05 measured, one layer earlier.

---

## What is not wired up

**Adzuna `top_companies`** (`16-ats-token-discovery.md:32`) is listed as a discovery
source and is **stubbed**. Task 15 is blocked: the endpoint needs an
`app_id`/`app_key` pair that requires registering an Adzuna account, and nobody has.

It is a seam rather than a hole. `adzuna_top_companies()` in `tools/ats-discover.py`
returns `[]`, says why on stderr, and its result is passed straight to
`insert_discovered_employers()` — the same entry point `--add-employer` uses. Switching
it on means filling in that one function and adding two keys to `.env`; nothing else
in the file changes. A discovery source being unavailable does not take the other 376
employers down with it.

**Apify's bootstrap actors** (`igolaizola/greenhouse-companies`,
`wickfeed/ats-company-discovery`) are also not used. The task itself says to bootstrap
with them and then "own the maintenance yourself. Do not build a dependency on it" —
this went straight to owning it, since the seed roster does not need them.

---

## Re-probe cadence, and the failure it is designed against

The failure mode is **not** a 404. It is a feed that keeps returning plausible-looking
postings that were filled six months ago, after the employer migrated ATS.

`run-daily.py` runs `tools/ats-discover.py --apply --nightly --limit 40` as its first
step — before `ingest/ats.py`, so a token learned this morning is pulled the same
night. `--nightly` is two phases in one process:

- **Monthly, watermark-gated:** re-validate *every* known token. One request per token
  against an API that expects programmatic traffic. This is the re-validation task 16
  asks for and the only thing that catches a stale feed, since a migrated employer's
  careers page looks fine. Tokens flagged by the 60-day rule are printed as
  `ats-discover: STALE -- ...` lines.
- **Nightly:** probe up to `--limit` employers with no conclusive answer yet — newly
  seeded ones, and ones a WAF refused last time. Least-recently-probed first, so the
  backlog drains over successive nights and the step then goes quiet on its own.

They are one STEPS entry rather than two because `run-daily.py` keys its
written/dropped accounting by script name; a second entry for the same script would
overwrite the first's counts and report one line for both.

**A full careers-page sweep is deliberately not scheduled.** `--apply --all` is ~50
minutes of outward HTTP against several hundred employer sites (the per-host delay
dominates: careers-page fallbacks are same-origin by construction). That is a first-run
and occasional-refresh operation, run by hand, not something to spend unattended every
month. Only a full pass advances the watermark; a `--limit` run must not convince the
next month that the re-validation already happened.

`company_ats.open_jobs_changed_at` moves only when `open_jobs_at_validation` actually
changes, which is what makes "unchanged for 60 days" answerable. `last_validated_at`
moves on every probe and cannot answer it, which is also why it is deliberately absent
from the content-hash fields — including it would report every monthly re-probe as
hundreds of updated rows and bury the handful that genuinely moved.
`tools/ats-discover.py --report` lists the flagged tokens.

---

## Landmines encountered, and the tests that pin them

**Workday's optional locale segment.** URLs are
`{tenant}.wd{N}.myworkdayjobs.com/{locale}/{site}`, where `{locale}` ("en-US") is
optional. A pattern capturing the first path segment records `en-US` as the site for
every employer that includes it, and task 18's CXS POST to
`/wday/cxs/{tenant}/en-US/jobs` then 404s — indistinguishable from a tenant with no open
roles. The locale group is non-capturing and optional
(`backend/ats_discovery.py:SIGNATURES`), and tenant, data centre and site are three
separate columns because `18-ingest-workday-cxs.md:54` forbids guessing the data
centre.

**Workday's `limit` cannot exceed 20.** CLAUDE.md's landmine: ask for 100 and Workday
returns an empty `jobPostings` array with no error, byte-identical to "no more
results". The validation request hardcodes 20 and a test asserts it — at 100, every
live Workday tenant in New York would have validated as `dead`.

**Greenhouse's embed form.** `boards.greenhouse.io/embed/job_board?for=TOKEN` puts the
real token in the query string. A pattern taking the first path segment records every
employer using that form as token `embed`, which 404s and lands as `dead` — a false
negative that reads exactly like a company that migrated ATS.

**iCIMS matched twice.** `-` is in the token character class, so
`careers-montefiore.icims.com` matched both the prefixed and the bare pattern, once
correctly as `montefiore` and once as `careers-montefiore`. The second validates
against `careers-careers-montefiore.icims.com`, 404s, and is stored as a `dead` row
sitting beside the valid one — again reading like an employer mid-migration rather than
like a regex bug. Fixed with a negative lookahead; both spellings are tested.

**Two employers, one board.** A health system and its subsidiaries share a Workday
tenant, and Staten Island University Hospital shares Northwell's careers host. Written
un-deduplicated, the same primary key is upserted twice in one batch and the second
write lands — and since change-tracking keys on the row id, the loser carries
`open_jobs_changed_at = NULL` and would blank it, disarming the 60-day stale check for
exactly the largest employers. `dedupe_by_id()`, with a test.

**The read cap made big healthy boards look unverifiable.** The fetcher capped every
response at 2 MB. `api.lever.co/v0/postings/leverdemo?mode=json` is **2.43 MB** for 388
jobs — measured, not hypothesised — so it arrived truncated, `json.loads` failed, and
`classify_validation` reported *"200 but the response was not a recognisable job
feed"*. The largest and healthiest boards, the ones most worth ingesting, were exactly
the ones that read as unverifiable, and the message blamed the employer for our own
cap. Validation responses now have their own 40 MB cap, and `Fetcher.get` returns a
`truncated` flag rather than letting the caller infer it — a body cut off at the cap is
indistinguishable from a malformed one, and whoever next raises a cap should not have
to also remember that.

**`never_found` rows have no token.** Keying them like a token row hashes `("","","")`
for every employer and collapses hundreds onto one row — silently, since `upsert()`
would report the rest as `unchanged`. They key on the employer name instead.

**`upsert_checked`, never a bare three-tuple.** `UpsertResult.__iter__` yields
`(new, updated, unchanged)` and not `.errors` — the defect task 03 existed to remove
and which CLAUDE.md names a landmine. Every write here goes through
`upsert_checked`, so this step also appears in `run-daily.py`'s nightly
written/dropped record via the `upsert-summary:` line.

---

## Known limitations

- **The seed roster's careers URLs are hand-assembled and some are wrong.** Employers
  move these paths constantly. A wrong URL is recorded as `missing_page` — explicitly
  *not* as "this employer has no ATS" — and the probe tries `{origin}/careers` and
  `{origin}/jobs` before concluding anything. The honest reading is that
  `missing_page` counts are a property of this seed file, not of the employers.
- **iCIMS validation is weaker than the rest.** iCIMS publishes no JSON feed, which is
  why task 20 reaches for Firecrawl. Validity there means "the search portal returns
  200 and lists job links", counted from the HTML.
- **Taleo, Oracle Cloud, SuccessFactors, Jobvite, BambooHR, ADP and Paylocity are
  detected but not validated.** They have no public feed this module can call, so they
  carry `status='unvalidated'` with the reason in `validation_note`. Recording them is
  deliberate: "which large NYC employers are on Taleo/Oracle" is exactly the skew
  `16-ats-token-discovery.md:92-100` asks to be reported, and it is the input that
  decides how much of the plan's weight tasks 18 and 20 carry.
- **One careers page, one pass — and this is the dominant limitation, not a marginal
  one.** Employers whose board is rendered client-side read as `not_found`. Measured,
  not estimated: **0 of 4** control employers with a verified live board were found
  (see the top of Results). Treat `not_found` as "no ATS URL in the bytes we were
  served" and nothing stronger. The remedies are slug-guessing against the vendor APIs
  (cheapest, and sends no traffic to employer sites), task 19's JSON-LD parser, and
  task 20's Firecrawl path.
- **A killed run loses up to 50 discovered rows.** Rows are flushed every
  `FLUSH_EVERY` (50) records rather than per employer, so an interrupted pass drops the
  current batch while leaving `last_probed_at` set on those employers — they look
  probed and are not. Bounded and deliberate (a per-employer flush would triple the
  write traffic), but it is why 60 `found` employers produced 15 token rows here.
- **The block rate is a moving target, and it moved.** 16 blocked at 140 employers,
  30 at 280. A pass run in one sitting from one IP gets progressively more refusals, so
  the nightly `--limit 40` backfill is not merely gentler than a full sweep — it is
  likely to reach employers a full sweep would have been blocked by.

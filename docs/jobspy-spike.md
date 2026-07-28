# JobSpy spike — does a self-hosted scraper work from the home IP?

**Task:** `docs/tasks/refactor/tranche_four/22-jobspy-spike.md`
**Run:** 2026-07-28, at commit `68f026f`, from the user's home connection.
**Egress IP:** `47.230.80.126` — Charter Communications (Spectrum), US residential.
Verified by `whois` before anything was queried, because the whole premise of the
spike is that the IP is residential.
**Versions:** `python-jobspy` 1.1.82 (latest on PyPI), Python 3.14, installed into a
throwaway venv in a scratchpad. Nothing was installed system-wide.
**Timebox:** the task allows two days plus a two-week observation. Actual elapsed
work was **under one hour**, because the answer arrived on the first query and
every subsequent probe only confirmed it.

---

## Decision

**Drop JobSpy. Do not build a router branch around it.**

This is the third row of the task's own threshold table
(`22-jobspy-spike.md:52`): *"block rate > 25%, or it fails silently and cannot be
health-checked reliably → **drop it.** Do not build a router branch around something
that lies about its own state."* Both halves of that condition are met, not one.

`23-serp-abstraction.md:75` says "Task 22's outcome sets whether step 2 exists at
all." **It does not exist.** Step 2 of the router should be deleted from task 23,
along with the JobSpy canary in its Definition of done (`23-serp-abstraction.md:119`).

---

## The headline finding, which is not the one the spike was designed to find

**JobSpy's Google Jobs scraper returns zero rows from this machine, and the cause is
not an IP block.**

The spike was built to answer "does a residential IP get through where a datacentre
IP does not?" That question was never reached. Google now requires JavaScript to
render *any* search result page, so a plain HTTP client — which is all JobSpy's
Google scraper is — receives a JS bootstrap shell containing no results, regardless
of who is asking or from where.

Evidence, in the order it removed alternative explanations:

| probe | result |
|---|---|
| `udm=8`, "AI operations specialist jobs near New York, NY" | HTTP **200**, 91,420 B, **0 jobs** |
| grep the response for `sorry/index`, `unusual traffic`, `captcha`, `recaptcha` | **0 occurrences of each** |
| grep the response for `data-async-fc` (the cursor JobSpy needs) | **absent** |
| grep the response for `enablejs` | **present** — it is a JS-required shell |
| **plain web search, no `udm` at all** (`q=weather new york`) | same 91 KB JS shell, no results |
| 4 different User-Agents (JobSpy's Chrome 130, a current Chrome 138, a bare UA, an old Firefox) | all 4 → same shell |
| `gbv=1` (the historical no-JS hint) | same shell |

The plain-web-search row is the decisive one. `q=weather new york` has no query-syntax
subtlety, no jobs vertical and no location parsing, and it still comes back as a
bootstrap page with zero results. **No query could have worked**, so "wrong query
syntax" — the explanation the upstream project offers for this symptom — is ruled out
here.

The response body is, in full, a `<noscript>` meta-refresh to
`/httpservice/retry/enablejs` plus a JS bundle. Google announced this on 2025-01-17
and was explicit that the purpose was to block scrapers and SEO tools. It is a
deliberate, global, 18-month-old platform change, not a reputation signal this IP
tripped.

### Confirmed upstream, and unfixed

[JobSpy issue #302](https://github.com/speedyapply/JobSpy/issues/302), "Google Jobs
and ZipRecruiter scraping not working (returns 0 results / 403 forbidden)", reports
this exact warning string. Opened **2025-09-06**, still **open** as of this run —
roughly eleven months with no fix and no maintainer diagnosis. This is not a local
misconfiguration and it is not about to be repaired.

---

## The six measurements

Dated 2026-07-28. Four are answerable, two are not, and the reason they are not is
itself the result.

**1. Does it work at all from this IP?** — **No. 0 of 20 queries returned any row.**
Total rows across the whole set: **0**.

**2. Result parity vs SerpApi** — **0%.** On the same queries and the same machine,
SerpApi's `google_jobs` engine returned **10 results for 10 of 10** attempted, every
one carrying an apply URL. Overlap by apply URL is 0, trivially: one side of the
comparison is the empty set. The Google Jobs vertical is alive and well; only the
free path into it is dead.

**3. Field completeness** — **unanswerable on the JobSpy side**, no results to
inspect. Worth recording from the source that had it worked, a second detail fetch
would *not* have been needed: `_parse_job` reads the description straight off the
card at `job_info[19]` (`jobspy/google/__init__.py:186`). The SerpApi control carried
median description lengths of 2,201 / 6,201 / 4,508 chars across the three queries
and apply options on 30/30 results.

**4. Block rate over 14 days** — **not run, deliberately.** The task asks for 30
queries a night for two weeks because "blocking is often gradual — reputation
accrues" (`22-jobspy-spike.md:66-68`). That design assumes a scraper that works on
night one and may degrade. This one fails 100% of the time on night one, from a
deterministic cause that is not reputational. Fourteen nights of 30 queries would be
~420 requests to Google to re-observe the same zero, and would be the one part of
this spike that could plausibly harm the IP's standing. **A 14-day observation has
nothing to observe.**

**5. Failure mode** — **silent, and this is the disqualifying finding.**
Across 23 total Google queries: **zero exceptions raised**, every HTTP status **200**,
every result set empty. In source, `scrape()` finds no cursor, emits
`log.warning("initial cursor not found, try changing your query or there was at most
10 results")`, and **returns `JobResponse(jobs=[])`** (`jobspy/google/__init__.py:54-58`).
The warning even suggests the caller's query is at fault. A totally broken scraper
and a genuinely empty search are byte-identical to the caller.

This is precisely the class CLAUDE.md names — *"Silence is this system's failure
mode... Alert on volume, not errors"* — and the same shape as the `UpsertResult.errors`
defect in `docs/ingest/DEFECTS.md`. It is worth noting that had this been integrated
without the spike, it would have contributed zero rows nightly while reporting
success, indefinitely.

**6. Wall-clock** — **p50 0.18s, p95 0.25s over 20 queries.** This number is
meaningless as throughput: it is the latency of failing fast. The SerpApi control ran
p50 3.3s, max 4.6s. Recorded only so nobody later mistakes JobSpy's speed for health —
**it is fast *because* it is broken**, which is a trap for any latency-based monitor.

---

## Why this result is more durable than "it worked from here today"

The team's standing worry about a favourable spike result is that it would be weak:
residential IPs get blocked inconsistently, so one clean night proves little. A
*negative* result has the opposite property here, and it is worth being explicit about
why confidence is high rather than low:

- The failure is **not IP-conditional**. A search with no jobs vertical and no
  location returned the same shell. Changing IP, adding a proxy, or moving to a
  different residential connection cannot change it.
- The failure is **not header-conditional**. Four User-Agents spanning two years and
  three browser families produced identical bytes.
- The cause is **documented and deliberate** on Google's side, and dated.
- The symptom is **reproduced by third parties** and has sat unfixed upstream for
  eleven months.

**What would invalidate this:**

1. **JobSpy ships a JS-executing Google backend** (headless browser or a rendering
   service). Then the spike must be re-run — but note the repo already has a data
   point against that path: `backend/ingest/google-serpapi.py:10-18` records that a
   live test of Playwright-driven browser automation against Google Jobs "got
   CAPTCHA-walled twice in a row (google.com/sorry/index), burning real spend for zero
   results." Browser automation is where the residential-IP question would *actually*
   get tested, and the one prior attempt from this project failed.
2. **Google reverses the JavaScript requirement.** No reason to expect this; the
   change exists to prevent exactly this use.
3. A **fork or alternative library** parses the JS-rendered payload. Not surveyed —
   out of the timebox, and it would need its own spike.

**What this spike did *not* establish:** whether a residential IP is treated better
than a datacentre one by Google's anti-bot systems. That hypothesis is untested. It is
not testable through JobSpy, because JobSpy never gets far enough for IP reputation to
be consulted. Anyone reviving the self-hosted idea should know the original question is
still open — it just cannot be answered with this tool.

---

## Recommendation for task 23: descope it sharply

This goes beyond deleting the JobSpy branch. Two findings now point the same way.

**JobSpy was the reason the abstraction looked cheap.** The ADDENDUM says it plainly
(`ADDENDUM-google-jobs-providers.md:73-74`): *"Test JobSpy first. If it holds up on
your residential IP, the whole table above becomes backup rather than backbone."* It
does not hold up. Every remaining provider in that table is metered, and the router's
job reverts to squeezing eight small free tiers.

**And Google Jobs is 4.8% of the corpus.** `docs/pursuit-gate-volume.md:115` measured
`google_jobs` at 142 of 2,975 matching rows, against greenhouse + ashby at 2,676 —
90% from the ATS pull alone. Task 23's Definition of done is a `serp/` package, eight
provider adapters, a normalizer, a quota ledger with per-provider credit multipliers, a
router, a cache and volume alerting (`23-serp-abstraction.md:108-121`). That is a large
build, and it makes a 4.8% source marginally larger.

**Recommended shape:**

- **Do not build `serp/` as specified now.** Keep the single working SerpApi
  integration (`backend/ingest/google-serpapi.py`) as the only Google Jobs path.
- **Do the cheap experiment first.** The 4.8% figure is measured against the *current*
  query bank, and that bank is the pre-retarget, Eric-shaped one:
  `backend/config/google-queries.json` is 32 queries across `core_swe`,
  `ai_integration`, `bridge_solutions` and `reentry_growth`, every one of them a
  software-engineering title. **Google Jobs has never been asked for the population
  the Pursuit cohort needs**, so 4.8% is not yet evidence that it cannot supply them.
  This spike's own control run is mild evidence the other way: `"barista"` in New York
  returned 10 results with 4,508-char median descriptions.
  Re-point the query bank at Pursuit-shaped terms and re-measure yield. That is a
  config edit plus a repeat of task 05's SQL — hours, not a package.
- **Let that number decide 23's fate.** If a Pursuit-shaped bank moves Google Jobs
  well above 4.8%, the capacity problem becomes real and the abstraction earns itself.
  If it stays near 4.8%, drop 23 and put the effort into ATS breadth, which is where
  90% of the corpus already comes from and where task 05 located the actual bottleneck
  (`docs/pursuit-gate-volume.md:126-129`: *"The broad-industry, non-tech employers the
  Pursuit cohort targets are essentially absent from every configured source... it is
  missing an entire category."*).
- **Task 24 (contributor API) is unaffected.** `22-jobspy-spike.md:75-76` already says
  so: it is the community feature, not just a quota source.

One piece of task 23 is worth keeping regardless of what happens to the rest:
**volume-based alerting**. This spike is a live demonstration of why — a source that
returns zero while reporting success is the failure mode, and it is not hypothetical.

---

## The query set, committed

Task 22 requires the query set be committed so it can be re-run when JobSpy or Google
changes (`22-jobspy-spike.md:82`). Deliberately **not** the existing bank in
`backend/config/google-queries.json`, which is pre-retarget and entirely
software-engineering titles; this one is Pursuit-shaped — entry-level, AI-adjacent,
all industries, NYC.

Location for all 20: `New York, NY`. JobSpy was called with
`site_name=["google"]`, `results_wanted=10`,
`google_search_term=f"{query} jobs near New York, NY"`, 2.5s between queries.

```
AI operations specialist            healthcare operations coordinator
AI implementation specialist        nonprofit program associate
automation specialist               legal operations assistant
workflow automation coordinator     logistics coordinator automation
prompt engineer                     recruiting coordinator AI
AI solutions associate              junior data analyst
operations analyst                  marketing coordinator AI
customer success associate AI       executive assistant automation
program coordinator                 business operations associate
AI content specialist               entry level analyst
```

All 20 returned 0 rows. Three of them (`AI operations specialist`, plus
`software engineer` and `barista` as controls) were also run through SerpApi, which
returned 10/10 each.

---

## Conduct of the spike

Recorded because the task is outward-facing and the IP is the one `run-daily.py` uses
nightly.

- **LinkedIn was never queried.** Every call passed `site_name=["google"]` explicitly.
  CLAUDE.md forbids scraping LinkedIn outright, and JobSpy supports it, so this was
  pinned in code rather than left to default. Worth stating what that costs: LinkedIn
  is a large part of JobSpy's value proposition for most users, so even a working
  JobSpy would have been worth materially less to this project than to the average
  adopter. That constraint applies to any future self-hosted scraper, not just this one.
- **Volume was small and one-directional.** 23 Google queries plus ~7 raw diagnostic
  requests, all at 2–3s spacing, spread over well under an hour. 3 SerpApi searches
  spent, from 116 remaining of the 250/month free tier.
- **No retrying into a block**, because there was never a block to retry into: every
  response was HTTP 200 with no CAPTCHA, no `/sorry/index` and no "unusual traffic"
  interstitial. Google's standing with this IP appears untouched — which the nightly
  SerpApi run does not depend on anyway, since SerpApi's own infrastructure talks to
  Google, not this machine (`backend/ingest/google-serpapi.py:105-112`).
- **No production code merged.** No dependency added, no ingest script, no
  `run-daily.py` entry, no schema, no `requirements.txt` change. JobSpy exists only in
  a scratchpad venv outside the repo. This document is the only artifact.

---

## Definition of done

- *"The six measurements above, recorded with dates."* ✔ — all six above, dated
  2026-07-28. Four measured; #3 is unanswerable on the JobSpy side for want of
  results, and #4 was deliberately not run, both with reasons stated.
- *"A written decision against the thresholds, including which branch was taken."* ✔ —
  drop it; third row of `22-jobspy-spike.md:52`, on both of its conditions.
- *"The query set committed, so it can be re-run when JobSpy or Google changes."* ✔ —
  20 queries above, with the exact call parameters.
- *"No production code merged."* ✔ — nothing added to the repo but this file.

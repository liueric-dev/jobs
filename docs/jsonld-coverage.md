# JSON-LD coverage on the long tail

**Task:** `docs/tasks/refactor/tranche_three/19-jsonld-parser.md`
**Measured:** 2026-07-28, against 55 live employer careers sites.
**Tool:** `backend/tools/jsonld-probe.py`. **Raw observations:**
`backend/data/jsonld-probe-2026-07-28.json`.
**Requests spent:** 333 of a 500 ceiling. **Nothing was written to the database.**

This is a measurement spike. **No parser was built.** The deliverable is a number,
its method, and a recommendation.

---

## Headline

**2 of 55 employers publish parseable `schema.org/JobPosting`. 3.6%.**

**Recommendation: DROP task 19.** Not descope — drop. The reasoning is in
[The recommendation](#the-recommendation); the short form is that the population it
exists to serve does not publish the data it exists to read, and the two employers
that do are reachable by cheaper means.

Task 19 estimates **30–60 relevant postings/day**. The generous ceiling measured
here is **1.1–2.3/day**, and that ceiling is not reachable. The claim is **13×–53×**
the ceiling.

This is the fourth Phase 3 yield estimate to be checked and the fourth to come back
an order of magnitude high:

| task | estimated | measured |
|---|---|---|
| 14 (NYC Open Data) | 20–60/day | 1.8/day |
| 18 (Workday CXS) | 80–200/day | ~1/day at four tenants |
| 05 (gate volume) | — | 43/day, ≈3/day usable |
| **19 (JSON-LD)** | **30–60/day** | **≤1.1–2.3/day (ceiling, not estimate)** |

Every figure in this document is printed by `jsonld-probe.py` against the committed
results file. Reproduce all of them with:

```
cd backend && (set -a; . ./.env; set +a; \
  python3 tools/jsonld-probe.py --report; \
  python3 tools/jsonld-probe.py --summarize data/jsonld-probe-2026-07-28.json --population all; \
  python3 tools/jsonld-probe.py --evidence  data/jsonld-probe-2026-07-28.json --population all; \
  python3 tools/jsonld-probe.py --estimate  data/jsonld-probe-2026-07-28.json --population all)
```

`--summarize` and `--estimate` also take `--population company_ats.never_found` and
`--population ats_seed.not_found` for the two halves separately. **No mode of this
tool writes anything**; `--run` and `--sitemap-pass` are the only ones that touch the
network, and neither is needed to reproduce a figure.

---

## The population is not the one the task assumes

`19-jsonld-parser.md:15-17` names its population: employers in `company_ats` with
`status = 'never_found'`. There are **35** of those. That set is *not* the set of
employers with no public ATS feed, and the difference is large enough to matter.

```
company_ats never_found:                     35
ats_seed not_found with NO never_found row:  104
true 'probed, no ATS' population:            139
```

`ats_seed` holds 376 seeded employers and records a probe outcome per employer
(`migrations/migrate_company_ats.py:98-116`). 139 of them came back `not_found` — the
real negative. Only 35 of those 139 also got a `never_found` row written into
`company_ats`, and those 35 are a contiguous alphabetical block:

```
first letter of employer_name, never_found rows:
  M=8  N=20  O=2  P=5
```

**This is a defect worth registering separately, not a fact about employers.** A
partial write-back means anything that sizes work off `company_ats.status` is sizing
off 25% of the population, chosen by initial letter. It also biases the 35 hard
toward NYC public institutions — 20 of 35 begin with "N", most of them "New York …" —
so their sector mix is government/health-heavy where the true `not_found` population
is education/nonprofit/finance-heavy:

| sector | in the 35 | in all 139 |
|---|---|---|
| government | 8 | 9 |
| education | 3 | 20 |
| nonprofit | 3 | 18 |
| finance | 3 | 17 |
| health | 5 | 15 |

**What was done about it.** The 35 were probed as briefed, *and* a seeded random
sample of **20** from the other 104 was probed as a representativeness control
(`--extra-sample 20`, `random.Random(19)`, reproducible). The two agree, which is the
main reason the headline is quotable:

| population | probed | reached | publish JobPosting |
|---|---|---|---|
| `company_ats.never_found` | 35 | 29 | **1** (2.9%) |
| `ats_seed.not_found` (control) | 20 | 16 | **1** (5.0%) |
| combined | **55** | **45** | **2** (3.6%) |

---

## Method

Two passes. The second exists because the first would have produced a wrong answer,
and that is the most important methodological point in this document.

### Pass 1 — careers page, then links out of it

Per employer: `robots.txt`, the careers page, up to 3 job-detail links scraped from
its HTML, and up to 3 sitemap documents. **204 requests over 35 + 20 employers.**

Pass 1 alone says *1 of 35 (2.9%)*. **That number is not trustworthy on its own**
(`--evidence`):

```
detail_pages_tried distribution           {0: 46, 1: 4, 2: 2, 3: 3}
employers reached                         45
reached with ZERO crawlable job links     36
detail pages opened, all employers        17
detail page outcomes                      {'missing_page': 5, 'fetched': 12}
```

**36 of the 45 reached employers render their listing client-side, so there were no
`<a href>`s to follow and no job detail page was ever opened for them.** Across all 55
employers, pass 1 managed to open **17** job detail pages in total, of which 12
returned content. Reporting pass 1 as employer coverage would be measuring
careers-page *index* markup and calling it employer coverage — structurally the same
error task 16 made when its positive
control found zero of four known-good ATS tokens because those boards render
client-side.

### Pass 2 — real job URLs, taken from each employer's own sitemap

A sitemap does not care whether the listing renders client-side, and it is the
discovery path `19-jsonld-parser.md:42-45` puts first. For every employer whose
sitemap declared job-shaped URLs, the first 3 were opened and parsed.
**129 requests, 66 job pages, 24 employers.**

```
employers with sitemap job URLs to try    24
job pages opened                          66
... fetched                               58
employers with >=1 JobPosting on a job    1 of 24
job pages fetched but carrying none       55
... of those, look client-side rendered   6
```

### Extraction

**`extruct` is not installed and was not installed.** `19-jsonld-parser.md:53` calls
for it; `backend/requirements.txt:1-6` is explicit that psycopg is "the pipeline's
only third-party dependency … every added package is another thing that can be
missing on one of them." A spike deciding *whether* to build a thing must not install
that thing's dependency as a side effect of deciding. The probe is stdlib only.

What that costs, so no floor is read as a ceiling:

| format | handled | note |
|---|---|---|
| JSON-LD | fully | `json.loads` over `<script type="application/ld+json">`, which is what extruct does too |
| microdata | scope counting + document-level `itemprop` set | not per-scope |
| RDFa | **detection only** | `typeof="JobPosting"` counted, never parsed |

RDFa was rejected rather than half-implemented: a real extractor needs CURIE prefix
resolution against `@vocab` and `xmlns:*`, and the question this spike asks is
"does the long tail publish anything at all", for which a count suffices.
**It did not matter — across every page opened in both passes, microdata JobPosting
scopes seen: 0. RDFa `typeof=JobPosting` scopes seen: 0.** Every posting found was
JSON-LD.

`@graph`, top-level arrays, `ItemList`, and `ItemList.itemListElement[].item` are all
handled by a **generic recursive walk** rather than by special-casing the three shapes
`19-jsonld-parser.md:58-59` names. Special-casing handles the three shapes someone
thought of and silently drops the fourth; two real shapes are already outside that
list (the `ListItem` indirection Google's own examples use, and `mainEntity` on a
`WebPage`). Verified against fixtures for all four shapes plus a `@type` given as a
list.

### Politeness

`robots.txt` fetched first and obeyed for this User-Agent; an unreachable or refused
`robots.txt` is treated as full disallow (RFC 9309 §2.3.1.4), not as permission.
One global request per 1.5s **and** at most one per host per 5s. **No retries ever** —
retrying into a rate limit is how a probe becomes an incident. A host answering
401/403/406/429/451 is blocklisted for the rest of the run. Honest User-Agent naming
the project with a contact URL, not a browser string.

```
requests, total     333  = pass 1 204 (page 145 + robots 59) + sitemap pass 129
request ceiling     500
delay/host-delay    1.5s / 5.0s
blocklisted hosts   ['careers.marshmclennan.com', 'ceoworks.org', 'www.glwd.org', 'www.paramount.com']
```

**No Firecrawl credits were used.** Task 20 needs that pool
(`19-jsonld-parser.md:89-92`), and a JS-rendered page is a *finding* here, not an
obstacle to route around. `curl_cffi` was likewise not used: TLS-fingerprint
impersonation exists to defeat a refusal, and a refusal is a datum this measurement
wanted to record.

**`_comment` convention — what was rejected:** browser User-Agent (a host that does
not want automated traffic is entitled to recognise it and say no; a 403 is a datum);
`RobotFileParser.read()` (it opens the URL itself, sending urllib's default UA,
bypassing the rate limiter *and* the request ceiling — three ways to be impolite while
implementing politeness); following off-host links (a careers page linking to
greenhouse would turn this into a measurement of greenhouse, precisely the population
task 19 is *not* for); probing past the end of a board.

---

## Results

### Outcomes

```
CAREERS-PAGE OUTCOME (population: all)
  fetched                  45    81.8%
  robots_disallowed         5     9.1%
  blocked                   3     5.5%
  unreachable               1     1.8%
  missing_page              1     1.8%
  REACHED (denominator)    45
```

`robots_disallowed` and "no JobPosting" are deliberately different buckets. Five
employers — MetLife, NYPL, NYU, New-York Historical Society, God's Love We Deliver —
**forbid** this crawl in `robots.txt`. Task 19 would be forbidden too. That is 9% of
the population removed before any parser question arises.

### Coverage

```
employers with >=1 parseable JobPosting      2  of 55   (3.6%)
... as a fraction of employers REACHED       2  of 45   (4.4%)
found on the careers page itself             0
found only on a job-detail page              1
found only via the sitemap pass              1
... those three sum to                       2   (must equal 2)
    via job-detail page  Moody's (3 posting(s))
    via sitemap pass     Etsy (3 posting(s))
microdata JobPosting scopes seen             0
RDFa typeof=JobPosting seen (count only)     0
reached, no JobPosting, looks like an SPA    7
unparseable ld+json blocks (all pages)       3
distinct postings harvested                  6
```

**The two hits came from two different discovery paths, and neither path alone would
have found both.** Moody's was reachable only by scraping job links out of its careers
HTML; Etsy only through its sitemap, because its careers page 404'd. At n=2 that is
worth stating plainly: an implementation would need *both* the index-page crawl and
the sitemap-driven crawl of `19-jsonld-parser.md:40-50` to achieve even the 3.6%
measured here. It cannot be descoped to whichever path looks cheaper. That raises
task 19's cost against an already-failing yield — it is an argument for dropping it,
not a caveat against doing so.

**Zero employers carry JobPosting on the careers page itself.** The `ItemList`
handling `19-jsonld-parser.md:58-59` warns so sharply about — "you will silently
ingest one posting from a page carrying twenty" — had nothing to fire on. There was
no page carrying twenty. Structured data is not *absent* from these sites; it is
present and it is about something else (`--evidence`):

```
ld+json <script> blocks found             41
... that did not parse as JSON            3
employers whose careers page had >=1      23
employers whose careers page had a        0
    JobPosting in one of them
```

**23 of 55 employers ship JSON-LD on their careers page and not one of them puts a
`JobPosting` in it.** That is the finding, and it is a stronger negative than an
absence would be: these employers have a structured-data pipeline and chose not to
describe their jobs with it.

The two publishers — named, because at n=2 a reader who cannot see *which* two cannot
judge whether they generalise:

| employer | population | discovery path | postings | fields |
|---|---|---|---|---|
| **Moody's** | `company_ats.never_found` | job-detail page linked from careers HTML | 3 | 7/8, **no `validThrough`** |
| **Etsy** | `ats_seed.not_found` (control) | `careers.etsy.com/sitemap.xml`, 36 job URLs declared | 3 | 7/8, **no `baseSalary`** |

That **Etsy** is one of the two is itself informative about what `ats_seed.not_found`
contains. It is a well-resourced tech employer running a bespoke careers site, not a
long-tail employer on Taleo or ADP — which is the profile `19-jsonld-parser.md:15-17`
describes. The one employer in the population task 19 actually targets is Moody's,
and Moody's publishes no `validThrough`.

Etsy's careers page 404'd in pass 1 (`missing_page`) and was found only by the
sitemap pass — which is the case the two-pass design exists for.

All three Etsy postings give `identifier` as the literal string `"Etsy"` and carry no
`url` at all, so an ingest keyed on either would collapse the whole board onto one
row. The first version of this tool did exactly that and reported 1 posting where the
truth was 3.

### Field completeness

n = 6 postings, 2 employers. Reported because the brief asks for it; **it cannot bear
weight at this n.**

| field | postings | % | employers |
|---|---|---|---|
| `title` | 6 | 100.0% | 2 |
| `description` | 6 | 100.0% | 2 |
| `datePosted` | 6 | 100.0% | 2 |
| **`validThrough`** | **3** | **50.0%** | **1** |
| `employmentType` | 6 | 100.0% | 2 |
| `hiringOrganization.name` | 6 | 100.0% | 2 |
| `jobLocation.address` | 6 | 100.0% | 2 |
| `baseSalary` | 3 | 50.0% | 1 |

**`validThrough` is the field that decides whether re-crawl is affordable**
(`19-jsonld-parser.md:69`). One of two employers publishes it. Moody's — the only
publisher actually in the `never_found` population — does not. So for the population
task 19 serves, the re-crawl mitigation that made the cost model work is **absent**,
and the fallback is the decaying re-crawl at `19-jsonld-parser.md:71-73`, i.e. the
expensive path, for the entire corpus.

### Sitemaps — and why the sitemap counts are not what they look like

```
employers with a fetchable sitemap          45 of 55
... carrying job-shaped URLs                24 of 55
... with <lastmod> on those URLs            22 of 55
total job-shaped sitemap URLs seen        7053
```

**Do not read 7,053 as 7,053 postings.** Opening 66 of them showed what they mostly
are:

| employer | declared | what the sampled URLs actually were |
|---|---|---|
| AECOM | 4,906 | **real job detail pages** — and carrying **zero** JSON-LD |
| Boston Consulting Group | 802 | `/ca/fr/career-growth`, `/ca/fr/…-jobs` — content and category pages, one per taxonomy node per language |
| Moody's | 347 | `/en/employment/london-sales-and-marketing-jobs/…` — faceted category indexes |
| Bronx Community College | 263 | `/jobtitles/academic-advisor/` — a job-*title* glossary, not postings |
| New York Life | 251 | `/careers/our-offices/ak` — one page per US state |
| NBA | 47 | `/career-development/`, `/intern-jobs` — content pages |
| Etsy | 36 | **real job detail pages**, JSON-LD present |

An earlier run of this tool — superseded, and not the one in the committed results
file — counted category indexes as job URLs, because `/category/…-jobs/` matches
"jobs". That was found by *opening* them, and those paths are now excluded
(`_LISTING_PATH` in `jsonld-probe.py`, with the measurement that motivated it recorded
beside the pattern). **The remaining 7,053 is still an overcount**, and this is stated
rather than corrected because correcting it needs a per-employer URL taxonomy — which is the crawler task 19 proposes, and is not worth building to
measure whether to build it.

The one clean signal: **AECOM declares 4,906 genuine job pages with `lastmod`, and
serves no structured data on any of the three sampled.** That is the shape task 19
was hoping for on the discovery side and a flat negative on the extraction side.

---

## The estimate

### What is measured, and what is not

**Measured well:** coverage — 2 of 55 employers, 3.6%, corroborated across two
independently drawn populations (2.9% and 5.0%).

**Not measured:** postings/day per publishing employer. At most three job pages were
opened per employer, so what was harvested is a sample of two boards, not a census.
The tool prints a raw rate of 0.07/day from the 6 postings and then says so itself:

```
STEPS 5-10 ARE NOT A YIELD, AND MUST NOT BE QUOTED AS ONE.
n=6 postings. CLAUDE.md: 'n=17 is not a result.'
```

**Deriving a postings/day estimate from n=6 was rejected.** The honest instrument at
this n is a *ceiling*: pick every uncertain quantity generously in task 19's favour
and see whether the claim survives. It does not.

### The ceiling

```
a  employers probed                        55
b  publishing parseable JobPosting         2
c  coverage = b/a                          0.036  (3.6%)
d  true 'probed, no ATS' population        139
e  employers in d expected to publish      5.1   = c x d
f  ASSUMED open postings per employer      100   (generous)
g  ASSUMED posting lifetime, days          30    (generous)
h  gross new postings/day                  16.8  = e x f / g

i  relevant fraction (hand-checked precision, n=30): 0.067
j  => RELEVANT POSTINGS/DAY                1.13/day
i  relevant fraction (AI-vocab + entry-level + NYC/remote): 0.137
j  => RELEVANT POSTINGS/DAY                2.31/day

UPPER BOUND: 1.1 - 2.3 relevant postings/day.
```

Every input favours task 19, deliberately, so that a reader who disputes one has to
dispute it *upward* — and there is no room upward:

- **f = 100 open postings/employer.** The two publishers declared 36 (Etsy) and an
  uncountable number (Moody's — its sitemap "job" URLs are category pages, so its
  live stock was never established). 100 is above both.
- **g = 30-day lifetime.** Shorter means more churn means more new postings/day, so
  30 is the generous end; the ATS feeds already ingested turn over more slowly.
- **i** comes from `docs/pursuit-gate-volume.md` — the pipeline's own measured funnel
  on the corpus that already exists (13.7% clear AI-vocab + entry-level + NYC/remote;
  6.7% survived hand-checking, n=30). Using the pipeline's funnel rather than the n=6
  gate result, which cannot resolve anything.

**The ceiling is still not reachable.** It credits task 19 with every posting at
every publishing employer, while one of the two publishers (Etsy) is not in the
`never_found` population task 19 exists to serve, and the other (Moody's) publishes
no `validThrough`, so its postings would need the expensive re-crawl path.

For the record, the relevance gate *was* run over the harvested titles, through
`relevance.tier_sql()` against a TEMP table rather than a Python reimplementation
(CLAUDE.md: "one implementation, two callers"). Result at n=6: tier 1 = 0, tier 2 = 1,
tier 3 = 5. **Reported, not used.** Six titles cannot resolve a fraction.

---

## The recommendation

**Drop task 19.** Do not build it, and do not descope it to "just the good employers".

1. **The data is not there.** 3.6% coverage, corroborated across two populations.
   The `never_found` employers run Taleo, Oracle, ADP, Paylocity and bespoke
   React careers sites, and those render client-side and emit no structured data —
   7 of 45 reached employers are visibly SPA shells with nothing server-rendered, and
   the other 36 simply publish no `JobPosting` anywhere reachable.

2. **Descoping to the publishers does not survive contact.** There are two of them.
   One is outside the target population. The other, Moody's, has **no `validThrough`**,
   which removes the cost mitigation the design leans on
   (`19-jsonld-parser.md:67-73`) and leaves decaying re-crawl for the whole corpus.
   A parser, a sitemap crawler, a re-crawl scheduler, a completeness store and a
   request-budget report — the six items in the Definition of done — for **one**
   employer's board is not a trade anyone would make stated plainly.

3. **9% of the population forbids it.** Five of 55 disallow this crawl in
   `robots.txt`. That is a permanent, non-negotiable ceiling on any version of this.

4. **The one employer worth having is reachable more cheaply.** Moody's job detail
   URLs are a stable, enumerable shape — `/en/job/{city}/{slug}/49841/{id}`, with a
   constant `49841` tenant segment (see `--evidence`) — and its careers page does
   expose crawlable links to them, which is how pass 1 found all three postings. If
   Moody's postings are wanted, add a bespoke fetcher for Moody's — one employer, one
   file — rather than building a general structured-data crawler to reach it. How
   many postings/day that would yield is **not measured here**; three pages were
   opened, not a board.

5. **It is the fourth over-estimate in a row, and the mechanism is now clear.**
   14, 18, 05 and 19 were all sized from the same table by the same method, and all
   four came back an order of magnitude low. **Every remaining Phase 3 yield estimate
   should be treated as unmeasured until it is measured.** Task 20 (iCIMS) is next
   and is sized the same way; it should get the same treatment *before* its Firecrawl
   credits are committed.

### What to keep

- `backend/tools/jsonld-probe.py` — keep. It is the instrument for re-asking this
  question in six months, and it is the positive control for the answer.
- `backend/data/jsonld-probe-2026-07-28.json` — keep. The raw observations, so the
  numbers above can be recomputed rather than trusted.
- **The `company_ats` / `ats_seed` write-back gap (35 vs 139)** — register as a defect.
  It is independent of this decision and it silently mis-sizes anything that reads
  `company_ats.status`.
- **The loose-date finding** — any future structured-data reader needs it. Moody's
  publishes `datePosted: "2026-6-10"`, which `datetime.date.fromisoformat` rejects.
  The first cut of this tool reported "0 of 3 postings have a parseable datePosted"
  directly beneath a completeness table asserting `datePosted` was present on 100% of
  them. **It was caught only because two numbers produced by the same tool
  contradicted each other** — which is an argument for printing more numbers than the
  prose needs, not fewer.

---

## Threats to validity

- **Every coverage figure is a floor.** Three job pages per employer, one careers
  page, one sitemap. An employer publishing JSON-LD on page four is counted as a
  negative. The floor is nonetheless 26× below the claim, and closing a 26× gap by
  sampling deeper would need the publishers to be ~26× denser than the sample — while
  55 of 58 fetched job pages carried nothing.
- **Blocked ≠ absent.** 3 blocked + 1 unreachable + 5 robots-disallowed = 9 employers
  where the question was never asked. All 9 are counted in the denominator, which is
  conservative *against* this document's conclusion — and 5 of the 9 are excluded
  from any future version by `robots.txt` anyway.
- **The 20-employer control is a sample.** Seeded (`random.Random(19)`) and
  reproducible, but n=20. It agrees with the 35 (5.0% vs 2.9%); it does not
  independently establish 3.6% to two significant figures, and 3.6% should not be
  quoted to two.
- **`ats_seed.not_found` inherits task 16's blind spot.** Task 16's own positive
  control found zero of four known-good ATS tokens because those boards render
  client-side, so `not_found` does not mean "no ATS" — some of these 55 employers do
  have an ATS feed nobody has found. That makes the JSON-LD population *smaller* than
  139, which makes this document's ceiling **generous**, not tight.
- **No JavaScript was executed.** By design — Firecrawl credits are task 20's. An
  employer whose JSON-LD is injected client-side reads here as a negative. This is
  the single assumption most likely to be wrong, and it is bounded — `--estimate`
  prints the bound:

  ```
  SENSITIVITY: if every SPA shell hides perfect JSON-LD
    reached, no JobPosting, looks like an SPA  7
    coverage would be                          9 of 55  (16.4%)
    gross new postings/day                     75.8
    => relevant postings/day                   5.1 - 10.4/day
  ```

  Even crediting task 19 with *every* SPA shell hiding perfect JSON-LD behind
  JavaScript, it lands at 5–10 relevant/day — still short of 30–60, and it would cost
  a Firecrawl fetch per page forever, which is task 20's budget.

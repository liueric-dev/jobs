# 35 — Extraction input sanity

**Status:** done (implemented with this file). **Depends on:** nothing. **Blocks:** nothing.

Extraction had no opinion about what it was reading. Give it one.

This file was written alongside the implementation rather than before it, because the
measurement that decides the predicate could only be made against the live table. Read
the measurement section before changing any number in it.

## The defect

Job `ff9f9d9f9643e185af0f48ca` (Taboola, *Product Analyst (Maternity-Leave
Replacement)*) had a `description_text` beginning:

```
*]:pointer-events-auto R6Vx5W_threadScrollVars scroll-mb-[calc(var(--scroll-root-safe
-area-inset-bottom,0px)+var(--thread-response-height))] ..." data-turn-id="request-WEB
:2bf172fa-..." data-testid="conversation-turn-136" data-turn="assistant">
```

That is a rendered ChatGPT web UI, not a job posting. It was **re-extracted at
`facts_version = 3` and produced confident facts from that markup** —
`role_archetype = 'data'`, `role_track = 'data_and_analytics'`, plus a fluent
two-sentence summary about partnering with Product Managers to define KPIs. The
re-extraction propagated the poison rather than clearing it.

It was not alone, and one row was worse. `53cbf3ae21a12bff1ff73476` (Get Hire
Technologies, *AI/ML Engineer*) carried **2,700 characters of a staffing firm's
navigation menu** — "SolutionsCareer Training Program (CTP)Managed Service Provider
(MSP)…", repeated four times — before the real posting began at character ~2,700. The
prompt window is 3,000 characters, so the model read the menu and about 300 characters
of job. It answered `senior` / `ml_research` / `core_ml_research`, and **that one
reached a `job_scores` row**: an LLM narrative, derived from a navigation menu, in the
list a Builder actually reads.

Extraction had no input-sanity gate at all. The whole of input preparation was
`extract.py:361`:

```python
description = (job.get("description_text") or "")[:MAX_DESCRIPTION_CHARS]
```

and the only content predicate anywhere was `coalesce(j.description_text,'') <> ''` at
`extract.py:406`. Non-empty went to the model; whatever came back was stored as fact.

**The general shape: any ingest path that captures the wrong bytes gets them laundered
into structured facts.**

## Provenance — confirmed, and it redirects the fix

All the greenhouse rows come through `ingest/ats.py`, a structured ATS API, not a
scraper. The markup is in **the employer's own job-description field**. Verified by
reading the stored `raw_json` and re-fetching live:

```
$ curl 'https://boards-api.greenhouse.io/v1/boards/taboola/jobs/8035268?content=true'
content len 11148,  'data-testid' in content: True
```

`ats.py:716` sets `description_text` from `greenhouse_description(job.get("content"))`,
and `greenhouse_description` (`ats.py:559-584`) is `strip_html(html.unescape(content))`.
Greenhouse served the DOM; the pipeline faithfully stored it. Somebody pasted a browser
page into Greenhouse's JD editor.

So the fix belongs at **extraction, for every source** — not at one scraper. That is
confirmed by the corpus: two of the contaminated rows are `google_jobs`, one of which
(`7bdfba1a4e254be44463737c`, SpeedyApply) is a scraped careers page. Same defect, two
completely different acquisition paths.

### Why the markup survived `strip_html()` — the mechanism

`lib/text.py:119` strips tags with `re.sub(r"<[^>]+>", " ", text)`. That is correct
until an attribute **value** contains `>`. Modern Tailwind class names do:

```
<section class="... [&:has([data-writing-block])>*]:pointer-events-auto ..." data-testid="...">
                                                ^ the regex ends the "tag" HERE
```

Everything after that `>` — the rest of the class list, then the `data-*` attributes,
then the real closing `>` — is emitted as **text**. Every contaminated row in the corpus
is that one mechanism.

**This was not fixed in `lib/text.py`, deliberately.** `strip_html` is called by every
ingest path, and a change to it rewrites `description_text`, which feeds `content_hash`
for the ATS and Google sources (`schema.py:131-135`) — the exact failure that module's
own docstring records (`lib/text.py:7-13`: unifying on the wrong variant reported 217
of 242 weworkremotely rows as changed when nothing upstream had). The blast radius is
the whole corpus; the defect is eight rows. Correcting the stripper is worth doing on
its own schedule, with a re-hash planned. `tests/test_extract.py`'s
`test_the_markup_survived_strip_html_in_the_first_place` fails when it happens, which
is the correct signal rather than a nuisance.

(Note for whoever does: CLAUDE.md's `lib/` vendoring rule is stale —
`HANDOFF.md:259-264`, `tools/lib-parity.sh` does not exist. `lib/` is this repo's own
code. The reason not to touch it here is blast radius, not vendoring.)

## The design

**The gate sits at `extract_facts()`, immediately before `build_prompt()`, and returns
`REJECTED`.** Four properties earn it that seat:

- `extract_facts` already has the three-outcome vocabulary `EXTRACTED` / `DEFERRED` /
  `REJECTED`, generalised from `score.py`.
- `REJECTED` already writes a tombstone at the current `FACTS_VERSION`
  (`mark_extract_failed`), so the row is not retried nightly — and a future
  `FACTS_VERSION` bump gives it one more chance, which is right if the employer has
  since fixed their posting.
- It costs **zero LLM calls**. The gate runs before `call` is even resolved, so that is
  structural rather than a claim in a comment, and a test asserts the fake `call` is
  never invoked.
- It surfaces in the `unusable` counter on the summary line, and it lands in `REJECTED`
  rather than `DEFERRED` so `drain_loop`'s zero-progress break still reads a batch of
  poisoned rows as progress.

**It is NOT in `_eligible_sql`.** A `WHERE` clause would remove these rows from
`remaining()` instead of reporting them — hiding the defect rather than counting it.
CLAUDE.md is explicit that silence is this system's failure mode.

**No new schema column.** The rejection reason rides in the model label instead:
`mark_extract_failed` is called with `input-markup/<model>`, which
`llm.failed_label()` renders as `FAILED:input-markup/deepseek-v4-flash@…`. The
`FAILED:` prefix is what every consumer actually tests (`match.py:285` excludes
tombstones with `NOT LIKE 'FAILED:%'`, `evals/corpus.py:171` buckets them the same
way), so the reason is queryable without moving a single predicate. Without it, the only
trace of a gate firing would be a `+1` on a counter shared with genuine model failures —
which is the silence the gate exists to end.

## The predicate, and the measurement that chose it

`markup_ratio(text)` is the share of whitespace-delimited tokens that match any of seven
markup signatures — an HTML attribute assignment (`foo="`), a CSS custom property
(`var(--`, `[--`, `--tw-`), a Tailwind arbitrary variant (`[&`, `]:` + lowercase), or
`!important`. It is pure, so it can be swept over a corpus without a database or a call.
It reads the **prompt window** (`prompt_description()`, the first
`MAX_DESCRIPTION_CHARS`), shared with `build_prompt` so the two cannot drift: markup past
character 3,000 reaches no model and is not grounds for a tombstone.

**Swept over all 13,282 described postings** (`tools/audit-description-markup.py`,
2026-07-28). Every row scored exactly `0.0` except eight, and those eight split with a
gap in the middle:

| ratio | job_id | platform | company / title |
|---|---|---|---|
| 0.5928 | `6fc72985f864b17e3c4c2513` | greenhouse | Fireblocks / GRC Expert |
| 0.1366 | `516d19374b2b9caf27ac6cf3` | greenhouse | Affirm / Business Development Associate |
| 0.1290 | `ff9f9d9f9643e185af0f48ca` | greenhouse | Taboola / Product Analyst ← the reported one |
| 0.0796 | `1074b7f0354bc3cceed49194` | greenhouse | Per Scholas / Instructional Assistant |
| 0.0640 | `e93ddca38b45bb929e6e46cd` | greenhouse | Databricks / Strategic Core Account Executive |
| 0.0453 | `7bdfba1a4e254be44463737c` | google_jobs | SpeedyApply / Forward Deployed Engineer Intern |
| 0.0247 | `53cbf3ae21a12bff1ff73476` | google_jobs | Get Hire Technologies / AI/ML Engineer |
| — | — | — | *— gap —* |
| 0.0040 | `cc7d1b61574ffdac2d112a8d` | greenhouse | Fireblocks / Product Manager, Mobile |
| 0.0000 | *the other 13,274* | | |

`MARKUP_REJECT_RATIO = 0.01` is the **geometric midpoint of that gap** —
`sqrt(0.0040 × 0.0247) = 0.0099` — so it clears the worst clean row by 2.5x and the
mildest poisoned one by 2.5x rather than sitting against either.

### False positives: 0

Every one of the seven rejected rows was inspected by hand and is contaminated. The
sharper version of the same number, because it is the one that matters:

> Of the **5,901 postings that already carry confident, non-tombstone facts**, the gate
> would reject **4**. All four are on the list above. **5,897 successfully-extracted real
> postings are unaffected.**

`cc7d1b61574ffdac2d112a8d` is **deliberately not rejected**: eleven characters of stray
Tailwind in an otherwise complete Fireblocks job description. Tombstoning a readable
posting is a worse outcome than extracting one with a nick in it. The threshold is set
where a prompt stops being a posting, not where it stops being clean.

### Two alternatives, measured and rejected

**A marker blocklist** (`data-testid=`, `pointer-events-auto`) — the query
`HANDOFF.md:410-413` used, which is where the "three rows" figure came from. It finds
**3 of the 8**. It misses both `google_jobs` rows and both of the Tailwind-only
greenhouse rows (Fireblocks, Databricks), because those leaked class names and no
`data-` attribute. The handoff's count was an artefact of the probe, not of the corpus.

**Repeated-content density** (fraction of duplicate 60-character shingles in the prompt
window), aimed squarely at the navigation-menu case. It scores **0.000 on all eight**
contaminated rows, and its six highest-scoring rows are legitimate postings: **six false
positives, zero true ones.** It measures boilerplate, which real job postings also have.
Recorded so it is not proposed again.

### One signature needed tightening, and the false positive that caused it

`\]:` alone matches `[ONSITE]: We are looking for a system administrator…` — standard
Who's Hiring prose, and `415fcb871b101301330b9a67` is exactly that. Requiring a
lowercase letter with no space (`\]:[a-z]`) keeps the Tailwind variant boundary
(`*]:pointer-events-auto`, `[&_hr]:my-3`) and drops the prose. It is the only false
positive the sweep has ever produced, so it has a test of its own.

## Remediation of the existing rows

A gate does not clean up what is already there. `tools/audit-description-markup.py
--remediate --commit`, run 2026-07-28: **7 jobs cleared, 4 `job_facts`, 5 `job_matches`
and 1 `job_scores` row deleted.** Re-running the sweep afterwards reports
`REJECTED at ratio >= 0.01: 0`.

Three dispositions were available:

1. **Tombstone the facts row, leave `description_text`.** Cheapest, and wrong: the
   poisoned bytes stay, so the next `FACTS_VERSION` bump re-extracts them and re-derives
   exactly the facts this task removes. It fixes the symptom at one version only.
2. **Delete the `jobs` row.** Loses the posting — and five of the eight are real jobs at
   real companies whose descriptions merely have soup spliced through them. Deleting
   Databricks' account-executive req over twelve Tailwind class names is worse than the
   defect.
3. **NULL `description_text`, clear `content_hash`, delete everything derived.** Chosen.

3 is right because the writes are parts of one fact: the bytes were never a job
description, nothing derived from them is evidence, and the row must be able to heal.
NULLing `description_text` makes the posting ineligible
(`coalesce(j.description_text,'') <> ''`), so it costs no further calls.

### The landmine in option 3, which is worth its own paragraph

**Clearing `content_hash` is not optional, and omitting it strands the row forever.**
`description_text` **is** in `HASH_FIELDS_ATS` and `HASH_FIELDS_SHORT`
(`schema.py:131-135`), and `lib/upsert.py:219` compares the **stored** `content_hash`
against a hash recomputed from the **incoming** record. A row whose `description_text` is
NULL but whose `content_hash` still matches upstream takes the `touch_sql` branch on every
subsequent run: `last_seen` is bumped, the description is never rewritten, and the posting
is permanently invisible while the night reports success. That is this pipeline's
signature failure mode, reintroduced by the cleanup meant to fix it. Clearing the hash
forces the UPDATE branch exactly once.

`job_matches` and `job_scores` are deleted too. They `CASCADE` from `jobs`, not from
`job_facts` (`schema.py:344,415,435`), so deleting the facts row alone would leave a
`match_score` and an LLM narrative derived from markup sitting in a Builder's list —
which is how `53cbf3ae21a12bff1ff73476`'s `core_ml_research` got there.

The expected repair is the employer fixing their job description. If they do not, the
gate rejects it again at the cost of one tombstone write and zero LLM calls.

The tool defaults to a dry run despite the owner's standing stance that database contents
are staging data (`HANDOFF.md:28-33`), because a destructive default that is only ever
typed once is a destructive default nobody reads twice.

## The fixture is a recording, not a construction

`evals/fixtures/cassettes/ats-greenhouse-domsoup.json`, recorded via
`python3 evals/record_cassettes.py ats-greenhouse-domsoup`. Two taboola postings from the
same board on the same day: `8035268`, the poisoned one, and `8087797` (*Senior Data
Scientist*), an ordinary posting as the control.

`HANDOFF.md:571-574` is the reason: *fixtures written from a specification test the
specification*, and all three failure modes task 18 found live were invisible to its four
constructed fixtures. The token that matters here is
`[&:has([data-writing-block])>*]:pointer-events-auto`, and what makes it dangerous is the
`>` in the middle of a class attribute. Nobody writing a fixture from a prose description
of "browser markup" would include that.

The recipe **refuses to record** bytes that no longer carry the defect — if Taboola fixes
the posting, or if the control starts scoring above the threshold, it raises rather than
silently downgrading to two clean postings that assert nothing. Same guard
`record_workday_cxs()` uses, same lesson (`HANDOFF.md:565-570`: a fixture that no longer
triggers its own failure reads like coverage and is worse than none).

The single-job endpoint is used rather than `fetch_greenhouse()`: the whole board is 95
postings and 875 KB of which one posting is the evidence, `ats-greenhouse.json` already
pins that `fetch_greenhouse` pages and unescapes correctly, and this recipe pins what
`greenhouse_description()` does to one pathological `content` at 26 KB. Same precedent as
`record_ats_greenhouse_no_content()`.

## What this does NOT catch — stated, because a gate that overclaims is worse than none

The predicate detects **leaked markup**. It is not a "is this a job posting" classifier.

`53cbf3ae21a12bff1ff73476` — the navigation-menu row — is caught only **incidentally**,
by two `data-widget_type="` fragments that happened to leak alongside the menu text. A
scraper that captured a clean navigation menu with no markup residue at all would score
`0.0` and pass. That case is real (it is what a better-behaved scraper produces) and it
is not addressed here.

The obvious candidate for it — repetition density — was measured above and is worse than
nothing. The honest next step is a positive-evidence check ("does this text contain the
things job postings contain") rather than a negative one, and it needs a corpus study of
its own before it earns a threshold. Not in scope; recorded so the limit is known rather
than assumed away.

## Definition of done

- [x] A gate at `extract_facts()`, before `build_prompt()`, returning `REJECTED`.
- [x] Zero LLM calls on a rejection — asserted with a fake `call` that fails the test if
      invoked.
- [x] A normal posting is unaffected, asserted over **real** postings: the cassette
      control, and a sweep showing 5,897 of 5,901 already-extracted rows untouched.
- [x] A false-positive sweep over the full `jobs` table, with its number: **0 of 13,282**,
      re-runnable via `tools/audit-description-markup.py`.
- [x] The rejection reaches the `unusable` counter, and lands in `REJECTED` so
      `drain_loop` still counts it as progress.
- [x] No new schema column.
- [x] The existing rows remediated by a repeatable script, not a one-off.
- [x] A recorded cassette rather than a constructed fixture.
- [x] Suite: **832 tests, OK** (floor was 782).

## Follow-ups this opens

1. **`strip_html()` mishandles `>` inside an attribute value.** The root cause. Fixing it
   requires a planned re-hash of the ATS and Google sources; see the blast-radius note
   above.
2. **Non-markup junk still passes**, per the section above. Needs a positive-evidence
   predicate and a corpus study.
3. **`cc7d1b61574ffdac2d112a8d`** is knowingly left contaminated at ratio 0.0040. It is
   the calibration point for the threshold; if follow-up 1 lands, it disappears on its own.

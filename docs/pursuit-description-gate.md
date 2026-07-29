# The description-first cohort gate

**Task:** `docs/tasks/refactor/tranche_two/10-description-first-gate.md`
**Measured:** 2026-07-28, at commit `2725949`, against the live database (11,824 rows in `jobs`).
**Amended:** 2026-07-29 — the gate **moved out of the migration** into
`backend/config/pursuit-relevance.json` (`4eefb7e`, proven a no-op), and two defects
that `docs/mock-acceptance.md` found were fixed (`e8f3b72`, `9dab9e6`).
**Method:** SQL only. No LLM calls. Nothing extracted or scored. The only write is the
`pursuit` profile row created by `backend/migrations/migrate_pursuit_profile.py`, which
is `active=False`.

> **Read the *Amendment, 2026-07-29* section before citing any number below.**
> Everything from *What changed in the code* onward is the 2026-07-28 measurement at
> commit `2725949` and has not been re-derived. The gate it describes is still the gate,
> with two lists changed and one file moved; the counts it quotes are one day and 1,623
> rows out of date.

---

## Headline

A posting whose title says nothing about AI and whose description says everything now
reaches tier 1 for a cohort profile that did not previously exist. Harvey's
**User Operations Specialist** — *"working fluency with AI tools (e.g. ChatGPT, Claude,
Gemini); you use them, not just know of them"* — sits at **tier 3** under the shared
config and at **tier 1** under the cohort gate.

**876 rows** are eligible for the cohort profile (tier ≤ 2), **573** of them newly, at
**13.2 postings/day** over the same 30-day window task 05 used. Hand-checked precision
on the newly-admitted set is **10.0% strict / 23.3% generous, n=30**, against task 05's
**6.7% / 10%** baseline for the vocabulary alone.

The gate is better than the one task 05 measured and it is still mostly noise. Nothing
about the correction it applies changes the conclusion task 05 reached: **the bottleneck
is sourcing, not gating.**

The author's `frontend` and `tech` profiles are byte-for-byte unaffected.

---

## Amendment, 2026-07-29

`docs/mock-acceptance.md` ran 55 synthetic postings through this gate and measured
something no live sample can: **recall**. It was **48.3%** — 15 of 29 intended-good
postings rejected, every one of them tier 3 and every one carrying AI vocabulary in the
description but not the title. Those are exactly the ordinary-employer roles this
profile exists to reach. Two causes, both fixed here; the mock corpus now reports
**89.7%**.

**`48.3% → 89.7%` is a statement about that corpus, which was built to contain the
failure mode it measures. It is not this gate's real recall and must never be quoted as
one.** What it is worth in production is the 11 rows below.

Four changes landed: `4eefb7e` (the move), `e8f3b72` (cause 1), `9dab9e6` (cause 2), and
one database write — `migrate_profiles.py --apply`, **without `--bump`** — to rewrite the
profile's `relevance_json` from the file. Re-measured with
`tools/mock-acceptance.py --dry-run` and with SQL; **no LLM calls**.

### Where the gate lives now (`4eefb7e`)

**`backend/config/pursuit-relevance.json`.** It was a dict literal inside
`migrations/migrate_pursuit_profile.py`. **Any citation anywhere pointing at
`COHORT_RELEVANCE` in the migration as the definition of a pattern group is stale** —
the migration still exposes `COHORT_RELEVANCE`, but as a read of the file
(`migrate_pursuit_profile.py:149`, `load_gate()`), so it remains the name to import and
is no longer the place to edit. Current line references:

| group | location |
|---|---|
| `title_include` | `config/pursuit-relevance.json:14` |
| `description_include` | `:55` |
| `title_exclude` | `:101` |
| `platform_exclude` | `:158` |
| the split's rationale and rejections | `:97`, `_description_entry_level_note` |
| the `title_exclude` review | `:145`, `_title_exclude_note` |

The move was proven a no-op: same config object, same emitted SQL, same row counts.

### The two fixes, and what they cost

**1. The entry-level group was title vocabulary applied to descriptions (`e8f3b72`).**
The gate is conjunctive — one AI term **and** one entry-level term in the **same
field** — and the eleven terms were nouns that appear in *titles*. A description does
not repeat its own title's seniority noun, so on the description path the AI half
matched and the entry half did not. The group is now **split**: `title_include` keeps
the same eleven nouns **byte for byte**, and `description_include` carries those eleven
**plus three phrases**, making it a **strict superset**. That shape is the guarantee —
the title path cannot change, the description path can only gain rows. Raw live
description matches, 18 / 0 / 11:

```
\yno\y[^.;:]{0,40}\y(?:experience|background|license)\y[^.;:]{0,25}\y(?:required|needed|necessary)\y
\ydoes not require\y[^.;:]{0,40}\y(?:experience|background)\y
\ytraining (?:is |will be )?provided\y
```

Term 2 matches **0** live rows and is kept deliberately, on the same standing as
`\yattorney\y` under `config/relevance.json:_dead_patterns_note`: verified working
against `mock_012`, waiting for its first live posting. `--dead` will report it.

**2. `title_exclude` gates both paths, and was excluding the target population
(`9dab9e6`).** `\ycustomer success\y` was **narrowed to four manager-and-above forms**,
not removed — removing it outright imports 5 *"Manager, Customer Success"* rows that the
seniority block deliberately does not catch, because `\ymanager\y` was measured and
rejected (see *What was rejected, and why*). The four terms admit exactly **7** rows.

`\yexecutive assistant\y` was **kept**, and the reason is a census rather than an
argument: all 12 open EA postings at the blocked employers were read, and they require
3+, 5+, 5+, 5+, 6+, 6+, 7+, 7+ and 10+ years of executive support (one states no
figure). Most are not NYC — Singapore, São Paulo, Seoul, Costa Rica, DC. Those are
senior administrative roles.

**The list was edited; `tier_sql` was not, and that was the decision.** `title_exclude`
applying to both include paths is deliberate and documented in the source
(`relevance.py:227-231`) and pinned by a test asserting it holds on **both** tier arms
(`test_relevance.py:203-211`). Changing `tier_sql` so it gated only the title path would
break that test and re-admit the **1,906** rows `config/relevance.json:121` counts as
sitting at tier 3 *because* of `title_exclude` — account executive, recruiter, nurse,
controller, VP.

### Live counts

Over **13,447 open rows**, 2026-07-29. **This is a different population from the 876 in
the Headline**, which is whole-table, all statuses, on 2026-07-28 at 11,824 rows. Do not
diff the two.

| step | tier ≤ 2 |
|---|---|
| before | 869 |
| after the vocabulary split (`e8f3b72`) | 873 |
| after the `title_exclude` narrowing (`9dab9e6`) | **880** |

Final distribution: **tier 1 456, tier 2 424, tier 3 12,567.**

`extract.remaining` went **2 → 13**. That backlog is under half of one
`EXTRACT_BATCH_SIZE=40` batch (`extract.py:113`) — about **$0.004** — and drains on the
first nightly run.

### Hand-check of the delta: a census, not a sample

All **11** added rows were read, not sampled, so there is no sampling error to argue
about:

| | n |
|---|---|
| on-target | ~7 |
| clear false positive | 1 |
| ambiguous | 3 |

That is **~64% strict**, against the incumbent gate's **10.0% strict / 23.3%
generous** measured on n=30 in *Hand-check, n=30* below. **The rows being added are
better than the rows already in.** The one clear miss is honest rather than a dialect
error: *Research Engineer, Interpretability | Anthropic* really does say "no research
experience is required".

### The four phrase families that were rejected — and why the mock corpus could not decide them

The mock corpus's three surviving false negatives are reachable only through four more
phrase families, and **on that corpus all four are free — zero added false positives.**
Compiled through `relevance.tier_sql` against the same 13,447 open rows they admit:

| family | live rows added |
|---|---|
| "we provide / offer … training" | +17 |
| "we (will) train" | +5 |
| "preferred but not required" | +5 |
| "experience … preferred / is a plus" | **+123** |

**All of them are senior engineering requisitions at AI employers** — `Software
Engineer, RL Training Infra | OpenAI`, `Full-Stack Software Engineer, Reinforcement
Learning | Anthropic`. `\ywe train\y` matched OpenAI's *"we train models"*, a false
friend that **cannot exist on a synthetic corpus** because no author writing a mock
rejection would think to write it. They score free there because every intended-bad mock
posting carrying that phrasing has no AI vocabulary at all, so the conjunction stops it
whatever the entry-level list says.

**A synthetic corpus can bound recall but cannot price precision, because its negatives
were written by whoever wrote its positives.** Recall stops at 89.7% on purpose. Nothing
in the mock run licenses these four; adding them on its evidence would have bought a
100% mock score and roughly +136 live rows of senior engineering -- a deduplicated
union, measured 2026-07-29 with zero overlap between the four.

### What a widened gate actually costs

**A widened gate is priced by the one-time backlog it creates, not by steady state.**
The earlier framing in this document — widening the gate widens the extraction queue —
points at the wrong risk. Extraction has roughly **15× headroom** against the volumes in
*Volume, for task 12*, and a one-off 11-row backlog is $0.004. **The real cost of
widening is precision**, which is why the census above is the number that mattered and
`extract.remaining` is not.

### What this does not deliver

**11 postings on a pool of 869 is +1.3%.** It does **not** meaningfully change what task
29's labellers will see, and it moves GATE 2's ">= 200/day" question **not at all**.

Doing it first was still right — the defect was real, the fix was cheap, and a labelling
session run through a knowingly-broken gate is wasted work. But nobody should read a
recovery into it that it does not deliver. Everything the Headline says still holds:
**the bottleneck is sourcing, not gating.**

---

## What changed in the code

### `description_include` (`backend/relevance.py:189-300`)

`tier_sql` composed title include/exclude, company exclude, description exclude and the
location columns. It now composes a second include path:

| tier | rule |
|---|---|
| 1 | (title match **or** description match) **and** location acceptable |
| 2 | (title match **or** description match), location unknown or elsewhere |
| 3 | everything else |

The OR is built at `relevance.py:223-226`; `title_exclude` is appended to the combined
predicate at `:227-234` — deliberately, and the comment there says so — so it gates
**both** paths, and the two tier arms repeat the whole
`row_ok` (`:297-299`) so an excluded title cannot merely drop from tier 1 to tier 2. A
`COALESCE(description_text, '')` guards the include path (`:220`) for the same reason
`description_exclude` has one (`:276`): 37 rows have no description, and `NULL ~* pattern`
is `NULL`, not `FALSE`.

### The invariant

**With `description_include` absent, null or empty, `tier_sql` emits the identical
string and the identical params.** Verified two ways:

1. **Byte equality against `HEAD`.** The pre-change module was loaded side by side with
   the new one and both were asked for SQL over the production config file, over
   `DISABLED`, over include-only, include+exclude, excludes-without-include, and
   locations-configured. All seven identical, including `union_sql`.
2. **Pinned in the suite.** `backend/tests/test_relevance.py:TestDescriptionIncludeIsInert`
   holds the production SQL as a golden string and asserts that absent / `[]` / `None` /
   `[[]]` all produce the same `(sql, params)` across six config shapes. It is
   deliberately brittle: anything that changes that string changes which postings get
   extracted, and that should require somebody to look at the string.

### Include groups (`relevance.py:123-187`)

An include list is either a flat list of strings — one OR group, the historical shape,
still what every list in `config/relevance.json` uses — or a list of lists, meaning a row
must match at least one term from **every** group. That is how the cohort gate expresses
"AI vocabulary AND an entry-level signal" (see *Why the gate is conjunctive*). A single
group keeps the un-suffixed parameter name (`rel_include`, not `rel_include1`), which is
what makes the byte-identity above possible.

**Rejected: writing the conjunction as one Postgres regex with lookahead constraints**
(`^(?=[\s\S]*a)(?=[\s\S]*b)`). It works — Postgres 16.4 supports lookahead, and `.`
matches newline by default so the `[\s\S]` is belt-and-braces — and it was the first
version. Two reasons it lost, neither of them correctness:

- It defeats `tools/relevance-report.py --dead`, which tests one term at a time and is
  the only thing standing between this config and the `\y`-vs-`\b` landmine. A lookahead
  blob is a single untestable pattern.
- Measured 1.00s of sequential scan against 0.77s for the plain AND over the same
  11,824 rows, because constraints force Postgres's backtracking engine.

### `platform_exclude` (`relevance.py:271-273`)

New, mirroring `company_exclude`. Matched against `jobs.platform`. It exists because the
task requires dropping the three tech-company sources from the *cohort* gate only, and
there was no mechanism for "this profile does not want this source" — sources are not
interchangeable across profiles, and deleting one globally would take it from the
author's profiles too. Emits nothing when absent, so it is inert for everyone who does
not set it (`test_relevance.py:test_platform_exclude_is_inert_when_absent`).

### `tools/relevance-report.py`

Three changes, all to make the `--dead` check actually cover the new configuration:

- `--profile NAME` now resolves that profile's own `relevance_json` via
  `relevance.for_profile`, not just which scored rows to exclude. A per-profile gate that
  the report cannot see is a gate nobody has checked.
- `dead_patterns` covers `description_include`, `platform_exclude`, `company_exclude` and
  `description_exclude`, each against the column `tier_sql` applies it to, and flattens
  include groups so every term is tested individually rather than hidden behind its
  live neighbours in a joined alternation.
- The **include** lists are tested against `title || description_text` rather than
  against one column. Deliberate: now that `description_include` exists, an include term
  is a claim about the posting's text, and this report's job is to catch the dialect
  mistake — a term that matches *nothing, anywhere* — not to prune terms that are merely
  rare in titles. `config/relevance.json:_dead_patterns_note` draws exactly that
  distinction. Per-column testing would report `zapier`, `copilot`, `n8n` and `make\.com`
  as dead purely because no title contains them, and a report that cries wolf is a report
  nobody reads.
- It also loads `backend/.env` (`override=False`), the way `tools/cost-test.py:314`
  does. It previously failed with "DATABASE_URL is not set" unless the caller exported it
  by hand, which is a poor property for the tool the landmine note tells you to run after
  every edit.

`backend/config/relevance.json` is **unchanged**. So is `max_tier_to_score = 2`, for the
reason `DECISIONS.md:300-330` records: `relevance.py:297-299` sends everything failing
`row_ok` to tier 3 and `:331` admits on `tier <= max_tier`, so 3 is an unconditional pass
that disables four exclusion lists at once.

---

## Why the gate is conjunctive

The task file says to lift task 05's regex verbatim and treat it as the gate. That would
ship a filter that task 05 itself hand-checked at **6.7% precision over 2,975 rows**.
The reason is in `docs/pursuit-gate-volume.md:196-217`: Pinterest, Brex, Braze, Notion,
Wiz, ElevenLabs, Anthropic and OpenAI all ship an AI blurb in the header of *every*
requisition, so a description-only vocabulary match selects for **the company being
AI-ish, not the role**. It is not a gate.

So the cohort gate requires **AI vocabulary AND an entry-level signal**, with location
deciding tier 1 vs tier 2 as before.

**Rejected: requiring the two signals in *different* fields** — AI anywhere in
title-or-body AND entry-level anywhere in title-or-body. That is the looser reading and
the one task 05's own numbers describe. It admits 1,803 rows against 1,671, and a 30-row
`md5(id)` sample of the 132-row delta was, on inspection, ~100% junk:

> Senior Marketing Data Analyst · Associate General Counsel, Commercial · Global Filing
> Specialist, Tax · Assistant Controller · Senior Oracle Procurement Specialist ·
> Analyst, Expert Insights - ECS (German Speaking) · Fund Accountant (Associate,
> Controller, Director)

Every one of them pairs an entry-level *word* in the title with company AI boilerplate in
the body — precisely the failure mode task 05 documented, arrived at from the other
direction. Requiring co-location in a single field is a weak proxy for "the AI vocabulary
is about the work", but it is not *no* proxy, and it costs 132 rows that are all noise.

The title path is kept even though it adds only **7 rows** beyond what
`description_include` already admits — descriptions restate their own title 81% of the
time (857 of 1,058 rows with an entry-level title signal also carry one in the body). The
7 are the best rows in the set:

```
FT/PT Remote AI Prompt Engineering & Evaluation – Will Train   (x2)
Technical Specialist, Claude Code
AI Specialist, Treasury Finance Operations
Associate Software Engineer — AI/LLM & Financial Systems
Machine Learning Researcher - PhD Intern (US)
```

It is also the only path for the 37 rows that have no `description_text` at all.

---

## The patterns

Postgres `~*`. Word boundary is `\y`. **[2026-07-29]** These lists now live in
`backend/config/pursuit-relevance.json`, not in the migration, and two of them have
changed — see *Amendment*. What follows is as measured on 2026-07-28.

**AI vocabulary** — task 05's list (`docs/pursuit-gate-volume.md:42`) plus three terms:

```
chatgpt|claude|copilot|gemini|\yllm\y|large language model|prompt engineer|prompting|
generative ai|\ygen ai\y|automation|workflow automation|zapier|\yn8n\y|make\.com|
ai tool|ai-powered|machine learning|\yai\y|ai-driven|ai-enabled
```

Added: **`\yai\y`**, **`ai-driven`**, **`ai-enabled`**. Task 05's list has no bare `\yai\y`
and so drops 3 of the 9 genuine tier-3 rows it identified itself; the two hyphenated forms
are how a large share of the corpus writes it (728 and 458 descriptions respectively).
The bare `\yai\y` is the expensive one — it alone matches **9,273 of 11,824** descriptions,
and removing it takes the gate from 1,671 rows to 1,177 — but it is load-bearing for
recall, and the entry-level conjunct is what makes it affordable.

**Entry-level signals** — task 05's list (`:48`) plus **`\yintern(ship)?s?\y`**:

```
\yentry.?level\y|\yjunior\y|\yassociate\y|\ycoordinator\y|\yassistant\y|\yspecialist\y|
\yanalyst\y|\yno experience\y|\ywill train\y|\yapprentice\y|\yintern(ship)?s?\y
```

The omission mattered: internships and new-grad programmes are the most reliably
entry-level postings in the corpus, and **both** rows judged genuine in the hand-check
below are Databricks intern/new-grad requisitions. Rejected: bare `\yintern` without a
trailing boundary — it matches `internal`, which appears in most job descriptions.

**[2026-07-29] This group is no longer shared between the two include paths.** The
eleven nouns above are the **title** group and are unchanged, byte for byte;
`description_include` carries them plus three phrases and is a strict superset. The
defect that forced it, the measurements, and the four phrase families that were
measured and rejected are in *Amendment* and in
`config/pursuit-relevance.json:_description_entry_level_note`.

### What was rejected, and why

- **Dropping `automation`, `ai tool` and `ai-powered`.** Task 05 measured them as the
  junk generators — 62% of its 2,975 matches came from those three and no narrower term.
  Kept anyway: the conjunction already removes most of what they pulled in, and
  `automation` is the single best word for the roles this cohort actually wants. An ops
  job that runs Zapier flows says "automation" and nothing else.
- **Adding `agentic`, `rpa`, `no-code`, `low-code`.** Plausible, unmeasured, therefore
  not added. Add them with a count beside them or not at all.
- **`gemini` and `claude`, kept despite known false positives.** `gemini` matches Gemini
  the crypto exchange (26 of 90 tier-3 matches in task 05 — and one landed in this task's
  own hand-check sample, *Marketing Coordinator (Predictions Partnerships)*), and `claude`
  matches the given name. Both are cheap to lose downstream, expensive to lose here.
- **`\ymanager\y` (876 → 765) and `\ylead\y` (876 → 833)** in `title_exclude`. Measured,
  not applied. `config/relevance.json:_title_exclude_note` argues at length that broad
  co-occurring words are the wrong thing to exclude, and "Manager, Customer Experience
  Specialist" is not entry-level while "Lead Teacher" can be. Three of the 30
  hand-checked rows were Manager titles, which is n=3 and not a reason to change a list.
  The numbers are recorded so task 13 can decide with them rather than re-derive them.
- **Also dropping `lever` from `platform_exclude`.** It has 9 rows in the table and 0
  reach this gate; excluding it would be a statement about a source nobody has measured.

### What was added to `title_exclude`

`config/relevance.json`'s list verbatim, plus a seniority block that is specific to this
profile: `\ysenior\y`, `\ysr\.?\y`, `\ystaff\y`, `\yprincipal\y`, `\ydirector\y`,
`\yhead of\y`. The cohort is explicitly entry-level and task 05 measured 59.5% of the
AI-vocabulary population as senior/lead/director/VP-shaped. It removes **448 rows**
(1,324 → 876).

The shared list is **copied, not referenced**. `relevance.load` merges a profile's config
over `DISABLED`, not over the file (`relevance.py:88-89`) — deliberately, so a profile's
behaviour never depends on a file it does not mention. The cost is that the two can
drift; check them against each other when either moves.

**[2026-07-29] The list was reviewed against the cohort's own target population and one
term narrowed.** Six of the inherited terms are exclusions on roles this cohort wants.
Rows each was blocking, alone, live: `\ycustomer success\y` 12, `\yexecutive assistant\y`
9, `\yfacilities\y` 1, `\yoffice manager\y` 0, `\ywarehouse\y` 0, `\ydriver\y` 0.
`\ycustomer success\y` became four manager-and-above forms; `\yexecutive assistant\y`
was kept on a 12-posting census; the three that block nothing are undecidable by
measurement and are recorded as such. Full reasoning in *Amendment* and in
`config/pursuit-relevance.json:_title_exclude_note`.

### `\y` vs `\b`

Task 05's positive control, re-run here against `description_text`:

| pattern | rows |
|---|---|
| `\yllm\y` | 1,127 |
| `\bllm\b` | **0** |
| `\yn8n\y` | 37 |
| `\bn8n\b` | **0** |

Zero rows, no error. And in the opposite direction, `make\.com` matches 2 rows table-wide
with the dot escaped and **116** unescaped — a 58× inflation, because `.` is a wildcard
that also catches "make a common…". Both traps are silent.

---

## Tier counts by platform, before and after

Whole table, all statuses. `frontend` and `tech` both have `relevance_json` NULL, so both
resolve to `config/relevance.json` and both produce the same numbers.

### `frontend` and `tech` — before

| platform | t1 | t2 | t3 |
|---|---|---|---|
| ashby | 759 | 239 | 1630 |
| builtin | 128 | — | 291 |
| google_jobs | 516 | 193 | 192 |
| greenhouse | 1285 | 1870 | 4215 |
| hn_whoishiring | 120 | 56 | 71 |
| lever | — | 2 | 7 |
| weworkremotely | 167 | — | 83 |
| **total** | **2975** | **2360** | **6489** |

### `frontend` and `tech` — after

**Identical.** Byte-for-byte: the two tables were generated by the same script before and
after the change and `diff` reports no difference. Independently, `relevance-report.py`
reports the same tier distribution for `tech` over unscored open rows before and after
(1,943 / 2,296 / 6,101), and `union_sql` over the active profiles binds the same ten
parameters as before — no `dincl`, no `pfexcl` — so the extraction gate is provably the
same predicate.

### `pursuit` (new, inactive)

| platform | t1 | t2 | t3 |
|---|---|---|---|
| ashby | 213 | 35 | 2380 |
| builtin | — | — | 419 |
| google_jobs | 54 | 36 | 811 |
| greenhouse | 177 | 361 | 6832 |
| hn_whoishiring | — | — | 247 |
| lever | — | — | 9 |
| weworkremotely | — | — | 250 |
| **total** | **444** | **432** | **10948** |

`builtin`, `weworkremotely` and `hn_whoishiring` are all-tier-3 by construction — that is
`platform_exclude` working. Before it was applied they contributed 116 of 1,664 rows (7%),
consistent with task 05's 5.3%.

### Volume, for task 12

By `posted_at_ts::date` over **2026-06-28 … 2026-07-27**, the same 30-day window task 05
used and for the same reason (`first_seen` is unusable — the table was re-seeded on
2026-07-24, see `docs/pursuit-gate-volume.md:136-149`).

| quantity | value |
|---|---|
| `pursuit` tier ≤ 2, whole table | **876** |
| …of which newly admitted (production tier 3) | **573** |
| …of which NYC or remote (tier 1) | **444** (50.7%) |
| `pursuit` tier ≤ 2, posted in window | 395 → **13.2/day** |
| …newly admitted, posted in window | 268 → **8.9/day** |
| union gate today (`frontend`+`tech`) | 5,335 rows, 1,975 in window → **65.8/day** |
| union gate **if `pursuit` were activated** | 5,908 rows, 2,243 in window → **74.8/day** |

**The number task 12 needs is +9/day, not +13.2/day.** The two active profiles already
admit 303 of the cohort gate's 876 rows, and extraction is shared — `job_facts` is
computed once per posting regardless of how many profiles want it. Activating `pursuit`
raises the nightly extraction pool from 65.8/day to 74.8/day, a **13.7% increase**.

Compare task 05's headline of 43/day for the raw vocabulary at tier 3. The conjunction and
the exclusions take that to 8.9/day of genuinely new work.

### Query cost

`EXPLAIN (ANALYZE, BUFFERS)` on the `pursuit` tier predicate over the whole table:
sequential scan, 136,397 buffers, all shared **hits** (no reads), **1,569 ms**. Against
the shared config alone: 387 ms. The three-profile union: 1,365 ms.

Roughly a second of extra sequential scan, once per nightly run, against task 04's
wall-clock baseline of hours. **No index was added.** A `tsvector` GIN index would not
serve these patterns anyway — `\yai\y`, `ai-powered` and `make\.com` are substring and
boundary patterns, not lexemes, so a GIN index could at best pre-filter and the regex
would still have to run. Revisit if the corpus grows an order of magnitude.

---

## Dead patterns

```
$ python3 tools/relevance-report.py --dead --samples 0 --profile pursuit
unscored open jobs for profile 'pursuit': 11445
gated by its own relevance_json
  NOTE: this profile is INACTIVE. ...

  tier 1:     427  (  3.7%)  scored
  tier 2:     404  (  3.5%)  scored
  tier 3:   10614  ( 92.7%)  SKIPPED

PATTERNS MATCHING NOTHING
  title_exclude    '\yattorney\y'
  title_exclude    '\ywarehouse\y'
```

**No new dead patterns.** Every one of the 32 include terms and all 3 `platform_exclude`
patterns match at least one open row. The two that are listed are inherited verbatim from
`config/relevance.json` and are documented there as deliberate: `_dead_patterns_note`
records that both were verified to match a synthetic title in Postgres and are kept as
working exclusions waiting for their first posting. They are reported at `HEAD` too, for
the shared config, unchanged by this task — "reports no dead patterns" was never literally
true and the correct reading is "no *new* ones".

The shared config's own report is unchanged: same distribution (1,943 / 2,296 / 6,101),
same two patterns.

---

## Hand-check, n=30

**Sample method.** 30 rows drawn with `ORDER BY md5(id) LIMIT 30` over the 573 rows that
are tier ≤ 2 for `pursuit` **and** tier 3 for the shared config — i.e. the newly-admitted
set, the rows this task is responsible for. Deterministic and reproducible.
Not `ORDER BY first_seen DESC`, which `CLAUDE.md` forbids because it is ~85%
greenhouse/ashby. This is an L0 set: never train on it, never recycle it. The ids are
listed at the end.

**Criterion**, the same one task 05 used: does the AI vocabulary describe *the work of
the role*, and is the role plausibly reachable by an entry-level Builder?

| | count | precision |
|---|---|---|
| **strict** — both halves of the criterion hold | **3 / 30** | **10.0%** |
| **generous** — entry-level and reachable at an AI-native employer, AI vocabulary boilerplate | **7 / 30** | **23.3%** |
| task 05 baseline, vocabulary alone | 2 / 30 | 6.7% (10% generous) |

**The three strict passes:**

- Databricks — *Product Management Intern (Summer 2027)*
- Databricks — *Associate Product Manager, New Grad (2027 Start)*
- EliseAI — *Customer Sentiment Specialist | Housing* — entry-level specialist at an
  AI-agent company, NYC, and the work is the AI product

The first two are the same two rows task 05 found. Both are 2027 starts.

**The four the generous count adds:** Cloudflare *Brand Social Media Intern (Fall 2026)*,
Cloudflare *Marketing Events and Campaigns Intern (Fall 2026)*, Brex *Brex Rotational
Program*, Toast *IT Help Desk Analyst*. All four are genuine entry points that a Builder
could get; in none of them does the AI vocabulary describe the role.

**The 23 rejected, by kind:**

| kind | n | examples |
|---|---|---|
| back-office ops where AI is company boilerplate | 8 | Yext *Billing Analyst*, Stripe *Financial Analyst, Business F&S*, AlphaSense *People Operations Coordinator*, Anthropic *People Partner, Tokyo* |
| sales-shaped | 5 | Toast *Bilingual Hybrid Development Representative* (×3), Databricks *Lakebase Specialist Sales*, Everlaw *Renewals Specialist* |
| manager / senior in all but title | 5 | Justworks *Manager, Customer Experience Specialist*, ElevenLabs *Billing Operations Manager*, OpenAI *IT Support Singapore, APAC Regional Lead*, Harvey *GTM Technology Product Owner* |
| marketing / events | 1 | Movable Ink *Event Marketing Specialist* |
| physical security | 1 | Pinterest *Physical Security Specialist II* |
| clinical | 1 | Sailor Health *Remote Clinical Psychologist – PhD / PsyD* |
| wrong-entity vocabulary match | 1 | Gemini (the crypto exchange) *Marketing Coordinator* |
| mid-level support at an AI company | 1 | OpenAI *Product Engagement Specialist, User Operations* |

**Say it plainly: 10% is a bad number.** It is 1.5× task 05's baseline and it is still
nine junk rows for every good one. The conjunction fixed what it was designed to fix —
the 59.5% senior-shaped and 23.5% sales-shaped fractions task 05 measured drop to 17.5%
and 18.7% on the newly-admitted set — and it did not fix the dominant failure, which is
that **an entry-level back-office role at an AI company matches every term in both
groups honestly**. Yext's *Billing Analyst* really is a billing analyst, at a company
whose boilerplate really does say "AI", and no regex over these two vocabularies can tell
it from Harvey's *User Operations Specialist*.

Population-level corroboration over the 876 eligible rows, which is stronger than n=30
and agrees with it:

| check | rows | of 876 |
|---|---|---|
| any AI signal in the **title** | 99 | **11.3%** |
| senior/lead/director/head/VP/principal/manager in title | 151 | 17.2% |
| sales-shaped title | 131 | 15.0% |
| AI match only on the bare `\yai\y` | 247 | 28.2% |
| NYC or remote | 444 | 50.7% |

11.3% have any AI signal in the title, against task 05's 4.3% for the vocabulary alone
and against a hand-checked 10.0%. The three agree.

**What this means for task 12 and task 13.** **[2026-07-29] The extraction-volume half
of this paragraph prices the wrong risk** — see *What a widened gate actually costs*.
The conclusion is unchanged; the reason is that widening costs a one-time backlog, not
steady-state throughput, and the binding constraint is precision. The gate is worth
shipping — 13.2/day for a
13.7% increase in extraction volume is cheap, `job_facts` is shared so the marginal cost
is only the 8.9/day that no active profile already wants, and it recovers rows like
Harvey's and Notion's that were invisible. It is **not** worth ranking on. Something
downstream has to distinguish "the role uses AI" from "the employer sells AI", and
`job_facts.ai_involvement` already exists to answer exactly that question. That is task
13's problem, and it now has a corpus to work on.

---

## The `pursuit` profile

Created by `backend/migrations/migrate_pursuit_profile.py`, following
`migrate_profiles.py`'s convention: dry run by default, `--apply` to write, idempotent.

- **`active=False`.** `profiles.load_active` filters on `active` (`profiles.py:94-106`)
  and is the only way `extract.py` and `match.py` learn a profile exists;
  `relevance.union_sql` (`relevance.py:307`) is built from exactly that list. Verified
  after applying: `load_active` returns `['frontend', 'tech']`, and the union gate binds
  the same ten parameters and selects the same 5,335 rows as before. **Production
  extraction volume provably cannot move until a human activates it.** `--active` is a
  separate flag from `--apply` so that creating the row and starting to spend LLM calls
  on it cannot be the same keystroke.
- **`persona_json` and `criteria_json` are placeholders and say so in their own text.**
  `criteria_json` is `base: 50` with empty `archetypes`, `flags` and `tech.boost`, so
  every posting would score exactly `base` — visibly uninformative rather than plausibly
  wrong. Task 13 owns the real weights and is blocked on cohort product judgement that is
  not this task's to make. Copying the `tech` profile's numbers would be worse than
  leaving them empty: they encode one software engineer's positioning.
- **`daily_narrative_budget=0`**, for the same reason.
- **`relevance_json` is real**, and **[2026-07-29]** is now read from
  `backend/config/pursuit-relevance.json` rather than defined in the migration
  (`migrate_pursuit_profile.py:149`, `COHORT_RELEVANCE = load_gate()`). It carries a
  `_comment` on every group: `_gate_shape_note`,
  `_regex_dialect`, `_ai_vocab_note`, `_entry_level_note`, `_title_include_note`,
  `_description_include_note`, `_title_exclude_note`, `_company_exclude_note`,
  `_platform_exclude_note`, `_description_exclude_note`, `_location_note`,
  `_max_tier_note`. Each records what was rejected, not only what was kept.

---

## Definition of done

- **A posting titled something outside `title_include` whose description mentions ChatGPT
  reaches tier 1 or 2.** ✔ 11 such rows. Two verified individually — Harvey *User
  Operations Specialist* (production tier 3 → cohort tier 1) and Notion *People Analytics
  & Operations (Rotational Program)* (tier 3 → tier 1). Neither title matches
  `config/relevance.json`'s `title_include`; both descriptions name ChatGPT as a tool the
  role uses. No constructed test was needed.
- **`frontend` and `tech` tier assignments unchanged.** ✔ Tier-count-by-platform tables
  diff clean; `union_sql` binds the same parameters; the emitted SQL is byte-identical to
  `HEAD`.
- **A test pins the invariant.** ✔ `tests/test_relevance.py`, classes
  `TestDescriptionIncludeIsInert`, `TestDescriptionInclude`, `TestIncludeGroups`,
  `TestPlatformExclude`.
- **`--dead` reports no dead patterns.** ✔ No new ones; the two reported are inherited and
  documented as deliberate.
- **30 newly-admitted rows hand-checked.** ✔ 10.0% strict / 23.3% generous, against task
  05's 6.7% / 10%.
- **Tier-count-by-platform before and after, plus the cohort's counts and rows/day.** ✔
- **Every new pattern group has a `_comment` recording rejections.** ✔
- **The `pursuit` profile exists via a migration, inactive, placeholders labelled.** ✔
- **Suite green.** ✔ `python3 -m unittest discover -s backend/tests`, run from the
  repo root. 466 before this task, 486 after — the 20 added are the invariant,
  include-group and `platform_exclude` tests. The total read 574 at the final run
  because two other agents were adding tests to the same tree concurrently; nothing
  in `tests/test_relevance.py`, `tests/test_extract.py` or `tests/test_match.py`
  fails.

---

## Defects found and not fixed

Out of scope; recorded so they are not re-discovered.

1. **`title_exclude` has `\yauditor\y` but not `\yaudit\y`.** Yext *IT Audit Analyst*
   clears the gate. Same class: `\yclinician\y`/`\ytherapist\y`/`\yphysician\y` but not
   `\ypsychologist\y` — Sailor Health *Remote Clinical Psychologist – PhD / PsyD* reaches
   tier 1.
2. **"Hybrid Development Representative" evades both `sales development` and `\ysdr\y`.**
   Toast's posting says outright that the role is "the foundational entry point into our
   sales organization … to develop the next generation of Account Executives", and three
   near-duplicate copies of it landed in a 30-row sample.
3. **A Singapore posting is tagged `location_is_remote = TRUE`.** `location_raw` is the
   bare string `'Singapore'` on job `b53c64e1a425afcb219e5776`. It reaches tier 1 for an
   NYC cohort. Ingest-side location tagging, not relevance.
4. **One `description_text` contains scraped ChatGPT web-UI markup.** Job
   `ff9f9d9f9643e185af0f48ca` (Taboola, *Product Analyst*) begins
   `*]:pointer-events-auto R6Vx5W_threadScrollVars … data-testid="conversation-turn-136"`.
   Something in that ingest path captured a browser DOM rather than a posting body. It is
   a data-quality problem for extraction, not for this gate.
5. **`tools/relevance-report.py` did not load `.env`** and failed with "DATABASE_URL is
   not set" unless the caller exported it. Fixed here, since it is the tool the landmine
   note tells you to run after every edit, and one that does not start is one nobody runs.

---

## Hand-checked sample, pinned

`ORDER BY md5(id) LIMIT 30` over the 573 newly-admitted rows, sorted for the record:

```
0c5ebf0334dea42c882d766c  0df7bb0fbfa7688b80116740  188fa2be52683cc320e2777d
25a9220a2af255b74e1e374f  3456694ebf915971c927de38  47217380cf60b22d82b9cd6b
65fc5b1dc213a6778f21926c  6954d573812995f4ad5c6d97  70adcb59836c734cfd914fa4
70c0c92e6a2533a297339eb5  740ce9fc59904bf11ab01212  764e620af2314ca7c8cd0765
79222cdbaeca2789fba87d76  79972a85b3f88d674ce48c5d  94c2d4f66e34f74f14baa278
a4db75a69cf5054b50e7f00f  b37b4dd62fadb84cc51408f0  b53c64e1a425afcb219e5776
b69f9399346a023b3fddf811  c0d1dc24f5ce4b92676a7080  c50c2e57a964d2ef2f41c1c0
ce0f130acde8f76a890ba02e  d89813a843b421275ebd8121  daf07ff41596f7e10f87efaa
e8032539cec11d126315a88e  ed7a3b711f8327ac9dee533a  f250c350d04abfcd5780be00
f706f3c63be1631f2ad99126  fc7ce75e9e2c24c6178b4e16  ff9f9d9f9643e185af0f48ca
```

Seven of these ids also appear in task 05's pinned sample (`0c5ebf03…`, `0df7bb0f…`,
`188fa2be…`, `94c2d4f6…`, `b53c64e1…`, `ce0f130a…`, `ed7a3b71…`) — unavoidable, since both
samples are `md5(id)`-ordered over overlapping populations, and worth knowing before
either is treated as independent evidence.

Per `CLAUDE.md`: this is an L0 set. Never train on it, never recycle it.

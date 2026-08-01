---
kind: record
written: 2026-07-28
generator: none
---

# Corpus volume under a widened gate

**Task:** `docs/tasks/refactor/tranche_one/05-widened-gate-volume.md`
**Measured:** 2026-07-28, at commit `36d83f5`, against the live database (11,824 rows in `jobs`).
**Method:** SQL only. No LLM calls. Nothing extracted, scored, or re-tuned. Read-only (`SELECT`).

---

## Headline

**N = 43 postings/day** matching the AI-tool vocabulary at tier 3, over
**2026-06-28 … 2026-07-27** (30 complete days, by `posted_at_ts::date`).

Adjusted for the hand-checked junk fraction, the *usable* rate is **≈3/day**.
Task 04 should size against 43/day for cost/quota (that is what the pipeline would
process) and against ≈3/day for anything that assumes the postings are on-target.

---

## Results

| quantity | value |
|---|---|
| tier-3 rows matching AI vocabulary | **2,975** (of 6,489 tier-3; 11,824 table) |
| …also entry-level signalled | **659** (22.2%) |
| …also NYC or remote | **407** (13.7%) |
| new per day, 30-day mean | **43/day** (2026-06-28 … 2026-07-27) |
| by platform | greenhouse 2,019 · ashby 657 · google_jobs 142 · builtin 94 · weworkremotely 50 · hn_whoishiring 13 · lever 0 |
| hand-checked precision, n=30 | **6.7%** (2/30 genuine — 93% junk) |

Tier distribution under the production config, for reference: tier 1 = 2,975,
tier 2 = 2,360, tier 3 = 6,489. (Tier 1 and "tier-3 matching AI vocab" are both
2,975. Coincidence — verified as two separate counts, not a copy/paste.)

---

## The regex, verbatim

Postgres `~*`. Word boundary is `\y`. Task 10 can lift this directly.

```
chatgpt|claude|copilot|gemini|\yllm\y|large language model|prompt engineer|prompting|generative ai|\ygen ai\y|automation|workflow automation|zapier|\yn8n\y|make\.com|ai tool|ai-powered|machine learning
```

Entry-level signals, applied to `title` OR `description_text`:

```
\yentry.?level\y|\yjunior\y|\yassociate\y|\ycoordinator\y|\yassistant\y|\yspecialist\y|\yanalyst\y|\yno experience\y|\ywill train\y|\yapprentice\y
```

Location: `COALESCE(location_is_nyc,FALSE) OR COALESCE(location_is_remote,FALSE)`.

Tier is **not** a column. There is no `relevance_tier` on `jobs` (`backend/schema.py:270-293`).
It is computed per query by `relevance.tier_sql()` (`backend/relevance.py:112-192`) from
`backend/config/relevance.json`. This measurement imported that function rather than
re-deriving the predicate, per CLAUDE.md's "one implementation, two callers".

### Positive control for the `\b` landmine

`backend/config/relevance.json:8` (`_regex_dialect`) warns that `\b` is BACKSPACE in
Postgres and silently matches nothing. Run both ways against `description_text`:

| pattern | rows |
|---|---|
| `\yllm\y` | 1,127 |
| `\bllm\b` | **0** |
| `\yn8n\y` | 37 |
| `\bn8n\b` | **0** |

The `\b` forms return zero with no error, exactly as documented. Every number in this
report used `\y`.

---

## Per-term contribution (within tier 3)

| term | rows | | term | rows |
|---|---|---|---|---|
| `automation` | 1,200 | | `chatgpt` | 119 |
| `ai tool` | 1,073 | | `gemini` | 90 |
| `ai-powered` | 683 | | `large language model` | 90 |
| `generative ai` | 399 | | `copilot` | 63 |
| `\yllm\y` | 301 | | `prompt engineer` | 44 |
| `claude` | 286 | | `prompting` | 26 |
| `machine learning` | 250 | | `zapier` | 19 |
| `workflow automation` | 93 | | `\yn8n\y` | 14 |
| | | | `\ygen ai\y` | 10 |
| | | | `make\.com` | **0** |

Three terms — `automation`, `ai tool`, `ai-powered` — carry the count. 1,850 of the
2,975 rows (62%) match **only** on those three and no narrower term. They are the
junk generators (below).

`make\.com` matches 0 tier-3 rows and only 2 in the whole table — the tool is
effectively absent from this corpus. Note for task 10: the dot **must** stay escaped.
Unescaped, `make.com` matches 116 rows table-wide, a 58x inflation, because `.` is a
wildcard that also catches "make a common…", "makes com…" and similar. That is a
second silent-inflation trap in the same family as `\b` vs `\y`, in the opposite
direction.

---

## Where they come from

The task predicted "almost none from `builtin-nyc`, `weworkremotely` or
`hn_whoishiring`, and whatever exists arrives via `google_jobs` and the broader ATS
pull."

**First half held. Second half did not.**

| platform | tier-3 + AI | tier-3 total | table total |
|---|---|---|---|
| greenhouse | 2,019 | 4,215 | 7,370 |
| ashby | 657 | 1,630 | 2,628 |
| google_jobs | 142 | 192 | 901 |
| builtin | 94 | 291 | 419 |
| weworkremotely | 50 | 83 | 250 |
| hn_whoishiring | 13 | 71 | 247 |
| lever | 0 | 7 | 9 |

The three tech-company sources contribute 157 rows, 5.3% — the prediction held.
But `google_jobs` contributes only 142 rows, 4.8%. **90% of the volume is the ATS
pull alone** (greenhouse + ashby = 2,676).

This is evidence *for* the Phase 3 sourcing rebuild, but not the evidence the task
expected: Google Jobs is not currently a meaningful source of this population either.
The broad-industry, non-tech employers the Pursuit cohort targets are essentially
absent from every configured source. The platform mix is not skewed — it is missing
an entire category.

Note the platform value is `builtin`, not `builtin-nyc` as the task file writes it.

---

## Rate: how N was derived, and why not from `first_seen`

**`first_seen` cannot produce a 30-day rate.** The whole table spans
`2026-07-24T02:29:11` … `2026-07-28T04:04:15` — five days — and 11,000 of 11,824
rows carry `first_seen` = 2026-07-24. The database was re-seeded on 2026-07-24.
Grouping by `first_seen::date` over "the last 30 days", as the task specifies,
would have returned a 4-day post-backfill window (17, 79, 20, 90 matching rows) and
a meaningless mean. Anyone re-running this should expect the same until the table
has 30 days of organic history.

`posted_at_ts` (populated for 11,694/11,824 rows; 2,974/2,975 of the matching set)
carries the real posting date and was used instead. It is trustworthy for the ATS
platforms: greenhouse and ashby put only 2% of postings on a weekend, which is
genuine business-day behaviour, and their history runs back to 2020-01-23 and
2023-05-25 respectively.

Matching rows by posted date, 2026-06-28 … 2026-07-27: **1,284 over 30 days = 42.8,
so N = 43/day.**

Three caveats, all pushing the same way — **43 is a floor:**

1. `builtin` has only four days of history (2026-07-25 …), `google_jobs` one month,
   `hn_whoishiring` two weeks. Their contribution is absent from most of the window.
   `builtin` alone ran 94 matching rows in 4 days (≈23/day) once it started.
2. The last 7 complete days (07-21 … 07-27) give **80/day** — nearly double. Some of
   that is the newer sources coming online rather than a real acceleration.
3. Greenhouse+ashby alone, which have honest deep history, give **33.5/day** and are
   roughly flat-to-rising week over week (177, 158, 244, 259, 285).

Survivorship was checked and is *not* a factor: 97%+ of matching rows are still
`status='open'` in every week of the window, so older weeks are not depressed by
closed postings being dropped.

`builtin` puts 65% of its postings on a weekend and `google_jobs` 21%, so their
`posted_at` is a scrape/refresh artifact rather than a true posting date. This does
not affect the 30-day total, only any attempt to read day-of-week structure.

---

## False-positive check, n=30

Sample: 30 rows drawn from the 2,975 with `ORDER BY md5(id) LIMIT 30` — deterministic
and reproducible, and representative of the population by platform (20/30 greenhouse
vs 68% in the population). Pinned by sorted `job_id`; the ids are listed at the end.

**Judged genuine: 2 of 30. Precision 6.7%. Junk fraction 93%.**

The criterion: does the AI vocabulary describe *the work of the role*, and is the
role plausibly reachable by an entry-level Builder? The two that pass are Databricks
*Product Management Intern (Summer 2027)* and Databricks *Associate Product Manager,
New Grad (2027 Start)* — both genuinely entry-level at an AI/data company, though
both are 2027 starts. A third, OpenAI *Growth - Digital Marketing (Enterprise)*, does
mention "AI-powered workflows" as part of the role but is a senior B2B marketing
leadership hire; counting it generously gives 10%.

The other 27 are: 11 sales roles (account executive, account manager, customer
success), 8 senior/lead/director/head roles, 4 back-office roles (billing operations,
corporate programs, energy accounting, IT support), 3 marketing roles, and 1 relist
spam posting.

### What generated the junk

Not `automation` and `machine learning` pulling in manufacturing and ML research, as
the task anticipated. That failure mode barely appeared. The dominant one is
**company boilerplate**, and it is worse:

- **`ai-powered` / `ai tool` / `generative ai` match the "About us" blurb.** Pinterest
  ships "At Pinterest, AI isn't just a feature, it's a powerful partner…" in the
  header of every posting, so every Pinterest requisition matches — including
  *Sr. Client Account Manager, Financial Services*. Brex ships "Brex's AI-native
  automation…" identically. Braze, Notion, Wiz, ElevenLabs, Anthropic and OpenAI all
  do the same. **Any AI-adjacent employer matches on all of its postings**, which
  inverts the intent: the pattern selects for the *company* being AI-ish, not the
  *role*.
- **`automation` matches ordinary ops language** — "accelerate operations",
  "workflow automation" in a renewals or IT-support context.
- **`gemini` matches Gemini the crypto exchange.** 90 tier-3 rows match `gemini`;
  26 of them are the company, not the model. *Marketing Coordinator (Predictions
  Partnerships)* at Gemini scores as both AI-signalled and entry-level-signalled and
  is neither.
- **`claude` will match the given name Claude**, same class of error, not separately
  quantified.

Population-level corroboration, which agrees with the hand-check and is stronger
than 30 rows:

| check | rows | of 2,975 |
|---|---|---|
| any AI signal in the **title** | 129 | **4.3%** |
| senior/lead/director/head/VP/principal/manager in title | 1,770 | 59.5% |
| sales-shaped title | 699 | 23.5% |
| match only on `automation`/`ai tool`/`ai-powered` | 1,850 | 62.2% |

4.3% of these rows have any AI signal in the title at all, against a hand-checked
6.7%. The two agree. **A description-only gate on this vocabulary is ~93% noise and
must not be shipped as-is** — which is task 10's job, and this is the baseline it
starts from.

### Relist spam is parked in tier 3

133 of the 2,975 are from the six relisters in `company_exclude`
(`backend/config/relevance.json:88-95`) and 104 contain the literal `reputed company`
from `description_exclude` (`:103-105`). These rows are at tier 3 *because* those
exclusions demoted them — tier 3 is where the spam was deliberately sent. Sample row
26 is `remote click jobs | DevOps Engineer (Remote Opportunity)` whose body reads
"reputed company is seeking an reputed company DevOps Engineer".

**Any plan that reopens tier 3 by raising `max_tier_to_score` to 3 re-admits every
posting the exclusion lists were written to suppress.** Task 10 needs to keep those
exclusions as a separate gate rather than folding them into tier.

---

## Correction: the task's premise does not hold against the config

`05-widened-gate-volume.md:13-20` states that `title_include` is `engineer`,
`engineering`, `developer`, `development engineer`, `software`, `swe`, `programmer`,
`architect`, `sre`, `site reliability`, `devops`, `platform`; that *AI Operations
Coordinator*, *Prompt Specialist*, *AI Implementation Analyst* and *Automation
Associate* therefore "None match. All fall to tier 3"; and that they are "never
scored, never extracted, never seen."

That was true of an earlier config. It is not true of
`backend/config/relevance.json:12-47`, which also contains `\yai\y`, `\yllm\y`,
`\yml\y`, `machine learning`, `\ydata scien`, `\ydata engineer`, `applied scien`,
`forward deployed`, `solutions engineer`, `technical account` and more — 34 terms,
not 12. **Any title with a standalone "AI" token already matches and lands in tier 1
or 2.**

Measured directly — titles carrying both an entry-level signal and an AI signal:

| tier | rows |
|---|---|
| 1 | 15 |
| 2 | 19 |
| 3 | **9** |

34 of 43 are already admitted. Real examples currently sitting in tier 1/2:
*AI Operations Specialist | Housing (New Grads 2025-2026)* (tier 1),
*AI Implementation Specialist* (tier 2), *AI Solutions Associate* (tier 1),
*AI Security Analyst* (tier 1), *AI Specialist, Treasury Finance Operations* (tier 2).
The task's own archetypes: `ai operations` → 5 rows, all tier 1/2. `ai implementation`
→ 13 rows, 12 at tier 1/2. `prompt specialist` and `automation associate` → **zero
rows at any tier.**

**This changes what the task is evidence for.** The target population is not sitting
untouched at tier 3 waiting for the gate to widen. It is largely already inside the
gate — there is just almost none of it: 43 rows in the entire 11,824-row table, across
all tiers. The bottleneck is **sourcing, not gating**. Widening the gate admits ~2,975
rows that are 93% boilerplate matches on employers who happen to mention AI, and
recovers 9 on-target postings.

That is an argument for Phase 3 sourcing and *against* expecting much from task 10's
description-first gate on its own. Task 04's projection should not assume the
widened gate unlocks a hidden corpus.

---

## Definition of done

- The table above is filled in and committed. ✔
- The regex is recorded in a form task 10 can lift directly. ✔
- `N` postings/day stated as a single number with its date range. ✔ — 43/day,
  2026-06-28 … 2026-07-27. Task 04 must still be updated to reference it.
- Nothing was extracted, scored, or re-tuned. ✔ — read-only, `SELECT` only, no LLM
  calls, no config changed.

## Hand-checked sample, pinned

`ORDER BY md5(id) LIMIT 30` over the 2,975, sorted for the record:

```
0c5ebf0334dea42c882d766c  0df7bb0fbfa7688b80116740  12819996bac536fd3a0f4cc3
188fa2be52683cc320e2777d  1f32c3d127f54c1b16ec47a2  389811453abad42dffb15a93
4367b7ebbb21359635acbdba  45a8fa91baaaff4da97ad046  46417cd3d2faf34d70c7f10d
52068d8d9d2f3b68588efea8  5e60281c1ac5583f82bc6c33  662f9fa2c6168d6f8064dd5d
7210482140c01e156e04fe3e  7a0c5456229e8bce70b457dd  85b735de7e7f269f56aa8476
8631bddf8c44195dd14e24cd  86875a366b843985448a61b1  8a6fc9bb45f0bb758862901f
94c2d4f66e34f74f14baa278  97a79c3acff89170906a5412  990eabf191d14d6a5ffb5440
9ffca50848cc188fb64094dd  a33ee658ebc474b5ce13543f  b53c64e1a425afcb219e5776
b940eb67ef9ee9ea07155baf  c89eece93fa54d86109aae6c  ce0f130acde8f76a890ba02e
cf15ad7579d5309f49893e3e  ed7a3b711f8327ac9dee533a  f1b17b727085d4fcffeaaded
```

Per CLAUDE.md: this is an L0 set. Never train on it, never recycle it.

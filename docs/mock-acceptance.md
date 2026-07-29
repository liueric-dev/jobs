# Mock acceptance run — a specification test, 2026-07-29

**What this is:** 55 synthetic postings with a quote-backed answer key, run through
the real pipeline (`relevance` → `extract` → `match` → `score`) in a throwaway
scratch schema, and compared against the key.

**What this is NOT, and the distinction is the whole point:** it is not task 29 and
does not reduce task 29's scope by one posting. Task 29 collects *human* labels;
this collects agreement with a specification an author wrote down. `HANDOFF.md:805-808`
records why that gap matters: *"Fixtures written from a specification test the
specification. All three failure modes task 18 found live were invisible to the four
constructed fixtures, because those encode the shapes the task file describes."*
Everything below inherits that limitation. **No value here reached `eval_labels`,
and none may.**

**Status — updated 2026-07-29, later the same day.** The gate defect (b) found has been
fixed and **(b) alone has been re-measured: recall 48.3% → 89.7%**. Both numbers are
below, with the fix and its limits. Read that arrow as a statement about *this corpus*
and nothing else — see (b).

**(a), (c), (d) and (e) are the original run's numbers and were not re-measured.**
Nothing in the fix touches extraction or scoring — it changes two regex lists in the
`pursuit` relevance gate — and re-running them costs **90 live calls**. (b) was free:
`--dry-run` produces it with no LLM calls at all. Do not read this document as
uniformly refreshed; only §(b) carries a 2026-07-29-post-fix figure.

## Method

| | |
|---|---|
| corpus | `docs/tasks/refactor/mock/mock-postings-v3.json`, 55 postings, sha256 `2624b2a3…` |
| key | `docs/tasks/refactor/mock/mock-postings-v3-answer-key.json` |
| harness | `backend/tools/mock-acceptance.py` |
| loader | `backend/evals/mock_corpus.py` |
| schema | `scratch_c1388ee2`, created and dropped by `evals/scratchdb.py` |
| model | `deepseek-v4-flash@api.deepseek.com`, `FACTS_VERSION` 3, `criteria_version` 2 |
| cost | **90 live calls** — 55 extraction (1 pass each; `mock` is unmeasured in `extraction-policy.json`) + 35 narratives |
| artifact | `backend/data/mock-acceptance-scratch_c1388ee2.json` |

**Ground truth provenance.** Every expected value carries the byte-exact substring of
the posting that determines it; 605/605 quotes verified as literal substrings, by a
validator written by a different agent than the one that wrote the key. 40 of 55
entries were derived here; 15 also carry the pre-existing addendum's verdict, and the
5 places the two disagree are recorded unresolved rather than merged.

**Fields the key deliberately leaves null** are excluded from the denominator rather
than scored as model errors. `years_experience_min` is null on 41 of 55 — most
postings state no minimum — which is why its n is 14 and its rate is not comparable
to the others.

**Two fields were removed from the extraction measurement mid-run and this matters.**
`location_is_nyc` and `location_is_remote` are not `job_facts` columns: `match.py:281`
reads them as `j.location_is_nyc, j.location_is_remote` from the `jobs` table. The
extractor never produces them — the loader does. Scoring the model against them would
have compared the loader's mapping to the key's reading of the same `location` string,
agreed almost always, and inflated the pooled figure with a field the model was never
asked. They are kept as a check on the loader, in a separate denominator.

**Containment.** `public` was never written. Verified after the run: 0 rows at
`platform='mock'`, no `mock_all` profile, no new scratch schemas, and `job_matches` /
`job_scores` content digests byte-identical to the pre-run baseline.

## (a) Extraction accuracy — pooled 86.4% [82.8–89.3], n=440

*Original run. Not re-measured after the gate fix — nothing in it touches extraction.*

| field | k/n | rate | Wilson 95% |
|---|---|---|---|
| `advanced_degree_required` | 54/54 | **100.0%** | [93.4–100.0] |
| `gap_friendly_language` | 54/54 | **100.0%** | [93.4–100.0] |
| `ai_involvement` | 51/52 | **98.1%** | [89.9–99.7] |
| `customer_facing` | 53/54 | 98.1% | [90.2–99.7] |
| `ml_research_required` | 53/54 | 98.1% | [90.2–99.7] |
| `years_experience_min` | 13/14 | 92.9% | [68.5–98.7] |
| `seniority_level` | 41/50 | 82.0% | [69.2–90.2] |
| `role_archetype` | 31/54 | **57.4%** | [44.2–69.7] |
| `remote_policy` | 30/54 | **55.6%** | [42.4–68.0] |

**`ai_involvement` at 98.1% is the result that matters most**, because it is the
cohort's entire targeting mechanism. Read it against task 06's self-consistency floor
of 92.2% on clean sources and 77.8% on `hn_whoishiring`: on constructed prose the
field is not the weak link. That does **not** transfer to real messy sources, and
task 29 remains the measurement that would.

**`remote_policy` at 55.6% is at least partly a definitional disagreement, not an
extraction error.** `extract.REMOTE_POLICY` is
`onsite/hybrid/remote_local/remote_anywhere/unknown` while the corpus's own field is
`onsite/hybrid/remote`, so the key had to choose `remote_local` vs `remote_anywhere`
per posting. Before treating this as a defect, someone should read the disagreements:
a rate this far below the neighbouring fields, on a field this mechanical, is more
likely a vocabulary mismatch than a model failure.

**`role_archetype` at 57.4% over a 26-value vocabulary** is the field whose key
entries are weakest — seniority is usually stated in a sentence, an archetype is an
inference over the whole posting. Treat it as a floor.

## (b) The gate — recall 48.3% → **89.7%**. **This is the finding.**

Measured twice with `tools/mock-acceptance.py --dry-run`: once at the original run, and
again on 2026-07-29 after the fix below. Both runs are free — the gate half of this
harness makes no LLM calls.

|  | before: admitted | before: rejected | after: admitted | after: rejected |
|---|---|---|---|---|
| intended good (29) | 14 | **15** | **26** | 3 |
| intended bad (25) | 10 | 15 | 10 | 15 |

|  | recall | precision |
|---|---|---|
| before | 48.3% [31.4–65.6] | 58.3% [38.8–75.5] |
| after | **89.7% [73.6–96.4]** | 72.2% [56.0–84.2] |

**Read `48.3% → 89.7%` as a statement about this corpus, and never as a claim about the
pipeline's real recall.** These 55 postings were written to contain the failure mode
the number measures. A corpus built around a defect will show a large recovery when the
defect is fixed; that is what a specification test is *for*, and it is not evidence
about postings nobody wrote to order. The same caveat that opens this document applies
with more force to the after-number than it did to the before-number.

What the before-number was, and still is, is the one quantity nothing else in this repo
can measure. Every figure ever produced here is precision over rows the pipeline
already chose to surface; 25 constructed rejects with known verdicts bound recall from
the side the pipeline is blind to. It is exactly task 29's fourth stratum — *"the only
way recall is estimable"* (`29-labelling-session.md:50`) — and it fired task 29's own
gate row: *"Gate-rejected bucket contains good roles → task 10's gate is too tight. Fix
before anything else, because no ranking work recovers a posting that never entered."*

**All 15 rejected good postings were tier 3, and all 15 carry AI vocabulary in the
description but not the title.** They are the ordinary-employer roles the retarget
targets: Permit Intake Assistant, Guest Experience Coordinator, Dispatch Operations
Associate, Claims Intake Associate, Loan Processing Assistant, Paratransit Scheduling
Assistant, Box Office & Patron Services Associate.

**Two distinct causes, which needed different fixes. Both have landed** — `4eefb7e`
(the gate moved out of the migration into `backend/config/pursuit-relevance.json`,
proven a no-op), `e8f3b72` (cause 1), `9dab9e6` (cause 2), plus the profile row
rewritten from the file by `migrate_profiles.py --apply`, without `--bump`.

**1. `ENTRY_LEVEL` was title vocabulary applied to descriptions (14 of 15). FIXED
(`e8f3b72`).** The group is `entry-level, junior, associate, coordinator, assistant,
specialist, analyst, no experience, will train, apprentice, intern` — nouns that appear
in job *titles*. The pursuit gate is conjunctive, requiring one AI term **and** one
entry-level term in the **same field**. A description does not repeat its own title's
seniority noun, so the AI half matched and the entry half did not. `mock_022` says
*"No retail or e-commerce experience required; training provided"* — matching neither
`\yno experience\y` nor `\ywill train\y`.

The fix splits the group in two. `title_include`
(`config/pursuit-relevance.json:14`) keeps the same eleven nouns **byte for byte**;
`description_include` (`:55`) gets those eleven **plus** three phrases, making it a
**strict superset**. That shape is the guarantee, and it is why the change needed no
argument about titles: the title path cannot change, and the description path can only
gain rows. The three phrases, with raw live description match counts 18 / 0 / 11:

```
\yno\y[^.;:]{0,40}\y(?:experience|background|license)\y[^.;:]{0,25}\y(?:required|needed|necessary)\y
\ydoes not require\y[^.;:]{0,40}\y(?:experience|background)\y
\ytraining (?:is |will be )?provided\y
```

**2. `title_exclude` gates both paths, and vetoed a good posting (mock_045). FIXED
(`9dab9e6`), and this document's original framing of it was wrong.** It said
`title_exclude` *"silently overrides"* the description-first gate. The consequence was
real; **"silently" was not**. The behaviour is documented as deliberate in the source
(`relevance.py:227-231`: *"a body full of AI vocabulary does not make an Account
Executive requisition into an entry-level AI job"*) and pinned by a test that asserts
it holds on both tier arms (`test_relevance.py:203-211`). `mock_045`, Customer Success
Associate at a publisher — AI support-assistant used daily, explicitly welcomes career
changers — was excluded by `\ycustomer success\y`.

That distinction decided the fix. **The list was edited; `tier_sql` was not.** Changing
`tier_sql` so `title_exclude` gates only the title path would break the pinned test and
re-admit the 1,906 rows `config/relevance.json:121` counts as being at tier 3 *because*
of `title_exclude` — account executive, recruiter, nurse, controller, VP. So
`\ycustomer success\y` was **narrowed to four manager-and-above forms** rather than
removed (`config/pursuit-relevance.json:101`); removing it outright would have imported
5 *"Manager, Customer Success"* rows, which the seniority block deliberately does not
catch. The four terms admit exactly the 7 target rows and recover `mock_045`.

`\yexecutive assistant\y` was **kept**, on a census rather than a paragraph: all 12
open EA postings at the blocked employers were read, and they ask for 3+, 5+, 5+, 5+,
6+, 6+, 7+, 7+ and 10+ years of executive support (one states no figure). Most are not
NYC. Those are senior administrative roles, not the cohort's.

**The false positives are the mirror image, and the fix did not add one.** The same ten
ids are admitted before and after — `mock_007`, `mock_009`, `mock_010`, `mock_035`,
`mock_036`, `mock_038`, `mock_039`, `mock_049`, `mock_050`, `mock_054`: `Nexora AI`,
`Aurelian Intelligence`, `Vireo Cognitive Systems` — AI-branded employers admitted on
company-adjacent vocabulary — plus two gig postings and two genuine technical-bar
roles. Precision rises from 58.3% to 72.2% purely because the denominator gained 12
true positives; **the recovery cost no precision on this corpus**. What that sentence
is worth is the subject of the next one.

### Recall stops at 89.7% on purpose

The three surviving false negatives are `mock_016`, `mock_017`, `mock_018`. They are
reachable **only** through four phrase families that were measured and **rejected**.
On this corpus all four are **free** — zero added false positives. Compiled through
`relevance.tier_sql` against the live table (13,447 open rows) they admit:

| family | live rows added |
|---|---|
| "we provide / offer … training" | +17 |
| "we (will) train" | +5 |
| "preferred but not required" | +5 |
| "experience … preferred / is a plus" | **+123** |

**Every one of them is a senior engineering requisition at an AI employer** —
`Software Engineer, RL Training Infra | OpenAI`, `Full-Stack Software Engineer,
Reinforcement Learning | Anthropic`. `\ywe train\y` matched OpenAI's *"we train
models"*: a false friend that **cannot exist on a synthetic corpus**, because no author
writing a mock rejection would think to write it.

They look free here because every intended-bad mock posting carrying that phrasing has
no AI vocabulary at all, so the conjunction stops it regardless of what the entry-level
list says. **This is this document's own rule firing on itself.** A fixture written from
a specification tests the specification: a synthetic corpus can *bound recall* — that
is (b)'s whole value, and nothing else here does it — but it **cannot price precision**,
because its negatives were written by whoever wrote its positives. Had the four families
been adopted on this corpus's say-so, the mock number would have gone to 100% and the
live gate would have taken +150 senior engineering rows.

### What the recovery is worth in production

**11 postings, on a pool of 869. +1.3%.** (Live figures and their hand-check are in
`docs/pursuit-description-gate.md`.) That does **not** meaningfully change what task
29's labellers will see, and it moves GATE 2's ">= 200/day" question **not at all**.

Doing it first was still right: the defect was real, the fix was cheap, and a labelling
session run through a knowingly-broken gate is wasted work. But nobody should read a
recovery into `48.3% → 89.7%` that it does not deliver. The mock corpus moved 41
points; the live pool moved 1.3%.

## (c) `score_job()` separation — AP 91.9%, precision@20 90.0%, chance 53.7%

*Original run. Not re-measured after the gate fix — the gate decides which postings
reach `score_job()`, not how it scores them, and `score_job()` is pure.*

54/54 scored, no drops. Tie bounds 90.3%–93.2% (optimistic/pessimistic tie-breaks).
Tie structure: 24 distinct scores over 54, largest block 11, `p_tie` 0.069.

Chance level is the positive rate, 53.7% — not 50%, and not 0. **The weights are
doing real work on postings that reach them.** Combined with (b): the ranking is good
and the gate in front of it is the constraint. That is the same conclusion task 10
reached from the other direction, now with a recall number attached.

## (d) The branding traps — 5 of 5 correct

*Original run. Not re-measured after the gate fix.*

HANDOFF's open question: task 13's four floor misses carry `ai_involvement='none'` at
AI-branded employers, and *"they may be correct rejections rather than weight errors,
and task 29's labels are the only thing that can settle it."*

| id | employer | model | key | tier | match |
|---|---|---|---|---|---|
| mock_007 | Nexora AI | `none` | `none` | 1 | 0 |
| mock_035 | Aurelian Intelligence | `none` | `none` | 1 | 0 |
| mock_036 | Vireo Cognitive Systems | `none` | `none` | 1 | 26 |
| mock_048 | Solvane AI | `none` | `none` | 3 | 17 |
| mock_053 | Fenwick AI Solutions | `none` | `none` | 3 | 0 |

**The extractor is not fooled by the company name, and the weights correctly place all
five below the floor of 40.** For constructed branding traps the answer is: correct
rejections, not weight errors.

**What this does not license.** These are constructed instances of a pattern someone
already suspected — the corpus was built to contain them. Real branding traps were not
sampled, and task 13's four actual floor misses are still unlabelled. This is evidence
that the mechanism works when the trap is unambiguous; it is not evidence that task
13's specific four are correct. **Do not re-tune weights on it, and do not treat task
13's DoD gap as resolved.**

## (e) Confound check — no visible effect

*Original run. Not re-measured after the gate fix — it is a decomposition of (a).*

| author | k/n | rate | Wilson 95% | postings |
|---|---|---|---|---|
| claude | 142/163 | 87.1% | [81.1–91.4] | 20 |
| glm | 136/155 | 87.7% | [81.6–92.0] | 19 |
| gpt | 34/40 | 85.0% | [70.9–92.9] | 5 |
| human | 68/82 | **82.9%** | [73.4–89.5] | 10 |

Human-written postings score 4.2 points below model-written ones, with overlapping
intervals at n=10 postings. **No confound visible at this n** — and n=10 cannot resolve
an effect of that size, so this rules nothing out. If the corpus is ever extended, more
human-written postings are the highest-value addition.

## What this cannot settle

- **It is a specification test.** It measures agreement with an author's intent, on
  postings written to contain the failure modes being looked for.
- **No Axis B.** No human preference was measured. Task 29 is untouched.
- **40 of 55 key entries were derived here**, not authored independently. The quotes
  make them auditable; they do not make them independent.
- **`role_archetype` and `remote_policy`** rates are confounded with key quality and
  vocabulary mismatch respectively. Read the disagreements before acting.
- **Synthetic prose is clean prose.** Task 06's reconciliation predicts extraction
  degrades on messy real sources; nothing here tests that.
- **A synthetic corpus bounds recall; it cannot price precision.** Its negatives were
  written by whoever wrote its positives, so a term that is "free" here may not be free
  anywhere else — see the four rejected phrase families in (b), free on all 55 postings
  and worth +150 senior engineering rows live.
- **89.7% is not the pipeline's recall.** It is agreement with a specification, on a
  corpus built to contain the defect that was just fixed.

## What to do next

1. ~~**Fix the gate before anything else.**~~ **Done, 2026-07-29** — `4eefb7e`,
   `e8f3b72`, `9dab9e6`. Both changes shipped: a description-phrased entry-level
   vocabulary (as a strict superset of the title group), and a review of
   `title_exclude` against the cohort's actual target roles, which narrowed one term
   and kept the rest on measurements recorded in
   `config/pursuit-relevance.json:_title_exclude_note`.
2. ~~**Re-run this after that change.**~~ **Done for (b) only** — recall 48.3% → 89.7%,
   at no cost. (a), (c), (d) and (e) were not re-run; they would cost 90 calls and the
   change cannot move them.
3. **Do not adopt the four rejected phrase families on this corpus's evidence.** They
   score free here and cost on the order of +136 live rows of senior engineering
   requisitions. The
   three remaining false negatives (`mock_016`, `mock_017`, `mock_018`) stay
   unrecovered on purpose.
4. **Task 29 is still the critical path.** Nothing here substitutes for it, and the
   fix changes what its labellers will see by **+1.3%** — 11 rows on 869. It does not
   move GATE 2.

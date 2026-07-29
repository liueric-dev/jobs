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

## (b) The gate — recall 48.3% [31.4–65.6]. **This is the finding.**

|  | admitted | rejected |
|---|---|---|
| intended good | 14 | **15** |
| intended bad | 10 | 15 |

**The relevance gate throws away more than half of the postings this cohort exists to
find.** Precision 58.3% [38.8–75.5].

This is the one quantity nothing else in this repo can measure. Every figure ever
produced here is precision over rows the pipeline already chose to surface; 25
constructed rejects with known verdicts bound recall from the side the pipeline is
blind to. It is exactly task 29's fourth stratum — *"the only way recall is
estimable"* (`29-labelling-session.md:50`) — and it fires task 29's own gate row:
*"Gate-rejected bucket contains good roles → task 10's gate is too tight. Fix before
anything else, because no ranking work recovers a posting that never entered."*

**All 15 rejected good postings are tier 3, and all 15 carry AI vocabulary in the
description but not the title.** They are the ordinary-employer roles the retarget
targets: Permit Intake Assistant, Guest Experience Coordinator, Dispatch Operations
Associate, Claims Intake Associate, Loan Processing Assistant, Paratransit Scheduling
Assistant, Box Office & Patron Services Associate.

**Two distinct causes, and they need different fixes.**

**1. `ENTRY_LEVEL` is title vocabulary applied to descriptions (14 of 15).** The group
is `entry-level, junior, associate, coordinator, assistant, specialist, analyst, no
experience, will train, apprentice, intern` — nouns that appear in job *titles*. The
pursuit gate is conjunctive, requiring one AI term **and** one entry-level term in the
**same field** (`migrate_pursuit_profile.py:216,229`). A description does not repeat
its own title's seniority noun, so the AI half matches and the entry half does not.
`mock_022` says *"No retail or e-commerce experience required; training provided"* —
matching neither `\yno experience\y` nor `\ywill train\y`.

Task 10 built a description-first gate and gave it a vocabulary that only works on
titles. The fix is a separate entry-level vocabulary for description text, phrased the
way postings actually phrase it.

**2. `title_exclude` silently overrides the description-first gate (mock_045).**
`relevance.py:232-234` applies `title_exclude` to **both** paths, so a title exclusion
vetoes a posting whose description passes both groups. `mock_045`, Customer Success
Associate at a publisher — AI support-assistant used daily, explicitly welcomes career
changers — is excluded by `\ycustomer success\y`.

`pursuit`'s `title_exclude` still carries `customer success`, `executive assistant`,
`office manager`, `facilities`, `warehouse`, `driver`, inherited from the
software-engineer profile where excluding them was correct. For a cohort targeting
AI-adjacent ops and support work at ordinary NYC employers, several of those are
exclusions on the target population itself.

**The false positives are the mirror image**: `Nexora AI`, `Aurelian Intelligence`,
`Vireo Cognitive Systems` — AI-branded employers admitted on company-adjacent
vocabulary — plus two gig postings and two genuine technical-bar roles.

## (c) `score_job()` separation — AP 91.9%, precision@20 90.0%, chance 53.7%

54/54 scored, no drops. Tie bounds 90.3%–93.2% (optimistic/pessimistic tie-breaks).
Tie structure: 24 distinct scores over 54, largest block 11, `p_tie` 0.069.

Chance level is the positive rate, 53.7% — not 50%, and not 0. **The weights are
doing real work on postings that reach them.** Combined with (b): the ranking is good
and the gate in front of it is the constraint. That is the same conclusion task 10
reached from the other direction, now with a recall number attached.

## (d) The branding traps — 5 of 5 correct

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

## What to do next

1. **Fix the gate before anything else.** (b) is the largest measured loss in the
   pipeline and no downstream work recovers a posting that never entered. Two separate
   changes: a description-phrased entry-level vocabulary, and a review of
   `title_exclude` against the cohort's actual target roles.
2. **Re-run this after that change.** It is 90 calls and the gate half needs none —
   `--dry-run` produces (b) for free.
3. **Task 29 is still the critical path.** Nothing here substitutes for it.

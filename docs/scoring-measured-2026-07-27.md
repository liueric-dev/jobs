---
kind: record
written: 2026-07-27
generator: none
---

# The scoring system, measured — 2026-07-27

> **Frozen at its date. Nobody keeps this current, and nobody should.** Every figure below
> was measured against the live database on **2026-07-27**, over **11,517 job rows** and
> **2 active profiles** (`tech` and `frontend`). A half-updated measurement is worse than an
> honestly stale one, because you cannot tell which is current
> ([`DOCS-POLICY.md`](DOCS-POLICY.md) rule 1).

**Split out of [`scoring.md`](scoring.md) on 2026-08-01 by task 43, executing `DEC-70`.**
That file opened *"Every figure below was measured against the live database on
2026-07-27"* and then served as the scoring **contract** the whole repo cites. Under rule 1
it cannot be both: a contract may not be stale, a measurement is frozen at its date. The
contract half kept the path, because every live citation of it means the contract. This is
the other half, moved verbatim.

**What it is not.** It is not the current state of the database, and no figure here should
be quoted forward without re-deriving it. **The system it describes has since been
retargeted** — `pursuit` is the only active profile, `tech` and `frontend` are inactive but
intact, and `FACTS_VERSION` has moved from 2 to 3. Both profiles below are inactive today.

**What it is for.** Two things the contract cannot carry. It is the worked example behind
every claim in [`scoring.md`](scoring.md) about scales not being comparable — the numbers
are what make that argument concrete rather than assertive. And it is the before/after
evidence for the `staff` defect, which is the only measured demotion in the run.

---

## The live funnel

| # | Stage | Candidates in | Candidates out | Cost per candidate | Cutoff |
|---|---|---|---|---|---|
| 1 | **Eligibility** `relevance.py` | 11,332 open | 5,158 tier ≤ 2 | free (SQL, in the same query) | `max_tier_to_score = 2` |
| 2 | **Extract** `extract.py` | 5,158 eligible | 5,288 `job_facts` (7 tombstoned) | ~$0.000385, 9.3s | `FACTS_VERSION = 2` — never re-run |
| 3 | **Match** `match.py` | 5,281 × 2 profiles = 10,562 | 3,372 `job_matches` | ~40 integer ops, no network | `MATCH_FLOOR = 40` |
| 4 | **Narrative** `score.py` | top of each profile's ranking | 1,254 `job_scores` (57 tombstoned) | ~$0.000288, 6.5s | `daily_narrative_budget = 20` |

`job_facts` (5,288) slightly exceeds current eligibility (5,158) because facts
are never deleted when config later narrows — that is the gap `load_facts`
closes by re-applying the union at read time.

### Tier distribution

The `max_tier_to_score = 2` cutoff removed 6,174 of 11,332 open postings —
**55% of the corpus never reached a model.**

```
tier 1  2,866  (25.3%)  title matches AND location acceptable   SCORED
tier 2  2,292  (20.2%)  title matches, location unknown         SCORED
tier 3  6,174  (54.5%)  everything else                         SKIPPED
```

### Tombstones

7 of 5,288 fact rows and 57 of 1,254 score rows were tombstones — a model that answered
unusably, never retried. The three-way split that produces them is contract and is in
[`scoring.md`](scoring.md) § *Degradation*.

---

## The two scales, and why a 70 is not a 70

This is the measured half of [`scoring.md`](scoring.md) § *Is a 70 for user A comparable to
a 70 for user B?* The answer is no, and the mechanism — every term read from that profile's
own `criteria_json` — is in the contract. These are the numbers it produced.

| profile | **theoretical max** | observed max | stored matches | min | median | mean | max |
|---|---|---|---:|---:|---:|---:|---:|
| `tech` | **121 → clamps to 100** | 100 (16 rows) | 3,077 | 40 | 62 | 62.5 | 100 |
| `frontend` | **84** | 83 | 295 | 40 | 54 | 55.5 | 83 |

Three consequences, all live on the day this was taken:

1. **`frontend` could never score above 84.** A `frontend` 80 was a near-perfect match; a
   `tech` 80 was its 90th percentile.
2. **`tech` saturated.** Its terms summed to 121, so `_clamp` discarded up to 21 points and
   **16 rows sat at exactly 100 with no way to distinguish them.**
3. **`MATCH_FLOOR` is a single global number applied to both scales** — 40% of `tech`'s
   usable range and 48% of `frontend`'s. It is part of why `frontend` had 295 stored matches
   against `tech`'s 3,077, a **10× difference across the same 5,288 extracted postings.**

The two scales drawn against the one cutoff they share:

```
points    0         20        40        60        80        100       120
          ├─────────┼─────────┼─────────┼─────────┼─────────┼─────────┤
                              ┊
        MATCH_FLOOR = 40 ─────┤  one global number, both profiles
                              ┊
tech      ░░░░░░░░░░░░░░░░░░░░███████████████████████████████▒▒▒▒▒▒▒▒▒▒
          never stored        stored · 3,077 rows · med 62   ↑ clamp discards
                              ┊                                21 points
                              ┊
frontend  ░░░░░░░░░░░░░░░░░░░░██████████████████████┤ 84
          never stored        stored · 295 rows      ↑ unreachable ceiling
                              ┊   med 54
                              ┊
                    40 = 40% of tech's usable range
                       = 48% of frontend's
```

### `fit_score` as observed

**min 0, max 95, mean 48.2 over 1,200 non-null rows.** The column is nominally 0–100 and
**unvalidated on write** (`score.py:361`; `has_fields` checks presence only,
`llm.py:262-263`), so a model returning `150` would be stored as 150 and a model returning
`"high"` would raise a psycopg error inside the worker thread. Neither had occurred — which
is a property of this sample, not a guarantee, and is why the contract records the hazard
rather than this range.

---

## The `staff` fix, measured — 2026-07-27

The defect and its general form are contract ([`scoring.md`](scoring.md) § *Seniority*):
**any seniority level a profile does not name is silently free** unless `penalty_per_level`
is set. `staff` was the one level of the nine named in neither `target`, `tolerate` nor
`hard_exclude` for the `tech` profile, so it fell to the distance branch — where
`penalty_per_level` was *also* absent and `.get(..., 0)` made the penalty exactly zero.
`add()` skips a falsy delta, so the posting scored as on-target **and recorded no reason for
it.**

Measured against otherwise-identical facts:

```
                 before          after
  new_grad         21              21
  junior           49              49
  mid  (target)    61              61
  senior           56              56
  staff          → 61  ← free    → 41    seniority:staff  -20
  principal        26              26
```

A Staff posting scored identically to a Mid one while Senior — a *closer* level — cost 5
points. Non-monotonic, and contradicting `persona.json:19` (*"not senior/staff/principal"*).

**783 of 5,146 eligible postings (15.2%) were `staff`; 452 of them were in the ranking, and
250 dropped below `MATCH_FLOOR` and were deleted** when the fix was applied. **The top 20 did
not change** — the effect was entirely in the middle of the list.

That last line is the reason this measurement is worth keeping. A change that deletes 250
rows and moves the top of the list not at all is the shape that looks like nothing happened
from the only view a user has.

---

## `job_events`, and the learned-ranker probe

**`job_events` held 0 rows.** The writer landed 2026-07-26 and nothing had driven traffic
through it. Engagement labels cannot be collected retroactively, so every day without a
frontend was training data permanently lost.

`tools/learned-ranker-probe.py` measured a learned ranker at **12.7/20 precision@20 against
the hand-tuned rules' 8.0/20**, using *exactly* the features that already exist — the
measured business case for replacing the weighting function, not the feature set.

> **Read that pair with the caveat its owner attaches to it.**
> [`archive/handoff-match-quality.md`](archive/handoff-match-quality.md) owns the 12.7/20 and
> relabels it: it is **imitation fidelity against a non-target persona**, not a quality
> score. It was measured for profile `tech` — the repo author's own software-engineer search
> — and does not transfer to the Pursuit cohort. `archive/README.md` says so in as many
> words: *"Do not quote them forward."*

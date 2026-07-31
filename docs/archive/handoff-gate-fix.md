# The gate fix LANDED, and what it did not buy

> **Archived from `docs/tasks/refactor/HANDOFF.md` on 2026-07-31**, when that file was split.
>
> **What it is:** Recorded 2026-07-29. Step 0's relevance-gate fix: mock gate recall 48.3% -> 89.7%, live tier <=2 869 -> 880. Its own first line says "What follows is the record, not a plan." The four forbidden phrase families it names are now guarded by a test, not by this prose.
>
> Moved, not deleted. `git log --follow` on this path reaches the original text, and a stub
> and link remain where this section was.

---

## READ THIS FIRST: the gate fix LANDED, and what it did not buy

**Done 2026-07-29, four commits: `4eefb7e`, `e8f3b72`, `9dab9e6`, plus a database write.**
Step 0 is closed. What follows is the record, not a plan.

| metric | before | after |
|---|---|---|
| mock gate recall | 14/29 = 48.3% [31.4–65.6] | **26/29 = 89.7% [73.6–96.4]** |
| mock gate precision | 58.3% | **72.2%** |
| mock false positives | 10 ids | **the same 10 ids, unchanged** |
| live tier ≤2, open | 869 (t1 450 / t2 419) | **880 (t1 456 / t2 424)** |
| `extract.remaining` | 2 | **13** |
| suite | 1030 | **1058** |

**Say it the long way wherever it is quoted: "48.3% → 89.7% *on the mock corpus*."** That
corpus was built to contain the failure mode it measures. It is not a claim about the
pipeline's recall on real postings, and nothing here reduces task 29 by one posting.

**What the defect was.** The gate is conjunctive — one AI term **and** one entry-level term
in the *same field* (`migrate_pursuit_profile.py:216,229`). Task 10 built a
description-first gate and handed it a **title** vocabulary: `associate, coordinator,
assistant, specialist, analyst`. A description does not restate its own title's seniority
noun, so the AI half matched and the entry half did not. 14 of the 15 lost postings failed
on that one group.

**What was done.** The gate moved out of a dict literal inside a migration that refuses to
run and into `backend/config/pursuit-relevance.json` (a no-op, proven by byte-identical
compiled SQL). `description_include`'s entry group became a **strict superset** of the
title group — the same eleven nouns byte-for-byte, plus three phrases — so the title path
*cannot* change and the description path *can only gain*. `\ycustomer success\y` was
narrowed to four manager-and-above terms rather than removed.

### The four phrase families that must stay out, and why the harness will tell you otherwise

Compiled through `relevance.tier_sql` against 13,447 live open rows:

| family | live rows admitted | mock cost |
|---|---:|---|
| `we provide/offer … training` | **+17** | zero |
| `we (will) train` | **+5** | zero |
| `preferred but not required` | **+5** | zero |
| `experience … preferred / is a plus` | **+123** | zero |

They admit `Software Engineer, RL Training Infra | OpenAI`, `Full-Stack Software Engineer,
Reinforcement Learning | Anthropic`, `Product Manager, Gen AI | Scale AI`. **`\ywe train\y`
matched OpenAI's *"we train models"*.**

**On the mock corpus all four measure as FREE**, because every intended-bad mock posting
carrying that phrasing has no AI vocabulary at all, so the conjunction rejects it on the
other half. That is a property of a corpus written to a specification. Adding them takes
mock recall to 100% at **~136 live junk rows**. Refused.
`backend/tests/test_pursuit_gate.py` carries a **sentinel** asserting their absence with
these counts in its docstring. **If the harness tells you they are free, that is the
harness's limitation, not a discovery.**

**The general rule this earned:** a synthetic corpus can bound *recall* but cannot price
*precision*, because its negatives were written by whoever wrote its positives.

### Read the size of it honestly

**+11 postings on an 869-row pool is +1.3%.** It does not meaningfully change what task
29's labellers see and it moves GATE 2's ≥200/day question **not at all**. Doing it first
was still right — the defect was real, the fix was cheap, and a labelling session run
through a knowingly-broken gate is wasted — but do not read a recovery into it that it
does not deliver.

The 11 new rows were hand-checked as a **census, not a sample**: ~7 on-target, 1 clear
false positive (`Research Engineer, Interpretability | Anthropic`, which really does say
"no research experience is required"), 3 ambiguous. **~64% strict against the incumbent
gate's 10.0%** (`migrate_pursuit_profile.py:166-167`) — the rows added are better than the
rows already in. The extraction backlog is 11 calls, ~$0.004, drained on the first nightly.

**Three mock false negatives remain — mock_016, mock_017, mock_018 — and they are
unreachable on purpose.** Only the rejected families recover them.

### What step 0 got wrong about the code, found by verifying it before implementing

- **`AI_VOCAB` had exactly ONE copy**, not two. Step 0 required a test that "the two copies
  are equal", which could not fail. It is now meaningful *because* the JSON move created
  two literals — the test is kept and its docstring says so.
- **`migrate_pursuit_profile.py` refuses to run before it checks `--apply`**, so even a dry
  run exits 1. It was already retired as a write path; that is what made the JSON move
  coherent. It still self-consumes `COHORT_RELEVANCE` at four sites, so the symbol was kept
  as a loader, not deleted.
- **`relevance.load()` merges over `DISABLED`, not over `config/relevance.json`**
  (`relevance.py:88-90`). **A per-profile gate must be complete, not a patch** — an omitted
  key goes permissive, it does not inherit.
- **`profiles.upsert` stores NULL for a falsy `relevance_cfg`** (`profiles.py:207`). An
  empty dict silently reverts `pursuit` to the shared author gate. The post-write md5 is
  what catches it.
- **`--force-placeholders` is not a flag on `migrate_profiles.py`** — it is on
  `migrate_pursuit_profile.py:462-465`. Step 0 warned about the wrong script.
- **The module docstring at `:71-78` pointed at nothing missing.** `migrate_profiles.py`,
  `config/pursuit-persona.json` and `config/pursuit-criteria.json` all exist, as do all six
  flags it names.
- Paths: **`relevance.py` is `backend/relevance.py`, not under `lib/`**; there is **no
  repo-root `config/`**; `extract._eligible_sql` is `:541-579`, not `:397`; tier assignment
  is `relevance.py:297-299` and `tier <= max_tier` is `:331`.

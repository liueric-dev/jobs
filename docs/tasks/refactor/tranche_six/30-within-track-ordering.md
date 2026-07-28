# 30 — Within-track ordering and display

**Status:** todo. **Depends on:** 11, 13, 29. **Blocks:** 32.

Decide what a Builder actually sees, and prove the display makes only claims the data
supports.

## The claim ladder

A ranking system can make three levels of claim, and they cost very different amounts
to earn.

| claim | UI says | requires | earnable here? |
|---|---|---|---|
| **ordinal** | a ranked list, no numbers | order correlates with preference | **yes** — precision@20 measures it |
| **categorical** | "strong match / worth a look / stretch" | validated thresholds | **yes**, with task 29's labels |
| **cardinal** | "87% match" | the number means something on a fixed scale | **no, and probably never** |

Cardinal is unearnable for a structural reason, not a temporary one. Calibrating a
score into a probability requires an outcome to calibrate against. There is no ATS
callback, no institutional placement data, and self-reported status decays. `applied`
is the terminal signal and it measures *intent*, not result. That ceiling does not move
with better modelling.

`score_job()` is `base 35 + Σ deltas`, clamped — an ordinal construction. A
`match_score` of 70 is not 70% of anything.

## The experiment that settles it

Run against task 29's labels before building any display.

1. Bucket the labelled postings by `match_score` into 3–4 bands.
2. Test whether score differences **within** a band predict anything — does a posting
   at 88 beat one at 81 in Builder judgement, more often than chance?
3. Report between-band and within-band separately.

If within-band resolution is at chance, the score carries exactly as much information
as its bucket, and showing the digits is a false-precision claim. My expectation is
real between-band signal and no within-band signal, but the point is to measure rather
than assume.

Supporting evidence that resolution is low: `HANDOFF-match-quality.md` §4.2 records 59
postings sharing `fit_score` 85 — 6.4% of the corpus on one integer. That is the
signature of a pointwise judge with perhaps five distinguishable states expressing them
through a 100-point scale.

## Separate the two jobs `fit_score` does

It is currently both a **training label** and a **displayed number**. Those need
different validation and it can pass one and fail the other.

As an ordinal training signal on 917 rows it is probably fine — the probe got 12.7/20
out of it. As a displayed number it must survive the within-band test. Do not let a
pass on the first justify the second.

## Display

**Group by `role_track`.** With no single target role, the product is "here is the
space of roles reachable with these skills, organised so you can work out which ones
you want." Tracks are the map. A Builder early in their journey browses several; one
further along narrows.

**Buckets within track**, three or four, with thresholds set from task 29's labels
rather than round numbers.

**Precision@20 measured within track**, not globally. Against an invented cohort-wide
target it means nothing; within a track there genuinely is a target and the metric
recovers its meaning.

**Promote `gap_bridging_angle` to the primary narrative output.** This is the change
that matters most for the population. "You managed a restaurant for nine years; here
is how that connects to this operations role, and here is the gap" is *the product*
for someone who does not yet know what they are looking for — and it is the one thing
in the pipeline an LLM is unambiguously good at.

It also resolves the career-changer problem task 13 deliberately refused to encode as
a weight. Prior-domain seniority is a narrative fact, not a scalar. This is where it
lives.

**Show `risk_factors` too.** Honest about stretch roles beats flattering about them,
particularly for people without industry pattern-matching to calibrate against.

## Ordering within a bucket

Once buckets carry the claim, within-bucket order matters less. Sort by freshness —
`posting_age_days` from task 11 — rather than by score decimals the data does not
support. A fresh posting in the same bucket is a better bet than a stale one, and
entry-level roles fill fast.

## Definition of done

- The within-band experiment is run against task 29's labels and its result recorded.
- A written decision on buckets vs score, justified by that result.
- Bucket thresholds derived from labels, not chosen.
- List groups by `role_track`.
- `gap_bridging_angle` is the primary narrative element; `risk_factors` visible.
- Within-bucket ordering by freshness.
- Precision@20 reported per track, with a paired bootstrap against the pre-refactor
  baseline.
- No 0–100 number appears in the UI unless the experiment justified it.

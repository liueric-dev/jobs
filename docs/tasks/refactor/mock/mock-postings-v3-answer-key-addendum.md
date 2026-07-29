# Answer key addendum — mock_041 through mock_055

For entries 001–040, see mock-postings-v2-answer-key.md. This covers only the new
additions from GLM's second batch.

## What was dropped

GLM regenerated five postings identical in every field except job_id to ones already
merged in from its first batch. Not reused, not resampled — word-for-word duplicates.
Dropped entirely rather than renumbered, since re-adding them would inflate the
"good" count without adding any new signal:

- Guest Experience Coordinator / Marquee Hospitality Group (duplicate of mock_016)
- Dispatch Operations Associate / Bayline Logistics (duplicate of mock_017)
- Listings Coordinator / Cornerstone Property Group (duplicate of mock_018)
- Quality Assurance Coordinator / Atlas Precision Manufacturing (duplicate of mock_019)
- Onboarding Specialist / Cobalt AI (duplicate of the posting already renamed to
  Cindervale AI at mock_020 — GLM regenerated the exact same real-company collision)

## What was renamed

- "Vexor AI" → "Solvane AI" (mock_048). Vexor is a real AI security/surveillance
  company — direct name collision.
- "Helix AI Solutions" → "Fenwick AI Solutions" (mock_053). Not an exact match to one
  company, but "Helix" + AI is an extremely crowded namespace (HelixAI, Helix
  Technologies, Helix Labs, BMC Helix all currently exist) — close enough to rename
  rather than risk it.
- "City of Bridgeport" → "City of Brennan Falls" (mock_051). Bridgeport, CT is a real
  municipality; swapped for a fictional one for consistency with the "never a real
  entity" rule.

## New entries

| id | intended category | note |
|---|---|---|
| mock_041 | good | Harborlight Academy — education, AI tutoring assistant genuinely used, no experience required |
| mock_042 | good — flag for your judgment | Marlowe Legal Aid Society — genuinely AI-adjacent, but requires "bachelor's degree or equivalent experience." Your cohort's floor was explicitly *no degree required*; "or equivalent experience" softens it but doesn't fully clear that bar. Worth deciding deliberately rather than by default. |
| mock_043 | good | Open Doors Community Services — nonprofit, AI intake assistant, no experience required |
| mock_044 | good | Pulsewave Media — AI auto-tagging tool, no media experience required |
| mock_045 | good | Ledgerline Publishing — remote, explicitly welcomes career changers |
| mock_046 | bad — clean reject | Greenwood Community Library — no AI mention anywhere |
| mock_047 | bad — seniority | Meridian Hotels International — genuine AI pricing tool, but Director + 7 yrs + MBA |
| mock_048 | bad — branding trap, and also out of geographic scope | Solvane AI (renamed) — no AI tool use described, 2-3 yrs required, *and* onsite in San Francisco, not NYC/remote. Two independent failure reasons, not one. |
| mock_049 | bad — not a real employer | Upwork — 1099 gig posting |
| mock_050 | bad — technical bar | Northwind Analytics — "entry-level" title, but BS in CS + PyTorch/TensorFlow + SQL required |
| mock_051 | bad — clean reject | City of Brennan Falls (renamed) — no AI mention |
| mock_052 | bad — seniority | Sterling Bay Insurance — genuine AI risk tool, but Head of Underwriting, 10+ yrs, CPCU |
| mock_053 | bad — branding trap, and also out of geographic scope | Fenwick AI Solutions (renamed) — no AI tool use described, 4+ yrs required, *and* onsite in Boston |
| mock_054 | bad — technical bar, extreme case | Lyric Labs — "intern" title, but requires active PhD enrollment and conference publications. Worth keeping as the far end of this failure mode — a categorical exclusion, not just a skills gap. |
| mock_055 | bad — not a real employer | Fiverr — per-task freelance gig |

## Running total (55 postings)

- Good: 30 (25 from before + 5 new)
- Bad: 25 (15 from before + 10 new)
- Ratio: ~55/45, close to even

Failure-mode coverage is now solid across the board — clean reject, seniority,
branding trap, not-a-real-employer, and technical-bar-mismatch each have 3-5
instances. The one genuinely new thing this batch added structurally is the
compound-failure case (branding trap *and* out-of-scope location in the same
posting) — worth keeping at least one of those, since real postings won't
usually fail for a single tidy reason.

---
kind: record
written: 2026-07-31
generator: none
---

# How these sessions ran it, and what worked

> **Archived from `docs/tasks/refactor/HANDOFF.md` on 2026-07-31**, when that file was split.
>
> **What it is:** Method notes from the same sessions. The durable half is promoted to HANDOFF.md § How this run works.
>
> Moved, not deleted. `git log --follow` on this path reaches the original text, and a stub
> and link remain where this section was.

---

## How these sessions ran it, and what worked

**Task 11's session: three subagents in two rounds.** Round 1 ran the corpus-evidence
agent and the scoring agent in parallel — disjoint files, neither blocking the other.
Round 2 ran the extraction agent, which needed round 1's derived vocabulary. The
orchestrator took the baseline, verified every claim, made the one judgement call it would
not delegate (pricing 14 new archetypes for the author's profile), and committed.

**The first session: six subagents in parallel, orchestrator verifying and committing.**
Nothing was committed by a subagent in either session. Every task was checked against the
code and the database before its commit. Mechanics worth keeping:

- **Every agent gets an explicit file-ownership list.** Five ran concurrently with one
  genuine collision all session (`record_cassettes.py`, below).
- **`run-daily.py`'s `STEPS` is orchestrator-only.** It is the one file every ingest task
  wants to edit. Agents report the line they want; the orchestrator wires it.
- **Take the baseline before the first agent starts.** Tier-count-by-platform for every
  active profile, and the test count. Task 10's "the author's profile is unaffected" claim
  was only checkable because that snapshot existed — and by the time it was checked, a
  concurrent agent had added 1,030 rows on a new platform, which would otherwise have
  looked like a regression.
- **The handoff is rolling, not terminal.** This file, `DECISIONS.md`, `CLAUDE_UPDATES.md`
  and `README.md` were updated in the same turn as every commit. The previous handoff was
  written once at the end, from a context already spent, which is why it read as recall
  rather than record.

**Five of six agents in the first session, and three of three in task 11's, completed
without sending a report at all.** They go idle silently. Do not wait for a summary; check
the artifacts. That is the norm, not the exception. **Sixteen of sixteen across the run
now**, all five mock-acceptance agents included — and two of them sent idle
notifications *twice*, for work already verified and committed, while a sixth agent
(a planning one) went idle twice and never reported at all, even when asked directly.
Treat the notification as "go look", including the second time, and do not spend turns
chasing a report that may not exist. **Budget for the artifacts being the only output
you will get.**

**Verification that actually caught things in task 11, in order of value.** Reading the
diff caught the most; the suite caught the least. Worth copying:

1. **Re-run the agent's own tool and grep for the prose's numbers.** Caught the
   unreproducible figures.
2. **Recompute a headline number independently.** Surfaced the 54-vs-55 distinction.
3. **Prove an equivalence claim by exhaustion, not by reading.** The rewritten tombstone
   guard was checked over a 192-case cross product of the four signals it reads.
4. **AST-check the invariant.** `score_job()`'s purity is a CLAUDE.md rule; walking the
   function for I/O calls and imports is three lines and does not rely on a promise.
5. **`match.py --dry-run` against the live database.** The claim "this change is inert in
   production" is worth exactly nothing unverified; it reports 0 matched or it does not.

**The one real collision:** `backend/evals/record_cassettes.py` accumulated two agents'
changes at once. Task 14's commit deliberately excluded it rather than ship task 17's
half-finished work under 14's number, and 17's commit carried both. The general fix is the
one `STEPS` already has — shared files get a single owner, named in advance.

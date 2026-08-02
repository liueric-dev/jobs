---
kind: contract
written: 2026-08-01
generator: none
---

# Working method

**How work is verified in this repo, and the specific ways verification has failed here.**

**Promoted 2026-08-01 from `docs/tasks/refactor/HANDOFF.md` § *How this run works*, where
it sat 1,479 lines into a rolling handoff about a labelling session.**
[`MEASUREMENT-TRAPS.md`](MEASUREMENT-TRAPS.md) is the precedent and the model — same move,
same reason: none of this is about Pursuit, Builders, job postings, one persona or one
model, which is [`DOCS-POLICY.md`](DOCS-POLICY.md) rule 5's test. Every sentence below
survives the product changing. A stub and a link remain where the section was, so an
inbound citation still lands.

**This is a `contract`, not a `record`.** It says how work is done *now*; a line in it that
stops being true is a defect, not history. The incidents cited as evidence are dated and
are not maintained — they are why the rule exists, and each one is a real thing that
happened to this codebase rather than a principle someone liked the sound of.

**The one-line index**, because the body is long and the body is where the evidence is:

| | |
|---|---|
| ownership | one fresh subagent per task; the orchestrator verifies, commits, and owns the shared **input** as well as the shared output |
| parallelism | fan out on *reading* and on *writing prose*, never on a chain of edits that each need the last one's number |
| before implementing | verify the plan against the code, and verify the plan's **arithmetic against the artifact** |
| after it is green | a green suite does not mean the brief was met; the finished artifact is where the remaining defects are |
| measurement | a denominator needs an adversarial reader who cannot see how the numerator was built |
| reports | verify, do not trust the report — including your own, and including a function you verified and then changed |

---

## How this run works

**A session appends to its OWN record and edits only the entry point's live state.** Added
2026-08-02 by task 47. `docs/tasks/refactor/sessions/YYYY-MM-DD-<slug>.md` is `kind: record` —
frozen on write, so it never accretes strikes — and it is where *what landed*, *the process
lesson* and *the finding to carry forward* go. **`HANDOFF.md` gets the state table and nothing
else**, and it declares a `budget:` that `audit-docs.py` C7 enforces.

This is a convention with a measurement behind it rather than a preference. Task 44 archived
`HANDOFF.md` from 2771 lines to 2272; **thirty-six hours later it was 2669**, with all six
doc checks green throughout, because `DOCS-POLICY.md` rule 4's *mark, do not delete* makes
appending the **correct** response to every correction — so a rolling file carrying narrative
can only grow. An archival is a one-time cut. A record that cannot be edited is a floor.

**One fresh subagent per task; the orchestrator verifies and commits.** Nothing is
committed by a subagent. The orchestrator checks each Definition of done against the
files, writes the decision-log entries, and commits with the task number.

**The orchestrator should OWN the shared input, not just the shared output.** `STEPS`
was already an orchestrator-only file because every ingest task wants to edit it. The
version-keys session generalised it: `schema.py` was the input *both* agents needed,
so the orchestrator wrote it first and handed both agents a stable file to read. That
removed the race task 11 had to solve by pasting values into a prompt, and it is
cheaper than either — one small edit before the agents start.

**A sequential change is not a parallelisable one, and pretending otherwise costs more
than it saves.** The gate fix was four commits where each one's gate was the previous
one's measurement — a mock number, a live row count, a dead-term list. The orchestrator
did all four itself. Agents were used where the work genuinely forked: **three read-only
verification agents up front** on disjoint areas of the code, and **three documentation
agents at the end** on disjoint files. That is the shape to copy: fan out on *reading* and
on *writing prose*, not on a chain of edits that each need the last one's number.

**Verify the plan against the code before implementing it, not after.** Three agents spent
one round-trip checking step 0's claims and found ten errors, four of which changed the
work — including a required test that asserted something which could not fail, and a
script that refuses to run before it checks `--apply`. **Step 0 had itself been produced by
a careful session with live measurements.** Its numbers were all correct; its claims about
the code were not. Those are different things and they fail independently.

**And verify the plan's ARITHMETIC against the artifact, not against the algebra.** Task
29's plan asserted that rotating labellers by `sha256(labeller_id)` would give 110 distinct
postings, from `distinct = overlap + n * (budget - overlap)`. Counted against the drawn
200-row set: **84.** The formula assumes disjoint windows; hashing gives random ones, and
random windows collide. **The formula was not wrong — it was describing a different
mechanism from the one being built**, which is the failure a re-read of the code cannot
catch, because the code matched the plan. Rank spacing gives 110. **26 postings and a
Definition of done**, and the only thing that found it was computing the number the plan
had asserted.

**A finished artifact is where to look for the defects the checks cannot see. Three of task
29's four were found that way** — after the code was written, the tests were green and, for
the fourth, after the artifact had been committed. The gate misclassification surfaced from
counting `surfaced` two ways; the 84-vs-110 from counting distinct postings instead of
trusting the formula; the overlap skew from **reading the ten rows in the block rather than
the strata totals above them, which were correct.** In all three the marginals summed. **A
total is not a composition**, and a suite that is green tells you the code does what it was
written to do, not that what it was written to do is what was wanted. **Budget a pass that
looks at the output itself, after everything is green — it is where the expensive ones
were.**

**A measurement's denominator needs an adversarial reader who cannot see how the
numerator was built.** The mock-acceptance session gave two agents the same contract and
no sight of each other's work: one wrote the answer key, the other wrote the loader that
validates it. The loader **refused** the key — `location_is_nyc` is not a `job_facts`
column (`match.py:281`), so the model never produces it and scoring it would have
compared the loader's own mapping against the key's reading of the same twenty
characters. Two of eleven "extraction accuracy" fields would have been a field agreeing
with itself. **One reader reviewing both files would not have caught it**; the refusal
came from the boundary, not from care. Design the boundary in on purpose. **DEC-47.**

**Re-verify a function after you change it, including when you were the one who
changed it.** The orchestrator brute-force-verified `average_precision`'s tie handling
against every permutation, then sent back a correction that altered its signature. A
verified-then-modified function is unverified; the check was re-run and only then
trusted.

**Make a migration prove its own method before it writes.**
`migrate_description_rehash.py` reconstructs `content_hash` and reports that it
reproduces the *stored* hash on 10,405/10,405 untouched rows. A reconstruction method
that could not reproduce existing hashes is caught before it touches anything, which is
a stronger guarantee than a dry-run diff and costs one extra column in the report.

**A green suite does not mean the brief was met.** The version-keys session's test
agent delivered 37 tests, all passing, with one required test missing — the one
asserting `run-daily.py`'s `STEPS` entry verbatim. The suite was green *without* it,
because it is a test about a constant nobody had changed. It was caught by reading
the agent's test list against the brief, not by running anything. **Check the
deliverable list item by item; the suite only tells you the code you wrote works.**

**Verify, do not trust the report.** This mattered repeatedly:

- Task 16 reported itself finished while its report contained a literal
  `## RESULTS_PLACEHOLDER` and `company_ats` held **zero rows**. Caught by querying the
  database rather than reading the summary. It took two more passes to finish.
- Several agents complete their work and go idle **without sending a report at all**.
  Verify the artifacts directly; do not wait for a summary that may never arrive. **Task
  11 confirmed this at 3 of 3** — every agent went idle silently and every one had done
  the work. Treat the idle notification as "go look", not as a failure.
- Task 11's corpus agent shipped a document claiming "every number below is printed by
  the tool". Four of its headline figures were printed nowhere and no flag produced them.
  The analysis was sound; the reproducibility claim was not. **Re-run the tool and grep
  its output for the numbers the prose asserts.**
- Test counts drift while other agents work concurrently, so a count quoted by one agent
  may include another's in-flight tests.
- **Phase 9 ran five agents and two never reported**, including one whose work had to be
  split across three commits — the split was derived from the diff instead. **Two reports
  that did arrive were resends of content already applied**, because the orchestrator had
  reconstructed it from the code and the inline comments while waiting. None of this cost
  anything, and the reason is the rule above it: verification went against the files from
  the start, so a missing report was a missing convenience rather than a missing input.
  **Design the run so that a report is corroboration, never the only copy.**

**Give each subagent an explicit do-not-touch file list.** Parallel agents collide
otherwise. Three ran concurrently for most of the first session on that basis, and task
11's three had zero collisions across six files.

**A fence is only as good as the route around it.** In phase 9 one agent needed two lines
changed in a file its brief fenced off; it stopped, reported the exact edit, and the
orchestrator routed it to the agent that owned the file in under a minute. A second agent
in the same wave simply edited a fenced file. Nothing was lost — the owner had already
committed — but *"it turned out fine"* is not *"it was safe"*. **Tell every agent what to
do when it needs a fenced file, not only that it may not touch it**; an agent with no route
around a fence will eventually climb it. And when one asks, answer fast: the cost of the
detour is what makes the rule followable.

**The orchestrator should own the shared registers, and take the agents' text rather than
their edits.** Phase 9 had two files every task wanted to write — a defect register and a
decision log — and the orchestrator wrote both, from text the agents supplied in their
reports. That is what let two waves run three-wide and two-wide at all. It also meant that
when a report never arrived, the register entry could still be written from the code and the
inline comments, which is exactly what happened twice.

**When a number disagrees, make the tool print both rather than picking one.** Task 11's
doc said the ops archetypes reclaim 54 rows; the orchestrator's independent recount said
55. Neither was wrong — 54 is the five recommended values, 55 is all seven proposed. The
fix was to print both rows, labelled, so the ambiguity cannot recur. Silently adopting
either number would have buried a real distinction.

**Send an agent back to its own file; do not fix it yourself.** The ownership boundary is
what makes parallelism safe, and it does not lapse because the agent went idle. Task 11's
corpus agent fixed its own tool and doc on a second pass.

**Hand a downstream agent its inputs inline.** Task 11's extraction agent needed the
vocabulary its sibling had just derived, while that sibling was still editing the file it
lived in. Pasting the values into the prompt removed the race entirely.

---

## What this does not cover

**Measurement itself.** Every trap that has invalidated a number in this repo is in
[`MEASUREMENT-TRAPS.md`](MEASUREMENT-TRAPS.md), and that file is read first.

**What each document is for.** [`DOCS-POLICY.md`](DOCS-POLICY.md): five kinds, one
lifecycle each, and which of its seven rules has a check.

**The repo's own invariants** — the four stages, `job_facts` being shared, `score_job()`
being pure, what a deferral is. Those are `.claude/CLAUDE.md` and the per-script contracts
under [`ingest/`](ingest/extract.md); they are the things this method is applied *to*, and
they change when the product does.

---
kind: record
written: 2026-08-02
generator: none
---

# Session record — 2026-08-02, task 23 and the seam `run_due()` was waiting on

**Frozen on write.** A `record` says what happened on a date and is corrected by a later
record rather than rewritten ([`../../../DOCS-POLICY.md`](../../../DOCS-POLICY.md) rule 4).

## Why this task, when the entry point said there was nothing to do

`HANDOFF.md` § *What is next* opened with *"A session opening this run today should expect
to find nothing it can start alone"*, and for the product/API track that was accurate. It
was not true of the run. **Task 23 was `todo`, was named as a blocker by two other tasks,
and needed no credential, no person and no device.**

The blocking graph, checked against the task files rather than taken from the entry point:

| blocker | blocks | who can do it |
|---|---|---|
| **23** | 24's contributor adapter, 25's two deferred bullets, any real result on 32's search screen | **a session** |
| 29 | 30, 12's next bump, 13's weights | a second labeller; round 2 matures ~2026-08-09 |
| `OQ-8` | 30's naming half | the owner |
| `OQ-1` | 24's `Contribute` page | the owner |
| `OQ-4` | Builder reachability, the unproven backup | the owner |

**The lesson for the next session is about the entry point, not about the task.** *"The
product/API track has nothing session-doable left"* is a true sentence that reads as *"the
run has nothing session-doable left"* to anyone skimming, and the README's status column —
which is where the answer actually lives — said `todo` on a task the entry point never
mentioned. Both documents were correct. The reader was the failure mode.

## What landed

`backend/serp/`: the interface and its three failure classes, a SerpApi adapter and an
Apify adapter, one normalizer that defines nothing, the dispatcher `run_due()` takes, the
date-chip policy, a cache and a quota ledger. Plus `config/serp-quota.json`, a
`searchqueries` row in `config/volume-floors.json`, and `backend/tests/test_serp.py`.

All three suites green; [`AUDIT.md`](../AUDIT.md) owns the counts and names the command for
each. Both doc checkers report 0.

**The seam, in one sentence:** `searchqueries.run_due(conn, provider=None)` had taken a
callable since task 25 landed and every caller passed `None`, so `search_query_results` was
empty in production and `webapp/search.py`'s join — which is the gate — returned nothing for
every Builder. `serp.dispatch.SearchQueryProvider` is that callable.

**Verified end to end without spending a search.** `tests/test_serp.py::TestTheSeamIsClosed`
walks recorded SerpApi bytes through `serp.call()`, the upsert, `attach_results()` and
`record_run()` against a real scratch schema: ten postings written, all attached, `run_count`
and `provider_last_used` set. A fake connection could not have shown it — `job_id REFERENCES
jobs(id)` is what makes "which ids may be attached" a real question.

## Five things found on the way

**1. The ledger defect had no number, so nothing scanned it.** `DECISIONS.md` recorded the
3.3x undercount and called it *"not reversible; it is a defect"*, and no `D` entry was ever
written. It is now `D76`. This is the register's familiar failure one step earlier than
usual: not an entry missing from the index, but a defect that never became an entry.

**2. Re-measuring it produced a number that must not be quoted as a ratio.**
`google_jobs_query_stats` holds 18 rows this calendar month; SerpApi's own counter reads 193
used, 57 left of 250. **They are not comparable** — the table records no provider, its month
is not the vendor's billing period, and a row is written only after a query has already
succeeded end to end. That incomparability *is* the defect, and `D76` states it rather than
publishing 10.7x as though it were the new 3.3x.

**3. `choose_date_chip()` was unreachable at any price.** It lived in
`ingest/google-serpapi.py`, whose filename has a hyphen, so no module can import it. The
dispatcher could not have had a date policy without moving it — and without one, every run
re-asks Google the same unfiltered question and pays for the same relevance-ranked page.
Moved to `serp/datechip.py`, re-exported under its old name.
`api/query_claims.py`'s copy stays: `backend/api/` may import only `schema.py` and `lib/`.

**4. `due_queries()` selected `last_run_at` and dropped it from the dict it built.** One
key. Without it the policy above has nothing to compute from.

**5. Two falsy-`or` bugs, both in code written this session, both caught by tests that
would otherwise have passed for the wrong reason.** `now or time.time()` in the cache made
an epoch of 0 read as the wall clock, so the TTL test stored "at 0", got the real clock, and
aged nothing. `env or os.environ` in `credentials_for()` made an empty environment fall back
to the real one, so *"no key configured returns None"* would have passed or failed depending
on whose `.env` was on disk. **The general form is worth keeping: `x or default` is wrong
whenever 0 or an empty container is a legitimate value, and the tests it breaks are the ones
that look green.**

## What was deliberately not done

**The two ingest scripts still talk to their providers directly** (`DEC-99`). Routing them
through `serp/` is what closes *"no second definition exists"* for the fetch path, and it is
a live nightly path carrying claim and watermark semantics the interface does not model yet.
Doing both in one pass would make the first failure ambiguous, on the one path that spends
metered credits every night.

**Nothing alerts on a large reconciliation delta.** The number is printed every run; the
threshold that turns it into an alert is a policy call nobody has made, and inventing one
would be `D71`'s mistake.

**Two of task 23's Definition-of-done lines are reported UNMET** rather than tuned into
being met — *"at least three providers"* (it is two, after a descope that cut six of eight)
and *"allowances verified per provider"* (they are not verified; the ledger asks the vendor
instead, which is what that line was reaching for). Same treatment task 13's unmet lines got.

## The Apify balance is nearly gone, and nobody was watching it

Read from the account endpoint while testing the ledger: **$3.99 of $5.00 used, $1.01
left**, renewing monthly. Nothing in this repo would have said so — `D37` records that no
reconciliation against Apify's billing exists, and the nightly step's own budget constants
are per-run caps, not a balance. It is not urgent and it is not this task's to fix; it is
recorded here because the instrument that noticed it did not exist yesterday.

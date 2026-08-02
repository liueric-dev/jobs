---
kind: task
written: 2026-07-28
generator: none
---

# 28 — Anonymous cohort aggregation

**Status:** DONE 2026-08-02. **Depends on:** 27, **which is DONE**. **Blocks:** 32.

> **UNBLOCKED 2026-08-02, and this is the one blocker on this track that was REMOVED rather
> than argued away.** `HANDOFF.md` carried this task as *"a real blocker"*: `job_events` was
> keyed `(profile, job_id)`, thirty Builders share `pursuit`, so *"4 **Builders** saved
> this"* — the entire deliverable — was not a question the table could answer. **`app_user_id
> TEXT` landed on `job_events` in `3f4f88e`** (`../../../../backend/schema.py:678`, index at
> `:703`), written from `user.id` by `POST /v1/events`
> (`../../../../backend/webapp/jobs.py:837`). `COUNT(DISTINCT app_user_id)` is now answerable.
>
> **Three things that column does not settle, and each changes the implementation below.**
>
> 1. **`builder_job_state` is NOT usable as the source, despite being the obvious one.** It
>    carries `saved_at` per Builder already — but it is declared in
>    `../../../../backend/webapp/schema_web.py:281-288`, on the **webapp's** side of the
>    ownership line, and § *Implementation* below puts this compute on the **nightly
>    cycle**. `.claude/CLAUDE.md` § *Layout*: the three processes have their own roles and
>    **none imports another**. A pipeline table must not require the surfacing service's
>    schema. So aggregate from `job_events`, which is what this file already says — the
>    reason is stronger than it looks.
> 2. **`save` and `unsave` are both events, so a distinct count over `event='save'` is
>    wrong.** `_STATE_WRITES` (`../../../../backend/webapp/jobs.py:573-574`) maps both, and
>    `job_events` is append-only. Someone who saved and then unsaved still has a `save` row
>    forever. Take the **latest** of `{save, unsave}` per `(app_user_id, job_id)`; the
>    current answer is a fold over the log, not a filter on it.
> 3. **`app_user_id IS NULL` rows must be excluded, not counted.** Pre-column rows are NULL
>    by design and unbackfilled (`../../../../backend/schema.py:662-671`). Counting them
>    collapses every pre-2026-08-01 saver into one phantom Builder — which would push
>    postings **over** the suppression threshold on the strength of a row that names nobody.
>    That is the privacy control failing open.
>
> **What the column does NOT unblock is the small-N problem below.** *"4 Builders saved
> this"* becoming an identifier in a thirty-person classroom is not something a column
> answers, and the suppression rule is load-bearing arithmetic today rather than a
> precaution. [`../../../labelling-report-2026-08-02.md`](../../../labelling-report-2026-08-02.md)
> records **two** labellers on `pursuit`; at that headcount a threshold of 3 suppresses
> everything by construction. **Do not tune it down to see output** — an empty badge is the
> correct rendering of a two-person cohort, and the first thing a test here should pin is
> that `2` produces no badge rather than a small one. (Instrument for the live count is
> `manage_app_users.py list`, which needs the database; the report is committed data and
> does not.)

Surface "4 Builders saved this" without ever revealing which four — and without the
count itself becoming an identifier.

## Why it earns its place

Two reasons, and the second is the one that matters technically.

**It is the community feature.** Pooled postings with visible collective interest is
the draw — Builders helping each other find things, which is the social contract the
whole app is organised around.

**Collaborative signal works at N=30 precisely because the cohort is homogeneous.**
"Four Builders saved this" is usable information immediately, in a way "four strangers
saved this" would not be. Thirty people with a shared floor — entry-level, AI-adjacent,
NYC — produce a signal that would need thousands of unrelated users to match.

## The small-N problem

This is the part that needs care, and it is easy to get wrong.

In a thirty-person cohort who see each other in a classroom, **a count of 1 is close
to an identifier.** "1 Builder saved this" plus knowing who was on their laptop, plus
a posting for a role someone mentioned, is enough. Aggregate counts are not
automatically anonymous at this scale.

### Rules

**Suppress below a threshold.** Show nothing until at least 3 Builders have saved a
posting. Below that, no badge — not "1 Builder", not a greyed-out zero. Absence of a
badge must not be readable as "exactly one or two."

**Bucket rather than count exactly.** `3–5`, `6–10`, `10+`. An exact count that
increments visibly lets an observer infer *when* someone saved something, which
combined with who was present narrows it further.

**Never expose ordering or recency.** No "recently saved by a Builder." Timing is the
strongest deanonymiser available in a room where people can see each other.

**Aggregate only `cohort_anon` events.** Task 27 sets `visibility` server-side.
Applications are `private` and must never reach this path — enforce it in the query,
not by convention.

## Implementation

A materialised count per `(job_id, cohort)`, refreshed on the nightly cycle rather
than computed live. Live computation invites a timing side channel and costs more.

```sql
cohort_signal (
    job_id, cohort_profile,
    save_bucket TEXT,        -- '3-5' | '6-10' | '10+' | null
    computed_at TEXT,
    PRIMARY KEY (job_id, cohort_profile)
)
```

The read endpoint joins this; it never touches `job_events` directly. One join, one
place where the suppression rule lives, no chance of a future endpoint forgetting it.

## Where it does not go

**Not into ranking, yet.** It is tempting to boost saved postings, and it would work
— but it creates a feedback loop with nothing to correct it: a posting that surfaces
early accumulates saves, ranks higher, accumulates more. At N=30 with no position-bias
correction (task 27's `rank` is logged but not yet used), the loop would be
unmitigated.

Log it, display it, and revisit after there is enough data to correct for exposure.
The events are being collected either way.

**Not across cohorts,** initially. A rolling programme means multiple cohorts exist
simultaneously with different profiles. Cross-cohort aggregation would raise the
counts and improve the signal, but it also means a Builder's save is visible to people
they have never met, which is a different privacy promise than the one made. Keep it
within cohort until there is a reason not to.

## Definition of done

- `cohort_signal` computed nightly from `cohort_anon` events only.
- Counts suppressed below 3 and bucketed above it.
- No recency, no ordering, no exact counts exposed.
- Application events provably cannot reach the aggregation — enforced in the query,
  with a test.
- The read endpoint joins the materialised table, never `job_events`.
- A written note in the endpoint docstring explaining the suppression threshold, so
  someone tuning it later knows it is a privacy control and not a display preference.

## What the work turned up

Implemented 2026-08-02. `../../../../backend/cohort.py` (new), `cohort_signal` in
`../../../../backend/schema.py:454-533`, the join and the field in
`../../../../backend/webapp/jobs.py`, the step in `../../../../backend/run-daily.py`, and
48 tests in `../../../../backend/webapp/tests/test_cohort_signal.py`. Webapp suite
159 → **207, OK**.

**1. Two of this file's instructions conflict, and the conflict is silent.** § *Rules*
says "aggregate only `cohort_anon` events — enforce it in the query"; the 2026-08-02
correction block says take the latest of `{save, unsave}`. An `unsave` is **not**
`cohort_anon`: `visibility_for()` maps only `save` (`COHORT_VISIBLE_EVENTS`,
`../../../../backend/webapp/jobs.py:80`), so every unsave row is stored `private`. A
fold filtered on `visibility = 'cohort_anon'` therefore drops exactly the rows that make
it a fold, and silently restores the retracted-save overcount the correction block exists
to prevent — nothing raises, the counts just come out too high. Resolved by putting the
visibility predicate on the **counted** row only: a save contributes only if it is
`cohort_anon`, and an unsave is read regardless of its label because it is a retraction
of the Builder's own save and can only ever *remove* somebody from a count. The privacy
failure mode is a posting appearing that should not have; a retraction cannot cause one.
`TestVocabularyDoesNotDrift.test_an_unsave_is_stored_private_and_that_is_why_the_fold_is_asymmetric`
pins it, so if `unsave` ever becomes cohort-visible that test says the asymmetry can go.

**2. `save_bucket` is `NOT NULL`, deviating from § *Implementation*'s DDL sketch.** That
sketch lists `null` as a fourth value. A row with a NULL bucket means "somebody saved this
and it is below three", and the webapp role holds SELECT on the table — so the row's mere
**existence** publishes the fact the threshold exists to withhold. That is the suppression
failing open, one indirection past the obvious way, and it defeats § *Rules*' "absence of
a badge must not be readable as 'exactly one or two'". Sub-threshold postings therefore get
**no row at all**; the endpoint LEFT JOINs and renders the miss as `null`, so the API shape
this file describes is unchanged. There is a `CHECK` on the three labels besides.

**3. `'10+'` means eleven or more.** The three labels are ambiguous at the seam and the
code is not: the first matching bound wins, so 10 savers is `'6-10'`. Kept verbatim
because `frontend/fixtures/contract/` already ships these exact strings; pinned by
`TestBucketArithmetic.test_ten_is_in_the_six_to_ten_bucket_not_the_open_one`.

**4. The `id DESC` tie-break is load-bearing, not tidiness.** `occurred_at` is TEXT to the
second and `record_events` stamps one `now` across a whole batch, so a save and an unsave
of the same posting can share a timestamp exactly. Without it the winner is arbitrary — and
arbitrary in the direction that publishes a badge half the time, which is the suppression
failing open nondeterministically.

**5. The webapp needed `SELECT` on `cohort_signal`, and `test_grants.py` could not see
that it did — `D69`.** Without the `schema_web.REQUIRED_TABLES` entry, `verify_schema()`
never checks the table, the service starts cleanly, and the first `GET /v1/jobs` is a
`permission denied` 500 — precisely the failure
`../../../../backend/webapp/tests/test_grants.py`'s own docstring says it exists to
convert into a refusal to start. **The scan missed it**, and the blind spot was
pre-existing rather than new: `sql_strings_in()` kept only strings matching
`SELECT|INSERT|UPDATE|DELETE`, so a hoisted `LEFT JOIN <table> <alias> ON …` fragment was
dropped before `_FROM_JOIN` ever ran. `_BUILDER_STATE_JOIN` is invisible the same way and
was declared only by luck — `write_builder_state`'s real INSERT names that table elsewhere
in the file. Stated generally: **the check worked whenever a table was WRITTEN and skipped
tables that are only ever JOINED**, which is to say it was blind to read-only tables
specifically, and a read-only join is exactly what this task added.

Closed the same day. `schema_web.py:53` now declares `"cohort_signal": ("SELECT",)` (the
profiles stream), `test_grants.py`'s `pipeline_read_only` tuple carries it, and
`sql_strings_in()` now keeps a string that is a statement **or** a join clause. The
widening is deliberately `JOIN … ON` rather than the obvious `_FROM_JOIN`: measured on
this package, the loose form admits `label.py`'s user-facing HTML and `onboarding.py`'s
error messages and reports the "tables" `memory`, `the`, `this`, `what`, `you` and `a`,
which could only be quieted by listing English words as aliases. The narrow form admits
exactly two more strings package-wide and adds exactly one name, the real missing grant.
**Residue:** a fragment with neither a statement keyword nor `JOIN … ON` — a bare
`FROM <table>` tail, a WHERE clause, a CTE body — is still dropped.

**6. `frontend/verify_fixtures.py` still exits 0, and that is the bad outcome.** It reads
`LIST_COLUMNS` / `STATE_FIELDS` out of the source with `ast` and compares them to the
fixtures. `cohort_signal` is a new response key that neither tuple contains, so the
verifier compares a key set it has not learned about and passes while
`fixtures/shipped/` no longer describes the code — the "confidently wrong" fixture its own
docstring warns about. `jobs.COHORT_FIELDS` is exported as a module-level tuple of strings
so the existing `ast` reader can pick it up; `frontend/` must add it to `list_row` and
`detail_row` and add the key to the shipped fixtures, positioned **after the state fields
and before `rank`** on list rows and last on detail rows. That order is pinned from the
backend side by `TestTheEndpointReadsTheMaterialisedTable.test_the_response_key_order_puts_cohort_signal_before_rank`.

**7. It writes zero rows today, and that is correct.** The cohort is two Builders
([`../../../labelling-report-2026-08-02.md`](../../../labelling-report-2026-08-02.md)) and
the floor is three. Because "silence is this system's failure mode", the step's summary
line prints the builder count and the floor beside the posting count — `0 posting(s)
[3-5=0, 6-10=0, 10+=0], 2 builder(s) saving, floor=3` distinguishes a quiet Tuesday from
a broken fold, which `0` alone cannot. It deliberately never prints how many postings are
*below* the threshold: that is a per-posting sub-threshold fact, which is the one thing
this module refuses to emit anywhere, logs included.

**8. `run-daily.py`'s docstring says "all nine steps" and there were twelve before this
change.** Stale before this task touched it, and left alone rather than fixed in passing —
it is a doc claim about the schedule as a whole, not about this step.

**9. `webapp/README.md`'s GRANT table is enforced by nothing, and that is a rule 7 gap.**
`../../../../backend/webapp/schema_web.py:19-23` names three consumers of
`REQUIRED_TABLES` — the startup check, the README's `GRANT` statements, and
`tests/test_grants.py`. The test checks the dict against the package's SQL and **never
against the README**, so the second consumer is on the honour system. That is the same
shape as the failure `tests/test_grants.py:11` records as the reason it exists: a grant
"documented in its README and verified by nothing", which surfaced as a 500 on a
contributor's first submit rather than as a refusal to start. The lesson was made
automatic for one of the two artefacts and not the other. Recorded rather than fixed —
a README-versus-constant check is its own piece of work, and it is exactly the
figure-lives-with-its-instrument problem `DOCS-POLICY.md` rule 7 and tranche seven's 45/46
are closing for `docs/`. `TABLES_TOUCHED = frozenset(REQUIRED_TABLES)`
(`schema_web.py:119`) is derived, so `test_required_tables_matches_tables_touched` needs
nothing.

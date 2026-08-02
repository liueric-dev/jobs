---
kind: contract
script: none -- this is a register over every ingest path, not a per-script reference
written: 2026-07-28
code_at: dd49a27 (audit base) + 28f1d0e (current HEAD, webapp-service)
generator: none
---

> **Provenance.** `generator: none` is literal: nothing in this repo produces
> `docs/ingest/*.md`. Earlier versions carried `generated:` frontmatter naming a
> tool that was never written, which made `.claude/CLAUDE.md`'s *"never hand-edit"*
> instruction unfollowable — the only way to fix a wrong line was to break the rule.
> The claim was dropped across all fourteen files on 2026-07-31; see
> [`34-documentation-cleanup.md`](../tasks/refactor/34-documentation-cleanup.md) §A2.
> These files are hand-written and are maintained by hand.

# Ingest audit defect register

`docs/ingestion_tests/README.md:7` said the `docs/ingest/` audit "found 16
defects at `dd49a27`," scattered across eleven generated documents with no
single list. This is that list.

**Method.** Walked all eleven `docs/ingest/*.md` files plus
`docs/ingestion_tests/04-score-validation.md` and `05-fetcher-harness.md` (the
two that trace defects into `score.py` and give the audit's own numbered
"defects this would catch" table). Pulled every row from a failure-behaviour
table describing a defect rather than intended behaviour, then grepped all
thirteen documents for `discarded`, `defect`, `silently`, `silent`, and `never
read` to find the rest. Every site below was re-checked against the code at
the current commit (`git log dd49a27..HEAD` touches only `backend/llm.py`,
`score.py`'s model-mismatch guard, and docs/tests for task 01 — no line
numbers cited here moved as a result, confirmed by direct read).

**Total: 45 entries** (`D01`–`D45`, verified unique and gapless) — `D43` and
`D44` were found by task 08 while closing `D15`, and `D45` by task 19's
coverage spike, not by the original pass; all three are recorded in full
below — more than the 16
the README named, because that count
was itself informal (nobody had built the list yet) and because triaging
means finding the remainder, per task 03's instruction to "audit the
remaining sources... before assuming four is the total." 25 are genuinely new
findings from this pass, not previously written up as a defect anywhere.

**Classes** (defined in `docs/tasks/refactor/tranche_one/02-triage-audit-defects.md`):
**silent data loss** (run reports success, rows missing or wrong — fix now),
**loud failure** (crashes/raises — fix opportunistically, harness catches
regressions), **cosmetic** (misleading comment, duplicated work, dead code —
fold into task 34).

**Disposition**, independent of class: **fix now**, **fix with harness**
(needs task 09's fetcher cassettes, or task 08's eval harness, to test
safely — do not fix blind against production), or **won't-fix** (reason
given).

**A disposition that names a blocker must spell it `BLOCKED-BY: <thing>`, and the thing
must be greppable.** That is the one rule this register learned the hard way: nine entries
were dispositioned *"fix with harness — task 09"*, task 09 landed three tranches ago,
nothing rescheduled them, and they were invisible in both directions for three tranches. A
blocker written as prose cannot be checked; a blocker written as a token can.

```bash
grep -n 'BLOCKED-BY:' docs/ingest/DEFECTS.md
```

is the whole mechanism. Every hit names something whose status is looked up in
[`tasks/refactor/README.md`](../tasks/refactor/README.md); a hit whose blocker has landed
is an entry that needs rescheduling **today**, and it is one command away instead of
nowhere. When the blocker clears the token becomes `UNBLOCKED-BY: <thing> (landed <sha>)`
and the entry is owned again — still greppable, now as a queue of work rather than a queue
of excuses.

**And check that the blocker was ever real.** Task 42 found that three of the six entries
task 34 marked UNBLOCKED needed no harness at all (D05, D11, D13); two of them said so in
their own text, in the same sentence that deferred them. A disposition written for a batch
gets applied to members that did not need it, so `BLOCKED-BY:` is a claim to verify against
the code, not a fact to inherit.

## Allocator — this register owns the `D` prefix

Per [`DOCS-POLICY.md`](../DOCS-POLICY.md) rule 6, one allocator per register and no
register issues an identifier in another's space. **This file owns `D<n>` and nothing
else does.** Decisions are `DEC-<n>` and live in
[`DECISIONS.md`](../tasks/refactor/DECISIONS.md); task numbers live in
[`tasks/refactor/README.md`](../tasks/refactor/README.md).

**Next free: `D71`.** Allocated `D01`–`D45` and `D66`–`D70`; **`D46`–`D65` are burnt and
must never be issued.** They are not defects and never were — `DECISIONS.md` continued this register's
count when it started allocating decision IDs mid-file, so those twenty numbers circulate
in eighty-odd places meaning *decisions*. Task 39 re-prefixed the live sites to `DEC-46`–
`DEC-65`, but `CLAUDE_UPDATES.md` and `docs/archive/` are `kind: record` and are
deliberately left unswept, so the old spelling survives in the tree on purpose. Issuing a
defect `D52` would make it ambiguous against those, which is the exact failure rule 6
exists to prevent. Skipping twenty integers is cheap; a number that resolves two ways is
not.

**Cross-register references are written out** — *"defect D45"*, *"decision DEC-52"* —
because a bare `D45` in a code comment cannot be resolved by a reader who does not already
know which file it came from. `backend/tools/ats-discover.py` is the worked example: its
dozen citations all read *"defect D45"* and all mean this register.

---

## Task 34's pass over this register, 2026-07-31

**Eleven closed, six re-dispositioned, three left open with reasons.** Every row
below was re-checked against the code rather than taken from this file.

**Two entries were already done and still listed as owed** — which is the register's
own failure mode, and the reason this pass re-read the code instead of the table:

- **D45's body has said `### D45 — fixed` since task 16's follow-up landed**, while its
  index row said *"**open** — needs a task"*. The index is the part anyone scans.
- **D27's five unused imports are all absent from `ats.py`**, verified name by name.

**Nine were dispositioned *"fix with harness — task 09"*, and task 09 landed three
tranches ago** (`09-fetcher-harness.md`, `68f026f`). Nothing rescheduled them, so they
were neither open-with-an-owner nor closed — invisible in both directions. Three are now
fixed (D10, D12, D17); six are marked **open, UNBLOCKED**, which is a real status rather
than a stale blocker.

**D17 was the cheapest confirmed bug in the repo** and had been waiting on a fix of two
lines. `run_actor_query()` bound `run` only inside the poll loop, so an actor run that
came back `SUCCEEDED` immediately skipped the loop, passed the status check, and read a
name that was never assigned — **a paid Apify run whose results are never collected,
reported as one failed query among many.** The reproduction was already committed at
`tests/test_ingest_cassettes.py`, written to assert the `UnboundLocalError` on purpose
with a note saying *"whoever fixes the defect flips this assertion."* It is flipped.

**Three counts in this register were wrong**, all in the same direction — the code had
more of the defect than the entry claimed:

| entry | recorded | actual |
|---|---|---|
| D28 | *"4 unused imports"* | **5** — the whole `from datetime import …` line is dead |
| D30 | *"5 unused imports"* | 5, but `timezone` **is** used and would have gone in a sweep |
| A5 (task 34) | two stale docstring sites | **three**, plus the cassette's own `note` |

Counted with an AST walk over binding-vs-`Name`-use rather than by grep, because grep
cannot tell an import from the word appearing in a comment — which is exactly how D32's
`ids` was miscounted in the first place.

**Three are left open on purpose, with the reason recorded:**

- **D31** (three of six ingests bypass `lib.http` retry/backoff) — *"I could not
  determine whether this is deliberate or an incomplete migration"* is still the honest
  state, and `weworkremotely.md` says so. Each of the three imports `http` **solely for
  `DEFAULT_TIMEOUT`** and then calls `urllib.request.urlopen` directly, which is either a
  deliberate opt-out of backoff for a cheap endpoint or a migration nobody finished.
  **This is a decision, not a fix**, and making it silently uniform would change retry
  behaviour on three live sources to settle a documentation question.
- **D33** (`google_jobs_query_stats` accumulates, read by nothing) — the adaptive-cadence
  consumer that was meant to read it is **task 25**. Deleting the table now destroys the
  input; wiring it now is task 25's job. Left with the pointer.
- **D34** (22 orphaned `job_ingest_state` watermark rows) — a DELETE against the live
  database, not a code change. It needs the owner at a psql prompt and gains nothing from
  being run by an agent mid-refactor.

## Task 42's pass, 2026-08-01

**All six UNBLOCKED entries closed** (D02, D03, D05, D11, D13, D23), each with a test that
fails without its fix — 21 tests added to `backend/tests`. The suite's size is
[`AUDIT.md`](../tasks/refactor/AUDIT.md)'s figure under policy rule 2 and is read from the
`Ran N tests` line, not restated here. (This paragraph originally typed both counts;
`audit-docs.py` check C4 caught it within an hour of landing, which is the first thing that
check ever did.)

**Three of the six were never blocked** — D05, D11 and D13 needed no cassette, no scratch
database and no fixture. Only D02 and D23 genuinely did; D03's fix needed nothing but its
re-derivation did. This is D17's shape three more times, and it is why `BLOCKED-BY:` above
is a token rather than prose.

**Every count quoted for these six was wrong — all four of them:**

| entry | recorded | actual |
|---|---|---|
| D03 | *"135 of 351 live rows"* | **421 of 678**, and **0 misshapen** |
| D05 | *"three `continue` … a fourth"* | **five** statements: 3 drops, 1 already counted, 1 dedupe |
| D02 | line cites correct | but the recorded page **cannot** show the defect — hence the fixture |
| D13 | `extract.py:82-83` | **`extract.py:220-221`**, 138 lines off |

Line cites had also drifted in D03 (`:148`→`:146`, `:338`→`:336`), D11 (all three sites
moved) and D23 (`:422`→`:438`). **Read the code, not the cite.**

## Index

| id | class | disposition | one-line |
|---|---|---|---|
| [D01](#d01) | silent data loss | **fixed** — task 03 | Per-record upsert errors discarded at 8 call sites |
| [D02](#d02) | silent data loss | **fixed** — task 42, 2026-08-01 — paired by containment, desync fixture committed | `builtin-nyc.py` title/company zip can silently misattribute |
| [D03](#d03) | silent data loss | **fixed** — task 42, 2026-08-01 — scoped to `fa-sack-dollar`; **421 of 678** live rows, not 135 of 351 | `builtin-nyc.py` salary regex unscoped, captures false positives |
| [D04](#d04) | silent data loss | won't-fix (documented) | `weworkremotely.py` token from display name — silent duplicate rows |
| [D05](#d05) | silent data loss | **fixed** — task 42, 2026-08-01 — 3 named drop counters + a separate dedupe count, in the summary | `weworkremotely.py` drops items with zero counters at any verbosity |
| [D06](#d06) | silent data loss | won't-fix (documented) | `weworkremotely.py` all-feeds-empty indistinguishable from a quiet day |
| [D07](#d07) | silent data loss | won't-fix (mitigated) | Google sources: non-English relative dates silently lose `posted_at` |
| [D08](#d08) | silent data loss | fix before deploy — task 24 | Contributor API: empty submit still advances the watermark |
| [D09](#d09) | silent data loss | fix before deploy — task 24 | Contributor API: unreadable query bank silently mislabels `mode` |
| [D10](#d10) | silent data loss | **fixed** — task 34, 2026-07-31 — now reported, still `[]` | `match.py`: bad `tech_stack` JSON silently becomes `[]` |
| [D11](#d11) | silent data loss | **fixed** — task 42, 2026-08-01 — ids logged at `DEBUG_PRINT_KEYS`, `DEC-69` | `match.py`: demoted/orphaned rows deleted with no recoverable log |
| [D12](#d12) | silent data loss | **fixed** — task 34, 2026-07-31 — `check_criteria_sections()`, 4 tests | `match.py`: a typo'd `criteria.json` section silently disables itself |
| [D13](#d13) | silent data loss | **fixed** — task 42, 2026-08-01 — import-time assertion, was never blocked | `match.py`/`extract.py`: seniority vocabulary drift scores as free |
| [D14](#d14) | silent data loss | won't-fix (documented, low current risk) | `match.py --profile` can silently prune another profile's rows |
| [D15](#d15) | silent data loss | **fixed** — task 08 | `score.py`: `fit_score`/`primary_track` stored unvalidated (audit item 8) |
| [D16](#d16) | loud failure | **fixed** — task 08 | `score.py`: missing `buckets` key kills a profile's whole batch |
| [D17](#d17) | loud failure | **fixed** — task 34, 2026-07-31 — reproduction flipped to assert the rows | `google-apify.py`: `UnboundLocalError` on immediate-success poll (audit item 1) |
| [D18](#d18) | loud failure | fix opportunistically | Uncaught `KeyError` on malformed config (audit item 6) |
| [D19](#d19) | loud failure | fix opportunistically | Normalization outside the per-unit `try` in 4 scripts (audit item 7) |
| [D20](#d20) | loud failure | fix opportunistically | `match.py`: no per-record isolation, one bad row kills the run (audit item 3) |
| [D21](#d21) | loud failure | fix opportunistically | `hn-hiring.py`: `relevance.json` load failure crashes at import |
| [D22](#d22) | loud failure | won't-fix (deliberate) | `ensure_schema` raises uncaught if `public.events` exists |
| [D23](#d23) | silent data loss | **fixed** — task 42, 2026-08-01 — one transaction, ledger commits with the rows | `hn-hiring.py`: ledger-before-upsert crash window strands comments (audit item 4) |
| [D24](#d24) | silent data loss (unconfirmed) | won't-fix (unconfirmed; revisit if it recurs) | `extract.py`: 15 rows possibly permanently starved at `facts_version=1` |
| [D25](#d25) | silent data loss | **fixed** — `28f1d0e` | Live model silently differed from the documented default |
| [D26](#d26) | cosmetic | **fixed** — task 34, 2026-07-31 — the surviving half was a test's *reason* | Stale "`unescape=False`" claim in two files contradicts `ats.py` |
| [D27](#d27) | cosmetic | **fixed** — verified 2026-07-31, all five absent | `ats.py`: 5 unused imports |
| [D28](#d28) | cosmetic | **fixed** — task 34, 2026-07-31 — **5** unused, not the 4 recorded | `builtin-nyc.py`: 4 unused imports, `http` imported for one constant |
| [D29](#d29) | cosmetic | **fixed** — task 34, 2026-07-31 | `weworkremotely.py`: `parse_posted_at` called twice on the same value |
| [D30](#d30) | cosmetic | **fixed** — task 34, 2026-07-31 — `timezone` IS used and was kept | `weworkremotely.py`: 5 unused imports |
| [D31](#d31) | cosmetic | **open — needs a decision, not a fix** | Inconsistent `lib.http` usage — 3 of 6 ingest scripts bypass retry/backoff |
| [D32](#d32) | cosmetic | **fixed** — task 34, 2026-07-31 | `hn-hiring.py`: 3 unused imports |
| [D33](#d33) | cosmetic | **open — belongs to task 25** | `google_jobs_query_stats` accumulates, read by nothing |
| [D34](#d34) | cosmetic | **open — a data cleanup, needs the live DB** | 22 orphaned `job_ingest_state` watermark rows |
| [D35](#d35) | cosmetic | **fixed** — task 34, 2026-07-31 — env var now actually read | `CLAIM_TTL_MINUTES` documented but unread by `google-serpapi.py` |
| [D36](#d36) | silent data loss | won't-fix (patched API-side) | `claimed_by` asymmetry already caused a real ownership-check bug |
| [D37](#d37) | cosmetic | won't-fix (low stakes) | `google-apify.py`: abandoned actor runs billed and untracked |
| [D38](#d38) | cosmetic | won't-fix (harmless) | `POST /v1/events` impression-dedup race under concurrent requests |
| [D39](#d39) | cosmetic | fix opportunistically | `extract.py`: concurrent runs would double-spend LLM calls (no lock) |
| [D40](#d40) | cosmetic | fix opportunistically | `score.py`: login-triggered and nightly runs can double-spend |
| [D41](#d41) | cosmetic | fix before deploy — task 24 | Contributor API: `claim` is unmetered beyond the daily cap (self-documented gap) |
| [D42](#d42) | cosmetic | **fixed** — task 34, 2026-07-31 — marked seen, counted, reported | `hn-hiring.py`: null comment items re-fetched forever (audit item 5) |
| [D43](#d43) | silent data loss | **fixed** — task 08 | `score.py`: a tombstone left the previous score in place, and `has_fields` let an all-null answer through |
| [D44](#d44) | loud failure | **fixed** — task 08 | `evals/__main__.py`: `evals run` raised `UnboundLocalError` for every task |
| [D45](#d45) | silent under-sizing | **fixed** — verified 2026-07-31; the body has said so and this row did not | `company_ats`: the `never_found` write-back from `ats_seed` is partial. 35 rows against a true population of 139 |
| [D66](#d66) | silent data loss | **fixed** — 2026-08-01 — `job_events.app_user_id`, nullable and unbackfilled | `GET /v1/jobs` reports `seen` cohort-wide, not per Builder |
| [D67](#d67) | silent data loss | **fixed** — 2026-08-01 — same column, same join; dedup key deliberately untouched | `applied` likewise, contradicting the `private` visibility on its own event row |
| [D68](#d68) | silent data loss | **fixed** — 2026-08-01 — both halves; two conjuncts, one on each end of the derivation | `derive_skips` reads *and* is vetoed by another Builder's events if the client echoes their `request_id` |
| [D69](#d69) | check with a blind spot | **PARTIALLY fixed** — 2026-08-02 — `_JOIN_CLAUSE` closes the join-fragment case; **three-part residue, recorded not closed** | `test_grants` kept only strings containing a statement keyword, so a table named solely in a hoisted `JOIN … ON` fragment was never checked for a GRANT |
| [D70](#d70) | check with a blind spot | **open** — found 2026-08-02 | `frontend/verify_fixtures.py` hardcodes the tail of the expected key list, so a new response field is invisible: fixtures and verifier agree with each other and both disagree with the code |

**D66 and D67 were absent from this index entirely** until they were closed — added
2026-08-01, on the lesson D45's row records four paragraphs above: *"the index is the part
anyone scans."* A body with no index row is the same failure as an index row that
disagrees with its body, one step earlier.

---

## Silent data loss — fix now, before Phase 3

This is the only class that justifies delaying Phase 3, because it is the
only class the operator cannot detect by watching the nightly run.

### D01 — fixed

**Per-record upsert errors discarded, at every one of 8 call sites.**
`lib/upsert.py:157-166`'s `UpsertResult.__iter__` yields `(new, updated,
unchanged)` and never `.errors`, so `x, y, z = upsert(...)` reads naturally
and silently drops every per-record failure. Confirmed at:

- `backend/ingest/ats.py:337`
- `backend/ingest/builtin-nyc.py:404`
- `backend/ingest/google-serpapi.py:325`
- `backend/ingest/weworkremotely.py:225`
- `backend/ingest/hn-hiring.py:426-427` (reads `.new` only; `.errors` never touched)
- `backend/ingest/google-apify.py:232`
- `backend/api/app.py:336`
- `backend/api/query_claims.py:444` (`upsert()` also omits `debug=`, so there
  is no stderr fallback either)

Blast radius: **all ingest** — every write path in the pipeline. A run with a
hundred failed records and zero read errors reports success; the only symptom
is a corpus quietly smaller than it should be. **Status: fixed**
(`docs/tasks/refactor/tranche_one/03-fix-silent-upsert-errors.md`) —
`lib/upsert.py` gained `upsert_checked()`, which logs an `upsert-summary:`
line carrying `errors=N` on every call including when N is zero, and raises
`UpsertErrorRate` above a 5% per-run failure rate. All 8 sites call it;
`UpsertResult.__iter__` is deliberately unchanged. `run-daily.py` now reports
per-step written/dropped counts, so "ran and wrote nothing" and "ran and
dropped everything" no longer print identically.
`backend/tests/test_upsert_checked.py` covers all 8 paths.

### D02 — fixed

**`builtin-nyc.py` pairs titles and companies by list index, not by
containment**, and nothing verifies the pairing (`backend/ingest/builtin-nyc.py:316-333`).
A card with no company anchor, or an extra `company-title` anchor anywhere
earlier on the page, shifts every subsequent pairing by one — silently
attaching the wrong company to the wrong title, indistinguishable from a
correct row. Whether this has ever fired is unknown; there is no assertion,
no counter, and no stored `raw_json` to audit against.

Blast radius: one source (`builtin`). Disposition: **fix with harness** —
needs a cassette fixture (`docs/ingestion_tests/05-fetcher-harness.md`'s
suggested `fixtures/cassettes/`) to safely exercise a desync case without
scraping the live site to check.

**Fixed, task 42, 2026-08-01.** `parse_page` now pairs by containment: a card's
company is the last `data-id="company-title"` anchor before its title and after
the previous title (`backend/ingest/builtin-nyc.py:328-345`). An anchor belonging
to no card is ignored instead of consumed, and a card with no anchor of its own
drops **only itself** and is counted (`no_company_anchor`, reported in the summary
line at every verbosity).

The recorded page could not express the defect — it holds 23 titles and 23 anchors
interleaved one for one, so index-zip and containment agree on it exactly. Per task
34 rule 4 the cassette was not re-recorded; the case lives in a fixture beside it,
`backend/evals/fixtures/builtin-nyc-desync.html` — a four-card slice of the recording
with exactly one anchor deleted, whose remainder is asserted to still be a
byte-for-byte substring of the cassette so it cannot rot into a hand-written copy.

**A correction worth keeping.** `test_titles_and_companies_line_up` asserted
`len(titles) == len(companies)`, which is **not** sufficient: extend that fixture by
one anchor and the counts match again while every pairing stays wrong. Counting is not
a proxy for containment.

### D03 — fixed

**`SALARY_PATTERN` is not scoped to a salary element** — it matches
`[0-9]{1,3}K-[0-9]{1,3}K` anywhere in a builtin card window
(`backend/ingest/builtin-nyc.py:148`, `:338`). Any "100K-150K"-shaped
substring is captured as `salary_text`; 135 of 351 live rows have a non-empty
value, none verified against the actual salary field. Blast radius: one
source (`builtin`). Disposition: **fix with harness** — task 09, same
fixture work as D02 (both need a cassette of real `builtin` HTML to change
the regex against without scraping production to check).

**Fixed, task 42, 2026-08-01.** `SALARY_PATTERN` is scoped to Built In's own salary
element (`fa-sack-dollar`), read exactly the way the location and work-type fields
either side of it already are (`backend/ingest/builtin-nyc.py:146-160`). The line
cites above were off by two: the pattern was at `:146`, the read at `:336`.

**The count is re-derived and was stale.** Not 135 of 351 — **421 of 678** builtin
rows carry a non-empty `salary_text` (2026-08-01, read-only query against the
pipeline database). More usefully, **0 of the 421 are misshapen**: every one matches
`^\d{1,3}K-\d{1,3}K` and the suffixes are `Annually` (417) and `Hourly` (4), which is
Built In's two renderings of that element and nothing else. So the defect is real in
principle with no observable instance in production today. Shape is evidence, not
proof — a title reading "Sales Engineer 120K-260K OTE" would match too — but the
suffix distribution is what makes the false-positive count credibly zero.

On the recorded page scoped and unscoped agree on all 23 cards and both find 20
salaries, so the change is provably inert on real bytes. The false positive is derived
in-test from those bytes (one card's title text edited, the disclosed range left where
Built In renders it), the same way `_immediate_success()` derives D17's.

### D04

**`weworkremotely.py`'s `company_token` is derived from the posting's display
name**, via `slugify` (`backend/ingest/weworkremotely.py:165`), not a stable
id the way `ingest/ats.py`'s config-sourced token is. A company that changes
how it writes its own name in the RSS title produces a different token,
hence a different primary key, hence a second row for the same posting.
Nothing detects this. Blast radius: one source (`weworkremotely`).
Disposition: **won't-fix** — no alternative stable id exists in the feed;
documented as a known limitation, not actionable without a fuzzy-match layer
the docstring explicitly declines to build.

### D05 — fixed

**`weworkremotely.py` drops items via three separate `continue` statements
with zero counters at any verbosity**: no colon in `<title>`
(`:146-149`), a `NON_TECH_EXCLUDE_PATTERN` match (`:150-151`), and an empty
`source_id` (`:159-161`); a fourth path, cross-listed duplicates, is also
uncounted (`:206-211`). The summary reports only `len(all_records)`. A regex
change to the exclude pattern that started matching legitimate engineering
titles "would produce no signal at all" (`docs/ingest/weworkremotely.md:309-312`).
Blast radius: one source (`weworkremotely`). Disposition: **fix with
harness** — task 09; adding counters is low-risk but this script is one of
the six task 09 covers, and a cassette confirms the counts match what the
fixture actually drops before changing production output.

**Fixed, task 42, 2026-08-01.** Three named counters — `DROP_REASONS`
(`backend/ingest/weworkremotely.py:150`) — reported in the summary line at every
verbosity, not behind `DEBUG_PRINT_KEYS`: a count that only appears when someone
thinks to ask for it is the same silence in a different shape.

**The `continue` count, re-derived.** There are five `continue` statements, not three
and not four: `:147`, `:149`, `:159` are the silent drops this entry is about; `:209`
is a fetch/parse failure that was **already** counted in `category_errors`; `:214` is
the cross-listed dedupe. This entry's "three, plus a fourth" was structurally right and
cited `:206-211` — the exception handler — for a dedupe that lives at `:211-215`.

**The dedupe is counted and reported separately from the drops**, deliberately. It is a
correct outcome, and it is normally nonzero — WWR cross-lists by design, 7 on the
recorded feeds. Folding it into a "dropped" total gives that total a large noisy floor,
and an exclude-pattern regression eating five real titles would move it from 7 to 12:
invisible, which is the exact failure these counters exist to expose.

**Measured on the `wwr-feeds` cassette:** 187 items in, 178 records out, 9 dropped (all
`non_tech_excluded`), 7 cross-listed. 16 of 187 — 8.6% — left the script without a row,
and every one was invisible.

**This never needed task 09.** Adding counters is a caller-side change with no
production dependency; this entry says so itself (*"adding counters is low-risk"*) in
the same sentence that defers it. See the note under D13.

### D06

**All four `weworkremotely` feeds returning zero items with zero errors is
indistinguishable from a quiet day.** The failure gate is `if not
all_records and category_errors` (`backend/ingest/weworkremotely.py:219`), so
a run where every feed answers 200 with an empty or fully-filtered body exits
0 silently. Blast radius: one source. Disposition: **won't-fix** — the
document's own analysis holds: `close_stale` is time-based, not diff-based,
so this is not a mass-close risk, only a slow-news-day false negative.

### D07

**Non-English relative timestamps silently fail to parse.**
`hl=en&gl=us` on the SerpApi request is "load-bearing"
(`docs/ingest/google-serpapi.md:398-401`) — without it, Google intermittently
returns relative dates like `"há 2 dias"`, which
`text.parse_relative_posted_at`'s English-only regex cannot parse, losing
`posted_at` with no visible error. Currently mitigated by the two query
params on every call. Blast radius: google sources
(`google-serpapi.py`, `google-apify.py` — shared `google_jobs.py` normalizer).
Disposition: **won't-fix**, currently mitigated; revisit if the query
parameters are ever dropped or a non-US locale is added.

### D08

**A contributor submitting `jobs: []` still advances the query's
watermark.** `submit` performs no non-empty check; `qc.upsert(conn, [])`
writes nothing, then `mark_success` runs unconditionally
(`backend/api/app.py:336-341`), marking the query covered for the next 20
hours. A buggy or lazy contributor worker can silently mark a query "done"
with zero rows collected. Blast radius: one source (contributor API; never
deployed). Disposition: **fix before deploy** — `docs/tasks/refactor/README.md`
Phase 4 task 24 revives this service; this should be closed as part of that
work, not before.

### D09

**`_mode_for_slug` silently returns `"unknown"`** when the query bank is
unreadable at submit time (`backend/api/app.py:389-401`), which feeds
`location_is_remote` via `normalize_job`'s `mode` parameter — a config read
failure at exactly the wrong moment quietly corrupts a stored fact rather
than rejecting the submission. Blast radius: one source (contributor API;
never deployed). Disposition: **fix before deploy** — task 24.

### D10

**`match.py` silently coerces a `tech_stack` JSON parse failure to
`[]`** (`backend/match.py:237-240`), losing that job's tech-match signal for
every profile with no counter anywhere. Blast radius: all profiles (match
stage). Disposition: **fix with harness** — task 09 (match.py fixes need the
scratch database it builds, per its own "do not fix blind against
production" principle); log a counter, no semantic change needed since `[]`
is a reasonable fallback.

### D11 — fixed

**Demoted and orphaned `job_matches` rows are deleted with no recoverable
log of which jobs.** Only counts reach stdout
(`backend/match.py:274`, `:298`, `:363-369`). A weight edit that demotes
hundreds of rows reports a number with no way to see which — and the rows
are already gone by the time anyone looks. Blast radius: all profiles (match
stage). Disposition: **fix with harness** — task 09; log job ids at
`DEBUG_PRINT_KEYS` verbosity at minimum, since `match.py` currently reads
that flag nowhere.

**Fixed, task 42, 2026-08-01.** `match.py` now reads `DEBUG_PRINT_KEYS` (it read it
nowhere) and logs the ids of every deleted row through one function,
`log_deleted_ids()` — `[debug]` prefix, stderr, off by default. `prune_orphans` gets
them from `DELETE … RETURNING job_id`; the demotion path already held the exact list.
Interface choice and rejected alternative recorded as decision `DEC-69`.

**Every line cite in this entry had moved.** `:274` is `score_job`'s return, `:298` is
inside a docstring, `:363-369` is `prune_orphans`'s docstring. The real sites are
`:378-381` (orphan DELETE), `:438-441` and `:460-464` (demotion), `:506-512` (summary).
The claim itself was accurate.

**This never needed task 09** — wiring an env var and printing a list is caller-side.
The scratch database appears in the test, not in the fix. See the note under D13.

### D12

**`criteria_json` structure is not validated at scoring time.** Every
section lookup defaults via `.get()` (`backend/match.py:97`, `:122`, `:133`,
`:139`, `:149`, `:163`, `:173`), so a typo'd section name in a profile's
criteria silently disables that entire section's penalty rather than
erroring. `profiles.validate()` runs before every write but nothing re-checks
at read time. Blast radius: all profiles (match stage). Disposition: **fix
with harness** — task 09.

### D13 — fixed

**`match.py`'s `SENIORITY_ORDER` must stay a superset of `extract.py`'s
`SENIORITY` vocabulary, and nothing asserts it**
(`backend/match.py:65-66`, `:116`; `backend/extract.py:82-83`). A level
present in one and absent from the other silently scores as free rather than
raising. Blast radius: all profiles (match/extract coupling). Disposition:
**fix with harness** — task 09; a shared constant or a startup assertion
would close this cheaply, verified against the scratch database rather than
production.

**Fixed, task 42, 2026-08-01.** `match.py` imports `extract.SENIORITY` and asserts at
import time that `SENIORITY_ORDER` covers it — `check_seniority_vocabulary()`, called at
module level, raising `SeniorityVocabularyDrift` (`backend/match.py:70-126`). A
**superset**, not equality: the ranker's scale may legitimately carry rungs the extractor
never emits, and only the other direction loses information. One definition of the
vocabulary, in `extract.py`, where the prompt and `_enum()` both read it.

Raised rather than warned, and that is the opposite of `check_criteria_sections()`: a
stray criteria section is one profile's own data, this is a repo-wide invariant between
two files that ship together. `score_job()` is untouched and still pure — the check is at
import, never inside the scorer — and `lib/` is untouched.

**The worst line drift in this register.** `extract.SENIORITY` is at
`backend/extract.py:220-221`, not `:82-83`. `match.py:65-66` was right; `:116` is now a
comment and the use site is `:152-158`.

**It was never blocked, and it was not alone.** It needed no cassette, no scratch
database and no fixture; it was dispositioned *"fix with harness"* alongside its
neighbours and inherited a blocker it did not have — the identical shape task 34 found in
D17. Task 42's pass found the same shape in **D05 and D11**: three of the six so-called
UNBLOCKED entries were never blocked on task 09 at all. Two of the three say so in their
own text. That is what the `BLOCKED-BY:` convention in this file's header exists to catch.

### D14

**`match.py --profile X` can silently prune another profile's valid match
rows.** `prune_orphans` deletes any `job_matches` row for the run's
profile(s) whose `job_id` is not in the loaded fact set
(`backend/match.py:271-274`), but `load_facts` applies the relevance union
of only the **selected** profile(s) (`:351-352`). Running
`match.py --profile frontend` therefore loads facts filtered by `frontend`'s
config alone, and any `frontend` match row for a job that only `tech`'s
config admits would be pruned as an orphan. Whether this is intended is not
determinable from the code — the union exists specifically to avoid this
class of problem, but is applied over `active` profiles or the single
`--profile`, never over all profiles regardless of selection. Blast radius:
manual single-profile runs only (the nightly nine-step run always scores all
active profiles together, so it is not exposed there). Disposition:
**won't-fix, for now** — no task currently owns this and it has not been
observed to fire; the reason it is left open rather than fixed is that its
intended behavior is itself unresolved (the union exists specifically to
avoid this class of problem, but is not applied consistently across
`--profile` and default runs). Revisit before Phase 5's multi-tenancy work
makes `--profile` a routine, rather than exceptional, invocation.

### D15 — fixed

**`score.py` writes `fit_score` and `primary_track` straight from model
output with no coercion, unlike `extract.py`'s `_enum()`/`_int_or_none()`**
(`backend/score.py:372-373`; full write-up and SQL to run first in
`docs/ingestion_tests/04-score-validation.md:38-83`) — this is "audit item
8." Scoring's vocabulary is Title Case with spaces (`Core SWE`, `AI
Integration`, ...), which is a different trap from extraction's snake_case
one: naively reusing `extract._enum()` would *silently rewrite* every stored
value. A drifted `primary_track` is invisible until something renders it
(`match.py` never reads it); an out-of-range or wrongly-typed `fit_score`
persists unclamped. Blast radius: all profiles (score stage). Disposition:
**fixed** — task 08, 2026-07-28.

`score.normalize()` (`backend/score.py`) now returns the exact column values
or `None`, with its own `TRACKS` vocabulary in stored Title Case and a
canonicalising comparison; `update_job_score` takes normalize()'s output and
indexes its keys, so there is no longer a path from a model response to the
table that skips coercion. Covered by `backend/tests/test_score.py`, which
also asserts the trap: `extract._enum()` rewrites all five track names.

**The register was right that this was worth checking before deciding how
much to coerce.** Measured against production on 2026-07-28 (method and full
output in `docs/score-validation.md`): 1,294 rows, `fit_score` between 0 and
95, and exactly **three** off-vocabulary `primary_track` values — all
`frontend_core`, all on the `frontend` profile, all written by
`deepseek-v4-flash`. So the drift is real but rare (3 of 1,237 model-written
rows, 0.24%), which is why the fix is a guard rather than a migration: the
stored form stays Title Case and no existing row is rewritten.

### D43 — fixed

**A tombstone left the previous score in place, and `llm.has_fields` let an
answer that was null in every column through as a row.** Two halves of one
outcome — a row in `job_scores` that reads as a real score and is not one.
Found by task 08 while running D15's diagnostic SQL.

`mark_score_failed`'s `ON CONFLICT` updated only `scored_at` and
`scoring_model` (`backend/score.py`, before this task), so a row
`update_job_score` had already written kept its `fit_score`, `primary_track`
and narrative under a `FAILED:` model label — contradicting this module's own
docstring, which promises a tombstone leaves "`fit_score` left NULL". And
`llm.has_fields` (`backend/llm.py:365-366`) checks that the six keys are
**present**, not that any holds a usable value, so `{"fit_score": null,
"primary_track": null, ...}` passed the write gate.

**Measured, not inferred:** 3 rows in production carry a `FAILED:` label with
a non-NULL `fit_score` (15, 80, 80) and a NULL `primary_track` and NULL
`gap_bridging_angle` — the combination only these two paths together can
produce. Every query that reads `fit_score` without also reading
`scoring_model` believes them. Blast radius: all profiles (score stage);
small in count, but silent by construction. Disposition: **fixed** — task 08:
the tombstone's `ON CONFLICT` now nulls all six narrative columns, and
`score.normalize()` rejects a response with nothing usable in it before it
can be written. The three existing rows are not backfilled — database
contents are staging data, and the next score of those postings overwrites
them correctly.

---

## Loud failure — fix opportunistically; the harness catches regressions

### D16 — fixed

**`score.py`'s `build_prompt` hard-indexes `persona["buckets"]`, but
`profiles.validate()` does not require the `buckets` key**
(`backend/score.py:301-303`; `backend/profiles.py:139-142` lists only
`background_summary`, `strengths`, `honest_gaps`, `scoring_instructions`). A
profile saved without `buckets` validates cleanly, then raises an uncaught
`KeyError` at scoring time. `score_one_job`'s only exception handling around
`build_prompt` is an outer `try/finally` (`:431`, `:462`) that just closes the
connection and re-raises; the inner `try` catches only
`llm.TransientError`/`(RuntimeError, JSONDecodeError)` around `llm.call`
(`:433-445`) and sits *below* the `build_prompt` call at `:432`. Because
`run_for_profile` materializes `pool.map` through `list()` (`:490`), the
`KeyError` takes down the **whole profile's remaining batch** — worse than a
deferred call, because a deferral is at least recorded. Full write-up:
`docs/ingestion_tests/04-score-validation.md:122-177`.

Blast radius: one profile's entire batch per occurrence (score stage). Not
`match.py`-class in blast radius, but the same missing-isolation defect
class as D20. Disposition: **fixed** — task 08, 2026-07-28.

**It was armed, not hypothetical.** The `pursuit` profile is `active` with a
persona that has no `buckets` key (verified 2026-07-28), and the only reason
it has never fired is `daily_narrative_budget = 0` — `select_shortlist` is
asked for zero rows, so `build_prompt` is never reached. The first budget
task 13 sets would have ended that profile's every batch.

**Only one of the two changes task 08 scoped was made, and the other was
deliberately rejected.** `build_prompt` now treats `buckets` as optional and
omits the section entirely when it is absent (the prompt is byte-identical
when it is present, so no cached response or prior comparison is
invalidated), and `score_one_job` guards its body: an unexpected exception
is a new `ERRORED` outcome — one job, nothing written, loud on stderr, and
named separately in `main()`'s summary so it cannot be misread as the
endpoint rate-limiting.

Adding `buckets` to `profiles.validate()`'s required keys was **not** done.
Under the Pursuit scope a persona with no positioning buckets is legitimate —
there is no single target role to bucket against — so requiring the key would
reject a profile that already exists and is active. Doing both would have
converted a scoring-time crash into a save-time one rather than removing it.
The reasoning is left as a comment at `backend/profiles.py:139-149` so the
absence does not read as the oversight it originally was.

### D17

**`google-apify.py`'s `run` variable is referenced before assignment when an
actor's start response already reports `SUCCEEDED`.** `run` is bound only
inside the polling `while` body (`backend/ingest/google-apify.py:179-190`);
a status of `SUCCEEDED` (or anything outside `("READY", "RUNNING")`) at the
*first* check skips the loop entirely, so `run["data"]["defaultDatasetId"]`
at line 190 raises `UnboundLocalError` — not in the caught list at
`:223-224` — and propagates, killing the step rather than counting as an
ordinary query error. This is "audit item 1." Whether Apify can return
`SUCCEEDED` synchronously from run-creation was not confirmed against the
live API. Blast radius: one source (`google-apify`). Disposition: **fix with
harness** — `docs/ingestion_tests/05-fetcher-harness.md` names the exact
fixture needed: `apify-immediate-success.json`.

### D18

**Uncaught `KeyError` on malformed config, before the guarded load
completes.** Two sites: `company["platform"]`/`company["token"]` in
`backend/ingest/ats.py:320-321` (subscripted before the `try` at `:325`,
inside the per-company loop, so one config entry missing either key kills
the whole run); and `bucket["queries"]`/`bucket["daily_budget"]` in
`backend/ingest/google-serpapi.py:213-214` (subscripted inside
`pick_stale_queries_by_bucket`, which runs after `load_query_buckets`'s
`try/except KeyError` at `:300` has already returned — the guard only covers
the top-level `buckets` key, not per-bucket structure). This is "audit item
6." Blast radius: one source each. Contrast: `google-apify.py`'s equivalent
subscripting sits *inside* the function its own `try` wraps
(`docs/ingest/google-apify.md:303-307`), so it is the better-guarded of the
two Google scripts. Disposition: fix opportunistically — move the
subscripting inside the guarded load, matching the apify script's pattern.

### D19

**Normalization/parsing happens outside the per-unit `try` block in four of
six ingest scripts**, so one malformed record's exception kills the entire
run rather than one unit. This is "audit item 7."

- `backend/ingest/ats.py:334` — normalize call outside the fetch-only `try`
  at `:325-332`.
- `backend/ingest/builtin-nyc.py:390` — `parse_page` outside the fetch-only
  `try` at `:382-388`.
- `backend/ingest/google-serpapi.py:324` — normalize outside the `try` at
  `:314-322`.
- `backend/ingest/google-apify.py:231` — normalize outside the `try` at
  `:221-229`.

`weworkremotely.py` gets this right — its parse call is inside the `try` at
`:196-198` (`docs/ingest/weworkremotely.md:295-296`). Blast radius: one
source each, four sources total. Disposition: fix opportunistically — move
each normalize/parse call inside its script's existing `try`.

### D20

**`match.py` has no per-record isolation anywhere in the stage** — the only
write path in the pipeline without `lib/upsert.py`'s per-record SAVEPOINT.
`score_job` is called unguarded at `backend/match.py:290`; a non-numeric
`criteria.json` weight raises an uncaught `TypeError` at `total += delta`
(`:92`). The `executemany` at `:304-316` is a single statement with no
per-row isolation, so one bad tuple aborts the whole batch. Any exception
propagates out of `match_profile` and kills the run **for all profiles**,
including ones already computed but not yet committed. This is "audit item
3," and `docs/ingestion_tests/05-fetcher-harness.md:45-57` notes the same
class recurs in `score.py` (D16) — three of nine pipeline scripts now known
to lack it, making this "a pipeline-wide invariant to test for," not a quirk
of one script.

Blast radius: all profiles, all of `job_matches` (match stage — the only
stage with no external call, which is also the reason isolation was skipped
here in the first place, per the doc's own speculation). Disposition: fix
opportunistically — no task currently owns this specifically; the fetcher
harness (task 09) is the natural place to add regression coverage once a
scratch database exists.

### D21

**`hn-hiring.py` has a hard, unguarded import-time dependency on
`config/relevance.json`.** `relevance.load()` runs at module import
(`backend/ingest/hn-hiring.py:90`, `:152`, into module-level `ROLE_PATTERN` at
`:164`). `_python_role_pattern` guards only `re.error` from pattern
translation (`:158-161`), not the file read itself. A config file that
cannot be read or parsed crashes at import, before `main()` runs and before
the standard `FAILED:` reporting convention applies. Blast radius: one
source (`hn_whoishiring`). Disposition: fix opportunistically.

### D22

**`schema.ensure_schema` raises an uncaught `RuntimeError` if
`public.events` exists in the target database**
(`backend/schema.py:261-266`; nothing catches it at `backend/ingest/ats.py:301`,
and by the same call pattern, every other ingest script). Blast radius: all
ingest (shared `ensure_schema` call). Disposition: **won't-fix** —
`docs/ingestion_tests/05-fetcher-harness.md:19-22` names this "FOOTGUN 2" in
`lib/dbconn.py` and explicitly calls it a *feature* to keep, since it is
what stops a script from running against a database still holding the
legacy `events` table shape.

### D23 — fixed

**A crash between the `hn-hiring.py` ledger commit and the `jobs` upsert
commit permanently strands comments.** The ledger commits once, after the
whole comment loop (`backend/ingest/hn-hiring.py:422`); the `jobs` upsert
commits separately, at the end of its own batch
(`backend/lib/upsert.py:235`). A crash between the two leaves comments
marked seen in `hn_seen_comments` with no corresponding `jobs` row — and
because the ledger is what gates re-fetching, a subsequent normal run would
skip them permanently; only `--reparse` recovers them. This is "audit item
4." No test covers this and no evidence in the journal that it has
occurred. Blast radius: one source (`hn_whoishiring`), unconfirmed
frequency. Disposition: **fix with harness** — task 09 lists this as
naturally expressible as a cassette test (crash-injection between the two
commits).

**Fixed, task 42, 2026-08-01.** The comment loop moved to `read_comments()`
(`backend/ingest/hn-hiring.py:342-410`), which **commits nothing**; the ledger inserts
stay open in the caller's transaction and `upsert()`'s single commit
(`backend/lib/upsert.py:235`) lands both halves together. A crash before that rolls back
both, so the comments are simply re-fetched next run — one wasted request each, against
HN's own free API, versus a posting lost for the life of the thread. The ledger commit was
at `:438`, not `:422` (`:422` is the null-item branch's INSERT).

**Not solved by reordering.** Upserting first and marking seen after leaves the
mirror-image window and would re-fetch every comment in the thread every night until it
closed. Atomicity is the property; ordering only chooses which failure.

Tested against the `hn-hiring` cassette and a scratch schema: `conn.rollback()` after
`read_comments()` **is** the crash, since a process that dies does not run cleanup and the
server rolls its open transaction back. Without the fix, 10 comments are stranded. Both
directions are pinned — nothing survives a crash, everything survives a commit.

### D24

**15 `job_facts` rows are possibly permanently starved at
`facts_version=1`.** They match `select_unextracted_jobs`'s `NOT EXISTS ...
facts_version >= 2` predicate and so should be re-extracted
(`backend/extract.py:184-186`), but `ORDER BY j.first_seen DESC LIMIT 40`
puts the newest eligible rows first every run — if newer eligible rows
keep arriving ahead of them in the queue, these 15 could never be reached.
Whether they are actually starved by ordering, or simply excluded by the
relevance union or a closed status, was not determined; confirming it
requires running the query against live data with the current profile
configs, which is out of scope for a read-only audit. Blast radius: one
source (extract stage), 15 rows currently. Disposition: **won't-fix,
unconfirmed** — no task currently owns this and the number is small (15
rows); a one-line diagnostic query (not a fix) would settle whether it is
real, and should be run before Phase 3's volume increase makes the answer
harder to see, but nothing today depends on the answer.

### D25 — fixed

**The live extraction/scoring model silently differed from the documented
default.** All `job_facts`/`job_scores` rows were written by
`deepseek-v4-flash@api.deepseek.com`, while `backend/llm.py`'s
`DEFAULT_MODEL` and `backend/README.md`'s configuration table both named
`glm-4.5-flash` — three sources (code default, `.env`, docs) giving three
different answers to "what runs in production," with nothing in code
enforcing agreement. This mattered specifically because every
self-consistency figure this refactor's decisions rest on
(`docs/ingestion_tests/README.md`'s 76%/94% numbers) is model-specific.
Blast radius: measurement validity across the whole pipeline (extract +
score stages). **Status: fixed, commit `28f1d0e`**
(`docs/tasks/refactor/tranche_one/01-pin-production-model.md`) — `llm.py`'s
`DEFAULT_MODEL` now pins `deepseek-v4-flash`, and `llm.model_mismatch()`
refuses to start under a different resolved model when
`JOBS_EXPECTED_MODEL` is set, wired into both `extract.py` and `score.py`.

### D36

**`job_ingest_state.claimed_by`/`claim_granted_at` exist but are never set
by `ingest/google-serpapi.py`, only by the contributor API's claim path** —
an asymmetry that already caused a real bug: the pipeline taking over an
expired claim leaves `claimed_by` stale as the previous contributor's id, so
a naive `claimed_by == caller` ownership check on the API side would pass
for a contributor whose claim had already been taken over
(`docs/ingest/google-serpapi.md` Open Questions;
`docs/ingest/contributor-api.md` "`holds_claim` and the takeover problem",
`backend/api/query_claims.py:243-285`). The fix (`claim_granted_at` as a
second condition) was applied API-side only — the root asymmetry in
`job_ingest_state`'s write pattern still exists. Blast radius: cross-component
(google ingest scripts + contributor API, sharing one table). Disposition:
**won't-fix** — already patched at the point that mattered; recorded here so
the next person touching the claim schema knows the asymmetry is load-bearing
for that fix, not an oversight to "complete" by having the ingest scripts set
the same columns.

### D44 — fixed

**`python3 -m evals run` raised `UnboundLocalError` for every task, on every
invocation.** `cmd_run` re-imported `corpus as corpus_mod` inside its
`--golden` branch (`backend/evals/__main__.py:143`, before this task) even
though the module already imports it at `:31`. Python decides local-vs-global
at compile time, so that one line made `corpus_mod` a local for the whole
function — and `:99`, which loads the corpus on every run, referenced it
before assignment. The `--golden` branch that caused it never had to execute.

Found by task 08 running its own definition of done
(`python3 -m evals run --task score --corpus ...`). It is not
score-specific: `--task extract` fails identically, because the failing line
runs before the task is used at all. It was introduced by task 07 (`3a8b42c`,
2026-07-28) alongside the `--golden` flag, so the window was one day.
`evals selfcheck` was unaffected — it has no such re-import — which is
why the gap went unnoticed. Blast radius: the eval harness CLI only, nothing
in the pipeline. Disposition: **fixed** — task 08 deleted the redundant
import; both `--task extract` and `--task score` now run.

---

### D45 — fixed

**`company_ats.status = 'never_found'` holds 35 rows against a true population
of 139, and the 35 are an alphabetical block.** `ats_seed` records a probe
outcome per employer (`backend/migrations/migrate_company_ats.py:98-116`);
`last_probe_outcome = 'not_found'` — "page fetched, no ATS signature", the real
negative — is **139** of its 376 rows. Only **35** of those got a `never_found`
row written back into `company_ats`; **104** never got a row at all.

The 35 are not a sample. Grouped by first letter of `employer_name` they are
`M=8 N=20 O=2 P=5` — a contiguous block, which is the signature of a write-back
that stopped partway rather than of anything about employers. Reproduce:

```sql
SELECT left(employer_name,1), count(*) FROM company_ats
WHERE status='never_found' GROUP BY 1 ORDER BY 1;

SELECT count(*) FROM ats_seed WHERE last_probe_outcome='not_found';        -- 139
SELECT count(*) FROM ats_seed s WHERE s.last_probe_outcome='not_found'
  AND NOT EXISTS (SELECT 1 FROM company_ats a
                  WHERE a.employer_name=s.employer_name AND a.status='never_found');  -- 104
```

**Why it matters more than its size.** `company_ats.status` is what downstream
work sizes itself against. Task 19 names `never_found` as its entire population
(`19-jsonld-parser.md:15-17`), so its brief was written against 25% of the set it
meant to describe. Task 17's roster and task 16's coverage figures read the same
column. Nothing crashes; the numbers are just quietly too small, which is this
system's documented failure mode — *"Silence is this system's failure mode"*
(CLAUDE.md), and *"alert on volume, not errors."*

Found by task 19's coverage spike (`2fecec5`) while assembling its probe
population, not by the original triage pass. The spike worked around it by
probing 35 target rows plus a 20-employer control drawn from `ats_seed`
directly, and the workaround is what surfaced the discrepancy.

**Root cause: two durability cadences on two different axes.** A probe writes
two tables. `record_probe()` leaves an `UPDATE ats_seed` pending on the
connection and the loop committed it **every 20 iterations**; the `company_ats`
rows were buffered in a Python list and flushed **every 50 records**
(`FLUSH_EVERY`). Because one counted *employers* and the other counted
*records*, no choice of constants could align them — and any run that died
before the final flush kept the seed outcome durably while silently discarding
the buffer. `--limit` defaulting to 20 with `ORDER BY last_probed_at NULLS
FIRST, employer_name` made successive runs walk the roster alphabetically,
which is where the block shape comes from.

The database still holds the fingerprint. Three passes ran on 2026-07-28
(`ats_seed.last_probed_at`): 07:14 probed 140 employers, 07:36 probed 40, 07:40
probed 100. Every one of those 280 outcomes is in `ats_seed`. `company_ats`
received rows from the 07:40 pass only, and **exactly 50** of them — `never_found`
35 + `valid` 7 + `unvalidated` 5 + `dead` 3 — which is one flush batch and not a
number any probe result would produce. The 104 shortfall is 71 + 22 from the two
passes that wrote nothing plus 11 from the truncated tail of the third.

Fixed in `backend/tools/ats-discover.py`:

- **One boundary, on the iteration axis.** `commit_batch()` is now the only
  place either table is made durable, called at `i % FLUSH_EVERY == 0` and once
  at the end (`probe_pass()`). `flush()` → `upsert()` commits, and that commit
  lands the pending `record_probe()` UPDATEs in the same transaction, so the
  two tables are partial by the same amount or not at all. `FLUSH_EVERY` is 20.
- **The loop was lifted out of `main()` into `probe_pass()`** so the cadence can
  be tested rather than argued. `tests/test_ats_discovery.py::CadenceTests`
  kills a pass at every one of 60 indices and asserts the two committed sets are
  equal. Against the pre-fix cadence that test fails at 31 of the 60 kill points;
  against the fix it passes at all 60.
- **A dropped record no longer exits 0.** `flush()` still survives one bad batch,
  but `reconcile_seed_outcomes()` re-reads `company_ats` for the batch's ids and
  clears `last_probed_at` / `last_probe_outcome` for any employer whose row is
  absent, so the employer is re-probed instead of being recorded as settled. This
  closes the last one-record-wide version of the same divergence: `upsert()`
  isolates per-record failures with a SAVEPOINT and commits the survivors
  *before* `check_error_rate` raises (`lib/upsert.py:198,:235`), so the seed
  outcome would otherwise have outlived the row. The run then exits 1.
- **Backfill, no network.** `--backfill-never-found` re-derives a row for every
  `ats_seed.last_probe_outcome = 'not_found'` via `ats_discovery.never_found_row()`.
  Applied 2026-07-28: 104 new, 35 unchanged, 0 dropped. `never_found` 35 → **139**;
  `valid` 75, `unvalidated` 5, `dead` 3 all unchanged. A second run reports 139
  unchanged. The 35 original rows keep `discovered_via = 'probe'`; the 104 carry
  `'backfill-from-ats_seed'`.

**Blast radius: reporting and sizing only, never ingest.** `never_found` rows
have `ats = ''` and `token = ''`, and `ingest/ats_sources.py:107-115` filters on
`ats = ANY(HANDLED_PLATFORMS)`, `status = ANY(('valid','unvalidated'))` *and*
`token <> ''` — three independent exclusions. Measured: the roster is 70 rows
before the backfill and 70 after.

**The widened column is still a floor, and is now measurably so.** `never_found`
means *"no ATS URL in the served HTML"*, not *"no ATS"*
(`backend/ats_discovery.py:499-508`). Of the four positive controls with a
verified live board — Datadog, MongoDB, Justworks, Ramp — the probe returned
`not_found` for all four, because their careers pages are client-rendered. All
four now carry a `never_found` row *alongside* their valid `greenhouse`/`ashby`
token row, so the column carries its own falsification: **≥4 of 139 rows are
provably wrong**, and every coverage figure derived from it is a lower bound.
Backfilling 104 rows widens a population that is already false-negative-heavy;
it does not make it more correct, it makes it complete.

Disposition: **fixed** — cadence aligned, backfill applied, 8 tests added (782 →
790). Unchanged and still open: 96 of 376 `ats_seed` rows have `last_probed_at`
NULL and have never been probed at all, which is why the `never_found`
first-letter histogram now runs A–R and stops. That is a separate gap in the
probe's coverage of the roster, not in this write-back.

**Follow-up for whoever owns `tools/jsonld-probe.py`** (not touched here):
`SEED_NOT_FOUND_SQL` at `:1000-1007` selects seed `not_found` rows *without* a
`company_ats` row as its wider control population. That set is now empty by
construction, which is correct behaviour but makes `--extra-sample` a no-op, and
the comment at `:995-999` still says "company_ats holds 35 never_found rows".

---

## Cosmetic — fold into task 34

### D26

**A stale claim about `ats.py` appears in two other files and contradicts
the code.** `backend/lib/text.py:112-114` and
`backend/tests/test_row_identity.py:171` both say "ats.py passes
`unescape=False`," but at this commit `normalize_lever`, `normalize_ashby`,
and `greenhouse_description` all use the default `unescape=True`
(`backend/ingest/ats.py:193`, `:261`, `:291`). `backend/migrations/migrate_ats_descriptions.py:6`
uses the past tense — "ingest/ats.py **passed** `unescape=False`" — and
appears to be the accurate account; the other two comments were not updated
when the behavior changed.

### D27

**5 unused imports in `ats.py`**: `re` (`:118`), `hashlib` (`:119`),
`urllib.request` (`:120`), `timedelta` (`:122`), `ids` (`:132`, used
indirectly through `lib/upsert.py` but never referenced by name in this
file).

### D28

**4 unused imports in `builtin-nyc.py`**: `hashlib` (`:112`), `datetime`,
`timedelta`, `timezone` (`:116`), plus `ids` (`:126`) unreferenced. `http` is
imported only for the `DEFAULT_TIMEOUT` constant, not its retry logic.

### D29

**`weworkremotely.py`'s `parse_posted_at` is called twice on the same
input** — once directly (`:172`) and once nested inside
`text.posted_at_timestamp` (`:173`) — producing the same value both times.
Explicitly flagged in `docs/ingest/weworkremotely.md:412-415` as "duplicated
work rather than a defect," with no comment explaining why the
already-computed value at `:172` is not reused. (This is the known member
named directly in `docs/tasks/refactor/tranche_one/02-triage-audit-defects.md:66-68`.)

### D30

**5 unused imports in `weworkremotely.py`**: `hashlib` (`:77`), `html as
html_module` (`:76`), `datetime`, `timedelta` (`:83`), `ids` (`:93`). `http`
is imported only for the `DEFAULT_TIMEOUT` constant.

### D31

**Retry/backoff usage is inconsistent across the six ingest scripts, with
no comment anywhere explaining the split.** `ats.py`, `hn-hiring.py`, and
`google-apify.py` go through `lib.http.get_json`/`post_json` and get 5
retries with exponential backoff; `weworkremotely.py`, `builtin-nyc.py`, and
`google-serpapi.py` call `urllib.request.urlopen` directly and get one
attempt, no backoff, no `Retry-After`. `lib/http.py:3-5` cites exactly this
scenario — "a single transient 503 from one ATS board failed that company
for the day" — as the reason the module exists. `docs/ingest/weworkremotely.md`
Open Questions: "I could not determine whether this is deliberate or an
incomplete migration." Failures here are counted (as category/query errors),
not silent, so this is a robustness gap rather than a correctness bug — but
it does mean transient upstream errors cost more completeness on three of
six sources than on the other three for no stated reason.

### D32

**3 unused imports in `hn-hiring.py`**: `hashlib` (`:77`), `timedelta`
(`:81`), `ids` (`:92`).

### D33

**`google_jobs_query_stats` accumulates and is read by nothing.**
Written by both `google-serpapi.py:334` and `google-apify.py:240`; the
adaptive-cadence logic it was built for was never implemented
(`backend/google_jobs.py:68-74`). Nothing prunes it; 32 rows currently.

### D34

**22 orphaned `job_ingest_state` watermark rows** keyed
`google_jobs:query:*` do not correspond to any of the 32 slugs in
`config/google-queries.json` — evidently from an earlier query bank.
`pick_stale_queries_by_bucket` only ever selects `WHERE dataset =
ANY(current_slugs)`, so they are inert but permanent; nothing prunes them.

### D35

**`CLAIM_TTL_MINUTES` is documented in `backend/README.md` as a
configuration variable but `google-serpapi.py` never reads it** —
`state.try_claim` is called without a `ttl_minutes` argument
(`backend/ingest/google-serpapi.py:235`), so the library default
(`DEFAULT_CLAIM_TTL_MINUTES = 15`, `backend/lib/state.py:90`) silently
applies instead. No code comment addresses the discrepancy between the
README and the call site.

### D37

**Abandoned Apify actor runs are billed and untracked.** A poll timeout
raises at `backend/ingest/google-apify.py:187-188` and the claim is released
immediately (`:226`), but the actor keeps running on Apify's infrastructure
and keeps billing. The `run_id` exists only inside the exception message,
printed under `DEBUG_PRINT_KEYS` only. No reconciliation against Apify's own
billing exists. Disposition: won't-fix — dollar amounts here are small
(≤$0.15/query) and the fix (persisting and polling abandoned run ids) is
disproportionate engineering for the stakes.

### D38

**`POST /v1/events`'s impression-dedup has a race under concurrent
requests.** The `NOT EXISTS` check is evaluated inside the same `INSERT`
statement (`backend/webapp/jobs.py:307-310`), so two simultaneous impression
posts for the same (profile, job) can both find no prior row and both
insert. There is no unique constraint, deliberately — the table is an
append-only log, not a state store. Disposition: won't-fix — a duplicate
impression row is noise, not incorrect data, in an append-only log.

### D39

**`extract.py` has no lock or claim; two concurrent runs (the nightly
pipeline overlapping `backend/scripts/backfill-facts.sh`) would both select
overlapping batches and double-spend LLM calls** (`backend/extract.py:176-191`).
`ON CONFLICT (job_id) DO UPDATE` means the second write does not error, just
costs twice. Disposition: fix opportunistically — a `FOR UPDATE SKIP LOCKED`
on the selection query would close this cheaply if it is ever observed to
matter.

### D40

**A login-triggered `score.py` run and the nightly run can double-spend.**
Both use the same unlocked `NOT EXISTS` anti-join
(`backend/score.py:234-235` in `select_shortlist`); `ON CONFLICT DO UPDATE`
prevents an error but not the duplicate LLM call. Depends on deployment,
which has not happened. Disposition: fix opportunistically, same shape of
fix as D39.

### D41

**Contributor API's `claim` endpoint has no rate limit beyond the daily
per-contributor cap.** `backend/api/README.md:214-224` names this as a known
gap before opening up: an unmetered claim-loop could lock the whole query
bank and starve the operator's own nightly pipeline. The daily cap counts
`submission_log` rows, and a claim that is never submitted writes no such
row, so a pure claim-loop is uncapped by that mechanism. Blast radius: one
source, never deployed. Disposition: **fix before deploy** — task 24.

### D42

**`hn-hiring.py` re-fetches HN items answering `null` forever.** `if not
comment: continue` (`backend/ingest/hn-hiring.py:409-410`) returns *before*
the ledger insert at `:412`, so an id HN answers with `null` is never marked
seen and is refetched on every subsequent run. This is "audit item 5." Not
data loss — the comment never produced a row either way — but a permanent,
low-volume waste of requests with no comment explaining why null bodies
should behave differently from the deliberate "transient failure, don't
mark seen" convention already used for fetch errors at the same site.
Disposition: fix with harness — task 09 lists this as naturally expressible
as a cassette test (`fixtures/cassettes/hn-item-null.json`).

---

### D66 — fixed

**`GET /v1/jobs` and `GET /v1/jobs/{id}` report `seen` cohort-wide, not per Builder.**
`_EVENT_STATE_JOIN` resolves it from `job_events` with `WHERE e.profile = v.profile`
(`backend/webapp/jobs.py`), and `job_events` has no `app_user_id` column at all — it is
keyed `(profile, job_id)` (`backend/schema.py`, `EVENTS_TABLE`). Thirty Builders share the
`pursuit` profile, so once a second Builder exists, one Builder's impression marks the row
`seen` for all of them.

Found by task 31 while making `dismissed` and `saved` per-Builder. Those two moved to
`builder_job_state`, which carries `app_user_id`; `seen` cannot follow, because it derives
from impressions and impressions live only in `job_events`.

**Invisible today and that is the whole risk.** `manage_app_users.py list` shows one active
`pursuit` labeller, so every value of `e.profile` belongs to one person and the join is
accidentally correct. It becomes wrong on the day a second Builder signs in, silently, with
no error and no changed code. Class: **silent data loss** (a wrong answer reported as a
right one). Disposition: **fix with schema change** —
~~`BLOCKED-BY: job_events has no app_user_id`~~
`UNBLOCKED-BY: job_events.app_user_id` — the column landed with the fix rather than
ahead of it, so this entry was never a queue item; the token is rewritten anyway, because
the header's grep is the mechanism and a stale `BLOCKED-BY:` on a closed entry is the
same invisible-in-both-directions state the nine task-09 entries were in.

**Fixed, 2026-08-01.** `app_user_id TEXT` was added to `job_events`
(`backend/schema.py:678`, in the `add_missing_columns` block on `EVENTS_TABLE`),
`POST /v1/events` writes it from `user.id` (`backend/webapp/jobs.py:837`), and
`_EVENT_STATE_JOIN` now resolves `seen` by `e.app_user_id = %s AND e.job_id = v.id`
(`backend/webapp/jobs.py:291`) instead of `e.profile = v.profile`.

**The profile is gone from the predicate rather than joined beside the user id.** Keeping
`e.profile = v.profile` as an extra conjunct would have preserved the existing
`idx_job_events_profile_job` for free, and it is wrong for the same reason the original
line was: a user id already names exactly one Builder, and re-adding the profile would
silently drop that Builder's own events from before a profile change
(`backend/webapp/manage_app_users.py:136`, `cmd_set_profile` — *"the only supported way to
move a user"*). `idx_job_events_user_job ON job_events(app_user_id,
job_id) WHERE app_user_id IS NOT NULL` (`backend/schema.py:703`) is the analogue that
keeps the per-row lookup off a sequential scan — the same regression
`idx_job_events_profile_job` was added to prevent, one key earlier.

**Nullable and unbackfilled, and that decides which way it fails.** The pre-existing rows
carry NULL, so the join's equality never matches them: an event nobody can be shown to
have generated resolves `seen` to FALSE for everyone rather than TRUE for everyone. A
sentinel would have been worse than NULL for a mechanical reason, not a stylistic one — a
sentinel JOINs, so it would hand every pre-column impression to whichever Builder drew it.
Pinned by `tests/test_event_replay.py`
`TestEventStateIsPerBuilder.test_an_event_written_before_the_column_belongs_to_nobody`.

**Every test for this passes vacuously with one account**, which is the defect's own shape
restated as a test-design constraint; `TestEventStateIsPerBuilder` uses `USER` and
`USER_B` on one profile throughout. With the read-side join reverted and everything else
in place, four of its cases fail on an assertion rather than an error — the two flags,
the detail endpoint, and the NULL-attribution direction.

---

### D67 — fixed

**The same for `applied`, and this one contradicts a written privacy promise.**
`bool_or(e.event = 'applied')` in the same lateral, same cause as D66.

Worse than D66 because `API-CONTRACT-v1.md` and `webapp/jobs.py`'s own
`COHORT_VISIBLE_EVENTS` comment both make applications `private` — *"in a cohort competing
for the same entry-level roles, seeing who else applied is discouraging at best"* — and
`visibility_for("applied")` correctly returns `private` on the event row. The response body
then leaks the same fact anyway: Builder B's list renders `applied: true` on a posting only
Builder A applied to. The control is enforced in the column and defeated in the join.

Not a leak of *identity* — the flag says someone in the cohort applied, not who — but at
N=30 in a shared classroom that is the distinction task 28 spends its whole *small-N
problem* section refusing to rely on.

Found by task 31, same pass as D66. Class: **silent data loss**. Disposition: **fix with
schema change** — ~~`BLOCKED-BY: job_events has no app_user_id`~~
`UNBLOCKED-BY: job_events.app_user_id`.

**Fixed, 2026-08-01, by the same change as D66** — one column, one join, and the two
defects were always one defect seen through two flags. `bool_or(e.event = 'applied')` sits
in the same lateral and is now filtered by the same `e.app_user_id = %s`
(`backend/webapp/jobs.py:291`).

**The privacy claim is now enforced in both places rather than one.**
`visibility_for("applied")` already returned `private` on the event row and always had;
what changed is that the response body stopped contradicting it. Pinned in both the list
and the detail endpoint, because `_STATE_COLUMNS` exists so the two cannot answer the same
question differently and they bind the join's parameters through different code paths —
`list_jobs` through its `params` list (`backend/webapp/jobs.py:352`), `get_job` through a
literal tuple (`:461`). A fix applied to one and not the other would have been caught only
by `TestEventStateIsPerBuilder.test_the_detail_endpoint_answers_the_same_way`.

**What this does NOT change: the 24-hour impression dedup.** It is still keyed
`(profile, job_id)` and not `(profile, job_id, app_user_id)`, so one Builder's render
still suppresses another Builder's impression of the same job for the rest of the window.
That is an OPEN DECISION belonging to the repo owner, recorded in
[`27-event-schema.md`](../tasks/refactor/tranche_five/27-event-schema.md),
[`API-CONTRACT-v1.md`](../tasks/refactor/API-CONTRACT-v1.md) and
[`engagement-events.md`](engagement-events.md). This change makes narrowing it *possible*
for the first time; it does not make the decision. **It is a real remaining hole in the
per-Builder story** — `seen` is now per-Builder in the read path while the write path can
still drop the impression that would have set it — and it is left recorded rather than
closed in passing.

> **The shared fix, noted once for both.** ~~An `app_user_id` column on `job_events`
> closes D66 and D67 together and is also what task 28 needs~~ — the column landed
> 2026-08-01 and D66/D67 are closed above. **The half of this note that is still live is
> task 28**: *"4 Builders saved this"* requires distinct users, no query over
> `(profile, job_id)` can produce one, and `job_events(app_user_id, job_id)` now can.
> Task 28's counting problem is unblocked by this column; its *small-N* privacy problem is
> not, and is not something a column can answer.

---

### D68 — fixed

**`derive_skips` was open at BOTH ends to another Builder's events if the client echoes
their `request_id`** — it read their impressions, and their actions vetoed the skips it
should have derived. `jobs.derive_skips()` selected impressions on
`imp.profile = %s AND imp.request_id = %s` (`backend/webapp/jobs.py:698-701`) and
inherited each row's `app_user_id`; its `NOT EXISTS` matched on
`other.profile = imp.profile` with no owner predicate at all. Thirty Builders share
`pursuit`, so the profile predicate constrains nothing, and the `request_id` predicate
constrains nothing either.

**One defect with two halves**, kept as one entry because they are one wrong idea — that a
`request_id` identifies a render and therefore a Builder — reached from two directions:

| half | what it did | shape |
|---|---|---|
| **fabrication** | derived skips FROM another Builder's impressions, stored under their name | a **false** negative |
| **suppression** | another Builder's action VETOED a skip this Builder's open should have derived | a **lost** negative |

**The second half was found by the fix for the first**, and that is worth keeping as a
pattern rather than as a footnote: narrowing the outer selection to one Builder made it
immediately visible that the inner `NOT EXISTS` had never been narrowed at all. A
half-answered question looks answered. The fabrication half was measured first and fixed
first; the suppression half was flagged in that fix's own "what this does not cover"
section and closed the same day, on the owner's call.

**Nothing binds a `request_id` to the user it was issued to.** `new_request_id()`
(`backend/webapp/jobs.py:164`) mints one per render and its own docstring says *"a client
cannot be trusted to generate it"* — but that is a statement of intent, not an
enforcement. `EventBatch.request_id` is a free-form client string (`:495`),
`validate_batch` checks only that it is non-empty (`:529`), and **there is no issuance
record anywhere**: the id goes out in the list response, rides the opaque cursor across
pages, and comes back on the batch unverified.

**Measured on a scratch schema, 2026-08-01**, before the fix:

> Builder A reports 7 impressions under `req_A`. Builder B posts one `open` at rank 7
> echoing `req_A`. The batch returns `{'recorded': 1, 'derived_skips': 6}`, and
> `job_events` holds `('impression', A, 7)`, `('open', B, 1)`, `('skip', A, 6)`.

Six fabricated negative training rows, for postings B never saw, stored under **A's**
`app_user_id`.

**It predates `app_user_id` and was not introduced by it.** The cross-Builder *read* has
been there since the derivation landed with task 27; before the column those six rows were
merely anonymous, and what the column added was a wrong *name* on the result. That is what
moved it from "note it" to "fix it" — and the reasoning that first dismissed it (*"the
selection is not additionally filtered by `app_user_id` because `request_id` already is
one"*) was written into `jobs.py` as a justification and was wrong. It was disproved by
measuring it rather than by re-reading it.

**It never reached `seen` or `applied`, and that boundary is part of the finding rather
than a mitigation of it.** `_EVENT_STATE_JOIN` matches `event IN ('impression','open')`
and `event = 'applied'`; `skip` is in neither, so none of this was ever visible in a
response body and no Builder could observe another's activity through it. The damage was
confined to L2 training data — which is the entire reason `job_events` exists, and
`job_events` is append-only, so every day the hole stayed open wrote permanently
unremovable wrong rows. That is what decided the fix over the deferral.

Class: **silent data loss** (fabricated rows reported as recorded). Disposition:
**fixed, 2026-08-01.**

**The fix is two conjuncts, one on each end of the derivation:**

- `AND imp.app_user_id = %s` bound to `user.id` (`backend/webapp/jobs.py:734`), with
  `derive_skips` taking the caller's id as a parameter (`:619`, passed at `:857`). Confines
  the derivation to the caller's own impressions.
- `AND other.app_user_id = imp.app_user_id` in the `NOT EXISTS` (`:742`). Confines the veto
  to the caller's own actions.

Together they make the `request_id` predicate a convenience rather than a load-bearing one.
`app_user_id` is still **copied** from the impression rather than stamped from the caller;
the first conjunct is what makes those two agree. Stamping instead would put B's name on a
row carrying A's rank and A's score snapshot — internally inconsistent, and worse.

**The owner match is not a removal.** A job *this* Builder acted on in *this* render must
still be excluded — counting a save as a skip would feed the ranker a negative for its best
outcome — and the derived `skip` rows carry the caller's `app_user_id`, which is what keeps
a second `open` further down the same render idempotent.

**The NULL question one level down resolves cleanly, and the resolution is correct on the
merits rather than convenient.** The outer conjunct already forces `imp.app_user_id`
non-NULL, so the only NULL that can reach `other.app_user_id = imp.app_user_id` is a legacy
row's; `NULL = 'u_123'` is NULL rather than TRUE, the row fails the `EXISTS`, and a
pre-column action event simply stops suppressing. **An event nobody can be shown to have
generated should not veto somebody else's negative.** Asserted rather than reasoned to —
see the third test below, which fails `5 != 6` without the inner conjunct.

**What this still does not cover, stated so it is not read as total:**

- **Renders whose impressions predate the column derive nothing.** NULL cannot satisfy the
  outer equality. Accepted deliberately by the owner: those rows are historical and already
  unattributable, so the practical loss is near zero against a hole that was writing
  unremovable rows daily.
- **`request_id` is still unverified.** The two conjuncts make a borrowed render id harmless
  to *this derivation*, not impossible to send. A batch echoing another Builder's
  `request_id` still writes its own events under that id, so one render id can span two
  Builders' rows. **Nothing reads it that way today** — grepped 2026-08-01, `derive_skips`
  is the only consumer of `job_events.request_id` in the tree; `score.py`, `match.py` and
  `tools/` do not reference the column. It is a constraint on the L2 analysis not yet
  written: `GROUP BY request_id` alone is not a render, `(app_user_id, request_id)` is.
- **The 24-hour impression dedup is untouched** and remains keyed `(profile, job_id)` —
  the OPEN DECISION recorded in D67 and in `engagement-events.md`.

Pinned by five cases in `backend/webapp/tests/test_event_replay.py`
`TestEventStateIsPerBuilder`, each paired with a guard so a broken derivation cannot pass
trivially:

| test | fails without the fix as |
|---|---|
| `test_an_echoed_request_id_cannot_derive_another_builders_skips` | `AssertionError: 6 != 0` |
| `test_a_builders_own_open_still_derives_its_skips` | *(guard — must hold both ways)* |
| `test_another_builders_action_cannot_suppress_my_skip` | `AssertionError: 5 != 6` |
| `test_my_own_action_still_suppresses_my_skip` | *(guard — must hold both ways)* |
| `test_a_pre_column_action_event_does_not_suppress` | `AssertionError: 5 != 6` |

---

## Cross-reference to prior write-ups

For readers arriving from a task file rather than this register:

| Elsewhere called | Here |
|---|---|
| "the original" upsert-discard defect, `ats.py:337` | D01 |
| "audit item 1" (`docs/ingestion_tests/05-fetcher-harness.md:34`) | D17 |
| "audit item 2" (ibid., `:35`) | D01 |
| "audit item 3" (ibid., `:36`, `:45-57`) | D20 (and D16, the same class in `score.py`) |
| "audit item 4" (ibid., `:37`) | D23 |
| "audit item 5" (ibid., `:38`) | D42 |
| "audit item 6" (ibid., `:39`) | D18 |
| "audit item 7" (ibid., `:40`) | D19 |
| "audit item 8" (`docs/ingestion_tests/04-score-validation.md:5`) | D15 |
| the `buckets` `KeyError`, "a second defect" (ibid., `:122-177`) | D16 |
| `weworkremotely.py`'s duplicated `parse_posted_at` call | D29 |

---

### D69 — partially fixed

<a id="d69"></a>

**`tests/test_grants.py` could not see a table that is only ever JOINED.** Its
`sql_strings_in()` kept only string literals containing `SELECT|INSERT|UPDATE|DELETE`, so a
hoisted `LEFT JOIN <table> <alias> ON …` constant — which contains none of those words — was
dropped before `_FROM_JOIN` ever ran. The check therefore worked whenever a table was
**written** and silently skipped tables that are only ever **joined**: it was blind to
read-only tables specifically.

**This is the failure that module's own docstring says it exists to prevent**, one level up:
*"a service that starts cleanly and 500s on that one request — in production, on someone
else's first click, with a permission error nobody was looking for."*

**Found 2026-08-02** when task 28 added `cohort_signal`, named in `webapp/jobs.py` solely in
a join fragment. The webapp suite was **green with no `REQUIRED_TABLES` entry and no
GRANT**, so `verify_schema()` never checked it and the first `GET /v1/jobs` would have been
`permission denied for table cohort_signal`.

**What makes it structural rather than a one-off:** `_BUILDER_STATE_JOIN` is invisible the
same way, and `builder_job_state` was declared **only by luck** — `write_builder_state`'s
real `INSERT INTO` names that table elsewhere in the same file. `cohort_signal` had no such
luck.

Class: **static check with a blind spot in its input filter** — the same family as the
`\y`/`\b` landmine: no error, no red, just a quietly empty answer.

**Fixed for the join-fragment case, 2026-08-02**, by keeping a string that is a statement
**or** a join clause (`_JOIN_CLAUSE`, requiring the `JOIN … ON` shape). The obvious wider
fix — keep anything `_FROM_JOIN` matches — was **measured and rejected**: it admits
`label.py`'s HTML and `onboarding.py`'s error strings and yields "tables" called `memory`,
`the`, `this`, `what`, `you` and `a`, out of prose like *"from the posting, not from
memory"*. Quieting those means listing English words in `_ALIASES`, which is how a real
missing GRANT eventually hides behind a plausible-looking word. The widening admits **2
strings across the package and adds exactly 1 table name** — `cohort_signal`, the genuinely
missing grant. Zero additions in the other five modules.

**DISPOSITION IS PARTIAL, DELIBERATELY. The residue is three-part and two parts are
permanent:**

1. **Non-join fragments with no statement keyword.** A hoisted bare `FROM <table>` tail, a
   WHERE clause, a CTE body, a subquery string. Still dropped. (`UPDATE … FROM` *is* caught —
   `UPDATE` is in `_STATEMENT`.)
2. **A table reached through a view is invisible to any version of this check.** `job_facts`
   appears in **no** SQL string anywhere in `webapp/` — only prose and the declaration — and
   is correctly granted, because `jobs_app` expands to `jobs + job_facts + job_matches +
   job_scores` and a plain view runs with the **caller's** privileges. Those entries come
   from the view definition in `backend/schema.py`, another process's file. **No scanner over
   this package's own strings can derive them.**
3. **A module outside `SERVICE_MODULES` is unscanned.** `profiles` is in real SQL at
   `webapp/schema_web.py:769` — `WHERE NOT EXISTS (SELECT 1 FROM profiles p …)`, running as
   the service role at startup — and that file is not in the tuple, deliberately, because it
   also holds admin-only DDL whose every `CREATE` would read as a table the service needs
   granted. That file now documents this against itself: *"the one place in the package where
   a service-role query's tables are declared by hand and checked by nothing."*

   > **MEASURED 2026-08-02 rather than left as a question, and it surfaces NO missing grant
   > today** — so this part of the residue is future-proofing, not a live defect. Scanning
   > `schema_web.py` yields `app_users`, `oauth_logins` and `profiles`, all already declared;
   > plus `information_schema` and `pg_constraint`, which are catalog names; plus `cascade`,
   > captured because `_FROM_JOIN` matches `UPDATE\s+CASCADE` in `ON DELETE CASCADE ON UPDATE
   > CASCADE`.
   >
   > **`cascade` is task 26's, not pre-existing debt — corrected 2026-08-02 after this note
   > was first written.** `grep "UPDATE CASCADE" backend/webapp/*.py` returns exactly two
   > lines, `schema_web.py:560` (the `builder_profiles_parent` composite FK) and `:606` (a
   > comment about it), and the file carried none before that FK landed the same day. So of
   > the three changes, **two are the pre-existing catalog gap and one is a direct consequence
   > of a table added hours earlier.** Recorded because it decides nothing and clarifies
   > everything: a follow-up that reads as inherited debt gets deprioritised differently from
   > one a fresh change created. The follow-up stays whole rather than split across two tasks
   > — at three small changes, splitting costs more than it clarifies.
   >
   > **The whole job is three small changes:** add `schema_web.py` to `SERVICE_MODULES`, add
   > `cascade` to `_KEYWORDS`, add a catalog predicate for the `pg_*` / `information_schema`
   > namespace. Both additions are principled rather than quieting: `cascade` is SQL grammar
   > following `UPDATE`, which is **exactly** the existing `_KEYWORDS = {"set"}` case (present
   > because `DO UPDATE SET` captures `set`), and the catalog namespace is closed and
   > well-defined — unlike the English words that ruled out the naive `_FROM_JOIN` widening.
   >
   > Deliberately **not** taken on 2026-08-02: it is scope beyond the defect, and landing a
   > scanner change at the commit point would invalidate the report it was being committed
   > against. The measurement is recorded here so the next person inherits an answer rather
   > than a question.
   >
   > `manage_app_users.py` stays excluded regardless — it runs as the admin role and its
   > `CREATE`s would read as tables the service needs granted, as `SERVICE_MODULES`' own
   > comment says.

**Together these are the argument for `REQUIRED_TABLES` staying hand-written rather than
derived**, which is a better justification than the file previously carried. All three are
recorded in `sql_strings_in()`'s docstring under their own heading. **Do not close this
without addressing (1), or restating (2) and (3) as accepted limits.**

---

### D70 — open

<a id="d70"></a>

**`frontend/verify_fixtures.py` hardcodes the tail of the key list it checks, so a new
response field is invisible to it.** `verify_fixtures.py:110-111` builds its expectation as

```python
list_row = tuple(jobs["LIST_COLUMNS"]) + tuple(jobs["STATE_FIELDS"]) + ("rank",)
detail_row = tuple(jobs["DETAIL_COLUMNS"]) + tuple(jobs["STATE_FIELDS"])
```

It reads three constants out of the source with `ast` and then **hardcodes the rest**.
`jobs.COHORT_FIELDS = ("cohort_signal",)` (`webapp/jobs.py:367`) is not read at all.

**Found 2026-08-02**, when task 28 added `cohort_signal` to both endpoints. The fixtures omit
the key, the verifier's expectation omits the key, **the two agree with each other and both
disagree with the source**, and `verify_fixtures.py` exits 0. Confirmed directly: the first
job object in `fixtures/shipped/GET_v1_jobs.json` ends `… dismiss_reason, rank`, while
`jobs.py:499-500` assigns `cohort_signal` between them.

Class: **static check with a blind spot** — the same family as [D69](#d69), found the same
day in a different checker. **The general form is worth more than either instance: a
verifier whose expectation is partly derived and partly hardcoded stops being a derivation
exactly where the hardcoding starts, and that seam is where the next field lands.** Both
defects are a checker that passed while the thing it checks had moved.

It also produces the specific failure `verify_fixtures.py`'s own docstring warns about — a
fixture that is confidently wrong, which is worse than no fixture, because a client author
builds a parser against it.

Disposition: **fix by deriving `COHORT_FIELDS`** rather than extending the hardcoded tail,
and see the verifier go red against the current fixtures before correcting them — a checker
nobody has watched fail is not a checker anyone has tested. If `rank` must stay literal
because the endpoint appends it rather than declaring it, that is acceptable and must be
stated in the docstring, since it is the seam this defect came through.

**Not a task-28 defect.** The field was added correctly and its position is pinned by two
tests on the endpoint side; the checker on the other side could not see it.

---
kind: contract
written: 2026-08-02
generator: none
---

# CLAUDE.md

Context for Claude Code sessions in this repo. Read before starting any task.

## What this is

A job discovery and tracking pipeline, being retargeted from one software engineer's
job search to the Pursuit AI-Native cohort — ~30 Builders, entry-level, AI-adjacent
roles, all industries, NYC.

## Commands

Everything resolves relative to `backend/`, never the repo root. `cd backend` first.

```bash
# Tests. No pytest anywhere; unittest is stdlib and works.
python3 -m unittest discover -s tests            # whole suite
python3 -m unittest tests.test_match             # one module
python3 -m unittest tests.test_match.TestName.test_case   # one case
python3 -m unittest discover -s tests -v         # names, for a skip-vs-pass question

# The nightly run, and any step standalone.
python3 run-daily.py                             # all nine steps, in order
python3 ingest/ats.py                            # every script runs alone
DEBUG_PRINT_KEYS=1 python3 ingest/google-serpapi.py   # verbose, convention everywhere

# After any config/relevance.json edit. Not optional — see the `\y` landmine.
python3 tools/relevance-report.py --dead

# Evals. Frozen fixtures, replay cache; --no-cache only for cost/latency.
python3 -m evals run --task extract --corpus evals/fixtures/corpus-v1.jsonl --model "$SPEC"
python3 -m evals selfcheck --model "$SPEC" --n 120 --repeat 3
```

The webapp is a separate process with its own venv:

```bash
cd backend/webapp
.venv/bin/python -m unittest discover -s tests
.venv/bin/uvicorn app:app --port 8421
```

There is no linter and no formatter configured. `psycopg[binary]` is the pipeline's
only third-party dependency and the intent is that it stays that way; the top level
uses system `python3` with no venv at all. Only `api/` and `webapp/` have venvs, and
both set `include-system-site-packages = false`, so anything missing there is missing
at runtime and nowhere else.

## Layout

**`backend/` holds three deliberately separate processes** — the nightly pipeline at
the top level, `api/` (the contributor work queue, expected to be deprecated) and
`webapp/` (the frontend's backend). Each has its own `.env`, its own venv and its own
Postgres role, and **none imports another**; they share only `schema.py` and `lib/`,
reached by a one-level-up `sys.path` insert. ~~`frontend/` is empty.~~

**`frontend/` is a client, as of 2026-08-02 (task 32).** Plain HTML, one stylesheet, ES
modules — **no build step, no framework, no npm, no `package.json`**, and that is a
constraint to keep, not an accident. The modules are `.mjs` so the same files load in a
browser and under `node` with nothing installed. Run it with `frontend/serve.py`, which
mounts the page on the **API's own origin** (`config.PORT`, 8421) rather than a second
dev server, because the session cookie is the client's only credential and a third origin
neither `FRONTEND_ORIGIN` nor `ALLOWED_ORIGINS` names gets dropped silently by the browser:

```bash
cd backend/webapp && .venv/bin/python ../../frontend/serve.py   # then http://localhost:8421/
python3 frontend/verify_fixtures.py    # fixtures still describe the server
node frontend/check_client.mjs         # client still agrees with the fixtures
```

Both checkers run in the backend suite (`tests/test_frontend_fixtures.py`); the node one
skips where node is absent. Today, Job detail and Saved are built; search, onboarding and
the phone test are not — `docs/tasks/refactor/tranche_six/32-frontend.md` has the table.

**Read through the `jobs_app` view, not the `jobs` table.** The base table is
deliberately unfiltered — `ingest/ats.py` pulls entire company boards, so roughly two
thirds of it is roles this pipeline exists to ignore. The view guarantees the four
fields a listing cannot render without, and those are deliberately *not* `NOT NULL`
constraints: `ingest/builtin-nyc.py` legitimately writes a listing row first and fills
`description_text` on a later pass. Enforce completeness at the read edge, not the
column.

## Architecture invariants

**The four stages are `relevance.py` → `extract.py` → `match.py` → `score.py`.**
Relevance and match are free arithmetic. Extract and score cost LLM calls.

**`job_facts` is shared; scores are per profile.** One extraction per posting, ever.
`job_matches` and `job_scores` are keyed `(job_id, profile)`. This is the property
that makes cost flat in users — do not break it.

**`match_score` orders the list. `fit_score` only annotates it.** Sorting by
`fit_score` would put an LLM call on the critical path for every posting. Stated in
three separate files; keep it true.

**LLMs explain, never rank.** No LLM call may sit between a user and an ordering.

**`score_job()` is pure.** No I/O. Unit-testable and sweepable. Keep it that way.

**A deferral is not a failure.** The endpoint never answering (429, timeout, 5xx)
writes nothing and retries next run; only a model that answered unusably gets a
tombstone row (`scoring_model="FAILED:..."`, NULL `fit_score`). Collapsing the two
would permanently discard postings nobody ever evaluated.

**Versions are cache keys.** Every derived row records the version of everything
upstream; a row is stale iff any recorded version differs from current. On
`job_scores` these are `facts_version`, `persona_sha`, `prompt_version` and
`criteria_version` (`schema.py`, `add_missing_columns` on `SCORES_TABLE`) — landed,
not "being added". `criteria_version` is annotated in that file as recorded for
provenance and deliberately **not** a cache key. There is no `persona_version`,
`features_version` or `model_version`; those names were planned and never built.

**`match_reasons` must survive any ranker change.** Per-rule attribution on every
row. This rules out gradient-boosted trees in favour of linear models, deliberately.

## Landmines

**Postgres word boundary is `\y`, not `\b`.** In Postgres `\b` is BACKSPACE, so a
`\b` pattern silently matches nothing and quietly demotes everything it was meant to
catch. Run `backend/tools/relevance-report.py --dead` after any pattern change.
There is no `tools/` at the repo root; every script this file names lives under
`backend/tools/`.

**Never unpack `upsert()` as a bare three-tuple.** `UpsertResult.__iter__` yields
three values and `.errors` is never read — the defect in at least four ingest
scripts. Use `upsert_checked`.

**Workday `limit` cannot exceed 20.** Ask for 100 and it returns an empty array with
no error, identical to "no more results."

**A throttled page is not the end of a list.** Reconcile collected counts against the
`total` the API returned. One published account lost 1,960 of 2,000 jobs to this.

**Silence is this system's failure mode.** Exhausted keys, revoked keys, blocked
scrapers and changed endpoints all return zero rows rather than raising. Alert on
volume, not errors.

**`deepseek-v4-flash` is the production model.** It does not agree with itself at
temperature 0 — **85.2% [77.6–90.6] on `seniority_level`, 94.8% [89.1–97.6] on
`ai_involvement`**, n=115, both **`agree2`** (task 06). Any measurement without that floor
beside it is uninterpretable. **Name the metric whenever you quote one of these.** The same
run yields `agree2` 94.8%, `pairwise` 90.7% and `unanimous` 87.0% for `ai_involvement`, all
correct and all in circulation; `--repeat 3` is the *run*, not the metric. `AUDIT.md`
§ *The three self-consistency metrics* owns all three and carries the command that
reproduces them from committed data (`DEC-71`). ~~76% / 94%~~ were the provisional **n=17** figures and
are superseded; `DECISIONS.md` § *06 — Was 76% real?* answers no. They are still quoted
in older documents, so check the n before reusing either pair.

## Measurement discipline

Read `docs/MEASUREMENT-TRAPS.md` (promoted from `HANDOFF-match-quality.md` §4). ~~Three
of its seven entries~~ **Several of its entries — the file owns the count** were found only
after the conclusions they invalidated had been written down as fact.

**Never evaluate on the layer you trained on.** L0 is human labels (never train), L1
is `fit_score`, L2 is `job_events`.

**Never select an eval corpus with `ORDER BY first_seen DESC`.** It is ~85%
greenhouse/ashby — clean ATS postings — so it measures the easy sources. Use the
frozen fixtures in `backend/evals/fixtures/`.

**Report average precision as the measurement, precision@20 as the objective.** A
count of twenty cannot resolve the differences being decided on.

**Pin eval sets by sorted `job_id`.** Never train on them, never recycle them.

## Conventions

**`_comment` fields in config JSON are load-bearing documentation.** They record
where numbers came from and — more valuably — what was rejected and why. Every new
config gets them, in the existing style. Read the ones in `config/relevance.json`
before writing new ones.

**Read `docs/DOCS-POLICY.md` before creating or retiring any document.** Seven rules,
and every one of them has a script or is marked unenforced. The two that bind hardest:
every doc declares `kind:` in frontmatter (`contract` / `rationale` / `record` /
`rolling` / `task`, one lifecycle each), and **a figure lives with its instrument in
exactly one document** — everywhere else cites that document. `DEC-66`.

~~**Docs come in two kinds with opposite lifecycles.**~~ **Superseded 2026-08-01 by the
five kinds in `DOCS-POLICY.md`** — the two-kind split was right and too coarse: it had no
name for a dated measurement, which is most of `docs/`, so measurements were maintained as
though they were contracts. The half of it that survives verbatim: hand-written rationale
is written at **decision time**, because the reasoning cannot be reconstructed later.
**`docs/ingest/*.md` are hand-written and marked so** — the frontmatter said
`script:`/`generated:` and no generator was ever written. Treat "never hand-edit" as
applying to a generator that exists, which for this repo is none of them.

**`lib/` is this repo's own code.** It was vendored from another repo and no longer is —
see `lib/__init__.py` and `tests/test_lib_contract.py`, which exists precisely because
code an application owns outright can be quietly rewritten. There is no
`tools/lib-parity.sh` and there never was; the drift check is
`tests/test_row_identity.py`, which pins literal outputs for anything feeding a stored
digest. Still do not change shared semantics there to solve a caller-side problem.

**Cite `file:line` when explaining a claim about the code.** Existing docs do this
throughout and it is why they are trustworthy.

## Working on a task

1. Read the task file in `docs/tasks/refactor/` completely.
2. Read every file it cites, at the lines it cites.
3. State the plan before writing code, including anything in the task that looks
   wrong given what the code actually says.
4. Implement.
5. Run the suite; it should not go down.
   **Run it BEFORE you change anything — that reading is your floor.** Not a number
   written here: ~~**1182** as of 2026-07-31~~ was correct the day it was typed, and on
   2026-08-01 this file, `AUDIT.md` and `HANDOFF.md` held three different values and none
   of them was what the runner printed (`DEC-71`).
   `cd backend && python3 -m unittest discover -s tests`
   `cd backend/webapp && .venv/bin/python -m unittest discover -s tests`
   `pytest` is installed in no interpreter here; `unittest` is stdlib and works.
   ~~It was at 263 tests~~ — that figure predated Phase 1 and was nine times too small
   to catch a regression. **Read the `Ran N tests` line, not a static count**: several
   modules gate on `scratchdb.available()`, and a skip is not a failure. They do run in
   the normal checkout — each such module calls `envfile.load(backend/.env)` before
   evaluating the gate, so an unset shell `DATABASE_URL` does not silence them.
6. Check the task's **Definition of done** item by item and report each.

Some tasks are not implementations:

- **04, 05, 06** are measurements. The deliverable is a number, committed, with its
  method and date. Do not tune anything.
- **22** is a timeboxed spike. The deliverable is a decision. Do not merge code.
- **02** produces a register, not fixes. A half-triaged list is worse than a complete
  one.
- **30** contains an experiment whose result decides the design. Run it first.

## Do not

- Do not add a second definition of the Google Jobs record shape. It was deliberately
  de-duplicated in `0c3ae51`.
- Do not reimplement relevance matching in Python. One implementation, two callers.
- Do not scrape LinkedIn.
- Do not backfill `rank` on existing `job_events` rows. A guessed rank is worse than
  a missing one.
- Do not re-tune on a provisional number. `n=17` is not a result.
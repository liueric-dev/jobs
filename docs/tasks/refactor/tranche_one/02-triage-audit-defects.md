# 02 — Triage the ingest audit defects

**Status:** DONE, `36d83f5`. **Depends on:** nothing. **Blocks:** all of Phase 3.

`docs/ingestion_tests/README.md:7` records that the `docs/ingest/` audit "found 16
defects at `dd49a27`." They are scattered across eleven generated documents, mostly
inside per-source **failure-behaviour tables**, and there is no single list. Build
one before adding five new ingest paths on top of them.

## Why this comes before Phase 3

The decision recorded at the time was *"rather than hand-fix them one at a time, the
decision was to build the thing that would have caught them"* — the evals harness.
That was right. But Phase 3 adds NYC Open Data, USAJobs, Adzuna, Workday, JSON-LD,
iCIMS and nonprofit boards. Any defect that is structural rather than incidental gets
copied into every new script written from the existing ones as a template.

At least one is structural. See task 03.

## Work

### Extract the register

Walk every `docs/ingest/*.md` and pull each row that describes a defect rather than
intended behaviour. The failure tables are the primary source; grep for `discarded`,
`defect`, `silently`, and `never read` to find the rest.

Produce `docs/ingest/DEFECTS.md`:

| field | contents |
|---|---|
| id | `D01`… stable, referenced from task files |
| source doc | `docs/ingest/ats.md:337` |
| site | `backend/ingest/ats.py:337` |
| class | see below |
| blast radius | one source / all ingest / all stages |
| status | open / fixed / won't-fix, with the commit or task that closed it |

### Classify

Three classes, and the class decides the schedule:

| class | meaning | when |
|---|---|---|
| **silent data loss** | the run reports success and rows are missing or wrong | fix now, before Phase 3 |
| **loud failure** | crashes, raises, or fails the run | fix opportunistically; the harness will catch regressions |
| **cosmetic** | misleading comment, duplicated work, dead code | fold into task 34 |

Silent data loss is the only class that justifies delaying Phase 3, because it is the
only class the operator cannot detect by watching the nightly run.

### Known members, to seed the register

Confirmed while writing this plan — not exhaustive, and finding the remainder is the
task:

- **Per-record upsert failures discarded** — `UpsertResult` unpacked as a three-tuple
  via `__iter__` (`backend/lib/upsert.py:157-166`), `.errors` never read.
  Confirmed in `ingest/ats.py:337`, `ingest/builtin-nyc.py:404`,
  `ingest/google-serpapi.py:325`, `ingest/weworkremotely.py:225`. **Silent data loss,
  all ingest.** → task 03.
- **`score.py` `buckets` KeyError** — `docs/ingestion_tests/04-score-validation.md:122`,
  found while tracing the prompt.
- **Audit item 8**, whatever it turns out to be — `04-score-validation.md` says it
  closes it.
- **Duplicated work in `weworkremotely`** — `docs/ingest/weworkremotely.md:414`
  explicitly notes this is "duplicated work rather than a defect, but no comment"
  says so. Cosmetic; task 34.

### Decide, per defect, one of three dispositions

- **Fix now** — silent data loss, or anything Phase 3 would copy.
- **Fix with the harness** — needs task 09's fetcher cassettes to test properly.
  Record the dependency; do not fix blind.
- **Won't fix** — record why. A defect deliberately left open with a reason is
  information; one silently dropped is not.

## Definition of done

- `docs/ingest/DEFECTS.md` exists, lists ≥16 entries, and every entry has a class and
  a disposition.
- Every silent-data-loss entry is either fixed or has a task number.
- `docs/ingestion_tests/README.md:7` links to the register rather than citing a bare
  count.
- The register is referenced from `docs/tasks/pursuit/README.md` so Phase 3 tasks can
  cite specific ids.

## Note on scope

Resist fixing as you go. The value of this task is the *list*; a half-triaged register
with three things fixed is worse than a complete register with nothing fixed, because
the next person cannot tell which rows were examined.

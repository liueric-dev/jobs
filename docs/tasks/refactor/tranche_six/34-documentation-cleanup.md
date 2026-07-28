# 34 — Documentation cleanup

**Status:** todo. **Depends on:** runs alongside every phase; finishes last.
**Blocks:** nothing.

Bring ~9,000 lines of documentation into line with a system that no longer matches it.

## The rule: by document type, not by schedule

Neither "update as you go" nor "regenerate at the end." The repo already contains both
kinds of document with **opposite lifecycles**, and the practice is to apply each
consistently.

**Generated reference** — `docs/ingest/*.md`, eleven files, ~4,600 lines, carrying
YAML frontmatter with `script:`, `commit:`, `generated:`. These are derived artifacts.
**Regenerate at phase boundaries; never hand-edit.** The provenance header is what
makes staleness mechanically detectable — a doc generated at `dd49a27` against a file
that has since changed is visibly stale without anyone noticing.

**Hand-written rationale** — `docs/scoring.md`, `backend/docs/*`, and the `_comment`
fields in `config/*.json`. Write at decision time, because the reasoning cannot be
reconstructed later. `relevance.json`'s *"Rejected alternative: flag rows where
SerpApi's `via` field matches company_name. It catches 160 rows but false-positives on
every company posting to its own careers site"* is information that existed for about
an hour. Regenerate at the end and it is gone.

For hand-written docs the practice is **staleness markers, not continuous rewriting**:
one line at the top the moment a doc becomes wrong, proper fix at a phase boundary.
Three half-updated docs are worse than one honestly-stale doc, because you cannot tell
which is current.

## Dispositions

| document | lines | disposition |
|---|---|---|
| `docs/scoring.md` | 784 | **Keep as current-state reference.** Header noting it describes the pre-Pursuit system; regenerate its measured figures after task 12 |
| `backend/docs/SCORING.md` | 516 | **Archive.** Superseded by `docs/scoring.md`; two hand-written scoring docs is drift. Its cost table is retained in the archive because task 04 supersedes rather than deletes it |
| `backend/docs/HANDOFF-match-quality.md` | 350 | **Split.** §4 (the seven measurement traps) is domain-independent — promote to `docs/MEASUREMENT-TRAPS.md`. The rest is persona-bound findings → `docs/archive/` |
| `backend/docs/HANDOFF-multimachine-google-jobs.md` | 349 | Review against task 24 — some may now be operator documentation rather than a handoff |
| `docs/ingest/*.md` | 4,600 | Regenerate at each phase boundary. Delete the three for retired sources; add nine for the new ones |
| `docs/tasks/job_ingest/` | 726 | **Never rewrite.** Append-only historical record; all five accurately marked done |
| `docs/ingestion_tests/` | 700 | Tasks 03–05 became 07–09 here. Update its README to point at the new tree and record that 05 moved earlier and why |
| `backend/api/README.md` | 237 | Task 24 corrects the "never deployed / expected to be deprecated" line. Verify it did |
| `docs/tasks/README.md` | 68 | Same deprecation note; same correction |
| `backend/docs/DEVELOPER.md` | 263 | **Regenerate at the end.** Its opening gap — "the pipeline scores every job it ingests and delivers none of them" — is closed by task 32 |
| `README.md`, `backend/README.md` | 621 | **Regenerate at the end.** Operational reference; stale operational docs actively mislead |
| `backend/evals/README.md`, `backend/webapp/README.md` | 425 | Update in place as their subsystems change |

## Create

**`docs/archive/`** with a README explaining that everything inside was measured
against the author's software-engineer persona and does not transfer. Every archived
file gets one line at the top: what it measured, when, and what superseded it.

**`docs/MEASUREMENT-TRAPS.md`** — promoted from the handoff. It is the most durable
thing in the repo and it is currently buried in a document about a persona that is no
longer the target. Three of its seven entries were found only *after* the conclusions
they invalidated had been written down as fact; that is worth keeping visible.

**`docs/ingest/DEFECTS.md`** — the register from task 02, kept current as entries close.

## Figures to correct, not delete

Several numbers in the docs are superseded rather than wrong, and the superseded
version is evidence about how the system was tuned. Mark them; keep them.

- `SCORING.md`'s cost table — right model, wrong denomination (task 04)
- `compare-extract.py`'s 95% / 90% self-agreement, cited in
  `criteria.json:_hard_exclude_comment` — likely describes clean sources only (task 06)
- `HANDOFF-match-quality.md`'s 12.7/20 — **relabel explicitly as imitation fidelity
  against a non-target persona**, so nobody quotes it as a quality figure in six months
- `docs/ingestion_tests/README.md`'s n=17 figures — superseded by task 06's n=120

## Keep the `_comment` convention

Every new config file — the cohort `criteria.json`, the cohort `relevance_json`, the
archetype superset, the `role_track` vocabulary, the quota ledger — gets `_comment`
fields in the existing style, recording where numbers came from and what was rejected.

This is the single most valuable documentation practice in the repo. It should survive
the refactor unchanged.

## Definition of done

- Every document above has its disposition applied.
- `docs/archive/` exists with per-file provenance headers.
- `docs/MEASUREMENT-TRAPS.md` promoted.
- `docs/ingest/` regenerated against the final commit; retired sources removed, new
  ones added.
- Superseded figures marked, not deleted.
- No document contradicts a running service.
- Every new config carries `_comment` fields.
- A one-paragraph note at the top of `docs/tasks/pursuit/README.md` recording that
  this tree is complete and what superseded it, so the next refactor starts where this
  one ended.

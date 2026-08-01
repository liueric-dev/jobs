---
kind: task
written: 2026-07-28
generator: none
---

# 01 — Pin the production model

**Status:** DONE, `28f1d0e`. **Depends on:** nothing. **Blocks:** 04, 06, and every cost or
quality figure produced after them.

Make the repo give one answer to "what model runs in production," and make the code
enforce it.

## The disagreement

Three sources, three answers:

| source | says |
|---|---|
| `backend/llm.py:32` | `DEFAULT_MODEL = "glm-4.5-flash"` |
| `backend/docs/SCORING.md` "What it costs" | measured against `deepseek-v4-flash` at `0.14 / 0.0028 / 0.28` per Mtok |
| `docs/ingestion_tests/README.md` | self-consistency measured on `deepseek-v4-flash` |
| **operator, 2026-07-28** | **`deepseek-v4-flash`** — chosen as the cheapest option found |

So the code default is wrong, or is overridden at runtime by `LLM_MODEL` /
`JOB_SCORING_MODEL` and nothing says so. `backend/score.py:50-65` compounds it with a
long comment titled "WHY THE DEFAULT MODEL IS glm-4.5-flash, NOT glm-4.7 — A REAL
DEAD END", describing `glm-4.5-flash` as "the free-tier model."

This is not cosmetic. Task 04 measures quota against whatever the code actually
calls; task 06 re-runs a self-consistency figure that only means something if the
model is known. Both are wrong by default until this lands.

**The upside of the confirmation:** the self-consistency finding —
`seniority_level` 76%, `ai_involvement` 94%, whole-record identical 0 of 17 — was
measured on `deepseek-v4-flash`. It describes production, not a model nobody runs.
That is worse news than it would otherwise have been, and it is why task 06 exists.

## Work

### Establish ground truth

Read the deployed environment, not the source. `backend/.env` and the systemd unit
(`~/.config/systemd/user/jobs-ingest.service`, per `run-daily.py:68`) decide what
actually runs. Record, per stage:

| stage | env var | value in production |
|---|---|---|
| `extract.py` | `LLM_MODEL` | unset in `backend/.env` -- resolves through `JOB_SCORING_MODEL` instead, since both stages share `llm.model()`, which checks `JOB_SCORING_MODEL` before `LLM_MODEL`. Actual: `deepseek-v4-flash`. |
| `score.py` | `JOB_SCORING_MODEL` | `deepseek-v4-flash` (`backend/.env`; base URL `JOB_SCORING_BASE_URL=https://api.deepseek.com`) |
| `evals` | `ModelSpec` | no default -- `evals.__main__`'s `--model` is `required=True`. Every documented invocation (`tools/cost-test.py`, `tools/compare-extract.py`, `evals/README.md`) points at `deepseek-v4-flash@$DEEPSEEK_BASE_URL@...`. |

Extraction and scoring run the **same** model in production -- both resolve
through `llm.model()`, and `.env` only overrides the shared `JOB_SCORING_MODEL`
name, not a stage-specific one. Confirmed against the database too:
`job_facts.extraction_model` is 100% `deepseek-v4-flash@api.deepseek.com`
(5,321 rows, plus 7 tombstoned `FAILED:` under the same model) and
`job_scores.scoring_model` is `deepseek-v4-flash@api.deepseek.com` for every
live score (1,237 rows) and its own 17 tombstones. The one disagreement: 40
`job_scores` rows are tombstoned `FAILED:glm-4.5-flash@api.z.ai` -- pre-pin
scoring attempts that failed under the old default and were correctly marked
rather than silently retried (`fit_score` is NULL on all 40, so nothing
downstream reads a glm-produced score). These are pre-pin artifacts for task
02's register, not a live disagreement.

If extraction and scoring run different models, that is a finding in itself — the
cost table and the self-consistency figures would each describe only one stage.

### `llm.py`

Set `DEFAULT_MODEL = "deepseek-v4-flash"`. Add a module comment recording that the
default is the production model and that changing it invalidates every calibration
figure downstream, in the style of the existing temperature comment at `:44-60`.

### Startup assertion

`extract.py` and `score.py` already log `model=` (`extract.py:440`). Promote that to
an assertion: if the resolved model differs from a `JOBS_EXPECTED_MODEL` pin, refuse
to start rather than silently producing rows under a different model. This mirrors
the schema check `backend/api/app.py:146-149` already does — fail at startup, not
mid-run.

### Provenance

`job_facts.extraction_model` and `job_scores.scoring_model` already exist and are
written. Verify both are populated for recent rows, and that no rows carry a model
string that disagrees with the pin. Any that do are pre-pin artifacts and should be
recorded in the defect register from task 02, not silently re-extracted.

### Documentation

- `backend/docs/SCORING.md` "What it costs" — the model name is correct; add a line
  stating it is the production model, so the table is not read as hypothetical.
- `backend/score.py:50-65` — the dead-end comment concerns a `glm` decision that no
  longer describes this pipeline. Retain the reasoning (it is genuinely useful about
  structured-output support) but retitle it so it does not read as a statement of
  what runs today.

## Definition of done

- `grep -rn "deepseek-v4-flash\|glm-4.5-flash" backend/` returns a single consistent
  story.
- A test asserts `llm.DEFAULT_MODEL` equals the documented production model, so
  future drift fails CI rather than a calibration run six weeks later.
- Both LLM stages refuse to start under an unexpected model.
- The per-stage table above is filled in and committed.

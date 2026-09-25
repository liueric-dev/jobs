# Evaluation tools

`evals/` runs extraction and scoring against fixed corpora so model changes can
be compared without changing the production jobs table. Use the pipeline's
Python environment and configured model credentials.

```bash
cd backend
.venv/bin/python -m evals --help
.venv/bin/python -m evals run --task extract \
  --corpus evals/fixtures/corpus-v1.jsonl --model MODEL
.venv/bin/python -m evals selfcheck --model MODEL --repeat 3 \
  --corpus evals/fixtures/corpus-v2.jsonl
```

Model specs accept `MODEL@BASE_URL@env:KEY_NAME`; keep literal API keys out of
arguments and stored run metadata. Cached responses are useful for comparing
parsing changes. Use `--no-cache` for cost or latency measurements. Running a
model against a corpus can make paid API calls.

The source corpus and cassettes are under `fixtures/`. Run the evaluation
tests with the pipeline suite: `.venv/bin/python -m unittest tests.test_evals`.

# jobs

Daily job-discovery automation, split into two halves.

| | what | state |
|---|---|---|
| [`backend/`](backend/) | the pipeline that finds, dedupes and scores postings, plus the contributor API | live |
| `frontend/` | the surfacing layer — nothing here yet | not started |

## backend/

Pulls tech/AI postings from seven independent sources into one Postgres table,
dedupes them, and has an LLM score each one against a candidate profile. It
**finds and judges** jobs; it does not apply to them, track applications, or do
outreach — those stay manual on purpose.

Start at [`backend/README.md`](backend/README.md) for setup and operation, or
[`backend/docs/`](backend/docs/) for architecture and design history.

```bash
cd backend
python3 -m unittest discover -s tests -t .   # the guard on row identity
python3 run-daily.py                         # what the nightly timer runs
```

Scheduled by a **systemd user timer**, not cron — `jobs-ingest.timer`, midnight
local. See `backend/README.md` for why, and `~/.hermes/scripts/jobs-ingest-status.sh`
for the last run's outcome.

## frontend/

Deliberately empty. `backend/score.py` scores every ingested job but nothing
yet pulls the high-scoring results and presents them — no digest, dashboard or
notification. That gap is the reason this directory exists; see the "No
surfacing layer yet" entry at the top of
[`backend/docs/DEVELOPER.md`](backend/docs/DEVELOPER.md).

Nothing outside this directory should need to change to add one: the pipeline's
output is rows in Postgres (`job_matches` ranked per profile, `job_scores` for
the narrated top slice), not files or an API this half owns.

## Layout note

Everything the backend needs resolves relative to `backend/`, never to this
directory or to the process's working directory — the `sys.path` inserts in
`ingest/`, `tools/`, `migrations/` and `scripts/` each reach exactly one level
up, and the shell scripts `cd` to their own parent. That is what made this
split a pure move: no import changed, and the tree can be relocated again as a
unit.

#!/usr/bin/env python3
"""
Single daily cron entry point for the jobs pipeline -- runs ingest/ats.py
(Greenhouse/Lever/Ashby), ingest/builtin-nyc.py (Built In NYC scrape),
ingest/weworkremotely.py (WWR category RSS feeds), ingest/hn-hiring.py
(HN "Who is hiring?" monthly thread), ingest/google-serpapi.py,
ingest/google-apify.py (Google Jobs via a rotating query bank -- the
Apify step deliberately depends on the SerpApi step running first, see
ingest/google-apify.py's docstring), and score.py (LLM fit
scoring, runs LAST since it scores whatever the other six just ingested)
one after another, in that order, in the same process tree.

WHY A WRAPPER INSTEAD OF A LOCK: all seven scripts write to the same
Postgres instance on the same machine and shouldn't run concurrently. An
earlier version of this solved that with a flock-based lock shared between
independently-scheduled cron jobs -- correct, but more machinery than the
actual problem needed. Since all seven should always run together once a
day anyway, there's no real independent-scheduling requirement to
preserve -- a single cron entry that calls them in sequence guarantees the
same non-overlap with nothing to reason about: no lock file, no flock edge
cases, no way for a stale lock to exist. Locking earns its complexity when
triggers are genuinely independent and don't know about each other; here
there was only ever one trigger pretending to be many.

NOTE ON RUNTIME: score.py makes one LLM call per unscored job
(SCORE_BATCH_SIZE=30 by default), which can add real wall-clock time to
this run depending on the configured model's latency -- unlike the other
six steps, which are all plain HTTP/RSS fetches.

Each sub-script still works fine run standalone for manual testing
(python3 ingest/ats.py) -- this wrapper is just the one path that runs
them automatically together.

BEHAVIOR: all steps always run, even if an earlier one fails -- they're
independent data sources (same reasoning ingest/ats.py itself uses for
per-company failures: one source being down isn't a reason to skip
another). Exit code is non-zero if any sub-script failed.

INSTALL: lives in ~/.hermes/scripts/jobs/ alongside the seven scripts
listed in STEPS.

SCHEDULE (run once to wire it up):
    hermes cron create "0 0 * * *" "" --script jobs/run-daily.py --no-agent \
        --name daily-jobs-ingest --deliver origin
    (subdirectory script paths work fine -- confirmed 2026-07-24 by moving
    this whole pipeline from ~/.hermes/scripts/ into ~/.hermes/scripts/jobs/
    and repointing the existing cron job via
    `hermes cron edit <job_id> --script jobs/run-daily.py`)

TEST BEFORE SCHEDULING:
    python3 run-daily.py
    DEBUG_PRINT_KEYS=1 python3 run-daily.py
    hermes cron run daily-jobs-ingest
"""

import os
import sys
import subprocess

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
STEPS = [
    "ingest/ats.py",
    "ingest/builtin-nyc.py",
    "ingest/weworkremotely.py",
    "ingest/hn-hiring.py",
    "ingest/google-serpapi.py",
    "ingest/google-apify.py",
    "score.py",
]


def run_step(script_name):
    path = os.path.join(SCRIPT_DIR, script_name)
    result = subprocess.run(
        [sys.executable, path],
        cwd=SCRIPT_DIR,
        env=os.environ.copy(),
        capture_output=True,
        text=True,
    )
    return result.returncode, result.stdout, result.stderr


def main():
    failures = []

    for script_name in STEPS:
        returncode, stdout, stderr = run_step(script_name)

        if stdout.strip():
            print(f"[{script_name}] {stdout.strip()}")
        if stderr.strip():
            print(f"[{script_name}] stderr: {stderr.strip()}", file=sys.stderr)

        if returncode != 0:
            failures.append(script_name)
            print(f"[{script_name}] exited with code {returncode}", file=sys.stderr)

    if failures:
        print(f"run-daily: {len(failures)}/{len(STEPS)} step(s) failed: {failures}")
        sys.exit(1)


if __name__ == "__main__":
    main()

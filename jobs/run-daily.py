#!/usr/bin/env python3
"""
Single daily cron entry point for the jobs pipeline -- runs ingest/ats.py
(Greenhouse/Lever/Ashby), ingest/builtin-nyc.py (Built In NYC scrape),
ingest/weworkremotely.py (WWR category RSS feeds), ingest/hn-hiring.py
(HN "Who is hiring?" monthly thread), ingest/google-serpapi.py,
ingest/google-apify.py (Google Jobs via a rotating query bank -- the
Apify step deliberately depends on the SerpApi step running first, see
ingest/google-apify.py's docstring), then the three scoring stages --
extract.py (one LLM call per new posting, shared by every profile),
match.py (free per-profile ranking) and score.py (narratives for the top
of each active profile's ranking) -- one after another, in that order, in
the same process tree.

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

NOTE ON RUNTIME: two of the nine steps make LLM calls and dominate the
wall clock. extract.py makes one per newly-ingested posting -- flat in the
number of profiles, since the facts it produces are shared. score.py makes
at most daily_narrative_budget per ACTIVE profile. The other seven steps
are plain HTTP/RSS fetches or, in match.py's case, arithmetic.

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
#: A step is a script name, or a script name plus arguments. Order matters
#: after ingest: extract turns new postings into shared facts, match turns
#: facts into per-profile rankings, and only then does score spend a call on
#: the top of each ranking. Running score before match would write narratives
#: for yesterday's ordering.
STEPS = [
    "ingest/ats.py",
    "ingest/builtin-nyc.py",
    "ingest/weworkremotely.py",
    "ingest/hn-hiring.py",
    "ingest/google-serpapi.py",
    "ingest/google-apify.py",
    "extract.py",
    "match.py",
    # The warm pass: prepare narratives for profiles that have been active in
    # the last week, so a returning user finds them already written. Dormant
    # profiles cost nothing here -- their narratives are generated on login
    # instead, which is what keeps spend tracking engagement rather than
    # registration.
    ["score.py", "--active-within-days", "7"],
]


def run_step(step):
    script_name = step if isinstance(step, str) else step[0]
    args = [] if isinstance(step, str) else list(step[1:])
    path = os.path.join(SCRIPT_DIR, script_name)
    result = subprocess.run(
        [sys.executable, path, *args],
        cwd=SCRIPT_DIR,
        env=os.environ.copy(),
        capture_output=True,
        text=True,
    )
    return result.returncode, result.stdout, result.stderr


def main():
    failures = []

    for step in STEPS:
        # Label by script name only -- the args are an implementation detail
        # of the schedule, not something a log reader needs on every line.
        script_name = step if isinstance(step, str) else step[0]
        returncode, stdout, stderr = run_step(step)

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

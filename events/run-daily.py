#!/usr/bin/env python3
"""Sequential entry point for the events pipeline.

Mirrors jobs/run-daily.py so both pipelines are driven the same way, and
replaces three separate cron entries (08:00 / 08:30 / 09:00) with one.

    hermes cron create "0 8 * * *" "" --script events/run-daily.py \
        --no-agent --name events-ingest --deliver origin

TEST BEFORE SCHEDULING:
    python3 events/run-daily.py
    DEBUG_PRINT_KEYS=1 python3 events/run-daily.py
    hermes cron run events-ingest

WHY ONE ENTRY POINT
    Three independent cron entries meant three chances to drift: the scripts
    were moved into events/ but the cron entries still named them at the old
    top-level path, so all three silently failed to launch at all. One entry
    is one thing to keep correct.

    Sequential rather than parallel is deliberate. The scripts share the
    `events` table, the geocode cache and the park_locations lookup; running
    them one at a time keeps lock contention at zero and makes the geocode
    cache warm for whoever runs second. None of them is slow enough for
    parallelism to be worth the complexity.

FAILURE POLICY
    Every step always runs -- a failing step never prevents later ones, since
    they ingest independent sources. The exit code is the aggregate signal:
    non-zero if any step failed. Individual scripts already distinguish
    "failed" from "partial" (a WAF block or a missing API key is reported and
    exits 0, because the work is checkpointed and resumes next run), so a
    non-zero exit here means something genuinely needs attention.

    migrate.py is deliberately NOT a step: it is a one-off, and it defaults
    to a dry run anyway.
"""

import os
import subprocess
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
STEPS = [
    "nyc-events-ingest.py",
    "nyc-library-events-ingest.py",
    "ticketmaster-seatgeek-ingest.py",
]


def run_step(script_name):
    result = subprocess.run(
        [sys.executable, os.path.join(SCRIPT_DIR, script_name)],
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
        print(f"events run-daily: {len(failures)}/{len(STEPS)} step(s) failed: "
              f"{failures}")
        sys.exit(1)


if __name__ == "__main__":
    main()

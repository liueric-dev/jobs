#!/usr/bin/env python3
"""
Single daily entry point for the jobs pipeline -- runs ingest/ats.py
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

WHY A WRAPPER: all nine steps write to the same Postgres instance on the
same machine and shouldn't run concurrently. An earlier version solved that
with a flock-based lock shared between independently-scheduled cron jobs --
correct, but more machinery than the problem needed, since all nine should
always run together once a day anyway. A single entry point that calls them
in sequence guarantees the same non-overlap with nothing to reason about.

AND WHY THERE IS A LOCK ANYWAY, in the systemd unit rather than here: the
argument above says a single *trigger* needs no lock, and that is still
true of timer-vs-timer -- systemd already serialises one unit. It does not
cover a hand-run overlapping the scheduled one, and two things now make that
overlap expensive rather than merely untidy. api/ and this pipeline
coordinate through the same job_ingest_state claim row, so two concurrent
runs stop serialising against each other; and the Google steps spend a
metered SerpApi budget, which a double run double-spends. So
jobs-ingest.service wraps this in `flock -n -E 0`, where -E 0 makes "already
running" a silent success rather than a false alarm. The lock lives in the
unit, not here, so a deliberate manual run can still bypass it.

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

ENVIRONMENT: this script establishes its own environment from ./.env rather
than assuming the caller did. The 2026-07-25 00:00 scheduled run failed all
seven steps at once on missing DATABASE_URL and missing API keys, because
`hermes cron` sanitises secrets out of the subprocess environment and nothing
had put the file back. Anything already exported takes precedence over the
file, so the unit's EnvironmentFile= wins and a one-off run can still
override a single key. See lib/envfile.py.

The .env file is read by both systemd and lib.envfile, which do not parse
identically -- stay inside the intersection documented in .env.example.

INSTALL: lives at ~/apps/jobs alongside the nine scripts listed in STEPS.
    python3 -m pip install --user 'psycopg[binary]'
    Nothing else. lib/ is part of this repo, not an installed package.

SCHEDULE: a systemd user timer, not `hermes cron`. The Hermes scheduler
resolves the script path and requires path.relative_to(HERMES_HOME/scripts),
naming symlink escape as a case it deliberately blocks, so this pipeline
became unschedulable there the moment it left ~/.hermes/scripts. Units are in
~/.config/systemd/user: jobs-ingest.{service,timer} plus jobs-failure@.service,
which replaces the `--deliver origin` notification the old scheduler gave free.

    systemctl --user enable --now jobs-ingest.timer
    systemctl --user list-timers jobs-ingest.timer
    journalctl --user -u jobs-ingest.service -n 50

TEST BEFORE SCHEDULING:
    python3 run-daily.py
    DEBUG_PRINT_KEYS=1 python3 run-daily.py
    JOBS_ENV_FILE=/dev/null python3 run-daily.py   # must fail with one line
    systemctl --user start jobs-ingest.service
"""

import os
import sys
import subprocess

from lib import envfile

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

#: Overridable so the "does it fail loudly with no config?" check has something
#: to point at: JOBS_ENV_FILE=/dev/null must produce one actionable line.
ENV_FILE = os.environ.get("JOBS_ENV_FILE", os.path.join(SCRIPT_DIR, ".env"))

#: Steps that cannot do anything useful without these. Checked once here so a
#: misconfigured run reports one actionable line, instead of nine steps each
#: printing their own version of the same failure -- which is exactly what the
#: 2026-07-25 run did (see envfile.py).
REQUIRED_ENV = ("DATABASE_URL",)
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
    # Before anything else: this process IS the environment every step
    # inherits (run_step passes os.environ.copy()), so establishing it here
    # covers all nine at once. Values already exported win -- see
    # envfile.load()'s override=False rationale -- which is what lets the
    # unit's EnvironmentFile= take precedence over this file.
    envfile.load(ENV_FILE)

    missing = [k for k in REQUIRED_ENV if not os.environ.get(k)]
    if missing:
        print(f"run-daily FAILED: {', '.join(missing)} not set and not found "
              f"in {ENV_FILE}. Every step would fail to connect; see "
              f".env.example.", file=sys.stderr)
        sys.exit(1)

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

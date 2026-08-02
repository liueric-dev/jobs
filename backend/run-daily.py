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

The final summary reports written/dropped record counts PER STEP, not just
how many steps exited non-zero. An exit code answers "did it run"; it cannot
tell "ran and wrote nothing" from "ran and dropped everything", and those two
need opposite responses -- the first is a quiet Tuesday, the second is data
loss. The counts come from the `upsert-summary:` line lib.upsert.upsert_checked
logs on every call; see parse_upsert_summaries() below.

ENVIRONMENT: this script establishes its own environment from ./.env rather
than assuming the caller did. The 2026-07-25 00:00 scheduled run failed all
seven steps at once on missing DATABASE_URL and missing API keys, because
`hermes cron` sanitises secrets out of the subprocess environment and nothing
had put the file back. Anything already exported takes precedence over the
file, so the unit's EnvironmentFile= wins and a one-off run can still
override a single key. See lib/envfile.py.

The .env file is read by both systemd and lib.envfile, which do not parse
identically -- stay inside the intersection documented in .env.example.

INSTALL: lives at ~/apps/jobs/backend alongside the nine scripts listed in STEPS.
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
import re
import sys
import subprocess

from lib import envfile
from lib.upsert import SUMMARY_PREFIX

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
    # -- ATS token discovery (task 16) ------------------------------------
    #
    # Both entries are discovery, not ingest, and both run BEFORE ingest/ats.py
    # so a token learned this morning is pulled the same night.
    #
    # ONE step, two phases -- `--nightly` runs both in a single process. They
    # answer different questions at very different costs, but they cannot be
    # two STEPS entries: `volumes` below is keyed by script name, so a second
    # entry for the same script would overwrite the first's written/dropped
    # counts and report one line for both. That is precisely the "ran and
    # wrote nothing" vs "ran and dropped everything" distinction this summary
    # exists to preserve.
    #
    #   MONTHLY, and only when the ats-discovery watermark says it is due:
    #     re-validate every known token. "Are the boards we know about still
    #     alive, and has anything gone stale?" -- ONE request per token,
    #     against APIs that expect programmatic traffic. This is the monthly
    #     re-probe task 16 asks for, and the only thing that catches the
    #     failure it is designed against: not a 404, but a feed still serving
    #     postings filled six months ago.
    #
    #   NIGHTLY: probe up to --limit employers that have no conclusive answer
    #     yet -- newly seeded ones, and ones a WAF refused last time. Capped
    #     so the nightly cost is a few minutes, least-recently-probed first,
    #     so the backlog drains over successive nights and the step then goes
    #     quiet on its own.
    #
    # A full careers-page sweep of the whole roster (`--apply --all`) is ~50
    # minutes of outward HTTP against several hundred employer sites. It is
    # deliberately NOT scheduled: that is a first-run and occasional-refresh
    # operation, run by hand, not something to spend every month unattended.
    ["tools/ats-discover.py", "--apply", "--nightly", "--limit", "40"],
    "ingest/ats.py",
    # After ats-discover.py, so a tenant discovered this morning is pulled the
    # same night, and beside ats.py because the two are the same shape of
    # source. ~8 minutes of nightly window at four tenants -- and that is WITH
    # the upstream gate: without it the same run is 1,366 detail requests and
    # 34 minutes. See docs/ingest/workday.md.
    "ingest/workday.py",
    "ingest/builtin-nyc.py",
    # With the other NYC-scoped source, and before extract.py -- which is the
    # only ordering constraint that matters. Yields ~1.8 relevant postings/day
    # against the task file's 20-60 estimate; kept because it is one documented
    # JSON API with an explicit close date per posting, not because of volume.
    # See docs/ingest/nyc-open-data.md.
    "ingest/nyc-open-data.py",
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
    # registration. (That login path is documented but not yet built -- nothing
    # under webapp/ calls run_for_profile today.)
    #
    # IT PASSES NO --rescore-* FLAG, AND THAT IS THE DECISION, NOT AN OMISSION.
    # job_scores now carries version columns, so a persona edit or a prompt
    # bump can mark stored narratives stale. Acting on that costs LLM calls, so
    # it never happens on a schedule: re-scoring is opt-in, needs an explicit
    # --limit, and is something an operator runs having first read
    # `score.py --stale-report`. This line is the single place the nightly
    # spend is decided, which is why a test asserts it verbatim.
    ["score.py", "--active-within-days", "7"],
    # The cohort badge (tranche_five/28). LAST, and it is the only step whose
    # input is the USERS rather than the postings -- it folds yesterday's saves
    # out of job_events into cohort_signal, from which webapp/ reads a bucket
    # and never an exact count.
    #
    # ORDER IS NOT LOAD-BEARING HERE, unlike extract -> match -> score. It reads
    # job_events, which only webapp/ writes, and jobs.id, which the ingest steps
    # settle. It sits at the end because it is the cheapest step and because a
    # failure in it should not delay the ranking; run-daily runs every step
    # regardless of what failed earlier, so nothing depends on that.
    #
    # NIGHTLY RATHER THAN AT READ TIME IS THE PRIVACY DESIGN, not an
    # optimisation to revisit. A badge recomputed live flips within a session
    # and tells an observer that somebody in the room just saved something,
    # which is the recency channel the suppression rule exists to close. See
    # cohort.py.
    #
    # IT WILL WRITE ZERO ROWS ON A HEALTHY RUN for as long as the cohort is
    # smaller than the floor of three -- two Builders today. Its summary line
    # prints the builder count and the floor beside the posting count for
    # exactly that reason: "0 postings" alone cannot tell a quiet Tuesday from
    # a broken fold, which is the distinction this whole summary exists for.
    "cohort.py",
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


#: One `key=value` pair of a lib.upsert.summary_line(). Parsed rather than
#: passed back structurally because the steps are SUBPROCESSES: giving them a
#: side channel would mean a temp file or an extra fd in nine scripts, where
#: the line they already have to log says everything needed.
_SUMMARY_FIELD = re.compile(r"(\w+)=(\d+)")


def parse_upsert_summaries(text):
    """Total the `upsert-summary:` lines in one step's output.

    Returns (written, errors). `written` counts rows this run actually put in
    the table -- new plus updated. `unchanged` is deliberately excluded: a run
    that re-saw everything and wrote nothing new is a normal quiet day, and
    folding it in would hide exactly the case this summary exists to expose.

    Steps that never upsert (extract, match, score) produce no such lines and
    come back (None, None), which the summary reports as "-" rather than as a
    zero they would be indistinguishable from.
    """
    written = errors = None
    for line in text.splitlines():
        if SUMMARY_PREFIX not in line:
            continue
        fields = dict(_SUMMARY_FIELD.findall(line))
        if "errors" not in fields:
            continue  # not a summary line after all; don't count a partial one
        if written is None:
            written = errors = 0
        written += int(fields.get("new", 0)) + int(fields.get("updated", 0))
        errors += int(fields["errors"])
    return written, errors


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
    #: script_name -> (written, errors), from the upsert-summary lines each
    #: step logs. WHY THIS IS HERE: the old summary printed only
    #: "{n}/{len(STEPS)} step(s) failed", so a step that upserted 400 records
    #: and dropped 100 counted as a clean success. An exit code answers "did
    #: it run"; it cannot distinguish "ran and wrote nothing" from "ran and
    #: dropped everything", and those need opposite responses.
    volumes = {}

    for step in STEPS:
        # Label by script name only -- the args are an implementation detail
        # of the schedule, not something a log reader needs on every line.
        script_name = step if isinstance(step, str) else step[0]
        returncode, stdout, stderr = run_step(step)

        if stdout.strip():
            print(f"[{script_name}] {stdout.strip()}")
        if stderr.strip():
            print(f"[{script_name}] stderr: {stderr.strip()}", file=sys.stderr)

        volumes[script_name] = parse_upsert_summaries(stdout + "\n" + stderr)

        if returncode != 0:
            failures.append(script_name)
            print(f"[{script_name}] exited with code {returncode}", file=sys.stderr)

    # Printed on EVERY run, including a clean one. This pipeline's failure
    # mode is silence -- an exhausted key, a revoked key, a blocked scraper
    # and a changed endpoint all return zero rows rather than raising -- so
    # the thing worth alerting on is volume, and a volume line that only
    # appears when something is already known to be wrong cannot be used for
    # that. "ats 0/0" on a Tuesday is the signal.
    parts = []
    for script_name in (s if isinstance(s, str) else s[0] for s in STEPS):
        written, errors = volumes.get(script_name, (None, None))
        label = script_name.removeprefix("ingest/").removesuffix(".py")
        parts.append(f"{label} -"
                     if written is None else
                     f"{label} {written}/{errors}")

    total_errors = sum(e for _, e in volumes.values() if e)
    print(f"run-daily: {len(STEPS) - len(failures)}/{len(STEPS)} step(s) ok, "
          f"{total_errors} record(s) dropped "
          f"[written/dropped: {', '.join(parts)}]")

    if failures:
        print(f"run-daily: {len(failures)}/{len(STEPS)} step(s) failed: {failures}")
        sys.exit(1)


if __name__ == "__main__":
    main()

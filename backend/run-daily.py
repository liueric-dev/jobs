#!/usr/bin/env python3
"""Run ATS validation and the independent raw-posting ingestion sources.

Known ATS boards are revalidated on their existing 30-day watermark. New
employers are added explicitly with tools/ats-discover.py. Each ingest source
runs even if another fails, and any failure makes the wrapper exit nonzero.
Per-step upsert counts are recorded for tools/volume-check.py. This wrapper
does not extract facts, match profiles, score jobs, or serve a web app.
"""

import os
import re
import sys
import subprocess

import volume_floors
from lib import envfile, pipelinelog
from lib.upsert import SUMMARY_PREFIX

log = pipelinelog.get_logger("run-daily")

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

#: Overridable so the "does it fail loudly with no config?" check has something
#: to point at: JOBS_ENV_FILE=/dev/null must produce one actionable line.
ENV_FILE = os.environ.get("JOBS_ENV_FILE", os.path.join(SCRIPT_DIR, ".env"))

#: Steps that cannot do anything useful without these. Checked once here so a
#: misconfigured run reports one actionable line, instead of every step
#: printing its own version of the same failure -- which is exactly what the
#: 2026-07-25 run did (see envfile.py).
REQUIRED_ENV = ("DATABASE_URL",)
#: A step is a script name, or a script name plus arguments.
STEPS = [
    # Known ATS boards are revalidated when the 30-day watermark is due.
    # New company boards are discovered by an explicit operator run.
    ["tools/ats-discover.py", "--apply", "--nightly", "--known-only"],
    "ingest/ats.py",
    "ingest/workday.py",
    "ingest/builtin-nyc.py",
    "ingest/nyc-open-data.py",
    "ingest/weworkremotely.py",
    "ingest/hn-hiring.py",
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
#: side channel would mean a temp file or an extra fd in every script, where
#: the line they already have to log says everything needed.
_SUMMARY_FIELD = re.compile(r"(\w+)=(\d+)")


def parse_upsert_summaries(text):
    """Total the `upsert-summary:` lines in one step's output.

    Returns (written, errors). `written` counts rows this run actually put in
    the table -- new plus updated. `unchanged` is deliberately excluded: a run
    that re-saw everything and wrote nothing new is a normal quiet day, and
    folding it in would hide exactly the case this summary exists to expose.

    Steps that never upsert (such as ATS validation) produce no such lines and
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
    # covers every step at once. Values already exported win -- see
    # envfile.load()'s override=False rationale -- which is what lets the
    # unit's EnvironmentFile= take precedence over this file.
    envfile.load(ENV_FILE)

    missing = [k for k in REQUIRED_ENV if not os.environ.get(k)]
    if missing:
        log.error(f"run-daily FAILED: {', '.join(missing)} not set and not found "
                  f"in {ENV_FILE}. Every step would fail to connect; see "
                  f".env.example.")
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
            log.error(f"[{script_name}] exited with code {returncode}")

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

    # Append the same counts to .run-volumes.jsonl, keyed by the SAME labels the
    # line above uses, so the floors in config/volume-floors.json are calibrated
    # against exactly the quantity they are checked against.
    #
    # WHY RECORD RATHER THAN CHECK. The floors are evaluated by
    # tools/volume-check.py on its own timer, not here, and the reason is not
    # tidiness: the hardest failure in this system to notice is the run that
    # never happened, and a check inside the run cannot report the run's
    # absence. Writing the file is all this process can usefully do; deciding
    # whether the file looks wrong -- including "the newest entry is thirty
    # hours old" -- is a question only something outside the run can ask.
    #
    # It also keeps a quiet night out of this script's exit code. A source that
    # went silent and a step that crashed need opposite responses, and one
    # alert channel meaning both would very quickly mean neither.
    labelled = {
        script_name.removeprefix("ingest/").removesuffix(".py"): counts
        for script_name, counts in volumes.items()
    }
    if volume_floors.record_run(labelled) is None:
        # Never fatal: every step above has already done its real work, and a
        # full disk here must not turn a successful ingest into a failed unit.
        # Say so, though -- a history that silently stops growing looks exactly
        # like a pipeline that is fine.
        log.warning("run-daily: could not append to "
                    f"{volume_floors.DEFAULT_HISTORY_PATH}; volume-check will see "
                    "this run as missing")

    if failures:
        print(f"run-daily: {len(failures)}/{len(STEPS)} step(s) failed: {failures}")
        sys.exit(1)


if __name__ == "__main__":
    main()

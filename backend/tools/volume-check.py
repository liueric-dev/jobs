#!/usr/bin/env python3
"""The soft-failure alarm: has any source gone quiet, and did the run happen?

jobs-failure@.service already covers HARD failures -- a step that exited
non-zero, a unit that crashed. This is its counterpart, and it is the one that
will actually fire, because nothing in this pipeline fails loudly. An exhausted
API key returns zero rows. A revoked key returns zero rows. A blocked scraper
returns zero rows. A Workday tenant that changed its site path returns zero
rows. None of them raise, and a green systemd unit says all four are fine.

    python3 backend/tools/volume-check.py            # check; exit 1 on findings
    python3 backend/tools/volume-check.py --digest   # the table, always exit 0
    python3 backend/tools/volume-check.py --self-test

WHY A SEPARATE UNIT FROM run-daily.py, restated here because it is the design:
the hardest failure to notice is the run that never happened, and a check at the
end of the run cannot report the run's absence. This reads .run-volumes.jsonl,
which run-daily.py appends to, so "newest entry is 30 hours old" is a finding
like any other. It also keeps a quiet night off jobs-ingest.service's exit code:
"a step crashed" and "a source went quiet" need different responses, and one
alert channel that means both means neither.

EXIT CODES
    0  nothing to report, or --digest
    1  at least one finding -- systemd runs OnFailure=jobs-failure@ and the
       journal tail this prints goes into the notification
    2  bad usage or unreadable config -- a broken checker must not look like a
       clean one, which is the failure mode `--self-test` exists to rule out

--self-test is not decoration. This project has twice shipped a check that could
not fail; the flag feeds a synthetic history that is guaranteed to breach every
declared floor and asserts that this script says so. Run it after ANY edit to
volume_floors.py or config/volume-floors.json.
"""

import argparse
import os
import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import volume_floors as vf  # noqa: E402  (needs the insert above)


def _print_rows(rows, stream=sys.stdout):
    if not rows:
        print("  (no sources evaluated)", file=stream)
        return
    width = max(len(r["source"]) for r in rows)
    for row in rows:
        mark = {"ok": "ok    ", "below": "BELOW ", "skipped": "skip  "}[row["status"]]
        note = ("insufficient history"
                if row["status"] == "skipped" else
                f"floor {row['floor']}")
        print(f"  {mark} {row['source']:<{width}}  "
              f"{row['total']:>6} written over {row['runs']:>3} run(s) "
              f"in {row['window_days']:>2}d   ({note})", file=stream)


def _synthetic_history(floors, now):
    """A history that is full-length for every window and empty of volume.

    Full-length so nothing is skipped for insufficient history -- a self-test
    that produced only `skip` rows would pass while checking nothing, which is
    precisely the class of defect this flag exists to catch.
    """
    longest = max(spec["window_days"] for spec in floors["sources"].values())
    return [
        {"at": (now - timedelta(hours=h)).isoformat(),
         "written": {s: 0 for s in floors["sources"]},
         "dropped": {s: 0 for s in floors["sources"]}}
        for h in range(longest * 24, 0, -1)
    ]


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Alert when a source goes quiet or a nightly run is missing.")
    parser.add_argument("--digest", action="store_true",
                        help="print every source's state and exit 0; for the "
                             "weekly unit, which is a report and not an alarm")
    parser.add_argument("--self-test", action="store_true",
                        help="check a synthetic all-zero history; this run MUST "
                             "report a finding for every floored source")
    parser.add_argument("--floors", default=None, help="override config path")
    parser.add_argument("--history", default=None, help="override history path")
    args = parser.parse_args(argv)

    try:
        floors = vf.load_floors(args.floors)
    except (OSError, ValueError) as exc:
        print(f"volume-check: cannot read floors: {exc}", file=sys.stderr)
        return 2
    if not floors.get("sources"):
        print("volume-check: no sources declared; nothing could ever fire",
              file=sys.stderr)
        return 2

    now = datetime.now(timezone.utc)

    if args.self_test:
        history = _synthetic_history(floors, now)
        findings, rows = vf.check_floors(history, floors, now)
        breached = {f.source for f in findings if f.kind == "below_floor"}
        missing = sorted(set(floors["sources"]) - breached)
        _print_rows(rows)
        if missing:
            print("SELF-TEST FAILED: an all-zero history did not breach "
                  f"{missing} -- this check cannot fail and must be fixed",
                  file=sys.stderr)
            return 2
        print(f"self-test ok: an all-zero history breaches all "
              f"{len(breached)} floored source(s)")
        return 0

    history = vf.read_history(args.history)
    findings, rows = vf.check_floors(history, floors, now)

    if args.digest:
        # The weekly read. Printed in full whether or not anything fired,
        # because "which sources are still alive?" is not a question a
        # findings-only report can answer.
        print(f"jobs volume digest, {now.isoformat(timespec='seconds')} "
              f"({len(history)} run(s) recorded)")
        _print_rows(rows)
        for finding in findings:
            print(f"  ATTENTION  {finding}")
        return 0

    if not findings:
        print(f"volume-check ok: {len(rows)} source(s) evaluated, "
              f"{len(history)} run(s) in history")
        _print_rows(rows)
        return 0

    print("volume-check: FINDINGS", file=sys.stderr)
    for finding in findings:
        print(f"  {finding}", file=sys.stderr)
    print("", file=sys.stderr)
    _print_rows(rows, stream=sys.stderr)
    #: The runbook was deleted 2026-08-02 with the rest of docs/. This prints a
    #: command rather than a path because an operator reading it is already at a
    #: shell, and a bare dead path is what sent them nowhere before.
    print("\nSee 'A source has gone quiet' in:\n"
          "  git show refactor-freeze-2026-08-02:docs/RUNBOOK.md",
          file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())

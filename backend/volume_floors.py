#!/usr/bin/env python3
"""Per-source volume floors: the history file, and the pure check over it.

WHY THIS IS A MODULE AND NOT PART OF run-daily.py

Two reasons, and the second is the one that matters.

`run-daily.py` cannot be imported -- the hyphen makes it not an identifier -- so
anything a test needs to reach has to live beside it. That is the mechanical
reason.

The real one: the check has to be able to fire when the run DID NOT HAPPEN.
That is the easiest failure in this system to miss, and a check that lives at the
end of the run is structurally incapable of reporting the run's absence. So
run-daily.py's only job here is to APPEND what it saw (record_run), and
tools/volume-check.py -- a separate unit on a separate timer -- reads the file
back and decides. Staleness of the newest entry is then just another finding.

THE SHAPE OF A FLOOR, AND WHY IT IS NOT A NIGHTLY NUMBER

A floor is a minimum total over a trailing window of runs, and the window is per
source. Measured over the five nights the journal held on 2026-08-02, a nightly
floor would have fired on four of the nine sources while nothing was wrong:
hn-hiring is a monthly thread and wrote zero every night, nyc-open-data wrote
zero on four of five, weworkremotely ran 0/0/3/2/2. Zero is those sources'
ordinary Tuesday. config/volume-floors.json carries every number with the
journal command that produced it.

check_floors() IS PURE -- no I/O, no clock, no config lookup. It takes the
history, the floors and `now`, and returns findings. That is what makes it
sweepable in tests without a database, a journal or a fake filesystem, and it is
the same discipline score_job() is held to.

WHAT A FINDING IS NOT: a finding is not a failure of the pipeline. A source
below its floor means "go look at that source", which is why the checker exits
non-zero on its own unit rather than turning jobs-ingest.service red. Those two
need different responses and sharing one alert would cost the alert its meaning.
"""

import json
import os
import tempfile
from datetime import datetime, timedelta, timezone

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

#: Appended by run-daily.py, read by tools/volume-check.py. Beside .run.lock and
#: gitignored for the same reason: it is this host's operational state, and one
#: machine's quiet week is not another machine's floor.
DEFAULT_HISTORY_PATH = os.path.join(SCRIPT_DIR, ".run-volumes.jsonl")
DEFAULT_FLOORS_PATH = os.path.join(SCRIPT_DIR, "config", "volume-floors.json")

#: Keep the history bounded without a logrotate dependency. The longest window
#: any source declares is 45 runs (hn-hiring, a monthly thread), so this holds
#: roughly a year of nightly runs -- enough to re-derive every floor in the file
#: from a real distribution rather than from five nights, which is the explicit
#: next step recorded in config/volume-floors.json's `_n`.
MAX_HISTORY_ENTRIES = 400


class FloorFinding:
    """One source that is below its floor, or one run that never arrived.

    A class rather than a tuple because these are formatted in three places --
    the CLI, the digest and the test assertions -- and a positional 4-tuple read
    at each of them is how a swapped pair of ints survives review.
    """

    def __init__(self, kind, source, detail):
        self.kind = kind          # "below_floor" | "stale" | "no_history"
        self.source = source      # source label, or "" for run-level findings
        self.detail = detail

    def __repr__(self):
        where = f" {self.source}" if self.source else ""
        return f"{self.kind}{where}: {self.detail}"

    __str__ = __repr__


def load_floors(path=None):
    """Read config/volume-floors.json, dropping the `_`-prefixed documentation.

    The `_comment` fields are load-bearing prose for a human and noise to the
    checker; stripping them here rather than at every read site means a new
    `_note` can be added to the config without touching code.
    """
    with open(path or DEFAULT_FLOORS_PATH, encoding="utf-8") as fh:
        raw = json.load(fh)
    sources = {
        name: spec
        for name, spec in raw.get("sources", {}).items()
        if not name.startswith("_")
    }
    return {
        "max_run_age_hours": raw.get("max_run_age_hours"),
        "sources": sources,
    }


def record_run(volumes, path=None, when=None, max_entries=MAX_HISTORY_ENTRIES):
    """Append one run's per-source written counts to the history file.

    `volumes` is run-daily.py's {script_name: (written, errors)} map. `written`
    of None means the step logged no upsert-summary line at all -- extract,
    match and score never upsert, and ats-discover skips its monthly phase --
    which is NOT the same as zero and is stored as null so the distinction
    survives into the check.

    NEVER RAISES. This runs at the very end of a nightly pipeline that has
    already done all of its real work, and a full disk or a bad permission here
    must not turn a successful ingest into a failed unit. It returns the path on
    success and None on failure, and the caller prints the reason. Losing one
    night of history costs the check one night of window; losing the run costs a
    night of ingest.
    """
    path = path or DEFAULT_HISTORY_PATH
    when = when or datetime.now(timezone.utc)
    entry = {
        "at": when.astimezone(timezone.utc).isoformat(),
        "written": {
            name: (None if written is None else int(written))
            for name, (written, _errors) in volumes.items()
        },
        "dropped": {
            name: (None if errors is None else int(errors))
            for name, (_written, errors) in volumes.items()
        },
    }
    try:
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry, sort_keys=True) + "\n")
        _trim(path, max_entries)
        return path
    except OSError:
        return None


def _trim(path, max_entries):
    """Keep the newest `max_entries` lines, replacing the file atomically.

    Rewrite-in-place would leave a truncated history behind a crash, and a
    truncated history is worse than a long one: it silently shortens every
    window and turns real findings into `insufficient history` skips.
    """
    try:
        with open(path, encoding="utf-8") as fh:
            lines = fh.readlines()
    except OSError:
        return
    if len(lines) <= max_entries:
        return
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(path) or ".", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.writelines(lines[-max_entries:])
        os.replace(tmp, path)
    except OSError:
        try:
            os.unlink(tmp)
        except OSError:
            pass


def read_history(path=None):
    """Parse the history file, oldest first. A missing file is an empty history.

    Unparseable lines are SKIPPED rather than fatal. A half-written final line
    -- the machine lost power mid-append -- must not stop the check from
    reporting on the twenty good runs above it, because the check's whole job is
    to still work on a morning when something went wrong.
    """
    path = path or DEFAULT_HISTORY_PATH
    entries = []
    try:
        with open(path, encoding="utf-8") as fh:
            lines = fh.readlines()
    except OSError:
        return entries
    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            entry = json.loads(line)
        except ValueError:
            continue
        if isinstance(entry, dict) and "at" in entry:
            entries.append(entry)
    entries.sort(key=lambda e: e["at"])
    return entries


def _parse_at(value):
    try:
        parsed = datetime.fromisoformat(value)
    except (TypeError, ValueError):
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def window_totals(history, source, window_days, now):
    """(total written, runs counted) for `source` over the trailing window.

    A `null` written -- the step logged no upsert summary -- contributes 0 to the
    total but still COUNTS as a run, because the run happened. The alternative,
    skipping it, would let a step that has started failing to emit its summary
    line quietly extend its own window forever and never reach the floor test.
    """
    cutoff = now - timedelta(days=window_days)
    total = 0
    runs = 0
    for entry in history:
        at = _parse_at(entry.get("at"))
        if at is None or at < cutoff or at > now:
            continue
        runs += 1
        written = (entry.get("written") or {}).get(source)
        if isinstance(written, int):
            total += written
    return total, runs


def check_floors(history, floors, now):
    """Pure. Returns (findings, rows) for the history against the floors.

    `rows` is every source's state whether or not it fired -- the digest prints
    it, because a table that only appears when something is wrong cannot answer
    "is this source still alive?", which is the question a weekly read is for.
    That is the same argument run-daily.py:272-277 makes for printing the volume
    line on clean runs.

    Findings, in the order they are worth reading:

      no_history  nothing has ever been recorded, or nothing within any window.
                  Reported once at run level, not once per source -- nine copies
                  of "there is no history" is not nine problems.
      stale       the newest run is older than max_run_age_hours. THE RUN THAT
                  DID NOT HAPPEN. Deliberately first among per-run findings,
                  because when it fires every source is below its floor for a
                  reason that has nothing to do with the sources.
      below_floor a source wrote less than its floor over its window, with at
                  least `window_days` of history covering it.
    """
    findings = []
    rows = []

    if not history:
        findings.append(FloorFinding(
            "no_history", "",
            "no runs recorded yet -- run-daily.py has not completed since "
            "volume recording landed, or the history file was removed"))
        return findings, rows

    newest = _parse_at(history[-1].get("at"))
    max_age = floors.get("max_run_age_hours")
    if newest is not None and max_age:
        age_hours = (now - newest).total_seconds() / 3600.0
        if age_hours > max_age:
            findings.append(FloorFinding(
                "stale", "",
                f"newest run is {age_hours:.1f}h old, limit {max_age}h "
                f"(at {newest.isoformat()}) -- the nightly run did not complete"))

    oldest = _parse_at(history[0].get("at"))
    span_days = ((now - oldest).total_seconds() / 86400.0) if oldest else 0.0

    for source, spec in sorted(floors.get("sources", {}).items()):
        floor = spec["floor"]
        window_days = spec["window_days"]
        total, runs = window_totals(history, source, window_days, now)

        # A window is only meaningful once the history REACHES BACK far enough
        # to cover it. Alerting on day one of a fresh install -- or the morning
        # after a restore -- teaches the reflex that ignores the channel before
        # it has ever been right once.
        #
        # THE TEST IS THE SPAN OF THE HISTORY, NOT THE NUMBER OF RUNS IN THE
        # WINDOW, and getting that wrong is how this check would have quietly
        # stopped checking. `runs >= window_days` is the obvious form and it is
        # wrong for a NIGHTLY pipeline: a 3-day window over one run a night
        # holds two or three runs depending on where the timer's jitter lands,
        # so the three-day sources would have reported `skipped` on most days
        # while the checker exited 0 and looked healthy. That is precisely the
        # class of defect --  a check that cannot fire -- this file's tests
        # exist to rule out, and it was found by running the CLI against a
        # synthetic healthy history rather than by reading the code.
        #
        # `runs == 0` is also a skip rather than a breach: no runs in the window
        # means the pipeline is not running, which the `stale` finding above
        # already says with the right words. Reporting it a second time per
        # source would bury the one line that names the actual cause.
        if span_days < window_days or runs == 0:
            rows.append({
                "source": source, "total": total, "floor": floor,
                "window_days": window_days, "runs": runs, "status": "skipped",
            })
            continue

        status = "below" if total < floor else "ok"
        rows.append({
            "source": source, "total": total, "floor": floor,
            "window_days": window_days, "runs": runs, "status": status,
        })
        if status == "below":
            findings.append(FloorFinding(
                "below_floor", source,
                f"wrote {total} over {runs} run(s) in {window_days}d, "
                f"floor {floor}"))

    return findings, rows

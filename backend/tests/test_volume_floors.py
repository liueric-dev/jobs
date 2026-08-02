"""Volume floors: the alarm can fire, and it does not fire on a normal week.

WHAT THIS PINS, AND WHY BOTH HALVES ARE NECESSARY

This system's failure mode is silence -- an exhausted key, a revoked key, a
blocked scraper and a moved endpoint all return zero rows and raise nothing --
so the alarm that catches them is the only thing standing between "a source
died" and "hiring has been slow lately". An alarm like that has exactly two ways
to be worthless, and a test suite that checks one of them is worse than none:

  1. IT CANNOT FIRE. This project has twice shipped a check that could not fail;
     `test_backfill_is_resumable_and_idempotent` skipped silently for its entire
     life. So: an all-zero history must breach every declared floor, and the
     assertion is over the floors in config/volume-floors.json rather than over
     a fixture, so a source added there without a floor is a failing test rather
     than a source nobody is watching.

  2. IT FIRES ON A NORMAL WEEK. An alarm that cries wolf teaches the reflex that
     retires all the others. So the real five nights recovered from the journal
     on 2026-08-02 -- the same numbers config/volume-floors.json was calibrated
     from, reproduced in _REAL_RUNS below -- must produce no findings at all.

WHY THE REAL NUMBERS ARE COPIED IN HERE rather than read from a live journal or
a database: this suite runs offline and must never be a flake. They are a
`record` in the DOCS-POLICY sense -- frozen at their date, with the command that
produced them written beside them in config/volume-floors.json's `_instrument`.
If the floors are re-derived from a longer history later, this fixture is
evidence of what they used to pass against and should be added to, not replaced.

Everything here is pure: volume_floors.check_floors() takes the history, the
floors and `now`, so there is no clock, no filesystem and no database in any of
these assertions. The two tests that do touch the filesystem use a tempdir and
say so.
"""

import json
import os
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import volume_floors as vf  # noqa: E402

BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

NOW = datetime(2026, 8, 2, 9, 0, tzinfo=timezone.utc)

#: The five nightly runs the journal held on 2026-08-02, oldest first, exactly
#: as run-daily.py's `written/dropped:` line reported them. `None` is a step that
#: logged no upsert-summary at all -- workday predates the journal window,
#: ats-discover's monthly phase was not due -- which is deliberately not zero.
_REAL_RUNS = [
    {"tools/ats-discover": 94, "ats": 671, "workday": None, "builtin-nyc": 67,
     "nyc-open-data": 354, "weworkremotely": 0, "hn-hiring": 0,
     "google-serpapi": 68, "google-apify": 5},
    {"tools/ats-discover": 29, "ats": 1058, "workday": None, "builtin-nyc": 61,
     "nyc-open-data": 0, "weworkremotely": 0, "hn-hiring": 0,
     "google-serpapi": 56, "google-apify": 7},
    {"tools/ats-discover": 19, "ats": 1143, "workday": None, "builtin-nyc": 69,
     "nyc-open-data": 0, "weworkremotely": 3, "hn-hiring": 0,
     "google-serpapi": 62, "google-apify": 8},
    {"tools/ats-discover": None, "ats": 955, "workday": 73, "builtin-nyc": 63,
     "nyc-open-data": 0, "weworkremotely": 2, "hn-hiring": 0,
     "google-serpapi": 59, "google-apify": 5},
    {"tools/ats-discover": None, "ats": 105, "workday": 29, "builtin-nyc": 57,
     "nyc-open-data": 0, "weworkremotely": 2, "hn-hiring": 0,
     "google-serpapi": 57, "google-apify": 7},
]


def _history(per_run, now=NOW, spacing_hours=24):
    """Turn a list of {source: written} into a history, newest last."""
    n = len(per_run)
    return [
        {"at": (now - timedelta(hours=spacing_hours * (n - i))).isoformat(),
         "written": written, "dropped": {}}
        for i, written in enumerate(per_run)
    ]


def _full_history(floors, written, now=NOW):
    """One entry per hour for the longest declared window.

    Long enough that no source is skipped for insufficient history -- a check
    over a short history reports `skipped` for everything and would pass while
    asserting nothing.
    """
    longest = max(s["window_days"] for s in floors["sources"].values())
    return _history([dict(written) for _ in range(longest * 24)],
                    now=now, spacing_hours=1)


class TestConfigIsUsable(unittest.TestCase):
    """The shipped config parses and declares enough for the check to mean
    something. A floors file with no sources is a checker that exits 0 forever."""

    def setUp(self):
        self.floors = vf.load_floors()

    def test_ships_sources_and_an_age_limit(self):
        self.assertTrue(self.floors["sources"], "no floored sources declared")
        self.assertTrue(self.floors["max_run_age_hours"],
                        "no max_run_age_hours: the run that never happened "
                        "would never be reported")

    def test_every_source_declares_a_floor_and_a_window(self):
        for name, spec in self.floors["sources"].items():
            with self.subTest(source=name):
                self.assertIsInstance(spec.get("floor"), int)
                self.assertIsInstance(spec.get("window_days"), int)
                self.assertGreater(spec["floor"], 0, "a floor of 0 never fires")
                self.assertGreater(spec["window_days"], 0)

    def test_every_source_records_where_its_number_came_from(self):
        """`_comment` fields in config JSON are load-bearing documentation --
        they record what was rejected and why, which is the half that cannot be
        reconstructed later. A floor with no provenance is a number someone
        will re-tune blind."""
        for name, spec in self.floors["sources"].items():
            with self.subTest(source=name):
                self.assertTrue(spec.get("_comment", "").strip(),
                                f"{name} has a floor and no rationale")

    def test_floored_names_match_the_labels_run_daily_prints(self):
        """The floors are keyed by run-daily.py's label -- the script name with
        `ingest/` and `.py` stripped (run-daily.py:281). A typo here is a source
        that is silently never checked, which looks exactly like a source that
        is fine."""
        import re
        with open(os.path.join(BACKEND_DIR, "run-daily.py"),
                  encoding="utf-8") as fh:
            source = fh.read()
        steps = source[source.index("STEPS = ["):source.index("\ndef run_step")]
        labels = {
            m.removeprefix("ingest/").removesuffix(".py")
            for m in re.findall(r'"([\w/\-]+\.py)"', steps)
        }
        unknown = set(self.floors["sources"]) - labels
        self.assertFalse(unknown,
                         f"floors keyed by names no step produces: {unknown}")


class TestTheAlarmCanFire(unittest.TestCase):
    """Half one: an all-zero history must breach every floor."""

    def setUp(self):
        self.floors = vf.load_floors()

    def test_all_zero_history_breaches_every_declared_floor(self):
        history = _full_history(self.floors, {s: 0 for s in self.floors["sources"]})
        findings, rows = vf.check_floors(history, self.floors, NOW)
        breached = {f.source for f in findings if f.kind == "below_floor"}
        self.assertEqual(breached, set(self.floors["sources"]),
                         "a source with a floor that a history of zeros does "
                         "not breach is not being watched at all")
        self.assertFalse([r for r in rows if r["status"] == "skipped"])

    def test_a_missing_source_key_is_treated_as_zero_not_as_absent(self):
        """A step that stops emitting its summary line entirely -- it crashed
        before its first upsert, or its name changed -- must not become
        invisible to the check. `written` absent counts as no rows, because no
        rows is what reached the table."""
        history = _full_history(self.floors, {})
        findings, _ = vf.check_floors(history, self.floors, NOW)
        breached = {f.source for f in findings if f.kind == "below_floor"}
        self.assertEqual(breached, set(self.floors["sources"]))

    def test_one_dead_source_among_healthy_ones_is_reported_alone(self):
        """The failure this whole design is for: eight sources fine, one
        returning zero. A global floor over the run total cannot see this,
        because ats alone outweighs everything else by an order of magnitude."""
        written = {s: spec["floor"] * 10 for s, spec in self.floors["sources"].items()}
        written["google-serpapi"] = 0
        history = _full_history(self.floors, written)
        findings, _ = vf.check_floors(history, self.floors, NOW)
        self.assertEqual([f.source for f in findings if f.kind == "below_floor"],
                         ["google-serpapi"])

    def test_a_run_that_never_happened_is_reported(self):
        """The easiest failure in the system to miss, and the reason the check
        lives outside run-daily.py: a check inside the run cannot report the
        run's absence."""
        floors = vf.load_floors()
        stale_now = NOW + timedelta(hours=floors["max_run_age_hours"] + 2)
        history = _full_history(floors, {s: 10 ** 6 for s in floors["sources"]})
        findings, _ = vf.check_floors(history, floors, stale_now)
        kinds = [f.kind for f in findings]
        self.assertIn("stale", kinds,
                      "volume was healthy so nothing else fired -- if staleness "
                      "does not fire here, a dead pipeline reports clean")

    def test_an_empty_history_says_so_rather_than_passing(self):
        findings, rows = vf.check_floors([], vf.load_floors(), NOW)
        self.assertEqual([f.kind for f in findings], ["no_history"])
        self.assertEqual(rows, [])

    def test_the_script_self_test_passes_and_exits_zero(self):
        """`volume-check.py --self-test` is the operator's version of the two
        assertions above, and the runbook tells them to run it after any floor
        edit. Wiring it in here is what keeps that instruction honest."""
        result = subprocess.run(
            [sys.executable, os.path.join(BACKEND_DIR, "tools", "volume-check.py"),
             "--self-test"],
            capture_output=True, text=True, cwd=BACKEND_DIR)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


class TestTheAlarmIsQuietOnANormalWeek(unittest.TestCase):
    """Half two: the real five nights must produce nothing."""

    def setUp(self):
        self.floors = vf.load_floors()
        self.history = _history(_REAL_RUNS)

    def test_the_five_measured_nights_produce_no_findings(self):
        findings, _ = vf.check_floors(self.history, self.floors, NOW)
        self.assertEqual(findings, [], f"false alarm on real data: {findings}")

    def test_the_worst_real_night_for_ats_does_not_fire(self):
        """ats wrote 1143 one night and 105 another with nothing wrong either
        time. A floor tight enough to see that swing would fire most weeks,
        which is why the shipped floor is an order of magnitude below the
        observed window minimum."""
        rows = {r["source"]: r
                for r in vf.check_floors(self.history, self.floors, NOW)[1]}
        self.assertEqual(rows["ats"]["status"], "ok")

    def test_the_monthly_and_intermittent_sources_are_not_called_outages(self):
        """hn-hiring is one monthly thread and wrote zero on all five nights;
        nyc-open-data wrote zero on four of five. A per-night floor would have
        fired on both. They are `skipped` here only because five nights is less
        than their window -- which is the honest answer, not a pass."""
        rows = {r["source"]: r
                for r in vf.check_floors(self.history, self.floors, NOW)[1]}
        for source in ("hn-hiring", "nyc-open-data", "weworkremotely"):
            with self.subTest(source=source):
                self.assertNotEqual(rows[source]["status"], "below")

    def test_a_nightly_pipeline_is_actually_checked_and_not_perpetually_skipped(self):
        """THE HOLE THIS CHECK NEARLY SHIPPED WITH.

        The sufficiency test was first written as `runs >= window_days`, which
        is wrong for a pipeline that runs ONCE A NIGHT: a 3-day window over one
        run a night holds two or three runs depending on where the timer's
        jitter lands, so the four sources that run every night reported
        `skipped` on most days while the checker exited 0 and looked healthy.
        A check that reports "ok" while evaluating nothing is the exact defect
        this file's first paragraph is about, and it was found by running the
        CLI against a synthetic healthy history rather than by reading the code.

        So: a fortnight of ordinary nightly runs must leave every short-window
        source actually EVALUATED."""
        fortnight = _history([{s: 0 for s in self.floors["sources"]}
                              for _ in range(14)])
        _, rows = vf.check_floors(fortnight, self.floors, NOW)
        by_source = {r["source"]: r for r in rows}
        for source, spec in self.floors["sources"].items():
            if spec["window_days"] > 14:
                continue
            with self.subTest(source=source):
                self.assertNotEqual(
                    by_source[source]["status"], "skipped",
                    f"{source} has a {spec['window_days']}d window and 14 "
                    "nightly runs of history, and is still not being checked")

    def test_no_runs_in_the_window_is_a_skip_not_nine_breaches(self):
        """When the pipeline stops, `stale` names the cause in one line. Nine
        below_floor findings on top of it would bury the one line worth reading."""
        old = _history([{s: 10 ** 6 for s in self.floors["sources"]}
                        for _ in range(60)],
                       now=NOW - timedelta(days=90))
        findings, rows = vf.check_floors(old, self.floors, NOW)
        self.assertEqual([f.kind for f in findings], ["stale"])
        self.assertTrue(all(r["status"] == "skipped" for r in rows))

    def test_a_short_history_is_skipped_rather_than_alerted(self):
        """The morning after a fresh install or a restore. Alerting then trains
        the operator to ignore the channel before it has ever been right."""
        findings, rows = vf.check_floors(_history(_REAL_RUNS[:1]),
                                         self.floors, NOW)
        self.assertEqual([f for f in findings if f.kind == "below_floor"], [])
        self.assertTrue(any(r["status"] == "skipped" for r in rows))


class TestHistoryFile(unittest.TestCase):
    """record_run/read_history round-trip. Uses a tempdir; touches nothing real."""

    def test_round_trip_preserves_none_distinctly_from_zero(self):
        """`-` and `0` in the volume line mean different things -- "this step
        never upserts" against "this step upserted nothing" -- and collapsing
        them is exactly the distinction run-daily.py's summary exists to
        preserve."""
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "h.jsonl")
            vf.record_run({"ats": (5, 0), "extract": (None, None)}, path=path)
            entry = vf.read_history(path)[0]
            self.assertEqual(entry["written"]["ats"], 5)
            self.assertIsNone(entry["written"]["extract"])

    def test_a_truncated_final_line_does_not_lose_the_good_runs(self):
        """A machine that lost power mid-append must not take the check down
        with it -- the morning after something went wrong is when it is needed."""
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "h.jsonl")
            vf.record_run({"ats": (5, 0)}, path=path)
            vf.record_run({"ats": (7, 0)}, path=path)
            with open(path, "a", encoding="utf-8") as fh:
                fh.write('{"at": "2026-08-0')
            self.assertEqual(len(vf.read_history(path)), 2)

    def test_history_is_bounded(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "h.jsonl")
            for _ in range(12):
                vf.record_run({"ats": (1, 0)}, path=path, max_entries=5)
            self.assertEqual(len(vf.read_history(path)), 5)

    def test_an_unwritable_path_returns_none_rather_than_raising(self):
        """run-daily.py calls this after every step has done its real work. A
        full disk must not turn a successful ingest into a failed unit."""
        self.assertIsNone(
            vf.record_run({"ats": (1, 0)},
                          path=os.path.join(os.sep, "nonexistent-dir", "h.jsonl")))

    def test_records_are_valid_json_lines(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "h.jsonl")
            vf.record_run({"ats": (5, 1)}, path=path)
            with open(path, encoding="utf-8") as fh:
                for line in fh:
                    json.loads(line)


if __name__ == "__main__":
    unittest.main()

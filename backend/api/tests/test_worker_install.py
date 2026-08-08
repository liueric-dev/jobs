"""T-29: `--install` / `--uninstall`, writing and removing a launchd agent.

WHAT THIS MACHINE CAN AND CANNOT CHECK. The row says it: this is Linux, so the
plist can be generated and diffed here but never loaded. Everything below is on
the generatable side of that line. Nothing here runs `launchctl`, and nothing
here simulates it: the two cases that reach it pass in a recorder and assert
the argv this worker WOULD hand it, which is a claim about our own call and not
about launchd's answer to it. Whether a real launchd accepts that plist is
DEV_TASKS.md's OQ-25 -- one watched install on somebody else's Mac -- and no
test in this repo may report on it.

WHY THIS FILE IMPORTS THE WORKER AND test_contributor_worker.py REFUSES TO.
That refusal is specific and load-bearing: T-28's bug is invisible to a test
that imports the module, because importing lets you monkeypatch CONFIG_PATH and
never notice it was resolved against the working directory. Nothing here is
about CONFIG_PATH. The plist is a pure function of a label, an interval and a
home directory, and calling it directly is the only way to read the file this
machine cannot load. The CLI-level cases below are subprocess runs, for the
same reason that file gives.

THE PLATFORM GATE IS IN cli(), NOT IN install_agent(). That is what lets the
file half be exercised here: `--install` as a Builder types it refuses on this
machine (asserted below, for real, no faking), while install_agent() itself is
platform-agnostic and runs against a temporary home. The alternative -- gating
inside install_agent() -- would make every assertion about the written plist
unreachable off a Mac, which is most of this row.

NO CLOCK. Nothing in this row has an interval measured from now, an expiry or a
timestamp. StartInterval is a duration, not a moment, and it is compared
against a module constant rather than against anything derived from a clock.
"""

import contextlib
import importlib.util
import io
import os
import plistlib
import shutil
import subprocess
import sys
import tempfile
import unittest

WORKER_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "contributor-worker")
WORKER = os.path.join(WORKER_DIR, "google-serpapi-worker.py")

#: Everything the worker reads out of the environment, cleared before every
#: subprocess run so the machine the suite is on cannot supply a setting the
#: test did not. Same list, same reason, as test_contributor_worker.py's.
WORKER_VARS = ("JOBS_API_BASE_URL", "JOBS_API_KEY", "SERPAPI_API_KEY",
               "MAX_QUERIES", "HTTP_TIMEOUT", "DEBUG")


def load_worker():
    """Import the worker under a name Python will accept.

    The file is `google-serpapi-worker.py`; the hyphens mean `import` cannot
    name it, so it is loaded from its path. Importing runs the module-level
    config load, which returns {} when no config.json sits beside the script --
    and test_contributor_worker.py asserts none is committed.
    """
    spec = importlib.util.spec_from_file_location("contributor_worker", WORKER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


worker = load_worker()


class Recorder:
    """Stands in for launchctl and records what it was asked to do.

    It answers 0 to everything by default. That is not a claim that launchctl
    would: it is what makes the FILE half -- which is all this machine can see
    -- observable at all. The failure answers are set explicitly per test.
    """

    def __init__(self, answers=None):
        self.calls = []
        self.answers = dict(answers or {})

    def __call__(self, args):
        self.calls.append(list(args))
        return self.answers.get(args[0], (0, ""))

    @property
    def verbs(self):
        return [call[0] for call in self.calls]


class FakeHome(unittest.TestCase):
    """A temporary directory standing in for ~, with the one subdirectory a
    Mac always has. LaunchAgents existing beforehand is what makes the
    before/after listing comparison mean anything -- against a directory this
    row created, "identical" would be trivially true."""

    def setUp(self):
        self.home = tempfile.mkdtemp(prefix="t29-")
        self.addCleanup(shutil.rmtree, self.home, True)
        self.agents = os.path.join(self.home, "Library", "LaunchAgents")
        os.makedirs(self.agents)

    def listing(self):
        return sorted(os.listdir(self.agents))

    def install(self, launchctl=None, **kwargs):
        """install_agent, with its output captured rather than spilled.

        These two functions talk to a Builder, so they print. Letting that into
        the suite's own output buries the one line that matters when something
        here goes red -- and capturing it is also what lets the messages
        themselves be asserted, which is most of what a Builder ever sees of
        this row.
        """
        return self._captured(worker.install_agent, launchctl, **kwargs)

    def uninstall(self, launchctl=None, **kwargs):
        return self._captured(worker.uninstall_agent, launchctl, **kwargs)

    def _captured(self, func, launchctl, **kwargs):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = func(home=self.home, launchctl=launchctl or Recorder(),
                        **kwargs)
        return code, out.getvalue()


class TestThePlist(unittest.TestCase):
    """The file, as a value. No disk, no launchctl, no platform."""

    def setUp(self):
        self.plist = worker.build_launch_agent(home="/Users/dana")

    def test_start_interval_is_the_local_floor(self):
        # T-29's own "Done when" clause. The floor is defined in the worker by
        # this row because T-31, which the row credits with defining it, is
        # unbuilt -- so the plist is compared against the constant, and the
        # constant against its value, and a change to either has to be typed.
        self.assertEqual(self.plist["StartInterval"],
                         worker.MIN_POLL_INTERVAL_SECONDS)
        self.assertEqual(worker.MIN_POLL_INTERVAL_SECONDS, 3600)

    def test_there_is_exactly_one_floor_constant(self):
        # T-31 inherits this name rather than declaring a second one. Two
        # floors that drift apart is a worker polling on one number and
        # scheduled on another, which nothing would report.
        floors = [name for name in dir(worker)
                  if "INTERVAL" in name and name.isupper()]
        self.assertEqual(floors, ["MIN_POLL_INTERVAL_SECONDS"])

    def test_the_worker_is_invoked_by_absolute_path(self):
        # The property api/tests/test_contributor_worker.py exists to protect,
        # asserted from the other end: this agent is the caller that has no
        # useful working directory, so neither of its two arguments may be
        # resolved against one.
        argv = self.plist["ProgramArguments"]
        self.assertEqual(len(argv), 2)
        for entry in argv:
            self.assertTrue(os.path.isabs(entry), f"{entry} is not absolute")
        self.assertEqual(os.path.basename(argv[1]), os.path.basename(WORKER))
        self.assertEqual(os.path.realpath(argv[1]), os.path.realpath(WORKER))

    def test_the_interpreter_is_the_one_that_installed(self):
        # "python3" would resolve through the agent's PATH, which is not the
        # Builder's shell PATH. Whatever ran --install is the interpreter that
        # was proved to work.
        self.assertEqual(self.plist["ProgramArguments"][0], sys.executable)

    def test_no_working_directory_is_pinned(self):
        # Setting one would make T-28's cwd-independence untested on the only
        # run that matters, by supplying the very thing the agent is supposed
        # not to have.
        self.assertNotIn("WorkingDirectory", self.plist)

    def test_it_does_not_run_at_load(self):
        # --install must not spend a SerpApi credit. T-30's --check is the
        # command specified to confirm an install without spending one.
        self.assertIs(self.plist["RunAtLoad"], False)

    def test_output_goes_somewhere_a_builder_can_read(self):
        # A launchd job has no terminal. Without these keys every failure this
        # agent has is invisible, including to OQ-25's watched install.
        expected = worker.launch_agent_log_path("/Users/dana")
        self.assertEqual(self.plist["StandardOutPath"], expected)
        self.assertEqual(self.plist["StandardErrorPath"], expected)
        self.assertTrue(expected.startswith("/Users/dana/"))

    def test_the_filename_is_the_label(self):
        # launchctl reports the Label and the directory shows the filename;
        # they have to be readable against each other.
        path = worker.launch_agent_path("/Users/dana")
        self.assertEqual(os.path.basename(path),
                         f"{self.plist['Label']}.plist")
        self.assertEqual(os.path.dirname(path),
                         "/Users/dana/Library/LaunchAgents")

    def test_it_serialises_to_a_plist_and_back_unchanged(self):
        # The whole of what this machine can say about the file's validity.
        self.assertEqual(plistlib.loads(plistlib.dumps(self.plist)),
                         self.plist)


class TestInstalling(FakeHome):

    def test_it_writes_one_agent_where_launchd_looks(self):
        code, _ = self.install()
        self.assertEqual(code, 0)
        self.assertEqual(
            self.listing(),
            [os.path.basename(worker.launch_agent_path(self.home))])

    def test_the_written_file_is_the_plist(self):
        self.install()
        with open(worker.launch_agent_path(self.home), "rb") as fh:
            written = plistlib.load(fh)
        self.assertEqual(written,
                         worker.build_launch_agent(home=self.home))
        self.assertEqual(written["StartInterval"],
                         worker.MIN_POLL_INTERVAL_SECONDS)

    def test_a_second_install_adds_no_second_agent(self):
        # The row's clause, taken literally. Idempotence here is structural --
        # one label, one path -- so this is the assertion that keeps it that
        # way if the path ever gains a component.
        self.install()
        first = self.listing()
        self.install()
        self.assertEqual(self.listing(), first)
        self.assertEqual(len(first), 1)

    def test_a_second_install_unloads_before_it_rewrites(self):
        # launchd holds the copy of the plist it read at load time, so
        # overwriting the file underneath a loaded job leaves the OLD schedule
        # running and reports success. The order is the fix, so the order is
        # what is asserted.
        self.install()
        recorder = Recorder()
        self.install(recorder)
        self.assertEqual(recorder.verbs, ["unload", "load"])

    def test_a_first_install_does_not_unload_anything(self):
        recorder = Recorder()
        self.install(recorder)
        self.assertEqual(recorder.verbs, ["load"])

    def test_what_it_asks_launchctl_to_do(self):
        # This asserts the argv this worker constructs. It does NOT assert that
        # launchctl accepts it -- no test on this machine can, and OQ-25 is
        # where that is found out.
        recorder = Recorder()
        self.install(recorder)
        self.assertEqual(
            recorder.calls,
            [["load", "-w", worker.launch_agent_path(self.home)]])

    def test_a_launchctl_that_refuses_the_load_is_reported_not_swallowed(self):
        code, output = self.install(
            Recorder({"load": (1, "Load failed: 5: Input/output error")}))
        self.assertEqual(code, 1)
        self.assertIn("worker FAILED", output)
        self.assertIn("Load failed: 5", output,
                      "launchctl's own words are the only diagnosis a Builder "
                      "or OQ-25 will have")

    def test_a_failed_unload_before_a_reinstall_is_not_fatal(self):
        # The ordinary cause is an agent that is present but not loaded. The
        # load is the step that has to work.
        self.install()
        code, output = self.install(
            Recorder({"unload": (1, "Could not find specified service")}))
        self.assertEqual(code, 0)
        self.assertNotIn("worker FAILED", output)

    def test_it_says_where_the_agent_and_the_log_are(self):
        # A scheduled run has no terminal, so the log path is the whole of what
        # a Builder has to look at when nothing seems to happen.
        _, output = self.install()
        self.assertIn(worker.launch_agent_path(self.home), output)
        self.assertIn(worker.launch_agent_log_path(self.home), output)

    def test_it_makes_the_directories_it_needs(self):
        # A Mac has ~/Library/LaunchAgents only if something created it, and
        # ~/Library/Logs may be absent too. Failing on a missing directory
        # would strand a Builder on the first thing they run.
        bare = tempfile.mkdtemp(prefix="t29-bare-")
        self.addCleanup(shutil.rmtree, bare, True)
        with contextlib.redirect_stdout(io.StringIO()):
            code = worker.install_agent(home=bare, launchctl=Recorder())
        self.assertEqual(code, 0)
        self.assertTrue(os.path.exists(worker.launch_agent_path(bare)))
        self.assertTrue(
            os.path.isdir(os.path.dirname(worker.launch_agent_log_path(bare))))


class TestUninstalling(FakeHome):

    def test_install_then_uninstall_leaves_the_directory_as_it_found_it(self):
        # The row's central clause: diff the listing before and after.
        before = self.listing()
        self.install()
        self.assertNotEqual(self.listing(), before)
        self.uninstall()
        self.assertEqual(self.listing(), before)

    def test_what_it_asks_launchctl_to_do(self):
        self.install()
        recorder = Recorder()
        self.uninstall(recorder)
        self.assertEqual(
            recorder.calls,
            [["unload", "-w", worker.launch_agent_path(self.home)]])

    def test_uninstalling_nothing_is_not_an_error(self):
        recorder = Recorder()
        code, output = self.uninstall(recorder)
        self.assertEqual(code, 0)
        self.assertIn("nothing to remove", output)
        self.assertEqual(recorder.calls, [],
                         "nothing was installed, so nothing should have been "
                         "asked of launchctl")

    def test_a_second_uninstall_is_not_an_error(self):
        self.install()
        self.uninstall()
        code, _ = self.uninstall()
        self.assertEqual(code, 0)

    def test_a_refused_unload_leaves_the_file_alone(self):
        # Deleting the plist while launchd still holds the job would leave a
        # schedule with no file left to unload it by.
        self.install()
        code, output = self.uninstall(
            Recorder({"unload": (1, "Operation not permitted")}))
        self.assertEqual(code, 1)
        self.assertIn("Operation not permitted", output)
        self.assertTrue(os.path.exists(worker.launch_agent_path(self.home)))

    def test_it_removes_the_schedule_and_leaves_the_credential(self):
        # DEV_TASKS.md's OQ-27, third bullet: whether --uninstall should also
        # remove the config.json T-28 taught the worker to read is an OWNER
        # DECISION about other people's machines, and it was open when this was
        # built. This pins the only answer this row is allowed to give --
        # remove the schedule, say where the credential still is, decide
        # nothing -- so that resolving OQ-27 the other way is a deliberate edit
        # here rather than a silent one.
        #
        # CONFIG_PATH is patched because the real one must stay empty: a
        # committed config.json is a committed credential, and
        # test_contributor_worker.py asserts there is none. Patching it is safe
        # HERE and not there -- that file is about how the path is RESOLVED,
        # and this is about what the message says once it is.
        elsewhere = os.path.join(self.home, "config.json")
        with open(elsewhere, "w", encoding="utf-8") as fh:
            fh.write('{"JOBS_API_KEY": "sekrit-minted-key"}')
        original = worker.CONFIG_PATH
        worker.CONFIG_PATH = elsewhere
        self.addCleanup(setattr, worker, "CONFIG_PATH", original)

        self.install()
        code, output = self.uninstall()

        self.assertEqual(code, 0)
        self.assertTrue(os.path.exists(elsewhere),
                        "--uninstall removed the credential, which is OQ-27's "
                        "decision to make and not this row's")
        self.assertIn(elsewhere, output,
                      "a Builder passing the machine on has to be told the "
                      "file is still there")
        self.assertNotIn("sekrit", output,
                         "the path, never the contents")

    def test_it_says_nothing_about_a_credential_that_is_not_there(self):
        # The environment-configured run, which has no file. Naming one that
        # does not exist would send a Builder looking for it.
        original = worker.CONFIG_PATH
        worker.CONFIG_PATH = os.path.join(self.home, "absent.json")
        self.addCleanup(setattr, worker, "CONFIG_PATH", original)
        self.install()
        _, output = self.uninstall()
        self.assertNotIn("absent.json", output)


class TestTheCommandLine(unittest.TestCase):
    """Subprocess runs, as a Builder would type them. Real, on this machine."""

    def run_worker(self, *args, home=None):
        environ = {k: v for k, v in os.environ.items() if k not in WORKER_VARS}
        if home is not None:
            environ["HOME"] = home
        return subprocess.run(  # noqa: S603 -- argv is sys.executable, a module-level constant path, and flags this test spells out
            [sys.executable, WORKER, *args],
            cwd=os.path.dirname(WORKER_DIR), env=environ,
            capture_output=True, text=True, timeout=60, check=False)

    def test_a_bare_run_is_untouched_by_the_flag_interface(self):
        # T-28's clause, re-asserted from the row that could have broken it:
        # adding an argument parser must leave the no-argument path printing
        # exactly what it printed, and exiting exactly as it exited.
        result = self.run_worker()
        self.assertEqual(
            result.stdout.strip(),
            "worker FAILED: set JOBS_API_BASE_URL, JOBS_API_KEY, "
            "SERPAPI_API_KEY (see this file's header)")
        self.assertEqual(result.returncode, 1)

    def test_install_refuses_on_this_platform_and_writes_nothing(self):
        # Not skipped and not faked: this machine is the non-Darwin case, so
        # this is the real assertion rather than a stand-in for one.
        self.assertNotEqual(sys.platform, "darwin",
                            "this test asserts the non-Darwin refusal; on a "
                            "Mac it would need rewriting, not skipping")
        home = tempfile.mkdtemp(prefix="t29-cli-")
        self.addCleanup(shutil.rmtree, home, True)
        result = self.run_worker("--install", home=home)
        self.assertEqual(result.returncode, 1)
        self.assertIn("macOS only", result.stdout)
        self.assertIn(sys.platform, result.stdout)
        self.assertEqual(os.listdir(home), [],
                         "a plist on a machine with no launchd is a file that "
                         "will never fire")

    def test_uninstall_refuses_on_this_platform_too(self):
        result = self.run_worker("--uninstall")
        self.assertEqual(result.returncode, 1)
        self.assertIn("macOS only", result.stdout)

    def test_the_refusal_points_somewhere(self):
        # A Builder told "no" with nowhere to go stops here. 0007 decision 7
        # makes non-Mac manual-run, and the header carries the cron line.
        result = self.run_worker("--install")
        self.assertIn("cron", result.stdout)

    def test_help_names_both_flags_and_exits_zero(self):
        result = self.run_worker("--help")
        self.assertEqual(result.returncode, 0)
        self.assertIn("--install", result.stdout)
        self.assertIn("--uninstall", result.stdout)

    def test_the_two_flags_are_mutually_exclusive(self):
        result = self.run_worker("--install", "--uninstall")
        self.assertNotEqual(result.returncode, 0)

    def test_an_unknown_flag_is_refused_rather_than_ignored(self):
        # Before this row the worker parsed nothing, so `--check` was silently
        # accepted and a run happened instead. T-30 lands --check on top of
        # this parser; until it does, asking for it has to say no.
        result = self.run_worker("--check")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("unrecognized arguments", result.stderr)


if __name__ == "__main__":
    unittest.main()

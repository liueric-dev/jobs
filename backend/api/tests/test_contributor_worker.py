"""T-28: the worker takes its settings from the environment, then from a
`config.json` beside itself.

WHY EVERY TEST HERE IS A SUBPROCESS RUN FROM SOMEWHERE ELSE. The file this row
is about is resolved from `__file__`, and the single bug it exists to prevent
is a resolution against the working directory instead -- which behaves
identically every time you run the worker by hand from its own directory, and
fails on every run T-29's launchd agent makes, because that agent sets no cwd
worth relying on. A test that imported the module and monkeypatched
CONFIG_PATH would pass just as happily against the broken version. So nothing
here imports the worker: each case runs the script as a Builder's machine
would, and `_run` refuses to run anything with cwd inside the worker's
directory, so the distinction cannot quietly stop being tested.

WHY THE UNREACHABLE PORT. "Proceeded past the unset-settings check" needs an
observable, and the next thing the worker does is POST to JOBS_API_BASE_URL and
name that URL when it cannot reach it. Pointing it at a port nothing is
listening on turns "which value won" into a string in the output -- so
precedence is asserted from the worker's own behaviour rather than from reading
its source. The port is bound and released to be sure it is closed; the call is
to 127.0.0.1 and refused immediately, so no test here touches a network.

NO CLOCK. Nothing in this row has a TTL, an expiry or a timestamp, so there is
no second clock to get out of step with the first.
"""

import json
import os
import re
import socket
import subprocess
import sys
import unittest

WORKER_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "contributor-worker")
WORKER_NAME = "google-serpapi-worker.py"
WORKER = os.path.join(WORKER_DIR, WORKER_NAME)

#: TASKS.md's T-28 quotes this as the message a bare environment must still
#: print, unchanged. Spelled out here rather than built from a list, because a
#: constructed expectation would follow the code into a regression.
BARE_MESSAGE = ("worker FAILED: set JOBS_API_BASE_URL, JOBS_API_KEY, "
                "SERPAPI_API_KEY (see this file's header)")

#: Everything the worker reads out of the environment. Cleared before every
#: run so the machine the suite happens to be on cannot supply a setting the
#: test did not.
WORKER_VARS = ("JOBS_API_BASE_URL", "JOBS_API_KEY", "SERPAPI_API_KEY",
               "MAX_QUERIES", "HTTP_TIMEOUT", "DEBUG")


def closed_port():
    """A port nothing is listening on: bound to learn a free one, then freed."""
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _run(script_dir, cwd, env=None):
    """Run the worker at `script_dir`, from `cwd`, with only `env` set."""
    assert os.path.abspath(cwd) != os.path.abspath(script_dir), (
        "run the worker from somewhere other than its own directory -- from "
        "its own directory, cwd and __file__ agree and this suite would stop "
        "being able to tell them apart")
    environ = {k: v for k, v in os.environ.items() if k not in WORKER_VARS}
    environ.update(env or {})
    # HTTP_TIMEOUT bounds the one case that gets as far as a connection. It is
    # refused rather than dropped, so this is a backstop, not the mechanism.
    environ.setdefault("HTTP_TIMEOUT", "5")
    return subprocess.run(  # noqa: S603 -- argv is sys.executable and WORKER_NAME, a module-level constant, under a directory this test made
        [sys.executable, os.path.join(script_dir, WORKER_NAME)],
        cwd=cwd, env=environ, capture_output=True, text=True, timeout=60,
        check=False)


class WorkerCopy(unittest.TestCase):
    """A copy of the worker in a temp directory, plus a `cwd` that is not it.

    The copy is what lets a config.json exist at all: the real directory must
    stay empty of one (see TestTheShippedDirectory), because a committed
    config.json is a committed credential and because the row's "unchanged
    message with no file" clause is asserted against that directory.
    """

    def setUp(self):
        import shutil
        import tempfile
        self.tmp = tempfile.mkdtemp(prefix="t28-")
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.script_dir = os.path.join(self.tmp, "worker")
        self.elsewhere = os.path.join(self.tmp, "elsewhere")
        os.makedirs(self.script_dir)
        os.makedirs(self.elsewhere)
        shutil.copy2(WORKER, self.script_dir)

    def write_config(self, payload, directory=None):
        path = os.path.join(directory or self.script_dir, "config.json")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(payload if isinstance(payload, str) else json.dumps(payload))
        return path

    def run_worker(self, env=None):
        return _run(self.script_dir, self.elsewhere, env)


class TestTheShippedDirectory(unittest.TestCase):
    """The real worker, in the real directory, with nothing set."""

    def test_no_config_json_is_committed(self):
        # Both a credential check and the precondition for the next test: the
        # message below is only "unchanged" if there is no file to change it.
        self.assertFalse(
            os.path.exists(os.path.join(WORKER_DIR, "config.json")),
            "a config.json in the shipped directory is a committed API key, "
            "and it would mask the bare-environment message this row must "
            "leave alone")

    def test_a_bare_environment_prints_the_message_it_always_printed(self):
        result = _run(WORKER_DIR, os.path.dirname(WORKER_DIR))
        self.assertEqual(result.stdout.strip(), BARE_MESSAGE)
        self.assertEqual(result.returncode, 1)

    def test_the_imports_are_all_standard_library(self):
        # T-28's own third acceptance clause, and the promise in the worker's
        # header that it runs on a stranger's machine with no pip install.
        with open(WORKER, encoding="utf-8") as fh:
            source = fh.read()
        imported = re.findall(r"^(?:import|from)\s+([A-Za-z_][\w.]*)",
                              source, re.MULTILINE)
        self.assertTrue(imported, "found no imports at all; this check is "
                                  "unanchored")
        for name in imported:
            self.assertIn(
                name.split(".")[0], sys.stdlib_module_names,
                f"{name} is not in the standard library, and this script's "
                f"header promises there is nothing to pip install")


class TestTheFileIsFoundBesideTheScript(WorkerCopy):

    def test_a_complete_config_gets_past_the_unset_check(self):
        port = closed_port()
        self.write_config({
            "JOBS_API_BASE_URL": f"http://127.0.0.1:{port}",
            "JOBS_API_KEY": "k-from-file",
            "SERPAPI_API_KEY": "serp-from-file",
        })
        result = self.run_worker()
        self.assertNotIn("worker FAILED: set", result.stdout)
        self.assertIn(f"could not reach http://127.0.0.1:{port}", result.stdout)

    def test_a_config_json_in_the_working_directory_is_not_found(self):
        # The bug this row is written against. The file is beside the caller,
        # not beside the script, so the worker must behave as if there is none.
        self.write_config({
            "JOBS_API_BASE_URL": "http://127.0.0.1:1",
            "JOBS_API_KEY": "k",
            "SERPAPI_API_KEY": "s",
        }, directory=self.elsewhere)
        result = self.run_worker()
        self.assertEqual(result.stdout.strip(), BARE_MESSAGE)
        self.assertEqual(result.returncode, 1)

    def test_the_file_beside_the_script_wins_over_one_in_the_way(self):
        # Both exist and disagree. Nothing about the outcome should depend on
        # which directory the caller was standing in.
        port = closed_port()
        self.write_config({
            "JOBS_API_BASE_URL": f"http://127.0.0.1:{port}/beside-the-script",
            "JOBS_API_KEY": "k", "SERPAPI_API_KEY": "s",
        })
        self.write_config({
            "JOBS_API_BASE_URL": f"http://127.0.0.1:{port}/in-the-cwd",
            "JOBS_API_KEY": "k", "SERPAPI_API_KEY": "s",
        }, directory=self.elsewhere)
        result = self.run_worker()
        self.assertIn("/beside-the-script", result.stdout)
        self.assertNotIn("/in-the-cwd", result.stdout)

    def test_it_is_found_from_a_working_directory_two_levels_away(self):
        # A launchd agent's cwd is not a sibling directory chosen to be
        # convenient; "/" is closer to what it actually gets.
        port = closed_port()
        self.write_config({
            "JOBS_API_BASE_URL": f"http://127.0.0.1:{port}",
            "JOBS_API_KEY": "k", "SERPAPI_API_KEY": "s",
        })
        result = _run(self.script_dir, os.path.abspath(os.sep))
        self.assertIn(f"could not reach http://127.0.0.1:{port}", result.stdout)

    def test_a_trailing_slash_in_the_file_is_stripped_as_in_the_environment(self):
        # The base URL is concatenated with a path that already leads with a
        # slash. The environment branch has always trimmed it; the file branch
        # is the same value from a different place and must not differ.
        port = closed_port()
        self.write_config({
            "JOBS_API_BASE_URL": f"http://127.0.0.1:{port}/",
            "JOBS_API_KEY": "k", "SERPAPI_API_KEY": "s",
        })
        result = self.run_worker()
        # The colon is the message's own separator before the error detail, so
        # matching up to it is what proves nothing trails the port.
        self.assertIn(f"could not reach http://127.0.0.1:{port}:", result.stdout)


class TestPrecedence(WorkerCopy):

    def test_the_environment_beats_the_file(self):
        port = closed_port()
        self.write_config({
            "JOBS_API_BASE_URL": f"http://127.0.0.1:{port}/from-file",
            "JOBS_API_KEY": "k", "SERPAPI_API_KEY": "s",
        })
        result = self.run_worker(
            {"JOBS_API_BASE_URL": f"http://127.0.0.1:{port}/from-env"})
        self.assertIn("/from-env", result.stdout)
        self.assertNotIn("/from-file", result.stdout)

    def test_an_empty_environment_variable_does_not_beat_the_file(self):
        # `export JOBS_API_BASE_URL=` is set-but-empty. Letting it win would
        # blank a working install, and the message would name a variable the
        # Builder can see they set.
        port = closed_port()
        self.write_config({
            "JOBS_API_BASE_URL": f"http://127.0.0.1:{port}/from-file",
            "JOBS_API_KEY": "k", "SERPAPI_API_KEY": "s",
        })
        result = self.run_worker({"JOBS_API_BASE_URL": ""})
        self.assertIn("/from-file", result.stdout)

    def test_the_two_sources_combine_field_by_field(self):
        # The realistic install: the file carries what the server minted, and
        # the SerpApi key is the one thing that never reached that server
        # (docs/adr/0006 decision 3), so it may well arrive from the shell.
        port = closed_port()
        self.write_config({
            "JOBS_API_BASE_URL": f"http://127.0.0.1:{port}",
            "JOBS_API_KEY": "k-from-file",
            "SERPAPI_API_KEY": "",
        })
        result = self.run_worker({"SERPAPI_API_KEY": "serp-from-env"})
        self.assertNotIn("worker FAILED: set", result.stdout)
        self.assertIn(f"could not reach http://127.0.0.1:{port}", result.stdout)

    def test_a_field_missing_from_both_is_named_along_with_the_file(self):
        self.write_config({
            "JOBS_API_BASE_URL": "http://127.0.0.1:1",
            "JOBS_API_KEY": "k",
            "SERPAPI_API_KEY": "",
        })
        result = self.run_worker()
        self.assertEqual(result.returncode, 1)
        self.assertIn("set SERPAPI_API_KEY", result.stdout)
        self.assertNotIn("JOBS_API_KEY,", result.stdout)
        self.assertIn(os.path.join(self.script_dir, "config.json"),
                      result.stdout)

    def test_no_secret_from_the_file_is_printed_on_the_way_out(self):
        # The file holds a minted credential. Nothing about failing to start
        # should put it on a terminal or into a launchd log.
        self.write_config({
            "JOBS_API_BASE_URL": "", "JOBS_API_KEY": "sekrit-minted-key",
            "SERPAPI_API_KEY": "sekrit-serp-key",
        })
        result = self.run_worker()
        self.assertNotIn("sekrit", result.stdout + result.stderr)


class TestABrokenFileSaysWhichFile(WorkerCopy):
    """A hand-edited config.json is the likeliest thing to be malformed, and
    the unset-variable message would send its author to the wrong place."""

    def test_invalid_json(self):
        self.write_config('{"JOBS_API_KEY": "k",}')
        result = self.run_worker()
        self.assertEqual(result.returncode, 1)
        self.assertIn("is not valid JSON", result.stdout)
        self.assertIn(os.path.join(self.script_dir, "config.json"),
                      result.stdout)
        self.assertNotIn("worker FAILED: set", result.stdout)

    def test_a_json_document_that_is_not_an_object(self):
        self.write_config('["JOBS_API_KEY"]')
        result = self.run_worker()
        self.assertEqual(result.returncode, 1)
        self.assertIn("must hold a JSON object", result.stdout)

    def test_a_value_that_is_not_a_string(self):
        # The webapp pins the payload flat and all-strings
        # (webapp/tests/test_contribute.py, TestTheWorkerContract). A number
        # typed in by hand would otherwise reach urllib as a non-string and
        # fail somewhere with no mention of the file.
        self.write_config('{"JOBS_API_BASE_URL": "http://127.0.0.1:1", '
                          '"JOBS_API_KEY": 12345, "SERPAPI_API_KEY": "s"}')
        result = self.run_worker()
        self.assertEqual(result.returncode, 1)
        self.assertIn("every value must be a string", result.stdout)
        self.assertIn("JOBS_API_KEY", result.stdout)

    def test_an_unreadable_file_is_reported_rather_than_ignored(self):
        path = self.write_config({"JOBS_API_KEY": "k"})
        os.chmod(path, 0o000)
        self.addCleanup(os.chmod, path, 0o600)
        if os.access(path, os.R_OK):  # running as root; the mode means nothing
            self.skipTest("this process can read a 0000 file")
        result = self.run_worker()
        self.assertEqual(result.returncode, 1)
        self.assertIn("worker FAILED:", result.stdout)
        self.assertNotIn("worker FAILED: set", result.stdout)

    def test_an_empty_object_is_not_an_error(self):
        # Nothing is wrong with the file; the settings are simply not in it.
        self.write_config({})
        result = self.run_worker()
        self.assertEqual(result.returncode, 1)
        self.assertIn("worker FAILED: set JOBS_API_BASE_URL, JOBS_API_KEY, "
                      "SERPAPI_API_KEY", result.stdout)

    def test_an_unknown_key_is_ignored(self):
        # A file from an older opt-in, or one a Builder added a note to. The
        # settings it does carry still work.
        port = closed_port()
        self.write_config({
            "JOBS_API_BASE_URL": f"http://127.0.0.1:{port}",
            "JOBS_API_KEY": "k", "SERPAPI_API_KEY": "s",
            "MAX_QUERIES": "9", "_comment": "left over from last time",
        })
        result = self.run_worker()
        self.assertIn(f"could not reach http://127.0.0.1:{port}", result.stdout)


if __name__ == "__main__":
    unittest.main()

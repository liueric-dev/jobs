"""Tests for lib/pipelinelog.py -- T-12's shared stderr format.

The one behaviour worth pinning is the reason this module exists instead of
`logging.basicConfig()` at each call site: a plain `logging.StreamHandler()`
captures `sys.stderr` at construction time, so once any script has logged
once, `contextlib.redirect_stderr` and `mock.patch.object(sys, "stderr",
...)` -- both used throughout tests/test_match.py and tests/test_score.py --
would silently stop capturing anything. If this file's tests ever fail
because output "goes missing" under a redirect, that regression is back.
"""

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import contextlib  # noqa: E402
import io  # noqa: E402
import logging  # noqa: E402
import unittest  # noqa: E402
from unittest import mock  # noqa: E402

from lib import pipelinelog  # noqa: E402


class TestRedirectCompatibility(unittest.TestCase):
    def setUp(self):
        # Force a fresh handler each test: production only ever installs one
        # per process, but the test suite imports this module once and would
        # otherwise share state across cases. Root handlers are restored
        # afterward -- leaving an extra one attached would double-emit every
        # later logging call in the SAME process, including the ones
        # tests/test_match.py and tests/test_score.py count exactly.
        root = logging.getLogger()
        original_handlers = list(root.handlers)
        original_installed = pipelinelog._installed
        self.addCleanup(setattr, root, "handlers", original_handlers)
        self.addCleanup(setattr, pipelinelog, "_installed", original_installed)
        pipelinelog._installed = False

    def test_redirect_stderr_still_captures_output(self):
        log = pipelinelog.get_logger("test.redirect")
        stream = io.StringIO()
        with contextlib.redirect_stderr(stream):
            log.warning("captured via redirect_stderr")
        self.assertIn("captured via redirect_stderr", stream.getvalue())

    def test_a_second_logger_reuses_the_first_handler_and_still_redirects(self):
        """Simulates two of the four scripts sharing one process (as they do
        under `python3 -m unittest discover`) -- the handler installs once,
        on the first get_logger() call, and every later logger must still
        honour a redirect that starts after that."""
        pipelinelog.get_logger("test.first")
        log = pipelinelog.get_logger("test.second")
        stream = io.StringIO()
        with contextlib.redirect_stderr(stream):
            log.warning("second logger, later redirect")
        self.assertIn("second logger, later redirect", stream.getvalue())

    def test_mock_patch_object_sys_stderr_is_also_honoured(self):
        """tests/test_score.py's TestPerJobIsolation patches sys.stderr this
        way rather than with redirect_stderr; both must work identically."""
        log = pipelinelog.get_logger("test.mockpatch")
        fake = io.StringIO()
        patcher = mock.patch.object(sys, "stderr", fake)
        patcher.start()
        try:
            log.error("captured via mock.patch.object")
        finally:
            patcher.stop()
        self.assertIn("captured via mock.patch.object", fake.getvalue())

    def test_the_format_names_level_and_logger(self):
        log = pipelinelog.get_logger("test.format")
        stream = io.StringIO()
        with contextlib.redirect_stderr(stream):
            log.warning("a message")
        out = stream.getvalue()
        self.assertIn("WARNING", out)
        self.assertIn("test.format", out)
        self.assertIn("a message", out)

    def test_the_logger_itself_is_always_at_debug(self):
        """Filtering is deliberately not this module's job -- see its
        docstring. Every caller keeps its own `if DEBUG_PRINT_KEYS:` guard;
        the logger must never add a second filter underneath it."""
        log = pipelinelog.get_logger("test.level")
        self.assertEqual(log.level, logging.DEBUG)


if __name__ == "__main__":
    unittest.main()

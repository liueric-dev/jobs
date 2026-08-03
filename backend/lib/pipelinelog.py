"""One stderr format for the pipeline stages' failure and deferral paths.

Replaces each script's own hand-rolled `print(f"[debug] ...", file=sys.stderr)`
with stdlib `logging`, decided once here rather than per call site.

**Filtering is not this module's job.** The logger returned is always at
DEBUG, so nothing is dropped by the logging layer itself -- every call site
keeps deciding for itself what gets shown, exactly as it did with `print()`:
the DEBUG_PRINT_KEYS-gated diagnostics stay behind their own `if
DEBUG_PRINT_KEYS:` guard in the caller, and the handful of failures this
pipeline already printed unconditionally (`# Loud unconditionally, not
behind DEBUG_PRINT_KEYS. Silence is this system's failure mode.` --
score.py) stay unconditional. This module only standardises the format.

**The handler resolves `sys.stderr` at write time, not at construction.**
`logging.StreamHandler()` captures whatever `sys.stderr` was when the first
call configured it -- so once a handler exists, `contextlib.redirect_stderr`
and `mock.patch.object(sys, "stderr", ...)` in tests silently stop working,
because the handler is still writing to the object it was built with. The
proxy below looks `sys.stderr` up fresh on every write, which is what makes
this module compatible with tests written for the print()-based version.
"""

import logging
import sys

_installed = False


class _StderrProxy:
    """A file-like object that always forwards to the current `sys.stderr`."""

    def write(self, message):
        sys.stderr.write(message)

    def flush(self):
        sys.stderr.flush()


def get_logger(name: str) -> logging.Logger:
    """A DEBUG-level logger named `name`, writing through the one handler.

    The handler is installed on the root logger once per process; every
    caller's logger propagates to it, so extract.py, match.py, score.py and
    run-daily.py all end up in the same format without each configuring
    logging themselves.
    """
    global _installed
    if not _installed:
        handler = logging.StreamHandler(_StderrProxy())
        handler.setFormatter(logging.Formatter(
            "%(asctime)s %(levelname)s %(name)s: %(message)s"))
        logging.getLogger().addHandler(handler)
        _installed = True
    logger = logging.getLogger(name)
    logger.setLevel(logging.DEBUG)
    return logger

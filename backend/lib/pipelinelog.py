"""Consistent stderr logging for the ingestion pipeline.

The handler resolves sys.stderr on each write, so redirected test output still
works after logger initialization. Callers decide which diagnostics are shown.
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
    caller's logger propagates to it, so all ingestion stages and run-daily.py
    use the same format without each configuring
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

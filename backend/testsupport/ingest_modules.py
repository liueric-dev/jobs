"""Import hyphenated ingest scripts by file path for offline tests.

Importing the modules does not run their guarded main() entry points.
"""

import importlib.util
import os
import sys

INGEST_DIR = os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "ingest")

_loaded = {}


def load(name):
    """The module for `ingest/<name>.py`, imported once per process.

    Cached because these modules compile regexes at import and because two
    imports of the same file would be two distinct module objects -- so a
    test that monkeypatched one would not affect the other, which is a
    confusing hour nobody needs to spend.
    """
    if name in _loaded:
        return _loaded[name]

    path = os.path.join(INGEST_DIR, f"{name}.py")
    if not os.path.exists(path):
        raise FileNotFoundError(path)

    # The scripts do this themselves at import (ingest/ats.py:129) so that
    # `import schema` resolves; doing it here too means importing one from a
    # test directory works regardless of what put us on the path.
    parent = os.path.dirname(INGEST_DIR)
    if parent not in sys.path:
        sys.path.insert(0, parent)

    modname = f"_ingest_{name.replace('-', '_')}"
    spec = importlib.util.spec_from_file_location(modname, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[modname] = module
    spec.loader.exec_module(module)
    _loaded[name] = module
    return module

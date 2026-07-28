"""Import an ingest script by path, because five of six have hyphens.

`ingest/google-serpapi.py` is not an identifier, so `import` cannot reach it
and `tests/test_upsert_checked.py:20` worked around the problem by testing
the TableSpec instead of the script. That was the right call there -- what
varied between its eight paths was the spec -- but it is the wrong call for
a cassette test, where the whole point is to run the REAL normalizer over
the REAL bytes. A test that exercises a copy of the parser measures the copy.

So: importlib by file path, the same mechanism
`tests/test_upsert_checked.py:267-272` already uses for `run-daily.py`.

SAFE TO IMPORT. Every ingest script guards its entry point with
`if __name__ == "__main__": main()`, so importing one runs its module body
and nothing else. The module body reads environment variables and builds
paths; none of them connects, fetches or writes. Verified for all six.
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

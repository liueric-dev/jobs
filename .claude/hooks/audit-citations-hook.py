#!/usr/bin/env python3
"""PostToolUse hook: T-7 in TASKS.md, Layer 4 item 3 of TASK-52-harness.md.

Runs `backend/tools/audit-citations.py` after every Edit/Write, so a new
drifted `file:line` citation is caught in the turn that wrote it rather than
the next session's re-verification. Stdlib only, deliberately -- the tool it
wraps runs under the top level's bare system python3 and this hook does too.

`audit-citations.py` has no path-scoped mode (see its own `main()`): it always
scans the whole tracked tree. Running the full scan on every edit is what "on
the touched path" means in practice here, not a per-file check -- the tool
itself is a whole-repo invariant ("0 new"), so a hook that only checked the
touched file would miss a new citation that drifted because THIS edit changed
what an earlier citation elsewhere resolves against.

Reads the PostToolUse JSON payload from stdin (only used for a diagnostic
message; the checker itself takes no arguments). Exit 0: no new drift, or the
checker could not run (e.g. this hook fired outside the jobs repo -- fails
open rather than blocking an unrelated project). Exit 2: new drift, surfaced
to Claude via stderr in the same turn -- see hooks reference on PostToolUse
exit codes.
"""

import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
CHECKER = REPO_ROOT / "backend" / "tools" / "audit-citations.py"


def main():
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        payload = {}
    touched = payload.get("tool_input", {}).get("file_path", "<unknown>")

    if not CHECKER.exists():
        return 0

    result = subprocess.run(
        [sys.executable, str(CHECKER)],
        capture_output=True, text=True, cwd=str(CHECKER.parent),
    )
    if result.returncode == 0:
        return 0

    print(f"audit-citations.py found new drift after editing {touched}:",
          file=sys.stderr)
    print(result.stderr.strip() or result.stdout.strip(), file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())

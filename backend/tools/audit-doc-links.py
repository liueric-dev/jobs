#!/usr/bin/env python3
"""Resolve every relative Markdown link under docs/ and report the broken ones.

WHY THIS EXISTS

Task 34 found sixteen broken relative links, ten of them in the file
`HANDOFF.md` calls "the ordered index". Every one was a missing or surplus
directory prefix -- `01-pin-production-model.md` for a file that lives in
`tranche_one/`, `../../../ADDENDUM...` for a sibling. None of them is visible
when reading the Markdown; they fail only when a reader clicks.

One of them cost more than a click. `README.md` linked to
`34-documentation-cleanup.md` without its `tranche_six/` prefix, a session
read the broken link as a missing file, and wrote a second task 34 at the
un-prefixed path. A link checker that had been run would have said "wrong
prefix" rather than "no such file", and the duplicate would not exist.

SCOPE IS ALL OF docs/, DELIBERATELY

Task 34 scoped its audit to `docs/tasks/refactor/`. Re-running it across the
whole tree found five more of the identical class in `docs/tasks/README.md`,
which that scope would never have reached. A checker scoped to the directory
whose links you already suspect is a checker that confirms what you knew.

WHAT IT DOES NOT CHECK

Anchors (`#section`) are stripped and ignored: they would need a heading index
per file, and a wrong anchor lands the reader on the right document. http(s)
and mailto links are skipped -- this runs offline and in a pre-commit hook,
where a network check is a flake, not a test.

    python3 backend/tools/audit-doc-links.py            # docs/, exit 1 if any
    python3 backend/tools/audit-doc-links.py docs/tasks # a subtree
"""

import os
import re
import sys

#: Inline `[text](target)`, allowing an optional "title" after the target.
#: The target may not contain whitespace or `)`, which is what keeps this from
#: swallowing prose that merely contains a bracket followed by a paren.
INLINE = re.compile(r"\[[^\]]*\]\(([^)\s]+)(?:\s+\"[^\"]*\")?\)")

#: Reference-style `[label]: target`, at the start of a line.
REFERENCE = re.compile(r"^\s*\[[^\]]+\]:\s*(\S+)")

#: Schemes and forms that are not filesystem paths. A bare `#anchor` is a link
#: into the same file; there is nothing to resolve.
SKIP = re.compile(r"^(https?:|mailto:|ftp:|#|<)")


def targets(line):
    """Every link target on one line, inline and reference-style."""
    found = [m.group(1) for m in INLINE.finditer(line)]
    ref = REFERENCE.match(line)
    if ref:
        found.append(ref.group(1))
    return found


def broken(root):
    """Yield (path, lineno, target, suggestion) for each link that misses.

    `suggestion` is the path of a file with the same basename elsewhere in the
    tree, when exactly one exists -- which is the answer in every case task 34
    found, because the defect is always a prefix rather than a rename. When
    zero or several match it is None, because guessing is what produced the
    duplicate task file this script exists to prevent.
    """
    by_basename = {}
    for dirpath, _, filenames in os.walk(root):
        for name in filenames:
            if name.endswith(".md"):
                by_basename.setdefault(name, []).append(
                    os.path.join(dirpath, name))

    for dirpath, _, filenames in os.walk(root):
        for name in sorted(filenames):
            if not name.endswith(".md"):
                continue
            path = os.path.join(dirpath, name)
            with open(path, encoding="utf-8") as fh:
                for lineno, line in enumerate(fh, 1):
                    for target in targets(line):
                        if SKIP.match(target):
                            continue
                        bare = target.split("#")[0]
                        if not bare:
                            continue
                        resolved = os.path.normpath(
                            os.path.join(dirpath, bare))
                        if os.path.exists(resolved):
                            continue
                        matches = by_basename.get(os.path.basename(bare), [])
                        suggestion = None
                        if len(matches) == 1:
                            suggestion = os.path.relpath(matches[0], dirpath)
                        yield path, lineno, target, suggestion


def main(argv):
    root = argv[1] if len(argv) > 1 else "docs"
    if not os.path.isdir(root):
        print(f"not a directory: {root}", file=sys.stderr)
        return 2

    count = 0
    for path, lineno, target, suggestion in broken(root):
        count += 1
        fix = f"  -> {suggestion}" if suggestion else "  -> no unique match"
        print(f"{path}:{lineno}\t{target}{fix}")

    print(f"\n{count} broken link(s) under {root}/", file=sys.stderr)
    return 1 if count else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))

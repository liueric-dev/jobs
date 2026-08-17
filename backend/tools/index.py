#!/usr/bin/env python3
"""Generate tools/README.md from the docstrings already in tools/*.py.

WHY GENERATED AND NOT WRITTEN
    A hand-maintained list of this directory is right the day it is written
    and wrong three tools later. This repo has already paid that bill once -- 137
    files under docs/ deleted on 2026-08-02 after an audit found 168 places
    they contradicted the code -- so an index that a human has to remember to
    update is the one shape this tree should not add.

    Every tool in this directory already opens with a one-line summary, and
    most of them are phrased as the question the tool answers. That IS the
    index; it just needed printing. The docstring is the contract, so the
    place to fix a wrong line is the tool, never the README.

THE TEST IS THE POINT
    tests/test_tools_index.py fails when the checked-in README does not match
    what this script would write. Without it this is just a different way to
    go stale -- with it, drift is a red run rather than a rumour, which is the
    same standard CLAUDE.md applies to citations and to CI.

USAGE
    python3 tools/index.py             # print, change nothing
    python3 tools/index.py --write     # rewrite tools/README.md
    python3 tools/index.py --check     # exit 1 if README.md is out of date
"""

import argparse
import ast
import os
import sys

TOOLS_DIR = os.path.dirname(os.path.abspath(__file__))
README = os.path.join(TOOLS_DIR, "README.md")

#: Not a tool -- this generator itself, and Python's package marker.
SKIP = {"index.py", "__init__.py"}

HEADER = """---
kind: index
generator: tools/index.py
---

# backend/tools/

**Measurement and one-off investigation. Nothing here runs as part of the nightly
pipeline** -- `run-daily.py`'s 14 steps touch none of it. Each entry below is the
first line of that file's own docstring; open the file for the full one, which is
where the caveats live (what it costs, what it writes, what it must not be trusted
for).

**This file is generated.** `python3 tools/index.py --write` rebuilds it and
`tests/test_tools_index.py` fails when it is out of date. To change a line here,
change the docstring in the tool.

Everything resolves relative to `backend/`, so `cd backend` first. Every tool here
takes command-line options; run one with `--help` for its own.

| tool | what it answers |
|---|---|
"""

FOOTER = """
Two of these cannot run on a clean checkout or against every machine, and the
reasons are in their docstrings rather than repeated here:
`learned-ranker-probe.py` needs numpy and sklearn, which are deliberately in no
`requirements.txt`, and `provision-database.py` has a banner to read before it is
pointed at a populated database.
"""


def summarise(path):
    """The opening sentence of one tool's docstring, or None if it has none.

    THE FIRST PARAGRAPH, NOT THE FIRST LINE. These docstrings are hard-wrapped
    at ~79 columns, so a first *line* cuts several of them mid-clause ("...and
    confirm every token against the"). Joining the paragraph and then cutting
    at the first sentence boundary gets the whole thought for the wrapped ones
    and changes nothing for the tools whose summary already fits on one line.
    """
    try:
        with open(path, encoding="utf-8") as fh:
            tree = ast.parse(fh.read())
    except (OSError, SyntaxError):
        return None
    doc = ast.get_docstring(tree)
    if not doc or not doc.strip():
        return None
    # get_docstring(clean=True) has already dedented; the first blank line ends
    # the summary paragraph.
    para = []
    for line in doc.strip().split("\n"):
        if not line.strip():
            break
        para.append(line.strip())
    summary = " ".join(para)
    if not summary:
        return None
    # THE WHOLE PARAGRAPH, NOT THE FIRST SENTENCE. Cutting at the first
    # sentence boundary was tried and reverted: it took "Costs ~3 SerpApi
    # credits." off verify-date-filter.py, which is the single most important
    # thing to know before running it. These summaries are one or two short
    # sentences by convention, so there is nothing to gain by trimming them
    # and a cost warning to lose.
    return summary


def render():
    """The full README text, deterministic and sorted."""
    rows, undocumented = [], []
    for name in sorted(os.listdir(TOOLS_DIR)):
        if not name.endswith(".py") or name in SKIP:
            continue
        summary = summarise(os.path.join(TOOLS_DIR, name))
        if summary is None:
            undocumented.append(name)
            continue
        # Escape the cell separator; a docstring is free text and one pipe
        # would silently split the row into a wrong-shaped table.
        rows.append(f"| [`{name}`]({name}) | {summary.replace('|', chr(92) + '|')} |")

    out = HEADER + "\n".join(rows) + "\n"
    if undocumented:
        # Named, not silently dropped. A tool with no docstring is the one
        # case this index cannot describe, and hiding it would make the list
        # look complete when it is not.
        out += ("\n**No module docstring, so not described above:** "
                + ", ".join(f"`{n}`" for n in undocumented) + ".\n")
    return out + FOOTER


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--write", action="store_true",
                    help="rewrite tools/README.md in place")
    ap.add_argument("--check", action="store_true",
                    help="exit 1 if tools/README.md is out of date")
    args = ap.parse_args()

    text = render()

    if args.write:
        with open(README, "w", encoding="utf-8") as fh:
            fh.write(text)
        print(f"tools/index.py: wrote {README}")
        return 0

    if args.check:
        try:
            with open(README, encoding="utf-8") as fh:
                current = fh.read()
        except OSError:
            print("tools/index.py: tools/README.md does not exist -- "
                  "run `python3 tools/index.py --write`")
            return 1
        if current != text:
            print("tools/index.py: tools/README.md is out of date -- "
                  "run `python3 tools/index.py --write`")
            return 1
        print("tools/index.py: tools/README.md is current")
        return 0

    sys.stdout.write(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())

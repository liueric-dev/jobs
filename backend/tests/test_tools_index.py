"""tools/README.md is generated, and this is what stops it going stale.

Run:  python3 -m unittest tests.test_tools_index

WHY THIS FILE EXISTS
    An index a human has to remember to update is the exact
    shape of the thing this repo deleted 137 files of on 2026-08-02. Generating
    it from the docstrings removes the remembering; this test removes the
    silence when someone adds a tool and does not regenerate.

    Without it, `tools/index.py` is just a different way to go stale -- the
    README would be wrong and nothing would say so. CLAUDE.md's standard is
    that a green run is the claim and a number in prose is a rumour, and that
    applies to a list of tools as much as to a test count.

WHAT IT DOES NOT CHECK
    Whether a docstring's summary is ACCURATE. Same limit as
    tools/audit-citations.py, and worth stating rather than assuming: this
    asserts the README matches the docstrings, never that a docstring matches
    what its tool does.
"""

import importlib.util
import os
import subprocess
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
BACKEND = os.path.dirname(HERE)
TOOL = os.path.join(BACKEND, "tools", "index.py")
README = os.path.join(BACKEND, "tools", "README.md")


def _run(*args):
    return subprocess.run([sys.executable, TOOL, *args],
                          capture_output=True, text=True, cwd=BACKEND)


def _load_tool():
    spec = importlib.util.spec_from_file_location("tools_index", TOOL)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class TestTheReadmeIsCurrent(unittest.TestCase):

    def test_check_passes(self):
        """The whole point. Fails when a tool is added, removed, or has its
        summary docstring edited, without `tools/index.py --write`."""
        r = _run("--check")
        self.assertEqual(
            r.returncode, 0,
            "tools/README.md is out of date. Run:\n"
            "    cd backend && python3 tools/index.py --write\n"
            f"{r.stdout}{r.stderr}")

    def test_readme_exists_and_is_marked_generated(self):
        """A generated file that does not say so invites hand-editing, and a
        hand edit here is silently reverted by the next --write."""
        self.assertTrue(os.path.exists(README), f"{README} is missing")
        with open(README, encoding="utf-8") as fh:
            text = fh.read()
        self.assertIn("generator: tools/index.py", text)
        self.assertIn("This file is generated.", text)


class TestEveryToolIsDescribed(unittest.TestCase):

    def test_no_tool_lacks_a_docstring(self):
        """Every tool had a summary line when the index was built. A new one
        without one is not a crash -- render() lists it under 'No module
        docstring' rather than dropping it -- but it is still a gap, and the
        cheapest moment to close it is when it is added."""
        mod = _load_tool()
        missing = []
        for name in sorted(os.listdir(os.path.join(BACKEND, "tools"))):
            if not name.endswith(".py") or name in mod.SKIP:
                continue
            if mod.summarise(os.path.join(BACKEND, "tools", name)) is None:
                missing.append(name)
        self.assertEqual(
            missing, [],
            f"tools/ scripts with no module docstring: {missing}. Add a one-line "
            f"summary as the first line -- it is what tools/README.md prints.")

    def test_every_tool_appears_in_the_readme(self):
        mod = _load_tool()
        with open(README, encoding="utf-8") as fh:
            text = fh.read()
        for name in sorted(os.listdir(os.path.join(BACKEND, "tools"))):
            if not name.endswith(".py") or name in mod.SKIP:
                continue
            with self.subTest(tool=name):
                self.assertIn(f"[`{name}`]", text)

    def test_the_generator_does_not_list_itself(self):
        """index.py describes the directory; it is not one of the measurement
        tools the directory is for."""
        with open(README, encoding="utf-8") as fh:
            text = fh.read()
        self.assertNotIn("[`index.py`]", text)


class TestSummaryExtraction(unittest.TestCase):
    """The summary is a whole paragraph, joined. Both halves of that have
    already been got wrong once."""

    def _summarise_source(self, source):
        import tempfile
        with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False,
                                         encoding="utf-8") as fh:
            fh.write(source)
            path = fh.name
        try:
            return _load_tool().summarise(path)
        finally:
            os.unlink(path)

    def test_a_wrapped_summary_is_joined_not_truncated(self):
        """The first *line* cut several real docstrings mid-clause."""
        got = self._summarise_source(
            '"""Find which employers run which ATS, and confirm every token\n'
            'against the live feed before believing it.\n'
            '\n'
            'Some later paragraph that must not appear.\n'
            '"""\n')
        self.assertEqual(
            got,
            "Find which employers run which ATS, and confirm every token "
            "against the live feed before believing it.")

    def test_a_second_sentence_survives(self):
        """Cutting at the first sentence boundary was tried and reverted: it
        dropped 'Costs ~3 SerpApi credits.' from verify-date-filter.py."""
        got = self._summarise_source(
            '"""Does the date filter still filter? Costs ~3 SerpApi credits.\n'
            '\n'
            'Body.\n'
            '"""\n')
        self.assertIn("Costs ~3 SerpApi credits.", got)

    def test_only_the_first_paragraph_is_taken(self):
        got = self._summarise_source(
            '"""One line.\n\nA second paragraph.\n"""\n')
        self.assertEqual(got, "One line.")

    def test_no_docstring_is_none_not_a_crash(self):
        self.assertIsNone(self._summarise_source("x = 1\n"))

    def test_a_pipe_in_a_summary_is_escaped(self):
        """A docstring is free text; one unescaped pipe silently reshapes the
        Markdown table rather than erroring."""
        mod = _load_tool()
        rendered = mod.render()
        for line in rendered.splitlines():
            if line.startswith("| [`"):
                with self.subTest(line=line[:60]):
                    # name cell, summary cell -- exactly two, so three splits
                    self.assertEqual(
                        len(line.split("|")), 4,
                        "a summary's pipe was not escaped, so this row has the "
                        "wrong number of Markdown cells")


if __name__ == "__main__":
    unittest.main()

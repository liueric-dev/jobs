"""tools/audit-citations.py, run by the suite rather than by memory.

Run:  python3 -m unittest tests.test_citations

WHY THIS FILE EXISTS

`.claude/CLAUDE.md` requires a claim about the code to cite `file:line`,
"because that is what makes a claim checkable", and in the next sentence admits
that citations have drifted and that there is no checker. A rule with no
enforcement is how `docs/` accumulated 168 contradictions before anyone
counted them.

The bar is the one `docs/DOCS-POLICY.md` rule 7 set before it was deleted:
"fails a suite someone is already running", not "has a script". A checker
wired into nothing is a checker that runs once, on the day it is written --
which is exactly what `frontend/verify_fixtures.py` was, and what
`tests/test_frontend_fixtures.py` exists to fix for the same reason.

WHAT IS AND IS NOT PINNED HERE

Pinned: no NEW unresolvable citation. The ones already broken when the checker
landed are in `config/citation-baseline.json`, with the reason, and do not fail
the suite. Their COUNT is not written down here on purpose -- run the tool for
it; a number in prose is what `.claude/CLAUDE.md` warns goes stale silently,
and this one had already been quoted three different ways by the time the
checker was three commits old.

Pinned: the answer does not depend on whether the pipeline has run on this
machine. See TestIgnoredPathsAreNotJudged.

NOT pinned, and deliberately: that the baseline shrinks. A test that demanded
progress would either be trivially satisfiable or permanently red, and the
baseline is a record rather than a target. The checker prints the ones that
have started resolving so they can be dropped.

NOT checkable at all: whether a citation whose line still exists still says
what the citing comment claims. `tools/audit-citations.py`'s docstring names
the worked example. A green run here means the citations RESOLVE.

WHY IT SHELLS OUT INSTEAD OF IMPORTING. Same reason as
tests/test_frontend_fixtures.py: what is asserted is the EXIT STATUS, which is
the contract an operator and a future hook both depend on, so running it the
way a person runs it is the honest test.
"""

import os
import subprocess
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
BACKEND = os.path.dirname(HERE)
REPO = os.path.dirname(BACKEND)
TOOL = os.path.join(BACKEND, "tools", "audit-citations.py")
BASELINE = os.path.join(BACKEND, "config", "citation-baseline.json")


def _run(*args):
    return subprocess.run([sys.executable, TOOL, *args],
                          capture_output=True, text=True, cwd=BACKEND)


def _load_tool():
    """The tool as a module. Its filename has a hyphen, so it cannot be
    imported by name."""
    import importlib.util
    spec = importlib.util.spec_from_file_location("audit_citations", TOOL)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class TestTheCheckerItself(unittest.TestCase):
    """The regex has been wrong twice; both times it was suffix ordering."""

    def test_self_test_passes(self):
        r = _run("--self-test")
        self.assertEqual(r.returncode, 0,
                         f"audit-citations.py --self-test failed:\n{r.stdout}\n{r.stderr}")

    def test_json_and_jsonl_are_distinguished(self):
        """`.js` matching before `.json` produced ~2,500 false findings, and
        `.jsonl` missing entirely produced another ~40. Python's `|` takes the
        first alternative that matches, not the longest, so the suffix list
        must stay length-sorted and must stay complete."""
        mod = _load_tool()
        for text, expected in (
            ("a/b/corpus-v1.jsonl", "a/b/corpus-v1.jsonl"),
            ("a/b/MANIFEST.json", "a/b/MANIFEST.json"),
            ("a/b/app.mjs", "a/b/app.mjs"),
            ("a/b/check.js", "a/b/check.js"),
        ):
            with self.subTest(text=text):
                m = mod.CITATION.search(text)
                self.assertIsNotNone(m, f"{text} did not match at all")
                self.assertEqual(m.group(1), expected)


class TestIgnoredPathsAreNotJudged(unittest.TestCase):
    """A git-ignored path is present or absent depending on what has been RUN
    on this machine, not on what the tree contains, so the checker declines to
    judge citations to one.

    The case that forced this: `backend/.run-volumes.jsonl` is written by the
    nightly ingest. Two citations to it were baselined from a tree that had
    never run the pipeline; on a machine that HAD run it, the checker reported
    them as "now resolve and can be dropped". Dropping them would have made the
    next clean checkout report them as NEW and turn
    test_no_citation_broke_that_was_not_already_broken red on an unrelated edit.

    These assertions are about ignore RULES, never about file presence, so they
    hold either way round -- which is the property under test.
    """

    def test_an_ignored_path_is_reported_ignored_and_a_tracked_one_is_not(self):
        mod = _load_tool()
        got = mod._ignored(["backend/.run-volumes.jsonl", "backend/extract.py"])
        self.assertEqual(got, {"backend/.run-volumes.jsonl"})

    def test_a_finding_against_an_ignored_path_is_dropped(self):
        mod = _load_tool()
        kept = ("x -> backend/extract.py:1", "desc", ["backend/extract.py"])
        dropped = ("y -> backend/.run-volumes.jsonl",
                   "desc", ["backend/.run-volumes.jsonl"])
        self.assertEqual(mod._drop_ignored([kept, dropped]),
                         [(kept[0], kept[1])])

    def test_git_failing_does_not_silently_empty_the_report(self):
        """If the helper cannot answer, nothing is treated as ignored. A
        checker that goes quiet when a subprocess breaks reports success for
        the wrong reason, which is this repo's stated failure mode."""
        mod = _load_tool()
        real, mod.REPO = mod.REPO, os.path.join(BACKEND, "no-such-dir-here")
        try:
            self.assertEqual(mod._ignored(["backend/.run-volumes.jsonl"]), set())
        finally:
            mod.REPO = real


class TestTheTreeHasNoNewDrift(unittest.TestCase):

    def test_no_citation_broke_that_was_not_already_broken(self):
        r = _run()
        self.assertEqual(
            r.returncode, 0,
            "A citation in this commit names a file or a line that does not "
            "exist.\n\n" + (r.stderr or r.stdout) +
            "\n\nFix the citation. If the target is one of the 137 documents "
            "deleted on 2026-08-02, cite it as "
            "`git show refactor-freeze-2026-08-02:<path>` -- the checker "
            "allows that form on purpose.")

    def test_the_baseline_is_loadable_and_explains_itself(self):
        """A baseline without a stated reason is a silencer. This one carries
        its rationale in `_comment` fields, in the house style -- the same
        convention config/relevance.json uses and the reason those files
        survived the documentation purge."""
        import json
        with open(BASELINE, encoding="utf-8") as fh:
            data = json.load(fh)
        self.assertIn("accepted", data)
        for key in ("_comment", "_why_these_are_here", "_what_this_cannot_catch"):
            self.assertIn(key, data)
            self.assertGreater(len(data[key]), 80,
                               f"{key} must actually explain, not gesture")


if __name__ == "__main__":
    unittest.main()

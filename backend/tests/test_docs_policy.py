"""The documentation checks, and the retarget that made one of them real.

WHAT THIS FILE IS FOR AFTER `docs/adr/0010`. It used to wire in seven checks and
ran to 765 lines. Five of them are retired; what is left is C3 (a `kind: rolling`
document has not sat still while its subject moved) and C4 (a figure declared in
`config/doc-figures.json` does not appear outside its owning document).

THE MOST IMPORTANT TEST HERE IS `test_c3_sees_both_rolling_documents`, and the
reason is a failure mode worth naming: before the retarget, C3 scanned `docs/`
plus the reachability roots, and the only two `kind: rolling` files in the repo
sit at the repo root. So it reported zero findings for four months because it
could not see a single document it was written to check. **A check can be green
because it passed or because it never looked, and nothing in the output tells
them apart.** That test asserts it is looking.
"""

import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
BACKEND = os.path.dirname(HERE)
ROOT = os.path.dirname(BACKEND)


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


audit_docs = _load("audit_docs", os.path.join(BACKEND, "tools", "audit-docs.py"))


class TestTheTreeIsClean(unittest.TestCase):
    """The baseline is empty, so any finding of any check is a regression.

    `config/doc-policy-baseline.json` says this in its own `_why` and adds the
    rule that matters: do not grow it. A finding that genuinely cannot be fixed
    becomes a declared allowance in `doc-figures.json` WITH A WRITTEN REASON,
    which is a thing the next reader sees, rather than a row here, which is a
    thing nobody reads.
    """

    def test_the_checker_exits_zero_on_this_tree(self):
        findings, _ = audit_docs.run_checks(ROOT)
        self.assertEqual(
            [], [f"{f.check} {f.path}:{f.lineno} {f.problem}" for f in findings])

    def test_the_baseline_is_still_empty(self):
        data = audit_docs.load_baseline(ROOT)
        for check, entry in data["checks"].items():
            self.assertEqual([], entry["findings"], f"{check} baseline grew")

    def test_doc_links_is_wired_in_and_green(self):
        r = subprocess.run(
            [sys.executable, os.path.join(BACKEND, "tools", "audit-doc-links.py")],
            capture_output=True, text=True, cwd=BACKEND)
        self.assertEqual(0, r.returncode, r.stdout + r.stderr)


class TestTheRetiredChecksStayRetired(unittest.TestCase):
    def test_only_c3_and_c4_run(self):
        self.assertEqual(("C3", "C4"), audit_docs.CHECKS)

    def test_the_retired_identifiers_are_not_reused(self):
        """Gaps on purpose: C1, C2, C5, C6 and C7 are spent numbers.

        `docs/adr/0010` names them and `doc-policy-baseline.json` still cites
        them. Reusing one would silently redirect a citation to a different
        check, which is the same reason `TASKS.md` never reuses a `T-` number.
        """
        for retired in ("C1", "C2", "C5", "C6", "C7"):
            self.assertNotIn(retired, audit_docs.CHECKS)

    def test_the_helpers_only_they_used_are_gone(self):
        for name in ("check_kind", "check_orphans", "check_registers",
                     "check_archive", "check_budget", "VALID_KINDS", "ROOTS",
                     "DELIBERATE_ORPHANS"):
            self.assertFalse(hasattr(audit_docs, name),
                             f"{name} survived the reduction")


class TestC3ActuallyLooks(unittest.TestCase):
    def test_c3_sees_both_rolling_documents(self):
        """The retarget, asserted directly rather than through a zero count."""
        files = audit_docs.scanned_files(ROOT)
        rolling = [rel for rel in files
                   if audit_docs.frontmatter(
                       audit_docs.read(ROOT, rel))[0].get("kind") == "rolling"]
        self.assertEqual(["DEV_TASKS.md", "TASKS.md"], sorted(rolling))

    def test_the_rolling_files_are_outside_docs_and_tracked_anyway(self):
        for rel in ("TASKS.md", "DEV_TASKS.md"):
            self.assertIn(rel, audit_docs.TRACKED_OUTSIDE_DOCS)
            self.assertIn(rel, audit_docs.scanned_files(ROOT))

    def test_a_stale_rolling_document_is_reported(self):
        """A synthetic repo whose subject moved far past the threshold."""
        with tempfile.TemporaryDirectory() as tmp:
            docs = os.path.join(tmp, "docs")
            os.makedirs(docs)
            subprocess.run(["git", "init", "-q"], cwd=tmp, check=True)
            subprocess.run(["git", "config", "user.email", "t@t"], cwd=tmp, check=True)
            subprocess.run(["git", "config", "user.name", "t"], cwd=tmp, check=True)
            rel = "docs/rolling.md"
            with open(os.path.join(tmp, rel), "w") as fh:
                fh.write("---\nkind: rolling\nsubject: src\n---\n\n# rolling\n")
            os.makedirs(os.path.join(tmp, "src"))
            subprocess.run(["git", "add", "-A"], cwd=tmp, check=True)
            subprocess.run(["git", "commit", "-qm", "the document"], cwd=tmp, check=True)
            for i in range(audit_docs.ROLLING_STALE_COMMITS + 2):
                with open(os.path.join(tmp, "src", f"f{i}.py"), "w") as fh:
                    fh.write("x = 1\n")
                subprocess.run(["git", "add", "-A"], cwd=tmp, check=True)
                subprocess.run(["git", "commit", "-qm", f"c{i}"], cwd=tmp, check=True)
            found = list(audit_docs.check_rolling(tmp, [rel]))
        self.assertEqual(1, len(found), found)
        self.assertEqual("C3", found[0].check)


class TestC4(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = self.tmp.name
        os.makedirs(os.path.join(self.root, "backend", "config"))
        os.makedirs(os.path.join(self.root, "docs"))

    def _figures(self, **over):
        fig = {"name": "widget count", "owner": "docs/owner.md",
               "pattern": r"(?<![\d:.\-])42(?![\d.\-])", "allowed": []}
        fig.update(over)
        with open(os.path.join(self.root, "backend", "config",
                               "doc-figures.json"), "w") as fh:
            json.dump({"figures": [fig]}, fh)

    def _write(self, rel, body):
        full = os.path.join(self.root, rel)
        os.makedirs(os.path.dirname(full), exist_ok=True)
        with open(full, "w") as fh:
            fh.write(body)

    def test_a_restated_figure_outside_the_owner_is_reported(self):
        self._figures()
        self._write("docs/owner.md", "# owner\n\nrun the command.\n")
        self._write("docs/other.md", "# other\n\nthere are 42 widgets.\n")
        found = list(audit_docs.check_figures(
            self.root, ["docs/owner.md", "docs/other.md"]))
        self.assertEqual(1, len(found), found)
        self.assertEqual("docs/other.md", found[0].path)

    def test_the_owner_may_state_it(self):
        self._figures()
        self._write("docs/owner.md", "# owner\n\nthere are 42 widgets.\n")
        self.assertEqual(
            [], list(audit_docs.check_figures(self.root, ["docs/owner.md"])))

    def test_a_struck_figure_is_exempt(self):
        """Struck-and-kept is the correction form; the old number stays visible."""
        self._figures()
        self._write("docs/owner.md", "# owner\n")
        self._write("docs/other.md", "# other\n\nthere are ~~42~~ 43 widgets.\n")
        self.assertEqual([], list(audit_docs.check_figures(
            self.root, ["docs/owner.md", "docs/other.md"])))

    def test_a_declared_allowance_suppresses_it(self):
        self._figures(allowed=["docs/other.md"])
        self._write("docs/owner.md", "# owner\n")
        self._write("docs/other.md", "# other\n\nthere are 42 widgets.\n")
        self.assertEqual([], list(audit_docs.check_figures(
            self.root, ["docs/owner.md", "docs/other.md"])))


if __name__ == "__main__":
    unittest.main()

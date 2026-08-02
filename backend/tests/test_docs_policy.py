"""The repo's first doc test: both documentation checkers, run by the suite.

Run:  python3 -m unittest tests.test_docs_policy

WHY THIS FILE EXISTS

`docs/DOCS-POLICY.md` rule 7 says a rule with no check is a suggestion, and it
states the bar deliberately higher than "has a script": **"Fails a suite someone
is already running" is the bar.** `backend/tools/audit-doc-links.py` was the
counter-example that motivated the whole rule -- it reports zero broken links and
is wired into nothing. No test imported it, `.git/hooks` holds only `.sample`
files, and there is no CI configuration in the repo (verified 2026-08-01). It had
held for one day, and only because a person typed the command.

So this file wires in both checkers. `audit-doc-links.py` gets a case here for
exactly the reason task 36's argument rests on it, and `audit-docs.py` gets the
rest.

WHY THE ASSERTION IS "SUBSET OF A BASELINE" AND NOT "ZERO FINDINGS"

Task 36 requires two things that conflict. The checker **lands red** -- a checker
whose first run is green has been tested against nothing, and C5 has real failures
in the tree today. And both suites stay green, because that is the gate every
later wave of phase 9 runs against. Wiring a red checker into `unittest discover`
makes a red suite.

`backend/config/doc-policy-baseline.json` resolves it without weakening either
half. The CLI still exits non-zero today, which is what task 36's Definition of
done actually checks. The suite gates on **regression**: the current finding set
must be a SUBSET of the baseline, so clearing a finding keeps the suite green and
a NEW finding turns it red.

**A NON-EMPTY BASELINE IS A TEMPORARY STATE WITH AN OWNER.** Every check in that
file names the task that clears it -- C1 and C2 to task 37, C4 to task 38, C5 to
task 39. Tasks 37-40 prune it as they land, and phase 9 exits when `findings` is
empty everywhere. If you are reading this and the baseline is still non-empty
after tranche seven closed, that is the finding.

WHY THE SUBSET TEST IS RED TODAY, 2026-08-02

`audit-docs.py` was widened to scan the declared roots outside `docs/` -- the root
`README.md` and `.claude/CLAUDE.md` -- which closes the rule 7 gap `AUDIT.md` s
"What is open" and `HANDOFF.md` both name: those two were reachability roots for C2
and were read by NO other check, C4 included, while both carry figures.

**It landed red, on purpose, and the baseline was NOT grown to hide it.** That is
task 36's own precedent -- it landed red with real C5 failures -- and growing the
baseline here would be worse than the finding, because `doc-policy-baseline.json`
was pruned empty at the close of tranche seven and its `_why` says in terms: do not
add to it. Run `python3 backend/tools/audit-docs.py` for the current set; it is
deliberately not typed here (rule 3). The findings are of two kinds and only one is
a defect in a document:

  C1  neither root declares `kind:` in frontmatter. REAL, and rule 1 says every
      document declares one. Both read as `contract` by that table. The fix is two
      frontmatter blocks and it is the owner's, not a session's: `.claude/CLAUDE.md`
      is harness configuration and the root `README.md` is the repo's front page.

  C4  two hits in `.claude/CLAUDE.md`, and BOTH ARE THE INSTRUMENT, NOT THE FILE.
      The row patterns in `doc-figures.json` make a line compliant when it names its
      metric or cites the owner, and that lookahead is scoped to the PHYSICAL LINE.
      This file is hard-wrapped at ~88 columns, so `94.8%` sits one line above
      `agree2` and `~~1182~~` one line above `AUDIT.md` -- the prose satisfies rule
      3's corollary exactly as written and C4 cannot see it. Task 38 measured every
      one of those patterns line-by-line over `docs/`, where no registered figure
      happened to straddle a wrap; the widening is what surfaced that the unit of
      the claim is the sentence and the unit of the check is the line. Fixing it
      means re-deciding task 38's measured design and re-recording its
      `_pattern_note`s, which is a task, not a side effect of this one.

WHAT THESE TESTS DO NOT ASSERT

That the documents are any good. `audit-docs.py`'s own docstring names what is
deliberately unchecked -- whether a `rationale` entry is sound, whether a `record`
is interesting, whether any sentence in any document is true. A green run here is
a claim about frontmatter, links and identifiers and nothing more.
"""

import contextlib
import importlib.util
import io
import json
import os
import shutil
import sys
import tempfile
import unittest

_TOOLS = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tools")


def _load(name, filename):
    """Import a `tools/` script whose filename has a dash in it."""
    spec = importlib.util.spec_from_file_location(
        name, os.path.join(_TOOLS, filename))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


audit_docs = _load("audit_docs", "audit-docs.py")
audit_doc_links = _load("audit_doc_links", "audit-doc-links.py")

ROOT = audit_docs.REPO_ROOT

#: One walk of docs/ for the whole module. Every check reads every file, and the
#: tree does not change between test methods.
_CACHE = {}


def findings():
    if "f" not in _CACHE:
        _CACHE["f"] = audit_docs.run_checks(ROOT)
    return _CACHE["f"]


class TestDocLinksIsWiredIn(unittest.TestCase):
    """`audit-doc-links.py`, invoked by the suite rather than by memory."""

    def test_no_broken_relative_links_under_docs(self):
        broken = list(audit_doc_links.broken(os.path.join(ROOT, "docs")))
        self.assertEqual(
            [], broken,
            "broken relative link(s) under docs/. Run "
            "`python3 backend/tools/audit-doc-links.py` for the suggested targets. "
            "A broken link is indistinguishable from a missing file to anyone who "
            "does not resolve it -- that is what produced a duplicate task 34.")


class TestPolicyBaseline(unittest.TestCase):
    """The regression gate. See the module docstring for why it is a subset test."""

    def test_findings_are_a_subset_of_the_declared_baseline(self):
        found, _ = findings()
        baseline = audit_docs.load_baseline(ROOT)["checks"]
        new = []
        for finding in found:
            if finding.key not in baseline.get(finding.check, {}).get("findings", []):
                new.append(finding.line())
        self.assertEqual(
            [], new,
            "documentation policy finding(s) NOT in "
            f"{audit_docs.BASELINE_PATH}:\n" + "\n".join(new) +
            "\n\nFix the document. The baseline is for findings that predate "
            "task 36 and are owned by tasks 37-40; it is pruned, never grown.")

    def test_every_baselined_check_names_the_task_that_clears_it(self):
        for check, entry in audit_docs.load_baseline(ROOT)["checks"].items():
            self.assertTrue(
                entry["_cleared_by"].strip(),
                f"{check} has baselined findings and no owner. A tolerated "
                "finding with no owner is a finding nobody will ever clear.")

    def test_baseline_is_declared_for_every_check(self):
        baseline = audit_docs.load_baseline(ROOT)["checks"]
        self.assertEqual(sorted(audit_docs.CHECKS), sorted(baseline))


class TestC5DoesNotFireOnProse(unittest.TestCase):
    """A check that fires on the documents written to satisfy it gets switched off.

    A prototype of C5 run on 2026-08-01 flagged four lines that were all legitimate
    prose, three of them inside tranche seven's own files: a section *about* defect
    D16 in `docs/score-validation.md`, two headings in the task file that FIXES
    D11 and D13, and the old heading quoted inside a fenced code block in the task
    file that RETITLES it. These are the regression tests for that.
    """

    NEVER = (
        "docs/score-validation.md",
        "docs/tasks/refactor/tranche_seven/42-close-the-unblocked-defects.md",
        "docs/tasks/refactor/tranche_seven/39-split-the-d-namespace.md",
    )

    def test_the_four_prose_headings_are_not_findings(self):
        found, _ = findings()
        hit = [f.line() for f in found if f.check == "C5" and f.path in self.NEVER]
        self.assertEqual([], hit)

    def test_a_definition_is_only_ever_a_heading_in_a_register(self):
        found, _ = findings()
        outside = sorted({f.path for f in found if f.check == "C5"
                          and f.path not in audit_docs.REGISTERS})
        self.assertEqual([], outside)


class TestSyntheticTree(unittest.TestCase):
    """Behaviour, on a tree this test builds.

    Asserted here rather than against `docs/` on purpose: tasks 37-40 are clearing
    exactly the findings that make the real tree interesting, and a behavioural test
    that passes only until someone fixes the document is a test that will be deleted
    rather than understood.
    """

    def setUp(self):
        self.root = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.root)
        os.makedirs(os.path.join(self.root, "docs/ingest"))
        os.makedirs(os.path.join(self.root, "docs/tasks/refactor"))
        os.makedirs(os.path.join(self.root, "backend/config"))
        self.write("README.md", "# root\n")

    def write(self, rel, text):
        path = os.path.join(self.root, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(text)

    def figures(self, rows):
        self.write("backend/config/doc-figures.json",
                   json.dumps({"_comment": "test", "_why": "test",
                               "figures": rows}))

    def run_check(self, check):
        found, allowed = audit_docs.run_checks(self.root, [check])
        return found, allowed

    def test_c5_fires_on_a_foreign_prefix_and_on_a_double_definition(self):
        self.write("docs/ingest/DEFECTS.md", "# defects\n\n### D01 - a defect\n")
        self.write("docs/tasks/refactor/DECISIONS.md",
                   "# decisions\n\n## D99 - a decision in the wrong namespace\n"
                   "## DEC-1 - fine\n## DEC-1 - defined twice\n")
        found, _ = self.run_check("C5")
        tokens = sorted(f.key.split("::")[1] for f in found)
        self.assertEqual(["duplicate:DEC-1", "foreign:D99"], tokens)

    def test_c5_never_suggests_an_identifier_the_allocator_forbids(self):
        """`DEC-45` must never be printed. It cannot be allocated, ever.

        An earlier version of C5 answered `### D45` with "re-prefix this heading to
        DEC-45". `DECISIONS.md`'s allocator header starts at `DEC-46` -- the count
        begins there because `DEFECTS.md` burns 46-65 -- so `DEC-45` is an ID the
        allocator will never issue. A checker that suggests one is worse than a
        checker that refuses to guess: the reader either follows it and creates the
        collision rule 6 exists to prevent, or learns to distrust every other
        suggestion the tool makes, which is the reflex that retires all the others.

        The fix is genuinely ambiguous -- fresh allocation, or a retitle to a
        cross-reference -- so C5 refuses, per the contract inherited from
        audit-doc-links.py.
        """
        self.write("docs/ingest/DEFECTS.md", "# defects\n")
        self.write("docs/tasks/refactor/DECISIONS.md",
                   "# decisions\n\n## D45 - a decision numbered in the wrong space\n")
        found, _ = self.run_check("C5")
        self.assertEqual(1, len(found))
        self.assertIsNone(found[0].fix, "C5 must refuse to suggest a fix here")
        line = found[0].line()
        self.assertIn("no unambiguous fix", line)
        self.assertNotIn("re-prefix this heading to DEC-45", line)
        self.assertIn("not DEC-45, which the allocator does not issue", line)

    def test_c5_skips_headings_inside_fenced_code_blocks(self):
        self.write("docs/ingest/DEFECTS.md", "# defects\n")
        self.write("docs/tasks/refactor/DECISIONS.md",
                   "# decisions\n\n```\n## D99 - quoted, not defined\n```\n")
        found, _ = self.run_check("C5")
        self.assertEqual([], [f.line() for f in found])

    def test_c5_does_not_treat_a_named_cross_reference_as_a_definition(self):
        """`### Defect D45 - ...` is the disambiguating form task 39 proposes."""
        self.write("docs/ingest/DEFECTS.md", "# defects\n")
        self.write("docs/tasks/refactor/DECISIONS.md",
                   "# decisions\n\n### Defect D45 - why we did it that way\n")
        found, _ = self.run_check("C5")
        self.assertEqual([], [f.line() for f in found])

    def test_c5_goes_green_on_the_shape_task_39_lands(self):
        """The cross-task contract, pinned rather than promised.

        A DEFINITION IS AN IDENTIFIER AT THE START OF THE HEADING TEXT. Task 39
        keeps two `### Defect D45` headings in `DECISIONS.md` -- they are sections
        ABOUT defect D45, the same case as `docs/score-validation.md:216` -- and
        re-prefixes `D46`-`D65` to `DEC-46`-`DEC-65`, each behind an `<a id=...>`
        anchor so old links still land. A contains-anywhere match would fire on
        `### Defect D45` forever and C5 could never go green, which would make this
        checker the thing that blocks the task written to satisfy it.
        """
        self.write("docs/ingest/DEFECTS.md",
                   "# defects\n\n### D45 - fixed\n### D46 - a real defect\n")
        after_39 = (
            "# decisions\n\n"
            "### Defect D45 - one durability boundary, on the iteration axis\n\n"
            "### Defect D45 - `company_ats` holds every negative\n\n"
            '<a id="d46"></a>\n\n'
            "## DEC-46 - the mock corpus is a specification test\n\n"
            "## DEC-66 - documentation kinds are declared in the file\n")
        self.write("docs/tasks/refactor/DECISIONS.md", after_39)
        self.assertEqual([], [f.line() for f in self.run_check("C5")[0]])

        # ... and the pre-39 spelling is what it fires on, so 39 is what clears it.
        self.write("docs/tasks/refactor/DECISIONS.md",
                   after_39.replace("### Defect D45", "### D45")
                           .replace("## DEC-46", "## D46"))
        tokens = sorted(f.key.split("::")[1] for f in self.run_check("C5")[0])
        self.assertEqual(
            ["duplicate:D45", "foreign:D45", "foreign:D45", "foreign:D46"], tokens)

    def test_c2_reports_an_orphan_and_allows_a_declared_one(self):
        self.write("README.md", "# root\n\n[a](docs/a.md)\n")
        self.write("docs/a.md", "# a\n")
        self.write("docs/lonely.md", "# nobody links here\n")
        self.write("docs/stub.md", "# a deliberate stub\n")
        audit_docs.DELIBERATE_ORPHANS["docs/stub.md"] = "declared for this test"
        self.addCleanup(audit_docs.DELIBERATE_ORPHANS.pop, "docs/stub.md")
        found, allowed = self.run_check("C2")
        self.assertEqual(["docs/stub.md"], allowed)
        self.assertIn("docs/lonely.md", [f.path for f in found])
        self.assertNotIn("docs/stub.md", [f.path for f in found])

    def test_c2_separates_orphan_from_unreached(self):
        """An island of documents citing each other is not reachability."""
        self.write("docs/island-a.md", "# a\n\n[b](island-b.md)\n")
        self.write("docs/island-b.md", "# b\n")
        found, _ = self.run_check("C2")
        by_path = {f.path: f.key for f in found}
        self.assertTrue(by_path["docs/island-a.md"].endswith("::orphan"))
        self.assertTrue(by_path["docs/island-b.md"].endswith("::unreached"))

    def test_c2_reports_a_missing_declared_root_rather_than_crashing(self):
        found, _ = self.run_check("C2")
        self.assertIn("docs/README.md::missing-root", [f.key for f in found])

    def test_c1_suggests_a_kind_only_when_the_siblings_agree(self):
        self.write("docs/ingest/one.md", "---\nkind: contract\n---\n# one\n")
        self.write("docs/ingest/two.md", "# two, undeclared\n")
        self.write("docs/tasks/refactor/x.md", "---\nkind: task\n---\n# x\n")
        self.write("docs/tasks/refactor/y.md", "---\nkind: record\n---\n# y\n")
        self.write("docs/tasks/refactor/z.md", "# z, undeclared\n")
        found = {f.path: f for f in self.run_check("C1")[0]}
        self.assertIn("kind: contract", found["docs/ingest/two.md"].fix)
        self.assertIsNone(found["docs/tasks/refactor/z.md"].fix)

    def test_c1_rejects_a_kind_outside_the_five(self):
        self.write("docs/odd.md", "---\nkind: notes\n---\n# odd\n")
        found = {f.path: f for f in self.run_check("C1")[0]}
        self.assertIn("'notes' is not one of", found["docs/odd.md"].problem)

    def test_c4_flags_outside_the_owner_and_honours_an_explicit_allowance(self):
        self.figures([{"name": "widget count", "owner": "docs/owner.md",
                       "pattern": r"\b42\b", "allowed": ["docs/frozen/*"]}])
        self.write("docs/owner.md", "# owner\n\nthe count is 42\n")
        self.write("docs/copy.md", "# copy\n\nsomeone typed 42 here\n")
        self.write("docs/frozen/old.md", "# old\n\nit was 42 back then\n")
        self.write("docs/quoted.md", "# quoted\n\n```\n$ echo 42\n```\n")
        found, _ = self.run_check("C4")
        self.assertEqual(["docs/copy.md"], [f.path for f in found])

    def test_the_declared_roots_outside_docs_are_scanned_for_figures(self):
        """The rule 7 gap `AUDIT.md` named: roots were C2 roots and nothing else.

        `.claude/CLAUDE.md` and the root `README.md` are the two most-read documents
        in the repo and both carry figures, and until this they were checked by a
        `grep` in one task's Definition of done that a person has to remember to run
        -- which `DOCS-POLICY.md` rule 7 says is exactly one step better than prose.
        """
        self.figures([{"name": "widget count", "owner": "docs/owner.md",
                       "pattern": r"\b42\b", "allowed": []}])
        self.write("docs/owner.md", "# owner\n\nthe count is 42\n")
        self.write("README.md", "# root\n\nsomeone typed 42 here\n")
        self.write(".claude/CLAUDE.md", "# session context\n\nand 42 here too\n")
        found, _ = self.run_check("C4")
        self.assertEqual([".claude/CLAUDE.md", "README.md"],
                         sorted(f.path for f in found))

    def test_c1_reads_the_external_roots_too(self):
        """Rule 1 says EVERY document declares its kind, and these are documents."""
        self.write("README.md", "# root, undeclared\n")
        self.write(".claude/CLAUDE.md", "---\nkind: contract\n---\n# declared\n")
        found = {f.path: f for f in self.run_check("C1")[0]}
        self.assertIn("README.md", found)
        self.assertNotIn(".claude/CLAUDE.md", found)

    def test_a_root_is_never_reported_as_an_orphan(self):
        """C2 is the one check the roots are exempt from, and not as a favour.

        Reachability is defined FROM these files. Asking whether the thing the walk
        starts at was reached by the walk is a category error, and answering it
        would put a permanent unfixable finding on the file every session opens
        first -- which is the reflex that retires every other check.
        """
        self.write("README.md", "# root, linked from nowhere\n")
        self.write(".claude/CLAUDE.md", "# also linked from nowhere\n")
        found, _ = self.run_check("C2")
        self.assertEqual([], [f.path for f in found if not f.path.startswith("docs/")])

    def test_a_declared_root_that_does_not_exist_is_c2s_finding_and_only_c2s(self):
        """One missing file is one finding. `.claude/CLAUDE.md` is absent here."""
        self.assertNotIn(".claude/CLAUDE.md", audit_docs.external_roots(self.root))
        self.assertEqual([], [f.path for f in self.run_check("C1")[0]
                              if f.path == ".claude/CLAUDE.md"])
        self.assertIn(".claude/CLAUDE.md::missing-root",
                      [f.key for f in self.run_check("C2")[0]])

    def test_docs_files_stays_narrow_and_scanned_files_is_the_wider_set(self):
        """The widening is visible in the names, not hidden inside a walk."""
        self.write("README.md", "# root\n")
        self.write("docs/a.md", "# a\n")
        self.assertEqual(["docs/a.md"], audit_docs.docs_files(self.root))
        self.assertEqual(["README.md"], audit_docs.external_roots(self.root))
        self.assertEqual(["docs/a.md", "README.md"],
                         audit_docs.scanned_files(self.root))

    def test_external_roots_is_derived_from_ROOTS_and_is_not_a_second_list(self):
        """A second list of roots would be a figure copied to two places."""
        self.write("README.md", "# root\n")
        for rel in audit_docs.external_roots(self.root):
            self.assertIn(rel, audit_docs.ROOTS)

    def test_c6_wants_a_date_and_a_supersede_word_in_a_blockquote(self):
        os.makedirs(os.path.join(self.root, "docs/archive"))
        self.write("docs/archive/README.md", "# the archive index, exempt\n")
        self.write("docs/archive/good.md",
                   "# a measurement\n\n> **Archived from HANDOFF.md on 2026-07-31.**\n"
                   "> Recorded 2026-07-29.\n")
        self.write("docs/archive/nodate.md", "# a measurement\n\n> Archived.\n")
        self.write("docs/archive/bare.md", "# a measurement\n\nno header at all\n")
        found = {f.path: f.problem for f in self.run_check("C6")[0]}
        self.assertNotIn("docs/archive/README.md", found)
        self.assertNotIn("docs/archive/good.md", found)
        self.assertIn("a date", found["docs/archive/nodate.md"])
        self.assertIn("a provenance blockquote", found["docs/archive/bare.md"])


class TestRollingStaleness(unittest.TestCase):
    """C3, in a throwaway git repo, because on the real tree it finds nothing.

    Nothing in `docs/` declares `kind: rolling` yet -- task 37 is what labels
    `HANDOFF.md` -- so C3 reports 0 today and a green C3 is evidence of nothing at
    all. These build the situation rule 4 exists for: a rolling document that sat
    still while its subject moved. `HANDOFF.md`'s sixty-second entry point went on
    sending fresh sessions to a task that had already finished, and nothing was red.
    """

    def setUp(self):
        self.root = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.root)
        self.git("init", "-q")
        self.git("config", "user.email", "t@example.invalid")
        self.git("config", "user.name", "test")
        os.makedirs(os.path.join(self.root, "docs"))
        os.makedirs(os.path.join(self.root, "backend"))
        # Two commits' worth of threshold, so the test does not depend on 25.
        self.threshold = audit_docs.ROLLING_STALE_COMMITS
        audit_docs.ROLLING_STALE_COMMITS = 2
        self.addCleanup(setattr, audit_docs, "ROLLING_STALE_COMMITS", self.threshold)

    def git(self, *args):
        import subprocess
        subprocess.run(["git"] + list(args), cwd=self.root, check=True,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    def commit(self, rel, text, message):
        path = os.path.join(self.root, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(text)
        self.git("add", "-A")
        self.git("commit", "-q", "--no-gpg-sign", "-m", message)

    def test_a_rolling_document_whose_subject_moved_without_it_is_stale(self):
        self.commit("docs/handoff.md",
                    "---\nkind: rolling\nsubject: backend\n---\n# what to do next\n",
                    "write the handoff")
        for i in range(3):
            self.commit(f"backend/step{i}.py", f"# {i}\n", f"land step {i}")
        found, _ = audit_docs.run_checks(self.root, ["C3"])
        self.assertEqual(1, len(found), [f.line() for f in found])
        line = found[0].line()
        self.assertIn("docs/handoff.md", line)
        self.assertIn("has moved 3 times", line)
        self.assertIn("roll it forward, or archive it", line)

    def test_a_rolling_document_that_kept_up_is_not_stale(self):
        self.commit("docs/handoff.md",
                    "---\nkind: rolling\nsubject: backend\n---\n# what to do next\n",
                    "write the handoff")
        self.commit("backend/step.py", "# 0\n", "land one thing")
        self.assertEqual([], audit_docs.run_checks(self.root, ["C3"])[0])

    def test_a_non_rolling_document_is_never_stale(self):
        self.commit("docs/frozen.md", "---\nkind: record\n---\n# measured once\n",
                    "record a measurement")
        for i in range(5):
            self.commit(f"backend/step{i}.py", f"# {i}\n", f"land step {i}")
        self.assertEqual([], audit_docs.run_checks(self.root, ["C3"])[0])

    def test_without_git_c3_reports_nothing_rather_than_guessing(self):
        """An unknown history is not evidence of staleness."""
        bare = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, bare)
        os.makedirs(os.path.join(bare, "docs"))
        with open(os.path.join(bare, "docs/handoff.md"), "w", encoding="utf-8") as fh:
            fh.write("---\nkind: rolling\n---\n# rolling, but untracked\n")
        self.assertEqual([], audit_docs.run_checks(bare, ["C3"])[0])


class TestContract(unittest.TestCase):
    """The parts of task 36's Definition of done that are properties of the tool."""

    def test_exit_code_is_non_zero_while_anything_fires(self):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = audit_docs.main(["audit-docs.py"])
        found, _ = findings()
        self.assertEqual(1 if found else 0, code)

    def test_help_names_every_check(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out), self.assertRaises(SystemExit):
            audit_docs.main(["audit-docs.py", "--help"])
        text = out.getvalue()
        for check in audit_docs.CHECKS:
            self.assertIn(check, text)

    def test_c3_threshold_is_a_named_constant(self):
        """A bare integer buried in the check would be a Definition-of-done failure."""
        self.assertIsInstance(audit_docs.ROLLING_STALE_COMMITS, int)
        self.assertGreater(audit_docs.ROLLING_STALE_COMMITS, 0)
        with open(os.path.join(_TOOLS, "audit-docs.py"), encoding="utf-8") as fh:
            source = fh.read()
        self.assertIn("WHY 25", source, "the threshold has no comment explaining it")
        self.assertEqual(1, source.count("ROLLING_STALE_COMMITS = "))

    def test_valid_kinds_are_the_five_DOCS_POLICY_declares(self):
        with open(os.path.join(ROOT, "docs/DOCS-POLICY.md"), encoding="utf-8") as fh:
            policy = fh.read()
        for kind in audit_docs.VALID_KINDS:
            self.assertIn(f"| `{kind}` |", policy,
                          f"{kind!r} is accepted by the checker but is not a row in "
                          "DOCS-POLICY.md rule 1's table")

    def test_the_figure_declaration_carries_its_rationale(self):
        figures = audit_docs.load_figures(ROOT)
        self.assertTrue(figures["_comment"].strip())
        self.assertTrue(figures["_why"].strip())
        for row in figures["figures"]:
            self.assertTrue(row.get("_note", "").strip(),
                            f"{row['name']!r} has no _note saying where it came from")


if __name__ == "__main__":
    unittest.main()

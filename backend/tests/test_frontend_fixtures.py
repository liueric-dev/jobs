"""`frontend/verify_fixtures.py`, run by the suite rather than by memory.

Run:  python3 -m unittest tests.test_frontend_fixtures

WHY THIS FILE EXISTS

The bar is **"fails a suite someone is already running"**, not "has a script".
(It was `git show refactor-freeze-2026-08-02:docs/DOCS-POLICY.md` rule 7,
deleted 2026-08-02. The rule outlived the
document: it is why `tools/audit-citations.py` is pinned by
`tests/test_citations.py` rather than left to be typed.)
`frontend/verify_fixtures.py` was the same shape of gap
`git show refactor-freeze-2026-08-02:backend/tools/audit-doc-links.py` was before task 36: a checker
that exits 0 and is wired into nothing. Grepped 2026-08-02 -- no module under
`backend/tests/` or `backend/webapp/tests/` referenced it, `.git/hooks` holds
only `.sample` files, and there is no CI configuration in the repo. It had held
for one day, and only because a person typed the command.

The thing it protects is worth the wiring. `frontend/fixtures/shipped/` is what
the client's parser was built against, and its own docstring names the failure:
a fixture nobody re-checks becomes a description of an API that used to exist,
which is worse than no fixture because it is confidently wrong. The check that
breaks is a shape check -- add a column to `LIST_COLUMNS` in
`backend/webapp/jobs.py` and every fixture is stale in the same instant.

WHY IT SHELLS OUT INSTEAD OF IMPORTING

A checker whose *findings* a test asserts on should be imported --
`git show refactor-freeze-2026-08-02:backend/tests/test_docs_policy.py` did that, and retired 2026-08-02 with the documents
it checked. This one asserts on the **exit status**, which is the
whole contract `frontend/README.md` documents (`python3 frontend/verify_fixtures.py`
-> 0 or 1), so running it the way a person runs it is the honest test. It is
stdlib-only and reads `backend/webapp/*.py` with `ast` rather than importing
them, so it runs under the top level's bare system python3 -- no venv, and the
same interpreter this suite is already in.

WHAT THE SECOND TEST IS FOR

A checker whose first run is green has been tested against nothing. `test_the_
verifier_fails_on_a_stale_fixture` builds a throwaway copy of the tree, breaks
one fixture in it, and asserts a non-zero exit -- so this file fails if someone
ever reduces `verify_fixtures.py` to a script that prints and returns 0.

AND THE CLIENT HALF

`verify_fixtures.py` checks that the fixtures still describe the SERVER.
`frontend/check_client.mjs` checks that the CLIENT still agrees with the
fixtures and with three vocabularies it copies out of Python -- `ROLE_TRACK`
(`backend/extract.py`), `DISMISS_REASONS` (`backend/webapp/schema_web.py`) and
`CLIENT_EVENT_NAMES` (`backend/webapp/jobs.py`). Shape is not behaviour: a
correctly-shaped JSON string is still a client bug if nobody parses it, and
`apply` is a well-formed string that is a 400 (`DEC-73`).

That one needs node, which is NOT a dependency of this repo, so its case skips
when node is absent -- the same arrangement the scratch-database modules use,
and `.claude/CLAUDE.md`'s "read the `Ran N tests` line, not a static count; a
skip is not a failure" is written for exactly this.
"""

import ast
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
FRONTEND = os.path.join(REPO, "frontend")
VERIFY = os.path.join(FRONTEND, "verify_fixtures.py")
CHECK_CLIENT = os.path.join(FRONTEND, "check_client.mjs")
NODE = shutil.which("node")

def _verifier_sources():
    """The `backend/` modules verify_fixtures.py parses, read out of
    verify_fixtures.py itself. Paths relative to `backend/`.

    DERIVED RATHER THAN LISTED, AND THE LIST IS WHY. This was the literal
    ``("jobs.py", "auth.py", "schema_web.py")``. On 2026-08-02 the verifier
    grew a fourth -- ``onboarding.py``, for the onboarding fixtures task 26's
    screen moved into ``shipped/`` -- and the synthetic tree below stopped
    containing everything the verifier reads. The script then died on a missing
    file, which is still a non-zero exit, so the assertion that it "goes red"
    PASSED FOR THE WRONG REASON and only the assertion on its *output* noticed.

    That is `D70`'s shape one layer out: a check stops being a derivation
    exactly where its hardcoding starts, and that is where the next file lands.
    So the list is read from the source of truth, and a fifth module costs
    nothing here.

    AND IT LANDED AGAIN, ONE DIRECTORY UP, ON 2026-08-02. The pattern above was
    ``= REPO / "backend" / "webapp" / "<file>"`` -- derived in the filename and
    HARDCODED IN THE DIRECTORY. Task 32's search screen made the verifier read
    ``backend/searchnorm.py`` and ``backend/schema.py``, which are top-level
    pipeline modules on purpose (one normaliser and one bucket vocabulary,
    shared by both processes), and neither matched. Exactly the same failure
    mode as the one this docstring already described, displaced by one path
    segment: the seam moved from the filename to the directory. So the pattern
    now reads any depth under ``backend/``.
    """
    source = open(VERIFY, encoding="utf-8").read()
    matches = re.findall(r'= REPO / "backend"((?: / "[\w.]+")+)', source)
    assert matches, (
        "verify_fixtures.py no longer names its sources as "
        '`REPO / "backend" / ... / "<file>"`, so this test cannot build a '
        "tree containing them. Fix the pattern above, do not delete the check.")
    paths = [tuple(re.findall(r'"([\w.]+)"', tail)) for tail in matches]
    return tuple(dict.fromkeys(p for p in paths if p[-1].endswith(".py")))


#: The modules verify_fixtures.py parses, as path tuples relative to `backend/`.
#: Copied into the synthetic tree below so the second test exercises the real
#: comparison rather than a stub.
VERIFIER_SOURCES = _verifier_sources()


def _run(script):
    return subprocess.run([sys.executable, script], capture_output=True, text=True)


class TestVerifyFixturesIsWiredIn(unittest.TestCase):

    def test_the_script_is_where_the_documentation_says_it_is(self):
        self.assertTrue(
            os.path.isfile(VERIFY),
            f"{VERIFY} is missing. frontend/README.md documents "
            "`python3 frontend/verify_fixtures.py` as the way to check that the "
            "frozen fixtures still describe the API.")

    def test_the_shipped_fixtures_still_match_the_code(self):
        result = _run(VERIFY)
        self.assertEqual(
            0, result.returncode,
            "frontend/fixtures/shipped/ no longer describes "
            f"backend/{{{', '.join('/'.join(p) for p in VERIFIER_SOURCES)}}}.\n\n"
            f"{result.stdout}{result.stderr}\n"
            "Either a fixture is stale or a response shape changed by accident. "
            "There is no generator: fix the JSON by hand and re-run "
            "`python3 frontend/verify_fixtures.py`.")

    def test_the_verifier_fails_on_a_stale_fixture(self):
        """A green checker that cannot go red is not a checker.

        Built on a copy rather than by mutating the real tree, so a failure
        here cannot leave the repo dirty.
        """
        with tempfile.TemporaryDirectory() as root:
            frontend = os.path.join(root, "frontend")
            shutil.copytree(FRONTEND, frontend,
                            ignore=shutil.ignore_patterns("__pycache__"))
            for parts in VERIFIER_SOURCES:
                destination = os.path.join(root, "backend", *parts)
                os.makedirs(os.path.dirname(destination), exist_ok=True)
                shutil.copy(os.path.join(REPO, "backend", *parts), destination)

            # THE COPY MUST BE GREEN BEFORE IT IS BROKEN, and this line is here
            # because its absence let a real bug through on 2026-08-02: the
            # verifier grew a fourth webapp source, the tree below did not have
            # it, and the script died on a missing file -- which is a non-zero
            # exit, so "it goes red" passed while proving nothing at all. A
            # mutation test is only evidence if the unmutated case passes.
            clean = _run(os.path.join(frontend, "verify_fixtures.py"))
            self.assertEqual(
                0, clean.returncode,
                "the synthetic tree does not satisfy verify_fixtures.py before "
                "anything was broken in it, so the mutation below proves "
                "nothing. Usually this means the verifier reads a file "
                "WEBAPP_SOURCES did not copy.\n\n"
                f"{clean.stdout}{clean.stderr}")

            # Drop one key from one job object. That is exactly the drift this
            # exists to catch -- a column added to or removed from LIST_COLUMNS
            # shows up as a key set that no longer matches.
            path = os.path.join(frontend, "fixtures", "shipped", "GET_v1_jobs.json")
            with open(path, encoding="utf-8") as fh:
                body = json.load(fh)
            del body["jobs"][0]["match_score"]
            with open(path, "w", encoding="utf-8") as fh:
                json.dump(body, fh)

            result = _run(os.path.join(frontend, "verify_fixtures.py"))
            self.assertNotEqual(
                0, result.returncode,
                "verify_fixtures.py exited 0 on a fixture missing a key from "
                "LIST_COLUMNS. It is no longer checking shape, so wiring it "
                "into this suite proves nothing.")
            self.assertIn("match_score", result.stdout)


class TestClientAgreesWithTheFixtures(unittest.TestCase):
    """`frontend/check_client.mjs`, the other half of the contract test.

    Skipped rather than failed where node is absent: it is not a dependency of
    this repo and installing one to run a test would be a worse trade than the
    gap. Where node IS present -- which is the normal checkout -- this runs.
    """

    @unittest.skipUnless(NODE, "node is not installed")
    def test_the_client_modules_agree_with_shipped_and_with_the_source(self):
        result = subprocess.run([NODE, CHECK_CLIENT], capture_output=True, text=True)
        self.assertEqual(
            0, result.returncode,
            "the client no longer agrees with frontend/fixtures/shipped/ or with "
            "the Python vocabularies it copies.\n\n"
            f"{result.stdout}{result.stderr}")


class TestTheLauncherStillDefaultsToLoopback(unittest.TestCase):
    """`frontend/serve.py --host` exists, and its default did not move.

    `--host` was added so task 32's phone test does not have to wait for task
    33's tunnel. The risk it introduces is the obvious one: a default that
    quietly becomes 0.0.0.0 puts an app running with SESSION_COOKIE_SECURE
    false, and no TLS, on the LAN of whoever next runs the documented command.
    Nothing else in the repo would notice.

    Read with `ast` rather than imported, exactly as `verify_fixtures.py` reads
    `backend/webapp/*.py`: this module runs under the top level's bare system
    python3, which has no fastapi and cannot import serve.py at all.
    """

    def setUp(self):
        with open(os.path.join(FRONTEND, "serve.py"), encoding="utf-8") as fh:
            self.tree = ast.parse(fh.read())

    def _assign(self, name):
        for node in ast.walk(self.tree):
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name) and target.id == name:
                        value = node.value
                        # literal_eval has no opinion about frozenset({...}),
                        # which is the form LOOPBACK_HOSTS is written in.
                        if (isinstance(value, ast.Call)
                                and isinstance(value.func, ast.Name)
                                and value.func.id in ("frozenset", "set")):
                            value = value.args[0]
                        return ast.literal_eval(value)
        self.fail(f"{name} is not assigned in serve.py")

    def test_the_default_host_is_loopback(self):
        self.assertEqual("127.0.0.1", self._assign("DEFAULT_HOST"))

    def test_the_argparse_default_is_that_constant_and_not_a_literal(self):
        """A second spelling of the address is a second thing to get wrong."""
        for node in ast.walk(self.tree):
            if (isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Attribute)
                    and node.func.attr == "add_argument"
                    and node.args and getattr(node.args[0], "value", None) == "--host"):
                default = [kw.value for kw in node.keywords if kw.arg == "default"]
                self.assertTrue(default, "--host has no default; it would bind nothing")
                self.assertIsInstance(
                    default[0], ast.Name,
                    "--host's default is written as a literal rather than "
                    "DEFAULT_HOST, so the two can drift")
                self.assertEqual("DEFAULT_HOST", default[0].id)
                return
        self.fail("serve.py no longer declares a --host argument")

    def test_loopback_hosts_are_all_loopback(self):
        """The set decides whether the LAN warnings print. A stray public
        address in it would silence them for exactly the case they exist for."""
        self.assertEqual({"127.0.0.1", "localhost", "::1"},
                         set(self._assign("LOOPBACK_HOSTS")))


if __name__ == "__main__":
    unittest.main()

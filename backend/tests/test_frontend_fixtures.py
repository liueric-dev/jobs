"""`frontend/verify_fixtures.py`, run by the suite rather than by memory.

Run:  python3 -m unittest tests.test_frontend_fixtures

WHY THIS FILE EXISTS

`docs/DOCS-POLICY.md` rule 7 sets the bar at **"fails a suite someone is already
running"**, not at "has a script". `frontend/verify_fixtures.py` was the same
shape of gap `backend/tools/audit-doc-links.py` was before task 36: a checker
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

`tests/test_docs_policy.py` imports its two checkers because it asserts on the
*findings* they return. This one asserts on the **exit status**, which is the
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

import json
import os
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

#: The three modules verify_fixtures.py parses. Copied into the synthetic tree
#: below so the second test exercises the real comparison rather than a stub.
WEBAPP_SOURCES = ("jobs.py", "auth.py", "schema_web.py")


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
            "backend/webapp/{jobs,auth,schema_web}.py.\n\n"
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
            webapp = os.path.join(root, "backend", "webapp")
            shutil.copytree(FRONTEND, frontend,
                            ignore=shutil.ignore_patterns("__pycache__"))
            os.makedirs(webapp)
            for name in WEBAPP_SOURCES:
                shutil.copy(os.path.join(REPO, "backend", "webapp", name),
                            os.path.join(webapp, name))

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


if __name__ == "__main__":
    unittest.main()

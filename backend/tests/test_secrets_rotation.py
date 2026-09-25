"""Check that ingestion credentials remain untracked and environment-based.

The scheduled pipeline loads .env on each run, so rotating a key does not
require a code change or redeploy. These tests inspect files only.
"""

import os
import re
import subprocess
import unittest

BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPO_ROOT = os.path.dirname(BACKEND_DIR)

#: The env vars that carry a credential. Assembled from the .env.example
#: files rather than typed, so a key added to a service's example is covered
#: here on the day it is added -- see test_the_credential_list_is_derived.
_CREDENTIAL_HINT = re.compile(r"(KEY|TOKEN|SECRET|PASSWORD|DATABASE_URL)$")

#: Files that are ALLOWED to name a credential variable: the examples, which
#: hold placeholders by definition, and this test.
_EXAMPLE_SUFFIX = ".env.example"


def _git(*args):
    return subprocess.run(["git", *args], cwd=REPO_ROOT,
                          capture_output=True, text=True)


def _tracked_files():
    result = _git("ls-files")
    return [p for p in result.stdout.splitlines()
            if p and os.path.isfile(os.path.join(REPO_ROOT, p))]


def _credential_names():
    names = set()
    for rel in _tracked_files():
        if not rel.endswith(_EXAMPLE_SUFFIX):
            continue
        with open(os.path.join(REPO_ROOT, rel), encoding="utf-8") as fh:
            for line in fh:
                key = line.split("=", 1)[0].strip()
                if key and _CREDENTIAL_HINT.search(key):
                    names.add(key)
    return names


class TestNoSecretIsCommittable(unittest.TestCase):
    """.gitignore covers the files a credential lives in.

    Asserted through `git check-ignore` rather than by reading .gitignore,
    because what matters is git's answer after every pattern, negation and
    precedence rule has been applied -- and this repo has already been bitten
    once by a pattern that matched at a depth nobody intended (`scripts/`, fixed
    in the past)."""

    def test_env_files_are_ignored_and_examples_are_not(self):
        cases = [
            ("backend/.env", True),
            ("backend/.env.local", True),
            ("backend/.env.example", False),
            # cloudflared's two credentials. The tunnel JSON is a bearer
            # credential for the tunnel itself: whoever holds it can run the
            # tunnel and receive traffic for its hostnames.
            ("deploy/cloudflared/cert.pem", True),
            ("deploy/cloudflared/a1b2c3d4-0000-0000-0000-abcdef123456.json", True),
        ]
        for path, should_be_ignored in cases:
            with self.subTest(path=path):
                ignored = _git("check-ignore", "-q", path).returncode == 0
                self.assertEqual(
                    ignored, should_be_ignored,
                    f"{path}: ignored={ignored}, expected {should_be_ignored}")

    def test_no_env_file_is_tracked(self):
        """The one that would actually leak. `.env.*` plus `!.env.example` is
        subtle enough to get wrong, and a public repo makes a mistake here
        permanent in the host's history."""
        tracked = [p for p in _tracked_files()
                   if os.path.basename(p).startswith(".env")
                   and not p.endswith(_EXAMPLE_SUFFIX)]
        self.assertEqual(tracked, [])

    def test_no_private_key_or_credential_blob_is_tracked(self):
        bad = [p for p in _tracked_files()
               if p.endswith((".pem", ".key"))
               or os.path.basename(p) in ("secrets.json", "credentials.json")]
        self.assertEqual(bad, [])

    def test_backend_scripts_is_not_ignored(self):
        """An unanchored `scripts/` pattern matched at every
        depth, so backend/scripts/ was ignored; the four files already there
        were unaffected (tracking beats .gitignore) and nothing was red. What
        broke was the next file added -- a backup script that silently was not
        in the repo, which is the same shape of failure as a backup that
        silently was not running."""
        self.assertNotEqual(
            _git("check-ignore", "-q", "backend/scripts/backup-jobs.sh").returncode,
            0,
            "backend/scripts/ is ignored again; anchor the root pattern to "
            "/scripts/ -- see the comment in .gitignore")


class TestKeysAreRotatableWithoutARedeploy(unittest.TestCase):

    def test_the_credential_list_is_derived_and_non_empty(self):
        """If this ever comes back empty the two tests below pass vacuously,
        which is the way a check like this dies quietly."""
        names = _credential_names()
        self.assertTrue(names)
        for expected in ("DATABASE_URL",):
            self.assertIn(expected, names)

    def test_every_credential_is_read_from_the_environment_only(self):
        """No credential is ever assigned a literal in tracked code.

        The check is the assignment form: `NAME = "..."` or `NAME: "..."` with a
        non-empty string on the right. Reads (`os.environ.get("NAME")`) and
        empty-string defaults are what the codebase should look like and are
        allowed; a hard-coded value is a key that cannot be rotated without a
        commit.

        The value must be a LITERAL: `$`, `{` and `%` are excluded from it, so
        an indirection through the environment is not a finding. That exclusion
        is not cosmetic -- without it this fires on
        `backend/scripts/backfill-facts.sh:22`,
        `export JOB_SCORING_API_KEY="${JOB_SCORING_API_KEY:-$DEEPSEEK_API_KEY}"`,
        which is precisely the correct pattern: a default read from another
        environment variable and nothing baked in."""
        names = _credential_names()
        pattern = re.compile(
            r"""(?:^|[^\w.])(%s)\s*[:=]\s*["'][^"'\s${}%%]+["']"""
            % "|".join(sorted(re.escape(n) for n in names)))
        offenders = []
        for rel in _tracked_files():
            if not rel.endswith((".py", ".sh", ".mjs", ".yml", ".yaml", ".json",
                                 ".service", ".timer")):
                continue
            if rel.endswith(_EXAMPLE_SUFFIX) or rel.endswith(os.path.basename(__file__)):
                continue
            with open(os.path.join(REPO_ROOT, rel), encoding="utf-8",
                      errors="replace") as fh:
                for lineno, line in enumerate(fh, 1):
                    if pattern.search(line):
                        offenders.append(f"{rel}:{lineno}: {line.strip()}")
        self.assertEqual(offenders, [],
                         "credential assigned a literal in tracked code; "
                         "rotating it would require a commit")

    def test_the_pipeline_reloads_env_on_every_run(self):
        """The property that makes the pipeline need no restart at all: it
        establishes its own environment from ./.env at the top of main(), and
        every step is a subprocess inheriting it. Pinned because the 2026-07-25
        run failed all seven steps at once when nothing put that file back."""
        with open(os.path.join(BACKEND_DIR, "run-daily.py"), encoding="utf-8") as fh:
            source = fh.read()
        body = source[source.index("def main("):]
        self.assertIn("envfile.load(ENV_FILE)", body)
        self.assertLess(body.index("envfile.load(ENV_FILE)"),
                        body.index("for step in STEPS"),
                        "the environment must be established before any step "
                        "runs, or a rotated key reaches none of them")
        self.assertIn("env=os.environ.copy()", source,
                      "steps must inherit the reloaded environment")

    def test_no_credential_is_baked_into_a_systemd_unit(self):
        """Units reference EnvironmentFile=; they never carry Environment=KEY=.
        A key inside a unit is a key that needs `systemctl --user
        daemon-reload` and a file outside the repo to rotate, which is the
        redeploy this property exists to avoid."""
        names = _credential_names()
        offenders = []
        for rel in _tracked_files():
            if not rel.endswith((".service", ".timer")):
                continue
            with open(os.path.join(REPO_ROOT, rel), encoding="utf-8") as fh:
                for lineno, line in enumerate(fh, 1):
                    stripped = line.strip()
                    if not stripped.startswith("Environment="):
                        continue
                    if any(f"{n}=" in stripped for n in names):
                        offenders.append(f"{rel}:{lineno}: {stripped}")
        self.assertEqual(offenders, [])


if __name__ == "__main__":
    unittest.main()

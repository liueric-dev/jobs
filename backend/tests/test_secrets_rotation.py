"""Secrets: gitignored, absent from the tree, and rotatable without a redeploy.

WHY "ROTATABLE WITHOUT A REDEPLOY" IS A TESTABLE PROPERTY AND NOT A SLOGAN

Free-tier keys accumulate here -- the LLM key, SerpApi, Apify, Socrata, Adzuna,
plus Google OAuth -- and free-tier keys are rotated often, by whoever is holding
the pager, under time pressure. The property that makes that safe is narrow and
mechanical:

    NO CREDENTIAL IS A LITERAL IN TRACKED CODE, AND NO CREDENTIAL IS READ FROM
    ANYWHERE BUT THE PROCESS ENVIRONMENT.

If both hold, rotation is `edit .env` plus, for the two long-lived services, a
`systemctl --user restart`. Nothing is rebuilt, no file under version control
changes, and no commit is needed -- so a rotation at 23:00 cannot become a
deploy at 23:00. If either fails, rotating a key means editing code, which means
a commit, a review and a push, which means it does not happen.

THE ASYMMETRY WORTH KNOWING, and it is recorded here rather than smoothed over:
the pipeline needs no restart AT ALL, because run-daily.py:237 calls
envfile.load() at the top of every run and every step is a fresh subprocess
inheriting that environment (run-daily.py:191). The next nightly run picks up a
new key on its own. webapp/ and api/ are long-lived uvicorn processes that read
config at import, so they need a restart -- which is still not a redeploy, and
docs/RUNBOOK.md says which is which.

WHAT THIS DOES NOT CHECK. Whether the key in `.env` is valid, whether it has
quota left, or whether the provider has revoked it. Those are silent failures
that return zero rows, and they are caught by volume, not here --
tests/test_volume_floors.py and config/volume-floors.json.

Offline: reads tracked files and runs `git check-ignore`. No network, no
database, no live credential.
"""

import os
import re
import subprocess
import unittest

BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPO_ROOT = os.path.dirname(BACKEND_DIR)

#: The env vars that carry a credential. Assembled from the three .env.example
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
    return [p for p in result.stdout.splitlines() if p]


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
    by task 33)."""

    def test_env_files_are_ignored_and_examples_are_not(self):
        cases = [
            ("backend/.env", True),
            ("backend/.env.local", True),
            ("backend/api/.env", True),
            ("backend/webapp/.env", True),
            ("backend/.env.example", False),
            ("backend/api/.env.example", False),
            ("backend/webapp/.env.example", False),
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
        """The landmine task 33 found. `scripts/` unanchored matched at every
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
        for expected in ("SERPAPI_API_KEY", "APIFY_API_TOKEN", "DATABASE_URL"):
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


class TestTheContributorApiNeverLogsAPayload(unittest.TestCase):
    """A contributor's SerpApi key lives on their machine and the API only ever
    receives results. That holds only if nothing here writes a submitted body
    somewhere it would persist -- a journal line, a log file, or a database
    column -- because a worker that accidentally put its key in a payload would
    then have leaked it to the operator permanently.

    The audit behind this test, and its result, are in docs/RUNBOOK.md."""

    def test_nothing_under_api_writes_to_stdout_or_a_logger_at_request_time(self):
        api_dir = os.path.join(BACKEND_DIR, "api")
        emit = re.compile(r"(?:^|[^\w.])(print\s*\(|logging\.|logger\.|"
                          r"sys\.std(?:out|err)\.write)")
        offenders = []
        for name in ("app.py", "query_claims.py"):
            path = os.path.join(api_dir, name)
            with open(path, encoding="utf-8") as fh:
                for lineno, line in enumerate(fh, 1):
                    if line.lstrip().startswith("#"):
                        continue
                    if emit.search(line):
                        offenders.append(f"api/{name}:{lineno}: {line.strip()}")
        self.assertEqual(
            offenders, [],
            "a request-path emit in the contributor API: confirm it cannot "
            "carry a submitted payload, then allow it here explicitly")

    def test_submission_log_records_counts_and_not_bodies(self):
        """`submission_log` is the one table this service writes about a
        submission itself. It must hold counts and a reason, never the payload."""
        with open(os.path.join(BACKEND_DIR, "api", "app.py"), encoding="utf-8") as fh:
            source = fh.read()
        for insert in re.findall(r"INSERT INTO submission_log[^)]*\)", source):
            self.assertNotIn("payload", insert.lower())
            self.assertNotIn("body", insert.lower())
            self.assertNotIn("raw", insert.lower())


if __name__ == "__main__":
    unittest.main()

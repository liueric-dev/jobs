"""T-44: importing a sibling process's config must not pick this tool's database.

WHAT WENT WRONG. `tools/provision-database.py` imports `webapp/config.py` at
module scope, for the sys.path insert the rest of that package relies on.
That module calls `envfile.load(webapp/.env)` in its body (webapp/config.py:40),
and webapp/.env sets DATABASE_URL to `jobs_web`. Both that load and the tool's
own `envfile.load(backend/.env)` are override=False (lib/envfile.py:85), so the
first one to run wins -- and an import always runs before main(). On any machine
with a webapp/.env the tool connected as `jobs_web`, a role with no DDL rights.

WHY IT WAS INVISIBLE, AND WHY THAT SHAPES THIS FILE. A fresh checkout and CI
have no webapp/.env, so the only path either ever exercised was the one that
already worked. A test that reproduces the bug end to end therefore needs a file
CI does not have, and a test that skips without it would be a skip CI's suites
job forbids. So the coverage here is split in two, and both halves are needed:

  * BEHAVIOUR -- the guard itself is exercised directly, with a stand-in for the
    side effect webapp/config.py performs. This runs everywhere, needs no .env,
    and is what actually pins the semantics: an exported value survives, an
    unset one stays unset.

  * WIRING -- the imports are asserted to be *inside* the guard, and
    backend/.env asserted to still be loaded without override. A correct guard
    that nothing is wrapped in is the bug with extra code, and the two rejected
    fix shapes in T-44 are each ruled back out by one of these.

The end-to-end test at the bottom is deliberately kept despite being vacuous in
CI: on a machine with a webapp/.env -- the machine where the bug lives, and the
only one that can see it -- it is the test that fails if any of this is undone.
"""

import ast
import inspect
import os
import subprocess
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests.test_provision_covers_api_schema import _load_tool

_BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_TOOL = os.path.join(_BACKEND, "tools", "provision-database.py")

#: A URL shaped like the one that caused this, so a failure message names the
#: role rather than an opaque string. No credential: this value is never
#: connected to, only compared.
_INTRUDER = "postgresql://jobs_web@localhost:5432/jobs"
_PIPELINE = "postgresql://jobs_pipeline@localhost:5432/jobs"


class TestDatabaseUrlGuard(unittest.TestCase):
    """The behaviour half. `_database_url_unchanged()` in isolation."""

    @classmethod
    def setUpClass(cls):
        cls.tool = _load_tool()

    def setUp(self):
        self._saved = os.environ.get("DATABASE_URL")
        self.addCleanup(self._restore)

    def _restore(self):
        if self._saved is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = self._saved

    def test_an_exported_value_survives_the_import(self):
        """The case T-44's rejected override=True shape would have broken.

        A one-off run against a second database exports DATABASE_URL, and that
        must still win -- pointing this tool somewhere other than the configured
        database is how a new one gets provisioned.
        """
        os.environ["DATABASE_URL"] = _PIPELINE
        with self.tool._database_url_unchanged():
            os.environ["DATABASE_URL"] = _INTRUDER   # what importing config does
        self.assertEqual(os.environ["DATABASE_URL"], _PIPELINE)

    def test_an_unset_value_stays_unset(self):
        """Restoring an absent variable as "" would be worse than not restoring.

        lib/dbconn.database_url() raises a named error on an unset DATABASE_URL
        and would accept an empty string, turning a legible failure into a
        connection attempt against nothing.
        """
        os.environ.pop("DATABASE_URL", None)
        with self.tool._database_url_unchanged():
            os.environ["DATABASE_URL"] = _INTRUDER
        self.assertNotIn("DATABASE_URL", os.environ)

    def test_the_variable_is_restored_even_if_the_import_raises(self):
        """A failed import must not leave the wrong URL behind for a caller that
        catches it. This is why the restore is in a finally, not after the
        yield."""
        os.environ["DATABASE_URL"] = _PIPELINE
        with self.assertRaises(ImportError):
            with self.tool._database_url_unchanged():
                os.environ["DATABASE_URL"] = _INTRUDER
                raise ImportError("webapp/config.py blew up")
        self.assertEqual(os.environ["DATABASE_URL"], _PIPELINE)

    def test_nothing_else_in_the_environment_is_touched(self):
        """Scoped to DATABASE_URL, which is the whole argument for this shape
        over loading backend/.env first: webapp/.env's other keys still load
        normally, and no future key the two files share has its precedence
        silently decided here."""
        os.environ["UNRELATED_T44_KEY"] = "kept"
        self.addCleanup(os.environ.pop, "UNRELATED_T44_KEY", None)
        with self.tool._database_url_unchanged():
            os.environ["UNRELATED_T44_KEY"] = "changed"
        self.assertEqual(os.environ["UNRELATED_T44_KEY"], "changed")


class TestTheGuardIsWiredIn(unittest.TestCase):
    """The wiring half, read off the tool's AST rather than its behaviour.

    A guard nothing is wrapped in passes every test above. These are what fail
    if the import is moved back out, and they are read structurally rather than
    by regex so that reformatting the file cannot quietly stop them covering it.
    """

    @classmethod
    def setUpClass(cls):
        cls.tree = ast.parse(inspect.getsource(_load_tool()))

    def _guarded_import_names(self):
        """Every module name imported inside a `with _database_url_unchanged()`."""
        names = set()
        for node in ast.walk(self.tree):
            if not isinstance(node, ast.With):
                continue
            guarded = any(
                isinstance(item.context_expr, ast.Call)
                and isinstance(item.context_expr.func, ast.Name)
                and item.context_expr.func.id == "_database_url_unchanged"
                for item in node.items
            )
            if not guarded:
                continue
            for child in ast.walk(node):
                if isinstance(child, ast.Import):
                    names.update(alias.name for alias in child.names)
        return names

    def test_the_webapp_imports_are_inside_the_guard(self):
        """`config` is the one that loads webapp/.env; `schema_web` imports it,
        so it belongs inside too rather than relying on `config` being cached
        by then."""
        guarded = self._guarded_import_names()
        for module in ("config", "schema_web"):
            self.assertIn(module, guarded, (
                f"`import {module}` is not inside a `with "
                f"_database_url_unchanged()` block in provision-database.py -- "
                f"webapp/.env's DATABASE_URL reaches main() again and the tool "
                f"provisions as jobs_web (T-44)"))

    def test_backend_env_is_still_loaded_without_override(self):
        """The other rejected shape. override=True here would stop an exported
        DATABASE_URL winning, which is the precedence lib/envfile.py:90-94
        documents and every other caller relies on."""
        calls = [
            node for node in ast.walk(self.tree)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "load"
        ]
        self.assertEqual(len(calls), 1, "expected exactly one envfile.load call")
        overrides = [kw for kw in calls[0].keywords if kw.arg == "override"]
        self.assertEqual(overrides, [], (
            "provision-database.py passes `override` to envfile.load -- T-44 "
            "rejected that shape because it stops an exported DATABASE_URL "
            "from beating backend/.env"))


class TestImportingTheToolIsInert(unittest.TestCase):
    """End to end, in a child process with DATABASE_URL removed.

    VACUOUS IN CI AND THAT IS UNDERSTOOD: with no webapp/.env there is nothing
    to leak, so this passes for the wrong reason. It is kept rather than skipped
    because the machines that DO have a webapp/.env are the deployed one and
    every developer's, this fails on all of them if the guard is undone, and a
    skip is not available -- CI's suites job asserts nothing is skipped.
    """

    def test_importing_the_tool_does_not_set_database_url(self):
        env = {k: v for k, v in os.environ.items() if k != "DATABASE_URL"}
        probe = (
            "import importlib.util, os, sys; "
            f"spec = importlib.util.spec_from_file_location('_pd', {_TOOL!r}); "
            "m = importlib.util.module_from_spec(spec); "
            "spec.loader.exec_module(m); "
            "print(os.environ.get('DATABASE_URL', '<unset>'))"
        )
        # The S603 directive below names what it executes, following the same
        # convention .claude/rules/sql.md sets for spliced identifiers:
        # `sys.executable` and a module-level literal probe string, no runtime
        # input of any kind. (Do not open this comment with the directive word
        # itself -- ruff reads a comment starting that way as a blanket noqa.)
        result = subprocess.run(  # noqa: S603
            [sys.executable, "-c", probe],
            cwd=_BACKEND, env=env, capture_output=True, text=True, timeout=120,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), "<unset>", (
            "importing provision-database.py set DATABASE_URL as a side "
            "effect -- webapp/.env reached the process environment (T-44)"))


if __name__ == "__main__":
    unittest.main()

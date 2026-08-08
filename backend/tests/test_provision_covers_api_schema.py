"""T-39: a table in api/'s DDL must be reachable from provision-database.py.

WHAT WENT WRONG, so the shape of these tests reads as deliberate.
`tools/provision-database.py` is the one command that claims to stand a
database up from nothing, and until T-39 its STEPS list did not reach
`api/query_claims.ensure_schema()`. Three tables -- `contributors`, `api_keys`
and `submission_log` -- therefore did not exist on any database it created,
and since T-27 a webapp route depends on the first two, one HTTP hop away.

Nothing caught it, and the reason is the interesting part: the api suite's
database-backed tests build a `scratch_<hex>` schema by calling
`qc.ensure_schema()` themselves, so they prove the DDL *runs* and prove
nothing at all about whether the provisioning tool ever calls it. Every test
here is about the wiring between the two, which is exactly the seam neither
suite was watching.

TWO WAYS A NEW TABLE CAN BE COVERED, and this file requires both:

  * created -- `qc.ensure_schema` is in STEPS, so it runs;
  * reported -- the table is in `qc.REQUIRED_TABLES`, so `--verify-only`
    names it as missing on a database provisioned before it was added.

The second is not redundant. Step 6 only helps a database provisioned after
T-39; the deployed one was not, and `--verify-only` is the only thing that
will ever tell its operator so.

SCOPED TO TABLES, matching T-39's own 'Done when'. `qc.ensure_schema` also
adds columns (`claimed_by` and `claim_granted_at` on the watermark table),
and those are covered by step 6 but not by `REQUIRED_COLUMNS`, which holds
only `submission_log.action`. Whether that map should widen is api/'s call
about its own startup contract, not this tool's -- filed as T-45 rather than
decided here.

NOTE THE IMPORT BELOW MUTATES sys.path for the rest of the run: importing the
tool runs its module body, which puts `webapp/` and `api/` on it. Checked when
this was written -- no module name in either directory collides with anything
the pipeline suite imports. Recheck if that stops being true.
"""

import importlib.util
import inspect
import os
import re
import sys
import unittest

_BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_TOOL = os.path.join(_BACKEND, "tools", "provision-database.py")


def _load_tool():
    """Import provision-database.py, whose hyphen makes it un-importable.

    A path-based loader rather than a rename: the filename is what operators
    type and what CLAUDE.md documents, and it is not worth changing to please
    an import statement.
    """
    spec = importlib.util.spec_from_file_location("_provision_database", _TOOL)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


#: Both `CREATE TABLE foo` and `CREATE TABLE IF NOT EXISTS foo`. The DDL in
#: query_claims.py uses the second form throughout, but matching only that
#: would let a table added in the first form pass unnoticed -- and a test that
#: silently stops covering things is worse than no test.
_CREATE_TABLE = re.compile(
    r"CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?([A-Za-z_][A-Za-z0-9_]*)",
    re.IGNORECASE,
)


class TestProvisionReachesApiDDL(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.tool = _load_tool()
        sys.path.append(os.path.join(_BACKEND, "api"))
        import query_claims
        cls.qc = query_claims
        cls.created = sorted(set(
            _CREATE_TABLE.findall(inspect.getsource(query_claims.ensure_schema))
        ))

    def test_the_ddl_this_test_reads_is_not_empty(self):
        """Guard the regex, not the code.

        Every other test here passes vacuously if the scan finds nothing --
        rename the function, restructure the DDL into a helper, and the file
        goes green while covering zero tables. Three is what T-39 measured.
        """
        self.assertGreaterEqual(len(self.created), 3, self.created)
        for expected in ("contributors", "api_keys", "submission_log"):
            self.assertIn(expected, self.created)

    def test_steps_reaches_api_ensure_schema(self):
        """The created half: a new table in api/'s DDL is created by the tool."""
        functions = [fn for _name, fn in self.tool.STEPS]
        self.assertIn(self.qc.ensure_schema, functions)

    def test_api_ensure_schema_runs_last(self):
        """It commits internally and issues SET search_path on the shared
        connection, and it re-enters ensure_app_view's DROP fallback. All three
        reasons are in the tool's banner; this pins the ordering they require."""
        self.assertIs(self.tool.STEPS[-1][1], self.qc.ensure_schema)

    def test_every_table_api_creates_is_also_verified(self):
        """The reported half, and the one that fails if a future table is added
        to api/'s DDL and to neither. A table created but absent from
        REQUIRED_TABLES is invisible to --verify-only, so a database
        provisioned before it existed reports ready and is not."""
        missing = [t for t in self.created if t not in self.qc.REQUIRED_TABLES]
        self.assertEqual(missing, [], (
            f"query_claims.ensure_schema() creates {missing} but "
            f"REQUIRED_TABLES does not list {'it' if len(missing) == 1 else 'them'}, "
            f"so provision-database.py --verify-only cannot report "
            f"{'it' if len(missing) == 1 else 'them'} missing"))

    def test_the_tool_runs_the_api_verify(self):
        """--verify-only must actually call it. STEPS covering a table and the
        verify pass ignoring it is the pre-T-39 state with an extra step."""
        source = inspect.getsource(self.tool)
        self.assertIn("query_claims.verify_schema", source)

    def test_api_verify_schema_takes_a_connection(self):
        """It moved out of app.py in T-39 precisely so a caller with its own
        connection could use it. Restoring the no-argument form would break
        this tool without touching it."""
        parameters = inspect.signature(self.qc.verify_schema).parameters
        self.assertEqual(list(parameters), ["conn"])


if __name__ == "__main__":
    unittest.main()

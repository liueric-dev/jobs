"""The one grant here that is narrower than a table, and the check that sees it.

WHY THIS FILE EXISTS. `search_queries` is the only table this service WRITES and
does not own, and the write is scoped to three columns on purpose: a table-wide
`GRANT UPDATE` would hand `jobs_api` the five run statistics too, and a
contributor's submit could then forge a run history -- writing a future
`last_run_at` silences that query for every Builder (`query_claims.py`'s
REQUIRED_TABLES commentary, `docs/adr/0009`).

WHAT WENT WRONG, AND WHY A STATIC TEST WOULD NOT HAVE CAUGHT IT. That narrowness
was written down in three places -- the code comment, `README.md`, and
`DEV_TASKS.md`'s `OQ-29` -- and all three asserted the same false premise about
Postgres: that `has_table_privilege(..., 'UPDATE')` answers TRUE on a
column-level grant, so `verify_schema()` would accept the narrow form and simply
could not tell it apart from the wide one. It answers FALSE. The consequence was
not cosmetic: the only GRANT that satisfied the startup check was the table-wide
one the design refuses, so issuing exactly the two statements `OQ-29` specifies
left the service refusing to start, naming an UPDATE whose absence was the point.

Every check below is against a real server for that reason. The claim is about
what Postgres does, and no map, fake or assertion about this repo's own source
can falsify it -- which is exactly the shape of gap that let the premise stand.

NO verify_schema() CALL HERE, for the reason test_contributor_settings.py:973
gives about its own gap: verify_schema()'s loops are hardcoded to `public`
(`query_claims.py`), so under a scratch schema it answers about `public` no
matter which connection it is handed, and a test that passed would be passing for
the wrong reason. What is checked instead is the two halves it joins -- that
REQUIRED_COLUMN_PRIVILEGES names the right columns, and that the privilege
function it uses reports what this file says it reports.
"""

import os
import sys
import unittest

API_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BACKEND_DIR = os.path.dirname(API_DIR)
sys.path.insert(0, API_DIR)
sys.path.insert(0, BACKEND_DIR)

import query_claims as qc                             # noqa: E402
from evals import scratchdb                           # noqa: E402
from lib import envfile                               # noqa: E402

_BACKEND_ENV = os.path.join(BACKEND_DIR, ".env")


def _pipeline_url():
    try:
        with open(_BACKEND_ENV) as fh:
            return envfile.parse(fh.read()).get("DATABASE_URL")
    except OSError:
        return None


if "JOBS_SCRATCH_DATABASE_URL" not in os.environ:
    _url = _pipeline_url()
    if _url:
        os.environ["JOBS_SCRATCH_DATABASE_URL"] = _url

requires_db = unittest.skipUnless(
    scratchdb.available(),
    "no scratch database: set JOBS_SCRATCH_DATABASE_URL to a role with CREATE")

#: The columns the claim SQL writes on `search_queries`. Named once, here, and
#: asserted against REQUIRED_COLUMNS below rather than repeated -- the two maps
#: describe the same three columns from opposite directions (does it exist / may
#: this role write it) and drifting apart is the failure this pins.
CLAIM_COLUMNS = ("claimed_at", "claimed_by", "claim_granted_at")


class TestTheMapsAgree(unittest.TestCase):

    def test_the_update_is_column_scoped_and_not_table_wide(self):
        # The security property, stated as an assertion rather than a comment.
        # A future edit that "fixes" the startup check by widening the grant
        # fails here first.
        self.assertNotIn("UPDATE", qc.REQUIRED_TABLES["search_queries"],
                         "a table-wide UPDATE on search_queries would let a "
                         "contributor's submit forge a run history")
        self.assertIn("SELECT", qc.REQUIRED_TABLES["search_queries"])

    def test_the_column_privileges_name_the_claim_columns(self):
        self.assertEqual(
            qc.REQUIRED_COLUMN_PRIVILEGES["search_queries"]["UPDATE"],
            CLAIM_COLUMNS)

    def test_the_two_maps_describe_the_same_columns(self):
        # REQUIRED_COLUMNS says these three must EXIST; this map says this role
        # must be able to WRITE them. A column added to one and not the other is
        # either a startup check that cannot see a missing grant or one that
        # demands a grant for a column nothing writes.
        self.assertEqual(
            set(qc.REQUIRED_COLUMN_PRIVILEGES["search_queries"]["UPDATE"]),
            set(qc.REQUIRED_COLUMNS["search_queries"]))

    def test_no_table_is_in_both_maps_for_the_same_privilege(self):
        # Belt and braces: a privilege declared table-wide AND column-wise would
        # make the narrow map decorative, since the table check alone would
        # already demand the wide grant.
        for table, by_privilege in qc.REQUIRED_COLUMN_PRIVILEGES.items():
            for privilege in by_privilege:
                self.assertNotIn(
                    privilege, qc.REQUIRED_TABLES.get(table, ()),
                    f"{table}: {privilege} is declared both table-wide and "
                    f"column-wise, so the narrow declaration cannot bind")


@requires_db
class TestPostgresPrivilegeFunctions(unittest.TestCase):
    """What the two functions actually answer, measured rather than assumed.

    Run as the owner of a scratch table with its own privileges REVOKED from
    itself first -- otherwise every answer is TRUE by ownership and the test
    reports nothing. `jobs_pipeline` is not a superuser (evals/scratchdb.py says
    so, and superuser would answer TRUE regardless), which is what makes the
    revoke bite.
    """

    def _table(self, conn, name):
        conn.execute(f"CREATE TABLE {name}.t (a INT, b INT)")
        conn.execute(f"REVOKE ALL ON {name}.t FROM CURRENT_USER")
        conn.commit()
        return f"{name}.t"

    def test_has_table_privilege_cannot_see_a_column_grant(self):
        # THE BUG, pinned. This is the answer that made the documented GRANT
        # unusable and the undocumented one mandatory.
        with scratchdb.scratch_schema() as (conn, name):
            t = self._table(conn, name)
            conn.execute(f"GRANT SELECT ON {t} TO CURRENT_USER")
            conn.execute(f"GRANT UPDATE (a) ON {t} TO CURRENT_USER")
            conn.commit()
            self.assertFalse(
                conn.execute(
                    "SELECT has_table_privilege(current_user, %s, 'UPDATE')",
                    (t,)).fetchone()[0],
                "has_table_privilege() saw a column grant; if Postgres changed "
                "this, REQUIRED_COLUMN_PRIVILEGES' whole reason is gone")
            self.assertTrue(
                conn.execute(
                    "SELECT has_table_privilege(current_user, %s, 'SELECT')",
                    (t,)).fetchone()[0])

    def test_has_column_privilege_sees_it_and_stops_at_the_granted_column(self):
        # The function verify_schema() now uses, and the reason it is the right
        # one: it says yes to the claim column and no to the run statistic.
        with scratchdb.scratch_schema() as (conn, name):
            t = self._table(conn, name)
            conn.execute(f"GRANT UPDATE (a) ON {t} TO CURRENT_USER")
            conn.commit()
            for column, expected in (("a", True), ("b", False)):
                self.assertIs(
                    conn.execute(
                        "SELECT has_column_privilege(current_user, %s, %s, "
                        "'UPDATE')", (t, column)).fetchone()[0],
                    expected)

    def test_the_wide_grant_is_distinguishable_from_the_narrow_one(self):
        # T-58's premise, measured here so that row rests on a green test rather
        # than on this file's prose. Under a table-wide UPDATE the ungranted
        # column answers TRUE, which is exactly what a check for "too wide"
        # would key on -- and is the second thing the old comment said was
        # impossible.
        with scratchdb.scratch_schema() as (conn, name):
            t = self._table(conn, name)
            conn.execute(f"GRANT UPDATE ON {t} TO CURRENT_USER")
            conn.commit()
            self.assertTrue(conn.execute(
                "SELECT has_column_privilege(current_user, %s, 'b', 'UPDATE')",
                (t,)).fetchone()[0])
            self.assertTrue(conn.execute(
                "SELECT has_table_privilege(current_user, %s, 'UPDATE')",
                (t,)).fetchone()[0])


if __name__ == "__main__":
    unittest.main()

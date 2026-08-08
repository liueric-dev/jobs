"""T-27: the server-to-server mint route, and the one implementation behind it.

WHY THIS ROUTE EXISTS HERE rather than in ../../webapp/: `api_keys` is this
service's table and `jobs_api` is the only role granted INSERT on it, and
docs/adr/0006's consequences reject the alternative -- granting `jobs_web`
INSERT here -- outright. So the webapp authenticates the Builder, this service
issues the credential, and the two talk over one route in one direction on a
shared secret. 0006's consequences named that secret as unscoped; this is it.

THE PROPERTY UNDER TEST IS THE ONE THE WHOLE DESIGN RESTS ON: the raw key
exists in exactly one HTTP response and is never obtainable again. That is
asserted below by TRYING TO GET IT BACK -- from the stored row, from a second
mint, from the list command -- rather than by reading mint_credential() and
agreeing with it.
"""

import hashlib
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fakedb import FakeConn, patch_db                # noqa: E402

import app                                           # noqa: E402
import query_claims as qc                            # noqa: E402
from fastapi import HTTPException                    # noqa: E402

SECRET = "test-mint-secret-not-a-real-one"


class MintConn(FakeConn):
    """A connection that records the INSERTs and UPDATEs the mint issues.

    Dispatch on SQL text, matching this package's other fakes and for the
    reason fakedb.py gives: matching on call order would keep passing if a
    statement were dropped, and "a statement was dropped" is what the revoke
    half of a re-key would look like when it broke.
    """

    def __init__(self, known_contributors=()):
        super().__init__()
        self.known = set(known_contributors)
        self.contributors = []
        self.keys = []
        self.revocations = []
        self.committed = False

    def execute(self, sql, params=()):
        flat = " ".join(sql.split())
        if flat.startswith("SELECT 1 FROM contributors WHERE id"):
            return _Rows([(1,)] if params[0] in self.known else [])
        if flat.startswith("INSERT INTO contributors"):
            self.contributors.append(params)
            self.known.add(params[0])
            return _Rows([])
        if flat.startswith("UPDATE api_keys SET revoked_at"):
            self.revocations.append(params)
            return _Rows([])
        if flat.startswith("INSERT INTO api_keys"):
            self.keys.append(params)
            return _Rows([])
        raise AssertionError(f"unexpected SQL: {flat}")

    def commit(self):
        self.committed = True


class _Rows:

    def __init__(self, rows):
        self._rows = rows

    def fetchone(self):
        return self._rows[0] if self._rows else None

    def fetchall(self):
        return list(self._rows)


def run_mint(conn, body, authorization=f"Bearer {SECRET}", secret=SECRET):
    """Call the route with the shared secret configured to `secret`.

    qc.MINT_SHARED_SECRET is read at module import from the environment, so it
    is set here directly and restored afterwards -- the same thing patch_db
    does for the connection, and for the same reason: the test must not depend
    on the environment the suite happens to run in.
    """
    restore_db = patch_db(app, conn)
    previous = qc.MINT_SHARED_SECRET
    qc.MINT_SHARED_SECRET = secret
    try:
        return app.mint(app.MintRequest(**body), authorization=authorization)
    finally:
        qc.MINT_SHARED_SECRET = previous
        restore_db()


class TestTheRawKeyIsUnrecoverable(unittest.TestCase):

    def test_the_response_carries_it_and_the_stored_row_does_not(self):
        conn = MintConn()
        result = run_mint(conn, {"name": "Dana", "label": "dana-laptop"})
        raw = result["api_key"]
        self.assertTrue(raw)

        # THE READ-BACK ATTEMPT. Everything this service wrote, flattened, and
        # the raw key must appear in none of it.
        written = repr(conn.contributors) + repr(conn.keys) + repr(conn.revocations)
        self.assertNotIn(raw, written,
                         "the raw key reached the database; only sha256 may")
        self.assertIn(hashlib.sha256(raw.encode()).hexdigest(), written)

    def test_the_stored_value_is_exactly_the_sha256_of_the_response(self):
        conn = MintConn()
        result = run_mint(conn, {"name": "Dana"})
        key_hash = conn.keys[0][0]
        self.assertEqual(key_hash,
                         hashlib.sha256(result["api_key"].encode()).hexdigest())
        self.assertEqual(len(key_hash), 64)
        # The response reports the hash too, so the caller can log WHICH key it
        # minted without logging the key. That is the only other thing about
        # the credential this service will ever say.
        self.assertEqual(result["key_hash"], key_hash)

    def test_a_second_mint_cannot_return_the_first_key(self):
        # The read-back attempt that a caller could actually make: ask again.
        conn = MintConn()
        first = run_mint(conn, {"name": "Dana"})["api_key"]
        second = run_mint(conn, {"name": "Dana",
                                 "contributor_id": conn.contributors[0][0]})["api_key"]
        self.assertNotEqual(first, second)

    def test_there_is_no_route_that_returns_a_key_it_did_not_just_mint(self):
        # The structural half: enumerate the service's routes and assert that
        # exactly one of them can produce key material at all. A future
        # "resend my key" endpoint is the thing this forbids.
        minting = [r for r in app.app.routes
                   if getattr(r, "path", "") == "/v1/internal/contributors"]
        self.assertEqual(len(minting), 1)
        others = [getattr(r, "path", "") for r in app.app.routes
                  if "contributor" in getattr(r, "path", "")
                  and getattr(r, "path", "") != "/v1/internal/contributors"]
        self.assertEqual(others, [])


class TestRekeying(unittest.TestCase):

    def test_a_first_mint_creates_a_contributor_and_revokes_nothing(self):
        conn = MintConn()
        result = run_mint(conn, {"name": "Dana"})
        self.assertEqual(len(conn.contributors), 1)
        self.assertEqual(conn.revocations, [])
        self.assertTrue(result["contributor_id"].startswith("c_"))

    def test_a_re_key_revokes_the_live_keys_and_creates_no_contributor(self):
        conn = MintConn(known_contributors={"c_abc123"})
        result = run_mint(conn, {"name": "Dana", "contributor_id": "c_abc123"})
        self.assertEqual(conn.contributors, [])
        self.assertEqual(len(conn.revocations), 1)
        self.assertEqual(conn.revocations[0][1], "c_abc123")
        self.assertEqual(result["contributor_id"], "c_abc123")
        self.assertEqual(len(conn.keys), 1)

    def test_the_revocation_and_the_new_key_share_one_timestamp(self):
        # ONE CLOCK. The revocation stamp and the new key's created_at come
        # from the same utc_now_str() call, so the two can never straddle a
        # second boundary and produce a window in which the contributor holds
        # zero valid keys according to a naive reading of the table. This is
        # the file-level rule in TASKS.md: derive every timestamp from one
        # clock, or freeze all of them -- never one of each.
        conn = MintConn(known_contributors={"c_abc123"})
        result = run_mint(conn, {"name": "Dana", "contributor_id": "c_abc123"})
        revoked_at = conn.revocations[0][0]
        created_at = conn.keys[0][3]
        self.assertEqual(revoked_at, created_at)
        self.assertEqual(result["created_at"], created_at)

    def test_an_unknown_contributor_id_is_refused_not_created(self):
        # A re-key that silently became a first mint would leave the caller's
        # stored id pointing at nothing, and the caller would never find out.
        conn = MintConn()
        with self.assertRaises(HTTPException) as caught:
            run_mint(conn, {"name": "Dana", "contributor_id": "c_nope"})
        self.assertEqual(caught.exception.status_code, 409)
        self.assertEqual(conn.contributors, [])
        self.assertEqual(conn.keys, [])


class TestServiceAuthentication(unittest.TestCase):

    def test_an_unset_secret_disables_the_route(self):
        # NOT "allows anything". An env var nobody set must not leave a
        # credential-issuing endpoint open.
        conn = MintConn()
        with self.assertRaises(HTTPException) as caught:
            run_mint(conn, {"name": "Dana"}, secret="")
        self.assertEqual(caught.exception.status_code, 503)
        self.assertEqual(conn.keys, [])

    def test_a_wrong_secret_is_401_and_writes_nothing(self):
        conn = MintConn()
        with self.assertRaises(HTTPException) as caught:
            run_mint(conn, {"name": "Dana"}, authorization="Bearer wrong")
        self.assertEqual(caught.exception.status_code, 401)
        self.assertEqual(conn.keys, [])

    def test_a_missing_header_is_401(self):
        conn = MintConn()
        with self.assertRaises(HTTPException) as caught:
            run_mint(conn, {"name": "Dana"}, authorization=None)
        self.assertEqual(caught.exception.status_code, 401)

    def test_a_contributor_key_is_not_a_service_credential(self):
        # The separation that matters: if the two mechanisms were one, any
        # leaked contributor key would mint more keys. A valid-looking
        # contributor bearer token is simply a wrong secret here.
        conn = MintConn()
        with self.assertRaises(HTTPException) as caught:
            run_mint(conn, {"name": "Dana"},
                     authorization="Bearer " + "x" * 43)
        self.assertEqual(caught.exception.status_code, 401)


class TestThereIsOneMintImplementation(unittest.TestCase):
    """`.claude/CLAUDE.md`: one implementation, many callers.

    Before T-27 the mint lived in manage_users.cmd_create. It now lives in
    qc.mint_credential and that command is a caller, because a second copy of
    "the raw key is token_urlsafe(32) and only its sha256 is stored" is a
    second place for that property to be got wrong.
    """

    def _source(self, name):
        path = os.path.join(os.path.dirname(os.path.dirname(
            os.path.abspath(__file__))), name)
        with open(path, encoding="utf-8") as fh:
            return fh.read()

    def test_only_query_claims_inserts_into_api_keys(self):
        for module in ("app.py", "manage_users.py", "contribution_report.py"):
            self.assertNotIn("INSERT INTO api_keys", self._source(module),
                             f"{module} is a second mint")
        self.assertEqual(self._source("query_claims.py").count(
            "INSERT INTO api_keys"), 1)

    def test_only_query_claims_generates_key_material(self):
        # AST, not grep. cmd_create's docstring says the words "token_urlsafe"
        # and "sha256" -- correctly, since it is explaining where its mint
        # went -- and a text scan cannot tell that sentence from a call. This
        # looks for the CALL.
        import ast

        def generators(name):
            tree = ast.parse(self._source(name), filename=name)
            found = set()
            for node in ast.walk(tree):
                if (isinstance(node, ast.Call)
                        and isinstance(node.func, ast.Attribute)
                        and node.func.attr in ("token_urlsafe", "token_hex")):
                    found.add(node.func.attr)
            return found

        for module in ("app.py", "manage_users.py", "contribution_report.py"):
            self.assertEqual(generators(module), set(),
                             f"{module} generates its own key material")
        self.assertEqual(generators("query_claims.py"),
                         {"token_urlsafe", "token_hex"})

    def test_manage_users_still_mints_through_the_shared_function(self):
        # The manual fallback per docs/adr/0006 stays -- this is the assertion
        # that it stays as a CALLER and does not drift back into a copy.
        self.assertIn("qc.mint_credential(", self._source("manage_users.py"))


if __name__ == "__main__":
    unittest.main()

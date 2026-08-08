"""T-27: opting in, and the `config.json` that is the contract with T-28.

TWO PROPERTIES, AND THEY ARE THE ROW'S OWN ACCEPTANCE CRITERIA.

  1. The raw key appears in exactly one response and is never readable again.
     Asserted below by TRYING TO READ IT BACK -- from what this service stored,
     from a second opt-in, from every other route that takes a session -- not
     by reading contribute.py and agreeing with it.

  2. The payload is the exact file T-28's worker will load unmodified. T-28 is
     unbuilt, so TestTheWorkerContract reads the WORKER'S OWN SOURCE and
     compares. That is what makes it a contract rather than a fixture: renaming
     a field on either side turns this red, and a fixture copied from
     CONFIG_FIELDS would agree with a rename forever.

ONE CLOCK. Every timestamp asserted here comes from the fake connection's
record of what was written, compared against a bound captured from the same
run -- never against a literal. Two tests in this repo rotted by mixing a real
`now` with a hardcoded one (TASKS.md, "Two rotting tests"), and the opt-in
timestamp is exactly the kind of field that invites it.
"""

import json
import os
import re
import sys
import unittest
from datetime import datetime, timezone

WEBAPP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, WEBAPP_DIR)

import config  # noqa: E402  (must come first -- performs the sys.path insert)

import contribute  # noqa: E402
from auth import User  # noqa: E402
from fastapi import HTTPException  # noqa: E402

#: The worker T-28 will teach to read the file this row writes.
WORKER = os.path.join(os.path.dirname(WEBAPP_DIR), "api", "contributor-worker",
                      "google-serpapi-worker.py")

USER = User(id="u_1", email="dana@example.com", display_name="Dana",
            profile="pursuit", is_admin=False)


def _all_paths(application):
    """Every route path, walking included routers.

    app.routes holds a `_IncludedRouter` wrapper per include_router() call in
    this FastAPI rather than the routes themselves, so this recurses through
    `original_router` instead of reading `.path` off the wrapper -- which is
    None, and would make any scan of the route table silently empty.
    """
    found = []

    def walk(routes):
        for route in routes:
            inner = getattr(route, "original_router", None)
            if inner is not None:
                walk(inner.routes)
            elif getattr(route, "path", None):
                found.append(route.path)

    walk(application.routes)
    return found


class FakeResult:

    def __init__(self, rows=()):
        self._rows = list(rows)

    def fetchone(self):
        return self._rows[0] if self._rows else None

    def fetchall(self):
        return list(self._rows)


class FakeConn:
    """Enough of a psycopg connection for one opt-in.

    Dispatch on SQL text, matching this package's other fakes and ../api/'s,
    for the reason fakedb.py states there: matching on call order would keep
    passing if a statement were dropped.
    """

    def __init__(self, contributor_id=None):
        self.contributor_id = contributor_id
        self.updates = []
        self.committed = False

    def execute(self, sql, params=()):
        flat = " ".join(sql.split())
        if flat.startswith("SELECT contributor_id FROM app_users"):
            return FakeResult([(self.contributor_id,)])
        if flat.startswith("UPDATE app_users SET contributor_id"):
            self.updates.append(params)
            return FakeResult()
        raise AssertionError(f"unexpected SQL: {flat}")

    def commit(self):
        self.committed = True


class FakeMint:
    """Stands in for ../api/. Records what was asked, returns what it minted."""

    def __init__(self, contributor_id="c_minted", key="raw-key-aaa", fail=None):
        self.contributor_id = contributor_id
        self.key = key
        self.fail = fail
        self.calls = []

    def __call__(self, name, contributor_id=None):
        self.calls.append({"name": name, "contributor_id": contributor_id})
        if self.fail:
            raise self.fail
        return self.contributor_id, self.key


def run_opt_in(conn, mint, **settings):
    """Call the route with the database and the mint both replaced.

    Configuration is set on the module rather than in the environment, because
    config.py reads os.environ at import and a test that mutated the
    environment would depend on import order.
    """
    import contextlib

    defaults = {
        "JOBS_MINT_SHARED_SECRET": "test-secret",
        "CONTRIBUTOR_API_PUBLIC_URL": "https://jobs.example.com",
        "CONTRIBUTOR_API_INTERNAL_URL": "http://127.0.0.1:8420",
    }
    defaults.update(settings)
    previous = {k: getattr(config, k) for k in defaults}
    original_db = contribute.db
    original_mint = contribute.mint_credential

    @contextlib.contextmanager
    def fake_db():
        yield conn

    for key, value in defaults.items():
        setattr(config, key, value)
    contribute.db = fake_db
    contribute.mint_credential = mint
    try:
        return contribute.opt_in(user=USER)
    finally:
        for key, value in previous.items():
            setattr(config, key, value)
        contribute.db = original_db
        contribute.mint_credential = original_mint


class TestTheWorkerContract(unittest.TestCase):
    """The contract between this row and T-28, read from the worker's source.

    The worker today takes all four settings from the environment and exits 1
    naming three of them. T-28 makes it fall back to `config.json` beside
    itself. Until that lands, THIS is what stops the two halves being built
    against different field names.
    """

    def _worker_source(self):
        # Not a skipUnless. A missing worker means the contract has no other
        # side, and reporting that as "passed" is the failure mode this whole
        # test exists to avoid.
        self.assertTrue(os.path.exists(WORKER),
                        f"{WORKER} is gone; T-28's side of this contract has "
                        f"moved and CONFIG_FIELDS is now unanchored")
        with open(WORKER, encoding="utf-8") as fh:
            return fh.read()

    def test_every_field_is_a_setting_the_worker_actually_reads(self):
        source = self._worker_source()
        read = set(re.findall(r'os\.environ\.get\(\s*"([A-Z_]+)"', source))
        for field in contribute.CONFIG_FIELDS:
            self.assertIn(
                field, read,
                f"config.json carries {field}, which the worker does not read. "
                f"Either T-28 renamed it or this payload invented it; the two "
                f"rows have to agree on the name or the install fails on a "
                f"Builder's machine.")

    def test_every_setting_the_worker_requires_is_in_the_payload(self):
        # The other direction, and the one that catches a DROPPED field. The
        # worker's own unset-check names its required settings in one message;
        # anything named there and missing here is an install that exits 1.
        source = self._worker_source()
        required = set(re.findall(r"\b(JOBS_API_BASE_URL|JOBS_API_KEY|SERPAPI_API_KEY)\b",
                                  source.split("def main")[-1]))
        self.assertTrue(required, "the worker's main() no longer names its "
                                  "required settings; this check is unanchored")
        for setting in required:
            self.assertIn(
                setting, contribute.CONFIG_FIELDS,
                f"the worker requires {setting} and config.json does not "
                f"supply it")

    def test_the_payload_keys_are_exactly_the_declared_fields(self):
        self.assertEqual(tuple(contribute.build_config("k")),
                         contribute.CONFIG_FIELDS)

    def test_the_payload_is_flat_and_every_value_is_a_string(self):
        # The worker reads os.environ, where everything is a string. A loader
        # that has to coerce types is a second place for the two rows to
        # disagree.
        for key, value in contribute.build_config("k").items():
            self.assertIsInstance(key, str)
            self.assertIsInstance(value, str)

    def test_it_serialises_to_json_unchanged(self):
        payload = contribute.build_config("k")
        self.assertEqual(json.loads(json.dumps(payload)), payload)

    def test_the_serpapi_key_is_empty_not_a_placeholder(self):
        # docs/adr/0006 decision 3, retained by 0007: the contributor's SerpApi
        # key never reaches this server. The field is present so the Builder
        # knows where to type it, and EMPTY so the worker's own `if not
        # SERPAPI_API_KEY` check still fires -- a plausible-looking placeholder
        # would sail past it into a SerpApi 401.
        self.assertEqual(contribute.build_config("k")["SERPAPI_API_KEY"], "")

    def test_the_base_url_is_the_public_one(self):
        # The failure this prevents is a config.json that works on the server
        # and fails on every Builder's laptop.
        previous = config.CONTRIBUTOR_API_PUBLIC_URL
        config.CONTRIBUTOR_API_PUBLIC_URL = "https://jobs.example.com"
        try:
            self.assertEqual(contribute.build_config("k")["JOBS_API_BASE_URL"],
                             "https://jobs.example.com")
        finally:
            config.CONTRIBUTOR_API_PUBLIC_URL = previous


class TestTheRawKeyIsUnrecoverable(unittest.TestCase):

    def test_the_response_carries_it_and_this_service_stores_nothing(self):
        conn = FakeConn()
        mint = FakeMint(key="the-one-and-only-key")
        result = run_opt_in(conn, mint)

        self.assertEqual(result["config"]["JOBS_API_KEY"], "the-one-and-only-key")
        # THE READ-BACK ATTEMPT: everything this service wrote.
        self.assertNotIn("the-one-and-only-key", repr(conn.updates))
        # And not the hash either -- see schema_web._ensure_contributor_link.
        # A hash here would be a second copy of a credential artefact in a
        # second database, for no caller.
        import hashlib
        self.assertNotIn(hashlib.sha256(b"the-one-and-only-key").hexdigest(),
                         repr(conn.updates))

    def test_a_second_opt_in_returns_a_different_key(self):
        # The read-back a Builder could actually attempt: ask again. They get a
        # new credential, not the old one, and the old one is revoked by the
        # mint -- see ../../api/tests/test_mint.py.
        first = run_opt_in(FakeConn(), FakeMint(key="key-one"))
        second = run_opt_in(FakeConn(contributor_id="c_minted"),
                            FakeMint(key="key-two"))
        self.assertNotEqual(first["config"]["JOBS_API_KEY"],
                            second["config"]["JOBS_API_KEY"])

    def test_no_other_route_in_this_service_can_return_it(self):
        # The structural half. contribute.py is the only module here that ever
        # holds key material, and it holds it for the length of one response.
        #
        # THE ROUTE TABLE IS NOT FLAT. This FastAPI keeps an included router as
        # a `_IncludedRouter` wrapper in app.routes rather than copying its
        # routes up, so a naive scan of app.routes sees /v1/health, /openapi
        # and nothing else -- it would have reported "no route returns a key"
        # about a service with twenty routes. Walk `original_router`.
        import app
        paths = _all_paths(app.app)
        self.assertIn("/v1/jobs", paths,
                      "the route walk found no known route, so its verdict "
                      "about the mint route means nothing")
        self.assertEqual(paths.count("/v1/contribute/opt-in"), 1)
        for name in os.listdir(WEBAPP_DIR):
            if not name.endswith(".py") or name == "contribute.py":
                continue
            with open(os.path.join(WEBAPP_DIR, name), encoding="utf-8") as fh:
                self.assertNotIn(
                    "JOBS_API_KEY", fh.read(),
                    f"{name} names the contributor key; only contribute.py may, "
                    f"and only for the length of one response")

    def test_the_key_is_never_logged(self):
        # A log line is a read-back path with a longer retention than the
        # database. contribute.py logs nothing at all, which is the cheapest
        # way to be sure.
        with open(os.path.join(WEBAPP_DIR, "contribute.py"), encoding="utf-8") as fh:
            source = fh.read()
        self.assertNotIn("logging", source)
        self.assertNotIn("print(", source)


class TestTheStoredLink(unittest.TestCase):

    def test_a_first_opt_in_passes_no_contributor_id(self):
        conn = FakeConn(contributor_id=None)
        mint = FakeMint()
        run_opt_in(conn, mint)
        self.assertEqual(mint.calls[0]["contributor_id"], None)

    def test_a_second_opt_in_re_keys_rather_than_creating(self):
        conn = FakeConn(contributor_id="c_existing")
        mint = FakeMint(contributor_id="c_existing")
        run_opt_in(conn, mint)
        self.assertEqual(mint.calls[0]["contributor_id"], "c_existing")

    def test_the_minted_id_and_a_timestamp_are_stored(self):
        conn = FakeConn()
        run_opt_in(conn, FakeMint(contributor_id="c_minted"))
        self.assertEqual(len(conn.updates), 1)
        stored_id, stored_at, user_id = conn.updates[0]
        self.assertEqual(stored_id, "c_minted")
        self.assertEqual(user_id, USER.id)
        self.assertTrue(conn.committed)

    def test_the_timestamp_is_bracketed_by_one_clock(self):
        # ONE CLOCK, and the rule TASKS.md states after two tests rotted on
        # exactly this: the bounds and the value under test all come from the
        # same source, so there is no window in which this passes and no
        # window in which it stops.
        stamp = "%Y-%m-%dT%H:%M:%S"
        before = datetime.now(timezone.utc).strftime(stamp)
        conn = FakeConn()
        run_opt_in(conn, FakeMint())
        after = datetime.now(timezone.utc).strftime(stamp)
        written = conn.updates[0][1]
        self.assertLessEqual(before, written)
        self.assertLessEqual(written, after)

    def test_nothing_is_stored_when_the_mint_fails(self):
        # The ordering that matters: ../api/ is asked first, and a failure
        # there leaves this service exactly as it was.
        conn = FakeConn()
        mint = FakeMint(fail=HTTPException(status_code=502, detail="down"))
        with self.assertRaises(HTTPException) as caught:
            run_opt_in(conn, mint)
        self.assertEqual(caught.exception.status_code, 502)
        self.assertEqual(conn.updates, [])
        self.assertFalse(conn.committed)

    def test_the_name_sent_is_the_display_name_not_the_key(self):
        # ../api/ has no user directory and must not grow one; what it gets is
        # an operator-facing label. Checked because the argument is positional.
        conn = FakeConn()
        mint = FakeMint()
        run_opt_in(conn, mint)
        self.assertEqual(mint.calls[0]["name"], "Dana")


class TestConfiguration(unittest.TestCase):

    def test_an_unconfigured_server_says_so_and_calls_nothing(self):
        for missing in ("JOBS_MINT_SHARED_SECRET", "CONTRIBUTOR_API_PUBLIC_URL",
                        "CONTRIBUTOR_API_INTERNAL_URL"):
            with self.subTest(missing=missing):
                conn = FakeConn()
                mint = FakeMint()
                with self.assertRaises(HTTPException) as caught:
                    run_opt_in(conn, mint, **{missing: ""})
                self.assertEqual(caught.exception.status_code, 503)
                self.assertEqual(mint.calls, [])
                self.assertEqual(conn.updates, [])

    def test_the_public_url_has_no_default(self):
        # A default of 127.0.0.1 is the wrong value that would look most
        # plausible in a log, and it would ship a config.json that fails on
        # every Builder's machine.
        self.assertEqual(
            os.environ.get("CONTRIBUTOR_API_PUBLIC_URL", ""),
            config.CONTRIBUTOR_API_PUBLIC_URL)

    def test_the_secret_env_var_is_the_one_the_api_reads(self):
        # One secret, one name, two .env files. Read from ../api/'s source so
        # a rename there turns this red rather than turning minting off.
        api_source = os.path.join(os.path.dirname(WEBAPP_DIR), "api",
                                  "query_claims.py")
        with open(api_source, encoding="utf-8") as fh:
            self.assertIn('os.environ.get("JOBS_MINT_SHARED_SECRET"', fh.read())
        with open(os.path.join(WEBAPP_DIR, "config.py"), encoding="utf-8") as fh:
            self.assertIn('os.environ.get("JOBS_MINT_SHARED_SECRET"', fh.read())


class TestNoNewRuntimeDependency(unittest.TestCase):
    """TASKS.md's standing bound: no new runtime dependency in any of the three
    requirements.txt.

    THE FILE STAYS FIVE LINES. Its own header says so, and says httpx is the
    one addition over api/'s, there for exactly one call -- auth.py's POST to
    Google's token endpoint. This row makes it two calls, not six packages.
    """

    def _requirements(self):
        with open(os.path.join(WEBAPP_DIR, "requirements.txt"), encoding="utf-8") as fh:
            return [line.strip() for line in fh
                    if line.strip() and not line.startswith("#")]

    def test_the_dependency_list_is_unchanged(self):
        self.assertEqual(self._requirements(), [
            "fastapi==0.140.0",
            "uvicorn[standard]==0.51.0",
            "psycopg[binary]==3.3.4",
            "pydantic==2.13.4",
            "httpx==0.28.1",
        ])

    def test_the_call_out_reuses_the_client_auth_py_already_uses(self):
        # A second HTTP idiom in one service is two failure vocabularies to
        # keep in agreement for no gain.
        with open(os.path.join(WEBAPP_DIR, "contribute.py"), encoding="utf-8") as fh:
            source = fh.read()
        self.assertIn("import httpx", source)
        for stdlib_http in ("urllib.request", "http.client"):
            self.assertNotIn(stdlib_http, source)


if __name__ == "__main__":
    unittest.main()

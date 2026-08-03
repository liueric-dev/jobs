"""Per-unit isolation, and guarded config reads, in the ingest scripts.

WHAT THIS COVERS AND WHY IT IS A NEW MODULE

Defects D18, D19 and D21 (in the defect register, deleted 2026-08-02:
`git show refactor-freeze-2026-08-02:docs/ingest/DEFECTS.md`) are all the same
sentence said three ways: work that can fail is done OUTSIDE the block that
would have contained
the failure, so one bad unit ends the run instead of ending itself.

  D18  config keys subscripted after the guarded load returned
  D19  normalize/parse called outside the per-unit try
  D21  the role vocabulary loaded at import, before main() exists to report

None of them lives in a function. They live in `main()` -- in the shape of a
loop, not in the behaviour of anything a unit test could previously reach.
`tests/test_ingest_cassettes.py`'s header says why that gap existed: the
cassette harness exercises "the script's OWN fetch and normalize functions"
over recorded bytes, which is the right instrument for a parser and the wrong
one for a loop that is supposed to survive its parser. So these tests drive
`main()`, with the network faked at the module boundary and a scratch schema
underneath, and assert the property the register actually claims: the OTHER
units still land.

INJECTION AT THE SEAM, DELIBERATELY. Each test replaces the exact function the
register names as sitting outside the guard -- `parse_page`, `normalize_job`, a
`NORMALIZERS` entry -- with one that raises for one unit and works for the
rest. That is not a fake standing in for the defect: it IS the defect's input,
and before the fix every one of these tests loses every unit, not just the bad
one.

OFFLINE. Nothing here reaches the network; the fetchers are replaced outright.
The DB-backed cases need a scratch schema and skip without one.
"""

import io
import json
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import relevance                                              # noqa: E402
import schema                                                 # noqa: E402
from evals import scratchdb                                   # noqa: E402
from evals.ingest_modules import load as load_ingest          # noqa: E402
from lib import envfile                                       # noqa: E402

#: Same reason tests/test_ingest_cassettes.py:47-50 does it: the DB-backed
#: cases must not depend on the caller having exported DATABASE_URL by hand.
envfile.load(os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), ".env"))

requires_db = unittest.skipUnless(
    scratchdb.available(),
    "no scratch database: set DATABASE_URL (or JOBS_SCRATCH_DATABASE_URL)")


def record(**overrides):
    """A record satisfying schema.COLUMNS, the shape every normalize_* owes.

    Same construction as tests/test_upsert_checked.py:104-107 -- every column
    present, because upsert binds them as named parameters.
    """
    rec = {c: None for c in schema.COLUMNS}
    rec.update(platform="test", company_token="t", company_name="T",
               source_id="1", title="Engineer", job_url="https://example/1")
    rec.update(overrides)
    return rec


class _NoClose:
    """A connection proxy whose close() is a no-op.

    Every ingest main() closes the connection it was handed. The scratch
    schema's context manager needs that same connection alive afterwards to
    issue its DROP, so the one method is intercepted and nothing else is.
    """

    def __init__(self, conn):
        self._conn = conn

    def close(self):
        pass

    def __getattr__(self, name):
        return getattr(self._conn, name)


def count_rows(conn, platform):
    return conn.execute(
        f"SELECT count(*) FROM {schema.SCHEMA}.jobs WHERE platform = %s",
        (platform,)).fetchone()[0]


# ---------------------------------------------------------------------------
# D19 -- ingest/builtin-nyc.py, parse outside the per-page try
# ---------------------------------------------------------------------------

class TestBuiltInPerPageIsolation(unittest.TestCase):
    """D19 at `ingest/builtin-nyc.py:438` (the register said `:390`).

    `parse_page` sat after the fetch-only `try` at `:430-436`, so a page whose
    markup none of the regexes anticipated raised out of `main()` -- taking
    with it every page already parsed, because `all_records` is upserted once
    at the end rather than per page.
    """

    @classmethod
    def setUpClass(cls):
        cls.mod = load_ingest("builtin-nyc")

    @requires_db
    def test_one_unparseable_page_does_not_lose_the_other_pages(self):
        mod = self.mod
        pages = {n: f"<html>page {n}</html>" for n in range(1, 4)}
        which = {html: n for n, html in pages.items()}

        def parse_page(page_html, stats=None):
            n = which[page_html]
            if n == 2:
                raise IndexError("list index out of range")   # a real parser shape
            return [record(platform="builtin", source_id=f"p{n}",
                           title=f"Engineer {n}",
                           job_url=f"https://www.builtinnyc.com/jobs/{n}")]

        with scratchdb.scratch_schema() as (conn, _name):
            with mock.patch.object(mod, "MAX_PAGES", 3), \
                 mock.patch.object(mod, "DETAIL_FETCH_LIMIT", 0), \
                 mock.patch.object(mod, "REQUEST_DELAY_SECONDS", 0), \
                 mock.patch.object(mod, "fetch_page", lambda n: pages[n]), \
                 mock.patch.object(mod, "parse_page", parse_page), \
                 mock.patch.object(mod.dbconn, "connect_or_exit",
                                   lambda *a, **k: _NoClose(conn)):
                out, err = io.StringIO(), io.StringIO()
                with redirect_stdout(out), redirect_stderr(err):
                    mod.main()

            self.assertEqual(
                count_rows(conn, "builtin"), 2,
                "pages 1 and 3 parsed cleanly; a page-2 parse failure must "
                "cost page 2 and nothing else")
            self.assertIn("did not parse", err.getvalue(),
                          "a page that failed to parse must say so -- silence "
                          "is this system's failure mode")
            self.assertIn("2/3 pages (1 page failures)", out.getvalue(),
                          "the parse failure belongs in the summary's page "
                          "count alongside the fetch failures")

    @requires_db
    def test_every_page_failing_is_still_a_failed_run(self):
        """The isolation must not turn a total break into a quiet success."""
        mod = self.mod

        def parse_page(page_html, stats=None):
            raise IndexError("list index out of range")

        with scratchdb.scratch_schema() as (conn, _name):
            with mock.patch.object(mod, "MAX_PAGES", 2), \
                 mock.patch.object(mod, "DETAIL_FETCH_LIMIT", 0), \
                 mock.patch.object(mod, "REQUEST_DELAY_SECONDS", 0), \
                 mock.patch.object(mod, "fetch_page", lambda n: "<html></html>"), \
                 mock.patch.object(mod, "parse_page", parse_page), \
                 mock.patch.object(mod.dbconn, "connect_or_exit",
                                   lambda *a, **k: _NoClose(conn)):
                with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
                    with self.assertRaises(SystemExit) as cm:
                        mod.main()
            self.assertEqual(cm.exception.code, 1)


# ---------------------------------------------------------------------------
# D19 -- the two Google scripts, normalize outside the per-query try
# ---------------------------------------------------------------------------

class _GoogleIsolationCase(unittest.TestCase):
    """Shared body: both scripts call the same normalize_job()."""

    module = None          #: set by the subclass
    fetch_attr = None      #: the per-query fetch the subclass fakes
    platform = "google_jobs"

    QUERIES = [
        {"slug": "alpha", "query": "a", "location": "NYC", "mode": "ai_integration"},
        {"slug": "beta", "query": "b", "location": "NYC", "mode": "ai_integration"},
    ]

    def _run(self, conn, normalize_job):
        mod = self.mod
        picked = [(q, None) for q in self.QUERIES]
        out, err = io.StringIO(), io.StringIO()
        with mock.patch.object(mod, self.fetch_attr,
                               lambda *a, **k: [{"slug_echo": "x"}]), \
             mock.patch.object(mod, "normalize_job", normalize_job), \
             mock.patch.object(mod, "log_query_stats", lambda *a, **k: None), \
             mock.patch.object(mod.state, "mark_success", lambda *a, **k: None), \
             mock.patch.object(mod.state, "release_claim", lambda *a, **k: None), \
             mock.patch.object(mod.schema, "close_stale", lambda *a, **k: 0), \
             mock.patch.object(mod.dbconn, "connect_or_exit",
                               lambda *a, **k: _NoClose(conn)), \
             mock.patch.object(mod, self.pick_attr, lambda *a, **k: picked):
            with redirect_stdout(out), redirect_stderr(err):
                mod.main()
        return out.getvalue(), err.getvalue()

    def _assert_one_bad_query_costs_one_query(self, conn):
        calls = {"n": 0}

        def normalize_job(item, mode):
            calls["n"] += 1
            if calls["n"] == 1:
                raise KeyError("title")
            return record(platform=self.platform, source_id="ok",
                          title="Engineer", job_url="https://example/ok")

        out, err = self._run(conn, normalize_job)
        self.assertEqual(
            count_rows(conn, self.platform), 1,
            "the second query normalized cleanly; the first one's failure "
            "must not have ended the run before it was reached")
        self.assertIn("did not normalize", err)
        self.assertIn("1/2 queries succeeded (1 failed)", out,
                      "a query lost to normalization is a failed query in "
                      "the summary, not an invisible one")


class TestSerpApiQueryIsolation(_GoogleIsolationCase):
    """D19 at `ingest/google-serpapi.py:335` (the register said `:324`), and
    its guard is the fetch-only `try` at `:325-333` (the register said
    `:314-322`)."""

    fetch_attr = "serpapi_search"
    pick_attr = "pick_stale_queries_by_bucket"

    @classmethod
    def setUpClass(cls):
        cls.mod = load_ingest("google-serpapi")

    @requires_db
    def test_one_query_that_does_not_normalize_costs_one_query(self):
        with mock.patch.object(self.mod, "SERPAPI_API_KEY", "test-key"):
            with scratchdb.scratch_schema() as (conn, _name):
                self._assert_one_bad_query_costs_one_query(conn)


class TestApifyQueryIsolation(_GoogleIsolationCase):
    """D19 at `ingest/google-apify.py:241` (the register said `:231`), guarded
    by the fetch-only `try` at `:231-239` (the register said `:221-229`)."""

    fetch_attr = "run_actor_query"
    pick_attr = "pick_stale_queries"

    @classmethod
    def setUpClass(cls):
        cls.mod = load_ingest("google-apify")

    @requires_db
    def test_one_query_that_does_not_normalize_costs_one_query(self):
        with mock.patch.object(self.mod, "APIFY_API_TOKEN", "test-token"):
            with scratchdb.scratch_schema() as (conn, _name):
                self._assert_one_bad_query_costs_one_query(conn)


# ---------------------------------------------------------------------------
# D19 + D18 -- ingest/ats.py, per-company isolation
# ---------------------------------------------------------------------------

class TestAtsPerCompanyIsolation(unittest.TestCase):
    """D19's ats.py site is no longer where the register puts it.

    `597662b` moved the normalize call inside `fetch_company()`
    (`ingest/ats.py:1019`), which `main()` calls from inside its per-company
    `try` (`:1097`). Structurally the register's fix has already happened. What
    had NOT happened is the half that makes it mean anything: the `except`
    tuple at `:1100-1101` names transport exceptions only, so a normalizer
    raising still went straight past it and ended the run for every remaining
    company. These tests pin the behaviour rather than the shape.
    """

    @classmethod
    def setUpClass(cls):
        cls.mod = load_ingest("ats")

    def _roster(self):
        return [
            {"platform": "greenhouse", "token": "bad", "name": "Bad Co",
             "status": "valid"},
            {"platform": "greenhouse", "token": "good", "name": "Good Co",
             "status": "valid"},
        ]

    def _run(self, conn, roster, fetchers=None, normalizers=None):
        mod = self.mod
        fetchers = fetchers or {"greenhouse": lambda token, **k: mod.Fetched(
            [{"id": token}])}
        normalizers = normalizers or dict(mod.NORMALIZERS)
        out, err = io.StringIO(), io.StringIO()
        with mock.patch.object(mod, "FETCHERS", fetchers), \
             mock.patch.object(mod, "NORMALIZERS", normalizers), \
             mock.patch.object(mod.ats_sources, "load_companies",
                               lambda *a, **k: roster), \
             mock.patch.object(mod.dbconn, "connect_or_exit",
                               lambda *a, **k: _NoClose(conn)):
            with redirect_stdout(out), redirect_stderr(err):
                mod.main([])
        return out.getvalue(), err.getvalue()

    @requires_db
    def test_a_normalizer_that_raises_costs_one_company(self):
        mod = self.mod

        def normalize(company, job):
            if company["token"] == "bad":
                raise TypeError("'NoneType' object is not subscriptable")
            return record(platform="greenhouse",
                          company_token=company["token"],
                          company_name=company["name"], source_id=job["id"],
                          job_url=f"https://boards/{job['id']}")

        with scratchdb.scratch_schema() as (conn, _name):
            out, err = self._run(conn, self._roster(),
                                 normalizers={"greenhouse": normalize})
            self.assertEqual(
                count_rows(conn, "greenhouse"), 1,
                "Good Co normalized cleanly; Bad Co's normalizer raising must "
                "not have ended the run before Good Co was reached")
            self.assertIn("did not normalize", err)
            self.assertIn("1 failed", out)

    @requires_db
    def test_a_platform_with_no_fetcher_costs_one_company(self):
        """D18's residue at this site.

        `FETCHERS[platform]` / `NORMALIZERS[platform]` (`ingest/ats.py:1000`)
        is the config subscript that survived the move to `company_ats`: the
        roster's own `platform`/`token` keys are built literally by
        `ats_sources.load_companies` (`ingest/ats_sources.py:123-124`) and
        cannot be missing, but the platform NAME still has to be one this
        script has a fetcher for.
        """
        mod = self.mod
        roster = [{"platform": "nosuchplatform", "token": "x", "name": "X",
                   "status": "valid"}] + self._roster()[1:]

        def normalize(company, job):
            return record(platform="greenhouse", company_token=company["token"],
                          company_name=company["name"], source_id=job["id"],
                          job_url=f"https://boards/{job['id']}")

        with scratchdb.scratch_schema() as (conn, _name):
            out, err = self._run(conn, roster,
                                 normalizers={"greenhouse": normalize})
            self.assertEqual(
                count_rows(conn, "greenhouse"), 1,
                "an unknown platform in the roster is one company's problem, "
                "not the run's")
            self.assertIn("nosuchplatform", out + err)

    def test_the_platform_tables_agree_across_the_two_files(self):
        """The reason the KeyError above is reachable at all.

        `ats_sources.HANDLED_PLATFORMS` is what filters the roster query;
        `ats.FETCHERS` / `ats.NORMALIZERS` are what the run indexes. They are
        three independent literals in two files, and nothing before this
        noticed when one grew a platform the others had not.
        """
        from ingest import ats_sources
        self.assertEqual(set(ats_sources.HANDLED_PLATFORMS),
                         set(self.mod.FETCHERS))
        self.assertEqual(set(ats_sources.HANDLED_PLATFORMS),
                         set(self.mod.NORMALIZERS))


# ---------------------------------------------------------------------------
# D18 -- ingest/google-serpapi.py, per-bucket keys read after the guard
# ---------------------------------------------------------------------------

class TestQueryBucketsAreCheckedInsideTheGuard(unittest.TestCase):
    """D18's second site: `bucket["queries"]` / `bucket["daily_budget"]` at
    `ingest/google-serpapi.py:221-222` (the register said `:213-214`), read
    inside `pick_stale_queries_by_bucket` -- which runs at `:314`, after the
    guarded `load_query_buckets()` at `:307-312` (the register said `:300`)
    has already returned.

    The `q[...]` subscripts are the same defect one level down and are checked
    here too: `q["mode"]` is not touched until after the query's SerpApi
    credit has been spent.
    """

    @classmethod
    def setUpClass(cls):
        cls.mod = load_ingest("google-serpapi")

    def _load(self, config):
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
            json.dump(config, f)
            path = f.name
        try:
            with mock.patch.object(self.mod, "GOOGLE_JOBS_QUERIES_FILE", path):
                return self.mod.load_query_buckets()
        finally:
            os.unlink(path)

    def _bucket(self, **overrides):
        b = {"daily_budget": 2,
             "queries": [{"slug": "a", "query": "q", "location": "NYC",
                          "mode": "ai_integration"}]}
        b.update(overrides)
        return b

    def test_a_well_formed_config_still_loads(self):
        buckets = self._load({"buckets": {"one": self._bucket()}})
        self.assertEqual(list(buckets), ["one"])

    def test_a_bucket_with_no_daily_budget_fails_at_the_load(self):
        b = self._bucket()
        del b["daily_budget"]
        with self.assertRaises(KeyError) as cm:
            self._load({"buckets": {"one": b}})
        self.assertIn("one", str(cm.exception))
        self.assertIn("daily_budget", str(cm.exception))

    def test_a_bucket_with_no_queries_fails_at_the_load(self):
        b = self._bucket()
        del b["queries"]
        with self.assertRaises(KeyError) as cm:
            self._load({"buckets": {"one": b}})
        self.assertIn("queries", str(cm.exception))

    def test_a_query_missing_mode_fails_at_the_load_not_after_the_credit(self):
        b = self._bucket()
        del b["queries"][0]["mode"]
        with self.assertRaises(KeyError) as cm:
            self._load({"buckets": {"one": b}})
        self.assertIn("mode", str(cm.exception))
        self.assertIn("one", str(cm.exception))

    def test_a_query_missing_slug_fails_at_the_load(self):
        b = self._bucket()
        del b["queries"][0]["slug"]
        with self.assertRaises(KeyError):
            self._load({"buckets": {"one": b}})

    def test_buckets_that_are_not_an_object_fail_at_the_load(self):
        with self.assertRaises(TypeError):
            self._load({"buckets": [self._bucket()]})

    def test_the_shipped_config_passes_its_own_check(self):
        """The check is worthless if the real file does not satisfy it."""
        self.assertTrue(self.mod.load_query_buckets())

    def test_mains_guard_names_every_exception_the_load_can_raise(self):
        """D18's whole point: the failure must arrive where it is reported.

        Read off the source rather than asserted behaviourally, because
        reaching main()'s guard needs a database and this claim does not.
        """
        path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "ingest", "google-serpapi.py")
        with open(path) as f:
            src = f.read()
        guard = src[src.index("buckets = load_query_buckets()"):]
        guard = guard[:guard.index("conn.close()")]
        for exc in ("OSError", "json.JSONDecodeError", "KeyError", "TypeError"):
            self.assertIn(exc, guard,
                          f"load_query_buckets() can raise {exc} and main()'s "
                          f"guard does not name it")


# ---------------------------------------------------------------------------
# D21 -- ingest/hn-hiring.py, relevance.load() at import time
# ---------------------------------------------------------------------------

class TestRoleVocabularyLoadIsGuarded(unittest.TestCase):
    """D21 at `ingest/hn-hiring.py:151`, into module-level `ROLE_PATTERN` at
    `:163` (the register said `:90`, `:152`, `:164`).

    The register says "a config file that cannot be read or parsed crashes at
    import". Half of that is already false and was when it was written:
    `relevance.load()` catches FileNotFoundError and returns the DISABLED
    defaults (`relevance.py:95-96`), so a MISSING file never crashed anything.
    A file that is present and malformed did, and still does the moment the
    guard is removed.
    """

    @classmethod
    def setUpClass(cls):
        cls.mod = load_ingest("hn-hiring")

    def _with_config(self, text):
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
            f.write(text)
            return f.name

    def test_malformed_json_does_not_take_the_pattern_build_down(self):
        path = self._with_config("{not json at all")
        try:
            with mock.patch.object(relevance, "CONFIG_FILE", path):
                err = io.StringIO()
                with redirect_stderr(err):
                    self.assertIsNone(self.mod._python_role_pattern())
                self.assertIn("WARNING", err.getvalue(),
                              "the positional fallback is correct but it is "
                              "not free -- it must not be silent")
        finally:
            os.unlink(path)

    def test_a_config_that_is_not_an_object_does_not_take_it_down(self):
        path = self._with_config('["title_include"]')
        try:
            with mock.patch.object(relevance, "CONFIG_FILE", path):
                with redirect_stderr(io.StringIO()):
                    self.assertIsNone(self.mod._python_role_pattern())
        finally:
            os.unlink(path)

    def test_a_missing_file_was_never_the_problem(self):
        """Pins the half of D21's text that was wrong, so it stays pinned."""
        with mock.patch.object(relevance, "CONFIG_FILE",
                               "/nonexistent/relevance.json"):
            with redirect_stderr(io.StringIO()):
                self.assertIsNone(self.mod._python_role_pattern())

    def test_importing_the_module_survives_a_malformed_config(self):
        """The defect proper: this runs in the MODULE BODY.

        `evals/ingest_modules.py`'s docstring states as a precondition that
        importing an ingest script runs its body "and nothing else... none of
        them connects, fetches or writes". This one read a config file, and an
        unreadable one made the import itself the failure -- before main(), and
        therefore before the `FAILED:` reporting convention exists.
        """
        import importlib.util

        path = self._with_config("{not json at all")
        script = os.path.join(os.path.dirname(os.path.dirname(
            os.path.abspath(__file__))), "ingest", "hn-hiring.py")
        try:
            with mock.patch.object(relevance, "CONFIG_FILE", path):
                spec = importlib.util.spec_from_file_location(
                    "_hn_hiring_reimport_probe", script)
                module = importlib.util.module_from_spec(spec)
                err = io.StringIO()
                with redirect_stderr(err):
                    spec.loader.exec_module(module)     # D21: this raised
                self.assertIsNone(module.ROLE_PATTERN)
                self.assertIn("WARNING", err.getvalue())
        finally:
            sys.modules.pop("_hn_hiring_reimport_probe", None)
            os.unlink(path)

    def test_the_real_config_still_produces_a_pattern(self):
        """A guard that always falls back is the same bug wearing a hat."""
        self.assertIsNotNone(self.mod.ROLE_PATTERN,
                             "config/relevance.json has title_include "
                             "patterns; the live import must have compiled "
                             "them, not fallen back")


if __name__ == "__main__":
    unittest.main()

"""backend/serp/ -- the provider interface task 23 is, descoped.

WHAT THESE TESTS ARE FOR, IN ORDER OF HOW EXPENSIVE THE BUG WOULD BE

  1. The three failure classes stay three. A deferral recorded as a run is a
     query that goes quiet for its cadence window; a dead key reported as a
     deferral is a bank that retries forever and records nothing. Both are
     silent, which is this system's failure mode (".claude/CLAUDE.md").
  2. Nothing normalises except google_jobs.normalize_job. The register already
     holds what the second copy cost when it existed.
  3. Cost and latency are unreportable for a cached answer, enforced where the
     number is printed rather than by asking callers to remember.
  4. The API key is not in the cache key and does not reach disk.
  5. The ledger's authority is the vendor, and a reconciliation that did not
     happen never reads as agreement.

OFFLINE. Every provider test replays a committed cassette; cassettes.CassetteMiss
is fatal, so a request this suite does not have recorded fails rather than
quietly going back to the network.
"""

import json
import os
import sys
import tempfile
import unittest
import urllib.error

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import schema                                                  # noqa: E402
import searchnorm                                              # noqa: E402
import searchqueries                                           # noqa: E402
import serp                                                    # noqa: E402
from evals import cassettes, scratchdb                         # noqa: E402
from lib import envfile                                        # noqa: E402
from google_jobs import normalize_job                          # noqa: E402
from serp import cache as serpcache                            # noqa: E402
from serp import datechip, dispatch, normalize, quota          # noqa: E402
from serp.providers import apify as apify_mod                  # noqa: E402
from serp.providers import serpapi as serpapi_mod              # noqa: E402
from tests.test_ingest_cassettes import _immediate_success     # noqa: E402

#: The pipeline's own .env, as tests/test_search_queries.py:30 does it. Tests
#: must not depend on the caller having exported DATABASE_URL by hand -- and a
#: module that skipped for that reason would read exactly like one that passed.
envfile.load(os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), ".env"))

require_serpapi = unittest.skipUnless(
    cassettes.available("google-serpapi"),
    "cassette google-serpapi not recorded")
require_apify = unittest.skipUnless(
    cassettes.available("google-apify"),
    "cassette google-apify not recorded")

#: The exact query the google-serpapi cassette was recorded against. The
#: replayer matches on the scrubbed URL with parameter ORDER preserved
#: (evals/cassettes.py:139-155), so these three values plus serpapi.build_url()
#: reproducing the recorded parameter order is what makes replay possible at
#: all -- and is itself the assertion that the adapter is a faithful lift of
#: ingest/google-serpapi.py:311-343.
RECORDED_QUERY = "AI engineer"
RECORDED_LOCATION = "New York, New York, United States"
RECORDED_CHIP = "week"


class FakeResponse(urllib.error.HTTPError):
    def __init__(self, code):
        super().__init__("https://example.test/", code, "boom", {}, None)


class StubProvider:
    """A provider module's whole surface, so serp.call() can be driven."""

    NAME = "stub"
    UNIT = "searches"
    AccountRefused = serpapi_mod.AccountRefused
    DEFERRING_EXCEPTIONS = serpapi_mod.DEFERRING_EXCEPTIONS

    def __init__(self, raises=None, raw=None):
        self._raises = raises
        self._raw = raw if raw is not None else []
        self.calls = []

    def fetch(self, query, location, creds, *, date_chip=None):
        self.calls.append((query, location, date_chip))
        if self._raises is not None:
            raise self._raises
        return self._raw

    @staticmethod
    def credits_for(raw):
        return 1

    @staticmethod
    def account(creds):
        return {"used": 0, "left": 100, "allowance": 100}


def with_stub(stub):
    """Register `stub` as a provider for the duration of a `with` block."""
    class _Ctx:
        def __enter__(self):
            serp.PROVIDERS[stub.NAME] = stub
            return stub

        def __exit__(self, *exc):
            serp.PROVIDERS.pop(stub.NAME, None)
    return _Ctx()


# ---------------------------------------------------------------------------
# 1. the three failure classes
# ---------------------------------------------------------------------------

class TestTheThreeFailureClasses(unittest.TestCase):
    """serp/__init__.py's whole contract, and searchqueries.record_run()'s."""

    def test_429_after_backoff_is_a_deferral(self):
        with with_stub(StubProvider(raises=FakeResponse(429))) as stub:
            with self.assertRaises(serp.Deferred):
                serp.call("q", "NYC", provider=stub.NAME)

    def test_5xx_is_a_deferral(self):
        with with_stub(StubProvider(raises=FakeResponse(503))) as stub:
            with self.assertRaises(serp.Deferred):
                serp.call("q", "NYC", provider=stub.NAME)

    def test_a_timeout_is_a_deferral(self):
        with with_stub(StubProvider(raises=TimeoutError("slow"))) as stub:
            with self.assertRaises(serp.Deferred):
                serp.call("q", "NYC", provider=stub.NAME)

    def test_a_401_IS_NOT_A_DEFERRAL_and_the_clause_order_is_why(self):
        """HTTPError is a SUBCLASS of URLError, and URLError is in every
        adapter's DEFERRING_EXCEPTIONS. Reorder the two except clauses in
        serp._fetch and this test is the only thing that notices: a revoked
        key would be reported as a deferral, retried every night forever, and
        record nothing -- a dead key indistinguishable from a quiet one."""
        with with_stub(StubProvider(raises=FakeResponse(401))) as stub:
            with self.assertRaises(urllib.error.HTTPError):
                serp.call("q", "NYC", provider=stub.NAME)

    def test_an_account_refusal_is_its_own_class(self):
        refusal = serpapi_mod.AccountRefused("run out of searches")
        with with_stub(StubProvider(raises=refusal)) as stub:
            with self.assertRaises(serp.ProviderRefused):
                serp.call("q", "NYC", provider=stub.NAME)

    def test_an_unknown_provider_raises_rather_than_falling_back(self):
        """Six of the eight adapters are CUT. Serving 'scrapingbee' from
        SerpApi would spend a metered credit against a config line that says
        not to."""
        with self.assertRaises(ValueError):
            serp.resolve("scrapingbee")


class TestSerpApiReportsErrorsInsideA200(unittest.TestCase):
    """SerpApi answers a bad key, an exhausted plan and an empty result set all
    as HTTP 200 with an `error` key, so no status code sees them. The lifted
    function raised one RuntimeError for all three."""

    def _fetch_with_body(self, body):
        real = serpapi_mod.http.get_json
        serpapi_mod.http.get_json = lambda *a, **k: body
        try:
            return serpapi_mod.fetch("q", "NYC", "key")
        finally:
            serpapi_mod.http.get_json = real

    def test_no_results_is_an_answer_not_a_failure(self):
        got = self._fetch_with_body(
            {"error": "Google hasn't returned any results for this query."})
        self.assertEqual(got, [])

    def test_an_exhausted_plan_is_an_account_refusal(self):
        with self.assertRaises(serpapi_mod.AccountRefused):
            self._fetch_with_body(
                {"error": "Your account has run out of searches."})

    def test_an_invalid_key_is_an_account_refusal(self):
        with self.assertRaises(serpapi_mod.AccountRefused):
            self._fetch_with_body({"error": "Invalid API key."})

    def test_anything_else_is_spent_and_unusable(self):
        with self.assertRaises(RuntimeError):
            self._fetch_with_body({"error": "Unsupported `chips` parameter."})

    def test_a_missing_key_never_reaches_the_network(self):
        with self.assertRaises(serpapi_mod.AccountRefused):
            serpapi_mod.fetch("q", "NYC", None)


# ---------------------------------------------------------------------------
# 2. one definition of the record shape
# ---------------------------------------------------------------------------

class TestNothingHereNormalises(unittest.TestCase):

    def test_no_adapter_defines_a_normalizer(self):
        """The prohibition in ".claude/CLAUDE.md" -- "Do not add a second
        definition of the Google Jobs record shape" -- as a check rather than
        as a paragraph. google_jobs.py records what the drift cost: two of the
        four differences fed content_hash, so one posting written by two paths
        produced two digests and the row flip-flopped on alternating runs."""
        for mod in (serpapi_mod, apify_mod):
            for name in dir(mod):
                self.assertNotIn(
                    "normalize", name.lower(),
                    f"{mod.NAME} defines {name!r}; normalisation belongs to "
                    f"serp/normalize.py, which calls google_jobs.normalize_job")

    def test_normalize_records_is_normalize_job(self):
        # No relative `posted_at` on purpose. parse_relative_posted_at resolves
        # "2 days ago" as now - delta, so two calls microseconds apart differ --
        # google_jobs.py records that as the KNOWN BUG "posted_at slides", and
        # a test that tripped on it would be measuring the clock.
        job = {"title": "AI Engineer", "company_name": "Acme",
               "location": "New York, NY", "description": "<p>hi</p>",
               "detected_extensions": {"schedule_type": "Full-time"},
               "apply_options": [{"link": "https://example.test/a"}]}
        self.assertEqual(normalize.records([job], "New York, NY"),
                         [normalize_job(job, "nyc")])

    def test_the_same_payload_keys_the_same_row_by_either_provider(self):
        """"The two sources returning the same posting is supposed to be one
        row, and it only stays one row while both key it the same way"
        (google_jobs.py). Provider is not an input to normalisation, so this
        holds by construction -- and this test is what fails if a provider
        argument is ever threaded through."""
        job = {"title": "Data Analyst", "company_name": "Acme",
               "location": "New York, NY",
               "apply_options": [{"link": "https://example.test/b"}]}
        by_one = normalize.records([job], "New York, NY")[0]
        by_other = normalize.records([job], "New York, NY")[0]
        self.assertEqual(schema.make_job_id(by_one),
                         schema.make_job_id(by_other))

    def test_mode_is_derived_from_the_location_with_the_shared_pattern(self):
        self.assertEqual(normalize.mode_for("New York, NY"), "nyc")
        self.assertEqual(normalize.mode_for("Remote"), "remote")
        self.assertEqual(normalize.mode_for(None), "nyc")


# ---------------------------------------------------------------------------
# 3. provenance, and the refusal to price a replay
# ---------------------------------------------------------------------------

class TestCostIsUnreportableForACachedAnswer(unittest.TestCase):

    def _result(self, from_cache):
        return serp.SerpResult([], "serpapi", credits=1, unit="searches",
                               from_cache=from_cache, latency_s=1.5)

    def test_a_live_run_reports_spend_and_latency(self):
        line = serp.cost_line([self._result(False), self._result(False)])
        self.assertIn("2 searches", line)
        self.assertIn("3.0s", line)

    def test_one_cached_answer_suppresses_both(self):
        """evals/report.py's rule, applied to the other metered resource:
        "a replayed response carries the latency and token usage of the call
        that produced it ... mixing them produces a confident wrong number"."""
        line = serp.cost_line([self._result(False), self._result(True)])
        self.assertIn("not reported", line)
        self.assertIn("1/2", line)
        self.assertNotIn("1.5s", line)

    def test_the_unit_travels_with_the_number(self):
        mixed = [serp.SerpResult([], "serpapi", credits=2, unit="searches"),
                 serp.SerpResult([], "apify", credits=30, unit="results")]
        line = serp.cost_line(mixed)
        self.assertIn("2 searches", line)
        self.assertIn("30 results", line)
        self.assertNotIn("32", line)


# ---------------------------------------------------------------------------
# 4. the cache
# ---------------------------------------------------------------------------

class TestCache(unittest.TestCase):

    def setUp(self):
        self._dir = tempfile.TemporaryDirectory()
        self._prev = os.environ.get("SERP_CACHE_DIR")
        os.environ["SERP_CACHE_DIR"] = self._dir.name

    def tearDown(self):
        if self._prev is None:
            os.environ.pop("SERP_CACHE_DIR", None)
        else:
            os.environ["SERP_CACHE_DIR"] = self._prev
        self._dir.cleanup()

    def test_the_key_ignores_spelling_the_way_search_queries_does(self):
        self.assertEqual(
            serpcache.key("Software  Engineer", "New York, NY", now=0),
            serpcache.key("software engineer", "New York, NY", now=0))

    def test_the_date_chip_is_in_the_key(self):
        """chips=today and chips=month are different questions. Sharing an
        entry would serve a one-day window to a query that asked for a month --
        a silent under-fetch."""
        self.assertNotEqual(
            serpcache.key("q", "NYC", date_chip="today", now=0),
            serpcache.key("q", "NYC", date_chip="month", now=0))

    def test_the_provider_is_in_the_key(self):
        self.assertNotEqual(serpcache.key("q", "NYC", provider="serpapi", now=0),
                            serpcache.key("q", "NYC", provider="apify", now=0))

    def test_a_new_day_is_a_new_key(self):
        self.assertNotEqual(serpcache.key("q", "NYC", now=0),
                            serpcache.key("q", "NYC", now=86400 * 3))

    def test_the_api_key_is_not_in_the_material_and_never_reaches_disk(self):
        """23-serp-abstraction.md: "rotating a credential must not discard a
        corpus of paid-for answers, and a key must never reach disk"."""
        secret = "sk-" + "9" * 40
        digest = serpcache.key("q", "NYC", provider="serpapi", now=0)
        serpcache.put(digest, [{"title": "x"}], now=0)
        found = []
        for dirpath, _, names in os.walk(self._dir.name):
            for name in names:
                with open(os.path.join(dirpath, name)) as fh:
                    if secret in fh.read():
                        found.append(name)
        self.assertEqual(found, [])
        # And the digest itself does not move when the credential does.
        self.assertEqual(digest, serpcache.key("q", "NYC", provider="serpapi",
                                               now=0))

    def test_an_entry_older_than_the_ttl_is_a_miss(self):
        digest = serpcache.key("q", "NYC", now=0)
        serpcache.put(digest, [{"title": "x"}], now=0)
        self.assertIsNotNone(serpcache.get(digest, now=0))
        self.assertIsNone(
            serpcache.get(digest, now=serpcache.TTL_SECONDS + 1))

    def test_a_truncated_file_reads_as_a_miss(self):
        digest = serpcache.key("q", "NYC", now=0)
        serpcache.put(digest, [{"title": "x"}], now=0)
        path = serpcache._path(digest)
        with open(path, "w") as fh:
            fh.write('{"stored_at": 0, "raw": [{"tit')
        self.assertIsNone(serpcache.get(digest, now=0))

    def test_the_store_gitignores_itself(self):
        serpcache.put(serpcache.key("q", "NYC", now=0), [], now=0)
        with open(os.path.join(self._dir.name, ".gitignore")) as fh:
            self.assertEqual(fh.read().strip(), "*")

    def test_a_hit_is_marked_and_costs_nothing(self):
        with with_stub(StubProvider(raw=[])) as stub:
            first = serp.call("q", "NYC", provider=stub.NAME,
                              cache=serpcache, now=0)
            second = serp.call("q", "NYC", provider=stub.NAME,
                               cache=serpcache, now=0)
        self.assertFalse(first.from_cache)
        self.assertTrue(second.from_cache)
        self.assertEqual(second.credits, 0)
        self.assertEqual(len(stub.calls), 1, "the second call hit the network")


# ---------------------------------------------------------------------------
# 5. the ledger
# ---------------------------------------------------------------------------

class TestQuotaLedger(unittest.TestCase):

    CONFIG = {
        "serpapi": {"unit": "searches", "allowance": 250,
                    "reconcilable": True, "reserve": 0},
        "apify": {"unit": "results", "allowance": None,
                  "reconcilable": False, "reserve": 0},
    }

    def _ledger(self, answers):
        """answers is a list popped per account() call, so a run can move."""
        seq = list(answers)
        return quota.Ledger(self.CONFIG, creds_for=lambda name: "key",
                            account_fn=lambda creds: seq.pop(0))

    def test_the_delta_is_measured_over_the_run_not_over_the_month(self):
        """The correction to the calculation DECISIONS.md records as wrong by
        3.3x. An opening read and a closing read minutes apart is one number
        about one run; "used minus everything we think we ever spent" is a sum
        of four unknowns, because a second machine, the contributor worker and
        tools/verify-date-filter.py all spend the same account."""
        led = self._ledger([{"used": 137, "left": 113, "allowance": 250},
                            {"used": 145, "left": 105, "allowance": 250}])
        led.check("serpapi")
        for _ in range(8):
            led.spend("serpapi", 1)
        rec = led.reconcile("serpapi")
        self.assertEqual(rec.vendor_billed, 8)
        self.assertEqual(rec.local_spend, 8)
        self.assertEqual(rec.delta, 0)

    def test_a_positive_delta_names_spend_this_process_cannot_see(self):
        led = self._ledger([{"used": 100, "left": 150},
                            {"used": 111, "left": 139}])
        led.check("serpapi")
        led.spend("serpapi", 8)
        self.assertEqual(led.reconcile("serpapi").delta, 3)

    def test_an_unreachable_vendor_allows_the_run_and_says_so(self):
        """Refusing would turn a network blip into a night with no searches,
        and the exhausted-account case is already handled one layer down."""
        def boom(creds):
            raise urllib.error.URLError("no route to host")
        led = quota.Ledger(self.CONFIG, creds_for=lambda n: "key",
                           account_fn=boom)
        led.check("serpapi")             # must not raise
        rec = led.reconcile("serpapi")
        self.assertIsNone(rec.delta)
        self.assertIn("UNAVAILABLE", rec.line())

    def test_a_reconciliation_that_did_not_happen_never_reads_as_agreement(self):
        """Apify counts dollars where this pipeline counts results. A delta of
        zero would say the two agree; None plus a stated reason says they were
        never compared. This is D37 from the other end."""
        led = self._ledger([{"used": 1.25, "left": 3.75, "unit": "usd"},
                            {"used": 1.25, "left": 3.75, "unit": "usd"}])
        led.check("apify")
        led.spend("apify", 30)
        rec = led.reconcile("apify")
        self.assertIsNone(rec.delta)
        self.assertIn("NOT RECONCILED", rec.line())
        self.assertIn("units do not meet", rec.line())

    def test_check_refuses_when_the_vendor_says_the_plan_is_spent(self):
        led = self._ledger([{"used": 250, "left": 0, "allowance": 250}])
        with self.assertRaises(serp.ProviderRefused):
            led.check("serpapi")

    def test_the_reserve_is_honoured(self):
        config = {"serpapi": dict(self.CONFIG["serpapi"], reserve=10)}
        seq = [{"used": 242, "left": 8, "allowance": 250}]
        led = quota.Ledger(config, creds_for=lambda n: "key",
                           account_fn=lambda c: seq.pop(0))
        with self.assertRaises(serp.ProviderRefused):
            led.check("serpapi")

    def test_the_shipped_config_documents_every_provider_the_descope_keeps(self):
        cfg = quota.load_config()
        self.assertEqual(sorted(cfg), sorted(serp.PROVIDERS))
        for name, entry in cfg.items():
            self.assertEqual(entry["unit"], serp.PROVIDERS[name].UNIT,
                             f"{name}: the config and the adapter disagree "
                             f"about what its allowance is denominated in")

    def test_underscore_keys_are_documentation_and_are_dropped(self):
        cfg = quota.load_config()
        for entry in cfg.values():
            self.assertEqual([k for k in entry if k.startswith("_")], [])


# ---------------------------------------------------------------------------
# 6. the date chip
# ---------------------------------------------------------------------------

class TestDateChip(unittest.TestCase):

    def test_a_query_that_never_ran_gets_no_filter_at_all(self):
        """The deliberate backfill. None is NOT "today"."""
        self.assertIsNone(datechip.choose(None))
        self.assertIsNone(datechip.choose(""))

    def test_an_unparseable_timestamp_asks_broadly(self):
        self.assertIsNone(datechip.choose("last Tuesday"))

    def test_the_buckets_cover_the_gap_that_actually_elapsed(self):
        from datetime import datetime, timedelta, timezone
        now = datetime(2026, 8, 2, 12, 0, 0, tzinfo=timezone.utc)

        def at(**kw):
            return (now - timedelta(**kw)).strftime("%Y-%m-%dT%H:%M:%S")

        self.assertEqual(datechip.choose(at(hours=6), now=now), "today")
        self.assertEqual(datechip.choose(at(days=2), now=now), "3days")
        self.assertEqual(datechip.choose(at(days=5), now=now), "week")
        self.assertEqual(datechip.choose(at(days=40), now=now), "month")

    def test_the_ingest_script_and_serp_share_one_definition(self):
        """It MOVED, it was not copied. api/query_claims.py holds a third copy
        on purpose, because backend/api/ may import only schema.py and lib/."""
        from evals.ingest_modules import load as load_ingest
        script = load_ingest("google-serpapi")
        self.assertIs(script.choose_date_chip, datechip.choose)


# ---------------------------------------------------------------------------
# 7. the dispatcher run_due() has been waiting for
# ---------------------------------------------------------------------------

class QuietConn:
    """Enough of a connection for a run that writes nothing.

    lib/upsert.py commits even on an empty batch, so `None` is not a stand-in
    for a connection here. This is not a fake database -- the tests that need
    one either use scratchdb or assert on the SQL, per
    backend/api/tests/fakedb.py's own warning that dispatching on SQL text
    cannot falsify a WHERE clause.
    """

    def __init__(self, present=()):
        self.present = set(present)

    def execute(self, sql, params=None):
        rows = []
        if params and isinstance(params[0], list):
            rows = [(c,) for c in params[0] if c in self.present]
        return type("R", (), {"fetchall": lambda self_: rows,
                              "fetchone": lambda self_: None})()

    def commit(self):
        pass

    def transaction(self):
        class _T:
            def __enter__(self_inner):
                return self_inner

            def __exit__(self_inner, *exc):
                return False
        return _T()


class TestDispatch(unittest.TestCase):

    def _provider(self, stub, **kw):
        return dispatch.SearchQueryProvider(QuietConn(), provider=stub.NAME,
                                            creds="key", **kw)

    def test_it_carries_a_name_for_the_two_columns_that_store_one(self):
        """run_due() reads getattr(provider, "name", None) and writes it to
        search_query_results.provider and search_queries.provider_last_used. A
        bare function would store NULL in both, silently."""
        with with_stub(StubProvider()) as stub:
            self.assertEqual(self._provider(stub).name, stub.NAME)

    def test_a_deferral_returns_None_so_nothing_is_recorded(self):
        with with_stub(StubProvider(raises=FakeResponse(503))) as stub:
            fn = self._provider(stub)
            self.assertIsNone(fn({"text": "q", "location": "NYC"}))
            self.assertEqual(fn.stats.get("deferred"), 1)

    def test_an_unusable_answer_returns_an_empty_list_so_the_run_IS_recorded(self):
        """The credit is spent. Returning None would spend it again tomorrow;
        returning [] moves last_run_at and leaves last_result_at, which is what
        searchnorm.should_retire()'s "no results in 14 days" clock reads."""
        with with_stub(StubProvider(raises=RuntimeError("bad chips"))) as stub:
            fn = self._provider(stub)
            self.assertEqual(fn({"text": "q", "location": "NYC"}), [])
            self.assertEqual(fn.stats.get("unusable"), 1)

    def test_an_account_refusal_is_not_swallowed_per_query(self):
        refusal = serpapi_mod.AccountRefused("run out of searches")
        with with_stub(StubProvider(raises=refusal)) as stub:
            fn = self._provider(stub)
            with self.assertRaises(serp.ProviderRefused):
                fn({"text": "q", "location": "NYC"})

    def test_the_date_chip_comes_from_the_query_row(self):
        """searchqueries.due_queries() selected last_run_at all along and
        dropped it on the floor. Without it every run re-asks Google the same
        unfiltered question."""
        with with_stub(StubProvider(raw=[])) as stub:
            fn = self._provider(stub)
            fn({"text": "q", "location": "NYC", "last_run_at": None})
            self.assertEqual(stub.calls[-1][2], None)

    def test_credentials_are_read_from_the_environment_and_nowhere_else(self):
        self.assertEqual(sorted(dispatch.CRED_ENV), sorted(serp.PROVIDERS))
        self.assertEqual(
            dispatch.credentials_for("serpapi", {"SERPAPI_API_KEY": "k"}), "k")
        self.assertIsNone(dispatch.credentials_for("serpapi", {}))

    def test_configured_exposes_a_boolean_and_never_the_key(self):
        with with_stub(StubProvider()) as stub:
            self.assertIs(self._provider(stub).configured, True)
            self.assertIs(
                dispatch.SearchQueryProvider(QuietConn(), provider=stub.NAME,
                                             creds=None).configured, False)


class TestStoredIdsAreReadBackFromTheTable(unittest.TestCase):
    """search_query_results.job_id REFERENCES jobs(id), so an id for a record
    the upsert rejected takes the whole attach down with it."""

    def _records(self, n):
        return [{"title": f"Role {i}", "company_name": "Acme",
                 "location": "New York, NY", "platform": "google_jobs",
                 "company_token": "acme", "source_id": f"s{i}"}
                for i in range(n)]

    def _ids(self, records, present):
        with with_stub(StubProvider()) as stub:
            fn = dispatch.SearchQueryProvider(QuietConn(present),
                                              provider=stub.NAME, creds="k")
            return fn._stored_ids(records)

    def test_a_record_that_did_not_land_is_not_attached(self):
        records = self._records(3)
        ids = [schema.make_job_id(r) for r in records]
        got = self._ids(records, {ids[0], ids[2]})
        self.assertEqual(got, [ids[0], ids[2]])

    def test_a_posting_returned_twice_is_attached_once(self):
        """One search can return the same posting through two apply_options.
        attach_results' ON CONFLICT DO NOTHING absorbs it silently while
        record_run counts it twice."""
        rec = self._records(1)[0]
        job_id = schema.make_job_id(rec)
        self.assertEqual(self._ids([rec, dict(rec)], {job_id}), [job_id])

    def test_nothing_normalised_means_no_query_at_all(self):
        self.assertEqual(self._ids([], set()), [])


# ---------------------------------------------------------------------------
# 8. cassettes: the adapters against bytes the real endpoints really sent
# ---------------------------------------------------------------------------

class TestAdaptersAgainstRecordedBytes(unittest.TestCase):

    def assert_contract(self, records):
        self.assertTrue(records, "the cassette produced no records")
        for rec in records:
            missing = [c for c in schema.COLUMNS if c not in rec]
            self.assertEqual(missing, [], f"record is missing {missing}")
            self.assertEqual(rec["platform"], "google_jobs")
            self.assertTrue(schema.make_job_id(rec))

    @require_serpapi
    def test_the_lifted_url_still_matches_what_was_recorded(self):
        """The replayer matches on the scrubbed URL with parameter order
        preserved, so this is the assertion that the adapter is a faithful lift
        of ingest/google-serpapi.py:311-343 -- hl and gl included, in place."""
        url = serpapi_mod.build_url(RECORDED_QUERY, RECORDED_LOCATION,
                                    date_chip=RECORDED_CHIP, api_key="secret")
        recorded = cassettes.Cassette.load("google-serpapi").interactions[0].url
        self.assertEqual(cassettes.scrub_url(url), recorded)

    @require_serpapi
    def test_serpapi_through_the_interface(self):
        with cassettes.replay("google-serpapi"):
            result = serp.call(RECORDED_QUERY, RECORDED_LOCATION,
                               date_chip=RECORDED_CHIP, provider="serpapi",
                               creds="secret")
        self.assert_contract(result.records)
        self.assertEqual(result.provider, "serpapi")
        self.assertEqual(result.credits, 1)
        self.assertEqual(result.unit, "searches")
        self.assertFalse(result.from_cache)

    @require_apify
    def test_apify_through_the_interface(self):
        cassette = _immediate_success(cassettes.Cassette.load("google-apify"))
        with cassettes.replay(cassette=cassette):
            result = serp.call("AI engineer", "New York", provider="apify",
                               creds="secret")
        self.assert_contract(result.records)
        self.assertEqual(result.provider, "apify")
        self.assertEqual(result.unit, "results")
        self.assertEqual(result.credits, len(result.records))

    @require_serpapi
    @require_apify
    def test_both_adapters_produce_the_same_shape_from_their_own_bytes(self):
        """23-serp-abstraction.md's last DoD line: "Cassettes per provider,
        proving the adapters agree on one input." What is actually assertable
        offline is stronger than one shared posting, which the two recordings
        do not have: every field of the stored shape is produced by ONE
        function for both, so the sets of keys are identical and the id
        expression is the same. A per-provider normalizer breaks this."""
        with cassettes.replay("google-serpapi"):
            a = serp.call(RECORDED_QUERY, RECORDED_LOCATION,
                          date_chip=RECORDED_CHIP, provider="serpapi",
                          creds="secret")
        cassette = _immediate_success(cassettes.Cassette.load("google-apify"))
        with cassettes.replay(cassette=cassette):
            b = serp.call("AI engineer", "New York", provider="apify",
                          creds="secret")
        self.assertEqual(sorted(a.records[0]), sorted(b.records[0]))
        self.assertEqual(sorted(a.records[0]), sorted(schema.COLUMNS))

    @require_serpapi
    def test_a_replay_does_not_reach_the_network_on_a_miss(self):
        """cassettes.CassetteMiss is fatal by design: falling through to the
        network on a miss is how a replayed test quietly becomes a live one."""
        with cassettes.replay("google-serpapi"):
            with self.assertRaises(cassettes.CassetteMiss):
                serp.call("a query nobody recorded", RECORDED_LOCATION,
                          provider="serpapi", creds="secret")


class TestTheApifyDifferencesAreDeclaredNotHidden(unittest.TestCase):

    def test_apify_declares_that_it_cannot_take_a_date_chip(self):
        """An adapter that accepted the argument and dropped it would be
        indistinguishable from one that used it."""
        self.assertFalse(apify_mod.SUPPORTS_DATE_CHIP)
        self.assertTrue(getattr(serpapi_mod, "SUPPORTS_DATE_CHIP", True))

    def test_apify_declares_that_its_account_cannot_be_reconciled(self):
        self.assertFalse(apify_mod.RECONCILABLE)
        self.assertTrue(getattr(serpapi_mod, "RECONCILABLE", True))


# ---------------------------------------------------------------------------
# 9. the seam, closed: cassette bytes -> jobs -> search_query_results
# ---------------------------------------------------------------------------

@unittest.skipUnless(scratchdb.available(),
                     "no scratch database: set DATABASE_URL")
class TestTheSeamIsClosed(unittest.TestCase):
    """The whole point of task 23, asserted end to end and offline.

    Before this, run_due() took a provider and every caller passed None, so
    `search_query_results` was empty in production and webapp/search.py's join
    -- which is the gate -- returned nothing for every Builder. This test walks
    recorded SerpApi bytes through serp.call(), the upsert, attach_results()
    and record_run(), against a real Postgres schema.

    It is not a fake connection on purpose. backend/evals/scratchdb.py's own
    docstring gives the reason and names the defect class: a fake dispatching
    on SQL text cannot show a foreign key violation, and job_id REFERENCES
    jobs(id) is exactly what makes "which ids may be attached" a real question.
    """

    def _register(self, conn, text, location, *, last_run_at, now):
        normalized_text, normalized_location = searchnorm.validate(text, location)
        query_id = conn.execute(
            searchnorm.REGISTER_QUERY_SQL,
            (normalized_text, normalized_location, text, location, None,
             "builder", None, now)).fetchone()[0]
        conn.execute(searchnorm.REGISTER_WATCHER_SQL,
                     (query_id, "user-a", "pursuit", now))
        conn.execute("UPDATE search_queries SET last_run_at = %s WHERE id = %s",
                     (last_run_at, query_id))
        conn.commit()
        return query_id

    @staticmethod
    def _five_days_ago():
        """A real-clock timestamp, because the chip is a function of elapsed
        wall time: run_due() does not thread `now` through to the provider, so
        datechip.choose() reads the clock. Five days back lands in `week`,
        which is what the cassette was recorded with."""
        from datetime import datetime, timedelta, timezone
        return (datetime.now(timezone.utc)
                - timedelta(days=5)).strftime("%Y-%m-%dT%H:%M:%S")

    @require_serpapi
    def test_recorded_bytes_become_attached_results(self):
        with scratchdb.scratch_schema() as (conn, _name):
            query_id = self._register(
                conn, RECORDED_QUERY, RECORDED_LOCATION,
                last_run_at=self._five_days_ago(), now="2026-08-02T00:00:00")

            provider = dispatch.SearchQueryProvider(conn, provider="serpapi",
                                                    creds="secret")
            with cassettes.replay("google-serpapi"):
                dispatched, due = searchqueries.run_due(
                    conn, provider=provider, now="2026-08-02T12:00:00")

            self.assertEqual(due, 1)
            self.assertEqual(dispatched, 1)

            jobs = conn.execute(
                "SELECT count(*) FROM jobs WHERE platform = 'google_jobs'"
            ).fetchone()[0]
            self.assertGreater(jobs, 0, "the run wrote no postings")

            rows = conn.execute(
                "SELECT job_id, provider FROM search_query_results "
                "WHERE query_id = %s", (query_id,)).fetchall()
            self.assertGreater(len(rows), 0,
                               "nothing was attached, so the search screen "
                               "still renders an empty list")
            self.assertTrue(all(p == "serpapi" for _, p in rows),
                            "provider was not recorded on the link rows")

            # Every attached id is a real posting. The FK would have raised, so
            # this is belt and braces on the claim _stored_ids() makes.
            attached = [job_id for job_id, _ in rows]
            present = conn.execute(
                "SELECT count(*) FROM jobs WHERE id = ANY(%s)",
                (attached,)).fetchone()[0]
            self.assertEqual(present, len(attached))

            ran, result_count, last_provider = conn.execute(
                "SELECT run_count, result_count_last_run, provider_last_used "
                "FROM search_queries WHERE id = %s", (query_id,)).fetchone()
            self.assertEqual(ran, 1)
            self.assertEqual(result_count, len(attached))
            self.assertEqual(last_provider, "serpapi")

    @require_serpapi
    def test_a_second_run_the_same_day_is_served_from_cache(self):
        """The credit is spent once. searchnorm.is_due() would not offer the
        query again this soon, so the runner is called directly -- the property
        under test is the cache's, not the cadence's."""
        with tempfile.TemporaryDirectory() as cache_dir:
            prev = os.environ.get("SERP_CACHE_DIR")
            os.environ["SERP_CACHE_DIR"] = cache_dir
            try:
                with scratchdb.scratch_schema() as (conn, _name):
                    self._register(conn, RECORDED_QUERY, RECORDED_LOCATION,
                                   last_run_at=self._five_days_ago(),
                                   now="2026-08-02T00:00:00")
                    provider = dispatch.SearchQueryProvider(
                        conn, provider="serpapi", creds="secret",
                        cache=serpcache)
                    query = searchqueries.due_queries(
                        conn, now="2026-08-02T12:00:00")[0]
                    with cassettes.replay("google-serpapi"):
                        first = provider(query)
                    # No cassette this time: a live fetch would raise, so a
                    # pass here IS the assertion that nothing was fetched.
                    second = provider(query)
                    self.assertEqual(first, second)
                    self.assertEqual(provider.stats.get("cache_hits"), 1)
                    self.assertEqual(provider.stats.get("credits"), 1)
            finally:
                if prev is None:
                    os.environ.pop("SERP_CACHE_DIR", None)
                else:
                    os.environ["SERP_CACHE_DIR"] = prev


if __name__ == "__main__":
    unittest.main()

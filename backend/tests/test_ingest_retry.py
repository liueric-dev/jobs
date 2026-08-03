"""D31: which ingest fetches retry, which one does not, and why.

WHAT THIS FILE IS FOR

D31 (in the defect register, deleted 2026-08-02:
`git show refactor-freeze-2026-08-02:docs/ingest/DEFECTS.md`) sat open for
weeks because it was a decision rather than a bug: three of the six ingest
scripts imported `lib.http` solely
for `DEFAULT_TIMEOUT` and then called `urllib.request.urlopen` directly, and
nothing anywhere recorded whether that was deliberate or an unfinished
migration. It was both. On 2026-08-02 three of the four raw-urlopen sites
moved to `lib.http`; the fourth, `builtin-nyc.fetch_description`, stayed, and
staying is the deliberate part.

So this file has two halves, and the second matters more than the first:

  * the three migrated sites survive a transient failure they used to lose a
    whole feed, page or query to;
  * `fetch_description` still issues EXACTLY ONE request per posting. That
    test passes against the pre-migration tree too, on purpose -- it is not
    here to prove a change, it is here so that the next person who notices
    the inconsistency and tidies it up gets a red test and a reason instead
    of a rude scraper. `builtin-nyc.py`'s RateLimited docstring is the reason.

NO NETWORK. Every cassette here is built in memory. `no_sleep()` neutralises
lib/http.py's backoff, without which the retry tests take eight seconds each
and stop being run.
"""

import io
import os
import sys
import unittest
import urllib.error
import xml.etree.ElementTree as ET
from contextlib import redirect_stderr
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from evals import cassettes                                    # noqa: E402
from evals.cassettes import Cassette, Interaction              # noqa: E402
from evals.ingest_modules import load as load_ingest           # noqa: E402


def _cassette(*interactions, name="unit"):
    """Same shape as tests/test_cassettes.py:41-47. Kept local rather than
    imported from that module: a test importing another test file couples
    two suites' collection order together for two lines of constructor."""
    return Cassette(name=name, source="unit", recorded_at="2026-08-02T00:00:00Z",
                    interactions=list(interactions))


def _resp(url, body, *, status=200, headers=None, method="GET"):
    return Interaction(method=method, url=url, status=status, body=body,
                       headers=headers or {})


# ---------------------------------------------------------------------------
# the three that now retry
# ---------------------------------------------------------------------------

class TestWeWorkRemotelyFetchRetries(unittest.TestCase):
    """`fetch_feed`. Before D31's disposition, one 503 lost one category for
    the day -- `lib/http.py:3-5` names that exact scenario as why it exists."""

    @classmethod
    def setUpClass(cls):
        cls.wwr = load_ingest("weworkremotely")

    def _feed_url(self, category):
        return self.wwr.FEED_URL_TEMPLATE.format(category=category)

    FEED = ('<?xml version="1.0" encoding="UTF-8"?>\n'
            '<rss version="2.0"><channel><item>'
            '<title>Company: Backend Engineer</title>'
            '<link>https://weworkremotely.com/remote-jobs/x</link>'
            '</item></channel></rss>')

    def test_a_transient_429_costs_a_retry_and_not_the_category(self):
        cat = self.wwr.CATEGORIES[0]
        url = self._feed_url(cat)
        cas = _cassette(_resp(url, "slow down", status=429,
                              headers={"Retry-After": "1"}),
                        _resp(url, self.FEED))
        with cassettes.no_sleep(), cassettes.replay(cassette=cas) as player:
            with redirect_stderr(io.StringIO()):
                raw = self.wwr.fetch_feed(cat)
        self.assertEqual(len(player.requests), 2,
                         "the 429 must have been retried, not surfaced")
        self.assertIn(b"Backend Engineer", raw)

    def test_the_feed_is_bytes_and_ElementTree_will_parse_it(self):
        """The reason `lib.http.get_bytes` exists at all.

        Every WWR feed opens with an XML declaration naming its encoding, and
        `ET.fromstring` raises ValueError("Unicode strings with encoding
        declaration are not supported") when handed that as a str. A future
        edit swapping this call for `get_text` would parse nothing, and
        `parse_feed` would report a feed with no items rather than an error --
        silence, which is this system's failure mode.
        """
        cat = self.wwr.CATEGORIES[0]
        with cassettes.replay(cassette=_cassette(
                _resp(self._feed_url(cat), self.FEED))):
            raw = self.wwr.fetch_feed(cat)
        self.assertIsInstance(raw, bytes)
        self.assertEqual(
            [e.findtext("title") for e in ET.fromstring(raw).iter("item")],
            ["Company: Backend Engineer"])

    def test_a_permanent_404_is_still_exactly_one_request(self):
        """The migration must not turn a dead feed URL into five dead ones.
        `lib/http.py:76-77` is the distinction the module was written to make."""
        cat = self.wwr.CATEGORIES[0]
        cas = _cassette(_resp(self._feed_url(cat), "gone", status=404))
        with cassettes.no_sleep(), cassettes.replay(cassette=cas) as player:
            with redirect_stderr(io.StringIO()):
                with self.assertRaises(urllib.error.HTTPError) as caught:
                    self.wwr.fetch_feed(cat)
        self.assertEqual(caught.exception.code, 404)
        self.assertEqual(len(player.requests), 1,
                         "a 404 is permanent; retrying it burns wall-clock "
                         "with no possibility of succeeding")


class TestBuiltInListingPageRetries(unittest.TestCase):
    """`fetch_page`, the listing half. Contrast the detail half below."""

    @classmethod
    def setUpClass(cls):
        cls.builtin = load_ingest("builtin-nyc")

    def test_a_transient_503_costs_a_retry_and_not_the_page(self):
        url = f"{self.builtin.BASE_URL}?page=1"
        cas = _cassette(_resp(url, "upstream is unwell", status=503),
                        _resp(url, "<html>page 1</html>"))
        with cassettes.no_sleep(), cassettes.replay(cassette=cas) as player:
            with redirect_stderr(io.StringIO()):
                html = self.builtin.fetch_page(1)
        self.assertEqual(len(player.requests), 2)
        self.assertEqual(html, "<html>page 1</html>")

    def test_the_browser_user_agent_survived_the_migration(self):
        """`lib.http` has its own honest default UA; Built In is a scraped
        site and the committed cassettes were recorded under this one."""
        url = f"{self.builtin.BASE_URL}?page=1"
        seen = {}

        def spy(req, timeout=None, **_):
            seen["ua"] = req.get_header("User-agent")
            raise urllib.error.HTTPError(url, 404, "gone", {}, None)

        with mock.patch("urllib.request.urlopen", spy):
            with redirect_stderr(io.StringIO()):
                with self.assertRaises(urllib.error.HTTPError):
                    self.builtin.fetch_page(1)
        self.assertEqual(seen["ua"], self.builtin.USER_AGENT)


class TestSerpApiSearchRetries(unittest.TestCase):
    """`serpapi_search`. The query bank runs ~8 searches a day, so a query
    lost to a transient 429 is a day of coverage for that slug."""

    @classmethod
    def setUpClass(cls):
        cls.serp = load_ingest("google-serpapi")

    KEY = "sk-live-abcdef0123456789"

    def _url(self):
        """The url the player matches on, scrubbed the way a recording would
        be. `api_key` is a SECRET_PARAM, so the stored key carries REDACTED
        and a rotated key still finds its cassette -- which is the property
        `evals/cassettes.py` § THE KEY IS SCRUBBED exists to give."""
        import urllib.parse
        params = {"engine": "google_jobs", "q": "ai engineer",
                  "location": "New York", "hl": "en", "gl": "us",
                  "api_key": self.KEY}
        return cassettes.scrub_url("https://serpapi.com/search.json?"
                                   + urllib.parse.urlencode(params))

    def test_a_429_with_retry_after_is_retried(self):
        url = self._url()
        cas = _cassette(_resp(url, "rate limited", status=429,
                              headers={"Retry-After": "1"}),
                        _resp(url, '{"jobs_results": [{"title": "AI Engineer"}]}'))
        with mock.patch.object(self.serp, "SERPAPI_API_KEY", self.KEY):
            with cassettes.no_sleep(), cassettes.replay(cassette=cas) as player:
                with redirect_stderr(io.StringIO()):
                    results = self.serp.serpapi_search("ai engineer", "New York")
        self.assertEqual(len(player.requests), 2)
        self.assertEqual([r["title"] for r in results], ["AI Engineer"])

    def test_the_retry_log_cannot_leak_the_api_key(self):
        """The key travels in the query string, and going through `lib.http`
        is what put a logger anywhere near it. `lib/http.py:59` tags each
        retry with `url.split("?")[0]`; `docs/ingest/google-serpapi.md` raised
        this as an open question while the script still used raw urlopen.
        """
        url = self._url()
        cas = _cassette(_resp(url, "rate limited", status=429),
                        _resp(url, '{"jobs_results": []}'))
        err = io.StringIO()
        with mock.patch.object(self.serp, "SERPAPI_API_KEY", self.KEY):
            with cassettes.no_sleep(), cassettes.replay(cassette=cas):
                with redirect_stderr(err):
                    self.serp.serpapi_search("ai engineer", "New York")
        self.assertIn("[retry]", err.getvalue(),
                      "this test is vacuous unless a retry line was printed")
        self.assertNotIn(self.KEY, err.getvalue())
        self.assertNotIn("api_key", err.getvalue())

    def test_a_200_carrying_an_error_key_is_not_retried(self):
        """SerpApi signals most failures with HTTP 200 and an `error` body,
        and most of those are permanent -- a bad key, or an exhausted monthly
        allowance. Handing them to `body_is_transient` would retry a metered
        account's way through five of them."""
        url = self._url()
        cas = _cassette(_resp(url, '{"error": "Invalid API key"}'))
        with mock.patch.object(self.serp, "SERPAPI_API_KEY", self.KEY):
            with cassettes.no_sleep(), cassettes.replay(cassette=cas) as player:
                with self.assertRaises(RuntimeError):
                    self.serp.serpapi_search("ai engineer", "New York")

    def test_a_200_saying_no_results_is_an_answer_not_a_failure(self):
        """OQ-15, decided 2026-08-03. Before the fix, ANY `error` key raised --
        including SerpApi's "found nothing" wording, which is an answer, not a
        failure. The caller (main()) treats a raise as a query failure: it
        releases the claim so the query is retried immediately, and
        last_success_at never advances, even though the query had, in fact,
        just succeeded with zero results."""
        url = self._url()
        cas = _cassette(_resp(
            url, '{"error": "Google hasn\'t returned any results for this query."}'))
        with mock.patch.object(self.serp, "SERPAPI_API_KEY", self.KEY):
            with cassettes.no_sleep(), cassettes.replay(cassette=cas):
                results = self.serp.serpapi_search("ai engineer", "New York")
        self.assertEqual(results, [])


# ---------------------------------------------------------------------------
# the one that deliberately does not
# ---------------------------------------------------------------------------

class TestBuiltInDetailFetchDoesNotRetry(unittest.TestCase):
    """D31's deliberate quarter, pinned.

    `builtin-nyc.fetch_description` is the only raw `urlopen` left in
    `ingest/` and must stay that way. Its RateLimited docstring is the whole
    argument: "Collapsing this into 'no description, try the next one' is what
    turns a polite scraper into a rude one." `lib.http` would retry a 429 five
    times with backoff, which is that, with a schedule.

    These two pass against the pre-migration tree as well. That is the point.
    """

    @classmethod
    def setUpClass(cls):
        cls.builtin = load_ingest("builtin-nyc")

    URL = "https://www.builtinnyc.com/job/engineer/1"

    def test_a_429_raises_RateLimited_on_the_first_one(self):
        cas = _cassette(_resp(self.URL, "slow down", status=429,
                              headers={"Retry-After": "1"}))
        with cassettes.no_sleep(), cassettes.replay(cassette=cas) as player:
            with redirect_stderr(io.StringIO()):
                with self.assertRaises(self.builtin.RateLimited):
                    self.builtin.fetch_description(self.URL)
        self.assertEqual(
            len(player.requests), 1,
            "a 429 must end the pass, not schedule four more requests at a "
            "host that already said no -- see fetch_description's docstring")

    def test_a_transient_5xx_costs_one_posting_and_one_request(self):
        """The deferral, not a retry: None leaves the row eligible next run,
        which is the same shape score.py uses for a transient LLM failure."""
        cas = _cassette(_resp(self.URL, "unwell", status=503))
        with cassettes.no_sleep(), cassettes.replay(cassette=cas) as player:
            with redirect_stderr(io.StringIO()):
                self.assertIsNone(self.builtin.fetch_description(self.URL))
        self.assertEqual(len(player.requests), 1)


if __name__ == "__main__":
    unittest.main()

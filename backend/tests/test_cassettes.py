"""evals/cassettes.py: the record/replay harness itself.

WHAT THIS PINS, AND WHY EACH ONE

  * The seam is `urllib.request.urlopen`, not `lib.http.get_text`. Four of
    the six ingest scripts build their own Request and call urllib directly
    (weworkremotely.py:124, google-serpapi.py:280, builtin-nyc.py:182 and
    :241) so that they can send a browser-ish User-Agent lib/http.py has no
    parameter for. A harness hooked into lib/http.py would replay two
    sources and silently make live calls for the other four.

  * A miss is fatal. Falling through to the network on an unrecorded
    request is how a replayed test quietly becomes a live test again.

  * No credential reaches disk and no credential is part of the key.
    Rotating SERPAPI_API_KEY must not invalidate the recorded corpus --
    `evals/cache.py:31-36` made the same choice for the LLM half and this is
    the same rule one layer down.

  * No cassette carries a duration. A replayed response has the latency of a
    call made months ago; `Player.wall_clock` raises rather than answering.

No network: every test here builds its cassette in memory or reads a
committed one.
"""

import json
import os
import sys
import unittest
import urllib.error
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from evals import cassettes                                   # noqa: E402
from evals.cassettes import (Cassette, CassetteMiss,          # noqa: E402
                             Interaction, Player)


def _cassette(*interactions, name="unit"):
    return Cassette(name=name, source="unit", recorded_at="2026-07-28T00:00:00Z",
                    interactions=list(interactions))


def _ok(url, body, *, method="GET", status=200, **kw):
    return Interaction(method=method, url=url, status=status, body=body, **kw)


class TestTheSeam(unittest.TestCase):
    """Both ways this pipeline makes an HTTP request go through the cassette."""

    def test_lib_http_is_replayed(self):
        from lib import http
        with cassettes.replay(cassette=_cassette(
                _ok("https://example.test/j.json", '{"jobs": [1, 2]}'))):
            self.assertEqual(http.get_json("https://example.test/j.json"),
                             {"jobs": [1, 2]})

    def test_a_bare_urlopen_is_replayed_too(self):
        """The shape weworkremotely.py:123-125 and builtin-nyc.py:181-183 use:
        a hand-built Request with their own User-Agent, opened directly."""
        with cassettes.replay(cassette=_cassette(
                _ok("https://example.test/feed.rss", "<rss/>"))):
            req = urllib.request.Request("https://example.test/feed.rss",
                                         headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=5) as resp:
                self.assertEqual(resp.read(), b"<rss/>")
                self.assertEqual(resp.status, 200)

    def test_urlopen_is_restored_afterwards(self):
        real = urllib.request.urlopen
        with cassettes.replay(cassette=_cassette()):
            self.assertIsNot(urllib.request.urlopen, real)
        self.assertIs(urllib.request.urlopen, real)


class TestAMissIsFatal(unittest.TestCase):

    def test_unrecorded_request_raises_rather_than_fetching(self):
        with cassettes.replay(cassette=_cassette(
                _ok("https://example.test/a", "{}"))) as player:
            with self.assertRaises(CassetteMiss) as caught:
                urllib.request.urlopen("https://example.test/b")
        self.assertIn("https://example.test/a", str(caught.exception),
                      "the miss must say what the cassette DOES hold")
        self.assertEqual(player.requests, [("GET", "https://example.test/b")])

    def test_an_empty_cassette_misses_everything(self):
        with cassettes.replay(cassette=_cassette()):
            with self.assertRaises(CassetteMiss):
                urllib.request.urlopen("https://example.test/anything")


class TestOrderingAndBodies(unittest.TestCase):
    """Pagination, in both shapes this pipeline paginates in."""

    def test_same_url_twice_replays_in_recorded_order(self):
        """builtin-nyc.py pages with ?page=N, but hn-hiring.py and the ATS
        fetchers can ask the same url twice within one retry loop."""
        with cassettes.replay(cassette=_cassette(
                _ok("https://example.test/p", "first"),
                _ok("https://example.test/p", "second"))):
            first = urllib.request.urlopen("https://example.test/p").read()
            second = urllib.request.urlopen("https://example.test/p").read()
        self.assertEqual((first, second), (b"first", b"second"))

    def test_a_third_ask_replays_the_last_response(self):
        """A retry asking again for a page it already has is asking a question
        the cassette has answered; missing there would fail the retry test
        rather than the behaviour under test."""
        with cassettes.replay(cassette=_cassette(
                _ok("https://example.test/p", "only"))):
            for _ in range(3):
                self.assertEqual(
                    urllib.request.urlopen("https://example.test/p").read(),
                    b"only")

    def test_a_post_is_keyed_on_its_body(self):
        """Workday paginates by POST body, not by url -- the same endpoint
        answers 'everything' or 'nothing' depending on `limit`."""
        import hashlib
        small, big = b'{"limit": 20}', b'{"limit": 100}'
        cas = _cassette(
            _ok("https://example.test/jobs", '{"n": 20}', method="POST",
                request_body_sha256=hashlib.sha256(small).hexdigest()),
            _ok("https://example.test/jobs", '{"n": 0}', method="POST",
                request_body_sha256=hashlib.sha256(big).hexdigest()))
        with cassettes.replay(cassette=cas):
            def post(payload):
                req = urllib.request.Request("https://example.test/jobs",
                                             data=payload, method="POST")
                return json.loads(urllib.request.urlopen(req).read())
            self.assertEqual(post(small), {"n": 20})
            self.assertEqual(post(big), {"n": 0})


class TestErrorResponses(unittest.TestCase):

    def test_a_recorded_4xx_raises_HTTPError(self):
        with cassettes.replay(cassette=_cassette(
                _ok("https://example.test/x", "nope", status=404))):
            with self.assertRaises(urllib.error.HTTPError) as caught:
                urllib.request.urlopen("https://example.test/x")
        self.assertEqual(caught.exception.code, 404)
        self.assertEqual(caught.exception.read(), b"nope")

    def test_a_429_carries_retry_after_into_lib_http_backoff(self):
        """lib/http.py:78 reads Retry-After off the HTTPError's headers. If a
        replayed error did not carry headers, the retry path would be
        exercised in a shape it never takes in production."""
        from lib import http
        cas = _cassette(
            _ok("https://example.test/r", "slow down", status=429,
                headers={"Retry-After": "1"}),
            _ok("https://example.test/r", '{"ok": true}'))
        with cassettes.no_sleep(), cassettes.replay(cassette=cas):
            self.assertEqual(http.get_json("https://example.test/r"),
                             {"ok": True})


class TestNoCredentialReachesDiskOrTheKey(unittest.TestCase):

    def test_secret_query_parameters_are_scrubbed(self):
        self.assertEqual(
            cassettes.scrub_url("https://serpapi.com/s?q=ai&api_key=sk-abc123"),
            "https://serpapi.com/s?q=ai&api_key=REDACTED")
        self.assertEqual(
            cassettes.scrub_url("https://api.apify.com/v2/x?token=apify_tok"),
            "https://api.apify.com/v2/x?token=REDACTED")

    def test_non_secret_parameters_survive_untouched(self):
        """The scrubber must not normalise the url: it is the lookup key, and
        two callers spelling the same request differently would not match."""
        url = "https://serpapi.com/s?engine=google_jobs&q=AI+engineer&hl=en"
        self.assertEqual(cassettes.scrub_url(url), url)

    def test_the_key_survives_a_credential_rotation(self):
        """The property `evals/cache.py:35` states for the LLM cache, here."""
        cas = _cassette(_ok("https://serpapi.com/s?q=ai&api_key=REDACTED", "{}"))
        with cassettes.replay(cassette=cas):
            for key in ("old-key-11111", "new-key-22222"):
                self.assertEqual(
                    urllib.request.urlopen(
                        f"https://serpapi.com/s?q=ai&api_key={key}").read(),
                    b"{}")

    def test_secret_env_values_are_scrubbed_out_of_recorded_bytes(self):
        env = {"SOME_API_TOKEN": "tok_abcdefghijklmnop", "HOME": "/home/eric"}
        secrets = cassettes.secret_values(env)
        self.assertEqual(secrets, ["tok_abcdefghijklmnop"])
        self.assertEqual(
            cassettes.scrub_text('{"input": {"token": "tok_abcdefghijklmnop"}}',
                                 secrets),
            '{"input": {"token": "REDACTED"}}')

    def test_no_committed_cassette_contains_a_secret_shaped_env_value(self):
        secrets = cassettes.secret_values()
        if not secrets:
            self.skipTest("no secrets in this environment to look for")
        for name in cassettes.names():
            with self.subTest(cassette=name):
                with open(Cassette.path_for(name), encoding="utf-8") as fh:
                    blob = fh.read()
                for secret in secrets:
                    self.assertNotIn(secret, blob)


class TestTimingIsNeverReplayed(unittest.TestCase):
    """Restated from the evals harness rather than rediscovered.

    `docs/ingestion_tests/README.md:80-84`: a replayed response carries the
    latency of a call made months ago, so the rule is enforced where the
    number would be read.
    """

    def test_wall_clock_raises_instead_of_answering(self):
        player = Player(_cassette())
        with self.assertRaises(RuntimeError) as caught:
            player.wall_clock
        self.assertIn("never reported from replay", str(caught.exception))

    def test_no_committed_cassette_stores_a_duration_or_a_cost(self):
        for name in cassettes.names():
            with self.subTest(cassette=name):
                with open(Cassette.path_for(name), encoding="utf-8") as fh:
                    blob = fh.read()
                for key in cassettes.FORBIDDEN_KEYS:
                    self.assertNotIn(f'"{key}"', blob)


class TestProvenance(unittest.TestCase):
    """A fixture recorded in July must not silently become December's spec."""

    def test_every_committed_cassette_says_when_it_was_recorded(self):
        found = cassettes.names()
        self.assertTrue(found, "no cassettes committed at all")
        for name in found:
            with self.subTest(cassette=name):
                cas = Cassette.load(name)
                self.assertTrue(cas.recorded_at,
                                f"{name} has no recorded_at")
                self.assertTrue(cas.source, f"{name} does not say what it hit")
                self.assertTrue(cas.note, f"{name} does not say what it is for")

    def test_provenance_line_carries_the_date_and_the_age(self):
        cas = _cassette(_ok("https://example.test/a", "{}"))
        line = cas.provenance_line()
        self.assertIn("2026-07-28", line)
        self.assertIn("1 interaction", line)
        self.assertIsNotNone(cas.age_days())

    def test_a_cassette_with_no_date_still_renders(self):
        cas = Cassette("x", interactions=[])
        self.assertIsNone(cas.age_days())
        self.assertIn("unrecorded date", cas.provenance_line())


class TestRoundTrip(unittest.TestCase):

    def test_bytes_that_are_not_utf8_survive_exactly(self):
        raw = b"\xff\xfe<not utf-8>"
        body, b64 = cassettes._body_fields(raw)
        self.assertIsNone(body)
        self.assertEqual(Interaction(method="GET", url="u", status=200,
                                     body_b64=b64).raw, raw)

    def test_save_and_load_preserve_every_field(self, ):
        import tempfile
        cas = _cassette(_ok("https://example.test/a", "hello",
                            headers={"Content-Type": "text/plain"}),
                        name="roundtrip")
        cas.source, cas.note = "example.test", "a note"
        with tempfile.TemporaryDirectory() as tmp:
            cas.save(tmp)
            back = Cassette.load("roundtrip", tmp)
        self.assertEqual(back.source, "example.test")
        self.assertEqual(back.note, "a note")
        self.assertEqual(back.recorded_at, cas.recorded_at)
        self.assertEqual(back.interactions[0].raw, b"hello")
        self.assertEqual(back.interactions[0].headers,
                         {"Content-Type": "text/plain"})

    def test_a_missing_cassette_names_how_to_record_it(self):
        with self.assertRaises(cassettes.CassetteError) as caught:
            Cassette.load("no-such-cassette")
        self.assertIn("record_cassettes.py", str(caught.exception))


if __name__ == "__main__":
    unittest.main()

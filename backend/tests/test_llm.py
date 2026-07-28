"""Tests for llm.py -- JSON extraction and transient-failure classification.

Split out of the shared library's test_text_llm.py when llm.py moved into
jobs/: it had one consumer pipeline, so it went to live with it. The text.py
half of that file is now tests/test_lib_text.py in this repo.
"""

import json
import unittest
import urllib.request

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import llm  # noqa: E402  (llm.py)


class _FakeResp:
    """Minimal stand-in for urlopen's context-manager response."""

    def __init__(self, body):
        self._body = body

    def read(self):
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class TestLlmParsing(unittest.TestCase):
    def test_plain_json(self):
        self.assertEqual(llm.parse_json('{"fit_score": 7}'), {"fit_score": 7})

    def test_fenced_json(self):
        self.assertEqual(llm.parse_json('```json\n{"a": 1}\n```'), {"a": 1})

    def test_surrounded_by_chatter(self):
        self.assertEqual(
            llm.parse_json('Sure! Here is the result:\n{"a": 1}\nHope that helps.'),
            {"a": 1})

    def test_unparseable_returns_none(self):
        for bad in ("no json here", "", "{ broken", "}{"):
            self.assertIsNone(llm.parse_json(bad), repr(bad))

    def test_has_fields(self):
        self.assertTrue(llm.has_fields({"a": 1, "b": 2}, ("a", "b")))
        self.assertFalse(llm.has_fields({"a": 1}, ("a", "b")))
        self.assertFalse(llm.has_fields(None, ("a",)))
        self.assertFalse(llm.has_fields("not a dict", ("a",)))

    def test_failed_label_is_prefixed(self):
        self.assertTrue(llm.failed_label("m").startswith(llm.FAILED_PREFIX))




class TestPerCallOverrides(unittest.TestCase):
    """call_detailed()'s overrides must reach the wire without touching env.

    These exist so evaluation tooling can point at a second model in-process.
    The failure they guard against is subtle: before the overrides, tools that
    wanted a different model rebuilt the HTTP request by hand, which silently
    dropped ratelimit.acquire() and let a sweep spend the nightly run's quota.
    A regression here would push them back to doing that.
    """

    #: JOB_SCORING_* take priority over LLM_* in base_url()/model()/api_key()
    #: (see llm.py), so isolating only the LLM_* names left this suite at the
    #: mercy of whatever the ambient environment set -- in particular
    #: backend/.env's JOB_SCORING_BASE_URL/JOB_SCORING_MODEL, which point at
    #: the real production endpoint. A shell that has sourced .env made
    #: test_defaults_read_environment assert against the wrong URL. Every
    #: name base_url()/model()/api_key() consult must be cleared here.
    _ISOLATED_VARS = ("LLM_API_KEY", "LLM_BASE_URL", "LLM_MODEL",
                      "JOB_SCORING_API_KEY", "JOB_SCORING_BASE_URL",
                      "JOB_SCORING_MODEL")

    def setUp(self):
        self.captured = {}
        self.real = urllib.request.urlopen
        urllib.request.urlopen = self._fake
        self.env = {k: os.environ.get(k) for k in self._ISOLATED_VARS}
        for k in self._ISOLATED_VARS:
            os.environ.pop(k, None)
        os.environ["LLM_API_KEY"] = "envkey"
        os.environ["LLM_BASE_URL"] = "https://env.example/v1"

    def tearDown(self):
        urllib.request.urlopen = self.real
        for k, v in self.env.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v

    def _fake(self, req, timeout=None):
        self.captured = {"url": req.full_url,
                         "auth": req.get_header("Authorization"),
                         "body": json.loads(req.data.decode())}
        return _FakeResp(json.dumps({
            "choices": [{"message": {"content": '{"fit_score": 71}'}}],
            "usage": {"prompt_tokens": 1060, "completion_tokens": 240},
        }).encode())

    def test_defaults_read_environment(self):
        self.assertEqual(llm.call("hi"), '{"fit_score": 71}')
        self.assertEqual(self.captured["url"],
                         "https://env.example/v1/chat/completions")
        self.assertEqual(self.captured["auth"], "Bearer envkey")

    def test_overrides_do_not_mutate_environment(self):
        llm.call_detailed("hi", model="deepseek-v4-flash",
                          base_url="https://api.deepseek.com/v1",
                          api_key="sk-test")
        self.assertEqual(self.captured["url"],
                         "https://api.deepseek.com/v1/chat/completions")
        self.assertEqual(self.captured["auth"], "Bearer sk-test")
        self.assertEqual(self.captured["body"]["model"], "deepseek-v4-flash")
        # The whole point: a second model in-process leaves the first alone.
        self.assertEqual(os.environ["LLM_API_KEY"], "envkey")
        self.assertEqual(os.environ["LLM_BASE_URL"], "https://env.example/v1")

    def test_base_url_trailing_slash_does_not_double(self):
        llm.call_detailed("hi", base_url="https://x.example/v1/", api_key="k")
        self.assertEqual(self.captured["url"],
                         "https://x.example/v1/chat/completions")

    def test_completion_carries_usage_and_model(self):
        c = llm.call_detailed("hi", model="m", api_key="k")
        self.assertEqual(c.text, '{"fit_score": 71}')
        self.assertEqual(c.model, "m")
        self.assertEqual(c.usage["prompt_tokens"], 1060)
        self.assertGreaterEqual(c.latency_s, 0)
        # No OpenAI-compatible provider reports per-call cost; only the
        # claude CLI envelope does. Guessing one here would be a fiction that
        # eval/metrics.py would then report as measured.
        self.assertIsNone(c.cost_usd)

    def test_temperature_still_pinned_to_zero(self):
        # Sampling turns a ranking into a lottery -- see llm.py's note.
        llm.call_detailed("hi", model="m", api_key="k")
        self.assertEqual(self.captured["body"]["temperature"],
                         llm.DEFAULT_TEMPERATURE)


class TestDefaultModel(unittest.TestCase):
    def test_default_model_is_the_documented_production_model(self):
        # Every downstream calibration figure (docs/SCORING.md's cost table,
        # docs/ingestion_tests/README.md's self-consistency numbers) names
        # deepseek-v4-flash specifically. A silent drift here invalidates
        # them without anything else noticing -- see llm.py's module comment.
        self.assertEqual(llm.DEFAULT_MODEL, "deepseek-v4-flash")


class TestModelMismatch(unittest.TestCase):
    """extract.py/score.py's startup pin -- see llm.model_mismatch()."""

    _VARS = ("JOBS_EXPECTED_MODEL", "JOB_SCORING_MODEL", "LLM_MODEL")

    def setUp(self):
        self.env = {k: os.environ.get(k) for k in self._VARS}
        for k in self._VARS:
            os.environ.pop(k, None)

    def tearDown(self):
        for k, v in self.env.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v

    def test_unset_pin_is_a_noop(self):
        self.assertIsNone(llm.model_mismatch())

    def test_pin_matching_the_resolved_model_passes(self):
        os.environ["JOBS_EXPECTED_MODEL"] = llm.DEFAULT_MODEL
        self.assertIsNone(llm.model_mismatch())

    def test_pin_disagreeing_with_the_resolved_model_fails(self):
        os.environ["JOB_SCORING_MODEL"] = "deepseek-v4-flash"
        os.environ["JOBS_EXPECTED_MODEL"] = "glm-4.5-flash"
        mismatch = llm.model_mismatch()
        self.assertIsNotNone(mismatch)
        self.assertIn("deepseek-v4-flash", mismatch)
        self.assertIn("glm-4.5-flash", mismatch)


class TestTransientClassification(unittest.TestCase):
    """A transient failure must never look like a permanent one.

    score.py tombstones a job it cannot score so it is not retried forever.
    That is right for "the model returned garbage" and badly wrong for "HTTP
    429" -- the latter says nothing about the job, so recording it discards a
    posting that was never actually evaluated. These pin which is which.
    """

    def _call_raising(self, exc):
        """Run llm.call with urlopen replaced by something that raises."""
        import urllib.request
        real = urllib.request.urlopen
        urllib.request.urlopen = lambda *a, **k: (_ for _ in ()).throw(exc)
        try:
            return llm.call("prompt")
        finally:
            urllib.request.urlopen = real

    def _http_error(self, code):
        import urllib.error, io
        return urllib.error.HTTPError("http://x", code, "err", {},
                                      io.BytesIO(b"body"))

    def test_rate_limit_is_transient(self):
        with self.assertRaises(llm.TransientError):
            self._call_raising(self._http_error(429))

    def test_server_errors_are_transient(self):
        for code in (500, 502, 503, 504):
            with self.assertRaises(llm.TransientError, msg=f"HTTP {code}"):
                self._call_raising(self._http_error(code))

    def test_client_errors_are_permanent(self):
        # 400/401/404 are the endpoint's final answer -- retrying cannot help.
        for code in (400, 401, 403, 404):
            with self.assertRaises(RuntimeError, msg=f"HTTP {code}") as cm:
                self._call_raising(self._http_error(code))
            self.assertNotIsInstance(cm.exception, llm.TransientError,
                                     f"HTTP {code} must not be transient")

    def test_timeout_is_transient(self):
        with self.assertRaises(llm.TransientError):
            self._call_raising(TimeoutError("timed out"))

    def test_connection_error_is_transient(self):
        import urllib.error
        with self.assertRaises(llm.TransientError):
            self._call_raising(urllib.error.URLError("refused"))

    def test_transient_is_a_runtimeerror(self):
        # Callers that only catch RuntimeError must still not crash.
        self.assertTrue(issubclass(llm.TransientError, RuntimeError))


if __name__ == "__main__":
    unittest.main()

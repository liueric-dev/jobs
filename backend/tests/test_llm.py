"""Tests for llm.py -- JSON extraction and transient-failure classification.

Split out of the shared library's test_text_llm.py when llm.py moved into
jobs/: it had one consumer pipeline, so it went to live with it. The text.py
half of that file is now tests/test_lib_text.py in this repo.
"""

import unittest

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import llm  # noqa: E402  (llm.py)


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

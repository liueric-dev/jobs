"""Tests for client-side free-tier budget enforcement.

The behaviour that actually matters here is the daily cap: getting it wrong
either wastes budget or -- much worse -- lets a spent budget be recorded as a
judgement about a job. So these pin the cap arithmetic, the cross-process
persistence, and the reset boundary, plus the RPM spacing.
"""

import os
import tempfile
import threading
import time
import unittest

import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))))

from pipelib import ratelimit  # noqa: E402

MODEL = "gemini-3.6-flash"

#: Env this module reads. Cleared between tests so a stray value from the
#: developer's shell can't make a test pass that would fail in CI.
_ENV = ("LLM_MAX_RPM", "LLM_MAX_RPD", "LLM_QUOTA_STATE", "LLM_QUOTA_TZ",
        ratelimit._env_key("LLM_MAX_RPD", MODEL),
        ratelimit._env_key("LLM_MAX_RPM", MODEL))


class RateLimitCase(unittest.TestCase):
    def setUp(self):
        self._saved = {k: os.environ.pop(k, None) for k in _ENV}
        self._tmp = tempfile.NamedTemporaryFile(suffix=".json", delete=False)
        self._tmp.close()
        os.unlink(self._tmp.name)       # want the path, not the file
        os.environ["LLM_QUOTA_STATE"] = self._tmp.name
        ratelimit._last_call.clear()

    def tearDown(self):
        for k, v in self._saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        if os.path.exists(self._tmp.name):
            os.unlink(self._tmp.name)


class TestUncapped(RateLimitCase):
    def test_no_limits_is_a_noop(self):
        """Unset budgets must not touch the clock or the disk."""
        start = time.monotonic()
        for _ in range(50):
            ratelimit.acquire(MODEL)
        self.assertLess(time.monotonic() - start, 0.5)
        self.assertFalse(os.path.exists(self._tmp.name))

    def test_remaining_is_none_when_uncapped(self):
        self.assertIsNone(ratelimit.remaining_today(MODEL))


class TestDailyCap(RateLimitCase):
    def test_cap_allows_exactly_n_then_raises(self):
        os.environ["LLM_MAX_RPD"] = "3"
        for _ in range(3):
            ratelimit.acquire(MODEL)
        with self.assertRaises(ratelimit.QuotaExhausted):
            ratelimit.acquire(MODEL)

    def test_remaining_counts_down(self):
        os.environ["LLM_MAX_RPD"] = "3"
        self.assertEqual(ratelimit.remaining_today(MODEL), 3)
        ratelimit.acquire(MODEL)
        self.assertEqual(ratelimit.remaining_today(MODEL), 2)

    def test_budget_survives_a_fresh_process(self):
        """The whole point of the state file: an hourly cron must not get a
        fresh daily budget every hour."""
        os.environ["LLM_MAX_RPD"] = "2"
        ratelimit.acquire(MODEL)
        ratelimit._last_call.clear()        # simulate a new process
        ratelimit.acquire(MODEL)
        with self.assertRaises(ratelimit.QuotaExhausted):
            ratelimit.acquire(MODEL)

    def test_new_day_resets_the_budget(self):
        os.environ["LLM_MAX_RPD"] = "1"
        ratelimit.acquire(MODEL)
        state = ratelimit._read_state()
        state["date"] = "1999-01-01"        # backdate: yesterday's spend
        ratelimit._write_state(state)
        ratelimit.acquire(MODEL)            # must not raise

    def test_budgets_are_per_model(self):
        """Free tiers meter per model, so one model's spend must not consume
        another's -- this is what makes pooling models viable."""
        os.environ["LLM_MAX_RPD"] = "1"
        ratelimit.acquire(MODEL)
        ratelimit.acquire("gemini-3.5-flash-lite")   # separate budget
        with self.assertRaises(ratelimit.QuotaExhausted):
            ratelimit.acquire(MODEL)

    def test_per_model_override_beats_the_bare_name(self):
        os.environ["LLM_MAX_RPD"] = "1"
        os.environ[ratelimit._env_key("LLM_MAX_RPD", MODEL)] = "3"
        for _ in range(3):
            ratelimit.acquire(MODEL)
        with self.assertRaises(ratelimit.QuotaExhausted):
            ratelimit.acquire(MODEL)

    def test_cap_holds_under_concurrency(self):
        """score.py calls this from a ThreadPoolExecutor."""
        os.environ["LLM_MAX_RPD"] = "5"
        allowed, denied = [], []

        def worker():
            try:
                ratelimit.acquire(MODEL)
                allowed.append(1)
            except ratelimit.QuotaExhausted:
                denied.append(1)

        threads = [threading.Thread(target=worker) for _ in range(20)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        self.assertEqual(len(allowed), 5)
        self.assertEqual(len(denied), 15)


class TestPerMinuteSpacing(RateLimitCase):
    def test_calls_are_spaced_not_bursted(self):
        os.environ["LLM_MAX_RPM"] = "120"       # 0.5s apart
        ratelimit.acquire(MODEL)
        start = time.monotonic()
        ratelimit.acquire(MODEL)
        self.assertGreaterEqual(time.monotonic() - start, 0.4)

    def test_first_call_is_immediate(self):
        os.environ["LLM_MAX_RPM"] = "6"         # 10s apart
        start = time.monotonic()
        ratelimit.acquire(MODEL)
        self.assertLess(time.monotonic() - start, 0.5)


class TestResilience(RateLimitCase):
    def test_corrupt_state_file_does_not_crash(self):
        """A truncated budget file is cosmetic; refusing to run is not."""
        os.environ["LLM_MAX_RPD"] = "2"
        with open(self._tmp.name, "w") as f:
            f.write("{not json")
        ratelimit.acquire(MODEL)

    def test_unknown_timezone_falls_back_to_utc(self):
        os.environ["LLM_MAX_RPD"] = "2"
        os.environ["LLM_QUOTA_TZ"] = "Mars/Olympus_Mons"
        ratelimit.acquire(MODEL)


if __name__ == "__main__":
    unittest.main()

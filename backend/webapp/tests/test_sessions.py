"""Session token handling and the cursor encoding.

The property under test is that the cookie value is never what the database
stores -- the same guarantee api_keys gives, so that a database dump yields no
working credential.
"""

import base64
import hashlib
import json
import os
import sys
import unittest
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import auth  # noqa: E402
import jobs  # noqa: E402


class TestSessionToken(unittest.TestCase):

    def test_stored_value_is_the_hash_not_the_token(self):
        token = "a-session-cookie-value"
        stored = auth._hash(token)
        self.assertNotIn(token, stored)
        self.assertEqual(stored, hashlib.sha256(token.encode()).hexdigest())
        self.assertEqual(len(stored), 64)

    def test_hash_is_stable_and_distinct(self):
        self.assertEqual(auth._hash("x"), auth._hash("x"))
        self.assertNotEqual(auth._hash("x"), auth._hash("y"))

    def test_timestamps_round_trip(self):
        # Sliding expiry compares a stored TEXT stamp against now, so the
        # format has to survive the round trip exactly.
        now = datetime.now(timezone.utc).replace(microsecond=0)
        self.assertEqual(auth._parse(auth._stamp(now)), now)

    def test_stamp_format_matches_the_pipeline(self):
        stamped = auth._stamp(datetime(2026, 7, 26, 9, 5, 3, tzinfo=timezone.utc))
        self.assertEqual(stamped, "2026-07-26T09:05:03")
        # Fixed width, so string comparison is chronological comparison --
        # which is what every expires_at check in this service relies on.
        self.assertLess("2026-07-26T09:05:03", "2026-07-26T09:05:04")
        self.assertLess("2026-07-26T09:05:03", "2026-12-01T00:00:00")


class TestCursor(unittest.TestCase):

    def test_round_trip_with_a_timestamp(self):
        ts = datetime(2026, 7, 20, 12, 0, tzinfo=timezone.utc)
        score, encoded_ts, job_id = jobs.decode_cursor(
            jobs.encode_cursor(88, ts, "abc123"))
        self.assertEqual((score, job_id), (88, "abc123"))
        self.assertEqual(encoded_ts, ts.isoformat())

    def test_round_trip_with_a_null_timestamp(self):
        # posted_at_ts is NULL for plenty of rows; the cursor has to survive it
        # or pagination breaks exactly at the tail of the list.
        score, ts, job_id = jobs.decode_cursor(jobs.encode_cursor(0, None, "z"))
        self.assertEqual((score, ts, job_id), (0, None, "z"))

    def test_cursor_is_url_safe_and_unpadded(self):
        cursor = jobs.encode_cursor(100, None, "a/b+c")
        self.assertNotIn("=", cursor)
        self.assertNotIn("/", cursor)
        self.assertNotIn("+", cursor)

    def test_malformed_cursors_are_a_400(self):
        from fastapi import HTTPException
        for raw in ("", "!!!", base64.urlsafe_b64encode(b"[1]").decode(),
                    base64.urlsafe_b64encode(json.dumps({"a": 1}).encode()).decode()):
            with self.assertRaises(HTTPException) as caught:
                jobs.decode_cursor(raw)
            self.assertEqual(caught.exception.status_code, 400)


if __name__ == "__main__":
    unittest.main()

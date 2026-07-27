"""The open-redirect guard.

`next` is the only caller-supplied value in this service that ends up in a
Location header, so it is the only place an open redirect can happen. These
tests are the specification: an allowlist, not a blocklist.
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from auth import safe_next_path  # noqa: E402


class TestSafeNextPath(unittest.TestCase):

    def test_ordinary_paths_survive(self):
        for path in ("/", "/jobs", "/jobs/abc123", "/jobs?remote=true&q=a%20b",
                     "/jobs#section"):
            self.assertEqual(safe_next_path(path), path)

    def test_protocol_relative_is_rejected(self):
        # //evil.com reads like a path and is followed off-site by every
        # browser. This is the case the whole function exists for.
        self.assertEqual(safe_next_path("//evil.com"), "/")
        self.assertEqual(safe_next_path("//evil.com/jobs"), "/")
        self.assertEqual(safe_next_path("///evil.com"), "/")

    def test_absolute_urls_are_rejected(self):
        for raw in ("https://evil.com", "http://evil.com/jobs",
                    "javascript:alert(1)", "data:text/html,x"):
            self.assertEqual(safe_next_path(raw), "/", raw)

    def test_backslash_is_rejected(self):
        # Several browsers normalise '\' to '/' inside URLs, which turns
        # '/\evil.com' into a protocol-relative URL after the fact.
        self.assertEqual(safe_next_path("/\\evil.com"), "/")
        self.assertEqual(safe_next_path("\\\\evil.com"), "/")

    def test_bare_host_is_rejected(self):
        self.assertEqual(safe_next_path("evil.com"), "/")
        self.assertEqual(safe_next_path("jobs"), "/")

    def test_control_characters_are_rejected(self):
        # A newline in a Location header is response splitting.
        self.assertEqual(safe_next_path("/jobs\r\nSet-Cookie: a=b"), "/")
        self.assertEqual(safe_next_path("/jobs\x00"), "/")

    def test_empty_and_wrong_types(self):
        for raw in (None, "", 42, [], {}):
            self.assertEqual(safe_next_path(raw), "/")

    def test_colon_allowed_in_query_only(self):
        # A scheme is identified by a colon in the PATH; a colon in the query
        # string is ordinary data and must not cost the user their redirect.
        self.assertEqual(safe_next_path("/jobs?t=12:30"), "/jobs?t=12:30")
        self.assertEqual(safe_next_path("/a:b"), "/")


if __name__ == "__main__":
    unittest.main()

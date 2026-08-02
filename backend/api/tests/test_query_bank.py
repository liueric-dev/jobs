"""Defect D09: an unreadable query bank must not quietly become a stored fact.

WHAT WAS WRONG. `_mode_for_slug` wrapped `load_query_buckets()` in a bare
`except (OSError, ValueError, KeyError): return "unknown"`. `mode` is not
cosmetic -- `google_jobs.py:99` reads it as
`is_remote = REMOTE_PATTERN.search(location) or mode == "remote"` -- so a config
file that was unreadable for one request stored a batch of remote postings
marked non-remote. The submission returned 200. The rows are indistinguishable
from correct ones afterwards, which is what makes it silent data loss rather
than a bug someone would notice.

"Silence is this system's failure mode" is a named invariant in
`.claude/CLAUDE.md`; this was the API's instance of it.

WHY 500 AND NOT A RETRY-SAFE 4xx. Refusing the submission leaves the claim held,
the watermark unadvanced and the payload re-submittable, so the contributor's
SerpApi credit is not lost -- the failure is recoverable in every direction that
matters. The same read failure already returned 500 from `claim`
(`app.py`, the `except` around `qc.load_query_buckets()`); one failure now gets
one status whichever endpoint meets it.

AND THE OTHER BRANCH. A slug that is absent from a bank that read fine is a
different fact and gets a different answer: 409, because `claim` only ever
issues slugs from this bank, so the only route here is a dataset withdrawn
between claim and submit, or hand-crafted. That is "your claim is not live",
which is what 409 already means on this endpoint. Returning "unknown" for that
case was the same silent corruption wearing a plausible cause.
"""

import asyncio
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fakedb import FakeConn, FakeRequest, patch_db   # noqa: E402

import app                                          # noqa: E402
import query_claims as qc                           # noqa: E402
from fastapi import HTTPException                   # noqa: E402


def live_claim(contributor="c_test"):
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
    return (contributor, now, now)


class _BankBroken:
    """load_query_buckets raising what a real unreadable bank raises.

    OSError is the file being gone or unreadable; ValueError is json.load on
    truncated content; KeyError is a valid JSON document with no "buckets".
    All three were caught by the old sentinel, so all three are exercised.
    """

    def __init__(self, exc):
        self.exc = exc

    def __call__(self):
        raise self.exc


class TestModeForSlug(unittest.TestCase):

    def setUp(self):
        self._real = qc.load_query_buckets
        self.addCleanup(lambda: setattr(qc, "load_query_buckets", self._real))

    def test_a_readable_bank_still_answers(self):
        # The control. Every slug in the committed bank resolves to its own
        # mode, and no slug resolves to the string this defect was about.
        for bucket in self._real().values():
            for q in bucket["queries"]:
                self.assertEqual(app._mode_for_slug(q["slug"]), q["mode"])
                self.assertNotEqual(q["mode"], "unknown")

    def test_an_unreadable_bank_raises_rather_than_returning_unknown(self):
        # THE DEFECT. Restore the `return "unknown"` and this goes red three
        # times over.
        for exc in (OSError("no such file"), ValueError("bad json"),
                    KeyError("buckets")):
            with self.subTest(exc=type(exc).__name__):
                qc.load_query_buckets = _BankBroken(exc)
                with self.assertRaises(HTTPException) as caught:
                    app._mode_for_slug("anything")
                self.assertEqual(caught.exception.status_code, 500)
                self.assertIn("query bank unavailable", caught.exception.detail)

    def test_an_unknown_slug_in_a_readable_bank_is_a_409(self):
        with self.assertRaises(HTTPException) as caught:
            app._mode_for_slug("a-slug-nobody-ever-configured")
        self.assertEqual(caught.exception.status_code, 409)

    def test_no_code_path_returns_the_sentinel(self):
        # Stated as a property rather than a case, because the failure this
        # guards is someone re-introducing a fallback at a THIRD exit. The
        # function has exactly two ways out that are not an exception: a mode
        # from the bank, or nothing.
        with open(app.__file__, encoding="utf-8") as fh:
            source = fh.read()
        body = source.split("def _mode_for_slug")[1].split("\ndef ")[0]
        code = "\n".join(line for line in body.splitlines()
                         if not line.strip().startswith("#"))
        # The docstring names "unknown" while explaining why it is gone.
        code = code.split('"""')[2] if code.count('"""') >= 2 else code
        self.assertNotIn('"unknown"', code)


class TestSubmitRefusesWhenTheBankIsUnreadable(unittest.TestCase):
    """The endpoint-level consequence, which is the part that matters.

    _mode_for_slug raising is only useful if `submit` lets it out instead of
    catching it, and if it does so BEFORE anything is written.
    """

    def setUp(self):
        self._real = qc.load_query_buckets
        qc.load_query_buckets = _BankBroken(OSError("no such file"))
        self.addCleanup(lambda: setattr(qc, "load_query_buckets", self._real))

    def test_nothing_is_stored_and_the_watermark_stands(self):
        conn = FakeConn(claim_state=live_claim())
        restore = patch_db(app, conn)
        try:
            with self.assertRaises(HTTPException) as caught:
                asyncio.run(app.submit(
                    dataset="google_jobs:query:whatever",
                    request=FakeRequest(
                        '{"jobs": [{"title": "AI Engineer", "company_name": "Acme"}]}'),
                    authorization="Bearer key"))
        finally:
            restore()
        self.assertEqual(caught.exception.status_code, 500)
        self.assertEqual(conn.marked, [], "watermark advanced on a config failure")
        self.assertEqual(conn.log, [], "a failed submission was logged as one")
        # The claim is deliberately NOT released: the contributor already paid
        # SerpApi for this payload and the server is the thing that is broken,
        # so they keep the right to re-submit it for the rest of the TTL.
        self.assertEqual(conn.released, [])


class TestClaimAlreadyRefused(unittest.TestCase):
    """`claim`'s handling was already right, and is pinned so it stays the
    reference the submit path was made to match."""

    def test_claim_500s_on_an_unreadable_bank(self):
        real = qc.load_query_buckets
        qc.load_query_buckets = _BankBroken(OSError("no such file"))
        conn = FakeConn()
        restore = patch_db(app, conn)
        try:
            with self.assertRaises(HTTPException) as caught:
                app.claim(app.ClaimRequest(max=1), authorization="Bearer key")
        finally:
            restore()
            qc.load_query_buckets = real
        self.assertEqual(caught.exception.status_code, 500)
        self.assertIn("query bank unavailable", caught.exception.detail)


if __name__ == "__main__":
    unittest.main()

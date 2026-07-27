"""id_token claim validation.

Every one of these checks is the only thing standing between a forged or
replayed token and a session, BECAUSE THE SIGNATURE IS NOT VERIFIED -- see
auth.py's docstring for why that is sound in this flow and void in the other
one. One test per rejection, so a loosened check fails loudly.
"""

import base64
import json
import os
import sys
import time
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config  # noqa: E402
import auth  # noqa: E402

NONCE = "the-nonce-we-minted"


def make_token(**overrides):
    """A syntactically valid JWT with a chosen payload. The signature segment
    is junk on purpose: nothing in this path reads it, and a test that supplied
    a real one would imply otherwise."""
    claims = {
        "aud": config.GOOGLE_CLIENT_ID,
        "iss": "https://accounts.google.com",
        "exp": time.time() + 3600,
        "nonce": NONCE,
        "sub": "1234567890",
        "email": "someone@example.com",
        "email_verified": True,
        "name": "Some One",
    }
    claims.update(overrides)
    for key, value in list(claims.items()):
        if value is _ABSENT:
            del claims[key]
    payload = base64.urlsafe_b64encode(json.dumps(claims).encode()).decode().rstrip("=")
    return f"eyJhbGciOiJSUzI1NiJ9.{payload}.not-a-real-signature"


_ABSENT = object()


class TestIdTokenClaims(unittest.TestCase):

    def setUp(self):
        # The module reads config at call time, so pinning the client id here
        # is enough and no .env is required to run these.
        self._saved = config.GOOGLE_CLIENT_ID
        config.GOOGLE_CLIENT_ID = "test-client-id.apps.googleusercontent.com"

    def tearDown(self):
        config.GOOGLE_CLIENT_ID = self._saved

    def accepts(self, **overrides):
        return auth._claims_from_id_token(make_token(**overrides), NONCE)

    def rejects(self, **overrides):
        with self.assertRaises(ValueError):
            auth._claims_from_id_token(make_token(**overrides), NONCE)

    def test_a_good_token_is_accepted(self):
        claims = self.accepts()
        self.assertEqual(claims["email"], "someone@example.com")
        self.assertEqual(claims["sub"], "1234567890")

    def test_wrong_audience(self):
        # A token minted for a DIFFERENT Google client. Without this check any
        # site's token would authenticate here.
        self.rejects(aud="someone-elses-client.apps.googleusercontent.com")
        self.rejects(aud=_ABSENT)

    def test_wrong_issuer(self):
        self.rejects(iss="https://evil.example.com")
        self.rejects(iss=_ABSENT)

    def test_both_google_issuer_spellings_are_accepted(self):
        # Both appear in real tokens and which one you get is not something to
        # depend on.
        self.accepts(iss="accounts.google.com")
        self.accepts(iss="https://accounts.google.com")

    def test_expired(self):
        self.rejects(exp=time.time() - 3600)
        self.rejects(exp=_ABSENT)
        self.rejects(exp="not-a-number")

    def test_small_clock_skew_is_tolerated(self):
        # Expired by less than the leeway: accepted, because our clock and
        # Google's are not the same clock.
        self.accepts(exp=time.time() - (auth.CLOCK_SKEW_SECONDS - 5))

    def test_nonce_mismatch(self):
        # The nonce ties the token to the login WE started. Without it, a token
        # legitimately issued for our client id elsewhere would replay here.
        self.rejects(nonce="a-different-login")
        self.rejects(nonce=_ABSENT)

    def test_unverified_email(self):
        # Self-asserted addresses. Accepting one would let anyone who can make
        # a Google account claiming an allowlisted address in.
        self.rejects(email_verified=False)
        self.rejects(email_verified=_ABSENT)

    def test_missing_identity_claims(self):
        self.rejects(sub=_ABSENT)
        self.rejects(email=_ABSENT)

    def test_malformed_tokens(self):
        for raw in ("", "not-a-jwt", "a.b", "a.b.c.d", "header.!!!.sig"):
            with self.assertRaises(ValueError, msg=raw):
                auth._claims_from_id_token(raw, NONCE)


if __name__ == "__main__":
    unittest.main()

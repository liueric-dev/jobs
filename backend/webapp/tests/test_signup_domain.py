"""docs/adr/0012: a verified Workspace account in ALLOWED_SIGNUP_DOMAIN gets an
app_users row on first login; everyone else is still refused.

The property that must not regress is the one auth.py's docstring opens with:
Google authenticates, the allowlist authorises. The domain rule widens the
allowlist by exactly one Workspace domain and nothing else. So most of these
tests are refusals.
"""

import contextlib
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import auth
from fastapi import HTTPException

import config


def claims(**overrides):
    base = {"sub": "sub-1", "email": "builder@pursuit.org",
            "email_verified": True, "hd": "pursuit.org", "name": "A Builder"}
    base.update(overrides)
    return {k: v for k, v in base.items() if v is not None}


class _Rows:
    def __init__(self, row):
        self._row = row

    def fetchone(self):
        return self._row


class FakeAppUsers:
    """Just enough of app_users for _resolve_user's statements."""

    def __init__(self, users=()):
        self.users = [dict(u) for u in users]
        self.inserts = []

    def execute(self, sql, params=()):
        sql = " ".join(sql.split())
        if sql.startswith("SELECT id, active FROM app_users WHERE google_sub"):
            hit = [u for u in self.users if u.get("google_sub") == params[0]]
        elif sql.startswith("SELECT id, active FROM app_users WHERE email"):
            hit = [u for u in self.users
                   if u["email"] == params[0] and u.get("google_sub") is None]
        elif sql.startswith("INSERT INTO app_users"):
            uid, email, sub, _name, profile, _created = params
            self.inserts.append({"email": email, "google_sub": sub,
                                 "profile": profile})
            if not any(u["email"] == email or u.get("google_sub") == sub
                       for u in self.users):
                self.users.append({"id": uid, "email": email, "google_sub": sub,
                                   "profile": profile, "active": True})
            return _Rows(None)
        else:
            return _Rows(None)
        return _Rows((hit[0]["id"], hit[0]["active"]) if hit else None)

    def commit(self):
        pass


class SignupTestCase(unittest.TestCase):

    def setUp(self):
        self._saved = (config.ALLOWED_SIGNUP_DOMAIN, config.SIGNUP_PROFILE)
        config.ALLOWED_SIGNUP_DOMAIN = "pursuit.org"
        config.SIGNUP_PROFILE = "pursuit"

    def tearDown(self):
        config.ALLOWED_SIGNUP_DOMAIN, config.SIGNUP_PROFILE = self._saved

    def resolve(self, fake, c):
        with mock.patch.object(auth, "db", lambda: contextlib.nullcontext(fake)):
            return auth._resolve_user(c)


class TestSignupAllowed(SignupTestCase):

    def test_a_verified_workspace_account_in_the_domain(self):
        self.assertTrue(auth._signup_allowed(claims()))

    def test_another_domain(self):
        self.assertFalse(auth._signup_allowed(
            claims(email="x@gmail.com", hd=None)))
        self.assertFalse(auth._signup_allowed(
            claims(email="x@other.org", hd="other.org")))

    def test_a_consumer_account_claiming_the_address_has_no_hd(self):
        # A personal Google account can carry any address, including one
        # ending @pursuit.org. Only a Workspace account carries `hd`.
        self.assertFalse(auth._signup_allowed(claims(hd=None)))

    def test_hd_and_address_must_agree(self):
        self.assertFalse(auth._signup_allowed(claims(email="x@gmail.com")))
        self.assertFalse(auth._signup_allowed(
            claims(email="x@pursuit.org.evil.com")))

    def test_unverified_email(self):
        self.assertFalse(auth._signup_allowed(claims(email_verified=False)))
        self.assertFalse(auth._signup_allowed(claims(email_verified=None)))

    def test_off_unless_both_settings_are_present(self):
        config.ALLOWED_SIGNUP_DOMAIN = ""
        self.assertFalse(auth._signup_allowed(claims()))
        config.ALLOWED_SIGNUP_DOMAIN, config.SIGNUP_PROFILE = "pursuit.org", ""
        self.assertFalse(auth._signup_allowed(claims()))


class TestResolveUser(SignupTestCase):

    def test_first_login_creates_a_row_on_the_cohort_profile(self):
        fake = FakeAppUsers()
        user_id = self.resolve(fake, claims())
        self.assertTrue(user_id.startswith("u_"))
        self.assertEqual(fake.inserts, [{"email": "builder@pursuit.org",
                                         "google_sub": "sub-1",
                                         "profile": "pursuit"}])

    def test_second_login_creates_nothing(self):
        fake = FakeAppUsers()
        first = self.resolve(fake, claims())
        second = self.resolve(fake, claims())
        self.assertEqual(first, second)
        self.assertEqual(len(fake.inserts), 1)

    def test_other_domain_is_refused_and_nothing_is_written(self):
        fake = FakeAppUsers()
        with self.assertRaises(HTTPException) as ctx:
            self.resolve(fake, claims(email="x@gmail.com", hd=None))
        self.assertEqual(ctx.exception.status_code, 403)
        self.assertEqual(fake.inserts, [])

    def test_unset_setting_is_allowlist_only(self):
        config.ALLOWED_SIGNUP_DOMAIN = ""
        fake = FakeAppUsers()
        with self.assertRaises(HTTPException) as ctx:
            self.resolve(fake, claims())
        self.assertEqual(ctx.exception.status_code, 403)
        self.assertEqual(fake.inserts, [])

    def test_an_allowlisted_row_still_binds_by_email(self):
        fake = FakeAppUsers([{"id": "u_seeded", "email": "builder@pursuit.org",
                              "google_sub": None, "active": True}])
        self.assertEqual(self.resolve(fake, claims()), "u_seeded")
        self.assertEqual(fake.inserts, [])

    def test_a_disabled_row_is_not_resurrected_by_the_domain_rule(self):
        fake = FakeAppUsers([{"id": "u_off", "email": "builder@pursuit.org",
                              "google_sub": "sub-1", "active": False}])
        with self.assertRaises(HTTPException) as ctx:
            self.resolve(fake, claims())
        self.assertEqual(ctx.exception.status_code, 403)
        self.assertEqual(fake.inserts, [])

    def test_an_address_bound_to_a_different_sub_is_refused(self):
        # A recycled Workspace address: the row belongs to the previous holder.
        # ON CONFLICT leaves it alone, and the new sub finds no row.
        fake = FakeAppUsers([{"id": "u_prev", "email": "builder@pursuit.org",
                              "google_sub": "sub-previous", "active": True}])
        with self.assertRaises(HTTPException) as ctx:
            self.resolve(fake, claims(sub="sub-new"))
        self.assertEqual(ctx.exception.status_code, 403)


if __name__ == "__main__":
    unittest.main()

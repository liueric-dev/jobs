"""`manage_app_users.py set-profile`: the only supported way to move a user.

WHY THIS COMMAND IS WORTH ITS OWN TEST FILE
    app_users.profile decides which corpus a person sees -- it is the tenancy
    key jobs.py scopes every query to and the one label.py stamps onto axis-B
    labels. `add` cannot change it (email is UNIQUE, so a second add is
    refused), which left a hand-written UPDATE as the only path and therefore
    left the profile check unenforced on the one operation most likely to need
    it.

NO DATABASE HERE, DELIBERATELY -- the same line test_label_form.py draws. A
fake connection proves everything asserted below: which profiles are accepted,
which are refused, what is printed, and that the UPDATE names the row found by
email. What it cannot prove -- that `profiles` and `app_users` exist with these
columns -- is not a property of this command.

The fake answers `profiles` queries with rows in _COLUMNS order rather than
stubbing profiles.load_one, because "load_one and not load_active" IS the
requirement: load_one returns paused profiles and load_active does not, and a
stub would assert whichever one the code happened to call.
"""

import argparse
import contextlib
import io
import os
import sys
import unittest

WEBAPP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, WEBAPP_DIR)

import config  # noqa: E402,F401  (must come first -- performs the sys.path insert)

import manage_app_users  # noqa: E402
import profiles  # noqa: E402


def _profile_row(name, active=True):
    """A `profiles` row in profiles._COLUMNS order, as load_one selects it."""
    return (name, name.title(), "{}", None, "{}", 1, 20, active,
            "2026-01-01T00:00:00", "2026-01-01T00:00:00")


class FakeResult:

    def __init__(self, rows):
        self._rows = rows

    def fetchone(self):
        return self._rows[0] if self._rows else None

    def fetchall(self):
        return list(self._rows)


class FakeConn:
    """Enough of a psycopg connection for one run of cmd_set_profile.

    Dispatch is on the SQL text because that is what the command actually
    sends; matching on call order instead would keep passing if the SELECT and
    the UPDATE were reordered or one of them dropped.
    """

    def __init__(self, profile_rows, user_row):
        self.profiles = {r[0]: r for r in profile_rows}
        self.user_row = user_row
        self.updates = []
        self.commits = 0

    # `with connect() as conn:` -- psycopg's own context manager, which yields
    # the connection and does not close it.
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def execute(self, sql, params=()):
        flat = " ".join(sql.split())
        if "FROM profiles" in flat and "WHERE profile = %s" in flat:
            row = self.profiles.get(params[0])
            return FakeResult([row] if row else [])
        if "FROM profiles" in flat and "WHERE active" in flat:
            return FakeResult([r for r in self.profiles.values() if r[7]])
        if flat.startswith("SELECT id, profile FROM app_users"):
            return FakeResult([self.user_row] if self.user_row else [])
        if flat.startswith("UPDATE app_users SET profile"):
            self.updates.append(params)
            return FakeResult([])
        raise AssertionError(f"unexpected SQL: {flat}")

    def commit(self):
        self.commits += 1


@contextlib.contextmanager
def _patched(conn):
    original = manage_app_users.connect
    manage_app_users.connect = lambda admin=False: conn
    try:
        yield
    finally:
        manage_app_users.connect = original


def _run(conn, email="you@x.com", profile="pursuit"):
    """Run the command against `conn`. Returns (stdout, stderr, exit_code)."""
    out, err = io.StringIO(), io.StringIO()
    code = 0
    args = argparse.Namespace(email=email, profile=profile)
    with _patched(conn), contextlib.redirect_stdout(out), \
            contextlib.redirect_stderr(err):
        try:
            manage_app_users.cmd_set_profile(args)
        except SystemExit as e:
            code = e.code
    return out.getvalue(), err.getvalue(), code


def _conn(user=("u_abc", "tech"), profile_rows=None):
    return FakeConn(
        profile_rows if profile_rows is not None
        else [_profile_row("pursuit"), _profile_row("tech")],
        user)


class TestTheProfileChanges(unittest.TestCase):

    def test_the_row_found_by_email_is_the_row_updated(self):
        conn = _conn()
        out, err, code = _run(conn)
        self.assertEqual((err, code), ("", 0))
        # By id, not by email: the SELECT already resolved which row this is,
        # and a second WHERE email would be a second chance to get it wrong.
        self.assertEqual(conn.updates, [("pursuit", "u_abc")])
        self.assertEqual(conn.commits, 1)

    def test_the_email_is_normalised_the_way_add_normalises_it(self):
        # add() lowercases and strips before inserting (manage_app_users.py:69),
        # so a lookup that did not would never find the row it just created.
        conn = _conn()
        out, _, code = _run(conn, email="  YOU@X.com ")
        self.assertEqual(code, 0)
        self.assertEqual(conn.updates, [("pursuit", "u_abc")])
        self.assertIn("you@x.com", out)

    def test_before_and_after_are_both_printed(self):
        # The operator has to be able to see what the command did to a column
        # that is otherwise only visible through `list`.
        out, _, _ = _run(_conn())
        self.assertIn("tech -> pursuit", out)
        self.assertIn("u_abc", out)

    def test_the_operator_is_told_no_logout_is_needed(self):
        out, _, _ = _run(_conn())
        self.assertIn("NEXT request", out)


class TestWhatItRefuses(unittest.TestCase):

    def test_an_unknown_profile_is_rejected_and_nothing_is_written(self):
        conn = _conn()
        out, err, code = _run(conn, profile="nope")
        self.assertEqual(code, 1)
        self.assertIn("no such profile: 'nope'", err)
        # And it names where to look, as add() does.
        self.assertIn("pursuit", err)
        self.assertEqual(conn.updates, [])
        self.assertEqual(conn.commits, 0)

    def test_an_unknown_email_is_rejected_and_nothing_is_written(self):
        conn = _conn(user=None)
        out, err, code = _run(conn)
        self.assertEqual(code, 1)
        self.assertIn("no user with email 'you@x.com'", err)
        self.assertEqual(conn.updates, [])
        self.assertEqual(conn.commits, 0)

    def test_both_refusals_go_to_stderr_and_print_no_success_line(self):
        # A failure on stdout is a failure that a shell pipeline treats as a
        # result, and every other refusal in this file already uses stderr.
        for conn in (_conn(user=None), _conn()):
            out, err, code = _run(conn, profile="nope" if conn.user_row else "pursuit")
            self.assertEqual(code, 1)
            self.assertEqual(out, "")
            self.assertTrue(err)


class TestTheInactiveProfileWarning(unittest.TestCase):
    """The failure this command exists to correct.

    The one row this service has ever had sits on `tech`, which task 12 made
    inactive, and it got there because nothing warned. An inactive profile is
    skipped by profiles.load_active (profiles.py:94-106), so extract, match and
    score do no work for it and the user's list quietly stops moving.
    """

    def test_moving_onto_an_inactive_profile_warns_but_succeeds(self):
        conn = _conn(profile_rows=[_profile_row("pursuit", active=False),
                                   _profile_row("tech")])
        out, err, code = _run(conn)
        self.assertEqual((err, code), ("", 0))
        self.assertIn("WARNING", out)
        self.assertIn("active = False", out)
        # A warning, not an error: seeding a user onto a profile nobody has
        # activated yet is a legitimate order of operations, which is why
        # load_one ignores `active` at all (profiles.py:109-120).
        self.assertEqual(conn.updates, [("pursuit", "u_abc")])
        self.assertEqual(conn.commits, 1)

    def test_the_warning_says_what_actually_breaks(self):
        # "inactive" on its own does not tell an operator that the pipeline
        # stops working for this person, which is the whole consequence.
        conn = _conn(profile_rows=[_profile_row("pursuit", active=False)])
        out, _, _ = _run(conn)
        self.assertIn("load_active", out)

    def test_an_active_target_does_not_warn(self):
        # A warning on every run is a warning nobody reads.
        out, _, _ = _run(_conn())
        self.assertNotIn("WARNING", out)


class TestItUsesLoadOneAndNotLoadActive(unittest.TestCase):

    def test_an_inactive_profile_is_still_a_valid_target(self):
        # load_active would return nothing for this connection, so a command
        # validating against it would refuse the move outright.
        rows = [_profile_row("pursuit", active=False)]
        conn = FakeConn(rows, ("u_abc", "tech"))
        self.assertEqual(profiles.load_active(conn), [])
        self.assertIsNotNone(profiles.load_one(conn, "pursuit"))
        out, err, code = _run(conn)
        self.assertEqual((err, code), ("", 0))

    def test_the_active_profiles_listed_on_a_miss_exclude_the_paused_one(self):
        conn = _conn(profile_rows=[_profile_row("pursuit"),
                                   _profile_row("tech", active=False)])
        _, err, _ = _run(conn, profile="nope")
        self.assertIn("pursuit", err)
        self.assertNotIn("tech", err)


class TestTheSubcommandIsWired(unittest.TestCase):
    """Through main(), because a function nothing dispatches to is not a
    command. The rest of this file calls cmd_set_profile directly."""

    def _main(self, argv):
        conn = _conn()
        out, err = io.StringIO(), io.StringIO()
        code = 0
        original_argv = sys.argv
        sys.argv = ["manage_app_users.py"] + argv
        try:
            with _patched(conn), contextlib.redirect_stdout(out), \
                    contextlib.redirect_stderr(err):
                try:
                    manage_app_users.main()
                except SystemExit as e:
                    code = e.code
        finally:
            sys.argv = original_argv
        return conn, out.getvalue(), code

    def test_set_profile_dispatches_to_the_command(self):
        conn, out, code = self._main(
            ["set-profile", "--email", "you@x.com", "--profile", "pursuit"])
        self.assertEqual(code, 0)
        self.assertEqual(conn.updates, [("pursuit", "u_abc")])

    def test_both_flags_are_required(self):
        # Neither has a default worth guessing: an omitted --profile that fell
        # back to anything would move a user somewhere nobody asked for.
        for argv in (["set-profile", "--email", "you@x.com"],
                     ["set-profile", "--profile", "pursuit"]):
            conn, _, code = self._main(argv)
            self.assertEqual(code, 2)
            self.assertEqual(conn.updates, [])


if __name__ == "__main__":
    unittest.main()

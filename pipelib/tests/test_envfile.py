"""Tests for pipelib.envfile.

WHY THIS EXISTS
    envfile.py shipped with zero test coverage and, since slice C, has two
    consumers -- jobs/run-daily.py and ~/apps/events/run-daily.py. Its own
    docstring names the reason that matters: "`set -a; . file; set +a` is what
    the shell callers do, so this must agree with it or two entry points will
    disagree about one key's value."

    That is now a three-way agreement. The events `.env` is read by systemd's
    EnvironmentFile= as well, and systemd does NOT strip inline comments --
    which is exactly why ~/.hermes/.env cannot be handed to systemd (its
    GEMINI_API_KEY line has a whitespace-preceded ' # comment' that envfile
    strips and systemd would not). These tests pin the envfile half of that
    contract so a future edit cannot quietly move it.

Run:
    cd ~/.hermes/scripts && python3 -m unittest discover -s pipelib/tests -t .
"""

import os
import tempfile
import unittest

from pipelib import envfile


class TestParse(unittest.TestCase):
    def test_plain_key_value(self):
        self.assertEqual(envfile.parse("FOO=bar"), {"FOO": "bar"})

    def test_blank_lines_and_full_line_comments_ignored(self):
        text = "\n# a comment\n   \n  # indented comment\nFOO=bar\n"
        self.assertEqual(envfile.parse(text), {"FOO": "bar"})

    def test_export_prefix_is_stripped(self):
        """`export FOO=bar` is still FOO=bar -- the shell accepts both."""
        self.assertEqual(envfile.parse("export FOO=bar"), {"FOO": "bar"})

    def test_whitespace_preceded_hash_is_an_inline_comment(self):
        """The live ~/.hermes/.env relies on this (its GEMINI_API_KEY line)."""
        self.assertEqual(envfile.parse("FOO=bar  # trailing note"), {"FOO": "bar"})

    def test_hash_flush_against_value_is_part_of_the_value(self):
        """A password may legitimately contain '#'. This is the shell's rule.

        The distinction that makes the previous test safe: only whitespace
        before the '#' makes it a comment.
        """
        self.assertEqual(envfile.parse("FOO=pa#ssword"), {"FOO": "pa#ssword"})
        self.assertEqual(envfile.parse("FOO=#leading"), {"FOO": "#leading"})

    def test_matched_surrounding_quotes_are_stripped(self):
        self.assertEqual(envfile.parse('FOO="bar baz"'), {"FOO": "bar baz"})
        self.assertEqual(envfile.parse("FOO='bar baz'"), {"FOO": "bar baz"})

    def test_unmatched_quotes_are_left_alone(self):
        self.assertEqual(envfile.parse('FOO="bar'), {"FOO": '"bar'})

    def test_surrounding_whitespace_is_stripped(self):
        self.assertEqual(envfile.parse("  FOO = bar  "), {"FOO": "bar"})

    def test_later_lines_win(self):
        """Same precedence as the shell, where the last assignment survives."""
        self.assertEqual(envfile.parse("FOO=first\nFOO=second"), {"FOO": "second"})

    def test_empty_value_is_kept(self):
        self.assertEqual(envfile.parse("FOO="), {"FOO": ""})

    def test_value_containing_equals_is_not_split_again(self):
        """A URL query string or a base64 pad must survive intact."""
        self.assertEqual(
            envfile.parse("DATABASE_URL=postgresql://u:p@h:5432/d?sslmode=require"),
            {"DATABASE_URL": "postgresql://u:p@h:5432/d?sslmode=require"},
        )

    def test_unparseable_lines_are_skipped_not_fatal(self):
        text = "not a key=value line at all\n=novalue\n9INVALID=x\nFOO=bar\n"
        self.assertEqual(envfile.parse(text), {"FOO": "bar"})


class TestLoad(unittest.TestCase):
    def setUp(self):
        self._saved = dict(os.environ)
        self.addCleanup(self._restore)

    def _restore(self):
        os.environ.clear()
        os.environ.update(self._saved)

    def _write(self, text):
        fd, path = tempfile.mkstemp(prefix="envfile-test-")
        with os.fdopen(fd, "w") as f:
            f.write(text)
        self.addCleanup(os.unlink, path)
        return path

    def test_sets_unset_keys_and_returns_them(self):
        os.environ.pop("ENVFILE_TEST_A", None)
        applied = envfile.load(self._write("ENVFILE_TEST_A=value\n"))
        self.assertEqual(os.environ["ENVFILE_TEST_A"], "value")
        self.assertIn("ENVFILE_TEST_A", applied)

    def test_override_false_leaves_an_already_set_var_alone(self):
        """The file is the fallback, not the authority.

        This is what lets a one-off run export a key to point at another
        machine's quota without editing the file.
        """
        os.environ["ENVFILE_TEST_B"] = "from-environment"
        applied = envfile.load(self._write("ENVFILE_TEST_B=from-file\n"))
        self.assertEqual(os.environ["ENVFILE_TEST_B"], "from-environment")
        self.assertNotIn("ENVFILE_TEST_B", applied)

    def test_override_true_replaces_it(self):
        os.environ["ENVFILE_TEST_C"] = "from-environment"
        applied = envfile.load(self._write("ENVFILE_TEST_C=from-file\n"), override=True)
        self.assertEqual(os.environ["ENVFILE_TEST_C"], "from-file")
        self.assertIn("ENVFILE_TEST_C", applied)

    def test_missing_file_returns_empty_and_does_not_raise(self):
        """Not every machine running these scripts has an env file."""
        self.assertEqual(envfile.load("/nonexistent/path/to/.env"), [])

    def test_unreadable_path_does_not_raise(self):
        """A directory is an OSError on open(), same branch as a missing file."""
        self.assertEqual(envfile.load(tempfile.gettempdir()), [])


if __name__ == "__main__":
    unittest.main()

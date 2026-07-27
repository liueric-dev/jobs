"""Tests for lib/envfile.py -- .env parsing and loading.

Split out of the shared library's suite on 2026-07-26 when lib/ was vendored
into this repo (~/apps/REORG.md slice G).

stdlib unittest rather than pytest, which isn't installed here and isn't
worth adding as a dependency to a stdlib-plus-psycopg codebase.
"""

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import os  # noqa: E402
import tempfile  # noqa: E402
import unittest  # noqa: E402

from lib import envfile  # noqa: E402


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

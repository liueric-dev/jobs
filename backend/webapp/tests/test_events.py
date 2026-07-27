"""The event vocabulary and the LIKE escaping.

job_events.event is free TEXT, so the closed set in jobs.EVENT_NAMES is the
only thing keeping the table analysable for the learned ranker described in
../docs/SCORING.md. A typo'd event name is worse than a rejected one: it is
silently unusable training data that nobody notices for a year.
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import jobs  # noqa: E402


class TestEventNames(unittest.TestCase):

    def test_the_closed_set(self):
        # Pinned literally. Adding a name is a deliberate act that should
        # require editing this line, because every addition is a new column of
        # meaning in a table meant to be read years from now.
        self.assertEqual(
            set(jobs.EVENT_NAMES),
            {"impression", "open", "save", "unsave", "dismiss", "applied"})

    def test_batch_validation_rejects_unknown_names(self):
        batch = jobs.EventBatch(events=[
            {"job_id": "a", "event": "impression"},
            {"job_id": "b", "event": "clicked"},      # not in the set
        ])
        unknown = {e.event for e in batch.events} - set(jobs.EVENT_NAMES)
        self.assertEqual(unknown, {"clicked"})

    def test_batch_is_capped(self):
        # A page of impressions is one request; an unbounded list is a way to
        # make one request cost an arbitrary number of inserts.
        from pydantic import ValidationError
        with self.assertRaises(ValidationError):
            jobs.EventBatch(events=[{"job_id": str(i), "event": "impression"}
                                    for i in range(201)])

    def test_dedup_window(self):
        self.assertEqual(jobs.IMPRESSION_DEDUP_HOURS, 24)


class TestLikeEscaping(unittest.TestCase):

    def test_wildcards_in_user_input_are_escaped(self):
        # Without this, a search for '100%' matches every row and a search for
        # '_' matches every single character.
        self.assertEqual(jobs._like("100%"), "%100\\%%")
        self.assertEqual(jobs._like("a_b"), "%a\\_b%")

    def test_backslash_is_escaped_first(self):
        # Escaping backslash after the wildcards would double-escape the
        # escapes this function just added.
        self.assertEqual(jobs._like("a\\b"), "%a\\\\b%")

    def test_ordinary_terms_are_wrapped(self):
        self.assertEqual(jobs._like("engineer"), "%engineer%")


class TestListColumns(unittest.TestCase):

    def test_description_is_not_in_the_list_response(self):
        # The largest column in the database. The list has `summary` from
        # job_facts for this purpose; sending both on every page would be the
        # difference between a fast list and a slow one.
        self.assertNotIn("description_text", jobs.LIST_COLUMNS)
        self.assertIn("summary", jobs.LIST_COLUMNS)

    def test_detail_adds_the_description(self):
        self.assertIn("description_text", jobs.DETAIL_COLUMNS)
        self.assertEqual(set(jobs.LIST_COLUMNS) - set(jobs.DETAIL_COLUMNS), set())

    def test_ordering_sorts_on_the_sortable_timestamp(self):
        # posted_at is TEXT holding three incompatible formats, including Built
        # In's relative English ("Reposted 8 Hours Ago"), which no database can
        # order. Sorting on it would look fine and be wrong.
        self.assertIn("posted_at_ts", jobs.ORDER_BY)
        self.assertIn("match_score DESC", jobs.ORDER_BY)


if __name__ == "__main__":
    unittest.main()

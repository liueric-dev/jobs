"""Unit tests for the event-quality filters and borough derivation.

Run:  python3 pipelib/tests/test_event_quality.py

These cover the two pure pieces of the July 2026 quality pass:

  * schema.is_public_event -- decides which permitted_events rows are
    events at all. Both the ingest filter and migrate.py's delete run
    through it, so a change here silently deletes or re-admits rows in
    bulk. The precision cases matter most: the filter drops 2,590 of 6,457
    rows, and a substring match instead of a whole-title match would take
    real events with it.

  * boroughs.borough_from_park_ids -- the free path that resolves 943 of
    1,047 parks rows without a geometry lookup.

The point-in-polygon fallback is not unit-tested: it needs PostGIS and a
loaded boundary table, so it is exercised against the live database rather
than here.
"""

import importlib.util
import os
import sys
import unittest

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, _ROOT)
sys.path.insert(0, os.path.join(_ROOT, "events"))

import boroughs  # noqa: E402  (events/boroughs.py)


def _load(name, path):
    """Import a module by path, under a name that cannot collide.

    Both pipelines own a file called `schema.py` (events/ and jobs/) and both
    import it as bare `schema` after putting their own directory on the path.
    That is unambiguous when a script runs alone, but under `unittest
    discover` every test shares one interpreter, so whichever `schema` is
    imported first wins sys.modules and the other test silently gets the
    wrong module. Loading by path sidesteps the name entirely.
    """
    spec = importlib.util.spec_from_file_location(name, os.path.join(_ROOT, path))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


schema = _load("events_schema", "events/schema.py")


class TestIsPublicEvent(unittest.TestCase):

    def test_keeps_real_events(self):
        for title in ("Fort Greene Park Jazz Festival", "30th Avenue Fair",
                      "UNIA Founding Day Parade", "RiseBoro Farmers Markets",
                      "Classical Theatre of Harlem", "Pop-up cooling station"):
            self.assertTrue(schema.is_public_event(title, "Special Event"), title)

    def test_drops_generic_private_permits(self):
        for title in ("Miscellaneous", "Celebration", "Picnic", "Barbecue",
                      "Party", "Wedding ceremony", "Family Reunion"):
            self.assertFalse(schema.is_public_event(title, "Special Event"), title)

    def test_generic_match_is_whole_title_not_substring(self):
        """The 2,438-row win must not cost real events with the same word.

        "Picnic" is a private reservation; these are not.
        """
        for title in ("Picnic in the Park with the Philharmonic",
                      "Block Party on Dean Street",
                      "Celebration of Caribbean Heritage",
                      "Barbecue Cook-Off Championship"):
            self.assertTrue(schema.is_public_event(title, "Special Event"), title)

    def test_generic_match_ignores_case_and_padding(self):
        for title in ("  miscellaneous  ", "PICNIC", "Party"):
            self.assertFalse(schema.is_public_event(title, "Special Event"), title)

    def test_drops_closures_and_construction(self):
        for title in ("Lawn Closures & maintenance", "Construction", "closed",
                      "CROCHERON PARK GAZEBO CONSTRUCTION", "Turf Maintenance",
                      "Pilgrim Hill - Maintenance Days - Closed All Day"):
            self.assertFalse(schema.is_public_event(title, "Special Event"), title)

    def test_drops_facility_reservations_by_category(self):
        for category in ("Sport - Youth", "Sport - Adult",
                         "Theater Load in and Load Outs"):
            self.assertFalse(schema.is_public_event("League Game", category), category)

    def test_category_drop_beats_an_innocent_title(self):
        self.assertFalse(schema.is_public_event("Youth Soccer Finals", "Sport - Youth"))

    def test_handles_missing_title(self):
        for title in (None, "", "   "):
            self.assertTrue(schema.is_public_event(title, "Block Party"))


class TestBoroughFromParkIds(unittest.TestCase):

    def test_each_borough_prefix(self):
        self.assertEqual(boroughs.borough_from_park_ids("X045"), "Bronx")
        self.assertEqual(boroughs.borough_from_park_ids("B210W"), "Brooklyn")
        self.assertEqual(boroughs.borough_from_park_ids("M108Q1"), "Manhattan")
        self.assertEqual(boroughs.borough_from_park_ids("Q012B"), "Queens")
        self.assertEqual(boroughs.borough_from_park_ids("R038A"), "Staten Island")

    def test_multi_park_takes_the_first(self):
        """Citywide series list every site; the first beats NULL."""
        self.assertEqual(boroughs.borough_from_park_ids("Q099, R046, B057"), "Queens")

    def test_unknown_and_empty_are_none(self):
        for value in (None, "", "   ", "Z999", ","):
            self.assertIsNone(boroughs.borough_from_park_ids(value), repr(value))


if __name__ == "__main__":
    unittest.main()

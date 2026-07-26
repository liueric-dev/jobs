"""Unit tests for events/geocode.py's pure name-matching functions.

Split out of pipelib/tests/test_pipelib.py when geocode.py moved from
pipelib into events/: it has one consumer pipeline, so it lives with it.

These cover the park-name parser only. The point-in-polygon and Nominatim
paths need PostGIS and network access, so they are exercised against the
live database rather than here.
"""

import unittest

import sys, os
_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, _ROOT)
sys.path.insert(0, os.path.join(_ROOT, "events"))

import geocode  # noqa: E402  (events/geocode.py)


class TestParkNameMatching(unittest.TestCase):
    def test_park_name_split(self):
        self.assertEqual(geocode.park_name_of("Chelsea Park: Soccer-01"),
                         "Chelsea Park")
        self.assertEqual(
            geocode.park_name_of("Riverside Park: Lawn-145th Street West-RSP"),
            "Riverside Park")
        self.assertIsNone(geocode.park_name_of("MADISON AVE between E 42 and E 43"))
        self.assertIsNone(geocode.park_name_of(None))

    def test_candidates_cover_observed_mismatches(self):
        self.assertIn("thomas paine park",
                      list(geocode.candidates("Thomas Paine Park (Foley Square)")))
        self.assertIn("park of the americas",
                      list(geocode.candidates("Park Of The Americas / Linden Park")))
        self.assertIn("montefiore square park",
                      list(geocode.candidates("MontefioreSquarePark")))

    def test_candidates_are_deduped_and_ordered(self):
        got = list(geocode.candidates("Central Park"))
        self.assertEqual(got[0], "central park")
        self.assertEqual(len(got), len(set(got)))

    def test_normalize_strips_punctuation(self):
        self.assertEqual(geocode.normalize_name("Phil \"Scooter\" Rizzuto Park"),
                         "phil scooter rizzuto park")



if __name__ == "__main__":
    unittest.main()

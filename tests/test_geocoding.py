import unittest

from meteoblue_seeing.geocoding import (
    build_geocode_url,
    _is_british_isles_result,
    _simplify_result,
)
from meteoblue_seeing.validation import InputValidationError


class TestIsBritishIslesResult(unittest.TestCase):
    def test_republic_of_ireland_country_code_matches(self):
        item = {"country_code": "IE", "latitude": 53.27, "longitude": -9.05}
        self.assertTrue(_is_british_isles_result(item))

    def test_united_kingdom_country_code_matches(self):
        # GB covers Great Britain and Northern Ireland alike.
        item = {
            "country_code": "GB",
            "admin1": "Northern Ireland",
            "latitude": 54.6,
            "longitude": -5.9,
        }
        self.assertTrue(_is_british_isles_result(item))

    def test_great_britain_mainland_matches(self):
        item = {
            "country_code": "GB",
            "admin1": "England",
            "latitude": 51.5,
            "longitude": -0.12,
        }
        self.assertTrue(_is_british_isles_result(item))

    def test_scotland_matches(self):
        item = {
            "country_code": "GB",
            "admin1": "Scotland",
            "latitude": 55.95,
            "longitude": -3.19,
        }
        self.assertTrue(_is_british_isles_result(item))

    def test_isle_of_man_country_code_matches(self):
        item = {"country_code": "IM", "latitude": 54.15, "longitude": -4.48}
        self.assertTrue(_is_british_isles_result(item))

    def test_jersey_country_code_matches(self):
        item = {"country_code": "JE", "latitude": 49.18, "longitude": -2.11}
        self.assertTrue(_is_british_isles_result(item))

    def test_guernsey_country_code_matches(self):
        item = {"country_code": "GG", "latitude": 49.45, "longitude": -2.59}
        self.assertTrue(_is_british_isles_result(item))

    def test_faroe_islands_country_code_is_rejected(self):
        item = {"country_code": "FO", "latitude": 62.0, "longitude": -6.79}
        self.assertFalse(_is_british_isles_result(item))

    def test_continental_europe_is_rejected(self):
        item = {"country_code": "FR", "latitude": 48.85, "longitude": 2.35}
        self.assertFalse(_is_british_isles_result(item))

    def test_bounding_box_fallback_accepts_missing_country_code(self):
        item = {"latitude": 52.9, "longitude": -6.0}
        self.assertTrue(_is_british_isles_result(item))

    def test_bounding_box_fallback_rejects_far_away_point(self):
        item = {"latitude": 40.7, "longitude": -74.0}
        self.assertFalse(_is_british_isles_result(item))


class TestSimplifyResult(unittest.TestCase):
    def test_builds_a_readable_display_name(self):
        item = {
            "name": "Birr",
            "admin1": "County Offaly",
            "country": "Ireland",
            "country_code": "IE",
            "latitude": 53.0925,
            "longitude": -7.9107,
            "elevation": 63.0,
            "timezone": "Europe/Dublin",
        }
        simplified = _simplify_result(item)
        self.assertEqual(simplified["display_name"], "Birr, County Offaly, Ireland")
        self.assertEqual(simplified["latitude"], 53.0925)


class TestBuildGeocodeUrl(unittest.TestCase):
    def test_rejects_empty_query(self):
        with self.assertRaises(InputValidationError):
            build_geocode_url("   ")

    def test_url_contains_query_and_requests_extra_rows(self):
        url = build_geocode_url("Galway", limit=5)
        self.assertIn("name=Galway", url)
        self.assertIn("count=15", url)


if __name__ == "__main__":
    unittest.main()

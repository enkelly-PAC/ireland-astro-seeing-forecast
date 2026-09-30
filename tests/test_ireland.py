import unittest

from meteoblue_seeing import british_isles, ireland
from meteoblue_seeing.ireland import (
    IRELAND_MAX_LATITUDE,
    IRELAND_MAX_LONGITUDE,
    IRELAND_MIN_LATITUDE,
    IRELAND_MIN_LONGITUDE,
    is_within_ireland_region,
    validate_forecast_hours,
    validate_ireland_coordinates,
)
from meteoblue_seeing.validation import InputValidationError


class TestIrelandBackwardCompatibleAliases(unittest.TestCase):
    """The deprecated ``ireland`` module must keep working unchanged.

    It now re-exports the wider British Isles bounds under the original
    Ireland-branded names, so anything that previously imported from here
    keeps functioning, only with a wider accepted region.
    """

    def test_bounds_match_the_british_isles_module(self):
        self.assertEqual(IRELAND_MIN_LATITUDE, british_isles.BRITISH_ISLES_MIN_LATITUDE)
        self.assertEqual(IRELAND_MAX_LATITUDE, british_isles.BRITISH_ISLES_MAX_LATITUDE)
        self.assertEqual(IRELAND_MIN_LONGITUDE, british_isles.BRITISH_ISLES_MIN_LONGITUDE)
        self.assertEqual(IRELAND_MAX_LONGITUDE, british_isles.BRITISH_ISLES_MAX_LONGITUDE)

    def test_wicklow_head_is_valid(self):
        validate_ireland_coordinates(52.96544, -6.00233)

    def test_boundary_corners_are_valid(self):
        validate_ireland_coordinates(IRELAND_MIN_LATITUDE, IRELAND_MIN_LONGITUDE)
        validate_ireland_coordinates(IRELAND_MAX_LATITUDE, IRELAND_MAX_LONGITUDE)

    def test_paris_is_rejected(self):
        with self.assertRaises(InputValidationError):
            validate_ireland_coordinates(48.8566, 2.3522)

    def test_is_within_ireland_region_helper(self):
        self.assertTrue(is_within_ireland_region(53.27, -9.05))
        self.assertFalse(is_within_ireland_region(48.85, 2.35))

    def test_validate_forecast_hours_is_re_exported(self):
        self.assertEqual(validate_forecast_hours(96), 96)
        with self.assertRaises(InputValidationError):
            validate_forecast_hours(0)

    def test_ireland_module_is_an_alias_of_british_isles_functions(self):
        self.assertIs(
            ireland.validate_ireland_coordinates,
            british_isles.validate_british_isles_coordinates,
        )
        self.assertIs(
            ireland.is_within_ireland_region,
            british_isles.is_within_british_isles_region,
        )


if __name__ == "__main__":
    unittest.main()

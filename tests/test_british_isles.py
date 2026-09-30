import unittest

from meteoblue_seeing.british_isles import (
    BRITISH_ISLES_MAX_LATITUDE,
    BRITISH_ISLES_MAX_LONGITUDE,
    BRITISH_ISLES_MIN_LATITUDE,
    BRITISH_ISLES_MIN_LONGITUDE,
    is_within_british_isles_region,
    validate_british_isles_coordinates,
    validate_forecast_hours,
)
from meteoblue_seeing.validation import InputValidationError


class TestValidateBritishIslesCoordinates(unittest.TestCase):
    def test_wicklow_head_is_valid(self):
        validate_british_isles_coordinates(52.96544, -6.00233)

    def test_boundary_corners_are_valid(self):
        validate_british_isles_coordinates(
            BRITISH_ISLES_MIN_LATITUDE, BRITISH_ISLES_MIN_LONGITUDE
        )
        validate_british_isles_coordinates(
            BRITISH_ISLES_MAX_LATITUDE, BRITISH_ISLES_MAX_LONGITUDE
        )

    def test_london_is_valid(self):
        # Great Britain is now in scope, so London must be accepted.
        validate_british_isles_coordinates(51.5072, -0.1276)

    def test_edinburgh_is_valid(self):
        validate_british_isles_coordinates(55.9533, -3.1883)

    def test_shetland_lerwick_is_valid(self):
        validate_british_isles_coordinates(60.1547, -1.1494)

    def test_isle_of_man_douglas_is_valid(self):
        validate_british_isles_coordinates(54.1509, -4.4809)

    def test_channel_islands_jersey_is_valid(self):
        validate_british_isles_coordinates(49.1805, -2.1058)

    def test_outer_hebrides_stornoway_is_valid(self):
        validate_british_isles_coordinates(58.2093, -6.3861)

    def test_paris_is_rejected(self):
        with self.assertRaises(InputValidationError):
            validate_british_isles_coordinates(48.8566, 2.3522)

    def test_faroe_islands_are_rejected(self):
        # Sumba, the Faroe Islands' southernmost settlement, must stay
        # outside the region even though it is close to Shetland.
        with self.assertRaises(InputValidationError):
            validate_british_isles_coordinates(61.4, -6.71)

    def test_non_numeric_latitude_is_rejected(self):
        with self.assertRaises(InputValidationError):
            validate_british_isles_coordinates("52.9", -6.0)

    def test_boolean_latitude_is_rejected(self):
        with self.assertRaises(InputValidationError):
            validate_british_isles_coordinates(True, -6.0)

    def test_non_finite_longitude_is_rejected(self):
        with self.assertRaises(InputValidationError):
            validate_british_isles_coordinates(53.0, float("nan"))

    def test_is_within_british_isles_region_helper(self):
        self.assertTrue(is_within_british_isles_region(53.27, -9.05))
        self.assertTrue(is_within_british_isles_region(51.5072, -0.1276))
        self.assertFalse(is_within_british_isles_region(48.85, 2.35))


class TestValidateForecastHours(unittest.TestCase):
    def test_default_96_is_valid(self):
        self.assertEqual(validate_forecast_hours(96), 96)

    def test_bounds_are_inclusive(self):
        self.assertEqual(validate_forecast_hours(1), 1)
        self.assertEqual(validate_forecast_hours(120), 120)

    def test_zero_is_rejected(self):
        with self.assertRaises(InputValidationError):
            validate_forecast_hours(0)

    def test_above_120_is_rejected(self):
        with self.assertRaises(InputValidationError):
            validate_forecast_hours(121)

    def test_non_integer_is_rejected(self):
        with self.assertRaises(InputValidationError):
            validate_forecast_hours(48.5)

    def test_non_numeric_is_rejected(self):
        with self.assertRaises(InputValidationError):
            validate_forecast_hours("96")


if __name__ == "__main__":
    unittest.main()

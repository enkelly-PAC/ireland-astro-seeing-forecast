import unittest

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


class TestValidateIrelandCoordinates(unittest.TestCase):
    def test_wicklow_head_is_valid(self):
        validate_ireland_coordinates(52.96544, -6.00233)

    def test_boundary_corners_are_valid(self):
        validate_ireland_coordinates(IRELAND_MIN_LATITUDE, IRELAND_MIN_LONGITUDE)
        validate_ireland_coordinates(IRELAND_MAX_LATITUDE, IRELAND_MAX_LONGITUDE)

    def test_london_is_rejected(self):
        with self.assertRaises(InputValidationError):
            validate_ireland_coordinates(51.5072, -0.1276)

    def test_non_numeric_latitude_is_rejected(self):
        with self.assertRaises(InputValidationError):
            validate_ireland_coordinates("52.9", -6.0)

    def test_boolean_latitude_is_rejected(self):
        with self.assertRaises(InputValidationError):
            validate_ireland_coordinates(True, -6.0)

    def test_non_finite_longitude_is_rejected(self):
        with self.assertRaises(InputValidationError):
            validate_ireland_coordinates(53.0, float("nan"))

    def test_is_within_ireland_region_helper(self):
        self.assertTrue(is_within_ireland_region(53.27, -9.05))
        self.assertFalse(is_within_ireland_region(48.85, 2.35))


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

import unittest

from meteoblue_seeing.validation import ForecastInput, InputValidationError


def base_levels():
    return [
        {
            "altitude_m_asl": 500,
            "pressure_hpa": 950,
            "temperature_c": 15,
            "relative_humidity_pct": 50,
            "wind_u_ms": 1,
            "wind_v_ms": 1,
            "cloud_cover_pct": 0,
        },
        {
            "altitude_m_asl": 1500,
            "pressure_hpa": 850,
            "temperature_c": 10,
            "relative_humidity_pct": 50,
            "wind_u_ms": 1,
            "wind_v_ms": 1,
            "cloud_cover_pct": 0,
        },
    ]


class TestForecastInputValidation(unittest.TestCase):
    def test_valid_input_parses(self):
        payload = {"site_elevation_m_asl": 500, "levels": base_levels()}
        parsed = ForecastInput.from_dict(payload)
        self.assertEqual(len(parsed.levels), 2)
        self.assertEqual(parsed.site_elevation_m_asl, 500)

    def test_valid_time_is_normalised_to_utc(self):
        payload = {
            "site_elevation_m_asl": 500,
            "levels": base_levels(),
            "valid_time_utc": "2026-09-27T23:00:00+01:00",
        }
        parsed = ForecastInput.from_dict(payload)
        self.assertEqual(parsed.valid_time_utc.isoformat(), "2026-09-27T22:00:00+00:00")

    def test_valid_time_requires_offset(self):
        payload = {
            "site_elevation_m_asl": 500,
            "levels": base_levels(),
            "valid_time_utc": "2026-09-27T22:00:00",
        }
        with self.assertRaises(InputValidationError):
            ForecastInput.from_dict(payload)

    def test_missing_site_elevation(self):
        payload = {"levels": base_levels()}
        with self.assertRaises(InputValidationError):
            ForecastInput.from_dict(payload)

    def test_not_a_dict(self):
        with self.assertRaises(InputValidationError):
            ForecastInput.from_dict([1, 2, 3])

    def test_fewer_than_two_levels(self):
        payload = {"site_elevation_m_asl": 500, "levels": [base_levels()[0]]}
        with self.assertRaises(InputValidationError):
            ForecastInput.from_dict(payload)

    def test_missing_field_in_level(self):
        levels = base_levels()
        del levels[0]["temperature_c"]
        payload = {"site_elevation_m_asl": 500, "levels": levels}
        with self.assertRaises(InputValidationError):
            ForecastInput.from_dict(payload)

    def test_humidity_out_of_bounds(self):
        levels = base_levels()
        levels[0]["relative_humidity_pct"] = 150
        payload = {"site_elevation_m_asl": 500, "levels": levels}
        with self.assertRaises(InputValidationError):
            ForecastInput.from_dict(payload)

    def test_pressure_must_decrease_with_altitude(self):
        levels = base_levels()
        levels[1]["pressure_hpa"] = 960  # higher than level 0, invalid
        payload = {"site_elevation_m_asl": 500, "levels": levels}
        with self.assertRaises(InputValidationError):
            ForecastInput.from_dict(payload)

    def test_altitude_must_strictly_increase(self):
        levels = base_levels()
        levels[1]["altitude_m_asl"] = 500  # same as level 0, invalid
        payload = {"site_elevation_m_asl": 500, "levels": levels}
        with self.assertRaises(InputValidationError):
            ForecastInput.from_dict(payload)

    def test_non_numeric_field_rejected(self):
        levels = base_levels()
        levels[0]["temperature_c"] = "warm"
        payload = {"site_elevation_m_asl": 500, "levels": levels}
        with self.assertRaises(InputValidationError):
            ForecastInput.from_dict(payload)

    def test_wavelength_must_be_positive(self):
        payload = {
            "site_elevation_m_asl": 500,
            "levels": base_levels(),
            "wavelength_nm": -5,
        }
        with self.assertRaises(InputValidationError):
            ForecastInput.from_dict(payload)


if __name__ == "__main__":
    unittest.main()

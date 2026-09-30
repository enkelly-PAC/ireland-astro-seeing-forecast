import unittest
from unittest.mock import patch
from datetime import datetime, timezone

from meteoblue_seeing.wicklow_forecast import (
    PRESSURE_LEVELS_HPA,
    WICKLOW_HEAD_LATITUDE,
    WICKLOW_HEAD_LONGITUDE,
    WICKLOW_HEAD_NAME,
    _build_profile,
    _score_hour,
    _slugify,
    _solar_altitude_degrees,
    build_open_meteo_url,
    generate_location_forecast,
    generate_wicklow_forecast,
    render_html_report,
)
from meteoblue_seeing.validation import InputValidationError


def sample_api_payload():
    hourly = {
        "time": ["2026-09-27T22:00"],
        "cloud_cover": [20],
        "cloud_cover_low": [10],
        "cloud_cover_mid": [5],
        "cloud_cover_high": [12],
        "visibility": [20000],
    }
    heights = {
        1000: 120,
        925: 760,
        850: 1450,
        700: 3050,
        500: 5650,
        300: 9200,
        200: 11800,
    }
    temperatures = {
        1000: 12,
        925: 8,
        850: 4,
        700: -5,
        500: -22,
        300: -45,
        200: -56,
    }
    for pressure in PRESSURE_LEVELS_HPA:
        hourly[f"temperature_{pressure}hPa"] = [temperatures[pressure]]
        hourly[f"relative_humidity_{pressure}hPa"] = [50]
        hourly[f"wind_speed_{pressure}hPa"] = [36]
        hourly[f"wind_direction_{pressure}hPa"] = [270]
        hourly[f"geopotential_height_{pressure}hPa"] = [heights[pressure]]
    return {"hourly": hourly}


class TestWicklowForecast(unittest.TestCase):
    def test_url_requests_ukv_and_96_hours(self):
        url = build_open_meteo_url()
        self.assertIn("ukmo_seamless", url)
        self.assertIn("forecast_hours=96", url)
        self.assertIn("cloud_cover_high", url)

    def test_builds_valid_vertical_profile(self):
        profile = _build_profile(sample_api_payload(), 0)
        self.assertEqual(profile["valid_time_utc"], "2026-09-27T22:00:00Z")
        self.assertEqual(len(profile["levels"]), len(PRESSURE_LEVELS_HPA))
        self.assertGreater(
            profile["levels"][-1]["altitude_m_asl"],
            profile["levels"][0]["altitude_m_asl"],
        )
        self.assertLess(
            profile["levels"][-1]["pressure_hpa"],
            profile["levels"][0]["pressure_hpa"],
        )

    def test_clamps_model_supersaturation(self):
        payload = sample_api_payload()
        payload["hourly"]["relative_humidity_700hPa"] = [103]
        profile = _build_profile(payload, 0)
        level = next(
            item for item in profile["levels"] if item["pressure_hpa"] == 700
        )
        self.assertEqual(level["relative_humidity_pct"], 100.0)

    def test_solar_altitude_is_below_horizon_at_night(self):
        altitude = _solar_altitude_degrees(
            datetime(2026, 9, 27, 23, tzinfo=timezone.utc),
            52.96544,
            -6.00233,
        )
        self.assertLess(altitude, -18)

    def test_scores_use_ten_as_best(self):
        combined = {
            "display": {"index": 5, "arcsec": 0.49},
            "observability": {"estimated_clear_sky_pct": 100},
        }
        score = _score_hour(combined, 20000, -25)
        self.assertEqual(score["seeing_score_1_10"], 10)
        self.assertEqual(score["imaging_score_1_10"], 10)
        self.assertEqual(score["observing_score_1_10"], 10)

    def test_daylight_forces_observing_score_to_one(self):
        combined = {
            "display": {"index": 5, "arcsec": 0.49},
            "observability": {"estimated_clear_sky_pct": 100},
        }
        score = _score_hour(combined, 20000, 30)
        self.assertEqual(score["seeing_score_1_10"], 10)
        self.assertEqual(score["imaging_score_1_10"], 10)
        self.assertEqual(score["observing_score_1_10"], 1)

    def test_renders_report(self):
        report = {
            "forecast_hours": 1,
            "generated_at_utc": "2026-09-27T21:00:00Z",
            "forecasts": [
                {
                    "local_time": "2026-09-27T23:00:00+01:00",
                    "scores": {
                        "light_state": "astronomical night",
                        "seeing_score_1_10": 8,
                        "imaging_score_1_10": 8,
                        "observing_score_1_10": 7,
                    },
                    "cloud_bands": {
                        "total_cloud_pct": 20,
                        "low_cloud_pct": 10,
                        "mid_cloud_pct": 5,
                        "high_cloud_pct": 12,
                    },
                    "display": {"arcsec": 1.2},
                    "jet_stream": {"speed_ms": 20},
                }
            ],
        }
        output = render_html_report(report)
        self.assertIn("Wicklow Head astronomy forecast", output)
        self.assertIn("Seeing 1-10", output)
        self.assertIn("8</span>", output)

    def test_renders_report_with_generic_location_name(self):
        report = {
            "location": {"name": "Galway City, County Galway, Ireland"},
            "forecast_hours": 1,
            "generated_at_utc": "2026-09-27T21:00:00Z",
            "forecasts": [
                {
                    "local_time": "2026-09-27T23:00:00+01:00",
                    "scores": {
                        "light_state": "astronomical night",
                        "seeing_score_1_10": 5,
                        "imaging_score_1_10": 4,
                        "observing_score_1_10": 5,
                    },
                    "cloud_bands": {
                        "total_cloud_pct": 40,
                        "low_cloud_pct": 20,
                        "mid_cloud_pct": 10,
                        "high_cloud_pct": 10,
                    },
                    "display": {"arcsec": 2.0},
                    "jet_stream": {"speed_ms": 25},
                }
            ],
        }
        output = render_html_report(report)
        self.assertIn("Galway City astronomy forecast", output)
        self.assertNotIn("Wicklow Head astronomy forecast", output)


class TestSlugify(unittest.TestCase):
    def test_slugifies_a_full_location_name(self):
        self.assertEqual(
            _slugify("Galway City, County Galway, Ireland"),
            "galway-city-county-galway-ireland",
        )

    def test_falls_back_to_location_for_empty_input(self):
        self.assertEqual(_slugify("!!!"), "location")


class TestGenerateLocationForecast(unittest.TestCase):
    def test_validates_coordinates_before_any_network_call(self):
        with self.assertRaises(InputValidationError):
            # Paris, France: continental Europe is out of scope.
            generate_location_forecast(48.8566, 2.3522, "Paris")

    def test_validates_hours_before_any_network_call(self):
        with self.assertRaises(InputValidationError):
            generate_location_forecast(53.27, -9.05, "Galway", forecast_hours=200)

    def test_uses_model_grid_elevation_from_open_meteo(self):
        payload = sample_api_payload()
        payload["elevation"] = 63.0
        with patch(
            "meteoblue_seeing.wicklow_forecast.fetch_ukv_forecast",
            return_value=payload,
        ):
            report = generate_location_forecast(
                53.0925, -7.9107, "Birr, County Offaly, Ireland", forecast_hours=1
            )
        self.assertEqual(report["location"]["site_elevation_m_asl"], 63.0)
        self.assertEqual(report["location"]["name"], "Birr, County Offaly, Ireland")
        self.assertIn("astronomy", report)
        self.assertIn("moon", report["forecasts"][0]["body_positions"])
        self.assertIn("rise_local", report["astronomy"]["days"][0]["bodies"]["moon"])
        self.assertNotEqual(
            report["location"]["site_elevation_m_asl"], 84.0
        )  # not the Wicklow constant

    def test_missing_elevation_defaults_to_zero(self):
        payload = sample_api_payload()
        with patch(
            "meteoblue_seeing.wicklow_forecast.fetch_ukv_forecast",
            return_value=payload,
        ):
            report = generate_location_forecast(
                53.27, -9.05, "Galway City, Ireland", forecast_hours=1
            )
        self.assertEqual(report["location"]["site_elevation_m_asl"], 0.0)


class TestGenerateWicklowForecastBackwardCompatibility(unittest.TestCase):
    def test_wraps_generate_location_forecast_with_wicklow_defaults(self):
        payload = sample_api_payload()
        payload["elevation"] = 84.0
        with patch(
            "meteoblue_seeing.wicklow_forecast.fetch_ukv_forecast",
            return_value=payload,
        ) as mocked_fetch:
            report = generate_wicklow_forecast(forecast_hours=1)
        mocked_fetch.assert_called_once_with(
            1, WICKLOW_HEAD_LATITUDE, WICKLOW_HEAD_LONGITUDE
        )
        self.assertEqual(report["location"]["name"], WICKLOW_HEAD_NAME)
        self.assertEqual(report["location"]["latitude"], WICKLOW_HEAD_LATITUDE)
        self.assertEqual(report["location"]["longitude"], WICKLOW_HEAD_LONGITUDE)


if __name__ == "__main__":
    unittest.main()

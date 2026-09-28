import json
import unittest
from pathlib import Path

from meteoblue_seeing.config import SeeingConfig
from meteoblue_seeing.forecast import run_forecast
from meteoblue_seeing.validation import InputValidationError

SAMPLE_INPUT_PATH = Path(__file__).resolve().parent.parent / "data" / "sample_input.json"


class TestRunForecast(unittest.TestCase):
    def setUp(self):
        with open(SAMPLE_INPUT_PATH, "r", encoding="utf-8") as handle:
            self.sample_payload = json.load(handle)

    def test_sample_forecast_end_to_end(self):
        result = run_forecast(self.sample_payload)

        self.assertIn("model1", result)
        self.assertIn("model2", result)
        self.assertIn("display", result)
        self.assertIn("bad_layer", result)
        self.assertIn("jet_stream", result)
        self.assertIn("cloud_bands", result)
        self.assertIn("cat_layer_count", result)

        self.assertGreater(result["model1"]["seeing_arcsec"], 0.0)
        self.assertGreater(result["model2"]["seeing_arcsec"], 0.0)
        self.assertIn(result["model1"]["seeing_index"], range(1, 6))
        self.assertIn(result["model2"]["seeing_index"], range(1, 6))

        self.assertIsNotNone(result["bad_layer"])
        self.assertAlmostEqual(result["bad_layer"]["bottom_m"], 3000)
        self.assertAlmostEqual(result["bad_layer"]["top_m"], 5000)

        self.assertIsNotNone(result["jet_stream"])
        self.assertAlmostEqual(result["jet_stream"]["pressure_hpa"], 200.0)
        self.assertEqual(result["jet_stream"]["rating"], "poor")

        self.assertTrue(result["display"]["bad_layer_penalty_applied"])
        self.assertGreater(result["display"]["arcsec"], 0.0)

        # Sample input includes a level at 5000 m ASL (within the 4 to 8 km
        # band) with cloud_cover_pct explicitly set to 0, so the band is
        # reported (as 0.0), not omitted.
        self.assertEqual(result["cloud_bands"]["mid_4_8km_pct"], 0.0)

        # result must be JSON serialisable end to end
        json.dumps(result)

    def test_inline_jet_threshold_config_changes_label(self):
        cfg = SeeingConfig(use_inline_jet_threshold=True)
        result = run_forecast(self.sample_payload, cfg)
        self.assertAlmostEqual(result["jet_stream"]["threshold_high_ms"], 20.0)
        self.assertEqual(
            result["meta"]["method_labels"]["jet_stream_threshold"],
            "PUBLICLY_DOCUMENTED_INLINE_20MS",
        )

    def test_missing_levels_raises(self):
        payload = {"site_elevation_m_asl": 500, "levels": []}
        with self.assertRaises(InputValidationError):
            run_forecast(payload)

    def test_single_level_raises(self):
        payload = {
            "site_elevation_m_asl": 500,
            "levels": [
                {
                    "altitude_m_asl": 500,
                    "pressure_hpa": 950,
                    "temperature_c": 15,
                    "relative_humidity_pct": 50,
                    "wind_u_ms": 1,
                    "wind_v_ms": 1,
                    "cloud_cover_pct": 0,
                }
            ],
        }
        with self.assertRaises(InputValidationError):
            run_forecast(payload)

    def test_out_of_order_altitude_raises(self):
        payload = {
            "site_elevation_m_asl": 500,
            "levels": [
                {
                    "altitude_m_asl": 1500,
                    "pressure_hpa": 850,
                    "temperature_c": 10,
                    "relative_humidity_pct": 50,
                    "wind_u_ms": 1,
                    "wind_v_ms": 1,
                    "cloud_cover_pct": 0,
                },
                {
                    "altitude_m_asl": 500,
                    "pressure_hpa": 950,
                    "temperature_c": 15,
                    "relative_humidity_pct": 50,
                    "wind_u_ms": 1,
                    "wind_v_ms": 1,
                    "cloud_cover_pct": 0,
                },
            ],
        }
        with self.assertRaises(InputValidationError):
            run_forecast(payload)

    def test_non_finite_number_raises(self):
        payload = {
            "site_elevation_m_asl": 500,
            "levels": [
                {
                    "altitude_m_asl": 500,
                    "pressure_hpa": 950,
                    "temperature_c": float("nan"),
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
            ],
        }
        with self.assertRaises(InputValidationError):
            run_forecast(payload)


if __name__ == "__main__":
    unittest.main()

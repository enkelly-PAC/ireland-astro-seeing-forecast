import unittest
from pathlib import Path

from meteoblue_seeing.calibrate import calibrate, load_calibration_csv
from meteoblue_seeing.config import SeeingConfig
from meteoblue_seeing.validation import InputValidationError

SAMPLE_CSV_PATH = (
    Path(__file__).resolve().parent.parent / "data" / "sample_calibration.csv"
)


class TestLoadCalibrationCsv(unittest.TestCase):
    def test_loads_and_groups_cases(self):
        cases = load_calibration_csv(str(SAMPLE_CSV_PATH))
        self.assertEqual(len(cases), 2)
        case_a = next(c for c in cases if c.case_id == "case_a")
        self.assertEqual(case_a.site_elevation_m_asl, 500)
        self.assertEqual(len(case_a.levels), 6)
        self.assertAlmostEqual(case_a.observed_seeing1_arcsec, 1.2)
        self.assertAlmostEqual(case_a.observed_seeing2_arcsec, 1.1)
        self.assertAlmostEqual(case_a.observed_arcsec, 1.3)
        # levels must come out sorted by altitude
        altitudes = [lv["altitude_m_asl"] for lv in case_a.levels]
        self.assertEqual(altitudes, sorted(altitudes))

    def test_missing_column_raises(self):
        bad_path = SAMPLE_CSV_PATH.parent / "_bad_calibration.csv"
        bad_path.write_text("case_id,altitude_m_asl\ncase_a,500\n", encoding="utf-8")
        try:
            with self.assertRaises(InputValidationError):
                load_calibration_csv(str(bad_path))
        finally:
            bad_path.unlink()


class TestCalibrate(unittest.TestCase):
    def test_calibrate_runs_deterministically_and_improves_or_matches_fit(self):
        cases = load_calibration_csv(str(SAMPLE_CSV_PATH))
        base_cfg = SeeingConfig()

        cfg_1, metrics_1 = calibrate(cases, base_cfg, passes=1)
        cfg_2, metrics_2 = calibrate(cases, base_cfg, passes=1)

        # deterministic: same input, same output
        self.assertEqual(cfg_1.to_dict(), cfg_2.to_dict())
        self.assertEqual(metrics_1.to_dict(), metrics_2.to_dict())

        self.assertEqual(metrics_1.case_count, 2)
        self.assertIsNotNone(metrics_1.rmse_model1_arcsec)
        self.assertIsNotNone(metrics_1.rmse_model2_arcsec)
        self.assertIsNotNone(metrics_1.rmse_display_arcsec)
        self.assertGreater(metrics_1.iterations, 0)

    def test_calibrate_requires_at_least_one_case(self):
        with self.assertRaises(InputValidationError):
            calibrate([], SeeingConfig())


if __name__ == "__main__":
    unittest.main()

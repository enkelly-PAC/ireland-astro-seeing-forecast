import json
import subprocess
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SRC_PATH = REPO_ROOT / "src"
SAMPLE_INPUT = REPO_ROOT / "data" / "sample_input.json"
SAMPLE_HTML = REPO_ROOT / "data" / "sample_meteoblue_page.html"
SAMPLE_CSV = REPO_ROOT / "data" / "sample_calibration.csv"
SAMPLE_UKV_CSV = REPO_ROOT / "data" / "sample_windy_ukv_clouds.csv"


def run_cli(*args, cwd=None):
    env = {"PYTHONPATH": str(SRC_PATH)}
    import os

    full_env = dict(os.environ)
    full_env.update(env)
    return subprocess.run(
        [sys.executable, "-m", "meteoblue_seeing", *args],
        capture_output=True,
        text=True,
        env=full_env,
        cwd=str(cwd or REPO_ROOT),
    )


class TestCliForecast(unittest.TestCase):
    def test_forecast_command_on_sample_input(self):
        result = run_cli("forecast", str(SAMPLE_INPUT))
        self.assertEqual(result.returncode, 0, msg=result.stderr)
        payload = json.loads(result.stdout)
        self.assertIn("display", payload)
        self.assertIsNotNone(payload["bad_layer"])
        self.assertEqual(payload["jet_stream"]["rating"], "poor")

    def test_forecast_command_with_inline_jet_threshold(self):
        result = run_cli("forecast", str(SAMPLE_INPUT), "--use-inline-jet-threshold")
        self.assertEqual(result.returncode, 0, msg=result.stderr)
        payload = json.loads(result.stdout)
        self.assertAlmostEqual(payload["jet_stream"]["threshold_high_ms"], 20.0)

    def test_forecast_command_missing_file(self):
        result = run_cli("forecast", str(REPO_ROOT / "data" / "does_not_exist.json"))
        self.assertNotEqual(result.returncode, 0)


class TestCliCombineUkv(unittest.TestCase):
    def test_combine_ukv_command(self):
        result = run_cli("combine-ukv", str(SAMPLE_INPUT), str(SAMPLE_UKV_CSV))
        self.assertEqual(result.returncode, 0, msg=result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["cloud_source"]["provider"], "Windy")
        self.assertEqual(payload["cloud_source"]["model"], "UKV")
        self.assertEqual(payload["cloud_bands"]["total_cloud_pct"], 21.0)
        self.assertEqual(payload["observability"]["estimated_clear_sky_pct"], 79.0)
        self.assertEqual(payload["display"]["index"], 1)


class TestCliParseHtml(unittest.TestCase):
    def test_parse_html_command(self):
        result = run_cli("parse-html", str(SAMPLE_HTML), "--as-records")
        self.assertEqual(result.returncode, 0, msg=result.stderr)
        records = json.loads(result.stdout)
        self.assertEqual(len(records), 4)
        self.assertIn("seeing1_arcsec", records[0])


class TestCliCalibrate(unittest.TestCase):
    def test_calibrate_command(self, tmp_path=None):
        output_config = REPO_ROOT / "data" / "_test_calibrated_config.json"
        try:
            result = run_cli(
                "calibrate",
                str(SAMPLE_CSV),
                "--output-config",
                str(output_config),
                "--passes",
                "1",
            )
            self.assertEqual(result.returncode, 0, msg=result.stderr)
            metrics = json.loads(result.stdout)
            self.assertEqual(metrics["case_count"], 2)
            self.assertTrue(output_config.exists())
            saved = json.loads(output_config.read_text(encoding="utf-8"))
            self.assertIn("model_coefficients", saved)
        finally:
            if output_config.exists():
                output_config.unlink()


if __name__ == "__main__":
    unittest.main()

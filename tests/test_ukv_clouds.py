import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from meteoblue_seeing.ukv_clouds import (
    UkvCloudForecast,
    combine_forecast_with_ukv_cloud,
    load_windy_ukv_csv,
    match_ukv_cloud,
)
from meteoblue_seeing.validation import InputValidationError


class TestUkvCloudCsv(unittest.TestCase):
    def test_loads_and_sorts_rows(self):
        text = (
            "valid_time_utc,low_cloud_pct,mid_cloud_pct,high_cloud_pct,total_cloud_pct\n"
            "2026-09-27T23:00:00Z,5,4,9,16\n"
            "2026-09-27T22:00:00Z,8,5,12,21\n"
        )
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "clouds.csv"
            path.write_text(text, encoding="utf-8")
            rows = load_windy_ukv_csv(path)
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0].valid_time_utc.hour, 22)
        self.assertEqual(rows[0].total_cloud_pct, 21.0)

    def test_rejects_invalid_percentage(self):
        text = (
            "valid_time_utc,low_cloud_pct,mid_cloud_pct,high_cloud_pct\n"
            "2026-09-27T22:00:00Z,101,5,12\n"
        )
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "clouds.csv"
            path.write_text(text, encoding="utf-8")
            with self.assertRaises(InputValidationError):
                load_windy_ukv_csv(path)


class TestUkvCloudCombination(unittest.TestCase):
    def setUp(self):
        self.rows = [
            UkvCloudForecast(
                valid_time_utc=datetime(2026, 9, 27, 21, tzinfo=timezone.utc),
                low_cloud_pct=50,
                mid_cloud_pct=20,
                high_cloud_pct=10,
                total_cloud_pct=None,
            ),
            UkvCloudForecast(
                valid_time_utc=datetime(2026, 9, 27, 22, tzinfo=timezone.utc),
                low_cloud_pct=8,
                mid_cloud_pct=5,
                high_cloud_pct=12,
                total_cloud_pct=21,
            ),
        ]

    def test_matches_nearest_time(self):
        target = datetime(2026, 9, 27, 21, 50, tzinfo=timezone.utc)
        row, offset = match_ukv_cloud(self.rows, target, 30)
        self.assertEqual(row.valid_time_utc.hour, 22)
        self.assertAlmostEqual(offset, 10.0)

    def test_rejects_match_outside_tolerance(self):
        target = datetime(2026, 9, 28, 1, tzinfo=timezone.utc)
        with self.assertRaises(InputValidationError):
            match_ukv_cloud(self.rows, target, 30)

    def test_combines_clouds_without_changing_seeing(self):
        seeing = {
            "meta": {"valid_time_utc": "2026-09-27T22:00:00Z"},
            "cloud_bands": {
                "low_0_4km_pct": 90,
                "mid_4_8km_pct": 90,
                "high_8_15km_pct": 90,
            },
            "display": {"index": 5, "arcsec": 0.7},
        }
        combined = combine_forecast_with_ukv_cloud(seeing, self.rows[1], 0.0)
        self.assertEqual(combined["display"], seeing["display"])
        self.assertEqual(combined["cloud_bands"]["low_cloud_pct"], 8)
        self.assertEqual(combined["cloud_bands"]["total_cloud_pct"], 21)
        self.assertEqual(combined["profile_cloud_bands"]["low_0_4km_pct"], 90)
        self.assertEqual(combined["observability"]["estimated_clear_sky_pct"], 79)
        self.assertEqual(combined["observability"]["score_0_100"], 79)
        self.assertEqual(combined["cloud_source"]["model"], "UKV")


if __name__ == "__main__":
    unittest.main()

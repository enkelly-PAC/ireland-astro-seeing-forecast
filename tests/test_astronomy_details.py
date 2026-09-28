import unittest
from datetime import datetime, timezone

from meteoblue_seeing.astronomy_details import (
    BODY_DEFINITIONS,
    _moon_phase_name,
    astronomy_days,
    body_positions,
)


class TestAstronomyDetails(unittest.TestCase):
    def test_includes_moon_and_planets(self):
        names = [name for _key, name, _body in BODY_DEFINITIONS]
        self.assertEqual(names[0], "Moon")
        self.assertIn("Mercury", names)
        self.assertIn("Neptune", names)
        self.assertIn("Pluto", names)

    def test_moon_phase_names(self):
        self.assertEqual(_moon_phase_name(0), "New Moon")
        self.assertEqual(_moon_phase_name(90), "First quarter")
        self.assertEqual(_moon_phase_name(180), "Full Moon")
        self.assertEqual(_moon_phase_name(270), "Third quarter")

    def test_positions_include_altitude_and_azimuth(self):
        positions = body_positions(
            52.96544,
            -6.00233,
            84.0,
            datetime(2026, 9, 28, 22, tzinfo=timezone.utc),
        )
        self.assertEqual(len(positions), len(BODY_DEFINITIONS))
        self.assertIn("altitude_degrees", positions["moon"])
        self.assertIn("azimuth_degrees", positions["jupiter"])
        self.assertGreaterEqual(positions["moon"]["azimuth_degrees"], 0)
        self.assertLess(positions["moon"]["azimuth_degrees"], 360)

    def test_daily_details_include_events_and_moon_phase(self):
        details = astronomy_days(
            52.96544,
            -6.00233,
            84.0,
            [
                datetime(2026, 9, 28, 0, tzinfo=timezone.utc),
                datetime(2026, 9, 29, 0, tzinfo=timezone.utc),
            ],
        )
        self.assertEqual(details["timezone"], "Europe/Dublin")
        self.assertGreaterEqual(len(details["days"]), 2)
        moon = details["days"][0]["bodies"]["moon"]
        self.assertIsNotNone(moon["rise_local"])
        self.assertIsNotNone(moon["meridian_local"])
        self.assertIsNotNone(moon["set_local"])
        self.assertEqual(moon["rise_local"][:10], "2026-09-28")
        self.assertEqual(moon["meridian_local"][:10], "2026-09-29")
        self.assertEqual(moon["set_local"][:10], "2026-09-29")
        rise = datetime.fromisoformat(moon["rise_local"])
        meridian = datetime.fromisoformat(moon["meridian_local"])
        setting = datetime.fromisoformat(moon["set_local"])
        self.assertLess(rise, meridian)
        self.assertLess(meridian, setting)
        self.assertIn("phase_name", moon)
        self.assertGreater(moon["culmination_altitude_degrees"], -90)
        self.assertLess(moon["culmination_altitude_degrees"], 90)


if __name__ == "__main__":
    unittest.main()

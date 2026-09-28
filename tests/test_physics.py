import math
import unittest

from meteoblue_seeing.config import SeeingConfig
from meteoblue_seeing.physics import (
    build_layer_interfaces,
    compute_cloud_bands,
    find_strongest_bad_layer,
    potential_temperature_k,
    sample_jet_stream,
)
from meteoblue_seeing.validation import Level


def make_level(altitude, pressure, temp_c, rh=30.0, u=0.0, v=0.0, cloud=0.0):
    return Level(
        altitude_m_asl=altitude,
        pressure_hpa=pressure,
        temperature_c=temp_c,
        relative_humidity_pct=rh,
        wind_u_ms=u,
        wind_v_ms=v,
        cloud_cover_pct=cloud,
    )


class TestPotentialTemperature(unittest.TestCase):
    def test_matches_hand_calculation(self):
        cfg = SeeingConfig()
        # theta = T * (1000/p) ** (Rd/cp); at p = 1000 hPa theta == T (kelvin).
        theta = potential_temperature_k(15.0, 1000.0, cfg)
        self.assertAlmostEqual(theta, 15.0 + 273.15, places=6)

    def test_increases_with_altitude_for_fixed_temperature(self):
        cfg = SeeingConfig()
        theta_low = potential_temperature_k(10.0, 900.0, cfg)
        theta_high = potential_temperature_k(10.0, 700.0, cfg)
        self.assertGreater(theta_high, theta_low)


class TestBadLayerDetection(unittest.TestCase):
    def test_no_bad_layer_for_normal_lapse(self):
        cfg = SeeingConfig()
        levels = [
            make_level(0, 1000, 20.0),
            make_level(1000, 900, 13.5),
            make_level(2000, 800, 7.0),
        ]
        interfaces = build_layer_interfaces(levels, cfg)
        bad_layer = find_strongest_bad_layer(interfaces, cfg)
        self.assertIsNone(bad_layer)

    def test_single_marginal_interface_below_2k_is_not_reported(self):
        cfg = SeeingConfig()
        # Construct a gradient just at the per-interface threshold but with
        # a small total theta jump (< 2 K), so accumulation rule rejects it.
        levels = [
            make_level(0, 1000, 20.0),
            make_level(100, 990, 20.6),  # small inversion, short layer
        ]
        interfaces = build_layer_interfaces(levels, cfg)
        theta_jump = interfaces[0].theta_top_k - interfaces[0].theta_bottom_k
        self.assertLess(theta_jump, cfg.bad_layer_theta_jump_threshold_k)
        bad_layer = find_strongest_bad_layer(interfaces, cfg)
        self.assertIsNone(bad_layer)

    def test_strong_inversion_is_reported_and_merged(self):
        cfg = SeeingConfig()
        levels = [
            make_level(0, 1000, 20.0),
            make_level(1000, 900, 13.5),
            make_level(3000, 700, 2.0),
            make_level(4000, 620, 8.0),
            make_level(5000, 540, 10.0),
            make_level(7000, 410, -8.0),
        ]
        interfaces = build_layer_interfaces(levels, cfg)
        bad_layer = find_strongest_bad_layer(interfaces, cfg)
        self.assertIsNotNone(bad_layer)
        self.assertAlmostEqual(bad_layer.bottom_m, 3000)
        self.assertAlmostEqual(bad_layer.top_m, 5000)
        self.assertGreaterEqual(bad_layer.theta_jump_k, cfg.bad_layer_theta_jump_threshold_k)
        self.assertEqual(bad_layer.interface_count, 2)


class TestRichardsonAndCAT(unittest.TestCase):
    def test_zero_shear_gives_no_richardson_number(self):
        cfg = SeeingConfig()
        levels = [
            make_level(0, 1000, 20.0, u=5.0, v=5.0),
            make_level(1000, 900, 13.5, u=5.0, v=5.0),
        ]
        interfaces = build_layer_interfaces(levels, cfg)
        self.assertIsNone(interfaces[0].richardson_number)
        self.assertFalse(interfaces[0].cat_flag)

    def test_low_richardson_number_flags_cat(self):
        cfg = SeeingConfig()
        # Weak stability, strong shear -> low Ri -> CAT flag.
        levels = [
            make_level(0, 1000, 15.0, u=0.0, v=0.0),
            make_level(200, 978, 15.3, u=20.0, v=0.0),
        ]
        interfaces = build_layer_interfaces(levels, cfg)
        interface = interfaces[0]
        self.assertIsNotNone(interface.richardson_number)
        self.assertLessEqual(interface.richardson_number, cfg.ri_cat_threshold)
        self.assertTrue(interface.cat_flag)

    def test_high_richardson_number_no_cat(self):
        cfg = SeeingConfig()
        levels = [
            make_level(0, 1000, 15.0, u=0.0, v=0.0),
            make_level(1000, 900, 30.0, u=1.0, v=0.0),
        ]
        interfaces = build_layer_interfaces(levels, cfg)
        interface = interfaces[0]
        self.assertIsNotNone(interface.richardson_number)
        self.assertGreater(interface.richardson_number, cfg.ri_cat_threshold)
        self.assertFalse(interface.cat_flag)


class TestJetStream(unittest.TestCase):
    def test_exact_200hpa_level(self):
        cfg = SeeingConfig()
        levels = [
            make_level(0, 1000, 15.0),
            make_level(9000, 300, -40.0, u=10, v=0),
            make_level(11800, 200, -56.0, u=40, v=30),
            make_level(13000, 170, -58.0, u=20, v=10),
        ]
        jet = sample_jet_stream(levels, cfg)
        self.assertIsNotNone(jet)
        self.assertAlmostEqual(jet.pressure_hpa, 200.0)
        self.assertAlmostEqual(jet.speed_ms, math.hypot(40, 30))
        self.assertFalse(jet.interpolated)
        self.assertEqual(jet.rating, "poor")  # 50 m/s > 35 m/s default threshold

    def test_interpolated_level_between_brackets(self):
        cfg = SeeingConfig()
        levels = [
            make_level(0, 1000, 15.0),
            make_level(9000, 250, -45.0, u=0, v=0),
            make_level(11000, 150, -55.0, u=20, v=0),
        ]
        jet = sample_jet_stream(levels, cfg)
        self.assertIsNotNone(jet)
        self.assertTrue(jet.interpolated)
        self.assertGreater(jet.speed_ms, 0.0)
        self.assertLess(jet.speed_ms, 20.0)

    def test_out_of_range_returns_none(self):
        cfg = SeeingConfig()
        levels = [
            make_level(0, 1000, 15.0),
            make_level(1000, 900, 10.0),
        ]
        jet = sample_jet_stream(levels, cfg)
        self.assertIsNone(jet)

    def test_inline_threshold_option_changes_rating(self):
        cfg = SeeingConfig(use_inline_jet_threshold=True)
        levels = [
            make_level(0, 1000, 15.0),
            make_level(9000, 300, -40.0, u=10, v=0),
            make_level(11800, 200, -56.0, u=25, v=0),
        ]
        jet = sample_jet_stream(levels, cfg)
        self.assertIsNotNone(jet)
        self.assertAlmostEqual(jet.threshold_high_ms, 20.0)
        self.assertEqual(jet.rating, "poor")  # 25 m/s > 20 m/s inline threshold


class TestCloudBands(unittest.TestCase):
    def test_bands_are_independent_and_use_max(self):
        cfg = SeeingConfig()
        levels = [
            make_level(500, 950, 15.0, cloud=20),
            make_level(2000, 800, 5.0, cloud=60),
            make_level(6000, 450, -20.0, cloud=10),
            make_level(10000, 250, -50.0, cloud=0),
        ]
        bands = compute_cloud_bands(levels, cfg)
        self.assertEqual(bands.low_0_4km_pct, 60)
        self.assertEqual(bands.mid_4_8km_pct, 10)
        self.assertEqual(bands.high_8_15km_pct, 0)

    def test_missing_band_is_none(self):
        cfg = SeeingConfig()
        levels = [
            make_level(500, 950, 15.0, cloud=20),
            make_level(2000, 800, 5.0, cloud=60),
        ]
        bands = compute_cloud_bands(levels, cfg)
        self.assertIsNone(bands.mid_4_8km_pct)
        self.assertIsNone(bands.high_8_15km_pct)


if __name__ == "__main__":
    unittest.main()

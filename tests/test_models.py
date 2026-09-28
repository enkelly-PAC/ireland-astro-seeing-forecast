import math
import unittest

from meteoblue_seeing.config import SeeingConfig
from meteoblue_seeing.models import (
    air_density_kg_m3,
    combine_cn2_profiles,
    fried_parameter_m,
    integrate_cn2,
    refractivity_n_units,
    saturation_vapour_pressure_hpa,
    seeing_arcsec,
    seeing_index,
    seeing_score_1_10,
    water_vapour_pressure_hpa,
)
from meteoblue_seeing.physics import build_layer_interfaces
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


class TestHumidityAndRefractivity(unittest.TestCase):
    def test_saturation_vapour_pressure_increases_with_temperature(self):
        self.assertLess(
            saturation_vapour_pressure_hpa(0.0), saturation_vapour_pressure_hpa(20.0)
        )

    def test_water_vapour_pressure_scales_with_rh(self):
        low = water_vapour_pressure_hpa(20.0, 25.0)
        high = water_vapour_pressure_hpa(20.0, 75.0)
        self.assertLess(low, high)
        self.assertAlmostEqual(high / low, 3.0, places=6)

    def test_refractivity_dry_term_dominates_at_low_humidity(self):
        n_dry = refractivity_n_units(1000.0, 15.0, 0.0)
        n_humid = refractivity_n_units(1000.0, 15.0, 90.0)
        self.assertGreater(n_humid, n_dry)

    def test_air_density_decreases_with_altitude_like_pressure(self):
        cfg = SeeingConfig()
        rho_surface = air_density_kg_m3(1000.0, 15.0, cfg)
        rho_upper = air_density_kg_m3(700.0, 2.0, cfg)
        self.assertGreater(rho_surface, rho_upper)


class TestCn2AndSeeing(unittest.TestCase):
    def setUp(self):
        self.cfg = SeeingConfig()
        self.levels = [
            make_level(500, 950, 18.0, rh=55, u=2, v=1),
            make_level(1500, 850, 11.5, rh=50, u=6, v=3),
            make_level(3000, 700, 2.0, rh=40, u=12, v=6),
            make_level(4000, 620, 8.0, rh=25, u=20, v=10),
            make_level(5000, 540, 10.0, rh=20, u=28, v=13),
            make_level(9000, 300, -35.0, rh=10, u=46, v=20),
        ]

    def test_cn2_values_are_nonnegative(self):
        interfaces = build_layer_interfaces(self.levels, self.cfg)
        cn2_interfaces = combine_cn2_profiles(self.levels, interfaces, self.cfg)
        for interface in cn2_interfaces:
            self.assertGreaterEqual(interface.cn2_model1_m_negtwothirds, 0.0)
            self.assertGreaterEqual(interface.cn2_model2_m_negtwothirds, 0.0)

    def test_bad_layer_boosts_model1_integral(self):
        interfaces = build_layer_interfaces(self.levels, self.cfg)
        cn2_interfaces = combine_cn2_profiles(self.levels, interfaces, self.cfg)
        integral_with_inversion = integrate_cn2(cn2_interfaces, "cn2_model1_m_negtwothirds")

        calm_levels = [
            make_level(500, 950, 18.0, rh=55, u=2, v=1),
            make_level(1500, 850, 13.0, rh=50, u=3, v=1.5),
            make_level(3000, 700, 3.5, rh=40, u=4, v=2),
            make_level(4000, 620, -2.0, rh=25, u=5, v=2.5),
            make_level(5000, 540, -8.0, rh=20, u=6, v=3),
            make_level(9000, 300, -35.0, rh=10, u=8, v=4),
        ]
        calm_interfaces = build_layer_interfaces(calm_levels, self.cfg)
        calm_cn2 = combine_cn2_profiles(calm_levels, calm_interfaces, self.cfg)
        integral_calm = integrate_cn2(calm_cn2, "cn2_model1_m_negtwothirds")

        self.assertGreater(integral_with_inversion, integral_calm)

    def test_r0_and_seeing_are_finite_and_positive(self):
        interfaces = build_layer_interfaces(self.levels, self.cfg)
        cn2_interfaces = combine_cn2_profiles(self.levels, interfaces, self.cfg)
        integral = integrate_cn2(cn2_interfaces, "cn2_model1_m_negtwothirds")
        r0 = fried_parameter_m(integral, 500.0)
        self.assertTrue(math.isfinite(r0))
        self.assertGreater(r0, 0.0)
        arcsec = seeing_arcsec(r0, 500.0)
        self.assertTrue(math.isfinite(arcsec))
        self.assertGreater(arcsec, 0.0)

    def test_zero_integral_gives_zero_seeing(self):
        arcsec = seeing_arcsec(float("inf"), 500.0)
        self.assertEqual(arcsec, 0.0)

    def test_seeing_index_monotonic_and_bounded(self):
        cfg = SeeingConfig()
        values = [0.1, 0.8, 1.3, 2.0, 3.0, 10.0]
        indices = [seeing_index(v, cfg) for v in values]
        self.assertEqual(indices, sorted(indices, reverse=True))
        self.assertEqual(indices[0], 5)
        self.assertEqual(indices[-1], 1)
        for idx in indices:
            self.assertGreaterEqual(idx, 1)
            self.assertLessEqual(idx, 5)

    def test_direct_arcsecond_to_ten_point_score(self):
        cfg = SeeingConfig()
        cases = (
            (0.49, 10),
            (0.5, 9),
            (0.69, 9),
            (0.7, 8),
            (1.0, 8),
            (1.5, 7),
            (2.0, 6),
            (2.5, 5),
            (2.74, 4),
            (3.0, 4),
            (4.0, 3),
            (5.0, 2),
            (5.01, 1),
        )
        for arcsec, expected in cases:
            with self.subTest(arcsec=arcsec):
                self.assertEqual(seeing_score_1_10(arcsec, cfg), expected)


if __name__ == "__main__":
    unittest.main()

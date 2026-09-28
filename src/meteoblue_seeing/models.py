"""Empirical Cn2 profile models, vertical integration and seeing conversion.

Two independent, transparent Cn2 (refractive index structure constant)
models are built from the same input levels:

  Model 1 emphasises thermal stability (potential temperature gradient),
  wind shear / CAT activity, and pressure-temperature refractivity scaling.

  Model 2 gives more weight to density/refractivity fluctuations (via the
  ideal gas law) and to humidity gradients (via the Smith-Weintraub
  refractivity formula's wet term).

Both are STANDARD PHYSICS in functional form (they use recognised
turbulence-optics building blocks: the temperature structure parameter,
shear generation of turbulence, and atmospheric refractivity), but their
scaling coefficients are INFERRED/CALIBRATABLE, see config.py and README.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from .config import SeeingConfig
from .physics import KELVIN_OFFSET, LayerInterface
from .validation import Level


def saturation_vapour_pressure_hpa(temperature_c: float) -> float:
    """STANDARD PHYSICS: Tetens' formula for saturation vapour pressure
    over water, in hPa, accurate to about 0.1 percent over typical
    tropospheric temperatures.
    """

    return 6.1078 * 10 ** ((7.5 * temperature_c) / (temperature_c + 237.3))


def water_vapour_pressure_hpa(temperature_c: float, relative_humidity_pct: float) -> float:
    """STANDARD PHYSICS: actual water vapour partial pressure from RH."""

    return saturation_vapour_pressure_hpa(temperature_c) * (relative_humidity_pct / 100.0)


def refractivity_n_units(pressure_hpa: float, temperature_c: float, relative_humidity_pct: float) -> float:
    """STANDARD PHYSICS: Smith-Weintraub formula for microwave/optical-ish
    atmospheric refractivity, in N-units:

        N = 77.6 * P / T + 3.73e5 * e / T ** 2

    P is total pressure in hPa, e is water vapour partial pressure in hPa,
    T is temperature in kelvin. The first (dry) term dominates for visible
    light seeing calculations; the second (wet) term is retained so that
    humidity gradients contribute to Model 2, as requested.
    """

    temperature_k = temperature_c + KELVIN_OFFSET
    e = water_vapour_pressure_hpa(temperature_c, relative_humidity_pct)
    dry_term = 77.6 * pressure_hpa / temperature_k
    wet_term = 3.73e5 * e / (temperature_k ** 2)
    return dry_term + wet_term


def air_density_kg_m3(pressure_hpa: float, temperature_c: float, cfg: SeeingConfig) -> float:
    """STANDARD PHYSICS: ideal gas law, dry air approximation.

        rho = P / (R_d * T)

    P is converted from hPa to Pa.
    """

    temperature_k = temperature_c + KELVIN_OFFSET
    pressure_pa = pressure_hpa * 100.0
    return pressure_pa / (cfg.r_specific_dry_air_j_kgk * temperature_k)


@dataclass
class Cn2Interface:
    index_bottom: int
    index_top: int
    altitude_bottom_m: float
    altitude_top_m: float
    dz_m: float
    cn2_model1_m_negtwothirds: float
    cn2_model2_m_negtwothirds: float


def build_cn2_model1(
    levels: list[Level], interfaces: list[LayerInterface], cfg: SeeingConfig
) -> list[Cn2Interface]:
    """STANDARD PHYSICS functional form, INFERRED coefficients.

    Model 1 combines:
      - the squared potential temperature gradient (thermal stability, the
        classical driver of the temperature structure parameter Ct^2), and
      - shear generated turbulence enhancement, boosted further when the
        interface is flagged as clear air turbulence (CAT, Ri <= 0.25),
        and
      - a pressure/temperature refractivity scaling factor, since the
        conversion from temperature fluctuations to refractive index
        fluctuations depends on ambient pressure and temperature
        (dn/dT ~ -77.6e-6 * P / T ** 2, from the dry term of the
        Smith-Weintraub relation).
    """

    coeffs = cfg.model_coefficients
    results: list[Cn2Interface] = []

    for i, interface in enumerate(interfaces):
        bottom, top = levels[interface.index_bottom], levels[interface.index_top]
        p_mid = 0.5 * (bottom.pressure_hpa + top.pressure_hpa)
        t_mid_k = 0.5 * (bottom.temperature_c + top.temperature_c) + KELVIN_OFFSET

        dn_dt = 77.6e-6 * p_mid / (t_mid_k ** 2)  # per kelvin, dry term only
        refractivity_scale = coeffs.model1_refractivity_weight * (dn_dt ** 2) * 1.0e12

        stability_term = coeffs.model1_theta_gradient_weight * (interface.dtheta_dz_k_per_m ** 2)
        shear_term = 1.0 + coeffs.model1_shear_weight * interface.shear_sq_s2
        if interface.cat_flag:
            shear_term *= coeffs.model1_cat_boost

        cn2 = max(0.0, stability_term * shear_term * refractivity_scale)

        results.append(
            Cn2Interface(
                index_bottom=interface.index_bottom,
                index_top=interface.index_top,
                altitude_bottom_m=interface.altitude_bottom_m,
                altitude_top_m=interface.altitude_top_m,
                dz_m=interface.dz_m,
                cn2_model1_m_negtwothirds=cn2,
                cn2_model2_m_negtwothirds=0.0,  # filled in later
            )
        )

    return results


def build_cn2_model2(
    levels: list[Level], interfaces: list[LayerInterface], cfg: SeeingConfig
) -> list[float]:
    """STANDARD PHYSICS functional form, INFERRED coefficients.

    Model 2 gives more weight to:
      - refractivity fluctuations driven by air density differences between
        adjacent levels (ideal gas law), and
      - humidity gradients, via the wet term of the Smith-Weintraub
        refractivity formula,
    with a smaller contribution from the same thermal stability term used
    in Model 1 (a cross term, since temperature and humidity fluctuations
    are not fully independent in the real atmosphere).
    """

    coeffs = cfg.model_coefficients
    values: list[float] = []

    for interface in interfaces:
        bottom, top = levels[interface.index_bottom], levels[interface.index_top]
        dz = interface.dz_m

        rho_bottom = air_density_kg_m3(bottom.pressure_hpa, bottom.temperature_c, cfg)
        rho_top = air_density_kg_m3(top.pressure_hpa, top.temperature_c, cfg)
        d_rho_dz = (rho_top - rho_bottom) / dz
        # Normalise by a representative density so the density term is
        # dimensionless-ish and comparable in scale to the other terms.
        rho_ref = 0.5 * (rho_bottom + rho_top)
        density_term = coeffs.model2_density_weight * ((d_rho_dz / rho_ref) ** 2)

        n_bottom = refractivity_n_units(bottom.pressure_hpa, bottom.temperature_c, bottom.relative_humidity_pct)
        n_top = refractivity_n_units(top.pressure_hpa, top.temperature_c, top.relative_humidity_pct)
        dn_dz = (n_top - n_bottom) / dz

        rh_bottom = bottom.relative_humidity_pct
        rh_top = top.relative_humidity_pct
        d_rh_dz = (rh_top - rh_bottom) / dz
        humidity_term = coeffs.model2_humidity_gradient_weight * (d_rh_dz ** 2) * 1.0e-6

        cross_term = coeffs.model2_cross_term_weight * abs(interface.dtheta_dz_k_per_m) * abs(d_rh_dz) * 1.0e-3

        stability_term = coeffs.model2_theta_gradient_weight * (interface.dtheta_dz_k_per_m ** 2)

        refractivity_fluct_term = (dn_dz ** 2) * 1.0e-8

        raw_sum = (
            density_term + humidity_term + cross_term + stability_term + refractivity_fluct_term
        )
        cn2 = max(0.0, raw_sum * coeffs.model2_overall_scale)
        values.append(cn2)

    return values


def combine_cn2_profiles(
    levels: list[Level], interfaces: list[LayerInterface], cfg: SeeingConfig
) -> list[Cn2Interface]:
    model1 = build_cn2_model1(levels, interfaces, cfg)
    model2_values = build_cn2_model2(levels, interfaces, cfg)
    for interface, cn2_2 in zip(model1, model2_values):
        interface.cn2_model2_m_negtwothirds = cn2_2
    return model1


def integrate_cn2(cn2_interfaces: list[Cn2Interface], attr: str) -> float:
    """STANDARD PHYSICS: trapezoidal integration of Cn2(z) over altitude.

    Since Cn2 is only computed at layer interfaces (midpoints between two
    input levels are implicit in each interface value), each interface
    value is treated as constant across its own dz and multiplied by dz;
    this is equivalent to a midpoint rule, a standard and conservative
    choice for coarse, irregularly spaced radiosonde-like input levels.
    """

    total = 0.0
    for interface in cn2_interfaces:
        value = getattr(interface, attr)
        total += value * interface.dz_m
    return total


def fried_parameter_m(cn2_integral: float, wavelength_nm: float) -> float:
    """STANDARD PHYSICS: Fried parameter.

        r0 = [0.423 * k ** 2 * integral(Cn2 dz)] ** (-3/5)

    k = 2 * pi / lambda, lambda in metres.
    """

    if cn2_integral <= 0:
        return float("inf")
    wavelength_m = wavelength_nm * 1.0e-9
    k = 2.0 * math.pi / wavelength_m
    return (0.423 * (k ** 2) * cn2_integral) ** (-3.0 / 5.0)


ARCSEC_PER_RADIAN = 206264.80624709636


def seeing_arcsec(r0_m: float, wavelength_nm: float) -> float:
    """STANDARD PHYSICS: seeing disc full width at half maximum.

        epsilon = 0.98 * lambda / r0   (radians)

    converted to arcseconds.
    """

    if not math.isfinite(r0_m) or r0_m <= 0:
        return 0.0
    wavelength_m = wavelength_nm * 1.0e-9
    epsilon_rad = 0.98 * wavelength_m / r0_m
    return epsilon_rad * ARCSEC_PER_RADIAN


def seeing_index(arcsec: float, cfg: SeeingConfig) -> int:
    """INFERRED/CALIBRATABLE: map an arcsecond seeing estimate to a 1
    (very poor) to 5 (excellent) index using configurable thresholds.
    """

    thresholds = cfg.seeing_index_thresholds
    if arcsec <= thresholds.excellent_max:
        return 5
    if arcsec <= thresholds.good_max:
        return 4
    if arcsec <= thresholds.average_max:
        return 3
    if arcsec <= thresholds.poor_max:
        return 2
    return 1


def seeing_score_1_10(arcsec: float, cfg: SeeingConfig) -> int:
    """Approximate an informal Pickering score from FWHM arcseconds.

    Pickering is a subjective visual scale, so this conversion is intended
    as a practical guide rather than a formal equivalence.
    """

    thresholds = cfg.seeing_score_thresholds
    if arcsec < thresholds.score_10_max_exclusive:
        return 10
    if arcsec < thresholds.score_9_max_exclusive:
        return 9
    if arcsec <= thresholds.score_8_max:
        return 8
    if arcsec <= thresholds.score_7_max:
        return 7
    if arcsec <= thresholds.score_6_max:
        return 6
    if arcsec <= thresholds.score_5_max:
        return 5
    if arcsec <= thresholds.score_4_max:
        return 4
    if arcsec <= thresholds.score_3_max:
        return 3
    if arcsec <= thresholds.score_2_max:
        return 2
    return 1

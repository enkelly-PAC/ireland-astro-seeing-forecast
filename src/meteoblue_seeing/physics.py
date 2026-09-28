"""Core atmospheric optics physics.

Confidence labels are noted on each function:

  PUBLICLY DOCUMENTED   - reproduces a rule stated in meteoblue's own help
                          text (see README for exact URLs and quotes).
  STANDARD PHYSICS      - a textbook equation of atmospheric thermodynamics,
                          dynamics or optics, independent of meteoblue.
  INFERRED/CALIBRATABLE - our own construction, not found in any public
                          source, intended to be refined via calibration.
"""

from __future__ import annotations

from dataclasses import dataclass

from .config import SeeingConfig
from .validation import Level

KELVIN_OFFSET = 273.15


def potential_temperature_k(temperature_c: float, pressure_hpa: float, cfg: SeeingConfig) -> float:
    """STANDARD PHYSICS: Poisson's equation for potential temperature.

        theta = T * (P0 / P) ** (R_d / c_p)

    T is in kelvin, P0 is the reference pressure (1000 hPa), P is the level
    pressure in hPa, R_d is the specific gas constant for dry air and c_p is
    the specific heat capacity of dry air at constant pressure.
    """

    temperature_k = temperature_c + KELVIN_OFFSET
    kappa = cfg.r_specific_dry_air_j_kgk / cfg.c_p_dry_air_j_kgk
    return temperature_k * (cfg.reference_pressure_hpa / pressure_hpa) ** kappa


@dataclass
class LayerInterface:
    """Derived quantities for the interface between two adjacent levels."""

    index_bottom: int
    index_top: int
    altitude_bottom_m: float
    altitude_top_m: float
    dz_m: float
    theta_bottom_k: float
    theta_top_k: float
    dtheta_dz_k_per_m: float
    du_dz_s_inv: float
    dv_dz_s_inv: float
    shear_sq_s2: float
    richardson_number: float | None
    cat_flag: bool
    bad_layer_gradient_flag: bool


def build_layer_interfaces(levels: list[Level], cfg: SeeingConfig) -> list[LayerInterface]:
    """STANDARD PHYSICS + PUBLICLY DOCUMENTED thresholds.

    Computes, for every pair of vertically adjacent input levels, the
    potential temperature gradient, the horizontal wind shear, the gradient
    Richardson number, the clear air turbulence (CAT) flag (Ri <= 0.25) and
    the meteoblue "bad layer" adjacent gradient flag
    (dtheta/dz >= 0.005 K/m, equivalently 0.5 K per 100 m).
    """

    interfaces: list[LayerInterface] = []
    thetas = [potential_temperature_k(lv.temperature_c, lv.pressure_hpa, cfg) for lv in levels]

    for i in range(len(levels) - 1):
        bottom, top = levels[i], levels[i + 1]
        dz = top.altitude_m_asl - bottom.altitude_m_asl
        dtheta = thetas[i + 1] - thetas[i]
        dtheta_dz = dtheta / dz

        du_dz = (top.wind_u_ms - bottom.wind_u_ms) / dz
        dv_dz = (top.wind_v_ms - bottom.wind_v_ms) / dz
        shear_sq = du_dz * du_dz + dv_dz * dv_dz

        theta_ref = 0.5 * (thetas[i] + thetas[i + 1])
        if shear_sq < cfg.min_shear_sq_s2:
            # STANDARD numerical safeguard: with (near) zero shear the
            # gradient Richardson number is undefined/infinite. A positive
            # (stable) dtheta/dz with no shear is treated as infinitely
            # stable (no CAT); a negative (unstable) dtheta/dz with no shear
            # is treated as infinitely unstable (Ri -> -inf, still flagged
            # as CAT-relevant via the sign, but conservatively reported as
            # None here since no wind driven turbulence generation exists).
            richardson = None
            cat = False
        else:
            richardson = (cfg.gravity_m_s2 / theta_ref) * dtheta_dz / shear_sq
            cat = richardson <= cfg.ri_cat_threshold

        bad_gradient = dtheta_dz >= cfg.bad_layer_gradient_threshold_k_per_m

        interfaces.append(
            LayerInterface(
                index_bottom=i,
                index_top=i + 1,
                altitude_bottom_m=bottom.altitude_m_asl,
                altitude_top_m=top.altitude_m_asl,
                dz_m=dz,
                theta_bottom_k=thetas[i],
                theta_top_k=thetas[i + 1],
                dtheta_dz_k_per_m=dtheta_dz,
                du_dz_s_inv=du_dz,
                dv_dz_s_inv=dv_dz,
                shear_sq_s2=shear_sq,
                richardson_number=richardson,
                cat_flag=cat,
                bad_layer_gradient_flag=bad_gradient,
            )
        )

    return interfaces


@dataclass
class BadLayer:
    bottom_m: float
    top_m: float
    theta_jump_k: float
    mean_gradient_k_per_m: float
    interface_count: int


def find_strongest_bad_layer(
    interfaces: list[LayerInterface], cfg: SeeingConfig
) -> BadLayer | None:
    """PUBLICLY DOCUMENTED bad-layer criteria.

    The Meteosurf method linked from meteoblue specifies both an adjacent
    potential-temperature gradient of at least 0.5 K per 100 m
    (0.005 K/m) and a total potential-temperature difference of at least
    2 K across the layer. Contiguous qualifying interfaces are merged into
    runs, then the strongest qualifying run is reported. Selecting one run
    when several qualify is an implementation choice.
    """

    runs: list[list[LayerInterface]] = []
    current: list[LayerInterface] = []
    for interface in interfaces:
        if interface.bad_layer_gradient_flag:
            current.append(interface)
        else:
            if current:
                runs.append(current)
            current = []
    if current:
        runs.append(current)

    candidates: list[BadLayer] = []
    for run in runs:
        theta_bottom = run[0].theta_bottom_k
        theta_top = run[-1].theta_top_k
        theta_jump = theta_top - theta_bottom
        if theta_jump >= cfg.bad_layer_theta_jump_threshold_k:
            total_dz = run[-1].altitude_top_m - run[0].altitude_bottom_m
            mean_gradient = theta_jump / total_dz if total_dz > 0 else 0.0
            candidates.append(
                BadLayer(
                    bottom_m=run[0].altitude_bottom_m,
                    top_m=run[-1].altitude_top_m,
                    theta_jump_k=theta_jump,
                    mean_gradient_k_per_m=mean_gradient,
                    interface_count=len(run),
                )
            )

    if not candidates:
        return None

    return max(candidates, key=lambda bl: bl.theta_jump_k)


@dataclass
class JetSample:
    pressure_hpa: float
    speed_ms: float
    u_ms: float
    v_ms: float
    rating: str
    threshold_high_ms: float
    threshold_low_ms: float
    interpolated: bool


def sample_jet_stream(levels: list[Level], cfg: SeeingConfig) -> JetSample | None:
    """PUBLICLY DOCUMENTED: jet stream sampled at 200 hPa.

    If the exact pressure level is present it is used directly. Otherwise
    the wind components are linearly interpolated in log-pressure between
    the two bracketing levels (STANDARD PHYSICS convention: wind and most
    thermodynamic fields vary closer to linearly in log-pressure than in
    pressure itself). Returns None if the target pressure lies outside the
    supplied profile.
    """

    import math

    target = cfg.jet_pressure_hpa
    pressures = [lv.pressure_hpa for lv in levels]

    for lv in levels:
        if abs(lv.pressure_hpa - target) < 1e-9:
            u, v, interpolated = lv.wind_u_ms, lv.wind_v_ms, False
            break
    else:
        # pressures are strictly decreasing with index (validated upstream)
        bracket = None
        for i in range(len(levels) - 1):
            p_hi, p_lo = pressures[i], pressures[i + 1]
            if p_lo <= target <= p_hi:
                bracket = (i, i + 1)
                break
        if bracket is None:
            return None
        i_lo, i_hi = bracket
        lv_lo, lv_hi = levels[i_lo], levels[i_hi]
        log_p_lo = math.log(lv_lo.pressure_hpa)
        log_p_hi = math.log(lv_hi.pressure_hpa)
        log_p_t = math.log(target)
        frac = (log_p_t - log_p_lo) / (log_p_hi - log_p_lo)
        u = lv_lo.wind_u_ms + frac * (lv_hi.wind_u_ms - lv_lo.wind_u_ms)
        v = lv_lo.wind_v_ms + frac * (lv_hi.wind_v_ms - lv_lo.wind_v_ms)
        interpolated = True

    speed = math.hypot(u, v)
    high = cfg.jet_high_threshold_ms()
    low = cfg.jet_low_threshold_ms
    if speed > high or speed < low:
        rating = "poor"
    else:
        rating = "good"

    return JetSample(
        pressure_hpa=target,
        speed_ms=speed,
        u_ms=u,
        v_ms=v,
        rating=rating,
        threshold_high_ms=high,
        threshold_low_ms=low,
        interpolated=interpolated,
    )


@dataclass
class CloudBands:
    low_0_4km_pct: float | None
    mid_4_8km_pct: float | None
    high_8_15km_pct: float | None


def compute_cloud_bands(levels: list[Level], cfg: SeeingConfig) -> CloudBands:
    """PUBLICLY DOCUMENTED: cloud cover reported in three ASL bands,
    independent of the seeing calculation. We take the maximum reported
    cloud_cover_pct among levels whose altitude falls within each band, as
    a simple, transparent aggregation. A band with no supplied level
    returns None.
    """

    def band_max(lo: float, hi: float) -> float | None:
        values = [
            lv.cloud_cover_pct
            for lv in levels
            if lo <= lv.altitude_m_asl < hi
        ]
        return max(values) if values else None

    lo_lo, lo_hi = cfg.cloud_band_low_m
    mid_lo, mid_hi = cfg.cloud_band_mid_m
    hi_lo, hi_hi = cfg.cloud_band_high_m

    return CloudBands(
        low_0_4km_pct=band_max(lo_lo, lo_hi),
        mid_4_8km_pct=band_max(mid_lo, mid_hi),
        high_8_15km_pct=band_max(hi_lo, hi_hi),
    )

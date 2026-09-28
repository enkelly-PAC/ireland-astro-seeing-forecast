"""Deterministic, bounded calibration utility.

Takes CSV rows describing one or more atmospheric profiles ("cases"),
grouped by a ``case_id`` column, each with the same fields required by a
forecast input level, plus observed meteoblue output values
(``observed_seeing1_arcsec``, ``observed_seeing2_arcsec``,
``observed_arcsec``). It performs a deterministic coordinate-wise grid
search over a small, documented set of Model 1 / Model 2 coefficients and
the display blend/penalty parameters, minimising the summed squared error
against the observed values, and writes a fitted ``SeeingConfig`` JSON file
plus a fit metrics report.

Standard library only (``csv``, ``json``, ``math``, ``dataclasses``,
``itertools``). This is intentionally simple and bounded: it is a practical
starting point for refining the INFERRED coefficients in config.py against
a permitted, user-supplied black box dataset, not a general purpose
optimiser.
"""

from __future__ import annotations

import copy
import csv
import math
from dataclasses import dataclass, field
from typing import Any

from .config import SeeingConfig
from .forecast import run_forecast
from .validation import InputValidationError

REQUIRED_LEVEL_FIELDS = (
    "altitude_m_asl",
    "pressure_hpa",
    "temperature_c",
    "relative_humidity_pct",
    "wind_u_ms",
    "wind_v_ms",
    "cloud_cover_pct",
)

# The small, documented set of coefficients we allow calibration to adjust,
# expressed as multipliers of the SeeingConfig default value. Kept small and
# bounded on purpose, per the task requirements.
CANDIDATE_MULTIPLIERS: tuple[float, ...] = (0.25, 0.5, 0.75, 1.0, 1.5, 2.0, 3.0)

TUNABLE_COEFFICIENTS: tuple[str, ...] = (
    "model_coefficients.model1_theta_gradient_weight",
    "model_coefficients.model1_shear_weight",
    "model_coefficients.model1_cat_boost",
    "model_coefficients.model1_refractivity_weight",
    "model_coefficients.model2_theta_gradient_weight",
    "model_coefficients.model2_humidity_gradient_weight",
    "model_coefficients.model2_density_weight",
    "model_coefficients.model2_cross_term_weight",
    "model_coefficients.model2_overall_scale",
    "bad_layer_penalty_factor",
)


@dataclass
class CalibrationCase:
    case_id: str
    levels: list[dict[str, float]]
    site_elevation_m_asl: float
    wavelength_nm: float | None
    observed_seeing1_arcsec: float | None
    observed_seeing2_arcsec: float | None
    observed_arcsec: float | None

    def to_payload(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "site_elevation_m_asl": self.site_elevation_m_asl,
            "levels": self.levels,
        }
        if self.wavelength_nm is not None:
            payload["wavelength_nm"] = self.wavelength_nm
        return payload


def _to_float(value: str) -> float | None:
    value = (value or "").strip()
    if value == "":
        return None
    return float(value)


def load_calibration_csv(path: str) -> list[CalibrationCase]:
    """Read a calibration CSV and group its rows into cases.

    Expected columns (extra columns are ignored):
      case_id, site_elevation_m_asl, altitude_m_asl, pressure_hpa,
      temperature_c, relative_humidity_pct, wind_u_ms, wind_v_ms,
      cloud_cover_pct, wavelength_nm (optional),
      observed_seeing1_arcsec, observed_seeing2_arcsec, observed_arcsec
      (the three observed columns only need a value on one row per case).
    """

    by_case: dict[str, dict[str, Any]] = {}
    order: list[str] = []

    with open(path, "r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None:
            raise InputValidationError("calibration CSV has no header row")
        missing = [f for f in REQUIRED_LEVEL_FIELDS if f not in reader.fieldnames]
        if "case_id" not in reader.fieldnames:
            missing.append("case_id")
        if "site_elevation_m_asl" not in reader.fieldnames:
            missing.append("site_elevation_m_asl")
        if missing:
            raise InputValidationError(
                "calibration CSV missing required column(s): " + ", ".join(missing)
            )

        for row_index, row in enumerate(reader):
            case_id = (row.get("case_id") or "").strip()
            if not case_id:
                raise InputValidationError(f"row {row_index}: empty case_id")
            if case_id not in by_case:
                by_case[case_id] = {
                    "levels": [],
                    "site_elevation_m_asl": None,
                    "wavelength_nm": None,
                    "observed_seeing1_arcsec": None,
                    "observed_seeing2_arcsec": None,
                    "observed_arcsec": None,
                }
                order.append(case_id)
            bucket = by_case[case_id]

            level = {}
            for field_name in REQUIRED_LEVEL_FIELDS:
                raw = row.get(field_name)
                if raw is None or raw.strip() == "":
                    raise InputValidationError(
                        f"row {row_index} (case {case_id}): missing value for "
                        f"'{field_name}'"
                    )
                level[field_name] = float(raw)
            bucket["levels"].append(level)

            if bucket["site_elevation_m_asl"] is None:
                elevation = _to_float(row.get("site_elevation_m_asl", ""))
                if elevation is not None:
                    bucket["site_elevation_m_asl"] = elevation
            if bucket["wavelength_nm"] is None:
                wavelength = _to_float(row.get("wavelength_nm", ""))
                if wavelength is not None:
                    bucket["wavelength_nm"] = wavelength
            for observed_key in (
                "observed_seeing1_arcsec",
                "observed_seeing2_arcsec",
                "observed_arcsec",
            ):
                if bucket[observed_key] is None:
                    value = _to_float(row.get(observed_key, ""))
                    if value is not None:
                        bucket[observed_key] = value

    cases: list[CalibrationCase] = []
    for case_id in order:
        bucket = by_case[case_id]
        levels = sorted(bucket["levels"], key=lambda lv: lv["altitude_m_asl"])
        if len(levels) < 2:
            raise InputValidationError(
                f"case '{case_id}' has fewer than two levels after grouping"
            )
        if bucket["site_elevation_m_asl"] is None:
            raise InputValidationError(
                f"case '{case_id}' is missing site_elevation_m_asl"
            )
        cases.append(
            CalibrationCase(
                case_id=case_id,
                levels=levels,
                site_elevation_m_asl=bucket["site_elevation_m_asl"],
                wavelength_nm=bucket["wavelength_nm"],
                observed_seeing1_arcsec=bucket["observed_seeing1_arcsec"],
                observed_seeing2_arcsec=bucket["observed_seeing2_arcsec"],
                observed_arcsec=bucket["observed_arcsec"],
            )
        )
    return cases


def _get_path(cfg: SeeingConfig, dotted: str) -> float:
    obj: Any = cfg
    parts = dotted.split(".")
    for part in parts[:-1]:
        obj = getattr(obj, part)
    return getattr(obj, parts[-1])


def _set_path(cfg: SeeingConfig, dotted: str, value: float) -> None:
    obj: Any = cfg
    parts = dotted.split(".")
    for part in parts[:-1]:
        obj = getattr(obj, part)
    setattr(obj, parts[-1], value)


@dataclass
class FitMetrics:
    case_count: int
    rmse_model1_arcsec: float | None
    rmse_model2_arcsec: float | None
    rmse_display_arcsec: float | None
    iterations: int
    coefficient_path_order: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "case_count": self.case_count,
            "rmse_model1_arcsec": self.rmse_model1_arcsec,
            "rmse_model2_arcsec": self.rmse_model2_arcsec,
            "rmse_display_arcsec": self.rmse_display_arcsec,
            "iterations": self.iterations,
            "coefficient_search_order": self.coefficient_path_order,
        }


def _evaluate(cfg: SeeingConfig, cases: list[CalibrationCase]) -> tuple[float, dict[str, float | None]]:
    sq_error_1 = 0.0
    n1 = 0
    sq_error_2 = 0.0
    n2 = 0
    sq_error_d = 0.0
    nd = 0

    for case in cases:
        result = run_forecast(case.to_payload(), cfg)
        if case.observed_seeing1_arcsec is not None:
            diff = result["model1"]["seeing_arcsec"] - case.observed_seeing1_arcsec
            sq_error_1 += diff * diff
            n1 += 1
        if case.observed_seeing2_arcsec is not None:
            diff = result["model2"]["seeing_arcsec"] - case.observed_seeing2_arcsec
            sq_error_2 += diff * diff
            n2 += 1
        if case.observed_arcsec is not None:
            diff = result["display"]["arcsec"] - case.observed_arcsec
            sq_error_d += diff * diff
            nd += 1

    rmse1 = math.sqrt(sq_error_1 / n1) if n1 else None
    rmse2 = math.sqrt(sq_error_2 / n2) if n2 else None
    rmsed = math.sqrt(sq_error_d / nd) if nd else None

    total = 0.0
    for value in (rmse1, rmse2, rmsed):
        if value is not None:
            total += value
    return total, {
        "rmse_model1_arcsec": rmse1,
        "rmse_model2_arcsec": rmse2,
        "rmse_display_arcsec": rmsed,
    }


def calibrate(
    cases: list[CalibrationCase],
    base_config: SeeingConfig | None = None,
    passes: int = 2,
) -> tuple[SeeingConfig, FitMetrics]:
    """Deterministic coordinate-wise grid search.

    For each tunable coefficient, in a fixed order, try every candidate
    multiplier of its current value while holding all other coefficients
    fixed, keep whichever multiplier gives the lowest combined RMSE across
    all supplied cases, then move to the next coefficient. Repeat for
    ``passes`` full sweeps. This is bounded (a fixed small candidate list
    times a fixed small coefficient list times a fixed number of passes)
    and fully deterministic (no randomness).
    """

    if not cases:
        raise InputValidationError("calibration requires at least one case")

    best_cfg = copy.deepcopy(base_config) if base_config is not None else SeeingConfig()
    best_score, best_breakdown = _evaluate(best_cfg, cases)

    for _ in range(max(1, passes)):
        for path in TUNABLE_COEFFICIENTS:
            current_value = _get_path(best_cfg, path)
            for multiplier in CANDIDATE_MULTIPLIERS:
                candidate_cfg = copy.deepcopy(best_cfg)
                _set_path(candidate_cfg, path, current_value * multiplier)
                score, breakdown = _evaluate(candidate_cfg, cases)
                if score < best_score:
                    best_score = score
                    best_cfg = candidate_cfg
                    best_breakdown = breakdown

    metrics = FitMetrics(
        case_count=len(cases),
        rmse_model1_arcsec=best_breakdown["rmse_model1_arcsec"],
        rmse_model2_arcsec=best_breakdown["rmse_model2_arcsec"],
        rmse_display_arcsec=best_breakdown["rmse_display_arcsec"],
        iterations=max(1, passes) * len(TUNABLE_COEFFICIENTS) * len(CANDIDATE_MULTIPLIERS),
        coefficient_path_order=list(TUNABLE_COEFFICIENTS),
    )
    return best_cfg, metrics

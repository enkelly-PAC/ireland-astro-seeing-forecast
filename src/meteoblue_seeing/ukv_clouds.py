"""Windy UKV cloud import and seeing combination.

Windy displays the Met Office UKV model on windy.com, but UKV is not
currently listed as an official Point Forecast API model. This module
therefore reads a user-supplied CSV export or transcription and never
contacts Windy or an undocumented endpoint.
"""

from __future__ import annotations

import csv
import math
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .validation import InputValidationError, parse_utc_datetime


def format_utc_datetime(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _parse_percentage(raw: str | None, field_name: str, row_number: int) -> float | None:
    if raw is None or not raw.strip():
        return None
    try:
        value = float(raw)
    except ValueError as exc:
        raise InputValidationError(
            f"UKV cloud row {row_number}: {field_name} must be numeric"
        ) from exc
    if not math.isfinite(value) or not 0.0 <= value <= 100.0:
        raise InputValidationError(
            f"UKV cloud row {row_number}: {field_name} must be within [0, 100]"
        )
    return value


@dataclass(frozen=True)
class UkvCloudForecast:
    valid_time_utc: datetime
    low_cloud_pct: float
    mid_cloud_pct: float
    high_cloud_pct: float
    total_cloud_pct: float | None = None


def load_windy_ukv_csv(path: str | Path) -> list[UkvCloudForecast]:
    """Load user-supplied Windy UKV cloud percentages from CSV."""

    required = {
        "valid_time_utc",
        "low_cloud_pct",
        "mid_cloud_pct",
        "high_cloud_pct",
    }
    rows: list[UkvCloudForecast] = []
    with open(path, "r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None:
            raise InputValidationError("UKV cloud CSV has no header row")
        missing = sorted(required - set(reader.fieldnames))
        if missing:
            raise InputValidationError(
                f"UKV cloud CSV missing required column(s): {', '.join(missing)}"
            )
        for row_number, row in enumerate(reader, start=2):
            valid_time = parse_utc_datetime(
                row.get("valid_time_utc", ""),
                f"UKV cloud row {row_number} valid_time_utc",
            )
            low = _parse_percentage(row.get("low_cloud_pct"), "low_cloud_pct", row_number)
            mid = _parse_percentage(row.get("mid_cloud_pct"), "mid_cloud_pct", row_number)
            high = _parse_percentage(row.get("high_cloud_pct"), "high_cloud_pct", row_number)
            total = _parse_percentage(
                row.get("total_cloud_pct"), "total_cloud_pct", row_number
            )
            if low is None or mid is None or high is None:
                raise InputValidationError(
                    f"UKV cloud row {row_number}: low, mid and high cloud are required"
                )
            rows.append(
                UkvCloudForecast(
                    valid_time_utc=valid_time,
                    low_cloud_pct=low,
                    mid_cloud_pct=mid,
                    high_cloud_pct=high,
                    total_cloud_pct=total,
                )
            )
    if not rows:
        raise InputValidationError("UKV cloud CSV contains no data rows")
    return sorted(rows, key=lambda row: row.valid_time_utc)


def match_ukv_cloud(
    rows: list[UkvCloudForecast],
    target_time_utc: datetime,
    tolerance_minutes: float,
) -> tuple[UkvCloudForecast, float]:
    """Return the nearest UKV cloud row within the configured tolerance."""

    if tolerance_minutes < 0 or not math.isfinite(tolerance_minutes):
        raise InputValidationError("tolerance_minutes must be finite and non-negative")
    nearest = min(
        rows,
        key=lambda row: (
            abs((row.valid_time_utc - target_time_utc).total_seconds()),
            row.valid_time_utc,
        ),
    )
    offset_minutes = (
        nearest.valid_time_utc - target_time_utc
    ).total_seconds() / 60.0
    if abs(offset_minutes) > tolerance_minutes:
        raise InputValidationError(
            "no Windy UKV cloud row falls within "
            f"{tolerance_minutes:g} minutes of {format_utc_datetime(target_time_utc)}"
        )
    return nearest, offset_minutes


def _cloud_obstruction_pct(row: UkvCloudForecast) -> tuple[float, str]:
    if row.total_cloud_pct is not None:
        return row.total_cloud_pct, "WINDY_UKV_TOTAL_CLOUD"
    clear_fraction = (
        (1.0 - row.low_cloud_pct / 100.0)
        * (1.0 - row.mid_cloud_pct / 100.0)
        * (1.0 - row.high_cloud_pct / 100.0)
    )
    return 100.0 * (1.0 - clear_fraction), "INFERRED_INDEPENDENT_LAYER_OVERLAP"


def combine_forecast_with_ukv_cloud(
    seeing_result: dict[str, Any],
    cloud_row: UkvCloudForecast,
    offset_minutes: float,
) -> dict[str, Any]:
    """Overlay UKV cloud bands and calculate a separate observability score."""

    result = dict(seeing_result)
    original_clouds = result.get("cloud_bands")
    result["profile_cloud_bands"] = original_clouds
    result["cloud_bands"] = {
        "low_cloud_pct": cloud_row.low_cloud_pct,
        "mid_cloud_pct": cloud_row.mid_cloud_pct,
        "high_cloud_pct": cloud_row.high_cloud_pct,
        "total_cloud_pct": cloud_row.total_cloud_pct,
    }

    obstruction_pct, obstruction_method = _cloud_obstruction_pct(cloud_row)
    clear_sky_pct = max(0.0, 100.0 - obstruction_pct)
    seeing_index_value = float(result["display"]["index"])
    seeing_quality_pct = 25.0 * (seeing_index_value - 1.0)
    observing_score = clear_sky_pct * (0.5 + 0.5 * seeing_quality_pct / 100.0)

    if observing_score >= 80.0:
        rating = "excellent"
    elif observing_score >= 60.0:
        rating = "good"
    elif observing_score >= 40.0:
        rating = "marginal"
    elif observing_score >= 20.0:
        rating = "poor"
    else:
        rating = "unusable"

    result["cloud_source"] = {
        "provider": "Windy",
        "model": "UKV",
        "acquisition": "USER_SUPPLIED_EXPORT_OR_TRANSCRIPTION",
        "valid_time_utc": format_utc_datetime(cloud_row.valid_time_utc),
        "match_offset_minutes": offset_minutes,
        "network_fetch_performed": False,
        "layer_definition": (
            "UKV low, medium and high cloud categories; these are not "
            "relabeled as meteoblue's 0 to 4, 4 to 8 and 8 to 15 km bands"
        ),
    }
    result["observability"] = {
        "score_0_100": observing_score,
        "rating": rating,
        "estimated_cloud_obstruction_pct": obstruction_pct,
        "estimated_clear_sky_pct": clear_sky_pct,
        "cloud_obstruction_method": obstruction_method,
        "seeing_quality_pct": seeing_quality_pct,
        "method": "INFERRED_CALIBRATABLE",
        "formula": (
            "clear_sky_pct * (0.5 + 0.5 * ((seeing_index - 1) / 4))"
        ),
    }
    return result

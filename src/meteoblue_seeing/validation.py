"""Input validation for vertical profile forecasts.

This module is deliberately strict and explicit: it raises
``InputValidationError`` with a message describing exactly what is wrong,
rather than silently coercing bad data.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime, timezone


class InputValidationError(ValueError):
    """Raised when a forecast input document fails validation."""


def parse_utc_datetime(value: str, field_name: str = "valid_time_utc") -> datetime:
    """Parse an ISO 8601 timestamp and require an explicit UTC offset."""

    if not isinstance(value, str) or not value.strip():
        raise InputValidationError(f"{field_name} must be a non-empty ISO 8601 string")
    normalised = value.strip()
    if normalised.endswith("Z"):
        normalised = normalised[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(normalised)
    except ValueError as exc:
        raise InputValidationError(
            f"{field_name} must be a valid ISO 8601 timestamp: {value!r}"
        ) from exc
    if parsed.tzinfo is None:
        raise InputValidationError(f"{field_name} must include a UTC offset")
    return parsed.astimezone(timezone.utc)


@dataclass
class Level:
    """One vertical atmospheric level."""

    altitude_m_asl: float
    pressure_hpa: float
    temperature_c: float
    relative_humidity_pct: float
    wind_u_ms: float
    wind_v_ms: float
    cloud_cover_pct: float

    @classmethod
    def from_dict(cls, data: dict, index: int) -> "Level":
        required = (
            "altitude_m_asl",
            "pressure_hpa",
            "temperature_c",
            "relative_humidity_pct",
            "wind_u_ms",
            "wind_v_ms",
            "cloud_cover_pct",
        )
        missing = [key for key in required if key not in data]
        if missing:
            raise InputValidationError(
                f"level {index}: missing required field(s): {', '.join(missing)}"
            )
        values = {}
        for key in required:
            raw = data[key]
            if isinstance(raw, bool) or not isinstance(raw, (int, float)):
                raise InputValidationError(
                    f"level {index}: field '{key}' must be a number, got {raw!r}"
                )
            numeric = float(raw)
            if not math.isfinite(numeric):
                raise InputValidationError(
                    f"level {index}: field '{key}' must be finite, got {raw!r}"
                )
            values[key] = numeric
        return cls(**values)

    def validate_bounds(self, index: int) -> None:
        if self.pressure_hpa <= 0 or self.pressure_hpa > 1100:
            raise InputValidationError(
                f"level {index}: pressure_hpa out of plausible range (0, 1100]: "
                f"{self.pressure_hpa}"
            )
        if self.temperature_c < -120 or self.temperature_c > 60:
            raise InputValidationError(
                f"level {index}: temperature_c out of plausible range [-120, 60]: "
                f"{self.temperature_c}"
            )
        if not (0.0 <= self.relative_humidity_pct <= 100.0):
            raise InputValidationError(
                f"level {index}: relative_humidity_pct must be within [0, 100]: "
                f"{self.relative_humidity_pct}"
            )
        if not (0.0 <= self.cloud_cover_pct <= 100.0):
            raise InputValidationError(
                f"level {index}: cloud_cover_pct must be within [0, 100]: "
                f"{self.cloud_cover_pct}"
            )
        if abs(self.wind_u_ms) > 250 or abs(self.wind_v_ms) > 250:
            raise InputValidationError(
                f"level {index}: wind component magnitude implausibly large "
                f"(> 250 m/s): u={self.wind_u_ms}, v={self.wind_v_ms}"
            )
        if self.altitude_m_asl < -500 or self.altitude_m_asl > 40000:
            raise InputValidationError(
                f"level {index}: altitude_m_asl out of plausible range "
                f"[-500, 40000]: {self.altitude_m_asl}"
            )


@dataclass
class ForecastInput:
    site_elevation_m_asl: float
    levels: list[Level]
    wavelength_nm: float | None = None
    location_name: str | None = None
    valid_time_utc: datetime | None = None

    @classmethod
    def from_dict(cls, data: dict) -> "ForecastInput":
        if not isinstance(data, dict):
            raise InputValidationError("top level input must be a JSON object")
        if "site_elevation_m_asl" not in data:
            raise InputValidationError("missing required field: site_elevation_m_asl")
        site_elevation = data["site_elevation_m_asl"]
        if isinstance(site_elevation, bool) or not isinstance(
            site_elevation, (int, float)
        ):
            raise InputValidationError("site_elevation_m_asl must be a number")
        site_elevation = float(site_elevation)
        if not math.isfinite(site_elevation):
            raise InputValidationError("site_elevation_m_asl must be finite")

        raw_levels = data.get("levels")
        if not isinstance(raw_levels, list) or len(raw_levels) < 2:
            raise InputValidationError(
                "field 'levels' must be a list with at least two entries"
            )

        levels = [Level.from_dict(item, i) for i, item in enumerate(raw_levels)]
        for i, level in enumerate(levels):
            level.validate_bounds(i)

        for i in range(1, len(levels)):
            prev, cur = levels[i - 1], levels[i]
            if cur.altitude_m_asl <= prev.altitude_m_asl:
                raise InputValidationError(
                    "levels must be strictly ordered by increasing "
                    f"altitude_m_asl; level {i} ({cur.altitude_m_asl}) does not "
                    f"exceed level {i - 1} ({prev.altitude_m_asl})"
                )
            if cur.pressure_hpa >= prev.pressure_hpa:
                raise InputValidationError(
                    "levels must show strictly decreasing pressure_hpa as "
                    f"altitude increases; level {i} ({cur.pressure_hpa} hPa) is "
                    f"not below level {i - 1} ({prev.pressure_hpa} hPa)"
                )

        wavelength = data.get("wavelength_nm")
        if wavelength is not None:
            if isinstance(wavelength, bool) or not isinstance(
                wavelength, (int, float)
            ):
                raise InputValidationError("wavelength_nm must be a number")
            wavelength = float(wavelength)
            if not math.isfinite(wavelength) or wavelength <= 0:
                raise InputValidationError("wavelength_nm must be a positive number")

        location_name = data.get("location_name")
        if location_name is not None and not isinstance(location_name, str):
            raise InputValidationError("location_name must be a string if provided")

        valid_time_raw = data.get("valid_time_utc")
        valid_time = (
            parse_utc_datetime(valid_time_raw)
            if valid_time_raw is not None
            else None
        )

        return cls(
            site_elevation_m_asl=site_elevation,
            levels=levels,
            wavelength_nm=wavelength,
            location_name=location_name,
            valid_time_utc=valid_time,
        )

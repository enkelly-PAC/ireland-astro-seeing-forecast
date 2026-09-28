"""Shared Ireland wide location constants and validation helpers.

These bounds are deliberately generous: they cover the island of Ireland
(both the Republic of Ireland and Northern Ireland) plus a margin of
nearby coastal waters, so that headlands, islands and offshore observing
sites are not rejected by an overly tight box.
"""

from __future__ import annotations

import math

from .validation import InputValidationError

IRELAND_MIN_LATITUDE = 51.0
IRELAND_MAX_LATITUDE = 55.6
IRELAND_MIN_LONGITUDE = -11.5
IRELAND_MAX_LONGITUDE = -5.0

MIN_FORECAST_HOURS = 1
MAX_FORECAST_HOURS = 120
DEFAULT_FORECAST_HOURS = 96


def validate_ireland_coordinates(latitude: float, longitude: float) -> None:
    """Raise ``InputValidationError`` unless the point is within the Ireland region."""

    if isinstance(latitude, bool) or not isinstance(latitude, (int, float)):
        raise InputValidationError("latitude must be a number")
    if isinstance(longitude, bool) or not isinstance(longitude, (int, float)):
        raise InputValidationError("longitude must be a number")
    if not math.isfinite(latitude) or not math.isfinite(longitude):
        raise InputValidationError("latitude and longitude must be finite numbers")
    if not (IRELAND_MIN_LATITUDE <= latitude <= IRELAND_MAX_LATITUDE):
        raise InputValidationError(
            "latitude "
            f"{latitude} is outside the Ireland region "
            f"[{IRELAND_MIN_LATITUDE}, {IRELAND_MAX_LATITUDE}]"
        )
    if not (IRELAND_MIN_LONGITUDE <= longitude <= IRELAND_MAX_LONGITUDE):
        raise InputValidationError(
            "longitude "
            f"{longitude} is outside the Ireland region "
            f"[{IRELAND_MIN_LONGITUDE}, {IRELAND_MAX_LONGITUDE}]"
        )


def validate_forecast_hours(hours: int | float) -> int:
    """Validate and coerce a requested forecast length in hours, 1 to 120."""

    if isinstance(hours, bool) or not isinstance(hours, (int, float)):
        raise InputValidationError("hours must be a whole number")
    if not math.isfinite(hours) or hours != int(hours):
        raise InputValidationError("hours must be a whole number")
    hours_int = int(hours)
    if hours_int < MIN_FORECAST_HOURS or hours_int > MAX_FORECAST_HOURS:
        raise InputValidationError(
            f"hours must be within [{MIN_FORECAST_HOURS}, {MAX_FORECAST_HOURS}]: {hours_int}"
        )
    return hours_int


def is_within_ireland_region(latitude: float, longitude: float) -> bool:
    """Return ``True`` if the coordinate falls inside the generous Ireland box."""

    try:
        validate_ireland_coordinates(latitude, longitude)
    except InputValidationError:
        return False
    return True

"""Shared British Isles location constants and validation helpers.

"British Isles" here means Great Britain (England, Scotland and Wales),
Ireland (the Republic of Ireland and Northern Ireland), the Isle of Man,
the Channel Islands, and the surrounding island groups: the Hebrides
(Inner and Outer), Orkney, Shetland, the Isles of Scilly and other near
shore islands. It deliberately excludes the Faroe Islands and continental
Europe.

The bounds below are a single generous bounding box rather than a precise
coastline outline, so that headlands, islands and offshore observing sites
close to the edge of the region are not rejected by an overly tight box.
The box is sized to comfortably include Shetland's northernmost point
(around 60.86 N) while staying south of the Faroe Islands (whose
southernmost point is around 61.39 N), and to comfortably include the
Channel Islands' southernmost point (Jersey, around 49.17 N).
"""

from __future__ import annotations

import math

from .validation import InputValidationError

BRITISH_ISLES_MIN_LATITUDE = 49.0
BRITISH_ISLES_MAX_LATITUDE = 61.0
BRITISH_ISLES_MIN_LONGITUDE = -11.5
BRITISH_ISLES_MAX_LONGITUDE = 2.0

MIN_FORECAST_HOURS = 1
MAX_FORECAST_HOURS = 120
DEFAULT_FORECAST_HOURS = 96


def validate_british_isles_coordinates(latitude: float, longitude: float) -> None:
    """Raise ``InputValidationError`` unless the point is within the British Isles."""

    if isinstance(latitude, bool) or not isinstance(latitude, (int, float)):
        raise InputValidationError("latitude must be a number")
    if isinstance(longitude, bool) or not isinstance(longitude, (int, float)):
        raise InputValidationError("longitude must be a number")
    if not math.isfinite(latitude) or not math.isfinite(longitude):
        raise InputValidationError("latitude and longitude must be finite numbers")
    if not (BRITISH_ISLES_MIN_LATITUDE <= latitude <= BRITISH_ISLES_MAX_LATITUDE):
        raise InputValidationError(
            "latitude "
            f"{latitude} is outside the British Isles region "
            f"[{BRITISH_ISLES_MIN_LATITUDE}, {BRITISH_ISLES_MAX_LATITUDE}]"
        )
    if not (BRITISH_ISLES_MIN_LONGITUDE <= longitude <= BRITISH_ISLES_MAX_LONGITUDE):
        raise InputValidationError(
            "longitude "
            f"{longitude} is outside the British Isles region "
            f"[{BRITISH_ISLES_MIN_LONGITUDE}, {BRITISH_ISLES_MAX_LONGITUDE}]"
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


def is_within_british_isles_region(latitude: float, longitude: float) -> bool:
    """Return ``True`` if the coordinate falls inside the generous British Isles box."""

    try:
        validate_british_isles_coordinates(latitude, longitude)
    except InputValidationError:
        return False
    return True

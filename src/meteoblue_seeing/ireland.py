"""Backward-compatible alias module for :mod:`meteoblue_seeing.british_isles`.

This project originally covered only Ireland (the Republic of Ireland and
Northern Ireland) and this module held the region bounding box and
validation helpers. The project has since expanded in scope to the whole
British Isles: Great Britain, Ireland, Northern Ireland, the Isle of Man,
the Channel Islands, the Hebrides, Orkney, Shetland and surrounding
islands (excluding the Faroe Islands and continental Europe). The
canonical constants and helpers now live in
:mod:`meteoblue_seeing.british_isles`.

This module is kept, re-exporting the wider bounds under their original
Ireland-branded names, purely so any existing code that imports from
``meteoblue_seeing.ireland`` keeps working unchanged. New code should
import from :mod:`meteoblue_seeing.british_isles` directly.
"""

from __future__ import annotations

from .british_isles import (
    BRITISH_ISLES_MAX_LATITUDE,
    BRITISH_ISLES_MAX_LONGITUDE,
    BRITISH_ISLES_MIN_LATITUDE,
    BRITISH_ISLES_MIN_LONGITUDE,
    DEFAULT_FORECAST_HOURS,
    MAX_FORECAST_HOURS,
    MIN_FORECAST_HOURS,
    is_within_british_isles_region,
    validate_british_isles_coordinates,
    validate_forecast_hours,
)

# Deprecated aliases, kept for backward compatibility.
IRELAND_MIN_LATITUDE = BRITISH_ISLES_MIN_LATITUDE
IRELAND_MAX_LATITUDE = BRITISH_ISLES_MAX_LATITUDE
IRELAND_MIN_LONGITUDE = BRITISH_ISLES_MIN_LONGITUDE
IRELAND_MAX_LONGITUDE = BRITISH_ISLES_MAX_LONGITUDE

validate_ireland_coordinates = validate_british_isles_coordinates
is_within_ireland_region = is_within_british_isles_region

__all__ = [
    "IRELAND_MIN_LATITUDE",
    "IRELAND_MAX_LATITUDE",
    "IRELAND_MIN_LONGITUDE",
    "IRELAND_MAX_LONGITUDE",
    "MIN_FORECAST_HOURS",
    "MAX_FORECAST_HOURS",
    "DEFAULT_FORECAST_HOURS",
    "validate_ireland_coordinates",
    "validate_forecast_hours",
    "is_within_ireland_region",
]

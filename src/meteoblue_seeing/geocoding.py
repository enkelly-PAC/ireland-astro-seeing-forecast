"""Server-side proxy to the Open-Meteo Geocoding API, filtered to the British Isles.

This module only ever contacts the public, documented Open-Meteo Geocoding
API (https://open-meteo.com/en/docs/geocoding-api). It never scrapes or
proxies any meteoblue endpoint. Results are filtered so the location picker
in the browser UI only offers places in the British Isles: Great Britain,
Ireland, Northern Ireland, the Isle of Man, the Channel Islands, the
Hebrides, Orkney, Shetland and surrounding islands. The Faroe Islands and
continental Europe are explicitly out of scope. A bounding box fallback
covers the (rare) result that lacks a usable country code.
"""

from __future__ import annotations

import json
import urllib.parse
import urllib.request
from typing import Any

from .british_isles import is_within_british_isles_region
from .validation import InputValidationError

GEOCODING_URL = "https://geocoding-api.open-meteo.com/v1/search"

DEFAULT_RESULT_LIMIT = 8
MAX_RESULT_LIMIT = 20

# ISO 3166-1 country codes fully within scope: Ireland, the United Kingdom
# (Great Britain and Northern Ireland), the Isle of Man, Jersey and
# Guernsey (the Channel Islands' two crown dependencies). Any other
# country code, including the Faroe Islands (FO) and any continental
# European country, is rejected outright.
BRITISH_ISLES_COUNTRY_CODES = {"IE", "GB", "IM", "JE", "GG"}


def _is_british_isles_result(item: dict[str, Any]) -> bool:
    country_code = str(item.get("country_code") or "").upper()
    if country_code:
        return country_code in BRITISH_ISLES_COUNTRY_CODES
    latitude = item.get("latitude")
    longitude = item.get("longitude")
    if isinstance(latitude, (int, float)) and isinstance(longitude, (int, float)):
        return is_within_british_isles_region(latitude, longitude)
    return False


def _simplify_result(item: dict[str, Any]) -> dict[str, Any]:
    parts = [item.get("name")]
    for key in ("admin2", "admin1"):
        value = item.get(key)
        if value and value not in parts:
            parts.append(value)
    country = item.get("country")
    if country and country not in parts:
        parts.append(country)
    display_name = ", ".join(str(part) for part in parts if part)
    return {
        "name": item.get("name"),
        "display_name": display_name,
        "admin1": item.get("admin1"),
        "country": item.get("country"),
        "country_code": item.get("country_code"),
        "latitude": item.get("latitude"),
        "longitude": item.get("longitude"),
        "elevation": item.get("elevation"),
        "timezone": item.get("timezone"),
    }


def build_geocode_url(query: str, limit: int = DEFAULT_RESULT_LIMIT) -> str:
    if not isinstance(query, str) or not query.strip():
        raise InputValidationError("search query must not be empty")
    # Ask for extra rows because out-of-scope results are filtered out below.
    fetch_count = max(1, min(MAX_RESULT_LIMIT, limit)) * 3
    params = urllib.parse.urlencode(
        {
            "name": query.strip(),
            "count": min(100, fetch_count),
            "language": "en",
            "format": "json",
        }
    )
    return f"{GEOCODING_URL}?{params}"


def geocode_search(
    query: str,
    limit: int = DEFAULT_RESULT_LIMIT,
    timeout_seconds: float = 10.0,
) -> list[dict[str, Any]]:
    """Search the Open-Meteo Geocoding API and keep only British Isles results."""

    if limit <= 0:
        raise InputValidationError("limit must be a positive integer")
    url = build_geocode_url(query, limit)
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "british-isles-astro-seeing-forecast/0.1"},
    )
    with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
        payload = json.loads(response.read().decode("utf-8"))
    raw_results = payload.get("results") or []
    filtered = [item for item in raw_results if _is_british_isles_result(item)]
    return [_simplify_result(item) for item in filtered[:limit]]

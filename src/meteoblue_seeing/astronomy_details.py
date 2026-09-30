"""Planetary and lunar observing details for a British Isles forecast."""

from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo

import astronomy

BRITISH_ISLES_TIMEZONE = ZoneInfo("Europe/Dublin")
IRELAND_TIMEZONE = BRITISH_ISLES_TIMEZONE

BODY_DEFINITIONS = (
    ("moon", "Moon", astronomy.Body.Moon),
    ("mercury", "Mercury", astronomy.Body.Mercury),
    ("venus", "Venus", astronomy.Body.Venus),
    ("mars", "Mars", astronomy.Body.Mars),
    ("jupiter", "Jupiter", astronomy.Body.Jupiter),
    ("saturn", "Saturn", astronomy.Body.Saturn),
    ("uranus", "Uranus", astronomy.Body.Uranus),
    ("neptune", "Neptune", astronomy.Body.Neptune),
    ("pluto", "Pluto", astronomy.Body.Pluto),
)


def _astronomy_time(value: datetime) -> astronomy.Time:
    utc = value.astimezone(timezone.utc)
    seconds = utc.second + utc.microsecond / 1_000_000.0
    return astronomy.Time.Make(
        utc.year,
        utc.month,
        utc.day,
        utc.hour,
        utc.minute,
        seconds,
    )


def _local_iso(value: astronomy.Time | None) -> str | None:
    if value is None:
        return None
    utc = value.Utc().replace(tzinfo=timezone.utc)
    return utc.astimezone(BRITISH_ISLES_TIMEZONE).isoformat()


def _moon_phase_name(phase_degrees: float) -> str:
    phase = phase_degrees % 360.0
    if phase < 22.5 or phase >= 337.5:
        return "New Moon"
    if phase < 67.5:
        return "Waxing crescent"
    if phase < 112.5:
        return "First quarter"
    if phase < 157.5:
        return "Waxing gibbous"
    if phase < 202.5:
        return "Full Moon"
    if phase < 247.5:
        return "Waning gibbous"
    if phase < 292.5:
        return "Third quarter"
    return "Waning crescent"


def body_positions(
    latitude: float,
    longitude: float,
    elevation_m: float,
    valid_time_utc: datetime,
) -> dict[str, dict[str, float]]:
    """Calculate topocentric altitude and azimuth for each supported body."""

    observer = astronomy.Observer(latitude, longitude, elevation_m)
    astro_time = _astronomy_time(valid_time_utc)
    positions: dict[str, dict[str, float]] = {}
    for key, _name, body in BODY_DEFINITIONS:
        equatorial = astronomy.Equator(
            body,
            astro_time,
            observer,
            ofdate=True,
            aberration=True,
        )
        horizontal = astronomy.Horizon(
            astro_time,
            observer,
            equatorial.ra,
            equatorial.dec,
            astronomy.Refraction.Normal,
        )
        positions[key] = {
            "altitude_degrees": horizontal.altitude,
            "azimuth_degrees": horizontal.azimuth,
        }
    return positions


def _daily_body_details(
    observer: astronomy.Observer,
    body: astronomy.Body,
    local_date: date,
) -> dict[str, Any]:
    observing_day_start = datetime.combine(
        local_date,
        time(hour=12),
        tzinfo=BRITISH_ISLES_TIMEZONE,
    )
    start = _astronomy_time(observing_day_start)
    transit = astronomy.SearchHourAngle(body, observer, 0.0, start)
    rise = astronomy.SearchRiseSet(
        body,
        observer,
        astronomy.Direction.Rise,
        transit.time,
        -1.1,
    )
    setting = astronomy.SearchRiseSet(
        body,
        observer,
        astronomy.Direction.Set,
        transit.time,
        1.1,
    )
    reference = _astronomy_time(observing_day_start + timedelta(hours=12))
    illumination = astronomy.Illumination(body, reference)

    detail: dict[str, Any] = {
        "rise_local": _local_iso(rise),
        "meridian_local": _local_iso(transit.time),
        "set_local": _local_iso(setting),
        "culmination_altitude_degrees": transit.hor.altitude,
        "magnitude": illumination.mag,
        "illuminated_fraction": illumination.phase_fraction,
    }
    if body is astronomy.Body.Moon:
        phase_degrees = astronomy.MoonPhase(reference)
        detail["phase_degrees"] = phase_degrees
        detail["phase_name"] = _moon_phase_name(phase_degrees)
    return detail


def astronomy_days(
    latitude: float,
    longitude: float,
    elevation_m: float,
    forecast_times_utc: list[datetime],
) -> dict[str, Any]:
    """Build daily rise, set and meridian details across the forecast range."""

    if not forecast_times_utc:
        return {
            "provider": "Astronomy Engine",
            "timezone": "Europe/Dublin",
            "bodies": [],
            "days": [],
        }

    local_dates = sorted(
        {value.astimezone(BRITISH_ISLES_TIMEZONE).date() for value in forecast_times_utc}
    )
    final_date = forecast_times_utc[-1].astimezone(BRITISH_ISLES_TIMEZONE).date()
    if forecast_times_utc[-1].astimezone(BRITISH_ISLES_TIMEZONE).time() != time.min:
        local_dates = sorted(set(local_dates) | {final_date})

    observer = astronomy.Observer(latitude, longitude, elevation_m)
    days = []
    for local_date in local_dates:
        bodies = {
            key: _daily_body_details(observer, body, local_date)
            for key, _name, body in BODY_DEFINITIONS
        }
        days.append({"date": local_date.isoformat(), "bodies": bodies})

    return {
        "provider": "Astronomy Engine",
        "timezone": "Europe/Dublin",
        "bodies": [
            {"key": key, "name": name}
            for key, name, _body in BODY_DEFINITIONS
        ],
        "days": days,
    }

"""British Isles-wide astronomy forecast using UK Met Office model data.

This module started as a Wicklow Head only forecast and has been
generalised so that the same forecast pipeline can be run for any selected
latitude, longitude and name within the British Isles region (Great
Britain, Ireland, Northern Ireland, the Isle of Man, the Channel Islands
and surrounding islands). The original Wicklow Head constants, functions
and CLI behaviour are preserved: every public Wicklow function below is
now a thin wrapper around the generic location functions, so existing
callers keep working unchanged.

The four-day mode uses Open-Meteo's ``ukmo_seamless`` feed. It uses UKV
2 km for the near term and UKMO Global 10 km for the extended period,
which provides complete upper-air profiles across the 96-hour forecast.
"""

from __future__ import annotations

import html
import json
import math
import re
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from .astronomy_details import astronomy_days, body_positions
from .config import SeeingConfig
from .forecast import run_forecast
from .models import seeing_score_1_10
from .british_isles import (
    validate_british_isles_coordinates,
    validate_forecast_hours,
)
from .ukv_clouds import UkvCloudForecast, combine_forecast_with_ukv_cloud
from .validation import InputValidationError

WICKLOW_HEAD_LATITUDE = 52.96544
WICKLOW_HEAD_LONGITUDE = -6.00233
WICKLOW_HEAD_ELEVATION_M = 84.0
WICKLOW_HEAD_NAME = "Wicklow Head, County Wicklow, Ireland"
BRITISH_ISLES_TIMEZONE_NAME = "Europe/Dublin"
IRELAND_TIMEZONE_NAME = BRITISH_ISLES_TIMEZONE_NAME
WICKLOW_HEAD_TIMEZONE = ZoneInfo(BRITISH_ISLES_TIMEZONE_NAME)
PRESSURE_LEVELS_HPA = (1000, 925, 850, 700, 500, 300, 200)
OPEN_METEO_URL = "https://api.open-meteo.com/v1/forecast"


def _hourly_variables() -> list[str]:
    variables = [
        "cloud_cover",
        "cloud_cover_low",
        "cloud_cover_mid",
        "cloud_cover_high",
        "visibility",
    ]
    for pressure in PRESSURE_LEVELS_HPA:
        variables.extend(
            [
                f"temperature_{pressure}hPa",
                f"relative_humidity_{pressure}hPa",
                f"wind_speed_{pressure}hPa",
                f"wind_direction_{pressure}hPa",
                f"geopotential_height_{pressure}hPa",
            ]
        )
    return variables


def build_open_meteo_url(
    forecast_hours: int = 96,
    latitude: float = WICKLOW_HEAD_LATITUDE,
    longitude: float = WICKLOW_HEAD_LONGITUDE,
) -> str:
    forecast_hours = validate_forecast_hours(forecast_hours)
    query = urllib.parse.urlencode(
        {
            "latitude": latitude,
            "longitude": longitude,
            "hourly": ",".join(_hourly_variables()),
            "models": "ukmo_seamless",
            "forecast_hours": forecast_hours,
            "timezone": "UTC",
        }
    )
    return f"{OPEN_METEO_URL}?{query}"


def fetch_ukv_forecast(
    forecast_hours: int = 96,
    latitude: float = WICKLOW_HEAD_LATITUDE,
    longitude: float = WICKLOW_HEAD_LONGITUDE,
    timeout_seconds: float = 60.0,
) -> dict[str, Any]:
    """Fetch UK Met Office seamless point data through Open-Meteo."""

    url = build_open_meteo_url(forecast_hours, latitude, longitude)
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "british-isles-astro-seeing-forecast/0.1"},
    )
    with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
        payload = json.loads(response.read().decode("utf-8"))
    if "hourly" not in payload or "time" not in payload["hourly"]:
        raise InputValidationError("UKV API response did not contain hourly forecast data")
    return payload


def _wind_components(speed_kmh: float, direction_degrees: float) -> tuple[float, float]:
    """Convert meteorological wind direction and speed to east/north components."""

    speed_ms = speed_kmh / 3.6
    radians = math.radians(direction_degrees)
    return -speed_ms * math.sin(radians), -speed_ms * math.cos(radians)


def _utc_datetime(value: str) -> datetime:
    return datetime.fromisoformat(value).replace(tzinfo=timezone.utc)


def _solar_altitude_degrees(
    when_utc: datetime,
    latitude: float,
    longitude: float,
) -> float:
    """Approximate solar altitude using the NOAA fractional-year method."""

    day_of_year = when_utc.timetuple().tm_yday
    decimal_hour = (
        when_utc.hour
        + when_utc.minute / 60.0
        + when_utc.second / 3600.0
    )
    gamma = 2.0 * math.pi / 365.0 * (
        day_of_year - 1 + (decimal_hour - 12.0) / 24.0
    )
    equation_of_time = 229.18 * (
        0.000075
        + 0.001868 * math.cos(gamma)
        - 0.032077 * math.sin(gamma)
        - 0.014615 * math.cos(2.0 * gamma)
        - 0.040849 * math.sin(2.0 * gamma)
    )
    declination = (
        0.006918
        - 0.399912 * math.cos(gamma)
        + 0.070257 * math.sin(gamma)
        - 0.006758 * math.cos(2.0 * gamma)
        + 0.000907 * math.sin(2.0 * gamma)
        - 0.002697 * math.cos(3.0 * gamma)
        + 0.00148 * math.sin(3.0 * gamma)
    )
    true_solar_minutes = (
        decimal_hour * 60.0 + equation_of_time + 4.0 * longitude
    ) % 1440.0
    hour_angle = math.radians(true_solar_minutes / 4.0 - 180.0)
    latitude_radians = math.radians(latitude)
    cosine_zenith = (
        math.sin(latitude_radians) * math.sin(declination)
        + math.cos(latitude_radians)
        * math.cos(declination)
        * math.cos(hour_angle)
    )
    cosine_zenith = max(-1.0, min(1.0, cosine_zenith))
    return 90.0 - math.degrees(math.acos(cosine_zenith))


def _darkness_factor(solar_altitude_degrees: float) -> tuple[float, str]:
    if solar_altitude_degrees <= -18.0:
        return 1.0, "astronomical night"
    if solar_altitude_degrees < -6.0:
        return (-6.0 - solar_altitude_degrees) / 12.0, "twilight"
    return 0.0, "daylight"


def _build_profile(
    payload: dict[str, Any],
    index: int,
    elevation_m_asl: float = WICKLOW_HEAD_ELEVATION_M,
    location_name: str = WICKLOW_HEAD_NAME,
) -> dict[str, Any]:
    """Build one vertical profile input from a UKV hourly payload.

    ``elevation_m_asl`` and ``location_name`` default to the original
    Wicklow Head constants so this function stays backward compatible;
    :func:`generate_location_forecast` passes the model-grid elevation
    returned by Open-Meteo for any other selected point.
    """

    hourly = payload["hourly"]
    valid_time = _utc_datetime(hourly["time"][index])
    levels: list[dict[str, float]] = []
    for pressure in PRESSURE_LEVELS_HPA:
        keys = {
            "temperature": f"temperature_{pressure}hPa",
            "humidity": f"relative_humidity_{pressure}hPa",
            "speed": f"wind_speed_{pressure}hPa",
            "direction": f"wind_direction_{pressure}hPa",
            "height": f"geopotential_height_{pressure}hPa",
        }
        values = {name: hourly[key][index] for name, key in keys.items()}
        if any(value is None for value in values.values()):
            continue
        altitude = float(values["height"])
        if altitude <= elevation_m_asl:
            continue
        u_ms, v_ms = _wind_components(
            float(values["speed"]),
            float(values["direction"]),
        )
        levels.append(
            {
                "altitude_m_asl": altitude,
                "pressure_hpa": float(pressure),
                "temperature_c": float(values["temperature"]),
                # NWP pressure-level RH can report slight supersaturation
                # above 100%. The seeing input uses physical percentage
                # bounds, so constrain model values to [0, 100].
                "relative_humidity_pct": max(
                    0.0, min(100.0, float(values["humidity"]))
                ),
                "wind_u_ms": u_ms,
                "wind_v_ms": v_ms,
                "cloud_cover_pct": 0.0,
            }
        )
    levels.sort(key=lambda level: level["altitude_m_asl"])
    if len(levels) < 2:
        raise InputValidationError(
            f"UKV returned fewer than two usable pressure levels at {valid_time.isoformat()}"
        )
    return {
        "location_name": location_name,
        "site_elevation_m_asl": elevation_m_asl,
        "valid_time_utc": valid_time.isoformat().replace("+00:00", "Z"),
        "wavelength_nm": 500.0,
        "levels": levels,
    }


def _score_hour(
    combined: dict[str, Any],
    visibility_m: float | None,
    solar_altitude_degrees: float,
) -> dict[str, Any]:
    seeing_score = seeing_score_1_10(
        float(combined["display"]["arcsec"]),
        SeeingConfig(),
    )

    cloud_quality = combined["observability"]["estimated_clear_sky_pct"] / 100.0
    seeing_quality = (seeing_score - 1.0) / 9.0
    if visibility_m is None:
        visibility_factor = 1.0
    else:
        visibility_factor = max(0.0, min(1.0, visibility_m / 20000.0))
    darkness_factor, light_state = _darkness_factor(solar_altitude_degrees)

    imaging_quality = seeing_quality * (0.2 + 0.8 * cloud_quality)
    imaging_score = max(1, min(10, round(1.0 + 9.0 * imaging_quality)))
    usable_quality = (
        cloud_quality
        * (0.4 + 0.6 * seeing_quality)
        * visibility_factor
        * darkness_factor
    )
    observing_score = max(1, min(10, round(1.0 + 9.0 * usable_quality)))
    return {
        "seeing_score_1_10": seeing_score,
        "imaging_score_1_10": imaging_score,
        "observing_score_1_10": observing_score,
        "solar_altitude_degrees": solar_altitude_degrees,
        "light_state": light_state,
        "visibility_m": visibility_m,
        "method": "INFERRED_CALIBRATABLE",
    }


def generate_location_forecast(
    latitude: float,
    longitude: float,
    location_name: str,
    forecast_hours: int = 96,
) -> dict[str, Any]:
    """Build a combined UKV cloud and seeing forecast for any British Isles location.

    The site elevation used for the vertical profile is the model-grid
    elevation returned by Open-Meteo for the requested point (the
    elevation of the UKV grid cell actually sampled), not a hardcoded
    constant. Coordinates are validated against a generous British Isles
    region bounding box and ``forecast_hours`` is validated to [1, 120].
    """

    validate_british_isles_coordinates(latitude, longitude)
    forecast_hours = validate_forecast_hours(forecast_hours)

    payload = fetch_ukv_forecast(forecast_hours, latitude, longitude)
    grid_elevation = payload.get("elevation")
    elevation_m_asl = (
        float(grid_elevation)
        if isinstance(grid_elevation, (int, float))
        else 0.0
    )

    hourly = payload["hourly"]
    forecasts: list[dict[str, Any]] = []
    forecast_times_utc: list[datetime] = []
    skipped_hours = 0
    for index, time_text in enumerate(hourly["time"]):
        try:
            profile = _build_profile(
                payload,
                index,
                elevation_m_asl=elevation_m_asl,
                location_name=location_name,
            )
        except InputValidationError:
            # The UKV pressure-level (upper air) fields are only issued for a
            # shorter lead time than the requested rolling window; surface
            # fields such as cloud cover often extend further. Skip hours
            # that do not yet have a usable vertical profile rather than
            # failing the whole rolling forecast.
            skipped_hours += 1
            continue
        seeing = run_forecast(profile)
        valid_time = _utc_datetime(time_text)
        cloud = UkvCloudForecast(
            valid_time_utc=valid_time,
            low_cloud_pct=float(hourly["cloud_cover_low"][index]),
            mid_cloud_pct=float(hourly["cloud_cover_mid"][index]),
            high_cloud_pct=float(hourly["cloud_cover_high"][index]),
            total_cloud_pct=float(hourly["cloud_cover"][index]),
        )
        combined = combine_forecast_with_ukv_cloud(seeing, cloud, 0.0)
        combined["cloud_source"] = {
            "provider": "Met Office",
            "access_service": "Open-Meteo UKMO API",
            "model": "UK Met Office Seamless",
            "valid_time_utc": profile["valid_time_utc"],
            "network_fetch_performed": True,
            "layer_definition": "Native UKMO low, medium and high cloud categories",
        }
        solar_altitude = _solar_altitude_degrees(valid_time, latitude, longitude)
        visibility = hourly["visibility"][index]
        combined["scores"] = _score_hour(
            combined,
            None if visibility is None else float(visibility),
            solar_altitude,
        )
        combined["body_positions"] = body_positions(
            latitude,
            longitude,
            elevation_m_asl,
            valid_time,
        )
        combined["local_time"] = valid_time.astimezone(
            WICKLOW_HEAD_TIMEZONE
        ).isoformat()
        forecasts.append(combined)
        forecast_times_utc.append(valid_time)

    if not forecasts:
        raise InputValidationError(
            "UKV did not return any hour with a usable vertical profile for "
            f"{location_name}; try a shorter --hours value"
        )

    return {
        "location": {
            "name": location_name,
            "latitude": latitude,
            "longitude": longitude,
            "site_elevation_m_asl": elevation_m_asl,
            "timezone": BRITISH_ISLES_TIMEZONE_NAME,
        },
        "generated_at_utc": datetime.now(timezone.utc).isoformat().replace(
            "+00:00", "Z"
        ),
        "forecast_hours": len(forecasts),
        "requested_forecast_hours": forecast_hours,
        "skipped_hours_no_upper_air_data": skipped_hours,
        "astronomy": astronomy_days(
            latitude,
            longitude,
            elevation_m_asl,
            forecast_times_utc,
        ),
        "source": {
            "model": "UK Met Office Seamless",
            "near_term_model": "UKV 2 km",
            "extended_model": "UKMO Global 10 km",
            "access_service": "Open-Meteo UKMO API",
            "attribution": "Weather data by Open-Meteo.com and the UK Met Office",
        },
        "score_definition": {
            "seeing_score_1_10": (
                "Atmospheric seeing only, mapped approximately from FWHM "
                "arcseconds to a Pickering-style 1 to 10 scale. 10 is best, "
                "1 is worst. Clouds are never folded into this score."
            ),
            "observing_score_1_10": (
                "Experimental combined score: cloud clearance, seeing, "
                "visibility and darkness. 10 is best, 1 is worst."
            ),
            "imaging_score_1_10": (
                "Planetary imaging conditions: seeing and cloud only, with "
                "no darkness penalty. Target altitude is applied separately "
                "in the browser's target-specific imaging windows."
            ),
        },
        "forecasts": forecasts,
    }


def generate_wicklow_forecast(
    forecast_hours: int = 96,
    latitude: float = WICKLOW_HEAD_LATITUDE,
    longitude: float = WICKLOW_HEAD_LONGITUDE,
) -> dict[str, Any]:
    """Build a combined UKV cloud and seeing forecast for Wicklow Head.

    Kept for backward compatibility; this is now a thin wrapper around
    :func:`generate_location_forecast`.
    """

    return generate_location_forecast(
        latitude, longitude, WICKLOW_HEAD_NAME, forecast_hours
    )


def _score_class(score: int) -> str:
    if score >= 8:
        return "great"
    if score >= 6:
        return "good"
    if score >= 4:
        return "mixed"
    return "poor"


def render_html_report(report: dict[str, Any]) -> str:
    """Render a self-contained dark-theme astronomy forecast."""

    rows = []
    dark_rows = [
        item for item in report["forecasts"] if item["scores"]["light_state"] != "daylight"
    ]
    top_windows = sorted(
        dark_rows,
        key=lambda item: (
            item["scores"].get(
                "imaging_score_1_10",
                item["scores"]["observing_score_1_10"],
            ),
            -item["cloud_bands"]["total_cloud_pct"],
        ),
        reverse=True,
    )[:8]

    for item in report["forecasts"]:
        local = datetime.fromisoformat(item["local_time"])
        scores = item["scores"]
        clouds = item["cloud_bands"]
        score = scores.get("imaging_score_1_10", scores["observing_score_1_10"])
        rows.append(
            "<tr>"
            f"<td>{html.escape(local.strftime('%a %d %b %H:%M'))}</td>"
            f"<td>{html.escape(scores['light_state'])}</td>"
            f"<td>{clouds['total_cloud_pct']:.0f}%</td>"
            f"<td>{clouds['low_cloud_pct']:.0f}%</td>"
            f"<td>{clouds['mid_cloud_pct']:.0f}%</td>"
            f"<td>{clouds['high_cloud_pct']:.0f}%</td>"
            f"<td>{item['display']['arcsec']:.2f}</td>"
            f"<td><span class='score {_score_class(scores['seeing_score_1_10'])}'>"
            f"{scores['seeing_score_1_10']}</span></td>"
            f"<td><span class='score {_score_class(score)}'>{score}</span></td>"
            f"<td>{item['jet_stream']['speed_ms']:.0f} m/s</td>"
            "</tr>"
        )

    cards = []
    for item in top_windows:
        local = datetime.fromisoformat(item["local_time"])
        cards.append(
            "<div class='card'>"
            f"<strong>{html.escape(local.strftime('%a %d %b, %H:%M'))}</strong>"
            f"<div class='big'>{item['scores'].get('imaging_score_1_10', item['scores']['observing_score_1_10'])}/10</div>"
            f"<div>{item['cloud_bands']['total_cloud_pct']:.0f}% cloud, "
            f"{item['display']['arcsec']:.2f} arcsec seeing</div>"
            "</div>"
        )

    generated = html.escape(report["generated_at_utc"])
    location_full_name = report.get("location", {}).get("name", WICKLOW_HEAD_NAME)
    short_name = location_full_name.split(",")[0].strip() or location_full_name
    h1_text = html.escape(f"{short_name} astronomy forecast")
    title_text = html.escape(f"{short_name} Astronomy Forecast")
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title_text}</title>
<style>
body {{ margin: 0; background: #0b1020; color: #e7edf7; font: 15px/1.45 Segoe UI, sans-serif; }}
main {{ max-width: 1180px; margin: auto; padding: 24px; }}
h1 {{ margin-bottom: 4px; }} .muted {{ color: #9aa8bd; }}
.cards {{ display: grid; grid-template-columns: repeat(auto-fit,minmax(190px,1fr)); gap: 12px; margin: 20px 0; }}
.card {{ background: #151d31; border: 1px solid #283653; border-radius: 10px; padding: 14px; }}
.big {{ font-size: 28px; font-weight: 700; margin: 6px 0; }}
.table-wrap {{ overflow-x: auto; }}
table {{ width: 100%; border-collapse: collapse; background: #11182a; }}
th, td {{ padding: 8px 10px; border-bottom: 1px solid #27334d; text-align: right; white-space: nowrap; }}
th:first-child, td:first-child, th:nth-child(2), td:nth-child(2) {{ text-align: left; }}
th {{ position: sticky; top: 0; background: #18233a; }}
.score {{ display: inline-block; min-width: 28px; padding: 3px 7px; border-radius: 12px; text-align: center; font-weight: 700; }}
.great {{ background: #1d7a46; }} .good {{ background: #4d7d28; }}
.mixed {{ background: #9a7221; }} .poor {{ background: #963b3b; }}
code {{ color: #b8d7ff; }}
</style>
</head>
<body><main>
<h1>{h1_text}</h1>
<div class="muted">Coming {report['forecast_hours']} hours. Generated {generated}. Times are Europe/Dublin (shared UK and Ireland civil time).</div>
<h2>Best planetary imaging conditions</h2>
<div class="cards">{''.join(cards) if cards else '<div class="card">No dark forecast periods available.</div>'}</div>
<h2>Hourly forecast</h2>
<div class="table-wrap"><table>
<thead><tr><th>Local time</th><th>Light</th><th>Total cloud</th><th>Low</th><th>Mid</th><th>High</th><th>Seeing arcsec</th><th>Seeing 1-10</th><th>Imaging 1-10</th><th>Jet</th></tr></thead>
<tbody>{''.join(rows)}</tbody>
</table></div>
<p class="muted">Seeing is calculated from UKV pressure-level temperature, humidity and wind profiles. The imaging score prioritises seeing and cloud without penalising twilight. Scores are experimental and should be calibrated against captured data.</p>
<p class="muted">Attribution: Weather data by Open-Meteo.com and the UK Met Office.</p>
</main></body></html>"""


def _slugify(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return slug or "location"


def save_location_report(
    report: dict[str, Any],
    output_directory: str | Path,
    slug: str | None = None,
) -> tuple[Path, Path]:
    """Write the JSON and self-contained HTML reports for any location."""

    directory = Path(output_directory)
    directory.mkdir(parents=True, exist_ok=True)
    location_slug = slug or _slugify(
        report.get("location", {}).get("name", "location")
    )
    stamp = datetime.now(WICKLOW_HEAD_TIMEZONE).strftime("%Y%m%d-%H%M")
    json_path = directory / f"{location_slug}-forecast-{stamp}.json"
    html_path = directory / f"{location_slug}-forecast-{stamp}.html"
    json_path.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    html_path.write_text(render_html_report(report), encoding="utf-8")
    return json_path, html_path


def save_wicklow_report(
    report: dict[str, Any],
    output_directory: str | Path,
) -> tuple[Path, Path]:
    """Write the Wicklow Head reports. Kept for backward compatibility."""

    return save_location_report(report, output_directory, slug="wicklow-head")

"""Local HTTP server for the Ireland forecast UI.

The server binds to 127.0.0.1 by default and exposes three routes:

``GET /``
    The dark-theme browser UI (map, search, forecast table, cards).

``GET /api/geocode?q=...``
    A server-side proxy to the Open-Meteo Geocoding API, filtered to the
    Ireland region.

``GET /api/forecast?lat=...&lon=...&name=...&hours=96``
    A UKV seeing and cloud forecast for the requested point.

The HTTP layer uses the standard library. Planetary ephemerides are
calculated by Astronomy Engine.
"""

from __future__ import annotations

import json
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

from .geocoding import DEFAULT_RESULT_LIMIT, geocode_search
from .ireland import (
    DEFAULT_FORECAST_HOURS,
    validate_forecast_hours,
    validate_ireland_coordinates,
)
from .ui import load_index_html, load_planet_asset
from .validation import InputValidationError
from .wicklow_forecast import generate_location_forecast

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8765


def parse_geocode_params(query: dict[str, list[str]]) -> tuple[str, int]:
    """Parse and validate ``/api/geocode`` query parameters."""

    raw_query = (query.get("q") or [""])[0]
    if not raw_query.strip():
        raise InputValidationError("query parameter 'q' is required and must not be empty")
    limit_raw = (query.get("limit") or [str(DEFAULT_RESULT_LIMIT)])[0]
    try:
        limit = int(limit_raw)
    except ValueError as exc:
        raise InputValidationError("query parameter 'limit' must be an integer") from exc
    if limit <= 0:
        raise InputValidationError("query parameter 'limit' must be a positive integer")
    return raw_query, limit


def parse_forecast_params(
    query: dict[str, list[str]],
) -> tuple[float, float, str, int]:
    """Parse and validate ``/api/forecast`` query parameters."""

    lat_raw = (query.get("lat") or [None])[0]
    lon_raw = (query.get("lon") or [None])[0]
    if lat_raw is None or lon_raw is None:
        raise InputValidationError("query parameters 'lat' and 'lon' are required")
    try:
        latitude = float(lat_raw)
        longitude = float(lon_raw)
    except ValueError as exc:
        raise InputValidationError("'lat' and 'lon' must be numeric") from exc

    name = (query.get("name") or ["Selected location"])[0].strip() or "Selected location"

    hours_raw = (query.get("hours") or [str(DEFAULT_FORECAST_HOURS)])[0]
    try:
        hours_value: float = float(hours_raw)
    except ValueError as exc:
        raise InputValidationError("'hours' must be a whole number") from exc

    validate_ireland_coordinates(latitude, longitude)
    hours = validate_forecast_hours(hours_value)
    return latitude, longitude, name, hours


def _write_json(handler: BaseHTTPRequestHandler, status: int, payload: Any) -> None:
    body = json.dumps(payload).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


def _write_html(handler: BaseHTTPRequestHandler, status: int, html_text: str) -> None:
    body = html_text.encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "text/html; charset=utf-8")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


def _write_webp(handler: BaseHTTPRequestHandler, status: int, body: bytes) -> None:
    handler.send_response(status)
    handler.send_header("Content-Type", "image/webp")
    handler.send_header("Cache-Control", "public, max-age=86400")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


class IrelandForecastRequestHandler(BaseHTTPRequestHandler):
    """Routes ``/``, ``/api/geocode`` and ``/api/forecast``."""

    server_version = "MeteoblueSeeingIrelandForecast/0.1"

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A002 - stdlib signature
        # Keep the console quiet by default; override to add logging if needed.
        return

    def do_GET(self) -> None:  # noqa: N802 - required stdlib method name
        parsed = urllib.parse.urlsplit(self.path)
        path = parsed.path
        query = urllib.parse.parse_qs(parsed.query, keep_blank_values=True)
        try:
            if path in ("/", "/index.html"):
                _write_html(self, 200, load_index_html())
            elif path.startswith("/assets/"):
                filename = path.removeprefix("/assets/")
                try:
                    body = load_planet_asset(filename)
                except FileNotFoundError:
                    _write_json(self, 404, {"error": f"not found: {path}"})
                else:
                    _write_webp(self, 200, body)
            elif path == "/api/health":
                _write_json(
                    self,
                    200,
                    {
                        "status": "ok",
                        "service": "Ireland astronomy forecast",
                        "version": "0.2",
                    },
                )
            elif path == "/api/geocode":
                raw_query, limit = parse_geocode_params(query)
                results = geocode_search(raw_query, limit=limit)
                _write_json(self, 200, {"results": results})
            elif path == "/api/forecast":
                latitude, longitude, name, hours = parse_forecast_params(query)
                report = generate_location_forecast(
                    latitude, longitude, name, forecast_hours=hours
                )
                _write_json(self, 200, report)
            else:
                _write_json(self, 404, {"error": f"not found: {path}"})
        except InputValidationError as exc:
            _write_json(self, 400, {"error": str(exc)})
        except Exception as exc:  # defensive: never leak a stack trace to the client
            _write_json(self, 500, {"error": f"internal error: {exc}"})


def create_server(
    host: str = DEFAULT_HOST,
    port: int = DEFAULT_PORT,
) -> ThreadingHTTPServer:
    """Create (but do not start) the local HTTP server."""

    return ThreadingHTTPServer((host, port), IrelandForecastRequestHandler)


def serve_forever(host: str = DEFAULT_HOST, port: int = DEFAULT_PORT) -> None:
    """Start the local server and block until interrupted."""

    httpd = create_server(host, port)
    print(f"Serving the Ireland astronomy forecast UI on http://{host}:{port}/")
    print("Press Ctrl+C to stop.")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()

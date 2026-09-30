"""Azure Functions entry points for the public forecast API."""

from __future__ import annotations

import json
import logging
import sys
import urllib.error
from pathlib import Path
from typing import Any, Callable

import azure.functions as func

ROOT = Path(__file__).resolve().parent
SOURCE_DIRECTORY = ROOT / "src"
if str(SOURCE_DIRECTORY) not in sys.path:
    sys.path.insert(0, str(SOURCE_DIRECTORY))

from meteoblue_seeing.geocoding import geocode_search
from meteoblue_seeing.server import parse_forecast_params, parse_geocode_params
from meteoblue_seeing.validation import InputValidationError
from meteoblue_seeing.wicklow_forecast import generate_location_forecast

app = func.FunctionApp(http_auth_level=func.AuthLevel.ANONYMOUS)


def _json_response(payload: Any, status_code: int = 200) -> func.HttpResponse:
    return func.HttpResponse(
        json.dumps(payload, ensure_ascii=False),
        status_code=status_code,
        mimetype="application/json",
        charset="utf-8",
    )


def _query(req: func.HttpRequest) -> dict[str, list[str]]:
    return {name: [value] for name, value in req.params.items()}


def _handle(operation: Callable[[], Any]) -> func.HttpResponse:
    try:
        return _json_response(operation())
    except InputValidationError as exc:
        return _json_response({"error": str(exc)}, 400)
    except (TimeoutError, urllib.error.HTTPError, urllib.error.URLError):
        logging.exception("Upstream forecast provider request failed")
        return _json_response(
            {"error": "The forecast data provider could not be reached. Try again shortly."},
            502,
        )
    except Exception:
        logging.exception("Unhandled forecast API error")
        return _json_response({"error": "Internal forecast service error."}, 500)


@app.function_name(name="health")
@app.route(route="health", methods=["GET"])
def health(req: func.HttpRequest) -> func.HttpResponse:
    del req
    return _json_response(
        {
            "status": "ok",
            "service": "British Isles astronomy forecast",
            "version": "0.3",
        }
    )


@app.function_name(name="geocode")
@app.route(route="geocode", methods=["GET"])
def geocode(req: func.HttpRequest) -> func.HttpResponse:
    def operation() -> dict[str, Any]:
        raw_query, limit = parse_geocode_params(_query(req))
        return {"results": geocode_search(raw_query, limit=limit)}

    return _handle(operation)


@app.function_name(name="forecast")
@app.route(route="forecast", methods=["GET"])
def forecast(req: func.HttpRequest) -> func.HttpResponse:
    def operation() -> dict[str, Any]:
        latitude, longitude, name, hours = parse_forecast_params(_query(req))
        return generate_location_forecast(
            latitude,
            longitude,
            name,
            forecast_hours=hours,
        )

    return _handle(operation)

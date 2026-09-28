"""Direct Met Office UKV cloud access through AWS Open Data."""

from __future__ import annotations

import bisect
import math
import tempfile
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .ukv_clouds import UkvCloudForecast
from .validation import InputValidationError, parse_utc_datetime

BUCKET_BASE = "https://met-office-atmospheric-model-data.s3.eu-west-2.amazonaws.com"
DATASET_PREFIX = "uk-deterministic-2km"
PARAMETERS = {
    "low_cloud_pct": "cloud_amount_of_low_cloud",
    "mid_cloud_pct": "cloud_amount_of_medium_cloud",
    "high_cloud_pct": "cloud_amount_of_high_cloud",
    "total_cloud_pct": "cloud_amount_of_total_cloud",
}


class UkvDependencyError(RuntimeError):
    """Raised when optional NetCDF dependencies are unavailable."""


def _read_url(url: str, timeout_seconds: float = 60.0) -> bytes:
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "meteoblue-seeing-reconstruction/0.1"},
    )
    with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
        return response.read()


def _list_s3(prefix: str, delimiter: str | None = None) -> bytes:
    query = {"list-type": "2", "prefix": prefix}
    if delimiter is not None:
        query["delimiter"] = delimiter
    url = f"{BUCKET_BASE}/?{urllib.parse.urlencode(query)}"
    return _read_url(url)


def parse_s3_prefixes(xml_bytes: bytes) -> list[str]:
    root = ET.fromstring(xml_bytes)
    namespace = {"s3": "http://s3.amazonaws.com/doc/2006-03-01/"}
    return [
        element.text
        for element in root.findall("s3:CommonPrefixes/s3:Prefix", namespace)
        if element.text
    ]


def parse_s3_keys(xml_bytes: bytes) -> list[str]:
    root = ET.fromstring(xml_bytes)
    namespace = {"s3": "http://s3.amazonaws.com/doc/2006-03-01/"}
    truncated = root.findtext("s3:IsTruncated", default="false", namespaces=namespace)
    if truncated.lower() == "true":
        raise InputValidationError(
            "AWS object listing was truncated unexpectedly for an exact valid-time prefix"
        )
    return [
        element.text
        for element in root.findall("s3:Contents/s3:Key", namespace)
        if element.text
    ]


def _candidate_run_prefixes(valid_time_utc: datetime) -> list[str]:
    now_utc = datetime.now(timezone.utc)
    starting_date = min(valid_time_utc, now_utc).date()
    prefixes: list[str] = []
    for days_back in range(4):
        day = starting_date - timedelta(days=days_back)
        date_prefix = f"{DATASET_PREFIX}/{day:%Y%m%d}"
        prefixes.extend(parse_s3_prefixes(_list_s3(date_prefix, delimiter="/")))
    return sorted(set(prefixes), reverse=True)


def _find_cloud_keys(
    valid_time_utc: datetime,
) -> tuple[str, dict[str, str]]:
    valid_token = valid_time_utc.strftime("%Y%m%dT%H00Z")
    for run_prefix in _candidate_run_prefixes(valid_time_utc):
        keys = parse_s3_keys(_list_s3(f"{run_prefix}{valid_token}-"))
        matched: dict[str, str] = {}
        for output_name, parameter_name in PARAMETERS.items():
            suffix = f"-{parameter_name}.nc"
            key = next((candidate for candidate in keys if candidate.endswith(suffix)), None)
            if key is not None:
                matched[output_name] = key
        if len(matched) == len(PARAMETERS):
            return run_prefix.rstrip("/").split("/")[-1], matched
    raise InputValidationError(
        "no complete UKV cloud forecast was found in the AWS Open Data archive "
        f"for {valid_time_utc.isoformat()}"
    )


def _nearest_index(sorted_values, target: float) -> int:
    values = [float(value) for value in sorted_values]
    position = bisect.bisect_left(values, target)
    if position <= 0:
        return 0
    if position >= len(values):
        return len(values) - 1
    before = position - 1
    return before if abs(values[before] - target) <= abs(values[position] - target) else position


def _extract_cloud_fraction(
    path: Path,
    latitude: float,
    longitude: float,
) -> tuple[float, float, float]:
    try:
        from netCDF4 import Dataset
        from pyproj import CRS, Transformer
    except ImportError as exc:
        raise UkvDependencyError(
            "direct UKV access requires optional dependencies; "
            "install with: pip install -e \".[ukv]\""
        ) from exc

    with Dataset(path) as dataset:
        mapping = dataset.variables["lambert_azimuthal_equal_area"]
        mapping_attrs = {name: getattr(mapping, name) for name in mapping.ncattrs()}
        projection = CRS.from_cf(mapping_attrs)
        transformer = Transformer.from_crs("EPSG:4326", projection, always_xy=True)
        x_target, y_target = transformer.transform(longitude, latitude)

        x_values = dataset.variables["projection_x_coordinate"][:]
        y_values = dataset.variables["projection_y_coordinate"][:]
        x_index = _nearest_index(x_values, x_target)
        y_index = _nearest_index(y_values, y_target)
        x_actual = float(x_values[x_index])
        y_actual = float(y_values[y_index])

        cloud_variable = next(
            (
                variable
                for variable in dataset.variables.values()
                if str(getattr(variable, "standard_name", "")).endswith(
                    "cloud_area_fraction"
                )
                and variable.dimensions
                == ("projection_y_coordinate", "projection_x_coordinate")
            ),
            None,
        )
        if cloud_variable is None:
            raise InputValidationError(
                f"no cloud area fraction variable found in {path.name}"
            )
        value = cloud_variable[y_index, x_index]
        if getattr(value, "mask", False):
            raise InputValidationError(
                "the requested coordinate falls outside the usable UKV grid"
            )
        fraction = float(value)
        if not math.isfinite(fraction) or not 0.0 <= fraction <= 1.0:
            raise InputValidationError(
                f"unexpected UKV cloud fraction at requested coordinate: {fraction}"
            )
        return fraction * 100.0, x_actual, y_actual


def fetch_ukv_cloud_forecast(
    latitude: float,
    longitude: float,
    valid_time: str | datetime,
) -> tuple[UkvCloudForecast, dict]:
    """Fetch one hourly UKV cloud forecast directly from AWS Open Data."""

    if not math.isfinite(latitude) or not -90.0 <= latitude <= 90.0:
        raise InputValidationError("latitude must be finite and within [-90, 90]")
    if not math.isfinite(longitude) or not -180.0 <= longitude <= 180.0:
        raise InputValidationError("longitude must be finite and within [-180, 180]")
    if isinstance(valid_time, str):
        valid_time_utc = parse_utc_datetime(valid_time)
    else:
        if valid_time.tzinfo is None:
            raise InputValidationError("valid_time must include a UTC offset")
        valid_time_utc = valid_time.astimezone(timezone.utc)
    if valid_time_utc.minute or valid_time_utc.second or valid_time_utc.microsecond:
        raise InputValidationError("AWS UKV cloud valid_time must be on an exact hour")

    run_token, keys = _find_cloud_keys(valid_time_utc)
    values: dict[str, float] = {}
    grid_points: set[tuple[float, float]] = set()
    with tempfile.TemporaryDirectory(prefix="ukv-cloud-") as directory:
        directory_path = Path(directory)
        for output_name, key in keys.items():
            local_path = directory_path / Path(key).name
            local_path.write_bytes(_read_url(f"{BUCKET_BASE}/{urllib.parse.quote(key)}"))
            percentage, x_coord, y_coord = _extract_cloud_fraction(
                local_path, latitude, longitude
            )
            values[output_name] = percentage
            grid_points.add((x_coord, y_coord))

    if len(grid_points) != 1:
        raise InputValidationError("UKV cloud files resolved to inconsistent grid points")
    x_coord, y_coord = next(iter(grid_points))
    forecast = UkvCloudForecast(
        valid_time_utc=valid_time_utc,
        low_cloud_pct=values["low_cloud_pct"],
        mid_cloud_pct=values["mid_cloud_pct"],
        high_cloud_pct=values["high_cloud_pct"],
        total_cloud_pct=values["total_cloud_pct"],
    )
    metadata = {
        "provider": "Met Office",
        "distribution": "AWS Open Data",
        "model": "UKV",
        "model_run_utc": run_token,
        "valid_time_utc": valid_time_utc.isoformat().replace("+00:00", "Z"),
        "latitude": latitude,
        "longitude": longitude,
        "projection_x_m": x_coord,
        "projection_y_m": y_coord,
        "source_keys": keys,
        "licence": "CC BY-SA 4.0",
        "layer_definition": (
            "UKV low, medium and high cloud categories; not assumed to match "
            "meteoblue's 0 to 4, 4 to 8 and 8 to 15 km bands"
        ),
    }
    return forecast, metadata

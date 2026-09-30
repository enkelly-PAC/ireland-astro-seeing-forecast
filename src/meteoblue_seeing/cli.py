"""Command line interface.

Commands:
  forecast    Run a full seeing reconstruction on a JSON input file.
  combine-ukv Combine seeing with user-supplied Windy UKV cloud forecasts.
  combine-ukv-aws
              Combine seeing with UKV clouds fetched from AWS Open Data.
  wicklow-forecast
              Generate a four-day UKV astronomy forecast for Wicklow Head.
  british-isles-forecast
              Generate a rolling UKV astronomy forecast for any British
              Isles location by latitude, longitude and name. The
              ``ireland-forecast`` alias is kept for backward
              compatibility.
  serve       Start the local British Isles forecast browser UI and API
              server.
  parse-html  Extract table rows from a locally saved HTML page.
  calibrate   Fit model coefficients against a permitted CSV dataset.
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import Sequence

from .british_isles import DEFAULT_FORECAST_HOURS
from .calibrate import calibrate, load_calibration_csv
from .config import SeeingConfig
from .forecast import run_forecast
from .html_parser import largest_table, parse_tables_from_file, rows_to_dicts
from .server import DEFAULT_HOST, DEFAULT_PORT, serve_forever
from .ukv_clouds import (
    combine_forecast_with_ukv_cloud,
    load_windy_ukv_csv,
    match_ukv_cloud,
)
from .ukv_aws import UkvDependencyError, fetch_ukv_cloud_forecast
from .validation import ForecastInput, InputValidationError
from .wicklow_forecast import (
    generate_location_forecast,
    generate_wicklow_forecast,
    save_location_report,
    save_wicklow_report,
)


def _load_json_file(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def _cmd_forecast(args: argparse.Namespace) -> int:
    try:
        payload = _load_json_file(args.input)
    except (OSError, json.JSONDecodeError) as exc:
        print(f"error: could not read input file '{args.input}': {exc}", file=sys.stderr)
        return 2

    if args.config:
        try:
            cfg = SeeingConfig.load(args.config)
        except (OSError, json.JSONDecodeError) as exc:
            print(f"error: could not read config file '{args.config}': {exc}", file=sys.stderr)
            return 2
    else:
        cfg = SeeingConfig()

    if args.use_inline_jet_threshold:
        cfg.use_inline_jet_threshold = True
    if args.wavelength_nm is not None:
        cfg.wavelength_nm = args.wavelength_nm

    try:
        result = run_forecast(payload, cfg)
    except InputValidationError as exc:
        print(f"input validation error: {exc}", file=sys.stderr)
        return 1

    text = json.dumps(result, indent=2, sort_keys=True)
    if args.output:
        with open(args.output, "w", encoding="utf-8") as handle:
            handle.write(text)
            handle.write("\n")
    else:
        print(text)
    return 0


def _cmd_combine_ukv(args: argparse.Namespace) -> int:
    try:
        payload = _load_json_file(args.input)
        cloud_rows = load_windy_ukv_csv(args.ukv_clouds)
    except (OSError, json.JSONDecodeError, InputValidationError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    cfg = SeeingConfig()
    if args.config:
        try:
            cfg = SeeingConfig.load(args.config)
        except (OSError, json.JSONDecodeError) as exc:
            print(f"error: could not read config file '{args.config}': {exc}", file=sys.stderr)
            return 2
    if args.use_inline_jet_threshold:
        cfg.use_inline_jet_threshold = True

    profiles = payload.get("profiles") if isinstance(payload, dict) else None
    is_batch = profiles is not None
    if is_batch:
        if not isinstance(profiles, list) or not profiles:
            print("input validation error: 'profiles' must be a non-empty list", file=sys.stderr)
            return 1
        raw_profiles = profiles
    else:
        raw_profiles = [payload]

    combined_results = []
    try:
        for raw_profile in raw_profiles:
            parsed = ForecastInput.from_dict(raw_profile)
            if parsed.valid_time_utc is None:
                raise InputValidationError(
                    "valid_time_utc is required when combining with Windy UKV clouds"
                )
            seeing_result = run_forecast(raw_profile, cfg)
            cloud_row, offset = match_ukv_cloud(
                cloud_rows,
                parsed.valid_time_utc,
                args.tolerance_minutes,
            )
            combined_results.append(
                combine_forecast_with_ukv_cloud(seeing_result, cloud_row, offset)
            )
    except InputValidationError as exc:
        print(f"input validation error: {exc}", file=sys.stderr)
        return 1

    output: object = {"forecasts": combined_results} if is_batch else combined_results[0]
    text = json.dumps(output, indent=2, sort_keys=True)
    if args.output:
        with open(args.output, "w", encoding="utf-8") as handle:
            handle.write(text)
            handle.write("\n")
    else:
        print(text)
    return 0


def _cmd_combine_ukv_aws(args: argparse.Namespace) -> int:
    try:
        payload = _load_json_file(args.input)
    except (OSError, json.JSONDecodeError) as exc:
        print(f"error: could not read input file '{args.input}': {exc}", file=sys.stderr)
        return 2

    cfg = SeeingConfig()
    if args.config:
        try:
            cfg = SeeingConfig.load(args.config)
        except (OSError, json.JSONDecodeError) as exc:
            print(f"error: could not read config file '{args.config}': {exc}", file=sys.stderr)
            return 2
    if args.use_inline_jet_threshold:
        cfg.use_inline_jet_threshold = True

    profiles = payload.get("profiles") if isinstance(payload, dict) else None
    is_batch = profiles is not None
    if is_batch:
        if not isinstance(profiles, list) or not profiles:
            print("input validation error: 'profiles' must be a non-empty list", file=sys.stderr)
            return 1
        raw_profiles = profiles
    else:
        raw_profiles = [payload]

    combined_results = []
    cache: dict[str, tuple] = {}
    try:
        for raw_profile in raw_profiles:
            parsed = ForecastInput.from_dict(raw_profile)
            if parsed.valid_time_utc is None:
                raise InputValidationError(
                    "valid_time_utc is required when combining with UKV clouds"
                )
            timestamp = parsed.valid_time_utc.isoformat()
            if timestamp not in cache:
                cache[timestamp] = fetch_ukv_cloud_forecast(
                    args.latitude,
                    args.longitude,
                    parsed.valid_time_utc,
                )
            cloud_row, source_metadata = cache[timestamp]
            seeing_result = run_forecast(raw_profile, cfg)
            combined = combine_forecast_with_ukv_cloud(
                seeing_result, cloud_row, 0.0
            )
            combined["cloud_source"] = {
                **source_metadata,
                "network_fetch_performed": True,
            }
            combined_results.append(combined)
    except (InputValidationError, UkvDependencyError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    output: object = {"forecasts": combined_results} if is_batch else combined_results[0]
    text = json.dumps(output, indent=2, sort_keys=True)
    if args.output:
        with open(args.output, "w", encoding="utf-8") as handle:
            handle.write(text)
            handle.write("\n")
    else:
        print(text)
    return 0


def _cmd_parse_html(args: argparse.Namespace) -> int:
    try:
        tables = parse_tables_from_file(args.input)
    except OSError as exc:
        print(f"error: could not read HTML file '{args.input}': {exc}", file=sys.stderr)
        return 2

    if not tables:
        print("no tables found in the supplied HTML file", file=sys.stderr)
        return 1

    if args.table_index is not None:
        if args.table_index < 0 or args.table_index >= len(tables):
            print(
                f"error: table-index {args.table_index} out of range "
                f"(found {len(tables)} table(s))",
                file=sys.stderr,
            )
            return 2
        table = tables[args.table_index]
    else:
        table = largest_table(tables)

    if args.as_records:
        output: object = rows_to_dicts(table)
    else:
        output = table

    text = json.dumps(output, indent=2, sort_keys=False)
    if args.output:
        with open(args.output, "w", encoding="utf-8") as handle:
            handle.write(text)
            handle.write("\n")
    else:
        print(text)
    return 0


def _cmd_wicklow_forecast(args: argparse.Namespace) -> int:
    try:
        report = generate_wicklow_forecast(forecast_hours=args.hours)
        json_path, html_path = save_wicklow_report(report, args.output_directory)
    except (InputValidationError, OSError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    dark_forecasts = [
        item
        for item in report["forecasts"]
        if item["scores"]["light_state"] != "daylight"
    ]
    best = max(
        dark_forecasts,
        key=lambda item: item["scores"]["imaging_score_1_10"],
        default=None,
    )
    output = {
        "json_report": str(json_path),
        "html_report": str(html_path),
        "forecast_hours": report["forecast_hours"],
        "best_window": (
            {
                "local_time": best["local_time"],
                "seeing_score_1_10": best["scores"]["seeing_score_1_10"],
                "imaging_score_1_10": best["scores"]["imaging_score_1_10"],
                "total_cloud_pct": best["cloud_bands"]["total_cloud_pct"],
                "seeing_arcsec": best["display"]["arcsec"],
            }
            if best is not None
            else None
        ),
    }
    print(json.dumps(output, indent=2, sort_keys=True))
    return 0


def _cmd_british_isles_forecast(args: argparse.Namespace) -> int:
    try:
        report = generate_location_forecast(
            args.latitude,
            args.longitude,
            args.name,
            forecast_hours=args.hours,
        )
        json_path, html_path = save_location_report(report, args.output_directory)
    except (InputValidationError, OSError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    dark_forecasts = [
        item
        for item in report["forecasts"]
        if item["scores"]["light_state"] != "daylight"
    ]
    best = max(
        dark_forecasts,
        key=lambda item: item["scores"]["imaging_score_1_10"],
        default=None,
    )
    output = {
        "json_report": str(json_path),
        "html_report": str(html_path),
        "location": report["location"],
        "forecast_hours": report["forecast_hours"],
        "best_window": (
            {
                "local_time": best["local_time"],
                "seeing_score_1_10": best["scores"]["seeing_score_1_10"],
                "imaging_score_1_10": best["scores"]["imaging_score_1_10"],
                "total_cloud_pct": best["cloud_bands"]["total_cloud_pct"],
                "seeing_arcsec": best["display"]["arcsec"],
            }
            if best is not None
            else None
        ),
    }
    print(json.dumps(output, indent=2, sort_keys=True))
    return 0


def _cmd_serve(args: argparse.Namespace) -> int:
    serve_forever(host=args.host, port=args.port)
    return 0


def _cmd_calibrate(args: argparse.Namespace) -> int:
    try:
        cases = load_calibration_csv(args.input)
    except (OSError, InputValidationError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    base_cfg = SeeingConfig()
    if args.config:
        try:
            base_cfg = SeeingConfig.load(args.config)
        except (OSError, json.JSONDecodeError) as exc:
            print(f"error: could not read config file '{args.config}': {exc}", file=sys.stderr)
            return 2

    fitted_cfg, metrics = calibrate(cases, base_cfg, passes=args.passes)

    fitted_cfg.save(args.output_config)

    metrics_text = json.dumps(metrics.to_dict(), indent=2, sort_keys=True)
    if args.output_metrics:
        with open(args.output_metrics, "w", encoding="utf-8") as handle:
            handle.write(metrics_text)
            handle.write("\n")
    else:
        print(metrics_text)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="meteoblue_seeing",
        description=(
            "Independent, standard library only reconstruction of meteoblue "
            "style astronomy seeing output from public documentation and "
            "standard atmospheric optics."
        ),
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    forecast_parser = subparsers.add_parser(
        "forecast", help="run a full seeing reconstruction on a JSON input file"
    )
    forecast_parser.add_argument("input", help="path to a forecast input JSON file")
    forecast_parser.add_argument("--config", help="path to a SeeingConfig JSON file")
    forecast_parser.add_argument(
        "--output", help="write result JSON to this file instead of stdout"
    )
    forecast_parser.add_argument(
        "--use-inline-jet-threshold",
        action="store_true",
        help=(
            "use the 20 m/s inline help jet stream poor threshold instead of "
            "the default 35 m/s detailed help threshold"
        ),
    )
    forecast_parser.add_argument(
        "--wavelength-nm",
        type=float,
        default=None,
        help="override the observing wavelength in nanometres (default 500)",
    )
    forecast_parser.set_defaults(func=_cmd_forecast)

    combine_parser = subparsers.add_parser(
        "combine-ukv",
        help=(
            "combine seeing with a user-supplied Windy UKV cloud CSV; "
            "no network request is made"
        ),
    )
    combine_parser.add_argument(
        "input",
        help=(
            "forecast input JSON with valid_time_utc, or an object containing "
            "a non-empty profiles list"
        ),
    )
    combine_parser.add_argument(
        "ukv_clouds",
        help="CSV containing valid_time_utc and low, mid and high UKV cloud percentages",
    )
    combine_parser.add_argument("--config", help="path to a SeeingConfig JSON file")
    combine_parser.add_argument(
        "--output", help="write combined result JSON to this file instead of stdout"
    )
    combine_parser.add_argument(
        "--tolerance-minutes",
        type=float,
        default=90.0,
        help="maximum timestamp difference allowed for nearest matching (default: 90)",
    )
    combine_parser.add_argument(
        "--use-inline-jet-threshold",
        action="store_true",
        help="use the 20 m/s inline jet threshold instead of the default 35 m/s",
    )
    combine_parser.set_defaults(func=_cmd_combine_ukv)

    combine_aws_parser = subparsers.add_parser(
        "combine-ukv-aws",
        help="fetch Met Office UKV clouds from AWS Open Data and combine with seeing",
    )
    combine_aws_parser.add_argument(
        "input",
        help=(
            "forecast input JSON with valid_time_utc, or an object containing "
            "a non-empty profiles list"
        ),
    )
    combine_aws_parser.add_argument("--latitude", type=float, required=True)
    combine_aws_parser.add_argument("--longitude", type=float, required=True)
    combine_aws_parser.add_argument("--config", help="path to a SeeingConfig JSON file")
    combine_aws_parser.add_argument(
        "--output", help="write combined result JSON to this file instead of stdout"
    )
    combine_aws_parser.add_argument(
        "--use-inline-jet-threshold",
        action="store_true",
        help="use the 20 m/s inline jet threshold instead of the default 35 m/s",
    )
    combine_aws_parser.set_defaults(func=_cmd_combine_ukv_aws)

    wicklow_parser = subparsers.add_parser(
        "wicklow-forecast",
        help="generate a four-day cloud and seeing forecast for Wicklow Head",
    )
    wicklow_parser.add_argument(
        "--hours",
        type=int,
        default=96,
        help="rolling forecast length in hours, 1 to 120 (default: 96)",
    )
    wicklow_parser.add_argument(
        "--output-directory",
        default="reports",
        help="directory for JSON and HTML reports (default: reports)",
    )
    wicklow_parser.set_defaults(func=_cmd_wicklow_forecast)

    british_isles_parser = subparsers.add_parser(
        "british-isles-forecast",
        aliases=["ireland-forecast"],
        help=(
            "generate a rolling cloud and seeing forecast for any British "
            "Isles location (the ireland-forecast alias is kept for "
            "backward compatibility)"
        ),
    )
    british_isles_parser.add_argument(
        "--latitude", type=float, required=True, help="latitude in decimal degrees"
    )
    british_isles_parser.add_argument(
        "--longitude", type=float, required=True, help="longitude in decimal degrees"
    )
    british_isles_parser.add_argument(
        "--name",
        required=True,
        help="display name for the location, used in reports and filenames",
    )
    british_isles_parser.add_argument(
        "--hours",
        type=int,
        default=DEFAULT_FORECAST_HOURS,
        help="rolling forecast length in hours, 1 to 120 (default: 96)",
    )
    british_isles_parser.add_argument(
        "--output-directory",
        default="reports",
        help="directory for JSON and HTML reports (default: reports)",
    )
    british_isles_parser.set_defaults(func=_cmd_british_isles_forecast)

    serve_parser = subparsers.add_parser(
        "serve",
        help="start the local British Isles forecast browser UI and API server",
    )
    serve_parser.add_argument(
        "--host",
        default=DEFAULT_HOST,
        help="interface to bind (default: 127.0.0.1, local machine only)",
    )
    serve_parser.add_argument(
        "--port",
        type=int,
        default=DEFAULT_PORT,
        help="TCP port to listen on (default: 8765)",
    )
    serve_parser.set_defaults(func=_cmd_serve)

    parse_html_parser = subparsers.add_parser(
        "parse-html",
        help="extract table rows from a locally saved meteoblue style HTML page",
    )
    parse_html_parser.add_argument("input", help="path to a locally saved HTML file")
    parse_html_parser.add_argument(
        "--table-index",
        type=int,
        default=None,
        help="which table to extract (0-based); default is the largest table",
    )
    parse_html_parser.add_argument(
        "--as-records",
        action="store_true",
        help="treat the first row as a header and emit a list of objects",
    )
    parse_html_parser.add_argument(
        "--output", help="write result JSON to this file instead of stdout"
    )
    parse_html_parser.set_defaults(func=_cmd_parse_html)

    calibrate_parser = subparsers.add_parser(
        "calibrate",
        help="fit model coefficients against a permitted CSV calibration dataset",
    )
    calibrate_parser.add_argument("input", help="path to a calibration CSV file")
    calibrate_parser.add_argument(
        "--config", help="starting SeeingConfig JSON file (default: built-in defaults)"
    )
    calibrate_parser.add_argument(
        "--output-config",
        default="calibrated_config.json",
        help="where to write the fitted SeeingConfig JSON (default: %(default)s)",
    )
    calibrate_parser.add_argument(
        "--output-metrics",
        default=None,
        help="write fit metrics JSON to this file instead of stdout",
    )
    calibrate_parser.add_argument(
        "--passes",
        type=int,
        default=2,
        help="number of coordinate-descent sweeps over the coefficient list (default: 2)",
    )
    calibrate_parser.set_defaults(func=_cmd_calibrate)

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())

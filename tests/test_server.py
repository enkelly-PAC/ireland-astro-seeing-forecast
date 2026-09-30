import unittest
import json
import threading
import urllib.request

from meteoblue_seeing.server import (
    create_server,
    parse_forecast_params,
    parse_geocode_params,
)
from meteoblue_seeing.validation import InputValidationError


class TestParseGeocodeParams(unittest.TestCase):
    def test_parses_query_and_default_limit(self):
        query, limit = parse_geocode_params({"q": ["Galway"]})
        self.assertEqual(query, "Galway")
        self.assertEqual(limit, 8)

    def test_custom_limit_is_parsed(self):
        _, limit = parse_geocode_params({"q": ["Birr"], "limit": ["3"]})
        self.assertEqual(limit, 3)

    def test_missing_query_is_rejected(self):
        with self.assertRaises(InputValidationError):
            parse_geocode_params({})

    def test_blank_query_is_rejected(self):
        with self.assertRaises(InputValidationError):
            parse_geocode_params({"q": ["   "]})

    def test_non_integer_limit_is_rejected(self):
        with self.assertRaises(InputValidationError):
            parse_geocode_params({"q": ["Cork"], "limit": ["abc"]})

    def test_non_positive_limit_is_rejected(self):
        with self.assertRaises(InputValidationError):
            parse_geocode_params({"q": ["Cork"], "limit": ["0"]})


class TestParseForecastParams(unittest.TestCase):
    def test_parses_valid_wicklow_point(self):
        latitude, longitude, name, hours = parse_forecast_params(
            {
                "lat": ["52.96544"],
                "lon": ["-6.00233"],
                "name": ["Wicklow Head"],
                "hours": ["96"],
            }
        )
        self.assertAlmostEqual(latitude, 52.96544)
        self.assertAlmostEqual(longitude, -6.00233)
        self.assertEqual(name, "Wicklow Head")
        self.assertEqual(hours, 96)

    def test_defaults_name_and_hours_when_absent(self):
        _, _, name, hours = parse_forecast_params(
            {"lat": ["53.27"], "lon": ["-9.05"]}
        )
        self.assertEqual(name, "Selected location")
        self.assertEqual(hours, 96)

    def test_missing_lat_is_rejected(self):
        with self.assertRaises(InputValidationError):
            parse_forecast_params({"lon": ["-6.0"]})

    def test_non_numeric_lat_is_rejected(self):
        with self.assertRaises(InputValidationError):
            parse_forecast_params({"lat": ["north"], "lon": ["-6.0"]})

    def test_london_is_now_accepted_as_great_britain_is_in_scope(self):
        latitude, longitude, name, hours = parse_forecast_params(
            {"lat": ["51.5072"], "lon": ["-0.1276"], "name": ["London"]}
        )
        self.assertAlmostEqual(latitude, 51.5072)
        self.assertAlmostEqual(longitude, -0.1276)

    def test_out_of_british_isles_coordinates_are_rejected(self):
        with self.assertRaises(InputValidationError):
            # Paris, France: continental Europe is out of scope.
            parse_forecast_params({"lat": ["48.8566"], "lon": ["2.3522"]})

    def test_hours_out_of_range_is_rejected(self):
        with self.assertRaises(InputValidationError):
            parse_forecast_params(
                {"lat": ["53.0"], "lon": ["-8.0"], "hours": ["200"]}
            )

    def test_non_integer_hours_is_rejected(self):
        with self.assertRaises(InputValidationError):
            parse_forecast_params(
                {"lat": ["53.0"], "lon": ["-8.0"], "hours": ["48.5"]}
            )


class TestHealthEndpoint(unittest.TestCase):
    def test_health_endpoint(self):
        server = create_server("127.0.0.1", 0)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            port = server.server_address[1]
            with urllib.request.urlopen(
                f"http://127.0.0.1:{port}/api/health", timeout=5
            ) as response:
                payload = json.loads(response.read().decode("utf-8"))
            self.assertEqual(response.status, 200)
            self.assertEqual(payload["status"], "ok")
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)

    def test_planet_asset_endpoint(self):
        server = create_server("127.0.0.1", 0)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            port = server.server_address[1]
            with urllib.request.urlopen(
                f"http://127.0.0.1:{port}/assets/planet-saturn.webp",
                timeout=5,
            ) as response:
                body = response.read()
            self.assertEqual(response.status, 200)
            self.assertEqual(response.headers["Content-Type"], "image/webp")
            self.assertGreater(len(body), 1000)
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)

    def test_clavius_seeing_asset_endpoint(self):
        server = create_server("127.0.0.1", 0)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            port = server.server_address[1]
            with urllib.request.urlopen(
                f"http://127.0.0.1:{port}/assets/seeing-moon-clavius.webp",
                timeout=5,
            ) as response:
                body = response.read()
            self.assertEqual(response.status, 200)
            self.assertEqual(response.headers["Content-Type"], "image/webp")
            self.assertGreater(len(body), 10000)
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)


if __name__ == "__main__":
    unittest.main()

import json
import unittest
from unittest.mock import patch

import azure.functions as func

import function_app


def request(path: str, params: dict[str, str] | None = None) -> func.HttpRequest:
    return func.HttpRequest(
        method="GET",
        url=f"http://localhost/api/{path}",
        body=None,
        params=params or {},
    )


class TestAzureFunctionEndpoints(unittest.TestCase):
    def test_health(self):
        response = function_app.health(request("health"))
        payload = json.loads(response.get_body())

        self.assertEqual(response.status_code, 200)
        self.assertEqual(payload["status"], "ok")

    @patch("function_app.geocode_search")
    def test_geocode(self, geocode_search):
        geocode_search.return_value = [{"name": "Galway"}]

        response = function_app.geocode(
            request("geocode", {"q": "Galway", "limit": "3"})
        )
        payload = json.loads(response.get_body())

        self.assertEqual(response.status_code, 200)
        self.assertEqual(payload, {"results": [{"name": "Galway"}]})
        geocode_search.assert_called_once_with("Galway", limit=3)

    def test_geocode_rejects_missing_query(self):
        response = function_app.geocode(request("geocode"))
        payload = json.loads(response.get_body())

        self.assertEqual(response.status_code, 400)
        self.assertIn("query parameter 'q'", payload["error"])

    @patch("function_app.generate_location_forecast")
    def test_forecast(self, generate_location_forecast):
        generate_location_forecast.return_value = {"location": {"name": "Wicklow Head"}}

        response = function_app.forecast(
            request(
                "forecast",
                {
                    "lat": "52.96544",
                    "lon": "-6.00233",
                    "name": "Wicklow Head",
                    "hours": "96",
                },
            )
        )
        payload = json.loads(response.get_body())

        self.assertEqual(response.status_code, 200)
        self.assertEqual(payload["location"]["name"], "Wicklow Head")
        generate_location_forecast.assert_called_once_with(
            52.96544,
            -6.00233,
            "Wicklow Head",
            forecast_hours=96,
        )

    @patch("function_app.generate_location_forecast")
    def test_forecast_hides_unexpected_error_details(self, generate_location_forecast):
        generate_location_forecast.side_effect = RuntimeError("private detail")

        response = function_app.forecast(
            request(
                "forecast",
                {
                    "lat": "52.96544",
                    "lon": "-6.00233",
                },
            )
        )
        payload = json.loads(response.get_body())

        self.assertEqual(response.status_code, 500)
        self.assertEqual(payload["error"], "Internal forecast service error.")
        self.assertNotIn("private detail", response.get_body().decode("utf-8"))


if __name__ == "__main__":
    unittest.main()

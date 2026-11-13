"""Unit test tanpa Hermes/OpenRouter hidup — mock HTTP, validasi perutean."""

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

import hermes_client
from config import HORIZONTAL_THRESHOLD_M, VERTICAL_THRESHOLD_M
from hermes_advisor_api import router


class FakeHermesResponse:
    status_code = 200
    ok = True

    def json(self):
        return {"choices": [{"message": {"content": "Penjelasan berbahasa Indonesia."}}]}


class TestHermesClient(unittest.TestCase):
    def test_reads_windows_hermes_env(self):
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp) / "hermes"
            folder.mkdir()
            (folder / ".env").write_text("# komentar\nAPI_SERVER_KEY=abc-private\n")
            with patch.dict(os.environ, {"LOCALAPPDATA": temp, "API_SERVER_KEY": ""}):
                self.assertEqual(hermes_client.get_hermes_api_key(), "abc-private")

    def test_token_not_exposed_in_response(self):
        with patch.dict(os.environ, {"API_SERVER_KEY": "secret-key"}):
            with patch("hermes_client.requests.post", return_value=FakeHermesResponse()) as post:
                result = hermes_client.ask_hermes("instruksi", "data")
                self.assertEqual(result, "Penjelasan berbahasa Indonesia.")
                kwargs = post.call_args.kwargs
                self.assertEqual(kwargs["headers"]["Authorization"], "Bearer secret-key")
                self.assertEqual(kwargs["json"]["model"], "hermes-agent")
                self.assertFalse(kwargs["json"]["stream"])

    def test_invalid_gateway_auth(self):
        class Unauthorized:
            status_code = 401
            ok = False
        with patch.dict(os.environ, {"API_SERVER_KEY": "secret-key"}):
            with patch("hermes_client.requests.post", return_value=Unauthorized()):
                with self.assertRaisesRegex(hermes_client.HermesGatewayError, "API_SERVER_KEY"):
                    hermes_client.ask_hermes("sys", "user")

    def test_provider_unavailable_text_not_success(self):
        class Unavailable:
            status_code = 200
            ok = True
            def json(self):
                return {"choices": [{"message": {"content": "Provider said: HTTP 404. model is unavailable for free"}}]}
        with patch.dict(os.environ, {"API_SERVER_KEY": "secret-key"}):
            with patch("hermes_client.requests.post", return_value=Unavailable()):
                with self.assertRaisesRegex(hermes_client.HermesGatewayError, "Model OpenRouter"):
                    hermes_client.ask_hermes("sys", "user")


class TestAdvisorRoute(unittest.TestCase):
    def setUp(self):
        app = FastAPI()
        app.include_router(router)
        self.client = TestClient(app)
        self.request = {
            "source": "demo",
            "evaluation_status": "NO_ELIGIBLE_ALTERNATIVE",
            "candidate_count": 30,
            "eligible_candidate_count": 0,
            "recommended_route_id": None,
            "original_route": {
                "route_id": "ORIGINAL",
                "potential_conflicts": 1,
                "aircraft_analyzed": 2,
                "data_quality_status": "COMPLETE_ANALYSIS",
                "route_coverage_complete": True,
            },
            "top_routes": [{
                "route_id": "RIGHT_2500_M_F30",
                "potential_conflicts": 1,
                "aircraft_analyzed": 2,
                "data_quality_status": "COMPLETE_ANALYSIS",
                "route_coverage_complete": True,
                "cpa_candidate_eligible": False,
                "conflicts": [{
                    "callsign": "DEMO-CROSS",
                    "horizontal_cpa_m": 1642.47,
                    "vertical_separation_m": 0,
                }],
            }],
        }

    @patch("hermes_advisor_api.ask_hermes", return_value="Satu konflik tetap terdeteksi.")
    def test_endpoint_success_and_facts_are_deterministic(self, mock_ask):
        r = self.client.post("/api/agent-advice", json=self.request)
        self.assertEqual(r.status_code, 200, r.text)
        payload = r.json()
        self.assertEqual(payload["facts"]["shown_candidates"], 1)
        self.assertFalse(payload["facts"]["has_eligible_in_shown"])
        self.assertEqual(payload["facts"]["original_conflicts"], 1)
        self.assertEqual(payload["advice"], "Satu konflik tetap terdeteksi.")
        self.assertIn("BAHASA INDONESIA", mock_ask.call_args.args[0])
        self.assertNotIn("flight_plan", mock_ask.call_args.args[1])
        self.assertIn("1642.47", mock_ask.call_args.args[1])
        self.assertIn(f"horizontal <={HORIZONTAL_THRESHOLD_M:g} m", mock_ask.call_args.args[1])
        self.assertIn(f"vertikal <={VERTICAL_THRESHOLD_M:g} m", mock_ask.call_args.args[1])

    def test_missing_candidates_rejected(self):
        req = {**self.request, "top_routes": []}
        r = self.client.post("/api/agent-advice", json=req)
        self.assertEqual(r.status_code, 400)

    def test_more_than_six_rejected(self):
        req = {**self.request, "top_routes": self.request["top_routes"] * 7}
        r = self.client.post("/api/agent-advice", json=req)
        self.assertEqual(r.status_code, 422)

    @patch("hermes_advisor_api.ask_hermes")
    def test_complete_zero_conflict_candidate_is_eligible(self, mock_ask):
        mock_ask.return_value = "Tanpa konflik dalam horizon yang diuji."
        req = {**self.request, "top_routes": [{
            **self.request["top_routes"][0],
            "potential_conflicts": 0,
            "cpa_candidate_eligible": True,
            "conflicts": [],
        }]}
        payload = self.client.post("/api/agent-advice", json=req).json()
        self.assertTrue(payload["facts"]["has_eligible_in_shown"])


if __name__ == "__main__":
    unittest.main()

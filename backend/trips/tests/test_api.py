"""
Integration tests for Trips API endpoints.
Tests /api/v1/health/ and /api/v1/trips/route-analysis against SRS contracts.
"""
from django.test import TestCase


class TestTripsAPI(TestCase):
    def test_health_endpoint(self):
        resp = self.client.get("/api/v1/health/")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert "providers" in data

    def test_route_analysis_success(self):
        payload = {
            "origin": {"query": "Denver, CO"},
            "destination": {"query": "Chicago, IL"},
            "departure_at": "2026-11-02T08:00:00-07:00",
            "load_weight_lb": 42000,
            "checkpoint_spacing_miles": 25,
        }
        resp = self.client.post(
            "/api/v1/trips/route-analysis",
            data=payload,
            content_type="application/json",
        )
        assert resp.status_code == 200
        data = resp.json()

        assert "request_id" in data
        assert "recommended_route_id" in data
        assert len(data["routes"]) >= 1

        # Check recommended route
        rec_id = data["recommended_route_id"]
        rec_route = next((r for r in data["routes"] if r["route_id"] == rec_id), None)
        assert rec_route is not None
        assert rec_route["is_recommended"] is True
        assert rec_route["rank"] == 1

        # Check checkpoints structure
        checkpoints = rec_route["checkpoints"]
        assert len(checkpoints) >= 2
        for cp in checkpoints:
            assert "checkpoint_id" in cp
            assert "eta" in cp
            assert "weather" in cp
            assert "risk" in cp
            assert cp["risk"]["level"] in ["LOW", "MODERATE", "HIGH", "SEVERE", "NO_TRAVEL", "UNKNOWN"]

        # Check risk summary
        summary = rec_route["risk_summary"]
        for key in ["no_travel_miles", "severe_miles", "high_miles", "moderate_miles", "low_miles", "average_risk_score"]:
            assert key in summary

        # Check metadata
        assert "provider_metadata" in data
        assert "weather_source" in data["provider_metadata"]

    def test_validation_error_negative_weight(self):
        payload = {
            "origin": {"query": "Denver, CO"},
            "destination": {"query": "Chicago, IL"},
            "departure_at": "2026-11-02T08:00:00-07:00",
            "load_weight_lb": -500,
            "checkpoint_spacing_miles": 25,
        }
        resp = self.client.post(
            "/api/v1/trips/route-analysis",
            data=payload,
            content_type="application/json",
        )
        assert resp.status_code == 400
        data = resp.json()
        assert "error" in data
        assert data["error"]["code"] == "VALIDATION_ERROR"
        assert any(d["field"] == "load_weight_lb" for d in data["error"]["details"])

    def test_validation_error_missing_location(self):
        payload = {
            "origin": {"query": ""},
            "destination": {"query": "Chicago, IL"},
            "departure_at": "2026-11-02T08:00:00-07:00",
            "load_weight_lb": 35000,
        }
        resp = self.client.post(
            "/api/v1/trips/route-analysis",
            data=payload,
            content_type="application/json",
        )
        assert resp.status_code == 400
        data = resp.json()
        assert data["error"]["code"] == "VALIDATION_ERROR"


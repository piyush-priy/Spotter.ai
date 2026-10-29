"""Sprint 0 smoke tests — verify the app boots and health endpoint works."""
import pytest
from django.test import TestCase
from django.urls import reverse


class TestHealthEndpoint(TestCase):
    def test_health_returns_200(self):
        response = self.client.get("/api/v1/health/")
        assert response.status_code == 200

    def test_health_response_shape(self):
        response = self.client.get("/api/v1/health/")
        data = response.json()
        assert data["status"] == "ok"
        assert "providers" in data
        for provider in ("geocoding", "routing", "weather"):
            assert provider in data["providers"]

    def test_route_analysis_stub_returns_501(self):
        response = self.client.post(
            "/api/v1/trips/route-analysis",
            data={},
            content_type="application/json",
        )
        assert response.status_code == 501
        data = response.json()
        assert data["error"]["code"] == "NOT_IMPLEMENTED"
        assert "request_id" in data["error"]


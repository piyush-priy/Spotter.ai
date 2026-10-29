"""Smoke tests — verify the app boots and health endpoint works."""
from django.test import TestCase


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

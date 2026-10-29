"""
Unit tests for Checkpoint Generation and ETA interpolation.
Covers SRS Section 5.3 (FR-020 to FR-025).
"""
from datetime import datetime, timezone
import pytest
from trips.engine.checkpoints import (
    haversine_miles,
    generate_checkpoints,
)


class TestCheckpoints:
    def test_haversine_distance(self):
        # Denver (39.7392, -104.9903) to Colorado Springs (38.8339, -104.8214) is approx 65-70 miles
        d = haversine_miles(39.7392, -104.9903, 38.8339, -104.8214)
        assert 60.0 < d < 75.0

    def test_checkpoint_spacing_and_endpoints(self):
        # A simple linear polyline of 100 miles
        departure = datetime(2026, 11, 2, 8, 0, 0, tzinfo=timezone.utc)
        coords = [
            [40.0, -100.0],
            [40.0, -99.0],
            [40.0, -98.0],
        ]
        cps = generate_checkpoints(
            route_id="test-route",
            coordinates=coords,
            total_distance_miles=100.0,
            total_duration_seconds=7200,  # 2 hours
            departure_at=departure,
            spacing_miles=25,
        )

        assert len(cps) >= 4
        # Origin must be exact 0 miles
        assert cps[0]["distance_from_origin_miles"] == 0.0
        assert cps[0]["eta_quality"] == "EXACT"
        assert cps[0]["sequence"] == 0

        # Destination must be exact 100 miles
        assert cps[-1]["distance_from_origin_miles"] == 100.0
        assert cps[-1]["eta_quality"] == "EXACT"

        # Checkpoints in between are interpolated
        for cp in cps[1:-1]:
            assert cp["eta_quality"] == "INTERPOLATED"
            assert 0.0 < cp["distance_from_origin_miles"] < 100.0

        # Destination ETA should be departure + 2 hours
        assert cps[-1]["eta"] == "2026-11-02T10:00:00+00:00"


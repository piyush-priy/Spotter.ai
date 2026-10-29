"""
Unit tests for Route Aggregation and Deterministic Lexicographic Ranking.
Covers SRS Section 7.5 and Acceptance Criteria AC-006.
"""
import pytest
from trips.engine.ranking import (
    aggregate_route_risk,
    compute_ranking_tuple,
    rank_routes,
)


class TestRouteRiskAggregation:
    def test_aggregate_segments(self):
        checkpoints = [
            {"sequence": 0, "distance_from_origin_miles": 0.0, "risk": {"level": "LOW"}},
            {"sequence": 1, "distance_from_origin_miles": 25.0, "risk": {"level": "LOW"}},
            {"sequence": 2, "distance_from_origin_miles": 50.0, "risk": {"level": "MODERATE"}},
            {"sequence": 3, "distance_from_origin_miles": 75.0, "risk": {"level": "HIGH"}},
            {"sequence": 4, "distance_from_origin_miles": 100.0, "risk": {"level": "SEVERE"}},
        ]
        summary = aggregate_route_risk(checkpoints, total_distance_miles=100.0)
        assert summary["low_miles"] == 25.0
        assert summary["moderate_miles"] == 25.0
        assert summary["high_miles"] == 25.0
        assert summary["severe_miles"] == 25.0
        assert summary["no_travel_miles"] == 0.0
        # (0*25 + 1*25 + 2*25 + 3*25) / 100 = 150 / 100 = 1.50
        assert summary["average_risk_score"] == 1.50

    def test_unknown_miles_excluded_from_average_score(self):
        checkpoints = [
            {"sequence": 0, "distance_from_origin_miles": 0.0, "risk": {"level": "LOW"}},
            {"sequence": 1, "distance_from_origin_miles": 25.0, "risk": {"level": "LOW"}},
            {"sequence": 2, "distance_from_origin_miles": 50.0, "risk": {"level": "UNKNOWN"}},
        ]
        summary = aggregate_route_risk(checkpoints, total_distance_miles=50.0)
        assert summary["low_miles"] == 25.0
        assert summary["unknown_miles"] == 25.0
        # Only scored 25 miles with score 0 -> avg is 0.0
        assert summary["average_risk_score"] == 0.0


class TestRouteRanking:
    """
    AC-006:
    Given three routes; when route metrics differ; then ranking follows:
    (1) No Travel gate, (2) Severe miles, (3) High miles, (4) Average risk, (5) Duration, (6) Route ID
    """

    def test_ac_006_ranking_dimensions(self):
        # Route A: Has 5.0 Severe miles, but fast (1000s)
        route_a = {
            "route_id": "route-a",
            "duration_seconds": 1000,
            "risk_summary": {
                "no_travel_miles": 0.0,
                "severe_miles": 5.0,
                "high_miles": 0.0,
                "average_risk_score": 0.4,
            },
        }

        # Route B: 0 Severe miles, 10.0 High miles, duration 1500s
        # Should beat Route A because fewest Severe miles is preferred
        route_b = {
            "route_id": "route-b",
            "duration_seconds": 1500,
            "risk_summary": {
                "no_travel_miles": 0.0,
                "severe_miles": 0.0,
                "high_miles": 10.0,
                "average_risk_score": 0.3,
            },
        }

        # Route C: Contains No Travel miles (even if very short)
        # Should be ranked worst due to safety gate
        route_c = {
            "route_id": "route-c",
            "duration_seconds": 800,
            "risk_summary": {
                "no_travel_miles": 2.0,
                "severe_miles": 0.0,
                "high_miles": 0.0,
                "average_risk_score": 0.1,
            },
        }

        ranked = rank_routes([route_a, route_b, route_c])

        assert ranked[0]["route_id"] == "route-b"
        assert ranked[0]["rank"] == 1
        assert ranked[0]["is_recommended"] is True

        assert ranked[1]["route_id"] == "route-a"
        assert ranked[1]["rank"] == 2
        assert ranked[1]["is_recommended"] is False

        assert ranked[2]["route_id"] == "route-c"
        assert ranked[2]["rank"] == 3
        assert ranked[2]["is_recommended"] is False

    def test_tie_breaking_by_route_id(self):
        # Identical metrics tie-breaker
        r1 = {
            "route_id": "route-2",
            "duration_seconds": 2000,
            "risk_summary": {
                "no_travel_miles": 0.0,
                "severe_miles": 0.0,
                "high_miles": 0.0,
                "average_risk_score": 0.0,
            },
        }
        r2 = {
            "route_id": "route-1",
            "duration_seconds": 2000,
            "risk_summary": {
                "no_travel_miles": 0.0,
                "severe_miles": 0.0,
                "high_miles": 0.0,
                "average_risk_score": 0.0,
            },
        }

        ranked = rank_routes([r1, r2])
        assert ranked[0]["route_id"] == "route-1"
        assert ranked[1]["route_id"] == "route-2"


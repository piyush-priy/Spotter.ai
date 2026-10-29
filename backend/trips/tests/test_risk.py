"""
Unit tests for Risk Engine and Load Escalation Rules.
Validates the exact boundary test matrix and acceptance criteria from SRS Section 7 and Section 11.
"""
import pytest
from trips.engine.risk import (
    classify_wind,
    classify_rain,
    classify_snow,
    apply_load_escalation,
    evaluate_checkpoint_risk,
)


class TestWindBoundaries:
    """SRS Section 11 Wind Boundary Tests: 24.99, 25, 34.99, 35, 44.99, 45, 54.99, 55 mph"""

    def test_wind_boundaries(self):
        assert classify_wind(24.99)[0] == "LOW"
        assert classify_wind(25.0)[0] == "MODERATE"
        assert classify_wind(34.99)[0] == "MODERATE"
        assert classify_wind(35.0)[0] == "HIGH"
        assert classify_wind(44.99)[0] == "HIGH"
        assert classify_wind(45.0)[0] == "SEVERE"
        assert classify_wind(54.99)[0] == "SEVERE"
        assert classify_wind(55.0)[0] == "NO_TRAVEL"
        assert classify_wind(70.0)[0] == "NO_TRAVEL"

    def test_wind_unknown_and_invalid(self):
        assert classify_wind(None)[0] == "UNKNOWN"
        assert classify_wind(-5.0)[0] == "UNKNOWN"


class TestRainBoundaries:
    """SRS Section 11 Rain Boundary Tests: 0.09, 0.10, 0.24, 0.25, 0.49, 0.50, 1.00, 1.01 in/hr"""

    def test_rain_boundaries(self):
        assert classify_rain(0.09)[0] == "LOW"
        assert classify_rain(0.10)[0] == "MODERATE"
        assert classify_rain(0.24)[0] == "MODERATE"
        assert classify_rain(0.25)[0] == "HIGH"
        assert classify_rain(0.49)[0] == "HIGH"
        assert classify_rain(0.50)[0] == "SEVERE"
        assert classify_rain(1.00)[0] == "SEVERE"
        assert classify_rain(1.01)[0] == "NO_TRAVEL"
        assert classify_rain(2.50)[0] == "NO_TRAVEL"

    def test_rain_unknown_and_invalid(self):
        assert classify_rain(None)[0] == "UNKNOWN"
        assert classify_rain(-0.1)[0] == "UNKNOWN"


class TestSnowBoundaries:
    """SRS Section 11 Snow Boundary Tests: 0.49, 0.50, 0.99, 1.00, 1.99, 2.00, 3.00, 3.01 in/hr"""

    def test_snow_boundaries(self):
        assert classify_snow(0.49)[0] == "LOW"
        assert classify_snow(0.50)[0] == "MODERATE"
        assert classify_snow(0.99)[0] == "MODERATE"
        assert classify_snow(1.00)[0] == "HIGH"
        assert classify_snow(1.99)[0] == "HIGH"
        assert classify_snow(2.00)[0] == "SEVERE"
        assert classify_snow(3.00)[0] == "SEVERE"
        assert classify_snow(3.01)[0] == "NO_TRAVEL"
        assert classify_snow(5.00)[0] == "NO_TRAVEL"

    def test_snow_unknown_and_invalid(self):
        assert classify_snow(None)[0] == "UNKNOWN"
        assert classify_snow(-1.0)[0] == "UNKNOWN"


class TestLoadEscalationRules:
    """
    SRS Section 7.2 & 11 Load Rules:
    - Wind >= 55 mph -> No Travel (any load)
    - Wind 45-54 mph & load > 30,000 lb -> No Travel
    - Wind 35-44 mph & load > 40,000 lb -> Severe
    - Strict greater-than boundary checks: 30,000 vs 30,000.01 and 40,000 vs 40,000.01
    """

    def test_wind_55_any_load_is_no_travel(self):
        # AC-004: Given a route with 55 mph wind and any load -> No Travel
        level, rule = apply_load_escalation(55.0, 10000.0, "LOW")
        assert level == "NO_TRAVEL"
        assert rule is not None

        level, rule = apply_load_escalation(60.0, 45000.0, "LOW")
        assert level == "NO_TRAVEL"

    def test_wind_45_to_54_with_load_boundary_30000(self):
        # Weight exactly 30,000 does NOT trigger escalation
        level_exact, rule_exact = apply_load_escalation(50.0, 30000.0, "SEVERE")
        assert level_exact == "SEVERE"
        assert rule_exact is None

        # Weight 30,000.01 DOES trigger escalation to NO_TRAVEL (AC-003)
        level_over, rule_over = apply_load_escalation(50.0, 30000.01, "SEVERE")
        assert level_over == "NO_TRAVEL"
        assert rule_over is not None

    def test_wind_35_to_44_with_load_boundary_40000(self):
        # Weight exactly 40,000 does NOT trigger escalation
        level_exact, rule_exact = apply_load_escalation(38.0, 40000.0, "HIGH")
        assert level_exact == "HIGH"
        assert rule_exact is None

        # Weight 40,000.01 DOES trigger escalation to SEVERE (AC-002)
        level_over, rule_over = apply_load_escalation(38.0, 40000.01, "HIGH")
        assert level_over == "SEVERE"
        assert rule_over is not None

    def test_load_rule_never_downgrades(self):
        # If already SEVERE due to snow (2.5 in/hr), 38 mph wind + light load does NOT downgrade
        level, _ = apply_load_escalation(38.0, 20000.0, "SEVERE")
        assert level == "SEVERE"


class TestCheckpointEvaluation:
    """Acceptance Criteria End-to-End Evaluation Tests"""

    def test_ac_002_wind_35_load_42000(self):
        # AC-002: Given 35 mph wind; when load is 42,000 lb; then checkpoint is Severe with load-rule explanation
        res = evaluate_checkpoint_risk(
            wind_mph=35.0, rain_in_hr=0.0, snow_in_hr=0.0, load_weight_lb=42000.0
        )
        assert res["level"] == "SEVERE"
        assert res["load_rule_applied"] is not None
        assert any("Load rule" in r for r in res["reasons"])

    def test_ac_003_wind_50_load_31000(self):
        # AC-003: Given 50 mph wind and load 31,000 lb; then checkpoint is No Travel
        res = evaluate_checkpoint_risk(
            wind_mph=50.0, rain_in_hr=0.0, snow_in_hr=0.0, load_weight_lb=31000.0
        )
        assert res["level"] == "NO_TRAVEL"
        assert res["load_rule_applied"] is not None

    def test_ac_004_wind_55_any_load(self):
        # AC-004: Given 55 mph wind and any load; then checkpoint is No Travel
        res = evaluate_checkpoint_risk(
            wind_mph=55.0, rain_in_hr=0.0, snow_in_hr=0.0, load_weight_lb=15000.0
        )
        assert res["level"] == "NO_TRAVEL"

    def test_ac_005_rain_1_01_is_no_travel(self):
        # AC-005: Given 1.01 in/hr rain; then checkpoint is No Travel
        res = evaluate_checkpoint_risk(
            wind_mph=10.0, rain_in_hr=1.01, snow_in_hr=0.0, load_weight_lb=20000.0
        )
        assert res["level"] == "NO_TRAVEL"

    def test_unknown_weather_is_not_downgraded_to_low(self):
        # FR-034 / FR-047: Unavailable weather must be UNKNOWN, not LOW
        res = evaluate_checkpoint_risk(
            wind_mph=None, rain_in_hr=None, snow_in_hr=None, load_weight_lb=40000.0
        )
        assert res["level"] == "UNKNOWN"
        assert res["metric_levels"]["wind"] == "UNKNOWN"


"""
Pure risk classification and load escalation engine.

Normative rules from SRS Section 7:
Weather Thresholds:
- Wind:
    < 25 mph: LOW
    25 to < 35 mph: MODERATE
    35 to < 45 mph: HIGH
    45 to < 55 mph: SEVERE
    >= 55 mph: NO_TRAVEL
- Rain:
    < 0.10 in/hr: LOW
    0.10 to < 0.25 in/hr: MODERATE
    0.25 to < 0.50 in/hr: HIGH
    0.50 to 1.00 in/hr: SEVERE
    > 1.00 in/hr: NO_TRAVEL
- Snow:
    < 0.50 in/hr: LOW
    0.50 to < 1.00 in/hr: MODERATE
    1.00 to < 2.00 in/hr: HIGH
    2.00 to 3.00 in/hr: SEVERE
    > 3.00 in/hr: NO_TRAVEL

Load Rules:
- Wind >= 55 mph: NO_TRAVEL (any load)
- Wind 45-54.99 mph and load > 30,000 lb: NO_TRAVEL
- Wind 35-44.99 mph and load > 40,000 lb: SEVERE
- Load rules only escalate, never reduce.
- Exact weights (30,000 lb, 40,000 lb) do not trigger strict greater-than rules.
"""
from typing import Optional, Tuple, List, Dict, Any

RISK_LEVEL_ORDER = {
    "UNKNOWN": -1,
    "LOW": 0,
    "MODERATE": 1,
    "HIGH": 2,
    "SEVERE": 3,
    "NO_TRAVEL": 4,
}

ORDER_TO_LEVEL = {v: k for k, v in RISK_LEVEL_ORDER.items() if v >= 0}


def classify_wind(wind_mph: Optional[float]) -> Tuple[str, Optional[str]]:
    """Classify wind speed in mph. Returns (risk_level, explanation)."""
    if wind_mph is None:
        return "UNKNOWN", "Wind speed unavailable"
    if wind_mph < 0:
        return "UNKNOWN", "Invalid negative wind speed"
    if wind_mph >= 55.0:
        return "NO_TRAVEL", f"Wind speed {wind_mph:.1f} mph >= 55.0 mph"
    if wind_mph >= 45.0:
        return "SEVERE", f"Wind speed {wind_mph:.1f} mph (45.0-54.9 mph)"
    if wind_mph >= 35.0:
        return "HIGH", f"Wind speed {wind_mph:.1f} mph (35.0-44.9 mph)"
    if wind_mph >= 25.0:
        return "MODERATE", f"Wind speed {wind_mph:.1f} mph (25.0-34.9 mph)"
    return "LOW", f"Wind speed {wind_mph:.1f} mph (< 25.0 mph)"


def classify_rain(rain_in_hr: Optional[float]) -> Tuple[str, Optional[str]]:
    """Classify rain precipitation rate in inches/hour. Returns (risk_level, explanation)."""
    if rain_in_hr is None:
        return "UNKNOWN", "Rain rate unavailable"
    if rain_in_hr < 0:
        return "UNKNOWN", "Invalid negative rain rate"
    if rain_in_hr > 1.00:
        return "NO_TRAVEL", f"Rain rate {rain_in_hr:.2f} in/hr > 1.00 in/hr"
    if rain_in_hr >= 0.50:
        return "SEVERE", f"Rain rate {rain_in_hr:.2f} in/hr (0.50-1.00 in/hr)"
    if rain_in_hr >= 0.25:
        return "HIGH", f"Rain rate {rain_in_hr:.2f} in/hr (0.25-0.49 in/hr)"
    if rain_in_hr >= 0.10:
        return "MODERATE", f"Rain rate {rain_in_hr:.2f} in/hr (0.10-0.24 in/hr)"
    return "LOW", f"Rain rate {rain_in_hr:.2f} in/hr (< 0.10 in/hr)"


def classify_snow(snow_in_hr: Optional[float]) -> Tuple[str, Optional[str]]:
    """Classify snowfall rate in inches/hour. Returns (risk_level, explanation)."""
    if snow_in_hr is None:
        return "UNKNOWN", "Snow rate unavailable"
    if snow_in_hr < 0:
        return "UNKNOWN", "Invalid negative snow rate"
    if snow_in_hr > 3.00:
        return "NO_TRAVEL", f"Snow rate {snow_in_hr:.2f} in/hr > 3.00 in/hr"
    if snow_in_hr >= 2.00:
        return "SEVERE", f"Snow rate {snow_in_hr:.2f} in/hr (2.00-3.00 in/hr)"
    if snow_in_hr >= 1.00:
        return "HIGH", f"Snow rate {snow_in_hr:.2f} in/hr (1.00-1.99 in/hr)"
    if snow_in_hr >= 0.50:
        return "MODERATE", f"Snow rate {snow_in_hr:.2f} in/hr (0.50-0.99 in/hr)"
    return "LOW", f"Snow rate {snow_in_hr:.2f} in/hr (< 0.50 in/hr)"


def apply_load_escalation(
    wind_mph: Optional[float],
    load_weight_lb: float,
    current_level: str
) -> Tuple[str, Optional[str]]:
    """
    Apply load-specific escalation rules based on wind and cargo weight.
    Load rules only escalate risk, never reduce it.
    """
    if wind_mph is None:
        return current_level, None

    escalated_level = current_level
    rule_applied = None

    if wind_mph >= 55.0:
        if RISK_LEVEL_ORDER["NO_TRAVEL"] > RISK_LEVEL_ORDER[escalated_level]:
            escalated_level = "NO_TRAVEL"
            rule_applied = f"Wind >= 55 mph ({wind_mph:.1f} mph) mandates No Travel for any load"
    elif 45.0 <= wind_mph < 55.0 and load_weight_lb > 30000:
        if RISK_LEVEL_ORDER["NO_TRAVEL"] > RISK_LEVEL_ORDER[escalated_level]:
            escalated_level = "NO_TRAVEL"
            rule_applied = (
                f"Wind 45-54 mph ({wind_mph:.1f} mph) with load {load_weight_lb:,.0f} lb "
                "(> 30,000 lb) escalates to No Travel"
            )
    elif 35.0 <= wind_mph < 45.0 and load_weight_lb > 40000:
        if RISK_LEVEL_ORDER["SEVERE"] > RISK_LEVEL_ORDER[escalated_level]:
            escalated_level = "SEVERE"
            rule_applied = (
                f"Wind 35-44 mph ({wind_mph:.1f} mph) with load {load_weight_lb:,.0f} lb "
                "(> 40,000 lb) escalates to Severe"
            )

    return escalated_level, rule_applied


def evaluate_checkpoint_risk(
    wind_mph: Optional[float],
    rain_in_hr: Optional[float],
    snow_in_hr: Optional[float],
    load_weight_lb: float,
) -> Dict[str, Any]:
    """
    Evaluate weather metrics, determine highest severity, apply load escalation,
    and return machine-readable and human-readable explanation.
    """
    wind_level, wind_expl = classify_wind(wind_mph)
    rain_level, rain_expl = classify_rain(rain_in_hr)
    snow_level, snow_expl = classify_snow(snow_in_hr)

    metric_levels = {
        "wind": wind_level,
        "rain": rain_level,
        "snow": snow_level,
    }

    # Find highest base weather risk among known conditions
    known_levels = [
        level for level in [wind_level, rain_level, snow_level]
        if level != "UNKNOWN"
    ]

    if not known_levels:
        base_level = "UNKNOWN"
    else:
        max_order = max(RISK_LEVEL_ORDER[lvl] for lvl in known_levels)
        base_level = ORDER_TO_LEVEL[max_order]

    # Apply load escalation
    final_level, load_rule = apply_load_escalation(wind_mph, load_weight_lb, base_level)

    # Compile reasons / triggers
    reasons: List[str] = []
    if final_level == "UNKNOWN":
        reasons.append("Weather forecast unavailable at checkpoint")
    else:
        # Check which metrics match the base level or are high
        for condition, level, expl in [
            ("wind", wind_level, wind_expl),
            ("rain", rain_level, rain_expl),
            ("snow", snow_level, snow_expl),
        ]:
            if level in ("SEVERE", "NO_TRAVEL") or level == base_level and level != "LOW":
                if expl:
                    reasons.append(expl)

        if load_rule:
            reasons.append(f"Load rule: {load_rule}")

        if not reasons:
            reasons.append("All weather conditions within safe low-risk limits")

    return {
        "level": final_level,
        "base_level": base_level,
        "metric_levels": metric_levels,
        "reasons": reasons,
        "load_rule_applied": load_rule,
    }


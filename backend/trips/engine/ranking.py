"""
Route risk aggregation and deterministic lexicographic ranking engine.

Normative requirements from SRS Section 7.5:
- Segments between checkpoints assign miles to risk levels.
- Average risk score mapping:
    LOW = 0
    MODERATE = 1
    HIGH = 2
    SEVERE = 3
    NO_TRAVEL = 4
    (UNKNOWN is excluded from average risk score)
- Lexicographic ranking:
    1. No Travel exposure flag (0 for clean routes, 1 for routes with No Travel)
    2. Fewest Severe miles
    3. Fewest High miles
    4. Lowest average risk score
    5. Shortest duration (seconds)
    6. Stable tie-breaker by route_id
"""
from typing import List, Dict, Any, Tuple

NUMERIC_SCORE = {
    "LOW": 0.0,
    "MODERATE": 1.0,
    "HIGH": 2.0,
    "SEVERE": 3.0,
    "NO_TRAVEL": 4.0,
}


def aggregate_route_risk(
    checkpoints: List[Dict[str, Any]],
    total_distance_miles: float
) -> Dict[str, Any]:
    """
    Calculate miles per risk band from segments between consecutive checkpoints.
    Segment i ends at checkpoint i and assumes checkpoint i's risk level.
    """
    miles_by_band = {
        "no_travel_miles": 0.0,
        "severe_miles": 0.0,
        "high_miles": 0.0,
        "moderate_miles": 0.0,
        "low_miles": 0.0,
        "unknown_miles": 0.0,
    }

    if not checkpoints:
        return {**miles_by_band, "average_risk_score": 0.0}

    if len(checkpoints) == 1:
        # Single checkpoint route (trivial)
        level = checkpoints[0].get("risk", {}).get("level", "UNKNOWN")
        key = f"{level.lower()}_miles"
        if key in miles_by_band:
            miles_by_band[key] = round(total_distance_miles, 1)
        score = NUMERIC_SCORE.get(level, 0.0)
        return {**miles_by_band, "average_risk_score": score}

    weighted_score_sum = 0.0
    scored_miles_sum = 0.0

    for i in range(1, len(checkpoints)):
        prev_cp = checkpoints[i - 1]
        curr_cp = checkpoints[i]

        seg_miles = max(
            0.0,
            curr_cp["distance_from_origin_miles"] - prev_cp["distance_from_origin_miles"]
        )
        risk_level = curr_cp.get("risk", {}).get("level", "UNKNOWN")

        key = f"{risk_level.lower()}_miles"
        if key in miles_by_band:
            miles_by_band[key] += seg_miles

        if risk_level in NUMERIC_SCORE:
            weighted_score_sum += NUMERIC_SCORE[risk_level] * seg_miles
            scored_miles_sum += seg_miles

    for k in miles_by_band:
        miles_by_band[k] = round(miles_by_band[k], 1)

    avg_score = (
        round(weighted_score_sum / scored_miles_sum, 2)
        if scored_miles_sum > 0 else 0.0
    )

    return {
        **miles_by_band,
        "average_risk_score": avg_score,
    }


def compute_ranking_tuple(
    route: Dict[str, Any]
) -> Tuple[int, float, float, float, int, str]:
    """
    Produces the sortable ranking tuple:
    (no_travel_flag, severe_miles, high_miles, average_risk_score, duration_seconds, route_id)
    """
    summary = route["risk_summary"]
    no_travel_flag = 1 if summary.get("no_travel_miles", 0.0) > 0 else 0
    severe_miles = summary.get("severe_miles", 0.0)
    high_miles = summary.get("high_miles", 0.0)
    avg_score = summary.get("average_risk_score", 0.0)
    duration_s = route.get("duration_seconds", 0)
    route_id = route.get("route_id", "")

    return (
        no_travel_flag,
        round(severe_miles, 1),
        round(high_miles, 1),
        round(avg_score, 2),
        duration_s,
        route_id,
    )


def generate_ranking_rationale(
    route: Dict[str, Any],
    rank_position: int,
    total_routes: int
) -> str:
    """Generate clear, human-readable rationale for the route's rank position."""
    summary = route["risk_summary"]
    no_travel = summary.get("no_travel_miles", 0.0)
    severe = summary.get("severe_miles", 0.0)
    high = summary.get("high_miles", 0.0)
    duration_hrs = route.get("duration_seconds", 0) / 3600.0

    if rank_position == 1:
        if no_travel > 0:
            return (
                f"Ranked #1 of {total_routes} despite {no_travel:.1f} mi No Travel exposure "
                "because all alternative routes also have severe hazard conditions."
            )
        reasons = ["Zero No Travel conditions"]
        if severe == 0:
            reasons.append("zero Severe weather miles")
        else:
            reasons.append(f"lowest Severe exposure ({severe:.1f} mi)")

        if high == 0:
            reasons.append("zero High hazard miles")
        else:
            reasons.append(f"{high:.1f} mi High hazard")

        reasons.append(f"travel time of {duration_hrs:.1f} hrs")
        return f"Recommended route: {', '.join(reasons)}."
    else:
        if no_travel > 0:
            return (
                f"Ranked #{rank_position}: Contains {no_travel:.1f} miles of No Travel weather conditions."
            )
        return (
            f"Ranked #{rank_position}: Higher weather exposure "
            f"({severe:.1f} mi Severe, {high:.1f} mi High) or longer travel time ({duration_hrs:.1f} hrs)."
        )


def rank_routes(routes: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Sorts routes according to the normative ranking policy.
    Attaches rank, ranking tuple, and rationale to each route.
    """
    for r in routes:
        tup = compute_ranking_tuple(r)
        r["ranking"] = {"tuple": list(tup)}

    sorted_routes = sorted(routes, key=compute_ranking_tuple)

    for idx, r in enumerate(sorted_routes):
        rank = idx + 1
        r["rank"] = rank
        r["is_recommended"] = (rank == 1)
        r["rationale"] = generate_ranking_rationale(r, rank, len(sorted_routes))

    return sorted_routes


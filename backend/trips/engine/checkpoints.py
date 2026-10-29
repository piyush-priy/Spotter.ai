"""
Checkpoint generation and ETA calculation along route polylines.

Generates checkpoints at nominal spacing (10, 25, or 50 miles),
always including origin and destination, and computes projected arrival times.
"""
import math
from datetime import datetime, timedelta
from typing import List, Dict, Any, Tuple

EARTH_RADIUS_MILES = 3958.8


def haversine_miles(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculate the great-circle distance between two points in statute miles."""
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)

    a = (
        math.sin(delta_phi / 2.0) ** 2
        + math.cos(phi1) * math.cos(phi2) * (math.sin(delta_lambda / 2.0) ** 2)
    )
    c = 2.0 * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))
    return EARTH_RADIUS_MILES * c


def interpolate_coordinate(
    p1: Tuple[float, float], p2: Tuple[float, float], fraction: float
) -> Tuple[float, float]:
    """Linearly interpolate latitude and longitude between two points."""
    lat = p1[0] + (p2[0] - p1[0]) * fraction
    lon = p1[1] + (p2[1] - p1[1]) * fraction
    return (round(lat, 5), round(lon, 5))


def generate_checkpoints(
    route_id: str,
    coordinates: List[List[float]],
    total_distance_miles: float,
    total_duration_seconds: int,
    departure_at: datetime,
    spacing_miles: int = 25,
) -> List[Dict[str, Any]]:
    """
    Generate checkpoints along route geometry at nominal spacing.
    Always includes origin (0 miles) and destination (total_distance_miles).

    coordinates: list of [lat, lon] pairs.
    """
    if not coordinates:
        return []

    # If only 1 coordinate or 0 distance
    if len(coordinates) == 1 or total_distance_miles <= 0.0:
        return [
            {
                "checkpoint_id": f"{route_id}-cp-00",
                "sequence": 0,
                "distance_from_origin_miles": 0.0,
                "latitude": round(coordinates[0][0], 5),
                "longitude": round(coordinates[0][1], 5),
                "eta": departure_at.isoformat(),
                "eta_quality": "EXACT",
            }
        ]

    # Calculate cumulative distance along polyline segments
    segment_lengths: List[float] = []
    cumulative_distances: List[float] = [0.0]

    for i in range(len(coordinates) - 1):
        d = haversine_miles(
            coordinates[i][0], coordinates[i][1],
            coordinates[i + 1][0], coordinates[i + 1][1]
        )
        segment_lengths.append(d)
        cumulative_distances.append(cumulative_distances[-1] + d)

    raw_total_haversine = cumulative_distances[-1]
    # Scale factor if provider distance differs from sum of straight line segments
    scale_factor = (
        total_distance_miles / raw_total_haversine
        if raw_total_haversine > 0 else 1.0
    )

    scaled_cumulative = [d * scale_factor for d in cumulative_distances]

    # Target distances: 0, spacing, 2*spacing, ..., and destination
    target_distances: List[float] = [0.0]
    curr = float(spacing_miles)
    # Ensure intermediate points don't clash with destination (leave margin of at least 3 miles)
    while curr < (total_distance_miles - 3.0):
        target_distances.append(curr)
        curr += float(spacing_miles)

    target_distances.append(total_distance_miles)

    checkpoints: List[Dict[str, Any]] = []

    for seq, target_dist in enumerate(target_distances):
        is_origin = (seq == 0)
        is_destination = (seq == len(target_distances) - 1)

        if is_origin:
            lat, lon = coordinates[0][0], coordinates[0][1]
            eta = departure_at
            quality = "EXACT"
        elif is_destination:
            lat, lon = coordinates[-1][0], coordinates[-1][1]
            eta = departure_at + timedelta(seconds=total_duration_seconds)
            quality = "EXACT"
        else:
            # Find segment containing target_dist
            coord_idx = 0
            while (
                coord_idx < len(scaled_cumulative) - 1
                and scaled_cumulative[coord_idx + 1] < target_dist
            ):
                coord_idx += 1

            seg_start = scaled_cumulative[coord_idx]
            seg_end = scaled_cumulative[coord_idx + 1]
            seg_len = seg_end - seg_start

            if seg_len > 0:
                frac = (target_dist - seg_start) / seg_len
                frac = max(0.0, min(1.0, frac))
            else:
                frac = 0.0

            p1 = (coordinates[coord_idx][0], coordinates[coord_idx][1])
            p2 = (coordinates[coord_idx + 1][0], coordinates[coord_idx + 1][1])
            lat, lon = interpolate_coordinate(p1, p2, frac)

            # ETA based on route distance progress
            progress_ratio = target_dist / total_distance_miles if total_distance_miles > 0 else 0
            elapsed_seconds = int(progress_ratio * total_duration_seconds)
            eta = departure_at + timedelta(seconds=elapsed_seconds)
            quality = "INTERPOLATED"

        checkpoints.append({
            "checkpoint_id": f"{route_id}-cp-{seq:02d}",
            "sequence": seq,
            "distance_from_origin_miles": round(target_dist, 1),
            "latitude": round(lat, 5),
            "longitude": round(lon, 5),
            "eta": eta.isoformat(),
            "eta_quality": quality,
        })

    return checkpoints


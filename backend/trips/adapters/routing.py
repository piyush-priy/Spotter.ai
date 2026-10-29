"""
Routing adapter.
Retrieves up to three route alternatives for truck trips.
Integrates with OpenRouteService (ORS), OSRM public, and realistic corridor simulation fallback.
"""
import os
import math
import logging
from typing import List, Dict, Any, Optional
import httpx
from trips.engine.checkpoints import haversine_miles

logger = logging.getLogger(__name__)

METERS_TO_MILES = 0.000621371


class RoutingError(Exception):
    """Raised when routing fails."""
    def __init__(self, message: str, code: str = "ROUTING_PROVIDER_UNAVAILABLE"):
        super().__init__(message)
        self.code = code


def _generate_synthetic_corridors(
    origin_lat: float,
    origin_lon: float,
    dest_lat: float,
    dest_lon: float,
) -> List[Dict[str, Any]]:
    """
    Generate 3 distinct realistic route alternatives connecting origin and destination.
    Used for offline testing, demos, or when routing quotas are exceeded.
    """
    base_dist = haversine_miles(origin_lat, origin_lon, dest_lat, dest_lon) * 1.15  # road factor
    base_duration = int(base_dist / 55.0 * 3600)  # assume 55 mph avg truck speed

    # Midpoints and corridors
    mid_lat = (origin_lat + dest_lat) / 2.0
    mid_lon = (origin_lon + dest_lon) / 2.0

    # Perpendicular offset vector
    d_lat = dest_lat - origin_lat
    d_lon = dest_lon - origin_lon
    norm = math.sqrt(d_lat * d_lat + d_lon * d_lon) or 1.0
    perp_lat = -d_lon / norm
    perp_lon = d_lat / norm

    corridors = [
        {
            "route_id": "route-central",
            "name": "Central Interstate Corridor",
            "offset_factor": 0.0,
            "dist_factor": 1.0,
            "time_factor": 1.0,
        },
        {
            "route_id": "route-north",
            "name": "Northern Highway Corridor",
            "offset_factor": 0.8,
            "dist_factor": 1.06,
            "time_factor": 1.08,
        },
        {
            "route_id": "route-south",
            "name": "Southern Bypass Corridor",
            "offset_factor": -0.8,
            "dist_factor": 1.09,
            "time_factor": 1.12,
        },
    ]

    routes: List[Dict[str, Any]] = []

    for c in corridors:
        steps = 30
        coords: List[List[float]] = []
        for step in range(steps + 1):
            t = step / float(steps)
            # Quadratic bezier arc
            arc_weight = 4.0 * t * (1.0 - t)
            lat = (1.0 - t) * origin_lat + t * dest_lat + arc_weight * c["offset_factor"] * perp_lat
            lon = (1.0 - t) * origin_lon + t * dest_lon + arc_weight * c["offset_factor"] * perp_lon
            coords.append([round(lat, 5), round(lon, 5)])

        r_dist = round(base_dist * c["dist_factor"], 1)
        r_dur = int(base_duration * c["time_factor"])

        routes.append({
            "route_id": c["route_id"],
            "name": c["name"],
            "distance_miles": r_dist,
            "duration_seconds": r_dur,
            "coordinates": coords,
            "source": "simulated_truck_corridor",
        })

    return routes


async def get_route_alternatives(
    origin_lat: float,
    origin_lon: float,
    dest_lat: float,
    dest_lon: float,
    client: Optional[httpx.AsyncClient] = None,
) -> List[Dict[str, Any]]:
    """
    Obtain up to three route alternatives from origin to destination coordinates.
    Returns normalized list of routes.
    """
    ors_key = os.environ.get("ORS_API_KEY")
    owns_client = False
    if client is None:
        client = httpx.AsyncClient(timeout=10.0)
        owns_client = True

    try:
        # 1. Try OpenRouteService if API key configured
        if ors_key and "your-openrouteservice" not in ors_key:
            try:
                ors_url = "https://api.openrouteservice.org/v2/directions/driving-hgv/geojson"
                body = {
                    "coordinates": [[origin_lon, origin_lat], [dest_lon, dest_lat]],
                    "alternative_routes": {"target_count": 3},
                }
                headers = {"Authorization": ors_key, "Content-Type": "application/json"}
                resp = await client.post(ors_url, json=body, headers=headers)
                if resp.status_code == 200:
                    data = resp.json()
                    features = data.get("features", [])
                    if features:
                        routes = []
                        for i, feat in enumerate(features[:3]):
                            props = feat.get("properties", {}).get("summary", {})
                            geom = feat.get("geometry", {}).get("coordinates", [])
                            # Swap GeoJSON [lon, lat] to [lat, lon]
                            coords = [[pt[1], pt[0]] for pt in geom]
                            dist_miles = round(props.get("distance", 0.0) * METERS_TO_MILES, 1)
                            dur_secs = int(props.get("duration", 0.0))
                            routes.append({
                                "route_id": f"route-{i + 1}",
                                "name": f"ORS Route Option {i + 1}",
                                "distance_miles": dist_miles,
                                "duration_seconds": dur_secs,
                                "coordinates": coords,
                                "source": "openrouteservice",
                            })
                        if routes:
                            return routes
            except Exception as e:
                logger.warning("OpenRouteService request error: %s", e)

        # 2. Try OSRM public API with alternatives
        try:
            osrm_url = (
                f"http://router.project-osrm.org/route/v1/driving/"
                f"{origin_lon},{origin_lat};{dest_lon},{dest_lat}"
                f"?overview=full&geometries=geojson&alternatives=3"
            )
            resp = await client.get(osrm_url)
            if resp.status_code == 200:
                data = resp.json()
                raw_routes = data.get("routes", [])
                if raw_routes:
                    routes = []
                    for i, r in enumerate(raw_routes[:3]):
                        coords = [[pt[1], pt[0]] for pt in r.get("geometry", {}).get("coordinates", [])]
                        dist_miles = round(r.get("distance", 0.0) * METERS_TO_MILES, 1)
                        dur_secs = int(r.get("duration", 0.0))
                        routes.append({
                            "route_id": f"route-{i + 1}",
                            "name": f"Route Alternative {i + 1}",
                            "distance_miles": dist_miles,
                            "duration_seconds": dur_secs,
                            "coordinates": coords,
                            "source": "osrm",
                        })
                    return routes
        except Exception as e:
            logger.warning("OSRM public routing error: %s", e)

        # 3. Fallback to synthetic corridors (guarantees 3 distinct viable options)
        logger.info("Using simulated corridors for route alternatives")
        return _generate_synthetic_corridors(origin_lat, origin_lon, dest_lat, dest_lon)

    finally:
        if owns_client:
            await client.aclose()


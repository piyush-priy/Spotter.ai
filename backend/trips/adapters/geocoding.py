"""
Geocoding adapter.
Resolves human-readable addresses or city names to latitude and longitude.
Supports OpenCage, Nominatim (OSM), and curated fallback fixtures.
"""
import os
import logging
from typing import Dict, Any, Optional
import httpx

logger = logging.getLogger(__name__)

# Curated fallback coordinates for reliable offline demo / testing
DEMO_COORDINATES: Dict[str, Dict[str, Any]] = {
    "denver": {"latitude": 39.7392, "longitude": -104.9903, "formatted_address": "Denver, CO, USA"},
    "chicago": {"latitude": 41.8781, "longitude": -87.6298, "formatted_address": "Chicago, IL, USA"},
    "dallas": {"latitude": 32.7767, "longitude": -96.7970, "formatted_address": "Dallas, TX, USA"},
    "atlanta": {"latitude": 33.7490, "longitude": -84.3880, "formatted_address": "Atlanta, GA, USA"},
    "seattle": {"latitude": 47.6062, "longitude": -122.3321, "formatted_address": "Seattle, WA, USA"},
    "los angeles": {"latitude": 34.0522, "longitude": -118.2437, "formatted_address": "Los Angeles, CA, USA"},
    "new york": {"latitude": 40.7128, "longitude": -74.0060, "formatted_address": "New York, NY, USA"},
}


class GeocodingError(Exception):
    """Raised when geocoding fails."""
    def __init__(self, message: str, code: str = "GEOCODING_FAILED"):
        super().__init__(message)
        self.code = code


async def geocode_location(query: str, client: Optional[httpx.AsyncClient] = None) -> Dict[str, Any]:
    """
    Resolve query string to {latitude, longitude, formatted_address, source}.
    """
    query_clean = query.strip()
    if not query_clean:
        raise GeocodingError("Location query cannot be empty", code="INVALID_INPUT")

    query_lower = query_clean.lower()
    for key, coords in DEMO_COORDINATES.items():
        if key in query_lower:
            logger.info("Resolved %s via fixture coordinates", query_clean)
            return {**coords, "source": "fixture"}

    opencage_key = os.environ.get("OPENCAGE_API_KEY")
    owns_client = False
    if client is None:
        client = httpx.AsyncClient(timeout=8.0)
        owns_client = True

    try:
        # 1. Try OpenCage if key configured and not placeholder
        if opencage_key and "your-opencage" not in opencage_key:
            try:
                resp = await client.get(
                    "https://api.opencagedata.com/geocode/v1/json",
                    params={"q": query_clean, "key": opencage_key, "limit": 1},
                )
                if resp.status_code == 200:
                    data = resp.json()
                    results = data.get("results", [])
                    if results:
                        geom = results[0]["geometry"]
                        return {
                            "latitude": float(geom["lat"]),
                            "longitude": float(geom["lng"]),
                            "formatted_address": results[0].get("formatted", query_clean),
                            "source": "opencage",
                        }
            except Exception as e:
                logger.warning("OpenCage geocode error for '%s': %s", query_clean, e)

        # 2. Try Nominatim (OSM) as standard open-source provider
        try:
            resp = await client.get(
                "https://nominatim.openstreetmap.org/search",
                params={"q": query_clean, "format": "json", "limit": 1},
                headers={"User-Agent": "SpotterWeatherTruckRouting/1.0"},
            )
            if resp.status_code == 200:
                data = resp.json()
                if data and len(data) > 0:
                    return {
                        "latitude": float(data[0]["lat"]),
                        "longitude": float(data[0]["lon"]),
                        "formatted_address": data[0].get("display_name", query_clean),
                        "source": "nominatim",
                    }
        except Exception as e:
            logger.warning("Nominatim geocode error for '%s': %s", query_clean, e)

        raise GeocodingError(
            f"Could not resolve location '{query_clean}'. Please verify address or city name.",
            code="LOCATION_NOT_FOUND",
        )
    finally:
        if owns_client:
            await client.aclose()


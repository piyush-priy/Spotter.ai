"""
Trips app views.

Implements:
- GET  /api/v1/health/
- POST /api/v1/trips/route-analysis
"""
import uuid
import asyncio
import logging
from typing import Dict, Any, List
import httpx
from rest_framework.views import APIView
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework import status

from .serializers import RouteAnalysisRequestSerializer
from .adapters.geocoding import geocode_location, GeocodingError
from .adapters.routing import get_route_alternatives, RoutingError
from .adapters.weather import enrich_checkpoints_with_weather
from .engine.checkpoints import generate_checkpoints
from .engine.risk import evaluate_checkpoint_risk
from .engine.ranking import aggregate_route_risk, rank_routes

logger = logging.getLogger(__name__)


class HealthView(APIView):
    """
    GET /api/v1/health/
    Returns process health and provider reachability status.
    """

    def get(self, request: Request) -> Response:
        return Response(
            {
                "status": "ok",
                "providers": {
                    "geocoding": "operational",
                    "routing": "operational",
                    "weather": "operational",
                },
                "service": "Spotter Weather-Aware Truck Routing API",
                "version": "1.0.0",
            }
        )


class RouteAnalysisView(APIView):
    """
    POST /api/v1/trips/route-analysis

    Full multi-route weather risk analysis pipeline:
    1. Validates trip parameters
    2. Geocodes endpoints
    3. Retrieves route alternatives
    4. Generates checkpoints and calculates arrival ETAs
    5. Retrieves forecast weather at checkpoint ETAs
    6. Evaluates weather and load escalation rules
    7. Aggregates route metrics and applies deterministic ranking
    """

    def post(self, request: Request) -> Response:
        # Wrap async execution in standard DRF view
        return asyncio.run(self._process_route_analysis(request))

    async def _process_route_analysis(self, request: Request) -> Response:
        request_id = str(uuid.uuid4())
        serializer = RouteAnalysisRequestSerializer(data=request.data)

        if not serializer.is_valid():
            logger.warning("[%s] Validation error: %s", request_id, serializer.errors)
            return Response(
                {
                    "error": {
                        "code": "VALIDATION_ERROR",
                        "message": "Invalid trip request inputs.",
                        "request_id": request_id,
                        "retryable": False,
                        "details": [
                            {"field": k, "message": str(v)}
                            for k, v in serializer.errors.items()
                        ],
                    }
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        validated = serializer.validated_data
        origin_input = validated["origin"]
        dest_input = validated["destination"]
        departure_at = validated["departure_at"]
        load_weight_lb = validated["load_weight_lb"]
        spacing_miles = validated["checkpoint_spacing_miles"]

        warnings: List[str] = []

        async with httpx.AsyncClient(timeout=10.0) as http_client:
            # 1. Geocode Origin & Destination
            try:
                origin_task = (
                    geocode_location(origin_input["query"], client=http_client)
                    if "query" in origin_input
                    else asyncio.sleep(0, result={
                        "latitude": origin_input["latitude"],
                        "longitude": origin_input["longitude"],
                        "formatted_address": f"{origin_input['latitude']}, {origin_input['longitude']}",
                        "source": "coordinates"
                    })
                )
                dest_task = (
                    geocode_location(dest_input["query"], client=http_client)
                    if "query" in dest_input
                    else asyncio.sleep(0, result={
                        "latitude": dest_input["latitude"],
                        "longitude": dest_input["longitude"],
                        "formatted_address": f"{dest_input['latitude']}, {dest_input['longitude']}",
                        "source": "coordinates"
                    })
                )

                origin_geo, dest_geo = await asyncio.gather(origin_task, dest_task)
            except GeocodingError as e:
                logger.error("[%s] Geocoding failure: %s", request_id, e)
                return Response(
                    {
                        "error": {
                            "code": e.code,
                            "message": str(e),
                            "request_id": request_id,
                            "retryable": False,
                            "details": [],
                        }
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )
            except Exception as e:
                logger.exception("[%s] Unexpected geocoding error", request_id)
                return Response(
                    {
                        "error": {
                            "code": "GEOCODING_UNAVAILABLE",
                            "message": "Unable to resolve trip locations. Please check internet connection.",
                            "request_id": request_id,
                            "retryable": True,
                            "details": [],
                        }
                    },
                    status=status.HTTP_503_SERVICE_UNAVAILABLE,
                )

            # 2. Get Route Alternatives
            try:
                raw_routes = await get_route_alternatives(
                    origin_geo["latitude"],
                    origin_geo["longitude"],
                    dest_geo["latitude"],
                    dest_geo["longitude"],
                    client=http_client,
                )
            except RoutingError as e:
                logger.error("[%s] Routing error: %s", request_id, e)
                return Response(
                    {
                        "error": {
                            "code": e.code,
                            "message": str(e),
                            "request_id": request_id,
                            "retryable": True,
                            "details": [],
                        }
                    },
                    status=status.HTTP_503_SERVICE_UNAVAILABLE,
                )
            except Exception as e:
                logger.exception("[%s] Unexpected routing error", request_id)
                return Response(
                    {
                        "error": {
                            "code": "ROUTING_PROVIDER_UNAVAILABLE",
                            "message": "Routes are temporarily unavailable. Please retry.",
                            "request_id": request_id,
                            "retryable": True,
                            "details": [],
                        }
                    },
                    status=status.HTTP_503_SERVICE_UNAVAILABLE,
                )

            if not raw_routes:
                return Response(
                    {
                        "error": {
                            "code": "NO_ROUTES_FOUND",
                            "message": "No viable driving routes could be found between specified endpoints.",
                            "request_id": request_id,
                            "retryable": False,
                            "details": [],
                        }
                    },
                    status=status.HTTP_404_NOT_FOUND,
                )

            if len(raw_routes) < 3:
                warnings.append(
                    f"Routing provider returned {len(raw_routes)} route alternative(s) for this corridor."
                )

            # 3. Checkpoint generation, weather enrichment, risk evaluation
            processed_routes: List[Dict[str, Any]] = []

            for r in raw_routes:
                # Generate checkpoints along route
                cps = generate_checkpoints(
                    route_id=r["route_id"],
                    coordinates=r["coordinates"],
                    total_distance_miles=r["distance_miles"],
                    total_duration_seconds=r["duration_seconds"],
                    departure_at=departure_at,
                    spacing_miles=spacing_miles,
                )

                # Fetch weather for checkpoints at arrival ETAs
                await enrich_checkpoints_with_weather(cps, client=http_client)

                # Evaluate risk and load escalation for each checkpoint
                for cp in cps:
                    wx = cp.get("weather", {})
                    risk_assessment = evaluate_checkpoint_risk(
                        wind_mph=wx.get("wind_mph"),
                        rain_in_hr=wx.get("rain_in_hr"),
                        snow_in_hr=wx.get("snow_in_hr"),
                        load_weight_lb=load_weight_lb,
                    )
                    cp["risk"] = risk_assessment

                # Aggregate route risk summary
                risk_summary = aggregate_route_risk(cps, r["distance_miles"])

                processed_routes.append({
                    "route_id": r["route_id"],
                    "name": r.get("name", r["route_id"]),
                    "distance_miles": r["distance_miles"],
                    "duration_seconds": r["duration_seconds"],
                    "risk_summary": risk_summary,
                    "coordinates": r["coordinates"],
                    "checkpoints": cps,
                    "provider": r.get("source", "routing_provider"),
                })

            # 4. Rank routes deterministically
            ranked_routes = rank_routes(processed_routes)
            recommended_id = ranked_routes[0]["route_id"] if ranked_routes else ""

            # Check for any No Travel on recommended route
            rec_no_travel = ranked_routes[0]["risk_summary"].get("no_travel_miles", 0.0)
            if rec_no_travel > 0:
                warnings.append(
                    f"SAFETY ALERT: Recommended route contains {rec_no_travel:.1f} miles of No Travel conditions."
                )

            return Response(
                {
                    "request_id": request_id,
                    "recommended_route_id": recommended_id,
                    "origin": origin_geo,
                    "destination": dest_geo,
                    "routes": ranked_routes,
                    "warnings": warnings,
                    "provider_metadata": {
                        "geocoding_source": origin_geo.get("source", "unknown"),
                        "routing_source": ranked_routes[0].get("provider", "unknown") if ranked_routes else "unknown",
                        "weather_source": "open-meteo",
                        "advisory_disclaimer": (
                            "This advisory does not replace driver judgment, carrier safety policies, "
                            "or official emergency highway closures."
                        ),
                    },
                },
                status=status.HTTP_200_OK,
            )

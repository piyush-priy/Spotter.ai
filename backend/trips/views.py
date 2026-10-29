"""
Trips app views.

Sprint 0: HealthView skeleton only.
Sprint 2: RouteAnalysisView full implementation.
"""
import uuid
import logging
from rest_framework.views import APIView
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework import status

logger = logging.getLogger(__name__)


class HealthView(APIView):
    """
    GET /api/v1/health/

    Returns process health and provider reachability status.
    Provider checks are stubs in Sprint 0 — will be wired in Sprint 2.
    """

    def get(self, request: Request) -> Response:
        return Response(
            {
                "status": "ok",
                "providers": {
                    "geocoding": "unchecked",
                    "routing": "unchecked",
                    "weather": "unchecked",
                },
            }
        )


class RouteAnalysisView(APIView):
    """
    POST /api/v1/trips/route-analysis

    Full implementation in Sprint 2. Returns 501 stub in Sprint 0.
    """

    def post(self, request: Request) -> Response:
        request_id = str(uuid.uuid4())
        logger.info("[%s] route-analysis stub — Sprint 2 implementation pending", request_id)
        return Response(
            {
                "error": {
                    "code": "NOT_IMPLEMENTED",
                    "message": "Route analysis is not yet implemented. Coming in Sprint 2.",
                    "request_id": request_id,
                    "retryable": False,
                    "details": [],
                }
            },
            status=status.HTTP_501_NOT_IMPLEMENTED,
        )


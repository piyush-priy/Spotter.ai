"""
Custom DRF exception handler.

Maps unhandled exceptions to the stable error contract:
{
    "error": {
        "code": str,
        "message": str,
        "request_id": str,
        "retryable": bool,
        "details": list
    }
}

Provider error bodies, secrets, and full tracebacks are NEVER forwarded to clients.
"""
import uuid
import logging
from rest_framework.views import exception_handler
from rest_framework.response import Response

logger = logging.getLogger(__name__)


def custom_exception_handler(exc, context):
    """Wrap DRF exceptions in the application error contract."""
    response = exception_handler(exc, context)

    request_id = str(uuid.uuid4())

    if response is not None:
        # DRF handled it (validation error, 404, 405, etc.)
        original_data = response.data
        response.data = {
            "error": {
                "code": _drf_status_to_code(response.status_code),
                "message": _flatten_errors(original_data),
                "request_id": request_id,
                "retryable": False,
                "details": _extract_field_details(original_data),
            }
        }
        return response

    # Unhandled exception — log full details server-side, return generic 500
    logger.exception("[%s] Unhandled exception in view", request_id, exc_info=exc)
    return Response(
        {
            "error": {
                "code": "INTERNAL_ERROR",
                "message": "An unexpected error occurred. Please try again.",
                "request_id": request_id,
                "retryable": True,
                "details": [],
            }
        },
        status=500,
    )


def _drf_status_to_code(status_code: int) -> str:
    return {
        400: "VALIDATION_ERROR",
        404: "NOT_FOUND",
        405: "METHOD_NOT_ALLOWED",
        429: "RATE_LIMITED",
        501: "NOT_IMPLEMENTED",
    }.get(status_code, "REQUEST_ERROR")


def _flatten_errors(data) -> str:
    if isinstance(data, dict):
        msgs = []
        for v in data.values():
            msgs.append(_flatten_errors(v))
        return " ".join(msgs)
    if isinstance(data, list):
        return " ".join(str(i) for i in data)
    return str(data)


def _extract_field_details(data) -> list:
    if not isinstance(data, dict):
        return []
    return [{"field": k, "message": _flatten_errors(v)} for k, v in data.items() if k != "detail"]


"""
Response helpers for AnyCompany Hotel platform.

Provides standardized API response envelopes matching the platform convention:
    Success: {"success": true, "data": {...}, "metadata": {...}}
    Error:   {"success": false, "error": {"code": "...", "message": "...", "details": {...}}}

CORS: the `Access-Control-Allow-Origin` header is set here, on every response.

A REST API's `Cors` property only configures the OPTIONS preflight (a MOCK
integration). For a Lambda *proxy* integration, the actual (non-OPTIONS)
response carries only the headers the Lambda returns — so without this header
the browser sees a 200 with data but no Allow-Origin header and blocks the page
from reading it. Emitting Allow-Origin here is what makes cross-origin reads work.

The value defaults to "*", which allows both frontends (CRS + PMS share these
handlers). "*" is safe for this API because requests authenticate with a Bearer
token in the Authorization header, not cookies; Bearer tokens are not CORS
"credentials", so wildcard origin is permitted. Override with the
CORS_ALLOW_ORIGIN env var (e.g. a specific https origin in prod). The OPTIONS
preflight is still handled by API Gateway's Cors property.
"""

import json
import os
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

# Allowed origin for the actual (proxy) responses. Defaults to "*" (matches the
# non-prod Cors config and serves both frontends); set CORS_ALLOW_ORIGIN to a
# specific origin to lock it down. See module docstring for why this lives here.
_CORS_ALLOW_ORIGIN = os.environ.get("CORS_ALLOW_ORIGIN", "*")

RESPONSE_HEADERS = {
    "Content-Type": "application/json",
    "Access-Control-Allow-Origin": _CORS_ALLOW_ORIGIN,
}


def snake_to_camel(s: str) -> str:
    """
    Convert a snake_case string to camelCase.

    Args:
        s: Snake-case string (e.g., "guest_profile_id").

    Returns:
        camelCase string (e.g., "guestProfileId").
    """
    components = s.split("_")
    return components[0] + "".join(x.title() for x in components[1:])


def transform_keys(obj: Any) -> Any:
    """
    Recursively transform all dictionary keys from snake_case to camelCase.

    Handles nested dicts, lists, and leaves non-dict/list values unchanged.

    Args:
        obj: A dict, list, or scalar value.

    Returns:
        The same structure with all dict keys converted to camelCase.
    """
    if isinstance(obj, dict):
        return {snake_to_camel(k): transform_keys(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [transform_keys(item) for item in obj]
    return obj


def _build_response(status_code: int, body: dict) -> dict:
    """
    Build a Lambda proxy integration response with standard headers.

    Args:
        status_code: HTTP status code.
        body: Response body dict to be JSON-serialized.

    Returns:
        API Gateway Lambda proxy response dict.
    """
    return {
        "statusCode": status_code,
        "headers": RESPONSE_HEADERS,
        "body": json.dumps(body, default=str),
    }


def ok(data: Any, metadata: Optional[dict] = None) -> dict:
    """
    Return a 200 OK response with the standard success envelope.

    Args:
        data: Response payload (will have keys transformed to camelCase).
        metadata: Optional metadata dict (pagination, counts, etc.).

    Returns:
        API Gateway response with status 200.
    """
    response_body = {
        "success": True,
        "data": transform_keys(data),
        "metadata": {
            "requestId": str(uuid.uuid4()),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        },
    }
    if metadata:
        response_body["metadata"].update(transform_keys(metadata))
    return _build_response(200, response_body)


def created(data: Any) -> dict:
    """
    Return a 201 Created response with the standard success envelope.

    Args:
        data: Response payload (will have keys transformed to camelCase).

    Returns:
        API Gateway response with status 201.
    """
    response_body = {
        "success": True,
        "data": transform_keys(data),
        "metadata": {
            "requestId": str(uuid.uuid4()),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        },
    }
    return _build_response(201, response_body)


def error(status_code: int, code: str, message: str, details: Optional[dict] = None) -> dict:
    """
    Return an error response with the standard error envelope.

    Args:
        status_code: HTTP status code (4xx or 5xx).
        code: Machine-readable error code (e.g., "ROOM_NOT_AVAILABLE").
        message: Human-readable error message.
        details: Optional dict with additional error context.

    Returns:
        API Gateway response with the given status code.
    """
    error_body: dict[str, Any] = {
        "code": code,
        "message": message,
    }
    if details:
        error_body["details"] = transform_keys(details)

    response_body = {
        "success": False,
        "error": error_body,
    }
    return _build_response(status_code, response_body)


def not_found(message: str = "Resource not found.") -> dict:
    """Return a 404 Not Found error response."""
    return error(404, "NOT_FOUND", message)


def forbidden(message: str = "You do not have permission to access this resource.") -> dict:
    """Return a 403 Forbidden error response."""
    return error(403, "FORBIDDEN", message)


def bad_request(message: str = "Invalid request.") -> dict:
    """Return a 400 Bad Request error response."""
    return error(400, "BAD_REQUEST", message)


def server_error(message: str = "An internal error occurred.") -> dict:
    """Return a 500 Internal Server Error response."""
    return error(500, "INTERNAL_ERROR", message)
